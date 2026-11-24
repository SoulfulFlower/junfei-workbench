"""Miss-only mask union, followed by fresh unchanged selection gates.

The authenticated caller must fetch QC and selection receipts itself and prove
account/product/task ownership. This module has no credentials or transport.
It edits masks only and never certifies a union from two earlier pass flags.
"""
from pathlib import Path
import copy
import json
import threading
import time

import numpy as np
from PIL import Image
import automatic_garment_selection as selection

VERSION = 'automatic-garment-selection-revision-v2-local-roi'
CACHE_DIR = 'mr1'
LOCK = threading.RLock()
ROI_POLICY = {'sideFractionOfShortSide': .25, 'minimumSidePixels': 128,
    'maximumSidePixels': 256, 'maximumRegions': 6, 'maximumUnionImageFraction': .35,
    'thresholdsAreCorrectionScopeNotQualityPolicy': True}
REVIEW_INSTRUCTION = selection.REVIEW_INSTRUCTION + '''
This CURRENT overlay is a new miss-only union of two masks, with current
source-validated protections removed first. Neither earlier mask pass proves
this merged mask is correct. Inspect the entire current target garment again,
including previously correct cloth under hair loops and beside straps. Check
for both missed fabric AND newly included skin/hair/accessories/background.
Do not infer target ownership merely from similar colour or from a QC miss.
The numeric gate cannot be waived; an ambiguous boundary must not be asserted
correct just because this is an automatic correction. No pixels in the source
image have been changed. This is a fresh selection review, not a colour review.'''
REVIEW_INSTRUCTION += '''
Only candidate alpha INCREASES inside the server-QC miss neighbourhood ROIs
were permitted. Outside them previous alpha was preserved, except CURRENT
source protections/transparent pixels may remove it globally. This scope is
not proof that the previous alpha or the reported miss coordinate is correct.
Inspect the whole merged mask and report leaks or misses anywhere; do not
approve a pre-existing defect because it lies outside the correction ROI.'''


def _revision_rois(size, feedback):
    """Bound added alpha to source-coordinate neighbourhoods of real QC misses."""
    width, height = size
    locations = feedback.get('visualReview', {}).get('locations')
    if not isinstance(locations, list) or not 1 <= len(locations) <= ROI_POLICY['maximumRegions']:
        raise RevisionRejected('局部修订须有1–6个服务器漏选位置')
    side = min(ROI_POLICY['maximumSidePixels'], max(ROI_POLICY['minimumSidePixels'],
        round(min(size)*ROI_POLICY['sideFractionOfShortSide'])))
    union = np.zeros((height, width), 'uint8'); regions = []
    for index, row in enumerate(locations):
        if not isinstance(row, dict) or row.get('kind') != 'miss':raise RevisionRejected('局部修订只接受漏选位置')
        try:x, y = selection._point(row.get('point'), size)
        except (ValueError, TypeError) as error:raise RevisionRejected('局部修订坐标无效') from error
        crop_width, crop_height = min(width, side), min(height, side)
        left = max(0, min(width-crop_width, round(x-crop_width/2)))
        top = max(0, min(height-crop_height, round(y-crop_height/2)))
        bbox = [left, top, left+crop_width, top+crop_height]
        union[top:top+crop_height, left:left+crop_width] = 255
        regions.append({'missIndex': index, 'point': list(row['point']), 'pointPixels': [x, y],
            'bboxPixels': bbox, 'bboxEncoding': 'xyxy_half_open_original_source_pixels'})
    pixels = int((union > 0).sum())
    if pixels > union.size*ROI_POLICY['maximumUnionImageFraction']:
        raise RevisionRejected('漏选修订ROI总范围过大，未扩大为全局重规划')
    return union > 0, {'policy': copy.deepcopy(ROI_POLICY), 'regions': regions,
        'unionPixels': pixels, 'unionImageFraction': pixels/union.size,
        'unionMaskPixelSha256': selection._sha(union.tobytes()), 'maskHashEncoding': 'l8_top_to_bottom'}


class RevisionRejected(ValueError):
    def __init__(self, message, receipt=None, *, code='automatic_revision_rejected'):
        super().__init__(message)
        self.receipt = receipt or {'state': 'rejected', 'accepted': False, 'verified': False}
        self.code = code


