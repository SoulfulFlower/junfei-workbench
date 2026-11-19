"""Persist verified facts and color-photo bindings without touching navigation."""
import json
import sqlite3
from pathlib import Path
ROOT=Path('data/batch-20261030')
path=ROOT/'supplier-B0HKM1TPZ1.json'
e=json.loads(path.read_text(encoding='utf-8'))
codes={'红':'rPuJbvrduSH','卡其':'OvT4ZmRlhkH','黑白':'FLC0P6t5FDC','绿':'qra0A50LWyK','蓝':'eDsvwdSIMPE','浅灰':'rhh860fdddD'}
english={'红':'Red','卡其':'Khaki','黑白':'Black and White','绿':'Green','蓝':'Blue','浅灰':'Light Gray'}
e['variantReferences']=[{'color':c,'english':english[c],'url':'https://cbu01.alicdn.com/img/ibank/O1CN01'+code+'1WPfQ_!!2215826830658-0-cib.jpg_.webp'} for c,code in codes.items()]
e['holds']=[h for h in e['holds'] if '颜色图逐项' not in h]
path.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding='utf-8')
path=ROOT/'supplier-B0D2DS6JT6.json'
e=json.loads(path.read_text(encoding='utf-8'))
e['referenceImages']=['https://cbu01.alicdn.com/img/ibank/O1CN01ccBP9h25kp0qeNRx6_!!980537565-0-cib.jpg_.webp','https://cbu01.alicdn.com/img/ibank/O1CN01wh9uwO25kp0raHjUR_!!980537565-0-cib.jpg_.webp']
e['colors']=['白色']
path.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding='utf-8')
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
    db.execute('BEGIN IMMEDIATE')
    revision,body=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
    state=json.loads(body)
    for path in ROOT.glob('supplier-*.json'):
        e=json.loads(path.read_text(encoding='utf-8'))
        asin=e.get('asin') or e.get('referenceAsin')
        p=next((p for p in state['products'] if p['id']=='IMP-US-'+str(asin)),None)
        if not p:continue
        p['supplierVerification']=e
        refs=e.get('referenceImages') or e.get('images')
        if refs:
            p.setdefault('sourceImport',{}).setdefault('supplier',{})['images']=refs
        sizes=e.get('sizes') or list(e.get('sizePricesCny',{}))
        if sizes:p['sizeNames']=','.join(sizes);p['sizes']=len(sizes)
        if e.get('variantReferences'):
            p['supplierColorReferences']=e['variantReferences']
            p['assetColorBindings']={r['url']:r['color'] for r in e['variantReferences']}
        listing_path=ROOT/('listing-'+asin+'.json')
        if listing_path.exists():
            listing=json.loads(listing_path.read_text(encoding='utf-8'))
            state.setdefault('copy',{})[p['id']+'-US']=listing.get('copy',listing)
    db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(state,ensure_ascii=False)))
print('Evidence and active listings synchronized')
