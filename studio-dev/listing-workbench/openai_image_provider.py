"""Configurable Images transport, following IvyeaOps assistant/listing contracts.

Keep credentials account-local; paid retries are never implicit. Upstream source
and deliberate deviations are documented in docs/IVYEA-IMAGE-AUDIT-20261104.md.
"""
import base64
import hashlib
import io
import json
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request
from urllib.request import ProxyHandler, build_opener

import app_paths
import aigocode_provider as transport
import secrets_store
import image_proxy_diagnostics
import image_budget

CONFIG = app_paths.DATA / 'openai-image.json'
PROVIDER = 'OpenAI-compatible'
DEFAULT_BASE = 'https://api.openai.com/v1'
CODEX_TOOLS_BASE = 'http://127.0.0.1:8787/v1'


def validate_base(value):
    # Explicitly supported local service; never relax public URL validation for
    # other ports, LAN addresses, credentialed URLs, or downloaded image URLs.
    if isinstance(value, str) and value.strip().rstrip('/') == CODEX_TOOLS_BASE:
        return CODEX_TOOLS_BASE
    return transport._validate_url(value)


def config():
    try:
        value = json.loads(CONFIG.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def public():
    c = config()
    model = c.get('model', 'gpt-image-2')
    output_size = None
    if c.get('base_url') == CODEX_TOOLS_BASE:
        output_size = image_budget.configuration().get('codex_tools', {}).get('output_size')
        if output_size not in (None, '1600x1600'):
            raise ValueError('Codex Tools 出图尺寸配置无效')
    return {'provider': PROVIDER, 'hasKey': bool(secrets_store.load('openai_image')),
            'baseUrl': c.get('base_url', DEFAULT_BASE), 'model': model,
            'models': list(dict.fromkeys([model, *c.get('models', [])])),
            'protocol': c.get('protocol', 'edits'), 'quality': c.get('quality', 'medium'),
            'referenceSupported': True, 'outputSize': output_size}


def configure(data):
    c = config()
    key = transport.key_input(data)
    if data.get('base_url'):
        c['base_url'] = validate_base(data['base_url'])
    model = data.get('model', c.get('model', 'gpt-image-2'))
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,160}', model):
        raise ValueError('请填写接口实际提供的图片模型 ID')
    c['model'] = model
    c['protocol'] = data.get('protocol', c.get('protocol', 'edits'))
    c['quality'] = data.get('quality', c.get('quality', 'medium'))
    if c['protocol'] not in ('edits', 'reference_json'):
        raise ValueError('参考图协议必须是 edits 或 reference_json')
    if c['quality'] not in ('low', 'medium', 'high', 'auto'):
        raise ValueError('图片质量必须是 low、medium、high 或 auto')
    c.setdefault('base_url', DEFAULT_BASE)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(c), encoding='utf-8')
    temporary.replace(CONFIG)
    if data.get('clearKey'):
        secrets_store.save('openai_image', '')
    elif key:
        secrets_store.save('openai_image', key)
    return public()


