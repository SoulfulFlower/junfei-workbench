"""Continue one known quantity-format failure from its exact returned stages."""
import copy
import hashlib
import json
import re
import uuid

import listing_jobs as jobs
import provider

ERROR = '包装数量缺少依据，产品描述应使用无数量包装行'


def bundle(job, refs):
    if not isinstance(refs, dict) or set(refs) != {'initial', 'polish'}:
        raise ValueError('须提供原初稿与润色回执')
    folder = jobs.DB.parent / 'listing-responses'
    identity = {'jobId': job['id'], 'owner': job['owner'], 'productId': job['productId'],
                'inputDigest': job['inputDigest']}
    records = {}
    for stage, purpose in [('initial', None), ('polish', 'listing_unslop')]:
        ref = refs[stage]
        if (not isinstance(ref, dict) or set(ref) != {'id', 'sha256'}
                or not re.fullmatch(r'[a-f0-9]{32}', str(ref['id']))
                or not re.fullmatch(r'[a-f0-9]{64}', str(ref['sha256']))):
            raise ValueError('原回执编号或哈希无效')
        path = folder / (ref['id'] + '.json')
        raw = path.read_bytes()
        if len(raw) > 2*1024*1024 or hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('原回执哈希变化')
        record = json.loads(raw)
        if (record.get('listingTask') != identity or record.get('market') != job['market']
                or record.get('purpose') != purpose
                or record['response']['choices'][0].get('finish_reason') != 'stop'):
            raise ValueError('原回执任务、账号或阶段不匹配')
        provider.response_json(record['response'])
        records[stage] = record
    if refs['initial']['id'] == refs['polish']['id']:
        raise ValueError('初稿和润色回执不能相同')
    returned = set()
    for path in folder.glob('*.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('listingTask', {}).get('jobId') == job['id']:
            returned.add(path.stem)
    if returned != {ref['id'] for ref in refs.values()}:
        raise ValueError('原任务已有后续响应，须先核对，不能重复审校')
    if records['initial']['createdAt'] >= records['polish']['createdAt']:
        raise ValueError('原回执阶段顺序无效')
    routing = {(r.get('provider'), r['response'].get('model')) for r in records.values()}
    settings = provider.text_settings()
    if routing != {(provider.text_provider_name(settings), settings['model'])}:
        raise ValueError('原稿与当前模型身份不一致')
    return records


def amended_snapshot(job, state):
    product = jobs.product_for(state, job['productId'])
    snapshot = jobs.input_snapshot(state, product, job['market'])
    evidence = product.get('packageContentsEvidence')
    supplier = (product.get('sourceImport') or {}).get('supplier') or {}
    if (provider.confirmed_package_quantity(product.get('packageContents')) != 1
            or not isinstance(evidence, dict) or evidence.get('source') != 'supplier_page'
            or evidence.get('sourceUrl') != supplier.get('url') or not supplier.get('url')
            or evidence.get('quantity') != 1 or evidence.get('raw') != '组合形式: 单件'
            or not evidence.get('observedAt')):
        raise ValueError('缺少同货源单件包装的明确证据')
    original = job['inputSnapshot']
    base = copy.deepcopy(snapshot)
    for field in ('packageContents', 'packageContentsEvidence'):
        if field in original['product']:
            base['product'][field] = copy.deepcopy(original['product'][field])
        else:
            base['product'].pop(field, None)
    if base != original or provider.confirmed_package_quantity(original['product'].get('packageContents')) is not None:
        raise ValueError('除已核实包装内容外，原产品、文案或锁已变化')
    return snapshot


def start(owner, data):
    jobs.account(owner)
    if (not isinstance(data, dict) or set(data) != {'id', 'requestId', 'receipts'}
            or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', str(data['requestId']))):
        raise ValueError('原稿格式接续参数无效')
    with jobs.LOCK, jobs.database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        job = jobs.owned(conn, owner, data['id'])
        prior = job.get('formatRecovery')
        if prior:
            if prior.get('requestId') != data['requestId'] or prior.get('receipts') != data['receipts']:
                raise ValueError('原格式接续已经存在，先查询原任务')
            return jobs.public(job, include_result=True, reused=True)
        if (job['status'] != 'needs_review' or job.get('error') != ERROR
                or job.get('result') or job['id'] in jobs.ACTIVE):
            raise ValueError('不是已核实的单件包装格式失败，不能接续')
        bundle(job, data['receipts'])
        revision, state = jobs.workspace(conn)
        snapshot = amended_snapshot(job, state)
        recovery = {'id': uuid.uuid4().hex, 'requestId': data['requestId'],
            'scope': 'continue_returned_draft_after_package_evidence', 'phase': 'queued',
            'originalError': job['error'], 'receipts': copy.deepcopy(data['receipts']),
            'originalInputSnapshot': copy.deepcopy(job['inputSnapshot']),
            'originalInputDigest': job['inputDigest'], 'authorizedAt': jobs.stamp(),
            'modelIdentity': provider.exhausted_model_identity(provider.text_settings()), 'stageResponses': []}
        job.update(formatRecovery=recovery, inputSnapshot=snapshot, inputDigest=jobs.digest(snapshot),
            status='queued', runOwner=jobs.RUNTIME, stage='原稿格式接续已排队',
            message='复用原初稿和润色稿，继续未提交的审校')
        job.pop('error', None)
        jobs.write_outcome(conn, state, revision, job)
        jobs.save(conn, job)
        jobs.ACTIVE.add(job['id'])
    try:
        jobs.THREAD_FACTORY(target=execute, args=(owner, job['id']), daemon=True,
                           name='listing-format-' + job['id'][:8]).start()
    except Exception:
        jobs.ACTIVE.discard(job['id'])
        raise
    return jobs.public(job, include_result=True)


def execute(owner, jid):
    try:
        with jobs.LOCK, jobs.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            job = jobs.owned(conn, owner, jid)
            scope = job['formatRecovery']
            if job['status'] != 'queued' or scope['phase'] != 'queued' or job.get('runOwner') != jobs.RUNTIME:
                return
            original = {**job, 'inputDigest': scope['originalInputDigest']}
            records = bundle(original, scope['receipts'])
            if provider.exhausted_model_identity(provider.text_settings()) != scope['modelIdentity']:
                raise ValueError('原接续模型配置变化')
            scope['phase'] = 'running'
            job.update(status='running', stage='复用原稿接续审校中')
            jobs.save(conn, job)
        def saved(receipt_id, record):
            with jobs.LOCK, jobs.database() as conn:
                current = jobs.owned(conn, owner, jid)
                current['formatRecovery']['stageResponses'].append({'receiptId': receipt_id,
                    'purpose': record.get('purpose'), 'createdAt': record['createdAt']})
                jobs.save(conn, current)
        identity = {'jobId': jid, 'owner': owner, 'productId': job['productId'],
                    'inputDigest': job['inputDigest'], 'formatRecoveryId': scope['id']}
        with provider.listing_response_scope(identity, saved):
            result = provider.resume_listing_format(copy.deepcopy(job['inputSnapshot']['product']), job['market'],
                initial_raw=records['initial']['response'], polished_raw=records['polish']['response'],
                receipt_id=scope['receipts']['initial']['id'])
        result['copy']['generationEngine']['formatRecovery'] = {'id': scope['id'],
            'initialReceipt': scope['receipts']['initial']['id'], 'polishReceipt': scope['receipts']['polish']['id']}
        jobs.save_result_receipt(job, result)
        with jobs.LOCK, jobs.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = jobs.owned(conn, owner, jid)
            current['formatRecovery']['phase'] = 'completed'
            current.update(status='ready', result=result, responseReceipt=result.get('responseReceipt'))
            jobs.safe_apply_result(conn, current)
    except Exception as error:
        with jobs.LOCK, jobs.database() as conn:
            job = jobs.owned(conn, owner, jid)
            if job['status'] != 'applied':
                job['formatRecovery'].update(phase='needs_review', error=str(error)[:2000])
                job.update(status='needs_review', error=str(error)[:2000], stage='原稿接续待核对',
                           message='已保留原稿和接续响应，不自动重发')
                revision, state = jobs.workspace(conn)
                jobs.write_outcome(conn, state, revision, job)
                jobs.save(conn, job)
    finally:
        jobs.ACTIVE.discard(jid)
