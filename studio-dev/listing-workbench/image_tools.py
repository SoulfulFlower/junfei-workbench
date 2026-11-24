"""Account-local durable selection and colour-verification preflight jobs."""
import json,hashlib,uuid,sqlite3,threading,time,io,re
from pathlib import Path
from contextlib import closing
import app_paths
DB=app_paths.DATA/'image_tools.sqlite3';LOCK=threading.RLock();ACTIVE=set()
TERMINAL={'completed','failed','interrupted'}

def processor_version(kind):
    if kind=='selection':
        import automatic_garment_selection as module
        import automatic_mask_revision as revision
        import garment_component_proposals as proposals
        import automatic_local_selection as local
        import sam2_local_backend as backend
        return module.VERSION+':'+getattr(module,'ALGORITHM_VERSION','initial')+':'+revision.VERSION+':'+proposals.VERSION+':'+local.VERSION+':'+backend.VERSION
    if kind=='reference_sample':
        import automatic_reference_sample as module
        return module.VERSION
    import automatic_image_quality as module
    return module.VERSION+':'+getattr(module,'STORAGE_VERSION','initial')

def known_quality_io_failure(row):
    if row.get('kind')!='colour_check'or row.get('status')!='failed'or unresolved(row):return False
    intents=row.get('modelIntents',[]);calls=row.get('modelCalls',[])
    if len(intents)!=1 or intents[0].get('status')!='completed'or len(calls)!=1:return False
    import automatic_image_quality
    if row.get('processorVersion','').split(':',1)[0]!=automatic_image_quality.VERSION:return False
    if not calls[0].get('rawModelText')or not calls[0].get('inputImageSha256'):return False
    match=re.search(r"No such file or directory: '([^']+)'",row.get('error',''))
    if not match:return False
    try:Path(match[1]).resolve().relative_to((app_paths.DATA/'automatic-image-quality').resolve())
    except ValueError:return False
    return True

def unresolved(row):
    return (row.get('status')=='interrupted' or row.get('failureReceipt',{}).get('state')=='unknown'
        or row.get('result',{}).get('status')=='unverified'
        or any(item.get('status') in ('pending','unknown') for item in row.get('modelIntents',[])))

def upgrade_allowed(row):
    # A known semantic/local selection rejection has full retained vision
    # records. A transport exception or interrupted task is never a retry grant.
    return (row.get('status')=='failed' and not unresolved(row)
        and ((row.get('kind') in ('selection','reference_sample')and row.get('failureReceipt',{}).get('state')=='rejected')or known_quality_io_failure(row))
        and row.get('processorVersion','legacy')!=processor_version(row['kind']))

def retry_known_failure(task_id,product):
    old=get(task_id)
    if old['productId']!=product['id']:raise ValueError('原任务与当前商品不匹配')
    if not upgrade_allowed(old):raise ValueError('原任务没有已核实的本地/选区/取色失败或工具版本未更新，未重发模型')
    request=uuid.uuid5(uuid.NAMESPACE_URL,'junfei:image-tool:'+task_id+':'+processor_version(old['kind'])).hex
    return start({**old['inputs'],'kind':old['kind'],'requestId':request,'parentTaskId':task_id},product)
def db():
    c=sqlite3.connect(DB,timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, request_id TEXT UNIQUE, signature TEXT, body TEXT)');c.commit();return c
def save(row):
    row['updated']=time.time()
    with LOCK,closing(db())as c,c:c.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?,?)',(row['id'],row['requestId'],row['signature'],json.dumps(row,ensure_ascii=False)))
    return row
def get(task_id):
    with closing(db())as c:row=c.execute('SELECT body FROM tasks WHERE id=?',(task_id,)).fetchone()
    if not row:raise ValueError('当前账号没有该自动检查任务')
    return json.loads(row[0])
def asset_fields(data):
    return {k:v for k,v in data.items()if k in ('source','mask','renderedImage','protected','reference')and v is not None}
