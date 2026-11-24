"""Verified public LinkFox assets. Raw text/config/source is kept byte-for-byte."""
import hashlib,io,json,re,threading
from functools import lru_cache
from pathlib import Path
from PIL import Image,ImageOps
import app_paths

ROOT=Path(__file__).parent/'official-image-templates'
LOCK=threading.RLock()

@lru_cache(maxsize=1)
def manifest():
    value=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    if value.get('layoutCount')!=240 or value.get('verifiedImageCount')!=240 or value.get('repairCount')!=24:
        raise ValueError('官方模板资产未安装完整；不会使用简化蓝图代替')
    return value

def verified_file(relative):
    meta=manifest()['files'].get(relative)
    if not meta:raise ValueError('资源不在官方资产清单内')
    path=(ROOT/relative).resolve()
    if ROOT.resolve() not in path.parents or path.is_symlink():raise ValueError('模板资源路径异常')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('官方模板资源校验失败：'+relative)
    return raw

@lru_cache(maxsize=2)
def entries(kind='layout'):
    if kind not in ('layout','repair'):raise ValueError('模板类型无效')
    return json.loads(verified_file('layouts.json' if kind=='layout' else 'repairs.json'))

def get(identity,kind='layout'):
    if not isinstance(identity,str) or not identity.isdigit():raise ValueError('请选择有效模板ID')
    row=next((r for r in entries(kind) if r['id']==identity),None)
    if not row:raise ValueError('模板ID不在已验证原始库内')
    return row

def catalog(kind='layout'):
    output=[]
    for r in entries(kind):
        a=r.get('asset') or {}
        output.append({'id':r['id'],'name':r['name'],'style':r.get('style'),'width':a.get('width'),'height':a.get('height'),
            'available':bool(a.get('sha256')),'image':'/api/image-templates/image?kind='+kind+'&id='+r['id'] if a.get('sha256') else None,
            'promptLength':sum(map(len,r.get('modelPrompts',[]))) if kind=='layout' else len(r['config'].get('prompt','')),
            'needOptimize':bool(r.get('config',{}).get('needOptimize'))})
    return {'version':manifest()['version'],'kind':kind,'items':output,'count':len(output)}

def image(identity,kind='layout',preview=False):
    r=get(identity,kind);a=r.get('asset') or {}
    if not a.get('sha256'):raise ValueError('该模板配图未通过下载核验')
    raw=verified_file(a['file'])
    if hashlib.sha256(raw).hexdigest()!=a['sha256']:raise ValueError('模板ID与配图哈希不匹配')
    if preview:
        return preview_image(identity,kind)
    return raw,{'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[a['format']]

@lru_cache(maxsize=96)
def preview_image(identity,kind):
    raw,mime=image(identity,kind)
    picture=ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    picture.thumbnail((480,480),Image.Resampling.LANCZOS)
    b=io.BytesIO()
    if 'A' in picture.getbands():picture.save(b,'PNG');return b.getvalue(),'image/png'
    picture.convert('RGB').save(b,'JPEG',quality=86)
    return b.getvalue(),'image/jpeg'

def bind(identity,kind='layout'):
    """Copy a real template to this account's model-input cache, never a blueprint."""
    row=get(identity,kind);raw,_=image(identity,kind)
    from image_engine import asset
    import openai_image_provider as images
    target=app_paths.DATA/'official-template-bindings.json'
    key=kind+':'+identity
    with LOCK:
        cache=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        previous=cache.get(key)
        if previous and previous.get('originalSha256')==row['asset']['sha256']:
            try:
                if asset(previous['url'])[1]==previous['sha256']:return previous
            except (ValueError,OSError):pass
        picture=Image.open(io.BytesIO(raw));picture=ImageOps.exif_transpose(picture)
        resized=max(picture.size)>2400
        if resized:
            picture=picture.convert('RGB');picture.thumbnail((2400,2400),Image.Resampling.LANCZOS)
            b=io.BytesIO();picture.save(b,'PNG');raw=b.getvalue()
        bound=images.cache_image(raw)
        result={**bound,'id':identity,'kind':kind,'style':row.get('style'),'name':row['name'],
                'originalSha256':row['asset']['sha256'],'originalImageKey':row['asset'].get('imageKey'),
                'originalSourceUrl':row['asset']['url'],'referenceResizedOnly':resized,
                'prompt':row['modelPrompts'][0] if kind=='layout' else row['config'].get('prompt',''),
                'promptSha256':row['promptSha256'][0] if kind=='layout' else row['entrySha256']}
        cache[key]=result
        temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(cache,ensure_ascii=False),encoding='utf-8');temporary.replace(target)
        return result

