import json,time
from pathlib import Path
from PIL import Image,ImageDraw
import studio_bridge as bridge,visual_studio as visual
root=Path('data/batch-20261030');path=root/'bag-ai-master-plan.json'
p=visual.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
product={'id':p['productId'],'name':'Coffee plaid bow shoulder bag'}
task=bridge.review_set({'deliverable':'gallery'},product)
print('SET_REVIEW_STARTED',task['id'],flush=True)
while bridge.get_view(product)['jobs'].get('review_set',{}).get('status')=='running':time.sleep(2)
p=visual.get_project(p['id']);path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
print('SET_QA',json.dumps(p.get('set_qa'),ensure_ascii=True),flush=True)
report=['# AI-generated coffee plaid bag master','']
for i,im in enumerate(p['uiPlan']['images']):report.extend([f'## {i+1}. '+im.get('role',''),'- Buyer question: '+im.get('buyer_question',''),'- Evidence: '+im.get('evidence',''),'- Artwork: '+im.get('headline','')+' / '+im.get('subline',''),'',visual.compile_prompt(p,i),''])
(root/'bag-ai-master-instructions.md').write_text('\n'.join(report),encoding='utf-8')
canvas=Image.new('RGB',(1500,1050),'white');draw=ImageDraw.Draw(canvas)
for i in range(5):
    im=Image.open(root/'ai-master-bag'/(str(i+1)+'.png')).convert('RGB');im.thumbnail((490,490))
    x=(i%3)*500;y=(i//3)*525;canvas.paste(im,(x,y+25));draw.text((x+10,y+5),str(i+1),fill='black')
canvas.save(root/'ai-master-bag/contact.jpg',quality=94)
