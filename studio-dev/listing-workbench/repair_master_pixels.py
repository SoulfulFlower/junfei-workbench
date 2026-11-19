"""Repair AI-rendered frames using already rendered product pixels, no image API."""
import base64,json,time,uuid,io
import numpy as np
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
import visual_studio as v
import studio_bridge as b

root=Path('data/batch-20261030')
def image_data(im):
 out=io.BytesIO();im.save(out,'PNG');return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
def load(name):return v.get_project(json.loads((root/(name+'-ai-master-plan.json')).read_text(encoding='utf-8'))['id'])
def save_candidate(name,slot,image,previous,headline,subline,direction):
 p=load(name);im=p['uiPlan']['images'][slot];im.update(headline=headline,subline=subline,scene=direction,visual_concept=direction,camera_direction=direction)
 p['plan']['slots'][slot].update(headline=headline,caption=subline);p['set_qa']=None
 p['plan']['slots'][slot]['composition']=v.compile_prompt(p,slot)
 p.setdefault('operatorReview',[]).append({'slot':slot,'reason':direction,'sourceRun':previous,'method':'local composition of previously AI-generated pixels, no paid generation'})
 v.save_project(p)
 rid=uuid.uuid5(uuid.NAMESPACE_URL,p['id']+':pixel-repair-v1:'+str(slot)).hex
 file=Path('data/studio-results')/(rid+'.image');image.save(file,'PNG')
 run={'id':rid,'projectId':p['id'],'productId':p['productId'],'slot':slot,'status':'reviewing','image':'local:'+rid,'mode':'ai-master-local-repair','sourceRun':previous,'qc':[],'manual':False,'next':0,'autoRepair':False,'attempt':0}
 v.save_run(run)
 out=root/('ai-master-'+name);out.mkdir(exist_ok=True);image.save(out/(str(slot+1)+'-pixel-repair.png'))
 preview=image.copy();preview.thumbnail((600,600));preview.save(out/(str(slot+1)+'-pixel-repair-preview.jpg'))
 qc=v.review(p,slot,image_data(image));run['qc'].append(qc);run['status']='awaiting_manual' if qc['pass'] else 'needs_revision';v.save_run(run)
 print(name,run['status'],json.dumps(qc,ensure_ascii=False),flush=True)

font=lambda size,bold=False:ImageFont.truetype('C:/Windows/Fonts/'+('georgiab.ttf' if bold else 'arial.ttf'),size)
# Close portrait: crop before either hand enters the frame. No anatomy is redrawn.
cape=Image.open(root/'repair-inspect-cape-1.png').convert('RGB');w,h=cape.size
crop=cape.crop((int(w*220/600),0,int(w*570/600),int(h*240/600)))
canvas=Image.new('RGB',(2000,2000),'#f7f1e7');crop=crop.resize((2000,round(crop.height*2000/crop.width)),Image.Resampling.LANCZOS);canvas.paste(crop,(0,0))
d=ImageDraw.Draw(canvas);d.text((150,1560),'Sheer Evening Layer',font=font(103,True),fill='#571c2a');d.text((150,1730),'A translucent cape over your dress',font=font(57),fill='#432f2d')
save_candidate('cape',1,canvas,'a08f7019357d4d9b94102f1790b79afb','Sheer Evening Layer','A translucent cape over your dress','A deliberately cropped upper-body portrait, showing the exact sheer burgundy neckline and front layer over an excluded champagne styling dress. Hands and lower hem are outside this detail crop; do not require full-body visibility in this secondary detail frame.')

# Preserve the approved generated bag exactly; remove failed pleats and long chain.
hero=Image.open(root/'repair-inspect-evening-0.png').convert('RGB')
mask=Image.new('L',(600,600));ImageDraw.Draw(mask).polygon([(28,151),(157,151),(351,152),(530,151),(568,154),(573,194),(573,463),(566,475),(395,477),(215,481),(42,477),(27,465),(24,383),(24,232)],fill=255)
ImageDraw.Draw(mask).ellipse((548,129,571,158),fill=255)
mask=mask.resize(hero.size).filter(ImageFilter.GaussianBlur(.6))
alpha=np.asarray(mask).copy();alpha[np.asarray(hero).min(axis=2)>230]=0;mask=Image.fromarray(alpha)
bag=hero.convert('RGBA');bag.putalpha(mask);box=mask.getbbox();bag=bag.crop(box);bag=bag.resize((1750,round(bag.height*1750/bag.width)),Image.Resampling.LANCZOS)
scene=Image.open(root/'repair-inspect-evening-2.png').convert('RGB').resize((2000,2000))
canvas=Image.new('RGB',(2000,2000),'#efe4d1');canvas.paste(scene.crop((0,0,2000,695)),(0,0))
# A clean editorial product panel has no invented table geometry or chain.
d=ImageDraw.Draw(canvas);d.rectangle((0,695,2000,2000),fill='#efe4d1')
base_y=800+bag.height
shadow=Image.new('RGBA',canvas.size);sd=ImageDraw.Draw(shadow);sd.ellipse((160,base_y-26,1840,base_y+12),fill=(72,48,30,100));shadow=shadow.filter(ImageFilter.GaussianBlur(12));canvas=Image.alpha_composite(canvas.convert('RGBA'),shadow)
canvas.alpha_composite(bag,((2000-bag.width)//2,800));canvas=canvas.convert('RGB')
# Existing upper artwork is replaced with exact short copy on a clear panel.
d=ImageDraw.Draw(canvas);d.rectangle((0,0,2000,695),fill='#f6eedf');d.text((130,150),'An Evening Outfit',font=font(110,True),fill='#73521b');d.text((130,300),'Accent',font=font(110,True),fill='#73521b');d.text((130,490),'Champagne satin for formal styling',font=font(57),fill='#3d3326')
save_candidate('evening',2,canvas,'d30a6f1abd0f48fdb216dcdf579f499d','An Evening Outfit Accent','Champagne satin for formal styling','One exact approved AI-generated champagne pleated clutch in a warm cream editorial layout, large whole-product front view, preserving all approved pleats and hardware pixels. This detail/styling frame need not display the detachable chain. No person, invented chain, extra products, or unsupported accessories.')
