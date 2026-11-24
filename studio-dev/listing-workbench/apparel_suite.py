"""Independent Codex apparel orchestration from observed public type-69 behavior.

The original LinkFox server planner/final prompts remain unknown. This module
freezes an explicit candidate contract; it neither submits models nor binds SKUs.
"""
import copy
import hashlib
import json
import math

VERSION = 'codex-apparel-rebuild-v1'
KINDS = ('white', 'model', 'ins', 'seller', 'size')
ROLES = ('primary', 'same_sku', 'detail', 'colour_reference', 'unverified')
LAYOUTS = {'white': ('main',), 'model': ('scene',), 'ins': ('scene',),
           'seller': ('feature', 'detail'), 'size': ('feature',)}
QUESTIONS = {'white': '完整商品轮廓与真实颜色', 'model': '同款商品的穿着比例和结构',
             'ins': '有依据的真实使用场景与穿搭', 'seller': '可见结构如何回答买家问题',
             'size': '真实尺码数据和测量口径'}


def _text(value, label, limit=6000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(label + '格式无效')
    return value


def _sha(value, label):
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in '0123456789abcdef' for c in value)):
        raise ValueError(label + '缺少真实SHA256')
    return value


def _asset(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + '须绑定已冻结原图')
    return {'url': _text(value.get('url'), label + '地址', 4000),
            'sha256': _sha(value.get('sha256'), label)}


def _template(value):
    result = copy.deepcopy(value)
    if not isinstance(result, dict):
        raise ValueError('服装图位缺少完整官方模板绑定')
    _text(result.get('id'), '官方模板ID', 100)
    _asset(result, '官方模板配图')
    prompt = _text(result.get('prompt'), '官方完整原提示词', 100000)
    if hashlib.sha256(prompt.encode('utf-8')).hexdigest() != result.get('promptSha256'):
        raise ValueError('官方原提示词与模板ID的哈希不一致')
    return result


def _facts(config, references):
    value = config.get('productFacts', {})
    if not isinstance(value, dict):
        raise ValueError('商品事实须将已核实资料、可见观察和AI推断分开')
    result = {'verified': [], 'visible': [], 'inferences': []}
    for kind in result:
        rows = value.get(kind, [])
        if not isinstance(rows, list) or len(rows) > 80:
            raise ValueError('商品事实条目格式无效')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('商品事实缺少来源记录')
            item = {'statement': _text(row.get('statement'), '商品事实描述', 2000)}
            if kind == 'visible':
                idx = row.get('sourceIndex')
                if (type(idx) is not int or not 0 <= idx < len(references)
                        or not references[idx]['sameProduct']):
                    raise ValueError('可见结构事实必须指向当前同款真值图')
                item['sourceIndex'] = idx
            else:
                key = 'source' if kind == 'verified' else 'basis'
                item[key] = _text(row.get(key), '事实来源或推断依据', 2000)
            result[kind].append(item)
    return result


