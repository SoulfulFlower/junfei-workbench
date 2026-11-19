"""Target the failed oversized zipper inset without redoing passed frames."""
import json
from pathlib import Path
import visual_studio as visual

path=Path('data/batch-20261030/jewelry-ai-master-plan.json')
p=visual.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
image=p['uiPlan']['images'][2]
image.update(layout='poster_hero',product_presence='hero',headline='Woven Texture, Matching Tassel',subline='A closer look at the pouch exterior.',visual_concept='One single full-product photograph emphasizing the real woven exterior and matching tassel. No inset, magnifier, collage or exploded hardware.',scene='One closed teal pouch on a warm neutral dressing-table surface, exactly matching the first source pouch.',camera_direction='Three-quarter front at normal product-photography distance. Show the entire pouch and tassel; realistic small-scale gold zipper, never enlarged or invented.')
p['plan']['slots'][2].update(headline=image['headline'],caption=image['subline'],composition=visual.compile_prompt(p,2))
image['render_prompt']=p['plan']['slots'][2]['composition']
p['set_qa']=None
visual.save_project(p)
path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
r=visual.generate({'id':p['id'],'slot':2,'model':'gpt-image-2','size':'1:1','resolution':'2K','autoRepair':False})
print('TARGETED_REPAIR',r['id'],flush=True)
