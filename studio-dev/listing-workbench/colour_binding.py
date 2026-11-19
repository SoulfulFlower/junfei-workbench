"""Exact-SKU image associations from current evidence, separate from human approval."""
import hashlib
import json
import variant_colours


def candidate(record, product, master_id, master_reference, count):
    if record.get('productId') != product.get('id'):
        raise ValueError('套图与当前产品不匹配')
    if not master_id or record.get('masterId') != master_id:
        raise ValueError('母版已经变更')
    if record.get('status') not in ('done','awaiting_manual','approved') or record.get('validated') is not True:
        raise ValueError('套图尚未完成同款及逐图检查')
    groups=variant_colours.catalog(product)
    master_key=variant_colours.resolve(groups,product.get('masterColor'))
    master=groups.get(master_key)
    if not master or not master['ready'] or not variant_colours.has_reference(master,master_reference):
        raise ValueError('母版颜色或参考图未核实')
    key=record.get('colorKey') or variant_colours.resolve(groups,record.get('color'))
    group=groups.get(key)
    if not group or not group['ready'] or key==master_key:
        raise ValueError('目标颜色、供货资料或子SKU未核实')
    if not variant_colours.has_reference(group,record.get('reference')):
        raise ValueError('参考图与目标颜色不匹配')
    items=record.get('items') or []
    if (any(type(i.get('slot')) is not int for i in items)
            or sorted(i['slot'] for i in items)!=list(range(count))):
        raise ValueError('需要完整且顺序唯一的套图')
    for item in items:
        qc=item.get('qc') or {}
        if (not item.get('image') or item.get('status') not in ('done','awaiting_manual','approved')
                or qc.get('pass') is not True or qc.get('issues')):
            raise ValueError('仍有未通过检查的图位')
    skus=[child.get('sku') for child in group['children']]
    if not skus or any(not isinstance(sku,str) or not sku.strip() for sku in skus) or len(set(skus))!=len(skus):
        raise ValueError('子SKU缺失或重复')
    content={'version':1,'mode':'automatic_qc','masterId':master_id,'colorKey':key,
             'reference':record['reference'],'skus':skus,
             'images':[{'slot':i['slot'],'image':i['image']} for i in sorted(items,key=lambda i:i['slot'])]}
    content['signature']=hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {**content,'status':'linked'}
