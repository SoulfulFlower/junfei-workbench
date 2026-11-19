"""产品库已打开空白添加表单时填充；保存和发布由大脑另行核验。"""
import json
from pathlib import Path
import sys
from brain_client import send


def action(command):
    result = send(command)
    if result.get('status') != 'done':
        raise RuntimeError(str(result.get('error','动作未完成')) + '；截图：' + str(result.get('screenshot','')))
    return result


def fill_product(product):
    initial = action({'action':'snapshot'})
    snapshot = initial.get('snapshot', '')
    if '- dialog "产品详情"' not in snapshot or 'textbox "placeholder"' in snapshot or product['parentSku'] in snapshot:
        raise ValueError('必须在空白产品详情表单中运行；不会覆盖或重复添加已有变体')
    dialog = {'role':'dialog', 'name':'产品详情'}
    fields = {
        '来源链接':product['sourceUrl'], '品牌':product['brand'],
        '制造商':product['manufacturer'], 'SKU':product['parentSku'],
        '价格':product['variants'][0]['price'],
        '中文名':product.get('chineseName',product['title']), '英文名':product['title'],
        '标题':product['title'], '描述':product['description'], '关键词':product['searchTerms'],
        '备注':'本次计划店铺：' + product['store'] + '；变体价格为USD售价；重量与包装依据本次产品计划。',
    }
    for name, value in fields.items():
        action({'action':'fill', 'target':{'role':'textbox','name':name,'scope':dialog}, 'value':value})
        print('已填写：' + name, flush=True)
    for index, bullet in enumerate(product['bullets']):
        action({'action':'fill','target':{'role':'textbox','name':'五点描述','index':index,'scope':dialog},'value':bullet})
    for index, variant in enumerate(product['variants']):
        action({'action':'click','target':{'role':'button','name':'添加变体','scope':dialog}})
        for column, value in enumerate([variant['sku'], variant['color'], variant['size'], variant['price']]):
            action({'action':'fill','target':{'role':'textbox','name':'placeholder','index':index*4+column,'scope':dialog},'value':value})
        print('已填写变体：' + variant['sku'], flush=True)
    return action({'action':'snapshot'})


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    product = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))[0]
    result = fill_product(product)
    print(result['snapshot'])
