"""Export available evidence for inspection only, never as publication-ready output."""
import html
import json
import sqlite3
from pathlib import Path
import delivery_export
import studio_bridge
import colour_sets
import visual_studio

root = Path('data/batch-20261030/review-output')
root.mkdir(exist_ok=True)
with sqlite3.connect('data/studio.sqlite3') as db:
    state = json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
sections = []
summary = []
for evidence in sorted(root.parent.glob('supplier-*.json')):
    asin = evidence.stem.removeprefix('supplier-')
    if asin in {'B0GVBF7FQD', 'B0HKM1TPZ1', 'B0HDZJ4HRF', 'B0CYP3RX18'}:
        continue  # Replaced or rejected candidates never count toward delivery.
    product = next((p for p in state['products'] if p['id'] == 'IMP-US-' + asin), None)
    if product is None:
        continue  # Supplier candidates are not imported products.
    listing = state.get('copy', {}).get(product['id'] + '-US', {})
    if not listing.get('title'):
        continue
    supplier = json.loads(evidence.read_text(encoding='utf-8'))
    source_url = supplier.get('sourceUrl') or supplier.get('url') or ''
    view = studio_bridge.get_view(product)
    master_id = view.get('sets', {}).get('gallery', {}).get('_projectId')
    master = visual_studio.get_project(master_id) if master_id else None
    details = ''
    if master:
        directed = master.get('uiPlan', {}).get('images', [])
        ai_master = master.get('productionMode') == 'ai_master' or any(i.get('production_method') == 'generate_once' for i in directed)
        passed = sum(i.get('_status') in ('approved', 'awaiting_manual') for i in view.get('sets', {}).get('gallery', {}).get('images', []))
        total = len(master['plan']['slots'])
        details = '<p>' + ('AI 分镜生成母版' if ai_master else '实物素材制作') + ' · 单图检查通过 ' + str(passed) + '/' + str(total) + ' · 整套 AI 检查：' + ('通过，待人工核对' if (master.get('set_qa') or {}).get('ready') else '未通过或待检查') + '</p>'
        storyboard_name = asin + '-storyboard.json'
        (root / storyboard_name).write_text(json.dumps({'projectId': master['id'], 'brief': master.get('brief'), 'images': directed, 'setQA': master.get('set_qa')}, ensure_ascii=False, indent=2), encoding='utf-8')
        details += '<p><a href="' + storyboard_name + '">查看分镜与出图指令</a></p>'
    (root / (asin + '-review-only.zip')).write_bytes(delivery_export.build(product, listing, view))
    cards = []
    for kind, plan in view.get('sets', {}).items():
        for slot, item in enumerate(plan.get('images', [])):
            if not item.get('_runId') or not item.get('final_url'):
                continue
            if item.get('_status') not in ('approved', 'awaiting_manual'):
                continue
            raw, mime = studio_bridge.result_image(item['_runId'])
            ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}[mime]
            name = asin + '-' + kind + '-' + str(slot + 1) + ext
            (root / name).write_bytes(raw)
            cards.append('<figure><img src="' + name + '"><figcaption>图片 ' + str(slot + 1) + ' · AI检查通过，待人工核对</figcaption></figure>')
    current_master=view.get('sets',{}).get('gallery',{}).get('_projectId')
    for variant in colour_sets.list_sets(product['id'])['sets']:
        if current_master and variant.get('masterId')!=current_master:
            continue
        for item in variant.get('items', []):
            if item.get('status') not in ('approved', 'awaiting_manual') or not item.get('image'):
                continue
            raw, mime = colour_sets.image_bytes(variant['id'], item['slot'])
            ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}[mime]
            name = asin + '-variant-' + variant['id'] + '-' + str(item['slot'] + 1) + ext
            (root / name).write_bytes(raw)
            label = str(variant['color']) + ' · 图片 ' + str(item['slot'] + 1) + ' · AI检查通过，待人工核对'
            cards.append('<figure><img loading="lazy" src="' + name + '"><figcaption>' + html.escape(label) + '</figcaption></figure>')
    supplier_holds = supplier.get('holds') or supplier.get('notes') or []
    copy_detail = '<details><summary>查看 Listing、关键词与待核验资料</summary>'
    for field,label in [('title','标题'),('bullets','五点'),('description','描述'),('terms','后台词')]:
        copy_detail += '<h3>'+label+'</h3><pre>'+html.escape(str(listing.get(field,'')))+'</pre>'
    keyword_rows=[row for market in product.get('competitorResearch',{}).values() for row in market.get('keywords',[])]
    copy_detail += '<p>已采集关键词记录：'+str(len(keyword_rows))+'；有数据的搜索量在审核包 keywords.csv 中，未知值保持空白。</p>'
    copy_detail += '<p>仍需核实美国知识产权、无标供货/品牌权利、实际包装及运费、变体图片与库存。</p><ul>'+''.join('<li>'+html.escape(str(h))+'</li>' for h in supplier_holds)+'</ul></details>'
    summary.append({'asin':asin,'productId':product['id'],'title':listing['title'],'sourceUrl':source_url,'masterProjectId':master_id,'masterQAReady':bool(master and (master.get('set_qa') or {}).get('ready')),'masterImages':len(cards),'listingPresent':True,'publishReady':False,'remaining':['Complete variant galleries and visual review','Verify packaging, quantity and freight','US IP screening and branding rights'],'supplierHolds':supplier_holds})
    sections.append('<section><h2>' + html.escape(asin) + '</h2><p>' + html.escape(listing['title']) + '</p>' + details + '<p><a href="http://127.0.0.1:18765/?product=' + product['id'] + '">产品库编辑</a> · <a href="'+html.escape(source_url,quote=True)+'">1688货源</a> · <a href="' + asin + '-review-only.zip">审核包</a></p><div class="gallery">' + ''.join(cards) + '</div>'+copy_detail+'</section>')
ready=sum(s['masterQAReady'] for s in summary)
status='已整理 '+str(len(summary))+' 款 Listing，'+str(ready)+' 款母版通过整套 AI 检查。变体、人工图片核对和供货核验尚未全部完成，审核包不能直接用于发布。'
(root / 'handoff-status.json').write_text(json.dumps({'publishReady':False,'products':summary},ensure_ascii=False,indent=2),encoding='utf-8')
(root / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>10款新品母版与Listing审核</title><style>body{font:16px system-ui;max-width:1200px;margin:30px auto;background:#f5f6f8;color:#162336}section{background:white;padding:24px;margin:20px 0;border-radius:12px}section .gallery{display:flex;flex-wrap:wrap}figure{margin:8px;width:280px}img{width:100%}figcaption{font-size:13px}a{color:#1264ac}pre{white-space:pre-wrap;font:15px/1.7 system-ui;background:#f3f5f8;padding:16px}summary{cursor:pointer;color:#1264ac;margin-top:15px}</style><h1>10款新品母版与Listing审核</h1><p>'+status+'</p><p><a href="ten-products-master-listing-review.zip">下载10款母版与Listing审核总包</a> · <a href="handoff-status.json">查看交接状态</a></p>' + ''.join(sections), encoding='utf-8')
# Only these ten indexed products enter the bundle; stale replaced products stay out.
import zipfile
with zipfile.ZipFile(root/'ten-products-master-listing-review.zip','w',zipfile.ZIP_DEFLATED) as bundle:
    for path in [root/'index.html',root/'handoff-status.json']:
        bundle.write(path,path.name)
    for row in summary:
        for path in root.glob(row['asin']+'-*'):
            if path.is_file():bundle.write(path,path.name)
print('REVIEW_OUTPUT', root.resolve(), 'LISTINGS', len(sections))
