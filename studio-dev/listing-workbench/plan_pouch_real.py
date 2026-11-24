import json,sqlite3
from pathlib import Path
import visual_studio
root=Path('data/batch-20261030')
colors=json.loads((root/'pouch-colors/colors.json').read_text(encoding='utf-8'))
with sqlite3.connect('data/studio.sqlite3') as db:state=json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
p=next(p for p in state['products'] if p['id']=='IMP-US-B0HJH859M9')
target=root/'pouch-real-plan.json'
if not target.exists():
    project=visual_studio.plan({'references':[colors[0]['url']], 'count':4,'deliverable':'gallery','language':'en','brief':'Analyze the actual supplier photograph before making this four-image reusable storyboard. Use only source_layout; no paid image generation or redrawing. Buyer-facing differentiators are the visible curved clutch profile and knitted leopard motif. Slot0 main requires genuine white background; source has beige environment, so mark blocked unless true local isolation can preserve the product. Slot1 full real product photograph with one concise visual-style benefit. Slot2 local close-up of the actual knit and motif with product context. Do not claim size, capacity, waterproofing, certification, brand, hardware, or package count. Supplier package dimensions are not body dimensions. Eight actual SKU photographs are available; reuse this layout with each exact photograph, do not recolor patterns. Slot3 show the full clutch profile as an outfit accessory using only the real photograph; no invented model or outfit. No invented objects or interior views.'},p,state['copy'][p['id']+'-US'])
    target.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
else:project=json.loads(target.read_text(encoding='utf-8'))
print(json.dumps(project['uiPlan'],ensure_ascii=False),flush=True)

