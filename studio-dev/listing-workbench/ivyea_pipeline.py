"""IvyeaOps visual-director adapter. AGPL-3.0; see SOURCE-NOTICE.md.
Original director template and deterministic renderer are in ivyea_render_core.
Existing products, source evidence, auth and providers remain the storage boundary.
"""
import base64
import hashlib
import io
import json
import re
import time
import uuid
from types import SimpleNamespace
import ivyea_render_core as core
from ivyea_white_source import _white_background_score
from storyboard_variety import SCENE_FIELDS, gallery_issues, is_scene

MIN_PRODUCT_IMAGE_EDGE = 500
SUPPLIER_IMAGE_URL = re.compile(
    r'(https://cbu01\.alicdn\.com/[^?#]+?\.(?:jpe?g|png|webp))'
    r'(?:_(sum\.jpg|b\.jpg|\.webp|\d+x\d+(?:[a-z]\d+)*\.(?:jpe?g|png|webp)))?'
    r'(?:[?#].*)?', re.IGNORECASE)

IDENTITY = '''You are stage 1 of an ecommerce visual-director pipeline. Inspect the physical product before designing a gallery. Image 1 is the sole identity truth. Other images may support details only. Return JSON:
{"category_family":"specific family","object_behavior":"soft_goods|rigid_device|spatial_gear|category_specific","reference_presentation":"worn|flat|other|unknown","form_and_scale":"physical structure, flexibility, orientation","materials_and_finish":[],"product_colours":[],"supporting_palette":["five #RRGGBB colours"],"fidelity_anchors":["exact logo/label location, seams, closure, pockets, colours, silhouette"],"natural_interactions":[],"scene_families":[],"visual_opportunities":[],"avoid":[],"uncertainties":[]}
Also return "source_assessment":{"usable_views":[],"missing_views":[],"resolution_limits":[],"variant_references":[],"unsupported_claims":[]}. Identify which reference is an alternate SKU rather than another angle. Distinguish an actual physical detail from a promotional illustration. State when available photos cannot support a proposed image.
Return "reference_views":[{"index":0,"identity_match":"primary","angle":"three-quarter","visible":["directly visible construction"]}]. Include one entry per supplied reference with its zero-based index. For other images, identity_match must be "same_sku" only if the visible colour, pattern and distinguishing construction match image 1; use "different_sku" for a visible contradiction or "unverified" when insufficient. An opened collar or zipper and a different wearer pose are garment states, not by themselves a different SKU. Do not assume obscured details match: list only visible supporting construction and keep hidden parts unknown. Use exactly one observed angle from the input options, or "unknown". For a wearer judge the camera relative to the visible torso and garment, never the face or gaze. A crop, montage, partial occlusion or small image requires "unknown" only when the remaining visible garment cannot establish its viewing angle. Do not infer an unseen view. Record only what the photo visibly proves.
Do not infer waterproofing, warmth rating, material composition, package contents or dimensions from appearance. Separate source marketing graphics from physical product. Interior labels must remain attached to inside collar and be hidden by a wearer. Do not describe a label as an exterior feature. Never turn floating flames or supplier text into product attributes.'''

APPAREL_GALLERY_DIRECTION = (
    'Follow the IvyeaOps soft-goods sequence: white main image, core benefit, one material detail, real usage, '
    'evidence-backed comparison, verified fit or specifications, and a closing image. Reorder or replace roles based '
    'on available evidence. If comparison, measurements or package imagery lack evidence, use a distinct supported '
    'wearing scene, styling idea, or silhouette and length view. Never fill those slots with more detail crops. '
    'Use at most one standalone macro. Keep the garment prominent, with tight real wearing scenes '
    'and no arbitrary limit on hero compositions. No layout may be used more than twice. Show genuine '
    'differences in pose, framing, buyer question and scene while preserving the same sellable garment. '
    'On wearer cards with a visible face, specify head posture and gaze for each shot. Vary where the wearer looks, '
    'and do not copy a downward gaze from the reference unless the shot specifically calls for it.'
)
APPAREL_SEVEN_DIRECTION = (
    'USER-REQUESTED SEVEN-IMAGE CONTRACT: EXACTLY one pure-white main in slot1; '
    'two different evidence-backed construction detail images in slots2-3; '
    'three tight natural lifestyle photographs in slots4-6; one actual size guide in slot7. '
    'The single size guide is shared UNCHANGED by every colour and size variant. '
    'Details must show two distinct real structures, large and useful. No fabricated views, claims or measurements. '
    'Lifestyle images vary pose plus framing/composition, retain only verified angles and prominent complete garment structure. '
    'The three lifestyle photographs may use human_context three times with genuine shot diversity; other layout families at most twice. '
    'No advertising panels or detail collage may substitute for the three natural lifestyle jobs. '
    'Keep source garment colour under neutral daylight, and respect the original templates only in their intended detail/selling-point slots. '
    'On visible wearer faces specify posture and gaze, not a repeated downward source pose.'
)


APPAREL_NO_FILLER_DIRECTION = (
    'HIGHEST-PRIORITY APPAREL CREATIVE RULE: follow product identity analysis, a shared visual DNA, '
    'a distinct buyer question and an evidence-backed shot for every image. Do not mechanically copy '
    'the electronics examples, oversized spec-number panels, or a fixed packaging slot into clothing. '
    'Every image except a complete factual size table must visibly show the actual garment, a useful '
    'visible garment detail, or the garment being worn. Never use product_presence=absent for a clothing '
    'name, neckline slogan, material-percentage card, quantity card or package-contents card. '
    'One Top Included, 1 Pcs, 95% Polyester and similar statements cannot occupy a standalone slot. '
    'Include verified composition or quantity only as quiet supporting copy on a useful product image. '
    'Design the seven-image narrative around exact appearance, the main design benefit, one real material '
    'detail, genuine wearing context, a visible construction feature, distinct fit/drape or styling information, '
    'and the verified size guide. Adapt these jobs to the available evidence; do not manufacture a claim or view. '
    'If only the front view is verified, different wearing scenes may retain that front angle. Make the pose '
    'different and change at least one of framing or composition; do not invent an unseen angle just for variety. '
    'A new background alone and repeating the main wearer image as an inset do not add a new image job. '
    'Preserve meaningful product scale, concise factual copy, and a coherent set design. Do not fill seven slots '
    'by hiding the product behind typography, decorative number posters or blank caption boards. '
    'REUSABLE COLOUR MASTER: the whole gallery will also be recoloured from this master. Place readable copy '
    'in non-garment negative space or a small opaque neutral copy panel with contrasting lettering. Never rely '
    'on white lettering directly over dark cloth or dark lettering directly over pale cloth; the cloth colour '
    'will change while the approved words stay fixed. Keep the photograph dominant and the copy panel compact.'
)


