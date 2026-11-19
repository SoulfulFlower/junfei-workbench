"""从已上传图库为单颜色变体配图。图库顺序须由大脑视觉核对后传入。"""
from pathlib import Path
import json
import sys
from library_fill import action


def assign_variant(sku, main_index, count):
    action({'action':'click','target':{'role':'cell','name':'加载失败 ','scope':{'role':'row','name':sku,'exact':False}}})
    dialog = {'role':'dialog','name':'选择图片'}
    for index in [main_index, *[i for i in range(count) if i != main_index]]:
        # 点击真实图标；末行单元格可能横跨空列，点单元格中心会落空。
        action({'action':'click','target':{'css':'i','scope':{'role':'cell','name':'','index':index,'scope':dialog}}})
    observed = action({'action':'snapshot'})['snapshot'].split('- dialog "选择图片":')[-1]
    if observed.count('- cell ""') != count:
        raise ValueError('变体图片数量不符，等待大脑检查，不保存')
    action({'action':'click','target':{'role':'button','name':'保存','scope':dialog}})
    print('已配图：' + sku, flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    product = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))[0]
    for variant in product['variants'][int(sys.argv[2]):]:
        assign_variant(variant['sku'], int(sys.argv[3]), 1 + len(variant['images']))
