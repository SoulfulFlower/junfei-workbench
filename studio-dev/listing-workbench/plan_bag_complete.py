import json
import sqlite3
from pathlib import Path
import visual_studio

root=Path('data/batch-20261030');target=root/'bag-complete-plan.json'
colors=json.loads((root/'bag-detail/colors.json').read_text(encoding='utf-8'))
detail=json.loads((root/'bag-detail/observed-urls.json').read_text(encoding='utf-8'))['detailImages']
path=root/'supplier-B0G6LGTCTS.json';e=json.loads(path.read_text(encoding='utf-8'))
e.update(variantReferences=colors,detailImages=detail,dimensions='30 × 13 × 23 cm (supplier body dimensions)',dimensionsEvidence=detail[1],observedAt='2026-10-30')
path.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding='utf-8')
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
    db.execute('BEGIN IMMEDIATE')
    revision,raw=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone();state=json.loads(raw)
    p=next(p for p in state['products'] if p['id']=='IMP-US-B0G6LGTCTS')
    p.update(supplierVerification=e,supplierColorReferences=colors,assetColorBindings={r['url']:r['color'] for r in colors},masterColor='咖色',dimensions=e['dimensions'])
    p['imageReferenceSelection']={'primary':colors[1]['url']}
    listing=state['copy'][p['id']+'-US']
    db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(state,ensure_ascii=False)))
if not target.exists():
    project=visual_studio.plan({'references':[colors[1]['url'],detail[3],detail[1]],'count':4,'deliverable':'gallery','language':'en','brief':'Create a 4-image reusable source-photo gallery, no image-generation submissions. Slot0 isolated actual bag on white without text. Slot1 real wearing photo, show scale without inventing capacity claims. Slot2 body dimensions 30 x 13 x 23 cm based on supplier chart image3; no phone model, no strap-length claim. Slot3 visible bow and plaid detail, using a local crop of the actual main photograph with product context. Every image must use source_layout, no redrawing. These are nylon bags with nylon lining per supplier. Size refers to product body, never shipping package. Other colors have real SKU photographs, so reuse layout with actual photos rather than recolor prints. Do not add brand names, durability, waterproofing, or package-count claims. Source brand/rights are still unresolved; do not put internal audit warnings in public art.'},p,listing)
    target.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
else:project=json.loads(target.read_text(encoding='utf-8'))
print(json.dumps([{'slot':i,'headline':im.get('headline'),'subline':im.get('subline'),'method':im.get('production_method'),'evidence':im.get('evidence')} for i,im in enumerate(project['uiPlan']['images'])],ensure_ascii=False,indent=2),flush=True)
