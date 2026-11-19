import json,sqlite3,io
from pathlib import Path
import provider
out=Path('data/live-check');r=json.loads((out/'research-grounded.json').read_text(encoding='utf-8'))
s=json.loads(sqlite3.connect('data/studio.sqlite3').execute('SELECT body FROM workspace WHERE id=1').fetchone()[0]);p=next(p for p in s['products'] if p['id']=='IMP-UK-B0FVS1X3SP');p['name']='788连帽聚酯纤维冬季外套';p['competitorResearch']={'UK':r};p['reviewResearch']={'UK':r['reviewReport']}
original=provider.urlopen
def capture(*a,**k):
 with original(*a,**k) as response:body=response.read()
 (out/'listing-response.json').write_bytes(body)
 return io.BytesIO(body)
provider.urlopen=capture
try:
 result=provider.generate_listing(p,'UK');(out/'listing.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('SUCCESS',json.dumps(result['usage']),flush=True)
except Exception as e:print('ERROR',str(e),flush=True)
