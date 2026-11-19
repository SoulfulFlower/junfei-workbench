"""Evidence completeness gates for market-discovery candidates, not market estimates."""
from datetime import date, datetime, timezone, timedelta
import csv
import hashlib
import io
import re
import json
from pathlib import Path
import app_paths
import runtime_environment
from urllib.parse import urlsplit, parse_qs

DOMAINS = {'US': 'com', 'UK': 'co.uk', 'DE': 'de', 'FR': 'fr', 'IT': 'it', 'ES': 'es', 'JP': 'co.jp', 'CA': 'ca', 'AU': 'com.au', 'IN': 'in', 'MX': 'com.mx', 'BR': 'com.br'}
IP_CHECKS = ('brand', 'trademark', 'designPatent', 'utilityPatent', 'imageRights')


PRODUCT_DATE = 'sellersprite_product_listing'


def project_root():
    return runtime_environment.project_root(app_paths.APP)


def current_policy():
    """Snapshot the live operating policy; legacy tasks retain seller-level dates."""
    root = project_root()
    path = root / 'automation/config.json'
    if not path.is_file():
        path = app_paths.APP / 'automation/config.json'
    config = json.loads(path.read_text(encoding='utf-8'))
    selection = config['selection']
    basis = selection.get('freshness_basis', 'seller_listing')
    if basis not in ('seller_listing', PRODUCT_DATE):
        raise ValueError('未知选品日期口径')
    window = selection.get('window_days', 7)
    if type(window) is not int or not 1 <= window <= 365:
        raise ValueError('无效选品日期窗口')
    return {'freshnessBasis': basis, 'windowDays': window,
            'windowAuthorization': selection.get('window_authorization', {}),
            'sameProductRankPolicy': selection.get('same_product_rank_policy', {}),
            'brandPolicy': selection.get('brand_policy', {}),
            'patentSearchPolicy': selection.get('patent_search_policy', {}),
            'designPatentPolicy': selection.get('design_patent_policy', {}),
            'authorization': selection.get('freshness_authorization', {}),
            'supplierImagePolicy': config.get('images', {}).get('supplier_image_policy'),
            'sourcingPolicy': config.get('sourcing', {}),
            'supplierImageAuthorization': config.get('images', {}).get('supplier_image_authorization', {})}


def supplier_image_default(item, policy):
    if policy.get('supplierImagePolicy') != 'user_default_supplier_images' or not policy.get('supplierImageAuthorization', {}).get('instruction'):
        return False
    try:
        u = urlsplit(item.get('url', ''))
        return (item.get('status') == 'user_default' and item.get('basis') == 'user_default_supplier_use_not_supplier_license'
                and item.get('visuallyReviewed') is True and item.get('noUnauthorizedMarks') is True
                and u.scheme == 'https' and u.hostname == 'detail.1688.com' and u.port in (None, 443)
                and not u.username and not u.password and bool(re.fullmatch(r'/offer/\d+\.html', u.path)))
    except (TypeError, ValueError):
        return False


def product_date_source(value, listed):
    if not source(value):
        return False
    try:
        url = urlsplit(value['url'])
        host = (url.hostname or '').lower()
        return (url.scheme == 'https' and not url.username and not url.password
                and url.port in (None, 443)
                and (host == 'sellersprite.com' or host.endswith('.sellersprite.com'))
                and sellersprite_listing_dates(value.get('raw', '')) == [listed])
    except (ValueError, TypeError):
        return False


def any_seller_rank(task):
    policy = (task.get('selectionPolicy') or {}).get('sameProductRankPolicy') or {}
    return (policy.get('seller_scope') == 'any_seller'
            and bool(str(policy.get('instruction', '')).strip()))


