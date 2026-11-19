"""Reassess a supported usage composition without paying for another render."""
import json,time
from pathlib import Path
import visual_studio as v

root=Path('data/batch-20261030');path=root/'mesh-ai-master-plan.json'
p=v.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
r=v.get_run('61a2bf8e07404191bfd857ad4d5a47ab')
image=p['uiPlan']['images'][1]
direction='Single open white pouch at adult bathroom vanity. One plain unbranded brush and toothbrush held by the actual white retaining bands as in source reference 0. Contents are styling props, not included. Construction remains visible, no additional compartments.'
image.update(scene=direction,visual_concept=direction,camera_direction='Whole upright open product, realistic eye-level close photograph; no hands or collage.')
image['render_prompt']=v.compile_prompt(p,1)
p['plan']['slots'][1]['composition']=image['render_prompt']
p.setdefault('operatorReview',[]).append({'at':time.time(),'slot':1,'reason':'Actual source 0 visibly demonstrates a toothbrush retained inside. Keep this factual use composition instead of the stricter arbitrary empty-only secondary direction. Product identity and copy unchanged; rerun independent QA, no approval override.','runId':r['id']})
v.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
qc=v.review(p,1,r['image']);r['qc'].append(qc)
r['status']='awaiting_manual' if qc['pass'] else 'needs_revision'
v.save_run(r)
print(json.dumps({'status':r['status'],'qc':qc},ensure_ascii=False),flush=True)
