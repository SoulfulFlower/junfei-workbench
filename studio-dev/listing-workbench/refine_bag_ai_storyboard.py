import json
from pathlib import Path
import visual_studio as visual
root=Path('data/batch-20261030');path=root/'bag-ai-master-plan.json'
p=visual.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
old=p['uiPlan']['images'][4]
im=visual.model_json('You are the product visual director correcting an unsupported storyboard claim BEFORE paid rendering. Return one complete replacement image object with the same schema as the original. The references show a webbing shoulder strap with a visible metal slider. Shoulder carry is verified, crossbody fit is not. Do not rely on the existing listing as factual proof. Replace the shoulder-or-crossbody concept with an evidence-based adjustable-strap/hardware detail story, showing exact slider construction in context and a single real shoulder-carry view. Do not claim comfort, reinforced strength, strap length, detachable hardware, quick-release or durability. Preserve the locked master style and coffee SKU. Make this a polished AI-generated selling composition, not captioned source photography. Concise English headline and subline, one of each, no other public copy. production_method must be generate_once. Include buyer_question, evidence, visual_concept, camera_direction, scene and source_reference_indices. Output JSON only.',{'original':old,'style':p['uiPlan']['style'],'identity':p['plan']['identity']},[visual.encode_reference(p['references'][0]),visual.encode_reference(p['references'][1])])
for k in ['headline','subline','evidence','visual_concept','camera_direction']:
    if not isinstance(im.get(k),str) or not im[k].strip():raise ValueError('Incomplete replacement '+k)
updated={**old,**im,'slot':'4','production_method':'generate_once','big_number':'','proof':''}
p['uiPlan']['images'][4]=updated
p['plan']['slots'][4].update(question=updated['buyer_question'],evidence=updated['evidence'],headline=updated['headline'],caption=updated['subline'])
p['uiPlan']['images'][3]['subline']='30 cm wide × 13 cm deep × 23 cm high.'
p['plan']['slots'][3]['caption']=p['uiPlan']['images'][3]['subline']
for i in [3,4]:
    compiled=visual.compile_prompt(p,i);p['uiPlan']['images'][i]['render_prompt']=compiled;p['plan']['slots'][i]['composition']=compiled
visual.save_project(p);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
report=[]
for i,im in enumerate(p['uiPlan']['images']):report.extend([f'## {i+1}. '+im.get('role',''),'- Buyer question: '+im.get('buyer_question',''),'- Evidence: '+im.get('evidence',''),'- Artwork: '+im.get('headline','')+' / '+im.get('subline',''),'',visual.compile_prompt(p,i),''])
(root/'bag-ai-master-instructions.md').write_text('\n'.join(report),encoding='utf-8')
print('REFINED',updated['headline'],updated['subline'],flush=True)