def freeze_request(config, references, *, reference_sha256, templates, count,
                   no_text=True, brief=''):
    """Freeze before task signature/paid planning. Inputs must be server-resolved.

    template bindings come from official_image_templates.assignments/bind, never
    client-provided unchecked JSON. Formal listing continues its existing gate.
    """
    if not isinstance(config, dict):
        raise ValueError('服装套图配置无效')
    art_direction = config.get('artDirection', 'legacy-v1')
    if art_direction not in ('legacy-v1', 'template-led-v1'):
        raise ValueError('服装画面编排策略无效')
    if art_direction == 'template-led-v1' and config.get('sourcePixelMode'):
        raise ValueError('模板导演用于重新摄影生成；原片锁定须使用原片合成编排')
    if config.get('deliverable', 'creative') != 'creative':
        raise ValueError('正式七图必须沿原七图流程及真实尺码第7图校验，候选入口不能放行')
    if type(count) is not int or not 1 <= count <= 8:
        raise ValueError('服装候选套图张数须为1–8')
    if (not isinstance(references, list) or not references
            or len(reference_sha256) != len(references)):
        raise ValueError('服装原图与哈希数量不一致')
    roles = config.get('referenceRoles')
    if roles is None:
        roles = [{'role': 'primary', 'sameProduct': True}] + [
            {'role': 'unverified', 'sameProduct': False} for _ in references[1:]]
    if not isinstance(roles, list) or len(roles) != len(references):
        raise ValueError('每张服装原图必须有有序参考用途')
    frozen_refs = []
    for index, (url, sha, meta) in enumerate(zip(references, reference_sha256, roles)):
        if not isinstance(meta, dict) or meta.get('role') not in ROLES:
            raise ValueError('服装参考图用途无效')
        same = meta.get('sameProduct') is True
        if meta['role'] in ('primary', 'same_sku', 'detail') and not same:
            raise ValueError('主图/同款/细节真值必须有明确同款依据')
        frozen_refs.append({**_asset({'url': url, 'sha256': sha}, '服装原图'),
                            'sourceIndex': index, 'role': meta['role'], 'sameProduct': same})
    primary = [r for r in frozen_refs if r['role'] == 'primary']
    if len(primary) != 1:
        raise ValueError('服装套图必须且只能指定一张主真值图')
    counts = config.get('counts')
    if counts is None:
        # Independent same-product default, not a claim about LinkFox's 12-image default.
        photo_kind='ins' if config.get('templatePolicy')=='point-only-v1'else'model'
        counts = {'white': 1, photo_kind: min(1, count - 1), 'seller': max(0, count - 2)}
    if (not isinstance(counts, dict) or any(k not in KINDS for k in counts)
            or any(type(n) is not int or not 0 <= n <= 8 for n in counts.values())
            or sum(counts.values()) != count):
        raise ValueError('服装图种数量须准确覆盖本次张数')
    counts = {kind: counts.get(kind, 0) for kind in KINDS}
    width, height = config.get('targetWidth', 1536), config.get('targetHeight', 2048)
    if any(type(n) is not int or not 600 <= n <= 4096 for n in (width, height)):
        raise ValueError('服装输出宽高须为600–4096整数')
    common = math.gcd(width, height)
    ratio = f'{width // common}:{height // common}'
    if config.get('aspectRatio', ratio) != ratio:
        raise ValueError('服装输出比例与冻结尺寸不一致')
    if max(width / height, height / width) > 3:
        raise ValueError('服装输出比例不能超过3:1')
    facts = _facts(config, frozen_refs)
    chart = None
    if counts['size']:
        if no_text:
            raise ValueError('尺码图需真实文字数值，不能同时开启无文字模式')
        chart = config.get('sizeChart')
        if not isinstance(chart, dict):
            raise ValueError('尺码图缺少有来源的真实数据，不用模型补造')
        _text(chart.get('source'), '尺码资料来源', 3000)
        _text(chart.get('units'), '尺码单位', 100)
        _text(chart.get('measurementMethod'), '尺码测量口径', 2000)
        if not isinstance(chart.get('rows'), list) or not chart['rows']:
            raise ValueError('尺码图缺少原始数值行')
        for row in chart['rows']:
            if not isinstance(row, dict) or not row.get('size') or len(row) < 2:
                raise ValueError('尺码数据行无效')
        chart = copy.deepcopy(chart)
    consistency = {}
    if counts['model']:
        value = config.get('consistency', {})
        if not isinstance(value, dict):
            raise ValueError('模特与场景一致性配置无效')
        consistency = {'sameModelAcrossModelShots': True,
                       'exactScene': value.get('exactScene') is True,
                       'instructions': value.get('instructions', '')}
        if consistency['instructions']:
            _text(consistency['instructions'], '模特场景要求', 6000)
        for key in ('modelReference', 'sceneReference', 'sceneMask'):
            if value.get(key) is not None:
                consistency[key] = _asset(value[key], key)
        if consistency['exactScene'] and not consistency.get('sceneReference'):
            raise ValueError('遵循指定场景需要真实场景参考图')
        if consistency.get('sceneMask') and not consistency.get('sceneReference'):
            raise ValueError('场景蒙版必须绑定对应场景图')
        if counts['model'] > 1 and not consistency.get('modelReference'):
            raise ValueError('多张同模特图须先绑定同一真实模特参考，不能只靠文字声称一致')
    templates = [_template(t) for t in templates]
    policy=config.get('templatePolicy')
    if policy not in (None,'point-only-v1'):raise ValueError('服装模板分配策略无效')
    point_only=policy=='point-only-v1'
    selected=config.get('pointTemplateIds')
    if selected is not None:
        if (not point_only or not isinstance(selected,list) or len(selected)>8
                or len(set(selected))!=len(selected) or any(not isinstance(i,str)for i in selected)):
            raise ValueError('卖点模板须为不重复的官方ID列表')
        if selected and len(selected)!=counts['seller']:
            raise ValueError('每个卖点模板生成一张，已选模板数须等于卖点图数量')
        by_id={t['id']:t for t in templates}
        if any(i not in by_id for i in selected):raise ValueError('卖点模板缺少服务端核验的原配图和原文')
        seller_templates=[by_id[i] for i in selected] if selected else templates[:counts['seller']] if point_only else templates
    if selected is None:seller_templates=templates[:counts['seller']] if point_only else templates
    lifestyle_templates=[]
    if config.get('useLifestyleTemplates') is True and counts['ins']:
        if not point_only:raise ValueError('种草模板须使用按图种的独立模板分配')
        ids=config.get('lifestyleTemplateIds') or []
        if not isinstance(ids,list) or len(set(ids))!=len(ids) or any(not isinstance(i,str) for i in ids) or (ids and len(ids)!=counts['ins']):
            raise ValueError('种草图每张须绑定不同的官方模板，数量与图种一致')
        by_id={t['id']:t for t in templates}
        lifestyle_templates=[by_id[i] for i in ids] if ids and all(i in by_id for i in ids) else templates[counts['seller']:counts['seller']+counts['ins']] if not ids else []
        if len(lifestyle_templates)!=counts['ins'] or len({t['id'] for t in lifestyle_templates})!=counts['ins']:
            raise ValueError('种草图缺少已核验、互不重复的原配图和原文')
    if (counts['seller'] if point_only else count-counts['white']) and not templates:
        raise ValueError('服装套图需要完整官方配图和原文，不回退蓝图')
    slots, template_index, lifestyle_index = [], 0, 0
    # Explicit order can put white/main first while preventing model/ins conflation.
    order = config.get('shotOrder') or [k for k in KINDS for _ in range(counts[k])]
    if (not isinstance(order, list) or len(order) != count
            or any(order.count(k) != counts[k] for k in KINDS)
            or any(k not in KINDS for k in order)):
        raise ValueError('服装图序与图种数量不一致')
    for index, kind in enumerate(order):
        template = None
        if (kind=='seller' if point_only else kind!='white'):
            template = seller_templates[template_index % len(seller_templates)]
            template_index += 1
        if point_only and kind=='ins' and lifestyle_templates:
            template=lifestyle_templates[lifestyle_index];lifestyle_index+=1
        slots.append({'index': index, 'kind': kind, 'allowedLayouts': list(LAYOUTS[kind]),
                      'question': QUESTIONS[kind], 'officialTemplate': copy.deepcopy(template)})
    result={'version': VERSION, 'implementation': 'independent-codex-reconstruction',
            'observedMechanism': 'public LinkFox apparel type69; private server prompts unknown',
            'executionProvider': 'Codex Tools', 'deliverable': 'creative_candidate',
            'publicationEligible': False, 'formalSizeChartGateBypassed': False,
            'brief': _text(brief, '原始用户要求'), 'noText': bool(no_text), 'count': count,
            'counts': counts, 'references': frozen_refs, 'primaryReferenceIndex': primary[0]['sourceIndex'],
            'targetWidth': width, 'targetHeight': height, 'aspectRatio': ratio,
            'sourcePixelMode': config.get('sourcePixelMode') is True,
            'productFacts': facts, 'sizeChart': chart, 'consistency': consistency, 'slots': slots,
            'fidelityPolicy': {'whiteBalance': 'D65 neutral daylight; match original product chroma',
                               'construction': 'source-visible fringe rows, irregular strand gaps, length, density and seams'}}
    if point_only:
        result.update(templatePolicy=policy,pointTemplateIds=list(selected or []),
            templateInvocation={'observedRoute':'LinkFox apparel type69 pointStyles',
                'boundKinds':['seller'],'oneSelectedTemplatePerImage':True,
                'codexAdaptation':'verified artwork and complete public prompt; private server payload unknown'})
    if lifestyle_templates:
        result.update(useLifestyleTemplates=True,lifestyleTemplateIds=[t['id'] for t in lifestyle_templates])
        result['templateInvocation']['boundKinds'].append('ins')
        result['lifestyleTemplateAdaptation']='Explicit user-requested extension; native LinkFox ins was observed without layoutImageUrl, private server prompts unknown'
    if art_direction != 'legacy-v1':
        result['artDirection'] = art_direction
    return result


