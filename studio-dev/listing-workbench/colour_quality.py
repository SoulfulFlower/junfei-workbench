"""Practical ecommerce draft QA: cosmetic warnings do not trigger regeneration."""
POLICY='ecommerce-balanced-v1'
LABEL='常规电商质检：轻微瑕疵提醒，实质错误阻断'

INSTRUCTION='''Compare image1 locked master, image2 verified target colour guide and image3 current result.
Judge practical ecommerce usability at the image's normal customer viewing scale first. Additional labelled SOURCE/RESULT closeups are diagnostic evidence, not a reason to demand pixel-perfect retouching.
Blocking issues: wrong product/cut/construction; materially wrong target colour or pattern; substantial original-colour garment areas; obvious colour spill or damaged anatomy; loss of important knit/pattern structure that misrepresents the item; unreadable or factually incorrect size data, claims, labels, or required artwork text; conspicuous broken edges or compositing artifacts visible at normal viewing scale.
Warnings only: a small hair-edge colour cast, minor antialias fringe, tiny gap outline, slightly uneven shading, or modest texture softness that does not change product identity/material and does not distract at normal viewing scale. Do not reject an image just because a magnified comparison reveals such cosmetic imperfections. Existing negative space or gaps in the master are not new cutouts.
Do not infer hidden fit, fabric composition, accessories or measurements. Missing evidence for a critical product fact must remain a blocking/manual-check issue. A cosmetic uncertainty can be a warning.
If localPixelEvidence.contentOnlyInformationCard is true, the saved AI storyboard deliberately specifies no product photograph for this slot. Do not require a garment, target colour or construction comparison in that information card. Check its text against plannedCopy and supplierVerifiedFacts; supplier-stated composition need not be visually inferred from the garment photo. unchangedPixels is an exact source/result pixel comparison, not a model judgement. Still fail changed or unsupported claims and unreadable text.
Return one JSON object: {"decision":"pass|warn|fail","blockingIssues":["concrete material failures only"],"warnings":["acceptable cosmetic imperfections"],"observedColor":"short description"}.
A warning permits a review-draft handoff. It does not grant human approval or permission to publish.'''

def normalise(value):
    if not isinstance(value,dict):raise ValueError('换色审核输出格式错误')
    # Retain compatibility with older vision endpoints without silently
    # reclassifying their rejected results as cosmetic warnings.
    if 'decision' not in value:
        if type(value.get('pass')) is not bool or not isinstance(value.get('issues'),list) or any(not isinstance(s,str) for s in value['issues']):raise ValueError('换色审核输出格式错误')
        return {**value,'policy':POLICY,'decision':'pass' if value['pass'] and not value['issues'] else 'fail','warnings':[]}
    decision=value.get('decision');blocking=value.get('blockingIssues');warnings=value.get('warnings')
    if decision not in ('pass','warn','fail') or not isinstance(blocking,list) or not isinstance(warnings,list) or any(not isinstance(s,str) or not s.strip() for s in blocking+warnings):raise ValueError('换色审核分级格式错误')
    if decision=='fail' and not blocking:raise ValueError('不通过须说明实质问题')
    passed=decision!='fail' and not blocking
    return {**value,'pass':passed,'issues':blocking,'warnings':warnings,'decision':('warn' if warnings else 'pass') if passed else 'fail','policy':POLICY}
