"""Bounded, source-bound garment selection; no product-coordinate fixtures.

The caller supplies the authenticated account's Codex vision callback. Only
local segmentation/matting operates on pixels. Accepted selections require both
numeric gates and an independent source/overlay vision review. Historical
explicit masks remain outside this module and are never overwritten.
"""
from pathlib import Path
import ast
import copy
import hashlib
import io
import json
import math
import re
import threading
import time
import numpy as np
import cv2
from PIL import Image
import garment_component_proposals

VERSION = 'automatic-garment-selection-v1'
ALGORITHM_VERSION = 'source-conserving-planner-proposals-v8'
LOCK = threading.RLock()
TARGET = {'upper': 1, 'lower': 2, 'full': 3}
HUMAN_CLOTH = {'upper': (4,), 'lower': (5, 6), 'full': (7,)}
NEGATIVE_KINDS = {'background', 'skin', 'hair', 'accessory', 'other_garment', 'gap'}

PLAN_INSTRUCTION = '''Identify the CURRENT {kind} garment in source image 1. This is
an automatic tool call, not a request for a user to paint a mask. Image 2 is only
a coarse local selection overlay: blue means selected, natural colour means
not selected. It may miss light sleeves or include bags/straps/hair. SOURCE
PIXELS are authoritative; do not copy coarse mask mistakes. Do not infer hidden
fabric under hair, hands, bags or straps.
Use context.subject only as the caller's saved product identity/role, never as
proof of invisible facts. Select that product, not every upper-body garment.
An inner shirt and an outer jacket can share the same parser label and colour.
Return JSON ONLY:
{"foreground":[{"point":[u,v],"part":"visible garment component","evidence":"what is visibly cloth"}],
 "background":[{"point":[u,v],"kind":"background|skin|hair|accessory|other_garment|gap","evidence":"visible reason"}],
 "protections":[{"kind":"accessory|skin|hair|other_garment","path":[[u,v],[u,v]],"widthFraction":0.01,"evidence":"visible narrow occluder"}],
 "visibleParts":["..."],"limitations":["..."]}
All coordinates are NORMALIZED 0..1 in the ORIGINAL image, not the displayed
thumbnail. Give 3-12 well-spaced positive points across visible torso, sleeves,
collar/hem or legs and any missed cloth islands. Give 4-24 negative points on
actual skin, hair, accessories, surrounding background and visible openings.
Do not put negative points on garment shadows, pale highlights, stitching or
material transitions. Pale long sleeves are not bare arms. Smooth sleeves and
quilted torso can be the same garment. Do not put positive points on a belt,
bag or its strap, a phone, hair or another garment.
Narrow protection paths are for thin visible occluders such as a bag strap.
Their widthFraction is relative to min(image width,height), at most 0.04.
Keep previously correct source-supported points, including repaired visible
cloth islands, when adding a newly missed component. Do not forget an earlier
corrected defect merely because the latest review found another one.
Never draw a broad garment polygon or blanket over the torso. Do not claim a
human review, a successful result, or unseen private-model behaviour.'''

PLAN_PROPOSAL_INSTRUCTION = '''
Image 3, when present, contains enlarged SOURCE / HYPOTHESIS crop pairs from
context.sourceProposals. These are unverified possible visible cloth islands,
not a complete mask, not same-product proof, and never permission to fill
hidden fabric. Inspect real source structure and reject any wrong garment,
skin, hair, accessory or background hypothesis. If a source-visible proposal
belongs to the CURRENT target, you may explicitly choose its actual interior
point using the ORIGINAL normalized coordinates in its context (not montage
coordinates). Your normal evidence/foreground schema and every existing local
and independent review gate still apply. Do not adopt a candidate automatically.
'''

REVIEW_INSTRUCTION = '''Independently inspect original source image 1 and the
CURRENT selection overlay image 2. Use context.subject to identify the saved
target product; another upper-body garment is still excluded. Blue pixels will be recoloured; natural
pixels will remain original. Judge the CURRENT {kind} garment only, against the
source, including full view and fine boundaries. Check every visible sleeve or
leg, collar, cuffs, hem, source-visible seams/material panels; especially pale
sleeves mislabelled as arms. Skin, hair, bag straps, bags, phones, other garments
and actual background/gaps must remain outside. Do not invent hidden fabric.
Return JSON ONLY:
{"accepted":true_or_false,"issues":["concrete defects"],"warnings":["minor nonblocking edge observations"],
 "misses":[{"point":[u,v],"part":"visible missed fabric","evidence":"source observation"}],
 "leaks":[{"point":[u,v],"kind":"skin|hair|accessory|other_garment|background|gap","evidence":"source observation"}]}
Coordinates are normalized in the ORIGINAL image. A large missing cloth area,
dyed occluder, lost gap or boundary spill is a failure, even when numeric
coverage is high. Minor mixed-edge antialiasing can be noted without demanding
invented detail. accepted=true requires issues/misses/leaks to be empty. Never
claim human approval. This review cannot alter the source or waive any gate.'''


class SelectionRejected(ValueError):
    def __init__(self, message, receipt, *, code='automatic_selection_rejected'):
        super().__init__(message)
        self.receipt = receipt
        self.code = code


class VisionCallUnknown(RuntimeError):
    pass


class VisionIntentConflict(RuntimeError):
    pass


class PlanValidationError(ValueError):
    def __init__(self,message,diagnostics):
        super().__init__(message)
        self.point_diagnostics=diagnostics


def _sam_point_contradiction(error):
    return isinstance(error, (str, ValueError)) and re.fullmatch(
        r'Selection contradicts garment points \[.*\] or protection points \[.*\]', str(error)) is not None


def _within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def local_failure_resume_info(receipt, folder, cache_root):
    """Read-only eligibility check; never resets unknown/completed model calls."""
    folder = Path(folder)
    if receipt.get('state') != 'rejected' or receipt.get('verified') is not False or receipt.get('accepted') is not False:
        return {'eligible': False, 'reason': 'not_a_known_rejected_local_failure'}
    run_path = Path(receipt.get('runPath') or folder)
    if not _within(run_path, folder):
        return {'eligible': False, 'reason': 'local_run_not_inside_source_cache'}
    plans = sorted(run_path.glob('attempt-*/plan.json'))
    if not plans:
        return {'eligible': False, 'reason': 'no_completed_plan_to_reuse'}
    for path in list(folder.rglob('plan.json')) + list(folder.rglob('review.json')):
        try:
            stored = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError):
            return {'eligible': False, 'reason': 'unreadable_visual_call_record'}
        if stored.get('state') != 'completed':
            return {'eligible': False, 'reason': 'visual_call_pending_or_unknown'}
    attempts = receipt.get('attempts', [])
    if (attempts and all(a.get('state') == 'rejected' and _sam_point_contradiction(a.get('error', ''))
            and a.get('compiled') and not a.get('quality') and not a.get('independentReview') for a in attempts)):
        return {'eligible': True, 'reason': 'known_local_sam_point_contradiction', 'failure': {
            'exceptionType': 'ValueError', 'stage': 'local_select',
            'errors': [a['error'] for a in attempts]}, 'originalRunPath': str(run_path)}
    failure = receipt.get('localFailure')
    if isinstance(failure, dict):
        if (failure.get('exceptionType') not in ('OSError', 'FileNotFoundError', 'PermissionError', 'IsADirectoryError', 'NotADirectoryError')
                or failure.get('errno') not in (2, 3, 13, 20, 21, 28, 36, 206)
                or failure.get('stage') not in ('local_select', 'local_matte', 'persist_local_images', 'persist_acceptance')
                or not failure.get('filename') or not _within(failure['filename'], cache_root)):
            return {'eligible': False, 'reason': 'failure_is_not_an_identified_local_cache_io_error'}
        return {'eligible': True, 'reason': 'known_local_cache_io_error', 'failure': copy.deepcopy(failure),
            'originalRunPath': str(run_path)}
    # Compatibility with the first deployed version, which retained str(error)
    # but did not yet store typed localFailure metadata. Admit only the exact
    # local embedding-write pattern, never a generic rejected/transport error.
    error = receipt.get('error', '')
    match = re.fullmatch(r'\[Errno (2|3|36|206)\] [^:]+: (.+)', error) if isinstance(error, str) else None
    try:
        filename = ast.literal_eval(match.group(2)) if match else None
    except (ValueError, SyntaxError):
        filename = None
    if (not isinstance(filename, str) or not filename.endswith('.npz')
            or not _within(filename, folder / 'embeddings')
            or not receipt.get('attempts') or any(a.get('quality') or a.get('independentReview') for a in receipt['attempts'])):
        return {'eligible': False, 'reason': 'legacy_failure_is_not_a_known_embedding_write'}
    return {'eligible': True, 'reason': 'legacy_embedding_write_error', 'failure': {
        'exceptionType': 'FileNotFoundError', 'errno': int(match.group(1)),
        'filename': filename, 'stage': 'local_select', 'legacyError': error}, 'originalRunPath': str(run_path)}


def _archive_local_failure(manifest, info):
    raw = Path(manifest).read_bytes()
    digest = _sha(raw)
    # Keep this short: the source cache directory itself may already be long
    # on Windows. Content-addressed name is immutable and never overwritten.
    backup = Path(manifest).parent / ('lf-' + digest[:12] + '.json')
    if backup.exists():
        if backup.read_bytes() != raw:
            raise ValueError('旧本地失败备份内容不符，未覆盖或继续')
    else:
        with backup.open('xb') as stream:
            stream.write(raw)
    return {'previousReceiptPath': str(backup), 'previousReceiptSha256': digest,
        'reason': info['reason'], 'failure': info['failure'], 'resumedAt': time.time(),
        'originalRunPath': info.get('originalRunPath', str(Path(manifest).parent))}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pixels(image, mode):
    return _sha(image.convert(mode).tobytes())


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(_json(value), encoding='utf-8')
    temp.replace(path)


def _save_image(image, path):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    image.save(tmp, 'PNG')
    tmp.replace(path)


def _point(value, size):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in value)):
        raise ValueError('视觉选点须为0–1归一化坐标')
    return [round(value[0] * (size[0] - 1)), round(value[1] * (size[1] - 1))]


def _evidence(row):
    return isinstance(row.get('evidence'), str) and bool(row['evidence'].strip()) and len(row['evidence']) <= 1500


def _overlay(source, mask):
    rgb = np.asarray(source.convert('RGB')).astype('float32')
    weight = np.asarray(mask.convert('L'), dtype='float32') / 255 * .55
    blue = np.array([18, 139, 247], 'float32')
    return Image.fromarray(np.rint(rgb * (1 - weight[:, :, None]) + blue * weight[:, :, None]).clip(0, 255).astype('uint8'))