def check_apparel_gallery(images, *, forbid_filler=False, seven_policy=False):
    if forbid_filler:
        quantity_question=re.compile(r'\b(?:package contents|what.?s in the box|what is included|what comes (?:in|with)|how many|one (?:top|item|piece) included)\b|包装数量|包装清单|包含几件|有几件|数量说明|件数说明',re.I)
        for index,image in enumerate(images):
            actual_size_table=bool(index==len(images)-1 and image.get('size_chart') and re.search(r'\d',str(image.get('supporting_text',''))))
            if image.get('product_presence')=='absent' and not actual_size_table:
                raise ValueError(f'第 {index+1} 张服装图不能用无商品的纯文字卡凑数，请安排有依据的商品展示。')
            if quantity_question.search(str(image.get('role',''))+' '+str(image.get('buyer_question',''))):
                raise ValueError(f'第 {index+1} 张不能单独说明包装或件数；把数量并入有实际展示价值的图片。')
    detail_count=sum(core._layout_family(image)=='detail_macro' or image.get('shot_type')=='detail' for image in images)
    if seven_policy:
        from shared_size_chart import check_seven
        check_seven(images)
    elif detail_count>1:
        raise ValueError('服装套图最多安排一张独立细节特写，其余图位请用不同穿着场景、版型或搭配表达。')
    # No arbitrary hero quota or mandatory distant scene: product prominence
    # follows the buyer question. Original historical plans remain unchanged.


def size_chart_evidence(*candidates):
    """Prefer usable supplier dimensions over a previously linked competitor table."""
    usable=[]
    for chart in candidates:
        if not isinstance(chart,dict):
            continue
        columns,rows=chart.get('columns'),chart.get('rows')
        if (not chart.get('units') or not (chart.get('sourcePage') or chart.get('sourceImage'))
                or not isinstance(columns,list) or len(columns)<2 or not isinstance(rows,list) or not rows
                or any(not isinstance(row,list) or len(row)!=len(columns) or not all(row) for row in rows)):
            continue
        usable.append(chart)
    return next((chart for chart in usable if chart.get('sourceKind')=='supplier'),usable[0] if usable else None)


def size_chart_copy(chart):
    columns=' | '.join(map(str,chart['columns']))
    rows=[' | '.join(map(str,row)) for row in chart['rows']]
    return '\n'.join([f"{columns} ({chart['units']})",*rows])


def project_size_chart(product, previous):
    """Explicit current evidence wins over charts retained in old projects."""
    supplier = product.get('supplierSizeEvidence')
    competitor = product.get('competitorSizeEvidence')
    if isinstance(supplier, dict) or isinstance(competitor, dict):
        return size_chart_evidence(
            {**supplier, 'sourceKind':'supplier'} if isinstance(supplier, dict) else None,
            competitor)
    return size_chart_evidence(*(item.get('sizeEvidence') for item in previous))


def required_size_chart(product, gallery, sizes):
    """Return the identity of the reviewed seventh image for apparel delivery."""
    import creative_skills
    from supplier_variants import _size

    if creative_skills.select(product)['category'] != 'apparel':
        return None
    chart = size_chart_evidence(gallery.get('_sizeChartEvidence'))
    if not chart or not (chart.get('sourceKind') in ('supplier','physical_measurement') or (
            chart.get('sourceKind') == 'competitor' and chart.get('sameProductVerified') is True
            and re.fullmatch(r'[A-Z0-9]{10}', str(chart.get('sourceAsin'))))):
        raise ValueError('待补尺码：服装必须有供应商、实测或已核实同款竞品的尺码表')
    if any(not all(re.search(r'\d', str(value)) for value in row[1:]) for row in chart['rows']):
        raise ValueError('待补尺码：尺码表必须包含实际测量数值')
    expected = {_size(str(size or '')) for size in sizes}
    if not expected or '' in expected or not expected <= {_size(str(row[0])) for row in chart['rows']}:
        raise ValueError('待补尺码：尺码表必须覆盖所有拟刊登尺码')
    images = gallery.get('images') or []
    if len(images) != 7 or images[-1].get('size_chart') is not True:
        raise ValueError('待补尺码：服装第7张必须是尺码图')
    card = images[-1]
    review = card.get('render_qa') or {}
    digest = (review.get('technical') or {}).get('sha256')
    if (not card.get('_runId') or review.get('ready') is not True or not re.fullmatch(r'[0-9a-f]{64}', str(digest))
            or review.get('manual_visual_review_required') and card.get('human_reviewed') is not True):
        raise ValueError('待补尺码：服装第7张尺码图须完成数值、单位及成图校对')
    selection = product.get('generatedGallerySelection')
    if selection is not None:
        selected = selection.get('items', []) if isinstance(selection, dict) else []
        if (not isinstance(selected, list) or len(selected) != 7
                or not isinstance(selected[6], dict) or selected[6].get('sha256') != digest):
            raise ValueError('待补尺码：所选套图第7张与已校对尺码图不一致')
    return digest


