"""Replace a hallucinated inset using the approved generated product's own pixels."""
import base64,json,io,uuid
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
import visual_studio as v
root=Path('data/batch-20261030');p=v.get_project(json.loads((root/'cover-ai-master-plan.json').read_text(encoding='utf-8'))['id'])
hero=Image.open(root/'ai-master-cover/1.png').convert('RGB').resize((600,600))
font=lambda n,b=False:ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),n)
for slot in [2,3]:
 im=Image.open(root/('ai-master-cover/'+str(slot+1)+'.png')).convert('RGB').resize((2000,2000));d=ImageDraw.Draw(im)
 if slot==2:
  detail=ImageOps.fit(hero.crop((305,292,450,460)),(790,790),method=Image.Resampling.LANCZOS)
  mask=Image.new('L',(790,790));ImageDraw.Draw(mask).ellipse((0,0,789,789),fill=255)
  im.paste(detail,(84,1114),mask);d=ImageDraw.Draw(im);d.ellipse((80,1110,878,1908),outline='white',width=12)
  d.rectangle((900,1400,2000,2000),fill='#efece0');d.text((930,1455),'Woven Cloth,',font=font(107,True),fill='#39452c');d.text((930,1585),'Honest Drape',font=font(107,True),fill='#39452c');d.text((930,1780),'Visible weave and the lower tie',font=font(48),fill='#39452c')
  head,sub='Woven Cloth, Honest Drape','Visible weave and the lower tie'
  direction='Whole product with a circular detail crop taken directly from the approved AI main image, showing its actual central/front lower tie and weave. The inset is the identical product pixels, not an independently invented corner toggle. No added hardware or unsupported interior.'
 else:
  d.rectangle((0,0,2000,580),fill='#f2f1e8');d.text((145,140),'One Clean Silhouette',font=font(140,True),fill='#202529');d.text((145,340),'A square-cut cover in a quiet patio setting',font=font(67),fill='#484c4b')
  head,sub='One Clean Silhouette','A square-cut cover in a quiet patio setting'
  direction='A single square-cut black furniture cover in one quiet patio setting. Furniture feet visible below the hem are supported by the source. No requirement to show two locations and no protective-performance claims.'
 p['uiPlan']['images'][slot].update(headline=head,subline=sub,scene=direction,visual_concept=direction,camera_direction=direction)
 p['plan']['slots'][slot].update(headline=head,caption=sub);p['set_qa']=None;v.save_project(p)
 rid=uuid.uuid5(uuid.NAMESPACE_URL,p['id']+':inset-copy-repair:'+str(slot)).hex
 out=Path('data/studio-results')/(rid+'.image');im.save(out,'PNG');im.save(root/('ai-master-cover/'+str(slot+1)+'-pixel-repair.png'))
 run={'id':rid,'projectId':p['id'],'productId':p['productId'],'slot':slot,'image':'local:'+rid,'status':'reviewing','mode':'ai-master-local-repair','qc':[],'manual':False,'autoRepair':False,'attempt':0,'next':0};v.save_run(run)
 qc=v.review(p,slot,'data:image/png;base64,'+base64.b64encode(out.read_bytes()).decode());run['qc'].append(qc);run['status']='awaiting_manual' if qc['pass'] else 'needs_revision';v.save_run(run)
 print(slot,run['status'],json.dumps(qc,ensure_ascii=False),flush=True)
