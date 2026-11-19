"""Expose local candidates inside the existing image section, without approval."""
import json,time,uuid
from pathlib import Path
import colour_sets
import visual_studio as visual

root=Path('data/batch-20261030/ai-master-bag/local-recolor-trial')
data=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
master=visual.get_project(data['masterId'])
runs=visual.list_projects(master['productId'])['runs']
hero=next(r for r in runs if r['projectId']==master['id'] and r['slot']==0 and r['status'] in ('awaiting_manual','approved'))
for image in data['images']:
    if image['color']=='Coffee':continue
    sid=uuid.uuid5(uuid.NAMESPACE_URL,master['id']+':local-mask:'+image['color']).hex
    rid=uuid.uuid5(uuid.NAMESPACE_URL,sid+':0').hex
    (Path('data/studio-results')/(rid+'.image')).write_bytes((root/image['file']).read_bytes())
    visual.save_run({'id':rid,'projectId':'local-color:'+sid,'productId':master['productId'],'slot':0,'image':'local:'+rid,'status':'local_recolor_candidate','mode':'local-pixel','qc':[],'manual':False})
    items=[{'slot':0,'baseRun':hero['id'],'image':'local:'+rid,'status':'needs_revision','qc':{'pass':False,'issues':['本地换色试样：待核对选区边缘、五金和真实SKU颜色；其余附图尚未完成。']}}]
    for i in range(1,5):
        candidate=root/(image['color'].lower()+'-'+str(i+1)+'.png')
        crid=uuid.uuid5(uuid.NAMESPACE_URL,sid+':'+str(i)).hex
        (Path('data/studio-results')/(crid+'.image')).write_bytes(candidate.read_bytes())
        visual.save_run({'id':crid,'projectId':'local-color:'+sid,'productId':master['productId'],'slot':i,'image':'local:'+crid,'status':'local_recolor_candidate','mode':'local-pixel','qc':[],'manual':False})
        items.append({'slot':i,'image':'local:'+crid,'status':'needs_revision','qc':{'pass':False,'issues':['附图换色试样：肩带、阴影和选区边缘仍有漏色或误选，禁止按合格图片导出。']}})
    colour_sets.save({'id':sid,'productId':master['productId'],'masterId':master['id'],'color':image['color'],'reference':image['sourceReference'],'status':'needs_attention','created':time.time(),'model':'local-pixel','validated':True,'manual':False,'items':items,'referenceWarnings':['局部像素换色试样，未完成整套'],'error':'主图本地换色已出试样，待校验；附图选区处理中。'})
print('LOCAL_CANDIDATES_VISIBLE',4)