def _hash_json(value):return selection._sha(selection._json(value).encode())


def _persist(path, receipt):
    receipt['recordSha256'] = _hash_json({k: v for k, v in receipt.items() if k != 'recordSha256'})
    selection._write(path, receipt)


def _checked_path(value, root):
    if not isinstance(value, str) or not value or not selection._within(value, root):
        raise RevisionRejected('选区证据路径越出当前账号衣物缓存')
    path = Path(value).resolve()
    if not path.exists():raise RevisionRejected('选区证据文件不存在，未猜测或重发')
    return path


def can_revise(feedback):
    """Pure shape/policy check only; NOT ownership or source-binding proof."""
    if not isinstance(feedback, dict):return False
    review, numeric = feedback.get('visualReview'), feedback.get('numeric')
    if not isinstance(review, dict) or not isinstance(numeric, dict):return False
    locations = review.get('locations')
    if (feedback.get('passed') is not False or feedback.get('blocking') is not True
            or feedback.get('nextAction') != 'selection'
            or feedback.get('protectedPartsPreserved') is not True
            or review.get('category') != 'selection' or review.get('blocking') is not True
            or review.get('selectionComplete') is not False
            or any(review.get(k) is not True for k in ('protectedPartsPreserved', 'identityPreserved', 'materialPreserved', 'colourPlausible'))
            or any(type(numeric.get(k)) is not int or numeric[k] != 0 for k in ('outsideChangedPixels', 'alphaChangedPixels'))
            or not isinstance(locations, list) or not 1 <= len(locations) <= ROI_POLICY['maximumRegions']
            or any(not isinstance(row, dict) or row.get('kind') != 'miss' for row in locations)):
        return False
    try:
        for row in locations:
            selection._point(row.get('point'), (100, 100))
            if not isinstance(row.get('reason'), str) or not row['reason'].strip():return False
    except (ValueError, TypeError):return False
    return True


def _feedback(feedback, source, previous):
    if not isinstance(feedback, dict):raise RevisionRejected('须有服务器已核实的实际QC结果')
    binding, review, numeric = feedback.get('binding'), feedback.get('visualReview'), feedback.get('numeric')
    if not all(isinstance(v, dict) for v in (binding, review, numeric)):
        raise RevisionRejected('漏选合并须有完整源/选区绑定及独立QC')
    if any(not isinstance(binding.get(key), dict) for key in ('source', 'mask')):
        raise RevisionRejected('QC源/选区绑定格式不符')
    if (binding.get('source', {}).get('pixelSha256') != selection._pixels(source, 'RGBA')
            or binding.get('mask', {}).get('pixelSha256') != selection._pixels(previous, 'L')
            or binding.get('source', {}).get('size') != list(source.size)
            or binding.get('mask', {}).get('size') != list(source.size)):
        raise RevisionRejected('QC不是当前原片与旧选区的检查')
    if not can_revise(feedback):
        raise RevisionRejected('仅允许已核实的纯漏选且保护物保真的QC进行union；mixed/leak不得合并')
    return copy.deepcopy(feedback)


def _points(value, size):
    if not isinstance(value, dict) or not value.get('foreground') or not value.get('background'):
        raise RevisionRejected('原选区缺少实际前景/背景约束')
    result = copy.deepcopy(value)
    for key in ('foreground', 'background', 'sourceClothAnchors', 'sourceClothRidgePixels'):
        rows = result.get(key, [])
        if not isinstance(rows, list) or len(rows) > 4096:raise RevisionRejected('原选区约束无效')
        for point in rows:
            if (not isinstance(point, list) or len(point) != 2
                    or any(type(v) is not int for v in point)
                    or not 0 <= point[0] < size[0] or not 0 <= point[1] < size[1]):
                raise RevisionRejected('原选区约束坐标无效')
    return result


