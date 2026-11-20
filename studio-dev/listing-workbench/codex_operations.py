"""Account-scoped product status and operator-reviewed requests from Codex."""
import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager

import agent_center
import agent_handoff
import agent_research
import agent_selection
import app_paths
import codex_handoff
import discovery_intake
import erp_collection
import image_provider
import listing_jobs
import provider
import publication_flow
import studio_bridge
import visual_studio

VERSION = 1
TTL = 1800
REQUEST_ID = re.compile(r'[a-zA-Z0-9_-]{8,100}')
ACTION_LABELS = {
    'research_and_copy': '接续选品研究与文案',
    'generate_copy': '生成 Listing 文案',
    'generate_image': '生成指定图位',
    'collect_draft': '采集 ERP 草稿',
    'observe_publication': '核对原发布结果',
}
ACTION_EFFECTS = {
    'research_and_copy': ('原选品任务的研究与文案草稿','付费文本，预算仅记录',False),
    'generate_copy': ('本站 Listing 文案生成与版本合并','付费文本',False),
    'generate_image': ('指定方案的单个图位','按图像服务或订阅计量',False),
    'collect_draft': ('目标店铺的草稿保存与回读','ERP 草稿操作',True),
    'observe_publication': ('读取原美国及英国发布任务的回执','只读观察',False),
}


def authority(kind):
    stop, cost, writes = ACTION_EFFECTS[kind]
    return {'agentOperation':'submit_review','executor':'backend','stopAfter':stop,'costBasis':cost,
            'writesErp':writes,'authorizesPublication':False}


PROPOSAL_FIELDS = {
    'research_and_copy': {'budgetCny', 'researchAsins'},
    'generate_copy': set(),
    'generate_image': set(),
    'collect_draft': set(),
    'observe_publication': set(),
}


