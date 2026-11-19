"""按已审核产品计划关联已有行的颜色与尺码；不新增或删除变体。"""
import json
import sys
from pathlib import Path
from library_fill import action


def link(product):
    snapshot = action({'action': 'snapshot'})['snapshot']
    if 'dialog "替换变体主题"' in snapshot:
        raise ValueError('请先检查旧属性下拉；存在可关联值时应映射后确认')
    for variant in product['variants']:
        row = {'role': 'row', 'name': variant['sku'], 'exact': False}
        for col, value in [(4, variant['color']), (5, variant['size'])]:
            action({'action': 'click', 'target': {'css': f'td:nth-child({col}) i.el-icon-edit-outline', 'scope': row}})
            dialog = {'role': 'dialog', 'name': '修改属性值'}
            action({'action': 'fill', 'target': {'role': 'textbox', 'name': '输入属性', 'scope': dialog}, 'value': value})
            action({'action': 'click', 'target': {'role': 'button', 'name': '确 定', 'scope': dialog}})
        observed = action({'action': 'read', 'target': row})['value']
        if variant['color'] not in observed or variant['size'] not in observed:
            raise ValueError('颜色尺码回读不符：' + variant['sku'])
        print('颜色尺码已关联并回读：' + variant['sku'], flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    link(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))[0])
