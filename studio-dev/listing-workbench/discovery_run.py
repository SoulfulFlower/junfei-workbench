"""Read-only live assessment and a durable, OFFLINE-ONLY control simulation.

There is deliberately no live runner, injected callable, browser dispatch,
ingestion, scheduler or API mutation route in this module. Simulation receipts
are not observations and cannot qualify, import or publish a product.
"""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import uuid


_KINDS = frozenset(('search_capture', 'seller_capture', 'store_capture',
                    'title_phrase_capture'))
_UNRESOLVED = frozenset(('reserved', 'dispatch_unknown', 'unknown'))
_OUTCOMES = frozenset(('simulated_observed', 'simulated_blocked',
                       'simulated_inaccessible', 'unknown'))
_PHASES = _UNRESOLVED | _OUTCOMES | {'cancelled_before_dispatch', 'expired_before_dispatch'}
_RUN_STATES = frozenset(('ready', 'reserved', 'dispatch_unknown', 'waiting_for_plan',
                         'completed', 'blocked', 'stopped', 'cancelled', 'unknown'))
_FINAL = frozenset(('completed', 'blocked', 'stopped', 'cancelled', 'unknown'))
_FLAGS = dict(mode='simulation_only', simulationOnly=True, executionAllowed=False,
              automaticNavigationImplemented=False, externalCallsPerformed=0,
              qualificationEvaluated=False, qualifiedCount=0, importedCount=0)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise ValueError('invalid_identifier')
    return value


def _owner(value):
    if type(value) is not int or value < 1:
        raise ValueError('invalid_owner')
    return value


def _limit(value, name, maximum=20):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError('invalid_' + name)
    return value


