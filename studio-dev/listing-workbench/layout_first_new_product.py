"""Produce evidence-backed secondary images from real supplier pixels."""
import copy
import json
import time
import uuid
from pathlib import Path
import visual_studio as visual
import product_artwork
import studio_bridge
ROOT=Path('data/batch-20261030')
target=ROOT/'layout-project-B0D2DS6JT6.json'
if target.exists():
    project=json.loads(target.read_text(encoding='utf-8'))
else:
    project=json.loads((ROOT/'plan-B0D2DS6JT6.json').read_text(encoding='utf-8'))
    project=copy.deepcopy(project)
    project.update(parent=project['id'],id=uuid.uuid4().hex,created=time.time(),confirmed=False)
    codes=['ccBP9h25kp0qeNRx6','wh9uwO25kp0raHjUR','fUeVhf25kp0k0yFqv']
    project['references']=['https://cbu01.alicdn.com/img/ibank/O1CN01'+c+'_!!980537565-0-cib.jpg_.webp' for c in codes]
    captions=[('', '',0),('Floral Lace Border','A closer look at the floral pattern and decorative edge.',2),
        ('See-Through Lace','Openwork details reveal the tabletop underneath.',1),
        ('Six Size Options','60x60, 90x90, 90x140, 140x140, 140x180 and 140x220 cm. Square or rectangle by size.',0),
        ('Polyester Lace Tablecloth','Tablecloth only. Table, tableware and decorative items are not included.',0)]
    for index,(headline,caption,source) in enumerate(captions):
        im=project['uiPlan']['images'][index]
        for key in ('eyebrow','big_number','callout','supporting_text','proof'):
            im.pop(key,None)
        im.update(headline=headline,subline=caption,source_reference_indices=[source],
            production_method='blocked' if index==0 else 'source_layout',
            missing_evidence='No isolated tabletop-free photograph for a compliant main image.' if index==0 else '',
            size='2000x2000',text_on_image=index!=0,
            visual_concept='Use the complete selected source photograph without redraw or invented views.')
        slot=project['plan']['slots'][index]
        slot.update(headline=headline,caption=caption,composition=im['visual_concept'])
    project['analysis']['localSourceLayoutAdaptation']='Additional source details visually inspected; preserve full source photos. Main remains blocked, no invented cutout.'
    visual.save_project(project)
    target.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
product={'id':project['productId'],'name':'涤纶蕾丝桌布'}
existing=[r for r in visual.list_projects(product['id'])['runs'] if r['projectId']==project['id']]
indices=[i for i in range(1,5) if not any(r['slot']==i for r in existing)]
if indices:
    task=product_artwork.start({'confirmed':True,'indices':indices},product)
    print('LOCAL_LAYOUT_STARTED',task['id'],flush=True)
    while True:
        current=studio_bridge.get_view(product)['jobs'].get('render_set',{})
        if current.get('status')!='running':
            print(json.dumps(current,ensure_ascii=False),flush=True)
            break
        time.sleep(3)
else:
    print('Existing local images preserved; no repeat review calls',flush=True)
