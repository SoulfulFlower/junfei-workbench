"""Pure inputs for the US -> UK publication continuation; no browser or DB writes."""
import copy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

DEFAULT_PUBLICATION_FACTS = {'countryOfOrigin': 'CN', 'careInstructions': 'Machine Wash'}
DEFAULT_PUBLICATION_FACTS_SOURCE = {
    'source': 'user_configured_defaults', 'configuredAt': '2026-11-16',
    'scope': 'all_new_publication_jobs',
    'instruction': '用户要求所有产品新发布统一选择原产国中国、护理机洗，后续不重复询问；原产品字段仅作来源追溯，不覆盖统一刊登设置。',
}
WATER_RESISTANCE_DEFAULT_SOURCE = {
    'source': 'user_configured_defaults', 'configuredAt': '2026-11-17',
    'scope': 'ordinary_apparel_without_explicit_water_claim_new_publication_jobs',
    'instruction': '用户确认普通服装未声明防水时统一选择不防水；明确水性能或特殊防护声明不适用此默认。',
}


def _add_water_resistance_fact(facts, product, supplier, same_source):
    """Apply the selected clothing-only default, never overwrite source claims."""
    water = re.compile(r'防水|防泼水|抗水|耐水|拒水|疏水|water[\s_-]*(?:proof|resistan\w*|repellen\w*)|\bDWR\b|\bIPX\d', re.I)
    special = re.compile(r'防护|劳保|医用|雨衣|雨披|冲锋衣|潜水|泳衣|泳装|泳裤|滑雪|消防|防晒衣|protective|raincoat|rainwear|wetsuit|drysuit|swimwear|skiwear', re.I)
    ordinary = re.compile(r'T恤|上衣|衬衫|毛衣|针织衫|卫衣|开衫|裤|裙|外套|夹克|背心|袜|内衣|睡衣|\b(?:t[ -]?shirts?|shirts?|tops?|blouses?|pullovers?|sweaters?|cardigans?|hoodies?|jackets?|pants|trousers|jeans|skirts?|dresses?|shorts|socks|underwear|pajamas|pyjamas)\b', re.I)
    values, declarations, explicit = [], [], []

    def inspect(path, value, source, key=''):
        if value is None or value == '':return
        raw = value if isinstance(value, str) else str(value)
        values.append(raw)
        normalized_key = re.sub(r'[\s_-]', '', key).lower()
        is_water_field = normalized_key in ('waterresistancelevel','waterresistance','waterproof','iswaterproof','防水','防水等级','防水功能','防水性能')
        # This exact standalone workbench marker records no claim. Inspect all
        # remaining sentences, retaining original evidence and explicit fields.
        claim_text = ' '.join(part for part in re.split(r'(?<=[.!?])\s+|[\r\n]+', raw)
                              if part.strip() != 'No waterproof or performance claim.')
        if is_water_field or water.search(claim_text) or special.search(raw):
            declarations.append({'source':source,'path':path,'value':copy.deepcopy(value)})
        if source=='product_field' and normalized_key=='waterresistancelevel' and isinstance(value,str) and value.strip():
            explicit.append((path,value.strip()))

    for key,value in product.items():
        if water.search(key) or re.sub(r'[\s_-]','',key).lower() in ('waterresistancelevel','waterresistance','iswaterproof'):
            inspect(key,value,'product_field',key)
    for key in ('name','title','style','description','features','sourceCategory'):
        inspect(key,product.get(key),'product_text')
    imported=product.get('sourceImport') or {}
    if isinstance(imported,dict):
        for key in ('title','description','category','categoryName','categoryPath','productType'):
            inspect('sourceImport.'+key,imported.get(key),'source_text')
    for key,value in (product.get('attributes') or {}).items() if isinstance(product.get('attributes'),dict) else ():
        inspect('attributes.'+key,value,'product_field',key)
    if same_source:
        inspect('sourceImport.supplier.title',supplier.get('title'),'supplier_title')
        for key,value in (supplier.get('attributes') or {}).items() if isinstance(supplier.get('attributes'),dict) else ():
            inspect('sourceImport.supplier.attributes.'+key,value,'supplier_attribute',key)
    if declarations:
        facts.setdefault('sourceProductFacts',{})['waterResistanceDeclarations']=declarations
        if len({value for _,value in explicit})==1:
            path,value=explicit[0]
            facts['waterResistanceLevel']=value
            facts['waterResistanceLevelSource']={'source':'product_field','path':path,'value':value}
        facts['waterResistancePolicyDecision']={'applied':False,'reason':'explicit_water_or_protective_declaration','defaultValue':'not_water_resistant'}
        return
    category=str(product.get('cat') or '').strip().lower()
    if category in ('服装','clothing','apparel') and ordinary.search(' '.join(values)):
        facts['waterResistanceLevel']='not_water_resistant'
        facts['waterResistanceLevelSource']={**copy.deepcopy(WATER_RESISTANCE_DEFAULT_SOURCE),'basis':{'productCategory':product['cat'],'classification':'ordinary_apparel'}}
        facts['waterResistancePolicyDecision']={'applied':True,'reason':'ordinary_apparel_without_explicit_water_claim'}


