import io,json,urllib.request
from pathlib import Path
from PIL import Image
root=Path('data/batch-20261030');out=root/'source-cape-alternative';out.mkdir(exist_ok=True)
ids=['rTz9c229Oce6CMpCi','Aa1f6v29Oce6CGmkK','ph1MmQ29Oce5t5gl5','75p7LQ29Oce5tA7Jk','N6QRKF29Oce5t5glG']
urls=['https://cbu01.alicdn.com/img/ibank/O1CN01'+i+'_!!2214397748058-0-cib.jpg_.webp' for i in ids]
sheet=Image.new('RGB',(1200,800),'white')
for n,url in enumerate(urls):
 raw=urllib.request.urlopen(url,timeout=40).read();(out/f'{n}.image').write_bytes(raw)
 im=Image.open(io.BytesIO(raw)).convert('RGB');im.thumbnail((395,395));sheet.paste(im,((n%3)*400,(n//3)*400))
sheet.save(out/'contact.jpg')
facts={'referenceAsin':'B0H4R6193H','url':'https://detail.1688.com/offer/1059114174209.html','title':'纯色雪纺前短后长斗篷披肩','supplier':'苏州巴朵丝电子商务有限公司','captureMethod':'browser-visible-page-image-search','retrievedAt':'2026-10-30','images':urls,'referenceImages':[urls[i] for i in [0,1,3,4]],'colors':['白色','黑色','酒红色'],'attributes':{'material':'雪纺，具体纤维未明确；成分含量80–90%','brand':'朗弗诺，未取得品牌授权','packageweight':'200g','size':'135–175CM标注口径不明，不能作为披肩实测长度'},'priceEvidence':'常规24元，一件起批；券后18.87不作常规成本；境内运费5元起','packageWeightG':200,'holds':['品牌使用权及美国知识产权待核实，不使用朗弗诺品牌','包装130×200×5cm明显疑似展开尺寸，不能代入运费，需实测折叠包装','尺寸135–175CM含义不明，不生成尺码承诺','雪纺具体纤维未明确，不宣称真丝或防晒性能'],'status':'source_candidate_pending_photo_review','supplierMetrics':{'fulfillmentPercent':96.5,'qualityPercent':100,'repeatPercent':52.5,'pickup48hPercent':96}}
(root/'supplier-candidate-cape-alternative.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
print(out/'contact.jpg')
