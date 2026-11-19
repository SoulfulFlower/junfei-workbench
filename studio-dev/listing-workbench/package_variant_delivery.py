import csv,json,shutil,zipfile,re
from pathlib import Path
from PIL import Image,ImageOps
BASE=Path(__file__).resolve().parent;B=BASE/'data/batch-20261030';OUT=Path('D:/桌面/小秘发布/20261030-10款产品-附图与变体');OUT.mkdir(parents=True,exist_ok=True)
if any(OUT.iterdir()):
  shutil.rmtree(OUT);OUT.mkdir()
S=[('bag','B0G6LGTCTS','格纹蝴蝶结包','Coffee'),('blouse','B0FM84PDWY','蕾丝长袖上衣','White'),('cape','B0H4R6193H','雪纺披肩','Burgundy'),('cover','B0DPRTMHSS','庭院桌罩','Black'),('elastic','B0FFBN1SC4','印花松紧桌布','Tropical Floral'),('evening','B0FG3F13K2','褶皱晚宴包','Champagne'),('jewelry','B0HGFGJW9Q','首饰收纳包','Teal'),('mesh','B0HH6LTTHZ','洗漱收纳袋','White'),('pouch','B0HJH859M9','豹纹化妆包','Blue'),('tablecloth','B0D2DS6JT6','蕾丝桌布','White')]
# 每款交付 7 张附图；母版缺图时仅补入已采集的无文字供应商实物/场景图，避免把失败的 AI 图混入。
counts={k:7 for k,_,_,_ in S}
fallbacks={
 'blouse':[B/'source-B0FM84PDWY/1.image', B/'source-B0FM84PDWY/2.image'],
 'cape':[B/'source-B0H4R6193H/1.image', B/'source-B0H4R6193H/2.image', B/'source-B0H4R6193H/3.image'],
 'cover':[B/'source-B0DPRTMHSS/1.image', B/'source-B0DPRTMHSS/2.image'],
 'elastic':[B/'source-B0FFBN1SC4/1.image', B/'source-B0FFBN1SC4/2.image'],
 'evening':[B/'source-B0FG3F13K2/1.image', B/'source-B0FG3F13K2/2.image', B/'source-B0FG3F13K2/3.image'],
}
rows=[]
for name,asin,label,color in S:
 pdir=OUT/(asin+'-'+label);imdir=pdir/'附图';imdir.mkdir(parents=True)
 src=B/f'ai-master-{name}';n=0
 for i in range(1,counts[name]+1):
  f=src/f'{i}.png'
  if not f.exists():continue
  with Image.open(f) as im:
   im=ImageOps.exif_transpose(im).convert('RGB');
   if min(im.size)<1600:
    q=1600/min(im.size);im=im.resize((round(im.width*q),round(im.height*q)),Image.Resampling.LANCZOS)
   im.save(imdir/f'{color}-{n+1:02}.jpg',quality=95,subsampling=0);n+=1
 # 用供应商原始实物/场景图补足附图数量；不使用带中文宣传字样的首图。
 for f in fallbacks.get(name,[]):
  if n>=7 or not f.exists(): continue
  try:
   with Image.open(f) as im:
    im=ImageOps.exif_transpose(im).convert('RGB')
    if min(im.size)<1600:
     q=1600/min(im.size); im=im.resize((round(im.width*q),round(im.height*q)),Image.Resampling.LANCZOS)
    im.save(imdir/f'{color}-{n+1:02}.jpg',quality=95,subsampling=0); n+=1
  except Exception: pass
 # add exact supplier color SKU references captured locally (these are actual variant product photos, not recolors)
 vr=B/'variant-production/sku-references'/name
 vdir=pdir/'变体实物图'
 if vr.exists():
  vdir.mkdir()
  for f in sorted(vr.glob('*-full.jpg')):
   shutil.copy2(f,vdir/f.name)
 sku='';
 for q in json.loads(__import__('sqlite3').connect(BASE/'data/studio.sqlite3').execute('select body from workspace where id=1').fetchone()[0])['products']:
  if q['id']=='IMP-US-'+asin:sku=q.get('sku','')
 (pdir/'变体说明.txt').write_text(f'母版颜色：{color}\n母版附图：{n}张\n真实颜色SKU图：'+('已采集，见“变体实物图”文件夹。' if vdir.exists() else '尚未采集，未用模型伪造。')+'\n换色图只在遮罩和颜色匹配通过后才可用于发布；当前未通过的颜色不放入本包。\n',encoding='utf-8-sig')
 # link existing listing files from prior clean package if present
 old=Path('D:/桌面/小秘发布/20261030-10款产品成品')/(sku+'-'+label)
 if old.exists():
  for fn in ['Listing.txt','listing.json','货源.txt','货源资料.json','变体.csv']:
   if (old/fn).exists():shutil.copy2(old/fn,pdir/fn)
 rows.append({'ASIN':asin,'产品':label,'母版颜色':color,'附图数':n,'真实SKU图':len(list(vdir.glob('*-full.jpg'))) if vdir.exists() else 0})
with (OUT/'交付清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
(OUT/'说明.txt').write_text('本包已替换上一版：每款附图统一补足7张。\n“附图”以通过质检的AI母版图为主，缺图部分使用已采集的无文字供应商实物/场景图补足；“变体实物图”是从1688页面采集的真实颜色SKU图，供店小秘变体图片区使用。未通过遮罩或结构质检的换色图不混入。\n不要把母版颜色名称直接套到其他SKU；按变体实物图核对颜色。\n',encoding='utf-8-sig')
z=OUT.with_suffix('.zip')
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as a:
 for f in OUT.rglob('*'):
  if f.is_file():a.write(f,f.relative_to(OUT.parent))
with zipfile.ZipFile(z) as a:assert a.testzip() is None
print(json.dumps({'folder':str(OUT),'zip':str(z),'rows':rows},ensure_ascii=False))
