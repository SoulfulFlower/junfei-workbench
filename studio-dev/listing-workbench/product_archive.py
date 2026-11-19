"""Shared Amazon identity and product creation for research and discovery intake."""
import product_sku


def matches(product, market, asin):
    if product.get('id') == f'IMP-{market}-{asin}':
        return True
    source = product.get('sourceImport') or {}
    research = product.get('selectionResearch')
    reference = research.get('reference') if isinstance(research, dict) else None
    return any(isinstance(item, dict) and item.get('market') == market and item.get('asin') == asin
               for item in (source, reference))


def find(workspace, market, asin):
    products = [p for p in workspace.get('products', []) if matches(p, market, asin)]
    if len(products) > 1:
        raise ValueError('多个现有档案对应同一站点及ASIN，请先核对原档案')
    return products[0] if products else None


def ensure(workspace, user, candidate, research):
    market, asin = candidate['market'], candidate['asin']
    product = find(workspace, market, asin)
    if product is not None:
        return product, False
    if any(matches(entry.get('product') or {}, market, asin)
           for entry in workspace.get('deletedProducts', [])):
        return None, False
    products = workspace.setdefault('products', [])
    workspace.setdefault('copy', {})
    workspace.setdefault('reviews', {})
    # Amazon titles remain reference names. Supplier facts and production assets are separate.
    ranked = research.get('rankedCompetitors')
    competitor_input = '\n'.join(row['asin'] for row in ranked) if ranked is not None else asin
    warning = '选品参考，待查关键词和评论'
    if ranked is not None:
        warning = (f'循环选品已核对 {len(ranked)} 个有销售排名的竞品，待反查和拓展关键词'
                   if len(ranked) >= 3 else f'循环选品已核对 {len(ranked)} 个有销售排名的竞品，资料待补至至少 3 个')
    product = {
        'id': f'IMP-{market}-{asin}', 'name': candidate['title'], 'cat': '日用百货',
        'owner': user.get('name') or user.get('username', '待分配'),
        'colors': 1, 'sizes': 1, 'status': '待补资料', 'color': '#a6b39a', 'market': market,
        'brand': 'Generic', 'manufacturer': 'Generic', 'sourceUrl': '', 'material': '',
        'dimensions': '', 'features': '', 'packageContents': '', 'assets': [],
        'selectionResearch': {**research, 'reference': candidate},
        'competitorResearch': {market: {'market': market, 'input': competitor_input, 'keywords': [],
                                        'sources': [], 'structure': '', 'warnings': warning}},
        'productionReview': {'publishReady': False, 'remainingIssue': '待核实自有产品事实、类目和生产素材；不可直接生产发布。'},
    }
    product_sku.ensure(product, user, {p.get('sku') for p in products if p.get('sku')})
    products.insert(0, product)
    return product, True