def _add_confirmed_item_condition(facts, product):
    """Consume a product-bound user confirmation, never an inferred approval."""
    condition = product.get('itemCondition')
    evidence = product.get('itemConditionEvidence')
    if condition in (None, '') and evidence in (None, '', {}):
        return False
    if condition != 'new_new':
        raise ValueError('商品成色须为明确确认的全新（new_new）')
    product_id = product.get('id')
    if (not isinstance(product_id, str) or not product_id.strip()
            or not isinstance(evidence, dict)
            or evidence.get('source') != 'user_confirmation'
            or evidence.get('productId') != product_id
            or not isinstance(evidence.get('instruction'), str)
            or not evidence['instruction'].strip() or len(evidence['instruction']) > 2000
            or '\x00' in evidence['instruction']):
        raise ValueError('商品成色缺少本产品的用户明确确认证据')
    try:
        confirmed_at = evidence['confirmedAt']
        if not isinstance(confirmed_at, str):
            raise ValueError
        date = datetime.fromisoformat(confirmed_at.replace('Z', '+00:00'))
        if date.tzinfo is None or date.utcoffset() is None:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise ValueError('商品成色用户确认时间须为带时区的ISO时间') from None
    facts['itemCondition'] = condition
    facts['itemConditionEvidence'] = copy.deepcopy(evidence)
    return True


