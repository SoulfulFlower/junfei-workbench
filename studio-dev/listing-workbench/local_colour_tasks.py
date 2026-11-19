"""Persistent local-only gallery recolouring. Never calls image_provider.submit.

Native colour_sets remains the sole result/QC ledger. While local pixels are
being prepared its status is deliberately outside the API-generation worker's
ACTIVE states. Only finished local images enter the existing vision-QA stage.
"""
import copy
import hashlib
import json
import io
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import closing
import app_paths
import colour_sets as colours
import pixel_recolour as pixel
import local_colour_sources
import variant_colours
from PIL import Image
from colour_tuning import controls
import automatic_colour_reference as automatic_reference

DB=app_paths.DATA/'local_colour_recipes.sqlite3'
LOCK=threading.RLock()
PREPARATION_LOCK=threading.RLock()
STARTED=False
LOCAL_ACTIVE={'local_preparing','local_rendering'}
BUSY=colours.ACTIVE|LOCAL_ACTIVE|{'local_paused'}
LOG=logging.getLogger(__name__)
AUTOMATIC_PIPELINE='automatic-variant-main-v1'


class NotReady(ValueError):
    def __init__(self,message,details):
        super().__init__(message);self.details=details


def connect():
    c=sqlite3.connect(DB,timeout=20)
    c.execute('CREATE TABLE IF NOT EXISTS recipes(product TEXT,master TEXT,color TEXT,reference TEXT,body TEXT,PRIMARY KEY(product,master,color,reference))');c.commit()
    c.execute('CREATE TABLE IF NOT EXISTS recipe_history(id TEXT PRIMARY KEY,product TEXT,master TEXT,color TEXT,reference TEXT,body TEXT,archived REAL)');c.commit()
    return c


