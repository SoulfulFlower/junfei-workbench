"""Conservative variant-family evidence assessment; no graph mutation or external I/O.

A visible variant family is not a formal Amazon parent ASIN, an identical SKU,
shared seller evidence, an EXACT match, or selection/qualification evidence.
Imported JSON cannot authenticate itself. Only assess_recorded may enable the
narrow title-phrase dedup hint, and only for receipts loaded by the server from
its current authenticated owner's capture ledger. Never expose that internal
entry point to caller-supplied receipts.
"""
import hashlib
import itertools
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit

# Keep this module independent of app_paths and database modules: import is pure.
MARKETS = {'amazon.com': 'US', 'amazon.co.uk': 'UK', 'amazon.de': 'DE',
           'amazon.fr': 'FR', 'amazon.it': 'IT', 'amazon.es': 'ES',
           'amazon.co.jp': 'JP', 'amazon.ca': 'CA', 'amazon.com.au': 'AU',
           'amazon.in': 'IN', 'amazon.com.mx': 'MX', 'amazon.com.br': 'BR'}
COLLECTOR_VERSION = 2
MAX_CONTROLS = 200
MAX_OBSERVATIONS = 200
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
MAX_PRODUCTS = 20000
MAX_PAIRS = 20000
# Technical evidence freshness limits, not product/market qualification rules.
MAX_DEDUP_AGE = timedelta(hours=24)
MAX_RECIPROCAL_GAP = timedelta(minutes=15)
_RAW_FIELDS = {'schemaVersion', 'status', 'reason', 'capturedAt', 'marketplace',
               'asin', 'url', 'selectedAsin', 'controls'}
_CONTROL_FIELDS = {'containerId', 'selector', 'source', 'asin', 'dataAsin',
                   'href', 'label', 'selectedMarker'}
_EVIDENCE_FIELDS = {'schemaVersion', 'kind', 'collectorVersion', 'observationId',
                    'marketplace', 'asin', 'selectedAsin', 'sourceURL',
                    'observedAt', 'controls'}
_HINT_FIELDS = {'schemaVersion', 'kind', 'marketplace', 'asin', 'sourceURL',
                'observedAt', 'detailAsin'}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def _bounded(value, limit):
    """Bound JSON structure before serializing it (including nesting/cycles)."""
    stack, count, active = [(value, 0, False)], 0, set()
    while stack:
        item, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(item))
            continue
        count += 1
        if count > 500000 or depth > 24:
            raise ValueError('Evidence structure limit exceeded')
        if type(item) in (dict, list):
            if id(item) in active:
                raise ValueError('Evidence contains a cycle')
            active.add(id(item))
            stack.append((item, depth, True))
            if isinstance(item, dict):
                if any(type(k) is not str for k in item):
                    raise ValueError('Invalid JSON key')
                stack.extend((x, depth + 1, False) for x in item.values())
            else:
                stack.extend((x, depth + 1, False) for x in item)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError('Evidence must be JSON data')
    try:
        size = len(json.dumps(value, ensure_ascii=True, allow_nan=False))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('Invalid JSON evidence') from exc
    if size > limit:
        raise ValueError('Evidence size limit exceeded')


def _text(value, name, limit=300):
    if type(value) is not str or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid ' + name)
    return value.strip()


def _asin(value):
    value = _text(value, 'ASIN', 10)
    if not re.fullmatch(r'[A-Z0-9]{10}', value):
        raise ValueError('Invalid ASIN')
    return value


def _market(value):
    if type(value) is not str or value not in MARKETS.values():
        raise ValueError('Invalid marketplace')
    return value


def _time(value, name, now):
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(_text(value, name, 80).replace('Z', '+00:00'))
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid ' + name) from exc
    if dt.tzinfo is None or dt.utcoffset() is None or dt > now + timedelta(minutes=5):
        raise ValueError(name + ' requires a timezone and cannot be in the future')
    return dt.astimezone(timezone.utc)


