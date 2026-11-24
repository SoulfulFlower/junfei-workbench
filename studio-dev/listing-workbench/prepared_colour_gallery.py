"""Stage source layouts/native repair candidates for real colour-gallery QA.

No image generation, approval or SKU binding occurs in this entry point.
The existing colour worker checks reference identity and every finished slot.
"""
import copy
import hashlib
import io
import json
import re
import time
import uuid
from contextlib import closing
from PIL import Image
import colour_sets as colours
import image_composition
import image_engine
import image_provider
import image_quality
import local_colour_sources
import visual_studio as visual


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _owned_image(url):
    if not isinstance(url,str) or not re.fullmatch(r'/uploads/[a-f0-9]{32}\.(?:png|jpg|webp)',url):
        raise ValueError('修复候选必须属于当前账号图片空间')
    return image_provider.local_image(url)


def adopt(data,product):
    if data.get('confirmed') is not True:raise ValueError('请确认候选接入正式图库检查')
    request_id=data.get('requestId')
    if not isinstance(request_id,str) or not re.fullmatch(r'[a-f0-9-]{20,64}',request_id):raise ValueError('缺少接入请求编号')
    context=local_colour_sources.context(product)
    if data.get('masterId')!=context['id']:raise ValueError('当前母版已变化')
    reference=data.get('reference');group=colours.select_variant(product,data.get('colorKey'),reference)
    if group['color']==product.get('masterColor'):raise ValueError('不能覆盖当前母版颜色')
    linked=next((r for r in group['references'] if r['url']==reference and r.get('referenceType')=='amazon_variant_main'),None)
    if not linked:raise ValueError('需要已采集本色子体主图依据')
    reference_raw,_=image_provider.remote_reference(reference)
    reference_sha=hashlib.sha256(reference_raw).hexdigest()
    artifacts=data.get('artifacts')
    if (not isinstance(artifacts,list) or any(not isinstance(a,dict) or type(a.get('slot')) is not int for a in artifacts)
            or sorted(a['slot'] for a in artifacts)!=list(range(context['count']))):
        raise ValueError('候选必须完整覆盖每个图位且不能重复')
    project=visual.get_project(context['storyboardProjectId']);colours.require_master_colour(product,context['reference'])
    source_items={i['slot']:i for i in context['items']};items=[]
    for artifact in sorted(artifacts,key=lambda a:a['slot']):
        slot=artifact['slot'];proof=artifact.get('provenance') or {}
        if (proof.get('productId')!=product['id'] or proof.get('masterId')!=context['id'] or
                proof.get('referenceSha256')!=reference_sha or proof.get('humanReviewed') is not False):
            raise ValueError('候选来源与当前商品、母版或真实颜色依据不符')
        if proof.get('method')=='native_repair_lace_composite_on_exact_master_geometry':
            task=image_engine.get(proof.get('engineTaskId'))
            if task.get('productId')!=product['id'] or task.get('status') not in ('completed','needs_revision'):
                raise ValueError('原生修图任务仍在运行、状态不明或属于其他商品')
            results=task.get('results') or []
            if len(results)!=1 or results[0].get('aspectValid') is not True:raise ValueError('原生修图缺少正方形交付结果')
            result=results[0]
            if (result.get('providerJobId')!=proof.get('providerJobId') or result.get('image')!=proof.get('donorImage') or
                    hashlib.sha256(_owned_image(result['image'])).hexdigest()!=proof.get('donorSha256') or
                    reference_sha not in task.get('request',{}).get('referenceSha256',[]) or
                    proof.get('baseSource',{}).get('source')!=source_items[slot]['sourceUpload'] or
                    proof.get('outsideChangedPixels')!=0):raise ValueError('原生修图/原母版文件依据不一致')
        elif proof.get('method')!='actual_variant_source_layout':raise ValueError('不支持的正式候选来源')
        if hashlib.sha256(_owned_image(proof.get('referenceUpload'))).hexdigest()!=reference_sha:
            raise ValueError('原图排版未绑定本色真实参考文件')
        raw=_owned_image(artifact.get('image'));sha=hashlib.sha256(raw).hexdigest()
        if sha!=artifact.get('sha256'):raise ValueError('候选文件内容已变化')
        with Image.open(io.BytesIO(raw)) as image:
            if image.width<1600 or image.height<1600 or image.width!=image.height:raise ValueError('正式候选必须至少1600像素正方形')
        technical=image_quality.inspect(raw,main=slot==0,minimum=1600,full_bleed=slot>0,size_chart=bool(project['uiPlan']['images'][slot].get('size_chart')))
        composition=image_composition.for_project(raw,project,slot)
        if not technical['pass'] or not composition['pass']:raise ValueError('候选尚未通过真实技术/构图检查')
        item=copy.deepcopy(source_items[slot]);item.update(status='reviewing',image=artifact['image'],imageSha256=sha,
            localCorrection={'method':'prepared_native_source_or_repaired_artwork','sha256':sha,'humanReviewed':False,
                'time':time.time(),'provenance':copy.deepcopy(proof),'technical':technical,'composition':composition})
        items.append(item)
    if len({i['imageSha256'] for i in items})!=len(items):raise ValueError('不能用重复成图填满图库')
    signature=_digest({'productId':product['id'],'masterId':context['id'],'colorKey':group['key'],
                       'reference':reference,'artifacts':[{'slot':i['slot'],'sha256':i['imageSha256']} for i in items]})
    now=time.time();sid=uuid.uuid5(uuid.NAMESPACE_URL,'prepared-colour:'+product['id']+':'+request_id).hex
    candidate={'id':sid,'productId':product['id'],'masterId':context['id'],'masterColor':product.get('masterColor',''),
        'colorKey':group['key'],'color':group['color'],'reference':reference,'status':'validating','created':now,
        'model':'local-pixel','items':items,'manual':False,'validated':False,
        'storyboardProjectId':context['storyboardProjectId'],'referenceEvidenceType':'amazon_variant_main',
        'referenceSourceAsin':linked['sourceAsin'],'referenceSourceUrl':linked['sourceUrl'],
        'preparedGallery':{'requestId':request_id,'signature':signature,'referenceSha256':reference_sha,
                           'humanReviewed':False,'imageApiSubmissionAllowed':False},
        'localTask':{'id':uuid.uuid4().hex,'source':'prepared_native_artifacts','pendingSlots':list(range(context['count'])),
                     'created':now,'renderCompleted':now,'imageApiSubmissionAllowed':False}}
    # One reservation per original master/colour; repeating never resets QA.
    with colours.LOCK,closing(colours.db()) as c,c:
        c.execute('BEGIN IMMEDIATE')
        rows=c.execute('SELECT body FROM sets WHERE product_id=?',(product['id'],)).fetchall()
        for row in rows:
            existing=json.loads(row[0])
            if existing['id']==sid or (existing.get('masterId')==context['id'] and existing.get('colorKey')==group['key']):
                if (existing.get('preparedGallery') or {}).get('signature')==signature:return existing
                raise ValueError('本色已有原任务，请沿原图库修复，不能重复创建')
        c.execute('INSERT INTO sets VALUES(?,?,?,?)',(sid,product['id'],json.dumps(candidate,ensure_ascii=False),now))
    return candidate
