"""Opt-in public 1688 source collection, durable and scoped to the task snapshot."""
import copy
import hashlib
import json
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from contextlib import closing
from urllib.parse import urlsplit, quote_plus
import agent_center as agent
from agent_research import digest, snapshot
import importer


def sales_signal(raw):
    """Keep the displayed sales scope and lower bound; never infer variant sales."""
    raw = str(raw or '')
    for basis, pattern in (
        ('offer_sold', r'(已售|成交)\s*(\d+(?:\.\d+)?)\s*(万|千)?\s*\+?\s*(?:件|块|片|套|笔|单)?'),
        ('cross_network', r'(全网(?:销量)?)\s*(\d+(?:\.\d+)?)\s*(万|千)?\s*\+?\s*(?:件|块|片|套)?'),
    ):
        match = re.search(pattern, raw)
        if match:
            scale = {'万': 10000, '千': 1000}.get(match[3], 1)
            return {'basis': basis, 'lowerBound': float(match[2]) * scale, 'raw': match[0]}
    return None


def rank_candidates(ranked, score_key):
    import agent_selection
    policy = agent_selection.current_policy().get('sourcingPolicy', {})
    if policy.get('supplier_selection_policy') == 'public_sales_descending':
        # Prefer offer-specific counts. Do not silently compare cross-network
        # counts with this offer's sales. Similarity only breaks equal counts.
        basis = 'offer_sold' if any((x.get('sales') or {}).get('basis') == 'offer_sold' for x in ranked) else 'cross_network'
        for item in ranked:
            item['salesRankingBasis'] = basis
        ranked.sort(key=lambda x: (
            -int((x.get('sales') or {}).get('basis') == basis),
            -(x.get('sales') or {}).get('lowerBound', 0) if (x.get('sales') or {}).get('basis') == basis else 0,
            -x.get(score_key, 0), x.get('url', '')))
    else:
        ranked.sort(key=lambda x: (-x.get(score_key, 0), -x.get('lexicalScore', 0), x.get('title', ''), x.get('url', '')))
    return ranked


def _terms(value):
    """Tokenize English words and Chinese character bigrams for local ranking."""
    text = str(value or '').lower()
    words = set(re.findall(r'[a-z0-9]+', text))
    for run in re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]+', text):
        if len(run) == 1:
            words.add(run)
        else:
            words.update(run[i:i + 2] for i in range(len(run) - 1))
    return words


def _millimetres(value):
    """Read every axis, including shared suffix units (50 x 100 cm)."""
    unit = r'(?:millimeters?|millimetres?|centimeters?|centimetres?|inches|inch|毫米|厘米|公分|英寸|米|mm|cm|in|m|\")'
    text = str(value or '').lower()
    # Expand only a number chain with an explicit trailing unit. Individual
    # mixed-unit axes such as 45mm x 5m are handled by the normal scan below.
    def expand(match):
        return ' x '.join(number + match[2] for number in re.findall(r'\d+(?:\.\d+)?', match[1]))
    text = re.sub(r'(?<![\d.])((?:\d+(?:\.\d+)?\s*[x×✕*]\s*)+\d+(?:\.\d+)?)\s*(' + unit + r')(?![a-z])', expand, text)
    # Chinese card text often directly prefixes measurements with words such
    # as "宽" or "长", so only prevent splitting a longer numeric value.
    matches = re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(' + unit + r')(?![a-z])', text)
    result = Counter()
    for number, unit in matches:
        scale = 1 if unit in ('mm', 'millimeter', 'millimeters', 'millimetre', 'millimetres', '毫米') else 10 if unit in ('cm', 'centimeter', 'centimeters', 'centimetre', 'centimetres', '厘米', '公分') else 25.4 if unit in ('in', 'inch', 'inches', '英寸', '"') else 1000
        result[round(float(number) * scale, 3)] += 1
    return result


def _dimensions_match(expected, observed):
    dimensions = _millimetres(expected)
    if dimensions:
        return dimensions <= _millimetres(observed)
    return str(expected).strip().casefold() == str(observed).strip().casefold()


