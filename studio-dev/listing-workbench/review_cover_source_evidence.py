"""Correct an AI plan's unsupported corner-toggle requirement from source evidence."""
import json,time,base64
from pathlib import Path
import visual_studio as v,studio_bridge as b
root=Path('data/batch-20261030');p=v.get_project(json.loads((root/'cover-ai-master-plan.json').read_text(encoding='utf-8'))['id'])
r=v.get_run('22ded70bdae3450bb0531578e05be385')
if not any(q.get('sourceEvidenceRecheck') for q in r['qc']):
 p['plan']['identity']='Plain matte black soft Oxford-cloth cover with a flat square top, vertical seams and long hanging sides. Source photograph visibly shows furniture feet below the cover and a lower tie/toggle near the middle of the long front hem, not confined to a corner. No vents, coating or buckles are proven.'
 direction='Exact black soft square furniture cover on a restrained patio. Implied covered furniture may have feet visible below the hem, as in the actual supplier photo. Preserve a lower tie near the center/front hem as shown in the source, not a fabricated mandatory corner position. No performance claims or exposed hidden interiors.'
 p['uiPlan']['images'][1].update(scene=direction,visual_concept=direction,camera_direction=direction)
 p['plan']['slots'][1]['evidence']='Actual first supplier photo shows exposed furniture feet and a lower tie at the center of the long front hem. The earlier corner-only constraint was an AI planning error.'
 p.setdefault('operatorReview',[]).append({'slot':1,'reason':'Directly inspected source photograph: visible feet and center/front tie match source. Correct plan hallucination; independently recheck all remaining identity defects.','at':time.time()})
 p['plan']['slots'][1]['composition']=v.compile_prompt(p,1);p['set_qa']=None;v.save_project(p)
 raw,mime=b.result_image(r['id']);qc=v.review(p,1,'data:'+mime+';base64,'+base64.b64encode(raw).decode());qc['sourceEvidenceRecheck']=True;r['qc'].append(qc);r['status']='awaiting_manual' if qc['pass'] else 'needs_revision';v.save_run(r)
 print(r['status'],json.dumps(qc,ensure_ascii=False),flush=True)
