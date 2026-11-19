import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw
import image_provider
root=Path('data/batch-20261030')
for asin in sys.argv[1:]:
    facts=json.loads((root/('supplier-'+asin+'.json')).read_text(encoding='utf-8'))
    refs=facts.get('referenceImages') or facts.get('images') or []
    out=root/('source-'+asin);out.mkdir(exist_ok=True)
    canvas=Image.new('RGB',(1200,((len(refs)+2)//3)*420),'white');draw=ImageDraw.Draw(canvas)
    for i,url in enumerate(refs):
        path=out/(str(i)+'.image')
        if not path.exists():path.write_bytes(image_provider.remote_reference(url)[0])
        image=Image.open(path).convert('RGB');image.thumbnail((390,390))
        canvas.paste(image,((i%3)*400,(i//3)*420+25));draw.text(((i%3)*400+5,(i//3)*420+4),str(i),fill='black')
    canvas.save(out/'contact.jpg')
    print(out/'contact.jpg',flush=True)
