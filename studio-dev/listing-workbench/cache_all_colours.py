"""Cache actual completed outputs for the authorized local product trial."""
import io,json,time,collections
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import colour_sets as c
import trial_979071716133 as t

DEST=t.OUT/'all-colours'
DEST.mkdir(exist_ok=True)
FONT=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)

def snapshot():
    sets=c.list_sets(t.PID)['sets']
    return {'status':dict(collections.Counter(s['status'] for s in sets)),
            'images':sum(bool(i.get('image')) for s in sets for i in s['items']),
            'attention':[{'color':s['color'],'id':s['id'],'error':s.get('error'),
                'items':[{k:i.get(k) for k in ('slot','status','qc','error','jobId')} for i in s['items'] if i['status'] in ('failed','needs_revision','submit_unknown')]}
                for s in sets if s['status']=='needs_attention']}

def cache(s):
    for i in s['items']:
        if not i.get('image'):continue
        path=DEST/(s['color']+f"-{i['slot']+1:02}.png")
        marker=path.with_suffix('.source.json')
        if path.exists() and marker.exists() and json.loads(marker.read_text())==i['image']:continue
        raw,_=c.image_bytes(s['id'],i['slot'])
        Image.open(io.BytesIO(raw)).convert('RGB').save(path)
        marker.write_text(json.dumps(i['image']))

def sheet():
    p=t.product();refs=p['supplierColorReferences']
    canvas=Image.new('RGB',(7*240,22*266),'#e9edf2');draw=ImageDraw.Draw(canvas)
    for row,ref in enumerate(refs):
        for slot in range(7):
            path=(t.OUT/f'gallery-{slot+1:02}.png') if row==0 else DEST/(ref['color']+f'-{slot+1:02}.png')
            if path.exists():
                photo=Image.open(path).convert('RGB');photo.thumbnail((236,236));canvas.paste(photo,(slot*240,row*266))
            draw.text((slot*240+4,row*266+240),ref['color']+' '+str(slot+1),fill='#203047',font=FONT)
    canvas.save(t.OUT/'all-colours-contact-sheet.jpg',quality=90)

if __name__=='__main__':
    while True:
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(cache,c.list_sets(t.PID)['sets']))
        sheet();status=snapshot();t.dump('all-colours-progress.json',status)
        print(json.dumps(status,ensure_ascii=True),flush=True)
        if not any(k in c.ACTIVE for k in status['status']):break
        time.sleep(45)
