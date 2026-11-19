"""Explicitly authorized paid end-to-end check against the real product."""
import json
import sqlite3
import time
from pathlib import Path
import sys
import importer
import competitors
import provider
import visual_studio as visual

PRODUCT='IMP-UK-B0FVS1X3SP'
ROOT=Path(__file__).parent
OUT=ROOT/'data'/'live-e2e-20261027'
OUT.mkdir(exist_ok=True)

def dump(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def workspace():
    with sqlite3.connect(ROOT/'data'/'studio.sqlite3') as c:
        return json.loads(c.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])

def product():return next(p for p in workspace()['products'] if p['id']==PRODUCT)

def modify(action):
    with sqlite3.connect(ROOT/'data'/'studio.sqlite3',timeout=20) as c:
        c.execute('BEGIN IMMEDIATE')
        revision,body=c.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
        state=json.loads(body);p=next(p for p in state['products'] if p['id']==PRODUCT)
        action(state,p)
        c.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(state,ensure_ascii=False)))

def sources():
    p=product();dump('product-before.json',p)
    print('SUPPLIER_START',flush=True)
    supplier=importer.preview({'market':'UK','source':p['sourceImport']['supplier']['url']})
    dump('supplier-live.json',supplier)
    print('SUPPLIER',json.dumps({'title':bool(supplier['supplier'].get('title')),'images':len(supplier['supplier'].get('images',[])),'needsBrowser':supplier['supplier'].get('needsBrowser',False)}),flush=True)
    # Preserve previously browser-collected supplier data if direct fetch is blocked.
    if supplier['supplier'].get('title') and not supplier['supplier'].get('needsBrowser'):
        def update(s,p):
            previous=p['sourceImport']['supplier'];fresh=supplier['supplier']
            fresh['images']=list(dict.fromkeys(previous.get('images',[])+fresh.get('images',[])))
            p['sourceImport']['supplier']=fresh;importer.autofill_supplier(p)
        modify(update)
    p=product();facts={k:p.get(k,'') for k in ('style','material','dimensions','features','colorNames','sizeNames','brand','targetAudience')}
    facts['name']=p.get('supplierScope') or p['sourceImport']['supplier'].get('title','')
    print('RESEARCH_START',flush=True)
    research=competitors.analyse({'market':'UK','asins':'B0FVS1X3SP B0G1TDDXY2 B0FWC96WD7 B0FY67QHVZ','source':'sellersprite','mineKeywords':True,'includeReviews':True,'facts':facts})
    dump('research-live.json',research)
    def save(s,p):
        p.setdefault('competitorResearch',{})['UK']=research
        report=research.get('reviewReport')
        if report and report.get('samples'):p.setdefault('reviewResearch',{})['UK']=report
        p['market']='UK'
    modify(save)
    print('RESEARCH_DONE',json.dumps({'readable':sum(x['status']=='ok' for x in research['sources']),'keywords':len(research['keywords']),'reviews':len((research.get('reviewReport') or {}).get('samples',[]))}),flush=True)

def listing():
    print('LISTING_START',flush=True)
    import io
    original=provider.urlopen
    def capture(*args,**kwargs):
        with original(*args,**kwargs) as response:raw=response.read()
        (OUT/('text-response-'+str(time.time_ns())+'.json')).write_bytes(raw)
        return io.BytesIO(raw)
    provider.urlopen=capture
    result=provider.generate_listing(product(),'UK');dump('listing-live.json',result)
    def save(s,p):p.setdefault('pendingCopy',{})['UK']={'copy':result['copy'],'generatedAt':time.time(),'model':result['model']}
    modify(save)
    print('LISTING_DONE',json.dumps({'title':result['copy']['title'],'usage':result['usage']},ensure_ascii=True),flush=True)

def plan():
    p=product();result=json.loads((OUT/'listing-live.json').read_text(encoding='utf-8'))
    ref=(ROOT/'data/live-check/source-url.txt').read_text(encoding='utf-8').strip()
    brief='真实完整流程测试，制作同一件788藏青色连帽夹克。参考图一是唯一产品外观依据。去掉右上浮动火焰营销图标；保留实际胸前、袖章位置和轮廓，不放大或重造细小品牌字。穿着时内领标被身体遮挡，不得复制到脖子或皮肤。禁止不见依据的背面、其他颜色、尺寸数字、包装配件、保暖防水等性能。没有尺码实测与包装清单，第4张改为已提供尺码选择信息，第6张改为可见结构细节。不宣称品牌授权。最多短英文图片文案。每张回答不同购买问题，产品本体不变。'
    print('PLAN_START',flush=True)
    project=visual.plan({'references':[ref],'brief':brief,'count':7,'deliverable':'gallery','language':'en'},p,result['copy'])
    dump('image-project.json',{'id':project['id'],'productId':PRODUCT})
    dump('storyboard.json',project)
    print('PLAN_DONE',project['id'],flush=True)

if __name__=='__main__':
    {'sources':sources,'listing':listing,'plan':plan}[sys.argv[1]]()
