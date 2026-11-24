"""Append same-source observed coat facts before any original US Save."""
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import time
import uuid


def derive(product, source):
    supplier = product.get('sourceImport', {}).get('supplier', {})
    url = source.get('goods', {}).get('sourceUrl')
    match = re.fullmatch(r'https://detail\.1688\.com/offer/([1-9]\d*)\.html', str(url))
    path = product.get('sourceEvidence', {}).get('completeSourceObservation')
    if (product.get('id') != source.get('productId') or product.get('cat') != '服装'
            or not match or product.get('sourceUrl') != url or supplier.get('url') != url
            or not isinstance(path, str) or not Path(path).is_absolute()):
        raise ValueError('外套属性缺少当前产品绑定的完整同货源观察')
    file = Path(path)
    if file.suffix.lower() != '.json' or not file.is_file() or file.stat().st_size > 2*1024*1024:
        raise ValueError('外套完整货源观察文件无效')
    raw = file.read_bytes(); observed = json.loads(raw.decode('utf-8'))
    if not isinstance(observed, dict):raise ValueError('完整货源观察结构无效')
    attrs = observed.get('attributes') or {}
    try:
        when = datetime.fromisoformat(observed['observedAt'].replace('Z', '+00:00'))
        valid_time = when.tzinfo is not None and when.utcoffset() is not None
    except (ValueError, KeyError, TypeError):
        valid_time = False
    images = observed.get('images')
    if not isinstance(images, list) or not all(isinstance(v, str) for v in images):
        raise ValueError('完整货源观察图片来源无效')
    origin_images = set(images)
    # The complete native observation also records visible same-offer colour
    # buttons. 1688's exact _sum.jpg rendition and its original share one file.
    # Accept that known CDN rendition only, never arbitrary URL rewriting.
    colour_image_proofs = []
    for button in observed.get('colourButtons', []):
        if not isinstance(button, dict) or button.get('visible') is not True:
            continue
        image = button.get('image')
        match_image = re.fullmatch(r'(https://cbu01\.alicdn\.com/img/ibank/[^/?#]+\.(?:jpg|png))_sum\.jpg', str(image))
        if match_image:
            origin_images.add(match_image[1])
            colour_image_proofs.append({'observedUrl':image, 'originalUrl':match_image[1], 'colour':button.get('text')})
    bound = [a.get('originUrl') for a in product.get('assets', [])
             if a.get('sourceRole') == 'primary' and a.get('sourceSupplierUrl') == url]
    description = source.get('goods', {}).get('description', '').replace('<br>', '\n')
    def line(label):
        found = [v[len(label)+1:].strip() for v in description.splitlines() if v.startswith(label+':')]
        return found[0] if len(found) == 1 else ''
    ordinary = source.get('publicationFacts', {}).get('waterResistanceLevelSource', {}).get('basis', {}).get('classification')
    raglan = attrs.get('袖型') == '插肩袖'
    if raglan:
        closure_line = line('Front')
        text_matches = (re.fullmatch(r'Full zipper(?:; chevron quilting)?', closure_line, re.I)
                        and re.fullmatch(r'Smooth raglan long sleeves; plain straight openings', line('Sleeves'), re.I)
                        and re.fullmatch(r'Fitted padded jacket', line('Style'), re.I)
                        and all(supplier.get('attributes', {}).get(key) == attrs.get(key)
                                for key in ('门襟', '袖型', '袖长', '衣长')))
    else:
        closure_line = line('Closure')
        text_matches = (attrs.get('袖型') == '灯笼袖'
                        and re.fullmatch(r'Front half zipper(?: with a long red pull)?', closure_line, re.I)
                        and re.search(r'\blong sleeves\b', line('Style'), re.I))
    if (observed.get('canonicalUrl') != url or str(observed.get('offerId')) != match[1]
            or not valid_time or not bound or not all(v in origin_images for v in bound)
            or not isinstance(attrs, dict) or attrs.get('门襟') != '拉链'
            or not text_matches or attrs.get('袖长') != '长袖'
            or not str(attrs.get('衣长', '')).startswith('普通款(')
            or attrs.get('材质成分') != '涤纶（聚酯纤维）:100%'
            or supplier.get('attributes', {}).get('材质成分') != attrs['材质成分']
            or line('Material').lower() != '100% polyester'
            or ordinary != 'ordinary_apparel'):
        raise ValueError('外套货源、原文案或普通服装分类未提供一致明确依据')
    facts = {'source':'bound_supplier_catalogue_observation', 'productId':product['id'],
            'sourceUrl':url, 'humanReviewed':False,
            'observation':{'path':str(file), 'sha256':hashlib.sha256(raw).hexdigest(),
                           'observedAt':observed['observedAt'], 'offerId':match[1]},
            'closure':{'value':'Zipper', 'sourceField':'门襟', 'sourceValue':attrs['门襟'], 'frozenLine':closure_line},
            'sleeve':{'value':'Raglan Sleeve' if raglan else 'Lantern Sleeve', 'sourceField':'袖型', 'sourceValue':attrs['袖型'],
                      'length':'long_sleeve', 'sourceLength':attrs['袖长']},
            'itemLength':{'value':'Standard Length', 'sourceField':'衣长', 'sourceValue':attrs['衣长']},
            'dangerousGoods':{'value':'not_applicable', 'source':'inferred_workbench_classification',
                              'supplierVerified':False, 'basis':'ordinary_apparel_100_percent_polyester',
                              'note':'普通纯涤纶服装目录分类；不是供应商危险品声明、检测或认证。'}}
    if raglan:
        facts['closure']['frozenLineLabel'] = 'Front'
        facts['sleeve']['frozenLine'] = line('Sleeves')
        facts['style'] = {'value':line('Style'), 'source':'frozen_listing', 'supplierVerified':False,
                          'basis':'same_source_raglan_fitted_padded_jacket'}
    if colour_image_proofs:
        facts['observation']['colourButtonImageProofs'] = colour_image_proofs
    return facts


