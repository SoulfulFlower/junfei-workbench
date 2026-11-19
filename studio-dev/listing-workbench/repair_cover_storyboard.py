"""One targeted repair of the rejected patio frame; no automatic paid retries."""
import json
from pathlib import Path
import visual_studio as visual

path=Path('data/batch-20261030/cover-ai-master-plan.json')
p=visual.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
image=p['uiPlan']['images'][1]
image.update(layout='poster_hero',product_presence='hero',scene='One restrained patio photograph of the actual black rectangular cover over an implied table support, hanging nearly to the patio ground. No exposed furniture legs, no collage, no inset panels.',visual_concept='One coherent full-product patio scene. Preserve rectangular black drape and hem; no redundant panels or separate detail crops.',camera_direction='Three-quarter view, whole cover visible, naturally grounded hem with a small contact shadow.')
image['render_prompt']=visual.compile_prompt(p,1)
p['plan']['slots'][1]['composition']=image['render_prompt']
p['set_qa']=None
visual.save_project(p)
path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
r=visual.generate({'id':p['id'],'slot':1,'model':'gpt-image-2','size':'1:1','resolution':'2K','autoRepair':False})
print('TARGETED_REPAIR',r['id'],flush=True)
