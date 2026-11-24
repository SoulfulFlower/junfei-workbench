"""Local, hash-bound composition gate. No paid calls and no image modification."""
import hashlib
import io
import threading
from collections import Counter, OrderedDict, deque

from PIL import Image, ImageOps, ImageChops, ImageFilter

POLICY = 'product-composition-v4'
INSTRUCTION = ('COMPOSITION GATE: Make the sellable product visually substantial at thumbnail scale. '
               'Remove useless outer padding; do not place a small photograph inside a large grey/white card. '
               'Use a continuous edge-to-edge photograph for detail slots. Tighten scene framing so the actual '
               'garment, rather than the room, floor or styling trousers, dominates. Keep real proportions and '
               'important edges intact; never stretch the product or invent structure to fill space. '
               'For a size guide, enlarge the complete legible table instead of filling the frame with decoration.')
_CACHE = OrderedDict()
_LOCK = threading.RLock()


def _component(mask, width, height):
    """Largest connected region; detached headlines must not enlarge a photo."""
    remaining = set(i for i, value in enumerate(mask) if value)
    best = []
    while remaining:
        seed = remaining.pop()
        region, queue = [seed], deque([seed])
        while queue:
            at = queue.popleft()
            x, y = at % width, at // width
            for nx, ny in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
                other = ny*width+nx
                if 0 <= nx < width and 0 <= ny < height and other in remaining:
                    remaining.remove(other); region.append(other); queue.append(other)
        if len(region) > len(best):
            best = region
    if not best:
        return 0, None
    xs, ys = [i % width for i in best], [i // width for i in best]
    return len(best)/(width*height), [min(xs)/width, min(ys)/height,
                                     (max(xs)+1)/width, (max(ys)+1)/height]


def _neutral_frame(image):
    sample = ImageOps.contain(image, (192, 192)).convert('RGB')
    width, height = sample.size
    pixels = list(sample.get_flattened_data() if hasattr(sample, 'get_flattened_data') else sample.getdata())
    edges = [pixels[y*width+x] for y in range(height) for x in range(width)
             if x < 2 or y < 2 or x >= width-2 or y >= height-2]
    neutral = [p for p in edges if min(p) >= 185 and max(p)-min(p) <= 20]
    if len(neutral) < len(edges)*.65:
        return {'detected': False}
    buckets = Counter(tuple(v//8 for v in p) for p in neutral)
    bucket, _ = buckets.most_common(1)[0]
    candidates = [p for p in neutral if tuple(v//8 for v in p) == bucket]
    background = tuple(sorted(p[c] for p in candidates)[len(candidates)//2] for c in range(3))
    matching = lambda p: max(abs(a-b) for a, b in zip(p, background)) <= 22
    if sum(matching(p) for p in edges) < len(edges)*.65:
        return {'detected': False}
    # A pale textured garment can share the border's colour without being
    # empty padding. Count visible local texture as content as well as colour
    # contrast; uniform card margins (including mild JPEG noise) stay blank.
    grey = sample.convert('L')
    local_range = ImageChops.subtract(grey.filter(ImageFilter.MaxFilter(5)),
                                     grey.filter(ImageFilter.MinFilter(5)))
    ranges = list(local_range.get_flattened_data() if hasattr(local_range, 'get_flattened_data')
                  else local_range.getdata())
    mask = [not matching(p) or ranges[i] >= 16 for i, p in enumerate(pixels)]
    area, box = _component(mask, width, height)
    points = [i for i, value in enumerate(mask) if value]
    all_box = ([min(i % width for i in points)/width, min(i // width for i in points)/height,
                (max(i % width for i in points)+1)/width, (max(i // width for i in points)+1)/height]
               if points else None)
    return {'detected': True, 'background': list(background),
            'texturedContentFraction': round(sum(matching(p) and ranges[i] >= 16
                for i, p in enumerate(pixels))/len(pixels), 4),
            'blankFraction': round(1-sum(mask)/len(mask), 4),
            'largestRegionFraction': round(area, 4), 'contentBox': box, 'allContentBox': all_box}


def _lower_continuation(image, human, cloth, base):
    """Recover lower-leg pixels labelled as a full outfit, using real seeds.

    Growth stays in the coarse clothing domain, below the median lower-body
    seed, in its measured fabric palette, and connected to that seed.
    """
    import cv2
    import numpy as np
    count, labels, stats, _ = cv2.connectedComponentsWithStats(base.astype('uint8'))
    if count < 2:return base, None
    seed = labels == 1+stats[1:,cv2.CC_STAT_AREA].argmax()
    seed &= np.isin(cloth, (2,3)) & np.isin(human, (5,6))
    if seed.sum() < max(50, seed.size*.001):return base, None
    lab = cv2.cvtColor(np.asarray(image).astype('float32')/255, cv2.COLOR_RGB2LAB)
    values=lab[seed];centre=np.median(values[:,1:],axis=0)
    tolerance=max(10,float(np.percentile(np.linalg.norm(values[:,1:]-centre,axis=1),90))*1.75)
    low,high=np.percentile(values[:,0],(2,98));start=float(np.median(np.nonzero(seed)[0]))
    candidate=((cloth==3) & (np.indices(seed.shape)[0]>=start)
               & (np.linalg.norm(lab[:,:,1:]-centre,axis=2)<=tolerance)
               & (lab[:,:,0]>=low-25) & (lab[:,:,0]<=high+12))
    _,connected=cv2.connectedComponents((seed|candidate).astype('uint8'),connectivity=8)
    anchors=np.unique(connected[seed]);growth=candidate & np.isin(connected,anchors[anchors!=0])
    return base|growth, {'method':'connected_lower_clothing_palette','seedPixels':int(seed.sum()),
                         'startY':round(start/image.height,4),'chromaTolerance':round(tolerance,3),
                         'addedPixels':int((growth & ~base).sum())}


def _garment(image, kind):
    """Pinned SCHP/ATR model already shipped for local clothing automation."""
    import numpy as np
    import garment_auto
    sample = ImageOps.contain(image, (256, 256)).convert('RGB')
    with garment_auto.LOCK:
        labels = garment_auto.human_parser().predict(sample)
        cloth = garment_auto.parser().predict(sample)
        selected, _, _ = garment_auto.choose(cloth, kind, labels)
    classes = {'upper': (4,), 'lower': (5, 6), 'full': (4, 7)}[kind]
    mask = np.isin(labels, classes)
    area, box = _component(mask.flatten().tolist(), sample.width, sample.height)
    cloth_area, cloth_box = _component(selected.flatten().tolist(), sample.width, sample.height)
    if cloth_area > area:
        area, box = cloth_area, cloth_box
    refinement=None
    if kind=='lower' and area < .25:
        continued,proof=_lower_continuation(sample,labels,cloth,mask|selected)
        refined_area,refined_box=_component(continued.flatten().tolist(),sample.width,sample.height)
        if refined_area > area:area,box,refinement=refined_area,refined_box,proof
    return {'model': 'schp-atr-18-int8-static+u2net-clothes', 'kind': kind,
            'coverage': round(area, 4), 'box': box, 'refinement':refinement}


def inspect(raw, *, role='supporting', garment_kind=None):
    if role not in ('main', 'supporting', 'detail', 'size_chart'):
        raise ValueError('图片构图检查图位无效')
    if garment_kind not in (None, 'upper', 'lower', 'full'):
        raise ValueError('图片构图检查商品类别无效')
    sha = hashlib.sha256(raw).hexdigest()
    key = (POLICY, sha, role, garment_kind)
    with _LOCK:
        if key in _CACHE:
            # Never let a caller mutate a cached passing result.
            import copy
            return copy.deepcopy(_CACHE[key])
    result = {'policy': POLICY, 'sha256': sha, 'role': role, 'issues': []}
    def fail(code, message):
        result['issues'].append({'code': code, 'severity': 'error', 'message': message})
    try:
        if len(raw) > 25*1024*1024:
            raise ValueError('image too large')
        with Image.open(io.BytesIO(raw)) as source:
            if source.width*source.height > 40_000_000 or getattr(source, 'n_frames', 1) != 1:
                raise ValueError('invalid image')
            rgba = source.convert('RGBA')
            image = Image.new('RGB', source.size, 'white')
            image.paste(rgba, mask=rgba.getchannel('A'))
        if all(high-low < 5 for low, high in image.getextrema()):
            fail('EMPTY_COMPOSITION', '图片接近纯色，没有有效商品或信息内容。')
        frame = _neutral_frame(image)
        result['frame'] = frame
        box = frame.get('allContentBox' if role == 'size_chart' else 'contentBox')
        if box:
            width, height = box[2]-box[0], box[3]-box[1]
            result['contentEnvelope'] = {'width': round(width,4), 'height': round(height,4)}
            if role == 'main' and (max(width,height) < .85 or min(width,height) < .65):
                fail('SUBJECT_TOO_SMALL', '主图主体偏小或过窄：减少无效留白并重新构图，保持真实比例和关键结构，禁止拉伸凑满。')
            elif role != 'size_chart' and role != 'main':
                if (frame['blankFraction'] > .42 and width*height < .67
                        and min(width,height) < .80 and frame['largestRegionFraction'] > .035):
                    fail('BOXED_SMALL_PHOTO', '图片为大块浅色/灰底套小画面：放大实际照片或细节，取消无意义底框及二次留白。')
                elif frame['blankFraction'] > .68 and width*height < .72:
                    fail('EXCESSIVE_WHITESPACE', '图片无效留白过多，商品或信息画面偏小，请沿原图位重新构图。')
            elif role == 'size_chart' and (width < .70 or height < .45):
                fail('SIZE_CHART_TOO_SMALL', '尺码表内容区域过小：放大表格并减少留白，保留全部尺码、数值及单位。')
        elif frame.get('detected') and not result['issues']:
            fail('EMPTY_COMPOSITION', '图片未检测到有效商品或信息内容。')
        # Charts are information layouts, never passed to a clothing detector.
        # Human parsing estimates complete worn garments, not a cropped seam or
        # fabric surface. Detail images still receive the pixel framing checks
        # above and the separate source-bound semantic review.
        if garment_kind and role not in ('size_chart', 'detail') and not result['issues']:
            garment = _garment(image, garment_kind)
            result['garment'] = garment
            minimum = .25 if role == 'main' else .20 if role == 'detail' else .12
            if garment['coverage'] < minimum:
                fail('GARMENT_TOO_SMALL', '实际售卖服装占画面比例过小或无法可靠识别：收紧景别、突出商品后重新检查。')
    except (OSError, ValueError, ImportError, RuntimeError) as error:
        fail('COMPOSITION_UNAVAILABLE', '图片构图自动检查未完成，不能放行：'+str(error))
    result['pass'] = not result['issues']
    with _LOCK:
        import copy
        # A missing/repaired local model must be retryable on the same pixels.
        if not any(i['code'] == 'COMPOSITION_UNAVAILABLE' for i in result['issues']):
            _CACHE[key] = copy.deepcopy(result)
        while len(_CACHE) > 96:
            _CACHE.popitem(last=False)
    return result


def check(raw, *, slot, product=None, size_chart=False, detail=False):
    """Shared generation/export/ERP boundary. Metadata cannot override failure."""
    kind = None
    if product:
        import garment_auto
        value = garment_auto.category(product)
        if value != 'auto':
            kind = value
    role = 'size_chart' if size_chart else 'main' if slot == 0 else 'detail' if detail else 'supporting'
    return inspect(raw, role=role, garment_kind=kind)


def require(raw, **context):
    result = check(raw, **context)
    if not result['pass']:
        raise ValueError('第 '+str(context['slot']+1)+' 张图片构图不通过：'+'；'.join(i['message'] for i in result['issues']))
    return result


def for_project(raw, project, slot):
    cards = (project.get('uiPlan') or {}).get('images') or []
    card = cards[slot] if slot < len(cards) else {}
    return check(raw, slot=slot, product=project.get('productFacts') or {},
                 size_chart=card.get('size_chart') is True, detail=card.get('shot_type') == 'detail')
