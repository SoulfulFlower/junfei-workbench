"""Authenticated, escaped preview of saved copy and latest gallery results."""
from html import escape

def render(product,copy,view):
    e=lambda value:escape(str(value or ''))
    images=view.get('sets',{}).get('gallery',{}).get('images',[])
    count=sum(bool(im.get('final_url')) for im in images)
    passed=sum(bool(im.get('render_qa',{}).get('ready')) for im in images)
    cards=[]
    for i,image in enumerate(images):
        if not image.get('final_url'):continue
        status='AI检查通过，待人工确认' if image.get('render_qa',{}).get('ready') else '待修改 / 复核'
        cards.append('<figure><a href="'+e(image['final_url'])+'" target="_blank"><img src="'+e(image['final_url'])+'" alt="'+e(image.get('role'))+'"></a><figcaption>'+str(i+1)+' · '+e(image.get('role'))+' · '+status+'</figcaption></figure>')
    fields=[('商品亮点','highlights'),('五点描述','bullets'),('产品描述','description'),('后台搜索词','terms')]
    text=''.join('<section><h2>'+label+'</h2><p class="copy">'+e(copy.get(key))+'</p></section>' for label,key in fields)
    translations=copy.get('translations',{})
    zh=''.join('<section><h3>'+label+'</h3><p class="copy">'+e(translations.get(key))+'</p></section>' for label,key in [('标题','title'),*fields])
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Listing完整预览 · '+e(product['id'])+'</title><style>body{margin:0;background:#eef2f6;color:#203047;font:16px/1.7 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:28px}header,article,aside,details{background:white;border-radius:16px;padding:24px;margin-bottom:20px}h1{font-size:28px;line-height:1.4}h2{font-size:19px}.note{background:#fff4d9;padding:14px;border-radius:10px}.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}figure{margin:0;background:white;padding:12px;border-radius:14px}img{width:100%;aspect-ratio:1;object-fit:contain}figcaption{font-size:13px;color:#56677b}.copy{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#66788a}@media(max-width:700px){.gallery{grid-template-columns:1fr 1fr}main{padding:12px}}</style><main><header><small>钧飞跨境 · '+e(product.get('market','UK'))+' · '+e(product['id'])+'</small><h1>'+e(copy.get('title'))+'</h1><div class="note">Listing 草稿预览，未发布。已保存 '+str(count)+' 张图片，'+str(passed)+' 张通过单图AI检查；图片及品牌仍需审核。</div></header><div class="gallery">'+''.join(cards)+'</div><article>'+text+'</article><details><summary>展开中文翻译</summary>'+zh+'</details><details><summary>内部检查与缺失资料</summary><p class="copy">'+e(copy.get('warnings'))+'</p></details></main></html>').encode('utf-8')
