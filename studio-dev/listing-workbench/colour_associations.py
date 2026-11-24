"""Pure colour association updates; returns copies and preserves history records."""
import copy
from datetime import datetime, timezone
import colour_rules as rules


def reinstate(product, data, actor):
    if data.get('confirmed') is not True:
        raise ValueError('请核对货源资料后明确确认重新纳入')
    key = data.get('colorKey')
    candidate, group = rules.reinstatement_candidate(product, key)
    if not group['ready']:
        raise ValueError('该颜色尚不能重新纳入：' + '；'.join(group['issues']))
    old = product['sourceImport']['amazon']
    previous = old.get('listingEligibleVariants')
    if not isinstance(previous, list):
        previous = old['variants']
    old_asins = {row.get('asin') for row in previous}
    restored = [child['asin'] for child in group['children'] if child['asin'] not in old_asins]
    if not restored:
        return copy.deepcopy(product), False
    amazon = candidate['sourceImport']['amazon']
    coverage = candidate.get('supplierVariantCoverage') or {}
    event = {'action':'reinstate', 'colorKey':key, 'color':group['color'], 'asins':restored,
             'at':datetime.now(timezone.utc).isoformat(), 'actor':actor,
             'previousExclusions':[copy.deepcopy(row) for row in old.get('excludedVariants', [])
                                   if isinstance(row, dict) and row.get('asin') in restored],
             'supplierEvidence':copy.deepcopy(coverage)}
    amazon.setdefault('variantEligibilityHistory', []).append(event)
    # Keep original exclusions and exact child SKU strings; no new combinations.
    eligible = amazon['listingEligibleVariants']
    colors = list(dict.fromkeys(row.get('color_name') or row.get('color') for row in eligible))
    sizes = list(dict.fromkeys(row.get('size_name') or row.get('size') for row in eligible))
    candidate.update(colors=len(colors), colorNames=', '.join(colors), sizes=len(sizes), sizeNames=', '.join(sizes))
    return candidate, True


def set_master(product, data, actor):
    if data.get('confirmed') is not True:
        raise ValueError('请确认母版的实际颜色')
    group = rules.confirmed_master(product, data.get('colorKey'))
    candidate = copy.deepcopy(product)
    if candidate.get('masterColor') == group['color']:
        return candidate, False
    candidate.setdefault('masterColorHistory', []).append({
        'previous':candidate.get('masterColor'), 'color':group['color'],
        'at':datetime.now(timezone.utc).isoformat(), 'actor':actor})
    candidate['masterColor'] = group['color']
    return candidate, True