DIRECTOR = '''You are planning an INDEPENDENT Codex apparel image set, reconstructed from
observed public workflows; the original private server prompts are unknown.
Follow the frozen apparelSuite slots EXACTLY, including kind and order. White=complete
white-background main; model=one consistent model and scene; ins=separate natural lifestyle
concept (do not promise the same model); seller=evidence-backed structure/benefit photograph;
size=only supplied original measurements. Never replace requested kinds with generic posters.
Return {identity,style,shots}. Each shot: {kind,layout,sourceIndex,question,evidence,scene,camera,copy}.
layout must match its frozen allowedLayouts; sourceIndex is ONLY a verified same-product
reference. Primary/source reference and original fine-construction details are physical truth.
Every detail shot MUST include sourceCrop [x,y,width,height], normalized to 0..1 in that
shot's ORIGINAL sourceIndex photo, with positive width/height and the whole rectangle in bounds.
Choose a real crop containing the exact visible feature as construction evidence.
By default every assigned template is an actual image-generation composition reference, including
textless details: preserve its distinctive grouping, photo placement and typography hierarchy
with authorised product copy. Do not collapse all selling-point slots into plain enlarged crops.
Only when sourcePixelMode is explicitly true does the application compose original pixels;
in that mode no new angle, missing construction or invented resolution can be demanded.
References flagged colour_reference/unverified cannot establish garment shape or construction.
Keep supplied verified facts and visible observations separate from AI inferences. Do not
promote guessed fabric composition, dimensions, fringe counts or functionality into copy.
Keep the exact user brief complete. Never discard a trailing [用户原始要求] section.
Use every assigned original template artwork and complete original prompt for visual hierarchy,
never its example product facts, warm grade, simplified fringe or substitute silhouettes.
Only slots with a non-null officialTemplate use advertising layouts. In point-only-v1 mode,
seller/point slots alone bind pointStyles. ins is a natural lifestyle photograph, not an ad
card, collage or headline poster; model follows its separately selected person/scene references.
White and verified size data have their own purposes. Do not transfer a seller template to
ins/model/white/size merely because it appears among the planning reference images.
Neutral D65 white balance preserves original garment chroma; avoid orange/amber/red casts.
Fringe is sparse individual irregular fibres with real negative gaps and visible stitching,
not perfect teeth, a solid curtain, glued strips, fake tiers or an invented hem. Retain ONLY
details supported by actual sources, with no invented unseen back/inside view.
One current image answers one question. Product must remain prominent; no small garment on
oversized gray cards. Use tight scene framing and useful large details. No mandatory product-free
slot. noText=true means copy=[], while existing physical labels stay part of the product.
Exact size charts remain subject to the separate formal seven-image listing gate. Return JSON only.'''


