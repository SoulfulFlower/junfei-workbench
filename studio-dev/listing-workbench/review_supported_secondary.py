"""Recheck supported secondary styling; never waive identity defects."""
import json
from pathlib import Path
import visual_studio as v
root=Path('data/batch-20261030')
cases=[('mesh',1,'1f79a60de89d4028835764a726f4c2eb','An EMPTY open white mesh pouch at a bathroom vanity. Generic unbranded bathroom items may appear in the background, clearly separate from the sold pouch. Actual rectangular zipper tab, low pocket and white retaining bands remain exact; no invented accessories attached to the pouch.'),('evening',1,'fcb61ef1e8e64c1d8d8d2d1830a8da6a','One champagne pleated clutch in a restrained neutral product setting, on a plain surface. The whole bag remains visible, filling the frame to demonstrate the actual asymmetric pleats. No extra bags, inset, hands, labels or unsupported contents.')]
for name,slot,rid,direction in cases:
 path=root/(name+'-ai-master-plan.json');p=v.get_project(json.loads(path.read_text(encoding='utf-8'))['id']);r=v.get_run(rid)
 if any(q.get('operatorRecheck') for q in r.get('qc',[])):continue
 im=p['uiPlan']['images'][slot];im.update(scene=direction,visual_concept=direction,camera_direction='One coherent whole-product photograph with natural lighting, realistic scale, no collage.')
 p['plan']['slots'][slot]['composition']=v.compile_prompt(p,slot)
 p.setdefault('operatorReview',[]).append({'slot':slot,'runId':rid,'reason':'Secondary background surfaces and separate generic styling props are allowed when source-supported product identity and sale contents remain intact. Recheck independently; never force pass.'})
 v.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
 qc=v.review(p,slot,r['image']);qc['operatorRecheck']=True;r['qc'].append(qc);r['status']='awaiting_manual' if qc['pass'] else 'needs_revision';v.save_run(r)
 print(name,r['status'],json.dumps(qc,ensure_ascii=False),flush=True)
