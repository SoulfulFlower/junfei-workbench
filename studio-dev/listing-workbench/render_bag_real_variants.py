"""Reuse one AI storyboard with each SKU's real pixels, never a paid redraw."""
import base64
import copy
import io
import json
import sqlite3
import time
import uuid
from pathlib import Path
from PIL import Image
import colour_sets
import image_provider
import product_artwork
import studio_bridge
import visual_studio as visual

root=Path('data/batch-20261030');folder=root/'bag-detail'
project=json.loads((root/'bag-complete-plan.json').read_text(encoding='utf-8'))
colors=json.loads((folder/'colors.json').read_text(encoding='utf-8'))
details=json.loads((folder/'observed-urls.json').read_text(encoding='utf-8'))['detailImages']
master_path=root/'bag-real-production.json'
if master_path.exists():project=json.loads(master_path.read_text(encoding='utf-8'))
else:
    project.update(parent=project['id'],id=uuid.uuid4().hex,created=time.time(),confirmed=True)
    for i,im in enumerate(project['uiPlan']['images']):
        for k in ('eyebrow','big_number','callout','supporting_text','proof'):im.pop(k,None)
        im.update(production_method='source_layout',missing_evidence='',size='2000x2000',text_on_image=i!=0)
    project['uiPlan']['images'][1].update(headline='Everyday Shoulder Style',subline='See the bag in a real wearing view.')
    project['uiPlan']['images'][2].update(headline='Body Size 30 x 13 x 23 cm',subline='30 cm wide, 13 cm deep, 23 cm high.')
    project['uiPlan']['images'][3].update(headline='Plaid and Bow Detail',subline='See the front ties and checked fabric.')
    for i,im in enumerate(project['uiPlan']['images']):
        project['plan']['slots'][i].update(headline=im['headline'],caption=im['subline'])

def version_refs(index):
    color=colors[index]
    # SKU-specific real wearing photos, manually verified against supplier color labels.
    wearing={0:9,1:3,2:6,3:12,4:15}[index]
    image=Image.open(folder/('color-'+str(index)+'.image')).convert('RGB')
    crop=image.crop((145,475,700,790))
    crop_id=uuid.uuid5(uuid.NAMESPACE_URL,color['url']+'#front-detail-v1').hex
    path=image_provider.ROOT/'uploads'/(crop_id+'.jpg');path.parent.mkdir(exist_ok=True)
    if not path.exists():crop.save(path,'JPEG',quality=96)
    return [color['url'],details[wearing],'/uploads/'+crop_id+'.jpg']

project['references']=version_refs(1)
for i,ref in enumerate([0,1,0,2]):project['uiPlan']['images'][i]['source_reference_indices']=[ref]
visual.save_project(project)
master_path.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
product={'id':project['productId'],'name':'Plaid bow bag'}
runs=visual.list_projects(product['id'])['runs']
missing=[i for i in range(4) if not any(r['projectId']==project['id'] and r['slot']==i and r.get('image') for r in runs)]
if missing:
    task=product_artwork.start({'confirmed':True,'indices':missing},product)
    print('MASTER_STARTED',task['id'],flush=True)
    while studio_bridge.get_view(product)['jobs'].get('render_set',{}).get('status')=='running':time.sleep(2)
latest={}
for r in visual.list_projects(product['id'])['runs']:
    if r['projectId']==project['id']:latest.setdefault(r['slot'],r)
if len(latest)!=4 or any(r['status'] not in ('approved','awaiting_manual') for r in latest.values()):
    print('MASTER_NEEDS_REVIEW',json.dumps({i:r['status'] for i,r in latest.items()}),flush=True)
    raise SystemExit(1)
print('MASTER_PASSED',flush=True)
for index,color in enumerate(colors):
    if index==1:continue
    existing=next((s for s in colour_sets.list_sets(product['id'])['sets'] if s.get('masterId')==project['id'] and s['color']==color['color']),None)
    s=existing or {'id':uuid.uuid4().hex,'productId':product['id'],'masterId':project['id'],'color':color['color'],'reference':color['url'],'status':'reviewing','created':time.time(),'model':'local-source-layout','method':'real-sku-photo-layout','validated':True,'manual':False,'referenceCheck':{'sameProduct':True,'evidence':['Supplier SKU label and manually inspected construction match. Real pattern retained, no recoloring.']},'items':[]}
    target=copy.deepcopy(project);target['references']=version_refs(index)
    target['plan']['identity']='Actual '+color['english']+' plaid bow shoulder bag shown in the corresponding real SKU photographs. Preserve exact pattern, construction and color.'
    for slot in range(4):
        if any(i['slot']==slot and i.get('image') for i in s['items']):continue
        im=target['uiPlan']['images'][slot];ref=target['references'][im['source_reference_indices'][0]]
        source=base64.b64decode(visual.encode_reference(ref).split(',',1)[1])
        raw=product_artwork.compose(source,slot,im['headline'],im['subline'],preserve_full_source=True)
        rid=uuid.uuid4().hex;(image_provider.ROOT/'studio-results'/(rid+'.image')).write_bytes(raw)
        run={'id':rid,'projectId':'colour:'+s['id'],'productId':product['id'],'slot':slot,'image':'local:'+rid,'status':'reviewing','mode':'real-sku-photo-layout','qc':[]}
        visual.save_run(run)
        item={'slot':slot,'baseRun':latest[slot]['id'],'image':'local:'+rid,'status':'reviewing','sourceReference':ref,'method':'real-sku-photo-layout'}
        s['items'].append(item);colour_sets.save(s)
        try:
            qc=visual.review(target,slot,'data:image/png;base64,'+base64.b64encode(raw).decode(),source_layout=True)
            item.update(qc=qc,status='awaiting_manual' if qc['pass'] else 'needs_revision')
            run.update(qc=[qc],status=item['status'])
        except Exception as error:item.update(status='review_error',error=str(error));run.update(status='review_error',error=str(error))
        visual.save_run(run);colour_sets.save(s)
        print('REAL_SKU_IMAGE',color['english'],slot,item['status'],flush=True)
    s['status']='awaiting_manual' if all(i['status']=='awaiting_manual' for i in s['items']) else 'needs_attention'
    colour_sets.save(s)
print('REAL_VARIANTS_FINISHED',flush=True)