def store_recipe(recipe,product,context,group,reference):
    with closing(connect()) as c,c:
        previous=c.execute('SELECT body FROM recipes WHERE product=? AND master=? AND color=? AND reference=?',(product['id'],context['id'],group['key'],reference)).fetchone()
        if previous and json.loads(previous[0])!=recipe:
            c.execute('INSERT INTO recipe_history VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,product['id'],context['id'],group['key'],reference,previous[0],time.time()))
        c.execute('INSERT OR REPLACE INTO recipes VALUES(?,?,?,?,?)',(product['id'],context['id'],group['key'],reference,json.dumps(recipe)))
    return recipe


def parameters(data):
    target=data.get('target');pixel.color(target)
    exposure=data.get('exposure',0);texture=data.get('texture',1)
    if type(exposure) not in (int,float) or not -15<=exposure<=15 or type(texture) not in (int,float) or not 0<=texture<=2:raise ValueError('本地曝光或纹理参数超出范围')
    pattern=data.get('pattern')
    if pattern is not None:
        if not isinstance(pattern,dict) or pattern.get('kind') not in ('dark','light') or type(pattern.get('threshold')) not in (int,float) or not 10<=pattern['threshold']<=90:raise ValueError('图案参数无效')
        pixel.color(pattern.get('color'));pattern={k:pattern[k] for k in ('kind','color','threshold')}
    return {'target':target,'exposure':exposure,'texture':texture,'pattern':pattern,**controls(data)}


def configure(data,product):
    if data.get('confirmed') is not True:raise ValueError('请对照同色实物参考图确认颜色后保存')
    group=colours.select_variant(product,data.get('colorKey'),data.get('reference'))
    context=local_colour_sources.context(product)
    recipe={**parameters(data),'productId':product['id'],'masterId':context['id'],'colorKey':group['key'],'reference':data['reference'],
            'source':'user_confirmed_local_colour','pipeline':AUTOMATIC_PIPELINE,'manualTuning':True,'updated':time.time()}
    return store_recipe(recipe,product,context,group,data['reference'])


def sample_reference(data,product):
    # A client cannot turn the sampler into a cross-account image downloader.
    colours.select_variant(product,data.get('colorKey'),data.get('reference'))
    from colour_reference import sample
    return sample(data['reference'],data.get('box'))


def _recipe(product,context,group,reference,previous):
    with closing(connect()) as c:row=c.execute('SELECT body FROM recipes WHERE product=? AND master=? AND color=? AND reference=?',(product['id'],context['id'],group['key'],reference)).fetchone()
    if row:return json.loads(row[0])
    # Previously QC-passed local receipts are real calibrations, not guessed
    # RGB values from the colour name. Never learn from a rejected trial.
    if previous and previous.get('reference')==reference:
        for item in previous['items']:
            receipt=item.get('localCorrection',{}).get('pixelRecipe') or {}
            if _passed(item) and receipt.get('recipe'):
                return {**parameters(receipt['recipe']),'source':'previous_passed_local_receipt','reference':reference}
    return None


def _current_automatic_recipe(recipe):
    return bool(recipe and recipe.get('pipeline')==AUTOMATIC_PIPELINE and
        (recipe.get('manualTuning') is True or
         (recipe.get('automaticReferenceVersion')==automatic_reference.VERSION and
          recipe.get('selectionVersion')==automatic_reference.garment_auto.VERSION)))


def _automatic_recipe(product,context,group,reference,previous=None):
    main=automatic_reference.main_reference(group,reference);reference=main['url']
    existing=_recipe(product,context,group,reference,previous)
    if _current_automatic_recipe(existing):
        return existing
    sampled=automatic_reference.identify(product,group,reference,pixel.ROOT/'garment-embeddings')
    recipe={**parameters({'target':sampled['target'],'removeCast':True}),**sampled,'pipeline':AUTOMATIC_PIPELINE,
        'productId':product['id'],'masterId':context['id'],'colorKey':group['key'],'updated':time.time()}
    return store_recipe(recipe,product,context,group,reference)


def prepare(data,product):
    with PREPARATION_LOCK:return _prepare(data,product)


def _prepare(data,product):
    """Auto-colour preview from the linked variant main; no native set/QC job."""
    group=colours.select_variant(product,data.get('colorKey'),data.get('reference'))
    main=automatic_reference.main_reference(group,data.get('reference'))
    if any(s.get('status') in BUSY or s.get('id') in colours.IN_FLIGHT for s in colours.list_sets(product['id'])['sets']):
        raise NotReady('当前产品正在制作或检查，请等待本批完成后再调整共用选区',{'imageGenerationSubmitted':False})
    context,sources,selections,plans=_plans(product,{**data,'reference':main['url']})
    issues=[issue for p in plans for issue in p['issues'] if not issue.startswith(('缺少母版第','请先对照参考图'))]
    if issues:raise NotReady('自动换色尚未就绪：'+'；'.join(issues),{'imageGenerationSubmitted':False})
    recipe=_automatic_recipe(product,context,group,main['url'],plans[0]['previous'])
    slot=data.get('slot',0)
    if type(slot) is not int or slot not in sources:raise ValueError('请选择当前母版图位')
    selection=pixel.ensure_automatic_selections(product,[slot],refresh_legacy=True)[0]
    return {'recipe':recipe,'reference':main['url'],'selection':selection,'source':sources[slot],
        'pipeline':AUTOMATIC_PIPELINE,'userPointsRequired':False,'imageGenerationSubmitted':False}


def _passed(item):
    if not (item.get('image') and item.get('status') in ('approved','awaiting_manual') and (item.get('qc') or {}).get('pass') is True and not (item.get('qc') or {}).get('issues')):
        return False
    # Only account-owned bytes can justify reusing a completed result. Never
    # fetch a remote URL while checking readiness or trust a stale QC label.
    try:
        raw=pixel.image_provider.local_image(item['image'])
        expected=(item.get('localCorrection') or {}).get('sha256') or item.get('imageSha256')
        if expected and hashlib.sha256(raw).hexdigest()!=expected:return False
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height>18_000_000:return False
            im.verify()
        with Image.open(io.BytesIO(raw)) as im:im.load()
        return True
    except (ValueError,OSError,TypeError,Image.DecompressionBombError):return False


def _plans(product,data=None):
    data=data or {};context=local_colour_sources.context(product)
    groups=variant_colours.catalog(product);master_key=variant_colours.resolve(groups,product.get('masterColor'))
    colours.require_master_colour(product,context['reference'])
    ledger=colours.list_sets(product['id'])
    if ledger.get('errors'):raise NotReady('换色台账有损坏记录，请先从备份核对，未创建新任务',{'ledgerErrors':ledger['errors'],'imageGenerationSubmitted':False})
    existing=ledger['sets'];rows={}
    for s in existing:
        if s.get('masterId')==context['id']:
            rows.setdefault(s.get('colorKey') or variant_colours.resolve(groups,s.get('color')),s)
    sources={i['slot']:pixel.source_row(i) for i in context['items']}
    selections={slot:pixel.latest(pixel.selection_key(product,row),product) for slot,row in sources.items()}
    plans=[]
    for key,group in groups.items():
        if key==master_key:continue
        if data.get('colorKey') and key!=data['colorKey']:continue
        previous=rows.get(key)
        reference=data.get('reference') if data.get('colorKey')==key else previous.get('reference') if previous else None
        primary=next((r['url'] for r in group['references'] if r.get('referenceType')=='amazon_variant_main'),None)
        reference=primary or reference or next((r['url'] for r in group['references']),None)
        complete=bool(previous and sorted(i['slot'] for i in previous['items'])==list(range(context['count'])) and all(_passed(i) for i in previous['items']))
        pending=[] if complete else [slot for slot in sources if not previous or not _passed(next((i for i in previous['items'] if i['slot']==slot),{}))]
        recipe=_recipe(product,context,group,reference,previous)
        issues=[]
        if not complete:
            if previous and sorted(i['slot'] for i in previous['items'])!=list(range(context['count'])):issues.append('旧任务图位不完整或已变化，请先核对母版套图')
            if not group['ready']:issues.extend(group['issues'] or ['颜色变体资料不完整'])
            if not variant_colours.has_reference(group,reference):issues.append('缺少该颜色的真实参考图')
            try:automatic_reference.main_reference(group,reference)
            except ValueError as error:issues.append(str(error))
            if previous and (previous['status'] in BUSY or previous['id'] in colours.IN_FLIGHT):issues.append('当前颜色已有任务执行中，请等待完成')
            if previous and any(i['status'] in ('submitting','submit_unknown','generating','queued') for i in previous['items']):issues.append('存在尚未核对的API任务，本地入口不会重提或覆盖')
        missing=[slot for slot in pending if not selections[slot]]
        stale_selection=any(selections[slot] and not selections[slot].get('preserveWholeImage') and
            (selections[slot].get('automaticSelection') or {}).get('version')!=automatic_reference.garment_auto.VERSION for slot in pending)
        plans.append({'colorKey':key,'color':group['color'],'reference':reference,'previous':previous,'complete':complete,'pendingSlots':pending,'missingSlots':missing,'recipe':recipe,
            'automaticPreparationRequired':not complete and (bool(missing) or stale_selection or not _current_automatic_recipe(recipe)),'issues':issues})
    if data.get('colorKey') and not plans:raise ValueError('请选择当前产品的目标颜色，不能对母版颜色重复换色')
    return context,sources,selections,plans


def readiness(data,product):
    context,sources,selections,plans=_plans(product,data)
    return {'mode':'local-pixel','pipeline':AUTOMATIC_PIPELINE,'masterId':context['id'],'galleryCount':context['count'],'savedSlots':[n for n,s in selections.items() if s],
            'missingSlots':[n for n,s in selections.items() if not s],
            'colors':[{k:v for k,v in p.items() if k!='previous'} for p in plans],'imageGenerationCharges':False,'visionQaMayUseQuota':True}


def _matches(item,row,selection,recipe):
    receipt=item.get('localCorrection',{}).get('pixelRecipe') or {}
    return bool(selection and receipt.get('renderer')==pixel.VERSION and receipt.get('sourceHash')==row['sourceHash'] and receipt.get('selectionRevision')==selection['revision'] and receipt.get('recipe')==parameters(recipe))


def start(data,product,all_colors=False):
    with PREPARATION_LOCK:return _start(data,product,all_colors)


def _start(data,product,all_colors=False):
    if data.get('confirmed') is not True:raise ValueError('请确认本地换色；AI质检仍可能消耗模型额度')
    if not all_colors and not data.get('colorKey'):raise ValueError('请选择目标颜色')
    # Readiness remains read-only. A requested one-click run may create its
    # missing automatic selections, but only after all other preflights pass.
    context,sources,selections,preflight=_plans(product,{} if all_colors else data)
    other_issues=[issue for plan in preflight for issue in plan['issues'] if not issue.startswith(('缺少母版第','请先对照参考图'))]
    if not other_issues:
        groups=variant_colours.catalog(product)
        for plan in preflight:
            if not plan['complete']:_automatic_recipe(product,context,groups[plan['colorKey']],plan['reference'],plan['previous'])
        pending={slot for plan in preflight if not plan['complete'] for slot in plan['pendingSlots']}
        if pending:pixel.ensure_automatic_selections(product,sorted(pending),refresh_legacy=True)
    with LOCK,colours.LOCK:
        context,sources,selections,plans=_plans(product,{} if all_colors else data)
        blocked=[{'color':p['color'],'missingSlots':p['missingSlots'],'issues':p['issues']} for p in plans if p['issues']]
        if blocked:raise NotReady('本地换色尚未就绪：'+'；'.join(p['color']+'：'+'；'.join(p['issues']) for p in blocked),{'colors':blocked,'imageGenerationSubmitted':False})
        staged=[];skipped=[]
        for plan in plans:
            if plan['complete']:
                skipped.append({'color':plan['color'],'reason':'已过检，原图保留'});continue
            previous=plan['previous']
            if previous and previous.get('model')=='local-pixel':
                unchanged=[i['slot'] for i in previous['items'] if i['slot'] in plan['pendingSlots'] and i['status']=='needs_revision' and _matches(i,sources[i['slot']],selections[i['slot']],plan['recipe'])]
                if unchanged:raise NotReady('第'+ '、'.join(str(n+1) for n in unchanged)+'张参数未变，请先调整选区/颜色或使用仅复核入口',{'unchangedFailedSlots':unchanged,'imageGenerationSubmitted':False})
            if previous:s=copy.deepcopy(previous)
            else:
                s={'id':uuid.uuid4().hex,'productId':product['id'],'masterId':context['id'],'masterColor':product.get('masterColor',''),'color':plan['color'],'colorKey':plan['colorKey'],'reference':plan['reference'],
                   'created':time.time(),'items':[dict(i,status='local_pending') for i in context['items']],'manual':False,'validated':False,
                   'masterReference':context['reference'],'storyboardProjectId':context['storyboardProjectId']}
            if s['reference']!=plan['reference']:
                s.setdefault('referenceHistory',[]).append({'reference':s['reference'],'check':s.get('referenceCheck'),'time':time.time(),'reason':'user_selected_local_reference'})
                s.update(reference=plan['reference'],validated=False)
            s.update(colorKey=plan['colorKey'],color=plan['color'],manual=False)
            present={i['slot'] for i in s['items']}
            s['items'].extend(dict(i,status='local_pending') for i in context['items'] if i['slot'] not in present)
            linked=next((r for r in variant_colours.catalog(product)[plan['colorKey']]['references'] if r['url']==plan['reference']),{})
            if linked.get('referenceType')=='amazon_variant_main':s.update(referenceEvidenceType='amazon_variant_main',referenceSourceAsin=linked.get('sourceAsin'),referenceSourceUrl=linked.get('sourceUrl'))
            if s.get('model') and s['model']!='local-pixel':s.setdefault('previousModels',[]).append({'model':s['model'],'time':time.time()})
            job=uuid.uuid4().hex
            for item in s['items']:
                if item['slot'] not in plan['pendingSlots']:continue
                old={k:v for k,v in item.items() if k!='history'}
                item.setdefault('history',[]).append(old)
                item.update(status='local_pending');item.pop('qc',None)
                item.pop('jobId',None);item.pop('error',None)
                # Bind each original/selection revision now, not when a worker
                # happens to run after someone has edited the masks.
                item['localInput']={'source':sources[item['slot']],'selectionRevision':selections[item['slot']]['revision']}
            s.update(model='local-pixel',status='local_preparing',localTask={'id':job,'recipe':parameters(plan['recipe']),'pendingSlots':plan['pendingSlots'],'created':time.time(),'imageApiSubmissionAllowed':False})
            s['localTask']['colourSource']={k:plan['recipe'].get(k) for k in ('source','reference','sourceSha256','referenceSourceAsin','automaticReferenceVersion','selectionVersion','pipeline','manualTuning')}
            s.pop('error',None);staged.append(s)
        # Commit the entire start-all reservation once. All preflights finish
        # before any set is modified or any renderer/model is called.
        with closing(colours.db()) as c,c:
            for s in staged:c.execute('INSERT OR REPLACE INTO sets VALUES(?,?,?,?)',(s['id'],s['productId'],json.dumps(s,ensure_ascii=False),time.time()))
    if staged:start_worker()
    return {'mode':'local-pixel','sets':staged,'skipped':skipped,'totalColors':len(plans)+1,'createdColors':len(staged),'imageGenerationSubmitted':False}


def work(s,product):
    try:
        _work(s,product)
    except Exception as error:
        fail_task(s,error)


def fail_task(s,error):
    """Keep the original image/history and stop this job without starving others."""
    with colours.LOCK:
        current=colours.get(s['id'])
        if (current.get('localTask') or {}).get('id')!=(s.get('localTask') or {}).get('id'):return
        if current.get('status') not in LOCAL_ACTIVE|{'local_paused'}:return
        current.update(status='needs_attention',error='本地换色失败：'+str(error))
        current.setdefault('localTask',{})['lastError']={'type':type(error).__name__,'message':str(error),'at':time.time()}
        for item in current.get('items',[]):
            if item.get('status') in ('local_pending','local_rendering'):
                item.update(status='local_failed',error=str(error))
        colours.save(current)
    LOG.warning('Local colour task %s stopped: %s',s['id'],type(error).__name__)


def _work(s,product):
    task=s['localTask'];identity=task['id']
    for slot in task['pendingSlots']:
        with colours.LOCK:
            current=colours.get(s['id'])
            if current.get('localTask',{}).get('id')!=identity or current['status'] not in LOCAL_ACTIVE:return
            item=next(i for i in current['items'] if i['slot']==slot)
            if item['status']=='local_ready':continue
            current['status']='local_rendering';item['status']='local_rendering';colours.save(current)
            source=item['localInput']['source'];revision=item['localInput']['selectionRevision']
        try:
            receipt=pixel.render({**source,'revision':revision,**task['recipe']},product)
            # No image submission, safety-refusal replay, or provider-model
            # choice occurs in this branch. Native QA consumes only the result.
            with colours.LOCK:
                current=colours.get(s['id'])
                if current.get('localTask',{}).get('id')!=identity:return
                item=next(i for i in current['items'] if i['slot']==slot)
                item.update(image=receipt['image'],sourceUpload=source['source'],status='local_ready',
                    localCorrection={'method':'local_gallery_recolour','sha256':receipt['sha256'],'pixelRecipe':receipt,'humanReviewed':False,'time':time.time()})
                item['sourceSha256']=hashlib.sha256(pixel.image_provider.local_image(source['source'])).hexdigest()
                colours.save(current)
                if current['status']=='local_paused':return
        except Exception as error:
            fail_task(s,error)
            return
    with colours.LOCK:
        current=colours.get(s['id'])
        if current.get('localTask',{}).get('id')!=identity or current['status'] not in LOCAL_ACTIVE:return
        for item in current['items']:
            if item['status']=='local_ready':item['status']='reviewing'
        current['localTask']['renderCompleted']=time.time();current['status']='reviewing';colours.save(current)


def run_pending():
    with closing(colours.db()) as c:rows=c.execute('SELECT id,body FROM sets').fetchall()
    for sid,body in rows:
        s=None
        try:
            s=json.loads(body)
            if s.get('model')!='local-pixel' or s.get('status') not in LOCAL_ACTIVE:continue
            with closing(sqlite3.connect((app_paths.DATA/'studio.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)) as c:
                row=c.execute('SELECT body FROM workspace WHERE id=1').fetchone()
            product=next((p for p in (json.loads(row[0]) if row else {}).get('products',[]) if p['id']==s['productId']),None)
            if not product:raise ValueError('原产品已不存在，本地任务已停止')
            work(s,product)
        except Exception as error:
            LOG.warning('Local colour queue row %s failed: %s',sid,type(error).__name__)
            if isinstance(s,dict):
                try:fail_task(s,error)
                except Exception:LOG.exception('Could not persist local colour failure for %s',sid)


def loop():
    while True:
        try:run_pending()
        except Exception:LOG.exception('Local colour queue could not be read')
        time.sleep(2)


def start_worker():
    global STARTED
    with LOCK:
        if STARTED:return
        STARTED=True;threading.Thread(target=loop,daemon=True).start()


def control(name,data,product):
    if data.get('confirmed') is not True:raise ValueError('请确认本地任务操作；继续后AI质检仍可能消耗额度')
    with colours.LOCK:
        s=colours.get(data.get('id'))
        if s.get('productId')!=product['id'] or s.get('model')!='local-pixel':raise ValueError('当前账号本地换色任务不存在')
        if name=='pause':
            if s['status']=='local_paused':return {'set':s,'imageGenerationSubmitted':False}
            if s['status'] not in LOCAL_ACTIVE:raise ValueError('只可暂停本地像素处理阶段；已进入AI质检的请求不能撤回')
            s['status']='local_paused';s['localTask']['pausedAt']=time.time()
        elif name=='resume':
            if s['status']!='local_paused':raise ValueError('仅可继续已暂停任务；失败任务请先修正原因')
            s['status']='local_preparing';s['localTask']['resumedAt']=time.time()
        else:raise ValueError('未知本地任务操作')
        colours.save(s)
    if name=='resume':start_worker()
    return {'set':s,'imageGenerationSubmitted':False}


def action(name,data,product):
    if name=='prepare':return prepare(data,product)
    if name=='readiness':return readiness(data,product)
    if name=='sample-reference':return sample_reference(data,product)
    if name=='configure':return configure(data,product)
    if name in ('pause','resume'):return control(name,data,product)
    if name in ('start','start-all'):return start(data,product,all_colors=name=='start-all')
    raise ValueError('未知本地换色操作')
