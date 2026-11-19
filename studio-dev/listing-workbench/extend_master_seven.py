"""Add AI-directed supplementary frames to existing masters, preserving good files."""
import copy, json, time, uuid, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw
import visual_studio as v
import studio_bridge as bridge
from complete_variant_masks import data

ROOT=Path('data/batch-20261030')
NAMES=['bag','blouse','cape','cover','elastic','evening','jewelry','mesh','pouch','tablecloth']

def extend(name):
    path=ROOT/f'{name}-seven-image-plan.json'
    if path.exists():return v.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
    old=v.get_project(json.loads((ROOT/f'{name}-ai-master-plan.json').read_text(encoding='utf-8'))['id'])
    count=len(old['plan']['slots']);needed=7-count
    if needed<=0:return old
    sample={k:x for k,x in old['uiPlan']['images'][1].items() if k not in ['render_prompt','versions','final_url','base_url','_runId','_status','human_reviewed','render_qa']}
    context={'product':name,'identity':old['plan']['identity'],'unknowns':old['plan']['warnings'],'existingShots':[{k:im.get(k) for k in ['buyer_question','evidence','visual_concept','headline','subline']} for im in old['uiPlan']['images']], 'referenceCount':len(old['references']),'newImagesRequired':needed,'imageSchema':sample,'brief':old['brief']}
    instruction='You are the AI art director completing an existing Amazon gallery to 1 main plus 6 secondary images. Image1 is the existing finished master gallery; remaining images are actual supplier truth references. Return JSON {"images":[...EXACT requested number of NEW secondary images using provided imageSchema fields]}. Design DIFFERENT, useful sales stories complementary to existing images, never another main. Preserve master color and exact product identity and coherent art direction. Do not duplicate the existing same-angle detail shots or generic caption cards. Each shot needs buyer question, supported selling point, explicit evidence, scene/visual_concept, camera_direction, concise exact English headline/subline. No invented measurements, features, tests, waterproofing, capacity, certifications, invisible interior or rear view. Source images can support only visible facts. If true dimensions are absent, choose a practical arrangement/detail supported by the visible product. For apparel show only real cut, sleeve, hem, drape and layering; no warmth/UV claims. Never invent a size chart. For bags show confirmed closure, seams, fabric pattern and wearing/carrying arrangements; do not show a new strap. Set production_method=generate_once. source_reference_indices are zero-based relative to the supplier reference array (NOT image1 gallery), minimum [0]. Return at most 2 short sentences per field. Exact count is mandatory. Output JSON only, no long reasoning.'
    refs=[v.encode_reference(r) for r in old['references'][:4]]
    result=v.model_json(instruction,context,[data(ROOT/f'ai-master-{name}'/'contact.jpg'),*refs])
    additions=result.get('images',[])
    if len(additions)!=needed:raise ValueError('Wrong additional count')
    p=copy.deepcopy(old);p.update(id=uuid.uuid4().hex,parent=old['id'],created=time.time(),confirmed=True,set_qa=None)
    p['brief']=re.sub(r'\b[fF]our\b','seven',p['brief'])+' Complete the expanded seven-image gallery. Existing first frames are locked.'
    p['uiPlan']['creative_brief']=p['brief']
    for i,im in enumerate(additions,count):
        indices=im.get('source_reference_indices',[0])
        if not isinstance(indices,list) or any(type(x)!=int or x<0 or x>=len(old['references']) for x in indices):raise ValueError('Bad reference index')
        im={**sample,**im,'slot':str(i),'text_on_image':True,'production_method':'generate_once','versions':[]}
        for k in ['render_prompt','final_url','base_url','_runId','_status','human_reviewed','render_qa']:im.pop(k,None)
        p['uiPlan']['images'].append(im)
        p['plan']['slots'].append(dict(index=i,question=im['buyer_question'],evidence=im['evidence'],headline=im['headline'],caption=im.get('subline',''),composition=im['visual_concept'],purpose=im.get('role','Supplementary selling image')))
    v.save_project(p)
    # Link immutable existing runs into the expanded project for app display/export.
    with v.db() as db:oldruns=[json.loads(r[0]) for r in db.execute('select body from runs where project_id=?',(old['id'],))]
    for slot in range(count):
        good=[r for r in oldruns if r['slot']==slot and r['status'] in ('approved','awaiting_manual')]
        if good:
            r=copy.deepcopy(good[-1]);r.update(id=uuid.uuid4().hex,projectId=p['id']);v.save_run(r)
    path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PLANNED',name,needed,flush=True)
    return p

def produce(name):
    p=extend(name)
    count=5 if name=='bag' else 4
    for slot in range(count,7):
        with v.db() as db:prior=[json.loads(r[0]) for r in db.execute('select body from runs where project_id=?',(p['id'],))]
        runs=[r for r in prior if r['slot']==slot]
        if runs:
            run=runs[-1]
            if run['status'] not in ('generating','reviewing','approved','awaiting_manual'):
                print('RETAIN',name,slot,run['status'],flush=True);continue
        else:
            run=v.generate(dict(id=p['id'],slot=slot,model='gpt-image-2',size='1:1',resolution='2K',autoRepair=False))
            print('SUBMITTED',name,slot,run['id'],flush=True)
        while True:
            run=v.get_run(run['id'])
            if run['status'] in bridge.TERMINAL:break
            if run['status']=='generating' and run.get('next',0)<=time.time():v.advance(run['id'])
            time.sleep(4)
        if run['status'] in ('approved','awaiting_manual'):
            raw,_=bridge.result_image(run['id']);(ROOT/f'ai-master-{name}'/f'{slot+1}.png').write_bytes(raw)
            print('READY',name,slot+1,flush=True)
        else:print('DEFECT',name,slot+1,run['status'],str(run.get('qc'))[:800],flush=True)
    return name

if __name__=='__main__':
    import sys
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(produce,n):n for n in (sys.argv[1:] or NAMES)}
        for f in as_completed(jobs):
            try:print('FINISHED',f.result(),flush=True)
            except Exception as e:print('ERROR',jobs[f],str(e),flush=True)
