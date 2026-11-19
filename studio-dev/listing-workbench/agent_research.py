"""Durable, opt-in competitor research for the account-owned task runner."""
from urllib.parse import quote_plus, urlsplit, parse_qs
import re
import hashlib
import json
import sqlite3
import time
from contextlib import closing

import agent_center as agent
import competitors


MARKET_DOMAINS = {
    'US': 'www.amazon.com', 'UK': 'www.amazon.co.uk', 'DE': 'www.amazon.de',
    'FR': 'www.amazon.fr', 'IT': 'www.amazon.it', 'ES': 'www.amazon.es',
    'JP': 'www.amazon.co.jp', 'CA': 'www.amazon.ca', 'AU': 'www.amazon.com.au',
    'IN': 'www.amazon.in', 'MX': 'www.amazon.com.mx', 'BR': 'www.amazon.com.br',
}

_WORD = re.compile(r"[a-z0-9]+", re.I)
_MIN_TITLE_JACCARD = 0.25


def title_tokens(value):
    return {word.lower() for word in _WORD.findall(str(value or '')) if len(word) > 1}


def observed_competitors(task, limit=3):
    """Choose research-only ASINs from this product's validated front-search captures.

    This does not establish exact-match or product-selection eligibility.
    """
    product = (task.get('snapshot') or {}).get('product') or {}
    research = product.get('selectionResearch') or {}
    reference = research.get('reference') or {}
    own_asin = str(reference.get('asin') or product.get('asin') or '').upper()
    market = str(task.get('profile', {}).get('marketplace') or '').upper()
    domain = MARKET_DOMAINS.get(market)
    title = product.get('name') or product.get('title') or ''
    wanted = title_tokens(title)
    if not own_asin or not domain or not wanted:
        return []
    observations = product.get('selectionObservations')
    if not isinstance(observations, list):
        return []
    ranked = {}
    for observation in observations:
        if not isinstance(observation, dict) or observation.get('captureType') != 'browser_front_search':
            continue
        if str(observation.get('asin', '')).upper() != own_asin or str(observation.get('marketplace', '')).upper() != market:
            continue
        parsed = urlsplit(str(observation.get('url') or ''))
        try:
            port = parsed.port
        except ValueError:
            continue
        if (parsed.scheme != 'https' or parsed.username or port not in (None, 443)
                or parsed.hostname not in (domain, domain.removeprefix('www.')) or parsed.path != '/s'):
            continue
        query = parse_qs(parsed.query).get('k', [''])[0].strip()
        search = observation.get('search') if isinstance(observation.get('search'), dict) else {}
        if not query or query != str(search.get('query') or '').strip():
            continue
        for row in search.get('results') or []:
            if not isinstance(row, dict):
                continue
            asin = str(row.get('asin') or '').upper()
            if not re.fullmatch(r'[A-Z0-9]{10}', asin) or asin == own_asin:
                continue
            tokens = title_tokens(row.get('title'))
            score = len(wanted & tokens) / len(wanted | tokens) if wanted and tokens else 0
            if score < _MIN_TITLE_JACCARD:
                continue
            prior = ranked.get(asin)
            if prior is None or score > prior['score']:
                ranked[asin] = {'asin': asin, 'title': str(row.get('title') or '')[:500],
                                'score': round(score, 4), 'sourceUrl': observation['url'][:1000],
                                'capturedAt': str(observation.get('capturedAt') or '')[:40],
                                'status': 'research_candidate_unverified'}
    return sorted(ranked.values(), key=lambda item: (-item['score'], item['asin']))[:max(1, min(3, limit))]


def search_plan(task):
    """Build browser hand-off links without pretending a competitor is verified."""
    product = task.get('snapshot', {}).get('product') or {}
    market = str(task.get('profile', {}).get('marketplace') or 'US').upper()
    title = str(product.get('name') or product.get('title') or '').strip()
    if not title:
        return {'status': 'blocked', 'requiresBrowserReview': True,
                'warning': '缺少产品标题，无法生成前台竞品搜索计划'}
    query = ' '.join(title.split())[:180]
    encoded = quote_plus(query)
    domain = MARKET_DOMAINS.get(market, MARKET_DOMAINS['US'])
    return {
        'status': 'needs_browser',
        'marketplace': market,
        'query': query,
        'amazonUrl': f'https://{domain}/s?k={encoded}',
        'sellerSpriteUrl': 'https://www.sellersprite.com/',
        'requiresBrowserReview': True,
        'warning': '前台搜索和 SellerSprite 入口仅用于人工核验候选 ASIN、同款关系及排名；不会自动认定竞品、写入研究证据或调用付费服务',
    }
import provider
import sellersprite


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def safe_model(value):
    """Return a bounded model label without persisting arbitrary response data."""
    if not isinstance(value, str):
        return ''
    value = value.strip()
    return value if value and len(value) <= 200 else ''


_PRIVATE_KEYS = {'api_key', 'apikey', 'access_token', 'secret', 'raw_response',
                 'rawResponse', 'credential', 'credentials', 'password'}


