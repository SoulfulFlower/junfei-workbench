"""Isolated synthetic control tests. No live browser/network or production data."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

_IMPORT_ROOT = tempfile.TemporaryDirectory(prefix='discovery-live-import-')
with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': _IMPORT_ROOT.name}):
    import discovery_live as live


def chain():
    def event(eid, kind, parent, **fields):
        return dict(id=eid, kind=kind, parentId=parent, marketplace='US',
                    observedAt='2026-01-01T00:00:00Z', sourceType='browser_visible', **fields)
    return [event('k1', 'keyword', None, asin='B000000001', sourceTitle='Cotton Shirt Women',
                  phrase='Cotton Shirt', url='https://amazon.com/dp/B000000001'),
            event('q1', 'search', 'k1', query='Cotton Shirt', url='https://amazon.com/s?k=Cotton+Shirt',
                  products=[{'asin': 'B000000002', 'title': 'Cotton Shirt Blue'}]),
            event('s1', 'seller', 'q1', asin='B000000002', sellerId='SELLER1', sellerName='One',
                  sellerLabel='Sold by One', sellerLinkSource='visible_sold_by_link',
                  sellerLink='https://amazon.com/sp?seller=SELLER1', url='https://amazon.com/dp/B000000002'),
            event('t1', 'store', 's1', sellerId='SELLER1', status='captured',
                  url='https://amazon.com/s?me=SELLER1',
                  products=[{'asin': 'B000000003', 'title': "Women'S  Linen Pants Tall, Loose Summer Fit Blue"}])]


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='discovery-live-test-')
        self.root = Path(self.temp.name)
        self.cli = self.root / 'unused-cli.exe'
        self.cli.write_bytes(b'fixture only never executed')
        self.original = self.root / 'original-config.json'
        self.original.write_text(json.dumps({'browser': {'task_space_id': 4},
            'discovery_browser': {'account_bindings': {'1': {'task_space_id': 5}}}}), encoding='utf-8')
        self.config = {'browser': {'task_space_id': 4}, 'discovery_browser': {
            'engine': 'ego-lite', 'cli': str(self.cli), 'account_bindings': {'1': {
                'enabled': True, 'task_space_id': 6, 'task_space_name': 'Dedicated synthetic', 'page_label': 'p1'}}}}
        self.project = self.root / 'pilot-project'
        (self.project / 'automation').mkdir(parents=True)
        (self.project / 'automation' / 'config.json').write_text(json.dumps(self.config), encoding='utf-8')
        (self.root / 'discovery-live-isolation.json').write_text(json.dumps({
            'schemaVersion': 1, 'mode': 'isolated-read-only', 'owner': 1,
            'taskSpaceId': 6, 'dedicatedSpace': True}), encoding='utf-8')
        self.patches = [
            patch.object(live.app_paths, 'DATA', self.root), patch.object(live.app_paths, 'WORKER_USER', 0),
            patch.object(live.browser, 'DB', self.root / 'discovery_browser.sqlite3'),
            patch.object(live.ledger, 'DB', self.root / 'cyclic_discovery.sqlite3'),
            patch.object(live, '_ORIGINAL_CONFIG', self.original),
            patch.dict(os.environ, {'JUNFEI_DISCOVERY_LIVE': 'isolated-read-only', 'JUNFEI_PROJECT_ROOT': str(self.project)}),
            patch.object(live.browser.runtime_environment, 'configuration', side_effect=lambda: copy.deepcopy(self.config)),
            patch.object(live, '_launch_worker'),
            patch.object(live.browser.subprocess, 'run', side_effect=AssertionError('No subprocess in synthetic tests')),
            patch('socket.socket', side_effect=AssertionError('No network in synthetic tests')),
        ]
        for item in self.patches:
            item.start()
        self.ingest(chain()[:1])

    def tearDown(self):
        live._leases.clear()
        live._threads.clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def ingest(self, events, cycle='cycle', owner=1, revision=0):
        return live.ledger.ingest(owner, {'cycleId': cycle, 'expectedRevision': revision, 'events': events})

    def request(self, **changes):
        data = dict(runId='run1', cycleId='cycle', expectedRevision=live.ledger.report(1, 'cycle')['revision'],
                    sourceEventId='k1', maxActions=5, maxRounds=2, maxSeconds=120)
        data.update(changes)
        data['planFingerprint'] = live.planner.prepare(1, {k: data[k] for k in
            ('cycleId', 'expectedRevision', 'maxActions', 'maxRounds')})['planFingerprint']
        return data

    def begin(self, **changes):
        data = self.request(**changes)
        live.start(1, data)
        return data

    def receipt(self, lease, request, kind, result='captured'):
        live._check_lease(lease, 1, request, kind)
        base = {**request, 'captureKind': kind, 'schemaVersion': 1,
                'status': 'capture_started', 'reason': 'synthetic_fixture',
                'target': {'taskSpaceId': 6}}
        c = live.browser._connect(True)
        try:
            c.execute('BEGIN IMMEDIATE')
            live._browser_guard(c, 1, live.browser._binding(1)[0], lease)
            c.execute('INSERT INTO attempts VALUES (?,?,?,?,?)', (1, request['captureId'], 'fixture', 'capture_started', json.dumps(base)))
            c.commit()
        finally:
            c.close()
        live._dispatch_started(lease, 1, request, kind)
        if result == 'raise':
            raise RuntimeError('Synthetic uncertain dispatch')
        report = live.ledger.report(1, request['cycleId'])
        parent = next(e for e in report['events'] if e['id'] == request['parentId'])
        event = {'id': 'event-' + request['captureId'], 'kind': kind,
                 'parentId': parent['id'], 'marketplace': 'US', 'sourceType': 'browser_visible',
                 'observedAt': '2026-02-01T00:00:00+00:00'}
        if kind == 'search':
            from urllib.parse import urlencode
            event.update(query=parent['phrase'], url='https://amazon.com/s?' + urlencode({'k': parent['phrase']}),
                         products=[{'asin': 'B000000004', 'title': 'First visible product'},
                                   {'asin': 'B000000005', 'title': 'Second product'}])
        elif kind == 'seller':
            event.update(asin=request['asin'], sellerId='SELLER2', sellerName='Two',
                         sellerLabel='Sold by Two', sellerLinkSource='visible_sold_by_link',
                         sellerLink='https://amazon.com/sp?seller=SELLER2', url='https://amazon.com/dp/' + request['asin'])
        elif kind == 'store':
            event.update(sellerId=request['sellerId'], status='captured', url='https://amazon.com/s?me=' + request['sellerId'],
                         products=[{'asin': 'B000000006', 'title': 'New Linen Dress Long Sleeve'}])
        base.update(status=result)
        if result == 'captured':
            base['preparedBatch'] = {'cycleId': request['cycleId'], 'expectedRevision': request['expectedRevision'], 'events': [event]}
        else:
            base['reason'] = 'captcha_or_challenge' if result == 'blocked' else 'runtime_outcome_unknown'
        c = live.browser._connect(True)
        try:
            c.execute('UPDATE attempts SET status=?,receipt=? WHERE owner=1 AND id=?', (result, json.dumps(base), request['captureId']))
            c.commit()
        finally:
            c.close()
        if result == 'captured':
            live._check_lease(lease, 1, request, kind, phase='after_capture')
        return base

    def transport(self, owner, request, kind, lease):
        self.assertEqual(owner, 1)
        return self.receipt(lease, request, kind)

    def test_chain_is_finite_actual_stage_counts_and_no_qualification(self):
        self.begin()
        with patch.object(live.browser, 'capture_live', side_effect=self.transport) as capture:
            live._work(1, 'run1')
        result = live.status(1, 'run1')
        self.assertEqual((result['status'], result['reason'], result['usedActions']), ('stopped', 'action_limit', 5))
        self.assertEqual(result['observedStages'], {'search_capture': 2, 'seller_capture': 1, 'store_capture': 1, 'title_phrase_capture': 1})
        self.assertEqual(capture.call_count, 4)
        self.assertEqual(result['browserCapturesRecorded'], 4)
        self.assertEqual(result['qualifiedCount'] + result['importedCount'] + result['publicationsPerformed'], 0)
        self.assertFalse(result['productionExecutionAllowed'])
        self.assertNotIn('"token"', json.dumps(result))
        self.assertNotIn('"token_hash"', json.dumps(result))
        self.assertNotIn(str(self.cli), json.dumps(result))

    def test_title_prefix_is_literal_and_never_brand_rewrite(self):
        text = "Brand  Women'S Jacket, Green Extra Tall Fine Warm More"
        prefix = live.title_prefix(text)
        self.assertEqual(prefix, "Brand  Women'S Jacket, Green Extra Tall Fine Warm")
        self.assertTrue(text.startswith(prefix))
        with self.assertRaises(ValueError):
            live.title_prefix('x' * 301)

    def test_strict_request_limits_and_no_injected_privileges(self):
        data = self.request()
        for key in ('maxActions', 'maxRounds', 'maxSeconds'):
            for value in (0, True, '2', 1.5, 601):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    live.start(1, {**data, key: value})
        for extra in ('url', 'owner', 'lease', 'script', 'callback'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                live.start(1, {**data, extra: 'forbidden'})
        with self.assertRaises(ValueError):
            live.start(True, data)

    def test_production_default_frozen_employee_marker_and_collision_rejected(self):
        data = self.request()
        for item in (patch.dict(os.environ, {'JUNFEI_DISCOVERY_LIVE': ''}),
                     patch.dict(os.environ, {'JUNFEI_PROJECT_ROOT': ''}),
                     patch.object(live.app_paths, 'WORKER_USER', 1), patch.object(live.sys, 'frozen', True, create=True),
                     patch.object(live.browser, 'DB', self.root / 'wrong' / 'browser.sqlite3')):
            with item, self.assertRaises(ValueError):
                live.start(1, data)
        self.config['discovery_browser']['account_bindings']['2'] = copy.deepcopy(self.config['discovery_browser']['account_bindings']['1'])
        with self.assertRaisesRegex(ValueError, 'shared_binding'):
            live.start(1, data)
        del self.config['discovery_browser']['account_bindings']['2']
        self.original.write_text(json.dumps({'browser': {'task_space_id': 6}}))
        with self.assertRaisesRegex(ValueError, 'production_space'):
            live.start(1, data)

    def test_duplicate_start_never_restarts_and_budget_immutable(self):
        data = self.begin()
        self.assertEqual(live.start(1, data)['usedActions'], 0)
        self.assertEqual(live._launch_worker.call_count, 1)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            live.start(1, {**data, 'maxActions': 6})

    def test_status_is_read_only_and_account_isolated(self):
        self.begin()
        before = {p.name: p.read_bytes() for p in self.root.glob('*.sqlite3')}
        live.status(1, 'run1')
        with self.assertRaises(ValueError):
            live.status(2, 'run1')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.glob('*.sqlite3')})

    def test_owner_and_same_space_guards_and_private_lease(self):
        self.begin()
        self.assertTrue(live.planner_barrier(1))
        with self.assertRaises(ValueError):
            live.assert_owner_idle(1)
        with live._planning(1, 'run1'):
            self.assertEqual(live.planner_barrier(1), [])
        lease, step = live._reserve(1, 'run1')
        c = live.browser._connect()
        try:
            for owner in (1, 2):
                with self.assertRaisesRegex(ValueError, 'owns_scope'):
                    live._browser_guard(c, owner, {'spaceId': 6})
            live._browser_guard(c, 1, live.browser._binding(1)[0], lease)
            with self.assertRaisesRegex(ValueError, 'trusted_live_lease'):
                live._browser_guard(c, 1, {'spaceId': 6}, {'token': lease.token})
        finally:
            c.close()
        with self.assertRaises(ValueError):
            live._check_lease(lease, 1, {**step['request'], 'parentId': 'other'}, 'search')

    def test_concurrent_reservations_charge_once(self):
        self.begin()
        def reserve():
            try:
                return live._reserve(1, 'run1') is not None
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(lambda _: reserve(), range(2))), 1)
        self.assertEqual(live.status(1, 'run1')['usedActions'], 1)

    def test_stop_before_dispatch_and_late_dispatch_forbidden(self):
        self.begin()
        lease, step = live._reserve(1, 'run1')
        result = live.stop(1, 'run1', cancel=True)
        self.assertEqual(result['attempts'][0]['status'], 'cancelled_before_dispatch')
        self.assertEqual(result['usedActions'], 1)
        self.assertTrue(lease.stop_path.is_file())
        with self.assertRaises(ValueError):
            live._dispatch_started(lease, 1, step['request'], 'search')

    def test_stop_after_dispatch_keeps_unknown_and_blocks_new_run(self):
        data = self.begin()
        lease, step = live._reserve(1, 'run1')
        live._dispatch_started(lease, 1, step['request'], 'search')
        result = live.stop(1, 'run1')
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['unresolvedStepCount'], 1)
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            live.start(1, {**data, 'runId': 'new'})
        self.assertEqual(live.start(1, data)['status'], 'unknown')

    def test_unknown_or_access_block_stops_immediately(self):
        for outcome in ('blocked', 'execution_unknown', 'raise'):
            with self.subTest(outcome=outcome):
                rid = 'run-' + outcome
                # Separate owner histories intentionally use a new fixture DB,
                # not an operational retry or an acceptance runner.
                with patch.object(live.browser, 'DB', self.root / ('fixture-' + outcome + '.sqlite3')):
                    self.begin(runId=rid)
                    with patch.object(live.browser, 'capture_live', side_effect=lambda u, r, k, l: self.receipt(l, r, k, outcome)) as mock:
                        live._work(1, rid)
                    result = live.status(1, rid)
                    self.assertEqual(mock.call_count, 1)
                    self.assertEqual(result['usedActions'], 1)
                    self.assertEqual(result['status'], 'blocked' if outcome == 'blocked' else 'unknown')

    def test_graph_and_configuration_changes_stop_without_dispatch(self):
        self.begin()
        self.config['browser']['task_space_id'] = 7
        with patch.object(live.browser, 'capture_live') as capture:
            live._work(1, 'run1')
        capture.assert_not_called()
        self.assertEqual(live.status(1, 'run1')['usedActions'], 0)

    def test_graph_mutation_after_reservation_is_rejected(self):
        self.begin()
        lease, step = live._reserve(1, 'run1')
        self.ingest(chain()[1:2], revision=1)
        with self.assertRaisesRegex(ValueError, 'graph_changed'):
            live._check_lease(lease, 1, step['request'], 'search')

    def test_expired_dispatch_never_auto_resumes(self):
        data = self.begin()
        lease, step = live._reserve(1, 'run1')
        live._dispatch_started(lease, 1, step['request'], 'search')
        with patch.object(live, '_now', return_value=lease.deadline + 1):
            with self.assertRaisesRegex(ValueError, 'deadline'):
                live._check_lease(lease, 1, step['request'], 'search')
            live._halt(1, 'run1', 'expired')
        self.assertEqual(live.start(1, data)['status'], 'unknown')

    def test_attached_graph_and_receipt_finish_rollback_together(self):
        self.begin()
        lease, step = live._reserve(1, 'run1')
        receipt = self.receipt(lease, step['request'], 'search')
        with patch.object(live, '_save_step', side_effect=sqlite3.OperationalError('fixture failure')):
            with self.assertRaises(sqlite3.OperationalError):
                live._finish(lease, receipt)
        self.assertEqual(live.ledger.report(1, 'cycle')['revision'], 1)
        self.assertEqual(live.status(1, 'run1')['attempts'][0]['status'], 'dispatch_unknown')

    def test_reservation_and_budget_rollback_together(self):
        self.begin()
        with patch.object(live, '_save_run', side_effect=sqlite3.OperationalError('fixture failure')):
            with self.assertRaises(sqlite3.OperationalError):
                live._reserve(1, 'run1')
        result = live.status(1, 'run1')
        self.assertEqual((result['usedActions'], result['attempts']), (0, []))

    def test_absolute_round_cap_and_depth_first_store_prefix(self):
        self.ingest(chain()[1:], revision=1)
        self.begin(sourceEventId='t1', maxActions=3, maxRounds=2)
        with patch.object(live.browser, 'capture_live', side_effect=self.transport):
            live._work(1, 'run1')
        result = live.status(1, 'run1')
        self.assertEqual([s['kind'] for s in result['attempts']], ['title_phrase_capture', 'search_capture', 'seller_capture'])
        self.assertTrue(all(s['proposedRound'] == 2 for s in result['attempts']))
        self.assertEqual(result['attempts'][2]['chosenVisibleIndex'], 0)

    def test_unknown_capture_on_other_cycle_and_full_history_blocks(self):
        c = live.browser._connect(True)
        try:
            for n in range(120):
                value = {'captureId': str(n), 'cycleId': 'other', 'parentId': 'q',
                         'captureKind': 'seller', 'status': 'execution_unknown' if n == 0 else 'blocked'}
                c.execute('INSERT INTO attempts VALUES (?,?,?,?,?)', (1, str(n), 'fixture', value['status'], json.dumps(value)))
            c.commit()
        finally:
            c.close()
        with self.assertRaises(ValueError):
            live.start(1, self.request())

    def test_corrupt_live_history_is_a_barrier_even_when_status_unrecognized(self):
        self.begin()
        with live._transaction() as c:
            c.execute("UPDATE live_runs SET status='invented',payload='{}' WHERE owner=1")
        self.assertEqual(live.planner_barrier(1)[0]['reason'], 'live_history_inconsistent')
        c = live.browser._connect()
        try:
            with self.assertRaises(ValueError):
                live._browser_guard(c, 2, {'spaceId': 6})
        finally:
            c.close()

    def test_manual_write_guard_does_not_create_capture_db_when_disabled(self):
        self.assertFalse(live.browser.DB.exists())
        with patch.dict(os.environ, {'JUNFEI_DISCOVERY_LIVE': ''}):
            with live.owner_write_guard(1):
                pass
        self.assertFalse(live.browser.DB.exists())

    def test_manual_write_guard_blocks_active_run(self):
        self.begin()
        with self.assertRaises(ValueError):
            with live.owner_write_guard(1):
                self.fail('Must not enter a manual mutation')

    def test_no_new_round_beyond_absolute_limit(self):
        self.begin(maxActions=20, maxRounds=1)
        with patch.object(live.browser, 'capture_live', side_effect=self.transport):
            live._work(1, 'run1')
        result = live.status(1, 'run1')
        self.assertEqual(result['usedActions'], 3)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(all(s['proposedRound'] == 1 for s in result['attempts']))

    def test_real_capture_bridge_with_real_lease_and_mock_runtime(self):
        from datetime import datetime, timezone
        self.begin(maxActions=1)
        def runtime(args, **kwargs):
            now = datetime.now(timezone.utc).isoformat()
            product = {'asin': 'B000000004', 'title': 'Visible cotton product',
                       'productURL': 'https://amazon.com/dp/B000000004'}
            destination = 'https://amazon.com/s?k=Cotton+Shirt'
            raw = {'schemaVersion': 1, 'status': 'captured', 'marketplace': 'US',
                   'query': 'Cotton Shirt', 'url': destination, 'capturedAt': now,
                   'products': [product], 'evidence': {
                       'selector': live.browser.SEARCH_SELECTOR, 'query': 'Cotton Shirt',
                       'marketplace': 'US', 'sourceURL': destination, 'capturedAt': now,
                       'cards': [{**product, 'cardAsin': product['asin'],
                                  'anchorHref': product['productURL'],
                                  'cardSelector': live.browser.SEARCH_CARD_SELECTOR,
                                  'titleSelector': live.browser.SEARCH_TITLE_SELECTOR,
                                  'directMainSlot': True, 'visible': True, 'sponsored': False}]},
                   'navigationDispatched': True, 'collectorDispatched': True, 'navigationPhase': 'finished',
                   'navigationEvidence': {'spaceId': 6, 'name': 'Dedicated synthetic', 'label': 'p1',
                                          'destination': destination, 'selectedURL': destination}}
            result = live.status(1, 'run1')
            self.assertEqual(result['attempts'][0]['status'], 'dispatch_unknown')
            directory = Path(kwargs['cwd'])
            self.assertTrue(self.root in directory.parents)
            self.assertIn('await page.goto(', (directory / 'capture.mjs').read_text(encoding='utf-8'))
            (directory / 'result.json').write_text(json.dumps(raw), encoding='utf-8')
            return live.browser.subprocess.CompletedProcess(args, 0)
        with patch.object(live.browser.subprocess, 'run', side_effect=runtime) as dispatch:
            live._work(1, 'run1')
        result = live.status(1, 'run1')
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(result['reason'], 'action_limit', result)
        self.assertEqual(result['browserCapturesRecorded'], 1)
        self.assertEqual(result['revision'], 2)

    def test_corrupt_stop_path_cannot_write_another_file(self):
        self.begin()
        other = self.root / 'must-not-create.txt'
        with live._transaction() as c:
            row = c.execute('SELECT payload FROM live_runs WHERE owner=1').fetchone()
            run = json.loads(row[0])
            run['stopPath'] = str(other)
            c.execute('UPDATE live_runs SET payload=? WHERE owner=1', (json.dumps(run),))
        with self.assertRaisesRegex(ValueError, 'stop_path'):
            live.stop(1, 'run1')
        self.assertFalse(other.exists())

    def test_missing_status_and_stop_never_create_database(self):
        self.assertFalse(live.browser.DB.exists())
        for function in (live.status, live.stop):
            with self.assertRaisesRegex(ValueError, 'not found'):
                function(1, 'missing')
        self.assertFalse(live.browser.DB.exists())

    def test_nondurable_journal_modes_are_rejected_without_changing_modes(self):
        original_connect = live.browser._connect
        class Proxy:
            def __init__(self, connection, bad_query, mode):
                self.connection, self.bad_query, self.mode = connection, bad_query, mode
            def __getattr__(self, key):
                return getattr(self.connection, key)
            def execute(self, query, *args):
                if query == self.bad_query:
                    from unittest.mock import Mock
                    return Mock(fetchone=lambda: (self.mode,))
                return self.connection.execute(query, *args)
        for query in ('PRAGMA main.journal_mode', 'PRAGMA graph.journal_mode'):
            for mode in ('wal', 'off', 'memory', 'unknown'):
                with self.subTest(query=query, mode=mode), patch.object(live.browser, '_connect',
                        side_effect=lambda write: Proxy(original_connect(write), query, mode)):
                    with self.assertRaisesRegex(ValueError, 'rollback_journal'):
                        with live._transaction(graph=True):
                            self.fail('Nondurable transaction must not begin')


if __name__ == '__main__':
    unittest.main()
