"""Reference-image generation through a loopback ComfyUI SD img2img workflow."""
import base64
import io
import json
import os
import re
import secrets
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from PIL import Image, ImageOps

import app_paths
import openai_image_provider as raster


PROVIDER = 'ComfyUI local'
DEFAULT_BASE = 'http://127.0.0.1:8188'
MAX_IMAGE = 25 * 1024 * 1024
CONFIG = app_paths.DATA / 'comfyui-image.json'


class Unavailable(ValueError):
    """Preflight failed before any local generation request was submitted."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def endpoint(value):
    match = re.fullmatch(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/?', value or '') if isinstance(value, str) else None
    if not match or int(match[1]) > 65535:
        raise Unavailable('ComfyUI 只接受本机 HTTP 地址，例如 http://127.0.0.1:8188')
    return f'http://127.0.0.1:{match[1]}'


def config():
    if not CONFIG.is_file():
        return {'baseUrl': DEFAULT_BASE, 'checkpoint': '', 'denoise': .35}
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def public():
    settings = config()
    checkpoint = settings.get('checkpoint') or ''
    return {**settings, 'provider': PROVIDER, 'workflow': 'sd-img2img-v1',
            'models': [checkpoint] if checkpoint else [], 'maxReferences': 1}


def configure(data):
    if app_paths.WORKER_USER:
        raise Unavailable('本地工作流仅在本机工作台管理员的数据空间启用')
    base = endpoint(data.get('baseUrl', DEFAULT_BASE))
    model = data.get('checkpoint')
    denoise = data.get('denoise', .35)
    if (not isinstance(model, str) or not 1 <= len(model) <= 200 or not model.endswith('.safetensors')
            or any(ch in model for ch in '\\/:\r\n\x00') or type(denoise) not in (int, float)
            or not .10 <= denoise <= .75):
        raise Unavailable('请填写 ComfyUI 中的 SD Checkpoint safetensors 文件名，重绘强度范围 0.10–0.75')
    info = probe(base)
    if model not in info['models']:
        raise Unavailable('ComfyUI 未列出所选 Checkpoint，请检查 models/checkpoints')
    target = CONFIG.with_name('comfyui-image-'+uuid.uuid4().hex+'.tmp')
    target.write_text(json.dumps({'baseUrl': base, 'checkpoint': model, 'denoise': denoise}, ensure_ascii=False), encoding='utf-8')
    os.replace(target, CONFIG)
    return public()


def request(base, path, body=None, *, content_type='application/json', limit=4*1024*1024):
    headers = {'Content-Type': content_type} if body is not None else {}
    req = Request(endpoint(base)+path, data=body, headers=headers)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=25) as response:
            raw = response.read(limit+1)
    except HTTPError as error:
        raise ValueError(f'ComfyUI 请求失败（HTTP {error.code}）') from None
    except (URLError, TimeoutError):
        raise ValueError('ComfyUI 连接未确认，请检查本机服务') from None
    if len(raw) > limit:
        raise ValueError('ComfyUI 返回内容超过大小限制')
    return raw


def json_request(base, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    result = json.loads(request(base, path, body))
    if not isinstance(result, dict):
        raise ValueError('ComfyUI 返回格式无效')
    return result


def probe(base):
    try:
        stats = json_request(base, '/system_stats')
        node = json_request(base, '/object_info/CheckpointLoaderSimple')['CheckpointLoaderSimple']
        models = node['input']['required']['ckpt_name'][0]
        devices = [{key: device.get(key) for key in ('name', 'type', 'vram_total', 'vram_free')}
                   for device in stats.get('devices', []) if isinstance(device, dict)]
        if not isinstance(models, list) or not devices:
            raise ValueError()
        return {'ok': True, 'models': [name for name in models if isinstance(name, str) and name.endswith('.safetensors')],
                'devices': devices, 'message': 'ComfyUI 已连接。设备和模型来自本机服务，尚未提交生图。'}
    except (ValueError, TypeError, KeyError, IndexError):
        raise Unavailable('本机 ComfyUI 或 Checkpoint 列表不可用，请启动服务并核对模型安装') from None


def specification(data):
    if app_paths.WORKER_USER:
        raise Unavailable('本地工作流仅在本机工作台管理员的数据空间启用')
    spec = public()
    if data.get('model') not in spec['models']:
        raise Unavailable('请先配置本机 SD Checkpoint')
    if len(data['references']) != 1:
        raise Unavailable('当前本地 SD 图生图工作流只接受一张主体参考图。多参考任务请选择云端接口。')
    if spec['checkpoint'] not in probe(spec['baseUrl'])['models']:
        raise Unavailable('本机 ComfyUI 中已找不到所选 Checkpoint')
    try:
        output = raster.canvas(data.get('size', '1:1'), data.get('resolution', '1K'))
    except ValueError as error:
        raise Unavailable(str(error)) from None
    width, height = map(int, output.split('x'))
    scale = 768/max(width, height)
    spec['canvas'] = [width, height]
    spec['samplingCanvas'] = [max(64, round(n*scale/8)*8) for n in (width, height)]
    return spec


def upload(base, data_url):
    try:
        raw = base64.b64decode(data_url.partition(',')[2], validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.width * im.height > 40_000_000 or getattr(im, 'n_frames', 1) != 1:
                raise ValueError()
            image = ImageOps.exif_transpose(im).convert('RGB')
            image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            image.save(stream, 'PNG')
    except (ValueError, OSError, Image.DecompressionBombError):
        raise ValueError('本地生图参考图无法解码或尺寸超限') from None
    filename = 'studio-'+uuid.uuid4().hex+'.png'
    boundary = uuid.uuid4().hex
    head = f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'
    tail = f'\r\n--{boundary}--\r\n'
    answer = json.loads(request(base, '/upload/image', head.encode()+stream.getvalue()+tail.encode(),
                                content_type='multipart/form-data; boundary='+boundary))
    if answer.get('name') != filename or answer.get('type') != 'input' or answer.get('subfolder'):
        raise ValueError('ComfyUI 未返回该参考图的上传回执')
    return filename


def workflow(spec, reference, prompt, prefix):
    width, height = spec['samplingCanvas']
    output_width, output_height = spec['canvas']
    def node(kind, **inputs):
        return {'class_type': kind, 'inputs': inputs}
    return {
        '1': node('CheckpointLoaderSimple', ckpt_name=spec['checkpoint']),
        '2': node('LoadImage', image=reference),
        '3': node('ImageScale', image=['2', 0], upscale_method='lanczos', width=width, height=height, crop='center'),
        '4': node('VAEEncode', pixels=['3', 0], vae=['1', 2]),
        '5': node('CLIPTextEncode', text=prompt, clip=['1', 1]),
        '6': node('CLIPTextEncode', text='incorrect shape, changed product color, extra product parts, watermark, unreadable text', clip=['1', 1]),
        '7': node('KSampler', model=['1', 0], positive=['5', 0], negative=['6', 0], latent_image=['4', 0],
                  seed=secrets.randbits(32), steps=16, cfg=6, sampler_name='euler', scheduler='normal', denoise=spec['denoise']),
        '8': node('VAEDecode', samples=['7', 0], vae=['1', 2]),
        '9': node('ImageScale', image=['8', 0], upscale_method='lanczos', width=output_width, height=output_height, crop='disabled'),
        '10': node('SaveImage', images=['9', 0], filename_prefix=prefix),
    }


def submit(data, image, spec, requested_id):
    base = spec['baseUrl']
    reference = upload(base, image)
    prefix = 'studio-'+uuid.uuid4().hex
    payload = {'prompt': workflow(spec, reference, data['prompt'], prefix), 'client_id': prefix,
               'prompt_id': requested_id}
    result = json_request(base, '/prompt', payload)
    task = result.get('prompt_id')
    if not isinstance(task, str) or not re.fullmatch(r'[a-f0-9-]{36}', task):
        raise ValueError('ComfyUI 未返回有效任务号，先查询本机队列')
    return {'id': 'comfy-'+task, 'externalId': task, 'productId': data['productId'], 'slot': data['slot'],
            'model': data['model'], 'provider': PROVIDER, 'providerEndpoint': base, 'prompt': data['prompt'],
            'references': data['references'], 'status': 'submitted', 'progress': 0, 'images': [],
            'canvas': spec['canvas'], 'samplingCanvas': spec['samplingCanvas'], 'outputPrefix': prefix,
            'workflow': spec['workflow'], 'submittedAt': time.time()}


def poll(job):
    task = job['externalId']
    if not re.fullmatch(r'[a-f0-9-]{36}', task):
        raise ValueError('本地生图任务号无效')
    result = json_request(job['providerEndpoint'], '/history/'+task).get(task)
    updated = {**job, 'lastPolled': time.time()}
    if not result:
        if time.time()-job['submittedAt'] > 1200:
            updated.update(status='result_unknown', error='本机任务结果未确认，请核对原 ComfyUI 队列')
        return updated
    status = result.get('status', {})
    if status.get('status_str') == 'error':
        return {**updated, 'status': 'failed', 'error': 'ComfyUI 工作流执行失败，请查看该任务日志'}
    images = result.get('outputs', {}).get('10', {}).get('images', [])
    if not images and not status.get('completed'):
        return updated
    if len(images) != 1:
        raise ValueError('ComfyUI 没有返回一个可核对的输出文件')
    output = images[0]
    filename = output.get('filename', '')
    if (output.get('type') != 'output' or output.get('subfolder')
            or not re.fullmatch(re.escape(job['outputPrefix'])+r'_[0-9]+_\.png', filename)):
        raise ValueError('ComfyUI 输出文件与原任务不一致')
    raw = request(job['providerEndpoint'], '/view?'+urlencode({'filename': filename, 'type': 'output'}), limit=MAX_IMAGE)
    with Image.open(io.BytesIO(raw)) as picture:
        if list(picture.size) != job['canvas'] or getattr(picture, 'n_frames', 1) != 1:
            raise ValueError('ComfyUI 输出尺寸或帧数与分镜任务不一致')
    asset = raster.cache_image(raw)
    return {**updated, 'status': 'completed', 'progress': 100, 'images': [asset['url']],
            'resultCache': {'status': 'saved', 'assets': [asset], 'savedAt': time.time()}}