def select_product_truth(refs, encode, asin_truth=None):
    """IvyeaOps order: eligible uploads first, then eligible source images."""
    # When an explicit brief leads with this product's captured ASIN main,
    # preserve that identity anchor. A cleaner secondary catalog rendering may
    # depict a different collar/cuff construction despite sharing a listing.
    if asin_truth and refs and refs[0]==asin_truth['url']:
        selected=next(clear_product_images([refs[0]],encode),None)
        if selected:
            ref,encoded,_=selected
            return [ref,*[other for other in refs if other!=ref]],encoded
    for ref in sorted(dict.fromkeys(refs), key=lambda value: not value.startswith('/uploads/')):
        try:
            encoded=encode(ref)
            raw=base64.b64decode(encoded.split(',',1)[1],validate=True)
        except (ValueError,IndexError,OSError):
            continue
        if _white_background_score(raw)['ready']:
            return [ref,*[other for other in refs if other!=ref]],encoded
    # Explicitly selecting the current, captured ASIN main must have the same
    # fallback as automatic selection. Other non-white references remain details.
    if asin_truth and asin_truth['url'] in refs:
        fallback=next(clear_product_images([asin_truth['url']],encode),None)
        if fallback:
            ref,encoded,_=fallback
            return [ref,*[other for other in refs if other!=ref]],encoded
    raise ValueError('没有通过白底检测的同款商品真值图，请上传白底原图后再策划')


def clear_product_images(refs, encode):
    from PIL import Image

    groups = {}
    for ref in sorted(dict.fromkeys(refs), key=lambda value: not value.startswith('/uploads/')):
        match = SUPPLIER_IMAGE_URL.fullmatch(ref)
        key, variant = match.groups() if match else (ref, None)
        versions = groups.setdefault(key, [])
        if variant:
            variant = variant.lower()
            size = re.match(r'(\d+)x(\d+)', variant)
            if variant == 'sum.jpg' or (size and min(map(int, size.groups())) < MIN_PRODUCT_IMAGE_EDGE):
                continue
        versions.append((ref, variant is None))

    for versions in groups.values():
        best_rank = (False, 0)
        best = None
        for ref, original in versions:
            try:
                encoded = encode(ref)
                raw = base64.b64decode(encoded.split(',', 1)[1], validate=True)
                with Image.open(io.BytesIO(raw)) as image:
                    width, height = image.size
                    if min(width, height) < MIN_PRODUCT_IMAGE_EDGE:
                        continue
                    image.verify()
            except (ValueError, IndexError, OSError, SyntaxError):
                continue
            rank = (original, width * height)
            if rank > best_rank:
                best_rank = rank
                best = (ref, encoded, raw)
        if best:
            yield best


def captured_asin_truth(product):
    from asin_reference import ASIN, media_key

    imported=product.get('sourceImport') or {}
    asin=product.get('asin') or imported.get('asin')
    if not isinstance(asin,str) or not ASIN.fullmatch(asin):
        return None
    capture=product.get('editorAsinReference') or {}
    if (not capture.get('capturedAt') or capture.get('selectedAsin')!=asin
            or capture.get('market')!=(product.get('market') or imported.get('market') or 'US')):
        return None
    # A multi-colour source ASIN may be a different child from the selected
    # master. Use the already validated same-colour child's actual main image.
    if product.get('masterColor'):
        import variant_colours
        group=variant_colours.catalog(product).get(variant_colours.colour_key(product['masterColor']))
        if group and group.get('ready'):
            main=next((ref for ref in group['references']
                       if ref.get('referenceType')=='amazon_variant_main'),None)
            if main:
                return {'kind':'asin_main','asin':main['sourceAsin'],'url':main['url']}
    images=capture.get('referenceImages') or []
    if images and media_key(images[0]):
        return {'kind':'asin_main','asin':asin,'url':images[0]}
    return None


def select_automatic_product_truth(refs, encode, asin_truth=None):
    candidates = clear_product_images(refs, encode)
    details = []
    for ref, encoded, raw in candidates:
        if _white_background_score(raw)['ready']:
            truth = (ref, encoded)
            break
        if len(details) < 3:
            details.append((ref, encoded))
    else:
        fallback=next(clear_product_images([asin_truth['url']],encode),None) if asin_truth else None
        if fallback is None:
            raise ValueError(f'未找到短边至少 {MIN_PRODUCT_IMAGE_EDGE} 像素的同款白底商品图，请补传清晰原图或采集本款 ASIN 主图后再策划')
        return [fallback[:2],*[detail for detail in details if detail[0]!=fallback[0]]]

    while len(details) < 3:
        candidate = next(candidates, None)
        if candidate is None:
            break
        details.append(candidate[:2])
    return [truth, *details]


def analyze_layout_references(product, visual, product_truth=''):
    refs=(product.get('editorAsinReference') or {}).get('referenceImages') or (
        product.get('sourceImport',{}).get('amazon') or {}).get('referenceImages') or []
    refs=[ref for ref in refs if ref!=product_truth]
    if len(refs)<4:
        return [], '竞品套图不足4张，已按商品真值独立策划'
    indexed={}
    for index,ref in enumerate(refs[:8],1):
        try:
            indexed[index]=(ref,visual.encode_reference(ref))
        except (ValueError,OSError):
            continue
    if len(indexed)<4:
        return [], '可读取的竞品图不足4张，已跳过版式分析'
    templates=[]
    for offset in range(0,len(indexed),4):
        indices=list(indexed)[offset:offset+4]
        try:
            analysis=visual.model_json(
                'Reverse-engineer each competitor image as layout only. Do not use its product, brand, text or claims. '
                'Return {"templates":[{"index":1,"shot_type":"...","layout":"...","buyer_question":"...",'
                '"visual_structure":"framing, subject scale, negative space and information hierarchy"}]}. '
                'Use the provided original image indices, one per image.',
                {'indices':indices,'shotTypes':list(core._LAYOUT_DEFAULT_BY_TYPE),'layouts':list(core._LAYOUT_FAMILIES)},
                [indexed[i][1] for i in indices])
        except Exception:
            continue
        for item in analysis.get('templates',[]):
            if not isinstance(item,dict) or type(item.get('index')) is not int or item['index'] not in indices:
                continue
            if item.get('layout') not in core._LAYOUT_FAMILIES or item.get('shot_type') not in core._LAYOUT_DEFAULT_BY_TYPE:
                continue
            templates.append({'index':item['index'],'url':indexed[item['index']][0],
                              'layout':item['layout'],'shot_type':item['shot_type'],
                              'visual_structure':str(item.get('visual_structure',''))[:500],
                              'buyer_question':str(item.get('buyer_question',''))[:160]})
    return templates, '' if templates else '视觉模型未返回有效版式，已按商品真值独立策划'


