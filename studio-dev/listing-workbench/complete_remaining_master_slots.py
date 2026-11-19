"""One recorded retry after visible provider log reconciliation; no automatic retries."""
import json,time
from pathlib import Path
import visual_studio as v

root=Path('data/batch-20261030')
journal=root/'remaining-master-submissions.json'
records=json.loads(journal.read_text(encoding='utf-8')) if journal.exists() else []
targets=[('cape',1,'a65cf7e045844c04a98bba9bf7503e68'),('cover',1,'21e6ce9e26c7441187c4a5feed231e27'),('evening',2,'68eba6692ca949dca2efbe051c072817')]
for name,slot,old_id in targets:
    if any(r['name']==name and r['slot']==slot for r in records):continue
    p=v.get_project(json.loads((root/(name+'-ai-master-plan.json')).read_text(encoding='utf-8'))['id'])
    old=v.get_run(old_id)
    if old['status']=='submit_unknown':
        old['operatorAudit']={'at':time.time(),'source':'APIMart logged-in task log, pages 1 and 2, 263 total records','finding':'No image task between 2026-10-30 14:51:32 and 15:00:42. Both local submissions ended at 14:53. All surrounding provider IDs map to known local jobs.','decision':'One replacement submission; retain old record and evidence.'}
        v.save_run(old)
    elif name=='evening':
        direction='One exact champagne clutch on a plain evening dressing table. Front face parallel to camera, no foreshortening. Preserve the source asymmetric radiating satin pleats on BOTH sides of the central band, including the original right-side folds. Gold short chain is the original flattened interlocking CURB-LINK chain, NEVER round cable links. Chain rests naturally to the side without intersections or fabricated attachments. No people, hands, scarves, hooks, extra bags or jewelry. Product occupies most of frame; restrained warm evening light, plain muted background.'
        p['uiPlan']['images'][slot].update(scene=direction,visual_concept=direction,camera_direction=direction)
        p['plan']['slots'][slot]['composition']=v.compile_prompt(p,slot)
        p['set_qa']=None;v.save_project(p)
    else:raise ValueError('Unexpected previous status')
    rec={'name':name,'slot':slot,'previousRun':old_id,'status':'submitting'}
    records.append(rec);journal.write_text(json.dumps(records,indent=2),encoding='utf-8')
    r=v.generate({'id':p['id'],'slot':slot,'model':'gpt-image-2','size':'1:1','resolution':'2K','autoRepair':False})
    rec.update(status=r['status'],runId=r['id']);journal.write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(name,slot+1,r['id'],flush=True)
