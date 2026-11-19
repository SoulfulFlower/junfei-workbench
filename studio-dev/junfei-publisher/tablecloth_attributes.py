"""本次桌布类目校准；只使用已核实资料及用户确认包装尺寸。"""
import json
from library_fill import action


def form(name, translation=None):
    css = '.el-form-item:visible:has(> label span.normal:text-is(' + json.dumps(name) + '))'
    if translation:
        css += ':has(>label:has-text(' + json.dumps(translation, ensure_ascii=False) + '))'
    return {'css':css}


def fill(name, value, translation=None):
    scope = form(name, translation)
    action({'action':'fill','target':{'css':'input:visible','scope':scope},'value':str(value)})
    observed = action({'action':'inspect','target':scope})['value']['fields']
    if not any(field.get('value') == str(value) for field in observed):
        raise ValueError('属性填写核验失败：' + name)
    print('已填写 ' + name + ': ' + str(value),flush=True)


def choose(name, value, translation=None):
    scope = form(name, translation)
    action({'action':'click','target':{'css':'input:visible','scope':scope}})
    action({'action':'click','target':{'text':value,'scope':{'css':'.el-select-dropdown:visible'}}})
    print('已选择 ' + name + ': ' + value,flush=True)


def fill_tablecloth():
    fill('Color','White')
    choose('Style','经典款(Classic)')
    choose('Pattern','花卉图案(Floral)')
    fill('Model Name','Lace Tablecloth')
    fill('Model Number','WYJ20261030100733')
    fill('Occasion','Wedding','(提供场合)')
    choose('Occasion','婚礼(Wedding)','(场合)')
    choose('Item Shape','方形(Square)')
    # 父商品采用第一个60×60cm变体尺寸；每个子变体另行覆盖实际尺寸和形状。
    fill('Item Width Shorter Edge','23.622047')
    fill('Item Length Longer Edge','23.622047')
    choose('Are batteries required?','否(No)')
    fill('Maximum Order Quantity','88')
    choose('Included Components','Table Overlay(Table Overlay)')
    choose('Package Weight Unit','磅（重量单位）(Pounds)')
    fill('Package Weight','1.763698')
    for unit, dimension, value in [
        ('Package Width Unit','Item Package Width','10'),
        ('Package Height Unit','Item Package Height','5'),
        ('Package Length Unit','Item Package Length','10'),
    ]:
        choose(unit,'厘米单位(Centimeters)')
        fill(dimension,value)


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    fill_tablecloth()