def evidence_template(task):
    """Return an explicit, empty collection form for a market-research candidate.

    This is a data-entry aid only. Empty source fields intentionally fail inspect().
    """
    product = (task.get('snapshot') or {}).get('product') or {}
    research = product.get('selectionResearch') or {}
    reference = research.get('reference') or {}
    asin = reference.get('asin', '')
    market = task.get('profile', {}).get('marketplace', '')
    if not asin or not market:
        return None

    def source():
        return {'url': '', 'checkedAt': '', 'raw': ''}

    return {
        'asin': asin,
        'marketplace': market,
        'sellerId': '',
        'sellerCountry': '',
        'sellerCountrySource': source(),
        'fulfillment': '',
        'fulfillmentSource': source(),
        'collectionDate': '',
        'sellerListedDate': '',
        'productListedDate': '',
        'freshnessScope': (task.get('selectionPolicy') or {}).get('freshnessBasis', 'seller_listing'),
        'freshnessSource': source(),
        'frontSearch': {**source(), 'status': 'not_opened'},
        'matchedAsin': '',
        'match': '',
        'matchSource': source(),
        'matchedRank': {**source(), 'source': 'SellerSprite same-product search', 'asin': '', 'value': None},
        'ipChecks': {key: {**source(), 'status': 'not_checked', 'query': '', 'judgment': ''} for key in IP_CHECKS},
        'dailyQuotaLedgerVerified': False,
        'dailyQuotaSource': source(),
        '_instructions': {
            'source': '每项填写真实查看的网址、日期和页面原文；不要填写推测值。',
            'freshness': (f"按卖家精灵商品上架日期筛选近{(task.get('selectionPolicy') or {}).get('windowDays', 7)}天：填写 productListedDate，来源须为SellerSprite明确日期原文；不代表该卖家独立上新。" if (task.get('selectionPolicy') or {}).get('freshnessBasis') == PRODUCT_DATE else f"sellerListedDate 必须是卖家上架日期且在 collectionDate 前{(task.get('selectionPolicy') or {}).get('windowDays', 7)}天内；商品首次可售日期不等同。"),
            'frontSearch': '必须先打开当前站点 Amazon 标题首句搜索页，status 填 opened。',
            'matchedRank': ('填写标题首句搜索后确认的 exact/strong 同款数值排名；任意卖家（包括候选自身）均可，保留对应ASIN及原文，不用相似款替代。' if any_seller_rank(task) else '只填写其他卖家 exact/strong 同款在 SellerSprite 同款搜索中的数值排名，不填 Amazon 商品页 BSR。'),
            'ipChecks': '品牌、商标、外观专利、实用专利、图片权利逐项检查；不确定时不得填 clear。',
            'quota': '核对跨批次排重表和该店当日配额后再填写。'
        }
    }


