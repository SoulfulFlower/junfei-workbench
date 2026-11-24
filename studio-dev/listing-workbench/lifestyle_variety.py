"""User-requested template lifestyle diversity; never grants garment approval."""
import itertools,json,re,hashlib

POLICY='distinct-template-presentation-v1'
FIELDS=('settingFamily','modelAppearance','pose','framing','composition','styling')
DIRECTOR_RULE='''USER-REQUESTED LIFESTYLE TEMPLATE AND VARIETY CONTRACT, overriding generic unassigned-ins photography defaults:
Every ins slot HAS its assigned officialTemplate. Preserve that actual artwork's scene architecture, model grouping, visual hierarchy, text/nontext design and current-canvas adaptation. Return templateDesign exactly as for seller. This explicit template assignment authorizes that template's internal panels/copy. White and size slots remain separate. Product truth always overrides template merchandise, fabric, claims and unseen angles.
For each ins shot also return lifestylePresentation with SIX nonempty concise strings: settingFamily, modelAppearance, pose, framing, composition, styling. Plan the whole set before rendering: each image must have a visibly different setting family, different adult model appearance and different supporting outfit/styling. Vary pose AND framing/composition meaningfully; changing a background colour is insufficient. Do not output the same long-haired masked wearer, grey trousers, glass storefront or standard standing pose repeatedly. The source wearer/face, mask, hat, pants and accessories are NOT identity truth for lifestyle: references establish the GARMENT ONLY. Generate new adult models, visible unmasked faces, different hair styling and credible source-supported garment views. No uniform background across different selected templates; preserve original garment chroma despite template atmosphere. Avoid stereotypes or unsupported functional activities/claims. If one template has supporting model panels, keep that artwork internally coherent; model variety is assessed BETWEEN the separate requested images.
Different template IDs alone do not prove visible variety. Later independent comparison of the actual images must confirm the set's scene, adult model and presentation differences.'''

def choose_template_ids(library,count,requested=None,excluded=()):
    if type(count) is not int or not 1<=count<=8:raise ValueError('种草模板张数须为1–8')
    if requested:
        if (not isinstance(requested,list) or len(requested)!=count or len(set(requested))!=count
                or any(not isinstance(i,str) for i in requested)):
            raise ValueError('种草图每张选择不同原模板，数量必须一致')
        for identity in requested:library.get(identity)
        return list(requested)
    rows=library.entries();chosen=[]
    for style in ('C15','C17','C30','C6','C8','C29','C37','C39'):
        match=next((r['id'] for r in rows if r.get('style')==style and r['id'] not in excluded and r['id'] not in chosen),None)
        if match:chosen.append(match)
        if len(chosen)==count:return chosen
    raise ValueError('没有足够不同的已核验种草模板；不复制同一版式凑数')

def validate_plan(plan):
    shots=[s for s in plan['shots'] if s.get('apparelKind')=='ins']
    keys=set()
    for shot in shots:
        template=shot.get('officialTemplate')
        if not template or template['id'] in keys:raise ValueError('种草图缺少各自不同的原模板')
        keys.add(template['id'])
        value=shot.get('lifestylePresentation')
        if not isinstance(value,dict) or set(value)!=set(FIELDS) or any(not isinstance(value[k],str) or not value[k].strip() or len(value[k])>1200 for k in FIELDS):
            raise ValueError('种草策划须明确各自场景、模特、姿态、景别、构图和搭配')
    norm=lambda value:re.sub(r'[\W_]+','',value.casefold())
    for left,right in itertools.combinations(shots,2):
        a,b=left['lifestylePresentation'],right['lifestylePresentation']
        if any(norm(a[k])==norm(b[k]) for k in ('settingFamily','modelAppearance','styling')):
            raise ValueError('种草图场景、人物形象和搭配不能重复')
        if sum(norm(a[k])!=norm(b[k]) for k in ('pose','framing','composition'))<2:
            raise ValueError('种草图须在姿态、景别和构图中至少改变两项')
    return shots

