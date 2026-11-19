"""Compare collected Amazon child options with source-bound supplier observations.

This is an option-coverage check, never a stock, exact-match or profit attestation.
It neither creates a Cartesian product nor removes any collected child.
"""
from datetime import datetime
import re
from urllib.parse import urlsplit


def _offer(value):
    if not isinstance(value, str):
        return None
    try:
        u = urlsplit(value)
        if (u.scheme != 'https' or u.hostname != 'detail.1688.com'
                or u.port not in (None, 443) or u.username or u.password):
            return None
    except ValueError:
        return None
    match = re.fullmatch(r'/offer/([1-9][0-9]*)\.html', u.path)
    return match[1] if match else None


def _colour(value):
    return ' '.join(value.split()).casefold() if isinstance(value, str) else ''


def _size(value):
    if not isinstance(value, str):
        return ''
    s = re.sub(r'[\s_-]+', '', value).casefold()
    aliases = {'xsmall': 'xs', 'xxsmall': '2xs', 'xxs': '2xs',
               'small': 's', 'medium': 'm', 'large': 'l', 'xlarge': 'xl',
               'xxlarge': '2xl', 'xxl': '2xl', 'xxxlarge': '3xl', 'xxxl': '3xl'}
    if s in aliases:
        return aliases[s]
    match = re.fullmatch(r'([2-9][0-9]*)x(?:large|l)', s)
    return match[1] + 'xl' if match else s


def inspect(product):
    product = product if isinstance(product, dict) else {}
    source = product.get('sourceImport')
    source = source if isinstance(source, dict) else {}
    amazon = source.get('amazon') or {}
    children = amazon.get('variants') if isinstance(amazon, dict) else None
    result = {'ok': True, 'required': False, 'issues': [], 'observedChildCount': 0,
              'uncoveredChildren': [], 'stockVerified': False,
              'note': '仅比较货源可见选项，不代表逐SKU库存、同款、售价或利润已核实；保留全部采集子体。'}
    if children is None:
        return result
    if not isinstance(children, list):
        result.update(ok=False, required=True, issues=['已采集子体格式无效，不能核对货源变体覆盖'])
        return result
    result['observedChildCount'] = len(children)
    if not children:
        result.update(ok=False, required=True, issues=['已采集子体为空，不能核对全部颜色尺码'])
        return result
    if any(not isinstance(c, dict) or not _colour(c.get('color_name'))
           or not _size(c.get('size_name')) for c in children):
        result.update(ok=False, required=True, issues=['已采集子体缺少可核对的颜色尺码'])
        return result
    coverage = product.get('supplierVariantCoverage')
    if len(children) < 2 and coverage is None:
        return result
    result['required'] = True
    issues = result['issues']
    if not isinstance(coverage, dict):
        issues.append('尚未记录货源是否覆盖全部已采集颜色尺码')
        result['ok'] = False
        return result
    if coverage.get('productId') != product.get('id'):
        issues.append('货源变体观察不属于当前产品')
    selected = _offer(product.get('sourceUrl'))
    if not selected or _offer(coverage.get('sourceUrl')) != selected:
        issues.append('货源变体观察与当前货源链接不一致，需重新核对')
    supplier = source.get('supplier') if isinstance(source, dict) else None
    if isinstance(supplier, dict) and supplier.get('url') and _offer(supplier['url']) != selected:
        issues.append('采集货源与当前货源链接不一致，需重新核对')
    if not isinstance(coverage.get('evidence'), str) or not coverage['evidence'].strip():
        issues.append('缺少货源变体观察的来源证据')
    try:
        checked = datetime.fromisoformat(coverage.get('checkedAt', '').replace('Z', '+00:00'))
        if checked.tzinfo is None:
            raise ValueError('timezone missing')
    except (TypeError, ValueError, AttributeError):
        issues.append('缺少有效的货源变体观察时间')

    options = {}
    for label, key, normalize in (('颜色', 'supplierObservedColors', _colour),
                                  ('尺码', 'supplierObservedSizes', _size)):
        values = coverage.get(key)
        if (not isinstance(values, list) or not values
                or any(not isinstance(v, str) or not v.strip() for v in values)):
            issues.append('尚未记录货源可见' + label + '选项')
            options[key] = set()
        else:
            options[key] = {normalize(v) for v in values}

    pairs = coverage.get('supplierObservedVariants')
    pair_keys = None
    if pairs is not None:
        if (not isinstance(pairs, list) or not pairs or any(not isinstance(p, dict)
                or not _colour(p.get('color')) or not _size(p.get('size')) for p in pairs)):
            issues.append('货源已记录的具体颜色尺码组合格式无效')
            pair_keys = set()
        else:
            pair_keys = {(_colour(p['color']), _size(p['size'])) for p in pairs}

    missing_colours, missing_sizes = {}, {}
    for child in children:
        if not isinstance(child, dict):
            issues.append('已采集子体缺少可核对的颜色尺码')
            continue
        color, size = child.get('color_name'), child.get('size_name')
        if not _colour(color) or not _size(size):
            issues.append('已采集子体缺少可核对的颜色尺码')
            continue
        missing = []
        if _colour(color) not in options['supplierObservedColors']:
            missing_colours.setdefault(_colour(color), color.strip())
            missing.append('color')
        if _size(size) not in options['supplierObservedSizes']:
            missing_sizes.setdefault(_size(size), size.strip())
            missing.append('size')
        if pair_keys is not None and (_colour(color), _size(size)) not in pair_keys:
            missing.append('combination')
        if missing:
            result['uncoveredChildren'].append({'asin': child.get('asin'), 'color': color,
                                                'size': size, 'missing': missing})
    result['unverifiedColors'] = list(missing_colours.values())
    result['unverifiedSizes'] = list(missing_sizes.values())
    if missing_colours:
        issues.append('当前货源选项未覆盖已采集颜色：' + '、'.join(missing_colours.values()))
    if missing_sizes:
        issues.append('当前货源选项未覆盖已采集尺码：' + '、'.join(missing_sizes.values()))
    if any('combination' in c['missing'] for c in result['uncoveredChildren']):
        issues.append('当前货源具体规格记录未覆盖全部已采集颜色尺码组合')
    # Missing lists supplied by a renderer are deliberately not authoritative:
    # derive every gap again from the actual collected children and observations.
    result['issues'] = list(dict.fromkeys(issues))
    result['ok'] = not result['issues']
    result['checkedAt'] = coverage.get('checkedAt')
    result['sourceUrl'] = coverage.get('sourceUrl')
    return result
