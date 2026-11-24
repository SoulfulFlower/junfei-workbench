"""Source-pixel reference colour sampling, NEVER a complete garment selection.

The caller owns authenticated Codex Tools transport. Small source fabric
samples are locally checked, independently reviewed and persisted. No full
garment segmentation, recolouring, image generation or colour-name lookup is
performed here.
"""
from pathlib import Path
import copy
import json
import math
import threading
import time
import numpy as np
import cv2
from PIL import Image
import automatic_garment_selection as selection

VERSION = 'automatic-reference-sample-v2-kind-corroboration'
ALGORITHM_VERSION = 'source-pixel-midtone-samples-v2'
SCOPE = 'target_colour_sample_only'
CACHE_DIR = 'rs1'
LOCK = threading.RLock()

PLAN_INSTRUCTION = '''Identify the saved target garment in source image 1,
using context.subject. This task samples its REPRESENTATIVE FABRIC COLOUR;
it does NOT select the complete garment for recolouring. A previous selection
failure does not prevent valid clean fabric samples. Never propose a full mask.
Return JSON ONLY:
{"samples":[{"point":[u,v],"radiusFraction":0.01,"part":"visible target fabric part",
"tone":"midtone","evidence":"why this exact source patch is clean target cloth"}],
"limitations":["source lighting or multicolour limitations"]}
Give 3 to 8 small separated source patches across clean visible body/sleeve
fabric of THIS target garment. All coordinates are normalized 0..1 in the
original source; radiusFraction is 0.003 to 0.02 of the shorter image side.
Choose typical middle fabric tones, not seams, zips, edge mixtures, specular
highlights, deep shadows or folds. Exclude skin, hair, bags, straps, phones,
background and any separate inner garment, even if its parser label or colour
is similar. Quilted body and smooth sleeves may belong to the same garment.
Local parser garment subcategories can disagree. They are source fabric
evidence, never proof that a patch belongs to the saved target product.
Do not infer RGB from a colour name, alter pixels, fill hidden areas, or claim
human approval. Image 2, when present, shows ONLY actual attempted sample
pixels in blue; it is not a complete garment mask. Use previousFailure to
correct concrete rejected samples, without forcing a successful result.'''

REVIEW_INSTRUCTION = '''Independently inspect original source image 1 and actual
colour-sample overlay image 2. Blue pixels are ONLY the source pixels that will
be sampled, not a full clothing selection. Use context.subject to identify the
saved target product. DO NOT require full garment coverage or criticize
unsampled cuffs, pants, straps or garment edges. Instead check that EVERY blue
sample belongs to THIS target garment, avoids skin/hair/accessories/inner
clothing/background, and that the combined samples represent its normal
fabric middle tone rather than shadows, highlights or another material.
context.numericGate records any garment-subcategory disagreement. Independently
resolve those samples from the original photograph and context.subject;
neither a local fabric label nor the planner's claim establishes target identity.
Reject a sample on another top, pants, dress or inner garment even if clean
fabric and similar in colour. For kind=lower sample only the saved lower
garment; for upper only the saved upper garment; full does not mean the outfit.
The proposed RGB in context is computed from actual source pixels, never from
a colour name. Judge representativeness in the source photograph; do not claim
physical calibrated colour beyond that photograph or invent hidden facts.
Return JSON ONLY:
{"accepted":true_or_false,"allSamplesOnTarget":true_or_false,
"representativeColour":true_or_false,"issues":["specific source defects"],
"warnings":["nonblocking source-lighting limitations"],
"invalidSamples":[{"point":[u,v],"reason":"specific sampled defect"}]}
accepted=true requires allSamplesOnTarget=true, representativeColour=true,
issues=[] and invalidSamples=[]. This review cannot waive a failed numeric
gate and does not certify a complete garment/source recolouring mask.'''


class ReferenceSampleRejected(ValueError):
    def __init__(self, message, receipt, *, code='reference_sample_rejected'):
        super().__init__(message)
        self.receipt = receipt
        self.code = code


def _subject(value):
    subject = selection._subject(value)
    if not subject or subject.get('role') != 'target_colour_reference':
        raise ValueError('取色subject须明确role=target_colour_reference，不能作为源图完整选区')
    if not (subject.get('productName') or subject.get('target')):
        raise ValueError('取色须绑定已保存商品名或目标身份')
    return subject


