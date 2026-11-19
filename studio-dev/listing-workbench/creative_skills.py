import app_paths
"""Versioned application skills, snapshotted into each image plan."""
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

DB = app_paths.DATA / 'creative_skills.sqlite3'
DEFAULTS = {
    'planning': '先整理可确认的产品事实和缺失资料。每张图回答一个不同的买家问题，写明事实依据、背景、主体角度与位置、图上准确短文案、标注位置和禁止事项。整套图统一配色、光线、字体，但不要重复构图。参考图里的宣传文字不作为事实依据。缺少尺寸、包装清单、性能证明时不编造，改为有证据的细节展示，并列出待补资料。英文图片文字每行尽量不超过7词，优先手机端可读性。主图与副图按当前类目和站点要求区分，不把某个品类的布局当通用模板。',
    'apparel': '服装套图围绕款式轮廓、真实穿着、面料近景、口袋/拉链/缝线、已确认尺码和有依据的颜色展开。面料成分来自确认资料，保暖、防水等性能不能从外观推断。保持同款同色、版型、衣长、口袋和拉链结构。内领标位于后领内侧，穿着被遮挡时不展示；胸前和袖上标志保持原位置，禁止转移到人体皮肤。没有背面参考图不编造背面设计，没有尺码表不生成虚构数字。不要把搭配服饰当包装包含物。',
    'household': '日用百货套图围绕真实结构、实际用途、使用场景、细节、已确认尺寸和包装数量展开。明确产品与手、台面和环境的接触关系，禁止悬浮和错误比例。没有尺寸依据不凭图片估算比例；没有测试证明不宣称承重、防水、食品接触安全、抗菌等性能。配件和数量严格依据产品资料，缺少包装资料时改为产品细节展示。',
    'quality': '逐张对照原始主体图检查款式、颜色、结构、数量和商标位置；检查人体与产品接触、穿着遮挡和自然比例；核对图片文字拼写、重复、裁切和可读性；所有尺寸、性能、包装内容须有依据。区分真实产品标记和后加图片文案。商标转移到皮肤、改款、伪造尺寸或配件均判为不通过。无法看清的内容标记人工复核，不能当作已验证通过。'
}

def connection(db_path=None):
    c = sqlite3.connect(db_path or DB, timeout=20)
    c.execute('CREATE TABLE IF NOT EXISTS versions (version INTEGER PRIMARY KEY, body TEXT NOT NULL, created REAL NOT NULL)')
    c.commit()
    return c

def current(defaults=None, db_path=None):
    with closing(connection(db_path)) as c:
        row = c.execute('SELECT version,body FROM versions ORDER BY version DESC LIMIT 1').fetchone()
    return {'version': row[0], 'rules': json.loads(row[1])} if row else {'version': 0, 'rules': dict(defaults or DEFAULTS)}

def save(data, defaults=None, db_path=None):
    rules = data.get('rules')
    if not isinstance(rules,dict) or set(rules) != set(defaults or DEFAULTS):
        raise ValueError('技能字段不完整')
    if any(not isinstance(v,str) or not v.strip() or len(v)>6000 for v in rules.values()):
        raise ValueError('每项技能需填写1–6000字符')
    rules = {k:v.strip() for k,v in rules.items()}
    with closing(connection(db_path)) as c, c:
        c.execute('BEGIN IMMEDIATE')
        latest = c.execute('SELECT COALESCE(MAX(version),0) FROM versions').fetchone()[0]
        if type(data.get('version')) is not int or data['version'] != latest:
            raise ValueError('技能已被其他管理员更新，请重新打开后编辑')
        c.execute('INSERT INTO versions VALUES (?,?,?)',(latest+1,json.dumps(rules,ensure_ascii=False),time.time()))
    return {'version':latest+1,'rules':rules}

def select(product):
    import re
    text=' '.join(str(product.get(k,'')) for k in ('name','cat','style'))
    category='apparel' if re.search(r'服装|夹克|外套|卫衣|衬衫|开衫|针织衫|毛衣|裙|裤|jacket|coat|hoodie|shirt|cardigan|sweater|dress|trousers|apparel',text,re.I) else 'household'
    return {**current(),'category':category}

def instruction(snapshot,stage):
    rules=snapshot['rules']
    keys=('planning',snapshot['category']) if stage=='plan' else (('quality',snapshot['category']) if stage=='quality' else (snapshot['category'],))
    return '\n[APPLICATION SKILLS v'+str(snapshot['version'])+']\n'+'\n'.join(rules[k] for k in keys)+'\n[/APPLICATION SKILLS]\n'