def publication_facts(product):
    """Freeze explicit product facts without changing the source collection.

    New publication origin/care fields use the user's selected global policy.
    Old product values remain internal provenance, never listing overrides.
    Model facts come only from the bound supplier, not competitor templates.
    """
    facts = copy.deepcopy(DEFAULT_PUBLICATION_FACTS)
    facts['countryOfOriginSource'] = copy.deepcopy(DEFAULT_PUBLICATION_FACTS_SOURCE)
    facts['careInstructionsSource'] = copy.deepcopy(DEFAULT_PUBLICATION_FACTS_SOURCE)
    original = {key: copy.deepcopy(product[key]) for key in
                ('countryOfOrigin', 'countryOfOriginEvidence', 'careInstructions')
                if key in product and product[key] not in (None, '')}
    if original:
        facts['sourceProductFacts'] = original
    contradictions = []
    for key, selected in DEFAULT_PUBLICATION_FACTS.items():
        value = product.get(key)
        comparable = value.strip() if isinstance(value, str) else value
        if key == 'countryOfOrigin' and isinstance(comparable, str):
            comparable = comparable.upper()
        if comparable not in (None, '') and comparable != selected:
            contradictions.append({'field': key, 'sourceValue': copy.deepcopy(value),
                                   'selectedValue': selected, 'source': 'product_field',
                                   'selectedSource': 'user_configured_defaults'})
    if contradictions:
        facts['policyContradictions'] = contradictions
    imported = product.get('sourceImport') or {}
    supplier = imported.get('supplier') if isinstance(imported, dict) else None
    supplier = supplier if isinstance(supplier, dict) else {}
    attributes = supplier.get('attributes') or {}
    source_url, supplier_url = product.get('sourceUrl'), supplier.get('url')
    # A cached supplier block belonging to another product is not a source of
    # model facts. Ignore competitor attributes and unbound importer previews.
    same_source = (isinstance(source_url, str) and isinstance(supplier_url, str)
                   and source_url.split('?')[0].split('#')[0] == supplier_url.split('?')[0].split('#')[0]
                   and bool(source_url.strip()))
    number = attributes.get('货号') if isinstance(attributes, dict) and same_source else None
    if isinstance(number, str) and number.strip():
        number = number.strip()
        if len(number) > 120 or re.search(r'[\r\n\x00]', number):
            raise ValueError('供应商货号不适合作为产品型号，请核对原始资料')
        evidence = {'source': 'supplier_attribute', 'path': 'sourceImport.supplier.attributes.货号',
                    'sourceUrl': supplier_url, 'value': number}
        if supplier.get('retrievedAt'):
            evidence['retrievedAt'] = supplier['retrievedAt']
        facts.update(supplierModelNumber=number, modelName=number,
                     supplierModelNumberEvidence=copy.deepcopy(evidence), modelNameEvidence=copy.deepcopy(evidence))
    title = supplier.get('title')
    if (not _add_confirmed_item_condition(facts, product)
            and same_source and isinstance(title, str) and '新品' in title
            and not re.search(r'非新品|非全新|二手|翻新|旧货', title)):
        facts['itemCondition'] = 'new_new'
        facts['itemConditionEvidence'] = {'source': 'supplier_title', 'path': 'sourceImport.supplier.title',
                                          'sourceUrl': supplier_url, 'text': title}
    special = product.get('specialSizeType')
    if special is not None and (not isinstance(special, str) or len(special) > 2200):
        raise ValueError('特殊尺码分类须为明确的产品资料')
    if isinstance(special, str) and special.strip():
        facts['specialSizeType'] = special.strip()
        facts['specialSizeTypeEvidence'] = {'source': 'product_field', 'path': 'specialSizeType', 'inferred': False}
    elif same_source and isinstance(attributes, dict):
        length, sizes = attributes.get('衣长'), attributes.get('尺码')
        audience = str(product.get('targetAudience') or '').strip().lower()
        raw_sizes = re.split(r'[,，、\s]+', sizes.strip()) if isinstance(sizes, str) else []
        normalized_sizes = {'3XL' if size.upper() == 'XXXL' else size.upper() for size in raw_sizes if size}
        clothing = (product.get('cat') == '服装' and audience in ('women', '女士', '女性')
                    and isinstance(title, str) and bool(re.search(r'T恤|上衣|衬衫|\bshirts?\b|\btops?\b', title, re.I)))
        special_claim = re.search(r'petite|plus\s*size|big\s*(?:and|&)\s*tall|maternity|大码|加大码|孕妇|小个子|高个',
                                  ' '.join(str(v or '') for v in (title, product.get('style'), length)), re.I)
        if (clothing and isinstance(length, str) and length.startswith('普通款')
                and normalized_sizes == {'S', 'M', 'L', 'XL', 'XXL', '3XL'} and not special_claim):
            facts['specialSizeType'] = 'Standard'
            facts['specialSizeTypeEvidence'] = {
                'source': 'inferred_workbench_classification', 'inferred': True,
                'rule': 'ordinary_womens_tops_s_to_3xl_v1', 'sourceUrl': supplier_url,
                'basis': {'productCategory': product['cat'], 'targetAudience': product['targetAudience'],
                          'supplierLength': length, 'supplierSizes': sizes},
                'note': '按普通女士服装系列归为Standard；这是工作台分类，不声称供应商原文写有Standard，不因3XL自动归Plus。',
            }
    _add_water_resistance_fact(facts, product, supplier, same_source)
    return facts


def us_publication_missing_facts(facts):
    """Report the product facts required by the US draft writer before queueing."""
    required = {
        'countryOfOrigin': '本款原产国',
        'careInstructions': '本款护理方式',
        'modelName': '本款实际供应商型号',
        'itemCondition': '本款实际商品成色',
        'specialSizeType': '本款尺码分类',
    }
    return ['请补齐' + label for field, label in required.items() if not facts.get(field)]


def _amount(value, label):
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or number >= 10000000:
            raise InvalidOperation
        return format(number.quantize(Decimal('.01')), 'f')
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(label + '须为明确的GBP正数金额') from None


def _integer(value, label, minimum=0, maximum=100000000):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(label + '须为整数')
    try:
        number = int(str(value))
    except (ValueError, TypeError):
        raise ValueError(label + '须为整数') from None
    if number < minimum or number > maximum:
        raise ValueError(label + '超出允许范围')
    return number


