import json
from pathlib import Path
import live_e2e,colour_sets
p=live_e2e.product();refs=json.loads(Path('data/colour-check/urls.json').read_text(encoding='utf-8'))
s=colour_sets.start({'productId':p['id'],'color':'红色 / Red','reference':refs[1],'model':'gpt-image-2','confirmed':True},p)
Path('data/colour-check/live-set.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8');print(s['id'],flush=True)
colour_sets.work(s);print(s['status'],flush=True)
