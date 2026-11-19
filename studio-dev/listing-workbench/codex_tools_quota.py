"""Record explicitly enabled local ChatGPT subscription calls, separately from cash."""
import json
import os
from pathlib import Path

BASE = 'http://127.0.0.1:8787/v1'


def verify(policy, data):
    if policy.get('enabled') is not True or policy.get('mode') != 'chatgpt_subscription_quota':
        raise ValueError('Codex Tools 订阅额度模式未启用，未提交生图')
    unreferenced_slot=(data.get('protocol')=='generations' and data.get('references')==[]
                       and (data.get('size')=='1:1'
                            or (data.get('deliveryCanvas')=='1464x600' and data.get('size')=='16:9')))
    if (data.get('providerEndpoint')!=BASE or data.get('model')!='gpt-image-2'
            or (data.get('protocol')!='edits' and not unreferenced_slot)):
        raise ValueError('Codex Tools 订阅额度仅用于已核对的本机 gpt-image-2 编辑和无参考图图位')
    root = Path(os.environ.get('APPDATA','')) / 'com.carry.codex-tools'
    store = json.loads((root/'accounts.json').read_text(encoding='utf-8-sig'))
    accounts = [a for a in store.get('accounts',[]) if isinstance(a,dict) and a.get('apiProxyEnabled') is not False]
    if not accounts or any(a.get('sourceKind') != 'chatgpt' for a in accounts):
        raise ValueError('Codex Tools 账号池包含非订阅或未知来源，须先核实现金报价；未提交生图')
    if store.get('settings',{}).get('apiProxyPort') != 8787:
        raise ValueError('Codex Tools 端口已改变，未提交生图')
    return {'accountingBasis':'chatgpt_subscription_quota','units':1,'unit':'request',
            'cashCost':None,'cashCostVerified':False,
            'source':'local Codex Tools active account source types and native image transport',
            'note':'消耗 ChatGPT 订阅额度；不按人民币报价记账，不代表免费、无限额度或已结算费用。'}


def schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS image_quota_requests (
        id TEXT PRIMARY KEY, product_id TEXT NOT NULL, day TEXT NOT NULL,
        state TEXT NOT NULL, external_id TEXT, body TEXT NOT NULL)''')


def reserve(conn, policy, attempt, data, day):
    evidence=verify(policy,data)
    schema(conn)
    conn.execute('INSERT INTO image_quota_requests VALUES (?,?,?,?,NULL,?)',
                 (attempt['id'],attempt['productId'],day,'reserved',json.dumps(evidence,ensure_ascii=False)))
    return {'reservationId':attempt['id'],**evidence}


def update(conn, attempt):
    schema(conn)
    state=attempt.get('status','unknown')
    if state=='recorded':state=attempt.get('providerJob',{}).get('status','recorded')
    conn.execute('UPDATE image_quota_requests SET state=?, external_id=COALESCE(?,external_id) WHERE id=?',
                 (state,attempt.get('externalId'),attempt['id']))


def status(conn):
    schema(conn)
    fields=('reservationId','productId','day','state','externalId')
    return [dict(zip(fields,row)) for row in conn.execute(
        'SELECT id,product_id,day,state,external_id FROM image_quota_requests ORDER BY rowid DESC')]
