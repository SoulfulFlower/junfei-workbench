"""Store bounded, account-scoped observations from an explicitly opened Amazon page.

Observations remain separate from selectionEvidence and can never satisfy selection gates.
"""
from datetime import datetime
from urllib.parse import urlsplit, parse_qs, parse_qsl, urlencode, urlunsplit
import re

MARKETS = {
    'amazon.com': 'US', 'amazon.co.uk': 'UK', 'amazon.de': 'DE', 'amazon.fr': 'FR',
    'amazon.it': 'IT', 'amazon.es': 'ES', 'amazon.co.jp': 'JP', 'amazon.ca': 'CA',
    'amazon.com.au': 'AU', 'amazon.in': 'IN', 'amazon.com.mx': 'MX', 'amazon.com.br': 'BR',
}
FIELDS = ('title', 'brand', 'displayedPrice', 'sellerText', 'fulfillmentText', 'dateFirstAvailable')
STOP_WORDS = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'new', 'set', 'pack', 'of', 'a', 'an', 'to'}


def _title_terms(value):
    return {term for term in re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]+', str(value).lower())
            if len(term) > 1 and term not in STOP_WORDS}


def rank_visible_results(target_title, results):
    """Sort captured search results for human review using title-token overlap only."""
    target = _title_terms(target_title)
    ranked = []
    for item in results:
        terms = _title_terms(item.get('title', ''))
        union = target | terms
        overlap = target & terms
        score = len(overlap) / len(union) if union else 0.0
        ranked.append({**item, 'lexicalScore': round(score, 3), 'sharedTerms': sorted(overlap),
                       'reviewStatus': '仅关键词排序；待人工核对主图、结构、属性及其他卖家身份'})
    return sorted(ranked, key=lambda item: (-item['lexicalScore'], item['asin']))[:10]


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('采集数据格式无效')
    asin = str(data.get('asin', '')).strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{10}', asin):
        raise ValueError('ASIN格式无效')
    market = str(data.get('marketplace', '')).strip().upper()
    if market not in set(MARKETS.values()):
        raise ValueError('Amazon站点代码无效')
    parsed = urlsplit(str(data.get('url', '')))
    host = (parsed.hostname or '').lower().removeprefix('www.')
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError('页面来源网址格式无效') from exc
    capture_type = data.get('captureType', 'browser_visible_product_page')
    if capture_type not in ('browser_visible_product_page', 'browser_seller_profile', 'browser_front_search', 'browser_sellersprite_search', 'browser_1688_image_search'):
        raise ValueError('不支持的页面采集类型')
    query_values = parse_qs(parsed.query).get('k', [])
    if capture_type == 'browser_seller_profile':
        seller_id = str(data.get('sellerId', '')).strip().upper()
        if (parsed.scheme != 'https' or MARKETS.get(host) != market
                or parsed.username or parsed.password or port not in (None, 443)
                or parsed.path not in ('/sp', '/gp/help/seller/at-a-glance.html')
                or not re.fullmatch(r'[A-Z0-9]{5,30}', seller_id)
                or parse_qs(parsed.query).get('seller', [''])[0].upper() != seller_id):
            raise ValueError('卖家资料页网址、Seller ID与站点不匹配')
        profile_raw = str(data.get('sellerProfileText', '')).strip()
        if not profile_raw or len(profile_raw) > 4000:
            raise ValueError('请提供卖家资料页实际显示的经营资料原文（最多4000字符）')
    elif capture_type == 'browser_front_search':
        if parsed.scheme != 'https' or MARKETS.get(host) != market or parsed.path != '/s' or not query_values or not query_values[0].strip():
            raise ValueError('搜索页网址、关键词与站点无效；请从Amazon前台搜索结果页采集')
    elif capture_type == 'browser_sellersprite_search':
        if parsed.scheme != 'https' or parsed.username or port not in (None, 443) or not (host == 'sellersprite.com' or host.endswith('.sellersprite.com')):
            raise ValueError('SellerSprite观察必须来自其HTTPS页面')
    elif capture_type == 'browser_1688_image_search':
        image_route = host == 'air.1688.com' and parsed.path in (
            '/kapp/1688-search/pc-image-search', '/kapp/1688-search/pc-image-search/')
        if parsed.scheme != 'https' or parsed.username or parsed.password or port not in (None, 443) or (
                host not in ('s.1688.com', 'search.1688.com', '1688.com') and not image_route):
            raise ValueError('货源搜索观察必须来自1688搜索页')
    else:
        path_match = re.search(r'/dp/([A-Z0-9]{10})(?:/|$)', parsed.path, re.I)
        if parsed.scheme != 'https' or MARKETS.get(host) != market or not path_match or path_match.group(1).upper() != asin:
            raise ValueError('页面网址、ASIN与站点不匹配；请从对应Amazon商品详情页采集')
    try:
        captured = datetime.fromisoformat(str(data.get('capturedAt', '')).replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('采集时间格式无效') from exc
    safe_query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                  if not any(secret in key.lower() for secret in ('key', 'token', 'password', 'auth'))]
    safe_url = urlunsplit((parsed.scheme, host, parsed.path, urlencode(safe_query), ''))
    observation = {
        'asin': asin, 'marketplace': market, 'url': safe_url[:1000],
        'capturedAt': captured.isoformat(), 'captureType': capture_type,
        'fields': {key: str(data.get(key, '')).strip()[:2000] for key in FIELDS},
        'trust': 'unverified_observation',
        'limitations': '页面可见字段的辅助记录；不证明中国卖家、FBM、卖家上架日期、同款销售排名或IP权利，不满足选品准入证据。'
    }
    if capture_type == 'browser_seller_profile':
        observation['sellerProfile'] = {'sellerId': seller_id, 'raw': profile_raw,
                                        'warning': '资料页观察；需与本候选实际销售卖家核对，不自动认定国家或FBM。'}
    elif capture_type == 'browser_front_search':
        results = data.get('searchResults', [])
        if not isinstance(results, list) or len(results) > 20:
            raise ValueError('搜索结果格式无效或超过20条')
        clean_results = []
        for item in results:
            if not isinstance(item, dict):
                continue
            result_asin = str(item.get('asin', '')).strip().upper()
            title = str(item.get('title', '')).strip()[:500]
            if re.fullmatch(r'[A-Z0-9]{10}', result_asin) and title:
                clean_results.append({'asin': result_asin, 'title': title})
        observation['search'] = {
            'query': query_values[0][:300],
            'visibleResultCount': max(0, min(1000000, int(str(data.get('visibleResultCount', '0')).replace(',', '')))) if str(data.get('visibleResultCount', '0')).replace(',', '').isdigit() else 0,
            'resultText': str(data.get('resultText', '')).strip()[:1000],
            'results': clean_results,
        }
        if not observation['search']['query']:
            raise ValueError('搜索页没有关键词')
    elif capture_type == 'browser_sellersprite_search':
        rows = data.get('visibleRows', [])
        if not isinstance(rows, list) or len(rows) > 10:
            raise ValueError('SellerSprite结果行格式无效或超过10条')
        clean_rows = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            row_asin = str(item.get('asin', '')).strip().upper()
            row_text = str(item.get('text', '')).strip()[:300]
            if re.fullmatch(r'[A-Z0-9]{10}', row_asin) and row_text:
                clean_rows.append({'asin': row_asin, 'text': row_text})
        observation['sellerSprite'] = {
            'pageTitle': str(data.get('pageTitle', '')).strip()[:300],
            'rows': clean_rows,
            'warning': '仅保存当前页面可见文本供人工复核；不抽取或认证销售排名，不自动认定同款。'
        }
        if not clean_rows:
            raise ValueError('未读取到SellerSprite页面可见结果；请确认已登录并打开搜索结果页')
    elif capture_type == 'browser_1688_image_search':
        offers = data.get('offers', [])
        if not isinstance(offers, list) or len(offers) > 6:
            raise ValueError('1688可见候选格式无效或超过6条')
        clean_offers = []
        for item in offers:
            if not isinstance(item, dict):
                continue
            offer_id = str(item.get('offerId', '')).strip()
            detail = urlsplit(str(item.get('url', '')))
            image = urlsplit(str(item.get('imageUrl', '')))
            detail_host = (detail.hostname or '').lower()
            image_host = (image.hostname or '').lower()
            if not re.fullmatch(r'\d{8,20}', offer_id):
                continue
            if detail.scheme != 'https' or detail_host != 'detail.1688.com' or not re.search(rf'/offer/{offer_id}\.html(?:/|$)', detail.path):
                continue
            image_ok = image.scheme == 'https' and (image_host == 'alicdn.com' or image_host.endswith('.alicdn.com'))
            title = str(item.get('title', '')).strip()[:160]
            if not title:
                continue
            clean_offers.append({
                'offerId': offer_id, 'title': title, 'url': f'https://detail.1688.com/offer/{offer_id}.html',
                'imageUrl': f'https://{image_host}{image.path}'[:500] if image_ok else '',
                'priceText': str(item.get('priceText', '')).strip()[:80],
                'supplierText': str(item.get('supplierText', '')).strip()[:100],
                'raw': str(item.get('text', '')).strip()[:250],
            })
        if not clean_offers:
            raise ValueError('未读取到带1688商品详情链接的可见搜索结果')
        observation['sourcingSearch'] = {
            'offers': clean_offers,
            'warning': '1688图片搜索相似结果仅供人工筛选；未验证同款、材质、供货、报价、重量或图片权利。'
        }
    elif not observation['fields']['title']:
        raise ValueError('未读取到商品标题；请等待Amazon详情页加载完成后重试')
    return observation


