import json
import sqlite3
from pathlib import Path
import visual_studio
import studio_bridge
root=Path('data/batch-20261030')
with sqlite3.connect('data/studio.sqlite3') as db:
    state=json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
report=[]
for path in sorted(root.glob('supplier-*.json')):
    asin=path.stem.removeprefix('supplier-');pid='IMP-US-'+asin
    p=next((p for p in state['products'] if p['id']==pid),{})
    runs=visual_studio.list_projects(pid)['runs']
    report.append({'asin':asin,'name':p.get('name'),'researchSaved':bool(p.get('competitorResearch',{}).get('US')),
        'listingSaved':bool(state.get('copy',{}).get(pid+'-US',{}).get('title')),
        'imageCount':sum(bool(r.get('image')) for r in runs),
        'aiQcPassed':sum(bool(r.get('qc') and r['qc'][-1].get('pass')) for r in runs),
        'decision':p.get('productionReview',{}).get('batchDecision','pending_verification'),
        'publishReady':p.get('productionReview',{}).get('publishReady',False)})
(root/'progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
for row in report:
    for run in visual_studio.list_projects('IMP-US-'+row['asin'])['runs']:
        if run.get('status') not in ('approved','awaiting_manual'):
            print('REVIEW_HOLD',json.dumps({'id':run['id'],'slot':run['slot'],'status':run['status'],'qc':run.get('qc',[]),'error':run.get('error')},ensure_ascii=True))
with visual_studio.db() as db:
    print('ACTIVE_TASKS',db.execute("SELECT COUNT(*) FROM studio_tasks WHERE json_extract(body,'$.status')='running'").fetchone()[0])