def start(data,product):
    import image_engine,image_tool_vision
    kind=data.get('kind');request=data.get('requestId')
    if kind not in ('selection','reference_sample','colour_check'):raise ValueError('自动检查类型无效')
    if not isinstance(request,str)or not 8<=len(request)<=100:raise ValueError('自动检查需要持久requestId')
    inputs={k:data[k]for k in ('source','mask','renderedImage','target','protected','reference','selectionTaskId','force','feedback','role')if k in data}
    if inputs.get('role','source_garment')not in ('source_garment','target_colour_reference'):raise ValueError('自动选区参考用途无效')
    hashes={k:image_engine.asset(v)[1]for k,v in asset_fields(inputs).items()}
    if 'source'not in hashes:raise ValueError('自动检查缺少原图')
    if kind=='colour_check'and not all(k in hashes for k in ('mask','renderedImage')):raise ValueError('换色检查缺少选区或成图')
    route=image_tool_vision.identity()
    signature=hashlib.sha256(json.dumps({'kind':kind,'productId':product['id'],'inputs':inputs,'hashes':hashes},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with LOCK,closing(db())as c:
        prior=c.execute('SELECT signature,body FROM tasks WHERE request_id=?',(request,)).fetchone()
        if prior:
            if prior[0]!=signature:raise ValueError('原自动检查意图发生变化，未重新调用模型')
            return json.loads(prior[1])
        for item, in c.execute('SELECT body FROM tasks'):
            earlier=json.loads(item)
            if earlier.get('kind')==kind and earlier.get('assetSha256',{}).get('source')==hashes['source'] and unresolved(earlier):
                raise ValueError('同一原图有未核对的模型调用，保留原任务 '+earlier['id']+'，未再次付费调用')
        if data.get('parentTaskId'):
            parent=get(data['parentTaskId'])
            if not upgrade_allowed(parent)or parent['inputs']!=inputs or parent['productId']!=product['id']:raise ValueError('不能以新版本改写原自动处理意图')
        row={'id':uuid.uuid4().hex,'requestId':request,'signature':signature,'productId':product['id'],'garmentKind':__import__('garment_auto').category(product),
            'productName':product.get('name',''),'kind':kind,'inputs':inputs,'assetSha256':hashes,'visionIdentity':route,'status':'queued','created':time.time(),'humanReviewed':False,
            'processorVersion':processor_version(kind),'parentTaskId':data.get('parentTaskId')}
        if data.get('parentTaskId'):row['garmentKind']=parent['garmentKind']
        save(row);ACTIVE.add(row['id'])
        threading.Thread(target=run,args=(row['id'],),daemon=True,name='image-tool-'+row['id'][:8]).start()
    return row
def selected_receipt(data,row):
    if not data.get('selectionTaskId'):return None
    task=get(data['selectionTaskId'])
    if task['kind']!='selection'or task['status']!='completed':raise ValueError('自动选区检查尚未完成')
    if (task['productId']!=row['productId']or task['garmentKind']!=row['garmentKind']or task['inputs'].get('role','source_garment')!='source_garment'):
        raise ValueError('自动选区回执的商品、服装部件或参考用途不匹配')
    if task['inputs']['source']!=data['source']or task['result']['mask']['url']!=data['mask']:raise ValueError('选区回执与当前原图、蒙版不匹配')
    return task['result']['receipt']

def correction_evidence(data,row):
    """Resolve correction authority from this account's stored tasks, never UI claims."""
    feedback=data.get('feedback')
    if not isinstance(feedback,dict)or not feedback.get('qualityCheckId'):
        return feedback,None,None
    import image_engine,automatic_image_quality
    qc=get(feedback['qualityCheckId'])
    previous_id=feedback.get('previousSelectionTask')
    if (qc.get('kind')!='colour_check'or qc.get('status')!='completed'
        or qc.get('productId')!=row['productId']or qc.get('garmentKind')!=row['garmentKind']
        or qc.get('processorVersion','').split(':',1)[0]not in {automatic_image_quality.VERSION,'automatic-colour-quality-v3-details','automatic-colour-quality-v4-grounded-details','automatic-colour-quality-v5-grounded-leak-details'}
        or qc.get('inputs',{}).get('source')!=data['source']
        or qc.get('assetSha256',{}).get('source')!=row['assetSha256']['source']
        or not previous_id or qc.get('inputs',{}).get('selectionTaskId')!=previous_id
        or data.get('role','source_garment')!='source_garment'):
        raise ValueError('自动修正必须引用当前商品、原图及原选区的真实成图检查')
    # Recheck original bytes; a replaced URL must never authorize an automatic merge.
    for key,url in asset_fields(qc['inputs']).items():
        if image_engine.asset(url)[1]!=qc['assetSha256'].get(key):
            raise ValueError('自动修正引用的成图检查文件已变化')
    selected_receipt({**qc['inputs'],'selectionTaskId':previous_id},row)
    previous=get(previous_id)
    if previous.get('assetSha256',{}).get('source')!=row['assetSha256']['source']:
        raise ValueError('原选区的原片哈希与本次修正不匹配')
    result=qc['result']
    if result.get('passed')is not False or result.get('blocking')is not True or result.get('nextAction')!='selection':
        raise ValueError('原成图检查没有明确要求修正选区')
    canonical={'issues':result.get('issues',[]),'locations':result.get('locations',[]),
        'previousSelectionTask':previous_id,'qualityCheckId':qc['id']}
    row['correctionEvidence']={'qualityCheckId':qc['id'],'previousSelectionTask':previous_id,
        'qualitySignature':qc['signature'],'assetSha256':dict(qc['assetSha256'])};save(row)
    return canonical,image_engine.asset(qc['inputs']['mask'])[0],result
def perform(row):
    import image_engine,image_tool_vision
    data=row['inputs'];images={k:image_engine.asset(v)[0]for k,v in asset_fields(data).items()}
    def vision(instruction,context,pictures):
        if image_tool_vision.identity()!=row['visionIdentity']:raise ValueError('自动检查的账号模型配置已变化，未切换到其他路线')
        row['phase']=context.get('phase')or('selection'if row['kind']=='selection'else'colour_review');save(row)
        context_hash=hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if row.get('parentTaskId'):
            parent=get(row['parentTaskId'])
            if known_quality_io_failure(parent):
                receipt=parent['modelCalls'][0];hashes=[]
                for picture in pictures:
                    buffer=io.BytesIO();picture.save(buffer,'PNG');hashes.append(hashlib.sha256(buffer.getvalue()).hexdigest())
                digest=hashlib.sha256(instruction.encode()).hexdigest()
                if (hashes!=receipt['inputImageSha256']or digest!=receipt['instructionSha256']
                        or row['inputs']!=parent['inputs']or row['visionIdentity']!=parent['visionIdentity']
                        or row['garmentKind']!=parent['garmentKind']or row['productName']!=parent.get('productName')
                        or parent['modelIntents'][0].get('contextSha256',context_hash)!=context_hash):
                    raise ValueError('本地恢复的视觉输入或商品范围变化，未复用或重发模型')
                raw=receipt['rawModelText'].strip()
                if raw.startswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0].strip()
                value=json.loads(raw)
                if not isinstance(value,dict):raise ValueError('原模型回执不是完整JSON对象，未重新调用')
                replay={**receipt,'reusedFromToolTaskId':parent['id'],'reason':'known_local_artifact_path_failure'}
                row.setdefault('reusedModelCalls',[]).append(replay);save(row)
                return {'result':value,'receipt':replay}
        intent={'id':uuid.uuid4().hex,'status':'pending','instructionSha256':hashlib.sha256(instruction.encode()).hexdigest(),'created':time.time()}
        intent['contextSha256']=context_hash
        row.setdefault('modelIntents',[]).append(intent);save(row)
        try:result=image_tool_vision.call(instruction,context,pictures)
        except Exception as error:
            intent.update(status='unknown',error=str(error)[:2000]);save(row);raise
        intent.update(status='completed',receipt=result['receipt'],completed=time.time());save(row)
        row.setdefault('modelCalls',[]).append(result['receipt']);save(row)
        return result
    if row['kind']=='selection':
        import automatic_garment_selection as selection
        if row['garmentKind']=='auto':raise ValueError('自动服装选区需要已识别的商品品类')
        feedback,previous_mask,quality_feedback=correction_evidence(data,row)
        subject={'productName':row.get('productName',''),'target':row.get('productName',''),'role':data.get('role','source_garment')}
        import automatic_local_selection as local
        if quality_feedback is not None and not local.eligible(quality_feedback):
            raise selection.SelectionRejected('成图报告含未核实的非局部或泄漏问题，已停止；未回退重算整张选区',
                {'state':'rejected','accepted':False,'verified':False,'qualityCheckId':feedback['qualityCheckId'],
                 'reason':'outside_grounded_local_scope','globalFallbackSubmitted':False})
        if quality_feedback is not None:
            from sam2_local_backend import Sam2LocalBackend
            previous=get(feedback['previousSelectionTask']);qc_task=get(feedback['qualityCheckId'])
            mask,receipt=local.correct(images['source'],previous_mask,previous['result']['receipt'],
                kind=row['garmentKind'],subject=subject,qc=quality_feedback,
                actual_output=image_engine.asset(qc_task['inputs']['renderedImage'])[0],vision=vision,
                reference=image_engine.asset(qc_task['inputs']['reference'])[0] if qc_task['inputs'].get('reference') else None,
                cache_root=app_paths.DATA/'automatic-local-selection',garment_cache_root=app_paths.DATA/'automatic-garment-selection',
                vision_metadata=row['visionIdentity'],local_backend=Sam2LocalBackend(),explicit_protection=images.get('protected'))
        else:
            mask,receipt=selection.prepare(images['source'],row['garmentKind'],vision=vision,
                cache_root=app_paths.DATA/'automatic-garment-selection',protected=images.get('protected'),vision_metadata=row['visionIdentity'],initial_feedback=feedback,resume_local_error=True,
                subject=subject,max_attempts=3)
        if receipt.get('verified')is not True or receipt.get('accepted')is not True:raise ValueError('自动选区未完成独立验收')
        return {'mask':image_engine.cache(mask),'receipt':receipt,'sourceSha256':row['assetSha256']['source']}
    if row['kind']=='reference_sample':
        import automatic_reference_sample as sampling
        if row['garmentKind']=='auto':raise ValueError('目标衣料取色需要已识别的商品品类')
        sampled=sampling.sample(images['source'],row['garmentKind'],vision=vision,
            cache_root=app_paths.DATA/'automatic-reference-sample',vision_metadata=row['visionIdentity'],
            subject={'productName':row.get('productName',''),'target':row.get('productName',''),'role':'target_colour_reference'})
        receipt=sampled['receipt']
        if receipt.get('sampleVerified')is not True or receipt.get('accepted')is not True or receipt.get('eligibleAsSourceSelection')is not False:raise ValueError('目标参考衣料样本未通过独立复核')
        return {'target':sampled['target'],'sampleMask':image_engine.cache(sampled['mask']),'receipt':receipt}
    import automatic_image_quality as quality
    result=quality.check_colour(images['source'],images['mask'],images['renderedImage'],data.get('target'),vision=vision,
        cache_root=app_paths.DATA/'automatic-image-quality',selection_receipt=selected_receipt(data,row),reference=images.get('reference'),vision_identity=row['visionIdentity'],force=data.get('force')is True,
        subject={k:v for k,v in {'productName':row.get('productName','')[:200],'kind':row['garmentKind'],'role':'source_garment'}.items()if v})
    return result
def run(task_id):
    row=get(task_id)
    try:
        import image_engine
        for key,url in asset_fields(row['inputs']).items():
            if image_engine.asset(url)[1]!=row['assetSha256'][key]:raise ValueError('自动处理原图或选区哈希改变，未调用模型')
        row['status']='running';save(row)
        row['result']=perform(row);row['status']='completed';row['completed']=time.time();save(row)
    except Exception as error:
        row['status']='failed';row['error']=str(error)[:4000]
        if hasattr(error,'receipt'):row['failureReceipt']=error.receipt
        save(row)
    finally:
        with LOCK:ACTIVE.discard(task_id)
def poll(task_id):
    row=get(task_id)
    if row['status']=='queued'and task_id not in ACTIVE:
        with LOCK:
            if task_id not in ACTIVE:
                ACTIVE.add(task_id);threading.Thread(target=run,args=(task_id,),daemon=True).start()
    elif row['status']=='running'and task_id not in ACTIVE:
        row['status']='interrupted';row['error']='自动检查进程曾中断；原模型回执需核对，未重新付费调用';save(row)
    return {**row,'upgradeAllowed':upgrade_allowed(row)}
def verified_colour(data,product_id,*,garment_kind=None):
    """Read server-owned evidence; a client cannot self-approve an image."""
    import image_engine
    task=get(data['qualityCheckId'])
    if task['kind']!='colour_check'or task['status']!='completed'or task['productId']!=product_id:raise ValueError('当前成图缺少已完成的独立检查')
    if task.get('processorVersion')!=processor_version('colour_check'):raise ValueError('原质检来自旧策略；保留历史，当前交付需要新策略完整检查')
    if garment_kind not in (None,'auto')and task['garmentKind']!=garment_kind:raise ValueError('商品部件已变化，原成图检查不能用于新部件')
    for key in ('source','mask','renderedImage'):
        url=data['source']if key=='source'else data[key]
        if task['inputs'].get(key)!=url or image_engine.asset(url)[1]!=task['assetSha256'][key]:raise ValueError('成图/选区与独立检查回执不匹配')
    if task['inputs']['target'].lower()!=data['target'].lower():raise ValueError('目标色与独立检查不匹配')
    return task['result']

def colour_review(product_id,source,mask,rendered,target,*,quality_check_id=None,selection_task_id=None,product_name=''):
    inputs={'source':source,'mask':mask,'renderedImage':rendered,'target':target}
    if quality_check_id:return verified_colour({**inputs,'qualityCheckId':quality_check_id},product_id,
        garment_kind=__import__('garment_auto').category({'name':product_name}))
    if selection_task_id:inputs['selectionTaskId']=selection_task_id
    task=start({**inputs,'requestId':uuid.uuid4().hex,'kind':'colour_check'},{'id':product_id,'name':product_name})
    while task['status']not in TERMINAL:
        time.sleep(2);task=poll(task['id'])
    if task['status']!='completed':raise ValueError(task.get('error')or'独立换色检查未完成')
    return task['result']