def _attribute_signals(product, candidate_title):
    """Match explicitly supplied product attributes in the visible supplier title."""
    title = re.sub(r'[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+', '',
                   str(candidate_title or '').lower().replace('×', 'x').replace('✕', 'x'))
    labels = {'material': '材质', 'dimensions': '尺寸', 'colorNames': '颜色', 'sizeNames': '尺码'}
    known, matched = [], []
    placeholders = {'unknown', 'n/a', 'na', 'not specified', '未确认', '未知', '待补', '不详'}
    for key, label in labels.items():
        value = product.get(key)
        if isinstance(value, (list, tuple)):
            values = value
        elif isinstance(value, str):
            # Don't split Chinese descriptions into fragments; list delimiters are explicit.
            values = re.split(r'[,，;；|/]+', value)
        else:
            continue
        for item in values:
            value = str(item or '').strip()
            if value.casefold() in placeholders:
                continue
            normalized = re.sub(r'[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+', '',
                                value.lower().replace('×', 'x').replace('✕', 'x'))
            if len(normalized) < 2 or len(normalized) > 80:
                continue
            record = {'field': key, 'label': label, 'value': value[:80]}
            known.append(record)
            matched_value = normalized in title
            if key == 'dimensions':
                matched_value = _dimensions_match(value, candidate_title)
            if matched_value:
                matched.append(record)
    return known, matched


def observed_candidates(product):
    """Rank already captured 1688 image-search offers without verifying them.

    This only organizes account-owned browser observations. It never fetches a
    supplier page or promotes an offer to verified sourcing evidence.
    """
    listing = product.get('listing') if isinstance(product.get('listing'), dict) else {}
    target = ' '.join(str(listing.get('title') or product.get('name') or '').split())
    target_terms = _terms(target)
    ranked, seen = [], set()
    for observation in product.get('selectionObservations') or []:
        if not isinstance(observation, dict) or observation.get('captureType') != 'browser_1688_image_search':
            continue
        sourcing = observation.get('sourcingSearch')
        if not isinstance(sourcing, dict):
            continue
        for offer in (sourcing.get('offers') or []):
            if not isinstance(offer, dict):
                continue
            url = str(offer.get('url') or '').strip()
            if not url or url in seen:
                continue
            seen.add(url)
            title = str(offer.get('title') or '').strip()
            words = _terms(title)
            shared = sorted(target_terms & words)
            score = round(len(shared) / max(len(target_terms), 1), 4)
            card_text = str(offer.get('raw') or '')
            known_attributes, matched_attributes = _attribute_signals(product, title + ' ' + card_text)
            attribute_coverage = round(len(matched_attributes) / len(known_attributes), 4) if known_attributes else None
            triage_score = round(score if attribute_coverage is None else score * 0.65 + attribute_coverage * 0.35, 4)
            ranked.append({
                'url': url,
                'offerId': str(offer.get('offerId') or '').strip(),
                'title': title[:240],
                'priceText': str(offer.get('priceText') or '')[:160],
                'sales': sales_signal(card_text),
                'supplierText': str(offer.get('supplierText') or '')[:240],
                'imageUrl': str(offer.get('imageUrl') or '')[:1000],
                'lexicalScore': score,
                'matchedTerms': shared[:30],
                'attributeCoverage': attribute_coverage,
                'matchedAttributes': matched_attributes,
                'attributeEvidence': 'title_and_visible_card_text' if card_text else 'title',
                'rankSignals': ['title_terms'] + (['known_product_attributes'] if known_attributes else []),
                'triageScore': triage_score,
                'status': 'unverified_observation',
            })
    rank_candidates(ranked, 'triageScore')
    return ranked[:6]


def source_url(product):
    raw = product.get('sourceUrl') or product.get('sourceImport', {}).get('supplier', {}).get('url', '')
    if not isinstance(raw, str): return None
    try:
        url = urlsplit(raw.strip())
        if url.scheme == 'https' and url.netloc == 'detail.1688.com' and re.fullmatch(r'/offer/\d+\.html', url.path):
            return 'https://detail.1688.com' + url.path
    except ValueError:
        pass
    return None


