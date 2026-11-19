import json
from pathlib import Path
import visual_studio as v
path=Path('data/batch-20261030/cape-ai-master-plan.json')
p=v.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
for i,image in enumerate(p['uiPlan']['images']):
 image['production_method']='generate_once'
 image['reuse_strategy']='One burgundy master. Transparent variants require separately verified masks and actual SKU references.'
 if i==2:
  image.update(visual_concept='Whole burgundy cape with visible round neckline and outer rolled hem, no interior or unsupported macro construction.',camera_direction='Front three-quarter full cape with neckline visible, no hidden inner facing or seam cross sections.')
 image['render_prompt']=v.compile_prompt(p,i)
 p['plan']['slots'][i]['composition']=image['render_prompt']
p['uiPlan']['productionDecision']={'by':'operator','reason':'AI omitted production_method. Checked all four source-supported views; omit unknown interiors, fiber claims and dimensions. User explicitly authorized generated master.'}
v.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
print('CAPE_STORYBOARD_CONFIRMED')
