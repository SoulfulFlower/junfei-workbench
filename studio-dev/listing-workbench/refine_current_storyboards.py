"""Apply evidence corrections before further paid rendering; preserve rejected runs."""
import json
from pathlib import Path
import visual_studio as visual

root = Path('data/batch-20261030')
path = root / 'jewelry-ai-master-plan.json'
p = visual.get_project(json.loads(path.read_text(encoding='utf-8'))['id'])
raw = json.dumps(p, ensure_ascii=False)
for old, new in [('Six-layer cream-colored accordion dividers inside', 'Visible ivory accordion dividers inside'), ('six-layer', 'accordion'), ('Six-layer', 'Accordion')]:
    raw = raw.replace(old, new)
p = json.loads(raw)
for i, image in enumerate(p['uiPlan']['images']):
    if image.get('layout') == 'result_showcase':
        image.update(layout='poster_hero', product_presence='hero')
    image['evidence'] = ('Source photographs show a teal woven pouch with gold-tone zipper and matching tassel.' if i != 1 else 'Supporting source photograph shows the teal pouch open with ivory accordion dividers; exact compartment count is unverified.')
    prompt = visual.compile_prompt(p, i)
    image['render_prompt'] = prompt
    p['plan']['slots'][i].update(evidence=image['evidence'], composition=prompt)
visual.save_project(p)
path.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
print('Jewelry evidence corrected; no renders submitted by this script.')
