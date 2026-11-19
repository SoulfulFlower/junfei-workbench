"""Keep cape selling copy tied to visible source construction."""
import json,sqlite3
from pathlib import Path
path=Path('data/batch-20261030/listing-B0H4R6193H.json')
d=json.loads(path.read_text(encoding='utf-8'));c=d['copy']
c['bullets']='\n'.join([
'High-Low Silhouette: A short front and longer back create an asymmetric drape over a dress or top. The longer sides form the distinctive flowing outline shown in the product photos.',
'Sheer Chiffon Appearance: The translucent fabric lets the outfit underneath remain visible, adding a separate layer of color and texture. The dress shown is a styling example and is not included.',
'Rounded Neckline: A simple round opening frames the neckline, with a plain edge that keeps attention on the drape and the outfit underneath.',
'Open Sides: The cape hangs from the shoulders with open sides rather than fitted sleeves. Review the product photos and confirm the measurements before choosing this style.',
'Three Solid Colors: White, black and burgundy offer different ways to coordinate this chiffon capelet with evening outfits, wedding guest dresses and formal occasion styling.'
])
c['description']=c['description'].replace('Product: 1 Pcs x solid color chiffon high-low cape poncho shawl wrap','Product: Solid color chiffon high-low cape poncho shawl wrap')
c['alternatives'].pop('bulletsConversion',None);c['alternatives'].pop('bulletsQuestions',None)
c['editorialCorrections']=['Removed package-weight benefits, unsupported foldability and cool-weather claims. Removed unverified package quantity. Replaced stale alternative bullets containing these claims.']
path.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
 db.execute('BEGIN IMMEDIATE');rev,body=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone();s=json.loads(body)
 s['copy']['IMP-US-B0H4R6193H-US']=c
 db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(rev+1,json.dumps(s,ensure_ascii=False)))
print('CAPE_COPY_UPDATED')
