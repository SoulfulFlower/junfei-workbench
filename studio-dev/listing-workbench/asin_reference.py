"""Capture the selected Amazon gallery and independently verify one child page per colour."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urlsplit

import importer

ASIN = re.compile(r'[A-Z0-9]{10}')
MEDIA_HOSTS = {'m.media-amazon.com', 'images-na.ssl-images-amazon.com'}


def field(page, name, kind):
    for match in re.finditer(r'"' + name + r'"\s*:\s*', page):
        try:
            value = json.JSONDecoder().raw_decode(page, match.end())[0]
        except ValueError:
            continue
        if isinstance(value, kind):
            return value
    return kind()


def media_key(url):
    if not isinstance(url, str):
        return ''
    try:
        parts = urlsplit(url)
    except ValueError:
        return ''
    if parts.scheme != 'https' or parts.netloc not in MEDIA_HOSTS or '/images/I/' not in parts.path:
        return ''
    return parts.path.rsplit('/', 1)[-1].split('.', 1)[0]


class SelectedProduct(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.asin = ''
        self.image = {}
        self.feed(page)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'input' and attrs.get('id') == 'ASIN':
            self.asin = attrs.get('value', '')
        elif tag == 'img' and attrs.get('id') == 'landingImage':
            self.image = attrs


def landing_image(attrs):
    if media_key(attrs.get('data-old-hires')):
        return attrs['data-old-hires']
    try:
        candidates = json.loads(attrs.get('data-a-dynamic-image') or '{}')
    except ValueError:
        candidates = {}
    if isinstance(candidates, dict):
        valid = [(min(size), url) for url, size in candidates.items()
                 if media_key(url) and isinstance(size, list) and len(size) == 2
                 and all(type(value) is int for value in size)]
        if valid:
            return max(valid)[1]
    return attrs.get('src', '') if media_key(attrs.get('src')) else ''


def selected_gallery(page, main):
    main_key = media_key(main)
    if not main_key:
        return []
    for match in re.finditer(r"""['"]initial['"]\s*:\s*(?:A\.\$\.parseJSON\(\s*')?(?=\[)""", page):
        try:
            items = json.JSONDecoder().raw_decode(page, match.end())[0]
        except ValueError:
            continue
        images = [item.get('hiRes') or item.get('large') for item in items if isinstance(item, dict)]
        unique = {}
        for url in images:
            if key := media_key(url):
                unique.setdefault(key, url)
        if unique and next(iter(unique)) == main_key:
            return list(unique.values())[:7]
    return [main]


def observed_family(page):
    dims = field(page, 'dimensions', list)
    values = field(page, 'variationValues', dict)
    mapping = field(page, 'dimensionValuesDisplayData', dict)
    if not dims or not mapping or not values or len(dims) != len(set(dims)):
        return []
    if 'color_name' not in dims or any(dim not in ('color_name', 'size_name') for dim in dims):
        return []
    rows = []
    for asin, names in mapping.items():
        if not ASIN.fullmatch(asin) or not isinstance(names, list) or len(names) != len(dims):
            raise ValueError('Amazon 变体关系不完整，请重新采集')
        if any(not isinstance(name, str) or not name.strip() or name not in values.get(dim, [])
               for dim, name in zip(dims, names)):
            raise ValueError('Amazon 变体选项与子 ASIN 对应不完整，请重新采集')
        options = dict(zip(dims, names))
        rows.append({'asin': asin, 'color': options['color_name'], 'size': options.get('size_name', '')})
    colors = values['color_name']
    sizes = values.get('size_name', [''])
    return sorted(rows, key=lambda row: (colors.index(row['color']), sizes.index(row['size']), row['asin']))


def product_url(market, asin):
    return f'https://www.amazon.{importer.MARKET_DOMAINS[market]}/dp/{asin}'


def checked_image(page, child, market):
    selected = SelectedProduct(page)
    if selected.asin != child['asin'] or field(page, 'currentAsin', str) not in ('', child['asin']):
        raise ValueError('子商品页显示了其他 ASIN')
    values = field(page, 'variationValues', dict).get('color_name', [])
    index = field(page, 'selectedVariationValues', dict).get('color_name')
    if not isinstance(values, list) or type(index) is not int or not 0 <= index < len(values) or values[index] != child['color']:
        raise ValueError('未能确认子商品页所选颜色')
    main = landing_image(selected.image)
    if not main:
        raise ValueError('子商品页没有可核对的主图')
    gallery = selected_gallery(page, main)
    return {'url': gallery[0], 'sourceAsin': child['asin'],
            'sourceUrl': product_url(market, child['asin']), 'checkedAt': now()}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def capture(asin, market, previous=None, *, fetch=None):
    if (not isinstance(asin, str) or not ASIN.fullmatch(asin)
            or not isinstance(market, str) or market not in importer.MARKET_DOMAINS):
        raise ValueError('请输入有效 ASIN 并选择支持的站点')
    fetch = fetch or importer.fetch_amazon
    url = product_url(market, asin)
    try:
        page = fetch(url)
    except (OSError, URLError) as exc:
        raise ValueError('Amazon 页面暂不可读，请稍后重试') from exc
    selected = SelectedProduct(page)
    parent = field(page, 'parentAsin', str)
    if not ASIN.fullmatch(selected.asin) or asin not in (selected.asin, parent):
        raise ValueError('Amazon 未返回指定商品页，无法核对 ASIN')
    info = importer.parse_amazon(page)
    if not info['title']:
        raise ValueError('Amazon 未返回商品标题，请稍后重试')
    gallery = selected_gallery(page, landing_image(selected.image))
    children = observed_family(page)
    previous = previous or {}
    if not children and previous.get('asin') == asin and previous.get('market') == market and previous.get('variants'):
        raise ValueError('本次页面缺少变体关系，已保留上次采集')
    by_color = {}
    for child in children:
        by_color.setdefault(child['color'], []).append(child)
    preferred = field(page, 'colorToAsin', dict)
    saved = {entry['color']: entry['mainImage'] for entry in previous.get('colors', [])
             if entry.get('mainImage')} if previous.get('asin') == asin and previous.get('market') == market else {}

    def capture_color(item):
        color, rows = item
        prior = saved.get(color)
        if prior and media_key(prior.get('url')) and any(row['asin'] == prior.get('sourceAsin') for row in rows):
            return {'color': color, 'mainImage': prior}
        hint = preferred.get(color)
        hint = hint.get('asin') if isinstance(hint, dict) else ''
        choices = sorted(rows, key=lambda row: (row['asin'] != selected.asin, row['asin'] != hint))
        error = ''
        for child in choices[:2]:
            try:
                child_page = page if child['asin'] == selected.asin else fetch(product_url(market, child['asin']))
                return {'color': color, 'mainImage': checked_image(child_page, child, market)}
            except (ValueError, OSError, URLError) as exc:
                error = str(exc) if isinstance(exc, ValueError) else '子商品页暂不可读'
        return {'color': color, 'mainImage': None, 'issue': error}

    with ThreadPoolExecutor(max_workers=4) as pool:
        colors = list(pool.map(capture_color, by_color.items()))
    return {**info, 'asin': asin, 'selectedAsin': selected.asin, 'parentAsin': parent,
            'market': market, 'url': url, 'referenceImages': gallery, 'variants': children,
            'colors': colors, 'capturedAt': now()}