def normalize_reference_views(raw, refs):
    """Bind vision observations to the original inputs, never model-provided URLs."""
    entries = raw if isinstance(raw, list) else []
    observations = []
    for index, ref in enumerate(refs):
        matches = [item for item in entries if isinstance(item, dict)
                   and type(item.get('index')) is int and item['index'] == index]
        item = matches[0] if len(matches) == 1 else {}
        identity = item.get('identity_match')
        angle = item.get('angle')
        visible = item.get('visible')
        observations.append({
            'index': index,
            'url': ref,
            'identity': 'primary' if index == 0 else (
                identity if identity in ('same_sku', 'different_sku') else 'unverified'),
            'angle': angle if isinstance(angle, str) and angle in SCENE_FIELDS['angle'][1] else '',
            'visible': [value.strip()[:240] for value in visible[:6]
                        if isinstance(value, str) and value.strip()] if isinstance(visible, list) else [],
        })
    return observations


def shot_source(project, index):
    """Resolve one product photo and any angle restriction for this saved card."""
    refs = project.get('references', [])
    card = (project.get('uiPlan') or {}).get('images', [])
    card = card[index] if card else {}
    if card.get('production_method') == 'blocked':
        reason = str(card.get('missing_evidence') or '缺少已核实的商品事实或实拍角度').strip()
        return None, None, f'第 {index+1} 张分镜已标记不可制作：{reason}'
    if card.get('product_presence') == 'absent':
        return None, None, ''
    primary = refs[0] if refs else None
    views = (project.get('analysis') or {}).get('referenceViews')
    if views is None:
        if is_scene(card) and (project.get('engine') or {}).get('name') == 'IvyeaOps source migration':
            return primary, None, f'第 {index+1} 张是历史场景分镜，请重新策划以核实实拍角度。'
        return primary, None, ''
    sources = [view for view in views if view['identity'] in ('primary', 'same_sku')
               and view['url'] in refs and view['visible']]
    supplier_refs = (project.get('analysis') or {}).get('supplierReferences', [])
    if card.get('size_chart'):
        supplier_source = next((view for view in sources if view['url'] in supplier_refs), None)
        if supplier_source:
            return supplier_source['url'], supplier_source, ''
    if not is_scene(card):
        # The planner orders the photos needed for this shot. Keep one verified
        # product truth instead of silently substituting the set's first photo.
        preferred = card.get('source_reference_indices') or []
        for position in preferred if isinstance(preferred, list) else []:
            if type(position) is not int or not 0 <= position < len(refs):
                continue
            selected = next((view for view in sources if view['url'] == refs[position]), None)
            if selected:
                return selected['url'], selected, ''
        return primary, next((view for view in sources if view['url'] == primary), None), ''
    direction = card.get('scene_direction') or {}
    angle = direction.get('angle') if isinstance(direction, dict) else None
    options = SCENE_FIELDS['angle'][1]
    if not isinstance(angle, str) or angle not in options:
        return primary, None, f'第 {index+1} 张场景图请先选择镜头角度。'
    eligible = [view for view in sources if view['angle'] == angle]
    preferred=card.get('source_reference_indices') or []
    linked=[view for position in preferred if type(position) is int and 0<=position<len(refs)
            for view in eligible if view['url']==refs[position]] if isinstance(preferred,list) else []
    # Keep the verified scene angle and supplier priority, but apply them to
    # the photos actually linked by this shot. Another same-angle photograph
    # may hide the very waist/hem construction this card needs to show.
    candidates=linked or eligible
    source = next((view for view in candidates if view['url'] in supplier_refs), candidates[0] if candidates else None)
    if source:
        return source['url'], source, ''
    return primary, None, f'第 {index+1} 张缺少可核实的同款{options[angle]}实拍。请改用已核实角度，或补图后重新策划。'


