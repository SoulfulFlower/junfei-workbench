import json,urllib.request,io
from pathlib import Path
from PIL import Image,ImageDraw
root=Path('data/batch-20261030');out=root/'source-B0H4R6193H';out.mkdir(exist_ok=True)
urls=['https://cbu01.alicdn.com/img/ibank/'+x+'!!2214609930847-0-cib.jpg_.webp' for x in ['O1CN01RwPWQiydJIB1chua_','O1CN01njlaSJY3T7C1chua_','O1CN01HtqDf5QLzcG1chua_','O1CN01iiHyisUl2gC1chua_']]
frames=[]
for n,url in enumerate(urls):
 raw=urllib.request.urlopen(url,timeout=40).read();(out/f'{n}.image').write_bytes(raw)
 im=Image.open(io.BytesIO(raw)).convert('RGB');im.thumbnail((400,400));frames.append(im)
canvas=Image.new('RGB',(800,800),'white')
for n,im in enumerate(frames):canvas.paste(im,((n%2)*400,(n//2)*400))
canvas.save(out/'contact.jpg')
facts={'referenceAsin':'B0H4R6193H','url':'https://detail.1688.com/offer/1069141291812.html','title':'亚马逊热卖款不规则雪纺披肩新娘礼服外搭披风气质斗篷可一件代发','supplier':'苏州美币达贸易有限公司','captureMethod':'browser-visible-page-image-search','retrievedAt':'2026-10-30','images':urls,'attributes':{'material':'雪纺，具体纤维未明确；成分含量80–90%','brand':'其他','packageDimensions':'30×25×2cm','packageWeight':'200g','length':'肩到裙摆130cm；宽度00无效'},'colors':['纯白','乳白','酒红','黑','黄','浅卡其','浅灰','棕','粉','藏青'],'priceEvidence':'常规36元，起订2件；100–199件35元；200件以上33元；境内运费5元起','holds':['供应商好评76.9%、履约74%，待评估替代供应商','图片款式一致性待核实','品牌授权和美国知识产权待核实','订单属性4–7天与发货承诺3天冲突'],'status':'candidate_not_imported'}
(root/'supplier-candidate-B0H4R6193H.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
print(out/'contact.jpg')