def _review(value):
    if not isinstance(value, dict):raise ValueError('独立取色复核须返回对象')
    for key in ('accepted', 'allSamplesOnTarget', 'representativeColour'):
        if type(value.get(key)) is not bool:raise ValueError('取色复核缺少明确布尔结论')
    for key in ('issues', 'invalidSamples'):
        if not isinstance(value.get(key), list):raise ValueError('取色复核缺少完整缺陷集合')
    if any(not isinstance(row, str) for row in value['issues']):
        raise ValueError('取色复核缺陷须为具体文本')
    if 'warnings' in value and (not isinstance(value['warnings'], list)
            or any(not isinstance(row, str) for row in value['warnings'])):
        raise ValueError('取色复核warnings须为文本集合')
    if value['accepted'] and (not value['allSamplesOnTarget'] or not value['representativeColour']
            or value['issues'] or value['invalidSamples']):
        raise ValueError('取色复核声称通过但仍有归属或代表性缺陷')
    return value


def _evidence(source, kind, cloth, human):
    shape = (source.height, source.width)
    if cloth.shape != shape or human.shape != shape:
        raise ValueError('取色本地标签尺寸与原图不符')
    if not np.isin(cloth, [0, 1, 2, 3]).all() or not np.isin(human, np.arange(18)).all():
        raise ValueError('取色本地标签超出固定模型范围')
    allowed = list(selection.HUMAN_CLOTH[kind])
    if kind in ('upper', 'lower') and int(((cloth == selection.TARGET[kind]) & (human == 7)).sum()) >= max(50, cloth.size * .001):
        allowed.append(7)
    rgba = np.asarray(source.convert('RGBA'))
    # Both local models must still identify CLOTH, never anatomy/accessories.
    # A human-parser subcategory error may be corroborated only by the cloth
    # parser's exact requested kind. This adds no generic "any clothes" escape:
    # target identity remains a separate required original+overlay review.
    opaque = rgba[:, :, 3] > 230
    strict = (cloth > 0) & np.isin(human, allowed) & opaque
    kind_alias = ((cloth == selection.TARGET[kind]) & np.isin(human, [4, 5, 6, 7])
        & ~np.isin(human, allowed) & opaque)
    fabric = strict | kind_alias
    if fabric.sum() < 25:raise ValueError('本地双模型没有足够可核对衣料像素，未自动猜色')
    lab = cv2.cvtColor(rgba[:, :, :3].astype('float32') / 255, cv2.COLOR_RGB2LAB)
    light = lab[:, :, 0][fabric]
    return {'fabric': fabric, 'lab': lab, 'rgba': rgba, 'classes': allowed,
        'kindAliasFabric': kind_alias, 'cloth': cloth, 'human': human,
        'requestedClothClass': selection.TARGET[kind],
        'sourceFabricL10L90': np.quantile(light, [.1, .9]).tolist()}


