"""Narrow, explicit authorization for three evidenced UK SWEATSHIRT facts.

This module does not submit, read ERP, or mutate a workspace. The host archives
the returned scope before its independently journaled original-task Save.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / 'artifacts'
FACTS = {'outerMaterial': '100% polyester', 'weaveType': 'Knit', 'itemTypeName': 'Sweatshirt'}
REPRESENTATION = {'explicitCommonAttributes': True, 'exactNumericTypes': True,
                  'independentInventory': True, 'unknownGbpRrpZero': True}


def field(message):
    for key, pattern in [('outer.material', r'外部材料|outer material'),
                         ('weave_type', r'编织类型|weave type'),
                         ('item_type_name', r'产品类型名称|item type name')]:
        if re.search(pattern, message or '', re.I):
            return key
    return None


def identity_scope(job, record, source):
    preparation = record.get('ukPrepare') or {}
    prepared = preparation.get('preparedInput') or {}
    publication = record.get('ukPublish') or {}
    destination = prepared.get('destination') or {}
    expected = {'accountId': job['accountId'], 'productId': job['productId'], 'jobId': job['id'],
                'snapshotSha256': source.get('sha256'), 'publishId': str(publication.get('publishId') or ''),
                'destinationId': destination.get('destinationId'), 'draftId': str(destination.get('draftId') or ''),
                'erpAccountId': str(destination.get('erpAccountId') or ''), 'marketId': str(destination.get('marketId') or ''),
                'countryCode': 'GB', 'store': prepared.get('store'), 'parentSku': prepared.get('goods', {}).get('parentSku'),
                'schemaHash': destination.get('schemaHash')}
    if (source.get('accountId') != job['accountId'] or source.get('productId') != job['productId']
            or source.get('jobId') != job['id'] or record.get('accountId') != job['accountId']
            or record.get('productId') != job['productId'] or record.get('jobId') != job['id']
            or record.get('snapshotSha256') != source.get('sha256')
            or preparation.get('phase') != 'uk_draft_verified'
            or record.get('ukCopy', {}).get('phase') != 'copy_verified'
            or prepared.get('accountId') != job['accountId'] or prepared.get('productId') != job['productId']
            or prepared.get('sha256') != source.get('sha256') or prepared.get('marketplace') != 'UK'
            or destination.get('countryCode') != 'GB' or prepared.get('store') != source.get('ukTarget', {}).get('storeName')
            or destination.get('destinationId') != (source.get('ukTarget', {}).get('id') or source.get('ukTarget', {}).get('destinationId'))
            or expected['draftId'] != str(record.get('ukCopy', {}).get('draftId') or '')
            or expected['draftId'] != str(preparation.get('draftId') or '')
            or prepared.get('goods', {}).get('parentSku') != source.get('goods', {}).get('parentSku')
            or [(x.get('sku'), x.get('color'), x.get('size')) for x in prepared.get('goodsItems', [])]
                != [(x.get('sku'), x.get('color'), x.get('size')) for x in source.get('goodsItems', [])]
            or any(not value for value in expected.values())
            or any(not re.fullmatch(r'[1-9]\d*', expected[key]) for key in ('publishId', 'draftId', 'erpAccountId', 'marketId'))
            or str(publication.get('identity', {}).get('publishId') or '') != expected['publishId']
            or str(publication.get('sourceLink', {}).get('publishId') or '') != expected['publishId']
            or str(publication.get('sourceLink', {}).get('draftId') or '') != expected['draftId']
            or not publication.get('sourceEvidence') or not publication.get('fingerprint')):
        raise ValueError('必填属性修复缺少原英国已核实任务、冻结资料或受理历史身份')
    meta = preparation.get('schemaObservation') or {}
    if (meta.get('country_code') != 'GB' or meta.get('locale') != 'en_GB'
            or meta.get('product_type_name') != 'SWEATSHIRT' or meta.get('hash') != expected['schemaHash']
            or not meta.get('schema_content')):
        raise ValueError('必填属性修复缺少原GB SWEATSHIRT实际schema')
    return expected, prepared, publication


def evidence(request, prepared):
    item = request.get('evidence')
    if (not isinstance(item, dict) or set(item) != {'sourceUrl', 'materialText', 'weaveText', 'itemTitle', 'categoryPath', 'artifacts'}
            or item.get('sourceUrl') != prepared.get('goods', {}).get('sourceUrl')
            or not re.fullmatch(r'https://detail\.1688\.com/offer/\d+\.html', item.get('sourceUrl', ''))
            or not all(isinstance(item.get(k), str) and 0 < len(item[k]) <= 2000
                       for k in ('materialText', 'weaveText', 'itemTitle', 'categoryPath'))
            or '100%' not in item['materialText'] or '卫衣' not in item['itemTitle']
            or not re.search(r'工艺\s*[:：]?\s*针织', item['weaveText'])
            or not re.search(r'Sweatshirts\s*$', item['categoryPath'], re.I)
            or not re.search(r'Material:\s*100%\s*polyester(?:\n|$)',
                             re.sub(r'<br\s*/?\s*>', '\n', prepared['goods'].get('description', ''), flags=re.I), re.I)
            or not isinstance(item['artifacts'], list) or not 2 <= len(item['artifacts']) <= 4):
        raise ValueError('三项缺失事实须提供本款原供应商直接证据，不使用袖口罗纹推断整身织法')
    knit, composition = False, False
    for artifact in item['artifacts']:
        if (not isinstance(artifact, dict) or set(artifact) != {'path', 'sha256'}
                or not isinstance(artifact['path'], str) or not re.fullmatch(r'[a-f0-9]{64}', str(artifact.get('sha256') or ''))):
            raise ValueError('供应商证据文件及SHA不完整')
        path = Path(artifact['path']).resolve()
        if (not path.is_relative_to(ARTIFACT_ROOT.resolve()) or path.suffix.lower() != '.json'
                or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024):
            raise ValueError('供应商证据必须是当前工作区已保存的限定公开商品缓存')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact['sha256']:
            raise ValueError('供应商证据文件SHA已变化')
        body = json.loads(raw.decode('utf-8-sig'))
        actual, expected = urlsplit(body.get('url', '')), urlsplit(item['sourceUrl'])
        if (actual.scheme, actual.netloc, actual.path) != (expected.scheme, expected.netloc, expected.path):
            raise ValueError('供应商证据缓存不属于本款原offer')
        text = body.get('text') or ''
        if isinstance(text, str) and re.search(r'商品属性[\s\S]*?工艺\s*针织', text):
            knit = True
        attrs = body.get('attributes') or {}
        if (isinstance(attrs, dict) and attrs.get('材质成分') == '涤纶（聚酯纤维）:100%'
                and isinstance(body.get('title'), str) and '卫衣' in body['title']):
            composition = True
    if not knit or not composition:
        raise ValueError('完整原商品缓存未共同证实针织工艺和100%聚酯卫衣')
    return copy.deepcopy(item)


def freeze_scope(job, record, source, request):
    expected, prepared, publication = identity_scope(job, record, source)
    if (not isinstance(request, dict) or set(request) != {'sourceFingerprint', 'schemaHash', 'facts', 'representation', 'evidence'}
            or request.get('facts') != FACTS or request.get('representation') != REPRESENTATION
            or any(value is not True for value in request.get('representation', {}).values())
            or not re.fullmatch(r'[a-f0-9]{64}', str(request.get('sourceFingerprint') or ''))
            or request.get('schemaHash') != expected['schemaHash']):
        raise ValueError('必填修复必须明确三事实、原源指纹/schema和完整显式表示范围')
    observation = publication.get('latestObservation') or publication.get('failureObservation') or {}
    if (observation.get('status') != 'failed' or observation.get('verification') != 'failed'
            or observation.get('failed') is not True or observation.get('identityVerified') is not True
            or observation.get('unscopedMessageCount') != 0 or observation.get('acceptedCount') != 0
            or observation.get('childCount') != len(prepared['goodsItems'])
            or observation.get('count') != observation.get('childCount')
            or observation.get('messageCount') != observation.get('childCount') * 3
            or not re.fullmatch(r'[a-f0-9]{64}', str(observation.get('responseFingerprint') or ''))
            or any(str(observation.get(key, '')) != str(value) for key, value in expected.items() if key not in ('schemaHash', 'jobId'))):
        raise ValueError('当前原英国失败不是已核实的全部子体三项90220缺失')
    children = observation.get('children')
    if not isinstance(children, list) or len(children) != len(prepared['goodsItems']):
        raise ValueError('缺少原英国完整子体观察')
    urls = (record.get('ukPrepare') or {}).get('urls') or prepared.get('urls') or source.get('urls') or {}
    for row, variant in zip(children, prepared['goodsItems']):
        messages = row.get('messages') or []
        images = [urls.get(prepared['assets'][index]['sha256']) for index in variant['imageIndices']]
        if (row.get('sku') != variant['sku'] or not re.fullmatch(r'[1-9]\d*', str(row.get('childId') or ''))
                or row.get('status') != 'failed' or row.get('imagesSource') != 'child_gallery'
                or len(images) != 7 or any(not image for image in images) or row.get('images') != images
                or row.get('main') != images[0] or len(messages) != 3
                or any(str(m.get('code')) != '90220' or m.get('sku') != row['sku'] for m in messages)
                or {field(m.get('message')) for m in messages} != {'outer.material', 'weave_type', 'item_type_name'}):
            raise ValueError('原英国子SKU、七图或90220字段范围不符')
    if len({str(row['childId']) for row in children}) != len(children):
        raise ValueError('原英国子体ID重复')
    if publication.get('requiredAttributeRepair'):
        raise ValueError('已有必填修复检查点，不能建立另一份授权')
    return {**expected, 'children': [{'id': str(row['childId']), 'sku': row['sku']} for row in children],
            'sourceFingerprint': request['sourceFingerprint'], 'failureResponseFingerprint': observation['responseFingerprint'],
            'facts': copy.deepcopy(FACTS), 'representation': copy.deepcopy(REPRESENTATION),
            'evidence': evidence(request, prepared), 'retryOriginalTaskAfterVerifiedSave': True,
            'runtime': {'pythonExecutable': sys.executable}}


def validate_frozen(job, record, source):
    expected, _, publication = identity_scope(job, record, source)
    amendment = source.get('publicationRequiredAttributeRepair')
    if (not isinstance(amendment, dict) or not amendment.get('id')
            or amendment.get('scope') != 'repair_original_failed_required_attributes'
            or amendment.get('marketplace') != 'UK' or amendment.get('facts') != FACTS
            or amendment.get('representation') != REPRESENTATION
            or amendment.get('retryOriginalTaskAfterVerifiedSave') is not True
            or any(str(amendment.get(key, '')) != str(value) for key, value in expected.items())
            or type(amendment.get('authorizedAt')) not in (int, float) or amendment['authorizedAt'] <= 0
            or not re.fullmatch(r'[a-f0-9]{64}', str(amendment.get('sourceFingerprint') or ''))
            or not re.fullmatch(r'[a-f0-9]{64}', str(amendment.get('failureResponseFingerprint') or ''))):
        raise ValueError('原必填属性修复冻结授权身份不完整')
    journal = publication.get('requiredAttributeRepair')
    if journal and (journal.get('amendmentId') != amendment['id'] or str(journal.get('publishId')) != expected['publishId']):
        raise ValueError('原必填属性修复检查点不属于冻结授权')
    if amendment.get('preclickSaveRecovery'):
        validate_preclick_frozen(amendment, journal)
    if amendment.get('retryPreflightRecovery'):
        validate_retry_preflight_frozen(amendment, journal)
    return amendment


def source_fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def _preclick_original(journal, amendment):
    intent = (journal or {}).get('saveIntent') or {}
    error = (journal or {}).get('lastSaveError')
    url = 'https://www.junfeikuajing.com/#/amazon/product/' + amendment['publishId'] + '?type=publish'
    suffix = '; last URL was "' + url + '"; last title was "Amazon产品编辑 - 钧飞跨境".'
    if (not journal or journal.get('amendmentId') != amendment['id']
            or intent.get('scope') != 'one_original_task_native_save' or not intent.get('armedAt')
            or str(intent.get('publishId')) != amendment['publishId']
            or not isinstance(error, str)
            or not re.match(r'^page\.waitForFunction timed out after 20000ms on page p\d+;', error)
            or not error.endswith(suffix)
            or any(key in journal for key in ('guardInstallProof', 'lastGuardSnapshot', 'nativeRequests', 'guardError'))
            or not journal.get('beforeSource') or not journal.get('plannedSource')
            or source_fingerprint(journal['beforeSource']) != amendment['sourceFingerprint']):
        raise ValueError('不是原20秒页面就绪前超时且未进入护栏的限定检查点')
    return intent, error


def freeze_preclick_recovery(job, record, source):
    amendment = validate_frozen(job, record, source)
    journal = (record.get('ukPublish') or {}).get('requiredAttributeRepair')
    intent, error = _preclick_original(journal, amendment)
    if (amendment.get('preclickSaveRecovery') or journal.get('preclickSaveRecovery')
            or journal.get('phase') != 'save_unknown' or 'saveVerified' in journal
            or journal.get('retry', {}).get('intent')):
        raise ValueError('已消费或已有其他保存/重试，不建立另一页面就绪前纠正授权')
    # Reuse the original full failure validation without its new-authorization
    # checkpoint restriction. This is a derived scope, never a history reset.
    copied = copy.deepcopy(record)
    del copied['ukPublish']['requiredAttributeRepair']
    request = {key: copy.deepcopy(amendment[key]) for key in
               ('sourceFingerprint', 'schemaHash', 'facts', 'representation', 'evidence')}
    scope = freeze_scope(job, copied, source, request)
    return {**scope, 'originalMainAmendmentId': amendment['id'],
            'originalSaveIntentArmedAt': intent['armedAt'], 'originalLastSaveError': error,
            'beforeSourceFingerprint': source_fingerprint(journal['beforeSource']),
            'plannedSourceFingerprint': source_fingerprint(journal['plannedSource'])}


def validate_preclick_frozen(amendment, journal):
    recovery = amendment.get('preclickSaveRecovery') or {}
    intent, error = _preclick_original(journal, amendment)
    keys = ('accountId', 'productId', 'jobId', 'snapshotSha256', 'publishId', 'destinationId',
            'draftId', 'erpAccountId', 'marketId', 'countryCode', 'store', 'parentSku', 'schemaHash',
            'sourceFingerprint', 'failureResponseFingerprint', 'children')
    if (not recovery.get('id') or recovery.get('scope') != 'resume_original_required_attributes_preclick_save'
            or recovery.get('marketplace') != 'UK'
            or type(recovery.get('authorizedAt')) not in (int, float) or recovery['authorizedAt'] <= 0
            or recovery.get('originalMainAmendmentId') != amendment['id']
            or recovery.get('originalSaveIntentArmedAt') != intent['armedAt']
            or recovery.get('originalLastSaveError') != error
            or recovery.get('beforeSourceFingerprint') != source_fingerprint(journal['beforeSource'])
            or recovery.get('plannedSourceFingerprint') != source_fingerprint(journal['plannedSource'])
            or recovery.get('retryOriginalTaskAfterVerifiedSave') is not True
            or any(recovery.get(key) != amendment.get(key) for key in keys)):
        raise ValueError('页面就绪前纠正冻结范围与原历史不符')
    checkpoint = journal.get('preclickSaveRecovery')
    if checkpoint and checkpoint.get('amendmentId') != recovery['id']:
        raise ValueError('已有另一页面就绪前纠正检查点')
    return recovery


def _retry_preflight_original(amendment, journal):
    retry = (journal or {}).get('retry') or {}
    if (not journal or journal.get('saveVerified') is not True or not journal.get('saveVerifiedAt')
            or not journal.get('plannedSource') or not retry.get('intent', {}).get('armedAt')
            or str(retry['intent'].get('publishId')) != amendment['publishId']
            or retry['intent'].get('scope') != 'original_family_all_children'
            or retry.get('lastError') != '原失败任务行或店铺不唯一，未再次发布'
            or any(k in retry for k in ('nativeRequests', 'guardError'))):
        raise ValueError('不是原英国行匹配前置拒绝且未进入写入护栏的重试检查点')
    proof = journal.get('schemaValidationAfterSave') or {}
    saved = journal.get('preclickSaveRecovery') or journal
    requests = saved.get('nativeRequests') or []
    if (proof.get('passed') is not True or proof.get('checkedCount') != len(amendment['children']) + 1
            or proof.get('schemaHash') != amendment['schemaHash'] or saved.get('saveVerified') is not True
            or len(requests) != 1 or requests[0].get('method') != 'POST'
            or requests[0].get('url') != 'https://app.junfeikuajing.com/api/amazon/goods/publish/json-update'
            or requests[0].get('response', {}).get('httpStatus') != 200
            or requests[0].get('response', {}).get('body', {}).get('code') != 0):
        raise ValueError('缺少已验证的原正常保存和完整raw schema证据，不能仅重试')
    return retry


def freeze_retry_preflight_recovery(job, record, source):
    amendment = validate_frozen(job, record, source)
    journal = (record.get('ukPublish') or {}).get('requiredAttributeRepair') or {}
    retry = _retry_preflight_original(amendment, journal)
    if amendment.get('retryPreflightRecovery') or journal.get('retryPreflightRecovery'):
        raise ValueError('已有唯一重试前置纠正，不再授权')
    copied = copy.deepcopy(record);del copied['ukPublish']['requiredAttributeRepair']
    request = {key: copy.deepcopy(amendment[key]) for key in
               ('sourceFingerprint', 'schemaHash', 'facts', 'representation', 'evidence')}
    scope = freeze_scope(job, copied, source, request)
    return {**scope, 'originalMainAmendmentId': amendment['id'],
            'originalRetryIntentArmedAt': retry['intent']['armedAt'], 'originalRetryLastError': retry['lastError'],
            'plannedSourceFingerprint': source_fingerprint(journal['plannedSource']),
            'originalSaveVerifiedAt': journal['saveVerifiedAt']}


def validate_retry_preflight_frozen(amendment, journal):
    retry = _retry_preflight_original(amendment, journal)
    recovery = amendment.get('retryPreflightRecovery') or {}
    keys = ('accountId', 'productId', 'jobId', 'snapshotSha256', 'publishId', 'destinationId', 'draftId',
            'erpAccountId', 'marketId', 'countryCode', 'store', 'parentSku', 'schemaHash',
            'sourceFingerprint', 'failureResponseFingerprint', 'children')
    if (not recovery.get('id') or recovery.get('scope') != 'resume_original_required_attributes_retry_preflight'
            or recovery.get('marketplace') != 'UK'
            or type(recovery.get('authorizedAt')) not in (int, float) or recovery['authorizedAt'] <= 0
            or recovery.get('originalMainAmendmentId') != amendment['id']
            or recovery.get('originalRetryIntentArmedAt') != retry['intent']['armedAt']
            or recovery.get('originalRetryLastError') != retry['lastError']
            or recovery.get('originalSaveVerifiedAt') != journal['saveVerifiedAt']
            or recovery.get('plannedSourceFingerprint') != source_fingerprint(journal['plannedSource'])
            or any(recovery.get(key) != amendment.get(key) for key in keys)):
        raise ValueError('原英国重试前置纠正冻结范围不完整')
    checkpoint = journal.get('retryPreflightRecovery')
    if checkpoint and checkpoint.get('amendmentId') != recovery['id']:
        raise ValueError('已有另一原英国重试前置纠正检查点')
    return recovery
