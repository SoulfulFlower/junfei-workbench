"""Unverified non-primary cloth proposals for the EXISTING planner call.

No mask filling, provider call, SKU certification or quality-policy change.
The planner must inspect source structure and may reject every proposal.
"""
import hashlib
import math
import numpy as np
import cv2
from PIL import Image, ImageDraw

VERSION = 'non-primary-cloth-proposals-v1'
POLICY = {'minimumComponentPixels': 16, 'minimumStableInteriorPixels': 4,
    'maximumPrimaryFraction': .08, 'maximumImageFraction': .02,
    'maximumSourceLabDistance': 10., 'maximumRegions': 6,
    'thresholdsAreProposalFiltersOnly': True}


def _sha(data):return hashlib.sha256(data).hexdigest()


def propose(source, kind, evidence, *, max_regions=6):
    """Return JSON context and at most one source/candidate-overlay montage.

    Evidence is the current source's _local_evidence, not a candidate output.
    This API does not receive FG points and makes NO "unanchored" claim.
    """
    if not isinstance(source, Image.Image) or kind not in ('upper', 'lower', 'full'):
        raise ValueError('候选须有当前原图及明确衣物品类')
    if type(max_regions) is not int or not 0 <= max_regions <= 6:
        raise ValueError('候选图块数量须为0–6')
    if not isinstance(evidence, dict):raise ValueError('候选须使用当前本地源证据')
    width, height = source.size
    if min(width, height) < 16 or max(width, height) > 8192 or width*height > 40_000_000:
        raise ValueError('候选原图尺寸不支持')
    rgb = np.asarray(source.convert('RGB')); rgba = np.asarray(source.convert('RGBA'))
    arrays = {key: np.asarray(evidence.get(key)) for key in
        ('primary', 'human', 'distance', 'protected', 'sourceRGB', 'sourceLab', 'opaqueSource')}
    for key, value in arrays.items():
        expected = (height, width, 3) if key in ('sourceRGB', 'sourceLab') else (height, width)
        if value.shape != expected:raise ValueError('候选源证据尺寸不符：'+key)
    if not np.array_equal(arrays['sourceRGB'], rgb):raise ValueError('候选证据不是当前原图像素')
    for key in ('distance', 'sourceLab'):
        if not np.issubdtype(arrays[key].dtype, np.number) or not np.isfinite(arrays[key]).all():
            raise ValueError('候选源色彩证据无效')
    if (arrays['distance'] < 0).any() or not np.isin(arrays['human'], np.arange(18)).all():
        raise ValueError('候选本地分类或色差证据无效')
    if evidence.get('kind', kind) != kind:raise ValueError('候选证据衣物品类不符')
    allowed = evidence.get('semanticGarmentClasses')
    legal = {'upper': {4, 7}, 'lower': {5, 6, 7}, 'full': {7}}[kind]
    if (not isinstance(allowed, (list, tuple)) or not allowed
            or any(type(value) is not int or value not in legal for value in allowed)):
        raise ValueError('候选须保留当前品类的独立衣物语义')
    primary = arrays['primary'].astype(bool)
    protected = arrays['protected'].astype(bool)
    opaque = arrays['opaqueSource'].astype(bool)
    if not np.array_equal(opaque, rgba[:, :, 3] > 0):raise ValueError('候选源透明度证据不符')
    other = np.asarray(evidence.get('other', np.zeros((height, width), bool)))
    if other.shape != primary.shape:raise ValueError('其他衣物保护证据尺寸不符')
    body = primary & ~protected & opaque
    by, bx = np.nonzero(body)
    context = {'version': VERSION, 'kind': kind, 'sourceSize': [width, height],
        'sourcePixelSha256': _sha(rgba.tobytes()), 'sourceHashEncoding': 'rgba8_top_to_bottom',
        'unverifiedHypothesis': True, 'certifiesSelection': False, 'modifiesMask': False,
        'foregroundAnchorStatus': 'not_evaluated_api_has_no_foreground_points',
        'purpose': 'Inspect non-primary cloth hypotheses in this existing planner call; reject other garments, skin, hair, accessories or background even when similarly coloured. Use ORIGINAL normalized coordinates; never accept same-SKU identity from these filters.',
        'policy': dict(POLICY), 'regions': []}
    if not len(bx) or not max_regions:return {'context': context, 'montage': None}
    near = min(30, max(6, round(min(width, height) * .03)))
    primary_bbox = [int(bx.min()), int(by.min()), int(bx.max())+1, int(by.max())+1]
    max_area = min(int(body.sum() * POLICY['maximumPrimaryFraction']), int(primary.size * POLICY['maximumImageFraction']))
    context.update(primaryBBoxPixels=primary_bbox, maximumDistanceToPrimaryPixels=near,
        maximumComponentPixels=max_area, primaryPixels=int(body.sum()))
    candidates = (np.isin(arrays['human'], allowed) & (arrays['distance'] < POLICY['maximumSourceLabDistance'])
        & opaque & (rgba[:, :, 3] > 230) & ~primary & ~protected & ~other.astype(bool))
    count, labels, stats, centres = cv2.connectedComponentsWithStats(candidates.astype('uint8'), 8)
    nearest = cv2.distanceTransform((~body).astype('uint8'), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    found = []
    for label in range(1, count):
        x, y, w, h, area = map(int, stats[label])
        if not POLICY['minimumComponentPixels'] <= area <= max_area:continue
        if (x < primary_bbox[0]-near or y < primary_bbox[1]-near
                or x+w > primary_bbox[2]+near or y+h > primary_bbox[3]+near):continue
        component = labels[y:y+h, x:x+w] == label
        stable = cv2.erode(component.astype('uint8'), np.ones((3, 3), 'uint8'), borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
        if int(stable.sum()) < POLICY['minimumStableInteriorPixels']:continue
        distance = float(nearest[y:y+h, x:x+w][component].min())
        if distance > near:continue
        padded = np.pad(component.astype('uint8'), 1)
        depth = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
        dy, dx = np.nonzero(depth == depth.max())
        target = np.array(centres[label]) - [x, y]
        best = int(np.argmin((dx-target[0])**2 + (dy-target[1])**2))
        point = [int(x+dx[best]), int(y+dy[best])]
        full_component = (labels == label).astype('uint8') * 255
        found.append({'componentLabel': label, 'componentPixels': area,
            'stableInteriorPixels': int(stable.sum()), 'deepestInteriorDistancePixels': float(depth.max()),
            'distanceToPrimaryPixels': distance, 'componentBBoxPixels': [x, y, x+w, y+h],
            'pointPixels': point, 'point': [point[0]/(width-1), point[1]/(height-1)],
            'componentPixelSha256': _sha(full_component.tobytes()),
            'componentHashEncoding': 'l8_0_or_255_original_source_canvas',
            'sourcePixelSha256': context['sourcePixelSha256'], 'unverifiedHypothesis': True})
    found.sort(key=lambda row: (-row['stableInteriorPixels'], row['distanceToPrimaryPixels'], row['componentLabel']))
    regions = found[:max_regions]
    if not regions:return {'context': context, 'montage': None}
    panel, header = 256, 24
    montage = Image.new('RGB', (panel*2, (panel+header)*len(regions)), '#f4f4f0')
    draw = ImageDraw.Draw(montage)
    for index, row in enumerate(regions):
        x0, y0, x1, y1 = row['componentBBoxPixels']; px, py = row['pointPixels']
        side = min(width, height, max(64, min(128, max(x1-x0, y1-y0)+24)))
        left = max(0, min(width-side, round(px-side/2))); top = max(0, min(height-side, round(py-side/2)))
        bbox = [left, top, left+side, top+side]
        crop = rgb[top:top+side, left:left+side].copy()
        selected = labels[top:top+side, left:left+side] == row['componentLabel']
        overlay = crop.copy()
        overlay[selected] = np.rint(crop[selected].astype(float)*.4 + np.array([20, 150, 240])*.6).astype('uint8')
        boxes = []
        for column, pixels in enumerate((crop, overlay)):
            box = [column*panel, index*(panel+header)+header, (column+1)*panel, (index+1)*(panel+header)]
            montage.paste(Image.fromarray(pixels).resize((panel, panel), Image.Resampling.NEAREST), tuple(box[:2]))
            draw.text((column*panel+5, index*(panel+header)+5), f"REGION {index+1} {('SOURCE', 'HYPOTHESIS')[column]}", fill='black')
            boxes.append(box)
        row.update(region=index+1, cropBBoxPixels=bbox, bboxEncoding='xyxy_half_open_original_source_pixels',
            cropPixelSha256=_sha(crop.tobytes()), cropHashEncoding='rgb8_top_to_bottom',
            panelBoxesPixels=boxes, displayScale=panel/side,
            componentFullyInCrop=left <= x0 and top <= y0 and left+side >= x1 and top+side >= y1)
    context.update(regions=regions, columnRoles=['authoritative_source_crop', 'unverified_component_overlay'],
        montageSize=list(montage.size), montagePixelSha256=_sha(montage.tobytes()),
        montageHashEncoding='rgb8_top_to_bottom', candidateRegionsBeforeLimit=len(found))
    return {'context': context, 'montage': montage}
