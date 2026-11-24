import json,sqlite3
from pathlib import Path
import visual_studio as v, image_provider
from ivyea_pipeline import IDENTITY
s=json.loads(Path('data/batch-20261030/supplier-B0HH6LTTHZ.json').read_text(encoding='utf-8'))
original=image_provider.api
def capture(*args,**kwargs):
 r=original(*args,**kwargs)
 Path('data/batch-20261030/mesh-analysis-response.json').write_text(json.dumps(r,ensure_ascii=False),encoding='utf-8')
 print('Response shape',list(r),flush=True)
 for c in r.get('choices',[]):print('choice',c.get('finish_reason'),str(c.get('message',{}))[:1800],flush=True)
 return r
image_provider.api=capture
print(v.model_json(IDENTITY,{'product':'white mesh toiletry organizer'},[v.encode_reference(r) for r in s.get('referenceImages',s.get('images'))]))