def _fingerprint(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('invalid_fingerprint')
    return value


def inspect(user, data):
    """Read-only API-facing safety report. This is NOT an execution preflight.

    Same exact request contract as discovery_plan.prepare. Read current plan,
    effective account binding, and plan again; fail on changed snapshots. The
    binding fingerprint describes configured scope, not live tab ownership.
    """
    import discovery_plan as plan
    result = plan.prepare(user, data)
    binding = {'status': 'blocked', 'fingerprint': None,
               'liveOwnershipVerified': False}
    try:
        _, fingerprint = plan.browser._binding(user)
        binding.update(status='configured', fingerprint=fingerprint)
    except (ValueError, OSError):
        # Do not expose configuration, credentials or local installation paths.
        binding['reason'] = 'account_browser_binding_unavailable'
    latest = plan.assert_current(user, data, result['planFingerprint'])
    if binding['status'] == 'configured':
        try:
            _, fingerprint = plan.browser._binding(user)
        except (ValueError, OSError):
            raise ValueError('stale_configuration') from None
        if fingerprint != binding['fingerprint']:
            raise ValueError('stale_configuration')
    blockers = list(latest['blockers'])
    if binding['status'] != 'configured':
        blockers.append({'reason': binding['reason'], 'retryAllowed': False})
    blockers.extend([
        {'reason': 'production_bounded_runner_disabled', 'retryAllowed': False},
        {'reason': 'live_navigation_and_ownership_not_verified', 'retryAllowed': False},
        {'reason': 'simulation_is_not_live_execution_evidence', 'retryAllowed': False},
    ])
    return {
        'schemaVersion': 1, 'status': 'execution_disabled', 'readOnly': True,
        'owner': user, 'cycleId': latest['cycleId'], 'revision': latest['revision'],
        'executionAllowed': False, 'automaticNavigationImplemented': False,
        'persistentLiveQueueCreated': False, 'externalCallsPerformed': 0,
        'qualificationEvaluated': False, 'qualifiedCount': 0, 'importedCount': 0,
        'planId': latest['planId'], 'planFingerprint': latest['planFingerprint'],
        'graphFingerprint': latest['graphFingerprint'],
        'historyFingerprint': latest['historyFingerprint'],
        'limits': latest['limits'], 'roundLimitMeaning': 'absolute_proposed_round_number',
        'plannedActionCount': latest['plannedActionCount'],
        'binding': binding, 'blockers': blockers,
        'offlineControlAvailable': True, 'offlineControlMode': 'simulation_only',
        'isolatedPilotAvailable': True, 'isolatedPilotScope': 'source_only_temp_data_dedicated_space',
        'readinessScope': 'production_app_not_isolated_pilot',
        'nextStep': 'Review observations and current-page capture receipts. No live run can be started here.',
    }


def simulation_snapshot(owner, cycle_id, revision, actions, *, graph_fingerprint,
                        history_fingerprint, config_fingerprint,
                        ownership_fingerprint, owner_unresolved=False):
    """Build explicitly synthetic, data-only input. Never accepts a real plan.

    Fingerprints are fixture identities, not proof that a live page was checked.
    Each fixture action has actionId, sourceEventId, kind and proposedRound only.
    """
    value = dict(simulationOnly=True, owner=_owner(owner), cycleId=_id(cycle_id),
                 revision=revision, actions=actions,
                 graphFingerprint=graph_fingerprint, historyFingerprint=history_fingerprint,
                 configFingerprint=config_fingerprint, ownershipFingerprint=ownership_fingerprint,
                 ownerUnresolved=owner_unresolved)
    value['snapshotFingerprint'] = _digest(value)
    return _snapshot(value)


def _snapshot(value):
    fields = {'simulationOnly', 'owner', 'cycleId', 'revision', 'actions',
              'graphFingerprint', 'historyFingerprint', 'configFingerprint',
              'ownershipFingerprint', 'ownerUnresolved', 'snapshotFingerprint'}
    if not isinstance(value, dict) or set(value) != fields or value['simulationOnly'] is not True:
        raise ValueError('simulation_snapshot_required')
    _owner(value['owner'])
    _id(value['cycleId'])
    if type(value['revision']) is not int or value['revision'] < 0:
        raise ValueError('invalid_revision')
    if type(value['ownerUnresolved']) is not bool:
        raise ValueError('invalid_owner_barrier')
    for field in fields:
        if field.endswith('Fingerprint'):
            _fingerprint(value[field])
    actions = value['actions']
    if not isinstance(actions, list) or len(actions) > 20:
        raise ValueError('invalid_simulation_actions')
    seen = set()
    for action in actions:
        if not isinstance(action, dict) or set(action) != {'actionId', 'sourceEventId', 'kind', 'proposedRound'}:
            raise ValueError('invalid_simulation_action')
        _id(action['actionId'])
        _id(action['sourceEventId'])
        if action['kind'] not in _KINDS:
            raise ValueError('invalid_simulation_kind')
        _limit(action['proposedRound'], 'round')
        if action['actionId'] in seen:
            raise ValueError('duplicate_action')
        seen.add(action['actionId'])
    if _digest({k: v for k, v in value.items() if k != 'snapshotFingerprint'}) != value['snapshotFingerprint']:
        raise ValueError('snapshot_fingerprint_mismatch')
    return json.loads(json.dumps(value, allow_nan=False))


class OfflineSimulation:
    """Crash-safe local fixture controller; explicitly restricted to OS temp.

    The caller may simulate reservation, dispatch intent and outcomes as separate
    steps. These are SQLite state transitions only. No external adapter, callback,
    command, URL, product data or credentials are accepted. A fresh object over
    the same sandbox resumes bookkeeping, never automatically replays a step.
    """

    def __init__(self, sandbox, *, simulation_only=False):
        if simulation_only is not True:
            raise ValueError('simulation_only_opt_in_required')
        root = Path(sandbox).resolve()
        temp = Path(tempfile.gettempdir()).resolve()
        if not root.is_dir() or root == temp or temp not in root.parents:
            raise ValueError('existing_temporary_sandbox_required')
        # Never accept the application's configured or default live data tree,
        # even when an installation itself happens to be inside TEMP.
        import os
        live_roots = [Path(__file__).resolve().parent / 'data']
        configured = os.environ.get('JUNFEI_ACCOUNT_DATA')
        if configured:
            live_roots.append(Path(configured).resolve())
        if any(root == p.resolve() or p.resolve() in root.parents for p in live_roots):
            raise ValueError('production_data_forbidden')
        self.db = root / 'discovery-run-simulation.sqlite3'
        if self.db.is_symlink():
            raise ValueError('simulation_database_symlink_forbidden')
        self._initialize()

    def _initialize(self):
        with self._transaction(check=False) as c:
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and tables != {'simulation_meta', 'simulation_runs', 'simulation_attempts'}:
                raise ValueError('not_a_simulation_database')
            if tables:
                self._check_schema(c)
                return
            c.execute('CREATE TABLE simulation_meta (mode TEXT NOT NULL, version INTEGER NOT NULL)')
            c.execute("INSERT INTO simulation_meta VALUES ('simulation_only',1)")
            c.execute('''CREATE TABLE simulation_runs (
                owner INTEGER NOT NULL, id TEXT NOT NULL, cycle TEXT NOT NULL,
                initial_digest TEXT NOT NULL, snapshot TEXT NOT NULL,
                max_actions INTEGER NOT NULL, max_rounds INTEGER NOT NULL,
                used_actions INTEGER NOT NULL, state TEXT NOT NULL, reason TEXT,
                PRIMARY KEY(owner,id))''')
            c.execute('''CREATE TABLE simulation_attempts (
                owner INTEGER NOT NULL, run_id TEXT NOT NULL, cycle TEXT NOT NULL,
                action_id TEXT NOT NULL, round INTEGER NOT NULL, token TEXT NOT NULL,
                phase TEXT NOT NULL, expires REAL NOT NULL, snapshot_digest TEXT NOT NULL,
                PRIMARY KEY(owner,cycle,action_id), UNIQUE(owner,token))''')

    @staticmethod
    def _check_schema(c):
        if list(c.execute('SELECT mode,version FROM simulation_meta')) != [('simulation_only', 1)]:
            raise ValueError('not_a_simulation_database')

    @contextmanager
    def _transaction(self, *, check=True):
        c = sqlite3.connect(str(self.db), timeout=10)
        try:
            c.execute('PRAGMA synchronous=FULL')
            c.execute('BEGIN IMMEDIATE')
            if check:
                self._check_schema(c)
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def _run(c, owner, run_id):
        _owner(owner)
        _id(run_id)
        row = c.execute('''SELECT cycle,initial_digest,snapshot,max_actions,max_rounds,
                           used_actions,state,reason FROM simulation_runs WHERE owner=? AND id=?''',
                        (owner, run_id)).fetchone()
        if row is None:
            raise ValueError('simulation_run_not_found')
        value = dict(zip(('cycle', 'initial_digest', 'snapshot', 'max_actions', 'max_rounds',
                          'used_actions', 'state', 'reason'), row))
        value['snapshot'] = _snapshot(json.loads(value['snapshot']))
        if (value['state'] not in _RUN_STATES or value['snapshot']['owner'] != owner
                or value['snapshot']['cycleId'] != value['cycle']):
            raise ValueError('simulation_state_corrupt')
        _limit(value['max_actions'], 'actions')
        _limit(value['max_rounds'], 'rounds')
        if type(value['used_actions']) is not int or not 0 <= value['used_actions'] <= value['max_actions']:
            raise ValueError('simulation_budget_corrupt')
        count = c.execute('SELECT COUNT(*) FROM simulation_attempts WHERE owner=? AND run_id=?',
                          (owner, run_id)).fetchone()[0]
        if count != value['used_actions']:
            raise ValueError('simulation_budget_corrupt')
        return value

    @staticmethod
    def _barrier(c, owner, *, excluding_token=None):
        # ALL owner attempts, across every run and cycle, including old history.
        rows = c.execute('SELECT run_id,action_id,token,phase FROM simulation_attempts WHERE owner=?', (owner,))
        blocked = []
        for run_id, action_id, token, phase in rows:
            if phase not in _PHASES:
                raise ValueError('simulation_history_corrupt')
            if phase in _UNRESOLVED and token != excluding_token:
                blocked.append(dict(runId=run_id, actionId=action_id, phase=phase, retryAllowed=False))
        return blocked

    @staticmethod
    def _state(c, owner, run_id, state, reason=None):
        c.execute('UPDATE simulation_runs SET state=?,reason=? WHERE owner=? AND id=?',
                  (state, reason, owner, run_id))

    @staticmethod
    def _assert_snapshot(owner, row, current):
        current = _snapshot(current)
        if current['owner'] != owner or current['cycleId'] != row['cycle']:
            raise ValueError('simulation_owner_or_cycle_mismatch')
        if current['snapshotFingerprint'] != row['snapshot']['snapshotFingerprint']:
            raise ValueError('stale_simulation_snapshot')
        if current['ownerUnresolved']:
            raise ValueError('owner_capture_barrier')
        return current

    def create(self, owner, run_id, snapshot, *, max_actions, max_rounds):
        _owner(owner)
        _id(run_id)
        snapshot = _snapshot(snapshot)
        _limit(max_actions, 'actions')
        _limit(max_rounds, 'rounds')
        if snapshot['owner'] != owner:
            raise ValueError('simulation_owner_or_cycle_mismatch')
        digest = _digest([snapshot, max_actions, max_rounds])
        with self._transaction() as c:
            old = c.execute('SELECT initial_digest FROM simulation_runs WHERE owner=? AND id=?',
                            (owner, run_id)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('simulation_run_id_conflict')
                self._run(c, owner, run_id)
            else:
                if snapshot['ownerUnresolved'] or self._barrier(c, owner):
                    raise ValueError('owner_capture_barrier')
                c.execute('INSERT INTO simulation_runs VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (owner, run_id, snapshot['cycleId'], digest, json.dumps(snapshot),
                           max_actions, max_rounds, 0, 'ready', None))
        return self.status(owner, run_id)

    def reserve(self, owner, run_id, current_snapshot, *, lease_seconds=30):
        """Atomically charge one action and reserve the account. No dispatch."""
        _limit(lease_seconds, 'lease_seconds', 300)
        token = None
        action = None
        with self._transaction() as c:
            row = self._run(c, owner, run_id)
            current = self._assert_snapshot(owner, row, current_snapshot)
            if row['state'] not in ('ready', 'waiting_for_plan'):
                raise ValueError('simulation_run_not_reservable')
            if self._barrier(c, owner):
                raise ValueError('owner_capture_barrier')
            if row['used_actions'] >= row['max_actions']:
                self._state(c, owner, run_id, 'completed', 'action_limit')
            else:
                seen = {r[0] for r in c.execute('SELECT action_id FROM simulation_attempts WHERE owner=? AND cycle=?',
                                               (owner, row['cycle']))}
                pending = [a for a in current['actions'] if a['actionId'] not in seen]
                eligible = [a for a in pending if a['proposedRound'] <= row['max_rounds']]
                if not eligible:
                    self._state(c, owner, run_id, 'completed' if pending else 'waiting_for_plan',
                                'round_limit' if pending else 'observed_frontier_exhausted')
                else:
                    action = eligible[0]
                    token = uuid.uuid4().hex
                    c.execute('INSERT INTO simulation_attempts VALUES (?,?,?,?,?,?,?,?,?)',
                              (owner, run_id, row['cycle'], action['actionId'], action['proposedRound'],
                               token, 'reserved', time.time() + lease_seconds, current['snapshotFingerprint']))
                    c.execute("UPDATE simulation_runs SET used_actions=used_actions+1,state='reserved',reason=NULL WHERE owner=? AND id=?",
                              (owner, run_id))
        return {**_FLAGS, 'runId': run_id, 'reserved': token is not None,
                'reservationToken': token, 'action': action}

    def begin_simulated_dispatch(self, owner, run_id, token, current_snapshot):
        """Record unknown dispatch intent durably. Still does not execute anything."""
        token = _id(token)
        error = None
        with self._transaction() as c:
            row = self._run(c, owner, run_id)
            self._assert_snapshot(owner, row, current_snapshot)
            attempt = c.execute('SELECT phase,expires,snapshot_digest FROM simulation_attempts WHERE owner=? AND run_id=? AND token=?',
                                (owner, run_id, token)).fetchone()
            if not attempt or attempt[0] != 'reserved' or row['state'] != 'reserved':
                raise ValueError('simulation_reservation_not_dispatchable')
            if self._barrier(c, owner, excluding_token=token):
                raise ValueError('owner_capture_barrier')
            if attempt[2] != row['snapshot']['snapshotFingerprint']:
                raise ValueError('stale_simulation_snapshot')
            if time.time() >= attempt[1]:
                c.execute("UPDATE simulation_attempts SET phase='expired_before_dispatch' WHERE owner=? AND token=?", (owner, token))
                self._state(c, owner, run_id, 'stopped', 'lease_expired_before_dispatch')
                error = 'simulation_lease_expired'
            else:
                c.execute("UPDATE simulation_attempts SET phase='dispatch_unknown' WHERE owner=? AND token=?", (owner, token))
                self._state(c, owner, run_id, 'dispatch_unknown', 'simulated_dispatch_outcome_pending')
        if error:
            raise ValueError(error)
        return {**_FLAGS, 'runId': run_id, 'status': 'simulation_dispatch_unknown', 'retryAllowed': False}

    def record_simulated_outcome(self, owner, run_id, token, current_snapshot, outcome):
        """Record one fixed synthetic outcome; repeated/late/unknown results cannot replay."""
        token = _id(token)
        if not isinstance(outcome, str) or outcome not in _OUTCOMES:
            raise ValueError('invalid_simulated_outcome')
        with self._transaction() as c:
            row = self._run(c, owner, run_id)
            attempt = c.execute('SELECT phase,expires,snapshot_digest FROM simulation_attempts WHERE owner=? AND run_id=? AND token=?',
                                (owner, run_id, token)).fetchone()
            if not attempt or attempt[0] != 'dispatch_unknown':
                raise ValueError('simulation_outcome_not_recordable')
            reason = None
            try:
                self._assert_snapshot(owner, row, current_snapshot)
                if attempt[2] != row['snapshot']['snapshotFingerprint']:
                    raise ValueError('stale_simulation_snapshot')
                if self._barrier(c, owner, excluding_token=token):
                    raise ValueError('owner_capture_barrier')
                if time.time() >= attempt[1]:
                    raise ValueError('simulation_lease_expired_after_dispatch')
            except ValueError:
                outcome, reason = 'unknown', 'post_dispatch_guard_failed'
            c.execute('UPDATE simulation_attempts SET phase=? WHERE owner=? AND token=?', (outcome, owner, token))
            if outcome == 'unknown':
                state, reason = 'unknown', reason or 'simulated_outcome_unknown'
            elif row['state'] in ('cancelled', 'stopped'):
                state, reason = row['state'], row['reason']
            elif outcome != 'simulated_observed':
                state, reason = 'blocked', outcome
            elif row['used_actions'] >= row['max_actions']:
                state, reason = 'completed', 'action_limit'
            else:
                state = 'ready'
            self._state(c, owner, run_id, state, reason)
        return self.status(owner, run_id)

    def refresh_simulation(self, owner, run_id, previous_snapshot, next_snapshot):
        """Supply a new FIXTURE frontier without resetting cumulative limits.

        Requires increased graph revision and unchanged account/config/ownership.
        Plan refresh is never a way to clear a pending or unknown dispatch.
        """
        next_snapshot = _snapshot(next_snapshot)
        with self._transaction() as c:
            row = self._run(c, owner, run_id)
            previous = self._assert_snapshot(owner, row, previous_snapshot)
            if row['state'] not in ('ready', 'waiting_for_plan') or self._barrier(c, owner):
                raise ValueError('simulation_run_not_refreshable')
            if next_snapshot['ownerUnresolved']:
                raise ValueError('owner_capture_barrier')
            for key in ('owner', 'cycleId', 'configFingerprint', 'ownershipFingerprint'):
                if previous[key] != next_snapshot[key]:
                    raise ValueError('simulation_scope_changed')
            if (next_snapshot['revision'] <= previous['revision']
                    or next_snapshot['graphFingerprint'] == previous['graphFingerprint']):
                raise ValueError('fresh_simulation_graph_required')
            c.execute("UPDATE simulation_runs SET snapshot=?,state='ready',reason=NULL WHERE owner=? AND id=?",
                      (json.dumps(next_snapshot), owner, run_id))
        return self.status(owner, run_id)

    def stop(self, owner, run_id, *, cancel=False):
        """Cancel known-undispatched reservations. Never erase dispatched uncertainty."""
        if type(cancel) is not bool:
            raise ValueError('invalid_cancel')
        with self._transaction() as c:
            row = self._run(c, owner, run_id)
            if row['state'] not in _FINAL:
                c.execute("UPDATE simulation_attempts SET phase='cancelled_before_dispatch' WHERE owner=? AND run_id=? AND phase='reserved'",
                          (owner, run_id))
                self._state(c, owner, run_id, 'cancelled' if cancel else 'stopped',
                            'cancel_requested' if cancel else 'stop_requested')
        return self.status(owner, run_id)

    def status(self, owner, run_id):
        """Read-only, owner-scoped status. Expired leases NEVER auto-reclaim."""
        c = sqlite3.connect(self.db.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
        try:
            c.execute('BEGIN')
            self._check_schema(c)
            row = self._run(c, owner, run_id)
            blockers = self._barrier(c, owner)
            attempts = [dict(zip(('actionId', 'proposedRound', 'phase', 'leaseExpires'), r))
                        for r in c.execute('SELECT action_id,round,phase,expires FROM simulation_attempts WHERE owner=? AND run_id=? ORDER BY rowid',
                                           (owner, run_id))]
            for attempt in attempts:
                expires = attempt['leaseExpires']
                if not isinstance(expires, (int, float)) or not math.isfinite(expires):
                    raise ValueError('simulation_history_corrupt')
                attempt.update(leaseExpired=time.time() >= expires, retryAllowed=False,
                               simulationOnly=True)
            return {**_FLAGS, 'readOnly': True, 'owner': owner, 'runId': run_id,
                    'cycleId': row['cycle'], 'status': 'simulation_' + row['state'],
                    'reason': row['reason'], 'limits': {'maxActions': row['max_actions'], 'maxRounds': row['max_rounds']},
                    'roundLimitMeaning': 'absolute_proposed_round_number',
                    'usedActions': row['used_actions'], 'remainingActions': row['max_actions'] - row['used_actions'],
                    'highestReservedRound': max((a['proposedRound'] for a in attempts), default=0),
                    'snapshotFingerprint': row['snapshot']['snapshotFingerprint'],
                    'attempts': attempts, 'ownerBlockers': blockers,
                    'automaticRetryAllowed': False, 'liveExecutionEvidence': False}
        finally:
            c.close()
