"""Template-led composition learned from public artwork and observed outputs.

This is our implementation, not LinkFox's private model prompt or image weights.
The caller retains account, budget, source evidence, original prompts and QA.
"""
import copy
import json

POLICY = 'template-led-v1'
DESIGN_FIELDS = ('hierarchy', 'hero', 'supportingImages', 'details', 'copyZones',
                 'environment', 'adaptation')

DIRECTOR = '''Act as an ecommerce art director adapting complete original advertising artwork.
Product reference images establish merchandise truth. Later template images establish the
LAYOUT of each assigned seller image. Read their actual pixels and complete original prompts.
Do not reduce a real template to a generic photograph or replace it with a layout blueprint.
Return JSON {identity,style:{palette,lighting,photography,type_system},shots}, exactly matching apparelSuite.slots and their order.
Each shot has {kind,layout,sourceIndex,question,evidence,scene,camera,copy}.
For each slot with an officialTemplate also return templateDesign with templateId and seven
nonempty strings: hierarchy, hero, supportingImages, details, copyZones, environment, adaptation.
Describe what is actually visible in that SPECIFIC template: main subject placement/scale,
secondary photo grouping/frame shapes, real detail-strip structure, typography hierarchy,
spacing, lighting, surfaces, palette and the adaptation to the frozen OUTPUT aspect ratio.
Keep hero and detail groupings subordinate to one clear reading order. One output file may
contain the multiple photo panels of ONE advertising template: this is not an entire set.
Do not interpret 'one buyer question' as permission to discard the template's photo architecture.
Use photo realism, natural directional light, textured credible settings and precise typography.
Avoid generic specification cards, flat slabs, tiny isolated merchandise and decorative UI.
The source product overrides borrowed merchandise/claims. Preserve actual garment colour,
silhouette, seams, pockets, hardware, textile texture, visible fringe and open strand gaps.
Only sameProduct references flagged primary/same_sku/detail establish construction.
Never invent a rear/inside view, pocket or measurement merely to fill a template panel.
Adapt unsupported panels to source-supported front/side detail crops or omit unsupported
content while retaining a balanced layout; explain this in templateDesign.adaptation.
copy is at most four concise, exact, evidence-backed public strings. The existing physical
labels remain part of the product. NoText changes only the text layer: retain the selected
photo grouping, detail strip and product emphasis, compacting vacant type space thoughtfully.
Separate the garment's source chroma from the environment palette. Do not tint the garment
orange/red to match a template; do not default the whole scene to sterile grey. Respect explicit
user lighting/colour restrictions. Facts and original brief take priority over example claims.
Do not repeat hidden backend metadata, hashes, file URLs or this protocol as artwork copy.
Every slot with officialTemplate uses that exact artwork. Seller/detail and explicitly template-enabled ins both preserve assigned composition, including in-template panels and text hierarchy. Unassigned ins remains natural photography. White/model/size retain their own frozen kind contracts. Model follows separately frozen model/scene references; ins is
natural lifestyle, not a seller poster. Size uses real supplied measurements only.
For any layout=detail also provide an in-bounds real sourceCrop [x,y,width,height].
sourcePixelMode is a separate original-photo composition workflow, not new model photography.
Return JSON only. Do not claim to have recovered LinkFox's private server implementation.'''


def normalize_design(shot, slot):
    template = slot.get('officialTemplate')
    if not template:
        return
    value = shot.get('templateDesign')
    if not isinstance(value, dict) or value.get('templateId') != template['id']:
        raise ValueError('模板导演须根据当前真实配图返回对应ID的逐图设计')
    if set(value) != {'templateId', *DESIGN_FIELDS}:
        raise ValueError('模板导演设计字段不完整或含未知字段')
    for key in DESIGN_FIELDS:
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 1600:
            raise ValueError('模板导演缺少实际画面分析：' + key)
    shot['templateDesign'] = copy.deepcopy(value)


