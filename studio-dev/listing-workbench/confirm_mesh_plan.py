import json
from pathlib import Path
import visual_studio as v
path=Path('data/batch-20261030/mesh-ai-master-plan.json');p=json.loads(path.read_text(encoding='utf-8'))
for im in p['uiPlan']['images']:
 im['production_method']='generate_once'
 im['reuse_strategy']='Master only. Transparent mesh variants require actual SKU references and separate feasibility check.'
p['uiPlan']['images'][0]['role']='Single empty pouch on pure white in the source-supported open state'
p['uiPlan']['images'][0]['camera_direction']='Eye-level front three-quarter view preserving actual open zipper geometry; empty pouch, no invented closed view.'
p['uiPlan']['productionDecision']={'by':'operator','reason':'AI supplied complete evidence-backed storyboard but omitted production_method; user authorized AI master. Selected generate_once after checking each scene.'}
v.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
