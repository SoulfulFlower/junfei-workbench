"""Independent acceptance probes. Only fixed synthetic Python workers and TEMP data.

These tests exercise the actual offline wrapper, controller, capture bridge and
coordinator. EGO, Node, browser navigation and network behavior are NOT tested.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import discovery_live_coordinated as fixture

shared = fixture.shared
SOURCE = Path(__file__).resolve().parent


class CoordinatedAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='coordinated-acceptance-')
        self.base = Path(self.temp.name)
        self.root = self.base / 'coordinator'
        self.enrollment = shared.provision(self.root)
        self.kwargs = dict(coordinator_root=str(self.root),
            expected_identity=self.enrollment, namespace='acceptance-a',
            account_id=1, space_id=17001, run_id='acceptance-run')
        self.environment = patch.dict(os.environ, {'JUNFEI_WORKER_USER': '0'})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def record(self):
        return shared.Coordinator(self.enrollment, root=self.root).inspect(
            owner='fixture:acceptance-a:1', operation_id='acceptance-run')

    def child(self, code, *, timeout=45):
        env = dict(os.environ, JUNFEI_ACCOUNT_DATA=str(self.base / 'other-data'),
                   JUNFEI_PROJECT_ROOT=str(self.base / 'other-install'),
                   JUNFEI_WORKER_USER='0', PYTHONDONTWRITEBYTECODE='1')
        program = ('import sys; sys.path.insert(0, ' + repr(str(SOURCE)) + ');\n' + code)
        return subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', '-c', program],
            cwd=self.base, env=env, capture_output=True, text=True,
            encoding='utf-8', timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def other_process_blocked(self):
        kwargs = dict(self.kwargs, namespace='acceptance-b', account_id=2,
                      run_id='different-operation')
        code = ('import json; import discovery_live_coordinated as f\n'
                'try:\n f.run_fixture(**' + repr(kwargs) + ')\n'
                'except Exception as e:\n print(json.dumps({"error":str(e)}))\n'
                'else:\n raise AssertionError("conflicting child ran")\n')
        result = self.child(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'error': 'space_requires_review'})

    def assert_no_replay_or_new_id_escape(self, *, scenario='complete'):
        self.assertEqual(self.record().status, 'dispatch_unknown')
        with patch.object(fixture, '_invoke_worker', side_effect=AssertionError('replay')):
            result = fixture.run_fixture(**self.kwargs, scenario=scenario)
            self.assertTrue(result.replayed)
            self.assertIsNone(result.workspace)
            self.assertIsNone(result.summary)
            self.assertEqual(result.record.status, 'dispatch_unknown')
            with self.assertRaisesRegex(shared.CoordinationError, 'requires_review'):
                fixture.run_fixture(**dict(self.kwargs, run_id='new-id'))
        self.other_process_blocked()

    def test_complete_and_duplicate_do_not_create_another_worker(self):
        result = fixture.run_fixture(**self.kwargs)
        self.assertEqual(result.record.status, 'completed')
        self.assertTrue(result.summary['synthetic'])
        self.assertFalse(result.summary['legacyEntryProtected'])
        self.assertFalse(result.summary['productionExecutionAllowed'])
        self.assertEqual(result.summary['realBrowserCalls'], 0)
        self.assertEqual(result.summary['syntheticBrowserCaptures'], 4)
        self.assertEqual(result.summary['observedStages'], {
            'search_capture': 2, 'seller_capture': 1,
            'store_capture': 1, 'title_phrase_capture': 1})
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(fixture, '_invoke_worker', side_effect=AssertionError('replay')):
            again = fixture.run_fixture(**self.kwargs)
        self.assertEqual(again.record, result.record)
        self.assertTrue(again.replayed)
        self.assertIsNone(again.workspace)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_other_process_cannot_enter_during_terminal_verification(self):
        original = fixture._verify_terminal
        calls = []
        def verify(value, identity):
            self.assertEqual(self.record().status, 'dispatch_unknown')
            self.other_process_blocked()
            calls.append(value.workspace)
            return original(value, identity)
        with patch.object(fixture, '_verify_terminal', side_effect=verify):
            result = fixture.run_fixture(**self.kwargs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.record.status, 'completed')

    def test_other_process_cannot_enter_before_or_after_adapter_persistence(self):
        original = fixture._persist_terminal
        calls = []
        def persist(workspace, terminal):
            self.other_process_blocked()
            original(workspace, terminal)
            self.assertEqual(self.record().status, 'dispatch_unknown')
            self.other_process_blocked()
            calls.append(workspace)
        with patch.object(fixture, '_persist_terminal', side_effect=persist):
            result = fixture.run_fixture(**self.kwargs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.record.status, 'completed')

    def test_cross_process_conflict_between_actual_controller_steps(self):
        original = fixture._invoke_worker
        spaces = []
        def invoke(workspace, job):
            spaces.append(workspace)
            return original(workspace, job)
        with patch.object(fixture, '_invoke_worker', side_effect=invoke):
            with ThreadPoolExecutor(max_workers=1) as pool:
                running = pool.submit(fixture.run_fixture, **self.kwargs,
                                      scenario='pause_between_steps')
                deadline = time.monotonic() + 15
                try:
                    while not spaces or not (spaces[0] / 'between_steps.ready').is_file():
                        if running.done():
                            running.result()
                            self.fail('worker never paused')
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.02)
                    snapshot = fixture._snapshot(spaces[0])
                    self.assertEqual(len(snapshot['steps']), 1)
                    self.assertEqual(snapshot['steps'][0][5], 'observed')
                    self.assertEqual(snapshot['runs'][0][3], 'active')
                    duplicate = fixture.run_fixture(**self.kwargs,
                                                    scenario='pause_between_steps')
                    self.assertTrue(duplicate.replayed)
                    self.assertIsNone(duplicate.workspace)
                    self.assertEqual(duplicate.record.status, 'dispatch_unknown')
                    self.assertEqual(len(spaces), 1)
                    self.other_process_blocked()
                finally:
                    if spaces:
                        (spaces[0] / 'between_steps.release').write_text('release', encoding='ascii')
                result = running.result(timeout=30)
        self.assertEqual(result.record.status, 'completed')

    def test_worker_death_after_first_observation_is_unknown_without_replay(self):
        with self.assertRaises(fixture.FixtureError):
            fixture.run_fixture(**self.kwargs, scenario='crash_after_first')
        self.assert_no_replay_or_new_id_escape(scenario='crash_after_first')

    def test_worker_terminal_proof_cannot_release_while_child_is_alive(self):
        original = fixture._invoke_worker
        spaces = []
        def invoke(workspace, job):
            spaces.append(workspace)
            return original(workspace, job)
        with patch.object(fixture, '_invoke_worker', side_effect=invoke):
            with ThreadPoolExecutor(max_workers=1) as pool:
                running = pool.submit(fixture.run_fixture, **self.kwargs,
                                      scenario='pause_after_terminal')
                deadline = time.monotonic() + 15
                try:
                    while not spaces or not (spaces[0] / 'after_terminal.ready').is_file():
                        if running.done():
                            running.result()
                            self.fail('worker never paused after terminal proof')
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.02)
                    evidence = fixture._read_evidence(spaces[0])
                    self.assertIn('worker_terminal', evidence)
                    self.assertNotIn('parent_verified', evidence)
                    self.assertEqual(evidence['worker_terminal']['status']['status'], 'stopped')
                    self.assertEqual(fixture._snapshot(spaces[0])['runs'][0][3], 'stopped')
                    self.assertFalse(running.done())
                    self.assertEqual(self.record().status, 'dispatch_unknown')
                    replay = fixture.run_fixture(**self.kwargs,
                                                 scenario='pause_after_terminal')
                    self.assertTrue(replay.replayed)
                    self.assertIsNone(replay.workspace)
                    self.assertIsNone(replay.summary)
                    self.assertEqual(replay.record.status, 'dispatch_unknown')
                    self.assertEqual(len(spaces), 1)
                    self.other_process_blocked()
                finally:
                    if spaces:
                        (spaces[0] / 'after_terminal.release').write_text('release', encoding='ascii')
                result = running.result(timeout=30)
        self.assertEqual(result.record.status, 'completed')

    def test_parent_death_during_verification_is_unknown_without_replay(self):
        code = ('import os; import discovery_live_coordinated as f\n'
                'f._verify_terminal = lambda value, identity: os._exit(47)\n'
                'f.run_fixture(**' + repr(self.kwargs) + ')\n')
        result = self.child(code)
        self.assertEqual(result.returncode, 47, result.stderr)
        self.assert_no_replay_or_new_id_escape()

    def test_durable_terminal_acknowledgement_lost_retains_unknown(self):
        original = fixture._persist_terminal
        evidence = []
        def persist(workspace, terminal):
            original(workspace, terminal)
            evidence.append(fixture._read_evidence(workspace))
            raise OSError('synthetic lost persistence acknowledgement')
        with patch.object(fixture, '_persist_terminal', side_effect=persist):
            with self.assertRaises(OSError):
                fixture.run_fixture(**self.kwargs)
        self.assertIn('parent_verified', evidence[0])
        self.assert_no_replay_or_new_id_escape()

    def test_stop_is_not_terminal_proof_or_release(self):
        with self.assertRaises(fixture.FixtureError):
            fixture.run_fixture(**self.kwargs, scenario='stop_during_dispatch')
        self.assert_no_replay_or_new_id_escape(scenario='stop_during_dispatch')

    def test_bool_terminal_identity_fence_does_not_alias_integer(self):
        original = fixture._verify_terminal
        def verify(value, identity):
            proof = original(value, identity)
            self.assertEqual(identity.fence, 1)
            return replace(proof, identity=replace(identity, fence=True))
        with patch.object(fixture, '_verify_terminal', side_effect=verify):
            with self.assertRaisesRegex(shared.CoordinationError, 'terminal_evidence'):
                fixture.run_fixture(**self.kwargs)
        self.assert_no_replay_or_new_id_escape()

    def test_strict_worker_proof_type_rejects_boolean_version(self):
        original = fixture._verify_terminal
        def verify(value, identity):
            with sqlite3.connect(value.workspace / 'evidence.sqlite3') as conn:
                row = conn.execute("SELECT payload FROM evidence WHERE stage='worker_terminal'").fetchone()
                proof = json.loads(row[0]); proof['version'] = True
                conn.execute("UPDATE evidence SET payload=? WHERE stage='worker_terminal'",
                             (json.dumps(proof),))
            return original(value, identity)
        with patch.object(fixture, '_verify_terminal', side_effect=verify):
            with self.assertRaisesRegex(fixture.FixtureError, 'schema_invalid'):
                fixture.run_fixture(**self.kwargs)
        self.assert_no_replay_or_new_id_escape()

    def test_duplicate_json_proof_field_is_malformed_not_last_value_wins(self):
        original = fixture._verify_terminal
        def verify(value, identity):
            with sqlite3.connect(value.workspace / 'evidence.sqlite3') as conn:
                row = conn.execute("SELECT payload FROM evidence WHERE stage='worker_terminal'").fetchone()
                proof = json.loads(row[0])
                # The first invalid value must not be silently discarded by a
                # JSON parser that keeps only the last duplicate key.
                raw = '{"version":true,' + json.dumps(proof)[1:]
                conn.execute("UPDATE evidence SET payload=? WHERE stage='worker_terminal'", (raw,))
            return original(value, identity)
        with patch.object(fixture, '_verify_terminal', side_effect=verify):
            with self.assertRaises(fixture.FixtureError):
                fixture.run_fixture(**self.kwargs)
        self.assert_no_replay_or_new_id_escape()

    def test_import_has_no_data_browser_or_process_side_effects(self):
        code = '''
from unittest.mock import patch
with patch('pathlib.Path.mkdir', side_effect=AssertionError('unexpected mkdir')), \
     patch('sqlite3.connect', side_effect=AssertionError('unexpected SQLite')), \
     patch('subprocess.Popen', side_effect=AssertionError('unexpected child')):
    import discovery_live_coordinated
assert 'app_paths' not in sys.modules
assert 'discovery_live' not in sys.modules
assert 'discovery_browser' not in sys.modules
print('clean-import')
'''
        result = self.child(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'clean-import')

    def test_configuration_scope_change_before_terminal_verification_fails_closed(self):
        original = fixture._verify_terminal
        def verify(value, identity):
            path = value.workspace / 'project' / 'automation' / 'config.json'
            config = json.loads(path.read_text(encoding='ascii'))
            config['discovery_browser']['account_bindings']['1']['task_space_id'] += 1
            path.write_text(json.dumps(config), encoding='ascii')
            return original(value, identity)
        with patch.object(fixture, '_verify_terminal', side_effect=verify):
            with self.assertRaises(fixture.FixtureError):
                fixture.run_fixture(**self.kwargs)
        self.assert_no_replay_or_new_id_escape()

    def test_late_stop_marker_before_terminal_verification_fails_closed(self):
        original = fixture._verify_terminal
        def verify(value, identity):
            snapshot = fixture._snapshot(value.workspace)
            stop_path = Path(snapshot['runs'][0][-1]['stopPath'])
            self.assertIn(value.workspace, stop_path.parents)
            stop_path.write_text('stop', encoding='ascii')
            return original(value, identity)
        with patch.object(fixture, '_verify_terminal', side_effect=verify):
            with self.assertRaises(fixture.FixtureError):
                fixture.run_fixture(**self.kwargs)
        self.assert_no_replay_or_new_id_escape()

    def test_old_entry_remains_uncoordinated_launch_intent_only(self):
        code = '''
import json, os, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='old-entry-acceptance-') as base:
    os.environ['JUNFEI_ACCOUNT_DATA'] = str(Path(base) / 'import-data')
    os.environ['JUNFEI_WORKER_USER'] = '0'
    import discovery_live_coordinated as coordinated
    import test_discovery_live as old
    root = Path(base) / 'shared'
    identity = coordinated.shared.provision(root)
    shared = coordinated.shared.Coordinator(identity, root=root)
    shared.reserve(space_id=6, owner='held-account', operation_id='held', request_sha256='a'*64)
    f = old.LiveTests('test_duplicate_start_never_restarts_and_budget_immutable')
    f.setUp()
    try:
        f.begin()
        result = old.live.status(1, 'run1')
        assert result['status'] == 'active'
        assert old.live._launch_worker.call_count == 1
        assert result['coordinationScope'] == 'same_isolated_DATA_database_only_not_machine_global'
        assert shared.inspect(owner='held-account', operation_id='held').status == 'reserved'
        print(json.dumps({'launchIntent':1,'actualWorkers':0,'browserCalls':0}))
    finally:
        f.tearDown()
'''
        result = self.child(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'launchIntent':1,'actualWorkers':0,'browserCalls':0})


if __name__ == '__main__':
    unittest.main()
