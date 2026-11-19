"""Normalize visible 1688 SKU quotes and item-size tables without promoting to facts."""
import math
import re
from urllib.parse import urlsplit


def image_url(value):
    if not isinstance(value,str) or len(value)>3000 or any(ord(c)<32 for c in value):return ''
    try:
        parts=urlsplit(value)
        if (parts.scheme=='https' and re.fullmatch(r'cbu\d+\.alicdn\.com',parts.hostname or '')
                and parts.port in (None,443) and not parts.username and not parts.password
                and parts.path.startswith('/img/ibank/')):return value
    except ValueError:pass
    return ''


def image_capture(data,images):
    """Keep browser observations, never promote them to production approval."""
    rows=data.get('imageObservations',[])
    if not isinstance(rows,list) or len(rows)>80:raise ValueError('货源图片观察超出允许范围')
    observations=[]
    for raw in rows:
        if not isinstance(raw,dict) or raw.get('url') not in images:continue
        item={'url':raw['url'],'origin':raw.get('origin') if raw.get('origin') in ('product_page','supplier_detail') else 'unspecified',
              'visuallyReviewed':False,'productionApproved':False,'evidenceScope':'browser_observation'}
        for field in ('width','height','observedWidth','observedHeight'):
            value=raw.get(field)
            if type(value) is int and 0<value<=20000:item[field]=value
        observed=image_url(raw.get('observedUrl'))
        if observed:item['observedUrl']=observed
        if raw.get('originalStatus')=='browser_loaded_larger_original' and observed:
            parts=urlsplit(observed)
            expected=parts._replace(path=parts.path.removesuffix('_sum.jpg')).geturl()
            if parts.path.endswith('_sum.jpg') and expected==raw['url']:
                item['originalStatus']='browser_loaded_larger_original'
        elif raw.get('originalStatus')=='thumbnail_retained_original_unavailable':
            item['originalStatus']='thumbnail_retained_original_unavailable'
        observations.append(item)
    thumbnails=[u for u in images if urlsplit(u).path.endswith('_sum.jpg')]
    small=[r['url'] for r in observations if min(r.get('width',20001),r.get('height',20001))<=80]
    return {'imageObservations':observations,'imageCaptureSummary':{
        'imageCount':len(images),'observedImageCount':len(observations),
        'largerOriginalsLoaded':sum(r.get('originalStatus')=='browser_loaded_larger_original' for r in observations),
        'thumbnailCount':len(set(thumbnails+small)),'productionApproved':False}}


def text(value, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError('货源规格采集格式或长度无效')
    return value.strip()


def number(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+)?', value.strip()): return None
    result = float(value)
    return result if math.isfinite(result) and result > 0 else None


def normalize(data):
    rows = data.get('skuRows', [])
    tables = data.get('packagingTables', [])
    if not isinstance(rows, list) or len(rows) > 300 or not isinstance(tables, list) or len(tables) > 10:
        raise ValueError('货源规格采集超出允许范围')
    packages = {}
    duplicate_packages = set()
    for table in tables:
        if not isinstance(table, list) or len(table) > 301: raise ValueError('货源包装表格式无效')
        if not table: continue
        if any(not isinstance(row, list) or len(row) > 12 for row in table): raise ValueError('货源包装行格式无效')
        table = [[text(cell, 1000) for cell in row] for row in table]
        header = [re.sub(r'\s+', '', cell).replace('（', '(').replace('）', ')') for cell in table[0]]
        expected = ['规格', '长(cm)', '宽(cm)', '高(cm)', '体积(cm³)', '重量(g)']
        if header != expected: continue  # Unknown units/layout never guessed.
        for row in table[1:]:
            if len(row) != 6 or not row[0]: continue
            label = row[0]
            if label in packages: duplicate_packages.add(label)
            packages[label] = {'rawCells': row, 'lengthCm': number(row[1]), 'widthCm': number(row[2]),
                'heightCm': number(row[3]), 'volumeCm3': number(row[4]), 'weightG': number(row[5]),
                'weightScope': 'supplier_item_weight_unspecified',
                'warning': '供应商件重尺表；未说明净重或毛重，包装和实际发货重量待核实'}
    variants = []
    seen = set()
    for raw in rows:
        raw = text(raw, 2000)
        # Price is scoped to this visible SKU row, never the global coupon/range headline.
        match = re.fullmatch(r'(.+?)\s*[¥￥]\s*(\d+(?:\.\d+)?)\s*库存\s*(\d+)\s*件\s*', raw, re.S)
        if not match: continue
        label = match[1].strip()
        if not label: continue
        item = {'label': label, 'quoteRaw': raw, 'currency': 'CNY',
            'displayPriceCny': number(match[2]), 'supplierStock': int(match[3]),
            'quoteScope': 'displayed_sku_price', 'verifiedPurchasePrice': False,
            'warning': '页面展示参考价，会员折扣/起订量/税费/运费及结算价需核实；供应商库存不是店铺库存'}
        if label in packages and label not in duplicate_packages: item['itemPackage'] = packages[label]
        if label in seen: item['conflict'] = '同规格出现多条报价，不能自动选择'
        seen.add(label)
        variants.append(item)
    duplicates = {v['label'] for v in variants if 'conflict' in v}
    for variant in variants:
        if variant['label'] in duplicates: variant['conflict'] = '同规格出现多条报价，不能自动选择'
    return {'variants': variants, 'packagingTables': tables,
        'warnings': ['采集的SKU报价和件重尺仅作货源参考；不自动修改采购成本、包装毛重、库存或生产图片'],
        'unparsedSkuRowCount': len(rows) - len(variants)}
