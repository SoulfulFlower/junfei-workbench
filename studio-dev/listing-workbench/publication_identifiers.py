"""Exact original-US identifiers for one independently journaled UK repair.

Only reads hashed public research evidence. No ERP, browser or application calls.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

SCOPE = 'repair_original_failed_identifiers'
SWEATSHIRT_PROFILE = 'copied_sweatshirt_gtin_catalog_conflict'
IDENTITY = ('accountId', 'productId', 'jobId', 'snapshotSha256', 'publishId', 'destinationId',
            'draftId', 'erpAccountId', 'marketId', 'countryCode', 'store', 'parentSku', 'schemaHash')


def _profile(record):
    kind = (record.get('ukPrepare', {}).get('schemaObservation') or {}).get('product_type_name')
    if kind == 'SHIRT':
        return {'name': None, 'type': 'SHIRT', 'count': 30, 'codes': ['13013', '8566', '8572']}
    if kind == 'SWEATSHIRT':
        return {'name': SWEATSHIRT_PROFILE, 'type': 'SWEATSHIRT', 'count': 75, 'codes': ['100980', '13013']}
    raise ValueError('编码纠正仅支持已核实的原SHIRT30或SWEATSHIRT75失败范围')


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:raise ValueError()
        return parsed.timestamp()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('编码纠正缺少带时区的真实检查时间') from None


def existing_allowed_exemption_proof(publication, prepared, expected, fresh, raw, *, now=None):
    """Legacy allowed history plus a recent, guarded native CHECK; never an application."""
    historical = publication.get('readiness') or {}
    if (historical.get('store') != prepared['store']
            or historical.get('brand') != prepared['goods']['brand']
            or 'UPC豁免：允许销售' not in re.sub(r'\s+', '', str(historical.get('brandStatus', '')))
            or historical.get('shippingTemplate') != prepared['destination'].get('shippingTemplate')
            or str(historical.get('handlingDays')) != str(prepared.get('handlingDays'))):
        raise ValueError('缺少原英国同店品牌允许销售、运输模板及处理时间的历史证据')
    if not isinstance(fresh, dict):
        raise ValueError('缺少今天原英国SWEATSHIRT同店品牌允许销售的非申请只读检查证据')
    request = fresh.get('request') or {};guard = fresh.get('guardProof') or {};ui = fresh.get('ui') or {}
    scope = request.get('payload') or {};response = request.get('response') or {};body = response.get('body') or {}
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    observed = _timestamp(fresh.get('observedAt'));sent = _timestamp(request.get('sentAt'))
    if not -60 <= now - observed <= 900 or not 0 <= observed - sent <= 900:
        raise ValueError('英国非申请允许销售检查已过期，须重新只读核对（15分钟内）')
    if _timestamp(historical.get('checkedAt')) > observed:
        raise ValueError('英国历史允许销售时间晚于当前检查')
    identity_keys = ('accountId', 'productId', 'jobId', 'snapshotSha256', 'publishId', 'schemaHash')
    if (any(str(fresh.get(k)) != str(expected[k]) for k in identity_keys)
            or ui.get('url') != 'https://www.junfeikuajing.com/#/amazon/product/' + expected['publishId'] + '?type=publish'
            or ui.get('store') != prepared['store'] or ui.get('brand') != prepared['goods']['brand']
            or str(ui.get('nativeMarketId')) != expected['marketId']
            or 'UPC豁免：允许销售' not in re.sub(r'\s+', '', str(ui.get('status', '')))
            or request.get('method') != 'POST' or request.get('url') != 'https://app.junfeikuajing.com/api/amazon/category/upc-exemption/check'
            or set(scope) != {'seller_id', 'country_code', 'primary_category_name', 'product_type_name', 'brand'}
            or any(scope.get(k) != v for k, v in {'seller_id': raw.get('seller_id'), 'country_code': 'GB', 'primary_category_name': 'Fashion', 'product_type_name': 'SWEATSHIRT'}.items())
            or str(scope.get('brand', '')).strip().casefold() != prepared['goods']['brand'].strip().casefold()
            or not isinstance(scope['seller_id'], str) or not scope['seller_id']
            or response.get('httpStatus') != 200 or body.get('code') != 0
            or body.get('data', {}).get('status') != 'available' or body.get('data', {}).get('status_map', {}).get('available') != '允许销售'
            or guard.get('present') is not True or not isinstance(guard.get('token'), str) or not guard['token']
            or guard.get('bindings') != {'open': True, 'send': True, 'fetch': True}
            or guard.get('error') is not None or guard.get('requests') != [request] or request.get('kind') != 'check'):
        raise ValueError('英国新鲜非申请检查的同任务、店铺、GB/SWEATSHIRT、品牌或护栏证明不符')
    return {'kind': 'existing_allowed_and_fresh_native_check', 'historicalReadiness': copy.deepcopy(historical),
            'freshExemptionCheck': copy.deepcopy(fresh), 'singleApplyCount': 0}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def _identifiers(row):
    keys = ('standard_product_type', 'standard_product_id')
    if any(key not in row for key in keys):
        raise ValueError('原商品编码/type未完整回读，不把缺字段视为空值')
    return {key: row[key] for key in keys}


def introduced_identifiers(raw):
    return {'parent': _identifiers(raw),
            'children': {row['sku']: _identifiers(row) for row in raw['items']}}


def exemption_proof(record, prepared):
    response = (record.get('applyResponse') or {}).get('response') or {}
    scope = record.get('nativeScope') or {}
    latest = record.get('latestCheck') or {}
    if (len(record.get('applyRequests') or []) != 1 or not record.get('applyIntent')
            or record.get('phase') != 'allowed' or record.get('applicationState') != 'available'
            or response.get('httpStatus') != 200 or response.get('body', {}).get('code') != 0
            or not response.get('body', {}).get('data', {}).get('id') or latest.get('status') != 'available'
            or scope.get('country_code') != 'GB' or scope.get('primary_category_name') != 'Fashion'
            or scope.get('product_type_name') != 'SHIRT'
            or str(scope.get('brand')).upper() != prepared['goods']['brand'].upper()
            or latest.get('ui', {}).get('store') != prepared['store']
            or str(latest.get('ui', {}).get('nativeMarketId')) != str(prepared['destination']['marketId'])):
        raise ValueError('缺少原英国单次豁免及允许销售记录，不再次申请')
    return {'applicationId': str(response['body']['data']['id']), 'nativeScope': copy.deepcopy(scope),
            'applyIntent': copy.deepcopy(record['applyIntent']), 'allowedAt': record.get('allowedAt'),
            'singleApplyCount': 1}


def identity_scope(job, record, source):
    preparation = record.get('ukPrepare') or {};prepared = preparation.get('preparedInput') or {}
    publication = record.get('ukPublish') or {};destination = prepared.get('destination') or {}
    profile = _profile(record)
    expected = dict(accountId=job['accountId'], productId=job['productId'], jobId=job['id'],
        snapshotSha256=source.get('sha256'), publishId=str(publication.get('publishId') or ''),
        destinationId=destination.get('destinationId'), draftId=str(destination.get('draftId') or ''),
        erpAccountId=str(destination.get('erpAccountId') or ''), marketId=str(destination.get('marketId') or ''),
        countryCode='GB', store=prepared.get('store'), parentSku=prepared.get('goods', {}).get('parentSku'),
        schemaHash=destination.get('schemaHash'))
    if (any(not value for value in expected.values())
            or any(not re.fullmatch(r'[1-9]\d*', expected[k]) for k in ('publishId', 'draftId', 'erpAccountId', 'marketId'))
            or source.get('accountId') != job['accountId']
            or source.get('productId') != job['productId'] or source.get('jobId') != job['id']
            or any(record.get(k) != expected[k] for k in ('accountId', 'productId', 'jobId', 'snapshotSha256'))
            or any(prepared.get(k) != source.get(k) for k in ('accountId', 'productId', 'sha256', 'jobId'))
            or prepared.get('marketplace') != 'UK' or destination.get('countryCode') != 'GB'
            or prepared.get('store') != source.get('ukTarget', {}).get('storeName')
            or destination.get('destinationId') != (source.get('ukTarget', {}).get('id') or source.get('ukTarget', {}).get('destinationId'))
            or preparation.get('phase') != 'uk_draft_verified' or record.get('ukCopy', {}).get('phase') != 'copy_verified'
            or str(preparation.get('draftId')) != expected['draftId'] or str(record.get('ukCopy', {}).get('draftId')) != expected['draftId']
            or str(publication.get('identity', {}).get('publishId')) != expected['publishId']
            or str(publication.get('sourceLink', {}).get('publishId')) != expected['publishId']
            or str(publication.get('sourceLink', {}).get('draftId')) != expected['draftId']
            or not publication.get('sourceEvidence') or not publication.get('fingerprint')
            or prepared.get('goods', {}).get('parentSku') != source.get('goods', {}).get('parentSku')
            or [(v.get('sku'), v.get('color'), v.get('size')) for v in prepared.get('goodsItems', [])]
               != [(v.get('sku'), v.get('color'), v.get('size')) for v in source.get('goodsItems', [])]
            or len(prepared.get('goodsItems', [])) != profile['count']):
        raise ValueError('编码纠正缺少原英国完整SKU任务、复制、冻结资料或受理身份')
    meta = preparation.get('schemaObservation') or {}
    if (meta.get('country_code'), meta.get('locale'), meta.get('product_type_name'), meta.get('hash')) != (
            'GB', 'en_GB', profile['type'], expected['schemaHash']) or not meta.get('schema_content'):
        raise ValueError('缺少原英国对应商品类型的实际schema')
    return expected, prepared, publication


def read_evidence(workspace, reference):
    if (not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}
            or not isinstance(reference['path'], str) or len(reference['path']) > 2048
            or not re.fullmatch(r'[a-f0-9]{64}', str(reference['sha256']))):
        raise ValueError('编码纠正须提供有限研究JSON路径及SHA')
    workspace = Path(workspace).resolve();path = Path(reference['path'])
    path = (path if path.is_absolute() else workspace / path).resolve()
    try:relative = path.relative_to(workspace)
    except ValueError:raise ValueError('编码证据须在当前工作区研究目录') from None
    if (len(relative.parts) < 2 or not relative.parts[0].startswith('research-') or path.suffix.lower() != '.json'
            or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024):
        raise ValueError('编码证据须为当前工作区有限研究JSON')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference['sha256']:raise ValueError('编码证据SHA变化')
    value = json.loads(raw)
    if not isinstance(value, dict):raise ValueError('编码证据必须为完整JSON对象')
    return value, {'path': str(path), 'sha256': reference['sha256']}


def freeze_scope(job, record, source, evidence, reference):
    expected, prepared, publication = identity_scope(job, record, source)
    profile = _profile(record);count = profile['count'];codes = profile['codes']
    if publication.get('identifierRepair'):raise ValueError('已有编码纠正检查点，不再授权')
    raw = evidence.get('response', {}).get('data') or {};meta = evidence.get('meta') or {}
    failure = evidence.get('failure') or {};latest = publication.get('latestObservation') or publication.get('failureObservation') or {}
    frozen_meta = record['ukPrepare']['schemaObservation']
    def schema(value):
        data = value.get('schema_content');return json.loads(data) if isinstance(data, str) else data
    if (evidence.get('response', {}).get('code') != 0 or evidence.get('sourceFingerprint') != fingerprint(raw)
            or any(meta.get(k) != frozen_meta.get(k) for k in ('hash', 'country_code', 'locale', 'product_type_name'))
            or schema(meta) != schema(frozen_meta)
            or {k: v for k, v in failure.items() if k != 'observedAt'} != {k: v for k, v in latest.items() if k != 'observedAt'}
            or any(str(failure.get(k)) != str(v) for k, v in expected.items() if k not in ('schemaHash', 'jobId'))
            or any(failure.get(k) != v for k, v in {'identityVerified': True, 'failed': True, 'verification': 'failed',
                'status': 'failed', 'childCount': count, 'count': count, 'acceptedCount': 0, 'unscopedMessageCount': 0, 'messageCount': count * len(codes)}.items())
            or str(raw.get('id')) != expected['publishId'] or str(raw.get('uid')) != expected['erpAccountId']
            or str(raw.get('market_id')) != expected['marketId'] or raw.get('country_code') != 'GB'
            or raw.get('market', {}).get('alias') != prepared['store'] or raw.get('sku') != expected['parentSku']
            or raw.get('brand') != prepared['goods']['brand'] or raw.get('product_type_name') != profile['type']):
        raise ValueError('当前原英国编码失败、完整源资料、schema或身份与正式回执不符')
    rows = raw.get('items') or [];children = failure.get('children') or [];variants = prepared['goodsItems']
    if len(rows) != count or len(children) != count or len({str(r.get('id')) for r in rows}) != count:
        raise ValueError('编码纠正缺少完整原子体')
    urls = record['ukPrepare']['urls']
    for row, observed, variant in zip(rows, children, variants):
        images = [urls[prepared['assets'][i]['sha256']] for i in variant['imageIndices']]
        if (row.get('sku') != variant['sku'] or observed.get('sku') != variant['sku']
                or str(row.get('id')) != str(observed.get('childId')) or str(row.get('pid')) != expected['publishId']
                or observed.get('status') != 'failed' or observed.get('imagesSource') != 'child_gallery'
                or len(observed.get('messages') or []) != len(codes)
                or sorted(str(m.get('code')) for m in observed['messages']) != codes
                or row.get('main_image') != images[0] or row.get('extra', {}).get('images') != images
                or observed.get('images') != images or observed.get('main') != images[0]):
            raise ValueError('原SKU、对应编码错误或独立七图范围不符')
        if profile['name']:
            conflict = next(m for m in observed['messages'] if str(m.get('code')) == '100980')
            barcode = str(row.get('standard_product_id') or '').zfill(14)
            if (row.get('status') != 'failed' or row.get('asin') not in (None, '')
                    or re.findall(r'(?<!\d)\d{14}(?!\d)', str(conflict.get('message', ''))) != [barcode]
                    or str(row.get('price')) != str(variant.get('price')) or row.get('quantity') != variant.get('quantity')):
                raise ValueError('100980必须逐子对应当前12位码的14位形式且原价格库存不变')
    original = record['ukCopy'].get('sourceEvidence') or {};original = original.get('data', original)
    if (original.get('country_code') != 'US' or str(original.get('id')) != str(record.get('usPublish', {}).get('publishId'))
            or str(original.get('market_id')) != str(source.get('destination', {}).get('marketId'))
            or str(original.get('uid')) != expected['erpAccountId'] or original.get('sku') != expected['parentSku']
            or [r.get('sku') for r in original.get('items', [])] != [v['sku'] for v in variants]
            or _identifiers(original) != {'standard_product_type': 'UPC', 'standard_product_id': None}
            or any(_identifiers(r) != {'standard_product_type': None, 'standard_product_id': None} for r in original['items'])):
        raise ValueError('原美国编码不是明确原null，不清除已知真实编码')
    introduced = introduced_identifiers(raw);all_rows = [raw] + rows
    if (any(not re.fullmatch(r'\d{12}', str(r.get('standard_product_id') or ''))
                or r.get('standard_product_type') not in (None, 'UPC')
                or r.get('extra', {}).get('attributes', {}).get('brand', [{}])[0].get('value') != prepared['goods']['brand']
                or r.get('extra', {}).get('attributes', {}).get('supplier_declared_has_product_identifier_exemption', [{}])[0].get('value') is not True
                or 'externally_assigned_product_identifier' in r.get('extra', {}).get('attributes', {}) for r in all_rows)
            or len({r['standard_product_id'] for r in all_rows}) != count + 1
            or evidence.get('introducedIdentifiers') != introduced
            or evidence.get('sourceEvidenceFingerprint') != fingerprint(original)):
        raise ValueError('当前英国完整编码、豁免或原美国来源不符')
    if profile['name']:
        if raw.get('asin') not in (None, '') or str(raw.get('price')) != str(variants[0].get('price')):
            raise ValueError('原英国父体ASIN或价格范围不符')
        exemption = existing_allowed_exemption_proof(publication, prepared, expected, evidence.get('freshExemptionCheck'), raw)
    else:
        exemption = exemption_proof(record['ukPrepare'].get('brandExemption') or {}, prepared)
    if evidence.get('exemption') != exemption:raise ValueError('原豁免单次申请证据不符')
    return {**expected, **({'identifierProfile': profile['name'], 'productType': profile['type'], 'childCount': count,
                           'expectedErrorCodes': codes} if profile['name'] else {}),
            'children': [{'id': str(r['id']), 'sku': r['sku']} for r in rows],
            'sourceFingerprint': fingerprint(raw), 'failureResponseFingerprint': failure['responseFingerprint'],
            'sourceEvidenceFingerprint': fingerprint(original), 'sourceIdentifiers': {
                'countryCode': 'US', 'sourceId': str(original['id']), 'parentSku': original['sku'],
                'parent': _identifiers(original), 'children': {r['sku']: _identifiers(r) for r in original['items']}},
            'introducedIdentifiers': introduced, 'exemption': exemption, 'evidence': copy.deepcopy(reference),
            'retryOriginalTaskAfterVerifiedSave': True, 'runtime': {'pythonExecutable': sys.executable}}


def validate_frozen(job, record, source):
    expected, prepared, publication = identity_scope(job, record, source)
    profile = _profile(record)
    amendment = source.get('publicationIdentifierRepair') or {}
    if (not amendment.get('id') or amendment.get('scope') != SCOPE or amendment.get('marketplace') != 'UK'
            or type(amendment.get('authorizedAt')) not in (float, int) or amendment['authorizedAt'] <= 0
            or any(str(amendment.get(k)) != str(v) for k, v in expected.items())
            or amendment.get('retryOriginalTaskAfterVerifiedSave') is not True
            or any(not re.fullmatch(r'[a-f0-9]{64}', str(amendment.get(k) or '')) for k in
                   ('sourceFingerprint', 'sourceEvidenceFingerprint', 'failureResponseFingerprint'))
            or len(amendment.get('children') or []) != profile['count']
            or (profile['name'] and (amendment.get('identifierProfile') != profile['name']
                or amendment.get('productType') != profile['type'] or amendment.get('childCount') != profile['count']
                or amendment.get('expectedErrorCodes') != profile['codes']))
            or (not profile['name'] and amendment.get('identifierProfile') is not None)):
        raise ValueError('原编码纠正冻结授权不完整')
    journal = publication.get('identifierRepair')
    if journal and journal.get('amendmentId') != amendment['id']:raise ValueError('已有另一编码纠正检查点')
    if profile['name']:
        proof = existing_allowed_exemption_proof(publication, prepared, expected,
            (amendment.get('exemption') or {}).get('freshExemptionCheck'), publication.get('sourceEvidence') or {},
            now=amendment['authorizedAt'])
        if amendment.get('exemption') != proof:raise ValueError('原新鲜非申请检查冻结证据已变化')
    return amendment