def planning_context(recipe):
    return {'apparelSuite': copy.deepcopy(recipe), 'count': recipe['count'],
            'brief': recipe['brief'], 'noText': recipe['noText'],
            'productReferenceCount': len(recipe['references'])}


def normalize_plan(plan, recipe):
    """Apply after generic normalize_shots; never fill missing or failed proposals."""
    if not isinstance(plan, dict) or not isinstance(plan.get('shots'), list):
        raise ValueError('服装策划未返回逐图方案')
    result = copy.deepcopy(plan)
    if len(result['shots']) != recipe['count']:
        raise ValueError('服装策划图数与冻结请求不一致')
    truth = {r['sourceIndex'] for r in recipe['references']
             if r['sameProduct'] and r['role'] in ('primary', 'same_sku', 'detail')}
    for shot, slot in zip(result['shots'], recipe['slots']):
        if shot.get('kind') != slot['kind'] or shot.get('layout') not in slot['allowedLayouts']:
            raise ValueError('服装策划图种或版式与冻结图位冲突')
        if type(shot.get('sourceIndex')) is not int or shot['sourceIndex'] not in truth:
            raise ValueError('服装分镜没有绑定已确认同款真值图')
        if recipe['references'][shot['sourceIndex']]['role'] == 'detail' and shot['layout'] != 'detail':
            raise ValueError('局部细节真值不能推造完整服装或新穿着角度')
        if shot['layout'] == 'detail':
            crop = shot.get('sourceCrop')
            if (not isinstance(crop, list) or len(crop) != 4
                    or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in crop)
                    or crop[2] <= 0 or crop[3] <= 0
                    or crop[0] + crop[2] > 1.000001 or crop[1] + crop[3] > 1.000001):
                raise ValueError('服装细节图必须指定当前原片内真实sourceCrop矩形')
        shot['index'] = slot['index']
        shot['apparelKind'] = slot['kind']
        shot['officialTemplate'] = copy.deepcopy(slot['officialTemplate'])
        if recipe.get('artDirection') == 'template-led-v1':
            from apparel_art_direction import normalize_design
            normalize_design(shot, slot)
        if recipe.get('sourcePixelMode') and slot['kind']=='white':
            shot['sourcePixelIntentOriginal']={k:copy.deepcopy(shot.get(k)) for k in ('scene','camera')}
            shot['scene']='纯白背景；按所选原片的实际展示方式保留完整可见服装。如原片为穿着照片，则保留原穿着者可见部分与搭配，不凭空拆成裸衣或补造被遮挡结构。'
            shot['camera']='保留原片拍摄姿态与比例，当前服装突出且完整；原片已裁断的穿着者边缘贴合画面边缘，不在背景内部悬浮截断。'
        if recipe['noText'] or slot['kind'] == 'white':
            shot['copy'] = []
        if recipe.get('templatePolicy')=='point-only-v1'and slot['kind']in('ins','model') and not slot['officialTemplate']:
            shot['copy']=[]
        if slot['kind'] == 'size' and not recipe['sizeChart']:
            raise ValueError('尺码图不能绕过原始尺码证据')
    result['apparelSuite'] = copy.deepcopy(recipe)
    return result