def attach(workspace, observation):
    """Attach only to the matching candidate in the caller's authenticated workspace."""
    found = []
    for product in workspace.get('products', []):
        ref = (product.get('selectionResearch') or {}).get('reference') or {}
        if ref.get('asin', '').upper() == observation['asin'] and ref.get('market', '').upper() == observation['marketplace']:
            found.append(product)
    if len(found) != 1:
        raise ValueError('当前账号产品库中没有唯一匹配的选品候选；请先将该站点的调研候选加入产品库')
    product = found[0]
    if observation.get('captureType') == 'browser_front_search':
        reference = (product.get('selectionResearch') or {}).get('reference') or {}
        target_title = reference.get('title') or product.get('name', '')
        observation['matchReview'] = {
            'targetTitle': str(target_title)[:500],
            'method': 'normalized title-token Jaccard overlap',
            'candidates': rank_visible_results(target_title, observation.get('search', {}).get('results', [])),
            'warning': '仅按标题词重叠排序；不判断exact/strong，不证明其他卖家、同款、销售或排名。'
        }
    elif observation.get('captureType') == 'browser_sellersprite_search':
        observation['sellerSprite']['candidateAsin'] = observation['asin']
    entries = product.setdefault('selectionObservations', [])
    if not isinstance(entries, list):
        entries = product['selectionObservations'] = []
    # The exact same page snapshot should be idempotent when the user clicks twice.
    existing = next((item for item in entries if item.get('url') == observation['url'] and item.get('capturedAt') == observation['capturedAt']), None)
    if not existing:
        entries.append(observation)
        del entries[:-50]
    return product['id'], len(entries)


