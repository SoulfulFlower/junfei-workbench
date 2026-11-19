"""Per-account OpenAI-compatible image relay settings and image adapter."""
import app_paths
import base64
import ipaddress
import json
import socket
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
import secrets_store

BASE_URL = 'https://api.aigocode.dev/v1'
MODELS = ['gpt-image-2.5-flare', 'gpt-image-2.5-sunburst']
CONFIG = app_paths.DATA / 'aigocode-image.json'

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request, timeout):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _config():
    try:
        value = json.loads(CONFIG.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _validate_url(value):
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError('图片接口 URL 无效')
    value = value.strip().rstrip('/')
    parts = urlsplit(value)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('接口 URL 必须是 HTTPS 地址，不可带账号、密码、查询参数或片段')
    try:
        addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)}
        if any(not addr.is_global for addr in addresses):
            raise ValueError('接口 URL 不可指向本机或内网地址')
    except OSError:
        raise ValueError('接口域名无法解析') from None
    return value


def base_url():
    return _validate_url(_config().get('base_url') or BASE_URL)


def selected_model():
    return str(_config().get('model') or MODELS[0])


def public():
    config = _config()
    return {'provider': 'AIGoCode', 'hasKey': bool(secrets_store.load('aigocode')),
            'baseUrl': config.get('base_url') or BASE_URL, 'model': selected_model(),
            'models': config.get('models', MODELS), 'referenceSupported': True, 'active': config.get('active') is True,
            'message': '支持 OpenAI 兼容 Images API；参考图调用 /images/edits，要求所选模型和中转站支持。'}


def key_input(data):
    key = data.get('api_key', '')
    if not isinstance(key, str) or len(key) > 2000 or any(c in key for c in '\r\n'):
        raise ValueError('图片 API Key 格式不正确')
    return key.strip()


def configure(data):
    key = key_input(data)
    config = _config()
    if data.get('base_url'):
        config['base_url'] = _validate_url(data['base_url'])
    model = data.get('model')
    if model is not None:
        if not isinstance(model, str) or not model.strip() or len(model) > 160 or any(c in model for c in '\r\n'):
            raise ValueError('图片模型名称无效')
        config['model'] = model.strip()
    if isinstance(data.get('models'), list):
        config['models'] = sorted({x for x in data['models'] if isinstance(x, str) and 0 < len(x) <= 160})[:500]
    if data.get('activate') is True:
        config['active'] = True
    config.setdefault('base_url', BASE_URL)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG.with_suffix('.tmp')
    temp.write_text(json.dumps(config), encoding='utf-8')
    temp.replace(CONFIG)
    if data.get('clearKey'):
        secrets_store.save('aigocode', '')
    elif key:
        secrets_store.save('aigocode', key)
    return public()


def test_key(data):
    key = key_input(data) or secrets_store.load('aigocode')
    if not key:
        raise ValueError('请先输入或保存图片 API Key')
    request = Request(base_url() + '/models', headers={'Authorization': 'Bearer ' + key})
    try:
        with _open(request, timeout=25) as response:
            result = json.loads(response.read(4 * 1024 * 1024))
        if not isinstance(result, dict) or not isinstance(result.get('data'), list) or 'error' in result:
            raise ValueError('中转站返回的模型列表格式不正确')
        models = sorted({m['id'] for m in result['data'] if isinstance(m, dict) and isinstance(m.get('id'), str) and 0 < len(m['id']) <= 160})
    except HTTPError as error:
        raise ValueError(f'图片中转站返回 HTTP {error.code}，请检查密钥分组、权限或服务状态') from None
    except (URLError, TimeoutError):
        raise ValueError('图片中转站连接失败或超时，请检查 URL 后重试') from None
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError('图片中转站模型列表无法解析') from None
    return {'ok': True, 'models': models, 'supportedModels': models,
            'message': '✓ 密钥连接成功；模型列表已读取，实际可用范围由中转站分组决定。'}


def _multipart(model, prompt, size, quality, refs, image_field='image'):
    boundary = '----Junfei' + uuid.uuid4().hex
    chunks = []
    def field(name, value, filename=None, mime=None):
        head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if filename:
            head += f'; filename="{filename}"\r\nContent-Type: {mime}'
        chunks.extend([head.encode() + b'\r\n\r\n', value if isinstance(value, bytes) else str(value).encode(), b'\r\n'])
    field('model', model); field('prompt', prompt); field('size', size); field('quality', quality); field('n', '1'); field('output_format', 'png')
    for i, ref in enumerate(refs):
        mime, encoded = ref[5:].split(';base64,', 1)
        raw = base64.b64decode(encoded, validate=True)
        ext = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(mime)
        if not ext:
            raise ValueError('图片接口仅支持 PNG/JPEG/WebP 参考图')
        field(image_field, raw, f'reference-{i+1}.{ext}', mime)
    chunks.append(f'--{boundary}--\r\n'.encode())
    return b''.join(chunks), 'multipart/form-data; boundary=' + boundary


def generate(model, prompt, size, quality, refs):
    key = secrets_store.load('aigocode')
    if not key:
        raise ValueError('请先在模型设置中保存图片中转站 Key')
    root = base_url()
    if refs:
        body, content_type = _multipart(model, prompt, size, quality, refs)
        endpoint = root + '/images/edits'
    else:
        body = json.dumps({'model': model, 'prompt': prompt, 'size': size, 'quality': quality, 'n': 1, 'output_format': 'png'}).encode()
        content_type = 'application/json'
        endpoint = root + '/images/generations'
    request = Request(endpoint, data=body, headers={'Authorization': 'Bearer ' + key, 'Content-Type': content_type})
    try:
        with _open(request, timeout=240) as response:
            result = json.loads(response.read(45 * 1024 * 1024))
    except HTTPError as error:
        try:
            detail = error.read(4000).decode('utf-8', 'replace')
            message = json.loads(detail).get('error', {}).get('message', '')
        except (ValueError, AttributeError):
            message = ''
        raise ValueError(f'图片中转站返回 HTTP {error.code}：{str(message)[:500] or "请检查模型权限、参考图编辑能力与分组配置"}；没有自动重试') from None
    except (URLError, TimeoutError):
        raise ValueError('图片生成请求超时；请先在中转站后台核对任务，避免重复提交计费') from None
    try:
        encoded = result['data'][0]['b64_json']
        image = base64.b64decode(encoded, validate=True)
        if not image.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'RIFF')):
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError('中转站未返回有效 b64_json 图片；请确认模型支持 OpenAI Images API') from None
    ext = '.png' if image.startswith(b'\x89PNG') else '.jpg' if image.startswith(b'\xff\xd8\xff') else '.webp'
    path = app_paths.DATA / 'uploads' / (uuid.uuid4().hex + ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)
    return '/uploads/' + path.name

