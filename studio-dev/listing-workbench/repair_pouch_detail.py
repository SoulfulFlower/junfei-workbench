import base64,copy,json,uuid
from pathlib import Path
from PIL import Image
import visual_studio as visual
import image_provider,product_artwork,colour_sets
root=Path('data/batch-20261030')
p=json.loads((root/'pouch-real-plan.json').read_text(encoding='utf-8'))
for s in colour_sets.list_sets(p['productId'])['sets']:
    for item in s['items']:
        if item['slot']!=2 or item['status']!='needs_revision':continue
        c=next(c for c in json.loads((root/'pouch-colors/colors.json').read_text(encoding='utf-8')) if c['color']==s['color'])
        image=Image.open(c['path']).convert('RGB');w,h=image.size
        part=image.crop((int(w*.30),int(h*.35),int(w*.70),int(h*.75)))
        key=uuid.uuid5(uuid.NAMESPACE_URL,c['url']+'#square-knit-v2').hex
        path=image_provider.ROOT/'uploads'/(key+'.jpg');part.save(path,'JPEG',quality=96)
        ref='/uploads/'+key+'.jpg'
        target=copy.deepcopy(p);target['references']=[ref]
        im=target['uiPlan']['images'][2];im.update(headline='Knit Pattern Up Close',subline='A closer look at the actual leopard motif.',source_reference_indices=[0],big_number='',proof='')
        target['plan']['identity']='Actual pink and magenta SKU knit photographed by supplier; preserve all source pattern and color.'
        raw=product_artwork.compose(path.read_bytes(),2,im['headline'],im['subline'],preserve_full_source=True)
        rid=uuid.uuid4().hex;(image_provider.ROOT/'studio-results'/(rid+'.image')).write_bytes(raw)
        run={'id':rid,'projectId':'colour:'+s['id'],'productId':p['productId'],'slot':2,'image':'local:'+rid,'status':'reviewing','mode':'real-sku-photo-layout','qc':[]}
        visual.save_run(run)
        qc=visual.review(target,2,'data:image/png;base64,'+base64.b64encode(raw).decode(),source_layout=True)
        status='awaiting_manual' if qc['pass'] else 'needs_revision'
        item.update(previousImage=item['image'],image='local:'+rid,status=status,qc=qc,sourceReference=ref)
        run.update(status=status,qc=[qc]);visual.save_run(run);colour_sets.save(s)
        print('REPAIRED',s['color'],status,flush=True)
