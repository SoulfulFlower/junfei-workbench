"""Explicit, finite, isolated read-only browser discovery pilot.

Never enabled on production/account-worker DATA. Local observations are not
qualification, product import or publication. No work starts at module import.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import time

import app_paths
import cyclic_discovery as ledger
import discovery_browser as browser
import discovery_plan as planner


MODE = 'isolated_read_only_pilot'
ACTIVE = ('active', 'stopping', 'unknown')
UNRESOLVED = ('reserved', 'dispatch_unknown', 'unknown')
_context = ContextVar('discovery_live_internal_plan', default=None)
_leases = {}
_lease_lock = threading.Lock()
_threads = {}
_ORIGINAL_CONFIG = Path(__file__).resolve().parent.parent / 'automation' / 'config.json'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _now():
    return time.time()


def _schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS live_runs (
        owner INTEGER NOT NULL, id TEXT NOT NULL, space INTEGER NOT NULL,
        status TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(owner,id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS live_steps (
        owner INTEGER NOT NULL, run_id TEXT NOT NULL, number INTEGER NOT NULL,
        logical TEXT NOT NULL, token_hash TEXT NOT NULL, status TEXT NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY(owner,run_id,number), UNIQUE(owner,logical))''')


def _has_schema(c):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_runs'").fetchone())


@contextmanager
def _transaction(graph=False, existing=False):
    c = (sqlite3.connect(browser.DB.resolve().as_uri() + '?mode=rw', uri=True, timeout=20)
         if existing else browser._connect(True))
    try:
        c.execute('PRAGMA synchronous=FULL')
        if existing:
            if not _has_schema(c):
                raise ValueError('Live run not found')
        else:
            _schema(c)
        c.commit()
        if graph:
            if not ledger.DB.is_file() or ledger.DB.resolve() == browser.DB.resolve():
                raise ValueError('isolated_graph_required')
            c.execute('ATTACH DATABASE ? AS graph', (str(ledger.DB.resolve()),))
            # Atomic attached-DB commits require rollback journals, not WAL.
            durable_modes = ('delete', 'truncate', 'persist')
            if c.execute('PRAGMA main.journal_mode').fetchone()[0] not in durable_modes or c.execute('PRAGMA graph.journal_mode').fetchone()[0] not in durable_modes:
                raise ValueError('rollback_journal_required')
            c.execute('PRAGMA graph.synchronous=FULL')
        c.execute('BEGIN IMMEDIATE')
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def _run(c, user, run_id):
    row = c.execute('SELECT status,payload FROM live_runs WHERE owner=? AND id=?', (user, run_id)).fetchone()
    if not row:
        raise ValueError('Live run not found')
    value = json.loads(row[1])
    if value['status'] != row[0] or value['runId'] != run_id or value['owner'] != user:
        raise ValueError('live_history_inconsistent')
    limits = value.get('limits')
    if (not isinstance(limits, dict) or set(limits) != {'maxActions', 'maxRounds', 'maxSeconds'}
            or any(type(limits[k]) is not int or not low <= limits[k] <= high for k, low, high in
                   (('maxActions', 1, 20), ('maxRounds', 1, 20), ('maxSeconds', 15, 600)))
            or type(value.get('usedActions')) is not int or not 0 <= value['usedActions'] <= limits['maxActions']
            or type(value.get('revision')) is not int or value['revision'] < 1
            or type(value.get('stopRequested')) is not bool
            or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) for k in ('createdAt', 'deadline'))
            or value['deadline'] != value['createdAt'] + limits['maxSeconds']):
        raise ValueError('live_history_inconsistent')
    _stop_path(user, run_id, value.get('stopPath'))
    return value


def _stop_path(user, run_id, recorded=None):
    root = browser.DB.parent.resolve()
    directory = root / 'discovery-live-control'
    expected = directory / (_digest([user, run_id]) + '.stop')
    if directory.resolve() != directory or expected.resolve() != expected:
        raise ValueError('live_stop_path_escape')
    if recorded is not None and recorded != str(expected):
        raise ValueError('live_stop_path_mismatch')
    return expected


def _save_run(c, run):
    c.execute('UPDATE live_runs SET status=?,payload=? WHERE owner=? AND id=?',
              (run['status'], json.dumps(run), run['owner'], run['runId']))


def _save_step(c, user, run_id, step):
    c.execute('UPDATE live_steps SET status=?,payload=? WHERE owner=? AND run_id=? AND number=?',
              (step['status'], json.dumps(step), user, run_id, step['number']))


def _locked_runs(c, user, space=None, exempt=None):
    if not _has_schema(c):
        return []
    rows = c.execute('SELECT owner,id,space,status,payload FROM live_runs ORDER BY owner,id').fetchall()
    blockers = []
    for owner, rid, sid, state, raw in rows:
        if not (owner == user or (space is not None and sid == space)):
            continue
        try:
            run = json.loads(raw)
            valid = (isinstance(run, dict) and run.get('owner') == owner and run.get('runId') == rid
                     and run.get('status') == state and run.get('binding', {}).get('spaceId') == sid
                     and state in (*ACTIVE, 'completed', 'stopped', 'blocked'))
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            blockers.append({'reason': 'live_history_inconsistent', 'retryAllowed': False})
        elif state in ACTIVE and (owner, rid) != exempt:
            blockers.append({'reason': 'live_run_requires_review' if state == 'unknown' else 'live_run_owns_scope',
                             'runId': rid if owner == user else None, 'status': state, 'retryAllowed': False})
    return blockers


def planner_barrier(user):
    """Read-only owner barrier; private planning context cannot come from JSON."""
    ledger._owner(user)
    c = browser._connect()
    if c is None:
        return []
    try:
        return _locked_runs(c, user, exempt=_context.get())
    except (ValueError, TypeError, sqlite3.Error):
        return [{'reason': 'live_history_unreadable', 'retryAllowed': False}]
    finally:
        c.close()


def assert_owner_idle(user):
    if planner_barrier(user):
        raise ValueError('live_run_owns_scope')


@contextmanager
def owner_write_guard(user):
    """API ingestion must hold this lock throughout its ledger mutation."""
    ledger._owner(user)
    if os.environ.get('JUNFEI_DISCOVERY_LIVE') != 'isolated-read-only' and not planner_barrier(user):
        yield
        return
    with _transaction() as c:
        if _locked_runs(c, user):
            raise ValueError('live_run_owns_scope')
        yield


def _policy(user):
    if os.environ.get('JUNFEI_DISCOVERY_LIVE') != 'isolated-read-only' or app_paths.WORKER_USER or getattr(sys, 'frozen', False):
        raise ValueError('live_pilot_explicit_isolation_required')
    root, temp = browser.DB.parent.resolve(), Path(tempfile.gettempdir()).resolve()
    if root == temp or temp not in root.parents or ledger.DB.parent.resolve() != root:
        raise ValueError('live_pilot_temp_data_required')
    if browser.DB.resolve().parent != root or ledger.DB.resolve().parent != root:
        raise ValueError('live_pilot_database_path_escape')
    if app_paths.DATA.resolve() != root:
        raise ValueError('live_pilot_data_scope_mismatch')
    configured_root = os.environ.get('JUNFEI_PROJECT_ROOT', '')
    if not configured_root or not Path(configured_root).is_absolute():
        raise ValueError('live_pilot_temp_project_required')
    project = browser.runtime_environment.project_root().resolve()
    if project != Path(configured_root).resolve() or project == temp or temp not in project.parents or project == _ORIGINAL_CONFIG.parent.parent.resolve():
        raise ValueError('live_pilot_temp_project_required')
    config_path = project / 'automation' / 'config.json'
    if not config_path.is_file() or project not in config_path.resolve().parents:
        raise ValueError('live_pilot_config_path_escape')
    marker = json.loads((root / 'discovery-live-isolation.json').read_text(encoding='utf-8'))
    route, binding_hash = browser._binding(user)
    if marker != {'schemaVersion': 1, 'mode': 'isolated-read-only', 'owner': user,
                  'taskSpaceId': route['spaceId'], 'dedicatedSpace': True}:
        raise ValueError('live_pilot_marker_mismatch')
    config = browser.runtime_environment.configuration()
    bindings = config.get('discovery_browser', {}).get('account_bindings', {})
    if not isinstance(bindings, dict) or any(
            key != str(user) and isinstance(value, dict) and value.get('enabled') is True
            and value.get('task_space_id') == route['spaceId'] for key, value in bindings.items()):
        raise ValueError('live_pilot_shared_binding_forbidden')
    # A disposable pilot may never reuse a source application's production route.
    original = json.loads(_ORIGINAL_CONFIG.read_text(encoding='utf-8-sig'))
    forbidden = {original.get('browser', {}).get('task_space_id')}
    for value in original.get('discovery_browser', {}).get('account_bindings', {}).values():
        if isinstance(value, dict):
            forbidden.add(value.get('task_space_id'))
    if route['spaceId'] in forbidden:
        raise ValueError('live_pilot_production_space_forbidden')
    return route, binding_hash, _digest({'config': config, 'production': original, 'marker': marker})


def _request(user, data):
    ledger._owner(user)
    fields = {'runId', 'cycleId', 'expectedRevision', 'sourceEventId',
              'maxActions', 'maxRounds', 'maxSeconds', 'planFingerprint'}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('Expected exact finite live pilot request')
    request = {name: ledger._id(data[name], name) for name in ('runId', 'cycleId', 'sourceEventId')}
    for name, low, high in (('expectedRevision', 1, 5000), ('maxActions', 1, 20),
                            ('maxRounds', 1, 20), ('maxSeconds', 15, 600)):
        if type(data[name]) is not int or not low <= data[name] <= high:
            raise ValueError('Invalid ' + name)
        request[name] = data[name]
    if not isinstance(data['planFingerprint'], str) or not re.fullmatch('[a-f0-9]{64}', data['planFingerprint']):
        raise ValueError('Invalid planFingerprint')
    request['planFingerprint'] = data['planFingerprint']
    return request


@contextmanager
def _planning(user, run_id):
    token = _context.set((user, run_id))
    try:
        yield
    finally:
        _context.reset(token)


def _snapshot(user, request, run_id):
    with _planning(user, run_id):
        plan = planner.prepare(user, {k: request[k] for k in
                                     ('cycleId', 'expectedRevision', 'maxActions', 'maxRounds')})
    if plan['blockers']:
        raise ValueError('owner_capture_barrier')
    graph = ledger.report(user, request['cycleId'])
    if planner._digest(graph) != plan['graphFingerprint']:
        raise ValueError('stale_graph')
    return graph, plan


def _pick(graph, plan, source_id):
    source = next((e for e in graph['events'] if e['id'] == source_id), None)
    if source is None:
        raise ValueError('live_source_missing')
    # Planner preview limits are not our durable budget; recover only its
    # otherwise-valid action_limit entries, never blocked/round-limited entries.
    candidates = [a for a in plan['actions'] + [a for a in plan['skipped'] if a.get('reason') == 'action_limit']
                  if a['sourceEventId'] == source_id]
    order = {p['asin']: i for i, p in enumerate(source.get('products', []))}
    candidates.sort(key=lambda a: (order.get(a.get('asin'), 0), a['kind'], a.get('asin', '')))
    if not candidates:
        return None
    chosen = dict(candidates[0])
    chosen.update(selectionPolicy='coverage_smoke_first_visible_unhandled_not_quality_ranking',
                  chosenVisibleIndex=order.get(chosen.get('asin')),
                  similarityEvaluated=False)
    return chosen


def title_prefix(title):
    """Literal first eight whitespace-delimited tokens, capped at 300 chars.

    No branding deletion, normalization, rewriting, synonyms or EXACT inference.
    The returned bytes are a contiguous opening of the actually observed title.
    """
    title = ledger._text(title, 'listedTitle')
    tokens = list(re.finditer(r'\S+', title))
    end = tokens[min(len(tokens), 8) - 1].end()
    if end > 300:
        endings = [m.end() for m in tokens[:8] if m.end() <= 300]
        if not endings:
            raise ValueError('title_opening_too_long')
        end = endings[-1]
    return title[:end]


def _logical(action):
    target = action.get('normalizedQuery') if action['kind'] == 'search_capture' else action.get('sellerId') if action['kind'] == 'store_capture' else action.get('familyGroupId', action.get('asin'))
    return _digest([action['kind'], action['marketplace'], target])


def _capture_request(run, action, number):
    request = {'captureId': 'live-' + _digest([run['owner'], run['runId'], number])[:48],
               'cycleId': run['cycleId'], 'expectedRevision': run['revision'],
               'parentId': action['sourceEventId']}
    if action['kind'] == 'seller_capture':
        request['asin'] = action['asin']
    if action['kind'] == 'store_capture':
        request['sellerId'] = action['sellerId']
    return request


class _Lease:
    def __init__(self, user, run_id, number, token, stop_path, deadline):
        self.user, self.run_id, self.number, self.token = user, run_id, number, token
        self.stop_path, self.deadline = stop_path, deadline


def _verify_lease(c, lease, user, request=None, kind=None, after=False):
    with _lease_lock:
        valid = type(lease) is _Lease and _leases.get(id(lease)) is lease
    if not valid or lease.user != user:
        raise ValueError('trusted_live_lease_required')
    run = _run(c, user, lease.run_id)
    row = c.execute('SELECT token_hash,status,payload FROM live_steps WHERE owner=? AND run_id=? AND number=?',
                    (user, lease.run_id, lease.number)).fetchone()
    if not row or not secrets.compare_digest(row[0], _digest(lease.token)):
        raise ValueError('live_lease_mismatch')
    step = json.loads(row[2])
    if row[1] != step['status'] or step['status'] not in ('reserved', 'dispatch_unknown'):
        raise ValueError('live_step_not_dispatchable')
    if run['status'] != 'active' or run.get('stopRequested') or lease.stop_path.exists():
        raise ValueError('live_stop_requested')
    if _now() >= run['deadline']:
        raise ValueError('live_deadline_expired')
    if request is not None and (request != step['request'] or kind + '_capture' != step['action']['kind']):
        raise ValueError('live_lease_target_mismatch')
    return run, step


def _browser_guard(c, user, binding, lease=None):
    """Called by capture inside its BEGIN IMMEDIATE transaction."""
    exempt = None
    if lease is not None:
        run, _ = _verify_lease(c, lease, user)
        if binding != run['binding']:
            raise ValueError('live_binding_changed')
        exempt = (user, lease.run_id)
    if _locked_runs(c, user, binding['spaceId'], exempt):
        raise ValueError('live_run_owns_scope')


def _check_lease(lease, user, request, kind, phase='before_dispatch'):
    c = browser._connect()
    if c is None:
        raise ValueError('live_lease_missing')
    try:
        run, step = _verify_lease(c, lease, user, request, kind, phase == 'after_capture')
        route, binding_hash, config_hash = _policy(user)
        if (route, binding_hash, config_hash) != (run['binding'], run['bindingFingerprint'], run['configFingerprint']):
            raise ValueError('live_configuration_changed')
        graph = ledger.report(user, run['cycleId'])
        if planner._digest(graph) != step['graphFingerprint'] or graph['revision'] != step['request']['expectedRevision']:
            raise ValueError('live_graph_changed')
        history = [[cid, state, planner._digest(raw)] for cid, state, raw in c.execute(
            'SELECT id,status,receipt FROM attempts WHERE owner=? AND id<>? ORDER BY id',
            (user, step['request']['captureId']))]
        if planner._digest(history) != step['historyFingerprint']:
            raise ValueError('live_capture_history_changed')
        return {'cancelPath': str(lease.stop_path), 'deadline': run['deadline']}
    finally:
        c.close()


def _dispatch_started(lease, user, request, kind):
    _check_lease(lease, user, request, kind)
    with _transaction() as c:
        run, step = _verify_lease(c, lease, user, request, kind)
        if step['status'] != 'reserved':
            raise ValueError('live_dispatch_already_attempted')
        step.update(status='dispatch_unknown', dispatchedAt=_now())
        _save_step(c, user, run['runId'], step)


def start(user, data):
    """Authenticated caller supplies owner; request never accepts credentials/URL/code."""
    request = _request(user, data)
    route, binding_hash, config_hash = _policy(user)
    with _transaction(graph=True) as c:
        old = c.execute('SELECT request_hash FROM live_runs WHERE owner=? AND id=?', (user, request['runId'])).fetchone()
        if old:
            if old[0] != _digest(request):
                raise ValueError('Conflicting runId reuse')
            # Idempotent read only. Never relaunch an abandoned/finished worker.
            return _public(c, _run(c, user, request['runId']))
        if _locked_runs(c, user, route['spaceId']) or browser._history_blocks(c, user):
            raise ValueError('prior_run_or_capture_unresolved')
        # Capture worker also blocks same-space attempts across owners in this DB.
        for status_value, raw in c.execute('SELECT status,receipt FROM attempts'):
            receipt = json.loads(raw)
            if receipt.get('target', {}).get('taskSpaceId') == route['spaceId'] and status_value in browser.UNRESOLVED_HISTORY:
                raise ValueError('bound_space_capture_unresolved')
        graph, plan = _snapshot(user, request, request['runId'])
        if plan['planFingerprint'] != request['planFingerprint']:
            raise ValueError('stale_plan')
        source = next((e for e in graph['events'] if e['id'] == request['sourceEventId']), None)
        if not source or source['kind'] not in ('keyword', 'store'):
            raise ValueError('live_seed_must_be_observed_keyword_or_store')
        if not _pick(graph, plan, request['sourceEventId']):
            raise ValueError('live_seed_has_no_action')
        now = _now()
        marker_dir = browser.DB.parent / 'discovery-live-control'
        marker_dir.mkdir(exist_ok=True)
        stop_path = _stop_path(user, request['runId'])
        if stop_path.exists():
            raise ValueError('live_stop_marker_exists')
        run = {'schemaVersion': 1, 'owner': user, 'runId': request['runId'],
               'cycleId': request['cycleId'], 'status': 'active', 'reason': 'explicit_start',
               'revision': graph['revision'], 'cursor': request['sourceEventId'],
               'limits': {k: request[k] for k in ('maxActions', 'maxRounds', 'maxSeconds')},
               'usedActions': 0, 'createdAt': now, 'deadline': now + request['maxSeconds'],
               'stopRequested': False, 'binding': route, 'bindingFingerprint': binding_hash,
               'configFingerprint': config_hash, 'graphFingerprint': plan['graphFingerprint'],
               'historyFingerprint': plan['historyFingerprint'], 'planFingerprint': plan['planFingerprint'],
               'stopPath': str(stop_path)}
        c.execute('INSERT INTO live_runs VALUES (?,?,?,?,?,?)',
                  (user, request['runId'], route['spaceId'], 'active', _digest(request), json.dumps(run)))
    try:
        _launch_worker(user, request['runId'])
    except BaseException:
        _halt(user, request['runId'], 'worker_start_failed')
        raise
    return status(user, request['runId'])


def _launch_worker(user, run_id):
    worker = threading.Thread(target=_work, args=(user, run_id), daemon=True,
                              name='discovery-live-' + run_id)
    _threads[(user, run_id)] = worker
    worker.start()


def _reserve(user, run_id):
    with _transaction(graph=True) as c:
        run = _run(c, user, run_id)
        if run['status'] != 'active':
            return None
        if run['stopRequested'] or _now() >= run['deadline'] or run['usedActions'] >= run['limits']['maxActions']:
            run.update(status='stopped', reason='stop_requested' if run['stopRequested'] else 'time_limit' if _now() >= run['deadline'] else 'action_limit')
            _save_run(c, run)
            return None
        if c.execute('SELECT 1 FROM live_steps WHERE owner=? AND status IN (?,?,?)', (user, *UNRESOLVED)).fetchone():
            raise ValueError('live_step_unresolved')
        route, binding_hash, config_hash = _policy(user)
        if (route, binding_hash, config_hash) != (run['binding'], run['bindingFingerprint'], run['configFingerprint']):
            raise ValueError('live_configuration_changed')
        graph, plan = _snapshot(user, {'cycleId': run['cycleId'], 'expectedRevision': run['revision'], **run['limits']}, run_id)
        if plan['graphFingerprint'] != run['graphFingerprint'] or plan['historyFingerprint'] != run['historyFingerprint']:
            raise ValueError('live_graph_or_history_changed')
        action = _pick(graph, plan, run['cursor'])
        if action is None:
            run.update(status='completed', reason='branch_exhausted_or_round_limited')
            _save_run(c, run)
            return None
        logical = _logical(action)
        if c.execute('SELECT 1 FROM live_steps WHERE owner=? AND logical=?', (user, logical)).fetchone():
            run.update(status='completed', reason='previously_attempted_target')
            _save_run(c, run)
            return None
        number, token = run['usedActions'] + 1, secrets.token_hex(32)
        request = _capture_request(run, action, number)
        step = {'number': number, 'status': 'reserved', 'action': action, 'request': request,
                'reservedAt': _now(), 'graphFingerprint': plan['graphFingerprint'],
                'planFingerprint': plan['planFingerprint'], 'historyFingerprint': plan['historyFingerprint']}
        c.execute('INSERT INTO live_steps VALUES (?,?,?,?,?,?,?)',
                  (user, run_id, number, logical, _digest(token), 'reserved', json.dumps(step)))
        run['usedActions'] = number
        _save_run(c, run)
        lease = _Lease(user, run_id, number, token, Path(run['stopPath']), run['deadline'])
        with _lease_lock:
            _leases[id(lease)] = lease
        return lease, step


def _ingest_attached(c, run, batch):
    if set(batch) != {'cycleId', 'expectedRevision', 'events'} or batch['cycleId'] != run['cycleId'] or batch['expectedRevision'] != run['revision'] or len(batch['events']) != 1:
        raise ValueError('live_batch_mismatch')
    row = c.execute('SELECT revision FROM graph.discovery_cycles WHERE owner=? AND cycle=?', (run['owner'], run['cycleId'])).fetchone()
    if row is None or row[0] != run['revision']:
        raise ValueError('live_graph_changed')
    events = {r[0]: json.loads(r[1]) for r in c.execute('SELECT id,payload FROM graph.discovery_events WHERE owner=? AND cycle=? ORDER BY rowid', (run['owner'], run['cycleId']))}
    event = ledger._clean(batch['events'][0])
    if event['id'] in events or len(events) >= 5000:
        raise ValueError('live_duplicate_or_full_graph')
    events[event['id']] = event
    ledger._validate_graph(events)
    c.execute('INSERT INTO graph.discovery_events VALUES (?,?,?,?)', (run['owner'], run['cycleId'], event['id'], json.dumps(event, ensure_ascii=False, sort_keys=True)))
    c.execute('UPDATE graph.discovery_cycles SET revision=revision+1 WHERE owner=? AND cycle=?', (run['owner'], run['cycleId']))
    run.update(revision=run['revision'] + 1, cursor=event['id'])
    run['graphFingerprint'] = planner._digest(ledger._report(run['cycleId'], run['revision'], events))
    return event


def _finish(lease, receipt):
    with _transaction(graph=True) as c:
        run, step = _verify_lease(c, lease, lease.user)
        action = step['action']
        is_title = action['kind'] == 'title_phrase_capture'
        if planner._digest(ledger.report(lease.user, run['cycleId'])) != step['graphFingerprint']:
            raise ValueError('live_graph_changed')
        route, binding_hash, config_hash = _policy(lease.user)
        if (route, binding_hash, config_hash) != (run['binding'], run['bindingFingerprint'], run['configFingerprint']):
            raise ValueError('live_configuration_changed')
        if not isinstance(receipt, dict) or receipt.get('status') not in ('captured', 'prepared'):
            unknown = not isinstance(receipt, dict) or receipt.get('status') in ('capture_started', 'execution_unknown', 'unknown')
            step.update(status='unknown' if unknown else 'blocked', reason='capture_unknown' if unknown else str(receipt.get('reason', 'capture_blocked'))[:100], finishedAt=_now())
            run.update(status='unknown' if unknown else 'blocked', reason=step['reason'])
        else:
            if is_title:
                if receipt.get('status') != 'prepared':
                    raise ValueError('live_title_receipt_mismatch')
            else:
                stored = c.execute('SELECT status,receipt FROM attempts WHERE owner=? AND id=?', (lease.user, step['request']['captureId'])).fetchone()
                if not stored or stored[0] != 'captured' or json.loads(stored[1]) != receipt:
                    raise ValueError('live_capture_receipt_not_recorded')
            batch = receipt['preparedBatch']
            event = _ingest_attached(c, run, batch)
            if event['parentId'] != action['sourceEventId'] or event['kind'] != {'search_capture': 'search', 'seller_capture': 'seller', 'store_capture': 'store', 'title_phrase_capture': 'keyword'}[action['kind']]:
                raise ValueError('live_event_target_mismatch')
            step.update(status='observed', observationId=event['id'], finishedAt=_now(),
                        browserCapturePerformed=not is_title,
                        titlePolicy='literal_first_8_whitespace_tokens_max_300_chars' if is_title else None)
            # Refresh only own graph/history changes. Budget/deadline stay immutable.
            with _planning(lease.user, lease.run_id):
                _, history_hash, blockers = planner._attempts(lease.user)
            if blockers:
                raise ValueError('owner_capture_barrier')
            run['historyFingerprint'] = history_hash
        _save_step(c, lease.user, lease.run_id, step)
        _save_run(c, run)


def _halt(user, run_id, reason):
    with _transaction() as c:
        run = _run(c, user, run_id)
        unresolved = c.execute('SELECT number,status,payload FROM live_steps WHERE owner=? AND run_id=? AND status IN (?,?,?)', (user, run_id, *UNRESOLVED)).fetchall()
        unknown = False
        for _, state, raw in unresolved:
            step = json.loads(raw)
            # Reserved actions have not been dispatched by the trusted bridge.
            state = 'cancelled_before_dispatch' if state == 'reserved' else 'unknown'
            step.update(status=state, reason=reason, finishedAt=_now())
            unknown |= state == 'unknown'
            _save_step(c, user, run_id, step)
        if run['status'] == 'unknown':
            unknown = True
        run.update(status='unknown' if unknown else 'stopped', reason=reason)
        _save_run(c, run)


def _work(user, run_id):
    try:
        while True:
            reserved = _reserve(user, run_id)
            if reserved is None:
                return
            lease, step = reserved
            try:
                action = step['action']
                if action['kind'] == 'title_phrase_capture':
                    receipt = ledger.prepare_keyword(user, {
                        'cycleId': step['request']['cycleId'], 'expectedRevision': step['request']['expectedRevision'],
                        'parentId': action['sourceEventId'], 'asin': action['asin'],
                        'phrase': title_prefix(action['listedTitle'])})
                else:
                    receipt = browser.capture_live(user, step['request'], action['kind'].removesuffix('_capture'), lease)
                _finish(lease, receipt)
            finally:
                with _lease_lock:
                    _leases.pop(id(lease), None)
    except Exception:
        # No retry, no resume, no refund. Error details are not allowed to leak
        # runtime command lines, route paths or credentials into API responses.
        _halt(user, run_id, 'worker_stopped_for_review')


def _public(c, run):
    steps = [json.loads(row[0]) for row in c.execute('SELECT payload FROM live_steps WHERE owner=? AND run_id=? ORDER BY number', (run['owner'], run['runId']))]
    attempts = [{'number': s['number'], 'kind': s['action']['kind'], 'status': s['status'],
                 'sourceEventId': s['action']['sourceEventId'], 'proposedRound': s['action']['proposedRound'],
                 'selectionPolicy': s['action'].get('selectionPolicy'),
                 'chosenVisibleIndex': s['action'].get('chosenVisibleIndex'),
                 'similarityEvaluated': False,
                 **{k: s[k] for k in ('reason', 'observationId', 'browserCapturePerformed', 'titlePolicy') if k in s}}
                for s in steps]
    observed = [s for s in steps if s['status'] == 'observed']
    return {'schemaVersion': 1, 'mode': MODE, 'runId': run['runId'], 'cycleId': run['cycleId'],
            'status': run['status'], 'reason': run['reason'], 'revision': run['revision'],
            'limits': run['limits'], 'usedActions': run['usedActions'], 'deadline': run['deadline'],
            'stopRequested': run['stopRequested'], 'attempts': attempts,
            'observedStages': {kind: sum(s['action']['kind'] == kind for s in observed) for kind in
                               ('search_capture', 'seller_capture', 'store_capture', 'title_phrase_capture')},
            'browserCapturesRecorded': sum(s.get('browserCapturePerformed', False) for s in observed),
            'completedObservationCount': len(observed),
            'unresolvedStepCount': sum(s['status'] in UNRESOLVED for s in steps),
            'qualificationEvaluated': False, 'qualifiedCount': 0, 'importedCount': 0,
            'paidCallsPerformed': 0, 'uploadsPerformed': 0, 'publicationsPerformed': 0,
            'automaticResumeAllowed': False, 'retryAllowed': False,
            'branchPolicy': 'one_branch_first_visible_unhandled_depth_first',
            'coordinationScope': 'same_isolated_DATA_database_only_not_machine_global',
            'productionExecutionAllowed': False}


def status(user, run_id):
    ledger._owner(user)
    run_id = ledger._id(run_id, 'runId')
    c = browser._connect()
    if c is None:
        raise ValueError('Live run not found')
    try:
        c.execute('BEGIN')
        if not _has_schema(c):
            raise ValueError('Live run not found')
        return _public(c, _run(c, user, run_id))
    finally:
        c.close()


def stop(user, run_id, cancel=False):
    ledger._owner(user)
    run_id = ledger._id(run_id, 'runId')
    if type(cancel) is not bool:
        raise ValueError('cancel must be boolean')
    # Read-only existence/owner check first, then mode=rw never creates a DB
    # even if somebody removes it between these two operations.
    status(user, run_id)
    with _transaction(existing=True) as c:
        run = _run(c, user, run_id)
        if run['status'] not in ACTIVE:
            return _public(c, run)
        # Persist the stop marker before releasing the DB lock. In-flight JS
        # checks it before navigation and evaluation. Existing markers survive.
        _stop_path(user, run_id, run['stopPath']).write_text('cancel' if cancel else 'stop', encoding='ascii')
        run.update(stopRequested=True, status='stopping', reason='cancel_requested' if cancel else 'stop_requested')
        _save_run(c, run)
    _halt(user, run_id, 'cancel_requested' if cancel else 'stop_requested')
    return status(user, run_id)
