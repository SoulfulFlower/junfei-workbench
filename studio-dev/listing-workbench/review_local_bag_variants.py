"""Independent colour/mask QA, no generation calls and no forced passes."""
import base64,io,json,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import colour_sets,visual_studio as v
root=Path('data/batch-20261030');folder=root/'ai-master-bag/local-recolor-trial'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
def data(im):
 im=im.convert('RGB');im.thumbnail((2000,2000));out=io.BytesIO();im.save(out,'JPEG',quality=95);return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
def gallery(color=None):
 out=Image.new('RGB',(2500,500),'white')
 for slot in range(5):
  path=root/'ai-master-bag'/(str(slot+1)+'.png') if color is None else folder/(color.lower()+('' if slot==0 else '-'+str(slot+1))+'.png')
  out.paste(Image.open(path).convert('RGB').resize((500,500)),(slot*500,0))
 return data(out)
master=gallery()
def check(s):
 ref=next(i for i in manifest['images'] if i['color']==s['color']);reference=Image.open(root/'bag-detail'/('color-'+str(['Black','Coffee','Green','Purple','Beige'].index(s['color']))+'.image'))
 result=v.model_json('You are an independent product recolor QA reviewer. Image1 has five LOCKED AI master frames left-to-right. Image2 is the actual target SKU reference (use actual fabric/strap color, ignore the white photo background). Image3 has five LOCAL recolored output frames in identical order. Inspect each output frame: full bag, EVERY shoulder strap and every macro/detail inset must match target hue. Person/skin/clothes/hair/background/ground shadows, metal hardware and all exact artwork words must remain unchanged. Reject residual brown coffee fabric, polygon-shaped color spills into coat/background, clipping, washed-out texture, or source-target hue mismatch. Plaid must remain plaid, not become a new pattern. Do not require copying supplier lighting. Return JSON {"items":[{"slot":0,"pass":bool,"issues":["actual concrete defect"]}, ... all slots 0 through 4]}. Uncertainty is a failure, never an automatic pass.',{'targetColor':s['color'],'method':'local masked quantile mapping; no image generation'},[master,data(reference),gallery(s['color'])])
 rows=result.get('items',[])
 if len(rows)!=5 or {r.get('slot') for r in rows}!=set(range(5)):raise ValueError('Invalid QA slot list')
 for item in s['items']:
  qc=next(r for r in rows if r['slot']==item['slot']);passed=qc.get('pass') is True and qc.get('issues')==[]
  item['qc']={**qc,'at':time.time(),'reviewModel':v.VISION_MODEL,'method':'independent three-way gallery check'}
  item['status']='awaiting_manual' if passed else 'needs_revision'
 s['status']='awaiting_manual' if all(i['status']=='awaiting_manual' for i in s['items']) else 'needs_attention'
 s['error']='' if s['status']=='awaiting_manual' else '局部换色检查有未通过图片，未按整套完成导出。'
 colour_sets.save(s);print(s['color'],[(i['slot'],i['status'],i['qc']['issues']) for i in s['items']],flush=True)
 return {'color':s['color'],'status':s['status'],'items':rows}
sets=[s for s in colour_sets.list_sets('IMP-US-B0G6LGTCTS')['sets'] if s.get('masterId')==manifest['masterId'] and s.get('model')=='local-pixel']
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(check,sets))
(folder/'independent-qa.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