def sanitize_report(value):
    """Drop provider secrets/raw payloads before the durable report is written."""
    if isinstance(value, dict):
        return {key: sanitize_report(item) for key, item in value.items()
                if key not in _PRIVATE_KEYS}
    if isinstance(value, list):
        return [sanitize_report(item) for item in value]
    return value


def snapshot(workspace, task):
    pid, market = task['productId'], task['profile']['marketplace']
    return {'product': next((p for p in workspace['products'] if p['id'] == pid), None),
            'listing': workspace.get('copy', {}).get(pid + '-' + market, {}),
            'review': workspace.get('reviews', {}).get(pid, {})}


def report(user, tid):
    with agent.LOCK, closing(agent.connect()) as c:
        task = agent.owned(c, user, tid)
    if not task.get('researchReportAvailable'):
        raise ValueError('没有已保存的竞品研究报告')
    raw = (agent.DATA / 'agent-results' / tid / 'research-report.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != task['researchAttempt']['sha256']:
        raise ValueError('研究报告文件已变更，请核对')
    return json.loads(raw)


def save_plan(user, task, plan):
    """Persist the browser hand-off plan so it remains auditable after refresh/restart."""
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True).encode('utf-8')
    folder = agent.DATA / 'agent-results' / task['id']
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'research-plan.json'
    digest_value = hashlib.sha256(raw).hexdigest()
    if path.exists():
        existing = path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != digest_value:
            raise ValueError('研究核验计划已变化，请先核对旧计划')
    else:
        path.write_bytes(raw)
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        current['researchPlanAvailable'] = True
        current['researchPlanSha256'] = digest_value
        agent.put(c, current)
        if not current.get('researchPlanRecorded'):
            current['researchPlanRecorded'] = True
            agent.event(c, current, 'research_plan_saved', '竞品浏览器核验计划已保存；未调用付费服务', sha256=digest_value)
            agent.put(c, current)
    return plan


def plan_report(user, tid):
    with agent.LOCK, closing(agent.connect()) as c:
        task = agent.owned(c, user, tid)
    if not task.get('researchPlanAvailable'):
        raise ValueError('没有已保存的竞品核验计划')
    raw = (agent.DATA / 'agent-results' / tid / 'research-plan.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != task.get('researchPlanSha256'):
        raise ValueError('竞品核验计划文件已变更，请核对')
    return json.loads(raw)


def collect(user, task):
    baseline = agent.inspect_research(task)
    if baseline['ok']:
        return baseline  # Existing usable research does not trigger a paid refresh.
    if not task.get('researchAsins'):
        candidates = observed_competitors(task)
        if candidates and task.get('results', {}).get('facts', {}).get('ok'):
            # Persist the exact observed choices before any external research call.
            selected = [item['asin'] for item in candidates]
            with agent.LOCK, closing(agent.connect()) as c, c:
                current = agent.owned(c, user, task['id'])
                if current.get('researchAsins'):
                    selected = current['researchAsins']
                else:
                    current['researchAsins'] = selected
                    current['researchCandidateSelection'] = candidates
                    agent.put(c, current)
                    agent.event(c, current, 'research_candidates_selected',
                                '从当前账号、站点的Amazon前台观察中按标题相似度选出研究候选；未核实同款或选品准入',
                                candidates=candidates)
            task['researchAsins'] = selected
            task['researchCandidateSelection'] = candidates
        else:
            plan = search_plan(task)
            plan['observedCandidates'] = candidates
            plan['candidatePolicy'] = {'minimumTitleJaccard': _MIN_TITLE_JACCARD,
                                       'maximumCandidates': 3,
                                       'meaning': '仅为竞品关键词研究候选；不是同款核实或选品准入证据'}
            plan = save_plan(user, task, plan)
            return {**baseline, 'needsCompetitorAsins': True, 'researchSearchPlan': plan,
                    'issues': ['没有达到标题相似度门槛的有效Amazon前台观察候选；请补充观察或填写已核验竞品ASIN'],
                    'note': '未调用研究服务，不写入研究证据' if not candidates else '前台观察候选因事实检查未通过而未采用；未调用研究服务'}
    if not task.get('researchAsins'):
        plan = save_plan(user, task, search_plan(task))
        return {**baseline, 'needsCompetitorAsins': True, 'researchSearchPlan': plan,
                'issues': ['请先在Amazon前台和SellerSprite人工核验并填写1至5个竞品ASIN'],
                'note': '已生成浏览器核验入口；未调用付费服务，不写入研究证据'}
    if not task['results'].get('facts', {}).get('ok'):
        return {'ok': False, 'issues': ['货源资料检查通过后才能自动研究竞品']}
    with agent.LOCK, closing(agent.connect()) as c:
        current = agent.owned(c, user, task['id'])
    attempt = current.get('researchAttempt')
    if attempt:
        if attempt['state'] != 'saved':
            raise ValueError('竞品研究已尝试但结果未确认；请先对账，不自动重复调用')
        return apply_report(user, task, report(user, task['id']))
    if not provider.settings_public()['hasKey'] or not sellersprite.public()['hasKey']:
        return {'ok': False, 'issues': ['当前账号文本模型或共享卖家精灵未配置；未调用服务']}
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        if current.get('researchAttempt'):
            raise ValueError('同一任务研究调用已登记，未重复调用')
        if current['status'] != 'running': raise ValueError('任务当前没有运行')
        if snapshot(agent.load_workspace(), task) != task['snapshot']:
            return {'ok': False, 'issues': ['资料已变更，请更新资料重检；未调用服务']}
        current.update(researchAttempt={'state': 'started', 'at': time.time(),
                                       'productHash': digest(task['snapshot']['product'])}, paidSpendCny=None)
        agent.put(c, current)
        agent.event(c, current, 'research_started', '开始卖家精灵正文及反查词采集与文本分析；不采评论、不额外挖词，费用待账单核实',
                    market=task['profile']['marketplace'], asins=task['researchAsins'])
    product = task['snapshot']['product']
    facts = {k: product.get(k, '') for k in ('name', 'material', 'style', 'dimensions', 'features', 'colorNames', 'sizeNames', 'brand')}
    result = competitors.analyse({'market': task['profile']['marketplace'], 'asins': ' '.join(task['researchAsins']),
                                 'source': 'sellersprite', 'mineKeywords': False, 'includeReviews': False, 'facts': facts})
    if not isinstance(result, dict) or result.get('market') != task['profile']['marketplace']:
        raise ValueError('研究结果站点或格式无效，未采用；请核对调用结果')
    if not isinstance(result.get('sources'), list) or not isinstance(result.get('keywords'), list):
        raise ValueError('研究结果缺少来源或关键词；未自动重试')
    result.update(input=' '.join(task['researchAsins']), collectedAt=time.time())
    # Keep accounting metadata in the task ledger without copying raw provider
    # responses, credentials, or other unbounded fields into the audit trail.
    usage = agent.safe_usage(result.get('usage'))
    model = safe_model(result.get('model'))
    persisted = sanitize_report(result)
    if usage:
        persisted['usage'] = usage
    else:
        persisted.pop('usage', None)
    if model:
        persisted['model'] = model
    else:
        persisted.pop('model', None)
    raw = json.dumps(persisted, ensure_ascii=False).encode('utf-8')
    folder = agent.DATA / 'agent-results' / task['id']
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'research-report.json').open('xb') as output:
        output.write(raw)
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        current['researchAttempt'].update(state='saved', sha256=hashlib.sha256(raw).hexdigest())
        if usage:
            current['researchAttempt']['usage'] = usage
        if model:
            current['researchAttempt']['model'] = model
        current['researchReportAvailable'] = True
        agent.put(c, current)
        agent.event(c, current, 'research_saved', '竞品研究报告已保存，含原始来源及读取失败信息',
                    sha256=current['researchAttempt']['sha256'], usage=usage, model=model or None)
    return apply_report(user, task, persisted)


