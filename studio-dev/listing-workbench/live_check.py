import json,time
from pathlib import Path
import importer,competitors
out=Path('data/live-check');out.mkdir(exist_ok=True)
r=importer.preview({'market':'UK','source':'https://detail.1688.com/offer/958196845665.html'})
(out/'supplier.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print('SUPPLIER',bool(r['supplier']['title']),r['supplier'].get('needsBrowser'),flush=True)
try:
 result=competitors.analyse({'market':'UK','asins':'B0FVS1X3SP','source':'sellersprite','mineKeywords':True,'includeReviews':True,'facts':{}})
 (out/'research.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print('RESEARCH',json.dumps({'sources':[{k:s.get(k) for k in ('asin','status','title','error')} for s in result.get('sources',[])],'keywords':len(result.get('keywords',[])),'reviews':len((result.get('reviewReport') or {}).get('samples',[])),'reviewError':(result.get('reviewReport') or {}).get('error'),'analysisError':(result.get('reviewReport') or {}).get('analysisError')},ensure_ascii=False),flush=True)
except Exception as e:print(type(e).__name__,str(e),flush=True)
