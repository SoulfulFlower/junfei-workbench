"""Verified size data, seven-image direction and byte-identical variant reuse."""
import copy
import hashlib
import io
from PIL import Image

REVIEW_RULE = '''This slot is the single size chart SHARED UNCHANGED across every colour/size variant by explicit user instruction. localPixelEvidence.sharedSizeChart is server verified against the current storyboard size_chart slot, locked master bytes and exact SHA256. Do not require its small product preview to match the target variant colour. Still compare every measurement, unit, label and readability to verifiedSizeEvidence/plannedCopy. Incorrect data, missing rows, unreadable text, altered source or damaged artwork remain blocking. This rule applies ONLY to the verified size-chart slot; all other garment colour/identity checks are unchanged.'''

def layout_contract(chart):
    if chart.get('style')=='editorial-split-v1':
        return 'One square chart: left 50 percent is a large approved white-background merchandise preview, garment complete. Right 50 percent is a warm ivory panel, with SIZE & FIT and the cm subtitle at its top, and the four-column exact source-data table below. Fine brown rules, no large grey header band; one unit label. Data and merchandise fidelity remain binding.'
    return 'One square chart with a clear Size Guide title, original-source preview, and complete exact measurement table with original units.'

def size_plan(recipe):
    chart=recipe['sizeChart'];source=recipe['primaryReferenceIndex']
    return {'identity':'Same source-verified merchandise; measurements only from the frozen source chart',
        'style':{'photography':'Approved merchandise preview without product redraw'},
        'planSource':'deterministic verified-size-layout contract, not an AI storyboard',
        'shots':[{'kind':'size','layout':'feature','sourceIndex':source,
            'question':'What are the sourced measurements?', 'evidence':'All values and units are frozen from '+chart['source'],
            'scene':layout_contract(chart),'camera':'Use only the frozen approved preview; preserve full visible garment and source proportions.',
            'copy':['SIZE & FIT' if chart.get('style')=='editorial-split-v1' else 'Size Guide','Garment measurements / '+chart['units']]} for _ in range(recipe['count'])]}

def from_product(product):
    from ivyea_pipeline import project_size_chart
    chart=project_size_chart(product,[])
    if not chart:
        raise ValueError('尺码图缺少当前商品有来源的真实尺寸表，不用模型补造')
    columns=chart['columns']
    rows=chart['rows']
    sizes={s.strip() for s in str(product.get('sizeNames','')).split(',') if s.strip()}
    if sizes and not sizes.issubset({str(row[0]) for row in rows}):
        raise ValueError('真实尺寸表未覆盖全部拟售尺码')
    if len(set(columns))!=len(columns):raise ValueError('尺码表列名重复')
    # Preserve exact sourced labels and values. The wire adapter calls the first
    # column "size"; the typesetter retains the actual column labels separately.
    return {'source':chart.get('sourcePage') or chart['sourceImage'], 'units':chart['units'],
        'measurementMethod':chart.get('measurementBasis') or chart.get('measurementMethod') or chart.get('measurementsScope') or 'Original source table; measurement method not supplied',
        'style':'editorial-split-v1', 'columns':list(columns), 'rows':[{'size':row[0],**dict(zip(columns[1:],row[1:]))} for row in rows],
        'sourceEvidence':copy.deepcopy(chart)}

def table(chart):
    columns=chart.get('columns') or ['Size',*[key for key in chart['rows'][0] if key!='size']]
    if not isinstance(columns,list) or len(columns)<2 or not chart.get('rows'):raise ValueError('完整尺码表缺失')
    rows=[]
    for row in chart['rows']:
        values=[row['size'],*[row.get(key) for key in columns[1:]]]
        if any(v is None or not str(v).strip() for v in values):raise ValueError('尺码表数据不完整')
        rows.append(values)
    return {'columns':columns,'rows':rows,'units':chart['units'],
        'measurementsScope':chart.get('sourceEvidence',{}).get('measurementsScope')}

def render_candidate(chart,source,index,cache):
    from product_artwork import compose_size_chart
    raw_source=io.BytesIO();source.save(raw_source,'PNG')
    if chart.get('style')=='editorial-split-v1':
        from size_chart_layouts import editorial
        raw,layout=editorial(source,table(chart))
    elif chart.get('style') in (None,'classic-v1'):
        raw=compose_size_chart(raw_source.getvalue(),table(chart),'Size Guide');layout={'style':'classic-v1'}
    else:raise ValueError('尺码图版式无效')
    original=Image.open(io.BytesIO(raw));native=cache(original)
    delivered=cache(original.resize((1600,1600),Image.Resampling.LANCZOS))
    return {'index':index,'image':delivered['url'],'raw':native['url'],'aspectValid':True,
        'productionMethod':'verified-size-data-typesetting','sharedAcrossAllVariants':True,'sizeLayout':layout,
        'sizeDataSha256':hashlib.sha256(__import__('json').dumps(chart,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'sourceSha256':hashlib.sha256(raw_source.getvalue()).hexdigest()}

def check_seven(images):
    from storyboard_variety import is_scene
    from ivyea_render_core import _layout_family
    if len(images)!=7:raise ValueError('新七图须为白底1、细节2、种草3、尺码1')
    detail=lambda card:card.get('shot_type')=='detail' or _layout_family(card)=='detail_macro'
    if (images[0].get('shot_type')!='white_main' or not all(detail(c) and not is_scene(c) for c in images[1:3])
            or not all(is_scene(c) and not detail(c) for c in images[3:6])
            or detail(images[6]) or is_scene(images[6])):
        raise ValueError('七图图位须为：白底主图1、两张不同细节、三张种草摄影、共用尺码图7；不可换成其他图种')

def reuse_receipt(source,load):
    raw=load(source['source']);digest=hashlib.sha256(raw).hexdigest()
    if digest!=source['sharedSizeChart'].get('sourceSha256'):
        raise ValueError('全变体共用尺码图源文件已经变化')
    return {'image':source['source'],'sha256':digest,'renderer':'shared-size-chart-byte-reuse-v1',
        'sourceHash':source['sourceHash'],'sharedAcrossAllVariants':True,
        'imageGenerationSubmitted':False,'garmentSelectionPerformed':False,'changedPixels':0}

def verify_reuse(item,source_raw,result_raw,project):
    cards=project.get('uiPlan',{}).get('images',[]);slot=item.get('slot')
    if type(slot) is not int or not 0<=slot<len(cards) or cards[slot].get('size_chart') is not True:
        raise ValueError('共用尺码图必须绑定当前分镜真实尺码图位')
    digest=hashlib.sha256(source_raw).hexdigest()
    if item.get('sharedSizeChart',{}).get('sourceSha256')!=digest or result_raw!=source_raw:
        raise ValueError('共用尺码图必须完整逐字节复用当前母版，禁止换色或改表')
    return {'sharedSizeChart':True,'unchangedPixels':True,'byteIdentical':True,
        'sourceSha256':digest,'verifiedSizeEvidence':project.get('sizeEvidence'),
        'sharedAcrossAllVariants':True}
