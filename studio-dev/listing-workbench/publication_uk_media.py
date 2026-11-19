"""One independent original-UK media retry; no browser, network or DB writes."""
import copy
import re
import sys
import time
import uuid
from urllib.parse import urlsplit
import publication_identifiers as identifiers
from publication_media_episode import COOLDOWN_SECONDS, REGIONAL, ACCELERATED, _time, _iso

SCOPE = 'retry_original_uk_failed_media_once'
IDENTITY = identifiers.IDENTITY


def context(job, record, source):
    expected, prepared, publication = identifiers.identity_scope(job, record, source)
    if (len(prepared['goodsItems']) != 75
            or record['ukPrepare']['schemaObservation'].get('product_type_name') != 'SWEATSHIRT'):
        raise ValueError('英国媒体恢复仅支持原SWEATSHIRT75任务')
    return expected, {**prepared, 'urls': record['ukPrepare']['urls']}, publication


def manifest(prepared):
    assets = prepared.get('assets') or []; urls = prepared.get('urls') or {}
    result = []
    for asset in assets:
        sha = asset.get('sha256'); url = urls.get(sha); u = urlsplit(url or '')
        if (not re.fullmatch(r'[a-f0-9]{64}', str(sha)) or u.scheme+'://'+str(u.hostname) != REGIONAL
                or u.username or u.password or u.port or u.query or u.fragment or not u.path.startswith('/u/')
                or asset.get('width') != 1600 or asset.get('height') != 1600):
            raise ValueError('英国媒体恢复须复用原区域对象、SHA与1600像素图片')
        result.append({'sha256': sha, 'url': url, 'width': 1600, 'height': 1600})
    # The original 105 positions legitimately share one neutral image across
    # colours (91 unique files). Keep every position; do not manufacture files.
    if len(result) != 105 or len({a['url'] for a in result}) != len({a['sha256'] for a in result}):
        raise ValueError('英国原105图片图位不完整或同URL对应不同内容')
    return result


def prior_repair(publication):
    journal = publication.get('identifierRepair') or {}; retry = journal.get('retry') or {}
    requests = retry.get('nativeRequests') or []; publish_id = str(publication.get('publishId'))
    if (journal.get('saveVerified') is not True or not journal.get('plannedSource')
            or retry.get('requestAccepted') is not True or len(requests) != 1
            or requests[0].get('method') != 'POST'
            or requests[0].get('url') != 'https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish'
            or requests[0].get('payload') != {'ids': [int(publish_id)]}
            or requests[0].get('response', {}).get('httpStatus') != 200
            or requests[0].get('response', {}).get('body', {}).get('code') != 0):
        raise ValueError('原英国编码修复及已消耗重试回执未完整确认，不能另建媒体恢复')
    return journal['plannedSource'], _time(requests[0].get('sentAt'))