def search_plan(product):
    """Build a browser handoff for sourcing when no supplier URL is saved.

    This is a navigation aid only: it does not claim a match, fetch a supplier,
    or promote any result into verified sourcing evidence.
    """
    listing = product.get('listing') if isinstance(product.get('listing'), dict) else {}
    title = str(listing.get('title') or product.get('name') or '').strip()
    # Keep the handoff readable and avoid carrying markup or an unbounded title.
    title = re.sub(r'\s+', ' ', title).strip()[:120]
    if not title:
        return None
    query = title
    return {
        'status': 'needs_browser',
        'query': query,
        'keywordUrl': 'https://s.1688.com/selloffer/offer_search.htm?keywords=' + quote_plus(query),
        'imageSearchUrl': 'https://s.1688.com/selloffer/offer_search.htm',
        'method': 'keyword_plus_image_search',
        'observedCandidates': observed_candidates(product),
        'requiresBrowserReview': True,
        'warning': '搜索计划仅用于打开1688并人工筛选；不证明同款、价格、供货、重量或图片权利。'
    }


def report(user, tid):
    with agent.LOCK, closing(agent.connect()) as c:
        task = agent.owned(c, user, tid)
    if not task.get('sourcingReportAvailable'): raise ValueError('没有已保存的货源报告')
    raw = (agent.DATA/'agent-results'/tid/'sourcing-report.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != task['sourcingAttempt']['sha256']:
        raise ValueError('货源报告校验失败，请核对')
    return json.loads(raw)


def save_plan(user, task, plan):
    """Persist a browser sourcing handoff without treating it as supplier evidence."""
    if not plan:
        raise ValueError('无法生成货源搜索计划')
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True).encode('utf-8')
    folder = agent.DATA / 'agent-results' / task['id']
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'sourcing-plan.json'
    digest_value = hashlib.sha256(raw).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest_value:
            raise ValueError('货源搜索计划已变化，请先核对旧计划')
    else:
        path.write_bytes(raw)
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        current['sourcingPlanAvailable'] = True
        current['sourcingPlanSha256'] = digest_value
        agent.put(c, current)
        if not current.get('sourcingPlanRecorded'):
            current['sourcingPlanRecorded'] = True
            agent.event(c, current, 'sourcing_plan_saved', '1688货源搜索计划已保存；未认定同款或供应商', sha256=digest_value)
            agent.put(c, current)
    return plan


