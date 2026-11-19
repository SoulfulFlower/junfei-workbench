import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import agent_center as agent
import agent_intake as intake
import market_research as research


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(agent, 'DATA', self.root), patch.object(agent, 'DB', self.root/'agent.sqlite3'),
                        patch.object(research, 'DB', self.root/'research.sqlite3')]
        for item in self.patches: item.start()
        self.user = {'id': 1, 'username': 'fixture'}
        self.profile = agent.save_profile(1, dict(name='US fixture', store='Store', marketplace='US', shippingTemplate='FBM'))
        self.candidates = [research.candidate({'asin': a, 'title': 'Fixture reference'}, 'US') for a in ('B012345678', 'B087654321')]
        self.report = dict(id='report', created=1, status='completed', request={'market': 'US', 'month': '202609'}, candidates=self.candidates)
        research.save(self.report)
        self.workspace = {}
        research.import_products('report', [c['asin'] for c in self.candidates], self.workspace, self.user)
        self.save_workspace()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def save_workspace(self):
        with closing(sqlite3.connect(self.root/'studio.sqlite3')) as c, c:
            c.execute('CREATE TABLE IF NOT EXISTS workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            c.execute('INSERT OR REPLACE INTO workspace VALUES(1,1,?)', (json.dumps(self.workspace),))

    def enqueue(self):
        return intake.enqueue(1, self.profile, 'report', self.candidates)

    def no_dispatch(self, user, tid):
        return agent.public(agent.detail(user, tid))

    def test_candidate_starts_and_blocks_before_paid_work(self):
        with patch.object(agent, 'start', side_effect=lambda user, tid: agent.public(agent.detail(user, tid))) as start:
            outcomes = self.enqueue()
        self.assertEqual(start.call_count, 2)
        self.assertEqual([o['status'] for o in outcomes], ['created', 'created'])
        for outcome in outcomes:
            task = outcome['task']
            self.assertNotIn('snapshot', task)
            self.assertFalse(task['autoResearch'])
            self.assertFalse(task['autoListing'])
            self.assertFalse(task['aiPlanning'])
            self.assertEqual(task['intake']['reportId'], 'report')
            with patch('agent_center.threading.Thread.start'):
                agent.start(1, task['id'])
            with patch('competitors.analyse') as analyse, patch('provider.generate_listing') as generate:
                agent.run(1, task['id'])
            analyse.assert_not_called(); generate.assert_not_called()
            stored = agent.detail(1, task['id'])
            self.assertEqual(stored['status'], 'blocked')
            self.assertFalse(stored['results']['facts']['selection']['ok'])

    def test_repeated_intake_reuses_every_status_without_restart(self):
        with patch.object(agent, 'start', side_effect=self.no_dispatch):
            first = self.enqueue()
        for status in ('queued', 'paused', 'running', 'needs_review', 'blocked', 'inspection_done', 'done'):
            with self.subTest(status=status):
                with agent.LOCK, closing(agent.connect()) as c, c:
                    for result in first:
                        task = agent.owned(c, 1, result['task']['id'])
                        task.update(status=status)
                        agent.put(c, task)
                with patch.object(agent, 'start') as start:
                    repeated = self.enqueue()
                start.assert_not_called()
                self.assertEqual([x['status'] for x in repeated], ['reused', 'reused'])
                self.assertEqual([x['task']['id'] for x in first], [x['task']['id'] for x in repeated])

    def test_start_failure_keeps_durable_task_and_never_restarts_on_retry(self):
        with patch.object(agent, 'start', side_effect=RuntimeError('dispatch failure')):
            results = self.enqueue()
        self.assertTrue(all(o['task']['id'] and '启动未确认' in o['reason'] for o in results))
        with patch.object(agent, 'start') as start:
            results = self.enqueue()
        start.assert_not_called()
        self.assertTrue(all(o['status'] == 'reused' for o in results))

    def test_partial_create_failure_recovers_only_missing_task(self):
        original = agent.create
        def create(user, data, **kwargs):
            if data['productId'].endswith('B012345678'): raise RuntimeError('failure')
            return original(user, data, **kwargs)
        with patch.object(agent, 'create', side_effect=create), patch.object(agent, 'start', side_effect=self.no_dispatch):
            first = self.enqueue()
        self.assertEqual(first[0]['status'], 'error')
        self.assertEqual(first[1]['status'], 'created')
        with patch.object(agent, 'start', side_effect=self.no_dispatch) as start:
            second = self.enqueue()
        self.assertEqual([o['status'] for o in second], ['created', 'reused'])
        self.assertEqual(start.call_count, 1)

    def test_deleted_and_wrong_reference_not_overwritten(self):
        self.workspace['products'].pop()
        self.workspace['products'][0]['selectionResearch']['reference']['asin'] = 'B099999999'
        self.save_workspace()
        with patch.object(agent, 'start') as start:
            outcomes = self.enqueue()
        start.assert_not_called()
        self.assertEqual([o['status'] for o in outcomes], ['skipped', 'error'])
        self.assertEqual(agent.list_tasks(1), [])

    def test_validate_account_market_and_report_bounds(self):
        asins = [self.candidates[0]['asin']]
        profile, candidates = intake.validate(1, 'report', asins*2, self.profile['id'])
        self.assertEqual(len(candidates), 1)
        for user, report, selection, pid in [(2,'report',asins,self.profile['id']), (1,'missing',asins,self.profile['id']),
            (1,'report',[],self.profile['id']), (1,'report',[{}],self.profile['id']), (1,'report',['B099999999'],self.profile['id'])]:
            with self.subTest(user=user, report=report, selection=selection), self.assertRaises(ValueError):
                intake.validate(user, report, selection, pid)
        other = agent.save_profile(1, dict(name='UK',store='Other',marketplace='UK',shippingTemplate='FBM'))
        with self.assertRaises(ValueError): intake.validate(1, 'report', asins, other['id'])
        self.report['status'] = 'running'
        research.save(self.report)
        with patch.object(research, 'ACTIVE', {'report'}), self.assertRaises(ValueError):
            intake.validate(1, 'report', asins, self.profile['id'])


if __name__ == '__main__': unittest.main()
