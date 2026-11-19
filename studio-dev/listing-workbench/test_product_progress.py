import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import product_progress as progress
import workbench_image_tasks


class ProductProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put('studio.sqlite3', 'workspace', 'id INTEGER,body TEXT',
                 [(1, json.dumps({'products': [{'id': 'P', 'sku': 'SKU', 'market': 'US'}]}))])
        self.snapshot = patch.object(workbench_image_tasks, 'snapshot', return_value=[])
        self.snapshot.start()
        self.addCleanup(self.snapshot.stop)

    def put(self, filename, table, schema, rows):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute('CREATE TABLE IF NOT EXISTS ' + table + '(' + schema + ')')
            conn.execute('DELETE FROM ' + table)
            if rows:
                conn.executemany('INSERT INTO ' + table + ' VALUES(' + ','.join('?' for _ in rows[0]) + ')', rows)

    def projects(self, *rows):
        self.put('visual_studio.sqlite3', 'projects', 'id TEXT,product_id TEXT,body TEXT,created REAL',
                 [(pid, product, json.dumps({'deliverable': kind}), created) for pid, product, kind, created in rows])

    def runs(self, *rows):
        self.put('visual_studio.sqlite3', 'runs', 'id TEXT,project_id TEXT,body TEXT,updated REAL',
                 [(rid, project, json.dumps({'productId': product, 'slot': slot, 'status': status}), updated)
                  for rid, project, product, slot, status, updated in rows])

    def summary(self):
        return progress.summary(self.root, 2)['products'][0]

    def test_current_failed_checks_and_unknown_submission_are_actionable_without_manual_pending(self):
        self.projects(('current', 'P', 'gallery', 1))
        for status in ['needs_revision', 'failed', 'review_error', 'submit_unknown', 'interrupted',
                       'awaiting_manual', 'approved', 'generating']:
            with self.subTest(status=status):
                self.runs(('run', 'current', 'P', 0, status, 1))
                before = (self.root / 'visual_studio.sqlite3').read_bytes()
                result = self.summary()
                self.assertEqual(result['needsAttention'], status in progress.VISUAL_BLOCKED)
                self.assertEqual(result['running'], status in progress.VISUAL_ACTIVE)
                self.assertEqual((self.root / 'visual_studio.sqlite3').read_bytes(), before)

    def test_newer_project_and_slot_retry_retire_old_failures(self):
        self.projects(('old', 'P', 'gallery', 1), ('current', 'P', 'gallery', 2))
        self.runs(('old', 'old', 'P', 1, 'failed', 5),
                  ('first', 'current', 'P', 0, 'needs_revision', 6),
                  ('second', 'current', 'P', 0, 'awaiting_manual', 7))
        self.assertFalse(self.summary()['needsAttention'])
        self.projects(('old', 'P', 'gallery', 1), ('current', 'P', 'gallery', 2), ('new', 'P', 'gallery', 3))
        self.assertFalse(self.summary()['needsAttention'])

    def test_same_timestamp_matches_studio_project_and_run_id_order(self):
        self.projects(('a', 'P', 'gallery', 1), ('b', 'P', 'gallery', 1))
        self.runs(('old', 'a', 'P', 0, 'failed', 2), ('a', 'b', 'P', 0, 'failed', 3),
                  ('b', 'b', 'P', 0, 'approved', 3))
        self.assertFalse(self.summary()['needsAttention'])

    def test_current_aplus_and_superseded_inflight_operations_are_separate(self):
        self.projects(('old', 'P', 'gallery', 1), ('gallery', 'P', 'gallery', 3), ('aplus', 'P', 'aplus', 2))
        self.runs(('old', 'old', 'P', 0, 'generating', 5),
                  ('gallery', 'gallery', 'P', 0, 'approved', 3), ('aplus', 'aplus', 'P', 0, 'needs_revision', 2))
        result = self.summary()
        self.assertTrue(result['running'])
        self.assertEqual([r['taskId'] for r in result['reasons']], ['aplus'])

    def test_deleted_or_foreign_products_never_leak_progress(self):
        self.projects(('foreign', 'OTHER', 'gallery', 1))
        self.runs(('foreign', 'foreign', 'OTHER', 0, 'submit_unknown', 2))
        self.assertFalse(self.summary()['needsAttention'])
        self.assertEqual(len(progress.summary(self.root, 2)['products']), 1)

    def test_listing_uses_current_owner_and_product_market_and_latest_request(self):
        def job(jid, owner, market, status, created):
            return (jid, owner, created, json.dumps({'id': jid, 'productId': 'P', 'market': market, 'status': status}))
        self.put('studio.sqlite3', 'listing_generation_jobs', 'id TEXT,owner INTEGER,created REAL,body TEXT',
                 [job('old', 2, 'US', 'needs_review', 1), job('new', 2, 'US', 'applied', 2),
                  job('uk', 2, 'UK', 'needs_review', 3), job('foreign', 3, 'US', 'needs_review', 4)])
        self.assertFalse(self.summary()['needsAttention'])

    def test_erp_owner_product_sku_and_newer_receipt_scope(self):
        def job(jid, owner, sku, status, created):
            return (jid, owner, json.dumps({'id': jid, 'productId': 'P', 'parentSku': sku,
                                           'status': status, 'createdAt': created}))
        for filename in ('erp-collection/jobs.sqlite3', 'publication-flow/jobs.sqlite3'):
            self.put(filename, 'jobs', 'id TEXT,account_id INTEGER,body TEXT',
                     [job('old', 2, 'SKU', 'needs_reconciliation', 1), job('new', 2, 'SKU', 'verified', 2),
                      job('foreign', 3, 'SKU', 'failed', 3), job('other-sku', 2, 'OTHER', 'failed', 4)])
        self.assertFalse(self.summary()['needsAttention'])
        self.put('erp-collection/jobs.sqlite3', 'jobs', 'id TEXT,account_id INTEGER,body TEXT',
                 [job('current', 2, 'SKU', 'needs_reconciliation', 5)])
        self.assertEqual(self.summary()['reasons'][0]['code'], 'needs_reconciliation')

    def test_colour_failure_and_running_set_are_read_only(self):
        with patch.object(workbench_image_tasks, 'snapshot', return_value=[
            {'id': 'failed', 'productId': 'P', 'status': 'needs_attention'},
            {'id': 'running', 'productId': 'P', 'status': 'local_rendering'}]):
            result = self.summary()
        self.assertTrue(result['needsAttention'])
        self.assertTrue(result['running'])
        self.assertEqual(result['reasons'][0]['stage'], 'colours')

    def test_empty_account_does_not_create_ledgers(self):
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp)
            self.assertEqual(progress.summary(empty, 3), {'products': []})
            self.assertEqual(list(empty.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
