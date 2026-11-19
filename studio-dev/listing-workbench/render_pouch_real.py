"""Render only supported secondary slots from real SKU pixels; no image generation."""
import base64,copy,json,time,uuid
from pathlib import Path
from PIL import Image
import visual_studio as visual
import image_provider,product_artwork,studio_bridge,colour_sets
root=Path('data/batch-20261030')
project=json.loads((root/'pouch-real-plan.json').read_text(encoding='utf-8'))
colors=json.loads((root/'pouch-colors/colors.json').read_text(encoding='utf-8'))
def refs(color):
    source=Image.open(color['path']).convert('RGB');w,h=source.size
    part=source.crop((int(w*.27),int(h*.43),int(w*.73),int(h*.69)))
    key=uuid.uuid5(uuid.NAMESPACE_URL,color['url']+'#knit-closeup-v1').hex
    path=image_provider.ROOT/'uploads'/(key+'.jpg');path.parent.mkdir(exist_ok=True)
    if not path.exists():part.save(path,'JPEG',quality=96)
    return [color['url'],'/uploads/'+key+'.jpg']
for slot,headline,subline,ref in [(1,'A Bold Leopard Accent','Contrast colors in a curved clutch silhouette.',0),(2,'Knit Pattern Up Close','A closer look at the actual leopard motif.',1)]:
    im=project['uiPlan']['images'][slot]
    im.update(headline=headline,subline=subline,production_method='source_layout',source_reference_indices=[ref])
    for key in ['proof','big_number']:im[key]=''
project['references']=refs(colors[0]);visual.save_project(project)
product={'id':project['productId'],'name':'Knit leopard clutch'}
latest={}
for r in visual.list_projects(product['id'])['runs']:
    if r['projectId']==project['id']:latest.setdefault(r['slot'],r)
missing=[i for i in [1,2] if i not in latest or latest[i]['status'] not in ('approved','awaiting_manual')]
if missing:
    task=product_artwork.start({'confirmed':True,'indices':missing},product)
    print('MASTER_STARTED',task['id'],flush=True)
    while studio_bridge.get_view(product)['jobs'].get('render_set',{}).get('status')=='running':time.sleep(2)
latest={}
for r in visual.list_projects(product['id'])['runs']:
    if r['projectId']==project['id']:latest.setdefault(r['slot'],r)
if any(i not in latest or latest[i]['status'] not in ('approved','awaiting_manual') for i in [1,2]):
    print('MASTER_NEEDS_REVIEW',flush=True);raise SystemExit(1)
for color in colors[1:]:
    s=next((s for s in colour_sets.list_sets(product['id'])['sets'] if s.get('masterId')==project['id'] and s['color']==color['color']),None)
    s=s or {'id':uuid.uuid4().hex,'productId':product['id'],'masterId':project['id'],'color':color['color'],'reference':color['url'],'status':'reviewing','created':time.time(),'model':'local-source-layout','method':'real-sku-photo-layout','validated':True,'manual':False,'items':[]}
    target=copy.deepcopy(project);target['references']=refs(color)
    target['plan']['identity']='Actual corresponding supplier SKU photograph; preserve its exact colors, knit motif and silhouette.'
    for slot in [1,2]:
        if any(i['slot']==slot and i.get('image') for i in s['items']):continue
        im=target['uiPlan']['images'][slot];ref=target['references'][im['source_reference_indices'][0]]
        source=base64.b64decode(visual.encode_reference(ref).split(',',1)[1]);raw=product_artwork.compose(source,slot,im['headline'],im['subline'],preserve_full_source=True)
        rid=uuid.uuid4().hex;(image_provider.ROOT/'studio-results'/(rid+'.image')).write_bytes(raw)
        run={'id':rid,'projectId':'colour:'+s['id'],'productId':product['id'],'slot':slot,'image':'local:'+rid,'status':'reviewing','mode':'real-sku-photo-layout','qc':[]}
        item={'slot':slot,'baseRun':latest[slot]['id'],'image':'local:'+rid,'status':'reviewing','sourceReference':ref,'method':'real-sku-photo-layout'}
        s['items'].append(item);visual.save_run(run);colour_sets.save(s)
        try:
            qc=visual.review(target,slot,'data:image/png;base64,'+base64.b64encode(raw).decode(),source_layout=True)
            item.update(qc=qc,status='awaiting_manual' if qc['pass'] else 'needs_revision');run.update(qc=[qc],status=item['status'])
        except Exception as e:item.update(status='review_error',error=str(e));run.update(status='review_error',error=str(e))
        visual.save_run(run);colour_sets.save(s);print('SKU_IMAGE',color['color'],slot,item['status'],flush=True)
    s['status']='needs_attention';s['missingSlots']=[0,3];colour_sets.save(s)
print('SECONDARIES_FINISHED_MAIN_STILL_MISSING',flush=True)