def _load_evidence(source, candidate, receipt, root, kind, subject):
    if not isinstance(receipt, dict):raise RevisionRejected('须有服务器候选选区回执')
    manifest = _checked_path(receipt.get('cacheManifestPath'), root)
    persisted = json.loads(manifest.read_text('utf-8'))
    supplied = {k: v for k, v in receipt.items() if k != 'cacheReused'}
    if supplied != persisted:raise RevisionRejected('候选选区回执不等于服务器原件')
    if (persisted.get('state') != 'accepted' or persisted.get('verified') is not True
            or persisted.get('accepted') is not True or persisted.get('kind') != kind
            or persisted.get('subject') != subject
            or persisted.get('sourceHashEncoding') != 'rgba8_top_to_bottom'
            or persisted.get('maskHashEncoding') != 'l8_top_to_bottom'
            or persisted.get('sourceSize') != list(source.size)
            or persisted.get('sourcePixelSha256') != selection._pixels(source, 'RGBA')
            or persisted.get('maskPixelSha256') != selection._pixels(candidate, 'L')):
        raise RevisionRejected('候选选区未验收或源/蒙版/商品身份不符')
    run = _checked_path(persisted.get('runPath'), root)
    mask_path = _checked_path(persisted.get('maskPath'), run)
    if selection._sha(mask_path.read_bytes()) != persisted.get('maskPngSha256'):
        raise RevisionRejected('候选mask PNG哈希不符')
    saved_mask = Image.open(mask_path).convert('L')
    if saved_mask.size != source.size or selection._pixels(saved_mask, 'L') != selection._pixels(candidate, 'L'):
        raise RevisionRejected('候选mask原件像素不符')
    source_path = _checked_path(str(run/'source.png'), run)
    saved_source = Image.open(source_path).convert('RGBA')
    if saved_source.size != source.size or selection._pixels(saved_source, 'RGBA') != selection._pixels(source, 'RGBA'):
        raise RevisionRejected('候选选区源图原件不符')
    attempts = persisted.get('attempts')
    if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
        raise RevisionRejected('候选选区缺少末轮证据')
    entry = attempts[-1]
    if entry.get('state') != 'accepted' or type(entry.get('number')) is not int or not 1 <= entry['number'] <= 3:
        raise RevisionRejected('候选末轮没有通过记录')
    attempt = run / f"attempt-{entry['number']:02}"
    names = {'labels': run/'local-labels.npz', 'source': run/'source.png',
        'protection': attempt/'protection.png', 'domain': attempt/'candidate-domain.png',
        'candidate': mask_path}
    for path in names.values():_checked_path(str(path), run)
    protection = Image.open(names['protection']).convert('L')
    domain = Image.open(names['domain']).convert('L')
    if protection.size != source.size or domain.size != source.size:
        raise RevisionRejected('候选保护/独立domain尺寸不符')
    compiled = entry.get('compiled')
    if not isinstance(compiled, dict):raise RevisionRejected('候选缺少compiled源证据')
    expected_protection = compiled.get('automaticSourceConstraints', {}).get('protectedPixelSha256After')
    if not expected_protection or selection._pixels(protection, 'L') != expected_protection:
        raise RevisionRejected('实际保护原件与原compiled哈希不符')
    points = _points(entry.get('points'), source.size)
    with np.load(names['labels'], allow_pickle=False) as labels:
        if set(labels.files) != {'cloth', 'human'}:raise RevisionRejected('本地原始标签集合不符')
        base = selection._local_evidence(source, kind, labels['cloth'], labels['human'], None)
    # Recompute from the source evidence; original explicit/instance/background
    # protections remain included. No earlier protection is subtracted.
    saved = np.asarray(protection) > 0
    effective_protection = Image.fromarray((saved | base['protected']).astype('uint8') * 255)
    # Reproduce prepare's exact ordering: original local evidence remains
    # unchanged and compiled protection is a separate recovery argument. The
    # stronger union protection above is used only for the NEW mask and gate.
    evidence, recovery = selection._recover_domain(source, base, points, protection)
    if selection._pixels(evidence['coarse'], 'L') != selection._pixels(domain, 'L'):
        raise RevisionRejected('保存candidate-domain与当前源标签/约束重算不符')
    domain_sha = compiled.get('candidateDomainRecovery', {}).get('effectiveDomainPixelSha256')
    if domain_sha and domain_sha != selection._pixels(domain, 'L'):
        raise RevisionRejected('candidate-domain与原compiled哈希不符')
    original_quality = selection._quality(candidate, source, points, protection, evidence)
    if not original_quality['accepted']:raise RevisionRejected('候选在原数字门禁重算未通过')
    provenance = {'candidateReceiptPath': str(manifest), 'candidateReceiptSha256': selection._sha(manifest.read_bytes()),
        'artifacts': {key: {'path': str(path), 'sha256': selection._sha(path.read_bytes())} for key, path in names.items()},
        'pointsSha256': _hash_json(points), 'candidateDomainPixelSha256': selection._pixels(domain, 'L'),
        'storedProtectionPixelSha256': selection._pixels(protection, 'L'),
        'effectiveProtectionPixelSha256': selection._pixels(effective_protection, 'L'),
        'localLabelsHashScope': 'observed_now_bound_to_derived_identity; original_selection_has_no_label_file_hash',
        'candidateNumericRecheck': original_quality, 'domainRecomputation': recovery}
    return persisted, points, effective_protection, evidence, provenance