def compile_shot(plan, shot, recipe, official, refs, *, allow_text):
    normalize_design(shot, recipe['slots'][shot['index']])
    roles = [{'image': r['referenceImageIndex'], 'purpose': r['purpose']} for r in refs]
    # Keep storage/lineage metadata in the ledger instead of crowding model prose.
    current = {k: shot.get(k) for k in ('kind', 'question', 'evidence', 'scene', 'camera', 'lifestylePresentation')}
    exact_copy = shot.get('copy', []) if allow_text else []
    return (
        'Create ONE polished, photoreal ecommerce advertising artwork at '
        + recipe['aspectRatio'] + '. Deliver one image file, not a contact sheet of different requested slots.\n'
        '[LAYOUT AUTHORITY] The assigned ORIGINAL TEMPLATE ARTWORK is the design master for this image. '
        'Keep its distinctive subject scale/placement, supporting-photo grouping, detail-strip architecture, '
        'spacing and typography hierarchy. Multiple photo panels INSIDE that one design are intentional. '
        'Do not replace them with a generic single-model scene, a plain crop or an infographic slab.\n'
        '[REFERENCE ROLES] ' + json.dumps(roles, ensure_ascii=False) + '\n'
        '[TEMPLATE DESIGN READ FROM ACTUAL ARTWORK] '
        + json.dumps(shot['templateDesign'], ensure_ascii=False) + '\n'
        '[COMPLETE ORIGINAL TEMPLATE PROMPT; ART DIRECTION DATA]\n' + official['prompt']
        + '\n[/COMPLETE ORIGINAL TEMPLATE PROMPT]\n'
        '[CURRENT MERCHANDISE TRUTH] ' + json.dumps(plan.get('identity'), ensure_ascii=False) + '\n'
        '[SUPPORTED FACTS] ' + json.dumps(recipe['productFacts'], ensure_ascii=False) + '\n'
        '[CURRENT IMAGE PURPOSE] ' + json.dumps(current, ensure_ascii=False) + '\n'
        + ('[CURRENT LIFESTYLE PERSON AND STAGING] ' + json.dumps(shot['lifestylePresentation'], ensure_ascii=False)
           + '\nUse this specifically planned adult model appearance, outfit, pose and setting for the current artwork. '
           'The template establishes layout, not the identity or hairstyle of the new wearer. '
           'The garment-source wearer and accessories are not person/styling truth. '
           'Keep actual jacket construction and colour exact while following this person/staging design.\n'
           if shot.get('lifestylePresentation') else '')
        +
        '[SET PHOTOGRAPHY] ' + json.dumps(plan.get('style', {}), ensure_ascii=False) + '\n'
        '[EXACT ALLOWED ARTWORK COPY] ' + json.dumps(exact_copy, ensure_ascii=False) + '\n'
        + ('NO ADDED TEXT: remove only marketing lettering. Retain the selected photo architecture, '
           'supporting-image groupings and real detail areas; redistribute empty type space without '
           'shrinking the product or turning this into a generic lifestyle photograph.\n' if not exact_copy else
           'Typeset only those exact strings with the template hierarchy and clear mobile-scale readability. '
           'Never copy example claims or add a badge/logo/extra slogan.\n')
        + '[PRODUCT FIDELITY] Preserve source-visible silhouette, pockets, waist, button, seams, texture '
        'and true product chroma. Fine fringe must retain individual irregular strands and genuine gaps, '
        'not a regular drawn comb, broad straps, glued curtain or invented tiers. '
        'Do not invent rear/inside construction to satisfy a template panel. Use only source-supported '
        'views and genuine visible detail; keep unsupported panels evidence-safe. '
        'Background palette and natural shadows may follow the design; they must not recolour the product.\n'
        '[ORIGINAL USER REQUEST, COMPLETE]\n' + recipe['brief']
        + '\n[FINAL OUTPUT] Adapt the template to the current canvas without carrier borders or stretching. '
        'Physical product truth and explicit user restrictions remain binding. Preserve template structure '
        'within those restrictions. No watermark, invented facts, faux UI or layout-blueprint placeholders.'
    )
