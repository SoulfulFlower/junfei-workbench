import json
from pathlib import Path
from PIL import Image, ImageDraw
import image_provider
root=Path('data/batch-20261030/bag-detail')
keys=['O1CN01xXxyPe1H2Bx7nMwXO','O1CN01Az0jaY1H2Bx7Cr8s7','O1CN019W7oqH1H2Bx7nMwan','O1CN01SKPMcJ1H2Bx7ZNH57','O1CN01rFKYP71H2Bx1RINf3']
rows=[]
canvas=Image.new('RGB',(1500,330),'white');draw=ImageDraw.Draw(canvas)
for i,(color,key) in enumerate(zip(['黑色','咖色','绿色','紫色','米色'],keys)):
    url='https://cbu01.alicdn.com/img/ibank/'+key+'_!!2218575140699-0-cib.jpg_.webp'
    p=root/('color-'+str(i)+'.image')
    if not p.exists():p.write_bytes(image_provider.remote_reference(url)[0])
    im=Image.open(p).convert('RGB');im.thumbnail((290,290));canvas.paste(im,(i*300,30));draw.text((i*300+5,5),str(i),fill='black')
    rows.append({'color':color,'url':url,'english':['Black','Coffee','Green','Purple','Beige'][i]})
(root/'colors.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
canvas.save(root/'colors-contact.jpg')
