import json
from pathlib import Path
import visual_studio as v,studio_bridge as b
x=json.load(open('data/live-check/full-image-runs.json'))
for i in (1,3,5):
 r=v.get_run(x['runs'][i]);p=v.get_project(r['projectId'])
 if i==1:
  try:raw,mime=b.result_image(r['id']);Path('data/live-check/full-set/2.jpg').write_bytes(raw);print('SCENE_SAVED',flush=True)
  except Exception as e:print('SCENE_ERROR',str(e),flush=True)
 if r['status']=='review_error' and r.get('image'):
  try:
   qc=v.review(p,i,r['image']);r['qc'].append(qc);r.update(status='awaiting_manual' if qc['pass'] else 'needs_revision');r.pop('error',None);v.save_run(r);print('QC',i,qc['pass'],flush=True)
  except Exception as e:print('QC_ERROR',i,str(e),flush=True)