def evidence_draft(task):
    """Prefill only source links, capture dates and verbatim browser observations.

    Browser observations are not promoted to selectionEvidence: classification,
    seller identity, exact-match, rank, IP and quota decisions remain blank for
    explicit review. The returned draft is a review aid, never a passing gate.
    """
    template = evidence_template(task)
    if template is None:
        return None
    product = (task.get('snapshot') or {}).get('product') or {}
    observations = product.get('selectionObservations')
    if not isinstance(observations, list):
        observations = []

    def observation_source(item, raw):
        if not isinstance(item, dict) or not isinstance(raw, str) or not raw.strip():
            return None
        url = item.get('url')
        captured = item.get('capturedAt')
        if not isinstance(url, str) or not url.startswith('https://') or not isinstance(captured, str):
            return None
        return {'url': url[:1000], 'checkedAt': captured[:10], 'raw': raw[:2000]}

    asin = template['asin']
    market = template['marketplace']
    matching = [item for item in observations if isinstance(item, dict)
                and item.get('asin') == asin and item.get('marketplace') == market]
    detail = next((item for item in reversed(matching)
                   if item.get('captureType') == 'browser_visible_product_page'), None)
    if detail:
        fields = detail.get('fields') if isinstance(detail.get('fields'), dict) else {}
        fulfillment = observation_source(detail, fields.get('fulfillmentText', ''))
        if fulfillment: template['fulfillmentSource'] = fulfillment

    # A buy-box seller name alone is not a country source. Keep actual business
    # address observations separately, with their own profile URL and date.
    profile = next((item for item in reversed(matching)
                    if item.get('captureType') == 'browser_seller_profile'), None)
    if profile:
        fields = profile.get('sellerProfile') if isinstance(profile.get('sellerProfile'), dict) else {}
        country_source = observation_source(profile, fields.get('raw', ''))
        if country_source:
            template['sellerCountrySource'] = country_source
    else:
        fields = {}

    front = next((item for item in reversed(matching)
                  if item.get('captureType') == 'browser_front_search'), None)
    if front:
        search = front.get('search') if isinstance(front.get('search'), dict) else {}
        raw = 'Query: ' + str(search.get('query') or '') + '\n' + str(search.get('resultText') or '')
        source_value = observation_source(front, raw)
        if source_value and search.get('query'):
            template['frontSearch'] = {**source_value, 'status': 'opened'}

    # Preserve candidate rows and label-based rank suggestions as an explicitly
    # unverified appendix. Never choose the matching ASIN or fill the gate.
    sprite_rows = []
    front_results = {}
    for item in matching:
        if item.get('captureType') != 'browser_front_search':
            continue
        search = item.get('search') if isinstance(item.get('search'), dict) else {}
        for result in search.get('results') or []:
            if not isinstance(result, dict):
                continue
            result_asin = str(result.get('asin') or '').upper()
            if re.fullmatch(r'[A-Z0-9]{10}', result_asin) and result_asin != asin:
                front_results.setdefault(result_asin, []).append({
                    'title': str(result.get('title') or '')[:500],
                    'url': str(item.get('url') or '')[:1000],
                    'capturedAt': str(item.get('capturedAt') or '')[:40],
                })
    for item in matching:
        if item.get('captureType') != 'browser_sellersprite_search':
            continue
        sprite = item.get('sellerSprite') if isinstance(item.get('sellerSprite'), dict) else {}
        for row in sprite.get('rows') or []:
            if isinstance(row, dict) and row.get('asin') and row.get('text') and row.get('asin') != asin:
                raw = str(row['text'])[:300]
                rank_values = sellersprite_rank_values(raw)
                listed_dates = sellersprite_listing_dates(raw)
                row_asin = str(row['asin']).upper()[:10]
                matched_front_rows = front_results.get(row_asin, [])
                sprite_rows.append({'asin': row_asin, 'raw': raw,
                                    'url': str(item.get('url', ''))[:1000],
                                    'capturedAt': str(item.get('capturedAt', ''))[:40],
                                    'rankSuggestions': rank_values if len(rank_values) == 1 else [],
                                    'productListedDateSuggestions': listed_dates if len(listed_dates) == 1 else [],
                                    'alsoInAmazonSearch': bool(matched_front_rows),
                                    'amazonSearchTitles': [x['title'] for x in matched_front_rows if x['title']][:3],
                                    'reviewPriority': 'cross_source_review' if matched_front_rows and len(rank_values) == 1 else 'single_source_review',
                                    'status': 'unverified_observation'})
    # Put candidates observed on both pages with one clearly labeled numeric rank
    # ahead for human review. This is a review queue only: neither match nor sales
    # qualification is inferred, and numeric rank magnitude is never used to sort.
    sprite_rows.sort(key=lambda row: (row['reviewPriority'] != 'cross_source_review',
                                      not bool(row['rankSuggestions']), row['asin']))
    draft = {**template, '_instructions': {**template['_instructions'],
        'autofill': '来源链接、采集时间和页面原文由本账号浏览器观察预填；仍需逐项核对，绝不自动判定卖家国家、FBM、上架日期、同款排名、IP或配额。',
        'sellerSpriteRows': '附录给出明确排名标签对应的数值建议，仅用于节省抄录；跨 Amazon 搜索与 SellerSprite 同时出现的 ASIN 排在前面供人工复核。跨页出现不等于同款或出单证明；请核对页面原文、同款ASIN和排名口径。建议不会自动写入matchedRank或通过准入。'}}
    draft['_observations'] = {'trust': 'unverified_observation', 'sellerSpriteRows': sprite_rows,
                              'sellerProfileSellerId': str(fields.get('sellerId', ''))[:30]}
    return draft