def plan_report(user, tid):
    with agent.LOCK, closing(agent.connect()) as c:
        task = agent.owned(c, user, tid)
    if not task.get('sourcingPlanAvailable'):
        raise ValueError('没有已保存的货源搜索计划')
    raw = (agent.DATA / 'agent-results' / tid / 'sourcing-plan.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != task.get('sourcingPlanSha256'):
        raise ValueError('货源搜索计划文件已变更，请核对')
    return json.loads(raw)


def probe_observed_candidates(user, task, product, candidates):
    """Read at most three already-captured public 1688 details; never adopt them."""
    ranked = []
    seen = set()
    for item in candidates:
        safe_url = source_url({'sourceUrl': item.get('url')})
        if safe_url and safe_url not in seen:
            seen.add(safe_url)
            ranked.append({**item, 'url': safe_url})
        if len(ranked) >= 3:
            break
    if not ranked:
        return {}
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        state = current.get('sourcingCandidateProbe')
        if state:
            if state.get('productHash') != digest(task['snapshot']['product']):
                return {}
        else:
            if current['status'] != 'running':
                return {}
            if snapshot(agent.load_workspace(), task) != task['snapshot']:
                return {}
            state = {'state': 'started', 'at': time.time(),
                     'productHash': digest(task['snapshot']['product']),
                     'items': [{'url': item['url'], 'title': item.get('title', '')[:240],
                                'offerId': item.get('offerId', ''), 'status': 'pending'}
                               for item in ranked]}
            current['sourcingCandidateProbe'] = state
            agent.put(c, current)
            agent.event(c, current, 'sourcing_candidates_probe_started',
                        '开始只读检查最多3个已采集的1688候选详情；不采用货源、不改产品参数',
                        urls=[item['url'] for item in ranked])

    # A per-candidate started marker prevents a process interruption from
    # silently issuing the same page request again on resume.
    for index, item in enumerate(ranked):
        with agent.LOCK, closing(agent.connect()) as c, c:
            current = agent.owned(c, user, task['id'])
            state = current.get('sourcingCandidateProbe') or {}
            saved = state.get('items', [])
            if index >= len(saved) or saved[index].get('url') != item['url']:
                continue
            if saved[index].get('status') != 'pending':
                continue
            saved[index]['status'] = 'reading'
            saved[index]['startedAt'] = time.time()
            agent.put(c, current)
        try:
            supplier = importer.read_supplier(item['url'])
            summary = {'title': str(supplier.get('title') or '')[:500],
                       'attributes': {str(k)[:100]: str(v)[:500] for k, v in
                                      list((supplier.get('attributes') or {}).items())[:40]},
                       'imageCount': len(supplier.get('images') or []),
                       'captureMethod': supplier.get('captureMethod')}
            outcome = {'status': 'collected', 'supplier': summary,
                       'captureSha256': digest(supplier),
                       'checkedAt': datetime.now(timezone.utc).isoformat(),
                       'limitations': '公开详情页观察；未核实变体、结算价、供货能力、毛重或图片权利'}
        except Exception:
            outcome = {'status': 'needs_browser',
                       'checkedAt': datetime.now(timezone.utc).isoformat(),
                       'limitations': '公开读取失败或页面要求登录/验证；请在已登录浏览器打开详情并采集'}
        with agent.LOCK, closing(agent.connect()) as c, c:
            current = agent.owned(c, user, task['id'])
            saved = current.get('sourcingCandidateProbe', {}).get('items', [])
            if index < len(saved) and saved[index].get('url') == item['url'] and saved[index].get('status') == 'reading':
                saved[index].update(outcome)
                saved[index]['status'] = outcome['status']
                agent.put(c, current)
                agent.event(c, current, 'sourcing_candidate_probe_saved',
                            '1688候选详情读取结果已留档；仍未采用为货源',
                            url=item['url'], status=outcome['status'], pageSha256=outcome.get('pageSha256'))
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        state = current.get('sourcingCandidateProbe') or {}
        if state.get('productHash') == digest(task['snapshot']['product']):
            state['state'] = 'saved' if all(x.get('status') != 'reading' for x in state.get('items', [])) else 'uncertain'
            state['completedAt'] = time.time()
            agent.put(c, current)
            saved_items = state.get('items', [])
    return {item['url']: item for item in saved_items}


def rank_detail_probes(plan, product, observations):
    """Rank read candidates using explicit product attributes visible on detail pages."""
    ranked = []
    for candidate in plan.get('observedCandidates') or []:
        detail = observations.get(candidate.get('url'))
        if not detail or detail.get('status') != 'collected':
            candidate['detailRecommendedRank'] = None
            continue
        supplier = detail.get('supplier') or {}
        known, matched, conflicts = _detail_attribute_signals(product, supplier)
        coverage = round(len(matched) / len(known), 4) if known else None
        score = candidate.get('lexicalScore', 0) if coverage is None else round(
            candidate.get('lexicalScore', 0) * 0.65 + coverage * 0.35, 4)
        candidate['detailAttributeCoverage'] = coverage
        candidate['detailMatchedAttributes'] = matched
        candidate['detailAttributeConflicts'] = conflicts
        candidate['detailTriageScore'] = score
        ranked.append(candidate)
    rank_candidates(ranked, 'detailTriageScore')
    for rank, candidate in enumerate(ranked, 1):
        candidate['detailRecommendedRank'] = rank
    return plan


def _detail_attribute_signals(product, supplier):
    """Compare known product facts with structured supplier page attributes.

    An explicit supplier attribute takes precedence over title text, so a
    conflicting color/material cannot be hidden by keyword-heavy titles.
    """
    attributes = supplier.get('attributes') if isinstance(supplier.get('attributes'), dict) else {}
    groups = {
        'material': ('材质', '材料', '面料', '成分', 'material', 'fabric'),
        'dimensions': ('尺寸', '规格', '长', '宽', '高', 'dimension', 'size', 'length', 'width', 'height'),
        'colorNames': ('颜色', '色系', 'color'),
        'sizeNames': ('尺码', '尺寸', 'size'),
    }
    known, matched, conflicts = [], [], []
    placeholders = {'unknown', 'n/a', 'na', 'not specified', '未确认', '未知', '待补', '不详'}
    title = str(supplier.get('title') or '')
    for field, markers in groups.items():
        raw = product.get(field)
        values = raw if isinstance(raw, (list, tuple)) else re.split(r'[,，;；|/]+', str(raw or ''))
        explicit = [(str(key), str(value)) for key, value in attributes.items()
                    if any(marker in str(key).lower() for marker in markers)]
        for value in values:
            value = str(value or '').strip()
            if not value or value.casefold() in placeholders:
                continue
            normalized = re.sub(r'[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+', '',
                                value.lower().replace('×', 'x').replace('✕', 'x'))
            if len(normalized) < 2 or len(normalized) > 80:
                continue
            signal = {'field': field, 'label': {'material':'材质','dimensions':'尺寸',
                       'colorNames':'颜色','sizeNames':'尺码'}[field], 'value': value[:80]}
            known.append(signal)
            if explicit:
                observed = ' '.join(value for _, value in explicit)
                observed_normalized = re.sub(r'[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+', '',
                                             observed.lower().replace('×', 'x').replace('✕', 'x'))
                is_match = normalized in observed_normalized
                if field == 'dimensions':
                    is_match = _dimensions_match(value, observed)
                if is_match:
                    matched.append(signal)
                else:
                    conflicts.append({**signal, 'supplierAttributes': explicit[:5]})
                continue
            fallback_known, fallback_matched = _attribute_signals(
                {field: value}, title)
            if fallback_known and fallback_matched:
                matched.append(signal)
    return known, matched, conflicts


def collect(user, task):
    baseline = agent.inspect_facts(task)
    if baseline['ok'] or not baseline.get('selection', {}).get('ok'):
        return baseline
    url = source_url(task['snapshot']['product'])
    if not url:
        plan = search_plan(task['snapshot']['product'])
        if plan:
            plan = save_plan(user, task, plan)
            observations = probe_observed_candidates(user, task, task['snapshot']['product'],
                                                     plan.get('observedCandidates') or [])
            for candidate in plan.get('observedCandidates') or []:
                candidate['detailProbe'] = observations.get(candidate.get('url'))
            rank_detail_probes(plan, task['snapshot']['product'], observations)
            if observations:
                plan['candidateProbeNote'] = '对前三条已采集候选做了只读详情读取；结果仅供比较，不会自动选定或写入货源。'
        issues = ['产品尚未保存有效的1688商品详情链接；请打开搜索计划完成关键词/以图筛选'] + baseline['issues']
        return {**baseline, 'issues': issues, 'sourcingSearchPlan': plan}
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        attempt = current.get('sourcingAttempt')
        if attempt:
            if attempt['state'] != 'saved': raise ValueError('货源读取结果尚未确认，请先核对原记录，不自动重复请求')
        else:
            if current['status'] != 'running': raise ValueError('任务当前没有运行')
            if snapshot(agent.load_workspace(), task) != task['snapshot']:
                return {**baseline, 'issues': ['资料已变化，请更新资料重检；未请求货源页面']}
            current['sourcingAttempt'] = {'state':'started','at':time.time(),'productHash':digest(task['snapshot']['product']),'url':url}
            agent.put(c, current)
            agent.event(c, current, 'sourcing_started', '读取已填写的1688公开商品页面；不调用模型，不提交采购订单', url=url)
    if attempt:
        return apply_report(user, task, report(user, task['id']))
    try:
        supplier = importer.read_supplier(url)
        result = {'url':url,'checkedAt':datetime.now(timezone.utc).isoformat(),'status':'collected','supplier':supplier,
                  'captureSha256':digest(supplier),
                  'warnings':['仅公开页面采集，不代表已核实同款、结算价、包装毛重或图片/品牌权利']}
    except Exception:
        result = {'url':url,'checkedAt':datetime.now(timezone.utc).isoformat(),'status':'needs_browser',
                  'issues':['公开页面读取失败或要求登录/动态加载；请在浏览器采集货源后更新原任务资料，不自动绕过验证']}
    raw = json.dumps(result,ensure_ascii=False).encode('utf-8')
    folder = agent.DATA/'agent-results'/task['id']; folder.mkdir(parents=True,exist_ok=True)
    with (folder/'sourcing-report.json').open('xb') as stream: stream.write(raw)
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c,user,task['id'])
        current['sourcingAttempt'].update(state='saved',sha256=hashlib.sha256(raw).hexdigest())
        current['sourcingReportAvailable'] = True
        agent.put(c,current)
        agent.event(c,current,'sourcing_saved','货源读取报告已保存，不自动重发',status=result['status'])
    return apply_report(user,task,result)


