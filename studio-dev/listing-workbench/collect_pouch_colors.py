"""Cache actual SKU photographs observed in supplier buttons and gallery."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
import image_provider

root=Path('data/batch-20261030/pouch-colors');root.mkdir(exist_ok=True)
colors=['蓝色','粉底-玫红花','绿粉色','黑棕色','卡其色','黑白色','粉底-橙花','蓝绿色']
keys=['O1CN01IoZtfd1eakxfuDZBW','O1CN017rH7J91eakxgyWYk1','O1CN01ne22dW1eakxeQdnEl','O1CN016GLUxY1eakxgyWQPj','O1CN01in47H51eal29S6eR0','O1CN01V4CHJf1eakxf1m6eE','O1CN017o4Zfl1eakxhEhxIz','O1CN01Lu71fG1eal2AsODlE']
records=[]
canvas=Image.new('RGB',(1200,660),'white');draw=ImageDraw.Draw(canvas)
for i,(color,key) in enumerate(zip(colors,keys)):
    url='https://cbu01.alicdn.com/img/ibank/'+key+'_!!2219805373888-0-cib.jpg_.webp'
    path=root/(str(i)+'.image')
    if not path.exists():path.write_bytes(image_provider.remote_reference(url)[0])
    im=Image.open(path).convert('RGB');im.thumbnail((295,300));canvas.paste(im,((i%4)*300,(i//4)*330+25));draw.text(((i%4)*300+5,(i//4)*330+5),str(i),fill='black')
    records.append({'color':color,'url':url,'path':str(path),'sourceUrl':'https://detail.1688.com/offer/924536861780.html'})
(root/'colors.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
canvas.save(root/'contact.jpg')
print('CACHED',len(records))
