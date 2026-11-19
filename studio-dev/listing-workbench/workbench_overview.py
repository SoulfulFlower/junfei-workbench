"""Read the sources used by the account-scoped workbench home."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import discovery_intake
import workbench_image_tasks


SHANGHAI = timezone(timedelta(hours=8))
IMAGE_ACTIVE = {'submitting', 'generating', 'reviewing', 'repairing'}
IMAGE_JOB_ACTIVE = {'pending', 'submitting', 'submitted', 'processing'}


def rows(root, filename, table, columns, where='', values=()):
    path = root / filename
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return []
        return db.execute(f'SELECT {columns} FROM {table} {where}', values).fetchall()


def discoveries_today(events, day):
    observed = set()
    for event in events:
        if event.get('kind') not in {'search', 'store'}:
            continue
        date = datetime.fromisoformat(event['observedAt'].replace('Z', '+00:00')).astimezone(SHANGHAI).date()
        if date == day:
            observed.update((event['marketplace'], item['asin']) for item in event.get('products', []))
    return len(observed)


def current_visual_runs(root, products, visual_runs):
    """Return latest slot results for each product's current deliverable.

    Old projects remain in the ledger, but no longer create current failures
    or review work. Old ledgers without project rows fall back to run times.
    Active work is counted separately, including superseded in-flight runs.
    """
    projects=workbench_image_tasks.bodies(root,'visual_studio.sqlite3','projects')
    latest={}
    for project in sorted(projects,key=lambda p:(p.get('created',0),p.get('id','')),reverse=True):
        pid=project.get('productId') or project.get('product_id')
        if pid in products:
            latest.setdefault((pid,project.get('deliverable','gallery')),project['id'])
    known={pid for pid,_ in latest}
    for _,run in sorted(visual_runs,key=lambda item:item[0],reverse=True):
        pid=run.get('productId')
        if pid in products and pid not in known:
            latest.setdefault((pid,'gallery'),run['projectId'])
    current=set(latest.values())
    slots={}
    for _,run in sorted(visual_runs,key=lambda item:item[0],reverse=True):
        if run.get('productId') in products and run.get('projectId') in current:
            slots.setdefault((run['projectId'],run['slot']),run)
    return list(slots.values())


def overview(root, owner):
    day = datetime.now(SHANGHAI).date()
    workspace = rows(root, 'studio.sqlite3', 'workspace', 'body', 'WHERE id=1')
    state = json.loads(workspace[0][0]) if workspace else {}
    products = {item['id']: item for item in state.get('products', [])}
    events = [json.loads(body) for (body,) in rows(
        root, 'cyclic_discovery.sqlite3', 'discovery_events', 'payload', 'WHERE owner=?', (owner,))]
    tasks = [(created, json.loads(body)) for created, body in rows(
        root, 'agent-center.sqlite3', 'tasks', 'created, body', 'WHERE user_id=?', (owner,))]
    visual_runs = [(updated, json.loads(body)) for updated, body in rows(
        root, 'visual_studio.sqlite3', 'runs', 'updated, body')]
    image_jobs = [json.loads(body) for (body,) in rows(root, 'image_jobs.sqlite3', 'jobs', 'body')]
    cli_tasks = discovery_intake.overview(root, owner)
    colour_jobs = workbench_image_tasks.snapshot(root, products)
    listing_jobs = [json.loads(body) for (body,) in rows(root,'studio.sqlite3',
        'listing_generation_jobs','body','WHERE owner=? ORDER BY updated DESC LIMIT 100',(owner,))]
    erp_jobs = [json.loads(body) for (body,) in rows(root,'erp-collection/jobs.sqlite3',
        'jobs','body','WHERE account_id=?',(owner,))]

    listing_active = {task['productId'] for _, task in tasks
                      if task.get('productId') in products and task.get('status') == 'running'
                      and (task.get('listingAttempt') or {}).get('state') == 'started'}
    listing_active.update(job['productId'] for job in listing_jobs
                          if job.get('productId') in products and job.get('status') in ('queued','running'))
    images_active = {run['productId'] for _, run in visual_runs
                     if run.get('productId') in products and run.get('status') in IMAGE_ACTIVE}
    images_active.update(job['productId'] for job in image_jobs
                         if job.get('productId') in products and job.get('status') in IMAGE_JOB_ACTIVE)
    # Superseded colour sets no longer create current review work, but their
    # in-flight local/remote operations remain real until the worker finishes.
    images_active.update(job['productId'] for job in workbench_image_tasks.bodies(root,'colour_sets.sqlite3','sets')
                         if job.get('productId') in products and job.get('status') in workbench_image_tasks.ACTIVE)
    # Ignore superseded runs when counting current image failures.
    latest_runs = current_visual_runs(root,products,visual_runs)
    pending_listing = 0
    for product_id, product in products.items():
        market = (product.get('sourceImport') or {}).get('market') or product.get('market') or 'US'
        copy = state.get('copy', {}).get(f'{product_id}-{market}') or {}
        pending = (product.get('pendingCopy') or {}).get(market) or {}
        if product_id not in listing_active and not (copy.get('title') or (pending.get('copy') or {}).get('title')):
            pending_listing += 1

    recent = []
    for created, task in tasks:
        product = products.get(task.get('productId')) or (task.get('snapshot') or {}).get('product') or {}
        recent.append({'title': product.get('name') or task.get('title') or f"任务 {task['id'][:8]}",
                       'source': '工作台', 'status': task['status'],
                       'at': task.get('updated') or created or None})
    for task in cli_tasks:
        if task.get('updatedAt'):
            recent.append({'title': products.get(task['productId'], {}).get('name') or task['asin'],
                           'source': 'CLI', 'status': task['status'], 'stage': task['stage'],
                           'at': datetime.fromisoformat(task['updatedAt']).timestamp()})
    recent.extend({'title':job['productName']+' · '+job['color'],
                   'source':'本地换色' if job['local'] else '变体换色', 'stage':'images',
                   'status':job['status'],'at':job['updated'] or None} for job in colour_jobs)
    recent.extend({'title':products.get(job.get('productId'),{}).get('name') or job.get('productId','文案任务'),
        'source':'文案任务','stage':'listing','status':{'applied':'done','ready':'needs_review','needs_review':'uncertain'}.get(job['status'],job['status']),
        'at':job.get('updatedAt') or job.get('createdAt')} for job in listing_jobs)
    recent.extend({'title':products.get(job.get('productId'),{}).get('name') or job.get('productId','ERP采集'),
        'source':'ERP采集','stage':'publish','status':{'verified':'done','needs_reconciliation':'needs_review'}.get(job['status'],job['status']),
        'at':job.get('updatedAt') or job.get('createdAt')} for job in erp_jobs)
    quality_pending={pid for pid,p in products.items() if p.get('status')=='待审核'}
    quality_pending.update(job['productId'] for job in colour_jobs if job['status'] in ('awaiting_manual','needs_attention'))
    quality_pending.update(run['productId'] for run in latest_runs
                           if run.get('status') in ('awaiting_manual','needs_revision','review_error'))
    return {
        'date': day.isoformat(), 'timezone': 'Asia/Shanghai',
        'metrics': {
            'products': len(products), 'discoveredToday': discoveries_today(events, day),
            'listingPending': pending_listing, 'listingRunning': len(listing_active),
            'imagesRunning': len(images_active),
            'qualityPending': len(quality_pending),
            'erpPending': len({job['productId'] for job in erp_jobs if job.get('productId') in products
                               and job.get('status') in ('queued','running','needs_reconciliation')}),
            'failed': sum(task.get('status') == 'failed' for _, task in tasks)
                      + sum(job['status'] in ('needs_attention','failed') for job in colour_jobs)
                      + sum(run.get('status') == 'failed' for run in latest_runs)
                      + sum(job.get('status') == 'failed' and job.get('productId') in products
                            and not job.get('storyboardProjectId') for job in image_jobs),
        },
        'recent': sorted(recent, key=lambda item: item['at'] or 0, reverse=True)[:8],
    }