def apply_report(user, task, result):
    baseline = agent.inspect_facts(task)
    if result['status'] != 'collected':
        return {**baseline, 'reportAvailable':True,'issues':result['issues']+baseline['issues']}
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c,user,task['id'])
        if current['sourcingAttempt'].get('applied'):
            return {**baseline,'reportAvailable':True,'note':'已采集过货源；保留当前资料，不重复读取或覆盖'}
        if digest(task['snapshot']['product']) != current['sourcingAttempt']['productHash']:
            return {**baseline,'ok':False,'reportAvailable':True,'issues':['产品资料已变化，保留报告，不把旧货源应用到新资料']}
        with closing(sqlite3.connect(agent.DATA/'studio.sqlite3',timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
            if not row: raise ValueError('当前账号产品库不存在，货源报告已保留')
            workspace = json.loads(row[1])
            if snapshot(workspace,task) != task['snapshot']:
                return {**baseline,'ok':False,'reportAvailable':True,'issues':['采集期间产品、文案或审核发生变化，报告保留，未覆盖']}
            product = next(p for p in workspace['products'] if p['id']==task['productId'])
            source = product.setdefault('sourceImport',{})
            previous = copy.deepcopy(source.get('supplier',{}))
            incoming = copy.deepcopy(result['supplier'])
            incoming['retrievedAt'] = result['checkedAt']
            if previous and source_url({'sourceUrl':previous.get('url','')}) != result['url']:
                source.setdefault('supplierHistory',[]).append(previous)
                previous = {}
            # Preserve richer extension evidence; this reader only fills missing fields.
            merged = {**incoming,**previous}
            merged['attributes'] = {**incoming.get('attributes',{}),**previous.get('attributes',{})}
            merged['lastPublicReadAt'] = result['checkedAt']
            source['supplier'] = merged
            # Cost, quantity and weight need exact variant/units; don't promote a range/headline.
            saved = {key:copy.deepcopy(product[key]) for key in ('purchasePrice','packageWeight','productWeight','packageDimensions') if key in product}
            importer.autofill_supplier(product)
            for key in ('purchasePrice','packageWeight','productWeight','packageDimensions'):
                if key in saved: product[key] = saved[key]
                else: product.pop(key,None); product.get('autoImportedFields',{}).pop(key,None)
            review = workspace.setdefault('reviews',{}).setdefault(task['productId'],{})
            review.update(copy=False,images=False)
            if product.get('status') in ('已通过','待审核'): product['status']='需修改'
            revision=row[0]+1
            db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision,json.dumps(workspace,ensure_ascii=False)))
        current.setdefault('revisions',[]).append({'at':time.time(),'snapshot':current['snapshot'],'results':current['results'],'reason':'自动货源读取更新资料'})
        current['sourcingAttempt']['applied']=True
        current.update(snapshot=snapshot(workspace,task),workspaceRevision=revision)
        agent.put(c,current)
        agent.event(c,current,'sourcing_applied','公开货源资料已保存；保留经营参数，文案和图片需重新核对',revision=revision)
    probe = copy.deepcopy(task); probe['snapshot'] = current['snapshot']
    return {**agent.inspect_facts(probe),'reportAvailable':True,'note':'已读取货源并补充缺失资料；报价/重量、同款与图片权利仍需核实'}
