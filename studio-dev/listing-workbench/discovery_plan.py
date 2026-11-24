"""Bounded offline frontier preview. No navigation, capture, ingestion or retries.

Only already observed graph branches can become proposed actions. Unknown future
search results, sellers, stores and title phrases are never simulated. maxRounds
is an absolute proposed round-number ceiling, not an ongoing execution budget.
"""
import hashlib
import json
import re
import sqlite3

import cyclic_discovery as ledger
import discovery_browser as browser
import discovery_family as family


_KINDS = {
    'pending_search_capture': ('search_capture', 'keyword', 0),
    'needs_seller_capture': ('seller_capture', 'search', 1),
    'needs_store_capture': ('store_capture', 'seller', 2),
    'needs_title_phrase_capture': ('title_phrase_capture', 'store', 3),
}
_ACTIVE = frozenset(('capture_started', 'execution_unknown', 'unknown', 'running'))
_TERMINAL = frozenset(('captured', 'blocked', 'configuration_blocked',
                       'stopped', 'inaccessible', 'needs_review', 'cancelled'))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _request(user, data):
    ledger._owner(user)
    fields = {'cycleId', 'expectedRevision', 'maxActions', 'maxRounds'}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('Expected cycleId, expectedRevision, maxActions and maxRounds only')
    request = {'cycleId': ledger._id(data.get('cycleId'), 'cycleId')}
    revision = data.get('expectedRevision')
    if type(revision) is not int or revision < 0:
        raise ValueError('Invalid expectedRevision')
    request['expectedRevision'] = revision
    for name in ('maxActions', 'maxRounds'):
        if type(data[name]) is not int or not 1 <= data[name] <= 20:
            raise ValueError(name + ' must be an integer from 1 to 20')
        request[name] = data[name]
    return request


def _attempts(user):
    """Read ALL owner attempts, never the 100-row UI history or a writable DB.

    DB status and receipt must agree. An unreadable history cannot establish that
    there is no outstanding dispatch, so it is a global barrier, not an empty list.
    """
    if not browser.DB.exists():
        return [], _digest([]), []
    conn = None
    rows, fingerprints, blockers = [], [], []
    try:
        conn = sqlite3.connect(browser.DB.resolve().as_uri() + '?mode=ro',
                               uri=True, timeout=10)
        conn.execute('BEGIN')
        for capture_id, status, receipt in conn.execute(
                'SELECT id,status,receipt FROM attempts WHERE owner=? ORDER BY id', (user,)):
            fingerprints.append([capture_id, status, _digest(receipt)])
            value = json.loads(receipt)
            if (not isinstance(value, dict) or value.get('status') != status
                    or value.get('captureId') != capture_id
                    or not isinstance(value.get('cycleId'), str)
                    or not isinstance(value.get('parentId'), str)
                    or value.get('captureKind', 'seller') not in ('seller', 'store', 'search', 'family')):
                blockers.append({'reason': 'capture_history_inconsistent',
                                 'captureId': capture_id, 'status': status})
                continue
            rows.append(value)
            if status in _ACTIVE:
                blockers.append({'reason': 'prior_capture_unresolved',
                                 'captureId': capture_id, 'status': status,
                                 'cycleId': value.get('cycleId'), 'retryAllowed': False})
            elif status not in _TERMINAL:
                blockers.append({'reason': 'unrecognized_capture_status',
                                 'captureId': capture_id, 'status': status,
                                 'retryAllowed': False})
    except (OSError, sqlite3.Error, ValueError, TypeError):
        blockers.append({'reason': 'capture_history_unreadable', 'retryAllowed': False})
    finally:
        if conn is not None:
            conn.close()
    import discovery_live
    try:
        live_barriers = discovery_live.planner_barrier(user)
        blockers.extend(live_barriers)
        if live_barriers:
            fingerprints.append(['live_run_barriers', live_barriers])
    except (OSError, sqlite3.Error, ValueError, TypeError):
        blockers.append({'reason': 'live_run_history_unreadable', 'retryAllowed': False})
    return rows, _digest(fingerprints), blockers


def _target(kind, event, asin=None):
    if kind == 'search_capture':
        return ledger._norm(event['phrase'])
    if kind == 'store_capture':
        return event['sellerId']
    return asin


def _logical(kind, event, asin=None):
    return kind, event['marketplace'], _target(kind, event, asin)


def _receipt_branches(receipts, events, cycle):
    """Prevent a new attempt even when the previous capture was not ingested."""
    branches = {}
    for receipt in receipts:
        if receipt.get('cycleId') != cycle:
            continue
        event = events.get(receipt.get('parentId'))
        kind = receipt.get('captureKind', 'seller') + '_capture'
        if not event or kind not in ('search_capture', 'seller_capture', 'store_capture'):
            continue
        expected = {'search_capture': 'keyword', 'seller_capture': 'search',
                    'store_capture': 'seller'}[kind]
        if event['kind'] != expected:
            continue
        if kind == 'seller_capture':
            asin = receipt.get('asin')
            if asin not in [p['asin'] for p in event['products']]:
                continue
        else:
            asin = None
        if kind == 'store_capture' and receipt.get('sellerId') != event['sellerId']:
            continue
        key = _logical(kind, event, asin)
        branches.setdefault(key, []).append({
            'captureId': receipt['captureId'], 'status': receipt['status'],
            'reason': receipt.get('reason', 'capture_already_attempted'),
            'retryAllowed': False})
    return branches