def source(value):
    if not isinstance(value, dict): return False
    try:
        url = urlsplit(value.get('url', ''))
        date.fromisoformat(str(value.get('checkedAt', ''))[:10])
        return url.scheme in ('https', 'http') and bool(url.hostname) and bool(str(value.get('raw', '')).strip())
    except (ValueError, TypeError, AttributeError):
        return False


def local_ledger_review(evidence):
    """Read the configured ledger, never a caller-selected file; do not reserve a slot."""
    report = {'ok': False, 'reservation': False}
    try:
        root = project_root().resolve()
        config = json.loads((root / 'automation/config.json').read_text(encoding='utf-8'))['selection']
        path = (root / config['selected_ledger']).resolve()
        path.relative_to(root)
        content = path.read_bytes()
        report.update(ledgerPath=str(path), sha256=hashlib.sha256(content).hexdigest())
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        if not {'marketplace', 'asin', 'selected_at'}.issubset(reader.fieldnames or []):
            raise ValueError('台账缺少站点、ASIN或日期列')
        market, asin, seller = (evidence[k] for k in ('marketplace', 'asin', 'sellerId'))
        if not all(isinstance(v, str) and v.strip() for v in (market, asin, seller)):
            raise ValueError('候选身份不完整')
        collected = date.fromisoformat(evidence['collectionDate'])
        if collected != date.today():
            raise ValueError('每日配额必须按当前本地日期重新核对')
        count = 0
        duplicate = False
        for row in reader:
            if any(not isinstance(row.get(key), str) for key in ('marketplace', 'asin', 'selected_at')):
                raise ValueError('台账包含不完整记录')
            if row.get('marketplace', '').strip() != market:
                continue
            if row.get('asin', '').strip().upper() == asin.upper():
                duplicate = True
            recorded = datetime.fromisoformat(row.get('selected_at', '').replace('Z', '+00:00'))
            if recorded.tzinfo is not None:
                recorded = recorded.astimezone(timezone(timedelta(hours=8)))
            if recorded.date() == collected:
                recorded_seller = (row.get('seller_id') or '').strip()
                if not recorded_seller:
                    raise ValueError('当日台账记录缺少Seller ID，无法确认每日配额')
                if recorded_seller == seller:
                    count += 1
        limit = config.get('max_per_store_per_day', 2)
        if type(limit) is not int or not 1 <= limit <= 2:
            raise ValueError('每日配额配置无效')
        report.update(duplicate=duplicate, sameSellerToday=count, limit=limit,
                      checkedAt=collected.isoformat(), ok=not duplicate and count < limit)
        if duplicate: report['reason'] = 'ASIN已存在于跨批次台账'
        elif count >= limit: report['reason'] = '同店当日配额已满'
    except (OSError, ValueError, TypeError, KeyError, csv.Error, UnicodeError) as exc:
        report['reason'] = str(exc)
    return report


def quota_source(value, evidence):
    if isinstance(value, dict) and value.get('captureType') == 'local_selection_ledger':
        actual = local_ledger_review(evidence)
        try:
            return (actual['ok'] and value.get('checkedAt') == actual['checkedAt']
                    and value.get('sha256') == actual['sha256']
                    and Path(value.get('ledgerPath', '')).resolve() == Path(actual['ledgerPath']))
        except (ValueError, TypeError, KeyError, OSError):
            return False
    return source(value)


def numeric_sellersprite_rank(rank, matched_asin):
    """Accept only a visible numeric rank captured from a SellerSprite page.

    The structured value is convenient for downstream checks, but the captured
    page text remains the auditable source. A placeholder or unrelated number
    must never satisfy the same-product rank gate.
    """
    if not isinstance(rank, dict) or rank.get('source') != 'SellerSprite same-product search':
        return False
    if rank.get('asin') != matched_asin or type(rank.get('value')) is not int or rank['value'] <= 0:
        return False
    if not source(rank):
        return False
    try:
        url = urlsplit(rank['url'])
        host = (url.hostname or '').lower()
        if url.scheme != 'https' or url.username or url.password or url.port not in (None, 443) or not (host == 'sellersprite.com' or host.endswith('.sellersprite.com')):
            return False
    except (ValueError, TypeError, AttributeError):
        return False
    raw = str(rank.get('raw', '')).strip()
    if not raw or raw.casefold() in {'--', '—', '-', '****', 'n/a', 'na', '暂无', '无数据'}:
        return False
    if rank.get('captureType') == 'sellersprite_mcp_asin_detail':
        if url.hostname != 'mcp.sellersprite.com' or url.path != '/mcp' or url.query or url.username or url.password or url.port not in (None, 443):
            return False
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return False
        return (isinstance(payload, dict) and payload.get('asin') == matched_asin
                and type(payload.get('bsrRank')) is int and payload['bsrRank'] == rank['value'])
    values = sellersprite_rank_values(raw)
    return len(values) == 1 and rank['value'] == values[0]


