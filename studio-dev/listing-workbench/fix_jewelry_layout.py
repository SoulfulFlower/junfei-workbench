"""Replace the rejected cropped group photograph with an intact source photograph."""
import json
import time
from pathlib import Path
import product_artwork
import studio_bridge
import visual_studio as visual

path = Path('data/batch-20261030/layout-project-B0HGFGJW9Q.json')
project = json.loads(path.read_text(encoding='utf-8'))
im = project['uiPlan']['images'][4]
im.update(headline='Zipper and Tassel', subline='See the zipper closure and matching fabric tassel.',
          source_reference_indices=[3], production_method='source_layout',
          visual_concept='Preserve the entire supplier photograph, including every tassel. Show the visible closure details; do not claim a close-up.')
project['plan']['slots'][4].update(headline=im['headline'], caption=im['subline'],
    evidence='Inspected supplier photograph 3: complete pouches with visible zipper closures and tassels.')
visual.save_project(project)
path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
product = {'id': project['productId'], 'name': 'Jewelry pouch'}
task = product_artwork.start({'confirmed': True, 'indices': [4]}, product)
print('LOCAL_REPLACEMENT', task['id'], flush=True)
while True:
    job = studio_bridge.get_view(product)['jobs'].get('render_set', {})
    if job.get('status') != 'running':
        print(json.dumps(job, ensure_ascii=False), flush=True)
        break
    time.sleep(3)
