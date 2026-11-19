"""Read-only image preparation after copy. Never generates, approves or queues work."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from urllib.parse import urlsplit

import agent_center as agent
import agent_handoff
import agent_research
import runtime_environment
import supplier_variants


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def read_task(user, tid):
    if not agent.DB.is_file():
        raise ValueError('任务不存在或无权访问')
    with closing(sqlite3.connect(agent.DB.resolve().as_uri() + '?mode=ro', uri=True)) as c:
        return agent.owned(c, user, tid)


def read_workspace():
    path = agent.DATA / 'studio.sqlite3'
    if not path.is_file():
        raise ValueError('缺少已保存的工作台资料与版本')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as c:
        row = c.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
    if not row or type(row[0]) is not int or row[0] < 0:
        raise ValueError('工作台版本未知，不能绑定图片准备清单')
    return row[0], json.loads(row[1])


def image_policy():
    policy = runtime_environment.configuration(agent.app_paths.APP).get('images', {})
    # Only expose non-secret, non-account policy fields.
    return {key: policy.get(key) for key in ('gallery_count', 'minimum_short_side')}


def inventory(product_id):
    """Read existing journals without creating databases, polling or retrying."""
    records, issues = [], []
    queries = [
        ('visual_studio.sqlite3', 'visual',
         'SELECT r.body FROM runs r JOIN projects p ON p.id=r.project_id WHERE p.product_id=?'),
        ('colour_sets.sqlite3', 'colour', 'SELECT body FROM sets WHERE product_id=?'),
        ('image_jobs.sqlite3', 'submission', 'SELECT body FROM submission_attempts WHERE product_id=?'),
        ('image_jobs.sqlite3', 'image_job', 'SELECT body FROM jobs'),
    ]
    for filename, kind, query in queries:
        path = agent.DATA / filename
        if not path.is_file():
            continue
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as c:
                rows = c.execute(query, () if kind == 'image_job' else (product_id,)).fetchall()
            for (raw,) in rows:
                row = json.loads(raw)
                if not isinstance(row, dict):
                    raise ValueError('invalid journal')
                if kind == 'image_job' and row.get('productId') != product_id:
                    continue
                records.append({'kind': kind, 'id': str(row.get('id', '')),
                                'status': str(row.get('status') or row.get('state') or 'unknown'),
                                'slot': row.get('slot') if type(row.get('slot')) is int else str(row.get('slot'))[:200] if isinstance(row.get('slot'), str) else None,
                                'externalId': str(row.get('externalId') or '') if kind == 'submission' else ''})
        except (sqlite3.Error, ValueError, TypeError):
            issues.append(kind + ' 图片历史无法完整读取，须先核对，不能按无任务处理')
    safe = {'completed', 'approved', 'awaiting_manual', 'needs_revision', 'failed', 'cancelled', 'saved'}
    jobs = {row['id']: row for row in records if row['kind'] == 'image_job'}
    pending = []
    for row in records:
        if row['kind'] == 'submission' and row['status'] == 'recorded':
            job = jobs.get(row['externalId'])
            if not job or job['status'] not in ('completed', 'failed', 'cancelled'):
                pending.append(row)
        elif row['status'] not in safe:
            pending.append(row)
    if pending:
        issues.append('已有进行中或结果未知的图片记录，须核对原任务，不能重复提交')
    return {'records': records, 'issues': issues, 'readOnly': True,
            'providerStatusChecked': False, 'imageBytesChecked': False}


def reference_kind(value):
    if not isinstance(value, str) or not value.strip():
        return None
    if re.fullmatch(r'/uploads/[A-Za-z0-9_.-]+', value) and '..' not in value:
        return 'local_not_opened'
    try:
        url = urlsplit(value)
        if url.scheme == 'https' and url.hostname and not url.username and not url.password:
            return 'remote_not_fetched'
    except ValueError:
        pass
    return None


def build(task, workspace, revision, history, policy):
    """Pure metadata preparation. A ready checklist is never image approval."""
    fresh = agent_research.snapshot(workspace, task)
    agent_handoff.assert_candidate_identity(task, fresh)
    if fresh != task.get('snapshot') or task.get('workspaceRevision') != revision:
        raise ValueError('工作台或文案审核已变化，请更新资料重检后再查看图片准备清单')
    product = fresh['product']
    blockers = list(history['issues'])
    if any(task.get('results', {}).get(key, {}).get('ok') is not True
           for key in ('facts', 'research', 'listing')):
        blockers.append('原任务的选品货源、竞品和文案检查必须全部通过；生成草稿不等于采用及审核')
    for key in ('planningAttempt', 'sourcingAttempt', 'researchAttempt', 'listingAttempt'):
        if key in task and (not isinstance(task[key], dict) or task[key].get('state') != 'saved'):
            blockers.append(key + ' 结果未确认，须先核对原记录')
    count, minimum = policy.get('gallery_count'), policy.get('minimum_short_side')
    if type(count) is not int or not 1 <= count <= 9:
        blockers.append('套图张数配置无效')
        count = None
    if type(minimum) is not int or minimum < 1600:
        blockers.append('图片最小短边配置缺失或低于1600')
    if count is not None and count != 7:
        blockers.append('当前图片审核和导出仍固定检查7张，配置不一致，不能进入制作')
    source = product.get('sourceImport')
    amazon = source.get('amazon') if isinstance(source, dict) else None
    children = amazon.get('variants') if isinstance(amazon, dict) else None
    if not isinstance(children, list) or not children:
        blockers.append('缺少实际采集的颜色尺码子体，不根据颜色和尺码拼出虚构组合')
        children = []
    by_color, seen_skus, seen_pairs, seen_asins = {}, set(), set(), set()
    for child in children:
        if not isinstance(child, dict):
            blockers.append('子体记录格式无效')
            continue
        color = str(child.get('color_name') or '').strip()
        size = str(child.get('size_name') or '').strip()
        sku = child.get('sku')
        asin = child.get('asin')
        if not color or not size:
            blockers.append('实际子体缺少颜色或尺码')
            continue
        key = supplier_variants._colour(color)
        pair = (key, supplier_variants._size(size))
        if pair in seen_pairs:
            blockers.append('子体颜色尺码重复，须核对映射：' + color + ' / ' + size)
        seen_pairs.add(pair)
        if not isinstance(sku, str) or not sku.strip():
            sku = None
            blockers.append('实际子SKU未保存：' + color + ' / ' + size)
        else:
            sku = sku.strip()
            if sku in seen_skus:
                blockers.append('子SKU重复：' + sku)
            seen_skus.add(sku)
        if not isinstance(asin, str) or not re.fullmatch('[A-Z0-9]{10}', asin):
            blockers.append('来源子体ASIN无效：' + color + ' / ' + size)
        elif asin in seen_asins:
            blockers.append('来源子体ASIN重复：' + asin)
        seen_asins.add(asin if isinstance(asin, str) else '')
        item = by_color.setdefault(key, {'color': color, 'children': [], 'references': []})
        item['children'].append({'sku': sku, 'size': size, 'sourceAsin': asin if isinstance(asin, str) else None})
    declared = re.split(r'[,，、;；\n]', str(product.get('colorNames') or ''))
    for color in (value.strip() for value in declared if value.strip()):
        if supplier_variants._colour(color) not in by_color:
            blockers.append('已声明颜色没有实际子体，未自动剔除：' + color)
    references = product.get('supplierColorReferences', [])
    bindings = product.get('assetColorBindings', {})
    if not isinstance(references, list) or not isinstance(bindings, dict):
        blockers.append('颜色素材映射格式无效')
        references, bindings = [], {}
    mapped_urls, unused = {}, []
    for index, ref in enumerate(references):
        if not isinstance(ref, dict):
            blockers.append('来源图记录格式无效')
            continue
        url = ref.get('url')
        color = bindings.get(url) if isinstance(url, str) else None
        color = color or ref.get('color')
        key = supplier_variants._colour(color)
        kind = reference_kind(url)
        if not key or not kind:
            blockers.append('第' + str(index + 1) + '条来源图缺有效颜色或安全素材定位符')
            continue
        if url in mapped_urls and mapped_urls[url] != key:
            blockers.append('同一来源图被映射到不同颜色，须核对真实颜色')
        mapped_urls[url] = key
        metadata = {'sourceIndex': index, 'locatorSha256': digest(url), 'kind': kind,
                    'pixelsVerified': False}
        if key not in by_color:
            unused.append({'sourceIndex': index, 'color': str(color)})
        else:
            by_color[key]['references'].append(metadata)
    master = product.get('masterColor')
    master_key = supplier_variants._colour(master)
    if master_key not in by_color:
        blockers.append('母版颜色未明确绑定到实际子体')
    sets = sorted(by_color.items(), key=lambda item: (item[0] != master_key, item[0]))
    for key, item in sets:
        if not item['references']:
            blockers.append('缺少该颜色真实素材映射：' + item['color'])
        item['role'] = 'master' if key == master_key else 'full_colour_set_after_master_review'
        item['slots'] = [{'slot': index, 'label': '白底主图' if index == 0 else '辅图' + str(index),
                          'status': 'not_evaluated', 'approved': False}
                         for index in range(count or 0)]
    try:
        coverage = supplier_variants.inspect(product)
        blockers.extend(coverage['issues'])
    except (TypeError, ValueError, AttributeError, KeyError):
        blockers.append('货源变体记录格式无效，未核对库存或可售状态')
    return {'schemaVersion': 1, 'preparationOnly': True, 'readOnly': True,
            'taskId': task['id'], 'productId': task['productId'],
            'marketplace': task['profile']['marketplace'], 'store': task['profile']['store'],
            'workspaceRevision': revision, 'snapshotSha256': digest(fresh),
            'inputSha256': digest({'task': task, 'snapshot': fresh, 'policy': policy, 'history': history}),
            'readyForManualPreparation': not blockers, 'blockers': list(dict.fromkeys(blockers)),
            'executionAllowed': False, 'paidCallsAllowed': False, 'productionReady': False,
            'imagesReady': False, 'humanReviewed': False, 'stockVerified': False,
            'budget': {'taskBudgetCny': task.get('budgetCny'), 'allPaidPathsHardCapped': False,
                       'imageSpendAuthorized': False, 'newReservations': 0},
            'galleryCountPerColor': count, 'minimumShortSide': minimum,
            'plannedColorCount': len(sets),
            'plannedImageCount': len(sets) * count if count is not None else None,
            'masterColor': master if isinstance(master, str) else None,
            'sets': [item for _, item in sets], 'unusedReferenceMappings': unused,
            'history': history,
            'nextSteps': ['先核对并完成母版颜色的整套图及审核',
                          '母版确认后逐色制作完整套图，保留同色实际子SKU映射',
                          '再检查真实图片、内容审核、费用和导出要求'],
            'note': '仅核对已保存的元数据；未读取图片像素、下载素材、核实库存、预留费用或创建图片任务。清单不是成图、审核、预算硬封顶或发布授权。'}


def preview(user, tid, expected_revision):
    with agent.LOCK:
        try:
            task = read_task(user, tid)
            if (task.get('executionScope') != agent_handoff.SCOPE
                    or not isinstance(task.get('copyHandoff'), dict)
                    or task['copyHandoff'].get('scope') != agent_handoff.SCOPE
                    or task.get('taskMode') != 'production' or task.get('status') != 'blocked'
                    or tid in agent.ACTIVE):
                raise ValueError('仅已停止的原选品到文案任务可查看图片准备清单')
            if (task.get('exportAvailable') or task.get('junfeiPlanAvailable')
                    or 'erpObservation' in task
                    or any(key in task.get('results', {}) for key in ('images', 'export', 'junfeiPreflight', 'publish', 'verify'))):
                raise ValueError('已有图片阶段或交付/ERP记录，请核对原流程，不作为新图片准备入口')
            revision, workspace = read_workspace()
            if type(expected_revision) is not int or expected_revision != revision:
                raise ValueError('工作台版本已变化，请刷新后重新预览')
            policy = image_policy()
            history = inventory(task['productId'])
            result = build(task, workspace, revision, history, policy)
            if read_workspace() != (revision, workspace) or read_task(user, tid) != task or image_policy() != policy or inventory(task['productId']) != history:
                raise ValueError('准备期间任务、工作台或配置已变化，请刷新后重试')
            return result
        except sqlite3.Error:
            raise ValueError('本地资料无法完整只读读取，未创建或恢复任务') from None