def sellersprite_rank_values(raw):
    """Extract values only when SellerSprite visibly labels them as rank."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    label = r'(?:sales\s*rank|bsr|销售排名|销量排名|排名)'
    number = r'([1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)'
    matches = re.findall(label + r'\s*[:：]?\s*#?\s*' + number + r'(?![\d,])', raw, flags=re.I)
    values = []
    for token in matches:
        try:
            value = int(token.replace(',', ''))
        except ValueError:
            continue
        if value > 0 and value not in values:
            values.append(value)
    return values


def sellersprite_listing_dates(raw):
    """Extract ISO dates only when SellerSprite explicitly labels listing date."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    label = r'(?:seller\s*listed(?:\s*date)?|listing\s*date|date\s*listed|listed\s*on|上架日期|上架时间|刊登日期)'
    matches = re.findall(label + r'\s*[:：]?\s*(\d{4}-\d{2}-\d{2})(?!\d)', raw, flags=re.I)
    dates = []
    for value in matches:
        try:
            normalized = date.fromisoformat(value).isoformat()
        except ValueError:
            continue
        if normalized not in dates:
            dates.append(normalized)
    return dates


def inspect(task):
    product = task['snapshot']['product'] or {}
    if not product: return {'ok': False, 'issues': ['未接入自动同行选品，尚无产品可核验']}
    if not product.get('selectionResearch'):
        return {'ok': True, 'skipped': True, 'note': '用户指定的既有产品；未执行自动选品，不记录为新入选'}
    evidence = product.get('selectionEvidence')
    if not isinstance(evidence, dict):
        return {'ok': False, 'issues': ['月度市场候选尚未完成7天新品、中国FBM、前台同款及IP核验；不能直接转为生产入选'], 'note': '市场销量或AI建议不替代选品硬条件'}
    issues = []
    research = product['selectionResearch']
    reference = research.get('reference', {}) if isinstance(research, dict) else {}
    if not isinstance(reference, dict): reference = {}
    asin, market = reference.get('asin'), task['profile']['marketplace']
    if evidence.get('asin') != asin or evidence.get('marketplace') != market:
        issues.append('选品证据ASIN或站点与当前候选不一致')
    if evidence.get('sellerCountry') != 'CN' or not source(evidence.get('sellerCountrySource')):
        issues.append('缺少中国卖家国家原文、网址及检查时间')
    if evidence.get('fulfillment') != 'FBM' or not source(evidence.get('fulfillmentSource')):
        issues.append('缺少FBM履约原文、网址及检查时间')
    if not str(evidence.get('sellerId', '')).strip(): issues.append('缺少同行Seller ID')
    window = (task.get('selectionPolicy') or {}).get('windowDays', 7)
    try:
        if type(window) is not int or not 1 <= window <= 365: raise ValueError()
        collected = date.fromisoformat(evidence.get('collectionDate', ''))
        basis = (task.get('selectionPolicy') or {}).get('freshnessBasis', 'seller_listing')
        if basis not in ('seller_listing', PRODUCT_DATE): raise ValueError()
        field = 'productListedDate' if basis == PRODUCT_DATE else 'sellerListedDate'
        listed = date.fromisoformat(evidence.get(field, ''))
        if not 0 <= (collected - listed).days <= window or collected > date.today(): raise ValueError()
        if evidence.get('freshnessScope') != basis or not source(evidence.get('freshnessSource')): raise ValueError()
        if basis == PRODUCT_DATE and not product_date_source(evidence.get('freshnessSource'), listed.isoformat()): raise ValueError()
    except (ValueError, TypeError):
        issues.append(f'缺少近{window}天卖家精灵商品上架日期及明确标注的来源原文（非卖家独立上新）' if (task.get('selectionPolicy') or {}).get('freshnessBasis') == PRODUCT_DATE else f'缺少近{window}天卖家上架日期依据；月度快照和商品首次可售日期不能直接替代')
    search = evidence.get('frontSearch', {})
    try:
        url = urlsplit(search.get('url', ''))
        query = parse_qs(url.query).get('k', [''])[0]
        if url.scheme != 'https' or url.hostname != 'www.amazon.' + DOMAINS[market] or url.path != '/s' or not query.strip(): raise ValueError()
        if search.get('status') != 'opened' or not source(search): raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        issues.append('缺少已实际打开的当前站点Amazon标题首句搜索链接和观察原文')
    matched = evidence.get('matchedAsin', '')
    if evidence.get('match') not in ('exact', 'strong') or not re.fullmatch(r'[A-Z0-9]{10}', str(matched)) or (matched == asin and not any_seller_rank(task)) or not source(evidence.get('matchSource')):
        issues.append('缺少任意卖家的exact/strong同款及核图依据' if any_seller_rank(task) else '缺少其他卖家的exact/strong同款及核图依据')
    rank = evidence.get('matchedRank', {})
    if not numeric_sellersprite_rank(rank, matched):
        issues.append('缺少前台同款ASIN的SellerSprite数值销售排名及原始证据')
    checks = evidence.get('ipChecks')
    if not isinstance(checks, dict): checks = {}
    policy = task.get('selectionPolicy') or {}
    if policy.get('brandPolicy', {}).get('mode') == 'generic_only':
        brand = checks.get('brand') or {}
        u = urlsplit(brand.get('url', ''))
        if (brand.get('observedBrand') != 'Generic' or not source(brand)
                or u.scheme != 'https' or u.hostname != 'www.amazon.' + DOMAINS[market]
                or u.path != '/dp/' + str(asin)
                or not re.search(r'\bBrand\s*[:：]\s*Generic\b', str(brand.get('raw', '')), re.I)):
            issues.append('只选Amazon商品页品牌明确为Generic的产品，缺少对应ASIN品牌原文')
    for key in IP_CHECKS:
        item = checks.get(key, {})
        if not isinstance(item, dict): item = {}
        patent_policy = policy.get('patentSearchPolicy') or {}
        if key in ('designPatent', 'utilityPatent') and patent_policy.get('mode') == 'skip_by_user_instruction' and patent_policy.get('instruction'):
            if (item.get('status') != 'skipped_by_user' or item.get('searchPerformed') is not False
                    or not str(item.get('judgment', '')).strip() or item.get('instruction') != patent_policy['instruction']):
                issues.append('专利须明确记录按用户要求未检索：' + key)
            continue
        accepted = item.get('status') == 'clear' or (key == 'imageRights' and supplier_image_default(item, task.get('selectionPolicy') or {}))
        if key == 'designPatent':
            design_policy = (task.get('selectionPolicy') or {}).get('designPatentPolicy') or {}
            accepted = accepted or (design_policy.get('mode') == 'obvious_overall_match_only'
                and bool(design_policy.get('instruction'))
                and item.get('status') == 'no_obvious_match'
                and item.get('searchPerformed') is True
                and item.get('obviousOverallMatchFound') is False)
        if not accepted or not source(item) or not str(item.get('query', '')).strip() or not str(item.get('judgment', '')).strip():
            issues.append('侵权/权利核验未完成：' + key)
    if evidence.get('dailyQuotaLedgerVerified') is not True or not quota_source(evidence.get('dailyQuotaSource'), evidence):
        issues.append('缺少跨批次排重及同店每日最多2款的台账核对记录')
    return {'ok': not issues, 'issues': issues, 'note': '仅核对已保存证据的字段与一致性；不把布尔值或来源网址本身当作真实性证明，不自动写入正式入选表'}