@contextmanager
def connect():
    with closing(sqlite3.connect(app_paths.DATA / 'codex-operations.sqlite3', timeout=15)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS proposals (
            account INTEGER, product TEXT, market TEXT, id TEXT, body TEXT NOT NULL,
            PRIMARY KEY(account, product, market, id))''')
        yield db


def read_workspace(database):
    with database() as db:
        row = db.execute('SELECT revision, body FROM workspace WHERE id=1').fetchone()
    return (row[0], json.loads(row[1])) if row else (0, {})


def validate_scope(workspace, product_id, market):
    if not isinstance(product_id, str) or not product_id or len(product_id) > 200:
        raise ValueError('请选择商品')
    if not isinstance(market, str) or market not in provider.MARKET_LANGUAGES:
        raise ValueError('请选择有效站点')
    return erp_collection.product_for(workspace, product_id)


def selection_tasks(owner, product_id, market):
    with closing(agent_center.connect()) as db:
        rows = db.execute(
            """SELECT body FROM tasks WHERE user_id=?
               AND json_extract(body,'$.productId')=?
               AND json_extract(body,'$.profile.marketplace')=?
               AND json_extract(body,'$.intake.source')='selection-report'
               ORDER BY created DESC""", (owner, product_id, market))
        return [json.loads(row[0]) for row in rows]


def selection_required(owner, product, market, tasks=None):
    reference = (product.get('selectionResearch') or {}).get('reference') or {}
    if tasks is None:
        tasks = selection_tasks(owner, product['id'], market)
    return bool(tasks or (reference.get('market') == market and reference.get('asin')))


def _project_actions(product, market):
    product_market = product.get('market') or (product.get('sourceImport') or {}).get('market') or 'US'
    if market != product_market:
        return None, []
    visual = visual_studio.list_projects(product['id'])
    projects = [p for p in visual['projects'] if p.get('market', market) == market
                and p.get('deliverable', 'gallery') == 'gallery']
    if not projects:
        return None, []
    project = projects[0]
    runs = {}
    for run in visual['runs']:
        if run.get('projectId') == project['id']:
            runs.setdefault(run.get('slot'), run)
    slots = []
    for index, _ in enumerate((project.get('plan') or {}).get('slots', [])):
        run = runs.get(index, {})
        slots.append({'slot': index, 'label': visual_studio.slot_name(project, index),
                      'runId': run.get('id'), 'status': run.get('status')})
    settings = image_provider.public()
    model = next(iter(settings['models']), None)
    return {'id': project['id'], 'confirmed': project.get('confirmed') is True, 'slots': slots}, [
        {'projectId': project['id'], 'slot': slot['slot'], 'label': slot['label'],
         'model': model, 'provider': settings['activeProvider'],
         'projectDigest': listing_jobs.digest(project)} for slot in slots
        if model and slot['runId'] is None]


def status(owner, database, product_id, market):
    revision, workspace = read_workspace(database)
    p = validate_scope(workspace, product_id, market)
    copy_key = product_id + '-' + market
    copy = workspace.get('copy', {}).get(copy_key, {})
    tasks = selection_tasks(owner, product_id, market)
    task = tasks[0] if len(tasks) == 1 else None
    cli_tasks = discovery_intake.overview(app_paths.DATA, owner, product_id)
    cli_task = next((t for t in cli_tasks if t['productId'] == product_id), None)
    actions, blockers = [], []

    def allow(action, **target):
        actions.append({'type': action, 'label': ACTION_LABELS[action], 'target': target,'authority':authority(action)})

    if cli_task:
        blockers.append('此款由关联的 CLI 台账执行，请按原任务和阶段核对')
    elif selection_required(owner, p, market, tasks):
        if not task:
            blockers.append('请在任务中心核对本款唯一的原选品任务')
        elif task['status'] == 'blocked' and 'copyHandoff' not in task:
            probe = dict(task, snapshot=agent_research.snapshot(workspace, task),
                         selectionPolicy=agent_selection.current_policy(), executionScope=agent_handoff.SCOPE)
            checks = agent_center.inspect_facts(probe)
            if checks['ok']:
                allow('research_and_copy', taskId=task['id'])
            else:
                blockers.extend(checks['issues'])
        elif task['status'] in ('needs_review', 'running', 'queued', 'awaiting_approval', 'blocked'):
            blockers.append(task.get('reason') or '请核对原选品任务及文案回执')
    else:
        generation = (p.get('listingGeneration') or {}).get(market, {})
        if generation.get('status') in ('uncertain', 'running', 'queued', 'ready', 'needs_review'):
            blockers.append('请核对原文案任务')
        elif p.get('name') and any(isinstance(p.get(field), str) and p[field].strip()
                                   for field in ('material', 'dimensions', 'features', 'style')):
            if len(listing_jobs.listing_locks.locked(copy)) == len(listing_jobs.FIELDS):
                blockers.append('当前文案字段全部锁定')
            else:
                allow('generate_copy')
        else:
            blockers.append('请补齐本款已核验的商品资料')
    visual, image_targets = _project_actions(p, market)
    if not cli_task:
        for target in image_targets:
            allow('generate_image', **target)
    erp = erp_collection.view(owner, workspace, product_id)
    destinations = [d for d in erp['destinations'] if d.get('marketplace') == market]
    erp_jobs = [j for j in erp['jobs'] if j.get('marketplace') == market]
    issues = {i['destinationId']: i['message'] for i in erp['issues']}
    packets = {}
    configured = {d['id']:d for d in erp_collection.destinations(owner)}
    for destination in destinations:
        destination_id = destination['id']
        prior = next((j for j in erp_jobs if j['destinationId'] == destination_id), None)
        if destination_id in issues:
            blockers.append(issues[destination_id])
        elif not cli_task and (prior is None or prior['status']=='needs_reconciliation'):
            target=configured.get(destination_id)
            if target is None:continue
            try:
                packet=erp_collection.preflight(owner,p,copy,target,prior)
            except (ValueError,TypeError,KeyError,OSError) as error:
                blockers.append(destination['store']+' · '+(str(error) if isinstance(error,ValueError) else '本地成品资料不完整，请核对原记录'))
                continue
            packets[destination_id]=packet
            allow('collect_draft',destinationId=destination_id,store=destination['store'],
                  destinationDigest=listing_jobs.digest(target),reviewDigest=erp_collection.review_digest(packet))
    published = publication_flow.list_jobs(owner, product_id) if market in ('US', 'UK') else []
    for job in published:
        if not cli_task and job.get('canObserveLatestReceipts'):
            allow('observe_publication', jobId=job['id'])

    reference = (p.get('selectionResearch') or {}).get('reference') or {}
    supplier = (p.get('sourceImport') or {}).get('supplier') or {}
    variants = erp_collection.eligible_variant_rows(p)
    stage = ('发布与在售核对' if published else 'ERP 草稿' if erp_jobs else '视觉套图' if visual
             else 'Listing 文案' if copy.get('title') else '选品、货源与研究')
    return {
        'version': VERSION, 'accountId': owner, 'productId': product_id, 'market': market, 'revision': revision, 'stage': stage,
        'product': {'name': p['name'], 'parentSku': p.get('sku'),
                    'variants': [{'sku': sku, 'color': color, 'size': size, 'sourceAsin': asin,'source':source,'mappingStatus':mapping}
                                 for sku, color, english, size, source, mapping, asin in variants]},
        'selection': {'qualification':{k:v for k,v in ((p.get('selectionResearch') or {}).get('qualification') or {}).items()
                                      if k in ('estimatedMarketProfitRmb','profitScope','evidenceSha256','supplierUrl','cliJobId')},
                      'reference': {key: reference[key] for key in ('asin', 'market', 'url') if key in reference},
                      'cliTask': cli_task,
                      'tasks': [{'id': t['id'], 'status': t['status'], 'reason': t.get('reason'),
                                 'scope': t.get('executionScope')} for t in tasks]},
        'supplier': {'url': p.get('sourceUrl'), 'capturedUrl': supplier.get('url'),
                     'facts': {field: p.get(field) for field in ('material', 'dimensions', 'features',
                                                                 'style','packageContents', 'packageWeight')}},
        'copy': {'digest': listing_jobs.digest(copy), 'fields': {key: copy.get(key) for key in listing_jobs.FIELDS},
                 'job': (p.get('listingGeneration') or {}).get(market)},
        'visual': visual,
        'draftPackets':packets,
        'amounts':amounts(p,market,tasks),
        'erp': {'destinations': destinations, 'jobs': [
            {'draftReadbackVerified':j.get('status')=='verified' and bool(j.get('draftId')),
             **{key: j.get(key) for key in ('id', 'status', 'phase', 'destinationId', 'draftId', 'collectionId')}}
            for j in erp_jobs]},
        'publication': [{key: j.get(key) for key in ('id', 'status', 'phase', 'sourceStore', 'targetStore',
                                                     'usPublishId', 'ukDraftId', 'ukPublishId', 'onlineVerified',
                                                     'usPublicationObservation','ukPublicationObservation','publishSubmitted')}
                        for j in published],
        'blockers': list(dict.fromkeys(blockers)), 'actions': actions,
    }


def amounts(product,market,tasks):
    research=product.get('selectionResearch') or {}
    proof=research.get('qualification') or {}
    return {'estimatedMarketProfitCny':proof.get('estimatedMarketProfitRmb') if
            (research.get('reference') or {}).get('market')==market else None,
            'textBudgets':[{'taskId':t['id'],'budgetCny':t['copyHandoff']['budgetCny']} for t in tasks
                           if (t.get('copyHandoff') or {}).get('budgetCny') is not None],
            'productImageCosts':image_provider.product_cost_receipts(product['id']),
            'externalBillCny':None}


def proposal_view(body):
    proposal = json.loads(body)
    if proposal['status'] in ('assigned', 'pending') and proposal['expiresAt'] <= time.time():
        proposal['status'] = 'expired'
    elif proposal['status'] in ('assigned','pending') and (proposal.get('assignment') or {}).get('version')!=2:
        proposal['status'] = 'requires_assignment'
    return proposal


def read_proposal(db, key):
    row = db.execute('SELECT body FROM proposals WHERE account=? AND product=? AND market=? AND id=?', key).fetchone()
    if row is None:
        raise ValueError('找不到该商品和站点的请求')
    return proposal_view(row[0])


def reconcile(proposal,key):
    if proposal['status'] not in ('dispatching','needs_review'):
        return proposal
    kind=proposal['request']['type']
    ledgers={'research_and_copy':lambda:closing(agent_center.connect()),'generate_copy':listing_jobs.database,
             'generate_image':lambda:closing(visual_studio.db()),'collect_draft':erp_collection.connect,
             'observe_publication':publication_flow.connect}
    with ledgers[kind]() as db:
        found=codex_handoff.lookup(db,key)
    if found:
        prepared=found['handoffStage']=='prepared'
        return {**proposal,**found,'status':'needs_review' if prepared else 'dispatched',
                'message':'接续已配置，启动待核对' if prepared else '原执行器已登记交接，业务结果见原任务'}
    return {**proposal,'message':'尚未找到本次执行器回执，请按原请求核对'}


def receipt(owner, product, market, request_id):
    with connect() as db:
        key=(owner, product, market, request_id)
        return reconcile(read_proposal(db,key),key)


def decline(owner, product, market, request_id):
    key = (owner, product, market, request_id)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        proposal = read_proposal(db, key)
        if proposal['status'] not in ('assigned', 'pending'):
            return proposal
        proposal.update(status='declined', declinedAt=time.time(), declinedBy=owner)
        db.execute('UPDATE proposals SET body=? WHERE account=? AND product=? AND market=? AND id=?',
                   (json.dumps(proposal, ensure_ascii=False), *key))
        return proposal


def list_proposals(account, product, market):
    with connect() as db:
        rows = db.execute("""WITH scoped AS (
            SELECT rowid AS sequence, body FROM proposals WHERE account=? AND product=? AND market=?
        ) SELECT body FROM scoped WHERE sequence IN (
            SELECT sequence FROM scoped ORDER BY sequence DESC LIMIT 30
        ) OR json_extract(body,'$.status') IN ('dispatching','needs_review')
          OR (json_extract(body,'$.status') IN ('pending','assigned') AND json_extract(body,'$.expiresAt')>?)
        ORDER BY sequence DESC""", (account, product, market, time.time()))
        proposals=[proposal_view(row[0]) for row in rows]
        return [reconcile(p,(account,product,market,p['request']['requestId'])) for p in proposals]


REVIEW_STEPS = {
    'research_and_copy': '核对原选品任务编号、候选 ASIN、货源资料及运营员指定的竞品与预算。',
    'generate_copy': '核对当前站点、商品资料与现有文案，指出缺少依据或相互矛盾的商品描述。',
    'generate_image': '核对当前方案、图位用途、已保存的生成记录及指定模型。',
    'collect_draft': '核对目的店铺、父子 SKU、当前站点文案、图位及原 ERP 草稿回执。',
    'observe_publication': '核对原发布任务编号、关联店铺和已有回执，区分已受理与已在售。',
}
REVIEW_INPUTS = {
    'research_and_copy': ('selection', 'supplier'),
    'generate_copy': ('product', 'supplier', 'copy'),
    'generate_image': ('product', 'visual'),
    'collect_draft': ('product', 'copy', 'visual', 'erp'),
    'observe_publication': ('publication',),
}


def review_inputs(snapshot,data):
    kind,target=data['type'],data['target']
    inputs={k:snapshot[k] for k in REVIEW_INPUTS[kind]}
    if kind=='collect_draft':
        inputs={'packet':snapshot['draftPackets'][target['destinationId']],
                'receipts':[j for j in snapshot['erp']['jobs'] if j['destinationId']==target['destinationId']]}
    elif kind=='observe_publication':
        inputs={'publication':[j for j in snapshot['publication'] if j['id']==target['jobId']]}
    return {**inputs,'target':target,'parameters':data['parameters'],'market':snapshot['market']}


def checklist(inputs):
    items=[]
    def visit(path,value):
        if isinstance(value,dict) and value and 'sha256' not in value:
            for key,child in value.items():
                visit(path+'/'+key.replace('~','~0').replace('/','~1'),child)
        elif isinstance(value,list) and value:
            for index,child in enumerate(value):
                visit(path+'/'+str(index),child)
        else:
            items.append({'path':path,'digest':listing_jobs.digest(value)})
    visit('',inputs)
    return items


def validate_evidence(assignment,refs,decision):
    expected={i['path']:i['digest'] for i in assignment['checks']}
    seen=set()
    blocked=False
    for ref in refs:
        if not isinstance(ref,dict) or set(ref)!={'path','digest','decision'}:
            raise ValueError('请逐项回传路径、原值摘要和结论')
        path=ref['path']
        if (not isinstance(path,str) or path in seen or path not in expected or expected[path]!=ref['digest']
                or ref['decision'] not in ('ready','blocked')):
            raise ValueError('核对项重复、资料不符或结论无效')
        seen.add(path)
        blocked |= ref['decision']=='blocked'
    if (decision=='ready' and (seen!=expected.keys() or blocked)) or (decision=='blocked' and not blocked):
        raise ValueError('通过须逐项核对，阻塞须指出具体项目')


def check_unresolved_handoff(db,owner,product,market,request):
    kind=request['type']
    fields={'research_and_copy':('taskId',),'generate_copy':(),'generate_image':('projectId','slot'),
            'collect_draft':('destinationId',),'observe_publication':('jobId',)}[kind]
    rows=db.execute("""SELECT market,id,body FROM proposals WHERE account=? AND product=?
        AND json_extract(body,'$.request.type')=?
        AND json_extract(body,'$.status') IN ('dispatching','needs_review')""",(owner,product,kind))
    for old_market,rid,body in rows.fetchall():
        item=json.loads(body)
        if kind=='generate_copy' and old_market!=market:
            continue
        if any(item['request']['target'].get(k)!=request['target'].get(k) for k in fields):
            continue
        current=reconcile(item,(owner,product,old_market,rid))
        if current['status']!='dispatched':
            raise ValueError('同一动作仍有待对账的执行意图，请查看 '+old_market+' 原请求 '+rid)
        db.execute('UPDATE proposals SET body=? WHERE account=? AND product=? AND market=? AND id=?',
                   (json.dumps(current,ensure_ascii=False),owner,product,old_market,rid))


def assign(owner, database, product, market, data):
    if not isinstance(data, dict) or set(data) != {'revision', 'type', 'target', 'parameters'}:
        raise ValueError('操作请求格式无效')
    kind, parameters = data['type'], data['parameters']
    if (type(data['revision']) is not int or not isinstance(kind, str)
            or kind not in PROPOSAL_FIELDS or not isinstance(parameters, dict)
            or set(parameters) != PROPOSAL_FIELDS[kind] or not isinstance(data['target'], dict)):
        raise ValueError('操作请求参数无效')
    if kind == 'research_and_copy':
        agent_handoff.copy_parameters(parameters)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        snapshot = status(owner, database, product, market)
        if data['revision'] != snapshot['revision'] or not any(
                a['type'] == kind and a['target'] == data['target'] for a in snapshot['actions']):
            raise ValueError('操作或资料版本已变化，请重新读取商品状态')
        check_unresolved_handoff(db,owner,product,market,data)
        inputs = review_inputs(snapshot,data)
        fingerprint = listing_jobs.digest([2,data, inputs])
        rows = db.execute("""SELECT body FROM proposals WHERE account=? AND product=? AND market=?
            AND json_extract(body,'$.fingerprint')=? AND json_extract(body,'$.expiresAt')>? AND json_extract(body,'$.assignment.version')=2
            AND json_extract(body,'$.status') IN ('assigned','pending')""",
                          (owner, product, market, fingerprint, time.time()))
        existing = rows.fetchone()
        if existing:
            return proposal_view(existing[0])
        request_id = uuid.uuid4().hex
        proposal = {'request': {**data, 'requestId': request_id}, 'status': 'assigned', 'label': ACTION_LABELS[kind],
                    'fingerprint': fingerprint,
                    'authority':authority(kind),
                    'assignment': {'version':2,'checks':checklist(inputs),'accountId': owner, 'productId': product, 'market': market,
                                   'goal': '核对后端指定动作的输入并交回核对意见',
                                   'instructions': REVIEW_STEPS[kind], 'inputs': inputs,
                                   'allowedOperations': ['submit_review'],
                                   'resultSchema': {'decision': ['ready', 'blocked'], 'note': '1 至 500 字',
                                                    'evidence': ['path','digest','decision']}},
                    'createdAt': time.time(), 'expiresAt': time.time() + TTL}
        db.execute('INSERT INTO proposals VALUES (?,?,?,?,?)',
                   (owner, product, market, request_id, json.dumps(proposal, ensure_ascii=False)))
        return proposal


def next_assignment(owner, product, market):
    with connect() as db:
        row = db.execute("""SELECT body FROM proposals WHERE account=? AND product=? AND market=?
            AND json_extract(body,'$.status')='assigned' AND json_extract(body,'$.assignment.version')=2
            AND json_extract(body,'$.expiresAt')>?
            ORDER BY rowid LIMIT 1""", (owner, product, market, time.time())).fetchone()
        return {'assignment': json.loads(row[0]) if row else None}


def submit_review(owner, database, product, market, data):
    if not isinstance(data, dict) or set(data) != {'requestId', 'decision', 'note', 'evidence'}:
        raise ValueError('仅接受派单编号、核对结论、说明及证据引用')
    request_id, note, refs = data['requestId'], data['note'], data['evidence']
    if (not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id)
            or data['decision'] not in ('ready', 'blocked') or not isinstance(note, str)
            or not 1 <= len(note.strip()) <= 500 or not isinstance(refs, list)
            or not refs):
        raise ValueError('核对结果格式无效')
    key = (owner, product, market, request_id)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        item = read_proposal(db, key)
        if item.get('review') == data:
            return item
        if item['status'] != 'assigned':
            raise ValueError('仅当前有效派单可交回一次核对结果')
        assignment = item['assignment']
        validate_evidence(assignment,refs,data['decision'])
        snapshot = status(owner, database, product, market)
        request = item['request']
        if (snapshot['revision'] != request['revision']
                or not any(a['type']==request['type'] and a['target']==request['target'] for a in snapshot['actions'])
                or review_inputs(snapshot,request)!=assignment['inputs']):
            item.update(status='stale', message='派单资料或允许动作已变化，请由工作台重新派单')
        else:
            item.update(review=data, reviewedAt=time.time(), status='pending' if data['decision']=='ready' else 'blocked')
        db.execute('UPDATE proposals SET body=? WHERE account=? AND product=? AND market=? AND id=?',
                   (json.dumps(item, ensure_ascii=False), *key))
        return item


@contextmanager
def dispatch_guard(key):
    directory = app_paths.DATA / 'codex-dispatch-locks'
    directory.mkdir(exist_ok=True)
    name = hashlib.sha256(json.dumps(key).encode()).hexdigest()
    with closing(sqlite3.connect(directory / (name + '.sqlite3'), timeout=0)) as guard:
        try:
            guard.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError as exc:
            raise ValueError('原审批仍在处理，请稍后刷新原请求') from exc
        yield


def resolve_submission(owner, product, market, request_id, reference):
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError('原请求编号无效')
    if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 500:
        raise ValueError('请记录查询的原账单、服务工单或 ERP 流水及核查结论')
    key = (owner, product, market, request_id)
    with dispatch_guard(key), connect() as db:
        db.execute('BEGIN IMMEDIATE')
        proposal = read_proposal(db, key)
        if proposal['status'] not in ('dispatching', 'needs_review'):
            return proposal
        proposal = reconcile(proposal, key)
        if not proposal.get('handoffStage'):
            proposal.update(status='not_submitted', message='运营员已核实未提交，可重新派单',
                            resolution={'operator': owner, 'at': time.time(), 'requestId': request_id,
                                        'reference': reference.strip()})
        db.execute('UPDATE proposals SET body=? WHERE account=? AND product=? AND market=? AND id=?',
                   (json.dumps(proposal, ensure_ascii=False), *key))
        return proposal


def approve(owner, database, product, market, request_id):
    with dispatch_guard((owner, product, market, request_id)):
        return approve_locked(owner, database, product, market, request_id)


def approve_locked(owner, database, product, market, request_id):
    key = (owner, product, market, request_id)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        proposal = read_proposal(db, key)
        if proposal['status'] != 'pending':
            return reconcile(proposal,key)
        data = proposal['request']
        check_unresolved_handoff(db,owner,product,market,data)
        snapshot = status(owner, database, product, market)
        if snapshot['revision'] != data['revision'] or not any(
                a['type'] == data['type'] and a['target'] == data['target'] for a in snapshot['actions']):
            raise ValueError('商品资料或任务已变化，请重新提交操作请求')
        if review_inputs(snapshot,data)!=proposal['assignment']['inputs'] or proposal['authority']!=authority(data['type']):
            raise ValueError('核对资料或授权范围已变化，请重新派单')
        # Persist intent before dispatch. A lost response cannot cause another dispatch.
        proposal.update(status='dispatching', approvedAt=time.time(), approvedBy=owner)
        db.execute('UPDATE proposals SET body=? WHERE account=? AND product=? AND market=? AND id=?',
                   (json.dumps(proposal, ensure_ascii=False), *key))
    try:
        result = dispatch(owner, database, product, market, data)
    except Exception:
        # An external service may already have accepted the request.
        proposal.update(status='needs_review', message='须核对本款原任务及外部回执')
        proposal=reconcile(proposal,key)
    else:
        proposal.update(status='dispatched', jobId=result.get('id'), jobStatus=result.get('status'))
    with connect() as db:
        db.execute('UPDATE proposals SET body=? WHERE account=? AND product=? AND market=? AND id=?',
                   (json.dumps(proposal, ensure_ascii=False), *key))
    return proposal


def dispatch(owner, database, product, market, data):
    kind, target = data['type'], data['target']
    handoff=(owner,product,market,data['requestId'])
    if kind == 'research_and_copy':
        task_id = target['taskId']
        agent_handoff.prepare(owner, task_id, dict(data['parameters'], workspaceRevision=data['revision'],
                                                   confirmPaidText=True, acknowledgeBudgetNotHardCap=True),handoff=handoff)
        return agent_center.start(owner, task_id)
    if kind == 'generate_copy':
        return listing_jobs.start(owner, {'productId': product, 'market': market,
                                         'expectedRevision': data['revision'], 'requestId': data['requestId']},handoff=handoff)
    if kind == 'observe_publication':
        return publication_flow.observe(owner, target['jobId'],handoff=handoff)
    revision, workspace = read_workspace(database)
    if revision != data['revision']:
        raise ValueError('资料已更新，请核对原请求')
    if kind == 'generate_image':
        p = validate_scope(workspace, product, market)
        copy = workspace.get('copy', {}).get(product + '-' + market, {})
        return studio_bridge.render(
            {'projectId': target['projectId'], 'indices': [target['slot']], 'confirmed': True,
             'config': {'model': target['model'], 'size': '1:1', 'resolution': '2K'}},
            p, copy, codex_target=target,handoff=handoff)
    if kind == 'collect_draft':
        destination = next((d for d in erp_collection.destinations(owner) if d['id'] == target['destinationId']), None)
        if listing_jobs.digest(destination) != target['destinationDigest']:
            raise ValueError('ERP 目标已变化，请核对本款原请求')
        return erp_collection.start(owner, workspace, {'productId': product, 'destinationId': target['destinationId']},
                                    reviewed_digest=target['reviewDigest'],handoff=handoff)
    raise ValueError('未知操作')
