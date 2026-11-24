"""Bind observed supplier skirt facts to an original, unsaved US preparation."""
import copy
import json
import re
import time
import uuid


def derive(product, source):
    supplier=product.get('sourceImport',{}).get('supplier',{})
    facts=source.get('publicationFacts',{})
    url=facts.get('supplierModelNumberEvidence',{}).get('sourceUrl')
    model=facts.get('supplierModelNumber')
    if (product.get('id')!=source.get('productId') or not url
            or url!=product.get('sourceUrl') or url!=supplier.get('url')
            or url!=source.get('goods',{}).get('sourceUrl')
            or not model or supplier.get('attributes',{}).get('货号')!=model
            or not supplier.get('retrievedAt')):
        raise ValueError('短裙属性缺少当前账号同款货源及真实型号依据')
    title=supplier.get('title','')
    choices={'高腰':'High Rise','中腰':'Mid Rise','低腰':'Low Rise'}
    rise=[(word,value) for word,value in choices.items() if word in title]
    if len(rise)!=1 or supplier.get('attributes',{}).get('图案')!='纯色':
        raise ValueError('同款货源没有唯一明确腰型或纯色属性')
    return {'source':'bound_supplier_catalogue_facts','sourceUrl':url,'supplierModelNumber':model,
            'retrievedAt':supplier['retrievedAt'],'humanReviewed':False,
            'rise':{'value':rise[0][1],'path':'sourceImport.supplier.title','sourceValue':rise[0][0],'sourceText':title},
            'pattern':{'value':'Solid','path':'sourceImport.supplier.attributes.图案','sourceValue':'纯色'}}


def append(user, job, folder, packet, product, write_json):
    source=packet['input'];receipt=json.loads((folder/'receipt.json').read_text('utf-8'))
    prepared=receipt.get('usPrepare',{});schema=prepared.get('schemaObservation',{})
    if (job.get('accountId')!=user or source.get('accountId')!=user
            or source.get('jobId')!=job['id'] or receipt.get('jobId')!=job['id']
            or source.get('productId')!=job['productId'] or receipt.get('productId')!=job['productId']
            or receipt.get('accountId')!=user or receipt.get('snapshotSha256')!=source.get('sha256')
            or receipt.get('phase')!='us_preparation' or receipt.get('usPublish')
            or schema.get('country_code')!='US' or schema.get('product_type_name')!='SKIRT'
            or any(prepared.get(k) for k in ('preparedInput','saveIntendedAt','requestSent','submitted'))):
        raise ValueError('仅可在原美国短裙尚未冻结保存或发布时补充同款货源属性')
    evidence=derive(product,source);amended=copy.deepcopy(packet)
    preparation=amended['input'].setdefault('usPreparation',{})
    if preparation.get('skirtFacts'):
        if preparation['skirtFacts']!=evidence:raise ValueError('原短裙属性依据冲突')
        return
    preparation['skirtFacts']=evidence;identity=uuid.uuid4().hex
    write_json(folder/'amendments'/(identity+'.json'),{'at':time.time(),'kind':'us_skirt_supplier_facts','evidence':evidence,'previousInput':packet})
    write_json(folder/'input.json',amended)
    job.setdefault('amendments',[]).append({'id':identity,'kind':'us_skirt_supplier_facts','evidence':evidence})
