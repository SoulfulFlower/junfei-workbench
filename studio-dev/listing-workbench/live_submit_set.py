import json,time
from pathlib import Path
import visual_studio as v
x=json.load(open('data/live-check/full-image-project.json'));p=v.get_project(x['id'])
p['plan']['identity']='Exact navy hooded zip-front jacket in the first reference. Preserve its exact opening, collar, brownish lining, silver central zip, original small chest embroidery, sleeve patch and neck label positions. Do not replace markings with flags or new text. Their fine lettering is unresolved; do not enlarge or invent it. No back view is provided. Floating flame icon is NOT part of product and must be removed.'
p['plan']['slots'][1]['caption']='Navy jacket for everyday layering.'
p['plan']['slots'][4]['headline']='Material Detail';p['plan']['slots'][4]['caption']='A closer look at the visible texture.'
for slot in p['plan']['slots']:
 slot['composition']+=' Preserve all original garment markings as small unresolved shapes if needed; never invent legible branding. Do not claim added logos, fabric performance or hidden features. Remove floating fire icon. No rear views.'
p['plan']['warnings'].append('人工复核修正：不将模型猜测的旗帜标识或面料手感作为事实，标识细字不得重造。')
p['confirmed']=True;v.save_project(p)
runs=[]
for index in range(7):
 try:
  r=v.generate({'id':p['id'],'slot':index,'autoRepair':False,'model':'gemini-3-pro-image-preview','size':'1:1','resolution':'2K'});runs.append(r['id']);print('SUBMITTED',index,r['id'],flush=True)
 except Exception as e:print('SUBMIT_ERROR',index,str(e),flush=True)
 Path('data/live-check/full-image-runs.json').write_text(json.dumps({'projectId':p['id'],'runs':runs}),encoding='utf-8')
