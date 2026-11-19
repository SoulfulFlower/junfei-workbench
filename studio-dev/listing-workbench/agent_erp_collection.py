"""Task-center handoff to the account's formal, durable ERP collection flow.

No legacy binding is created. Reading a receipt never starts a browser, and a
verified receipt is adopted only after its current business contents match.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import tempfile

import erp_collection as erp

STEPS=('plan','junfeiPreflight','publish')


def destinations(user):
    return [{k:d[k] for k in ('id','name','store','marketplace') if k in d}
            for d in erp.destinations(user)]


def profile_for_destination(user, target_id):
    matches=[d for d in erp.destinations(user) if d.get('id')==target_id]
    if len(matches)!=1:raise ValueError('请明确选择本账号已配置的正式ERP采集目标')
    target=matches[0]
    # These task labels do not carry browser/plugin login or transport settings.
    return {'id':'erp:'+target['id'],'name':target.get('name') or target['store'],
            'store':target['store'],'marketplace':target['marketplace'],'mode':'draft','platform':'junfei',
            'quantity':target.get('quantity'),'handlingDays':target.get('handlingDays'),'shippingTemplate':''}


def destination(user, profile, target_id):
    if profile.get('mode')!='draft':
        raise ValueError('正式ERP交付仅保存目标店铺草稿，不发布')
    matches=[d for d in erp.destinations(user) if d.get('id')==target_id]
    if len(matches)!=1:
        raise ValueError('请明确选择本账号已配置的正式ERP采集目标')
    target=matches[0]
    if (target.get('marketplace')!=profile.get('marketplace')
            or target.get('store')!=profile.get('store')):
        raise ValueError('正式ERP目标的店铺、站点须与任务档案完全一致，请核对后重新选择')
    return target


def saved_job(user, product_id, target_id):
    """Read-only lookup: opening the task page must not allocate an ERP job."""
    path=erp.ROOT/'jobs.sqlite3'
    if not path.is_file():return None
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone():return None
        row=db.execute('SELECT body FROM jobs WHERE account_id=? AND product_id=? AND destination_id=?',
                       (user,product_id,target_id)).fetchone()
    return json.loads(row[0]) if row else None


def assert_no_legacy_operations(user, task, ledger_path):
    """A new task/mode cannot bypass an old unknown or SKU operation barrier."""
    import agent_erp
    product=task['snapshot']['product']
    sku=product.get('sku','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',sku):
        raise ValueError('产品缺少有效父SKU')
    project=agent_erp.project_root()
    for name in ('ego-library-draft-executions','ego-library-package-executions'):
        if (project/'automation/data'/name/(str(user)+'-'+sku+'.json')).exists():
            raise ValueError('此账号原SKU已有旧ERP操作回执（含未知结果或次数限制），请先对账；未新建、上传或重试')
    if (project/'automation/data/ego-workbench.lock').exists():
        raise ValueError('旧ERP浏览器操作仍有执行锁待核对，未启动正式采集')
    config=project/'automation/config.json'
    if config.is_file():
        browser=json.loads(config.read_text(encoding='utf-8')).get('browser',{})
        bindings=[b for b in browser.get('erp_account_bindings',{}).get(str(user),[])
                  if b.get('product_id')==task['productId'] and b.get('store')==task['profile']['store']
                  and b.get('marketplace')==task['profile']['marketplace']]
        for path in (project/'automation/data/ego-draft-executions').glob('*.json') if bindings else []:
            record=json.loads(path.read_text(encoding='utf-8'))
            if any(all(record.get(k)==binding.get(field) for k,field in
                       (('draftId','draft_id'),('erpSku','erp_sku'),('store','store'))) for binding in bindings):
                raise ValueError('此账号已有绑定ERP草稿的旧修改回执，请先对账；新任务不绕过原记录')
    if not Path(ledger_path).is_file():return
    with closing(sqlite3.connect(Path(ledger_path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone():return
        for tid,raw in db.execute('SELECT id,body FROM tasks WHERE user_id=?',(user,)):
            if tid==task['id']:continue
            previous=json.loads(raw)
            if previous.get('erpWorkflowVersion')==2:continue
            prior_sku=(previous.get('snapshot',{}).get('product') or {}).get('sku')
            if previous.get('productId')!=task['productId'] and prior_sku!=sku:continue
            effect=previous.get('results',{}).get('publish') or {}
            if (previous.get('libraryDraftAttempted') or effect.get('copySynced') or effect.get('librarySaved')
                    or effect.get('draftId') or effect.get('libraryId')
                    or previous.get('status')=='needs_review' and previous.get('cursor',0)>=7):
                raise ValueError('原任务已有ERP执行或未知结果，请先核对原SKU回执；不能通过新任务重新上传')


def preflight(user, task, workspace, ledger_path):
    target=destination(user,task['profile'],task.get('erpDestinationId'))
    assert_no_legacy_operations(user,task,ledger_path)
    product=erp.product_for(workspace,task['productId'])
    listing=workspace.get('copy',{}).get(product['id']+'-'+target['marketplace'],{})
    prior=saved_job(user,product['id'],target['id'])
    original=None
    if prior:
        jid=prior.get('id','')
        if not re.fullmatch(r'[a-f0-9]{32}',jid):raise ValueError('原ERP采集任务编号无效，已停止等待核对')
        path=erp.ROOT/jid/'collection.json'
        if path.is_file():original=json.loads(path.read_text(encoding='utf-8'))
        if prior.get('status')=='verified' and original is None:
            raise ValueError('原ERP完成回执缺少可核对快照，不能仅凭完成状态接续')
        if prior.get('status')=='verified':
            receipt=erp.ROOT/jid/'receipt.json'
            if prior.get('engine')!='native-v2' or prior.get('nativeJoined') is not True or not receipt.is_file():
                raise ValueError('原记录未证明正式ERP原生转入及草稿核对，请到原交付页对账')
            try:erp.verified_result(dict(prior),json.loads(receipt.read_text(encoding='utf-8')),original)
            except (ValueError,KeyError,TypeError) as error:
                raise ValueError('正式ERP原回执证据不完整，已保留原记录等待核对') from error
    # The formal module checks the selected original files, confirmed children,
    # prices and Listing. A temporary folder contains no external credentials.
    with tempfile.TemporaryDirectory(prefix='agent-erp-preflight-') as folder:
        current=erp.finished_snapshot(user,product,listing,target,Path(folder)/'media',original)
    if original and erp.inputs.content_digest(current)!=erp.inputs.content_digest(original):
        raise ValueError('当前成品与原正式采集版本不同，请先对账更新；未复用旧成功回执或重新上传')
    return {'ok':True,'issues':[],'draftOnly':True,'published':False,
            'destination':{k:target[k] for k in ('id','name','store','marketplace') if k in target},
            'contentSha256':erp.inputs.content_digest(current),'variantCount':len(current['goodsItems']),
            'imageCount':len(current['assets']),'note':'正式采集预检通过，未操作ERP；原始文件、SKU与草稿范围已核对'}


def sync(user, task, workspace, ledger_path):
    preflight(user,task,workspace,ledger_path)
    prior=saved_job(user,task['productId'],task['erpDestinationId'])
    if prior:
        job=erp.public(prior)
        # This path is entirely read-only and does not call start/execute.
        if job['status']=='verified':return outcome(job)
        # An in-flight or uncertain original result is a receipt to inspect,
        # never permission for the task center to replay the browser operation.
        return {**outcome(job),'erpPending':True,'reason':'正式ERP原任务尚在执行或待对账，请在原交付页核对/继续；未新建或重新上传'}
    job=erp.start(user,workspace,{'productId':task['productId'],'destinationId':task['erpDestinationId'],
        'expectedListing':workspace.get('copy',{}).get(task['productId']+'-'+task['profile']['marketplace'],{})})
    return {**outcome(job),'erpPending':job['status']!='verified',
            'reason':'正式采集已启动，关闭页面后仍可从同一任务查看回执' if job['status']!='verified' else 'ERP草稿已核对'}


def outcome(job):
    verified=bool(job.get('status')=='verified' and job.get('published') is False
              and job.get('engine')=='native-v2' and job.get('nativeJoined') is True
              and re.fullmatch(r'\d+',str(job.get('draftId','')))
              and re.fullmatch(r'\d+',str(job.get('collectionId',''))))
    return {'ok':verified,'issues':[],'draftOnly':True,'published':False,
            'erpCollection':job,'reason':'正式ERP草稿回执已核对；未发布' if verified else '正式ERP采集等待原回执核对'}
