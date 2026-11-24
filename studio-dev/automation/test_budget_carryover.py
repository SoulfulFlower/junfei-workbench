import json
import os
import socket
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from pipeline import Pipeline, STAGES


class BudgetCarryoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, JUNFEI_ACCOUNT_DATA=self.tmp.name)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.net = patch.object(socket.socket, 'connect', side_effect=AssertionError('offline tests'))
        self.net.start()
        self.addCleanup(self.net.stop)
        self.cfg = {'images': {'enabled': True, 'per_product_budget_rmb': 100, 'daily_budget_rmb': 10}, 'execution': {'max_attempts': 5}}
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        self.p = Pipeline(self.path, self.cfg)
        self.addCleanup(self.p.db.close)
        for job in ('old', 'new', 'other'):
            self.p.db.execute("INSERT INTO jobs(id,market,source_id,stage,config,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (job, 'US', job, STAGES.index('images'), json.dumps(self.cfg), 'test', 'test'))

    def old(self, amount='7'):
        r = self.p.reserve_image_cost('old', amount)['reservation_id']
        self.p.db.execute('UPDATE image_costs SET day=? WHERE id=?', ((date.today()-timedelta(days=1)).isoformat(), r))
        return r

    def test_cross_day_pending_counts_and_status_explains_scope(self):
        self.old()
        with self.assertRaises(ValueError): self.p.reserve_image_cost('new', '4')
        status = self.p.image_budget_status()
        self.assertEqual(status['carryover_reserved_rmb'], '7.00')
        self.assertEqual(status['daily_used_and_reserved_rmb'], '7.00')
        self.assertIn('not a provider', status['scope'])
        self.p.reserve_image_cost('new', '3')

    def test_historical_settled_no_longer_counts(self):
        r = self.old()
        self.p.settle_image_cost(r, '7', 'verified actual charge')
        self.assertEqual(self.p.image_budget_status()['daily_used_and_reserved_rmb'], '0.00')
        self.p.reserve_image_cost('new', '10')

    def test_failure_and_unknown_keep_reservation(self):
        self.old()
        for status in ('blocked', 'uncertain'):
            self.p.db.execute("UPDATE jobs SET status='ready' WHERE id='old'")
            token = self.p.claim('old')['token']
            self.p.hold('old', token, status, 'provider outcome needs reconciliation')
            self.assertEqual(self.p.image_budget_status()['carryover_reserved_rmb'], '7.00')
            with self.assertRaises(ValueError): self.p.reserve_image_cost('new', '4')

    def test_failed_event_rolls_back_reservation(self):
        with patch.object(self.p, 'event', side_effect=RuntimeError('write failure')):
            with self.assertRaises(RuntimeError): self.p.reserve_image_cost('new', '3')
        self.assertEqual(self.p.db.execute('SELECT COUNT(*) FROM image_costs').fetchone()[0], 0)

    def test_concurrent_connections_cannot_exceed_remaining(self):
        self.old('6')
        barrier = threading.Barrier(2)
        outcomes = []
        def reserve(job):
            p = Pipeline(self.path, self.cfg)
            try:
                barrier.wait(timeout=10)
                try:
                    p.reserve_image_cost(job, '3')
                    outcomes.append('ok')
                except ValueError: outcomes.append('blocked')
            finally: p.db.close()
        threads = [threading.Thread(target=reserve, args=(job,)) for job in ('new', 'other')]
        for t in threads: t.start()
        for t in threads: t.join(timeout=15)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertCountEqual(outcomes, ['ok', 'blocked'])
        self.assertEqual(self.p.image_budget_status()['daily_used_and_reserved_rmb'], '9.00')

    def test_over_budget_blocks_new_reservation_and_claim(self):
        r = self.old('1')
        self.assertEqual(self.p.settle_image_cost(r, '2', 'verified actual charge')['state'], 'over_budget')
        with self.assertRaises(ValueError): self.p.reserve_image_cost('old', '1')
        with self.assertRaises(ValueError): self.p.claim('old')
        with self.assertRaises(ValueError): self.p.settle_image_cost(r, '0', 'duplicate settlement')

    def test_settlement_failure_keeps_pending(self):
        r = self.old()
        with patch.object(self.p, 'event', side_effect=RuntimeError('write failure')):
            with self.assertRaises(RuntimeError): self.p.settle_image_cost(r, '0', 'confirmed no charge')
        self.assertEqual(self.p.image_budget_status()['carryover_reserved_rmb'], '7.00')

if __name__ == '__main__':
    unittest.main()
