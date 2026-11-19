"""Read current account production failures for archive status; never recover jobs.

The CLI pipeline is a separate historical ledger. It is deliberately not rewritten
or used to infer publication, quality approval, or a request that can be retried.
"""
import json
import sqlite3
from contextlib import closing


VISUAL_ACTIVE = {'submitting', 'generating', 'reviewing', 'repairing'}
VISUAL_BLOCKED = {'needs_revision', 'failed', 'review_error', 'submit_unknown', 'interrupted'}
COLOUR_ACTIVE = {'queued', 'validating', 'generating', 'reviewing', 'local_preparing', 'local_rendering'}


def rows(root, filename, table, columns, where='', values=()):
    path = root / filename
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return []
        return conn.execute(f'SELECT {columns} FROM {table} {where}', values).fetchall()


def summary(root, owner):
    workspace = rows(root, 'studio.sqlite3', 'workspace', 'body', 'WHERE id=1')
    state = json.loads(workspace[0][0]) if workspace else {}
    products = {p['id']: p for p in state.get('products', [])}
    result = {pid: {'productId': pid, 'parentSku': p.get('sku', ''), 'needsAttention': False,
                    'running': False, 'reasons': []} for pid, p in products.items()}

    def add(pid, stage, code, message, **details):
        if pid in result:
            result[pid]['needsAttention'] = True
            result[pid]['reasons'].append({'stage': stage, 'code': code, 'message': message, **details})

    # Match studio_bridge.get_view: newest project per deliverable, and latest
    # updated run per slot. A newer plan or retry retires old failures.
    projects = rows(root, 'visual_studio.sqlite3', 'projects',
                    "id,product_id,COALESCE(json_extract(body,'$.deliverable'),'gallery')",
                    'ORDER BY created DESC,id DESC')
    current = {}
    for project_id, pid, kind in projects:
        if pid in products:
            current.setdefault((pid, kind), project_id)
    project_owner = {project_id: pid for (pid, _), project_id in current.items()}
    seen = set()
    for run_id, project_id, pid, slot, status in rows(root, 'visual_studio.sqlite3', 'runs',
            "id,project_id,json_extract(body,'$.productId'),json_extract(body,'$.slot'),json_extract(body,'$.status')",
            'ORDER BY updated DESC,id DESC'):
        if pid in result and status in VISUAL_ACTIVE:
            # Superseded in-flight operations still exist and must finish.
            result[pid]['running'] = True
        key = (project_id, slot)
        if project_owner.get(project_id) != pid or key in seen:
            continue
        seen.add(key)
        if status in VISUAL_BLOCKED:
            message = ('图片提交结果待核对，请查询原任务回执' if status == 'submit_unknown' else
                       '图片自动检查未通过，请查看对应图位' if status == 'needs_revision' else
                       '图片任务需处理，请查看原任务记录')
            add(pid, 'images', status, message, slot=slot, taskId=run_id)

    # Colour sets have their own frozen master identity. Reuse the same read-only
    # selection as the home/task list, without current_sets()'s binding writes.
    from workbench_image_tasks import snapshot
    for job in snapshot(root, products):
        pid, status = job['productId'], job['status']
        if status in COLOUR_ACTIVE:
            result[pid]['running'] = True
        elif status in {'needs_attention', 'failed', 'local_paused'}:
            add(pid, 'colours', status, '变体换色需处理，请查看原套图任务', taskId=job['id'])

    # Only current-account, current-product tasks are returned. Latest per market
    # is enough for display; recovering or retrying remains the owning module's job.
    seen = set()
    for body, in rows(root, 'studio.sqlite3', 'listing_generation_jobs', 'body',
                     'WHERE owner=? ORDER BY created DESC,id DESC', (owner,)):
        job = json.loads(body)
        pid, market = job.get('productId'), job.get('market')
        product = products.get(pid)
        if not product or market != ((product.get('sourceImport') or {}).get('market') or product.get('market') or 'US'):
            continue
        if (pid, market) in seen:
            continue
        seen.add((pid, market))
        if job.get('status') in {'queued', 'running'}:
            result[pid]['running'] = True
        elif job.get('status') in {'ready', 'needs_review', 'failed'}:
            add(pid, 'listing', job['status'], '文案任务需核对或恢复，请查看原完成稿', taskId=job['id'])

    for filename, stage in [('erp-collection/jobs.sqlite3', 'erp'), ('publication-flow/jobs.sqlite3', 'publication')]:
        seen = set()
        for body, in rows(root, filename, 'jobs', 'body',
                         "WHERE account_id=? ORDER BY json_extract(body,'$.createdAt') DESC,id DESC", (owner,)):
            job = json.loads(body)
            pid = job.get('productId')
            if pid not in result or pid in seen or job.get('parentSku') not in (None, products[pid].get('sku')):
                continue
            seen.add(pid)
            if job.get('status') in {'queued', 'running'}:
                result[pid]['running'] = True
            elif job.get('status') in {'needs_reconciliation', 'failed', 'blocked'}:
                add(pid, stage, job['status'], 'ERP任务需核对原回执，请勿重复提交', taskId=job['id'])
    return {'products': list(result.values())}
