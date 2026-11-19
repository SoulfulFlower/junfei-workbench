"""Plan only selected sourced products, with no image-render submissions."""
import json
import sqlite3
import sys
from pathlib import Path
import visual_studio
ROOT=Path('data/batch-20261030')
for asin in sys.argv[1:]:
    target=ROOT/('plan-'+asin+'.json')
    if target.exists():
        print('EXISTING_PLAN',asin,flush=True);continue
    evidence=json.loads((ROOT/('supplier-'+asin+'.json')).read_text(encoding='utf-8'))
    refs=evidence.get('referenceImages') or evidence.get('images') or []
    with sqlite3.connect('data/studio.sqlite3') as db:
        state=json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
    product=next(p for p in state['products'] if p['id']=='IMP-US-'+asin)
    listing=state.get('copy',{}).get(product['id']+'-US')
    if not refs or not listing:
        print('MISSING_INPUT',asin,flush=True);continue
    print('PLAN',asin,flush=True)
    try:
        plan=visual_studio.plan({'references':refs[:2],'count':5,'deliverable':'gallery','language':'en',
            'brief':'先分析实物，再按买家购买问题策划5张图。每张一个有依据的卖点。优先真实素材排版，不虚构视角、结构、尺寸、用途、性能、包装数量。主图只显示实际出售物；缺独立实物图则明确标记blocked。不同格纹和图案只用各自实拍图，禁止把换色冒充换花型。品牌授权、专利、包装缺口属于内部问题，不写在图片上。当前只策划，禁止提交生图。'},product,listing)
        target.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PLAN_SAVED',asin,plan['id'],flush=True)
    except Exception as error:
        print('PLAN_FAILED',asin,type(error).__name__,str(error)[:160],flush=True)
