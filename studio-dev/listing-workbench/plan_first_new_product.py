import json
import sqlite3
import sys
from pathlib import Path
import visual_studio
ROOT=Path('data/batch-20261030')
asin='B0D2DS6JT6'
with sqlite3.connect('data/studio.sqlite3',timeout=30) as db:
    db.execute('BEGIN IMMEDIATE')
    revision,body=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
    state=json.loads(body)
    product=next(p for p in state['products'] if p['id']=='IMP-US-'+asin)
    copy=state['copy'][product['id']+'-US']
    copy=copy.get('copy',copy)
    # The supplier offers both square and rectangular sizes: do not call all six rectangular.
    copy['title']='White Polyester Lace Tablecloth, Square and Rectangle Sizes'
    copy['highlights']='Polyester lace table cover in six square and rectangular sizes, from 60x60cm to 140x220cm'
    for key in ('bullets','description'):
        copy[key]=copy[key].replace('This rectangle tablecloth','This lace tablecloth').replace('This rectangular tablecloth','This lace tablecloth').replace('polyester lace rectangle tablecloth','polyester lace tablecloth').replace('White Lace Rectangle Tablecloth','White Lace Tablecloth').replace('Shape: Rectangle','Shape: Square or rectangle, depending on selected size')
    copy.setdefault('translations',{})['title']='白色涤纶蕾丝桌布，多种方形及长方形尺寸'
    state['copy'][product['id']+'-US']=copy
    (ROOT/('listing-'+asin+'.json')).write_text(json.dumps({'copy':copy},ensure_ascii=False,indent=2),encoding='utf-8')
    db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(state,ensure_ascii=False)))
facts=json.loads((ROOT/('supplier-'+asin+'.json')).read_text(encoding='utf-8'))
target=ROOT/('plan-'+asin+'.json')
if not target.exists() and ('--verify-new-vision' in sys.argv or not (ROOT/'visual-service-unavailable.json').exists()):
    plan=visual_studio.plan({'references':facts['referenceImages'][:1],'count':5,'deliverable':'gallery','language':'en',
        'brief':'展示真实白色花边蕾丝桌布。不同尺寸有方形和长方形，图片不得暗示所有尺寸同一形状。先检查源图，保留花纹，不重新设计。每张回答不同购买问题：花边纹样、透视铺桌效果、尺寸选择、聚酯成分。图中桌子餐具花瓶不包含。优先source_layout，无法支撑的视角标记blocked。不要用无法核实的柔软、易洗、防水或性能卖点。'},product,copy)
    target.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PLAN_SAVED',plan['id'],flush=True)