def compile_project(project,index):
    import studio_bridge
    plan=project.get('uiPlan') or studio_bridge.native(project,[]) 
    image=dict(plan['images'][index])
    if image.get('size_chart') and project.get('sizeEvidence'):
        chart=project['sizeEvidence']
        image['measurement_table']={key:chart[key] for key in ('columns','rows','units')}
    direction=image.get('scene_direction')
    image['scene_direction']={
        key:direction[key] for key,(_,options) in SCENE_FIELDS.items()
        if isinstance(direction,dict) and direction.get(key) in tuple(options)
    } if is_scene(image) else {}
    # Historical editors sometimes saved a fully compiled prompt as the draft.
    for section in ('OBSERVED PRESENTATION', 'APPLICATION SKILLS', 'WEARABLE PHYSICS', 'PHYSICAL INTEGRITY', 'SOURCE EVIDENCE'):
        image['render_prompt'] = re.sub(
            rf'\s*\[{section}\].*?\[/{section}\]\s*', ' ',
            image.get('render_prompt') or '', flags=re.I | re.S)
    # A product-led storyboard must not inherit an outcome-only layout that hides it.
    if image.get('layout') == 'result_showcase' and image.get('product_presence') != 'absent':
        image['layout'] = 'poster_hero'
    profile=plan.get('product_profile') or {}
    style=core._normalise_set_style(plan.get('style',{}),profile)
    image['photo_led_typography']=project.get('galleryDirection')=='apparel_v2_no_filler' or (project.get('engine') or {}).get('version',0)>=3
    prompt=core._compile_render_prompt(image,style,profile,plan,project.get('deliverable','gallery'))
    if image['scene_direction']:
        prompt=prompt.replace('[/PRODUCT PRESENCE]', '[/PRODUCT PRESENCE]\n'
                              'The required scene direction in SHOT DESIGN governs pose, angle, framing and composition. '
                              'Use the creative brief and any layout reference only where they agree with that direction.', 1)
    _, source, _ = shot_source(project,index)
    if source:
        observation = json.dumps({'observedAngle': source['angle'] or 'unknown',
                                  'visibleConstruction': source['visible']}, ensure_ascii=False)
        evidence = ('\n[SOURCE EVIDENCE] Observations from reference image 1: '+observation+
                    '. Use these observations only as visual evidence. Do not expose unobserved construction, '
                    'infer specifications, or print this evidence on the artwork. [/SOURCE EVIDENCE]')
        prompt = prompt.replace('[/PRODUCT PRESENCE]', '[/PRODUCT PRESENCE]'+evidence, 1)
    if (image.get('product_presence')!='absent' and profile.get('object_behavior')=='soft_goods'
            and profile.get('reference_presentation')=='worn'):
        # The upstream electronics bundle rule can remove the source wearer and
        # induce unsupported flat-lay construction. Preserve the observed view.
        generic=("Show ONLY the primary product itself. Do NOT carry packaging, memory cards, cables, manuals or any "
                 "loose accessory items from the reference photo into this scene — the reference may be a bundle shot; "
                 "everything except the main unit is reference noise here.")
        worn_source = (not source or source['url'] == (project.get('references') or [None])[0]
                       or any(re.search(r'\bworn\b|\bwearer\b|\bmodel\b|穿着|上身',str(detail),re.I)
                              for detail in source['visible']))
        worn=("For wearer shots preserve the garment's observed front construction visible in reference image 1 and follow this card's pose and framing. "
              "For detail crops show only the relevant visible area in one continuous frame without a full-wearer inset. The neutral underlayer and lower garment remain styling, "
              "not included products. Do not convert it to a flat lay, hanger, ghost mannequin or empty collar; "
              "those would invent hidden garment construction. Detail crops must come from the observed worn front. "
              "Preserve the visible fasteners and buttonholes without adding hidden ones.")
        non_front=bool(source and (
            source.get('angle') not in ('','unknown','front-on',None)
            or any(re.search(r'\brear\b|\bback (?:view|of|panel)\b|后背|背面|侧后',str(detail),re.I)
                   for detail in source.get('visible',[]))))
        if not worn_source:
            worn=("Reference image 1 is the selected, verified same-SKU product photograph for this card, not the set's original wearer photo. "
                  "Reproduce only its visible front, collar, seams, cuffs and hem. Follow this card's framing and presentation; "
                  "remove the source hanger, background and styling garments when the card requests the product alone. "
                  "Keep visible interior labels attached to their original garment panels. Do not invent unseen back construction, "
                  "label lettering or hidden seams. For a worn scene, keep interior labels physically occluded by the wearer.")
        if non_front:
            worn=("Reference image 1 is the selected, verified same-SKU photograph for this card. "
                  "Preserve only garment construction visible in its actual observed view, and follow this card's supported camera and framing. "
                  "Do not rotate it to the set's primary front view or reconstruct a hidden neckline, back panel, side seam, interior or hem. "
                  "Detail crops must come from the observed worn view, without a full-wearer inset. "
                  "Preserve physical occlusion and the photographed sleeve, waist and visible finish; hidden construction stays hidden. "
                  "Do not turn an observed worn view into a flat lay, hanger or ghost mannequin.")
        prompt=prompt.replace(generic,'')
        prompt+='\n[OBSERVED PRESENTATION] '+worn+' [/OBSERVED PRESENTATION]'
    if image.get('shot_type')=='white_main' and (project.get('analysis') or {}).get('productTruthSource'):
        prompt+='\nUse the sole product-truth reference image 1 to preserve the garment. Remove any hand-held props and jewelry from the final white-background main image.'
    # Local identity/occlusion safety supplements the upstream core.
    skill=project.get('creativeSkills')
    if skill:prompt+='\n[APPLICATION SKILLS] '+skill['rules'][skill['category']]+' [/APPLICATION SKILLS]'
    return prompt+'\n[WEARABLE PHYSICS] physical occlusion overrides label visibility. Skin must be free of copied product marks. Keep exterior markings attached to their original fabric panels. [/WEARABLE PHYSICS]'


