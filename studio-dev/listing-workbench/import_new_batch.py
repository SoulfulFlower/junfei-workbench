"""Import observed supplier evidence without turning unresolved checks into approvals."""
import json
import sqlite3
import time
from pathlib import Path
import importer
import market_research

ROOT = Path('data/batch-20261030')
NAMES = {'B0D2DS6JT6': '涤纶蕾丝桌布', 'B0FFBN1SC4': '方形松紧印花桌布',
    'B0FM84PDWY': '蕾丝拼接罩衫', 'B0G6LGTCTS': '格纹蝴蝶结肩包',
    'B0GVBF7FQD': '印花托特包', 'B0HGFGJW9Q': '拉链首饰收纳袋',
    'B0HH6LTTHZ': 'EVA洗漱收纳袋', 'B0HJH859M9': '磁扣夹子收纳包',
    'B0DPRTMHSS': '方形户外家具桌罩', 'B0HKM1TPZ1': '格纹蝴蝶结布艺收纳篮'}
pool = {}
for path in ROOT.glob('pool-*.json'):
    for row in market_research.rows(json.loads(path.read_text(encoding='utf-8'))):
        if row.get('asin'):
            pool[row['asin']] = market_research.candidate(row, 'US')

with sqlite3.connect('data/studio.sqlite3', timeout=30) as connection:
    connection.execute('BEGIN IMMEDIATE')
    revision, body = connection.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
    (ROOT / ('workspace-before-import-' + str(revision) + '.json')).write_text(body, encoding='utf-8')
    state = json.loads(body)
    changed = []
    for path in sorted(ROOT.glob('supplier-*.json')):
        if path.stem.startswith('supplier-candidate-'):
            continue
        evidence = json.loads(path.read_text(encoding='utf-8'))
        asin = evidence.get('asin') or evidence['referenceAsin']
        pid = 'IMP-US-' + asin
        if any(x.get('product', {}).get('id') == pid for x in state.get('deletedProducts', [])):
            continue
        existing = next((x for x in state['products'] if x['id'] == pid), None)
        if existing is None:
            attrs = evidence.get('attributes', {})
            mapped = {'材质': evidence.get('material') or attrs.get('material', ''),
                '颜色': ','.join(evidence.get('colors', [])) or attrs.get('color', '') or ','.join(attrs.get('colors', [])),
                '尺码': ','.join(evidence.get('sizes', [])),
                '供应商品牌声明': evidence.get('brandDeclaration') or attrs.get('brand', ''),
                '资料核实状态': '待核实，未完成侵权和发布审核'}
            importer.merge_browser_capture(state, {'url': evidence.get('sourceUrl') or evidence['url'],
                'title': evidence.get('title') or NAMES[asin] + ' 供应商搜图候选',
                'attributes': mapped, 'images': evidence.get('referenceImages') or evidence.get('images', []),
                'asin': asin, 'market': 'US', 'capturedAt': '2026-10-30'})
            existing = next(x for x in state['products'] if x['id'] == pid)
            existing.update(name=NAMES[asin], cat='服装' if asin == 'B0FM84PDWY' else '日用百货',
                brand='', manufacturer='', status='待补资料')
            existing['selectionResearch'] = {'sourceMonth': '202609', 'reference': pool.get(asin), 'batch': '20261030'}
        existing['supplierVerification'] = evidence
        existing['productionReview'] = {'publishReady': False, 'remainingIssue': '；'.join(
            evidence.get('holds') or evidence.get('notes') or ['待完成货源、知识产权、运费和变体图片核实'])}
        keywords = ROOT / ('keywords-' + asin + '.json')
        if keywords.exists():
            existing.setdefault('competitorResearch', {})['US'] = json.loads(keywords.read_text(encoding='utf-8'))
        changed.append(pid)
    connection.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',
        (revision + 1, json.dumps(state, ensure_ascii=False)))
    connection.commit()
print(json.dumps({'synced': changed, 'publishReady': 0}, ensure_ascii=True))