def formal_direction():
    """Append to the native formal planner/render prompt without changing schema.

    This policy cannot grant size-chart, publication, identity or review approval.
    The caller retains the original native.output contract and seven-image gate.
    """
    return '''[INDEPENDENT APPAREL ORCHESTRATION: codex-apparel-rebuild-v1]
This is an independent Codex reconstruction of observed public apparel workflows;
the private LinkFox server planner and final prompts remain unknown. Keep the current
formal native.output schema, all existing field names and the exact seven-image contract.
Do not emit the free image engine's {identity,style,shots} schema or add extra image slots.
Image 7 remains the real size chart using the existing verified same-product source,
units, measurement method and all intended sizes; absence of evidence blocks the formal
set. Never fabricate measurement values, replace image 7 with lifestyle art, or treat
this policy as an approval or a substitute for the existing formal size-chart checks.

Declare each current slot's intent within the existing formal fields: full white main,
consistent model/scene, separate lifestyle (ins), evidence-backed selling-point/detail,
or real size data. Consistent model slots share the same actual model reference and
explicit scene reference where provided. Lifestyle/ins can vary context and styling;
do not silently call it model consistency. Model/scene-only reference material must not
become garment structure truth or leak into unrelated selling-point/detail/size slots.

Use the existing ordered source_reference_indices, with only source-verified primary or
same_sku photos for garment truth. Bind each shot to its specific current same-product
source; do not replace every shot with the first photo, mix another colour/SKU into
construction truth, or infer an unseen back/inside angle from a small detail crop.
Separate verified supplier/measurement facts, visible image observations and unverified
AI inferences. Preserve full original user requirements, including a trailing
[用户原始要求] section. Guessed material composition, benefits or fringe tiers cannot
become product facts or public artwork copy. Check every claimed special design against
the actual source image; retain only supported silhouette, seams, hardware and fibres.

Use each assigned ORIGINAL official template artwork and its COMPLETE raw prompt,
preserving its immutable ID/image hash/prompt hash in provenance. It is composition and
type hierarchy reference only. Do not use simplified blueprint substitutes, copy its
example product/brand/measurements, or let its warm lighting and simplified illustration
override current product identity. Existing noText rules remain: no added marketing
words when disabled, but physical source labels and the required factual size chart
remain governed by their existing slot rules.

Neutral D65 daylight white balance must preserve the actual source garment chroma;
no amber/orange/red grading, golden-hour filters, warm spotlights or added saturation.
For source-visible fringe preserve irregular individual strand length, real gaps,
density, separated rows when actually visible, edge thickness and stitching. Never
merge it into a solid curtain/panel, a uniform comb or invented extra fringe tiers.
Keep the garment prominent, scene framing tight, construction details large and useful;
no gray slabs containing tiny photos and no typography-only cards to fill seven slots.
Where original-pixel detail crops are supported, use a real in-bounds crop of that slot's
source photo, not a generative substitute; do not stretch it or invent missing detail.
Render only the CURRENT formal image slot, preserving the other slots and old receipts.
Output dimensions and reference order follow the frozen current provider contract.
This policy records intent and constraints, never visual verification or human approval.
[/INDEPENDENT APPAREL ORCHESTRATION]'''


