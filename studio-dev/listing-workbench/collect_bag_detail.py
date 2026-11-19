"""Cache image URLs read from the live supplier detail DOM, without guessing URLs."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw
import image_provider

root=Path('data/batch-20261030')
keys=['O1CN01127raX1H2Bx7D35jw','O1CN01CTY04C1H2Bx70GwEY','O1CN016YLf4v1H2Bx7ZYkiI','O1CN01FOsVuE1H2Bx67rMUg','O1CN01eqx11b1H2Bx67pYDZ','O1CN01yrdixe1H2Bx7iIrgd','O1CN01rbRAHK1H2Bx67pcNo','O1CN01RID7RI1H2Bx5kmNrJ','O1CN01FRvBhy1H2Bx6WYWCZ','O1CN01lJhCy61H2Bx5kju1D','O1CN01HMKgDN1H2Bx67obzP','O1CN01F1CRd41H2Bx7iFFAj','O1CN01XkuGoL1H2Bx6upLYw','O1CN01aNqXh01H2Bx5kmeUj','O1CN01rfdUm61H2Bx70Dmp5','O1CN01tKS7Gl1H2Bx1RSqvB','O1CN01wAg05u1H2Bx7iFRe6','O1CN01sddmhB1H2Bx67sZKW','O1CN01nVlWwm1H2Bx7D3xnI','O1CN01JZvQPb1H2Bx5kkIz0','O1CN01ya7HMM1H2Bx1RUSh2','O1CN01tM3xDH1H2Bx7IeVTO','O1CN01poETuU1H2Bx7IcMU1','O1CN01FEUHzW1H2Bx67AawJ','O1CN01MsvVL31H2Bx67ASdj','O1CN01lhswYP1H2Bx5kkAe1','O1CN01PMQFeP1H2Bx7D1Ttu']
urls=['https://cbu01.alicdn.com/img/ibank/'+key+'_!!2218575140699-0-cib.jpg' for key in keys]
urls+=['https://cbu01.alicdn.com/img/ibank/O1CN01kxLXqQ1H2Bx6pMlmt_!!2218575140699-0-cib.jpg?__r__=1762419211247']
out=root/'bag-detail';out.mkdir(exist_ok=True)
(out/'observed-urls.json').write_text(json.dumps({'sourceUrl':'https://detail.1688.com/offer/991480382021.html','observedAt':'2026-10-30','detailImages':urls},indent=2),encoding='utf-8')
def fetch(pair):
    i,url=pair;p=out/(str(i)+'.jpg')
    if not p.exists():p.write_bytes(image_provider.remote_reference(url)[0])
    return i,p
with ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(fetch,enumerate(urls)))
for start in range(0,len(results),12):
    batch=results[start:start+12]
    canvas=Image.new('RGB',(1200,((len(batch)+3)//4)*370),'white');draw=ImageDraw.Draw(canvas)
    for n,(i,p) in enumerate(batch):
        im=Image.open(p).convert('RGB');im.thumbnail((290,340));canvas.paste(im,((n%4)*300,(n//4)*370+25));draw.text(((n%4)*300+5,(n//4)*370+5),str(i),fill='black')
    canvas.save(out/('contact-'+str(start)+'.jpg'))
print('CACHED',len(results),flush=True)
