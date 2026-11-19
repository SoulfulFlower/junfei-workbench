import json,sqlite3
from pathlib import Path
root=Path('data/batch-20261030')
colors=json.loads((root/'pouch-colors/colors.json').read_text(encoding='utf-8'))
evidence=root/'supplier-B0HJH859M9.json'
e=json.loads(evidence.read_text(encoding='utf-8'))
e['variantReferences']=colors
e['packageDimensionNote']='30 x 23 x 3 cm is supplier shipping package size, not product body dimensions.'
evidence.write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding='utf-8')
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
    db.execute('BEGIN IMMEDIATE')
    rev,raw=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone();state=json.loads(raw)
    p=next(p for p in state['products'] if p['id']=='IMP-US-B0HJH859M9')
    p.update(supplierVerification=e,supplierColorReferences=colors,assetColorBindings={r['url']:r['color'] for r in colors})
    db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(rev+1,json.dumps(state,ensure_ascii=False)))
print('SYNCED_REAL_SKU_REFERENCES',len(colors))
