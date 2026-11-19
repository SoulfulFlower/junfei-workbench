"""Account-local immutable master selections and one deterministic render chain."""
import base64
import hashlib
import io
import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
import numpy as np
from PIL import Image
import app_paths
import colour_sets
import colour_master
import image_provider
from local_mask_recolor import render_fabric
from colour_tuning import controls

ROOT=app_paths.DATA
LOCK=threading.RLock()
VERSION='fabric-tone-v8'

def connection():
    c=sqlite3.connect(ROOT/'pixel_recolour.sqlite3',timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS selections(key TEXT, revision INTEGER, product TEXT, body TEXT, PRIMARY KEY(key,revision))')
    c.execute('CREATE TABLE IF NOT EXISTS renders(id TEXT PRIMARY KEY,product TEXT,body TEXT)')
    c.commit()
    return c

def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()

def asset(raw):
    digest=hashlib.sha256(raw).hexdigest();name=digest[:32]+'.png'
    folder=ROOT/'uploads';folder.mkdir(exist_ok=True,parents=True)
    path=folder/name
    if path.is_symlink():raise ValueError('图片路径异常')
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('图片内容冲突')
        return '/uploads/'+name
    temporary=folder/(uuid.uuid4().hex+'.tmp');temporary.write_bytes(raw);temporary.replace(path)
    return '/uploads/'+name

def image(url):
    raw=image_provider.local_image(url)
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>18_000_000:raise ValueError('图片超过1800万像素')
        im.load();return im.copy()

def fingerprint(im):
    raw=np.asarray(im.convert('RGB')).tobytes()
    if 'A' in im.getbands():raw+=b'RGBA-alpha:'+im.getchannel('A').tobytes()
    return hashlib.sha256(raw).hexdigest()

def master_items(product):
    wanted=colour_master.selection_id(product)
    if not wanted:
        project=colour_sets.studio_bridge.latest_project(product['id'],'gallery')
        wanted=project['id'] if project else None
    rows={}
    for s in colour_sets.list_sets(product['id'])['sets']:
        if wanted and s['masterId']!=wanted:continue
        for item in s['items']:
            if item.get('sourceUpload') and item['slot'] not in rows:
                rows[item['slot']]=item
    if not rows:
        from local_colour_sources import context
        rows={i['slot']:i for i in context(product)['items']}
    return rows

def source_row(item):
    raw=image_provider.local_image(item['sourceUpload'])
    if item.get('sourceSha256') and hashlib.sha256(raw).hexdigest()!=item['sourceSha256']:raise ValueError('已锁定母版文件内容变化，请核对原图')
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>18_000_000:raise ValueError('图片超过1800万像素')
        return {'slot':item['slot'],'source':item['sourceUpload'],'sourceHash':fingerprint(im),'width':im.width,'height':im.height,
                'productAbsent':item.get('productAbsent') is True}

def sources(product):
    rows=master_items(product)
    return {'sources':[source_row(rows[n]) for n in sorted(rows)]}

def resolve(data,product):
    if type(data.get('slot')) is not int:raise ValueError('请选择母版图位')
    if data.get('uploadedSource'):
        if data['slot']!=-1:raise ValueError('上传图片只能用于独立换色预览')
        source=uploaded_source(data,product)['source']
        if data.get('sourceHash')!=source['sourceHash']:raise ValueError('上传图片内容已变化，请重新载入')
        return selection_key(product,source),source
    item=master_items(product).get(data['slot'])
    if not item:raise ValueError('请先确认整套母版并创建换色方案')
    source=source_row(item)
    if data.get('sourceHash')!=source['sourceHash']:raise ValueError('母版已变化，请重新载入选区')
    key=selection_key(product,source)
    return key,source

def selection_key(product,source):
    return hashlib.sha256(f"{product['id']}:{source['slot']}:{source['sourceHash']}".encode()).hexdigest()

def latest(key,product):
    with closing(connection()) as c:
        row=c.execute('SELECT body FROM selections WHERE key=? AND product=? ORDER BY revision DESC LIMIT 1',(key,product['id'])).fetchone()
    return json.loads(row[0]) if row else None

def selection(data,product):
    key,source=resolve(data,product)
    return {'source':source,'selection':latest(key,product),'renderer':VERSION}


def uploaded_source(data,product):
    url=data.get('uploadedSource')
    if not isinstance(url,str) or not re.fullmatch(r'/uploads/[a-zA-Z0-9_-]+\.(png|jpg|jpeg|webp)',url):raise ValueError('请使用当前账号上传的图片')
    from PIL import ImageOps
    im=ImageOps.exif_transpose(image(url))
    # A canonical PNG makes browser orientation and server mask coordinates agree.
    url=asset(png(im.convert('RGBA') if 'A' in im.getbands() else im.convert('RGB')))
    return {'source':{'slot':-1,'source':url,'uploadedSource':url,'sourceHash':fingerprint(im),'width':im.width,'height':im.height,'productAbsent':False},'skuAssociationAllowed':False}


def automatic_selection(data,product,*,reset_legacy=False):
    """Generate and save a model selection, without requesting human prompts."""
    import garment_auto
    key,source=resolve(data,product);previous=latest(key,product)
    revision=previous['revision'] if previous else 0
    if type(data.get('revision')) is not int or data['revision']!=revision:raise ValueError('选区版本已变化，请重新载入')
    if previous and data.get('replace') is not True:
        return {'source':source,'selection':previous,'renderer':VERSION,'reused':True,'imageGenerationSubmitted':False}
    original=image(source['source']);protected=image(previous['protected']).convert('L') if previous and not reset_legacy else Image.new('L',original.size)
    if source.get('productAbsent'):
        mask=Image.new('L',original.size);protected=Image.new('L',original.size,255)
        receipt={'type':'automatic-product-absent','automatic':True,'humanReviewed':False,'imageGenerationSubmitted':False}
    else:
        mask,receipt=garment_auto.identify(original,protected,ROOT/'garment-embeddings','auto' if source.get('uploadedSource') else garment_auto.category(product))
    encode=lambda im:base64.b64encode(png(im)).decode()
    # Saving re-resolves the source and checks the revision again after inference.
    summary={k:v for k,v in receipt.items() if k!='selection'}
    record=save_selection({**data,'alpha':encode(mask),'protected':encode(protected),'edits':[*((previous or {}).get('edits') or [])[-8:],summary],
        **({'illumination':encode(Image.new('L',original.size)),'adjustments':[]} if reset_legacy else {}),
        'preserveWholeImage':source.get('productAbsent') is True,'confirmed':source.get('productAbsent') is True},product,automatic_provenance=summary)
    return {'source':source,'selection':record,'automatic':True,'userPointsRequired':False,'renderer':VERSION,'imageGenerationSubmitted':False}


def ensure_automatic_selections(product,slots=None,*,refresh_legacy=False):
    import garment_auto
    rows=sources(product)['sources'];wanted=set(slots) if slots is not None else {r['slot'] for r in rows}
    records=[]
    for row in rows:
        if row['slot'] not in wanted:continue
        previous=latest(selection_key(product,row),product)
        legacy=bool(previous and (previous.get('automaticSelection') or {}).get('version')!=garment_auto.VERSION and not previous.get('preserveWholeImage'))
        records.append(automatic_selection({**row,'revision':previous['revision'] if previous else 0,'replace':refresh_legacy and legacy},product,reset_legacy=refresh_legacy and legacy)['selection'])
    return records

def mask_data(value,size):
    if not isinstance(value,str) or len(value)>12*1024*1024:raise ValueError('选区文件过大或无效')
    try:
        raw=base64.b64decode(value,validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.format!='PNG' or im.size!=size:raise ValueError('选区必须为与母版同尺寸的PNG')
            return im.convert('L')
    except (OSError,ValueError) as error:raise ValueError('选区必须为与母版同尺寸的PNG') from error


def select_garment(data,product):
    import garment_workflow
    key,source=resolve(data,product)
    previous=latest(key,product);revision=previous['revision'] if previous else 0
    if type(data.get('revision')) is not int or data['revision']!=revision:raise ValueError('选区版本已变化，请重新载入')
    original=image(source['source']);size=original.size
    alpha=mask_data(data.get('alpha'),size);protected=mask_data(data.get('protected'),size)
    if source.get('productAbsent'):raise ValueError('无商品图位不需要识别衣服')
    result,receipt=garment_workflow.select(original,alpha,protected,data,ROOT/'garment-embeddings')
    # Return an unsaved proposal. Save still applies the immutable revision check.
    return {'alpha':asset(png(result)),'provenance':receipt,'sourceHash':source['sourceHash'],'revision':revision,'saved':False}


def inspect_garment(data,product):
    import garment_workflow
    _,source=resolve(data,product);original=image(source['source'])
    mask,report=garment_workflow.inspect(original,mask_data(data.get('alpha'),original.size),mask_data(data.get('protected'),original.size))
    return {'overlay':asset(png(mask)),**report,'sourceHash':source['sourceHash'],'imageGenerationSubmitted':False}

def save_selection(data,product,*,automatic_provenance=None):
    with LOCK:
        key,source=resolve(data,product)
        previous=latest(key,product);revision=previous['revision'] if previous else 0
        if type(data.get('revision')) is not int or data['revision']!=revision:raise ValueError('选区已被修改，请重新载入后再保存')
        size=(source['width'],source['height'])
        selected=mask_data(data.get('alpha'),size);protected=mask_data(data.get('protected'),size)
        illumination=mask_data(data['illumination'],size) if data.get('illumination') else (image(previous['illumination']).convert('L') if previous and previous.get('illumination') else Image.new('L',size))
        adjustments=previous.get('adjustments',[]) if previous else []
        if 'adjustments' in data:
            if not isinstance(data['adjustments'],list) or len(data['adjustments'])>4:raise ValueError('局部去色边最多4层')
            adjustments=[]
            for layer in data['adjustments']:
                if not isinstance(layer,dict) or type(layer.get('sourceLightness')) is not bool:raise ValueError('局部去色边参数无效')
                if layer.get('color')!='target':color(layer.get('color'))
                adjustments.append({'mask':asset(png(mask_data(layer.get('mask'),size))),'color':layer['color'],'sourceLightness':layer['sourceLightness']})
        alpha=np.asarray(selected).copy();alpha[np.asarray(protected)>0]=0
        preserve=data.get('preserveWholeImage') is True
        if preserve:
            if (source.get('productAbsent') is not True or data.get('confirmed') is not True
                    or np.any(alpha) or not np.all(np.asarray(protected)==255) or adjustments):
                raise ValueError('仅分镜明确无商品的图位可在全图保护后原样复用')
        elif np.count_nonzero(alpha>230)<50:raise ValueError('衣服选区不足，尚未保存')
        edits=data.get('edits',[])
        if not isinstance(edits,list) or len(json.dumps(edits))>65536:raise ValueError('编辑历史过大')
        record={'key':key,'revision':revision+1,**source,'alpha':asset(png(Image.fromarray(alpha))),'protected':asset(png(protected)),
                'illumination':asset(png(illumination)),'adjustments':adjustments,'updated':time.time(),'edits':edits,'humanReviewed':False,'renderer':VERSION,
                'preserveWholeImage':preserve}
        if automatic_provenance is not None:record['automaticSelection']=automatic_provenance
        elif previous and previous.get('automaticSelection'):record['automaticSelection']=previous['automaticSelection']
        with closing(connection()) as c,c:c.execute('INSERT INTO selections VALUES(?,?,?,?)',(key,revision+1,product['id'],json.dumps(record)))
        return record

def color(value):
    if not isinstance(value,str) or not re.fullmatch('#[a-fA-F0-9]{6}',value):raise ValueError('颜色须为#RRGGBB')
    return [int(value[n:n+2],16) for n in (1,3,5)]

def render(data,product):
    key,source=resolve(data,product);record=latest(key,product)
    if not record or data.get('revision')!=record['revision']:raise ValueError('请先保存当前选区，再预览换色')
    for field in ('alpha','protected','illumination'):
        if record.get(field):
            digest=hashlib.sha256(image_provider.local_image(record[field])).hexdigest()
            if record[field].rsplit('/',1)[1]!=digest[:32]+'.png':raise ValueError('已保存选区文件内容变化，请恢复备份')
    for layer in record.get('adjustments',[]):
        digest=hashlib.sha256(image_provider.local_image(layer['mask'])).hexdigest()
        if layer['mask'].rsplit('/',1)[1]!=digest[:32]+'.png':raise ValueError('去色边选区内容变化')
    recipe={'target':data.get('target'),'exposure':data.get('exposure',0),'texture':data.get('texture',1),'pattern':data.get('pattern'),**controls(data)}
    target=color(recipe['target'])
    if any(type(recipe[n]) not in (int,float) or not np.isfinite(recipe[n]) for n in ('exposure','texture')):raise ValueError('纹理或曝光参数无效')
    pattern=recipe['pattern']
    if pattern:
        if not isinstance(pattern,dict) or pattern.get('kind') not in ('dark','light') or type(pattern.get('threshold')) not in (int,float) or not 10<=pattern['threshold']<=90:raise ValueError('波点参数无效')
        pattern={**pattern,'color':color(pattern.get('color'))}
    rid=hashlib.sha256(json.dumps([VERSION,key,record['revision'],recipe],sort_keys=True).encode()).hexdigest()
    with LOCK:
        with closing(connection()) as c:cached=c.execute('SELECT body FROM renders WHERE id=? AND product=?',(rid,product['id'])).fetchone()
        if cached:
            result=json.loads(cached[0]);raw=image_provider.local_image(result['image'])
            if hashlib.sha256(raw).hexdigest()!=result['sha256']:raise ValueError('缓存成图内容已变化')
            return result
        original=image(source['source']);alpha=np.asarray(image(record['alpha']).convert('L'),dtype=float)/255
        protect=image(record['protected']).convert('L')
        illumination=image(record['illumination']).convert('L') if record.get('illumination') else None
        adjustments=[{'mask':image(layer['mask']),'color':target if layer['color']=='target' else color(layer['color']),'sourceLightness':layer['sourceLightness']} for layer in record.get('adjustments',[])]
        if record.get('preserveWholeImage') is True:
            if source.get('productAbsent') is not True or np.any(alpha) or not np.all(np.asarray(protect)==255) or adjustments:
                raise ValueError('原样复用的无商品图位或全图保护已变化')
            result=original.copy()
        else:
            result=render_fabric(original,alpha,protect,target,exposure=recipe['exposure'],texture=recipe['texture'],pattern=pattern,illumination=illumination,adjustments=adjustments,**controls(recipe))
        raw=png(result)
        receipt={'id':rid,'image':asset(raw),'sha256':hashlib.sha256(raw).hexdigest(),'selectionKey':key,'selectionRevision':record['revision'],
                 'sourceHash':source['sourceHash'],'slot':source['slot'],'recipe':recipe,'renderer':VERSION,'time':time.time(),'humanReviewed':False}
        with closing(connection()) as c,c:c.execute('INSERT INTO renders VALUES(?,?,?)',(rid,product['id'],json.dumps(receipt)))
        return receipt

def commit(data,product):
    # Reuse the native repair ledger and real QA, never assign a pass here.
    with LOCK,colour_sets.LOCK:
        with closing(connection()) as c:row=c.execute('SELECT body FROM renders WHERE id=? AND product=?',(data.get('renderId'),product['id'])).fetchone()
        if not row:raise ValueError('当前账号没有这份换色成图')
        receipt=json.loads(row[0]);s=colour_sets.get(data.get('id'))
        if receipt['slot']<0:raise ValueError('上传图片仅用于独立预览，不可替换母版图位或关联SKU')
        if receipt['renderer']!=VERSION:raise ValueError('处理链已更新，请重新预览当前失败图位')
        if s['productId']!=product['id']:raise ValueError('当前账号产品与换色方案不一致')
        wanted=colour_master.selection_id(product)
        if wanted and s['masterId']!=wanted:raise ValueError('当前产品已更换母版，请重新核对换色方案')
        item=next((i for i in s['items'] if i['slot']==receipt['slot']),None)
        if not item or item['status']!='needs_revision':raise ValueError('此入口只修正未通过质检的图位')
        record=latest(receipt['selectionKey'],product)
        if not record or record['revision']!=receipt['selectionRevision']:raise ValueError('选区已更新，请使用最新预览')
        if not item or fingerprint(image(item['sourceUpload']))!=receipt['sourceHash']:raise ValueError('成图与该图位母版不一致')
        raw=image_provider.local_image(receipt['image'])
        if hashlib.sha256(raw).hexdigest()!=receipt['sha256']:raise ValueError('成图内容已变化')
        staged=colour_sets.prepare_local_repair(s,{**data,'slot':receipt['slot'],'image':receipt['image'],'note':data.get('note') or '统一母版选区换色；保留纹理，保护非衣服区域','confirmed':True},product)
        next(i for i in staged['items'] if i['slot']==receipt['slot'])['localCorrection']['pixelRecipe']=receipt
        return colour_sets.save(staged)

def commit_batch(data,product):
    """Stage every receipt first, then atomically commit one colour's repairs."""
    with LOCK,colour_sets.LOCK:
        changes=data.get('changes')
        if not isinstance(changes,list) or not 1<=len(changes)<=12:raise ValueError('修正批次无效')
        s=colour_sets.get(data.get('id'));staged=json.loads(json.dumps(s));receipts=[]
        if s['productId']!=product['id'] or s['status'] in colour_sets.ACTIVE or s['id'] in colour_sets.IN_FLIGHT:raise ValueError('请等待该颜色当前任务停止')
        wanted=colour_master.selection_id(product)
        if wanted and s['masterId']!=wanted:raise ValueError('当前产品已更换母版，请重新核对换色方案')
        slots=set()
        for change in changes:
            if not isinstance(change,dict):raise ValueError('修正批次项必须为对象')
            with closing(connection()) as c:row=c.execute('SELECT body FROM renders WHERE id=? AND product=?',(change.get('renderId'),product['id'])).fetchone()
            if not row:raise ValueError('本账号没有这份成图')
            r=json.loads(row[0]);item=next((i for i in staged['items'] if i['slot']==r['slot']),None)
            if r['renderer']!=VERSION:raise ValueError('处理链已更新，请重新预览当前失败图位')
            if not item or item['slot'] in slots or item['status']!='needs_revision':raise ValueError('仅可批量修正不同的失败图位')
            slots.add(item['slot']);record=latest(r['selectionKey'],product)
            if not record or record['revision']!=r['selectionRevision'] or fingerprint(image(item['sourceUpload']))!=r['sourceHash']:raise ValueError('选区版本或母版已变化')
            if hashlib.sha256(image_provider.local_image(r['image'])).hexdigest()!=r['sha256']:raise ValueError('成图内容已变化')
            staged['status']=s['status']
            colour_sets.prepare_local_repair(staged,{'confirmed':True,'slot':r['slot'],'previousImage':change.get('previousImage'),'image':r['image'],'note':'统一处理链：按原始母版选区换色，保留针织纹理并保护非衣服区域'},product)
            item['localCorrection']['pixelRecipe']=r;receipts.append(r)
        staged.setdefault('localRepairBatches',[]).append({'time':time.time(),'slots':sorted(slots),'imageSubmissionAllowed':False,'humanReviewed':False,'renderer':VERSION})
        return colour_sets.save(staged)

def action(name,data,product):
    if name=='commit' and 'changes' in data:return commit_batch(data,product)
    return {'sources':lambda d,p:sources(p),'uploaded-source':uploaded_source,'auto':automatic_selection,'selection':selection,'segment':select_garment,'inspect':inspect_garment,'save':save_selection,'render':render,'commit':commit}[name](data,product)