def _now(value=None):
    result = value or datetime.now(timezone.utc)
    if not isinstance(result, datetime) or result.tzinfo is None:
        raise ValueError('Invalid reference time')
    return result.astimezone(timezone.utc)


def _product_url(value, market, asin):
    value = _text(value, 'product URL', 4000)
    if re.search(r'[\\\x00-\x20]', value) or re.search(r'/(?:\.|%2e){1,2}(?:/|$)', value.split('?', 1)[0], re.I):
        raise ValueError('Ambiguous product URL')
    p = urlsplit(value)
    host = (p.hostname or '').lower().removeprefix('www.')
    try:
        port = p.port
    except ValueError as exc:
        raise ValueError('Invalid URL port') from exc
    match = re.fullmatch(r'(?:/[^/]+/dp|/dp|/gp/product)/([A-Z0-9]{10})(?:/(?:ref=[A-Za-z0-9_.=-]+)?)?', p.path)
    if (p.scheme != 'https' or p.username is not None or p.password is not None
            or port not in (None, 443) or MARKETS.get(host) != market
            or not match or match[1] != asin or p.fragment):
        raise ValueError('Product URL marketplace or ASIN mismatch')
    pairs = parse_qsl(p.query, keep_blank_values=True)
    identity = [k.lower() for k, _ in pairs if k.lower() in
                {'asin', 'seller', 'sellerid', 'me', 'merchant', 'merchantid', 'k', 'q'}]
    if identity:
        raise ValueError('Conflicting identity in product URL')
    # Do not preserve arbitrary URL fields (tracking, authentication, or claims).
    return urlunsplit(('https', host, '/dp/' + asin, '', ''))


def normalize_capture(raw, *, marketplace, asin, started_at=None, now=None):
    """Validate fixed collector output against the server's current page target.

    This checks content, not authenticity. The browser adapter must additionally
    check page/space ownership, route, collector hash, and unchanged graph scope.
    """
    _bounded(raw, 262144)
    if type(raw) is not dict or set(raw) != _RAW_FIELDS:
        raise ValueError('Invalid family capture fields')
    market, asin, now = _market(marketplace), _asin(asin), _now(now)
    if (type(raw['schemaVersion']) is not int or raw['schemaVersion'] != 1
            or raw['status'] != 'captured'
            or raw['reason'] != 'visible_variant_controls_observed'
            or raw['marketplace'] != market or raw['asin'] != asin
            or raw['selectedAsin'] != asin):
        raise ValueError('Family capture identity mismatch')
    observed = _time(raw['capturedAt'], 'capturedAt', now)
    if started_at is not None and observed < _time(started_at, 'startedAt', now):
        raise ValueError('Family capture predates dispatch')
    url = _product_url(raw['url'], market, asin)
    if type(raw['controls']) is not list or not 2 <= len(raw['controls']) <= MAX_CONTROLS:
        raise ValueError('Expected 2-200 variant controls')
    controls, seen, labels, selected = [], set(), {}, []
    for row in raw['controls']:
        if type(row) is not dict or set(row) != _CONTROL_FIELDS:
            raise ValueError('Invalid variant control fields')
        container = _text(row['containerId'], 'containerId', 80)
        radio = row['source'] == 'visible_inline_twister_radio'
        if radio:
            if container not in ('inline-twister-row-color_name', 'inline-twister-row-size_name'):
                raise ValueError('Unsupported inline variant container')
            selector = '#' + container + ' li[data-asin] input[role="radio"]'
            marker = 'aria-checked+a-button-selected'
        else:
            if not re.fullmatch(r'variation_[a-z0-9_]{1,64}', container):
                raise ValueError('Unsupported variant container')
            selector = '#' + container + ' li[data-asin] a[href]'
            marker = 'swatchSelect'
        target = _asin(row['asin'])
        if (row['selector'] != selector or row['source'] not in ('visible_twister_anchor', 'visible_inline_twister_radio')
                or row['dataAsin'] != target or row['selectedMarker'] not in ('', marker)):
            raise ValueError('Variant source or ASIN conflict')
        label = _text(row['label'], 'variant label')
        if radio:
            if row['href'] is not None:
                raise ValueError('Inline radio cannot invent a product href')
            href = None
        else:
            href = _product_url(row['href'], market, target)
        key = container, target
        if key in labels and labels[key] != label:
            raise ValueError('Conflicting variant labels')
        labels[key] = label
        item = dict(containerId=container, selector=selector, source=row['source'],
                    asin=target, dataAsin=target, href=href, label=label,
                    selectedMarker=row['selectedMarker'])
        signature = _digest(item)
        if signature not in seen:
            seen.add(signature)
            controls.append(item)
        if row['selectedMarker']:
            selected.append(target)
    if not selected or set(selected) != {asin}:
        raise ValueError('Missing or conflicting selected variant identity')
    for container in {x['containerId'] for x in controls if x['source'] == 'visible_inline_twister_radio'}:
        if len([x for x in controls if x['containerId'] == container and x['selectedMarker']]) != 1:
            raise ValueError('Inline dimension requires one selected control')
    if len({x['asin'] for x in controls}) < 2:
        raise ValueError('No alternative variant observed')
    # An option cannot be both selected and unselected in the same dimension.
    for key in labels:
        markers = {x['selectedMarker'] for x in controls if (x['containerId'], x['asin']) == key}
        if len(markers) > 1:
            raise ValueError('Conflicting selected markers')
    controls.sort(key=lambda x: (x['containerId'], x['asin'], x['label']))
    result = dict(schemaVersion=1, kind='visible_variant_controls',
                  collectorVersion=COLLECTOR_VERSION, marketplace=market, asin=asin,
                  selectedAsin=asin, sourceURL=url, observedAt=observed.isoformat(),
                  controls=controls)
    result['observationId'] = _digest(result)
    return result


