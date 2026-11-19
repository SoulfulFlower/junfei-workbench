"""Derive truthful batch progress from current master runs, never old variants."""
import json
from pathlib import Path
import visual_studio as visual
import colour_sets

root=Path('data/batch-20261030')
report={'batchComplete':False,'targetProducts':10,'masters':[]}
for path in sorted(root.glob('*-ai-master-plan.json')):
    p=visual.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
    latest={}
    for r in visual.list_projects(p['productId'])['runs']:
        if r['projectId']==p['id']:latest.setdefault(r['slot'],r)
    variants=[s for s in colour_sets.list_sets(p['productId'])['sets'] if s.get('masterId')==p['id']]
    report['masters'].append({'name':path.name.removesuffix('-ai-master-plan.json'),'productId':p['productId'],'projectId':p['id'],'passedImages':sum(r['status'] in ('approved','awaiting_manual') for r in latest.values()),'totalImages':len(p['plan']['slots']),'setQA':p.get('set_qa'),'humanApproved':False,'variantsComplete':False,'localRecolorCandidates':sum(s.get('model')=='local-pixel' for s in variants),'needsRevisionSlots':[i+1 for i,r in latest.items() if r['status']=='needs_revision']})
    path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
    if (p.get('set_qa') or {}).get('ready'):
        (root/('ai-master-'+path.name.removesuffix('-ai-master-plan.json'))/'needs-review.json').unlink(missing_ok=True)
(root/'ai-master-progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'masters':len(report['masters']),'passedImages':sum(p['passedImages'] for p in report['masters']),'setsQAReady':sum(bool((p['setQA'] or {}).get('ready')) for p in report['masters']),'localRecolorCandidates':sum(p['localRecolorCandidates'] for p in report['masters'])}))
