import json,sqlite3
from pathlib import Path
from unittest.mock import patch
import competitors,provider
out=Path('data/live-check');r=json.loads((out/'research.json').read_text(encoding='utf-8'))
s=json.loads(sqlite3.connect('data/studio.sqlite3').execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
p=next(p for p in s['products'] if p['id']=='IMP-UK-B0FVS1X3SP')
p=json.loads(json.dumps(p));p['name']='788连帽聚酯纤维冬季外套'
facts={k:p.get(k,'') for k in ('name','material','style','dimensions','features','colorNames','sizeNames','brand')}
with patch('competitors.sellersprite.read_sources',return_value=r['sources']),patch('competitors.review_insights.collect',return_value=r['reviewReport']),patch('competitors.sellersprite.mine_keywords',return_value=r['mining']):
 result=competitors.analyse({'market':'UK','asins':'B0FVS1X3SP','source':'sellersprite','mineKeywords':True,'includeReviews':True,'facts':facts})
(out/'research-grounded.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('GROUNDED_RESEARCH',len(result['keywords']),flush=True)
p['competitorResearch']={'UK':result};p['reviewResearch']={'UK':result['reviewReport']}
try:
 generated=provider.generate_listing(p,'UK')
 (out/'listing.json').write_text(json.dumps(generated,ensure_ascii=False,indent=2),encoding='utf-8')
 print('LISTING',json.dumps({'title':generated['copy']['title'],'highlights':generated['copy']['highlights'],'usage':generated['usage']},ensure_ascii=True),flush=True)
except Exception as e:print('GENERATION_ERROR',type(e).__name__,str(e),flush=True)
