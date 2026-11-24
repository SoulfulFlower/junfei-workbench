"""Focused offline-only whole-run integration tests. Never invoke EGO or network."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import discovery_live_coordinated as runner


class CoordinatedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='coordinated-focused-')
        self.root = Path(self.temp.name)
        self.coordinator = self.root / 'coordinator'
        self.identity = runner.shared.provision(self.coordinator)
        self.counter = 0
        self.workspaces = []
        invoke = runner._invoke_worker
        def remember(workspace, job):
            self.workspaces.append(workspace)
            return invoke(workspace, job)
        self.invoke = patch.object(runner, '_invoke_worker', side_effect=remember)
        self.invoke.start()

    def tearDown(self):
        self.invoke.stop()
        # Only roots allocated by this test's exact run invocation, no glob cleanup.
        temp = Path(tempfile.gettempdir()).resolve()
        for path in self.workspaces:
            self.assertEqual(path.parent, temp)
            self.assertTrue(path.name.startswith('discovery-coordinated-fixture-'))
            shutil.rmtree(path)
        self.temp.cleanup()

    def args(self, **changes):
        self.counter += 1
        result = dict(coordinator_root=self.coordinator, expected_identity=self.identity,
            namespace='focused', account_id=1, space_id=11000+self.counter,
            run_id='run-'+str(self.counter))
        result.update(changes)
        return result

    def record(self, args):
        return runner.shared.Coordinator(self.identity, root=self.coordinator).inspect(
            owner='fixture:'+args['namespace']+':'+str(args['account_id']),
            operation_id=args['run_id'])

    def assert_unknown(self, args):
        original = self.record(args)
        self.assertEqual(original.status, 'dispatch_unknown')
        with patch.object(runner, '_invoke_worker', side_effect=AssertionError('No replay child')):
            repeated = runner.run_fixture(**args)
        self.assertTrue(repeated.replayed)
        self.assertIsNone(repeated.workspace)
        self.assertEqual(repeated.record, original)
        with self.assertRaisesRegex(runner.shared.CoordinationError, 'space_requires_review'):
            runner.run_fixture(**{**args, 'account_id':2, 'run_id':'different-run'})

    @staticmethod
    def change_proof(workspace, mutate):
        with closing(sqlite3.connect(workspace/'evidence.sqlite3')) as conn, conn:
            value = json.loads(conn.execute("SELECT payload FROM evidence WHERE stage='worker_terminal'").fetchone()[0])
            mutate(value)
            conn.execute("UPDATE evidence SET payload=? WHERE stage='worker_terminal'", (runner._json(value),))

    def tamper_before_verify(self, args, mutate):
        verify = runner._verify_terminal
        def changed(value, identity):
            mutate(value.workspace)
            return verify(value, identity)
        with patch.object(runner, '_verify_terminal', side_effect=changed):
            with self.assertRaises((runner.FixtureError, ValueError, sqlite3.Error)):
                runner.run_fixture(**args)
        self.assert_unknown(args)

    def test_complete_bound_chain_and_durable_terminal(self):
        result = runner.run_fixture(**self.args())
        self.assertEqual(result.record.status, 'completed')
        self.assertFalse(result.replayed)
        self.assertTrue(result.summary['synthetic'])
        self.assertEqual(result.summary['realBrowserCalls'], 0)
        self.assertEqual(result.summary['syntheticBrowserCaptures'], 4)
        self.assertEqual(sum(result.summary['observedStages'].values()), 5)
        self.assertFalse(result.summary['legacyEntryProtected'])
        evidence = runner._read_evidence(result.workspace)
        self.assertEqual(set(evidence), {'intent','worker_terminal','parent_verified',
                                         'transport_1','transport_2','transport_3','transport_5'})
        terminal = evidence['parent_verified']
        self.assertEqual(result.record.evidence_sha256, runner._digest(terminal))
        self.assertEqual(terminal['identity'], vars(result.record.identity))
        self.assertEqual(terminal['workerProof']['transportCalls'], 4)
        for stage in ('transport_1','transport_2','transport_3','transport_5'):
            self.assertEqual(evidence[stage]['identity'], terminal['identity'])
        self.assertFalse(result.summary['productionExecutionAllowed'])
        self.assertEqual(sum(result.summary[k] for k in ('qualifiedCount','importedCount',
            'paidCallsPerformed','uploadsPerformed','publicationsPerformed')),0)

    def test_completed_replay_has_no_child_and_next_operation_advances_fence(self):
        args = self.args()
        first = runner.run_fixture(**args)
        with patch.object(runner, '_invoke_worker', side_effect=AssertionError('No child')):
            second = runner.run_fixture(**args)
        self.assertEqual(second.record,first.record)
        self.assertTrue(second.replayed)
        self.assertIsNone(second.workspace)
        third = runner.run_fixture(**{**args,'run_id':'later'})
        self.assertEqual(third.record.identity.fence, first.record.identity.fence+1)
        self.assertNotEqual(third.record.identity.dispatch_nonce,first.record.identity.dispatch_nonce)

    def test_input_rejects_aliases_live_space_and_arbitrary_options(self):
        for changes in ({'account_id':True},{'space_id':True},{'space_id':6},
                {'space_id':10001.0},{'scenario':'real'},{'namespace':'../escape'},
                {'run_id':'x/y'},{'callback':'anything'},{'workspace':str(self.root)}):
            with self.subTest(changes=changes), self.assertRaises((runner.FixtureError,TypeError)):
                runner.run_fixture(**self.args(**changes))
        self.assertEqual(self.workspaces,[])

    def test_source_and_non_account_worker_gates(self):
        for guard in (patch.object(runner.sys,'frozen',True,create=True),
                      patch.dict(os.environ,{'JUNFEI_WORKER_USER':'9'})):
            with guard, self.assertRaisesRegex(runner.FixtureError,'source_non_account_worker'):
                runner.run_fixture(**self.args())
        self.assertEqual(self.workspaces,[])

    def test_missing_wrong_or_non_temp_enrollment_cannot_auto_initialize(self):
        missing = self.root/'missing'
        for changes in ({'coordinator_root':missing},{'expected_identity':'0'*32},
                        {'coordinator_root':Path(__file__).resolve().parent}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runner.run_fixture(**self.args(**changes))
        self.assertFalse(missing.exists())
        self.assertEqual(self.workspaces,[])

    def test_bad_terminal_outcomes_and_crash_never_release(self):
        for scenario in ('blocked','unknown','worker_exception','worker_baseexception',
                         'stop_during_dispatch','exit_without_proof','crash_after_first'):
            args = self.args(scenario=scenario)
            with self.subTest(scenario=scenario), self.assertRaises(runner.FixtureError):
                runner.run_fixture(**args)
            self.assert_unknown(args)

    def test_exact_terminal_schema_and_current_identity_required(self):
        mutations = [lambda p:p.update(unexpected=True), lambda p:p.update(version=True),
            lambda p:p.update(joined=1), lambda p:p.update(transportCalls=4.0),
            lambda p:p['identity'].update(fence=True),
            lambda p:p['identity'].update(space_id=True),
            lambda p:p['identity'].update(dispatch_nonce='0'*64),
            lambda p:p['identity'].update(operation_id='old-run'),
            lambda p:p['request'].update(expectedRevision=True)]
        for number, mutate in enumerate(mutations):
            with self.subTest(number=number):
                self.tamper_before_verify(self.args(),lambda w: self.change_proof(w,mutate))

    def test_changed_durable_rows_are_not_trusted_even_with_terminal_status(self):
        def missing_step(workspace):
            with closing(sqlite3.connect(workspace/'data/discovery_browser.sqlite3')) as conn, conn:
                conn.execute('DELETE FROM live_steps WHERE number=2')
        def changed_graph(workspace):
            with closing(sqlite3.connect(workspace/'data/cyclic_discovery.sqlite3')) as conn, conn:
                conn.execute("UPDATE discovery_events SET payload='{}' WHERE id='seed'")
        for mutate in (missing_step,changed_graph):
            self.tamper_before_verify(self.args(),mutate)

    def test_self_consistent_snapshot_hash_does_not_bypass_semantics(self):
        def mutate(workspace):
            with closing(sqlite3.connect(workspace/'data/discovery_browser.sqlite3')) as conn, conn:
                raw = json.loads(conn.execute('SELECT payload FROM live_runs').fetchone()[0])
                raw['reason']='worker_stopped_for_review'
                conn.execute('UPDATE live_runs SET payload=?',(runner._json(raw),))
            self.change_proof(workspace,lambda p:p.update(snapshotHash=runner._digest(runner._snapshot(workspace))))
        self.tamper_before_verify(self.args(),mutate)

    def test_transport_identity_and_artifact_bytes_must_match(self):
        def mutate_row(workspace, field, value):
            with closing(sqlite3.connect(workspace/'evidence.sqlite3')) as conn, conn:
                raw=json.loads(conn.execute("SELECT payload FROM evidence WHERE stage='transport_1'").fetchone()[0])
                raw[field]=value
                conn.execute("UPDATE evidence SET payload=? WHERE stage='transport_1'",(runner._json(raw),))
        def changed_bytes(workspace):
            proof=runner._read_evidence(workspace)['transport_1']
            (workspace/proof['directory']/'result.json').write_text('{}',encoding='ascii')
        for mutate in (lambda w:mutate_row(w,'number',True),
                       lambda w:mutate_row(w,'directory','../../foreign'),changed_bytes):
            self.tamper_before_verify(self.args(),mutate)

    def test_parent_receipt_write_failure_and_lost_ack_retain_barrier(self):
        persist=runner._persist_terminal
        for committed in (False,True):
            args=self.args()
            def fail(workspace,terminal):
                if committed: persist(workspace,terminal)
                raise sqlite3.OperationalError('synthetic lost acknowledgement')
            with patch.object(runner,'_persist_terminal',side_effect=fail), self.assertRaises(sqlite3.Error):
                runner.run_fixture(**args)
            self.assert_unknown(args)

    def test_graph_open_failure_closes_already_open_browser_handle(self):
        browser = Mock()
        with patch.object(runner,'_connect',side_effect=[browser,sqlite3.OperationalError('unavailable')]):
            with self.assertRaises(sqlite3.Error):
                runner._snapshot(self.root)
        browser.close.assert_called_once_with()

    def test_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for raw in ('{"a":1,"a":1}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(runner.FixtureError):runner._loads(raw)


if __name__ == '__main__':
    unittest.main()