"""Offline planner tests. All writes are synthetic fixtures in temporary storage."""
import copy
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


# app_paths has an import-time directory initializer; never point it at production.
_IMPORT_ROOT = tempfile.TemporaryDirectory(prefix='discovery-plan-import-')
with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': _IMPORT_ROOT.name}):
    import discovery_plan as plan


def chain():
    def event(eid, kind, parent, **fields):
        return dict(id=eid, kind=kind, parentId=parent, marketplace='US',
                    observedAt='2026-01-01T00:00:00Z', sourceType='browser_visible', **fields)
    return [
        event('k1', 'keyword', None, asin='B000000001', sourceTitle='Cotton Shirt Women',
              phrase='Cotton Shirt', url='https://amazon.com/dp/B000000001'),
        event('q1', 'search', 'k1', query='Cotton Shirt', url='https://amazon.com/s?k=Cotton+Shirt',
              products=[{'asin': 'B000000002', 'title': 'Cotton Shirt Blue'}]),
        event('s1', 'seller', 'q1', asin='B000000002', sellerId='SELLER1',
              sellerName='Seller One', sellerLabel='Sold by Seller One',
              sellerLinkSource='visible_sold_by_link', sellerLink='https://amazon.com/sp?seller=SELLER1',
              url='https://amazon.com/dp/B000000002'),
        event('t1', 'store', 's1', sellerId='SELLER1', status='captured',
              url='https://amazon.com/s?me=SELLER1',
              products=[{'asin': 'B000000003', 'title': 'Linen Pants Women'}]),
        event('k2', 'keyword', 't1', asin='B000000003', sourceTitle='Linen Pants Women',
              phrase='Linen Pants', url='https://amazon.com/dp/B000000003'),
        event('q2', 'search', 'k2', query='Linen Pants', url='https://amazon.com/s?k=Linen+Pants',
              products=[{'asin': 'B000000004', 'title': 'Linen Pants Tall'}]),
        event('s2', 'seller', 'q2', asin='B000000004', sellerId='SELLER2',
              sellerName='Seller Two', sellerLabel='Sold by Seller Two',
              sellerLinkSource='visible_sold_by_link', sellerLink='https://amazon.com/sp?seller=SELLER2',
              url='https://amazon.com/dp/B000000004'),
        event('t2', 'store', 's2', sellerId='SELLER2', status='captured',
              url='https://amazon.com/s?me=SELLER2',
              products=[{'asin': 'B000000005', 'title': 'Wool Coat Long'}]),
    ]


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='discovery-plan-test-')
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(plan.ledger, 'DB', self.root / 'graph.sqlite3'),
            patch.object(plan.browser, 'DB', self.root / 'captures.sqlite3'),
            patch.object(plan.browser, 'capture', side_effect=AssertionError('No capture permitted')),
            patch.object(plan.browser, 'capture_store', side_effect=AssertionError('No capture permitted')),
            patch.object(plan.browser.subprocess, 'run', side_effect=AssertionError('No subprocess permitted')),
        ]
        for p in self.patches:
            p.start()
        self.request = dict(cycleId='test', expectedRevision=1, maxActions=20, maxRounds=20)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def ingest(self, events, owner=1, revision=0, cycle='test'):
        return plan.ledger.ingest(owner, {'cycleId': cycle, 'expectedRevision': revision, 'events': events})

    def prepare(self, owner=1, **fields):
        with patch.object(plan.ledger, 'ingest', side_effect=AssertionError('No ingestion permitted')):
            return plan.prepare(owner, {**self.request, **fields})

    def receipt(self, capture_id, status='captured', owner=1, **fields):
        receipt = dict(captureId=capture_id, cycleId='test', parentId='q1',
                       expectedRevision=1, captureKind='seller', asin='B000000002',
                       status=status, reason='test_fixture')
        receipt.update(fields)
        with closing(sqlite3.connect(plan.browser.DB)) as conn, conn:
            conn.execute('CREATE TABLE IF NOT EXISTS attempts (owner INTEGER, id TEXT, digest TEXT, status TEXT, receipt TEXT, PRIMARY KEY(owner,id))')
            conn.execute('INSERT INTO attempts VALUES (?,?,?,?,?)',
                         (owner, capture_id, 'fixture', status, json.dumps(receipt)))
        return receipt

    def snapshot(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.iterdir() if p.is_file()}

    def test_missing_ledger_does_not_create_database(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.prepare()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(plan.ledger.DB.exists())
        self.assertFalse(plan.browser.DB.exists())

    def test_exact_request_and_finite_integer_limits(self):
        self.ingest(chain()[:1])
        for field in ('maxActions', 'maxRounds'):
            for value in (0, -1, 21, True, False, 1.0, '2', None, math.inf, math.nan):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.prepare(**{field: value})
        for field in self.request:
            request = {k: v for k, v in self.request.items() if k != field}
            with self.subTest(missing=field), self.assertRaises(ValueError):
                plan.prepare(1, request)
        with self.assertRaises(ValueError):
            self.prepare(execute=True)
        for revision in (True, -1, '1', 1.0):
            with self.assertRaises(ValueError):
                self.prepare(expectedRevision=revision)

    def test_exact_owner_and_current_revision(self):
        self.ingest(chain()[:1])
        for owner in (True, 0, -1, '1', None):
            with self.assertRaises(ValueError):
                self.prepare(owner=owner)
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.prepare(owner=2)
        for revision in (0, 2):
            with self.assertRaisesRegex(ValueError, 'stale_revision'):
                self.prepare(expectedRevision=revision)
        self.ingest(chain()[:1], owner=2)
        self.assertNotEqual(self.prepare()['planId'], self.prepare(owner=2)['planId'])

    def test_read_only_deterministic_fingerprint_and_safe_contract(self):
        self.ingest(chain()[:2])
        before = self.snapshot()
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first, second)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(plan.browser.DB.exists())
        self.assertEqual(first['status'], 'ready')
        self.assertTrue(first['readOnly'])
        self.assertFalse(first['executionAllowed'])
        self.assertFalse(first['automaticNavigationImplemented'])
        self.assertFalse(first['persistentQueueCreated'])
        self.assertFalse(first['qualificationEvaluated'])
        self.assertEqual((first['qualifiedCount'], first['importedCount'], first['externalCallsPerformed']), (0, 0, 0))
        self.assertEqual(first['planId'], first['planFingerprint'])
        self.assertEqual(first, plan.assert_current(1, self.request, first['planId']))
        action = first['actions'][0]
        self.assertEqual((action['kind'], action['sourceEventId'], action['sourceRound'], action['proposedRound']),
                         ('seller_capture', 'q1', 1, 1))
        self.assertNotIn('sellerId', action)
        self.assertNotIn('similarity', action)
        self.assertEqual(action['source']['eventId'], 'q1')
        self.assertFalse(action['executionAllowed'])

    def test_all_frontier_stages_use_real_sources_without_hypothetical_chain(self):
        for length, kind, source in ((1, 'search_capture', 'k1'), (2, 'seller_capture', 'q1'),
                                     (3, 'store_capture', 's1'), (4, 'title_phrase_capture', 't1')):
            with self.subTest(kind=kind):
                cycle = 'stage' + str(length)
                self.ingest(chain()[:length], cycle=cycle)
                result = self.prepare(cycleId=cycle)
                self.assertEqual(len(result['actions']), 1)
                action = result['actions'][0]
                self.assertEqual((action['kind'], action['sourceEventId']), (kind, source))
                if kind == 'title_phrase_capture':
                    self.assertEqual(action['proposedRound'], 2)
                    self.assertEqual(action['listedTitle'], 'Linen Pants Women')
                    self.assertNotIn('query', action)
                    self.assertNotIn('phrase', action)

    def test_round_limit_is_absolute_not_number_of_distinct_rounds(self):
        self.ingest(chain())
        limited = self.prepare(maxRounds=2)
        self.assertEqual(limited['actions'], [])
        self.assertEqual(limited['status'], 'no_actions')
        self.assertEqual(limited['roundLimitedCount'], 1)
        self.assertEqual(limited['skipped'][0]['proposedRound'], 3)
        self.assertEqual(self.prepare(maxRounds=3)['actions'][0]['proposedRound'], 3)

    def test_action_caps_and_duplicate_asin_sources(self):
        rows = chain()[:2]
        rows[1]['products'] = [{'asin': 'B' + str(i).zfill(9), 'title': 'Visible Product ' + str(i)}
                               for i in range(100, 125)]
        duplicate = copy.deepcopy(rows[1])
        duplicate['id'] = 'q_duplicate'
        self.ingest(rows + [duplicate])
        result = self.prepare(maxActions=7, maxRounds=1)
        self.assertEqual(len(result['actions']), 7)
        self.assertEqual(result['actionLimitedCount'], 18)
        self.assertEqual(len({a['asin'] for a in result['actions']}), 7)
        self.assertEqual(len([s for s in result['skipped'] if s['reason'] == 'duplicate_proposed_target']), 25)
        self.assertTrue(all(a['proposedRound'] <= 1 for a in result['actions']))

    def test_query_normalization_and_market_isolation(self):
        first = chain()[0]
        duplicate = copy.deepcopy(first)
        duplicate.update(id='same_query', phrase='COTTON---shirt')
        uk = copy.deepcopy(first)
        uk.update(id='uk_query', marketplace='UK', url='https://amazon.co.uk/dp/B000000001')
        self.ingest([first, duplicate, uk])
        result = self.prepare()
        self.assertEqual(len(result['actions']), 2)
        self.assertEqual({a['marketplace'] for a in result['actions']}, {'US', 'UK'})
        self.assertEqual({a['normalizedQuery'] for a in result['actions']}, {'cotton shirt'})

    def test_handled_target_and_searched_phrase_are_not_planned_again(self):
        rows = chain()[:3]
        duplicate_search = copy.deepcopy(rows[1])
        duplicate_search['id'] = 'q_repeat'
        duplicate_keyword = copy.deepcopy(rows[0])
        duplicate_keyword.update(id='k_repeat', phrase='COTTON SHIRT')
        self.ingest(rows + [duplicate_search, duplicate_keyword])
        result = self.prepare()
        self.assertEqual([a['kind'] for a in result['actions']], ['store_capture'])
        self.assertIn('already_handled_observed_target', [s['reason'] for s in result['skipped']])
        self.assertIn('duplicate_keyword_already_searched', [s['reason'] for s in result['skipped']])

    def test_store_seller_dedup_and_already_handled_title(self):
        rows = chain()[:5]
        extra_seller = copy.deepcopy(rows[2])
        extra_seller['id'] = 's_duplicate'
        extra_store = copy.deepcopy(rows[3])
        extra_store.update(id='t_duplicate', parentId='s_duplicate')
        self.ingest(rows + [extra_seller, extra_store])
        result = self.prepare()
        self.assertEqual([a['kind'] for a in result['actions']], ['search_capture'])
        self.assertIn('already_handled_observed_target', [s['reason'] for s in result['skipped']])

    def test_latest_round_search_prioritized(self):
        rows = chain()[:5]
        other = copy.deepcopy(rows[0])
        other.update(id='root_other', sourceTitle='Other Item Title', phrase='Other Item')
        self.ingest(rows + [other])
        result = self.prepare(maxActions=1)
        self.assertEqual(result['actions'][0]['sourceEventId'], 'k2')
        self.assertEqual(result['actionLimitedCount'], 1)

    def test_inaccessible_and_rejected_sources_propagate_review(self):
        rows = chain()[:4]
        rows[3].update(status='inaccessible', products=[], reason='Access challenge')
        rows[1]['products'].append({'asin': 'B000000099', 'title': 'Unrelated', 'similarity': 'REJECT'})
        self.ingest(rows)
        result = self.prepare()
        self.assertEqual(result['actions'], [])
        self.assertEqual({r['status'] for r in result['review']}, {'inaccessible', 'needs_review'})
        self.assertTrue(all(r['retryAllowed'] is False for r in result['review']))

    def test_empty_results_are_not_success_or_an_invented_branch(self):
        rows = chain()[:2]
        rows[1]['products'] = []
        self.ingest(rows)
        result = self.prepare()
        self.assertEqual(result['status'], 'no_actions')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['skipped'][0]['reason'], 'no_new_products')

    def test_unknown_or_started_any_owner_cycle_blocks_every_stage(self):
        self.ingest(chain()[:1])
        for status in ('execution_unknown', 'capture_started'):
            self.receipt(status, status=status, cycleId='different_cycle', parentId='elsewhere')
        result = self.prepare()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['actions'], [])
        self.assertEqual({b['status'] for b in result['blockers']}, {'execution_unknown', 'capture_started'})

    def test_hidden_active_attempt_beyond_100_history_entries_blocks(self):
        self.ingest(chain()[:2])
        self.receipt('old_active', status='execution_unknown', cycleId='older_cycle')
        for i in range(105):
            self.receipt('new_' + str(i), cycleId='older_cycle')
        self.assertEqual(len(plan.browser.history(1)['items']), 100)
        self.assertFalse(any(r['status'] == 'execution_unknown' for r in plan.browser.history(1)['items']))
        before = self.snapshot()
        result = self.prepare()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['blockers'][0]['captureId'], 'old_active')
        self.assertEqual(self.snapshot(), before)

    def test_other_owner_active_receipt_cannot_leak_or_block(self):
        self.ingest(chain()[:2])
        baseline = self.prepare()
        self.receipt('other_owner_secret', status='execution_unknown', owner=2)
        result = self.prepare()
        self.assertEqual(result, baseline)
        self.assertNotIn('other_owner_secret', json.dumps(result))

    def test_stopped_blocked_and_captured_receipts_never_trigger_retry(self):
        self.ingest(chain()[:2])
        for status in ('stopped', 'blocked', 'configuration_blocked', 'captured'):
            self.receipt('attempt_' + status, status=status)
        result = self.prepare()
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['status'], 'no_actions')
        self.assertEqual(result['review'][0]['reason'], 'existing_capture_requires_review')
        self.assertEqual({a['status'] for a in result['review'][0]['attempts']},
                         {'stopped', 'blocked', 'configuration_blocked', 'captured'})

    def test_search_and_store_receipt_branches_are_not_retried(self):
        self.ingest(chain()[:3])
        self.receipt('store_attempt', captureKind='store', parentId='s1', sellerId='SELLER1', status='blocked')
        self.assertEqual(self.prepare()['actions'], [])
        self.ingest(chain()[:1], cycle='only_keyword')
        self.receipt('search_attempt', captureKind='search', parentId='k1', cycleId='only_keyword', status='stopped')
        self.assertEqual(self.prepare(cycleId='only_keyword')['actions'], [])

    def test_corrupt_or_unrecognized_history_fails_closed(self):
        self.ingest(chain()[:1])
        self.receipt('corrupt', status='captured')
        with closing(sqlite3.connect(plan.browser.DB)) as conn, conn:
            conn.execute("UPDATE attempts SET receipt='not-json'")
        self.assertEqual(self.prepare()['status'], 'blocked')
        with closing(sqlite3.connect(plan.browser.DB)) as conn, conn:
            conn.execute('DELETE FROM attempts')
        self.receipt('new_state', status='future_state')
        self.assertEqual(self.prepare()['blockers'][0]['reason'], 'unrecognized_capture_status')

    def test_row_receipt_mismatch_and_missing_table_fail_closed(self):
        self.ingest(chain()[:1])
        self.receipt('mismatch', status='execution_unknown')
        with closing(sqlite3.connect(plan.browser.DB)) as conn, conn:
            conn.execute("UPDATE attempts SET status='captured'")
        self.assertEqual(self.prepare()['blockers'][0]['reason'], 'capture_history_inconsistent')
        with closing(sqlite3.connect(plan.browser.DB)) as conn, conn:
            conn.execute('DROP TABLE attempts')
        self.assertEqual(self.prepare()['blockers'][0]['reason'], 'capture_history_unreadable')

    def test_stale_fingerprint_on_history_limits_and_graph_changes(self):
        self.ingest(chain()[:1])
        initial = self.prepare()
        with self.assertRaisesRegex(ValueError, 'stale_plan'):
            plan.assert_current(1, {**self.request, 'maxActions': 2}, initial['planId'])
        self.receipt('later_unknown', status='execution_unknown', cycleId='different')
        with self.assertRaisesRegex(ValueError, 'stale_plan'):
            plan.assert_current(1, self.request, initial['planId'])
        self.ingest(chain()[1:2], revision=1)
        with self.assertRaisesRegex(ValueError, 'stale_revision'):
            self.prepare()
        self.assertNotEqual(self.prepare(expectedRevision=2)['planId'], initial['planId'])

    def test_concurrent_graph_change_rejected(self):
        self.ingest(chain()[:1])
        original = plan.ledger.report(1, 'test')
        changed = copy.deepcopy(original)
        changed['revision'] = 2
        with patch.object(plan.ledger, 'report', side_effect=[original, changed]):
            with self.assertRaisesRegex(ValueError, 'stale_revision'):
                self.prepare()


if __name__ == '__main__':
    unittest.main()
