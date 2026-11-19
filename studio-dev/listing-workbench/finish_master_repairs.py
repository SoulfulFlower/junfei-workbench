"""Recorded one-shot repairs for concrete physical defects; no color renders."""
import json
from pathlib import Path
import visual_studio as v
root=Path('data/batch-20261030');log=root/'master-repairs-4.json'
records=json.loads(log.read_text(encoding='utf-8')) if log.exists() else []
fixes={
'cape':{0:'Full-front adult model on pure white wearing the exact burgundy high-low sheer cape over a plain fitted champagne dress. Both arms rest naturally behind the long cape side panels; hands fully hidden by fabric, not visible. Exact round neckline and short front, long back. No other props or text.',3:'Three-quarter side-front adult model wearing the exact burgundy high-low sheer cape. Hands naturally held behind the body and fully occluded, no visible fingers. Show round neck, short front, long trailing sides in one restrained setting. No rear construction, no invented seams.'},
'evening':{2:'The exact champagne pleated clutch resting on a plain evening dressing table beside a separate plain folded dark scarf. No hands, models, hooks or rail. Gold-tone short chain lies naturally alongside the bag without intersections. Exact asymmetric source pleats, whole bag visible, no extra bags.'},
'elastic':{1:'Direct flat overhead photograph. Exact tropical printed square fitted tablecloth, square outline and original floral density, on thin square tabletop filling nearly the entire frame. No chairs, table legs, people, props or room furniture. Show elastic perimeter clearly without exaggerated thickness.'}}
for name,slots in fixes.items():
 path=root/(name+'-ai-master-plan.json');p=v.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
 for slot,direction in slots.items():
  if any(x['name']==name and x['slot']==slot for x in records):continue
  prev=next(r for r in v.list_projects(p['productId'])['runs'] if r['projectId']==p['id'] and r['slot']==slot)
  if prev['status']!='needs_revision':continue
  im=p['uiPlan']['images'][slot];im.update(scene=direction,visual_concept=direction,camera_direction=direction)
  if name=='evening':
   im.update(headline='An Evening Outfit Accent',subline='Pleated satin and a gold-tone chain')
   p['plan']['slots'][slot].update(headline=im['headline'],caption=im['subline'])
  p['plan']['slots'][slot]['composition']=v.compile_prompt(p,slot);p['set_qa']=None;v.save_project(p)
  path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
  rec={'name':name,'slot':slot,'previousRun':prev['id'],'status':'submitting'};records.append(rec);log.write_text(json.dumps(records,indent=2),encoding='utf-8')
  r=v.generate({'id':p['id'],'slot':slot,'model':'gpt-image-2','size':'1:1','resolution':'2K','autoRepair':False})
  rec.update(runId=r['id'],status=r['status']);log.write_text(json.dumps(records,indent=2),encoding='utf-8');print(name,slot+1,r['id'],flush=True)
