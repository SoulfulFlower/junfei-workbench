import io, json, urllib.request
from pathlib import Path
from PIL import Image

root=Path('data/batch-20261030')
out=root/'source-B0FG3F13K2'
out.mkdir(exist_ok=True)
ids=['lnEYKZ1gif52DYib2','ixWiSP1gif53pUbVY','2jPafs1gif53DYvgm','R9D5gn1gif52aLYzo','Yrg8Ye1gif53vDDA9','rBAquY1gif53SOt9o','RXjGcX1gif52aN6gx']
urls=['https://cbu01.alicdn.com/img/ibank/O1CN01'+i+'_!!2209957334176-0-cib.jpg_.webp' for i in ids]
canvas=Image.new('RGB',(1200,1200),'white')
for n,url in enumerate(urls):
    raw=urllib.request.urlopen(url,timeout=40).read()
    (out/f'{n}.image').write_bytes(raw)
    im=Image.open(io.BytesIO(raw)).convert('RGB');im.thumbnail((390,390))
    canvas.paste(im,((n%3)*400,(n//3)*400))
canvas.save(out/'contact.jpg')
facts={'referenceAsin':'B0FG3F13K2','url':'https://detail.1688.com/offer/1002212696577.html','title':'简约纯色绸缎色丁褶皱设计链条晚宴包','supplier':'义乌市静居箱包有限公司','retrievedAt':'2026-10-30','captureMethod':'browser-visible-page-image-search','images':urls,'colors':['香槟色','黑色'],'attributes':{'material':'外层具体成分未明确；里料涤纶','brand':'静居；页面无可授权自有品牌','closure':'磁扣','size':'25×14.5×2cm；页面称同包装尺寸','packageweight':'约200g','included':'一条短链','sku':'XF-52'},'priceEvidence':'常规29元，2件起批；50–299件27元，300件以上25元；券后26.94不作常规成本；境内运费7元起','holds':['参考商品为橙色，货源只证实香槟色和黑色，不制作不存在的橙色SKU','品牌使用权与美国知识产权待核实','实物图片与目标款式细节待比对','外层成分未明确，不宣称真丝','实际包装尺寸与运费需复核'],'status':'candidate_pending_visual_review'}
(root/'supplier-candidate-B0FG3F13K2.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
print(out/'contact.jpg')
