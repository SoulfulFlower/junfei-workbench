"""Build and verify the complete local 22-colour trial delivery."""
import collections,csv,io,json,zipfile
from PIL import Image,ImageDraw,ImageFont
import trial_979071716133 as t
import colour_sets as c
import delivery_export as d
import cache_all_colours as cache

def finalize():
    p=t.product();sets=c.list_sets(t.PID)['sets']
    assert len(sets)==21
    assert all(len(s['items'])==7 and all(i.get('image') and i['status']=='awaiting_manual' for i in s['items']) for s in sets),'Incomplete or rejected outputs remain'
    for s in sets:cache.cache(s)
    cache.sheet()
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    board=Image.new('RGB',(5*280,5*310),'#edf0f3');draw=ImageDraw.Draw(board)
    for index,ref in enumerate(p['supplierColorReferences']):
        path=t.OUT/'gallery-01.png' if index==0 else cache.DEST/(ref['color']+'-01.png')
        im=Image.open(path).convert('RGB');im.thumbnail((276,276));x=index%5*280;y=index//5*310;board.paste(im,(x,y));draw.text((x+6,y+280),ref['color'],font=font,fill='#203047')
    board.save(t.OUT/'all-22-colours-preview.jpg',quality=92)
    listing=t.state()['copy'][t.PID+'-US'];raw=d.build(p,listing)
    path=t.OUT/'local-trial.zip';path.write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        prefix=p['sku']+'/'
        manifest=json.loads(z.read(prefix+'image-manifest.json'))
        counts=collections.Counter(i['color'] for i in manifest['images'])
        assert len(manifest['images'])==154 and len(counts)==22 and set(counts.values())=={7} and not manifest['missing'],counts
        variants=list(csv.DictReader(io.StringIO(z.read(prefix+'variants.csv').decode('utf-8-sig'))))
        assert len(variants)==88 and all(row['image_count']=='7' and len(row['generated_images'].split('|'))==7 and row['main_image'] in z.namelist() for row in variants)
        assert json.loads(z.read(prefix+p['sku']+'-listing.json'))['description']==listing['description']
        assert len({row['sku'] for row in variants})==88
    report={'colors':22,'images':154,'variants':88,'eachColorImages':7,'missing':[],'archive':str(path),'bytes':len(raw),'humanReviewed':False,'cloudChanged':False,'materialWarnings':{s['color']:s['referenceWarnings'] for s in sets if s.get('referenceWarnings')}}
    t.dump('complete-delivery-verification.json',report)
    print(json.dumps(report,ensure_ascii=True),flush=True)

if __name__=='__main__':finalize()