def scope(job, record, source, *, anchor=None, now=None):
    now = time.time() if now is None else now
    expected, prepared, publication = context(job, record, source)
    assets = manifest(prepared); preserved, last_retry = prior_repair(publication)
    obs = publication.get('latestObservation') or {}
    if (job.get('status') not in ('submitted', 'failed', 'needs_reconciliation')
            or publication.get('phase') != 'publication_failed' or obs.get('identityVerified') is not True
            or obs.get('failed') is not True or obs.get('verification') != 'failed' or obs.get('status') != 'failed'
            or any(str(obs.get(k)) != str(v) for k, v in expected.items() if k not in ('jobId', 'schemaHash'))
            or obs.get('count') != 1 or obs.get('acceptedCount') != 74 or obs.get('childCount') != 75
            or obs.get('unscopedMessageCount') != 0
            or not re.fullmatch(r'[a-f0-9]{64}', str(obs.get('responseFingerprint')))):
        raise ValueError('须先核对原英国75子体恰1失败、74受理的完整最新媒体观察')
    variants = {v['sku']: v for v in prepared['goodsItems']}; children = obs.get('children') or []
    if (len(variants) != 75 or len(children) != 75 or len({c.get('childId') for c in children}) != 75
            or {c.get('sku') for c in children} != set(variants)):
        raise ValueError('英国媒体恢复原75子SKU身份不完整')
    failed = []
    for child in children:
        v = variants[child['sku']]
        images = [prepared['urls'][prepared['assets'][i]['sha256']] for i in v['imageIndices']]
        if (len(images) != 7 or len(set(images)) != 7 or child.get('imagesSource') != 'child_gallery'
                or child.get('images') != images or child.get('main') != images[0]
                or (child.get('color'), child.get('size')) != (v.get('color'), v.get('size'))
                or child.get('status') not in ('accepted', 'failed')
                or bool(child.get('messages')) != (child['status'] == 'failed')):
            raise ValueError('英国原75子SKU颜色尺码或独立七图不符')
        if child['status'] == 'failed': failed.append(child)
    if (len(failed) != 1 or obs.get('failedChildIds') != [failed[0]['childId']]
            or obs.get('skus') != [failed[0]['sku']]):
        raise ValueError('英国失败子体与原SKU范围不符')
    child = failed[0]; messages = obs.get('messages') or []
    if messages != child.get('messages') or obs.get('messageCount') != len(messages):
        raise ValueError('英国媒体失败消息归属不完整')
    errors = [m for m in messages if m.get('code') == '300060' and m.get('severity') == 'ERROR']
    warnings = [m for m in messages if m.get('code') == '18448' and m.get('severity') == 'WARNING'
                and re.search(r'(?<![A-Za-z_])material(?![A-Za-z_])', m.get('message', ''))]
    if len(errors) != 6 or len(warnings) > 1 or len(errors)+len(warnings) != len(messages):
        raise ValueError('英国此范围只支持六条300060及明确不阻止展示的material提醒')
    if warnings and '不会阻止' not in warnings[0]['message']:
        raise ValueError('英国材质提醒未明确为非阻断信息')
    media = []
    for message in errors:
        urls = re.findall(r'https?://[^\s\"\'<>]+', message.get('message', ''))
        if len(urls) != 1:raise ValueError('英国媒体错误缺少唯一原URL')
        reported = urls[0]; u = urlsplit(reported)
        if (u.scheme+'://'+str(u.hostname) not in (REGIONAL, ACCELERATED) or u.username or u.password
                or u.port or u.query or u.fragment):raise ValueError('英国媒体错误URL不是原区域或加速对象')
        matches = [(i, url) for i, url in enumerate(child['images']) if urlsplit(url).path == u.path]
        if len(matches) != 1 or message.get('sku') != child['sku'] or message.get('childId') != child['childId']:
            raise ValueError('英国媒体错误不属于原失败SKU图片')
        slot, original = matches[0]; asset = next(a for a in assets if a['url'] == original)
        media.append(dict(childId=child['childId'], sku=child['sku'], code='300060', slot=slot,
                          originalUrl=original, reportedUrl=reported, assetSha256=asset['sha256']))
    media.sort(key=lambda m: m['slot'])
    if len({m['slot'] for m in media}) != 6:raise ValueError('英国六个报错图片不唯一')
    observed = _time(obs.get('observedAt'))
    if anchor is not None:
        if (not isinstance(anchor, dict) or {k:v for k,v in anchor.items() if k != 'observedAt'}
                != {k:v for k,v in obs.items() if k != 'observedAt'}):
            raise ValueError('英国首次失败锚点不是同一完整观察')
        observed = min(observed, _time(anchor.get('observedAt')))
    not_before = max(observed, last_retry)+COOLDOWN_SECONDS
    if observed > now or now < not_before:raise ValueError('原英国媒体失败或真实重试后尚未冷却20分钟')
    return {**expected, 'marketplace': 'UK', 'scope': SCOPE, 'nativeScope': 'original_parent_family',
            'variantCount': 75, 'assetCount': 105, 'failureResponseFingerprint': obs['responseFingerprint'],
            'failedChildIds': [child['childId']], 'failedSkus': [child['sku']], 'failedMedia': media,
            'originalFailureObservation': copy.deepcopy(obs),
            'nonBlockingWarnings': copy.deepcopy(warnings), 'assetManifest': assets,
            'preservedSource': copy.deepcopy(preserved), 'failureObservedAt': _iso(observed),
            'priorRealRetryAt': _iso(last_retry), 'cooldownSeconds': COOLDOWN_SECONDS,
            'cooldownNotBefore': not_before, 'saveProductData': False, 'replaceImages': False}


