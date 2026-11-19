import json,sys
from pathlib import Path
import visual_studio as v
import produce_evidence_master as p
r=json.loads(Path('data/batch-20261030/mesh-analysis-response.json').read_text(encoding='utf-8'))
t=r['choices'][0]['message']['content'].strip()
if t.startswith('```'):t=t.split('\n',1)[1].rsplit('```',1)[0].strip()
profile=json.loads(t)
original=v.model_json
used=False
def cached(instruction,context,images):
 global used
 if images and not used:
  used=True
  return profile
 return original(instruction,context,images)
v.model_json=cached
sys.argv=['produce_evidence_master.py','mesh']
p.main()
