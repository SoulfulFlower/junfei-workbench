"""Retry failed visual reviews with JPEG transport; never render new artwork."""
import base64
import io
import json
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageOps
import visual_studio as visual

def jpeg(data):
    image = Image.open(io.BytesIO(data)).convert('RGB')
    image = ImageOps.contain(image, (2000, 2000))
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=94)
    return 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode()

original = visual.encode_reference
def reference(ref):
    return jpeg(base64.b64decode(original(ref).split(',', 1)[1]))

for run in visual.list_projects('IMP-US-B0D2DS6JT6')['runs']:
    if run.get('status') != 'review_error' or not run.get('image', '').startswith('local:'):
        continue
    print('REVIEW_EXISTING', run['id'], flush=True)
    try:
        raw = (Path('data/studio-results') / (run['id'] + '.image')).read_bytes()
        with patch.object(visual, 'encode_reference', reference):
            qc = visual.review(visual.get_project(run['projectId']), run['slot'], jpeg(raw), source_layout=True)
        run.setdefault('qc', []).append(qc)
        run['status'] = 'awaiting_manual' if qc['pass'] else 'needs_revision'
        run.pop('error', None)
        run['reviewTransport'] = 'jpeg; original artwork preserved'
        visual.save_run(run)
        print('REVIEW_RESULT', run['slot'], qc['pass'], json.dumps(qc['issues'], ensure_ascii=False), flush=True)
    except Exception as error:
        print('REVIEW_FAILED', type(error).__name__, str(error)[:180], flush=True)
