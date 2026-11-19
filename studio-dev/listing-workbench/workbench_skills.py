"""Catalog of the skills connected to this workbench and its CLI workflow."""
import os
from pathlib import Path

import creative_skills
import listing_skills


# id, name, input, output, editable rule set, focused rule
BUILTIN_SKILLS = {
    '产品研究': (
        ('sourcing', '货源核验', '候选 ASIN、供应商页面和规格', '同款货源、规格和成本依据', None, None),
        ('competitor', '竞品分析', '当前站点的竞品 ASIN', '竞品资料及证据', None, None),
        ('keywords', '关键词挖掘', '竞品 ASIN、种子词和卖家精灵数据', '反查与拓展关键词及指标', None, None),
        ('reviews', '评论洞察', '竞品 ASIN 和真实评论', '买家问题、需求和使用场景', None, None),
    ),
    'Listing 与套图': (
        ('listing', 'Listing 生成', '已核实商品资料和站点关键词', '当前站点 Listing 草稿', 'listing', 'evidence'),
        ('listing-optimize', 'Listing 优化', '当前文案、商品事实和已选词', '改写后的 Listing 字段', 'listing', 'conversion'),
        ('listing-style', '文案去模板化', '待润色的五点与关键词命中记录', '更自然且保留事实的买家文案', None, None),
        ('storyboard', '图片策划', '实拍素材、Listing 和商品事实', '待确认分镜与实拍依据', 'images', 'planning'),
        ('image', '图片生成', '已确认分镜、商品实拍和图片模型', '按图位生成的成图', 'images', 'apparel'),
        ('image-colors', '变体换色', '母版套图和同款颜色参考', '各颜色的对应图位', None, None),
        ('image-qc', '图片质检', '成图、商品实拍和分镜', '单图或整套检查结果', 'images', 'quality'),
    ),
    '交付': (
        ('erp', '钧飞 ERP 交接', '审核后的文案、成图和 SKU', '交接资料及已有任务回执', None, None),
    ),
}

CODEX_SKILLS = (
    ('amazon-full-pipeline', '亚马逊全流程总控', '目标站点、账号和任务范围', '阶段台账、交付记录与待确认项'),
    ('cyclic-product-discovery', '循环选品', '关键词、标题首句或卖家店铺', '选品来源、排名证据与竞品 ASIN'),
)


def catalog():
    versions = {'listing': listing_skills.current()['version'], 'images': creative_skills.current()['version']}
    codex_home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    groups = [{
        'label': 'Codex 工作流',
        'skills': [
            {'id': key, 'name': name, 'input': inputs, 'output': outputs, 'mode': 'codex',
             'installed': (codex_home / 'skills' / key / 'SKILL.md').is_file(), 'invocation': '$' + key}
            for key, name, inputs, outputs in CODEX_SKILLS
        ],
    }]
    for group, skills in BUILTIN_SKILLS.items():
        groups.append({'label': group, 'skills': [
            {'id': key, 'name': name, 'input': inputs, 'output': outputs,
             'mode': 'editable' if editor else 'builtin', 'editor': editor, 'rule': rule,
             'version': versions.get(editor), 'route': 'agent' if group == '交付' else 'products'}
            for key, name, inputs, outputs, editor, rule in skills
        ]})
    return {'groups': groups}