def _action(kind, event, asin):
    source_round = event['round']
    action = {
        'kind': kind, 'status': 'proposed', 'marketplace': event['marketplace'],
        'sourceEventId': event['id'], 'sourceRound': source_round,
        'proposedRound': source_round + (kind == 'title_phrase_capture'),
        'source': {key: event[key] for key in
                   ('eventId', 'parentId', 'sourceURL', 'observedAt', 'round', 'trust')},
        'executionAllowed': False, 'retryAllowed': False,
    }
    if kind == 'search_capture':
        action.update(query=event['phrase'], normalizedQuery=event['normalizedPhrase'],
                      asin=event['asin'], requirements=[
                          'An independently opened, account-bound current search page matching this exact query is required.',
                          'Capture visible results once, verify the receipt, then ingest against a freshly checked revision.'])
    elif kind == 'seller_capture':
        product = next(p for p in event['products'] if p['asin'] == asin)
        action.update(asin=asin, listedTitle=product['title'], requirements=[
            'An independently opened, account-bound current product page matching this ASIN is required.',
            'Observe the visible Sold by link. Do not infer seller identity or same-product similarity.'])
    elif kind == 'store_capture':
        action.update(sellerId=event['sellerId'], asin=event['asin'], requirements=[
            'An independently opened, account-bound current seller listing matching this observed sellerId is required.',
            'Capture visible listing cards once. Do not substitute a brand store.'])
    else:
        product = next(p for p in event['products'] if p['asin'] == asin)
        action.update(asin=asin, listedTitle=product['title'], requirements=[
            'An explicit title-opening phrase from this exact recorded listing card is required.',
            'Use prepare_keyword with this store event and current revision; this preview supplies no phrase and saves nothing.'])
    return action


