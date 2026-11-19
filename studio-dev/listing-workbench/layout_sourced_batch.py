"""Use inspected supplier pixels for supported storyboard slots only."""
import copy
import json
import time
import uuid
from pathlib import Path
import visual_studio as visual
import product_artwork
import studio_bridge
root=Path('data/batch-20261030')
specs={
 'B0G6LGTCTS':{1:('Worn Across the Body','See the bag in a real wearing view.',0),2:('Plaid and Bow Detail','A closer view of the front design.',1)},
 'B0HGFGJW9Q':{1:('Fabric and Tassel Detail','Color options shown in supplier photographs.',0),2:('Divided Interior','Open pouches show the interior compartments.',1),4:('Zipper and Tassel','A closer look at the visible closure details.',2)},
 'B0HJH859M9':{1:('Leopard Knit Design','A real view of the blue and mint pattern.',1)},
 'B0FFBN1SC4':{1:('Fitted Floral Design','See the floral pattern on a square table.',1)},
 'B0FM84PDWY':{1:('Lace and V-Neck Detail','See the lace pattern and relaxed sleeve shape.',1)},
}
for asin,mapping in specs.items():
    target=root/('layout-project-'+asin+'.json')
    if target.exists():
        project=json.loads(target.read_text(encoding='utf-8'))
    else:
        project=copy.deepcopy(json.loads((root/('plan-'+asin+'.json')).read_text(encoding='utf-8')))
        project.update(parent=project['id'],id=uuid.uuid4().hex,created=time.time(),confirmed=False)
        evidence=json.loads((root/('supplier-'+asin+'.json')).read_text(encoding='utf-8'))
        project['references']=evidence.get('referenceImages') or evidence['images']
        for index,im in enumerate(project['uiPlan']['images']):
            for key in ('eyebrow','big_number','callout','supporting_text','proof'):im.pop(key,None)
            if index not in mapping:
                im.update(production_method='blocked',missing_evidence='Missing independent single-item main photo or verified specification detail.')
                continue
            headline,caption,source=mapping[index]
            im.update(headline=headline,subline=caption,source_reference_indices=[source],production_method='source_layout',missing_evidence='',size='2000x2000',text_on_image=True,visual_concept='Preserve the complete inspected supplier photo. Do not redraw or change the product.')
            project['plan']['slots'][index].update(headline=headline,caption=caption,evidence='Visually inspected supplier photo '+str(source))
        visual.save_project(project)
        target.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
    product={'id':project['productId'],'name':asin}
    runs=visual.list_projects(product['id'])['runs']
    indices=[i for i in mapping if not any(r['projectId']==project['id'] and r['slot']==i for r in runs)]
    if not indices:continue
    task=product_artwork.start({'confirmed':True,'indices':indices},product)
    print('LOCAL_LAYOUT',asin,task['id'],flush=True)
    while True:
        job=studio_bridge.get_view(product)['jobs'].get('render_set',{})
        if job.get('status')!='running':
            print('LAYOUT_FINISHED',asin,json.dumps(job,ensure_ascii=False),flush=True);break
        time.sleep(3)