def read_evidence(workspace, job, record, source, references, *, now=None):
    if not isinstance(references, dict) or set(references) != {'failureAnchor', 'mediaReadcheck'}:
        raise ValueError('英国媒体恢复须原失败锚点和六图片完整SHA证据')
    anchor_file, _ = identifiers.read_evidence(workspace, references['failureAnchor'])
    readcheck, _ = identifiers.read_evidence(workspace, references['mediaReadcheck'])
    matches = [v for v in anchor_file.get('observations', []) if v.get('jobId') == job['id']
               and (v.get('observation') or {}).get('publishId') == str(record.get('ukPublish', {}).get('publishId'))]
    if anchor_file.get('accountId') != job['accountId'] or len(matches) != 1:
        raise ValueError('英国原失败锚点属于其他账号或任务')
    anchor = copy.deepcopy(matches[0].get('observation'))
    # An offline parser may construct its observation after the actual GET.
    # The guarded capture's own recorded read time anchors the episode, while
    # every identity/message/image field still has to match the canonical read.
    if matches[0].get('observedAt'):
        captured = matches[0]['observedAt']
        if (_time(captured) > _time(anchor.get('observedAt'))
                or readcheck.get('failureObservedAt') != captured):
            raise ValueError('英国首次实际读取时间与图片回读证据不符')
        anchor['observedAt'] = captured
    result = scope(job, record, source, anchor=anchor, now=now)
    if (readcheck.get('accountId') != job['accountId'] or readcheck.get('jobId') != job['id']
            or readcheck.get('publishId') != result['publishId'] or readcheck.get('sku') != result['failedSkus'][0]
            or readcheck.get('failureResponseFingerprint') != result['failureResponseFingerprint']
            or readcheck.get('allSixPassed') is not True or readcheck.get('requestCount') != 6
            or _time(readcheck.get('startedAt')) < _time(result['failureObservedAt'])):
        raise ValueError('英国六图片证据不属于原任务本次失败')
    objects = readcheck.get('objects') or []; expected = {m['reportedUrl']: m for m in result['failedMedia']}
    if len(objects) != 6 or {v.get('url') for v in objects} != set(expected):raise ValueError('英国六图片URL证据不完整')
    _, prepared, _ = context(job, record, source)
    for obj in objects:
        m = expected[obj['url']]; response = obj.get('response') or {}; decoded = obj.get('decoded') or {}
        asset = next(a for a in prepared['assets'] if a['sha256'] == m['assetSha256'])
        if (any(obj.get(k) != m[k] for k in ('sku', 'childId', 'slot', 'code'))
                or obj.get('localPath') != asset.get('path') or obj.get('sha256') != asset['sha256']
                or obj.get('expectedSha256') != asset['sha256'] or obj.get('localSha256') != asset['sha256']
                or obj.get('sameOriginalBytes') is not True or obj.get('officialVerifierPassed') is not True
                or response.get('status') != 200 or response.get('finalUrl') != obj['url']
                or response.get('bodySha256') != asset['sha256'] or not response.get('bodyBytes', 0) > 0
                or decoded.get('passed') is not True or decoded.get('fullPillowDecode') is not True
                or (decoded.get('format'), decoded.get('width'), decoded.get('height')) != ('PNG', 1600, 1600)):
            raise ValueError('英国媒体完整响应、原SHA或图片解码证明不符')
    return result


def freeze(job, record, source, workspace, references, *, now=None):
    if source.get('publicationUkMediaRecovery') or record.get('ukPublish', {}).get('mediaRecovery'):
        raise ValueError('原英国已有唯一媒体恢复授权或检查点，不另建或覆盖')
    result = read_evidence(workspace, job, record, source, references, now=now)
    return {**result, 'id': uuid.uuid4().hex, 'authorizedAt': time.time() if now is None else now,
            'evidence': copy.deepcopy(references), 'runtime': {'pythonExecutable': sys.executable}}


def validate(job, record, source):
    expected, prepared, publication = context(job, record, source)
    amendment = source.get('publicationUkMediaRecovery') or {}; preserved, last = prior_repair(publication)
    if (any(amendment.get(k) != v for k,v in expected.items())
            or not re.fullmatch(r'[a-f0-9]{32}', str(amendment.get('id')))
            or amendment.get('scope') != SCOPE or amendment.get('marketplace') != 'UK'
            or amendment.get('nativeScope') != 'original_parent_family' or amendment.get('variantCount') != 75
            or amendment.get('assetCount') != 105 or amendment.get('assetManifest') != manifest(prepared)
            or amendment.get('preservedSource') != preserved or amendment.get('saveProductData') is not False
            or amendment.get('replaceImages') is not False or amendment.get('cooldownSeconds') != COOLDOWN_SECONDS
            or amendment.get('cooldownNotBefore') != max(_time(amendment.get('failureObservedAt')), last)+COOLDOWN_SECONDS
            or not isinstance(amendment.get('authorizedAt'), (int,float))
            or amendment['authorizedAt'] < amendment['cooldownNotBefore']):
        raise ValueError('原英国媒体恢复冻结身份、原业务资料或冷却合同不符')
    if (set(amendment.get('runtime') or {}) != {'pythonExecutable'}
            or not isinstance(amendment['runtime']['pythonExecutable'], str)
            or not amendment['runtime']['pythonExecutable']):
        raise ValueError('原英国媒体恢复缺少服务端冻结的Python运行路径')
    journal = publication.get('mediaRecovery')
    if journal and (journal.get('amendmentId') != amendment['id'] or journal.get('amendment') != amendment):
        raise ValueError('原英国媒体恢复检查点不属于该唯一授权')
    original = amendment.get('originalFailureObservation')
    frozen_record = copy.deepcopy(record); frozen_job = {**job, 'status': 'needs_reconciliation'}
    frozen_record['ukPublish'].update(phase='publication_failed', latestObservation=original)
    anchor = copy.deepcopy(original)
    if not isinstance(anchor, dict):raise ValueError('原英国媒体恢复缺少完整冻结失败观察')
    anchor['observedAt'] = amendment['failureObservedAt']
    checked = scope(frozen_job, frozen_record, source, anchor=anchor, now=amendment['authorizedAt'])
    if any(amendment.get(k) != v for k,v in checked.items()):
        raise ValueError('原英国媒体恢复冻结失败范围已改变')
    return amendment
