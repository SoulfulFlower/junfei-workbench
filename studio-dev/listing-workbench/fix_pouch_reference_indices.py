"""Correct the planner's one-based indices for its sole supplied reference.
The recorded invalid-reference run failed before image_provider.submit.
"""
import json,time
from pathlib import Path
import visual_studio as v
path=Path('data/batch-20261030/pouch-ai-master-plan.json')
p=v.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
assert len(p['references'])==1
for im in p['uiPlan']['images']:
    assert im.get('source_reference_indices') in ([1],[0])
    im['source_reference_indices']=[0]
p.setdefault('corrections',[]).append({'time':time.time(),'reason':'Planner used one-based 1 for the sole reference; bind to zero-based 0 before provider submission.'})
v.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
for r in v.list_projects(p['productId'])['runs']:
    if r['projectId']==p['id'] and r['status']=='submit_unknown' and not r.get('jobIds') and r.get('error','').startswith('分镜参考图关联无效'):
        r.update(status='failed',failureStage='local_reference_validation',providerSubmitted=False)
        v.save_run(r)
        # Keep this failed record as history; the producer permits this exact local-only failure.
print('REFERENCE_FIXED',p['id'])