def _extract(source, plan, evidence):
    if not isinstance(plan, dict) or not isinstance(plan.get('samples'), list) or not 3 <= len(plan['samples']) <= 8:
        raise ValueError('取色计划须提供3–8个有依据的小样区')
    fabric, lab = evidence['fabric'], evidence['lab']
    rgba = evidence['rgba']
    rows, rejected, seen = [], [], []
    for index, row in enumerate(plan['samples']):
        if (not isinstance(row, dict) or not selection._evidence(row)
                or not isinstance(row.get('part'), str) or not row['part'].strip()
                or row.get('tone') != 'midtone'):
            raise ValueError('取色点须有目标部件、中间调用途和当前原片证据')
        x, y = selection._point(row.get('point'), source.size)
        radius = row.get('radiusFraction', .01)
        if type(radius) not in (int, float) or not math.isfinite(radius) or not .003 <= radius <= .02:
            raise ValueError('取色半径须为原图短边0.3%–2%，不能替代整件选区')
        r = max(2, min(24, round(radius * min(source.size))))
        if any(math.hypot(x - px, y - py) < max(r, pr) * 2 for px, py, pr in seen):
            rejected.append({'index': index, 'reason': 'overlapping_or_duplicate_sample', 'pointPixels': [x, y]});continue
        seen.append((x, y, r))
        x0, x1, y0, y1 = max(0, x-r), min(source.width, x+r+1), max(0, y-r), min(source.height, y+r+1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        circle = (xx-x)**2 + (yy-y)**2 <= r*r
        valid = circle & fabric[y0:y1, x0:x1]
        if not fabric[y, x] or valid.sum() < 9 or valid.sum() / max(1, circle.sum()) < .90:
            rejected.append({'index': index, 'reason': 'source_patch_not_clean_dual_model_fabric', 'pointPixels': [x, y]});continue
        xy = np.column_stack([xx[valid], yy[valid]]).astype('int32')
        pixels = lab[xy[:, 1], xy[:, 0]]
        centre = np.median(pixels, axis=0)
        l25, l75 = np.quantile(pixels[:, 0], [.25, .75])
        if l75-l25 > 12 or np.quantile(np.linalg.norm(pixels-centre, axis=1), .90) > 18:
            rejected.append({'index': index, 'reason': 'source_patch_mixes_edges_glare_or_deep_folds', 'pointPixels': [x, y]});continue
        low, high = evidence['sourceFabricL10L90']
        margin = max(3, (high-low) * .1)
        if not low-margin <= centre[0] <= high+margin:
            rejected.append({'index': index, 'reason': 'source_patch_is_extreme_fabric_shadow_or_highlight', 'pointPixels': [x, y]});continue
        rows.append({'index': index, 'pointPixels': [x, y], 'radiusPixels': r,
            'part': row['part'], 'evidence': row['evidence'], 'pixelCount': len(xy),
            'kindCorroboratedMismatchPixels': int(evidence['kindAliasFabric'][xy[:, 1], xy[:, 0]].sum()),
            'clothClasses': np.unique(evidence['cloth'][xy[:, 1], xy[:, 0]]).astype(int).tolist(),
            'humanClasses': np.unique(evidence['human'][xy[:, 1], xy[:, 0]]).astype(int).tolist(),
            'medianLab': centre.tolist(), 'xy': xy})
    if rows:
        centres = np.array([row['medianLab'] for row in rows], 'float32')
        centre = np.median(centres, axis=0)
        distance = np.linalg.norm(centres-centre, axis=1)
        mad = float(np.median(np.abs(distance-np.median(distance))))
        limit = max(8., 3 * mad)
        keep = []
        for row, delta in zip(rows, distance):
            if delta > limit:
                rejected.append({'index': row['index'], 'reason': 'sample_colour_outlier', 'distanceLab': float(delta)})
            else:keep.append(row)
        rows = keep
    mask = np.zeros(fabric.shape, 'uint8')
    all_xy, patch_indices = [], []
    for row in rows:
        xy = row['xy'];mask[xy[:, 1], xy[:, 0]] = 255
        all_xy.append(xy);patch_indices.append(np.full(len(xy), row['index'], 'uint8'))
    xy = np.vstack(all_xy) if all_xy else np.empty((0, 2), 'int32')
    patch = np.concatenate(patch_indices) if patch_indices else np.empty(0, 'uint8')
    raw_pixels = rgba[xy[:, 1], xy[:, 0]]
    values = lab[xy[:, 1], xy[:, 0]]
    issues = []
    if len(rows) < 3:issues.append('fewer_than_three_clean_independent_source_samples')
    if len(xy) < 25:issues.append('too_few_actual_source_pixels')
    if (mask > 0).mean() > .05:issues.append('sampling_area_cannot_be_full_garment_selection')
    if rows:
        centres = np.array([row['medianLab'] for row in rows], 'float32')
        chroma_range = float(np.linalg.norm(np.quantile(centres[:, 1:], .90, axis=0)
            - np.quantile(centres[:, 1:], .10, axis=0)))
        if chroma_range > 12:issues.append('source_samples_do_not_show_one_representative_colour')
        spatial = np.ptp(np.array([row['pointPixels'] for row in rows]), axis=0)
        if max(spatial) < min(source.size) * .05:issues.append('samples_not_spatially_representative')
        robust = np.median(centres, axis=0)
        nearest = int(np.argmin(np.linalg.norm(values-robust, axis=1)))
        actual_rgb = raw_pixels[nearest, :3].astype(int).tolist()
        target = '#' + ''.join(f'{channel:02x}' for channel in actual_rgb)
        target_source = {'pointPixels': xy[nearest].astype(int).tolist(), 'rgba': raw_pixels[nearest].astype(int).tolist(),
            'lab': values[nearest].astype(float).tolist(), 'robustPatchMedianLab': robust.astype(float).tolist()}
    else:
        chroma_range, target, target_source = None, None, None
    quality = {'accepted': not issues, 'issues': issues, 'cleanSampleCount': len(rows),
        'sourcePixelCount': len(xy), 'selectedPixelCount': int((mask > 0).sum()),
        'selectedFraction': float((mask > 0).mean()), 'invalidSelectedPixels': int(((mask > 0) & ~fabric).sum()),
        'chromaRangeLab': chroma_range, 'sourceFabricL10L90': evidence['sourceFabricL10L90'],
        'semanticGarmentClasses': evidence['classes'], 'rejectedSamples': rejected,
        'requestedClothClass': evidence['requestedClothClass'],
        'kindCorroboratedMismatchPixels': sum(row['kindCorroboratedMismatchPixels'] for row in rows),
        'targetIdentityRequiresIndependentReview': True,
        'samples': [{key: value for key, value in row.items() if key != 'xy'} for row in rows],
        'targetSourcePixel': target_source}
    return Image.fromarray(mask), target, quality, {'xy': xy, 'rgba': raw_pixels, 'patch_index': patch}


def _guard_prior_unknown(root, identity, current):
    for path in Path(root).glob('*/*/receipt.json'):
        if path.resolve() == Path(current).resolve():continue
        try:old = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError):continue
        old_id = old.get('identity', old)
        if old_id.get('sourcePixelSha256') != identity['sourcePixelSha256'] or old_id.get('vision') != identity['vision']:continue
        unresolved = old.get('state') in ('processing', 'unknown')
        for call in list(path.parent.rglob('plan.json')) + list(path.parent.rglob('review.json')):
            try:unresolved |= json.loads(call.read_text('utf-8')).get('state') != 'completed'
            except (OSError, ValueError):unresolved = True
        if unresolved:
            raise ReferenceSampleRejected('同源同模型存在未决取色调用，先对账，未因身份变化重发',
                {'state': 'unknown', 'sampleVerified': False, 'accepted': False,
                    'verificationScope': SCOPE, 'eligibleAsSourceSelection': False,
                    'blockingReceiptPath': str(path), 'blockingReceiptSha256': selection._sha(path.read_bytes())},
                code='reference_sample_unknown')