def request_json(endpoint, body=None, content_type='application/json', key=None):
    key = key or secrets_store.load('openai_image')
    if not key:
        raise ValueError('请在当前账号配置 OpenAI 兼容图片接口密钥')
    request = Request(endpoint, data=body,
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': content_type})
    try:
        local = endpoint.startswith(CODEX_TOOLS_BASE + '/')
        opener = build_opener(ProxyHandler({}), transport._NoRedirect()).open if local else transport._open
        with opener(request, timeout=280 if body is not None else 25) as response:
            payload = response.read(48 * 1024 * 1024 + 1)
        if len(payload) > 48 * 1024 * 1024:
            raise ValueError('图片接口响应过大；请核对原任务，未重复提交')
        result = json.loads(payload)
    except HTTPError as error:
        if local:
            raise image_proxy_diagnostics.ProxyHTTPError(image_proxy_diagnostics.capture(error,endpoint,key)) from None
        # Never echo upstream bodies: some proxies include credentials in errors.
        raise ValueError(f'图片接口 HTTP {error.code}；未自动重试，请核对权限及原任务') from None
    except (URLError, TimeoutError):
        raise ValueError('图片接口连接失败或超时；原提交待核对，未自动重试') from None
    except (ValueError, UnicodeError):
        raise ValueError('图片接口响应无法解析；请核对原任务，未自动重试') from None
    if not isinstance(result, dict) or result.get('error'):
        raise ValueError('图片接口未返回有效结果；请核对原任务，未自动重试')
    return result


def test_key(data):
    key = transport.key_input(data) or secrets_store.load('openai_image')
    root = validate_base(config().get('base_url', DEFAULT_BASE))
    result = request_json(root + '/models', key=key)
    if not isinstance(result.get('data'), list):
        raise ValueError('接口没有返回有效模型列表')
    models = sorted({x['id'] for x in result['data'] if isinstance(x, dict)
                     and isinstance(x.get('id'), str) and 0 < len(x['id']) <= 160})
    return {'ok': True, 'models': models, 'supportedModels': models,
            'message': '已读取模型列表；未生图，尚未验证参考图编辑权限、费用或模型可用性。'}


def canvas(ratio, resolution):
    sizes = {
        '1600': {'1:1':'1600x1600'},
        '1K': {'1:1':'1024x1024', '4:5':'1024x1280', '3:4':'1008x1344', '16:9':'1536x864'},
        '2K': {'1:1':'2048x2048', '4:5':'2048x2560', '3:4':'1920x2560', '16:9':'2560x1440'},
        '4K': {'16:9':'3840x2160'},
    }
    try:
        return sizes[resolution][ratio]
    except KeyError:
        raise ValueError('该比例不支持所选分辨率；4K仅支持16:9，未静默缩小画布') from None


def specification(data):
    c = public()
    if data.get('model') not in c['models']:
        raise ValueError('所选模型不属于当前 OpenAI 兼容接口配置')
    aplus=data.get('deliveryCanvas')=='1464x600' and data.get('size')=='16:9'
    codex_gallery=c['baseUrl']==CODEX_TOOLS_BASE and data.get('size')=='1:1'
    if (aplus or codex_gallery) and c['protocol']=='edits' and data.get('references')==[]:
        c={**c,'protocol':'generations'}
    if c.get('outputSize'):
        if aplus:
            # The A+ workflow performs its own cover crop and quality checks.
            return {**c,'providerEndpoint':validate_base(c['baseUrl']),
                    'canvas':'1464x600','outputSize':None}
        if data.get('size', '1:1') != '1:1':
            raise ValueError('当前 Codex Tools 出图尺寸为1600×1600，请选择1:1比例')
        pixels = c['outputSize']
    else:
        pixels = canvas(data.get('size', '1:1'), data.get('resolution', '1K'))
    return {**c, 'providerEndpoint': validate_base(c['baseUrl']), 'canvas': pixels}


def submission_credentials(spec):
    """Capture credentials immediately before reservation, without persisting keys."""
    key=secrets_store.load('openai_image')
    if not key:raise ValueError('请先在当前账号配置图片接口密钥；未预留或提交生成')
    if validate_base(config().get('base_url',DEFAULT_BASE))!=spec['providerEndpoint']:
        raise ValueError('图片接口配置已改变，请重新读取设置；未提交生成')
    return key


def cache_image(raw):
    from PIL import Image
    if not raw or len(raw) > 32 * 1024 * 1024:
        raise ValueError('返回图片为空或过大')
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format not in ('PNG', 'JPEG', 'WEBP') or picture.width * picture.height > 40_000_000:
                raise ValueError()
            picture.load()
            width, height = picture.size
            extension = {'PNG':'.png', 'JPEG':'.jpg', 'WEBP':'.webp'}[picture.format]
    except Exception:
        raise ValueError('返回内容不是有效 PNG/JPEG/WebP 图片；未标记完成') from None
    path = app_paths.DATA / 'uploads' / (uuid.uuid4().hex + extension)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {'url':'/uploads/' + path.name, 'sha256':hashlib.sha256(raw).hexdigest(),
            'width':width, 'height':height, 'bytes':len(raw)}


def remote_image(url):
    # Download without API credentials; never follow redirects to private hosts.
    if not isinstance(url, str):
        raise ValueError('图片 URL 无效')
    parts = urlsplit(url)
    # Signed image URLs may have a query; validate their origin separately.
    transport._validate_url(parts._replace(path='', query='', fragment='').geturl())
    safe = url
    with transport._open(Request(safe), timeout=60) as response:
        raw = response.read(32 * 1024 * 1024 + 1)
    return cache_image(raw)


def finalize_asset(asset, output_size):
    """Keep provider pixels and record local sizing separately from generation."""
    if not output_size:
        return asset
    if output_size != '1600x1600':
        raise ValueError('不支持的成图尺寸')
    if (asset['width'], asset['height']) == (1600, 1600):
        return asset
    from PIL import Image, ImageOps
    with Image.open(app_paths.DATA / asset['url'].lstrip('/')) as original:
        original = ImageOps.exif_transpose(original)
        alpha = 'A' in original.getbands() or 'transparency' in original.info
        original = original.convert('RGBA' if alpha else 'RGB')
        scaled = ImageOps.contain(original, (1600, 1600), Image.Resampling.LANCZOS)
        picture = Image.new(original.mode, (1600, 1600), (0, 0, 0, 0) if alpha else 'white')
        picture.paste(scaled, ((1600-scaled.width)//2, (1600-scaled.height)//2))
        buffer = io.BytesIO()
        picture.save(buffer, format='PNG')
    return {**cache_image(buffer.getvalue()), 'sourceAsset': asset,
            'processing': {'method':'contain_lanczos', 'targetSize':output_size,
                           'sourceWidth':asset['width'], 'sourceHeight':asset['height'],
                           'upscaled':scaled.width > asset['width'] or scaled.height > asset['height']}}


def parse_result(payload, output_size=None):
    rows = payload.get('data')
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise ValueError('接口没有返回图片或任务号；请核对原提交')
    item = rows[0]
    if item.get('task_id'):
        task = item['task_id']
        if not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', task):
            raise ValueError('接口返回的任务号格式无效')
        return {'status':'submitted', 'externalId':task, 'images':[]}
    if item.get('b64_json'):
        try:
            raw = base64.b64decode(item['b64_json'], validate=True)
        except (ValueError, TypeError):
            raise ValueError('接口返回的图片编码无效') from None
        asset = cache_image(raw)
    elif isinstance(item.get('url'), str):
        asset = remote_image(item['url'])
    else:
        raise ValueError('接口未返回有效 task_id、b64_json 或图片 URL')
    asset = finalize_asset(asset, output_size)
    return {'status':'completed', 'progress':100, 'images':[asset['url']],
            'assets':[asset], 'usage':payload.get('usage')}


def wide_reference(ref):
    """Keep source pixels in a wide carrier so edits do not inherit a portrait canvas."""
    from PIL import Image, ImageOps
    raw=base64.b64decode(ref.split(',',1)[1],validate=True)
    with Image.open(io.BytesIO(raw)) as source:
        source=ImageOps.exif_transpose(source).convert('RGB')
        if abs(source.width/source.height-1464/600)<0.03:
            return ref
        fitted=ImageOps.contain(source,(1464,600),Image.Resampling.LANCZOS)
        carrier=Image.new('RGB',(1464,600),'#F3F0EA')
        carrier.paste(fitted,((1464-fitted.width)//2,(600-fitted.height)//2))
        output=io.BytesIO()
        carrier.save(output,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')


def submit(data, refs, spec, on_response=None, api_key=None):
    root, model = spec['providerEndpoint'], data['model']
    if data.get('deliveryCanvas')=='1464x600':
        refs=[wide_reference(ref) for ref in refs]
    submitted_hashes=[hashlib.sha256(base64.b64decode(ref.split(',',1)[1],validate=True)).hexdigest()
                      for ref in refs] if spec['protocol']=='edits' else []
    if spec['protocol'] == 'edits':
        body, mime = transport._multipart(model, data['prompt'], spec['canvas'], spec['quality'], refs,
                                          image_field='image[]' if len(refs) > 1 else 'image')
        path = '/images/edits'
    else:
        fields={'model':model, 'prompt':data['prompt'], 'size':spec['canvas'],
                'quality':spec['quality'], 'n':1}
        if refs:
            fields['image_urls']=refs
        body=json.dumps(fields).encode()
        mime, path = 'application/json', '/images/generations'
    # No optional-parameter retry: protocol selection must be explicit.
    api_key=api_key or submission_credentials(spec)
    payload = request_json(root + path, body, mime, key=api_key)
    seed = {'id':uuid.uuid4().hex, 'provider':PROVIDER, 'productId':data['productId'],
            'slot':data['slot'], 'model':model, 'prompt':data['prompt'],
            'references':data['references'], 'providerEndpoint':root,
            'protocol':spec['protocol'], 'quality':spec['quality'], 'canvas':spec['canvas'],
            'submittedReferenceSha256':submitted_hashes,
            'outputSize':spec.get('outputSize'),
            'credentialFingerprint':hashlib.sha256(api_key.encode()).hexdigest()}
    receipt_id = uuid.uuid4().hex
    directory = app_paths.DATA / 'image-responses'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (receipt_id + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'job':seed, 'payload':payload}), encoding='utf-8')
    temporary.replace(path)
    if on_response:
        on_response(receipt_id)
    return {**seed, 'responseReceipt':receipt_id, **parse_result(payload, seed.get('outputSize'))}


def recover(receipt_id, product_id, slot):
    if not isinstance(receipt_id, str) or not re.fullmatch(r'[a-f0-9]{32}', receipt_id):
        raise ValueError('图片响应回执无效')
    value = json.loads((app_paths.DATA / 'image-responses' / (receipt_id + '.json')).read_text(encoding='utf-8'))
    seed = value['job']
    if seed.get('productId') != product_id or seed.get('slot') != slot:
        raise ValueError('图片响应回执不属于当前产品图位')
    return {**seed, 'responseReceipt':receipt_id, **parse_result(value['payload'], seed.get('outputSize'))}


def poll(job):
    # Pin the original endpoint: switching the active provider must not reroute jobs.
    root = validate_base(job['providerEndpoint'])
    key=secrets_store.load('openai_image')
    current_root=validate_base(config().get('base_url',DEFAULT_BASE))
    fingerprint=hashlib.sha256(key.encode()).hexdigest() if key else ''
    if current_root!=root or (job.get('credentialFingerprint') and job['credentialFingerprint']!=fingerprint):
        raise ValueError('原任务的接口凭据配置已改变；请恢复原地址和密钥后查询，未向原地址发送新密钥或重提生成')
    payload = request_json(root + '/tasks/' + quote(job['externalId'], safe=''),key=key)
    data = payload.get('data')
    if not isinstance(data, dict):
        raise ValueError('原任务查询响应无效；未重新提交')
    status = data.get('status')
    if status == 'completed':
        images = data.get('result', {}).get('images', [])
        if not images or not isinstance(images[0], dict):
            raise ValueError('任务完成但无图片，保留原任务等待核对')
        url = images[0].get('url')
        if isinstance(url, list):
            url = url[0] if url else None
        return {**job, **parse_result({'data':[{'url':url}]}, job.get('outputSize')), 'lastPolled':__import__('time').time()}
    if status not in ('submitted','pending','processing','failed','cancelled'):
        raise ValueError('原任务状态未知；未重新提交')
    return {**job, 'status':status, 'progress':data.get('progress', 0),
            'error':'上游图片任务失败，请核对账单' if status == 'failed' else '',
            'lastPolled':__import__('time').time()}
