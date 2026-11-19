import json
from pathlib import Path
import visual_studio as v
root=Path('data/batch-20261030');log=root/'remaining-repairs-3.json'
records=json.loads(log.read_text(encoding='utf-8')) if log.exists() else []
fixes={
 'cover':{1:'One overhead oblique patio photo looking down on the black covered rectangular furniture, camera high enough that no furniture legs or underside can be seen. One scene only, complete cover, consistent daylight.'},
 'elastic':{0:'Directly overhead flat product presentation on pure white. Show the complete square printed fitted cover with only its rolled elastic perimeter. Thin invisible support, absolutely no visible furniture legs or table base. Preserve exact original hibiscus pattern scale and density.',1:'Direct overhead view of the same exact tropical hibiscus printed fitted square cover in a quiet dining setting. No people, chairs, hands or utensils. Preserve exact print repeat, floral density and square outline from the source. No rounded table corners.'},
 'mesh':{1:'Single open empty white mesh pouch at clean bathroom vanity. Preserve the exact rectangular fabric zipper pull TAB from source, never a ring pull. Whole product visible, actual low front pocket and WHITE retaining bands. No brush, toothbrush, hand or cosmetic props.'},
 'evening':{1:'One close front view focusing on the asymmetric pleated satin front, entire bag still visible but filling the image. Preserve exact champagne pleats. No model, hand, props, inset or collage.',2:'One champagne clutch suspended by its actual gold-tone chain on an unbranded simple garment rail beside an adult evening outfit on a hanger. No people, hands or body parts. Complete bag visible, realistic chain contact and gravity.'}}
for name,slots in fixes.items():
 path=root/(name+'-ai-master-plan.json');p=v.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
 for slot,direction in slots.items():
  if any(x['name']==name and x['slot']==slot for x in records):continue
  previous=next(r for r in v.list_projects(p['productId'])['runs'] if r['projectId']==p['id'] and r['slot']==slot)
  if previous['status']!='needs_revision':continue
  im=p['uiPlan']['images'][slot];im.update(scene=direction,visual_concept=direction,camera_direction=direction,layout='white_main' if slot==0 else 'poster_hero',product_presence='hero')
  if name=='mesh':
   im['evidence']='Source photographs show the actual open pouch, low front pocket and white retaining bands. Empty pouch is supported; no hand interaction is required.'
   p['plan']['slots'][slot]['evidence']=im['evidence']
  if name=='evening' and slot==2:
   im.update(headline='Evening Outfit Accent',subline='Pleated satin with a gold-tone chain')
   p['plan']['slots'][slot].update(headline=im['headline'],caption=im['subline'])
  im['render_prompt']=v.compile_prompt(p,slot);p['plan']['slots'][slot]['composition']=im['render_prompt'];p['set_qa']=None
  v.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
  record={'name':name,'slot':slot,'previousRun':previous['id'],'status':'submitting'};records.append(record);log.write_text(json.dumps(records,indent=2),encoding='utf-8')
  r=v.generate({'id':p['id'],'slot':slot,'model':'gpt-image-2','size':'1:1','resolution':'2K','autoRepair':False})
  record.update(runId=r['id'],status=r['status']);log.write_text(json.dumps(records,indent=2),encoding='utf-8');print(name,slot+1,r['id'],flush=True)
