import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import agent_center as agent


class WorkflowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        runtime = self.root / 'automation'
        runtime.mkdir()
        example = Path(__file__).resolve().parents[1] / 'automation/config.example.json'
        (runtime / 'config.json').write_bytes(example.read_bytes())
        self.enterContext(patch.dict(os.environ, {'JUNFEI_PROJECT_ROOT': str(self.root)}))
        self.workspace = {
            'products': [{'id': 'fixture', 'name': 'Synthetic test', 'market': 'US'}],
            'copy': {}, 'reviews': {},
        }
        self.patches = [
            patch.object(agent, 'DATA', self.root),
            patch.object(agent, 'DB', self.root / 'agent.sqlite3'),
            patch.object(agent, 'load_workspace', return_value=self.workspace),
            patch.object(agent, 'workspace_revision', return_value=None),
            patch.dict(agent.TOOLS, {step: (lambda t: {'ok': True})
                       for step in agent.STEPS if step != 'plan'}),
        ]
        for item in self.patches:
            item.start()
        agent.TOOLS['images'] = lambda t: {'ok': False, 'issues': ['fixture image gate']}
        self.profile = agent.save_profile(1, dict(
            name='Test', store='Test store', marketplace='US',
            shippingTemplate='Test shipping', quantity=1))
        self.task = agent.create(1, dict(
            goal='Synthetic recovery test', profileId=self.profile['id'],
            productId='fixture', taskMode='production', autoSourcing=False,
            aiPlanning=True, budgetCny=1))
        self.reply = {'summary': 'Synthetic plan',
                      'steps': [{'tool': 'facts', 'purpose': 'Check saved facts'}],
                      'missing': []}

    def tearDown(self):
        agent.ACTIVE.discard(self.task['id'])
        agent.RUN_TOKENS.pop(self.task['id'], None)
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def stored(self):
        with closing(agent.connect()) as c:
            return agent.owned(c, 1, self.task['id'])

    def edit(self, **fields):
        with agent.LOCK, closing(agent.connect()) as c, c:
            task = agent.owned(c, 1, self.task['id'])
            task.update(fields)
            agent.put(c, task)
        return task

    def start(self):
        with patch('agent_center.threading.Thread.start'):
            return agent.start(1, self.task['id'])

    def run_flow(self):
        self.start()
        agent.run(1, self.task['id'])
        return self.stored()

    def test_intent_committed_before_model_and_result_hidden_from_public_snapshot(self):
        def model(*args):
            attempt = self.stored()['planningAttempt']
            self.assertEqual(attempt['state'], 'started')
            self.assertTrue(attempt['externalEffectPossible'])
            self.assertEqual(attempt['step'], 'plan')
            return self.reply
        with patch('visual_studio.model_json', side_effect=model) as call:
            task = self.run_flow()
        call.assert_called_once()
        self.assertEqual(task['planningAttempt']['state'], 'saved')
        self.assertEqual(task['results']['plan'], task['planningResult'])
        self.assertNotIn('planningResult', agent.public(task))
        self.assertIsNone(task['paidSpendCny'])
        self.assertEqual(task['status'], 'blocked')
        self.assertNotIn('publish', task['results'])

    def test_timeout_reconciliation_cannot_resubmit_paid_plan(self):
        with patch('visual_studio.model_json', side_effect=TimeoutError('fixture')) as call:
            task = self.run_flow()
            self.assertEqual(task['status'], 'needs_review')
            self.assertEqual(task['cursor'], 0)
            with self.assertRaisesRegex(ValueError, '不自动重复调用'):
                agent.resume_after_review(1, task['id'], 'Checked service account')
            with self.assertRaises(ValueError):
                agent.start(1, task['id'])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(self.stored()['planningAttempt']['state'], 'started')

    def test_invalid_model_tool_cannot_be_retried_with_reconciliation_note(self):
        bad = {'summary': 'Unsafe plan', 'steps': [{'tool': 'shell', 'purpose': 'Run'}]}
        with patch('visual_studio.model_json', return_value=bad) as call:
            task = self.run_flow()
            with self.assertRaises(ValueError):
                agent.resume_after_review(1, task['id'], 'Retry requested')
        self.assertEqual(task['status'], 'needs_review')
        self.assertEqual(call.call_count, 1)

    def test_failed_intent_write_calls_no_provider(self):
        original = agent.put
        def fail(c, task):
            if task.get('planningAttempt', {}).get('state') == 'started':
                raise OSError('fixture intent write failure')
            return original(c, task)
        self.start()
        with patch.object(agent, 'put', side_effect=fail), patch('visual_studio.model_json') as call:
            agent.run(1, self.task['id'])
        call.assert_not_called()
        self.assertEqual(self.stored()['status'], 'needs_review')
        self.assertNotIn('planningAttempt', self.stored())

    def test_saved_result_survives_step_commit_failure_and_is_reused(self):
        original = agent.event
        def fail(c, task, kind, message, **extra):
            if kind == 'tool_finished' and extra.get('tool') == 'plan':
                raise OSError('fixture checkpoint-to-step crash')
            return original(c, task, kind, message, **extra)
        with patch('visual_studio.model_json', return_value=self.reply) as call:
            self.start()
            with patch.object(agent, 'event', side_effect=fail):
                agent.run(1, self.task['id'])
            task = self.stored()
            self.assertEqual(task['planningAttempt']['state'], 'saved')
            self.assertEqual(task['status'], 'needs_review')
            self.assertEqual(task['cursor'], 0)
            self.assertNotIn('plan', task['results'])
            agent.resume_after_review(1, task['id'], 'Verified saved planning receipt')
            task = self.run_flow()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(task['results']['plan']['summary'], 'Synthetic plan')
        self.assertEqual(task['status'], 'blocked')

    def make_saved_interruption(self):
        with patch('visual_studio.model_json', return_value=self.reply):
            self.start()
            agent.generate_task_plan(1, self.stored())
        self.edit(status='needs_review')
        agent.ACTIVE.discard(self.task['id'])
        agent.RUN_TOKENS.pop(self.task['id'], None)

    def test_changed_or_corrupt_checkpoint_stops_before_model(self):
        self.make_saved_interruption()
        task = self.stored()
        task['planningResult']['summary'] = 'Altered'
        self.edit(planningResult=task['planningResult'])
        with patch('visual_studio.model_json') as call:
            with self.assertRaisesRegex(ValueError, '校验失败'):
                agent.resume_after_review(1, task['id'], 'Resume')
        call.assert_not_called()

    def test_changed_request_cannot_reuse_saved_result(self):
        self.make_saved_interruption()
        self.edit(goal='Changed request')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            agent.resume_after_review(1, self.task['id'], 'Resume')

    def test_legacy_started_plan_is_not_replayed(self):
        self.edit(status='needs_review')
        with closing(agent.connect()) as c, c:
            agent.event(c, self.stored(), 'tool_started', 'Legacy plan', tool='plan')
        with patch('visual_studio.model_json') as call:
            with self.assertRaisesRegex(ValueError, '旧版AI规划'):
                agent.resume_after_review(1, self.task['id'], 'Resume legacy work')
        call.assert_not_called()

    def test_legacy_completed_plan_remains_usable(self):
        self.edit(status='needs_review', cursor=1, results={'plan': {'ok': True}})
        with patch('visual_studio.model_json') as call:
            agent.resume_after_review(1, self.task['id'], 'Checked prior completed stage')
            task = self.run_flow()
        call.assert_not_called()
        self.assertEqual(task['status'], 'blocked')
        self.assertEqual(task['results']['plan'], {'ok': True})

    def test_recheck_preserves_paid_receipt_and_repeats_only_free_checks(self):
        with patch('visual_studio.model_json', return_value=self.reply) as call:
            task = self.run_flow()
            attempt = task['planningAttempt'].copy()
            self.workspace['products'][0]['name'] = 'Updated synthetic facts'
            refreshed = agent.recheck(1, task['id'])
            self.assertEqual(refreshed['cursor'], 1)
            with patch.dict(agent.TOOLS, {'facts': lambda t: {'ok': True, 'fresh': True}}):
                done = self.run_flow()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(done['planningAttempt'], attempt)
        self.assertTrue(done['results']['facts']['fresh'])

    def test_return_after_state_change_saves_receipt_without_advancing(self):
        def model(*args):
            self.edit(status='needs_review', reason='State changed externally')
            return self.reply
        with patch('visual_studio.model_json', side_effect=model) as call:
            task = self.run_flow()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(task['status'], 'needs_review')
        self.assertEqual(task['reason'], 'State changed externally')
        self.assertEqual(task['cursor'], 0)
        self.assertEqual(task['planningAttempt']['state'], 'saved')
        self.assertNotIn('plan', task['results'])
        with patch('visual_studio.model_json') as call:
            agent.resume_after_review(1, task['id'], 'Verified returned saved receipt')
            self.run_flow()
        call.assert_not_called()

    def test_old_execution_cannot_overwrite_new_execution(self):
        def model(*args):
            self.edit(executionId='new-execution', status='queued', reason='New owner')
            return self.reply
        with patch('visual_studio.model_json', side_effect=model):
            task = self.run_flow()
        self.assertEqual(task['executionId'], 'new-execution')
        self.assertEqual(task['status'], 'queued')
        self.assertEqual(task['reason'], 'New owner')
        self.assertEqual(task['cursor'], 0)
        self.assertNotIn('plan', task['results'])

    def test_old_exception_cannot_overwrite_new_execution(self):
        def model(*args):
            self.edit(executionId='new-execution', status='queued', reason='New owner')
            raise TimeoutError('old response failed')
        with patch('visual_studio.model_json', side_effect=model):
            task = self.run_flow()
        self.assertEqual(task['status'], 'queued')
        self.assertEqual(task['reason'], 'New owner')

    def test_resume_cannot_start_while_local_worker_still_active(self):
        self.start()
        self.edit(status='needs_review')
        with self.assertRaisesRegex(ValueError, '仍在执行'):
            agent.resume_after_review(1, self.task['id'], 'Resume')

    def test_direct_runner_without_claim_does_nothing(self):
        with patch('visual_studio.model_json') as call:
            agent.run(1, self.task['id'])
        call.assert_not_called()
        self.assertEqual(self.stored()['status'], 'queued')

    def test_account_isolation_for_reconciliation(self):
        self.make_saved_interruption()
        with self.assertRaisesRegex(ValueError, '无权访问'):
            agent.resume_after_review(2, self.task['id'], 'Resume')
        self.assertEqual(self.stored()['status'], 'needs_review')

    def test_two_processes_claim_paid_planning_once(self):
        self.start()
        root = str(self.root)
        tid = self.task['id']
        code = """
import json, os, socket, time
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
socket.socket.connect = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('External IO disabled'))
import agent_center as agent
root=Path(os.environ['FIXTURE_ROOT'])
agent.DATA=root;agent.DB=root/'agent.sqlite3'
with closing(agent.connect()) as c:
    task=agent.owned(c,1,os.environ['FIXTURE_TASK'])
def model(*args):
    with (root/'model-calls').open('a',encoding='utf-8') as stream: stream.write('called\\n')
    time.sleep(0.3)
    return {'summary':'Fixture','steps':[{'tool':'facts','purpose':'Check'}],'missing':[]}
try:
    with patch('visual_studio.model_json',side_effect=model):
        result=agent.generate_task_plan(1,task)
    print(json.dumps({'saved':result['ok']}))
except ValueError:
    print(json.dumps({'stopped':True}))
"""
        env = dict(os.environ, FIXTURE_ROOT=root, FIXTURE_TASK=tid,
                   JUNFEI_ACCOUNT_DATA=root, JUNFEI_WORKER_USER='0')
        processes = [subprocess.Popen([sys.executable, '-B', '-c', code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=Path(__file__).resolve().parent,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for _ in range(2)]
        replies = []
        for child in processes:
            stdout, stderr = child.communicate(timeout=30)
            self.assertEqual(child.returncode, 0, stderr.decode('utf-8',errors='replace'))
            replies.append(json.loads(stdout.decode('utf-8')))
        self.assertEqual((self.root/'model-calls').read_text(encoding='utf-8').splitlines(), ['called'])
        self.assertTrue(any(item.get('saved') for item in replies))
        self.assertEqual(self.stored()['planningAttempt']['state'], 'saved')
