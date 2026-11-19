import json,sqlite3,sys
from pathlib import Path
import importer,market_research,competitors

root=Path('data/batch-20261030');cape='--cape' in sys.argv
asin='B0H4R6193H' if cape else 'B0FG3F13K2';pid='IMP-US-'+asin
facts=json.loads((root/('supplier-candidate-cape-alternative.json' if cape else 'supplier-candidate-'+asin+'.json')).read_text(encoding='utf-8'))
facts.update(status='source_photos_verified_pending_ip_and_freight')
if not cape:
    facts.update(productDimensionsCm=[25,14.5,2],packageCm=[25,14.5,2],packageWeightG=200)
    facts['holds'].remove('实物图片与目标款式细节待比对')
(root/('supplier-'+asin+'.json')).write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
reference=None
for path in root.glob('pool-*.json'):
    for row in market_research.rows(json.loads(path.read_text(encoding='utf-8'))):
        if row.get('asin')==asin:reference=market_research.candidate(row,'US')
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
    db.execute('BEGIN IMMEDIATE')
    revision,body=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
    state=json.loads(body)
    if not any(p['id']==pid for p in state['products']):
        (root/f'workspace-before-evening-{revision}.json').write_text(body,encoding='utf-8')
        importer.merge_browser_capture(state,{'url':facts['url'],'title':facts['title'],'attributes':{'材质':facts['attributes']['material'],'颜色':','.join(facts['colors']),'资料核实状态':'未完成侵权和运费审核'},'images':facts['images'],'asin':asin,'market':'US','capturedAt':'2026-10-30'})
        p=next(p for p in state['products'] if p['id']==pid)
        p.update(name='前短后长雪纺披肩' if cape else '褶皱链条晚宴包',brand='',manufacturer='',cat='服装' if cape else '日用百货',status='待补资料',supplierVerification=facts,selectionResearch={'reference':reference,'batch':'20261030'},productionReview={'publishReady':False,'remainingIssue':'；'.join(facts['holds'])})
        p['copyNotes']='雪纺纤维未明确，不宣称真丝；尺寸标注口径不明，不承诺适配身高或实测长度；不售搭配裙子，不使用朗弗诺或Hedovan品牌。' if cape else '外层成分未明确，不宣称真丝；只售香槟色和黑色。含一条短链，不承诺长肩带。不得使用GORGLITTER或静居品牌。'
        db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(state,ensure_ascii=False)))
        print('IMPORTED',pid,flush=True)
target=root/('keywords-'+asin+'.json')
if not target.exists():
    result=competitors.analyse({'market':'US','asins':asin,'source':'sellersprite','mineKeywords':True,'facts':facts})
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('KEYWORDS',len(result.get('keywords',[])),flush=True)