def apply_report(user, task, result):
    probe = json.loads(json.dumps(task))
    market = task['profile']['marketplace']
    probe['snapshot']['product'].setdefault('competitorResearch', {})[market] = result
    check = agent.inspect_research(probe)
    if not check['ok']:
        errors = [str(s.get('error')) for s in result['sources'] if isinstance(s, dict) and s.get('error')]
        return {**check, 'reportAvailable': True, 'issues': check['issues'] + errors,
                'note': '未取得可用研究数据；报告保留，不重复请求，不用空数据覆盖原资料'}
    with agent.LOCK, closing(agent.connect()) as c, c:
        current = agent.owned(c, user, task['id'])
        if digest(task['snapshot']['product']) != current['researchAttempt']['productHash']:
            return {'ok': False, 'reportAvailable': True, 'issues': ['研究后产品资料已变化；请对比报告，不自动采用旧分析或再次付费']}
        with closing(sqlite3.connect(agent.DATA / 'studio.sqlite3', timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision, body FROM workspace WHERE id=1').fetchone()
            if not row: raise ValueError('工作台资料不存在；研究报告已保留')
            workspace = json.loads(row[1])
            if snapshot(workspace, task) != task['snapshot']:
                return {'ok': False, 'reportAvailable': True, 'issues': ['采集期间资料或文案发生变化；报告已保留，未覆盖，请对比处理']}
            product = next(p for p in workspace['products'] if p['id'] == task['productId'])
            product.setdefault('competitorResearch', {})[market] = result
            workspace.setdefault('reviews', {}).setdefault(task['productId'], {})['copy'] = False
            revision = row[0] + 1
            db.execute('UPDATE workspace SET revision=?, body=? WHERE id=1', (revision, json.dumps(workspace, ensure_ascii=False)))
        current.setdefault('revisions', []).append({'at': time.time(), 'snapshot': current['snapshot'],
                                                  'results': current['results'], 'reason': '自动竞品研究更新资料'})
        current.update(snapshot=snapshot(workspace, task), workspaceRevision=revision)
        agent.put(c, current)
        agent.event(c, current, 'research_applied', '来源及关键词已保存到工作台；下一阶段使用同一研究结果，文案需重新审核', revision=revision)
    return {**check, 'reportAvailable': True, 'note': '已采用真实来源研究结果；数据存在不等于同款、搜索量及相关性已独立验证'}
