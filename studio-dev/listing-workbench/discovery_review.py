"""Find one evidenced review reference without changing the ranked keyword seeds."""
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import asin_reference
import importer
import review_insights
import sellersprite
import visual_studio


class SearchCards(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.cards = {}
        self.asin = ''
        self.title = False
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('data-component-type') == 's-search-result':
            asin = attrs.get('data-asin') or ''
            self.asin = asin if asin_reference.ASIN.fullmatch(asin) else ''
            self.title = False
        if tag == 'h2' and self.asin and self.asin not in self.cards:
            self.cards[self.asin] = ''
            self.title = True

    def handle_endtag(self, tag):
        if tag == 'h2':
            self.title = False

    def handle_data(self, data):
        if self.title and self.asin:
            self.cards[self.asin] += data + ' '


def original_empty(report, market, asins):
    if not isinstance(report, dict):
        return False
    sources = report.get('sources') or []
    return (report.get('market') == market and not report.get('error') and report.get('samples') == []
            and set(re.findall(asin_reference.ASIN, report.get('input') or '')) == set(asins)
            and isinstance(sources, list) and all(isinstance(source, dict) for source in sources)
            and sorted(source.get('asin', '') for source in sources) == sorted(asins)
            and all(source.get('status') == 'empty' and source.get('count') == 0
                    and source.get('pages') == 2 for source in sources))


def search_source(market, ranked):
    host = urlsplit(asin_reference.product_url(market, ranked[0]['asin'])).hostname
    for row in ranked:
        search = row.get('search') or {}
        url, query = search.get('url', ''), search.get('keyword', '')
        parts = urlsplit(url)
        if (query and parts.scheme == 'https' and parts.netloc == host and parts.path == '/s'
                and parse_qs(parts.query).get('k') == [query]):
            return {'url': url, 'keyword': query}
    raise ValueError('缺少已核实的同站点 Amazon 搜索来源，暂不能自动补评论参考')


INSTRUCTION = '''Compare each candidate's actual image with image 1, the original product.
Image 2 onwards correspond in order to candidates. Approve only a clearly similar product type,
overall structure, construction and intended use. Do not approve based on color, pattern, or title alone.
Pattern, colors or small trim may differ if the core construction matches. Reject ambiguous photos,
major construction differences, and unrelated products. Explain the visible matches and differences in Chinese.
Return JSON {"matches":[{"asin":"candidate ASIN","reason":"specific visible matches and differences"}]}
ordered by closest structure. Return an empty list if none qualify.'''


def supplement(product, original):
    selection = product.get('selectionResearch') or {}
    ranked = selection.get('rankedCompetitors') or []
    reference = selection.get('reference') or {}
    market, asin = reference.get('market'), reference.get('asin')
    if selection.get('sourceMonth') != 'cyclic-discovery' or market not in importer.MARKET_DOMAINS or not 3 <= len(ranked) <= 5:
        raise ValueError('仅支持已核实竞品的循环选品档案')
    asins = [row['asin'] for row in ranked]
    if not original_empty(original, market, asins):
        raise ValueError('须确认原竞品评论均查询成功且无正文，才能补查')
    captured = product.get('editorAsinReference') or {}
    original_image = next(iter(captured.get('referenceImages') or []), '')
    if captured.get('asin') != asin or captured.get('market') != market or not asin_reference.media_key(original_image):
        raise ValueError('请先采集本款 ASIN 主图，用于核对竞品结构')
    search = search_source(market, ranked)
    try:
        cards = SearchCards(importer.fetch_amazon(search['url'])).cards
    except OSError as error:
        raise ValueError('Amazon 搜索暂不可读，已保留原竞品') from error
    if not cards:
        raise ValueError('Amazon 未返回可核对的搜索结果，已保留原竞品')
    excluded = {asin, captured.get('parentAsin'), *asins, *(row['parent_asin'] for row in ranked)}
    words = set(re.findall(r"[^\W_]+", captured.get('title', '').lower()))
    ordered = sorted((key for key in cards if key not in excluded),
                     key=lambda key: -len(words.intersection(re.findall(r"[^\W_]+", cards[key].lower()))))
    client = sellersprite.Client().connect()
    candidates = {}
    images = [visual_studio.encode_reference(original_image)]
    for candidate in ordered[:20]:
        detail = client.call('asin_detail', {'marketplace': market, 'asin': candidate})
        parent = detail.get('parent') or ''
        rank, category = detail.get('bsrRank'), detail.get('bsrLabel')
        image = detail.get('zoomImageUrl') or detail.get('imageUrl')
        if (detail.get('asin') != candidate or not asin_reference.ASIN.fullmatch(parent)
                or parent in excluded or type(rank) is not int or rank <= 0 or not category
                or not detail.get('ratings') or not asin_reference.media_key(image)):
            continue
        try:
            encoded = visual_studio.encode_reference(image)
        except ValueError:
            continue
        excluded.add(parent)
        candidates[candidate] = {'asin': candidate, 'parentAsin': parent, 'title': detail.get('title', ''),
                                 'market': market, 'url': asin_reference.product_url(market, candidate),
                                 'imageUrl': image, 'rank': rank, 'rankCategory': category}
        images.append(encoded)
        if len(candidates) == 4:
            break
    if not candidates:
        raise ValueError('搜索范围内没有找到有排名、可核对主图的不同父体竞品')
    result = visual_studio.model_json(INSTRUCTION, {'market': market, 'originalASIN': asin,
        'candidates': list(candidates.values())}, images, purpose='discovery_review_match')
    matches = result.get('matches')
    if not isinstance(matches, list):
        raise ValueError('模型未返回可核对的竞品结构判断')
    for match in matches[:4]:
        if not isinstance(match, dict):
            continue
        key, reason = match.get('asin'), match.get('reason')
        if not isinstance(key, str) or key not in candidates or not isinstance(reason, str) or not reason.strip():
            continue
        extra = review_insights.collect({'market': market, 'asins': key}, client=client)
        if not extra['samples']:
            if any(source.get('status') == 'failed' for source in extra['sources']):
                raise ValueError(extra['sources'][0].get('error') or '补充竞品评论查询失败，请重试')
            continue
        return {**original, 'samples': extra['samples'], 'fetchedAt': extra['fetchedAt'],
                'sources': original['sources'] + extra['sources'], 'supplement': {
                    **candidates[key], 'structureEvidence': reason.strip()[:1000], 'search': search,
                    'rankSource': 'SellerSprite MCP', 'checkedAt': datetime.now(timezone.utc).isoformat(),
                }}
    raise ValueError('未找到结构相近且有真实评论正文的竞品，已保留原竞品与关键词')
