"""Export an explicit ordered selection of this account's completed image jobs.

Selections are review drafts. Neither job completion nor selecting an image is
human approval. Source bytes are fetched once, validated, and cached by content.
"""
import hashlib
import io
import ipaddress
import json
import socket
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from PIL import Image
import image_provider
import image_budget

MAX_BYTES = 25 * 1024 * 1024
ERP_MAX_BYTES = 5 * 1024 * 1024


def prepare_delivery(raw):
    """Preserve small originals; derive a traceable JPEG without resizing large ones."""
    source = inspect(raw)
    if len(raw) < ERP_MAX_BYTES:
        return raw, source
    with Image.open(io.BytesIO(raw)) as im:
        # Explicit white compositing avoids black backgrounds on transparent PNGs.
        rgba = im.convert('RGBA')
        rgb = Image.new('RGB', im.size, 'white')
        rgb.paste(rgba, mask=rgba.getchannel('A'))
        for quality in (95, 92, 90, 85):
            buffer = io.BytesIO()
            rgb.save(buffer, format='JPEG', quality=quality, subsampling=0,
                     optimize=False, progressive=False)
            delivered = buffer.getvalue()
            if len(delivered) < ERP_MAX_BYTES:
                return delivered, {**inspect(delivered), 'sourceSha256':source['sha256'],
                    'sourceMime':source['mime'], 'sourceBytes':len(raw),
                    'deliveryBytes':len(delivered), 'transformation':{
                        'version':1, 'operation':'jpeg_white_background_no_resize',
                        'quality':quality, 'subsampling':0}}
    raise ValueError('图片保持原尺寸压缩后仍超过钧飞5MB限制，请单独处理')


def download(url):
    if isinstance(url, str) and url.startswith('/uploads/'):
        return image_provider.local_image(url)
    u = urlsplit(url)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise ValueError('生成图片地址不安全')
    addresses = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('生成图片地址不得指向内部网络')
    with build_opener(image_provider.NoImageRedirect()).open(Request(url, headers={'User-Agent':'JunfeiListing/1.0'}), timeout=40) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('生成图片超过25MB')
    return raw


def inspect(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('生成图片超过25MB')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ('PNG', 'JPEG', 'WEBP') or getattr(im, 'n_frames', 1) != 1:
                raise ValueError('成图必须为单帧PNG/JPG/WebP')
            minimum = image_budget.configuration().get('minimum_short_side', 1600)
            if min(im.size) < minimum or max(im.size) > 12000:
                raise ValueError('生成图片尺寸未满足交付要求')
            size, fmt = list(im.size), im.format
            im.verify()
    except (OSError, Image.DecompressionBombError):
        raise ValueError('生成图片内容无法解码') from None
    return {'dimensions':size, 'mime':{'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[fmt],
            'sha256':hashlib.sha256(raw).hexdigest()}


def image_bytes(job, index):
    url = job['images'][index]
    if not isinstance(url, str):
        raise ValueError('生成结果地址无效')
    cache = image_provider.ROOT / 'generated-gallery-results'
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([job['id'], index, url]).encode()).hexdigest()
    path = cache / (key + '.image')
    raw = path.read_bytes() if path.is_file() else download(url)
    info = inspect(raw)
    if not path.exists():
        tmp = path.with_suffix('.tmp-' + uuid.uuid4().hex)
        tmp.write_bytes(raw)
        tmp.replace(path)
    return raw, info


def selected(product, current_project_id):
    selection = product.get('generatedGallerySelection')
    if selection is None:
        return None
    if not isinstance(selection, dict) or selection.get('version') != 1:
        raise ValueError('生成图片导出选择格式无效，请重新保存选择')
    if selection.get('sourceStudioProjectId') != current_project_id:
        raise ValueError('视觉方案已更换，请重新核对并保存导出图片选择')
    items = selection.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValueError('请选择1–20张生成图片用于导出')
    jobs = {j['id']:j for j in image_provider.jobs()['jobs']}
    seen, result = set(), []
    # Validate every selected handle before fetching any source image.
    for row in items:
        if not isinstance(row, dict):
            raise ValueError('生成图片选择项无效')
        jid, index = row.get('jobId'), row.get('imageIndex', 0)
        if not isinstance(jid, str) or type(index) is not int or index < 0 or (jid, index) in seen:
            raise ValueError('生成图片重复或图片序号无效')
        seen.add((jid, index))
        job = jobs.get(jid)
        if not job or job.get('productId') != product['id']:
            raise ValueError('生成任务不属于当前账号和产品')
        if job.get('status') != 'completed' or not isinstance(job.get('images'), list) or index >= len(job['images']):
            raise ValueError('所选生成任务尚未完成或没有对应图片')
        if row.get('sha256') is not None and (not isinstance(row['sha256'], str) or len(row['sha256']) != 64):
            raise ValueError('生成图片哈希无效')
        result.append((row, job, index))
    return result


def export_images(product, current_project_id):
    rows = selected(product, current_project_id)
    if rows is None:
        return None
    import agent_review
    reviewed = agent_review.gallery_approved(product, rows)
    output = []
    for slot, (row, job, index) in enumerate(rows):
        raw, info = image_bytes(job, index)
        if row.get('sha256') and row['sha256'] != info['sha256']:
            raise ValueError('生成图片与已核对文件哈希不符，未导出')
        raw, info = prepare_delivery(raw)
        output.append((raw, {**info, 'slot':slot, 'jobId':job['id'], 'imageIndex':index,
                            'providerSlot':job.get('slot',''), 'status':'awaiting_manual',
                            'humanReviewed':False, 'productionApproved':False,
                            'agentReviewedForDraft':reviewed,
                            'reviewScope':'draft_only' if reviewed else None}))
    return output


def selection_summary(product, current_project_id):
    """Read selection ownership/review metadata without fetching or caching images.

    The ERP handoff still verifies the actual bytes and selected SHA256 values.
    Native render QA is a different source and must not approve selected jobs.
    """
    selection = product.get('generatedGallerySelection')
    if selection is None:
        return None
    result = {'productId': product['id'], 'selection': selection,
              'imageCount': 0, 'ready': False, 'reviewScope': 'draft_only'}
    try:
        rows = selected(product, current_project_id)
        result['imageCount'] = len(rows)
        if len(rows) != 7:
            raise ValueError('已选母版须保留完整7张图片')
        import agent_review
        if not agent_review.gallery_approved(product, rows):
            raise ValueError('已选母版尚未通过当前产品及图片哈希绑定的草稿审核')
        result['ready'] = True
    except (ValueError, KeyError, TypeError) as error:
        result['reason'] = str(error)
    return result
