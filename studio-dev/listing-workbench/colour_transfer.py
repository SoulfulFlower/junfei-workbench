"""Independent, selection-bound colour transfer; no remote service or vendor code.

Coloured, neutral and reference-photo transfers use different mappings. Statistics
come from opaque selected pixels, never the scene. Protection wins after feather.
"""
import numpy as np
import cv2
from PIL import Image

VERSION = 'selective-transfer-v1'


def transfer(source, mask, target, *, protected=None, reference=None, reference_mask=None, blend=True):
    rgb = np.asarray(source.convert('RGB'))
    a = np.asarray(mask.convert('L') if isinstance(mask, Image.Image) else mask, dtype=np.float32)
    if a.shape != rgb.shape[:2] or not np.isfinite(a).all():
        raise ValueError('换色选区必须与原图尺寸一致')
    if a.max() > 1:
        a /= 255
    if np.any((a < 0) | (a > 1)):
        raise ValueError('选区透明度必须为0–1')
    a = a.copy()
    if protected is not None:
        p = np.asarray(protected.convert('L') if isinstance(protected, Image.Image) else protected)
        if p.shape != a.shape:
            raise ValueError('保护区必须与原图尺寸一致')
        a[p > 0] = 0
    if 'A' in source.getbands():
        a[np.asarray(source.getchannel('A')) == 0] = 0
    selected = a > .95
    if np.count_nonzero(selected) < 50:
        raise ValueError('选区内至少需要50个完整商品像素')
    src = rgb.astype(np.float32) / 255
    lab = cv2.cvtColor(src, cv2.COLOR_RGB2LAB)
    colour = np.asarray(target, dtype=np.float32) / 255
    if colour.shape != (3,) or not np.isfinite(colour).all() or np.any((colour < 0) | (colour > 1)):
        raise ValueError('目标颜色必须为有效RGB值')
    dstlab = cv2.cvtColor(colour.reshape(1, 1, 3), cv2.COLOR_RGB2LAB)[0, 0]
    hsv = cv2.cvtColor(src, cv2.COLOR_RGB2HSV)
    thsv = cv2.cvtColor(colour.reshape(1, 1, 3), cv2.COLOR_RGB2HSV)[0, 0]
    main = np.median(lab[selected], axis=0)
    lo, hi = np.percentile(lab[:, :, 0][selected], [5, 95])
    mapped = lab.copy()
    if reference is not None:
        ref = np.asarray(reference.convert('RGB'), dtype=np.float32) / 255
        ref_lab = cv2.cvtColor(ref, cv2.COLOR_RGB2LAB)
        if reference_mask is None:
            raise ValueError('参考照片取色需要明确衣料/商品选区，不能把背景参与统计')
        rm = np.asarray(reference_mask.convert('L') if isinstance(reference_mask, Image.Image) else reference_mask)
        if rm.shape != ref.shape[:2] or np.count_nonzero(rm > (240 if rm.max() > 1 else .95)) < 50:
            raise ValueError('参考照片选区无效')
        samples = ref_lab[rm > (240 if rm.max() > 1 else .95)]
        # A robust affine transform retains source texture; it never copies
        # reference-photo texture or geometry. Bound gain to avoid metallic folds.
        centre = np.median(samples, axis=0)
        dstlab = centre
        src_std = np.std(lab[selected], axis=0)
        ref_std = np.std(samples, axis=0)
        gain = np.clip(ref_std / np.maximum(src_std, 1), .65, 1.4)
        mapped = (lab - main) * gain + centre
        branch = 'reference-photo'
    elif thsv[1] < .12:
        # Percentile remap for black/white/grey; preserve fold rank and high
        # frequency detail rather than merely replacing a/b on a dark source.
        target_l = float(dstlab[0])
        spread = max(8., min(26., float(hi-lo)))
        newlo, newhi = max(1., target_l-spread*.55), min(99., target_l+spread*.45)
        normal = np.clip((lab[:, :, 0]-lo)/max(float(hi-lo), 1.), -.25, 1.25)
        remap = newlo + normal*(newhi-newlo)
        relative = target_l + (lab[:, :, 0]-main[0])*.65
        mapped[:, :, 0] = .7*remap + .3*relative
        mapped[:, :, 1:] = dstlab[1:]
        branch = 'neutral'
    else:
        # Circular hue is set explicitly; S and V keep local variation. Dark
        # neutral sources need a value lift before chroma can be visible.
        shsv = np.median(hsv[selected], axis=0)
        out = hsv.copy()
        out[:, :, 0] = thsv[0]
        out[:, :, 1] = np.clip(thsv[1] + .45*(hsv[:, :, 1]-shsv[1]), 0, 1)
        out[:, :, 2] = np.clip(thsv[2] + (hsv[:, :, 2]-shsv[2])*.8, 0, 1)
        mapped = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_HSV2RGB), cv2.COLOR_RGB2LAB)
        branch = 'chromatic'
    mapped[:, :, 0] = mapped[:, :, 0].clip(0, 100)
    replacement = cv2.cvtColor(mapped.astype(np.float32), cv2.COLOR_LAB2RGB).clip(0, 1)
    # Never expand the supplied selection into skin, hardware, type or scenery.
    weight = a*a*(3-2*a) if blend else (a>0).astype(np.float32)
    result = np.rint((src*(1-weight[:, :, None])+replacement*weight[:, :, None])*255).clip(0, 255).astype('uint8')
    result[a == 0] = rgb[a == 0]
    output = Image.fromarray(result)
    if 'A' in source.getbands():
        output.putalpha(source.getchannel('A'))
    actual = cv2.cvtColor(result.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    stats = {'version': VERSION, 'branch': branch, 'selectedPixels': int(selected.sum()),
             'sourceLab': main.tolist(), 'targetLab': dstlab.tolist(),
             'resultLab': np.median(actual[selected], axis=0).tolist(),
             'sourceLightRange': [float(lo), float(hi)],
             'outsideChangedPixels': int(np.any(result[a == 0] != rgb[a == 0], axis=-1).sum()),
             'humanReviewed': False}
    return output, stats