def uk_publication_inputs(source, product, target):
    """Return {ukTarget, ukCommerce} from explicit same-product GBP inputs.

    `source` is the finished US collection snapshot. `target` is account-owned
    connection config. Its UK market IDs are optional: the native edit form
    resolves them and verifies them before saving. US market IDs are never
    copied. Prices/stock/handling are product-owned; a UK quote must carry the
    existing same-source evidence fields rather than an exchange-rate guess.
    """
    if source.get('marketplace') != 'US' or source.get('productId') != product.get('id'):
        raise ValueError('美国快照与当前产品不同')
    skus = [row.get('sku') for row in source.get('goodsItems', [])]
    if not skus or any(not isinstance(sku, str) or not sku for sku in skus) or len(set(skus)) != len(skus):
        raise ValueError('美国快照子SKU集合无效')
    if not isinstance(target, dict) or not target.get('storeName'):
        raise ValueError('请先配置对应英国店铺')
    target_id = target.get('id') or target.get('destinationId')
    if not target_id or target_id == source.get('destination', {}).get('destinationId'):
        raise ValueError('请配置独立的英国目标连接编号')
    if target.get('storeName') == source.get('store'):
        raise ValueError('英国目标不能仍是美国店铺')
    for key, expected in [('countryCode', 'GB'), ('currency', 'GBP'), ('languageTag', 'en_GB')]:
        if target.get(key, expected) != expected:
            raise ValueError('英国目标' + key + '不符')
    shipping = target.get('shippingTemplate')
    if isinstance(shipping, str):
        shipping = {'name': shipping}
    if not isinstance(shipping, dict) or not str(shipping.get('name', '')).strip():
        raise ValueError('请配置英国站实际运输模板名称')
    details = copy.deepcopy((product.get('erpDelivery') or {}).get('UK') or {})
    prices = details.get('variantPrices') or {}
    if not isinstance(prices, dict):
        raise ValueError('英国各变体售价必须按原子SKU保存')
    uniform = details.get('price')
    basis = {'source': 'product_saved_prices', 'currency': 'GBP'}
    if not uniform and not all(sku in prices for sku in skus):
        quote = (product.get('erpDraftPricing') or {}).get('UK') or {}
        if (quote.get('marketplace') == 'UK' and quote.get('currency') == 'GBP'
                and quote.get('sourceUrl') == product.get('sourceUrl')
                and quote.get('scope') == 'quote_based_draft_base_scenario' and quote.get('basisSha256')):
            uniform = quote.get('price')
            basis = {'source': 'saved_selection_quote', 'currency': 'GBP', 'quote': copy.deepcopy(quote)}
    amounts = {sku: _amount(prices.get(sku, uniform), '英国售价 ' + sku) for sku in skus}
    # A copy may retain source stock only under an explicit product-owned policy.
    quantities = details.get('variantQuantities') or {}
    quantity = details.get('quantity')
    if details.get('inventoryPolicy') == 'preserve_source' and quantity is None and not quantities:
        quantities = {row['sku']: row['quantity'] for row in source['goodsItems']}
    stocks = {sku: _integer(quantities.get(sku, quantity), '英国库存 ' + sku) for sku in skus}
    handling = _integer(details.get('handlingDays'), '英国处理时间', 0, 30)
    # Only explicit UK IDs survive. Connection fields stay with the source
    # snapshot and are separately checked by the native publication adapter.
    uk_target = {key: copy.deepcopy(target[key]) for key in
                 ('id', 'destinationId', 'storeName', 'marketId', 'marketplaceId', 'erpUserId', 'erpAccountId', 'categoryHints', 'brand')
                 if target.get(key) is not None}
    uk_target.update(countryCode='GB', currency='GBP', languageTag='en_GB', shippingTemplate=copy.deepcopy(shipping))
    if str(uk_target.get('marketId', '')) == str(source.get('destination', {}).get('marketId', '')) and uk_target.get('marketId'):
        raise ValueError('英国不能沿用美国ERP站点编号')
    if uk_target.get('marketplaceId') == source.get('destination', {}).get('marketplaceId') and uk_target.get('marketplaceId'):
        raise ValueError('英国不能沿用美国Amazon站点编号')
    return {'ukTarget': uk_target, 'ukCommerce': {'currency': 'GBP', 'variantPrices': amounts,
            'quantities': stocks, 'handlingDays': handling, 'pricingBasis': basis}}


def uk_publication_requirements(source, product, target):
    try:
        result = uk_publication_inputs(source, product, target)
        return {'ready': True, 'missing': [], **result}
    except (ValueError, TypeError, KeyError) as error:
        return {'ready': False, 'missing': [str(error)]}
