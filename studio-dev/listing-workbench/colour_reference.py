"""Robust colour sampling from an explicitly selected patch of a real SKU photo."""
import hashlib
import io
import math
import numpy as np
from PIL import Image, ImageOps
import image_provider


def sample(reference, box):
    # Callers must establish product/variant ownership before reaching here.
    if not isinstance(box, list) or len(box) != 4 or any(
        type(n) not in (int, float) or not math.isfinite(n) for n in box
    ):
        raise ValueError('请在同色参考图上框选一块面料')
    left, top, right, bottom = box
    if not 0 <= left < right <= 1 or not 0 <= top < bottom <= 1:
        raise ValueError('取色范围必须位于参考图内')
    raw = (image_provider.local_image(reference) if reference.startswith('/uploads/')
           else image_provider.remote_reference(reference)[0])
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.width * opened.height > 18_000_000:
            raise ValueError('参考图超过1800万像素')
        image = ImageOps.exif_transpose(opened).convert('RGBA')
    pixels = [int(left * image.width), int(top * image.height),
              int(math.ceil(right * image.width)), int(math.ceil(bottom * image.height))]
    patch = image.crop(pixels)
    if patch.width * patch.height < 25:
        raise ValueError('取色区域太小，请框选至少25个像素的面料')
    patch.thumbnail((256, 256))
    import cv2
    rgba = np.asarray(patch)
    visible = rgba[:, :, 3] > 230
    if int(visible.sum()) < 25:
        raise ValueError('取色区域有效面料像素不足，请避开透明背景')
    lab = cv2.cvtColor(rgba[:, :, :3].astype('float32') / 255, cv2.COLOR_RGB2LAB)[visible]
    centre = np.median(lab, axis=0)
    distances = np.linalg.norm(lab - centre, axis=1)
    # Reject a few seams/specular spots without assuming that black or white
    # pixels are background. Those are valid product colours too.
    core = lab[distances <= np.percentile(distances, 80)]
    centre = np.median(core, axis=0)
    rgb = np.rint(cv2.cvtColor(centre.reshape(1, 1, 3).astype('float32'), cv2.COLOR_LAB2RGB)[0, 0] * 255).clip(0, 255).astype(int)
    variation = float(np.percentile(distances, 80))
    warnings = ['区域颜色变化较大，建议避开花纹、背景和强反光后重新取色'] if variation > 18 else []
    return {'target': '#' + ''.join(f'{v:02x}' for v in rgb), 'rgb': rgb.tolist(),
            'reference': reference, 'sourceSha256': hashlib.sha256(raw).hexdigest(),
            'box': box, 'pixelBox': pixels, 'width': image.width, 'height': image.height,
            'variation': round(variation, 2), 'warnings': warnings,
            'method': 'reference-patch-lab-median-v1', 'imageGenerationSubmitted': False}
