"""Sync completed research and precise batch holds without resetting user edits."""
import json
import sqlite3
from pathlib import Path
ROOT=Path('data/batch-20261030')
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
    db.execute('BEGIN IMMEDIATE')
    revision,body=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
    state=json.loads(body)
    count=0
    for path in ROOT.glob('keywords-*.json'):
        asin=path.stem.removeprefix('keywords-')
        product=next((p for p in state['products'] if p['id']=='IMP-US-'+asin),None)
        if product:
            product.setdefault('competitorResearch',{})['US']=json.loads(path.read_text(encoding='utf-8'))
            count+=1
    for asin,reason in {
        'B0HKM1TPZ1':'包装37×30×7cm，体积重/8000=0.97125kg；已导入报价约103.70–135.35元运费，加采购23元。参考售价17.98美元下暂不投入制图，候选待替换；未核实当前报价有效性。',
        'B0GVBF7FQD':'42款印花的版权来源未核实；暂停制图和交付，候选待替换。',
    }.items():
        product=next((p for p in state['products'] if p['id']=='IMP-US-'+asin),None)
        if product:
            review=product.setdefault('productionReview',{})
            review.update(publishReady=False,batchDecision='replace_candidate',batchDecisionReason=reason)
    pid='IMP-US-B0D2DS6JT6'
    listing=state.get('copy',{}).get(pid+'-US',{})
    if listing:
        listing['description']=listing['description'].replace('Product: Polyester lace rectangle tablecloth table cover','Product: Polyester lace tablecloth table cover')
        (ROOT/'listing-B0D2DS6JT6.json').write_text(json.dumps({'copy':listing},ensure_ascii=False,indent=2),encoding='utf-8')
    db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(state,ensure_ascii=False)))
print('RESEARCH_SYNCED',count)
marker=ROOT/'visual-service-unavailable.json'
status=json.loads(marker.read_text(encoding='utf-8'))
status.update(status='recovered_verified',verifiedModel='gemini-3-flash-preview',qcTransport='JPEG',automaticRetry=False,imageRenderSubmitted=False)
marker.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
