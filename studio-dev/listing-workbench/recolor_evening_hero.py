"""Local-only black SKU trial; explicit cloth mask keeps gold hardware intact."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
from local_mask_recolor import recolor
root=Path('data/batch-20261030');out=root/'ai-master-evening'/'local-black';out.mkdir(exist_ok=True)
source=Image.open(root/'ai-master-evening/1.png').convert('RGB')
mask=Image.new('L',(600,600));draw=ImageDraw.Draw(mask)
draw.polygon([(28,151),(157,151),(351,152),(530,151),(568,154),(573,194),(573,463),(566,475),(395,477),(215,481),(42,477),(27,465),(24,383),(24,232)],fill=255)
mask=mask.resize(source.size).filter(ImageFilter.GaussianBlur(.7))
target=Image.open(root/'source-B0FG3F13K2/4.image').convert('RGB')
# Actual supplier black fabric sample, away from background and hardware.
result=recolor(source,mask,target,(210,730,930,1120))
mask.save(out/'cloth-mask.png');result.save(out/'black-hero-review.png')
preview=result.copy();preview.thumbnail((600,600));preview.save(out/'preview.jpg')
overlay=source.copy();overlay.paste(Image.new('RGB',source.size,(0,240,180)),mask=mask.point(lambda a:int(a*.4)));overlay.thumbnail((600,600));overlay.save(out/'mask-review.jpg')
(out/'manifest.json').write_text(json.dumps({'method':'local-mask-reference-quantile','paidGeneration':False,'status':'needs_color_and_mask_review','source':'../1.png','targetReference':'source-B0FG3F13K2/4.image','sampleBox':[210,730,930,1120]},indent=2),encoding='utf-8')
print(out/'preview.jpg')
