"""Remove a redundant spec text block; retain and recheck the actual dimension diagram."""
import json
from pathlib import Path
import visual_studio as v,studio_bridge as b
root=Path('data/batch-20261030');path=root/'bag-ai-master-plan.json'
p=v.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
r=next(r for r in v.list_projects(p['productId'])['runs'] if r['projectId']==p['id'] and r['slot']==3)
if r['status']!='needs_revision':raise SystemExit('No failed dimension copy to review')
im=p['uiPlan']['images'][3]
im['big_number']=''
im['copyRevisionNote']='Removed redundant combined size block. Retained exact full width/depth/height sentence and verified dimension callouts; no product or measurement change.'
p['copyRevisions']=p.get('copyRevisions',[])+[{'slot':3,'reason':im['copyRevisionNote'],'runId':r['id']}]
v.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
qc=v.review(p,3,r['image'])
r['qc'].append(qc);r['status']='awaiting_manual' if qc['pass'] else 'needs_revision';v.save_run(r)
if qc['pass']:
    raw,mime=b.result_image(r['id']);(root/'ai-master-bag/4.png').write_bytes(raw)
print('DIMENSION_COPY_REVIEW',r['status'],json.dumps(qc,ensure_ascii=True),flush=True)