def append(user, job, folder, packet, product, write_json):
    source = packet['input']; receipt = json.loads((folder/'receipt.json').read_text('utf-8'))
    prepared = receipt.get('usPrepare') or {}; schema = prepared.get('schemaObservation') or {}
    if (job.get('accountId') != user or source.get('accountId') != user or receipt.get('accountId') != user
            or job.get('id') != source.get('jobId') or receipt.get('jobId') != job['id']
            or job.get('productId') != source.get('productId') or receipt.get('productId') != job['productId']
            or receipt.get('snapshotSha256') != source.get('sha256')
            or receipt.get('phase') != 'us_preparation' or receipt.get('usPublish')
            or schema.get('country_code') != 'US' or schema.get('product_type_name') != 'COAT'
            or any(prepared.get(k) for k in ('saveIntendedAt', 'requestSent', 'submitted', 'response'))
            or prepared.get('schemaValidation', {}).get('passed') is not False):
        raise ValueError('仅可在原美国COAT真实schema预检失败且尚未保存或发布时补充同款属性')
    evidence = derive(product, source); amended = copy.deepcopy(packet)
    preparation = amended['input'].setdefault('usPreparation', {})
    if preparation.get('coatFacts'):
        if preparation['coatFacts'] != evidence:raise ValueError('原外套供货属性依据冲突')
        return
    preparation['coatFacts'] = evidence; identity = uuid.uuid4().hex
    write_json(folder/'amendments'/(identity+'.json'), {'at':time.time(), 'kind':'us_coat_supplier_facts',
               'evidence':evidence, 'previousInput':packet, 'previousUsPreparation':prepared})
    write_json(folder/'input.json', amended)
    job.setdefault('amendments', []).append({'id':identity, 'kind':'us_coat_supplier_facts', 'evidence':evidence})


def append_uk_weave(user, job, folder, packet, evidence, write_json):
    """Freeze an explicit seller catalogue choice before the original GB Save."""
    source = packet['input']; receipt = json.loads((folder/'receipt.json').read_text('utf-8'))
    prepared = receipt.get('ukPrepare') or {}; meta = prepared.get('schemaObservation') or {}
    schema = meta.get('schema_content') or {}
    if isinstance(schema, str):schema = json.loads(schema)
    values = schema.get('properties', {}).get('weave_type', {}).get('items', {}).get('properties', {}).get('value', {})
    enums = values.get('enum', []) + [v for branch in values.get('anyOf', []) for v in branch.get('enum', [])]
    if (not isinstance(evidence, dict) or set(evidence) != {'productId','value','source','supplierVerified','scope','instruction','configuredAt','schemaHash'}
            or evidence.get('source') != 'user_configured_defaults' or evidence.get('supplierVerified') is not False
            or evidence.get('scope') != 'missing_catalogue_attribute_only' or evidence.get('value') != 'Plain'
            or not isinstance(evidence.get('instruction'), str) or not evidence['instruction'].strip()
            or evidence.get('productId') != source.get('productId') or evidence.get('schemaHash') != meta.get('hash')
            or 'Plain' not in enums):
        raise ValueError('英国外套目录默认须绑定本品、真实schema和明确的经营默认来源')
    try:
        when = datetime.fromisoformat(evidence['configuredAt'].replace('Z', '+00:00'))
        if when.tzinfo is None:raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError('英国外套目录默认时间无效')
    us = receipt.get('usPublish') or {}
    if (any(x.get('accountId') != user for x in (source, receipt, job))
            or receipt.get('jobId') != job.get('id') or source.get('jobId') != job.get('id')
            or receipt.get('productId') != job.get('productId') or source.get('productId') != job.get('productId')
            or receipt.get('snapshotSha256') != source.get('sha256') or receipt.get('phase') != 'uk_preparation'
            or receipt.get('ukPublish') or receipt.get('ukCopy', {}).get('phase') != 'copy_verified'
            or us.get('phase') != 'publishing_verified' or not us.get('publishId')
            or meta.get('country_code') != 'GB' or meta.get('locale') != 'en_GB' or meta.get('product_type_name') != 'COAT'
            or prepared.get('schemaValidationBeforeSave', {}).get('passed') is not False
            or any(prepared.get(k) for k in ('saveIntendedAt','requestSent','submitted','response','preparedInput'))
            or source.get('usPreparation', {}).get('coatFacts', {}).get('productId') != source.get('productId')):
        raise ValueError('仅可对同账号原英国COAT保存前失败预检追加目录默认，不重建刊登')
    amended = copy.deepcopy(packet); preparation = amended['input'].setdefault('ukPreparation', {})
    if preparation.get('coatWeave'):
        if preparation['coatWeave'] != evidence:raise ValueError('英国外套目录默认冲突')
        return
    preparation['coatWeave'] = copy.deepcopy(evidence); identity = uuid.uuid4().hex
    write_json(folder/'amendments'/(identity+'.json'), {'at':time.time(),'kind':'uk_coat_catalogue_default',
               'evidence':evidence,'previousInput':packet,'previousUkPreparation':prepared})
    write_json(folder/'input.json', amended)
    job.setdefault('amendments', []).append({'id':identity,'kind':'uk_coat_catalogue_default','evidence':evidence})