def _observation(raw, now):
    if type(raw) is not dict:
        raise ValueError('Invalid family observation')
    if raw.get('kind') == 'legacy_detail_asin':
        if (set(raw) != _HINT_FIELDS or type(raw['schemaVersion']) is not int
                or raw['schemaVersion'] != 1):
            raise ValueError('Invalid legacy hint fields')
        market, asin = _market(raw['marketplace']), _asin(raw['asin'])
        result = dict(schemaVersion=1, kind='legacy_detail_asin', marketplace=market,
                      asin=asin, selectedAsin=None,
                      sourceURL=_product_url(raw['sourceURL'], market, asin),
                      observedAt=_time(raw['observedAt'], 'observedAt', now).isoformat(),
                      detailAsin=_asin(raw['detailAsin']))
        result['observationId'] = _digest(result)
        return result
    if set(raw) != _EVIDENCE_FIELDS or raw.get('kind') != 'visible_variant_controls' or raw.get('collectorVersion') != COLLECTOR_VERSION:
        raise ValueError('Invalid normalized family evidence')
    result = normalize_capture(dict(schemaVersion=raw['schemaVersion'], status='captured',
        reason='visible_variant_controls_observed', capturedAt=raw['observedAt'],
        marketplace=raw['marketplace'], asin=raw['asin'], url=raw['sourceURL'],
        selectedAsin=raw['selectedAsin'], controls=raw['controls']),
        marketplace=raw['marketplace'], asin=raw['asin'], now=now)
    if raw['observationId'] != result['observationId'] or raw != result:
        raise ValueError('Family evidence fingerprint or canonical form mismatch')
    return result


def _graph(graph):
    _bounded(graph, 33554432)
    if type(graph) is not dict or type(graph.get('products')) is not list or len(graph['products']) > MAX_PRODUCTS:
        raise ValueError('Invalid or oversized discovery graph')
    products = {}
    for row in graph['products']:
        if type(row) is not dict:
            raise ValueError('Invalid graph product')
        market, asin = _market(row.get('marketplace')), _asin(row.get('asin'))
        key = market + ':' + asin
        if row.get('id') != key or key in products:
            raise ValueError('Duplicate or mismatched graph product')
        products[key] = row
    return products