def render_references(recipe, shot, *, template=None, construction_anchor=None):
    """Return exact ordered model-input records; caller passes their URLs to provider.

    Store the returned map as shot.apparelReferenceRoles before compile_shot.
    Do not append unrelated references after freezing this actual index map.
    """
    index = shot.get('sourceIndex')
    if type(index) is not int or not 0 <= index < len(recipe['references']):
        raise ValueError('服装当前图位的真值来源无效')
    source = recipe['references'][index]
    if not source['sameProduct'] or source['role'] not in ('primary', 'same_sku', 'detail'):
        raise ValueError('服装当前图位不能使用未核实参考作为真值')
    records = [{**copy.deepcopy(source), 'purpose': 'exact current garment truth'}]
    frozen_template = recipe['slots'][shot['index']]['officialTemplate']
    template = template if template is not None else shot.get('officialTemplate')
    if ((template is None) != (frozen_template is None)
            or (template is not None and any(template.get(k) != frozen_template.get(k)
                for k in ('id', 'sha256', 'promptSha256')))):
        raise ValueError('实际模板配图与冻结服装图位不一致')
    if template:
        value = _template(template)
        records.append({**_asset(value, '官方模板'), 'purpose': 'original template artwork; composition only',
                        'templateId': value['id']})
    if construction_anchor:
        records.append({**_asset(construction_anchor, '原片结构细节'),
                        'purpose': 'real original-pixel construction crop; not a second panel'})
    if shot.get('apparelKind', shot.get('kind')) == 'model':
        for key, purpose in [('modelReference', 'selected consistent model identity only'),
                             ('sceneReference', 'selected scene/background reference only'),
                             ('sceneMask', 'scene mask, not product or garment texture')]:
            if recipe['consistency'].get(key):
                records.append({**recipe['consistency'][key], 'purpose': purpose})
    return [{'referenceImageIndex': i + 1, **row} for i, row in enumerate(records)]