def prepare(user, data):
    """Return a deterministic, account-scoped preview; never perform its actions."""
    request = _request(user, data)
    report = ledger.report(user, request['cycleId'])
    if report['revision'] != request['expectedRevision']:
        raise ValueError('stale_revision')
    events = {e['id']: e for e in report['events']}
    receipts, history_fingerprint, blockers = _attempts(user)
    family_receipts = [r for r in receipts if r.get('captureKind') == 'family'
                       and r.get('status') == 'captured' and r.get('cycleId') == request['cycleId']]
    family_assessment = family.assess_recorded(report, family_receipts)
    handled_families = {family.title_dedup_key(family_assessment, e['marketplace'], e['asin'])
                        for e in events.values() if e['kind'] == 'keyword'}
    attempted = _receipt_branches(receipts, events, request['cycleId'])
    done = {
        'search_capture': {(e['marketplace'], ledger._norm(e['query']))
                           for e in events.values() if e['kind'] == 'search'},
        'seller_capture': {(e['marketplace'], e['asin'])
                           for e in events.values() if e['kind'] == 'seller'},
        'store_capture': {(e['marketplace'], e['sellerId'])
                          for e in events.values() if e['kind'] == 'store'},
        'title_phrase_capture': {(e['marketplace'], e['asin'])
                                 for e in events.values() if e['kind'] == 'keyword'},
    }
    candidates, skipped, review = [], [], []
    for row in report['queue']:
        event = events.get(row['eventId'])
        if event is None:
            raise ValueError('Invalid queue provenance')
        source = {'sourceEventId': event['id'], 'sourceRound': event['round'],
                  'marketplace': event['marketplace'], 'sourceASIN': row.get('sourceASIN'),
                  'sourceStatus': row['status'], 'executionAllowed': False}
        spec = _KINDS.get(row['status'])
        if spec is None:
            target = skipped if row['status'] in ('no_new_products', 'duplicate_keyword_already_searched') else review
            target.append({**source, 'reason': event.get('reason', row['status']),
                           'status': event.get('status', row['status']), 'retryAllowed': False})
            continue
        kind, source_kind, priority = spec
        if event['kind'] != source_kind:
            raise ValueError('Invalid queue source kind')
        if source_kind == 'store' and event.get('status') != 'captured':
            review.append({**source, 'reason': 'store_not_captured', 'retryAllowed': False})
            continue
        key = _logical(kind, event, row.get('sourceASIN'))
        family_key = None
        if kind == 'title_phrase_capture':
            family_key = family.title_dedup_key(family_assessment, event['marketplace'], row['sourceASIN'])
            if family_key.startswith('family-') and family_key in handled_families:
                skipped.append({**source, 'reason': 'observed_family_title_already_handled',
                                'kind': kind, 'familyGroupId': family_key,
                                'preserveSellerCapture': True})
                continue
        if key[1:] in done[kind]:
            skipped.append({**source, 'reason': 'already_handled_observed_target', 'kind': kind})
            continue
        if key in attempted:
            review.append({**source, 'reason': 'existing_capture_requires_review',
                           'kind': kind, 'attempts': attempted[key], 'retryAllowed': False})
            continue
        action = _action(kind, event, row.get('sourceASIN'))
        if family_key and family_key.startswith('family-'):
            action.update(familyGroupId=family_key, preserveSellerCapture=True)
            key = (kind, event['marketplace'], family_key)
        candidates.append((priority, key, action))
    candidates.sort(key=lambda item: (item[0], -item[2]['proposedRound'],
                                     item[1], item[2]['sourceEventId']))
    actions, seen, round_limited, action_limited = [], set(), 0, 0
    for _, key, action in candidates:
        if key in seen:
            skipped.append({**action, 'status': 'skipped', 'reason': 'observed_family_title_duplicate' if action.get('familyGroupId') else 'duplicate_proposed_target'})
            continue
        seen.add(key)
        if action['proposedRound'] > request['maxRounds']:
            round_limited += 1
            skipped.append({**action, 'status': 'skipped', 'reason': 'round_limit'})
        elif len(actions) >= request['maxActions']:
            action_limited += 1
            skipped.append({**action, 'status': 'skipped', 'reason': 'action_limit'})
        else:
            actions.append(action)
    # A second read catches concurrent ledger ingestion during the history read.
    # This remains a preview snapshot, not a dispatch lock or execution grant.
    latest = ledger.report(user, request['cycleId'])
    if latest['revision'] != report['revision'] or _digest(latest) != _digest(report):
        raise ValueError('stale_revision')
    _, latest_history_fingerprint, latest_blockers = _attempts(user)
    if latest_history_fingerprint != history_fingerprint or latest_blockers != blockers:
        raise ValueError('stale_capture_history')
    if blockers:
        skipped.extend({**a, 'status': 'blocked', 'reason': 'owner_capture_barrier'} for a in actions)
        actions = []
    proposed_rounds = sorted({a['proposedRound'] for a in actions})
    result = {
        'schemaVersion': 1, 'status': 'blocked' if blockers else ('ready' if actions else 'no_actions'),
        'readOnly': True, 'owner': user, 'cycleId': request['cycleId'],
        'revision': report['revision'], 'expectedRevision': request['expectedRevision'],
        'limits': {'maxActions': request['maxActions'], 'maxRounds': request['maxRounds']},
        'roundLimitMeaning': 'absolute_proposed_round_number',
        'observedRoundCount': report['roundCount'], 'actions': actions,
        'plannedActionCount': len(actions), 'proposedRounds': proposed_rounds,
        'proposedRoundCount': len(proposed_rounds),
        'skipped': sorted(skipped, key=lambda x: (x['sourceEventId'], x.get('sourceASIN') or x.get('asin', ''), x['reason'])),
        'review': sorted(review, key=lambda x: (x['sourceEventId'], x.get('sourceASIN') or '', x['reason'])),
        'blockers': blockers, 'roundLimitedCount': round_limited,
        'actionLimitedCount': action_limited,
        'executionAllowed': False, 'automaticNavigationImplemented': False,
        'qualificationEvaluated': False, 'qualifiedCount': 0, 'importedCount': 0,
        'externalCallsPerformed': 0, 'persistentQueueCreated': False,
        'familyAssessmentFingerprint': family_assessment['assessmentFingerprint'],
        'familyDedup': {'scope': 'title_phrase_capture_only',
                       'eligibleGroupCount': family_assessment['dedupEligibleGroupCount'],
                       'formalParentMappingEstablished': False, 'sellerCapturePreserved': True,
                       'originalNodesPreserved': True},
        'graphFingerprint': _digest(report), 'historyFingerprint': history_fingerprint,
        'nextStep': ('Review unresolved capture receipts without retrying, then prepare a fresh preview.' if blockers else
                     'Use the existing account-bound current-page capture workflow or provide the explicit title phrase required by the first action. Reconcile its receipt, ingest verified observations, and prepare a fresh preview.' if actions else
                     'Review stopped or inaccessible branches and any preview limits. No further action is proposed.'),
        'limitations': 'Offline preview only. No action ran. Future branches require new real observations and a fresh plan. Limits do not create a scheduler or authorize navigation, retries, qualification or import.',
    }
    result['planFingerprint'] = _digest(result)
    result['planId'] = result['planFingerprint']
    result['staleGuard'] = {'owner': user, 'cycleId': request['cycleId'],
                            'expectedRevision': request['expectedRevision'],
                            'planFingerprint': result['planFingerprint'],
                            'requiresFreshPrepare': True, 'executionAuthorization': False}
    return result


def assert_current(user, data, plan_fingerprint):
    """Recompute identity before using a preview; still never authorizes dispatch."""
    if not isinstance(plan_fingerprint, str) or not re.fullmatch('[a-f0-9]{64}', plan_fingerprint):
        raise ValueError('Invalid planFingerprint')
    current = prepare(user, data)
    if current['planFingerprint'] != plan_fingerprint:
        raise ValueError('stale_plan')
    return current