def _evaluate(graph, evidence, recorded_ids, now, conflict_sources=None):
    products = _graph(graph)
    _bounded(evidence, MAX_EVIDENCE_BYTES)
    if type(evidence) is not list or len(evidence) > MAX_OBSERVATIONS:
        raise ValueError('Expected at most 200 family observations')
    observations, unique = [], set()
    for raw in evidence:
        item = _observation(raw, now)
        key = item['marketplace'] + ':' + item['asin']
        if key not in products:
            raise ValueError('Family source is not in this graph')
        if item['observationId'] not in unique:
            unique.add(item['observationId'])
            observations.append(item)
    observations.sort(key=lambda x: x['observationId'])
    direct, hints, same_time, conflicts = {}, {}, {}, set(conflict_sources or ())
    snapshots = {}
    observation_times = {}
    for item in observations:
        source = item['marketplace'] + ':' + item['asin']
        if item['kind'] == 'legacy_detail_asin':
            hints.setdefault((item['marketplace'], item['detailAsin']), set()).add(source)
            continue
        same_time.setdefault((source, item['observedAt']), set()).add(item['observationId'])
        snapshots.setdefault(source, []).append(item)
        observation_times[item['observationId']] = _time(item['observedAt'], 'observedAt', now)
    for source, items in snapshots.items():
        # Never stitch one old outgoing link to a later return link. A changing
        # control target set can be a dynamic partial load or changed listing;
        # neither is sufficient to suppress further discovery.
        memberships = {tuple(sorted({c['asin'] for c in item['controls']})) for item in items}
        if len(memberships) > 1:
            conflicts.add(source)
        item = max(items, key=lambda x: (x['observedAt'], x['observationId']))
        for row in item['controls']:
            target = item['marketplace'] + ':' + row['asin']
            if target != source and target in products:
                direct.setdefault((source, target), set()).add(item['observationId'])
    for (source, _), signatures in same_time.items():
        if len(signatures) > 1:
            conflicts.add(source)
    pair_keys, hinted = set(), set()
    def add_pair(a, b, hint=False):
        if a == b:
            return
        key = tuple(sorted((a, b)))
        pair_keys.add(key)
        if hint:
            hinted.add(key)
        if len(pair_keys) > MAX_PAIRS:
            raise ValueError('Family pair limit exceeded')
    for a, b in direct:
        add_pair(a, b)
    for members in hints.values():
        for a, b in itertools.combinations(sorted(members), 2):
            add_pair(a, b, True)
    pairs, supported, eligible = [], set(), set()
    for a, b in sorted(pair_keys):
        forward, reverse = direct.get((a, b), set()), direct.get((b, a), set())
        status, reasons = 'pending_verification', []
        if a in conflicts or b in conflicts:
            reasons.append('contradictory_snapshot_evidence')
        elif forward and reverse:
            status = 'supported_visible_family'
            supported.add((a, b))
            reasons.append('reciprocal_visible_variant_controls')
            if (forward & recorded_ids) and (reverse & recorded_ids):
                times = [observation_times[x] for x in forward | reverse]
                if any(t > now for t in times):
                    reasons.append('capture_clock_ahead_of_assessment')
                elif any(now - t > MAX_DEDUP_AGE for t in times):
                    reasons.append('recorded_evidence_expired_for_dedup')
                elif max(times) - min(times) > MAX_RECIPROCAL_GAP:
                    reasons.append('reciprocal_captures_too_far_apart')
                else:
                    eligible.add((a, b))
            else:
                reasons.append('imported_evidence_not_authenticated')
        elif forward or reverse:
            reasons.append('reciprocal_selected_product_capture_missing')
        else:
            reasons.append('shared_detail_asin_is_not_family_mapping')
        pairs.append(dict(productIds=[a, b], marketplace=products[a]['marketplace'],
                          status=status, reasonCodes=reasons,
                          evidenceIds=sorted(forward | reverse),
                          sharedDetailHint=(a, b) in hinted, formalParentAsin=None,
                          formalParentStatus='unknown', identicalSkuEstablished=False,
                          dedupEligible=(a, b) in eligible))
    # Do not take transitive closure as proof. An entire component must be a
    # complete reciprocal clique; A<->B and B<->C never establishes A<->C.
    neighbors = {}
    for a, b in supported:
        neighbors.setdefault(a, set()).add(b)
        neighbors.setdefault(b, set()).add(a)
    groups, visited = [], set()
    for start in sorted(neighbors):
        if start in visited:
            continue
        component, pending = set(), [start]
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(neighbors[current] - component)
        visited.update(component)
        members = sorted(component)
        member_pairs = set(itertools.combinations(members, 2))
        complete = member_pairs <= supported
        dedup = complete and member_pairs <= eligible
        groups.append(dict(groupId='family-' + _digest(members)[:32],
            marketplace=products[members[0]]['marketplace'], productIds=members,
            status='supported_visible_family' if complete else 'pending_verification',
            reasonCodes=['complete_reciprocal_controls' if complete else 'transitive_family_link_not_proof'],
            formalParentAsin=None, formalParentStatus='unknown', dedupEligible=dedup,
            dedupScope=['title_phrase_capture'] if dedup else [],
            preserveSellerCapture=True, preserveOriginalNodes=True))
    annotations, groups_by_product = [], {}
    related_products = {key for pair in pairs for key in pair['productIds']}
    for group in groups:
        for key in group['productIds']:
            groups_by_product.setdefault(key, []).append(group)
    for key in sorted(products):
        member_groups = groups_by_product.get(key, [])
        related = key in related_products
        annotations.append(dict(productId=key,
            status='supported_visible_family' if any(g['status'] == 'supported_visible_family' for g in member_groups) else 'pending_verification',
            groupIds=[g['groupId'] for g in member_groups],
            reasonCodes=['family_evidence_available'] if related else ['no_sufficient_family_evidence'],
            preserveSellerCapture=True))
    result = dict(schemaVersion=1, status='assessed', readOnly=True,
        cycleId=graph.get('cycleId'), revision=graph.get('revision'),
        graphFingerprint=_digest(graph), evidenceFingerprint=_digest(observations),
        evidence=observations, pairs=pairs, groups=groups, products=annotations,
        authenticity='server_recorded_capture' if recorded_ids else 'unverified_import',
        dedupEligibleGroupCount=sum(g['dedupEligible'] for g in groups),
        originalProductCount=len(products), originalNodesPreserved=True,
        sellerEvidencePreserved=True, executionAllowed=False,
        qualificationEvaluated=False, qualifiedCount=0, importedCount=0,
        formalParentMappingEstablished=False,
        dedupFreshnessPolicy={'maxAgeSeconds': int(MAX_DEDUP_AGE.total_seconds()),
                             'maxReciprocalGapSeconds': int(MAX_RECIPROCAL_GAP.total_seconds())},
        limitations='Visible reciprocal control membership is not a formal parent, identical SKU, shared seller, EXACT match, rank transfer, or qualification. Imported evidence cannot suppress work. Original graph and seller branches remain unchanged.')
    result['assessmentFingerprint'] = _digest(result)
    return result


