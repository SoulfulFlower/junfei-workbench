import json,time,uuid
from pathlib import Path
import visual_studio as v
import colour_sets
root=Path('data/batch-20261030');master=v.get_project(json.loads((root/'evening-ai-master-plan.json').read_text(encoding='utf-8'))['id'])
sid=uuid.uuid5(uuid.NAMESPACE_URL,master['id']+':local-black').hex;rid=uuid.uuid5(uuid.NAMESPACE_URL,sid+':0').hex
Path('data/studio-results').joinpath(rid+'.image').write_bytes((root/'ai-master-evening/local-black/black-hero-review.png').read_bytes())
v.save_run({'id':rid,'projectId':'local-color:'+sid,'productId':master['productId'],'slot':0,'image':'local:'+rid,'status':'local_recolor_candidate','mode':'local-pixel','qc':[],'manual':False})
colour_sets.save({'id':sid,'productId':master['productId'],'masterId':master['id'],'color':'Black','reference':json.loads((root/'supplier-B0FG3F13K2.json').read_text(encoding='utf-8'))['images'][4],'status':'needs_attention','created':time.time(),'model':'local-pixel','validated':True,'manual':False,'items':[{'slot':0,'image':'local:'+rid,'status':'needs_revision','qc':{'pass':False,'issues':['本地换色：已修正取色混入背景导致的过曝；仍需检查边缘与整套附图，不允许按完成导出。']}}],'referenceWarnings':['只完成主图试样，附图未完成'],'error':'黑色主图本地换色待边缘核对；不是整套完成。'})
print('LOCAL_BLACK_PREVIEW_IN_EXISTING_IMAGE_SECTION')