def compile_shot(plan, shot, brief, *, no_text=False):
    recipe = plan['apparelSuite']
    if brief != recipe['brief']:
        raise ValueError('原始服装要求已改变，须创建新版本')
    slot = recipe['slots'][shot['index']]
    if shot.get('apparelKind') != slot['kind']:
        raise ValueError('当前服装图位类型已改变')
    refs = shot.get('apparelReferenceRoles')
    if not isinstance(refs, list) or not refs:
        raise ValueError('服装生图须先冻结实际模型参考顺序')
    expected = render_references(recipe, shot, construction_anchor=shot.get('constructionAnchor'))
    # Exact roles/index/hash prevent a model portrait becoming a garment truth image.
    if refs != expected:
        raise ValueError('模型参考顺序或角色与冻结服装图位不一致')
    official = slot.get('officialTemplate')
    if recipe.get('artDirection') == 'template-led-v1' and official:
        from apparel_art_direction import compile_shot as template_directed
        return template_directed(plan, shot, recipe, _template(official), refs,
            allow_text=not (no_text or recipe['noText'] or slot['kind'] == 'white'))
    raw = ''
    if official:
        official = _template(official)
        raw = ('\n[OFFICIAL ORIGINAL TEMPLATE id=' + official['id'] + ']\n' + official['prompt']
               + '\n[/OFFICIAL ORIGINAL TEMPLATE]\n')
    allow_text = not (no_text or recipe['noText'] or slot['kind'] == 'white')
    current = {k: v for k, v in shot.items() if k not in (
        'officialTemplate', 'apparelReferenceRoles', 'constructionAnchor', 'sourceLayers', 'blueprint', 'sceneDetails')}
    current['copy'] = shot.get('copy', []) if allow_text else []
    consistency = recipe['consistency'] if slot['kind'] == 'model' else {}
    kind_design=('\n[NATIVE KIND WITHOUT SELLER TEMPLATE] '+
        ('Natural lifestyle photography, no ad layout panels, detail-card matrix, infographic icons or added slogans. '
         'The adult wearer, pose, background and styling may differ while the exact garment construction remains true.'if slot['kind']=='ins'else
         'Follow only this kind and its separately frozen references/data. Do not borrow a selling-point template.')
        if recipe.get('templatePolicy')=='point-only-v1'and not official else '')
    return ('Create ONE finished apparel ecommerce photograph at ' + recipe['aspectRatio']
        + ' (' + str(recipe['targetWidth']) + ' x ' + str(recipe['targetHeight']) + ').\n'
        '[PRIORITY] Exact product pixels and verified facts > original user request > current shot '
        '> neutral set style > borrowed template composition. The template cannot override garment colour or structure.\n'
        '[CURRENT OUTPUT ONLY] Render this one ' + slot['kind'] + ' image, never the whole set or another slot.\n'
        '[ACTUAL ORDERED REFERENCE ROLES] ' + json.dumps(refs, ensure_ascii=False) + '\n'
        '[PRODUCT IDENTITY] ' + json.dumps(plan.get('identity'), ensure_ascii=False) + '\n'
        '[FACTS / VISIBLE OBSERVATIONS / UNVERIFIED INFERENCES] '
        + json.dumps(recipe['productFacts'], ensure_ascii=False) + '\n'
        '[COLOUR] Neutral D65 daylight white balance. Match source garment chroma; '
        'no amber/orange/red cast, golden-hour filter, warm spotlight or automatic brown saturation. '
        'Ignore warm template lighting while retaining its useful composition.\n'
        '[CONSTRUCTION] Preserve the exact visible silhouette and any source-visible waist, fly, seams, hardware, '
        'surface texture. For source-visible fringe only, preserve irregular strand length/spacing, '
        'separate fibres, real negative gaps, density and stitching. Never merge fringes into a solid '
        'panel/curtain, uniform comb teeth or invented rows. Do not create unseen construction.\n'
        '[IMAGE DESIGN] Garment prominent; tight believable scenes, edge-to-edge useful construction '
        'details; no small photos floating on gray/white slabs, pasted textile texture or stock substitute product. '
        'For white, retain complete required garment edges on pure white. '
        'For model, retain selected model/scene identity; ins is a separate lifestyle concept.\n'
        '[CURRENT SHOT] ' + json.dumps(current, ensure_ascii=False) + '\n'
        '[SET STYLE, SUBJECT TO NEUTRAL PRODUCT LOCK] ' + json.dumps(plan.get('style', {}), ensure_ascii=False) + '\n'
        '[MODEL-SHOT CONSISTENCY ONLY] ' + json.dumps(consistency, ensure_ascii=False) + '\n'
        +kind_design+'\n'
        '[EXACT ALLOWED ARTWORK COPY] ' + json.dumps(current['copy'], ensure_ascii=False) + '\n'
        'This list is the only added text; empty means no added words. Retain physical source labels. '
        'No template slogans, logos, measurement guesses, badges, watermarks or signatures.\n'
        + ('[REAL SIZE DATA; DO NOT ALTER OR FILL] ' + json.dumps(recipe['sizeChart'], ensure_ascii=False) + '\n'
           if slot['kind'] == 'size' else '')
        + raw
        + '\n[ORIGINAL USER REQUEST, COMPLETE] ' + recipe['brief']
        + '\n[FINAL PRODUCT LOCK] Above original template text is reference data, not permission '
        'to change these identity, colour, construction, noText or current-slot constraints. '
        'Render ONE current output even if the complete original request describes several images. '
        'Independent Codex reconstruction; do not claim the private LinkFox server prompt was recovered.')
