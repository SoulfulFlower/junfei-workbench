"""Product-owned commerce inputs; store connections never supply a product price."""
import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
import app_paths

MARKETS={'US':('USD','US','en_US'),'UK':('GBP','GB','en_GB'),'DE':('EUR','DE','de_DE'),
         'FR':('EUR','FR','fr_FR'),'IT':('EUR','IT','it_IT'),'ES':('EUR','ES','es_ES'),
         'CA':('CAD','CA','en_CA'),'AU':('AUD','AU','en_AU'),'JP':('JPY','JP','ja_JP')}


def amount(value,label):
    try:
        if isinstance(value,bool):raise InvalidOperation
        value=Decimal(str(value))
        if not value.is_finite() or value<=0 or value>=10000000:raise InvalidOperation
        return format(value.quantize(Decimal('.01')),'f')
    except (InvalidOperation,ValueError,TypeError):raise ValueError(label+'须为明确的正数金额') from None


def purchase_price(product):
    supplier=product.get('sourceImport',{}).get('supplier',{})
    attrs=supplier.get('attributes',{}) if supplier.get('url')==product.get('sourceUrl') else {}
    value=product.get('purchasePrice') or attrs.get('采购价') or attrs.get('价格')
    if value is None:return None
    m=re.fullmatch(r'\s*(?:CNY|RMB|¥|￥)?\s*(\d+(?:\.\d{1,2})?)\s*(?:元|CNY|RMB)?\s*',str(value),re.I)
    if not m:raise ValueError('采购价须是明确的人民币金额，不能采用价格区间')
    return amount(m[1],'人民币采购价')


def selection_quote(user,product,market):
    """Only read the linked account's verified sourcing event, never another DB."""
    qualification=(product.get('selectionResearch') or {}).get('qualification',{})
    if not qualification.get('cliJobId'):return None
    import discovery_intake
    asin=product.get('sourceImport',{}).get('asin') or product.get('asin')
    try:
        with discovery_intake.read_db(discovery_intake.cli_path(app_paths.DATA)) as db:
            job,proof,_=discovery_intake.qualify(db,user,market,asin)
            if (job['id']!=qualification['cliJobId'] or proof['evidenceSha256']!=qualification.get('evidenceSha256')
                    or proof['supplierUrl']!=product.get('sourceUrl')):raise ValueError('选品定价回执与当前产品不同')
            event,_=discovery_intake.completed(db,job['id'],'sourcing')
            quote=copy.deepcopy(event['sourcing_evidence']['selected_quote'])
            if proof.get('draftPricing'):quote.setdefault('purchase_price_rmb',proof['draftPricing']['purchaseCny'])
            return quote
    except (OSError,KeyError) as error:raise ValueError('本账号选品定价回执暂时不可读') from error