def _cached(source, receipt, folder):
    mask_path, pixels_path = Path(receipt['maskPath']), Path(receipt['samplePixelsPath'])
    if not selection._within(mask_path, folder) or not selection._within(pixels_path, folder):
        raise ValueError('取色缓存路径越出当前源图')
    if (selection._sha(mask_path.read_bytes()) != receipt['maskPngSha256']
            or selection._sha(pixels_path.read_bytes()) != receipt['samplePixelsSha256']):
        raise ValueError('取色缓存文件哈希不符')
    mask = Image.open(mask_path).convert('L')
    if mask.size != source.size or selection._pixels(mask, 'L') != receipt['maskPixelSha256']:
        raise ValueError('取色样本蒙版像素身份不符')
    with np.load(pixels_path, allow_pickle=False) as data:
        xy, pixels = data['xy'], data['rgba']
        if (xy.ndim != 2 or xy.shape[1] != 2 or pixels.shape != (len(xy), 4) or not len(xy)
                or not np.issubdtype(xy.dtype, np.integer) or (xy < 0).any()
                or (xy[:, 0] >= source.width).any() or (xy[:, 1] >= source.height).any()):
            raise ValueError('取色缓存源像素坐标不符')
        actual = np.asarray(source.convert('RGBA'))[xy[:, 1], xy[:, 0]]
        if not np.array_equal(actual, pixels):raise ValueError('取色缓存包含非当前源图像素')
        expected = np.zeros((source.height, source.width), 'uint8');expected[xy[:, 1], xy[:, 0]] = 255
        if not np.array_equal(expected, np.asarray(mask)):raise ValueError('取色蒙版与实际样本坐标不符')
        rgb = np.array([int(receipt['target'][i:i+2], 16) for i in (1, 3, 5)])
        if not np.any(np.all(pixels[:, :3] == rgb, axis=1)):raise ValueError('缓存目标色不是实际源像素')
    return {'target': receipt['target'], 'mask': mask, 'receipt': {**receipt, 'cacheReused': True}}


