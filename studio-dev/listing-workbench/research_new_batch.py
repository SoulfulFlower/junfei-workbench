"""Resume-safe keyword evidence collection for the local candidate batch."""
import json
from pathlib import Path
import competitors

OUT = Path('data/batch-20261030')
for path in sorted(OUT.glob('supplier-*.json')):
    if path.stem.startswith('supplier-candidate-'):
        continue
    facts = json.loads(path.read_text(encoding='utf-8'))
    asin = facts.get('asin') or facts.get('referenceAsin') or path.stem.removeprefix('supplier-')
    target = OUT / ('keywords-' + asin + '.json')
    if target.exists():
        continue
    print('RESEARCH', asin, flush=True)
    try:
        result = competitors.analyse({'market': 'US', 'asins': asin,
            'source': 'sellersprite', 'mineKeywords': True, 'facts': facts})
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('SAVED', asin, 'keywords', len(result.get('keywords', [])), flush=True)
    except Exception as error:
        print('FAILED', asin, type(error).__name__, flush=True)
