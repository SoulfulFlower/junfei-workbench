import csv
import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent
BATCH = BASE / 'data/batch-20261030'
OUT = Path('D:/桌面/小秘发布/20261030-10款产品成品')
if OUT.exists() and '--resume' not in sys.argv:
    raise SystemExit('Target exists; preserve existing delivery')
state = json.loads(sqlite3.connect(BASE / 'data/studio.sqlite3').execute('select body from workspace where id=1').fetchone()[0])
items = [
 ('bag','B0G6LGTCTS','格纹蝴蝶结包','Coffee',5),
 ('blouse','B0FM84PDWY','蕾丝长袖上衣','White',4),
 ('cape','B0H4R6193H','雪纺披肩','Burgundy',4),
 ('cover','B0DPRTMHSS','庭院桌罩','Black',4),
 ('elastic','B0FFBN1SC4','印花松紧桌布','Tropical Floral',4),
 ('evening','B0FG3F13K2','褶皱晚宴包','Champagne',4),
 ('jewelry','B0HGFGJW9Q','首饰收纳包','Teal',4),
 ('mesh','B0HH6LTTHZ','洗漱收纳袋','White',4),
 ('pouch','B0HJH859M9','豹纹化妆包','Blue',4),
 ('tablecloth','B0D2DS6JT6','蕾丝桌布','White',4),
]
rows=[]
for name, asin, label, color, count in items:
    p = next(p for p in state['products'] if p['id']=='IMP-US-'+asin)
    c = {k:state['copy'][p['id']+'-US'].get(k,'') for k in ['title','highlights','bullets','description','terms']}
    bullets = [b.strip() for b in c['bullets'].splitlines() if b.strip()]
    assert len(bullets)==5, asin
    if name=='bag':
        c['highlights']='Coffee plaid nylon shoulder and crossbody purse with bow accent'
        bullets[3]='Coffee Plaid Finish: A coffee-colored plaid pattern pairs with the bow accent for a coordinated casual look.'
    elif name=='blouse':
        c['highlights']='White polyester long sleeve top with lace panel detail; sizes S to XL'
        bullets[3]='White Lace Detail: The white color highlights the lace panel and pairs with jeans or skirts for everyday styling.'
    elif name=='cape':
        c['highlights']='Burgundy chiffon capelet with sheer fabric and a high-low hem'
        bullets[4]='Burgundy Finish: The wine-red shade adds color to a layered outfit while leaving the sheer chiffon texture visible.'
    elif name=='cover':
        for k in c: c[k]=c[k].replace('210D Oxford','Oxford').replace('210D','Oxford')
        bullets=[b.replace('210D Oxford','Oxford').replace('210D','Oxford') for b in bullets]
    elif name=='elastic':
        bullets[1]='Tropical Floral Print: The colorful botanical pattern gives the square table cover a decorative focal point for dining and gathering spaces.'
        bullets[2]='Polyester Fabric: Made of 100% polyester, with a printed surface and an elastic edge around the square cover.'
        c['description']=c['description'].replace('Pattern: Printed','Pattern: Tropical floral print')
    elif name=='evening':
        c['highlights']='Champagne pleated satin evening bag with chain detail, polyester lining; 25 x 14.5 x 2 cm'
        bullets[4]='Champagne Finish: The pale champagne satin works with the gold-tone chain detail and asymmetric pleated front.'
    elif name=='jewelry':
        c['highlights']='Teal fabric zip jewelry pouch with accordion-style interior and tassel accent'
        bullets[0]='Jewelry Storage Layout: The accordion-style interior provides separate sections for organizing small jewelry items; the images show the actual layout.'
        bullets[4]='Teal Exterior: A blue-green fabric exterior is finished with a zipper and decorative tassel.'
        c['description']=c['description'].replace('Six-layer layout','Accordion-style layered layout')
    elif name=='mesh':
        c['highlights']='White EVA toiletry pouch for makeup brushes and toothbrush storage'
        bullets[1]='Visible Pouch Detail: The white pouch has a zip opening and a textured mesh-style panel, as shown in the product images.'
        bullets[4]='White Finish: The neutral white color coordinates with bathroom and travel accessories.'
    elif name=='pouch':
        c['highlights']='Blue contrast-color leopard print polyester makeup pouch with magnetic tab closure'
        bullets[1]='Cosmetic Pouch Shape: The wide opening gives access to the interior; compare the product measurements with the items you plan to carry.'
        bullets[2]='Polyester Shell: The fabric exterior combines a leopard print panel with contrast color blocking.'
        bullets[3]='Blue Contrast Color: This version features the blue colorway shown in the included product images.'
    c['bullets']='\n'.join(bullets)
    c['description']=re.sub(r'^Colors?:.*$', 'Color: '+color, c['description'], flags=re.M)
    if name=='elastic' and 'Color:' not in c['description']:
        c['description']=c['description'].replace('Shape: Square','Color/Pattern: Tropical Floral\nShape: Square')
    c['description']=c['description'].replace('champagne or black','champagne')
    assert 'Product:' in c['description'] and 'Notes:' in c['description']
    assert len(c['terms'].encode('utf-8'))<=250, asin
    sku=p.get('sku') or 'NEW-'+asin
    folder=OUT/(sku+'-'+label)
    images=folder/'图片'
    images.mkdir(parents=True, exist_ok=True)
    for n in range(1,count+1):
        with Image.open(BATCH/f'ai-master-{name}'/f'{n}.png') as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            if min(im.size)<1600:
                ratio=1600/min(im.size)
                im=im.resize((round(im.width*ratio),round(im.height*ratio)),Image.Resampling.LANCZOS)
            im.save(images/f'{color.replace(" ","-")}-{n:02d}.jpg',quality=95,subsampling=0)
    (folder/'listing.json').write_text(json.dumps(dict(sku=sku,market='US',brand='Generic',manufacturer='Generic',color=color,**c),ensure_ascii=False,indent=2),encoding='utf-8')
    sections=[('Title',c['title']),('Highlights',c['highlights'])]+[(f'Bullet {i}',b) for i,b in enumerate(bullets,1)]+[('Description',c['description']),('Search Terms',c['terms'])]
    (folder/'Listing.txt').write_text('\n\n'.join(k+'\n'+v for k,v in sections),encoding='utf-8-sig')
    supplier=json.loads((BATCH/f'supplier-{asin}.json').read_text(encoding='utf-8'))
    (folder/'货源资料.json').write_text(json.dumps(supplier,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'货源.txt').write_text('货源链接：'+supplier.get('sourceUrl',p.get('sourceUrl',''))+'\n供应商：'+supplier.get('supplier','')+'\n交付颜色/图案：'+color+'\n',encoding='utf-8-sig')
    sizes=[x.strip() for x in re.split('[,，]',p.get('sizeNames') or '') if x.strip()] or ['']
    with (folder/'变体.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['parent_sku','child_sku','color','size','price_usd','quantity','main_image'])
        for i,size in enumerate(sizes,1):w.writerow([sku,f'{sku}-{color.replace(" ","")}-{i:02}',color,size,'','',f'图片/{color.replace(" ","-")}-01.jpg'])
    rows.append(dict(sku=sku,name=label,color=color,images=count,sizes=' / '.join(sizes),folder=folder.name))

with (OUT/'交付清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
(OUT/'交付说明.txt').write_text('10款产品，41张AI母版图片，每款独立文件夹。Listing.txt为可复制刊登文案，listing.json为结构化文案，变体.csv为当前母版颜色及已采集尺码。图片均为JPEG，短边至少1600像素。\n本包只包含母版颜色，未完成的其他颜色不包含。\n发布数据：售价和库存未提供，CSV保留空白；货源资料保留原始已知信息及缺口，不能将竞品ASIN当成新产品GTIN。首饰包蓝绿色与印花桌布图案的供应商SKU尚未精确对应；知识产权、供货授权及部分包装数据未全部核实。本包未执行店小秘发布。\n',encoding='utf-8-sig')
archive=OUT.with_suffix('.zip')
if archive.exists():raise SystemExit('ZIP exists')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for f in sorted(OUT.rglob('*')):
        if f.is_file():z.write(f,f.relative_to(OUT.parent))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
jpgs=list(OUT.rglob('*.jpg'))
assert len(jpgs)==41
for f in jpgs:
    with Image.open(f) as im:assert min(im.size)>=1600
print(json.dumps({'folder':str(OUT),'zip':str(archive),'products':len(rows),'images':len(jpgs),'bytes':archive.stat().st_size},ensure_ascii=False))