class LocalBackend:
    """Adapter to the existing pinned local models and pixel selection tools."""
    def identity(self):
        import garment_auto
        return {'selectionVersion': garment_auto.VERSION,
            'clothingManifest': copy.deepcopy(garment_auto.parser().manifest),
            'humanManifest': copy.deepcopy(garment_auto.human_parser().manifest)}

    def labels(self, source):
        import garment_auto
        cloth_model = garment_auto.parser()
        human_model = garment_auto.human_parser()
        return cloth_model.predict(source), human_model.predict(source), {
            'clothing': copy.deepcopy(cloth_model.manifest),
            'human': copy.deepcopy(human_model.manifest),
            'selectionVersion': garment_auto.VERSION,
        }

    def select(self, source, coarse, protected, points, cache):
        import garment_workflow
        diagnostics = []
        # Single-positive decodes can choose fragmented pieces and contradict
        # other correct garment points. Ask SAM about all verified positives
        # jointly before any bounded local fallback.
        try:
            with garment_workflow.LOCK:
                model = garment_workflow.selector(cache)
                proposal, sam_receipt = model.select(source, points['foreground'], points['background'])
            branch = 'joint_sam_then_source_grabcut'
            diagnostics.append({'method': 'joint_sam', 'accepted': True, 'receipt': sam_receipt})
        except ValueError as error:
            if not _sam_point_contradiction(error):
                raise
            diagnostics.append({'method': 'joint_sam', 'accepted': False, 'error': str(error)})
            # This is only a local proposal branch, never an accepted semantic
            # mask. Actual source-pixel GrabCut still obeys all verified points,
            # explicit protection, later matting and independent review.
            proposal = coarse.copy()
            branch = 'source_grabcut_after_joint_sam_contradiction'
        refinement_points = points['foreground'] + points.get('sourceClothAnchors', [])
        if points.get('sourceClothRidgePixels'):
            refined = _refine_source_cloth(source, proposal, points, protected)
        else:
            refined = garment_workflow.GarmentSelector.refine(source, proposal,
                points['background'], protected, refinement_points)
        refined = garment_workflow.prompted_components(refined, refinement_points)
        final = garment_workflow.combine(coarse, refined, protected, 'replace')
        return final, {'branch': branch, 'samDiagnostics': diagnostics,
            'foreground': copy.deepcopy(points['foreground']), 'background': copy.deepcopy(points['background']),
            'sourceClothAnchors': copy.deepcopy(points.get('sourceClothAnchors', [])),
            'sourceClothRidgePixelCount': len(points.get('sourceClothRidgePixels', [])),
            'sourcePixelRefinement': 'source_GrabCut_with_dual_semantic_thin_cloth_ridges'
                if points.get('sourceClothRidgePixels') else 'existing_GarmentSelector.refine_GrabCut',
            'numericAndIndependentReviewRequired': True, 'imageGenerationSubmitted': False, 'humanReviewed': False}

    def matte(self, source, mask, protected, points):
        from local_mask_recolor import fabric_matte
        alpha = fabric_matte(source, mask, protected, radius=2,
            foreground_seeds=points['foreground'] + points.get('sourceClothAnchors', [])
                + points.get('sourceClothRidgePixels', []),
            background_seeds=points['background'])
        return Image.fromarray(np.rint(np.clip(alpha, 0, 1) * 255).astype('uint8')), {
            'method': 'existing_closed_form_fabric_matte', 'radius': 2,
        }


