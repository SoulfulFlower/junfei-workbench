"""Recoverable candidate intake; never refreshes/restarts existing tasks."""
import json
from contextlib import closing
import agent_center as agent
import market_research


def validate(user, report_id, asins, profile_id):
    profile = next((p for p in agent.profiles(user) if p['id'] == profile_id), None)
    if not profile:
        raise ValueError('请先选择本账号已保存的店铺档案')
    report = market_research.get(report_id)
    if report['status'] == 'running':
        raise ValueError('调研尚在运行，请结束后再加入任务')
    if not isinstance(asins, list) or not 1 <= len(asins) <= 30 or any(not isinstance(a, str) for a in asins):
        raise ValueError('请勾选1–30个候选')
    by = {c['asin']: c for c in report['candidates']}
    if any(a not in by for a in asins):
        raise ValueError('候选不属于当前账号的调研记录')
    candidates = [by[a] for a in dict.fromkeys(asins)]
    if any(c['market'] != profile['marketplace'] for c in candidates):
        raise ValueError('候选站点与店铺档案不一致，请选择对应站点店铺')
    return profile, candidates


def enqueue(user, profile, report_id, candidates):
    """Import commits first. Each task commits independently, so retry recovers partial work.

    Reuse *all* prior tasks for product/profile, including blocked/uncertain/done.
    Only brand-new tasks start automatically. An interrupted queued task stays available
    in the task center for explicit resume, never becomes an implicit retry.
    """
    outcomes = []
    for candidate in candidates:
        pid = 'IMP-' + candidate['market'] + '-' + candidate['asin']
        outcome = {'asin': candidate['asin'], 'productId': pid}
        try:
            with agent.LOCK:
                workspace = agent.load_workspace()
                product = next((p for p in workspace.get('products', []) if p['id'] == pid), None)
                if not product:
                    outcomes.append(dict(outcome, status='skipped', reason='产品已删除或未入库，不创建任务'))
                    continue
                reference = product.get('selectionResearch', {}).get('reference', {})
                if reference.get('asin') != candidate['asin'] or reference.get('market') != profile['marketplace']:
                    raise ValueError('现有产品的候选身份不一致，未覆盖、未创建任务')
                with closing(agent.connect()) as c:
                    prior = [json.loads(row[0]) for row in c.execute(
                        'SELECT body FROM tasks WHERE user_id=? ORDER BY created DESC', (user,))]
                existing = next((t for t in prior if t['productId'] == pid and t['profile']['id'] == profile['id']), None)
                if existing:
                    outcomes.append(dict(outcome, status='reused', task=agent.public(existing)))
                    continue
                task = agent.create(user, {
                    'goal': '核验选品候选；证据通过后按店铺档案继续资料检查、导出与草稿准备。缺项阻断，不自动付费。',
                    'profileId': profile['id'], 'productId': pid, 'taskMode': 'production',
                    'autoResearch': False, 'autoListing': False, 'aiPlanning': False,
                }, intake={'source': 'selection-report', 'reportId': report_id, 'asin': candidate['asin']})
            outcome.update(status='created', task=task)
            try:
                outcome['task'] = agent.start(user, task['id'])
            except Exception:
                # The durable task is the recovery anchor even when dispatch failed.
                outcome['reason'] = '任务已保存但启动未确认；请在任务中心核对，不自动重启'
        except ValueError as exc:
            outcome.update(status='error', reason=str(exc))
        except Exception:
            outcome.update(status='error', reason='任务接入异常；入库结果保留，请核对任务中心后重试接入')
        outcomes.append(outcome)
    return outcomes
