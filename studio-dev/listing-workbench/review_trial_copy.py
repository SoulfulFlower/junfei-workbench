import json,csv,zipfile,runpy
import trial_979071716133 as t
c=t.state()['copy'][t.PID+'-US']
c['title']="Women's Bustier Top, Cropped Cami with Fixed Wide Straps"
c['highlights']='Sleeveless corset-style top with shaped cups, front seams, slight stretch; polka dot and solid options, XS-L'
c['bullets']='\n'.join([
"Bustier shape: This women's bustier top has a cropped, slim-fitting silhouette with formed cups and visible vertical front seams. The cup outlines and seams define the front of the bodice, while the short hem keeps the cut distinct from a full-length camisole. Choose this shape when comparing cropped cami designs; it is one separate top, rather than a dress or matching set.",
"Fixed wide straps: The sleeveless top has wide shoulder straps that are fixed in place and not removable. This strap construction is part of the design, so choose it if you want a cami with attached straps rather than a strapless style. The visible scalloped edging follows the neckline and hem, adding a separate detail to the polka dot or solid-color bodice.",
"Polyester with slight stretch: The main fabric is polyester, with slight stretch stated in the product information. This women’s corset top combines that material with a short, fitted cut and visible front seams. Use those specific details to compare its construction with other tops; the fabric description does not indicate a cotton, denim, mesh or leather garment.",
"Polka dot or solid: The color range includes both patterned and solid versions of the same cropped top. For a women's polka dot top, select a dot-pattern colorway; for a plain finish, choose one of the solid options. Dot and background colors vary by selection, so the black-and-white design shown in the main images does not represent every available colorway.",
"Sizes and package: Choose from XS, S, M and L in the selected colorway. Each package contains one sleeveless cropped cami, with no built-in padded cups. Compare the offered size and color options before choosing the combination you want; the cup shape and fixed straps belong to the top itself, while the size and color selection identifies the version included in the order."
])
c['description']=c['description'].replace('Women Polka Dot Bustier Top Sleeveless Corset Top','Women’s Cropped Bustier Top with Fixed Straps').replace('Style Category: Women corset top / bustier top','Style Category: Women’s corset-style cami / bustier top')
c['terms']=t.provider.fit_backend_bytes('camisole tank unpadded fitted scalloped bodice neckline vertical seams polyester stretch short cami womens clothing tops patterned dotted dots straps cropped bustiers sleeveless form cups solid layering')
c['translations']={
'title':'女士短款胸衣式吊带上衣，固定宽肩带',
'highlights':'无袖胸衣式上衣，立体罩杯、前部拼缝、微弹；可选波点或纯色，XS-L',
'bullets':'胸衣式轮廓：这款女士短款上衣为修身轮廓，带立体罩杯及可见前部纵向拼缝。罩杯外形和拼缝勾勒前片，短下摆区别于常规长款吊带背心。比较短款吊带设计时可参考这些结构；这是一件独立上衣，不是连衣裙或成套服装。\n固定宽肩带：无袖上衣配宽肩带，肩带固定且不可拆卸。如希望选择带固定肩带而非无肩带设计，可参考这一结构。领口与下摆可见波浪形饰边，为波点或纯色衣身增加细节。\n涤纶与微弹：主要面料为涤纶，产品资料标注略有弹性。这款女士胸衣式上衣采用短款修身剪裁及可见前部拼缝。比较不同上衣时可参考这些具体信息；该面料说明不表示本品为棉、牛仔、网纱或皮革制品。\n波点或纯色：同款短上衣包含印花及纯色版本。需要波点款时请选择点纹颜色，需要素色外观时请选择纯色。点纹及底色随选项变化，主图展示的黑白配色不代表所有颜色。\n尺码与包装：选定颜色后，可选XS、S、M、L。每份包装含一件无袖短款吊带上衣，无内置胸垫。选择前请比较可选尺码和颜色组合；罩杯外形与固定肩带属于上衣本身结构，而颜色与尺码选项决定订单中的具体版本。',
'description':t.provider.ensure_description_notes('女士固定肩带短款胸衣式上衣\n面料名称: 涤纶\n弹性: 微弹\n工艺: 立体罩杯与纵向拼缝\n衣长: 短款\n款式: 无袖、固定肩带、修身\n图案: 部分配色为波点，另有纯色可选\n罩杯: 无胸垫\n肩带类型: 固定、不可拆卸\n颜色: 多种配色，含波点及纯色\n尺码: XS、S、M、L\n风格类别: 女士胸衣式吊带上衣\n\n1件 x 女士固定肩带短款胸衣式上衣',chinese=True),
'terms':'吊带背心、无胸垫、修身、波浪饰边、衣身、领口、纵向拼缝、涤纶、微弹、短款、女士服装、印花、点纹、肩带、胸衣式上衣、无袖、立体罩杯、纯色、叠穿'}
c['warnings']='关键词数据来自卖家精灵美国站，挖掘月份2026.09；反查多数词量未知。购买率为第三方市场口径，非本品转化率。只采用与产品匹配的词，不采用无肩带、网纱、牛仔、绑带或未核实鱼骨等词。后台词可用相关词不足230字节，保留较短版本。尚无实测尺码表、精确纤维比例及背面照片；库存和一件不代发采购条件待核实。'
research=t.product()['competitorResearch']['US'];coverage=[]
for k in research['keywords']:
    phrase=k['phrase']; fields=[f for f in ['title','highlights','bullets','description','terms'] if phrase.casefold() in c[f].casefold()]
    coverage.append({'phrase':phrase,'exactPlacements':fields,'monthlySearches':k.get('monthlySearches'),'note':'按原词精确匹配；语法变形不计入此列' if fields else '未原词采用；保留数据供审核，正文可用自然语法或款式限定表达'})
c['contentAudit']={'keywordPlacements':[{'phrase':r['phrase'],'placement':f,'reason':'最终文本原词匹配'} for r in coverage for f in r['exactPlacements']],'omittedKeywords':[{'phrase':r['phrase'],'reason':r['note']} for r in coverage if not r['exactPlacements']],'factChecks':['核实实物颜色、尺码、面料比例及库存']}
c['zh']='\n\n'.join(c['translations'][k] for k in ['title','bullets','description'])
t.provider.validate_title_fields(c,'US');t.provider.validate_market_language(c,'US')
assert len(c['bullets'].splitlines())==5 and all(len(b)<=500 for b in c['bullets'].splitlines())
assert c['description'].endswith(t.provider.DESCRIPTION_NOTES)
t.change(lambda s:s['copy'].__setitem__(t.PID+'-US',c));t.dump('keyword-coverage.json',coverage);t.dump('listing-reviewed.json',c)
runpy.run_path('export_trial.py')
files=['preview.html','README.txt','listing.txt','listing-reviewed.json','variants.csv','contact-sheet.jpg','recolor-wine-red.png','recolor-qc.json','keywords.csv','keyword-coverage.json','keyword-research-reviewed.json','keyword-sources.json','keyword-mining.json']+[p.name for p in sorted(t.OUT.glob('gallery-*'))]
with zipfile.ZipFile(t.OUT/'local-trial.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in files:z.write(t.OUT/name,name)
print('REVIEWED',len(c['title']),[len(b) for b in c['bullets'].splitlines()],len(c['terms'].encode()))
