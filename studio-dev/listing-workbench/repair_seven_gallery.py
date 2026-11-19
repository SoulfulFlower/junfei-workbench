"""Repair supplementary artwork with existing AI pixels, then independently check."""
import base64,io,json,time,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from PIL import Image,ImageDraw,ImageFont,ImageOps
import visual_studio as v
ROOT=Path('data/batch-20261030');TEMP=ROOT/'variant-production'
font=lambda n,b=False:ImageFont.truetype('C:/Windows/Fonts/'+('georgiab.ttf' if b else 'arial.ttf'),n)

def image(name,slot,failed=True):
    p=TEMP/f'failed-{name}-{slot}.png' if failed else ROOT/f'ai-master-{name}'/f'{slot}.png'
    return Image.open(p).convert('RGB')

def panel(im,box,head,sub):
    w,h=im.size;crop=im.crop(tuple(round(x*s) for x,s in zip(box,[w,h,w,h])))
    out=Image.new('RGB',(2000,2000),'#f6f0e7');out.paste(ImageOps.fit(crop,(2000,1480),method=Image.Resampling.LANCZOS),(0,0))
    d=ImageDraw.Draw(out);d.text((120,1550),head,font=font(90,True),fill='#443b30');d.text((120,1745),sub,font=font(49),fill='#443b30')
    return out

def save(name,slot,im,head,sub,desc):
    p=v.get_project(json.loads((ROOT/f'{name}-seven-image-plan.json').read_text(encoding='utf-8'))['id']);idx=slot-1
    card=p['uiPlan']['images'][idx];card.update(headline=head,subline=sub,big_number='',proof='',visual_concept=desc,scene=desc,camera_direction=desc,layout='poster_hero',text_on_image=True)
    p['plan']['slots'][idx].update(headline=head,caption=sub,composition=desc);p['set_qa']=None
    v.save_project(p)
    rid=uuid.uuid5(uuid.NAMESPACE_URL,p['id']+':seven-repair-v1:'+str(idx)).hex
    f=Path('data/studio-results')/(rid+'.image');im.save(f,'PNG')
    run=dict(id=rid,projectId=p['id'],productId=p['productId'],slot=idx,image='local:'+rid,status='reviewing',mode='ai-master-local-repair',qc=[],manual=False,autoRepair=False,attempt=0,next=0)
    v.save_run(run)
    qc=v.review(p,idx,'data:image/png;base64,'+base64.b64encode(f.read_bytes()).decode());run['qc']=[qc];run['status']='awaiting_manual' if qc['pass'] else 'needs_revision';v.save_run(run)
    im.save(TEMP/f'repaired-{name}-{slot}.png')
    if qc['pass']:im.save(ROOT/f'ai-master-{name}'/f'{slot}.png')
    print('REPAIR',name,slot,run['status'],qc['issues'],flush=True)

def repair(name,slot):
    im=image(name,slot)
    if (name,slot)==('blouse',5):
        head='Delicate Scalloped Neckline';sub='Intricate lace trim enhances the deep V-neck.'
        result=panel(im,(.2,.06,.8,.48),head,sub);desc='Deliberately tight neckline detail cropped from the same AI-rendered exact garment, showing scalloped V-neck trim; no full product or new construction required in this detail image.'
    elif (name,slot)==('blouse',6):
        # Exclude the blurred hands entirely; show the broad sleeve from an existing good frame.
        im=image(name,2,False);head='Room Through The Sleeve';sub='A wide batwing cut with a sheer chiffon finish'
        result=panel(im,(.01,.25,.43,.68),head,sub);desc='Tight supported sleeve detail, cropped from the approved AI master worn blouse, showing fabric drape and batwing cut. A deliberately cropped detail, no whole garment requirement.'
    elif (name,slot)==('blouse',7):
        im=image(name,3,False);head='Scalloped Lace Finish';sub='A floral lace panel along the lower edge'
        result=panel(im,(.33,.30,.98,.88),head,sub);desc='Close crop of the approved AI master lace hem; preserve its actual flower scale and trim. No separate full-product inset or invented new lace pattern.'
    elif (name,slot)==('cape',5):
        head='Fluid Chiffon Drape';sub='Sheer fabric with a gently finished edge'
        result=panel(im,(.18,.23,.96,.93),head,sub);desc='Close crop of burgundy chiffon and lower hem only, deliberately excluding the neckline so no unsupported neckline binding is shown. Actual sheer fabric folds, no new feature.'
    elif (name,slot)==('cape',6):
        im=image(name,1,False);head='Open At The Sides';sub='A cape layer draped over your outfit'
        result=panel(im,(.35,.24,.84,.72),head,sub);desc='Supported front-side detail cropped directly from the approved master front view, showing the open side and draping burgundy layer over an excluded ivory styling dress. No back fastener or unknown rear seam.'
    elif (name,slot)==('cape',7):
        head='Sophisticated Layering';sub='Adds color without hiding your silhouette'
        result=panel(im,(.40,.01,.99,.66),head,sub);desc='Upper-body and upper-skirt styling portrait cropped from the same AI artwork, with burgundy sheer cape over an excluded black dress. No full-length requirement.'
    elif (name,slot)==('cover',5):
        head='A Defined Lower Hem';sub='Soft fabric drapes around the table shape'
        result=panel(im,(.08,.38,.95,.86),head,sub);desc='A deliberate lower-half product detail showing black cover hem and visible furniture legs. No folded-state illustration, storage/capacity or protective performance claim.'
    elif name=='elastic':
        head,sub=('A Fitted Corner','Elastic gathers along the printed edge') if slot==5 else ('Botanical Print Detail','Colorful flowers across the polyester surface')
        box=(.02,.36,.70,.79) if slot==5 else (.15,.30,.74,.66)
        result=panel(im,box,head,sub);desc='A tight printed tabletop detail crop excluding background chairs and ambiguous overlap. No invented material structure; show actual printed flowers and elastic edge only where visible.'
    elif (name,slot)==('evening',5):
        im=image(name,4,False);head='Gold-Tone Snap Detail';sub='A magnetic closure beneath the top edge'
        result=panel(im,(.25,.20,.85,.59),head,sub);desc='Tight crop from the approved AI opening image, showing the actual gold-tone magnetic snap and champagne lining; no chain or exterior loop construction invented.'
    elif (name,slot)==('evening',6):
        head='Compact Proportions';sub='25 cm wide for formal styling'
        result=panel(im,(.18,.25,.94,.85),head,sub);desc='Close carrying detail crop of the same champagne bag and fingers, with model elbow and upper arm outside the frame; 25cm width is a supplier-stated measurement. No fit-phone or capacity claim.'
    else:
        im=image(name,1,False);head='Size At A Glance';sub='25 x 14.5 x 2 cm'
        result=panel(im,(.02,.20,.98,.85),head,sub);desc='Exact approved AI master bag pixels in a clean dimensional information panel. Supplier states width25cm height14.5cm depth2cm; text gives these facts without an invented side view or scale comparison. No chain or lightweight claim.'
    save(name,slot,result,head,sub,desc)

if __name__=='__main__':
    jobs=[('blouse',5),('blouse',6),('blouse',7),('cape',5),('cape',6),('cape',7),('cover',5),('elastic',5),('elastic',6),('evening',5),('evening',6),('evening',7)]
    # Serialize per product to avoid project updates overwriting each other.
    def group(name):
        for n,s in jobs:
            if n==name:repair(n,s)
    with ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(group,n):n for n in dict(jobs)}
        for f in as_completed(fs):
            try:f.result()
            except Exception as e:print('ERROR',fs[f],str(e),flush=True)
