"""Apply a workspace change against the records the browser originally read."""


import listing_locks
import product_sku
import variant_colours

MAPS = {'copy', 'reviews'}



def empty():
    return {'products': [], 'copy': {}, 'reviews': {}}


class Conflict(ValueError):
    def __init__(self, scope, key):
        super().__init__(f'记录 {key} 已在其他页面或后台任务中更改')
        self.scope = scope
        self.key = key


def apply_changes(state, changes):
    if not isinstance(changes, list):
        raise ValueError('工作区修改格式不正确')
    products = {product['id']: product for product in state['products']}
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError('工作区修改格式不正确')
        scope, key = change.get('scope'), change.get('key')
        if not isinstance(key, str) or not key or scope not in ('products', 'copy', 'reviews', 'workspace'):
            raise ValueError('工作区修改范围不正确')
        if scope == 'workspace' and key in ('products', 'copy', 'reviews'):
            raise ValueError('核心档案必须按记录保存')
        records = products if scope == 'products' else state[scope] if scope in MAPS else state
        current = [records[key]] if key in records else []
        before, after = change.get('before'), change.get('after')
        if any(not isinstance(value, list) or len(value) > 1 for value in (before, after)):
            raise ValueError('工作区记录格式不正确')
        if current == after:
            continue
        if current != before:
            raise Conflict(scope, key)
        if scope == 'products' and after and (not isinstance(after[0], dict) or after[0].get('id') != key):
            raise ValueError('产品 ID 与修改记录不一致')
        if after:
            records[key] = after[0]
        else:
            records.pop(key, None)
    existing = {product['id'] for product in state['products']}
    state['products'] = [product for key, product in products.items() if key not in existing] + [
        products[product['id']] for product in state['products'] if product['id'] in products
    ]
    return state


def validate(previous, state, user):
    if not isinstance(state, dict) or not isinstance(state.get('products'), list) or any(
        not isinstance(state.get(key), dict) for key in MAPS
    ):
        raise ValueError('产品库格式不正确')
    old_skus = {product['id']: product.get('sku') for product in previous.get('products', [])}
    ids = set()
    for product in state['products']:
        if not isinstance(product, dict) or not all(
            isinstance(product.get(key), str) and product[key] for key in ('id', 'name', 'cat', 'owner', 'status', 'color')
        ):
            raise ValueError('产品字段不完整')
        if product['id'] in ids:
            raise ValueError('产品 ID 不能重复')
        ids.add(product['id'])
        if any(type(product.get(key)) is not int or not 1 <= product[key] <= 500 for key in ('colors', 'sizes')):
            raise ValueError('颜色和尺码数量必须在 1 到 500 之间')
        for field in ('brand', 'manufacturer'):
            value = product.get(field, '')
            if not isinstance(value, str):
                raise ValueError('品牌和制造商必须为文字')
            product[field] = value.strip() or 'Generic'
        sku = product.get('sku')
        if sku and (not isinstance(sku, str) or (sku != old_skus.get(product['id']) and not product_sku.PARENT_SKU.fullmatch(sku))):
            raise ValueError(product_sku.PARENT_SKU_ERROR)
    used = {product['sku'] for product in state['products'] if product.get('sku')}
    for product in state['products']:
        if not product.get('sku'):
            product_sku.ensure(product, user, used)
    counts = {}
    for product in state['products']:
        sku = product['sku'].casefold()
        counts[sku] = counts.get(sku, 0) + 1
    for product in state['products']:
        if product['sku'] != old_skus.get(product['id']) and counts[product['sku'].casefold()] > 1:
            raise ValueError('父 SKU 已存在')
    listing_locks.validate_state(previous, state)
    variant_colours.validate_master_changes(previous, state)
