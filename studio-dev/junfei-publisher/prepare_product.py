"""将本地 Listing Studio 导出格式转换为刊登计划；缺少事实即报错。"""
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path


def prepare(folder, *, store, marketplace, currency, quantity, weight_grams, main_image, variant_prices=None):
    folder = Path(folder).resolve(strict=True)
    if not store.strip() or not marketplace.strip():
        raise ValueError('必须明确店铺与站点')
    if not isinstance(quantity, int) or quantity < 0:
        raise ValueError('必须明确非负整数库存')
    weight = Decimal(str(weight_grams))
    if not weight.is_finite() or weight <= 0:
        raise ValueError('必须明确本批采用的包装重量')
    if currency != 'USD':
        raise ValueError('此转换入口仅计算美元价格；其它币种请提供明确售价')
    listing = json.loads((folder / 'listing.json').read_text(encoding='utf-8-sig'))
    source = json.loads((folder / '货源资料.json').read_text(encoding='utf-8-sig'))
    with (folder / '变体.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    main = Path(main_image).resolve(strict=True)
    if not main.is_relative_to(folder):
        raise ValueError('主图必须位于产品资料目录')
    color_values = {row['color'] for row in rows}
    if len(color_values) != 1:
        raise ValueError('多颜色必须逐颜色指定主图，不能统一使用一张图')
    image_dir = main.parent
    images = [str(p.resolve()) for p in sorted(image_dir.iterdir()) if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'} and p.resolve() != main]
    if len(images) > 8:
        raise ValueError('附图超过8张，请先明确图片选择')
    bullets = listing['bullets'].splitlines() if isinstance(listing['bullets'], str) else listing['bullets']
    if len(bullets) != 5:
        raise ValueError('需完整五点')
    product = {
        'id': listing['sku'], 'parentSku': listing['sku'], 'store': store,
        'marketplace': marketplace, 'currency': currency, 'brand':listing['brand'],
        'manufacturer': listing.get('manufacturer', listing['brand']),
        'title': listing['title'], 'highlight': listing.get('highlights', ''),
        'description': listing['description'], 'bullets': bullets, 'searchTerms': listing['terms'],
        'sourceUrl':source['sourceUrl'], 'handlingDays':3,
        'shippingTemplate':'', 'variants':[],
        'reviewNotes': ['本次用户明确指定统一包装重量及库存；不代表各尺码实测重量', *source.get('holds', [])],
    }
    for row in rows:
        cost = Decimal(str(source['sizePricesCny'][row['size']]))
        saved = (variant_prices or {}).get(row['child_sku'])
        if saved is None:
            raise ValueError('缺少明确变体售价；旧固定运费公式已停用，请先按实际物流报价定价')
        price = Decimal(str(saved))
        if not price.is_finite() or price <= 0 or price.as_tuple().exponent < -2:
            raise ValueError('变体售价必须是正数且最多两位小数')
        product['variants'].append({
            'sku':row['child_sku'], 'color':row['color'], 'size':row['size'],
            'price':str(price), 'quantity':quantity, 'weightGrams':float(weight),
            'costRmb':float(cost), 'mainImage':str(main), 'images':images,
        })
    return product
