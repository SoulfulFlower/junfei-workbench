"""One explicitly authorized later media episode; never reset an older intent."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid

SCOPE = 'retry_original_new_media_failure_episode'
COOLDOWN_SECONDS = 1200
REGIONAL = 'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com'
ACCELERATED = 'https://junfeikuajing.oss-accelerate.aliyuncs.com'
IDENTITY = ('accountId', 'productId', 'jobId', 'snapshotSha256', 'publishId', 'destinationId',
            'draftId', 'erpAccountId', 'marketId', 'countryCode', 'store', 'parentSku')


def read_episode_evidence(workspace, receipt_path, job, record, source, references):
    """Two hashed workspace research JSONs, never an arbitrary file-reading API."""
    if not isinstance(references,dict) or set(references)!={'failureAnchor','mediaReadcheck'}:
        raise ValueError('新媒体恢复须两份完整原失败锚点和图片回读JSON证据')
    workspace=Path(workspace).resolve(); values={}; verified={}
    for name,reference in references.items():
        if (not isinstance(reference,dict) or set(reference)!={'path','sha256'}
                or not isinstance(reference['path'],str) or not reference['path'] or len(reference['path'])>2048
                or not re.fullmatch(r'[a-f0-9]{64}',str(reference['sha256']))):
            raise ValueError('媒体证据只能提供path和SHA256')
        path=Path(reference['path']); path=(path if path.is_absolute() else workspace/path).resolve()
        try: relative=path.relative_to(workspace)
        except ValueError: raise ValueError('媒体证据必须位于当前workspace研究目录') from None
        if (path.suffix.lower()!='.json' or len(relative.parts)<2
                or not (relative.parts[0].startswith('research-') or relative.parts[0]=='artifacts')
                or not path.is_file() or path.stat().st_size>2*1024*1024):
            raise ValueError('媒体证据只读workspace research/artifacts内有限大小JSON')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=reference['sha256']: raise ValueError('媒体证据SHA256不符')
        try: value=json.loads(raw)
        except ValueError: raise ValueError('媒体证据不是有效JSON') from None
        if not isinstance(value,dict): raise ValueError('媒体证据必须是JSON对象')
        values[name]=value;verified[name]={'path':str(path),'sha256':reference['sha256']}
    anchor=values['failureAnchor']; linked=anchor.get('sourceReceiptPath')
    if not isinstance(linked,str):raise ValueError('原失败锚点缺少原回执路径')
    linked=Path(linked); linked=(linked if linked.is_absolute() else workspace/linked).resolve()
    if linked!=Path(receipt_path).resolve():raise ValueError('原失败锚点属于其他任务回执')
    observation=anchor.get('observation'); readcheck=values['mediaReadcheck']
    scope=media_episode_scope(job,record,source,failure_anchor=observation,media_evidence=readcheck)
    if not isinstance(observation,dict):raise ValueError('原失败锚点缺少完整观察')
    expected={}
    for row in scope['failedMedia']:
        for url in (row['originalUrl'],ACCELERATED+urlsplit(row['originalUrl']).path):expected[url]=row
    objects=readcheck.get('objects')
    if not isinstance(objects,list) or len(objects)!=4 or {r.get('url') for r in objects}!=set(expected):
        raise ValueError('图片证据须精确原两对象的双域四个URL')
    for item in objects:
        row=expected[item['url']]; asset=next(a for a in source['assets'] if a['sha256']==row['assetSha256'])
        if (item.get('sku')!=row['sku'] or str(item.get('code'))!=row['code'] or item.get('slot')!=row['slot']
                or item.get('expectedSha256')!=asset['sha256'] or item.get('sha256')!=asset['sha256']
                or item.get('status')!=200 or item.get('finalUrl')!=item['url'] or item.get('decoded') is not True
                or item.get('sameOriginalBytes') is not True or item.get('format')!='PNG'
                or (item.get('width'),item.get('height'))!=(1600,1600)
                or not isinstance(item.get('localPath'),str) or Path(item['localPath']).resolve()!=Path(asset['path']).resolve()):
            raise ValueError('图片证据与原账号SKU、图位、资产或原文件不符')
    if _time(readcheck.get('at'))<_time(readcheck.get('failureObservedAt')):raise ValueError('图片证据时间先于失败观察')
    return observation,readcheck,verified


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('媒体恢复缺少有效观察或原请求时间') from None


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def _identity(job, record, source):
    destination = source.get('destination') or {}
    us = record.get('usPublish') or {}
    expected = dict(accountId=job['accountId'], productId=job['productId'], jobId=job['id'],
                    snapshotSha256=source.get('sha256'), publishId=str(us.get('publishId') or ''),
                    destinationId=job['destinationId'], draftId=str(destination.get('draftId') or ''),
                    erpAccountId=str(destination.get('erpAccountId') or ''), marketId=str(destination.get('marketId') or ''),
                    countryCode='US', store=source.get('store'), parentSku=source.get('goods', {}).get('parentSku'))
    if (any(source.get(k) != expected[k] or record.get(k) != expected[k] for k in ('accountId', 'productId', 'jobId'))
            or record.get('snapshotSha256') != expected['snapshotSha256']
            or destination.get('destinationId') != expected['destinationId'] or destination.get('countryCode') != 'US'
            or not re.fullmatch(r'[1-9]\d*', expected['publishId'])
            or str(us.get('identity', {}).get('publishId')) != expected['publishId']
            or str(us.get('sourceLink', {}).get('publishId')) != expected['publishId']
            or str(us.get('sourceLink', {}).get('draftId')) != expected['draftId'] or not us.get('sourceEvidence')):
        raise ValueError('新媒体恢复缺少原账号、快照及美国父任务完整身份')
    return expected


def _manifest(source):
    assets, urls = source.get('assets'), source.get('urls') or {}
    if not isinstance(assets, list) or len(assets) != 35:
        raise ValueError('须保留原35个图片资产')
    result = []
    for asset in assets:
        sha = asset.get('sha256'); url = urls.get(sha)
        parsed = urlsplit(url or '')
        if (not re.fullmatch(r'[a-f0-9]{64}', str(sha)) or parsed.scheme+'://'+str(parsed.hostname) != REGIONAL
                or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment
                or not parsed.path.startswith('/u/') or asset.get('width') != 1600 or asset.get('height') != 1600):
            raise ValueError('新媒体恢复仅复用原区域对象及原1600像素图片')
        result.append({k: v for k, v in dict(sha256=sha, url=url, width=1600, height=1600).items()})
    if len({r['sha256'] for r in result}) != 35 or len({r['url'] for r in result}) != 35:
        raise ValueError('原图片资产不能唯一对应')
    return result


def _prior_retry_times(us):
    main = us.get('mainImageRepair') or {}; old = us.get('mediaRecovery') or {}; retry = main.get('retry') or {}
    if (main.get('saveVerified') is not True or main.get('persistedSchemaValidation', {}).get('passed') is not True
            or main.get('persistedSchemaValidation', {}).get('checkedCount') != 31
            or str((old.get('intent') or {}).get('publishId'))!=str(us.get('publishId'))
            or str((retry.get('intent') or {}).get('publishId'))!=str(us.get('publishId')) or retry.get('requestAccepted') is not True):
        raise ValueError('须先核对原MAIN已保存且旧恢复和原重试均已消耗，不可替代旧检查点')
    times=[]
    for journal in (old, retry):
        requests=journal.get('nativeRequests')
        if (not isinstance(requests,list) or len(requests)!=1 or requests[0].get('payload')!={'ids':[int(us['publishId'])]}
                or requests[0].get('method')!='POST'
                or requests[0].get('url')!='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish'
                or requests[0].get('response',{}).get('httpStatus')!=200
                or requests[0].get('response',{}).get('body',{}).get('code')!=0):
            raise ValueError('旧原任务重试回执不完整，不能创建另一恢复')
        times.append(_time(requests[0].get('sentAt')))
    return times


def media_episode_scope(job, record, source, *, media_evidence=None, failure_anchor=None, now=None):
    now=time.time() if now is None else now
    expected=_identity(job,record,source); us=record['usPublish']; manifest=_manifest(source)
    if job.get('status') not in ('submitted','failed','needs_reconciliation'):
        raise ValueError('进行中的原任务不能同时建立媒体恢复')
    prior_times=_prior_retry_times(us)
    obs=us.get('latestObservation') or {}
    if (us.get('phase')!='publication_failed' or obs.get('identityVerified') is not True
            or obs.get('failed') is not True or obs.get('verification')!='failed' or obs.get('status')!='failed'
            or any(str(obs.get(k))!=str(v) for k,v in expected.items() if k!='jobId')
            or not re.fullmatch(r'[a-f0-9]{64}',str(obs.get('responseFingerprint')))
            or obs.get('count')!=2 or obs.get('acceptedCount')!=28 or obs.get('childCount')!=30
            or obs.get('messageCount')!=2 or obs.get('unscopedMessageCount')!=0):
        raise ValueError('须最新完整核对原30子体恰2个媒体失败、28个受理')
    children=obs.get('children') or []; variants=source.get('goodsItems') or []
    by_sku={r.get('sku'):r for r in variants}; by_id={r.get('childId'):r for r in children}
    if len(variants)!=30 or len(by_sku)!=30 or len(children)!=30 or len(by_id)!=30 or {r.get('sku') for r in children}!=set(by_sku):
        raise ValueError('原30子SKU身份不完整')
    failed=[]
    for child in children:
        variant=by_sku[child['sku']]
        try: images=[source['urls'][source['assets'][i]['sha256']] for i in variant['imageIndices']]
        except (KeyError,IndexError,TypeError): raise ValueError('原图片映射不完整') from None
        if (len(images)!=7 or len(set(images))!=7 or child.get('imagesSource')!='child_gallery'
                or child.get('images')!=images or child.get('main')!=images[0]
                or (child.get('color'),child.get('size'))!=(variant.get('color'),variant.get('size'))
                or child.get('status') not in ('accepted','failed')
                or bool(child.get('messages'))!=(child['status']=='failed')):
            raise ValueError('须保留原30子SKU各自独立七图与颜色尺码')
        if child['status']=='failed': failed.append(child['childId'])
    if (set(failed)!=set(obs.get('failedChildIds') or []) or len(failed)!=2
            or {by_id[i]['sku'] for i in failed}!=set(obs.get('skus') or [])):
        raise ValueError('失败子体范围不一致')
    messages=obs.get('messages') or []
    if len(messages)!=2 or {str(m.get('code')) for m in messages}!={'20000','18320'} or {m.get('childId') for m in messages}!=set(failed):
        raise ValueError('此次恢复仅支持已核对的20000下载超时及18320主图反馈组合')
    failed_media=[]
    for message in messages:
        child=by_id[message['childId']]
        if message.get('sku')!=child['sku'] or child.get('messages')!=[message]:
            raise ValueError('失败消息未精确归属于原SKU')
        code=str(message['code'])
        if code=='18320':
            amendment=(source.get('publicationMainImageRepair') or {})
            if (child['childId']!=amendment.get('failedChildId') or child['sku']!=amendment.get('failedSku')
                    or child['main']!=amendment.get('mainImageUrl')): raise ValueError('18320不是原已保存的MAIN子体')
            original=child['main']; reported=original; slot=0
        else:
            reported_urls=re.findall(r'https?://[^\s\"\'<>]+',message.get('message',''))
            if len(reported_urls)!=1: raise ValueError('下载失败须有唯一可核对原媒体URL')
            reported=reported_urls[0]; parsed=urlsplit(reported)
            if (parsed.scheme+'://'+str(parsed.hostname) not in (REGIONAL,ACCELERATED) or parsed.username or parsed.password
                    or parsed.port or parsed.query or parsed.fragment): raise ValueError('下载失败URL不是原区域或加速对象')
            candidates=[(i,u) for i,u in enumerate(child['images']) if urlsplit(u).path==parsed.path]
            if len(candidates)!=1: raise ValueError('失败URL不能唯一映射原子SKU图片')
            slot,original=candidates[0]
        asset=next(r for r in manifest if r['url']==original)
        failed_media.append(dict(childId=child['childId'],sku=child['sku'],code=code,slot=slot,
                                 originalUrl=original,reportedUrl=reported,assetSha256=asset['sha256']))
    observed=_time(obs.get('observedAt'))
    # Fresh GETs do not restart the same episode's clock. Only an identical full
    # observation (apart from its read time) can supply the earlier anchor.
    stable=lambda value:{k:v for k,v in value.items() if k!='observedAt'}
    for anchor in (us.get('failureObservation'),failure_anchor):
        if anchor is not None:
            if not isinstance(anchor,dict) or stable(anchor)!=stable(obs):
                if anchor is failure_anchor: raise ValueError('首次失败锚点不属于当前同一完整失败观察')
                continue
            observed=min(observed,_time(anchor.get('observedAt')))
    if media_evidence is not None:
        if not isinstance(media_evidence,dict) or media_evidence.get('allAvailableAndExact') is not True:
            raise ValueError('外部只读图片证据未通过')
        if _time(media_evidence.get('failureObservedAt'))<observed:
            raise ValueError('图片只读证据早于本次失败锚点')
    not_before=max(observed,*prior_times)+COOLDOWN_SECONDS
    if observed>now or now<not_before: raise ValueError('最近失败观察或真实重试后尚未冷却20分钟')
    return {**expected,'marketplace':'US','scope':SCOPE,'nativeScope':'original_parent_family',
            'variantCount':30,'assetCount':35,'failureResponseFingerprint':obs['responseFingerprint'],
            'failedChildIds':copy.deepcopy(obs['failedChildIds']),'failedSkus':copy.deepcopy(obs['skus']),
            'failedMedia':failed_media,'assetManifest':manifest,'failureObservedAt':_iso(observed),
            'cooldownNotBefore':not_before,'cooldownSeconds':COOLDOWN_SECONDS,
            'priorRealRetryAt':_iso(max(prior_times)),'requiresVerifiedOriginalMain':True,
            'saveProductData':False,'replaceImages':False}


def build_media_episode(job, record, source, *, media_evidence=None, failure_anchor=None, now=None):
    if source.get('publicationMediaEpisodes') or (record.get('usPublish') or {}).get('mediaEpisodes'):
        raise ValueError('该原任务已有新媒体episode；保留原授权及意图，只读对账，不能再建')
    scope=media_episode_scope(job,record,source,media_evidence=media_evidence,failure_anchor=failure_anchor,now=now)
    old_fingerprints=[(source.get(key) or {}).get('failureResponseFingerprint') for key in ('publicationRecovery','publicationMainImageRepair')]
    if scope['failureResponseFingerprint'] in old_fingerprints:
        raise ValueError('该失败指纹已有旧授权，不另建episode')
    return {'id':uuid.uuid4().hex,'authorizedAt':time.time() if now is None else now,**scope}


def validate_media_episode(job, record, source, amendment):
    expected=_identity(job,record,source)
    if (not isinstance(amendment,dict) or amendment.get('scope')!=SCOPE or amendment.get('marketplace')!='US'
            or any(amendment.get(k)!=v for k,v in expected.items())
            or not re.fullmatch(r'[a-f0-9]{32}',str(amendment.get('id')))
            or amendment.get('assetManifest')!=_manifest(source)
            or amendment.get('nativeScope')!='original_parent_family' or amendment.get('variantCount')!=30
            or amendment.get('assetCount')!=35 or amendment.get('saveProductData') is not False
            or amendment.get('replaceImages') is not False or amendment.get('requiresVerifiedOriginalMain') is not True):
        raise ValueError('原媒体episode授权身份或资产不符')
    frozen=source.get('publicationMediaEpisodes') or []
    journals=record['usPublish'].get('mediaEpisodes') or []
    if (not isinstance(frozen,list) or not isinstance(journals,list) or len(frozen)!=1 or frozen[0]!=amendment or len(journals)>1
            or journals and journals[0].get('amendmentId')!=amendment['id']):
        raise ValueError('原任务只允许一份独立媒体episode，不覆盖或重建')
    failed_ids,failed_skus,media=amendment.get('failedChildIds'),amendment.get('failedSkus'),amendment.get('failedMedia')
    if (not re.fullmatch(r'[a-f0-9]{64}',str(amendment.get('failureResponseFingerprint')))
            or not isinstance(failed_ids,list) or len(failed_ids)!=2 or len(set(failed_ids))!=2
            or not isinstance(failed_skus,list) or len(failed_skus)!=2 or len(set(failed_skus))!=2
            or not isinstance(media,list) or len(media)!=2 or {m.get('code') for m in media}!={'20000','18320'}
            or {m.get('childId') for m in media}!=set(failed_ids) or {m.get('sku') for m in media}!=set(failed_skus)
            or amendment.get('cooldownSeconds')!=COOLDOWN_SECONDS
            or not isinstance(amendment.get('authorizedAt'),(int,float)) or amendment['authorizedAt']<=0
            or _time(amendment.get('failureObservedAt'))>amendment['authorizedAt']
            or amendment.get('cooldownNotBefore')!=max(_time(amendment['failureObservedAt']),*_prior_retry_times(record['usPublish']))+COOLDOWN_SECONDS):
        raise ValueError('原媒体episode失败范围或冷却合同不完整')
    return amendment