def plan_project(data,product,listing,progress=None):
    import visual_studio as visual
    import creative_skills
    import review_insights
    import product_insights
    refs=data.get('references')
    automatic=refs is None
    asin_truth=captured_asin_truth(product)
    if automatic:
        refs=list(product_insights.source_images(product))
    elif not isinstance(refs,list) or not 1<=len(refs)<=4:
        raise ValueError('请提供 1–4 张同款参考图')
    count=data.get('count',7);kind=data.get('deliverable','gallery')
    if type(count) is not int or count not in range(4,9) or kind not in ('gallery','aplus'):raise ValueError('不支持的套图类型或张数')
    if progress:progress('white','校验白底商品图与本款 ASIN 主图',.08)
    if automatic:
        selected = select_automatic_product_truth(refs, visual.encode_reference, asin_truth)
        refs, reference_images = map(list, zip(*selected))
    else:
        refs, truth_image = select_product_truth(refs, visual.encode_reference, asin_truth)
        reference_images = [truth_image, *[visual.encode_reference(ref) for ref in refs[1:]]]
    use_asin_truth=bool(asin_truth and refs[0]==asin_truth['url'])
    facts={k:product.get(k,'') for k in ('name','material','style','dimensions','packageDimensions','productWeight','packageWeight','packageContents','features','targetAudience','colorNames','sizeNames','masterColor','copyNotes')}
    brief=visual.bounded(data.get('brief',''),4000)
    skill=creative_skills.select(product)
    apparel_gallery=kind=='gallery' and skill['category']=='apparel'
    apparel_aplus=kind=='aplus' and skill['category']=='apparel'
    chart=None
    if (apparel_gallery and count==7) or apparel_aplus:
        previous=visual.list_projects(product['id'])['projects']
        chart=project_size_chart(product,previous)
    if progress:progress('identity','识别同款商品外观与实拍角度',.25)
    vision=visual.vision_label()
    profile=visual.model_json(IDENTITY,{'ownProductFacts':facts,'referenceIndices':list(range(len(refs))),
                                       'angleOptions':list(SCENE_FIELDS['angle'][1])},
                              reference_images)
    if not isinstance(profile.get('fidelity_anchors'),list) or not profile['fidelity_anchors']:raise ValueError('视觉识别未得到产品身份锚点，不能继续生图')
    behavior=profile.get('object_behavior','category_specific')
    if behavior not in core._DEFAULT_SET_PALETTES:profile['object_behavior']='category_specific'
    reference_views = normalize_reference_views(profile.pop('reference_views', None), refs)
    supported_views = [{k:v for k,v in view.items() if k!='url'} for view in reference_views
                       if view['identity'] in ('primary','same_sku') and view['angle'] and view['visible']]
    # No mandatory size/packaging/comparison slot when facts cannot support one.
    narrative='1. white_main hero white_main: exact sellable product. Remaining images: choose distinct factual buyer questions based on the source assessment and creative brief. No mandatory lifestyle, size, packaging, comparison or colour chart. A macro must retain whole-product context when the crop alone is ambiguous. Do not fill missing evidence with invented views or repetitive crops.'
    if apparel_gallery:
        narrative=APPAREL_SEVEN_DIRECTION if count==7 else APPAREL_GALLERY_DIRECTION
    if kind=='aplus':
        narrative=('Build one brand story across a 1464x600 brand banner, primary benefit, usage or education, '
                   'an evidenced detail or comparison, and a trust close. Use one distinct buyer question per module. '
                   'Benefit or trust modules may show only the outcome when the product is unnecessary. '
                   'Do not include a white gallery main image.')
        prompt_direction=(
            'Design an editorial sequence with deliberate variation in subject scale, photograph placement and text '
            'position. Use the supplied type system with restraint. Headlines are short labels subordinate to the '
            'photography, with at most one short supporting sentence. Avoid repeated oversized bold titles, repeated '
            'left-copy/right-product banners, generic slogans, rounded information cards and decorative waves. '
            'Keep real materials, garment structure and useful information visually dominant. Use one quiet palette '
            'throughout. For clothing, a size module must show the actual sourced measurements, not size letters alone.'
        )
        narrative+=' '+prompt_direction
    ctx=json.dumps({'ownProductFacts':facts,'buyerQuestions':review_insights.context(product,product.get('market','UK'))},ensure_ascii=False)
    if progress and kind=='gallery':progress('templates','分析竞品套图的版式',.32)
    import official_image_templates as official_library
    official_count=count-(1 if kind=='gallery' else 0)-(1 if (apparel_gallery and count==7) or apparel_aplus else 0)
    official_records=official_library.assignments(product,max(1,official_count),kind,
        data.get('layoutTemplateIds') or data.get('officialTemplateIds'))
    templates=[{**r,'index':i,'layout':'official','shot_type':'official'} for i,r in enumerate(official_records)]
    layout_note='Original public template artwork and verbatim prompts, bound by immutable template ID'
    planning_images=[reference_images[0]]+[visual.encode_reference(r['url']) for r in official_records]
    template_text=json.dumps([{k:v for k,v in item.items() if k!='url'} for item in templates],ensure_ascii=False) if templates else ''
    insights=product_insights.context(product)
    insight_text=json.dumps(insights.get('observations',[]),ensure_ascii=False) if insights else ''
    tone=visual.bounded(data.get('visual_tone','natural'),100)
    prompt=core.planning_prompt(deliverable=kind,count_rule=f'Produce EXACTLY {count} images.',product_context=ctx,approved=json.dumps({k:listing.get(k,'') for k in ('title','bullets','description')},ensure_ascii=False),product_profile_text=json.dumps(profile,ensure_ascii=False),img_sp=insight_text,template_text=template_text,narrative_text=narrative,deliverable_rules='First image is pure white without added text.' if kind=='gallery' else 'All modules are wide A+; no white main image.',body=SimpleNamespace(visual_tone=tone,brief=brief,language=data.get('language','en')),color_directive='Adapt design to this product category. No electronics visual metaphors on apparel. Competitor reviews and listing are not proof; only own facts and visual observations support claims. Confirmed photo observations support visible design only; cite their IDs in internal evidence, never in artwork. If no measurements or package facts exist, replace those slots with supported detail or usage stories; never force empty spec cards.')
    prompt+='\nPLANNER FACT CHECK BEFORE OUTPUT: A visible stand collar does not prove that it stays upright, is unlined or has any hidden construction. Do not turn an observed part into a durability/performance claim. Do not assert exact closure counts when occluded. Keep the reference garment hue, not a guessed supplier color label. Do not invent extra variant garment images or exact fabric swatches from a single-color reference; use another supported detail composition instead. Do not add real measurements, wash instructions or a size chart when none is supplied. Keep uncertainty explicit in internal profile notes, never buyer-facing artwork.\nPRODUCTION ECONOMY: For every image return production_method (source_layout|local_recolor|generate_once|blocked), source_reference_indices (zero-based), reuse_strategy and missing_evidence. Prefer actual source pixels and one reusable master. Only use local recolor for a verified opaque colour change with a reliable colour reference and mask; never change prints, embossing, transparency, hardware or structure by recoloring. Real patterned SKU photos should reuse the layout directly. Generate once only when source composition cannot achieve the evidence-backed concept. Mark missing facts/views as blocked instead of inventing content. Planning never authorizes automatic paid rendering.'
    production_mode=data.get('productionMode','ai_master')
    if production_mode not in ('ai_master','source_layout'):
        raise ValueError('不支持的母版制作方式')
    if production_mode=='ai_master':
        prompt=prompt.split('\nPRODUCTION ECONOMY:')[0]
        prompt+='\nAI MASTER PRODUCTION: Return a distinct buyer question, factual selling point, evidence, visual concept, camera direction and final artwork copy for every image. Use production_method=generate_once for supported shots; use blocked only for genuinely missing evidence that cannot be solved by choosing another supported concept. Preserve exact physical product identity from references while designing polished scenes, useful detail compositions and clear purchase benefits. Return source_reference_indices, reuse_strategy and missing_evidence per shot. Planning alone does not submit rendering.'
        if kind=='gallery':
            prompt+=' Build one coherent AI master gallery in the exact selected color. Do not replace it with source-photo caption layouts or repetitive crops, or generate other colors.'
    prompt+='\nREFERENCE INDEX CONTRACT: source_reference_indices are zero-based integers: the first reference is 0, the second is 1. There are '+str(len(refs))+' references, so every selected index must satisfy 0 <= index < '+str(len(refs))+'. For a single reference use [0]. Never use one-based numbering in this field.'
    prompt+='\nSET VARIETY: Give each card a distinct visual concept and camera direction. For apparel vary the pose, framing or supported viewing angle across wearer shots. Do not repeat the hero pose as a background or inset on multiple cards. Let genuine detail close-ups fill the frame when the feature is clear. Only use angles and garment configurations supported by the actual references.'
    if kind=='gallery':
        prompt+='\nPlan each image on a native square canvas. Vary the type zone, hierarchy, subject scale, and use of negative space as the buyer question changes. Integrate any type into the photograph or designed surface rather than repeatedly attaching a headline panel. Keep the photograph or intentional background continuous to all four edges. A wide scene means a distant or wide-lens view within the square canvas. Do not propose letterboxing or pillarboxing.'
    if apparel_gallery:
        prompt+='\n'+APPAREL_NO_FILLER_DIRECTION
    choices={key:list(options) for key,(_,options) in SCENE_FIELDS.items()}
    prompt+=('\nFor every product-visible lifestyle, environmental, human_context or scenario_mosaic image '
             'return a scene_direction object with one exact value for each field from '
             +json.dumps(choices,ensure_ascii=False)
             +('. For apparel keep only verified camera angles, require different poses and at least one different framing or composition. '
               if apparel_gallery else '. Every pair of scene images must differ in all four fields. ')+ 'Changing the background alone does not count. '
             +('For the requested three lifestyle photographs the human_context family may occur three times, with distinct source-supported pose and framing/composition; other layout families at most twice.' if apparel_gallery and count==7 else 'Do not use any layout family more than twice.'))
    prompt+=('\nUse the verified per-photo views below for scene camera angles. A different SKU, a competitor layout, '
             'or the model’s ability to imagine another angle cannot prove an unseen view. If only one angle is verified, '
             +('retain it across supported scenes while varying pose and framing or composition. ' if apparel_gallery
               else 'use it for a single scene and design other cards as distinct supported non-scene concepts when possible. ')+
             'Leave a required unsupported scene visibly blocked for the operator. Verified views: '
             +json.dumps(supported_views,ensure_ascii=False))
    if apparel_gallery and count==7:
        prompt+=('\nSlot 7 is always a size guide. Use the real product photograph as a visible background layer '
                 'with a contrasting measurement table. Supplier size evidence takes priority; use a linked same-style '
                 'competitor table when supplier dimensions are unavailable. No invented data. '
                 'Size evidence: '+json.dumps(chart or {},ensure_ascii=False))
    if apparel_aplus:
        prompt+=(
            '\nThe last A+ module is a functional size-and-fit guide. Use the matching supplier photograph on one '
            'side and a readable, aligned table on the other. Include every sourced size, measurement column, value '
            'and unit. Do not replace the table with S/M/L/XL buttons or a size-range slogan. Table labels and values '
            'must remain readable on the native 1464x600 canvas. Supplier measurements take priority. '
            'Size evidence: '+json.dumps(chart or {},ensure_ascii=False)
        )
    if progress:progress('plan','AI 正在编排整套分镜',.4)
    apparel_orchestration=None
    if apparel_gallery or apparel_aplus:
        import apparel_suite
        prompt+='\n'+apparel_suite.formal_direction()
        apparel_orchestration={'version':apparel_suite.VERSION,
            'implementation':'independent-codex-reconstruction','formalSizeChartGateBypassed':False,
            'sourceReferenceOrder':list(refs),'originalUserBrief':brief,
            'facts':facts,'unverifiedInferences':profile.get('uncertainties',[])}
    planning_instruction=creative_skills.instruction(skill,'plan')+'\n'+prompt
    planning_context={'facts':facts,'referenceIndexMap':dict(enumerate(refs))}
    native=visual.model_json(planning_instruction,planning_context,planning_images)
    proposed=native.get('images')
    if apparel_gallery and isinstance(proposed,list) and len(proposed)==count and all(isinstance(card,dict) for card in proposed):
        try:
            check_apparel_gallery(proposed,forbid_filler=True,seven_policy=count==7)
        except ValueError as issue:
            if progress:progress('plan','调整未通过策略检查的服装分镜',.55)
            native=visual.model_json(
                planning_instruction+'\nRevise the complete set to resolve this deterministic strategy check: '+str(issue),
                {**planning_context,'previousStoryboard':proposed},planning_images)
    if progress:progress('compile','绑定实拍并检查图位可生成性',.85)
    images=native.get('images')
    if not isinstance(images,list) or len(images)!=count:raise ValueError('策划张数不完整，未保存通用模板')
    style=core._normalise_set_style(native.get('style',{}),profile)
    native.update(style=style,product_profile=profile,deliverable=kind,creative_brief=brief,visual_tone=tone,language=data.get('language','en'),planner='official-original-director-v4',product_source_url=refs[0])
    if apparel_orchestration:native['apparelOrchestration']=apparel_orchestration
    slots=[]
    used_templates=set()
    for i,image in enumerate(images):
        if not isinstance(image,dict) or not str(image.get('evidence','')).strip():raise ValueError('每张分镜必须有产品事实依据')
        image.pop('template_url',None)  # Layout images are explicitly bound by the editor.
        main=kind=='gallery' and i==0
        if main:image.update(shot_type='white_main',layout='white_main',product_presence='hero',headline='',subline='',big_number='',proof='')
        if kind=='aplus' and (image.get('shot_type')=='white_main' or image.get('layout')=='white_main'):
            raise ValueError('A+ 模块不能包含商品套图的白底主图')
        if image.get('layout') not in core._LAYOUT_FAMILIES:raise ValueError('策划返回未知版式，未保存')
        if image.get('shot_type') not in core._LAYOUT_DEFAULT_BY_TYPE:
            image['shot_type']={'white_main':'white_main','poster_hero':'hero_feature','detail_macro':'detail','human_context':'lifestyle','scenario_mosaic':'lifestyle','spec_grid':'specs','trust_close':'trust','in_box_flatlay':'in_box','split_compare':'comparison','result_showcase':'hero_feature'}[image['layout']]
        image.update(slot=str(i),text_on_image=not main and any(
            image.get(key) for key in ('headline','subline','eyebrow','big_number','callout','supporting_text','proof')
        ),size='1464x600' if kind=='aplus' else '1600x1600',product_source_url=refs[0],versions=[])
        if (apparel_gallery and count==7 and i==6) or (apparel_aplus and i==count-1):
            image.update(role='尺码图',shot_type='specs',layout='spec_grid',product_presence='supporting',
                         size_chart=True,text_on_image=True,headline='Size & Fit' if apparel_aplus else 'Size Guide',big_number='',proof='',
                         subline='',eyebrow='',callout='',supporting_text=size_chart_copy(chart) if chart else '')
        if image.get('product_presence')=='absent':
            image['product_source_url']=''
        elif not main:
            template=next((item for item in templates if item['index'] not in used_templates
                           and item['url'] not in refs
                           and (item['layout']==image['layout'] or item['shot_type']==image['shot_type'])),None)
            if template:
                image.update(template_url=template['url'],template_index=template['index'])
                used_templates.add(template['index'])
        image['photo_led_typography']=True
        if apparel_orchestration:image['apparelOrchestration']=apparel_orchestration
        if not main and not image.get('size_chart'):
            bound=official_records[(i-1 if kind=='gallery' else i)%len(official_records)]
            image['template_url']=bound['url']
            image['official_template']=bound
            image.pop('layout_blueprint',None)
        for key in ('headline','subline','evidence','buyer_question','scene','visual_concept','camera_direction'):
            image[key]=visual.bounded(image.get(key,''),2500 if key=='evidence' else 800)
        image['render_prompt']=visual.bounded(image.get('render_prompt',''),20000)
        composition=image['render_prompt'] or image['camera_direction'] or image['scene']
        if not composition:
            composition=core._compile_render_prompt(image,style,profile,native,kind)
        slots.append({'index':i,'question':image['buyer_question'],'evidence':image['evidence'],'composition':composition,'headline':image['headline'],'caption':image['subline'],'purpose':image.get('role','')})
    if apparel_gallery:
        check_apparel_gallery(images,forbid_filler=True,seven_policy=count==7)
    identity=str(native.get('product_lock') or '; '.join(map(str,profile['fidelity_anchors'])))
    plan={'identity':identity,'palette':style['palette_hex'],'lighting':style['lighting'],'typography':style['type_system'],'audience':str(profile.get('category_family','')),'warnings':profile.get('uncertainties',[]),'slots':slots}
    planner=visual.provider.settings_public()
    project={'id':uuid.uuid4().hex,'productId':product['id'],'references':refs,'brief':brief,'created':time.time(),'plan':plan,'uiPlan':native,'confirmed':False,'deliverable':kind,'language':native['language'],'creativeSkills':skill,'analysis':{'sourceAssessment':profile.get('source_assessment',{}),'identityModel':vision.rsplit('/',1)[-1],'storyboardModel':planner['model'],'referenceCount':len(refs),'paidRenderingStarted':False},'engine':{'name':'IvyeaOps source migration','version':4,'vision':vision,'planner':planner['provider'],'renderer':'official original artwork and prompt compiler v4'}}
    project['productionMode']=production_mode
    if apparel_gallery and count==7:project['galleryImagePolicy']='seven-shared-size-v1'
    if apparel_orchestration:
        project['apparelOrchestration']=apparel_orchestration
        project['engine']['version']=5
        project['engine']['renderer']='official artwork with explicit apparel orchestration v5'
    project['analysis']['layoutNote']=layout_note
    if use_asin_truth:
        project['analysis']['productTruthSource']=asin_truth
    else:
        project['analysis']['whiteProductTruth']=refs[0]
    project['analysis']['referenceViews']=reference_views
    source_origins=product_insights.source_images(product)
    project['analysis']['supplierReferences']=[
        ref for ref in refs if source_origins.get(ref) in ('供应商图','供应商采集图')
    ]
    project['analysis']['referenceHashes']={
        ref:hashlib.sha256(base64.b64decode(encoded.split(',',1)[1],validate=True)).hexdigest()
        for ref,encoded in zip(refs,reference_images)
    }
    project['analysis']['layoutTemplates']=templates
    project['analysis']['materialInsightVersion']=insights.get('version','')
    project['analysis']['productFactsFingerprint']=product_insights.fingerprint(product)
    project['analysis']['listingFingerprint']=product_insights.digest({k:listing.get(k,'') for k in ('title','bullets','description')})
    if apparel_gallery:
        project['galleryDirection']='apparel_v2_no_filler'
    if chart:
        project['sizeEvidence']=chart
    project['aiStoryboard']={'version':1,'origin':'workbench_ai_planner','model':project['analysis']['storyboardModel']}
    # Retain the planning inputs, including unresolved supplier facts, for QC.
    # Storyboard evidence is model output and must not become its own proof.
    project['productFacts']=json.loads(json.dumps(facts,ensure_ascii=False))
    return visual.save_project(project)
