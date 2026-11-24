"""Analyze precise editable fabric polygons; render later using local pixels only."""
import base64, io, json, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import visual_studio as v

ROOT=Path('data/batch-20261030')
OUT=ROOT/'variant-production';OUT.mkdir(exist_ok=True)

def data(path):
    im=Image.open(path).convert('RGB');im.thumbnail((1200,1200))
    b=io.BytesIO();im.save(b,'JPEG',quality=95)
    return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()

def analyze(pair):
    name,slot=pair
    dest=OUT/f'{name}-mask-{slot}.json'
    if dest.exists():return str(dest)
    result=v.model_json('You are a precise product fabric segmentation annotator for a deterministic local recoloring tool. This is NOT an image generation task. Inspect this single finished artwork and trace only the SOLD PRODUCT fabric, including ALL straps, handles, bows, every duplicate product and every macro/detail inset. Exclude background, typography, skin, hair, clothes, props, ground shadows and gold/silver hardware. Output JSON {"regions":[{"outer":[[x,y],...],"holes":[[[x,y],...]],"label":"..."}],"notes":"..."}. Coordinates normalized 0..1000 over the ENTIRE image. Use 12-30 vertices to follow actual curved boundaries tightly. Each disjoint product/strap region needs a separate polygon. Holes exclude openings between straps, hardware and skin. No rough bounding rectangles. Product target: '+name+'. Bag: include ALL coffee fabric including dark interior openings; straps may have neutral dark brown pixels. Evening clutch: champagne satin only, never gold chain/snap or cream background. Cape: burgundy chiffon ONLY, no ivory dress/skin; include magnified burgundy neckline inset. Blouse: white chiffon and lace, including translucent fabric but not skin visible through lace holes. Jewelry: teal fabric including tassel only; exclude gold zipper and ivory accordion inserts. Mesh: white fabric/net strands only, no holes/background/brushes. Pouch: exact blue and mint leopard fabric only, NOT matching blue/mint typography or caption rectangles.',{'name':name,'slot':slot},[data(ROOT/f'ai-master-{name}'/f'{slot}.png')])
    if not result.get('regions'):raise ValueError('No regions')
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(dest)

if __name__=='__main__':
    names=sys.argv[1:] or ['bag','evening','cape','blouse','jewelry','mesh','pouch']
    jobs=[(name,n) for name in names for n in range(1,8) if (ROOT/f'ai-master-{name}'/f'{n}.png').exists()]
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={pool.submit(analyze,j):j for j in jobs}
        for f in as_completed(tasks):
            try:print('SAVED',f.result(),flush=True)
            except Exception as e:print('ERROR',tasks[f],str(e),flush=True)
