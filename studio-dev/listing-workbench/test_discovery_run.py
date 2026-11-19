"""Offline-only tests. Every database is isolated in OS temporary storage."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import discovery_run as run


def fp(label):
    return hashlib.sha256(label.encode()).hexdigest()


def snapshot(owner=1, cycle='fixture', revision=1, rounds=(1, 2, 3), **changes):
    fields = dict(graph_fingerprint=fp('graph-' + str(revision)),
                  history_fingerprint=fp('history-' + str(revision)),
                  config_fingerprint=fp('config'), ownership_fingerprint=fp('owned-space'))
    fields.update(changes)
    actions = [dict(actionId='a' + str(index), sourceEventId='source' + str(index),
                    kind='search_capture', proposedRound=number)
               for index, number in enumerate(rounds)]
    return run.simulation_snapshot(owner, cycle, revision, actions, **fields)


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='discovery-run-test-')
        self.root = Path(self.temp.name)
        self.sim = run.OfflineSimulation(self.root, simulation_only=True)
        self.snap = snapshot()
        self.no_effects = [patch('subprocess.run', side_effect=AssertionError('No subprocess')),
                           patch('subprocess.Popen', side_effect=AssertionError('No subprocess')),
                           patch('socket.socket', side_effect=AssertionError('No network'))]
        for p in self.no_effects:
            p.start()

    def tearDown(self):
        for p in reversed(self.no_effects):
            p.stop()
        self.temp.cleanup()

    def create(self, owner=1, run_id='r1', snap=None, **limits):
        return self.sim.create(owner, run_id, snap or self.snap,
                               **dict(dict(max_actions=20, max_rounds=20), **limits))

    def reserve(self, snap=None, **fields):
        return self.sim.reserve(1, 'r1', snap or self.snap, **fields)

    def dispatch(self, token=None, snap=None):
        token = token or self.reserve(snap)['reservationToken']
        self.sim.begin_simulated_dispatch(1, 'r1', token, snap or self.snap)
        return token

    def finish(self, token, outcome='simulated_observed', snap=None):
        return self.sim.record_simulated_outcome(1, 'r1', token, snap or self.snap, outcome)

    def sql(self, sql, args=()):
        with closing(sqlite3.connect(self.sim.db)) as c, c:
            c.execute(sql, args)

    def test_explicit_temp_only_and_no_production_data(self):
        with self.assertRaisesRegex(ValueError, 'opt_in'):
            run.OfflineSimulation(self.root)
        for path in (Path(__file__).resolve().parent, Path(tempfile.gettempdir()), self.root / 'missing'):
            with self.assertRaisesRegex(ValueError, 'temporary_sandbox'):
                run.OfflineSimulation(path, simulation_only=True)
        with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': str(self.root)}):
            with self.assertRaisesRegex(ValueError, 'production_data_forbidden'):
                run.OfflineSimulation(self.root, simulation_only=True)

    def test_foreign_database_is_not_adopted(self):
        with tempfile.TemporaryDirectory(prefix='discovery-run-foreign-') as root:
            db = Path(root) / self.sim.db.name
            with closing(sqlite3.connect(db)) as c, c:
                c.execute('CREATE TABLE real_data (x TEXT)')
            before = db.read_bytes()
            with self.assertRaisesRegex(ValueError, 'not_a_simulation_database'):
                run.OfflineSimulation(root, simulation_only=True)
            self.assertEqual(db.read_bytes(), before)

    def test_exact_fixture_schema_and_finite_bounds(self):
        for owner in (True, False, 0, -1, '1', None):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                snapshot(owner=owner)
        for field in ('max_actions', 'max_rounds'):
            for value in (0, 21, True, 1.0, '1', None, float('inf'), float('nan')):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.create(**{field: value})
        for extra in ('url', 'command', 'adapter', 'execute'):
            bad = copy.deepcopy(self.snap)
            bad[extra] = 'anything'
            with self.assertRaisesRegex(ValueError, 'simulation_snapshot_required'):
                self.create(snap=bad)
        bad = copy.deepcopy(self.snap)
        bad['simulationOnly'] = False
        with self.assertRaises(ValueError):
            self.create(snap=bad)
        bad = copy.deepcopy(self.snap)
        bad['actions'][0]['proposedRound'] = 2
        with self.assertRaisesRegex(ValueError, 'fingerprint_mismatch'):
            self.create(snap=bad)
        for rounds in ((True,), (0,), (21,), (1.0,)):
            with self.assertRaises(ValueError):
                snapshot(rounds=rounds)

    def test_durable_cumulative_action_budget_and_idempotent_create(self):
        self.create(max_actions=2)
        first = self.finish(self.dispatch())
        self.assertEqual(first['usedActions'], 1)
        self.sim = run.OfflineSimulation(self.root, simulation_only=True)
        self.assertEqual(self.create(max_actions=2)['usedActions'], 1)
        result = self.finish(self.dispatch())
        self.assertEqual(result['status'], 'simulation_completed')
        self.assertEqual((result['usedActions'], result['remainingActions']), (2, 0))
        self.assertEqual(result['reason'], 'action_limit')
        with self.assertRaisesRegex(ValueError, 'not_reservable'):
            self.reserve()
        with self.assertRaisesRegex(ValueError, 'id_conflict'):
            self.create(max_actions=3)
        self.assertEqual(self.create(max_actions=2)['usedActions'], 2)

    def test_round_limit_is_absolute_and_no_overshoot(self):
        self.snap = snapshot(rounds=(3, 1, 2))
        self.create(max_rounds=2)
        self.assertEqual(self.reserve()['action']['proposedRound'], 1)
        token = self._token_from_db()
        self.finish(self.dispatch(token))
        self.finish(self.dispatch())
        self.assertFalse(self.reserve()['reserved'])
        status = self.sim.status(1, 'r1')
        self.assertEqual(status['reason'], 'round_limit')
        self.assertEqual((status['usedActions'], status['highestReservedRound']), (2, 2))
        with self.assertRaisesRegex(ValueError, 'not_refreshable'):
            self.sim.refresh_simulation(1, 'r1', self.snap, snapshot(revision=2))

    def _token_from_db(self):
        with closing(sqlite3.connect(self.sim.db)) as c:
            return c.execute("SELECT token FROM simulation_attempts WHERE owner=1 AND phase='reserved'").fetchone()[0]

    def test_new_fixture_round_cannot_reset_lifetime_budget(self):
        self.snap = snapshot(rounds=(1,))
        self.create(max_actions=2, max_rounds=2)
        self.finish(self.dispatch())
        self.assertFalse(self.reserve()['reserved'])
        self.assertEqual(self.sim.status(1, 'r1')['status'], 'simulation_waiting_for_plan')
        next_snap = snapshot(revision=2, rounds=(1, 2))
        self.sim.refresh_simulation(1, 'r1', self.snap, next_snap)
        with self.assertRaisesRegex(ValueError, 'stale_simulation_snapshot'):
            self.reserve()
        self.snap = next_snap
        result = self.finish(self.dispatch())
        self.assertEqual(result['reason'], 'action_limit')
        self.assertEqual(result['usedActions'], 2)

    def test_two_workers_one_atomic_reservation(self):
        self.create()
        start = threading.Barrier(8)

        def worker(_):
            controller = run.OfflineSimulation(self.root, simulation_only=True)
            start.wait(timeout=10)
            try:
                return controller.reserve(1, 'r1', self.snap)['reserved']
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(worker, range(8))), 1)
        self.assertEqual(self.sim.status(1, 'r1')['usedActions'], 1)

    def test_account_barrier_spans_runs_cycles_and_other_owner_isolated(self):
        self.create()
        other_cycle = snapshot(cycle='other')
        self.create(run_id='r2', snap=other_cycle)
        token = self.dispatch()
        self.finish(token, 'unknown')
        with self.assertRaisesRegex(ValueError, 'owner_capture_barrier'):
            self.sim.reserve(1, 'r2', other_cycle)
        with self.assertRaisesRegex(ValueError, 'owner_capture_barrier'):
            self.create(run_id='new', snap=snapshot(cycle='new'))
        second = snapshot(owner=2)
        self.create(owner=2, snap=second)
        self.assertTrue(self.sim.reserve(2, 'r1', second)['reserved'])
        with self.assertRaisesRegex(ValueError, 'not_found'):
            self.sim.status(3, 'r1')
        with self.assertRaisesRegex(ValueError, 'not_found'):
            self.sim.stop(3, 'r1')

    def test_reserved_crash_and_expired_lease_never_auto_reclaim(self):
        self.create()
        with patch.object(run.time, 'time', return_value=100):
            token = self.reserve(lease_seconds=1)['reservationToken']
        self.sim = run.OfflineSimulation(self.root, simulation_only=True)
        status = self.sim.status(1, 'r1')
        self.assertTrue(status['attempts'][0]['leaseExpired'])
        self.assertEqual(status['ownerBlockers'][0]['phase'], 'reserved')
        with self.assertRaisesRegex(ValueError, 'not_reservable'):
            self.reserve()
        with self.assertRaisesRegex(ValueError, 'lease_expired'):
            self.dispatch(token)
        status = self.sim.status(1, 'r1')
        self.assertEqual(status['attempts'][0]['phase'], 'expired_before_dispatch')
        self.assertEqual(status['usedActions'], 1)
        self.assertEqual(status['ownerBlockers'], [])

    def test_dispatch_crash_persists_unknown_and_cannot_replay(self):
        self.create()
        token = self.dispatch()
        self.sim = run.OfflineSimulation(self.root, simulation_only=True)
        self.assertEqual(self.sim.status(1, 'r1')['status'], 'simulation_dispatch_unknown')
        with self.assertRaisesRegex(ValueError, 'not_dispatchable'):
            self.dispatch(token)
        with self.assertRaisesRegex(ValueError, 'not_reservable'):
            self.reserve()
        result = self.finish(token, 'unknown')
        self.assertEqual(result['status'], 'simulation_unknown')
        with self.assertRaisesRegex(ValueError, 'not_recordable'):
            self.finish(token)
        self.assertTrue(self.sim.stop(1, 'r1', cancel=True)['ownerBlockers'])
        with self.assertRaisesRegex(ValueError, 'not_refreshable'):
            self.sim.refresh_simulation(1, 'r1', self.snap, snapshot(revision=2))

    def test_cancel_before_dispatch_does_not_refund_or_replay(self):
        self.create()
        token = self.reserve()['reservationToken']
        result = self.sim.stop(1, 'r1', cancel=True)
        self.assertEqual(result['status'], 'simulation_cancelled')
        self.assertEqual(result['attempts'][0]['phase'], 'cancelled_before_dispatch')
        self.assertEqual(result['usedActions'], 1)
        with self.assertRaisesRegex(ValueError, 'not_dispatchable'):
            self.dispatch(token)
        # A new run cannot reissue even a known-undispatched spent action.
        self.create(run_id='r2')
        self.assertEqual(self.sim.reserve(1, 'r2', self.snap)['action']['actionId'], 'a1')

    def test_cancel_after_dispatch_preserves_barrier_and_accepts_only_its_late_receipt(self):
        self.create()
        token = self.dispatch()
        result = self.sim.stop(1, 'r1', cancel=True)
        self.assertEqual(result['status'], 'simulation_cancelled')
        self.assertEqual(result['ownerBlockers'][0]['phase'], 'dispatch_unknown')
        result = self.finish(token)
        self.assertEqual(result['status'], 'simulation_cancelled')
        self.assertEqual(result['ownerBlockers'], [])
        with self.assertRaisesRegex(ValueError, 'not_reservable'):
            self.reserve()

    def test_cancel_and_dispatch_race_never_loses_unknown_state(self):
        self.create()
        token = self.reserve()['reservationToken']
        start = threading.Barrier(2)

        def dispatch():
            start.wait(timeout=10)
            try:
                self.dispatch(token)
                return True
            except ValueError:
                return False

        def cancel():
            start.wait(timeout=10)
            return self.sim.stop(1, 'r1', cancel=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            dispatched = pool.submit(dispatch)
            stopped = pool.submit(cancel)
            did_dispatch = dispatched.result(timeout=10)
            stopped.result(timeout=10)
        result = self.sim.status(1, 'r1')
        self.assertEqual(result['status'], 'simulation_cancelled')
        self.assertEqual(bool(result['ownerBlockers']), did_dispatch)
        self.assertEqual(result['usedActions'], 1)

    def test_stale_graph_config_history_ownership_and_revision_block_each_phase(self):
        self.create()
        variants = [snapshot(revision=2), snapshot(config_fingerprint=fp('changed')),
                    snapshot(history_fingerprint=fp('changed')),
                    snapshot(ownership_fingerprint=fp('changed')),
                    snapshot(graph_fingerprint=fp('changed'))]
        for changed in variants:
            with self.subTest(changed=changed['snapshotFingerprint']), self.assertRaisesRegex(ValueError, 'stale_simulation_snapshot'):
                self.reserve(snap=changed)
        self.assertEqual(self.sim.status(1, 'r1')['usedActions'], 0)
        token = self.reserve()['reservationToken']
        for changed in variants:
            with self.assertRaisesRegex(ValueError, 'stale_simulation_snapshot'):
                self.dispatch(token, changed)
        self.dispatch(token)
        result = self.finish(token, snap=variants[0])
        self.assertEqual(result['status'], 'simulation_unknown')
        self.assertTrue(result['ownerBlockers'])

    def test_refresh_rejects_changed_scope_nonadvancing_revision_and_pending_work(self):
        self.create()
        invalid = [self.snap, snapshot(revision=0), snapshot(owner=2, revision=2),
                   snapshot(cycle='elsewhere', revision=2),
                   snapshot(revision=2, config_fingerprint=fp('changed')),
                   snapshot(revision=2, ownership_fingerprint=fp('changed')),
                   snapshot(revision=2, graph_fingerprint=self.snap['graphFingerprint']),
                   snapshot(revision=2, owner_unresolved=True)]
        for changed in invalid:
            with self.assertRaises(ValueError):
                self.sim.refresh_simulation(1, 'r1', self.snap, changed)
        self.reserve()
        with self.assertRaisesRegex(ValueError, 'not_refreshable'):
            self.sim.refresh_simulation(1, 'r1', self.snap, snapshot(revision=2))

    def test_expired_post_dispatch_result_remains_unknown(self):
        self.create()
        with patch.object(run.time, 'time', return_value=100):
            token = self.reserve(lease_seconds=1)['reservationToken']
            self.dispatch(token)
        result = self.finish(token)
        self.assertEqual(result['status'], 'simulation_unknown')
        self.assertEqual(result['reason'], 'post_dispatch_guard_failed')
        self.assertTrue(result['ownerBlockers'])

    def test_failed_reservation_transaction_rolls_back_both_budget_and_attempt(self):
        self.create()
        self.sql("CREATE TRIGGER fail_budget BEFORE UPDATE ON simulation_runs BEGIN SELECT RAISE(ABORT,'fixture disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.reserve()
        status = self.sim.status(1, 'r1')
        self.assertEqual(status['usedActions'], 0)
        self.assertEqual(status['attempts'], [])

    def test_failed_outcome_commit_preserves_dispatch_barrier(self):
        self.create()
        token = self.dispatch()
        self.sql("CREATE TRIGGER fail_outcome BEFORE UPDATE ON simulation_runs BEGIN SELECT RAISE(ABORT,'fixture disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.finish(token)
        result = self.sim.status(1, 'r1')
        self.assertEqual(result['status'], 'simulation_dispatch_unknown')
        self.assertTrue(result['ownerBlockers'])
        with self.assertRaisesRegex(ValueError, 'not_dispatchable'):
            self.dispatch(token)

    def test_corrupt_history_or_budget_fails_closed(self):
        self.create()
        self.reserve()
        self.sql("UPDATE simulation_attempts SET phase='future_unrecognized'")
        with self.assertRaisesRegex(ValueError, 'history_corrupt'):
            self.sim.status(1, 'r1')
        self.sql("UPDATE simulation_attempts SET phase='reserved'")
        self.sql('UPDATE simulation_runs SET used_actions=0')
        with self.assertRaisesRegex(ValueError, 'budget_corrupt'):
            self.sim.status(1, 'r1')

    def test_data_only_outcomes_no_callback_and_safety_flags(self):
        self.create()
        token = self.dispatch()
        for outcome in (lambda: self.fail('Must never execute callback'), 'captured', {}, None):
            with self.assertRaisesRegex(ValueError, 'invalid_simulated_outcome'):
                self.finish(token, outcome)
        result = self.finish(token, 'simulated_blocked')
        self.assertEqual(result['status'], 'simulation_blocked')
        self.assertTrue(result['simulationOnly'])
        for flag in ('executionAllowed', 'automaticNavigationImplemented', 'qualificationEvaluated', 'liveExecutionEvidence', 'automaticRetryAllowed'):
            self.assertFalse(result[flag])
        for key in ('qualifiedCount', 'importedCount', 'externalCallsPerformed'):
            self.assertEqual(result[key], 0)

    def test_status_readonly_no_secrets_no_lease_reclamation(self):
        self.create()
        token = self.reserve()['reservationToken']
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        status = self.sim.status(1, 'r1')
        after = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertNotIn(token, json.dumps(status))
        self.assertTrue(status['readOnly'])


# app_paths has an import-time initializer: it MUST never point at production.
_IMPORT_ROOT = tempfile.TemporaryDirectory(prefix='discovery-run-import-')
with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': _IMPORT_ROOT.name}):
    import discovery_plan as plan


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='discovery-run-inspect-')
        self.root = Path(self.temp.name)
        self.patches = [patch.object(plan.ledger, 'DB', self.root / 'graph.sqlite3'),
                        patch.object(plan.browser, 'DB', self.root / 'captures.sqlite3'),
                        patch.object(plan.browser, '_binding', return_value=({}, fp('configured'))),
                        patch.object(plan.browser, 'capture', side_effect=AssertionError('No capture')),
                        patch.object(plan.browser, 'capture_search', side_effect=AssertionError('No capture')),
                        patch.object(plan.browser, 'capture_store', side_effect=AssertionError('No capture')),
                        patch('subprocess.run', side_effect=AssertionError('No subprocess'))]
        for p in self.patches:
            p.start()
        self.event = dict(id='k1', kind='keyword', parentId=None, marketplace='US',
                          observedAt='2026-01-01T00:00:00Z', sourceType='browser_visible',
                          asin='B000000001', sourceTitle='Cotton Shirt Women', phrase='Cotton Shirt',
                          url='https://amazon.com/dp/B000000001')
        plan.ledger.ingest(1, dict(cycleId='fixture', expectedRevision=0, events=[self.event]))
        self.request = dict(cycleId='fixture', expectedRevision=1, maxActions=2, maxRounds=2)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_inspect_never_enables_execution_or_writes(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(plan.ledger, 'ingest', side_effect=AssertionError('No ingest')):
            result = run.inspect(1, self.request)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertEqual(result['status'], 'execution_disabled')
        self.assertFalse(result['executionAllowed'])
        self.assertFalse(result['binding']['liveOwnershipVerified'])
        self.assertEqual(result['binding']['status'], 'configured')
        self.assertEqual(result['plannedActionCount'], 1)
        self.assertEqual(result['offlineControlMode'], 'simulation_only')

    def test_binding_unavailable_and_changed_fail_closed_without_paths(self):
        with patch.object(plan.browser, '_binding', side_effect=ValueError('C:/secret-install-path')):
            result = run.inspect(1, self.request)
        self.assertEqual(result['binding']['status'], 'blocked')
        self.assertNotIn('secret-install-path', json.dumps(result))
        with patch.object(plan.browser, '_binding', side_effect=[({}, fp('one')), ({}, fp('two'))]):
            with self.assertRaisesRegex(ValueError, 'stale_configuration'):
                run.inspect(1, self.request)

    def test_history_unknown_blocks_everything_and_scope_is_checked(self):
        receipt = dict(captureId='old', cycleId='other', parentId='k1', status='execution_unknown', captureKind='search')
        with closing(sqlite3.connect(plan.browser.DB)) as c, c:
            c.execute('CREATE TABLE attempts (owner INTEGER, id TEXT, status TEXT, receipt TEXT)')
            c.execute('INSERT INTO attempts VALUES (?,?,?,?)', (1, 'old', 'execution_unknown', json.dumps(receipt)))
        result = run.inspect(1, self.request)
        self.assertEqual(result['plannedActionCount'], 0)
        self.assertIn('prior_capture_unresolved', [b['reason'] for b in result['blockers']])
        with self.assertRaisesRegex(ValueError, 'not found'):
            run.inspect(2, self.request)
        with self.assertRaisesRegex(ValueError, 'stale_revision'):
            run.inspect(1, {**self.request, 'expectedRevision': 0})


if __name__ == '__main__':
    unittest.main()
