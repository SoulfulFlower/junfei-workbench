import html
import json
from PIL import Image, ImageOps, ImageDraw
import trial_979071716133 as t

copy=t.state()['copy'][t.PID+'-US']
t.change(lambda s:s['copy'].__setitem__(t.PID+'-US',copy))
t.change(lambda s:next(p for p in s['products'] if p['id']==t.PID).update(status='待审核'))
t.dump('product.json',t.product())
t.dump('listing-reviewed.json',copy)
(t.OUT/'listing.txt').write_text('\n\n'.join(k.upper()+'\n'+copy.get(k,'') for k in ['title','highlights','bullets','description','terms']),encoding='utf-8')
runs=t.visual.list_projects(t.PID)['runs']
t.dump('image-runs.json',runs)
images=[]
for slot in range(7):
    candidates=[r for r in runs if r.get('slot')==slot and r.get('image') and r.get('projectId')=='57b7be906795432ca987dd5811ecc55b']
    if not candidates: continue
    run=candidates[0]
    raw,mime=t.studio_bridge.result_image(run['id'])
    name=f'gallery-{slot+1:02d}.'+{'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[mime]
    (t.OUT/name).write_bytes(raw)
    images.append((name,f'Gallery {slot+1} / {run.get("status", "review")}'))
images.append(('recolor-wine-red.png','Wine red recolor sample'))
sheet=Image.new('RGB',(1200,((len(images)+2)//3)*440),'#eeeeee')
draw=ImageDraw.Draw(sheet)
for i,(name,label) in enumerate(images):
    im=Image.open(t.OUT/name).convert('RGB');im.thumbnail((390,390))
    x=(i%3)*400;y=(i//3)*440
    sheet.paste(im,(x+(400-im.width)//2,y+(390-im.height)//2));draw.text((x+8,y+400),label,fill='black')
sheet.save(t.OUT/'contact-sheet.jpg',quality=92)
report='''本地样品测试，未部署、未发布。
货源：1688 offer 979071716133；参考 ASIN：B0G8F3NL39。
22 个供应商颜色 × XS/S/M/L = 88 个草稿组合；库存、SKU可售状态尚未核验。
供应商有“一件不代发”提示，应确认采购起订量。
面料仅确认以涤纶为主、微弹；无精确成分比例、实测尺码表、洗护证据及背面照片。
不采用参考ASIN中无货源依据的绑带、背扣、可调肩带等描述。
换色仅完成酒红色一份样图；未生成全部22色的整套图库。
所有图像仍需对照实物审查版型、波点及颜色；自动质检结果不等于实物核验。
'''
(t.OUT/'README.txt').write_text(report,encoding='utf-8')
parts=['<!doctype html><meta charset="utf-8"><title>本地产品测试</title><style>body{font:16px Arial;max-width:1200px;margin:35px auto;padding:20px;color:#222}img{width:100%;border:1px solid #ddd}section{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}pre{white-space:pre-wrap;line-height:1.6}article{padding:20px;background:#f5f5f5}</style><h1>Y325 本地产品自动化测试</h1><article><pre>'+html.escape(report)+'</pre></article>']
parts.append('<nav aria-label="预览导航" style="position:sticky;top:0;background:white;padding:16px;border-bottom:1px solid #ddd;display:flex;gap:24px;flex-wrap:wrap"><a href="http://127.0.0.1:18765/">返回本地工作台</a><a href="http://127.0.0.1:18765/?product=IMP-US-B0G8F3NL39">编辑此产品</a><a href="#listing-copy">Listing 文案</a><a href="#keyword-research">关键词调研</a><a href="#product-gallery">图片与换色</a></nav><p>本页是导出预览；进入本地工作台可继续编辑。</p><div id="listing-copy"></div>')
for k in ['title','highlights','bullets','description','terms']:
    parts.append('<h2>'+k+'</h2><pre>'+html.escape(copy[k])+'</pre>')
parts.append('<details><summary>中文翻译</summary>')
for k,v in copy.get('translations',{}).items():
    parts.append('<h3>'+html.escape(k)+'</h3><pre>'+html.escape(v)+'</pre>')
parts.append('</details>')
research=t.product().get('competitorResearch',{}).get('US',{})
parts.append('<h2 id="keyword-research">关键词调研依据</h2><p>SellerSprite 美国站；挖掘月份 2026.09。购买率为第三方市场口径，非本品转化率。未知值留空；非全量。</p><p><a href="keywords.csv">关键词数据 CSV</a></p><table border="1" cellpadding="8"><tr><th>关键词</th><th>月搜索量</th><th>市场购买率</th><th>来源</th></tr>')
for kw in research.get('keywords',[]):
    m=kw.get('metrics',[{}])[0];rate=m.get('purchaseRate')
    parts.append('<tr><td>'+html.escape(kw['phrase'])+'</td><td>'+str(kw.get('monthlySearches') if kw.get('monthlySearches') is not None else '未知')+'</td><td>'+(f'{rate:.2%}' if isinstance(rate,(int,float)) else '未知')+'</td><td>'+html.escape(m.get('source',''))+'</td></tr>')
parts.append('</table><h3>内部审核</h3><pre>'+html.escape(copy.get('warnings',''))+'</pre>')
parts.append('<h2 id="product-gallery">生成图片及换色样图</h2><section>')
parts.extend('<div><img src="'+name+'"><p>'+html.escape(label)+'</p></div>' for name,label in images)
parts.append('</section><p><a href="variants.csv">88个变体草稿 CSV</a></p>')
(t.OUT/'preview.html').write_text(''.join(parts),encoding='utf-8')
print(json.dumps({'images':len(images),'output':str(t.OUT)},ensure_ascii=True))

