"""Read account-owned colour jobs without starting workers or model calls."""
import json
import sqlite3
from contextlib import closing


ACTIVE={'queued','validating','generating','reviewing','local_preparing','local_rendering'}
LABELS={'queued':'待开始','validating':'核对参考图','generating':'生成中','reviewing':'AI质检中',
        'local_preparing':'本地换色准备中','local_rendering':'本地换色中','local_paused':'本地换色已暂停',
        'awaiting_manual':'待人工确认','approved':'已人工确认','needs_attention':'需处理','failed':'失败'}


def bodies(root,filename,table):
    path=root/filename
    if not path.is_file():return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as c:
        if not c.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?',(table,)).fetchone():return []
        # Propagate a damaged ledger, rather than displaying a false empty list.
        has_updated=table=='sets' and any(row[1]=='updated' for row in c.execute('PRAGMA table_info(sets)'))
        result=[]
        for row in c.execute('SELECT body'+(',updated' if has_updated else '')+' FROM '+table):
            value=json.loads(row[0])
            if has_updated:value['_ledgerUpdated']=row[1]
            result.append(value)
        return result


def snapshot(root,products=None):
    if products is None:
        states=bodies(root,'studio.sqlite3','workspace')
        products={p['id']:p for p in (states[0] if states else {}).get('products',[])}
    projects=bodies(root,'visual_studio.sqlite3','projects')
    latest={}
    for p in sorted(projects,key=lambda p:p.get('created',0),reverse=True):
        if p.get('deliverable','gallery')=='gallery':latest.setdefault(p.get('productId') or p.get('product_id'),p['id'])
    # Use exactly the same frozen-selection identity as the generation pipeline.
    from colour_master import selection_id
    masters={pid:selection_id(p) or latest.get(pid) for pid,p in products.items()}
    jobs=[]
    for s in bodies(root,'colour_sets.sqlite3','sets'):
        pid=s.get('productId')
        if pid not in products or masters.get(pid) and s.get('masterId')!=masters[pid]:continue
        items=s.get('items',[]);state=s.get('status','needs_attention');local=s.get('model')=='local-pixel'
        jobs.append({'id':s['id'],'productId':pid,'productName':products[pid].get('name') or pid,
            'color':s.get('color',''),'status':state,'statusLabel':LABELS.get(state,'需核对'),
            'local':local,'completed':sum(i.get('status') in ('approved','awaiting_manual') for i in items),
            'total':len(items),'manual':s.get('manual') is True,'error':s.get('error',''),
            'canPause':local and state in {'local_preparing','local_rendering'},
            'canResume':local and state=='local_paused',
            'updated':max(s.get('_ledgerUpdated',0),s.get('created',0),*(s.get('localTask',{}).get(k,0) for k in ('created','pausedAt','resumedAt','renderCompleted')))})
    return sorted(jobs,key=lambda j:j['updated'],reverse=True)