def _local_evidence(source, kind, cloth, human, explicit):
    if cloth.shape != (source.height, source.width) or human.shape != cloth.shape:
        raise ValueError('本地语义尺寸与原图不匹配')
    if not np.isin(cloth, [0, 1, 2, 3]).all() or not np.isin(human, np.arange(18)).all():
        raise ValueError('本地模型标签超出固定类别范围')
    opaque_source = np.asarray(source.convert('RGBA').getchannel('A')) > 0
    primary = (cloth == TARGET[kind]) & opaque_source
    # Strong requested-kind evidence from the clothing parser can bridge a
    # HUMAN garment subtype error (e.g. trousers called upper clothing). Human
    # skin/arm/hair/accessory labels never participate in this bridge.
    consensus = primary & np.isin(human, [4, 5, 6, 7])
    core = cv2.erode(consensus.astype('uint8'), np.ones((5, 5), 'uint8')) > 0
    if core.sum() < 100:
        core = cv2.erode(primary.astype('uint8'), np.ones((5, 5), 'uint8')) > 0
    if core.sum() < max(50, primary.size * .001):
        raise ValueError('本地模型未提供足够独立衣料种子，未认证整幅为商品')
    lab = cv2.cvtColor(np.asarray(source.convert('RGB'), dtype='float32') / 255, cv2.COLOR_RGB2LAB)
    samples = lab[core]
    # Several material/shadow clusters preserve real fabric variation; a single
    # colour name or a handpicked product-specific RGB never defines ownership.
    samples = samples[::max(1, len(samples) // 8000)]
    cv2.setRNGSeed(0)
    k = min(4, max(1, len(samples) // 30))
    _, assignments, centres = cv2.kmeans(samples.astype('float32'), k, None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, .2), 1, cv2.KMEANS_PP_CENTERS)
    weights = np.bincount(assignments.ravel(), minlength=len(centres)) / len(samples)
    dominant = centres[int(weights.argmax())]
    related_shade = (np.linalg.norm(centres[:, 1:] - dominant[1:], axis=1) < 8) & (np.abs(centres[:, 0] - dominant[0]) < 30)
    centres = centres[(weights >= .15) | related_shade]
    distance = np.min(np.stack([np.linalg.norm(lab - centre, axis=2) for centre in centres]), axis=0)
    # Ambiguous arm labels on independently seen cloth remain uncertain rather
    # than becoming unconditional background. Strong face/accessory evidence
    # and source colours still protect real anatomy and occluders.
    anatomy = np.isin(human, [1, 3, 9, 10, 11, 12, 13, 14, 15, 16, 17])
    protected = anatomy & (~primary | (distance > 18))
    protected |= (human == 2) & (distance > 12)
    other = ((cloth == 2) & np.isin(human, [5, 6])) if kind == 'upper' else (
        (cloth == 1) & (human == 4)) if kind == 'lower' else np.zeros(primary.shape, bool)
    protected |= other
    # Protect confident interiors without growing a semantic classification
    # error across a real neighbouring sleeve.
    protected = cv2.erode(protected.astype('uint8'), np.ones((3, 3), 'uint8')) > 0
    protected |= ~opaque_source
    if explicit is not None:
        if explicit.size != source.size:
            raise ValueError('显式保护区尺寸与原图不一致')
        protected |= np.asarray(explicit.convert('L')) > 0
    coarse = Image.fromarray((primary & ~protected).astype('uint8') * 255)
    semantic_classes = list(HUMAN_CLOTH[kind])
    # A hanging long jacket can be called a dress by SCHP while U2Net calls
    # multiple visible parts upper clothing. This is a measured disagreement,
    # not permission to include every other garment class.
    if kind in ('upper', 'lower') and int((primary & (human == 7)).sum()) >= max(50, primary.size * .001):
        semantic_classes.append(7)
    return {'primary': primary, 'consensus': consensus, 'human': human,
        'distance': distance, 'protected': protected, 'other': other, 'coarse': coarse,
        'fabricCentresLab': centres.tolist(), 'cloth': cloth, 'kind': kind,
        'sourceLab': lab, 'sourceRGB': np.asarray(source.convert('RGB')),
        'opaqueSource': opaque_source, 'semanticGarmentClasses': semantic_classes}


def _semantic_point_support(evidence, x, y):
    """An independently parsed cloth patch can contradict one category label.

    Requiring agreement with U2Net's upper/lower/full class discarded quilted
    jackets classified as full garments. Human clothing evidence must occupy a
    real source neighbourhood, not a single noisy point or an anatomy label.
    """
    human = evidence['human']
    target = np.isin(human, evidence['semanticGarmentClasses'])
    y0, y1 = max(0, y - 2), min(human.shape[0], y + 3)
    x0, x1 = max(0, x - 2), min(human.shape[1], x + 3)
    return bool(target[y, x] and target[y0:y1, x0:x1].mean() >= .6
        and evidence['opaqueSource'][y, x])


def _foreground_supported(evidence,x,y):
    primary_supported=(evidence['primary'][y,x] and not (
        evidence['human'][y,x]==0 and evidence['distance'][y,x]>=16))
    return bool(not evidence['protected'][y,x] and (primary_supported
        or _semantic_point_support(evidence,x,y)
        or (evidence['human'][y,x] in (4,5,6,7) and evidence['distance'][y,x]<16)))


def _recover_domain(source, evidence, points, protection):
    """Propose source-supported missed parts; this is never an acceptance gate.

    The original independent protections are immutable. Each recovered source
    component needs a validated automatic foreground anchor, the requested
    human clothing class, and agreement with observed source fabric colours.
    No colour name, product coordinate, polygon, generated pixels or final
    candidate output participates in this proposal.
    """
    primary = evidence['primary']
    protected = np.asarray(protection.convert('L')) > 0
    lab = evidence['sourceLab']
    anchors = [(x, y) for x, y in points['foreground'] if _semantic_point_support(evidence, x, y)]
    audit = {'algorithmVersion': ALGORITHM_VERSION, 'basePrimaryPixels': int(primary.sum()),
        'protectedPixelSha256Before': _pixels(protection, 'L'), 'anchorCount': len(anchors),
        'method': 'independent_human_class_source_lab_anchor_components', 'recoveredPixels': 0,
        'protectionPreserved': True, 'certifiesSelection': False}
    result = dict(evidence)
    if len(anchors) < 2:
        audit['reason'] = 'insufficient_independently_supported_anchors'
        return result, audit
    centres = np.asarray([np.median(lab[max(0, y-2):y+3, max(0, x-2):x+3], axis=(0, 1))
        for x, y in anchors], 'float32')
    distance = np.min(np.stack([np.linalg.norm(lab - centre, axis=2) for centre in centres]), axis=0)
    semantic = np.isin(evidence['human'], evidence['semanticGarmentClasses'])
    supported = semantic & (distance < 24) & evidence['opaqueSource'] & ~protected
    count, labels = cv2.connectedComponents(supported.astype('uint8'))
    keep = {int(labels[y, x]) for x, y in anchors} - {0}
    recovered = np.isin(labels, list(keep)) & ~protected
    effective = (primary | recovered) & ~protected
    result['primary'] = effective
    result['coarse'] = Image.fromarray(effective.astype('uint8') * 255)
    audit.update(recoveredPixels=int((effective & ~primary).sum()),
        effectiveDomainPixels=int(effective.sum()), anchoredComponents=len(keep),
        sourceColourCentresLab=centres.tolist(), maxSourceLabDistance=24,
        semanticGarmentClasses=list(evidence['semanticGarmentClasses']),
        effectiveDomainPixelSha256=_pixels(result['coarse'], 'L'),
        protectedPixelSha256After=_pixels(protection, 'L'))
    return result, audit


def _instance_protection(source, plan, evidence, reviewed=None):
    """Separate a same-category garment only with two visual and pixel proofs.

    reviewed must be the preceding independent source/overlay review made by
    this prepare run, not caller-supplied initial feedback. Watershed is only a
    source-pixel proposal. Both class labels can be identical: source boundary,
    current-plan exclusion seeds and independent leak seeds must co-identify
    the same component before any of it becomes a protection constraint.
    """
    empty = Image.new('L', source.size)
    audit = {'method': 'source_watershed_with_plan_and_independent_review',
        'algorithmVersion': ALGORITHM_VERSION, 'certifiesSelection': False,
        'acceptedRegions': [], 'rejectedRegions': [], 'protectedPixels': 0}
    if not reviewed or reviewed.get('accepted') is not False:
        audit['reason'] = 'no_preceding_independent_rejected_review'
        return empty, audit
    leaks = reviewed.get('leaks', [])
    if not isinstance(leaks, list):
        raise ValueError('上一轮独立复核缺少有效漏选区域集合')
    review_points = [_point(row.get('point'), source.size) for row in leaks
        if isinstance(row, dict) and row.get('kind') == 'other_garment' and _evidence(row)]
    if not review_points:
        audit['reason'] = 'independent_review_did_not_identify_another_garment'
        return empty, audit
    positives, other, outside = [], [], []
    for row in plan.get('foreground', []):
        if not isinstance(row, dict) or not _evidence(row):
            raise ValueError('实例分离保留点缺少原片证据')
        x, y = _point(row.get('point'), source.size)
        if not evidence['protected'][y, x] and (evidence['primary'][y, x]
                or _semantic_point_support(evidence, x, y)):
            positives.append([x, y])
    for row in plan.get('background', []):
        if not isinstance(row, dict) or row.get('kind') not in NEGATIVE_KINDS or not _evidence(row):
            raise ValueError('实例分离去除点缺少原片证据')
        point = _point(row.get('point'), source.size)
        (other if row['kind'] == 'other_garment' else outside).append(point)
    if len(positives) < 2 or len(other) < 2:
        audit['reason'] = 'insufficient_current_plan_instance_constraints'
        return empty, audit
    # Every marker is automatic and tied to the current raw source. Smoothing
    # removes sensor/texture noise at a scale derived from image resolution;
    # it does not introduce geometry or repair source pixels.
    sigma = max(.5, min(source.size) / 1500)
    rgb = cv2.GaussianBlur(np.asarray(source.convert('RGB')), (0, 0), sigma)
    markers = np.zeros((source.height, source.width), 'int32')
    cloth_union = (evidence['cloth'] > 0) | np.isin(evidence['human'], [4, 5, 6, 7])
    radius = max(2, round(min(source.size) / 300))
    erode_size = 4 * radius + 1
    confident_outside = cv2.erode((~cloth_union).astype('uint8'),
        np.ones((erode_size, erode_size), 'uint8')) > 0
    markers[confident_outside] = 3
    markers[[0, -1], :] = 3;markers[:, [0, -1]] = 3
    for label, points in ((1, positives), (2, other), (3, outside)):
        for x, y in points:cv2.circle(markers, (x, y), radius, label, -1)
    # An overlapping marker is not evidence of an instance boundary.
    if any(markers[y, x] != 1 for x, y in positives):
        audit['reason'] = 'instance_markers_conflict'
        return empty, audit
    cv2.watershed(rgb.copy(), markers)
    count, labels, stats, _ = cv2.connectedComponentsWithStats((markers == 2).astype('uint8'))
    lab = cv2.cvtColor(rgb.astype('float32') / 255, cv2.COLOR_RGB2LAB)
    gradient = np.sqrt(sum(cv2.Sobel(lab[:, :, c], cv2.CV_32F, 1, 0, ksize=3)**2
        + cv2.Sobel(lab[:, :, c], cv2.CV_32F, 0, 1, ksize=3)**2 for c in range(3))) / 8
    result = np.zeros(markers.shape, bool)
    for label in range(1, count):
        region = labels == label
        model_seeds = sum(int(region[y, x]) for x, y in other)
        review_seeds = sum(int(region[y, x]) for x, y in review_points)
        row = {'region': label, 'pixels': int(stats[label, cv2.CC_STAT_AREA]),
            'planOtherGarmentSeeds': model_seeds, 'independentReviewSeeds': review_seeds}
        if model_seeds < 2 or review_seeds < 1:
            row['reason'] = 'plan_and_review_did_not_coidentify_one_source_instance'
            audit['rejectedRegions'].append(row);continue
        if region.sum() > region.size * .35 or region.sum() < max(25, region.size * .0001):
            row['reason'] = 'source_instance_area_unreliable'
            audit['rejectedRegions'].append(row);continue
        # Assess actual source colour/texture edges, not the watershed marker
        # separation itself. A fabricated split on flat same-colour fabric has
        # zero source boundary contrast and is rejected even if two AIs agree.
        kernel = np.ones((5, 5), 'uint8')
        interior = cv2.erode(region.astype('uint8'), kernel) > 0
        boundary = region & ~(cv2.erode(region.astype('uint8'), np.ones((3, 3), 'uint8')) > 0)
        # Only the interface to TARGET cloth can prove another garment. The
        # strong outer silhouette against a wall cannot authenticate an
        # arbitrary partition of one flat-colour garment. Watershed itself
        # leaves a one-pixel boundary; sample source gradient near that line.
        boundary &= cv2.dilate((markers == 1).astype('uint8'), kernel) > 0
        if not interior.any() or not boundary.any():
            row['reason'] = 'source_instance_has_no_stable_interior'
            audit['rejectedRegions'].append(row);continue
        inside_median = float(np.median(gradient[interior]))
        source_edge = cv2.dilate(gradient, kernel)
        boundary_median = float(np.median(source_edge[boundary]))
        boundary_support = float((source_edge[boundary] > max(.5,
            float(np.quantile(gradient[interior], .75)))).mean())
        ratio = boundary_median / max(.1, inside_median)
        row.update(sourceBoundaryMedianLabGradient=boundary_median,
            sourceInteriorMedianLabGradient=inside_median, sourceBoundaryContrastRatio=ratio,
            sourceBoundarySupportFraction=boundary_support, targetContactBoundaryPixels=int(boundary.sum()))
        if boundary_median < .75 or ratio < 1.5 or boundary_support < .55:
            row['reason'] = 'no_independent_source_colour_or_texture_boundary'
            audit['rejectedRegions'].append(row);continue
        # Preserve enclosed folds/highlights of that instance. A target cloth
        # foreground point inside any hole prevents filling that hole.
        n_holes, holes = cv2.connectedComponents((~region).astype('uint8'))
        leave = set(np.unique(np.r_[holes[0], holes[-1], holes[:, 0], holes[:, -1]]).tolist())
        leave |= {int(holes[y, x]) for x, y in positives}
        filled = region | np.isin(holes, [i for i in range(1, n_holes) if i not in leave])
        if any(filled[y, x] for x, y in positives):
            row['reason'] = 'source_instance_conflicts_with_validated_target_point'
            audit['rejectedRegions'].append(row);continue
        result |= filled
        row.update(filledPixels=int(filled.sum()), accepted=True)
        audit['acceptedRegions'].append(row)
    audit.update(protectedPixels=int(result.sum()), markerRadiusPixels=radius,
        smoothingSigma=sigma, planSha256=_sha(_json(plan).encode()),
        independentReviewSha256=_sha(_json(reviewed).encode()))
    mask = Image.fromarray(result.astype('uint8') * 255)
    audit['instanceProtectionPixelSha256'] = _pixels(mask, 'L')
    return mask, audit


def _background_protection(source, plan, evidence, reviewed=None):
    """Carve a photographed gap, never a colour-name/white-image heuristic."""
    empty = Image.new('L', source.size)
    audit = {'method': 'plan_review_source_palette_background_components',
        'algorithmVersion': ALGORITHM_VERSION, 'certifiesSelection': False,
        'acceptedRegions': [], 'rejectedRegions': [], 'relocatedNegativePoints': [],
        'localGapExemplars': [], 'protectedPixels': 0}
    if not reviewed or reviewed.get('accepted') is not False:
        audit['reason'] = 'no_preceding_independent_rejected_review';return empty, audit
    leaks = [row for row in reviewed.get('leaks', []) if isinstance(row, dict)
        and row.get('kind') in ('gap', 'background') and _evidence(row)]
    if not leaks:
        audit['reason'] = 'independent_review_has_no_gap_or_background_leak';return empty, audit
    lab = evidence['sourceLab']
    foreground, exterior, negatives = [], [], []
    for row in plan.get('foreground', []):
        x, y = _point(row.get('point'), source.size)
        if not _foreground_supported(evidence,x,y):continue
        foreground.append(([x, y], np.median(lab[max(0,y-2):y+3, max(0,x-2):x+3], axis=(0,1))))
    for index, row in enumerate(plan.get('background', [])):
        if row.get('kind') not in ('gap', 'background') or not _evidence(row):continue
        x, y = _point(row.get('point'), source.size);negatives.append((index, [x, y]))
        if (row['kind'] == 'background' and evidence['human'][y,x] == 0 and evidence['distance'][y,x] > 18):
            exterior.append(np.median(lab[max(0,y-2):y+3, max(0,x-2):x+3], axis=(0,1)))
    if len(foreground) < 2 or len(exterior) < 2 or not negatives:
        audit['reason'] = 'insufficient_source_foreground_or_exterior_background_evidence';return empty, audit
    fg_distance = np.min(np.stack([np.linalg.norm(lab-c, axis=2) for _,c in foreground]), axis=0)
    bg_chroma = np.min(np.stack([np.linalg.norm(lab[:,:,1:]-c[1:], axis=2) for c in exterior]), axis=0)
    # At least one local parser must explicitly see background. Both-parsers
    # garment pixels cannot be deleted merely because they look like a floor.
    background_label = (evidence['cloth'] == 0) | (evidence['human'] == 0)
    radius = max(2, min(12, round(min(source.size)*.006)))
    review_points=[_point(row['point'],source.size) for row in leaks]
    palette=list(exterior)
    # A lit floor opening and a shaded exterior wall may be the same observed
    # background chroma but >18 Lab units apart in lightness. Add an ACTUAL
    # corroborated gap sample instead of widening the existing colour gate.
    for index,point in negatives:
        if plan['background'][index]['kind']!='gap':continue
        x,y=point
        matches=[p for p in review_points if math.hypot(p[0]-x,p[1]-y)<=radius]
        if not matches or not background_label[y,x] or bg_chroma[y,x]>=6:continue
        y0=max(0,y-1);y1=min(source.height,y+2);x0=max(0,x-1);x1=min(source.width,x+2)
        patch=lab[y0:y1,x0:x1]
        if patch.shape[:2]!=(3,3):continue
        if (background_label[y0:y1,x0:x1].mean()<.90
                or (fg_distance[y0:y1,x0:x1]>18).mean()<.90
                or (evidence['distance'][y0:y1,x0:x1]>18).mean()<.90
                or not evidence['opaqueSource'][y0:y1,x0:x1].all()):continue
        colour=np.median(patch,axis=(0,1))
        if np.quantile(np.linalg.norm(patch-colour,axis=2),.90)>4:continue
        if min(np.linalg.norm(colour-c) for c in palette)<2:continue
        palette.append(colour)
        audit['localGapExemplars'].append({'planIndex':index,'pointPixels':point,
            'sourceRGB':evidence['sourceRGB'][y,x].astype(int).tolist(),'sourceMedianLab':colour.tolist(),
            'corroboratingReviewPointPixels':min(matches,key=lambda p:math.hypot(p[0]-x,p[1]-y)),
            'localBackgroundFraction':float(background_label[y0:y1,x0:x1].mean()),
            'distanceToForegroundLab':float(fg_distance[y,x]),
            'chromaDistanceToExteriorLab':float(bg_chroma[y,x]),
            'lightnessDifferenceToExterior':float(min(abs(colour[0]-c[0]) for c in exterior)),
            'reason':'actual_source_gap_corroborated_by_current_plan_and_independent_review'})
        if len(audit['localGapExemplars'])>=8:break
    bg_distance = np.min(np.stack([np.linalg.norm(lab-c, axis=2) for c in palette]), axis=0)
    candidate = (background_label & (fg_distance > 18) & (evidence['distance'] > 18)
        & (bg_distance < 18) & (bg_chroma < 6) & evidence['opaqueSource'])
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate.astype('uint8'))
    border = set(np.unique(np.r_[labels[0],labels[-1],labels[:,0],labels[:,-1]]).tolist()) - {0}
    def nearest(point):
        x,y=point;x0=max(0,x-radius);y0=max(0,y-radius)
        yy,xx=np.where(labels[y0:min(source.height,y+radius+1), x0:min(source.width,x+radius+1)]>0)
        if not len(xx):return None
        i=int(np.argmin((xx+x0-x)**2+(yy+y0-y)**2));ax=int(xx[i]+x0);ay=int(yy[i]+y0)
        if math.hypot(ax-x,ay-y)>radius:return None
        return [ax,ay,int(labels[ay,ax])]
    plan_matches = [(index,point,nearest(point)) for index,point in negatives]
    review_matches = [nearest(_point(row['point'], source.size)) for row in leaks]
    gradient = np.sqrt(sum(cv2.Sobel(lab[:,:,i],cv2.CV_32F,1,0,ksize=3)**2
        + cv2.Sobel(lab[:,:,i],cv2.CV_32F,0,1,ksize=3)**2 for i in range(3)))/8
    peak = cv2.dilate(gradient, np.ones((5,5),'uint8'))
    source_cloth = (evidence['distance']<10) & np.isin(evidence['human'],[4,5,6,7])
    cloth_near = cv2.dilate(source_cloth.astype('uint8'),np.ones((7,7),'uint8'))>0
    accepted = set();result = np.zeros(candidate.shape,bool)
    common = {match[2] for match in review_matches if match} & {match[2] for _,_,match in plan_matches if match}
    for label in sorted(common):
        region=labels==label
        row={'component':label,'pixels':int(stats[label,cv2.CC_STAT_AREA]),
            'currentPlanPoints':sum(bool(match and match[2]==label) for _,_,match in plan_matches),
            'independentReviewPoints':sum(bool(match and match[2]==label) for match in review_matches),
            'connectedToImageBorder':label in border}
        if region.sum()<9 or any(region[y,x] for (x,y),_ in foreground):
            row['reason']='too_small_or_conflicts_with_current_foreground';audit['rejectedRegions'].append(row);continue
        boundary=region & ~(cv2.erode(region.astype('uint8'),np.ones((3,3),'uint8'))>0) & cloth_near
        boundary_score=float(np.median(peak[boundary])) if boundary.any() else 0.
        boundary_supported=int(boundary.sum())>=8 and boundary_score>=2
        row.update(sourceClothContactPixels=int(boundary.sum()),sourceBoundaryMedianLabGradient=boundary_score,
            sourceBoundarySupported=boundary_supported)
        if label not in border and not boundary_supported:
            row['reason']='no_source_connection_or_cloth_boundary';audit['rejectedRegions'].append(row);continue
        result|=region;accepted.add(label);row['accepted']=True;audit['acceptedRegions'].append(row)
    for index,point,match in plan_matches:
        if match and match[2] in accepted and point!=match[:2]:
            audit['relocatedNegativePoints'].append({'index':index,'fromPixels':point,'toPixels':match[:2],
                'reason':'model_coordinate_refined_to_confirmed_source_background'})
    mask=Image.fromarray(result.astype('uint8')*255)
    audit.update(protectedPixels=int(result.sum()),maxCoordinateRefinementPixels=radius,
        exteriorSourceLab=[c.tolist() for c in exterior],minimumFabricDistanceLab=18,
        sourceBackgroundPaletteLab=[c.tolist() for c in palette],
        maximumExteriorDistanceLab=18,maximumExteriorChromaDistanceLab=6,
        planSha256=_sha(_json(plan).encode()),independentReviewSha256=_sha(_json(reviewed).encode()),
        backgroundProtectionPixelSha256=_pixels(mask,'L'))
    return mask,audit


def _source_path_refinement(plan, row, path_points, ribbon, evidence):
    """Refine only a model ribbon, never erase existing independent protection.

    An actual occluder point from the plan, centreline continuity and original
    source colour boundaries must agree. Missing evidence retains the previous
    conservative protection and is explicitly diagnosed.
    """
    audit={'method':'conservative_model_ribbon','originalRibbonPixels':int((ribbon>0).sum())}
    object_points=[]
    near_path=cv2.dilate((ribbon>0).astype('uint8'),np.ones((7,7),'uint8'))>0
    for point in plan.get('background',[]):
        if point.get('kind')!=row['kind'] or not _evidence(point):continue
        x,y=_point(point['point'],(ribbon.shape[1],ribbon.shape[0]))
        # Pale occluders can share the garment's global colour clusters. The
        # source centreline and instance boundary, not a global colour-distance
        # cutoff, validate this independently labelled accessory exemplar.
        if near_path[y,x]:
            object_points.append([x,y])
    if not object_points:
        audit['reason']='no_independent_plan_occluder_seed_in_path';return ribbon>0,audit
    yy,xx=np.where(ribbon>0)
    if not len(xx):return ribbon>0,audit
    x0=max(0,int(xx.min())-3);x1=min(ribbon.shape[1],int(xx.max())+4)
    y0=max(0,int(yy.min())-3);y1=min(ribbon.shape[0],int(yy.max())+4)
    if (x1-x0)*(y1-y0)>1_000_000:
        audit['reason']='occluder_source_window_too_large';return ribbon>0,audit
    lab=evidence['sourceLab'][y0:y1,x0:x1]
    centres=[np.median(evidence['sourceLab'][max(0,y-1):y+2,max(0,x-1):x+2],axis=(0,1)) for x,y in object_points]
    delta=np.min(np.stack([np.linalg.norm(lab-c,axis=2) for c in centres]),axis=0)
    tube=ribbon[y0:y1,x0:x1]>0
    cloth_distance=evidence['distance'][y0:y1,x0:x1].copy()
    for point in plan.get('foreground',[]):
        fx,fy=_point(point['point'],(ribbon.shape[1],ribbon.shape[0]))
        if (evidence['primary'][fy,fx] and evidence['human'][fy,fx] in (4,5,6,7)
                and not evidence['protected'][fy,fx]):
            colour=np.median(evidence['sourceLab'][max(0,fy-1):fy+2,max(0,fx-1):fx+2],axis=(0,1))
            # A purported cloth exemplar identical to the occluder cannot
            # distinguish the two and is not used to erase the occluder.
            if min(np.linalg.norm(colour-c) for c in centres)>12:
                cloth_distance=np.minimum(cloth_distance,np.linalg.norm(lab-colour,axis=2))
    cloth=(evidence['primary'][y0:y1,x0:x1]
        &np.isin(evidence['human'][y0:y1,x0:x1],[4,5,6,7])
        &(cloth_distance<10)&(delta>12)&tube)
    if cloth.sum()<3:
        audit['reason']='no_source_supported_cloth_overcoverage';return ribbon>0,audit
    centreline=np.zeros(tube.shape,'uint8')
    cv2.polylines(centreline,[path_points-np.array([x0,y0],'int32')],False,255,1)
    core=tube&(delta<12)
    if (core&(centreline>0)).sum()/max(1,(centreline>0).sum())<.60:
        audit['reason']='source_occluder_does_not_support_model_centreline';return ribbon>0,audit
    gc=np.full(tube.shape,cv2.GC_BGD,'uint8');gc[tube]=cv2.GC_PR_FGD
    gc[cloth]=cv2.GC_BGD;gc[core]=cv2.GC_PR_FGD
    gc[centreline>0]=cv2.GC_FGD
    source_seeds=[]
    for x,y in object_points:
        if x0<=x<x1 and y0<=y<y1 and tube[y-y0,x-x0]:
            seed=[x,y]
        else:
            # A nearby bag-body exemplar may supply colour, but only an actual
            # matching source pixel inside this path can seed the narrow item.
            sy,sx=np.where(core)
            if not len(sx):continue
            nearest=int(np.argmin((sx+x0-x)**2+(sy+y0-y)**2))
            seed=[int(sx[nearest]+x0),int(sy[nearest]+y0)]
            if math.hypot(seed[0]-x,seed[1]-y)>6:continue
        source_seeds.append(seed);gc[seed[1]-y0,seed[0]-x0]=cv2.GC_FGD
    if not source_seeds:
        audit['reason']='no_nearby_matching_source_occluder_seed';return ribbon>0,audit
    try:
        cv2.setRNGSeed(0)
        cv2.grabCut(evidence['sourceRGB'][y0:y1,x0:x1].copy(),gc,None,
            np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
    except cv2.error as error:
        audit.update(reason='source_occluder_grabcut_failed',error=str(error)[:500]);return ribbon>0,audit
    selected=np.isin(gc,[cv2.GC_FGD,cv2.GC_PR_FGD])&tube
    # A short matching-colour highlight can interrupt an observed narrow
    # occluder. Close only a 5px interruption of its source-colour core, not the
    # whole model ribbon; this cannot restore a 20px geometric cloth blanket.
    continuity=cv2.morphologyEx(core.astype('uint8'),cv2.MORPH_CLOSE,np.ones((5,5),'uint8'))>0
    selected|=continuity&tube
    n,labels=cv2.connectedComponents(selected.astype('uint8'))
    keep={int(labels[y-y0,x-x0]) for x,y in source_seeds}-{0}
    selected=np.isin(labels,list(keep))&tube
    if any(not selected[y-y0,x-x0] for x,y in source_seeds) or selected.sum()<3:
        audit['reason']='occluder_seed_or_connected_instance_lost';return ribbon>0,audit
    released=cloth&~selected
    if not released.any():
        audit['reason']='no_certified_source_cloth_released';return ribbon>0,audit
    final=np.zeros(ribbon.shape,bool);final[y0:y1,x0:x1]=selected
    audit.update(method='source_pixel_occluder_grabcut',occluderPointsPixels=object_points,
        sourceOccluderSeedsPixels=source_seeds,
        sourceOccluderCentresLab=[c.tolist() for c in centres],retainedPixels=int(final.sum()),
        releasedSourceClothPixels=int(released.sum()),centrelineRetainedFraction=float(
            (selected&(centreline>0)).sum()/max(1,(centreline>0).sum())),
        sourcePixelMaskSha256=_sha(final.astype('uint8').tobytes()))
    return final,audit


def _point_diagnostics(rows,evidence,protection=None):
    result=[]
    for row in rows[:32]:
        x,y=row['pointPixels']
        item={k:copy.deepcopy(v) for k,v in row.items() if k in ('type','index','reason','pointPixels')}
        item.update(clothingLabel=int(evidence['cloth'][y,x]),humanLabel=int(evidence['human'][y,x]),
            labDistanceToSourceFabric=round(float(evidence['distance'][y,x]),3),
            baseProtected=bool(evidence['protected'][y,x]),didNotBecomeConstraint=True)
        if 'sourceRGB' in evidence:item['sourceRGB']=evidence['sourceRGB'][y,x].astype(int).tolist()
        if protection is not None:item['protectedAfterCurrentPlan']=bool(protection[y,x])
        result.append(item)
    return {'rejectedPoints':result,'totalRejectedPoints':len(rows),'diagnosticsTruncated':len(rows)>32,
        'foregroundCoverageMeaning':'coverage of accepted compiled foreground points only; rejected model points were NOT accepted'}


def _compile_plan(plan, size, evidence, explicit, instance_protection=None,
        background_protection=None, background_relocations=None):
    if not isinstance(plan, dict):
        raise ValueError('自动选区规划未返回对象')
    positives, negatives, rejected, relocated = [], [], [], []
    rows = plan.get('foreground')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 24:
        raise ValueError('自动选区规划缺少衣料保留点')
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not _evidence(row) or not isinstance(row.get('part'), str):
            raise ValueError('衣料保留点缺少当前原图证据')
        x, y = _point(row.get('point'), size)
        if not _foreground_supported(evidence,x,y):
            rejected.append({'type': 'foreground', 'index': index, 'reason': 'no_independent_fabric_support', 'pointPixels': [x, y]})
        else:
            positives.append([x, y])
    rows = plan.get('background')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 48:
        raise ValueError('自动选区规划缺少实际背景/遮挡去除点')
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get('kind') not in NEGATIVE_KINDS or not _evidence(row):
            raise ValueError('背景去除点缺少类型或当前原图证据')
        x, y = _point(row.get('point'), size)
        # This catches a common vision-coordinate error: a supposed hair/strap
        # point actually landed on the garment. Never punch that point out.
        replacement = (background_relocations or {}).get(index)
        if replacement is not None and row['kind'] in ('gap','background'):
            original = [x,y];x,y=replacement
            if background_protection is None or background_protection.getpixel((x,y)) == 0:
                raise ValueError('背景坐标修正没有已核对源像素保护支持')
            relocated.append({'index':index,'fromPixels':original,'toPixels':[x,y]})
        cloth_like = evidence['primary'][y, x] and evidence['distance'][y, x] < 10
        if row['kind'] in ('gap','background') and evidence['human'][y,x] in (4,5,6,7) and evidence['distance'][y,x] <= 12:
            cloth_like = True
        confirmed_other = (row['kind'] == 'other_garment' and instance_protection is not None
            and instance_protection.getpixel((x, y)) > 0)
        if cloth_like and not evidence['protected'][y, x] and not confirmed_other:
            rejected.append({'type': 'background', 'index': index, 'reason': 'point_conflicts_with_visible_fabric', 'pointPixels': [x, y]})
        else:
            negatives.append([x, y])
    if not positives or not negatives:
        raise PlanValidationError('视觉选点与独立原片证据冲突，未生成被认证的蒙版',
            _point_diagnostics(rejected,evidence))
    protected = evidence['protected'].copy()
    if instance_protection is not None:
        if instance_protection.size != size:
            raise ValueError('实例保护区与源图尺寸不符')
        protected |= np.asarray(instance_protection.convert('L')) > 0
    if background_protection is not None:
        if background_protection.size != size:raise ValueError('背景保护区与源图尺寸不符')
        protected |= np.asarray(background_protection.convert('L')) > 0
    path_rows = plan.get('protections', [])
    if not isinstance(path_rows, list) or len(path_rows) > 16:
        raise ValueError('遮挡保护路径数量无效')
    path_audit = []
    refined_occluders=np.zeros(protected.shape,bool)
    for row in path_rows:
        if (not isinstance(row, dict) or row.get('kind') not in NEGATIVE_KINDS - {'background', 'gap'}
                or not _evidence(row) or not isinstance(row.get('path'), list) or not 2 <= len(row['path']) <= 64):
            raise ValueError('只接受带当前原图证据的窄遮挡保护路径')
        width = row.get('widthFraction')
        if type(width) not in (int, float) or not math.isfinite(width) or not .001 <= width <= .04:
            raise ValueError('保护路径须为窄线，不能整块覆盖衣服')
        points = np.array([_point(point, size) for point in row['path']], 'int32')
        ribbon = np.zeros(protected.shape, 'uint8')
        cv2.polylines(ribbon, [points], False, 255, max(1, round(width * min(size))))
        if (ribbon > 0).sum() > protected.size * .10:
            raise ValueError('保护线覆盖过大，不能用大块几何蒙版替代原片边界')
        # A narrow model-drawn line is still a hypothesis. Local cloth evidence
        # prevents a misplaced line from erasing whole pale garment stripes.
        supported = (ribbon > 0) & (~evidence['primary'] | (evidence['distance'] > 10) | evidence['protected'])
        anchors = [bool(supported[y, x]) for x, y in points]
        along = []
        for first, last in zip(points[:-1], points[1:]):
            count = max(2, int(np.linalg.norm(last - first)) + 1)
            samples = np.rint(np.linspace(first, last, count)).astype('int32')
            along.extend(bool(supported[y, x]) for x, y in samples)
        longest_unmatched = current_run = 0
        for match in along:
            current_run = 0 if match else current_run + 1
            longest_unmatched = max(longest_unmatched, current_run)
        # A narrow path whose source anchors independently identify an occluder
        # may include that occluder's pale highlights. Thresholding each RGB
        # pixel separately would leave white islands in a real green strap.
        # Broad or fabric-anchored lines remain rejected/filter-only.
        source_anchored = (sum(anchors) >= max(2, math.ceil(len(anchors) * .6))
            and sum(along) / max(1, len(along)) >= .6
            and longest_unmatched <= max(6, round(width * min(size) * 2)))
        source_instance,path_refinement=_source_path_refinement(plan,row,points,ribbon,evidence)
        if path_refinement['method']=='source_pixel_occluder_grabcut':
            supported=source_instance;refined_occluders|=source_instance
        elif source_anchored:
            supported=ribbon>0
        protected |= supported
        path_audit.append({'kind': row['kind'], 'pointsPixels': points.tolist(),
            'widthPixels': max(1, round(width * min(size))), 'supportedPixels': int(supported.sum()),
            'sourceAnchored': source_anchored, 'longestUnmatchedPathPixels': longest_unmatched,
            'sourceRefinement':path_refinement})
    if explicit is not None:
        protected |= np.asarray(explicit.convert('L')) > 0
    restored=[]
    for item in list(rejected):
        if item['type']!='background' or item['reason']!='point_conflicts_with_visible_fabric':continue
        row=plan['background'][item['index']];x,y=item['pointPixels']
        if row['kind'] in ('accessory','hair','skin') and refined_occluders[y,x]:
            negatives.append([x,y]);rejected.remove(item)
            restored.append({'index':item['index'],'pointPixels':[x,y],
                'reason':'source_validated_occluder_instance_overrules_global_colour_similarity'})
    # Negative constraints must remain outside, but a doubtful predicted point
    # was filtered above. Do not dilate negative circles into a sleeve edge.
    for x, y in negatives:
        protected[y, x] = True
    conflicts=[{'type':'foreground','pointPixels':[x,y],
        'reason':'foreground_point_conflicts_with_source_protection'} for x,y in positives if protected[y,x]]
    if conflicts:
        raise PlanValidationError('视觉保留点与当前图保护路径冲突',
            _point_diagnostics(conflicts,evidence,protected))
    return {'foreground': positives, 'background': negatives}, Image.fromarray(protected.astype('uint8') * 255), {
        'rejectedPoints': rejected, 'relocatedBackgroundPoints': relocated, 'protectionPaths': path_audit,
        'restoredOccluderPoints':restored,
        'pointDiagnostics':_point_diagnostics(rejected,evidence,protected),
        'foregroundCount': len(positives), 'backgroundCount': len(negatives),
    }


def _refine_source_cloth(source, proposal, points, protection):
    """The existing source GrabCut trimap with independently seen thin ridges.

    Large-area certain foreground, search margin and iteration count are
    unchanged. Continuous thin interior evidence fills the known erosion gap;
    it cannot override source protections or actual background constraints.
    """
    image = np.asarray(source.convert('RGB'))
    mask = np.asarray(proposal.convert('L')) > 127
    possible = cv2.dilate(mask.astype('uint8'), np.ones((65, 65), 'uint8')) > 0
    certain = cv2.erode(mask.astype('uint8'), np.ones((21, 21), 'uint8')) > 0
    gc = np.full(mask.shape, cv2.GC_BGD, 'uint8')
    gc[possible] = cv2.GC_PR_BGD;gc[mask] = cv2.GC_PR_FGD;gc[certain] = cv2.GC_FGD
    for x, y in points['foreground']:
        cv2.circle(gc, (int(x), int(y)), 2, cv2.GC_FGD, -1)
    for x, y in points.get('sourceClothAnchors', []):gc[int(y), int(x)] = cv2.GC_FGD
    for x, y in points.get('sourceClothRidgePixels', []):gc[int(y), int(x)] = cv2.GC_FGD
    for x, y in points['background']:cv2.circle(gc, (int(x), int(y)), 4, cv2.GC_BGD, -1)
    protected = np.asarray(protection.convert('L')) > 0
    gc[cv2.erode(protected.astype('uint8'), np.ones((3, 3), 'uint8')) > 0] = cv2.GC_BGD
    cv2.setRNGSeed(0)
    cv2.grabCut(image.copy(), gc, None, np.zeros((1, 65)), np.zeros((1, 65)), 3, cv2.GC_INIT_WITH_MASK)
    selected = np.isin(gc, [cv2.GC_FGD, cv2.GC_PR_FGD]) & ~protected
    return Image.fromarray(selected.astype('uint8') * 255)


def _source_cloth_anchors(source, evidence, points, protection):
    """Keep independently seen narrow cloth from losing every GC sure seed.

    The existing GrabCut routine erodes 21x21 to make certain foreground. A
    genuine 8-pixel sleeve strip consequently has no certain seed at all. This
    supplies bounded source-derived interior ridge anchors only where BOTH
    original semantic models and original Lab evidence agree. It never erases
    a protection, follows a user/model hand polygon or infers hidden fabric.
    """
    before = _pixels(protection, 'L')
    protected = np.asarray(protection.convert('L')) > 0
    base = evidence['consensus'] & ~protected & (np.asarray(source.convert('RGBA'))[:, :, 3] > 230)
    # Chebyshev distance corresponds to the existing square 21x21 erosion.
    distance = cv2.distanceTransform(base.astype('uint8'), cv2.DIST_C, 3)
    local_max = cv2.dilate(distance, np.ones((5, 5), 'uint8'))
    ridge = (distance >= 2) & (distance <= 10) & (distance >= local_max)
    ridge &= evidence['distance'] < 10
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ridge.astype('uint8'))
    anchors, ridge_pixels, regions, skipped = [], [], [], []
    ordered = sorted(range(1, count), key=lambda i: (-int(stats[i, cv2.CC_STAT_AREA]), i))
    for label in ordered:
        if stats[label, cv2.CC_STAT_AREA] < 6:continue
        yy, xx = np.where(labels == label)
        coordinates = np.column_stack([xx, yy])
        clean = []
        for x, y in coordinates:
            if any(math.hypot(x-bx, y-by) <= 7 for bx, by in points['background']):continue
            radius = min(2, int(distance[y, x])-1)
            patch = evidence['sourceLab'][y-radius:y+radius+1, x-radius:x+radius+1]
            if patch.shape[:2] != (2*radius+1, 2*radius+1):continue
            if np.quantile(np.linalg.norm(patch-np.median(patch, axis=(0, 1)), axis=2), .9) <= 12:
                clean.append([int(x), int(y)])
        if len(clean) < 6:continue
        coordinates = np.array(clean, 'int32')
        ridge_pixels.extend(clean[:max(0, 2048-len(ridge_pixels))])
        centre = np.median(coordinates, axis=0)
        first = int(np.argmin(np.sum((coordinates-centre)**2, axis=1)))
        candidates = [coordinates[first]]
        span = float(np.linalg.norm(np.ptp(coordinates, axis=0)))
        if span >= 12:
            far = int(np.argmax(np.sum((coordinates-coordinates[first])**2, axis=1)))
            candidates.append(coordinates[far])
            # A centre plus only one extremity misses the opposite shadow
            # transition of a long narrow piece. Preserve both source ends.
            opposite = int(np.argmax(np.sum((coordinates-coordinates[far])**2, axis=1)))
            candidates.append(coordinates[opposite])
        kept = []
        for value in candidates:
            x, y = map(int, value)
            if any(math.hypot(x-bx, y-by) <= 7 for bx, by in points['background']):
                skipped.append({'pointPixels': [x, y], 'reason': 'near_background_constraint'});continue
            if any(math.hypot(x-px, y-py) <= 4 for px, py in points['foreground'] + anchors):continue
            radius = min(2, int(distance[y, x])-1)
            patch = evidence['sourceLab'][y-radius:y+radius+1, x-radius:x+radius+1]
            if patch.shape[:2] != (2*radius+1, 2*radius+1) or np.quantile(np.linalg.norm(patch-np.median(patch, axis=(0, 1)), axis=2), .9) > 12:
                skipped.append({'pointPixels': [x, y], 'reason': 'mixed_source_edge_or_material'});continue
            anchors.append([x, y]);kept.append([x, y])
            if len(anchors) >= 64:break
        if kept:regions.append({'ridgePixels': int(stats[label, cv2.CC_STAT_AREA]), 'anchors': kept})
        if len(anchors) >= 64 or len(ridge_pixels) >= 2048:break
    return anchors, {'method': 'dual_semantic_source_lab_thin_interior_ridges',
        'algorithmVersion': ALGORITHM_VERSION, 'anchorCount': len(anchors), 'maxAnchors': 64,
        'sourceClothAnchors': anchors, 'regions': regions, 'skipped': skipped,
        'sourceClothRidgePixels': ridge_pixels, 'ridgePixelCount': len(ridge_pixels), 'maxRidgePixels': 2048,
        'sourceClothRidgeSha256': _sha(_json(ridge_pixels).encode()),
        'sourceLabDistanceLimit': 10, 'distanceToNonConsensusPixels': [2, 10],
        'patchRadius': 'min(2, source_consensus_distance-1)', 'automaticSeedsExpandBeyondValidatedPixels': False,
        'compensatesExistingGrabCutErosion': 21, 'certifiesSelection': False,
        'protectedPixelSha256Before': before, 'protectedPixelSha256After': _pixels(protection, 'L'),
        'protectionPreserved': before == _pixels(protection, 'L')}


def _quality(mask, source, points, protection, evidence):
    a = np.asarray(mask.convert('L'))
    selected = a > 0
    protected = np.asarray(protection.convert('L')) > 0
    primary = evidence['primary']
    core = cv2.erode(primary.astype('uint8'), np.ones((5, 5), 'uint8')) > 0
    core &= ~protected
    margin = max(3, min(30, round(min(source.size) * .03)))
    domain = cv2.dilate(primary.astype('uint8'), np.ones((2 * margin + 1,) * 2, 'uint8')) > 0
    foreground_coverage = float(np.mean([a[y, x] >= 230 for x, y in points['foreground']]))
    automatic = points.get('sourceClothAnchors', [])
    source_coverage = float(np.mean([a[y, x] >= 230 for x, y in automatic])) if automatic else 1.
    ridge = points.get('sourceClothRidgePixels', [])
    ridge_coverage = float(np.mean([a[y, x] >= 230 for x, y in ridge])) if ridge else 1.
    values = {'selectedPixels': int(selected.sum()), 'softPixels': int(((a > 0) & (a < 255)).sum()),
        'selectedFraction': float(selected.mean()), 'foregroundCoverage': foreground_coverage,
        'sourceClothAnchorCount': len(automatic), 'sourceClothAnchorCoverage': source_coverage,
        'sourceClothRidgePixelCount': len(ridge), 'sourceClothRidgeCoverage': ridge_coverage,
        'protectedChangedPixels': int((selected & protected).sum()),
        'backgroundPointHits': sum(int(a[y, x] > 0) for x, y in points['background']),
        'semanticCorePixels': int(core.sum()),
        'semanticCoreCoverage': float(((a > 127) & core).sum() / max(1, core.sum())),
        'outsideDomainFraction': float((selected & ~domain).sum() / max(1, selected.sum()))}
    issues = []
    if selected.sum() < max(50, a.size * .005) or selected.mean() > .90:
        issues.append('selection_area_not_reliable')
    if foreground_coverage != 1:
        issues.append('visible_fabric_constraint_missing')
    if source_coverage != 1:
        issues.append('source_supported_thin_cloth_constraint_missing')
    if ridge_coverage != 1:
        issues.append('source_supported_thin_cloth_ridge_missing')
    if values['protectedChangedPixels'] or values['backgroundPointHits']:
        issues.append('explicit_background_or_protection_selected')
    if core.sum() < 50 or values['semanticCoreCoverage'] < .88:
        issues.append('independent_cloth_core_not_covered')
    if values['outsideDomainFraction'] > .02:
        issues.append('selection_extends_beyond_independent_cloth_domain')
    values['accepted'] = not issues
    values['issues'] = issues
    return values


def _review(value):
    if not isinstance(value, dict) or type(value.get('accepted')) is not bool:
        raise ValueError('独立选区复核未返回明确结论')
    for field in ('issues', 'misses', 'leaks'):
        if not isinstance(value.get(field), list):
            raise ValueError('独立选区复核缺少完整缺陷集合')
    if any(not isinstance(item, str) for item in value['issues']):
        raise ValueError('选区复核缺陷必须为具体文本')
    if 'warnings' in value and (not isinstance(value['warnings'], list) or any(not isinstance(item, str) for item in value['warnings'])):
        raise ValueError('选区复核提醒须为文本集合')
    if value['accepted'] and any(value[field] for field in ('issues', 'misses', 'leaks')):
        raise ValueError('复核声称通过但仍有选区缺陷')
    return value


def _vision_request(instruction, context, images):
    return {'instruction': instruction, 'context': context,
        'images': [{'size': list(image.size), 'rgbaSha256': _pixels(image, 'RGBA')} for image in images]}


def _reuse_completed_call(origin, destination, instruction, context, images, *, required=False):
    """Copy a known completed response only when the actual request matches."""
    origin, destination = Path(origin), Path(destination)
    if not origin.exists():
        if required:raise VisionIntentConflict('本地接续没有原已完成规划，未重新付费分析')
        return False
    saved = json.loads(origin.read_text('utf-8'))
    if saved.get('state') != 'completed':
        raise VisionCallUnknown('已有视觉请求未完成，未重发或覆盖')
    if saved.get('signature') != _sha(_json(saved.get('request')).encode()):
        raise VisionIntentConflict('原视觉请求回执签名不符，未继续付费分析')
    signature = _sha(_json(_vision_request(instruction, context, images)).encode())
    if saved['signature'] != signature:
        if required:raise VisionIntentConflict('本地接续的首次规划意图变化，未重复调用模型')
        return False
    raw = origin.read_bytes()
    if destination.exists():
        if destination.read_bytes() != raw:raise VisionIntentConflict('接续视觉回执已存在且不同，未覆盖')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:stream.write(raw)
    return {'path': str(origin), 'recordSha256': _sha(raw), 'signature': signature}


def _vision_call(vision, folder, name, instruction, context, images):
    request = _vision_request(instruction, context, images)
    signature = _sha(_json(request).encode())
    path = folder / (name + '.json')
    if path.exists():
        saved = json.loads(path.read_text('utf-8'))
        if saved.get('signature') != signature:
            raise VisionIntentConflict('自动视觉请求与已保存意图冲突，未重新调用')
        if saved.get('state') != 'completed':
            raise VisionCallUnknown('原视觉调用结果未知，保留请求意图，未自动重发')
        return saved['result']
    saved = {'signature': signature, 'request': request, 'state': 'pending', 'started': time.time()}
    _write(path, saved)
    try:
        raw = vision(instruction, copy.deepcopy(context), [image.copy() for image in images])
        _json(raw)  # Require complete serializable audit output before accepting it.
        result = raw.get('result') if isinstance(raw, dict) and isinstance(raw.get('result'), dict) else raw
        if not isinstance(result, dict):
            raise ValueError('视觉调用未返回JSON对象')
        saved.update(state='completed', completed=time.time(), raw=raw, result=result)
        _write(path, saved)
        return result
    except Exception as error:
        saved.update(state='unknown', error=str(error)[:2000])
        _write(path, saved)
        raise VisionCallUnknown('原视觉调用结果未知，未自动重发：' + str(error)) from error


def _subject(value):
    if value is None:
        return None
    if not isinstance(value, dict) or not value or set(value) - {'productName', 'role', 'target'}:
        raise ValueError('选区subject仅接受已保存productName、role、target字段')
    result = {}
    for key, text in value.items():
        if not isinstance(text, str) or not text.strip() or len(text) > 512:
            raise ValueError('选区subject字段须为不超过512字符的已保存短文本')
        if key == 'role' and text not in ('source_garment', 'target_colour_reference'):
            raise ValueError('选区subject角色无效')
        result[key] = text.strip()
    return result


def _guard_unresolved_intents(cache_root, identity, current_manifest):
    """A new algorithm/subject must not bypass an older unknown paid call."""
    for manifest in Path(cache_root).glob('*/*/receipt.json'):
        if manifest.resolve() == Path(current_manifest).resolve():
            continue
        try:
            previous = json.loads(manifest.read_text('utf-8'))
        except (OSError, ValueError):
            continue  # Identity cannot be established; never mutate that file.
        old = previous.get('identity', previous)
        if (old.get('sourcePixelSha256') != identity['sourcePixelSha256']
                or old.get('vision') != identity['vision']):
            continue
        unresolved = previous.get('state') in ('processing', 'unknown')
        unknown_files = []
        for call_path in list(manifest.parent.rglob('plan.json')) + list(manifest.parent.rglob('review.json')):
            try:
                call = json.loads(call_path.read_text('utf-8'))
                if call.get('state') != 'completed':
                    unknown_files.append(str(call_path))
            except (OSError, ValueError):
                unknown_files.append(str(call_path))
        if unresolved or unknown_files:
            facts = {'version': VERSION, 'algorithmVersion': ALGORITHM_VERSION, 'identity': identity,
                'verified': False, 'accepted': False, 'state': 'unknown', 'humanReviewed': False,
                'blockingReceiptPath': str(manifest), 'blockingReceiptSha256': _sha(manifest.read_bytes()),
                'unresolvedCallPaths': unknown_files, 'reason': 'same_source_vision_has_unresolved_prior_intent'}
            raise SelectionRejected('同源同模型存在旧版未决视觉调用，先对账，未因算法升级重发',
                facts, code='automatic_selection_unknown')


def _conserve_miss_only(source,candidate,protection,prior,source_sha):
    """Preserve reviewed selections only for an immediate miss-only correction.

    This produces a new unverified candidate. No passed state is inherited;
    current protection/alpha, current numeric policy and a fresh actual review
    retain authority over it.
    """
    audit={'applied':False,'method':'max_immediate_prior_for_numeric_pass_miss_only',
        'algorithmVersion':ALGORITHM_VERSION,'certifiesSelection':False,
        'sourcePixelSha256':source_sha,'newCandidatePixelSha256':_pixels(candidate,'L'),
        'currentProtectionPixelSha256':_pixels(protection,'L')}
    if not prior:
        audit['reason']='no_immediate_reviewed_candidate';return candidate,audit
    quality=prior.get('quality');review=prior.get('review')
    if not (isinstance(quality,dict) and quality.get('accepted') is True
            and isinstance(review,dict) and review.get('accepted') is False
            and isinstance(review.get('misses'),list) and bool(review['misses'])
            and isinstance(review.get('leaks'),list) and not review['leaks']):
        audit['reason']='prior_numeric_or_miss_only_review_not_eligible';return candidate,audit
    if prior.get('sourcePixelSha256')!=source_sha or _pixels(source,'RGBA')!=source_sha:
        raise ValueError('内部守恒前后源图身份不符，未合并不同源图选区')
    previous=prior.get('mask')
    if not isinstance(previous,Image.Image) or previous.size!=source.size or candidate.size!=source.size or protection.size!=source.size:
        raise ValueError('内部守恒图像尺寸与同一原图不符')
    old=np.asarray(previous.convert('L'));new=np.asarray(candidate.convert('L'))
    union=np.maximum(old,new);blocked=np.asarray(protection.convert('L'))>0
    transparent=np.asarray(source.convert('RGBA'))[:,:,3]==0
    result=union.copy();result[blocked|transparent]=0
    final=Image.fromarray(result)
    audit.update(applied=True,priorAttempt=prior.get('number'),priorMaskPath=prior.get('maskPath'),
        priorMaskPixelSha256=_pixels(previous,'L'),priorReviewSha256=_sha(_json(review).encode()),
        priorNumericSha256=_sha(_json(quality).encode()),
        inheritedPriorOnlyPixels=int(((old>new)&(result>new)).sum()),
        pixelsRemovedByCurrentProtection=int(((union>0)&blocked).sum()),
        pixelsRemovedBySourceAlpha=int(((union>0)&transparent&~blocked).sum()),
        resultMaskPixelSha256=_pixels(final,'L'),passedStateInherited=False)
    return final,audit


def prepare(source, kind, *, vision, cache_root, protected=None, local_backend=None,
            vision_metadata=None, initial_feedback=None, resume_local_error=False, subject=None,
            max_attempts=2):
    """Return (L mask, receipt) or SelectionRejected with persisted failure facts.

    ``vision(instruction, context, images)`` receives PIL images. It may return
    the JSON object or {result: JSON object, receipt: original_provider_receipt}.
    The callback is responsible for the existing account/model budget route;
    this module has no credentials or alternate model transport.
    """
    if kind not in TARGET or not isinstance(source, Image.Image):
        raise ValueError('自动服装选区须有原图和明确upper/lower/full类别')
    if not callable(vision):
        raise ValueError('自动选区须绑定当前账号的视觉分析接口')
    if type(resume_local_error) is not bool:
        raise ValueError('本地错误接续标记须为布尔值')
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError('自动选区max_attempts须为1–3，最多两次内部纠正')
    subject = _subject(subject)
    source = source.convert('RGBA')
    if source.width * source.height > 40_000_000 or min(source.size) < 16 or max(source.size) > 8192:
        raise ValueError('自动选区原图尺寸不支持')
    if protected is not None and (not isinstance(protected, Image.Image) or protected.size != source.size):
        raise ValueError('显式保护区须为同尺寸原图蒙版')
    if initial_feedback is not None and (not isinstance(initial_feedback, dict) or len(_json(initial_feedback)) > 16000):
        raise ValueError('初始自动质检反馈须为不超过16000字符的JSON对象')
    backend = local_backend or LocalBackend()
    local_identity = backend.identity() if callable(getattr(backend, 'identity', None)) else {
        'adapter': type(backend).__module__ + '.' + type(backend).__qualname__}
    identity = {'version': VERSION, 'algorithmVersion': ALGORITHM_VERSION, 'kind': kind, 'sourceSize': list(source.size),
        'maxAttempts': max_attempts,
        'subject': copy.deepcopy(subject),
        'sourcePixelSha256': _pixels(source, 'RGBA'), 'sourceHashEncoding': 'rgba8_top_to_bottom',
        'explicitProtectionSha256': _pixels(protected, 'L') if protected is not None else None,
        'initialFeedbackSha256': _sha(_json(initial_feedback).encode()) if initial_feedback is not None else None,
        'vision': copy.deepcopy(vision_metadata or getattr(vision, 'identity', None) or {'provider': 'caller_supplied_unverified'}),
        'localModelIdentity': local_identity,
        'proposalHelper':{'version':garment_component_proposals.VERSION,
            'moduleSha256':_sha(Path(garment_component_proposals.__file__).read_bytes())}}
    key = _sha(_json(identity).encode())
    folder = Path(cache_root).resolve() / VERSION / key
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'receipt.json'
    embeddings_cache = Path(cache_root).resolve() / 'embeddings'
    with LOCK:
        resumed = None
        original_run = None
        if manifest.exists():
            receipt = json.loads(manifest.read_text('utf-8'))
            if receipt.get('identity') != identity:
                raise SelectionRejected('选区缓存身份不符', receipt, code='selection_cache_mismatch')
            if receipt.get('verified') is True:
                path = Path(receipt.get('maskPath') or (folder / 'mask.png'))
                if not _within(path, folder):
                    raise SelectionRejected('选区缓存图片不在当前源图缓存内', receipt, code='selection_cache_mismatch')
                if path.is_file() and _sha(path.read_bytes()) == receipt.get('maskPngSha256'):
                    mask = Image.open(path).convert('L')
                    if mask.size == source.size and _pixels(mask, 'L') == receipt.get('maskPixelSha256'):
                        return mask, {**receipt, 'cacheReused': True}
                raise SelectionRejected('选区缓存图片哈希不符，未重新付费分析', receipt, code='selection_cache_mismatch')
            if receipt.get('state') in ('rejected', 'unknown'):
                info = local_failure_resume_info(receipt, folder, cache_root) if resume_local_error else None
                if not info or not info['eligible']:
                    raise SelectionRejected('此原图的自动选区尚未通过，保留原失败证据', receipt)
                resumed = _archive_local_failure(manifest, info)
                original_run = Path(info.get('originalRunPath') or folder)
            elif receipt.get('state') == 'processing':
                raise SelectionRejected('原选区工作没有明确终态，先核对原任务，未重新分析', receipt,
                    code='automatic_selection_unknown')
        _guard_unresolved_intents(cache_root, identity, manifest)
        run_path = folder
        if resumed is not None:
            for serial in range(1, 10000):
                run_path = folder / ('r' + str(serial).zfill(2))
                try:
                    run_path.mkdir()
                    break
                except FileExistsError:
                    continue
            else:
                raise SelectionRejected('本地接续目录已达上限，保留原回执', receipt)
        receipt = {'version': VERSION, 'identity': identity, **identity, 'state': 'processing',
            'verified': False, 'accepted': False, 'humanReviewed': False, 'attempts': [],
            'cacheManifestPath': str(manifest), 'created': time.time(), 'imageGenerationSubmitted': False}
        receipt['embeddingsCachePath'] = str(embeddings_cache)
        receipt['runPath'] = str(run_path)
        if resumed is not None:receipt['resumedLocalFailure'] = resumed
        if initial_feedback is not None:receipt['initialFeedback'] = copy.deepcopy(initial_feedback)
        _write(manifest, receipt)
        stage = 'local_labels'
        try:
            cloth, human, model_meta = backend.labels(source)
            evidence = _local_evidence(source, kind, np.asarray(cloth), np.asarray(human), protected)
            receipt['localModels'] = model_meta
            np.savez_compressed(run_path / 'local-labels.npz', cloth=cloth, human=human)
            _save_image(source, run_path / 'source.png')
            _save_image(evidence['coarse'], run_path / 'coarse.png')
            proposals=garment_component_proposals.propose(source,kind,evidence,max_regions=6)
            proposal_context=proposals['context'];proposal_montage=proposals['montage']
            if proposal_context.get('sourcePixelSha256')!=identity['sourcePixelSha256']:
                raise ValueError('候选源图哈希与当前任务不符')
            proposal_path=run_path/'source-proposals.json';_write(proposal_path,proposal_context)
            receipt['sourceProposals']={'version':garment_component_proposals.VERSION,
                'unverifiedHypothesis':True,'certifiesSelection':False,
                'contextPath':str(proposal_path),'contextSha256':_sha(proposal_path.read_bytes()),
                'regionCount':len(proposal_context['regions'])}
            if proposal_montage is not None:
                montage_path=run_path/'source-proposals.png';_save_image(proposal_montage,montage_path)
                receipt['sourceProposals'].update(montagePath=str(montage_path),
                    montagePngSha256=_sha(montage_path.read_bytes()),montagePixelSha256=_pixels(proposal_montage,'RGB'))
            current = evidence['coarse']
            prior_feedback = copy.deepcopy(initial_feedback)
            prior_independent_review = None
            accumulated_background = Image.new('L', source.size)
            background_proofs = []
            conservation_prior = None
            for attempt in range(max_attempts):
                attempt_folder = run_path / f'attempt-{attempt + 1:02}'
                attempt_folder.mkdir(exist_ok=True)
                entry = {'number': attempt + 1, 'state': 'planning'}
                receipt['attempts'].append(entry)
                _write(manifest, receipt)
                context = {'kind': kind, 'sourceSize': list(source.size), 'sourcePixelSha256': identity['sourcePixelSha256'],
                    'attempt': attempt + 1, 'localModelCounts': {'primary': int(evidence['primary'].sum()),
                    'independentConsensus': int(evidence['consensus'].sum())}, 'previousFailure': prior_feedback}
                if subject is not None:context['subject'] = copy.deepcopy(subject)
                context['sourceProposals']=copy.deepcopy(proposal_context)
                plan_images = [source, _overlay(source, current)]
                if proposal_montage is not None:plan_images.append(proposal_montage)
                plan_instruction=PLAN_INSTRUCTION.replace('{kind}',kind)+PLAN_PROPOSAL_INSTRUCTION
                if original_run is not None:
                    reused = _reuse_completed_call(original_run / f'attempt-{attempt + 1:02}' / 'plan.json',
                        attempt_folder / 'plan.json', plan_instruction, context, plan_images,
                        required=attempt == 0)
                    entry['planReusedFrom'] = reused or None
                    if not reused:entry['newPlanReason'] = 'new_actual_local_or_quality_feedback'
                plan = _vision_call(vision, attempt_folder, 'plan', plan_instruction, context, plan_images)
                entry['plan'] = plan
                try:
                    instance_mask, instance_audit = _instance_protection(source, plan, evidence,
                        prior_independent_review)
                    background_mask, background_audit = _background_protection(source, plan, evidence,
                        prior_independent_review)
                    old_background = np.asarray(accumulated_background) > 0
                    combined_background = old_background | (np.asarray(background_mask) > 0)
                    accumulated_background = Image.fromarray(combined_background.astype('uint8')*255)
                    background_audit['carriedSourceBackgroundPixels'] = int(old_background.sum())
                    if background_audit['protectedPixels']:
                        background_proofs.append(_sha(_json(background_audit).encode()))
                    background_audit['retainedProofSha256'] = list(background_proofs)
                    relocations = {r['index']:r['toPixels'] for r in background_audit['relocatedNegativePoints']}
                    points, protection, compiled = _compile_plan(plan, source.size, evidence, protected,
                        instance_protection=instance_mask, background_protection=accumulated_background,
                        background_relocations=relocations)
                    attempt_evidence, recovery = _recover_domain(source, evidence, points, protection)
                    automatic_points, automatic_audit = _source_cloth_anchors(source, evidence, points, protection)
                    points['sourceClothAnchors'] = automatic_points
                    points['sourceClothRidgePixels'] = automatic_audit['sourceClothRidgePixels']
                    compiled['candidateDomainRecovery'] = recovery
                    compiled['instanceSeparation'] = instance_audit
                    compiled['automaticSourceConstraints'] = automatic_audit
                    compiled['sourceBackgroundSeparation'] = background_audit
                    entry.update(points=points, compiled=compiled)
                    _save_image(protection, attempt_folder / 'protection.png')
                    _save_image(instance_mask, attempt_folder / 'instance-protection.png')
                    _save_image(accumulated_background, attempt_folder / 'background.png')
                    _save_image(attempt_evidence['coarse'], attempt_folder / 'candidate-domain.png')
                    stage = 'local_select'
                    embeddings_cache.mkdir(parents=True, exist_ok=True)
                    candidate, selection_receipt = backend.select(source, attempt_evidence['coarse'], protection, points, embeddings_cache)
                    stage = 'local_matte'
                    candidate, matte_receipt = backend.matte(source, candidate, protection, points)
                    if candidate.size != source.size:
                        raise ValueError('本地分割输出尺寸与原图不一致')
                    a = np.asarray(candidate.convert('L')).copy()
                    a[np.asarray(source.getchannel('A')) == 0] = 0
                    candidate = Image.fromarray(a)
                    stage = 'persist_local_images'
                    _save_image(candidate,attempt_folder/'new-mask.png')
                    candidate,conservation=_conserve_miss_only(source,candidate,protection,conservation_prior,
                        identity['sourcePixelSha256'])
                    conservation['newCandidateMaskPath']=str(attempt_folder/'new-mask.png')
                    conservation['newCandidatePngSha256']=_sha((attempt_folder/'new-mask.png').read_bytes())
                    entry['internalConservation']=conservation
                    _save_image(candidate, attempt_folder / 'mask.png')
                    overlay = _overlay(source, candidate)
                    _save_image(overlay, attempt_folder / 'overlay.png')
                    quality = _quality(candidate, source, points, protection, attempt_evidence)
                    entry.update(selection=selection_receipt, matting=matte_receipt, quality=quality)
                    # A numeric failure is still supplied to independent vision;
                    # vision may diagnose it but cannot waive the failed gate.
                    current = candidate
                    stage = 'review_vision'
                    review_context = {'kind': kind, 'attempt': attempt + 1, 'numericGate': quality}
                    review_context['pointDiagnostics']=compiled['pointDiagnostics']
                    review_context['internalConservation']=conservation
                    if subject is not None:review_context['subject'] = copy.deepcopy(subject)
                    if original_run is not None:
                        reused = _reuse_completed_call(original_run / f'attempt-{attempt + 1:02}' / 'review.json',
                            attempt_folder / 'review.json', REVIEW_INSTRUCTION.replace('{kind}', kind), review_context, [source, overlay])
                        entry['reviewReusedFrom'] = reused or None
                    reviewed = _review(_vision_call(vision, attempt_folder, 'review', REVIEW_INSTRUCTION.replace('{kind}', kind),
                        review_context, [source, overlay]))
                    entry.update(independentReview=reviewed, state='accepted' if quality['accepted'] and reviewed['accepted'] else 'rejected')
                    current = candidate
                    if entry['state'] == 'accepted':
                        stage = 'persist_acceptance'
                        _save_image(candidate, run_path / 'mask.png')
                        _save_image(overlay, run_path / 'overlay.png')
                        receipt.update(state='accepted', verified=True, accepted=True, quality=quality,
                            independentReview=reviewed, maskPath=str(run_path / 'mask.png'), overlayPath=str(run_path / 'overlay.png'),
                            maskPixelSha256=_pixels(candidate, 'L'), maskHashEncoding='l8_top_to_bottom',
                            maskPngSha256=_sha((run_path / 'mask.png').read_bytes()), completed=time.time())
                        _write(manifest, receipt)
                        return candidate, receipt
                    prior_feedback = {'numericGate': quality, 'independentReview': reviewed, 'previousPlan': plan,
                        'pointDiagnostics':compiled['pointDiagnostics']}
                    prior_independent_review = copy.deepcopy(reviewed)
                    conservation_prior={'number':attempt+1,'mask':candidate.copy(),'quality':copy.deepcopy(quality),
                        'review':copy.deepcopy(reviewed),'sourcePixelSha256':identity['sourcePixelSha256'],
                        'maskPath':str(attempt_folder/'mask.png')}
                except (ValueError, TypeError) as error:
                    conservation_prior=None
                    entry.update(state='rejected', error=str(error)[:2000])
                    prior_feedback = {'error': str(error), 'previousPlan': plan}
                    diagnostics=getattr(error,'point_diagnostics',None) or entry.get('compiled',{}).get('pointDiagnostics')
                    if diagnostics:
                        entry['pointDiagnostics']=diagnostics
                        prior_feedback['pointDiagnostics']=diagnostics
                _write(manifest, receipt)
            receipt.update(state='rejected', verified=False, accepted=False, completed=time.time(),
                error=f'自动选区在{max_attempts}次有界分析后仍未通过，未交付未核实蒙版')
            _write(manifest, receipt)
            raise SelectionRejected(receipt['error'], receipt)
        except SelectionRejected:
            raise
        except VisionCallUnknown as error:
            receipt.update(state='unknown', error=str(error)[:2000], verified=False, accepted=False)
            _write(manifest, receipt)
            raise SelectionRejected('自动选区中断；原调用和诊断已保留，未自动重复提交', receipt,
                code='automatic_selection_unknown') from error
        except Exception as error:
            receipt.update(state='rejected', error=str(error)[:2000], verified=False, accepted=False)
            if isinstance(error, OSError):
                receipt['localFailure'] = {'exceptionType': type(error).__name__, 'errno': error.errno,
                    'winerror': getattr(error, 'winerror', None), 'filename': str(error.filename) if error.filename else None,
                    'stage': stage}
            _write(manifest, receipt)
            raise SelectionRejected('自动选区未通过；诊断已保存，未认证蒙版：' + str(error), receipt) from error
