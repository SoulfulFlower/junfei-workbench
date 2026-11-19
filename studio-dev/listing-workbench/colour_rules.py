"""Pure colour association validation. No storage, rendering, or HTTP operations."""
import copy
import variant_colours as variants


def reinstatement_candidate(product, key):
    candidate = copy.deepcopy(product)
    amazon = candidate.get('sourceImport', {}).get('amazon', {})
    rows = amazon.get('variants')
    if not isinstance(rows, list) or not isinstance(key, str) or not key:
        raise ValueError('请选择已采集的目标颜色')
    target = [row for row in rows if isinstance(row, dict)
              and variants.colour_key(row.get('color_name') or row.get('color')) == key]
    if not target:
        raise ValueError('当前产品没有该颜色的已采集子体')
    eligible = amazon.get('listingEligibleVariants')
    if not isinstance(eligible, list):
        eligible = rows
    wanted = {row.get('asin') for row in [*eligible, *target]}
    amazon['listingEligibleVariants'] = [row for row in rows if row.get('asin') in wanted]
    group = variants.catalog(candidate).get(key)
    if not group:
        raise ValueError('该颜色没有可核对的子体')
    return candidate, group


def confirmed_master(product, key):
    group = variants.catalog(product).get(key) if isinstance(key, str) else None
    if not group or not group['ready']:
        raise ValueError('母版只能选择货源、子 SKU 和同色参考图均已确认的颜色')
    return group


def validate_master_changes(previous, current):
    old = {p['id']:p for p in previous.get('products', [])}
    for product in current.get('products', []):
        saved = old.get(product['id'])
        if (saved and isinstance(variants.observed_children(saved), list)
                and product.get('masterColor') != saved.get('masterColor')):
            confirmed_master(product, variants.colour_key(product.get('masterColor')))
