"""Remove unsupported fit/care claims and internal notes from buyer copy."""
import json,sqlite3
from pathlib import Path
path=Path('data/batch-20261030/listing-B0FG3F13K2.json')
d=json.loads(path.read_text(encoding='utf-8'));c=d.get('copy',d)
c['bullets']='\n'.join([
'Pleated Satin Look: An asymmetric pleated front gives this clutch purse its distinctive texture for evening outfits, weddings and formal occasions.',
'Slim Rectangular Shape: The bag measures approximately 25 x 14.5 x 2 cm. Compare the measurements with the items you plan to carry.',
'Magnetic Closure: The top opens with a magnetic fastening, with a polyester-lined interior visible inside.',
'Gold-Tone Chain: A matching gold-tone chain complements the pleated front and provides another way to hold the evening bag.',
'Two Solid Colors: Choose champagne or black to coordinate with your outfit. The pleated design and compact silhouette suit simple formal styling.'])
c['description']='Pleated Satin Chain Clutch Purse for Evening Occasions\nProduct Type: Pleated evening clutch\nLining: Polyester\nDimensions: Approximately 25 x 14.5 x 2 cm\nColors: Champagne or Black\nClosure: Magnetic fastening\n\nProduct: 1 x evening bag with chain\n\nNotes:\n1. Due to manual measurement, there may be slight differences in size. Thank you for your understanding\n2. Due to differences in monitors and lighting, the image may not reflect the actual color of the item. Thank you for your understanding'
c['editorialCorrections']=['Removed unverified phone capacity, care advice, package weight from selling bullets, and sourcing/internal fiber notes from buyer-facing text.']
path.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
 db.execute('BEGIN IMMEDIATE');revision,body=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone();s=json.loads(body)
 s['copy']['IMP-US-B0FG3F13K2-US']=c
 db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(s,ensure_ascii=False)))
print('BUYER_COPY_CORRECTED')
