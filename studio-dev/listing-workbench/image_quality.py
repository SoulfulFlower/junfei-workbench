"""Deterministic image-file checks. Identity and artwork copy require visual review."""
import hashlib
import io

from PIL import Image, ImageFilter, ImageOps, ImageStat


def _white_padding(image):
    """Detect matching outer white bands with sharp transitions into artwork."""
    sample = image.resize((96, 96), Image.Resampling.BOX)
    pixels = sample.get_flattened_data() if hasattr(sample, 'get_flattened_data') else sample.getdata()
    white = [int(min(pixel) >= 248 and max(pixel) - min(pixel) <= 5) for pixel in pixels]
    rows = [sum(white[start:start+96]) for start in range(0, len(white), 96)]
    columns = [sum(white[column::96]) for column in range(96)]

    def band(lines):
        count = next((i for i, pixels in enumerate(lines) if pixels < 94), len(lines))
        return count if 4 <= count <= 23 and min(lines[count:count+3]) <= 61 else 0

    for lines in (rows, columns):
        first, last = band(lines), band(lines[::-1])
        if first and last and abs(first-last) <= 3:
            return True
    return False


def inspect(raw, *, expected=None, minimum=1600, main=False, full_bleed=False):
    result = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'issues': []}
    issues = result['issues']
    try:
        if len(raw) > 25*1024*1024:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            if (image.format not in ('PNG', 'JPEG', 'WEBP') or getattr(image, 'n_frames', 1) != 1
                    or width*height > 40_000_000):
                raise ValueError()
            image.load()
            result.update(format=image.format, dimensions=[width, height])
            if expected and result['dimensions'] != expected:
                issues.append({'code': 'OUTPUT_SIZE', 'severity': 'error', 'message': '成图像素尺寸与任务不一致'})
            if min(width, height) < minimum:
                issues.append({'code': 'SHORT_SIDE', 'severity': 'warning', 'message': f'短边低于交付要求 {minimum} px'})
            rgb = image.convert('RGB')
            thumb = ImageOps.contain(rgb, (96, 96))
            ranges = thumb.getextrema()
            if all(high-low < 5 for low, high in ranges):
                issues.append({'code': 'FLAT_IMAGE', 'severity': 'error', 'message': '成图接近纯色，请核对输出'})
            elif min(thumb.size) > 4:
                edges = thumb.convert('L').filter(ImageFilter.FIND_EDGES)
                interior = edges.crop((1, 1, edges.width-1, edges.height-1))
                if ImageStat.Stat(interior).mean[0] < 1:
                    issues.append({'code': 'LOW_DETAIL', 'severity': 'warning', 'message': '缩略像素细节对比偏低，需人工核对清晰度'})
            if main:
                w, h = thumb.size
                corners = [thumb.getpixel((x, y)) for x in (0, w-1) for y in (0, h-1)]
                if any(min(pixel) < 245 for pixel in corners):
                    issues.append({'code': 'MAIN_CORNERS', 'severity': 'warning', 'message': '主图部分角落接近非白背景，需人工核对'})
            if full_bleed and _white_padding(rgb):
                issues.append({'code': 'WHITE_PADDING', 'severity': 'error',
                               'message': '成图含明显的上下或左右白边。让实景或版式背景连续铺满画布四边，保持图位原定的镜头、比例和安全边距。'})
    except (OSError, ValueError, Image.DecompressionBombError):
        issues.append({'code': 'BAD_FILE', 'severity': 'error', 'message': '成图无法按单帧 PNG/JPG/WebP 解码'})
    result['pass'] = not any(issue['severity'] == 'error' for issue in issues)
    return result


def duplicate_issues(files):
    seen, issues = {}, []
    for index, raw in enumerate(files, 1):
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen:
            issues.append({'code': 'DUPLICATE_FILE', 'severity': 'error',
                           'message': f'第 {seen[digest]} 和第 {index} 张使用完全相同的图片文件'})
        else:
            seen[digest] = index
    return issues