def review_set(task,model):
    shots=validate_plan(task['plan']);indices=[s['index'] for s in shots]
    results={r['index']:r for r in task['results']};chosen=[results[i] for i in indices]
    if any(r.get('review',{}).get('blocking') or not r.get('review',{}).get('identityPreserved') for r in chosen):
        return {'policy':POLICY,'blocking':True,'issues':['单图未通过，不授予整组种草图通过'],'warnings':[],'reviewSkipped':'single-image-failure'}
    pairs=list(itertools.combinations(indices,2))
    value=model('''Independently compare the ACTUAL finished lifestyle/template artworks, not just plan labels or template IDs. Reference1 is original GARMENT truth, not a required wearer identity. Following references are separate final artworks in supplied order. Judge each main adult wearer across separate artworks (supporting panels inside one template are intentionally coherent). For EVERY pair, are the scene setting family, adult model appearance, and pose/framing/composition/styling presentation visibly different? Similar glass-window/storefront settings, the same masked long-haired model/outfit and repeated near-identical standing camera views are not distinct even when template names differ. Different backgrounds alone cannot excuse repeated model and staging. Respect the garment's same construction/colour; variety cannot be achieved by inventing merchandise. Source wearer identity need not be copied. Keep existing product-fidelity, edge and colour failures blocking. Return JSON {blocking:bool,issues:[str],warnings:[str],pairs:[{left:int,right:int,sceneDistinct:bool,modelDistinct:bool,presentationDistinct:bool,evidence:str}]}. Use actual slot indices from context; return exactly all required pairs. Be explicit when faces or settings do not show enough evidence; do not manufacture a pass.''',
        {'policy':POLICY,'brief':task['request']['brief'],'imageSlots':indices,'pairs':pairs,
         'planningIntent':[{'index':s['index'],'templateId':s['officialTemplate']['id'],'presentation':s['lifestylePresentation']} for s in shots]},
        [task['request']['references'][0]]+[r['image'] for r in chosen],'independent_lifestyle_template_set_review')
    if not isinstance(value,dict) or type(value.get('blocking')) is not bool or not all(isinstance(value.get(k),list) and all(isinstance(x,str) for x in value[k]) for k in ('issues','warnings')):
        raise ValueError('种草整组检查没有明确结论，保留图片不自动通过')
    actual=value.get('pairs');seen=set()
    if not isinstance(actual,list):raise ValueError('种草整组检查缺少逐对实际比较')
    for row in actual:
        pair=(row.get('left'),row.get('right'));seen.add(pair)
        if pair not in pairs or any(type(row.get(k)) is not bool for k in ('sceneDistinct','modelDistinct','presentationDistinct')) or not isinstance(row.get('evidence'),str) or not row['evidence'].strip():
            raise ValueError('种草整组逐对检查格式不完整')
        if not all(row[k] for k in ('sceneDistinct','modelDistinct','presentationDistinct')):
            value['blocking']=True;value['issues'].append(f'种草图位{pair[0]+1}/{pair[1]+1}实际展示重复或证据不足：'+row['evidence'])
    if seen!=set(pairs) or len(actual)!=len(pairs):raise ValueError('种草整组检查漏了图对，不能放行')
    if value['issues']:value['blocking']=True
    value.update(policy=POLICY,actualImages=[{'index':r['index'],'image':r['image'],'providerJobId':r.get('providerJobId')} for r in chosen],automaticSetRegenerationPerformed=False,humanReviewed=False)
    return value

def prepare_recovery(recipe,parent,product_id,asset,poll):
    """One remaining per-slot correction for the proven missing-person wire bug.

    This cannot recover unknown submits, change intent, repeat a corrected slot,
    re-plan, or recursively retry an already fixed prompt policy.
    """
    old=parent.get('request',{})
    if (parent.get('productId')!=product_id or parent.get('status')!='needs_revision'
            or parent.get('pending') or old.get('lifestyleVarietyPolicy')!=POLICY
            or old.get('lifestylePromptPolicy') or parent.get('lifestyleSetReview',{}).get('blocking') is not True):
        raise ValueError('只可接续已完成且整组检查失败的旧版人物字段漏传任务')
    fields=('mode','brief','count','noText','referenceSha256','preserveSourcePixels','fidelityPolicy','templateExecutionPolicy')
    if any(recipe.get(k)!=old.get(k) for k in fields):raise ValueError('种草接续输入已变化')
    def identity(value):
        if isinstance(value,list):return [identity(v) for v in value]
        if isinstance(value,dict):return {k:identity(v) for k,v in value.items() if k!='url'}
        return value
    if any(identity(recipe.get(k))!=identity(old.get(k)) for k in ('apparelSuite','officialTemplates')):
        raise ValueError('种草接续模板、真值用途或事实已经变化')
    plan=parent.get('plan');shots=validate_plan(plan);rows=parent.get('results',[])
    if len(rows)!=recipe['count'] or sorted(r['index'] for r in rows)!=list(range(recipe['count'])):
        raise ValueError('原种草成图不完整')
    used={r['slot'] for r in parent.get('automaticCorrections',[])}
    pending=set()
    for pair in parent['lifestyleSetReview'].get('pairs',[]):
        if all(pair.get(k) is True for k in ('sceneDistinct','modelDistinct','presentationDistinct')):continue
        choices=[i for i in (pair.get('left'),pair.get('right')) if i not in used and i in {s['index'] for s in shots}]
        if not choices:raise ValueError('该图对已无剩余的一次自动纠正额度')
        if not pending.intersection(choices):pending.add(choices[0])
    if not pending:raise ValueError('原检查没有明确可纠正的重复图对')
    import copy
    outputs=copy.deepcopy(rows)
    for row in outputs:
        if row.get('review',{}).get('blocking') is not False or row.get('review',{}).get('identityPreserved') is not True:
            raise ValueError('原单图尚未通过，不能绕过纠正次数')
        snapshot=poll(row['providerJobId']);native=row.get('rawModelOutput') or row['raw']
        assets=[a.get('sourceAsset') or a for a in snapshot.get('assets',[])]
        if snapshot.get('status')!='completed' or native not in [a.get('url') for a in assets]+snapshot.get('images',[]) or asset(native)[1]!=row.get('rawSha256'):
            raise ValueError('原图片提供方结果或原生字节未核实')
        row['imageSha256']=asset(row['image'])[1]
        if row['index'] in pending:
            person=next(s['lifestylePresentation']['modelAppearance'] for s in shots if s['index']==row['index'])
            prompt=row.get('prompt','')
            if '[CURRENT LIFESTYLE PERSON AND STAGING]' in prompt or person in prompt:
                raise ValueError('原实际提示词不存在这项漏传缺陷，不重复生图')
    return {'parentTaskId':parent['id'],'plan':copy.deepcopy(plan),'results':outputs,
        'revisionSlots':sorted(pending),'attempts':copy.deepcopy(parent.get('attempts',[])),
        'automaticCorrections':copy.deepcopy(parent.get('automaticCorrections',[])),
        'originalSetReview':copy.deepcopy(parent['lifestyleSetReview']),
        'reason':'verified missing lifestylePresentation in actual render prompt',
        'planningRepeated':False,'maximumCorrectionsPerSlotAcrossLineage':1}