def choose_ids(product,count,deliverable='gallery',requested=None):
    if requested is not None:
        if not isinstance(requested,list) or not 1<=len(requested)<=8 or len(set(requested))!=len(requested):raise ValueError('请选择1–8个不重复官方模板ID')
        for identity in requested:get(identity)
        return [requested[i%len(requested)] for i in range(count)]
    apparel=bool(re.search(r'服装|上衣|裤|裙|shirt|pants|trousers|apparel|dress',str(product),re.I))
    styles=(['A29','A32','M20','A12','M16','A1'] if deliverable=='aplus' else
            ['C50','C39','C10','C11','C37','C14','C29','C47'] if apparel else
            ['L35','L32','L54','L4','L3','L121','L12','L8'])
    rows=entries()
    choices=[]
    for style in styles:
        # Style names are labels, never primary keys. Preserve actual ID order.
        r=next((r for r in rows if r.get('style')==style and r['available']),None)
        if r:choices.append(r['id'])
    if not choices:raise ValueError('没有适用且已核验的官方模板，未回退到简化蓝图')
    return [choices[i%len(choices)] for i in range(count)]

def assignments(product,count,deliverable='gallery',requested=None):
    return [bind(identity) for identity in choose_ids(product,count,deliverable,requested)]

def raw_prompt_section(bound):
    prompt=bound['prompt']
    if hashlib.sha256(prompt.encode('utf-8')).hexdigest()!=bound['promptSha256']:raise ValueError('原始模板提示词内容变化')
    return ('\n[OFFICIAL ORIGINAL TEMPLATE PROMPT id='+bound['id']+' style='+str(bound.get('style'))+']\n'
            +prompt+'\n[/OFFICIAL ORIGINAL TEMPLATE PROMPT]\n'
            'The full original prompt above controls composition and typography. Reference image 2 is its real original artwork, '
            'not a schematic. Adapt only the subject and verified copy to the current product. Never copy its brand, '
            'borrowed product features, measurements, badges or claims. Current product truth and explicit user no-text instructions take priority.')

def colour_resources():
    config=json.loads(verified_file('colour/config.json'))
    shaders={name:verified_file('colour/'+name).decode('utf-8') for name in
             ('originOut.fs','adjustMask.fs','gaussian.fs','colorChange.fs','lightness.fs','contrast.fs','vibrance.fs','colorBalance.fs','colorCurves.fs','hslAdjust.fs')}
    return {'config':config,'shaders':shaders,'version':manifest()['version'],'originalFiles':11,
            'sourceHashes':{k:v['sha256'] for k,v in manifest()['files'].items() if k.startswith('colour/')}}


def canonical_colour_source(url):
    """One decoded PNG truth avoids browser/Pillow JPEG rounding differences."""
    from image_engine import asset,cache
    original,digest=asset(url)
    normalized=cache(original.convert('RGBA'))
    return {'source':normalized,'original':url,'originalSha256':digest,
            'normalization':'exif_transpose_to_lossless_rgba_png','width':original.width,'height':original.height}

def expert_prompt(identity,brief,images,size='',*,objects=None,need_optimize=None,
                  image_capabilities=None,preservation=None):
    """Compile typed input with an optional independent Codex text optimizer.

    Original policies remain immutable audit metadata; no private server
    expanded prompt is claimed. Positional historical calls stay supported.
    """
    from repair_prompt_pipeline import compile_repair
    row=get(identity,'repair')
    return compile_repair(row,brief,images,size,objects=objects,
        need_optimize=need_optimize,image_capabilities=image_capabilities,
        preservation=preservation)