def _guard_unknown(root, identity, current):
    for path in Path(root).glob('*/*/receipt.json'):
        if path.resolve() == current.resolve():continue
        try:old = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError):continue
        if old.get('sourcePixelSha256') != identity['sourcePixelSha256'] or old.get('vision') != identity['vision']:continue
        unresolved = old.get('state') in ('processing', 'unknown')
        review = path.parent/'review.json'
        if review.exists():
            try:unresolved |= json.loads(review.read_text('utf-8')).get('state') != 'completed'
            except (OSError, ValueError):unresolved = True
        if unresolved:raise RevisionRejected('同源同模型存在未决合并复核，先对账，未重新提交',
            {**old, 'blockingReceiptPath': str(path)}, code='automatic_revision_unknown')


def revise(source, previous_mask, candidate_mask, candidate_receipt, *, kind, subject,
           vision, cache_root, garment_cache_root, vision_metadata, feedback):
    """Return (merged L mask, new receipt), or an explicit fail-closed error.

    All receipts/feedback MUST come from server-owned lookups after ownership
    checks. This module validates image identities, not account authorization.
    One fresh review only; no generation, local re-planning or correction loop.
    """
    if not isinstance(source, Image.Image) or kind not in selection.TARGET or not callable(vision):
        raise RevisionRejected('须有原图、明确品类与当前账号视觉回调')
    if any(not isinstance(mask, Image.Image) or mask.size != source.size for mask in (previous_mask, candidate_mask)):
        raise RevisionRejected('修订蒙版须与原图同尺寸')
    source = source.convert('RGBA'); previous_mask = previous_mask.convert('L'); candidate_mask = candidate_mask.convert('L')
    if source.width * source.height > 40_000_000 or min(source.size) < 16 or max(source.size) > 8192:
        raise RevisionRejected('修订原图尺寸不支持')
    subject = selection._subject(subject)
    if not subject or subject.get('role') != 'source_garment':raise RevisionRejected('修订须绑定当前源商品subject')
    if not isinstance(vision_metadata, dict) or not vision_metadata:raise RevisionRejected('须绑定实际视觉模型身份')
    feedback = _feedback(feedback, source, previous_mask)
    allowed_increase, roi_scope = _revision_rois(source.size, feedback)
    with LOCK:
        try:
            candidate, points, protection, evidence, provenance = _load_evidence(
                source, candidate_mask, candidate_receipt, garment_cache_root, kind, subject)
        except RevisionRejected:raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise RevisionRejected('候选源证据读取或核验失败，未提交复核：' + str(error)) from error
        previous_array, candidate_array = np.asarray(previous_mask), np.asarray(candidate_mask)
        outside_increase = (candidate_array > previous_array) & ~allowed_increase
        outside_new = (previous_array == 0) & (candidate_array > 0) & ~allowed_increase
        ys, xs = np.nonzero(outside_increase)
        suppressed = {'alphaIncreasePixels': int(outside_increase.sum()), 'newSelectedPixels': int(outside_new.sum()),
            'bboxPixels': None if not len(xs) else [int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1],
            'bboxEncoding': 'xyxy_half_open_original_source_pixels',
            'alphaIncreaseMaskPixelSha256': selection._sha((outside_increase.astype('uint8')*255).tobytes()),
            'newSelectedMaskPixelSha256': selection._sha((outside_new.astype('uint8')*255).tobytes()),
            'maskHashEncoding': 'l8_top_to_bottom'}
        identity = {'version': VERSION, 'selectionVersion': selection.VERSION,
            'selectionAlgorithmVersion': selection.ALGORITHM_VERSION, 'kind': kind, 'subject': subject,
            'sourceSize': list(source.size), 'sourceHashEncoding': 'rgba8_top_to_bottom',
            'sourcePixelSha256': selection._pixels(source, 'RGBA'),
            'previousMaskPixelSha256': selection._pixels(previous_mask, 'L'),
            'candidateMaskPixelSha256': selection._pixels(candidate_mask, 'L'),
            'correctionScope': roi_scope,
            'suppressedCandidateChanges': suppressed,
            'feedbackSha256': _hash_json(feedback), 'provenanceSha256': _hash_json(provenance),
            'vision': copy.deepcopy(vision_metadata), 'instructionSha256': selection._sha(REVIEW_INSTRUCTION.encode())}
        key = _hash_json(identity); folder = Path(cache_root).resolve()/CACHE_DIR/key[:32]
        manifest = folder/'receipt.json'
        if manifest.exists():
            old = json.loads(manifest.read_text('utf-8'))
            if old.get('identity') != identity:raise RevisionRejected('修订缓存身份不符', old, code='automatic_revision_cache_mismatch')
            if old.get('recordSha256') != _hash_json({k: v for k, v in old.items() if k != 'recordSha256'}):
                raise RevisionRejected('修订缓存回执哈希不符', old, code='automatic_revision_cache_mismatch')
            if old.get('state') == 'accepted' and old.get('verified') is True and old.get('accepted') is True:
                mask_path = _checked_path(old.get('maskPath'), folder)
                mask = Image.open(mask_path).convert('L')
                if (selection._sha(mask_path.read_bytes()) != old.get('maskPngSha256') or mask.size != source.size
                        or selection._pixels(mask, 'L') != old.get('maskPixelSha256')):
                    raise RevisionRejected('修订mask缓存哈希不符', old, code='automatic_revision_cache_mismatch')
                for name, digest in old.get('artifactSha256', {}).items():
                    if name not in {'source.png', 'mask.png', 'protect.png', 'overlay.png', 'roi.png', 'review.json'}:
                        raise RevisionRejected('修订缓存资产名不符', old, code='automatic_revision_cache_mismatch')
                    artifact = _checked_path(str(folder/name), folder)
                    if selection._sha(artifact.read_bytes()) != digest:
                        raise RevisionRejected('修订缓存资产哈希不符', old, code='automatic_revision_cache_mismatch')
                if set(old.get('artifactSha256', {})) != {'source.png', 'mask.png', 'protect.png', 'overlay.png', 'roi.png', 'review.json'}:
                    raise RevisionRejected('修订缓存缺少完整原件哈希', old, code='automatic_revision_cache_mismatch')
                return mask, {**old, 'cacheReused': True}
            raise RevisionRejected('已有修订失败或未决，保留证据，未重新复核', old,
                code='automatic_revision_unknown' if old.get('state') in ('processing', 'unknown') else 'automatic_revision_rejected')
        _guard_unknown(cache_root, identity, manifest)
        folder.mkdir(parents=True, exist_ok=True)
        receipt = {**identity, 'identity': identity, 'identitySha256': key, 'state': 'processing',
            'accepted': False, 'verified': False, 'humanReviewed': False, 'imageGenerationSubmitted': False,
            'cacheManifestPath': str(manifest), 'runPath': str(folder), 'created': time.time(),
            'derivedProvenance': provenance, 'attempts': copy.deepcopy(candidate['attempts'])}
        _persist(manifest, receipt)
        try:
            previous = np.asarray(previous_mask); proposed = np.asarray(candidate_mask)
            protected = np.asarray(protection) > 0
            union = previous.copy()
            union[allowed_increase] = np.maximum(previous[allowed_increase], proposed[allowed_increase])
            removed = protected | (np.asarray(source.getchannel('A')) == 0)
            union[removed] = 0
            mask = Image.fromarray(union)
            quality = selection._quality(mask, source, points, protection, evidence)
            receipt['quality'] = quality
            receipt['revision'] = {'method': 'roi_limited_max_previous_candidate_then_global_source_protection_zero',
                'correctionScope': roi_scope,
                'suppressedCandidateChanges': suppressed,
                'previousSelectedPixels': int((previous > 0).sum()),
                'previousSelectedRetainedPixels': int(((previous > 0) & (union >= previous)).sum()),
                'previousSelectedRemovedForProtectionPixels': int(((previous > 0) & removed).sum()),
                'previousSelectedReducedOutsideProtectionPixels': int(((union < previous) & ~removed).sum()),
                'newSelectedPixels': int(((previous == 0) & (union > 0)).sum()),
                'candidateAlphaIncreasePixelsOutsideROISuppressed': int(((proposed > previous) & ~allowed_increase).sum()),
                'candidateNewPixelsOutsideROISuppressed': int(((previous == 0) & (proposed > 0) & ~allowed_increase).sum()),
                'candidateAlphaIncreaseAmountOutsideROISuppressed': int(np.maximum(proposed.astype('int16')-previous.astype('int16'), 0)[~allowed_increase].sum()),
                'finalAlphaIncreasePixelsOutsideROI': int(((union > previous) & ~allowed_increase).sum()),
                'outsideROIAlphaDecreaseForProtectionPixels': int(((union < previous) & ~allowed_increase & removed).sum()),
                'effectiveProtectionPixelSha256': selection._pixels(protection, 'L')}
            if receipt['revision']['finalAlphaIncreasePixelsOutsideROI'] != 0:
                raise RevisionRejected('局部修订在ROI外新增alpha，未提交复核', receipt)
            selection._save_image(source, folder/'source.png'); selection._save_image(mask, folder/'mask.png')
            selection._save_image(protection, folder/'protect.png')
            selection._save_image(Image.fromarray(allowed_increase.astype('uint8')*255), folder/'roi.png')
            overlay = selection._overlay(source, mask); selection._save_image(overlay, folder/'overlay.png')
            context = {'kind': kind, 'subject': copy.deepcopy(subject), 'numericGate': quality,
                'revision': receipt['revision'], 'sourcePixelSha256': identity['sourcePixelSha256'],
                'previousMaskPixelSha256': identity['previousMaskPixelSha256'],
                'candidateMaskPixelSha256': identity['candidateMaskPixelSha256'],
                # Full server QC is hashed above, but its raw model response,
                # image URLs and earlier prompts are not replayed as context.
                'feedback': {'qualityId': feedback.get('qualityId'), 'nextAction': feedback['nextAction'],
                    'category': feedback['visualReview']['category'],
                    'locations': copy.deepcopy(feedback['visualReview']['locations']),
                    'protectedPartsPreserved': True},
                'priorFlagsDoNotCertifyMergedMask': True}
            reviewed = selection._review(selection._vision_call(vision, folder, 'review',
                REVIEW_INSTRUCTION.replace('{kind}', kind), context, [source, overlay]))
            passed = quality['accepted'] and reviewed['accepted']
            receipt.update(state='accepted' if passed else 'rejected', accepted=passed, verified=passed,
                revisionReview=reviewed, independentReview=reviewed, completed=time.time(),
                maskPath=str(folder/'mask.png'), overlayPath=str(folder/'overlay.png'),
                maskHashEncoding='l8_top_to_bottom', maskPixelSha256=selection._pixels(mask, 'L'),
                maskPngSha256=selection._sha((folder/'mask.png').read_bytes()))
            # Preserve current compiled paths for downstream detail QC, while
            # clearly replacing their original mask review with this new one.
            last = receipt['attempts'][-1]
            last['beforeRevisionQuality'] = last.get('quality')
            last.update(quality=quality, independentReview=reviewed, state=receipt['state'], revision=True)
            receipt['artifactSha256'] = {name: selection._sha((folder/name).read_bytes()) for name in
                ('source.png', 'mask.png', 'protect.png', 'overlay.png', 'roi.png', 'review.json')}
            _persist(manifest, receipt)
            if not passed:raise RevisionRejected('合并后的原数字门禁或新独立复核未通过', receipt)
            return mask, receipt
        except RevisionRejected:raise
        except selection.VisionCallUnknown as error:
            receipt.update(state='unknown', accepted=False, verified=False, error=str(error)[:2000])
            _persist(manifest, receipt)
            raise RevisionRejected('合并选区复核结果未决，保留原意图，未重发', receipt,
                code='automatic_revision_unknown') from error
        except Exception as error:
            receipt.update(state='rejected', accepted=False, verified=False, error=str(error)[:2000])
            _persist(manifest, receipt)
            raise RevisionRejected('合并工具失败，未交付蒙版：' + str(error), receipt) from error