def assess_graph(graph, evidence=None, *, now=None):
    """Assess untrusted/imported evidence. Never enable family deduplication."""
    return _evaluate(graph, [] if evidence is None else evidence, set(), _now(now))


def assess_recorded(graph, receipts, *, now=None):
    """INTERNAL: assess current-owner, server-loaded receipts, never HTTP input.

    This pure function cannot establish database ownership. The adapter must
    select the signed-in owner's rows, verify DB status against receipt status,
    and bind the result to the graph/capture-history fingerprints. Old collector
    receipts remain diagnostics; latest current receipts are selected per source
    with 200-source and 2 MiB JSON working caps. Excluded valid sources remain
    nonauthorizing diagnostics and independent graph branches. A caller
    boolean, imported observation, or supplied receipt is not that boundary.
    """
    now, products = _now(now), _graph(graph)
    if type(receipts) is not list:
        raise ValueError('Expected recorded family receipts list')
    if (type(graph.get('cycleId')) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', graph['cycleId'])
            or type(graph.get('revision')) is not int or graph['revision'] < 0):
        raise ValueError('Invalid recorded graph scope')
    events = graph.get('events')
    if type(events) is not list or len(events) > 5000:
        raise ValueError('Recorded family assessment requires graph events')
    event_map = {}
    for event in events:
        if type(event) is not dict or type(event.get('id')) is not str or event['id'] in event_map:
            raise ValueError('Invalid graph event identity')
        event_map[event['id']] = event
    evidence, capture_ids, recorded_ids = [], set(), set()
    latest, recent_memberships, recent_snapshots = {}, {}, {}
    diagnostics = {'totalReceiptCount': len(receipts), 'obsoleteCollectorReceiptCount': 0,
        'currentCollectorReceiptCount': 0, 'selectedSourceCount': 0,
        'supersededReceiptCount': 0, 'sourceLimitExcludedCount': 0,
        'byteLimitExcludedCount': 0, 'byteLimitExcludedSourceIds': [],
        'selectedEvidenceBytes': 2, 'maxEvidenceBytes': MAX_EVIDENCE_BYTES,
        'conflictingSourceCount': 0, 'samples': []}
    receipt_digests = []
    # Fixed bundled code only. No path, digest, or authenticity switch is taken
    # from HTTP input; changing the collector invalidates previous receipts.
    current_collector = hashlib.sha256(Path(__file__).with_name('discovery-family-collector.js').read_bytes()).hexdigest()
    for receipt in receipts:
        _bounded(receipt, 524288)
        if (type(receipt) is not dict or receipt.get('captureKind') != 'family'
                or receipt.get('status') != 'captured'
                or receipt.get('cycleId') != graph.get('cycleId')
                or type(receipt.get('expectedRevision')) is not int
                or type(graph.get('revision')) is not int
                or not 0 <= receipt['expectedRevision'] <= graph['revision']):
            raise ValueError('Invalid recorded family receipt scope')
        capture_id = _text(receipt.get('captureId'), 'captureId', 100)
        if not re.fullmatch(r'[A-Za-z0-9_.:-]+', capture_id) or capture_id in capture_ids:
            raise ValueError('Duplicate or invalid captureId')
        capture_ids.add(capture_id)
        for name in ('collectorSha256', 'bindingDigest'):
            if type(receipt.get(name)) is not str or not re.fullmatch(r'[a-f0-9]{64}', receipt[name]):
                raise ValueError('Missing recorded capture fingerprint')
        receipt_digests.append((capture_id, _digest(receipt)))
        if receipt['collectorSha256'] != current_collector:
            diagnostics['obsoleteCollectorReceiptCount'] += 1
            diagnostics['samples'].append({'captureId': capture_id, 'reason': 'obsolete_collector_non_authorizing'})
            diagnostics['samples'].sort(key=lambda row: row['captureId'])
            del diagnostics['samples'][20:]
            continue
        item = _observation(receipt.get('familyEvidence'), now)
        if item['kind'] != 'visible_variant_controls':
            raise ValueError('Recorded capture lacks variant controls')
        market, asin = item['marketplace'], item['asin']
        if receipt.get('asin') != asin or receipt.get('marketplace') != market or market + ':' + asin not in products:
            raise ValueError('Recorded family target mismatch')
        parent_id = receipt.get('parentId')
        if type(parent_id) is not str:
            raise ValueError('Invalid recorded family parentId')
        parent = event_map.get(parent_id)
        if (parent is None or parent.get('marketplace') != market
                or parent.get('kind') not in ('keyword', 'search', 'store', 'seller')):
            raise ValueError('Recorded family parent mismatch')
        if parent.get('kind') in ('search', 'store'):
            parent_products = parent.get('products')
            if type(parent_products) is not list or len(parent_products) > 50 or any(type(x) is not dict for x in parent_products):
                raise ValueError('Invalid parent product evidence')
            targets = [x.get('asin') for x in parent_products]
        else:
            targets = [parent.get('asin')]
        if asin not in targets or (parent.get('kind') == 'store' and parent.get('status') != 'captured'):
            raise ValueError('Family product missing from parent')
        observed = _time(item['observedAt'], 'observedAt', now)
        if not (_time(parent.get('observedAt'), 'parent observation time', now)
                <= _time(receipt.get('startedAt'), 'startedAt', now)
                <= observed <= _time(receipt.get('finishedAt'), 'finishedAt', now)):
            raise ValueError('Recorded family observation time mismatch')
        diagnostics['currentCollectorReceiptCount'] += 1
        source = market + ':' + asin
        previous = latest.get(source)
        if previous is None or (item['observedAt'], item['observationId']) > (previous['observedAt'], previous['observationId']):
            latest[source] = item
        # Superseded snapshots do not create outgoing links, but material
        # disagreement within the freshness window cannot disappear by capping
        # history. Older historical membership changes are nonauthorizing.
        if now - observed <= MAX_DEDUP_AGE:
            signature = tuple(sorted({c['asin'] for c in item['controls']}))
            recent_memberships.setdefault(source, set()).add(signature)
            recent_snapshots.setdefault((source, item['observedAt']), set()).add(item['observationId'])
    conflict_sources = {source for source, values in recent_memberships.items() if len(values) > 1}
    conflict_sources.update(source for (source, _), values in recent_snapshots.items() if len(values) > 1)
    candidates = sorted(latest.items(), key=lambda x: (x[1]['observedAt'], x[0]), reverse=True)[:MAX_OBSERVATIONS]
    chosen, evidence_bytes, byte_excluded = [], 2, []
    for source, item in candidates:
        # Match _bounded's exact ASCII JSON representation, including the list's
        # brackets and comma-space separators. Individually valid captures must
        # not poison the whole plan by overflowing the aggregate working set.
        item_bytes = len(json.dumps(item, ensure_ascii=True, allow_nan=False))
        added_bytes = item_bytes + (2 if chosen else 0)
        if evidence_bytes + added_bytes > MAX_EVIDENCE_BYTES:
            byte_excluded.append(source)
            continue
        chosen.append((source, item))
        evidence_bytes += added_bytes
    evidence = [item for _, item in chosen]
    recorded_ids = {item['observationId'] for item in evidence}
    diagnostics.update(selectedSourceCount=len(chosen),
        supersededReceiptCount=diagnostics['currentCollectorReceiptCount'] - len(latest),
        sourceLimitExcludedCount=max(0, len(latest) - len(candidates)),
        byteLimitExcludedCount=len(byte_excluded),
        byteLimitExcludedSourceIds=sorted(byte_excluded)[:20],
        selectedEvidenceBytes=evidence_bytes,
        conflictingSourceCount=len(conflict_sources))
    result = _evaluate(graph, evidence, recorded_ids, now, conflict_sources)
    result['historyDiagnostics'] = diagnostics
    result['captureHistoryFingerprint'] = _digest(sorted(receipt_digests))
    result['assessmentFingerprint'] = _digest({k: v for k, v in result.items() if k != 'assessmentFingerprint'})
    return result


def title_dedup_key(assessment, marketplace, asin):
    """Internal planner hint. Call only with a freshly server-built assessment.

    Seller, sourcing, qualification and import must NEVER call this function.
    Pending or imported evidence always returns the original market+ASIN key.
    """
    key = _market(marketplace) + ':' + _asin(asin)
    for group in assessment.get('groups', []):
        if (assessment.get('authenticity') == 'server_recorded_capture'
                and group.get('dedupEligible') is True
                and group.get('status') == 'supported_visible_family'
                and group.get('dedupScope') == ['title_phrase_capture']
                and key in group.get('productIds', [])):
            return group['groupId']
    return key
