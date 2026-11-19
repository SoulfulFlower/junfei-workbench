import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageDraw
import visual_studio as v,studio_bridge as b
x=json.load(open('data/live-check/full-image-runs.json'));root=Path('data/live-check/full-set');root.mkdir(exist_ok=True)
def get(rid):
 r=v.get_run(rid)
 if not r.get('image'):return
 try:raw,mime=b.result_image(rid);(root/(str(r['slot']+1)+'.jpg')).write_bytes(raw);print('SAVED',r['slot']+1,flush=True)
 except Exception as e:print('ERROR',r['slot'],str(e),flush=True)
with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(get,x['runs']))
canvas=Image.new('RGB',(1200,600),'#e9edf2');draw=ImageDraw.Draw(canvas)
for i in range(7):
 path=root/(str(i+1)+'.jpg')
 if path.exists():
  im=Image.open(path).convert('RGB');im.thumbnail((290,270));a=i%4*300;z=i//4*300;canvas.paste(im,(a,z));draw.text((a+5,z+275),str(i+1),fill='black')
canvas.save(root/'contact-sheet.jpg')
