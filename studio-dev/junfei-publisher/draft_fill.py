"""在已选择真实店铺和类目的草稿中填充明确价格库存。"""
import json
from pathlib import Path
import sys
from library_fill import action


def fill_prices(product):
    initial = action({'action':'snapshot'})
    if '/#/amazon/product/' not in initial['url'] or product['store'] not in initial['snapshot']:
        raise ValueError('当前不是目标店铺的产品编辑页')
    action({'action':'fill','target':{'placeholder':'父Sku,可自定义填写内容，方便卖家在后台识别是什么产品，该内容不在平台商城展示'},'value':product['parentSku']})
    action({'action':'fill','target':{'role':'textbox','name':'处理时间'},'value':str(product['handlingDays'])})
    if len(product['title']) <= 75 and product.get('highlight'):
        action({'action':'fill','target':{'role':'textbox','name':'商品亮点'},'value':product['highlight']})
    for variant in product['variants']:
        row = {'role':'row','name':variant['sku'],'exact':False}
        for name, value in [('成本价',variant['costRmb']), ('售价',variant['price']), ('库存',variant['quantity'])]:
            action({'action':'fill','target':{'role':'textbox','name':name,'scope':row},'value':str(value)})
        print('已核实填写成本/售价/库存：' + variant['sku'],flush=True)
    result = action({'action':'snapshot'})
    Path('jobs',product['id'],'draft-filled.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    product = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))[0]
    fill_prices(product)