def validate_seller_store(data):
    """Validate a visible seller storefront search capture without asserting freshness."""
    if not isinstance(data, dict):
        raise ValueError('店铺采集数据格式无效')
    parsed = urlsplit(str(data.get('url', '')))
    host = (parsed.hostname or '').lower().removeprefix('www.')
    market = MARKETS.get(host)
    seller_id = str(data.get('sellerId', '')).strip().upper()
    try:
        captured = datetime.fromisoformat(str(data.get('capturedAt', '')).replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('店铺页面采集时间格式无效') from exc
    params = parse_qs(parsed.query)
    if (parsed.scheme != 'https' or parsed.path != '/s' or not market
            or (data.get('marketplace') and data.get('marketplace') != market)
            or params.get('me', [''])[0].strip().upper() != seller_id
            or not re.fullmatch(r'[A-Z0-9]{5,30}', seller_id)):
        raise ValueError('请从含匹配 Seller ID 的 Amazon 店铺搜索结果页采集')
    rows = data.get('products')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError('店铺页需包含1至50条可见商品')
    clean = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        asin = str(item.get('asin', '')).strip().upper()
        title = str(item.get('title', '')).strip()[:500]
        if not re.fullmatch(r'[A-Z0-9]{10}', asin) or not title or asin in seen:
            continue
        image = urlsplit(str(item.get('imageUrl', '')))
        image_host = (image.hostname or '').lower()
        image_url = (str(item.get('imageUrl', ''))[:1000]
                     if image.scheme == 'https' and (image_host == 'm.media-amazon.com'
                     or image_host.endswith('.media-amazon.com')) else '')
        clean.append({'asin': asin, 'title': title,
                      'brandText': str(item.get('brandText', '')).strip()[:200],
                      'priceText': str(item.get('priceText', '')).strip()[:120],
                      'imageUrl': image_url,
                      'productUrl': f'https://www.{host}/dp/{asin}',
                      'raw': str(item.get('raw', '')).strip()[:1000]})
        seen.add(asin)
    if not clean:
        raise ValueError('页面没有可识别的Amazon商品卡片')
    sort_key = str(params.get('s', [''])[0])[:100]
    safe_query = urlencode([(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                            if key.lower() in {'me', 's', 'k', 'page', 'marketplaceid'}])
    observation = {
        'sellerId': seller_id, 'marketplace': market,
        'url': f'https://www.{host}{parsed.path}?{safe_query}'[:1500],
        'capturedAt': captured.isoformat(), 'sortKey': sort_key,
        'pageTitle': str(data.get('pageTitle', '')).strip()[:300],
        'pageSummary': str(data.get('pageSummary', '')).strip()[:1000],
        'products': clean, 'trust': 'unverified_observation',
        'limitations': '仅采集Amazon店铺搜索页当前可见商品卡片；排序参数不证明近7天卖家上架，页面未证明卖家国家、FBM、同款销售排名或图片权利。'
    }
    return observation


def attach_seller_store(workspace, observation):
    """Save an account-workspace-owned seller page observation idempotently."""
    entries = workspace.setdefault('sellerScoutObservations', [])
    if not isinstance(entries, list):
        entries = workspace['sellerScoutObservations'] = []
    existing = next((item for item in entries
                     if item.get('sellerId') == observation['sellerId']
                     and item.get('url') == observation['url']
                     and item.get('capturedAt') == observation['capturedAt']), None)
    if existing:
        return existing, len(entries)
    entries.append(observation)
    del entries[:-50]
    return observation, len(entries)