def sample(source, kind, *, subject, vision, cache_root, vision_metadata, local_backend=None):
    """Return {target:'#RRGGBB', mask:PIL L, receipt:...}, for target sampling ONLY."""
    if not isinstance(source, Image.Image) or kind not in selection.TARGET or not callable(vision):
        raise ValueError('取色须有原图、upper/lower/full类别和当前账号视觉回调')
    subject = _subject(subject)
    source = source.convert('RGBA')
    if min(source.size) < 16 or max(source.size) > 8192 or source.width*source.height > 18_000_000:
        raise ValueError('取色原图尺寸不支持')
    backend = local_backend or selection.LocalBackend()
    local_identity = backend.identity() if callable(getattr(backend, 'identity', None)) else {
        'adapter': type(backend).__module__ + '.' + type(backend).__qualname__}
    identity = {'version': VERSION, 'algorithmVersion': ALGORITHM_VERSION, 'verificationScope': SCOPE,
        'kind': kind, 'subject': subject, 'sourceSize': list(source.size),
        'sourcePixelSha256': selection._pixels(source, 'RGBA'), 'sourceHashEncoding': 'rgba8_top_to_bottom',
        'vision': copy.deepcopy(vision_metadata or getattr(vision, 'identity', None) or {'provider': 'caller_supplied_unverified'}),
        'localModelIdentity': local_identity}
    # DATA already has a long Windows path. A 128-bit directory key plus FULL
    # identity verification avoids the legacy MAX_PATH failure without silently
    # coalescing collisions. Temporary file names stay short as well.
    identity_sha = selection._sha(selection._json(identity).encode())
    folder = Path(cache_root).resolve() / CACHE_DIR / identity_sha[:32]
    manifest = folder / 'receipt.json'
    with LOCK:
        if manifest.exists():
            receipt = json.loads(manifest.read_text('utf-8'))
            if receipt.get('identity') != identity:
                raise ReferenceSampleRejected('取色缓存身份不符', receipt, code='reference_sample_cache_mismatch')
            if receipt.get('sampleVerified') is True and receipt.get('accepted') is True and receipt.get('verificationScope') == SCOPE:
                try:return _cached(source, receipt, folder)
                except (OSError, ValueError, KeyError) as error:
                    raise ReferenceSampleRejected('取色缓存不符，未重新付费分析：' + str(error), receipt,
                        code='reference_sample_cache_mismatch') from error
            raise ReferenceSampleRejected('已有取色任务未通过或结果未决，保留证据，未重复提交', receipt,
                code='reference_sample_unknown' if receipt.get('state') in ('unknown', 'processing') else 'reference_sample_rejected')
        _guard_prior_unknown(cache_root, identity, manifest)
        folder.mkdir(parents=True, exist_ok=True)
        receipt = {**identity, 'identity': identity, 'identitySha256': identity_sha, 'state': 'processing', 'accepted': False,
            'sampleVerified': False, 'verified': False, 'completeGarmentSelectionVerified': False,
            'eligibleAsSourceSelection': False, 'humanReviewed': False, 'imageGenerationSubmitted': False,
            'cacheManifestPath': str(manifest), 'attempts': [], 'created': time.time()}
        selection._write(manifest, receipt)
        try:
            cloth, human, models = backend.labels(source)
            evidence = _evidence(source, kind, np.asarray(cloth), np.asarray(human))
            receipt['localModels'] = models
            np.savez_compressed(folder / 'local-labels.npz', cloth=cloth, human=human)
            selection._save_image(source, folder / 'source.png')
            previous, current = None, None
            for attempt in range(2):
                attempt_folder = folder / f'a{attempt+1}';attempt_folder.mkdir(exist_ok=True)
                entry = {'number': attempt+1, 'state': 'planning', 'planPath': str(attempt_folder/'plan.json')}
                receipt['attempts'].append(entry)
                selection._write(manifest, receipt)
                context = {'verificationScope': SCOPE, 'kind': kind, 'subject': copy.deepcopy(subject),
                    'sourceSize': list(source.size), 'sourcePixelSha256': identity['sourcePixelSha256'],
                    'attempt': attempt+1, 'previousFailure': previous}
                images = [source] + ([selection._overlay(source, current)] if current is not None else [])
                plan = selection._vision_call(vision, attempt_folder, 'plan', PLAN_INSTRUCTION, context, images)
                entry['plan'] = plan
                try:
                    mask, target, quality, pixels = _extract(source, plan, evidence)
                    selection._save_image(mask, attempt_folder / 'sample-mask.png')
                    overlay = selection._overlay(source, mask);selection._save_image(overlay, attempt_folder / 'overlay.png')
                    np.savez_compressed(attempt_folder / 'sample-pixels.npz', **pixels)
                    entry.update(quality=quality, target=target, state='numeric_rejected',
                        maskPath=str(attempt_folder/'sample-mask.png'),
                        samplePixelsPath=str(attempt_folder/'sample-pixels.npz'))
                    current = mask
                    if target is None or not quality['accepted']:
                        previous = {'numericGate': quality, 'previousPlan': plan}
                        selection._write(manifest, receipt);continue
                    review_context = {**context, 'targetFromSourcePixels': target, 'numericGate': quality,
                        'completeGarmentCoverageRequired': False}
                    reviewed = _review(selection._vision_call(vision, attempt_folder, 'review', REVIEW_INSTRUCTION,
                        review_context, [source, overlay]))
                    entry.update(independentReview=reviewed, reviewPath=str(attempt_folder/'review.json'),
                        state='accepted' if reviewed['accepted'] else 'rejected')
                    if reviewed['accepted']:
                        mask_path, pixel_path = attempt_folder / 'sample-mask.png', attempt_folder / 'sample-pixels.npz'
                        receipt.update(state='accepted', accepted=True, sampleVerified=True, target=target,
                            quality=quality, independentReview=reviewed, completed=time.time(),
                            maskPath=str(mask_path), overlayPath=str(attempt_folder/'overlay.png'),
                            sampleMaskPath=str(mask_path), maskPurpose='reference_colour_sampling',
                            maskPixelSha256=selection._pixels(mask, 'L'), maskHashEncoding='l8_top_to_bottom',
                            maskPngSha256=selection._sha(mask_path.read_bytes()), samplePixelsPath=str(pixel_path),
                            samplePixelsSha256=selection._sha(pixel_path.read_bytes()))
                        selection._write(manifest, receipt)
                        return {'target': target, 'mask': mask, 'receipt': receipt}
                    previous = {'numericGate': quality, 'independentReview': reviewed, 'previousPlan': plan}
                except (ValueError, TypeError) as error:
                    entry.update(state='rejected', error=str(error)[:2000])
                    previous = {'error': str(error), 'previousPlan': plan}
                selection._write(manifest, receipt)
            receipt.update(state='rejected', error='取色经初次分析和一次自动纠正仍未通过，未猜色或发布样本', completed=time.time())
            selection._write(manifest, receipt)
            raise ReferenceSampleRejected(receipt['error'], receipt)
        except ReferenceSampleRejected:raise
        except selection.VisionCallUnknown as error:
            receipt.update(state='unknown', error=str(error)[:2000], accepted=False, sampleVerified=False)
            selection._write(manifest, receipt)
            raise ReferenceSampleRejected('取色视觉调用未决，保留原意图，未自动重发', receipt,
                code='reference_sample_unknown') from error
        except Exception as error:
            receipt.update(state='rejected', error=str(error)[:2000], accepted=False, sampleVerified=False)
            selection._write(manifest, receipt)
            raise ReferenceSampleRejected('取色失败，原证据已保存：'+str(error), receipt) from error
