"""Single, recorded targeted repairs; never resubmit an existing repair."""
import json
from pathlib import Path
import visual_studio as visual

ROOT = Path('data/batch-20261030')
FIXES = {
    'mesh': {
        1: 'Single open white pouch at an uncluttered adult bathroom vanity, no people. Preserve low front pocket and all WHITE internal bands exactly as reference; no gray or lavender fabric. One plain generic brush beside it, no contents obscuring construction.',
        2: 'Single OPEN white pouch, entire product visible with zipper opening and actual retaining bands clearly shown, normal close product photograph. No inset, no invented compartments, no closed pouch.',
        3: 'Single white pouch beside a plain open travel bag. No toothbrush, cosmetic packages or small accessories. Preserve realistic zipper and exact actual construction. Simple coherent photograph, no inset or collage.'},
    'elastic': {
        0: 'Pure white main photograph showing only the actual printed fitted cover on a minimally implied thin square support. No visible table legs, furniture, props, text or inset. Preserve exact reference print.',
        1: 'One actual printed square tabletop cover fitted flat over a thin normal tabletop. Elastic gathered hem only under the edge, no deep box sides or bunched corners. No people or hands. Quiet dining-room context, no accessories touching the product.',
        3: 'One coherent overhead photograph of the actual printed tabletop cover. No inset panels, utensils, cups, mugs, hands or dishes. Exact reference print dominates the composition; restrained surrounding room context only.'},
    'cover': {
        1: 'Single grounded patio photograph of one actual black rectangular cover. One physically coherent scene, no panels or collage, no visible furniture legs. Uniform daylight from one direction and realistic ground contact shadow.',
        3: 'Single quiet patio storage scene with one actual black rectangular cover shown whole, preserving drape and hem. No inset, no collage, no alternate angles in panels. Consistent daylight and contact shadows.'}}

def main():
    log = ROOT / 'targeted-repairs-2.json'
    records = json.loads(log.read_text(encoding='utf-8')) if log.exists() else []
    for name, slots in FIXES.items():
        path = ROOT / (name + '-ai-master-plan.json')
        p = visual.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
        for slot, direction in slots.items():
            if any(r['name'] == name and r['slot'] == slot for r in records):
                continue
            runs = [r for r in visual.list_projects(p['productId'])['runs'] if r['projectId'] == p['id'] and r['slot'] == slot]
            if not runs or runs[0]['status'] != 'needs_revision':
                continue
            image = p['uiPlan']['images'][slot]
            image.update(layout='poster_hero', product_presence='hero', scene=direction,
                         visual_concept=direction, camera_direction=direction)
            image['render_prompt'] = visual.compile_prompt(p, slot)
            p['plan']['slots'][slot]['composition'] = image['render_prompt']
            p['set_qa'] = None
            visual.save_project(p)
            path.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
            record = {'name':name, 'slot':slot, 'previousRun':runs[0]['id'], 'direction':direction, 'status':'submitting'}
            records.append(record)
            log.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            run = visual.generate({'id':p['id'], 'slot':slot, 'model':'gpt-image-2', 'size':'1:1', 'resolution':'2K', 'autoRepair':False})
            record.update(runId=run['id'], status=run['status'])
            log.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            print(name, slot + 1, run['id'], run['status'], flush=True)

if __name__ == '__main__':
    main()