def commerce(user,product,destination,variants,prior=None):
    variants=list(variants)
    market=destination.get('marketplace')
    if market not in MARKETS:raise ValueError('尚未配置此ERP站点的币种和语言')
    currency,country,language=MARKETS[market]
    details=(product.get('erpDelivery') or {}).get(market,{})
    costs=details.get('purchaseCny') or purchase_price(product)
    prices=details.get('variantPrices') or (product.get('junfeiVariantPrices') if market=='US' else {}) or {}
    if not isinstance(prices,dict):raise ValueError('各变体售价必须按子SKU保存')
    uniform=details.get('price')
    basis={'source':'product_saved_prices','currency':currency}
    quote=None
    if not uniform and not all(v[0] in prices for v in variants):
        saved=(product.get('erpDraftPricing') or {}).get(market,{})
        if (saved.get('marketplace')==market and saved.get('currency')==currency and saved.get('sourceUrl')==product.get('sourceUrl')
                and saved.get('scope')=='quote_based_draft_base_scenario' and saved.get('basisSha256')):
            uniform=saved.get('price');costs=costs or saved.get('purchaseCny');basis={'source':'saved_selection_quote','currency':currency,'quote':saved}
        else:
            quote=selection_quote(user,product,market)
            if quote and market=='US':
                uniform=quote.get('formula_price_usd');costs=costs or quote.get('purchase_price_rmb')
                basis={'source':'account_verified_selection_quote','currency':currency,'quote':quote}
    # Migration of an existing verified receipt is generic and never consults
    # a per-product config file. Fresh products cannot inherit these amounts.
    if prior and prior.get('accountId')==user and prior.get('productId')==product['id'] and prior.get('marketplace')==market:
        costs=costs or prior.get('destination',{}).get('purchaseCny')
        if not uniform and not prices:
            prices={v['sku']:v['price'] for v in prior.get('goodsItems',[])}
            basis={'source':'existing_product_receipt','currency':currency}
    if not costs:raise ValueError('缺少本款人民币采购价，请在产品完整资料中补齐')
    costs=amount(costs,'人民币采购价')
    amounts={v[0]:amount(prices.get(v[0],uniform),currency+'售价 '+v[0]) for v in variants}
    if not amounts:raise ValueError('没有可交付的真实子SKU')
    return {**destination,'currency':currency,'countryCode':destination.get('countryCode',country),
            'languageTag':destination.get('languageTag',language),'purchaseCny':costs,
            'price':next(iter(amounts.values())),'variantPrices':amounts,'pricingBasis':basis}


def category_hints(product):
    amazon=product.get('sourceImport',{}).get('amazon',{})
    reference=(product.get('selectionResearch') or {}).get('reference',{})
    return {'path':str(product.get('amazonCategoryPath') or amazon.get('category') or reference.get('category') or ''),
            'title':str(amazon.get('title') or reference.get('title') or product.get('name') or ''),
            'productType':str(product.get('amazonProductType') or '')}


def transport(user,product,destination):
    required=('browserBinding','page','storeId','storeName','seller','erpAccount','marketId','marketplaceId','erpUserId','baseUrl')
    if any(not destination.get(k) for k in required):raise ValueError('请先完成本账号店铺连接配置；只需配置一次，无需逐款绑定')
    if not re.fullmatch(r'p\d+',destination['page']):raise ValueError('ERP页面配置无效')
    base=destination['baseUrl'].rstrip('/')
    if not re.fullmatch(r'https?://[^/?#]+',base):raise ValueError('工作台来源地址无效')
    return {k:destination[k] for k in required}|{k:destination[k] for k in ('currency','countryCode','languageTag','purchaseCny')}


def source_url(user,pid,destination):
    return destination['baseUrl'].rstrip('/')+'/?'+urlencode({'product':pid,'step':'delivery','erpAccount':user,'erpTarget':destination['id']})


def content_digest(snapshot):
    """Compare business contents across v1/v2 receipts, ignoring transport IDs."""
    stable={k:snapshot.get(k) for k in ('accountId','productId','marketplace','store','goods','goodsItems','handlingDays','masterColor')}
    assets=[{k:a.get(k) for k in ('sha256','color','slot')} for a in snapshot.get('assets',[])]
    # Colour ledgers are returned by update time. A metadata read can reorder
    # the global asset list without changing any SKU's seven ordered images.
    # Compare resolved image identities, never their incidental global indices.
    if isinstance(stable['goodsItems'],list):
        rows=[]
        for original in stable['goodsItems']:
            row=copy.deepcopy(original)
            if 'imageIndices' in row:
                indices=row.pop('imageIndices')
                if (not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(assets) for i in indices)):
                    raise ValueError('采集快照子SKU图片索引无效')
                row['orderedImages']=[assets[i] for i in indices]
            rows.append(row)
        stable['goodsItems']=rows
    stable['assets']=sorted(assets,key=lambda a:json.dumps(a,sort_keys=True))
    return hashlib.sha256(json.dumps(stable,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
