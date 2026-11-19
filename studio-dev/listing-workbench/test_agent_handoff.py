"""Offline handoff regression: temporary databases, no real providers or ERP."""
import json
import socket
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import agent_center as agent
import agent_handoff
import agent_research
import agent_selection


class AgentHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agent-handoff-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = {'freshnessBasis': 'seller_listing', 'windowDays': 7}
        self.patches = [
            patch.object(agent, 'DATA', self.root),
            patch.object(agent, 'DB', self.root / 'agent.sqlite3'),
            patch.object(agent, 'ACTIVE', set()),
            patch.object(agent, 'RUN_TOKENS', {}),
            patch('agent_selection.current_policy', side_effect=lambda: self.clone(self.policy)),
            patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden in offline tests')),
            patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden in offline tests')),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.no_external = {}
        for target in ('visual_studio.model_json', 'provider.generate_listing', 'competitors.analyse',
                       'agent_sourcing.collect', 'agent_center.sync_erp'):
            item = patch(target, side_effect=AssertionError('External operation forbidden: ' + target))
            self.no_external[target] = item.start()
            self.addCleanup(item.stop)
        self.forbidden_tools = {name: Mock(side_effect=AssertionError('Out of scope: ' + name))
                                for name in ('images', 'export', 'junfeiPreflight', 'verify')}
        item = patch.dict(agent.TOOLS, self.forbidden_tools)
        item.start()
        self.addCleanup(item.stop)
        self.pid = 'IMP-US-B012345678'
        self.product = self.valid_product()
        self.listing = {'title': 'Cotton storage pouch', 'bullets': 'one\ntwo\nthree\nfour\nfive',
                        'description': 'A cotton storage pouch.', 'terms': 'cotton storage pouch'}
        self.workspace = {'products': [self.product], 'copy': {}, 'reviews': {}}
        self.save_workspace(7)
        self.profile = agent.save_profile(1, {
            'name': 'Offline draft shop', 'store': 'Offline Store', 'marketplace': 'US',
            'shippingTemplate': 'Fixture FBM', 'mode': 'draft',
        })
        created = agent.create(1, {
            'goal': 'Offline selected candidate handoff test', 'taskMode': 'production',
            'profileId': self.profile['id'], 'productId': self.pid,
            'autoResearch': False, 'autoListing': False, 'aiPlanning': False,
        }, intake={'source': 'selection-report', 'reportId': 'offline-report', 'asin': 'B012345678'})
        self.tid = created['id']
        self.mutate_task(status='blocked', cursor=2,
                         results={'plan': {'ok': True, 'summary': 'Original fixed plan'},
                                  'facts': {'ok': False, 'issues': ['Historical missing evidence']}})
        self.original = self.stored()
        self.assertTrue(agent.inspect_facts(self.original)['ok'], 'The fixture must pass real facts gates')

    @staticmethod
    def clone(value):
        return json.loads(json.dumps(value))

    def valid_product(self):
        today = date.today().isoformat()
        def source(raw='Offline fixture observation'):
            return {'url': 'https://www.sellersprite.com/', 'checkedAt': today, 'raw': raw}
        evidence = {
            'asin': 'B012345678', 'marketplace': 'US', 'sellerId': 'offline-seller',
            'sellerCountry': 'CN', 'sellerCountrySource': source(),
            'fulfillment': 'FBM', 'fulfillmentSource': source(),
            'collectionDate': today, 'sellerListedDate': today,
            'freshnessScope': 'seller_listing', 'freshnessSource': source(),
            'frontSearch': dict(source(), url='https://www.amazon.com/s?k=cotton+pouch', status='opened'),
            'matchedAsin': 'B087654321', 'match': 'strong', 'matchSource': source(),
            'matchedRank': dict(source('Sales rank: 1,234'),
                                source='SellerSprite same-product search',
                                asin='B087654321', value=1234),
            'ipChecks': {key: dict(source(), status='clear', query='Offline fixture query',
                                   judgment='Offline test evidence only') for key in agent_selection.IP_CHECKS},
            'dailyQuotaLedgerVerified': True, 'dailyQuotaSource': source(),
        }
        return {
            'id': self.pid, 'name': 'Cotton storage pouch', 'market': 'US',
            'sourceUrl': 'https://detail.1688.com/offer/123456789012.html',
            'material': 'cotton', 'dimensions': '10cm', 'packageContents': '1 pouch',
            'colorNames': 'Black', 'sizeNames': 'M', 'packageWeight': '100g',
            'masterColor': 'Black', 'supplierColorReferences': [{'url': 'offline-reference.png', 'color': 'Black'}],
            'selectionResearch': {'reference': {'asin': 'B012345678', 'market': 'US'}},
            'selectionEvidence': evidence,
            'competitorResearch': {'US': {
                'sources': [{'status': 'ok', 'asin': 'B087654321'}],
                'keywords': [{'phrase': 'cotton pouch', 'selected': True}],
            }},
        }

    def save_workspace(self, revision=7):
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as c, c:
            c.execute('CREATE TABLE IF NOT EXISTS workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            c.execute('INSERT OR REPLACE INTO workspace VALUES(1,?,?)',
                      (revision, json.dumps(self.workspace)))

    def stored(self):
        with closing(agent.connect()) as c:
            return self.clone(agent.owned(c, 1, self.tid))

    def mutate_task(self, **updates):
        with closing(agent.connect()) as c, c:
            task = agent.owned(c, 1, self.tid)
            task.update(updates)
            agent.put(c, task)
        return self.stored()

    def restore_original(self):
        with closing(agent.connect()) as c, c:
            agent.put(c, self.clone(self.original))

    def data(self, **updates):
        value = {'budgetCny': 10, 'confirmPaidText': True, 'acknowledgeBudgetNotHardCap': True,
                 'researchAsins': '', 'workspaceRevision': 7}
        value.update(updates)
        return value

    def prepare(self, data=None, user=1):
        # Enabling the feature must not dispatch a worker or perform paid work.
        with patch.object(agent, 'start', side_effect=AssertionError('Handoff must not start a task')) as start, \
                patch('agent_center.threading.Thread.start',
                      side_effect=AssertionError('Handoff must not start a thread')) as thread:
            result = agent.prepare_copy_handoff(user, self.tid, self.data() if data is None else data)
            start.assert_not_called()
            thread.assert_not_called()
        for mocked in self.no_external.values():
            mocked.assert_not_called()
        for mocked in self.forbidden_tools.values():
            mocked.assert_not_called()
        return result

    def assert_rejected_unchanged(self, data=None, user=1):
        before = self.stored()
        with self.assertRaises(ValueError):
            self.prepare(data, user=user)
        self.assertEqual(self.stored(), before, 'A denied handoff must not mutate the task')

    def run_sync(self):
        with patch('agent_center.threading.Thread.start'):
            agent.start(1, self.tid)
        agent.run(1, self.tid)
        return self.stored()

    def assert_scope_preserved(self, task):
        self.assertEqual(task['executionScope'], agent_handoff.SCOPE)
        self.assertEqual(task['status'], 'blocked')
        self.assertFalse(task.get('exportAvailable'))
        self.assertTrue(task['reason'])
        for name in ('images', 'export', 'junfeiPreflight', 'publish', 'verify'):
            self.assertNotIn(name, task['results'])
        for mocked in self.forbidden_tools.values():
            mocked.assert_not_called()
        self.no_external['agent_center.sync_erp'].assert_not_called()
        self.no_external['agent_sourcing.collect'].assert_not_called()

    def test_handoff_is_local_and_archives_latest_evidence_without_resetting_attempts(self):
        sourcing = {'state': 'saved', 'sha256': 'offline-source', 'applied': True}
        self.mutate_task(sourcingAttempt=sourcing)
        before = self.stored()
        self.product['material'] = 'verified cotton'
        self.save_workspace(8)
        self.policy['windowDays'] = 14
        result = self.prepare(self.data(workspaceRevision=8))
        task = self.stored()
        self.assertEqual(result['id'], self.tid)
        self.assertNotIn('snapshot', result)
        self.assertEqual(task['status'], 'queued')
        self.assertEqual(task['cursor'], 1)
        self.assertEqual(task['executionScope'], 'selection_to_copy')
        self.assertTrue(task['autoResearch'])
        self.assertTrue(task['autoListing'])
        self.assertFalse(task['autoSourcing'])
        self.assertFalse(task['aiPlanning'])
        self.assertEqual(task['sourcingAttempt'], sourcing)
        self.assertEqual(task['snapshot']['product']['material'], 'verified cotton')
        self.assertEqual(task['snapshot']['product']['selectionEvidence'], self.product['selectionEvidence'])
        self.assertEqual(task['selectionPolicy'], self.policy)
        self.assertEqual(task['workspaceRevision'], 8)
        self.assertEqual(task['results'], {'plan': before['results']['plan']})
        archived = task['revisions'][-1]
        for key in ('snapshot', 'results', 'selectionPolicy', 'autoResearch', 'autoListing', 'autoSourcing'):
            self.assertEqual(archived[key], before[key])
        self.assertEqual(task['copyHandoff']['budgetEnforcement'], 'record_only_not_hard_cap')
        self.assertEqual(agent.load_workspace(), self.workspace)
        self.assertEqual(len(agent.list_tasks(1)), 1)

    def test_missing_confirmation_and_non_literal_booleans_are_rejected(self):
        for key in ('confirmPaidText', 'acknowledgeBudgetNotHardCap'):
            for value in (None, False, 1, 'true'):
                with self.subTest(key=key, value=value):
                    self.assert_rejected_unchanged(self.data(**{key: value}))
            data = self.data()
            del data[key]
            self.assert_rejected_unchanged(data)
        self.assert_rejected_unchanged([])

    def test_invalid_budgets_are_rejected(self):
        for value in (None, 0, -1, True, False, '10', float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value):
                self.assert_rejected_unchanged(self.data(budgetCny=value))

    def test_research_asins_are_validated_and_normalized(self):
        for value in ([], 1, 'BAD', 'B000000001 B000000002 B000000003 B000000004 B000000005 B000000006'):
            with self.subTest(value=value):
                self.assert_rejected_unchanged(self.data(researchAsins=value))
        self.prepare(self.data(researchAsins='b087654321, B087654321; B011111111'))
        self.assertEqual(self.stored()['researchAsins'], ['B087654321', 'B011111111'])

    def test_account_and_task_state_are_checked(self):
        self.assert_rejected_unchanged(user=2)
        for status in ('queued', 'paused', 'running', 'needs_review', 'inspection_done', 'done'):
            with self.subTest(status=status):
                self.restore_original()
                self.mutate_task(status=status)
                self.assert_rejected_unchanged()
        self.restore_original()
        agent.ACTIVE.add(self.tid)
        self.assert_rejected_unchanged()
        agent.ACTIVE.discard(self.tid)

    def test_only_selection_intake_production_and_draft_profile_can_handoff(self):
        for update in ({'taskMode': 'inspect'}, {'intake': {}},
                       {'intake': {'source': 'other', 'asin': 'B012345678'}},
                       {'profile': dict(self.profile, mode='publish')}):
            with self.subTest(update=update):
                self.restore_original()
                self.mutate_task(**update)
                self.assert_rejected_unchanged()

    def test_changed_candidate_identity_market_and_missing_product_are_rejected(self):
        pristine = self.clone(self.workspace)
        for target, value in (('asin', 'B099999999'), ('referenceMarket', 'UK'), ('market', 'UK'),
                              ('missingProduct', True)):
            with self.subTest(target=target):
                self.workspace = self.clone(pristine)
                p = self.workspace['products'][0]
                if target == 'asin':
                    p['selectionResearch']['reference']['asin'] = value
                elif target == 'referenceMarket':
                    p['selectionResearch']['reference']['market'] = value
                elif target == 'market':
                    p['market'] = value
                else:
                    self.workspace['products'] = []
                self.save_workspace()
                self.assert_rejected_unchanged()

    def test_real_facts_and_selection_failures_cannot_be_authorized(self):
        pristine = self.clone(self.workspace)
        for change in ('material', 'weight', 'rank', 'missingEvidence'):
            with self.subTest(change=change):
                self.workspace = self.clone(pristine)
                product = self.workspace['products'][0]
                if change == 'material':
                    product['material'] = ''
                elif change == 'weight':
                    product['packageWeight'] = ''
                elif change == 'rank':
                    product['selectionEvidence']['matchedRank']['value'] = None
                else:
                    product.pop('selectionEvidence')
                self.save_workspace()
                self.assert_rejected_unchanged()

    def test_skipped_selection_is_rejected_even_when_facts_report_ok(self):
        with patch.object(agent, 'inspect_facts', return_value={
                'ok': True, 'selection': {'ok': True, 'skipped': True}, 'issues': []}):
            self.assert_rejected_unchanged()

    def test_revision_is_required_exact_and_rechecked_before_commit(self):
        for value in (None, True, '7', 6, 8):
            with self.subTest(value=value):
                self.assert_rejected_unchanged(self.data(workspaceRevision=value))
        with patch.object(agent, 'workspace_revision', side_effect=[7, 8]):
            self.assert_rejected_unchanged()
        self.assertNotIn('copyHandoff', self.stored())

    def test_missing_revision_context_is_supported_without_fabricated_revision(self):
        with patch.object(agent, 'workspace_revision', return_value=None):
            self.prepare(self.data(workspaceRevision=None))
        self.assertEqual(self.stored()['status'], 'queued')

    def test_any_prior_research_or_listing_attempt_blocks_new_handoff(self):
        for key in ('researchAttempt', 'listingAttempt'):
            for attempt in ({}, {'state': 'started'}, {'state': 'saved', 'sha256': 'offline'}):
                with self.subTest(key=key, attempt=attempt):
                    self.restore_original()
                    self.mutate_task(**{key: attempt})
                    self.assert_rejected_unchanged()

    def test_uncertain_planning_and_sourcing_attempts_are_preserved_and_rejected(self):
        for key in ('planningAttempt', 'sourcingAttempt'):
            for attempt in ({}, {'state': 'started', 'at': 123}, {'state': 'unknown', 'at': 123}):
                with self.subTest(key=key, attempt=attempt):
                    self.restore_original()
                    self.mutate_task(**{key: attempt})
                    self.assert_rejected_unchanged()

    def test_unconfirmed_ai_plan_cannot_be_skipped(self):
        self.mutate_task(aiPlanning=True, results={'facts': {'ok': False}})
        self.assert_rejected_unchanged()

    def test_existing_export_preflight_erp_and_verification_records_are_rejected(self):
        for key in ('export', 'junfeiPreflight', 'publish', 'verify'):
            with self.subTest(result=key):
                self.restore_original()
                self.mutate_task(results=dict(self.original['results'], **{key: {}}))
                self.assert_rejected_unchanged()
        for update in ({'exportAvailable': True}, {'junfeiPlanAvailable': True},
                       {'erpObservation': {}}, {'erpObservation': {'observedAt': 'offline'}}):
            with self.subTest(update=update):
                self.restore_original()
                self.mutate_task(**update)
                self.assert_rejected_unchanged()

    def test_failed_audit_write_rolls_back_the_entire_handoff(self):
        before = self.stored()
        with patch.object(agent, 'event', side_effect=RuntimeError('Offline audit disk failure')):
            with self.assertRaises(RuntimeError):
                self.prepare()
        self.assertEqual(self.stored(), before)
        self.assertEqual(agent.load_workspace(), self.workspace)

    def test_mock_generation_timeout_remains_uncertain_and_cannot_be_reauthorized(self):
        self.prepare()
        with patch('provider.settings_public', return_value={'hasKey': True}), \
                patch('provider.generate_listing', side_effect=TimeoutError('Offline simulated timeout')) as generate:
            first = self.run_sync()
            self.assertEqual(first['status'], 'needs_review')
            self.assertEqual(first['listingAttempt']['state'], 'started')
            self.assertFalse(first.get('listingDraftAvailable'))
            with self.assertRaises(ValueError):
                agent.recheck(1, self.tid)
            replay = self.prepare()
            self.assertEqual(replay['status'], 'needs_review')
            self.assertEqual(self.stored()['listingAttempt'], first['listingAttempt'])
            with self.assertRaises(ValueError):
                agent.start(1, self.tid)
            self.assertEqual(generate.call_count, 1)
        for mocked in self.forbidden_tools.values():
            mocked.assert_not_called()

    def test_identical_replay_is_idempotent_after_execution_records_exist(self):
        first = self.prepare()
        self.mutate_task(status='needs_review', cursor=3,
                         researchAttempt={'state': 'saved', 'sha256': 'offline'},
                         listingAttempt={'state': 'started', 'at': 123})
        before = self.stored()
        replay = self.prepare()
        self.assertEqual(replay['id'], first['id'])
        self.assertEqual(self.stored(), before)
        events = agent.detail(1, self.tid)['events']
        self.assertEqual(sum(e.get('kind') == 'copy_handoff_prepared' for e in events), 1)
        self.assert_rejected_unchanged(self.data(budgetCny=11))
        self.assert_rejected_unchanged(self.data(researchAsins='B087654321'))

    def test_existing_approved_copy_stops_at_listing_and_never_dispatches_images(self):
        self.workspace['copy'][self.pid + '-US'] = self.listing
        self.workspace['reviews'][self.pid] = {'copy': True, 'images': True}
        self.save_workspace()
        self.prepare()
        result = self.run_sync()
        self.assertTrue(result['results']['listing']['ok'])
        self.assert_scope_preserved(result)
        self.no_external['provider.generate_listing'].assert_not_called()
        self.no_external['competitors.analyse'].assert_not_called()

    def test_persisted_cursor_at_any_forbidden_stage_stops_before_tool_dispatch(self):
        self.prepare()
        configured = self.stored()
        # Includes cursor == len(STEPS), which must not leave a scoped task running.
        for cursor in range(agent.STEPS.index('images'), len(agent.STEPS) + 1):
            with self.subTest(cursor=cursor):
                with closing(agent.connect()) as c, c:
                    task = self.clone(configured)
                    task.update(cursor=cursor, status='queued')
                    agent.put(c, task)
                result = self.run_sync()
                self.assert_scope_preserved(result)
        self.no_external['provider.generate_listing'].assert_not_called()

    def test_unknown_execution_scope_requires_review_before_any_tool_is_dispatched(self):
        self.prepare()
        self.mutate_task(executionScope='unknown_untrusted_scope', cursor=1)
        before_events = len(agent.detail(1, self.tid)['events'])
        forbidden = {name: Mock(side_effect=AssertionError('Unexpected dispatch: ' + name))
                     for name in agent.STEPS}
        with patch.dict(agent.TOOLS, forbidden):
            result = self.run_sync()
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['cursor'], 1)
        self.assertTrue(result['reason'])
        for mocked in forbidden.values():
            mocked.assert_not_called()
        for mocked in self.no_external.values():
            mocked.assert_not_called()
        new_events = agent.detail(1, self.tid)['events'][before_events:]
        self.assertFalse(any(event.get('kind') == 'tool_started' for event in new_events))

    def test_negative_and_non_integer_cursors_require_review_without_dispatch(self):
        self.prepare()
        configured = self.stored()
        for cursor in (-1, -20, True, 1.5, '1', None):
            with self.subTest(cursor=cursor):
                with closing(agent.connect()) as c, c:
                    task = self.clone(configured)
                    task.update(cursor=cursor, status='queued')
                    agent.put(c, task)
                before_events = len(agent.detail(1, self.tid)['events'])
                forbidden = {name: Mock(side_effect=AssertionError('Unexpected dispatch: ' + name))
                             for name in agent.STEPS}
                with patch.dict(agent.TOOLS, forbidden):
                    result = self.run_sync()
                self.assertEqual(result['status'], 'needs_review')
                self.assertEqual(result['cursor'], cursor)
                self.assertTrue(result['reason'])
                for mocked in forbidden.values():
                    mocked.assert_not_called()
                for mocked in self.no_external.values():
                    mocked.assert_not_called()
                new_events = agent.detail(1, self.tid)['events'][before_events:]
                self.assertFalse(any(event.get('kind') == 'tool_started' for event in new_events))

    def test_scoped_recheck_rejects_removed_or_replaced_candidate_identity_atomically(self):
        self.prepare()
        self.mutate_task(status='blocked', cursor=4)
        configured = self.stored()
        pristine = self.clone(self.workspace)
        for change in ('removeSelectionResearch', 'replaceAsin', 'replaceReferenceMarket'):
            with self.subTest(change=change):
                with closing(agent.connect()) as c, c:
                    agent.put(c, self.clone(configured))
                self.workspace = self.clone(pristine)
                product = self.workspace['products'][0]
                if change == 'removeSelectionResearch':
                    product.pop('selectionResearch')
                elif change == 'replaceAsin':
                    product['selectionResearch']['reference']['asin'] = 'B099999999'
                else:
                    product['selectionResearch']['reference']['market'] = 'UK'
                self.save_workspace(8)
                before = self.stored()
                before_events = agent.detail(1, self.tid)['events']
                with self.assertRaises(ValueError):
                    agent.recheck(1, self.tid)
                self.assertEqual(self.stored(), before)
                self.assertEqual(agent.detail(1, self.tid)['events'], before_events)
                for mocked in self.no_external.values():
                    mocked.assert_not_called()

    def test_scoped_queued_and_resumed_tasks_reject_missing_identity_or_skipped_selection(self):
        self.prepare()
        configured = self.stored()
        pristine = self.clone(self.workspace)
        for state in ('queued', 'paused'):
            for step in ('research', 'listing'):
                for change in ('missingIdentity', 'skippedSelection'):
                    with self.subTest(state=state, step=step, change=change):
                        self.workspace = self.clone(pristine)
                        task = self.clone(configured)
                        if change == 'missingIdentity':
                            self.workspace['products'][0].pop('selectionResearch')
                        self.save_workspace()
                        task['snapshot'] = agent_research.snapshot(self.workspace, task)
                        task.update(status=state, cursor=agent.STEPS.index(step),
                                    results={'plan': {'ok': True},
                                             'facts': {'ok': True, 'selection': {'ok': True}},
                                             'research': {'ok': True}})
                        with closing(agent.connect()) as c, c:
                            agent.put(c, task)
                        with ExitStack() as stack:
                            research = stack.enter_context(patch('agent_research.collect',
                                                                  return_value={'ok': True}))
                            listing = stack.enter_context(patch.object(agent, 'generate_task_listing',
                                                                        return_value={'ok': False, 'issues': ['Should not run']}))
                            if change == 'skippedSelection':
                                stack.enter_context(patch.object(agent, 'inspect_facts', return_value={
                                    'ok': True, 'selection': {'ok': True, 'skipped': True}, 'issues': []}))
                            result = self.run_sync()
                            research.assert_not_called()
                            listing.assert_not_called()
                        self.assert_scope_preserved(result)
                        self.assertNotIn('researchAttempt', result)
                        self.assertNotIn('listingAttempt', result)
                        for mocked in self.no_external.values():
                            mocked.assert_not_called()

    def test_workspace_change_between_stages_blocks_the_next_paid_dispatch(self):
        self.prepare()
        configured = self.stored()
        pristine = self.clone(self.workspace)
        original_facts = agent.TOOLS['facts']
        original_collect = agent_research.collect
        for next_step in ('research', 'listing'):
            with self.subTest(next_step=next_step):
                self.workspace = self.clone(pristine)
                self.save_workspace()
                with closing(agent.connect()) as c, c:
                    agent.put(c, self.clone(configured))

                def change_workspace():
                    self.workspace['products'][0]['material'] = 'Changed after completed prior check'
                    self.save_workspace(8)

                def facts_then_change(task):
                    result = original_facts(task)
                    self.assertTrue(result['ok'])
                    change_workspace()
                    return result

                def research_then_change(user, task):
                    result = original_collect(user, task)
                    self.assertTrue(result['ok'])
                    change_workspace()
                    return result

                with ExitStack() as stack:
                    listing = stack.enter_context(patch.object(agent, 'generate_task_listing',
                                                                return_value={'ok': False, 'issues': ['Should not run']}))
                    if next_step == 'research':
                        stack.enter_context(patch.dict(agent.TOOLS, {'facts': facts_then_change}))
                        research = stack.enter_context(patch('agent_research.collect',
                                                              return_value={'ok': True}))
                    else:
                        research = stack.enter_context(patch('agent_research.collect',
                                                              side_effect=research_then_change))
                    result = self.run_sync()
                    listing.assert_not_called()
                    if next_step == 'research':
                        research.assert_not_called()
                    else:
                        research.assert_called_once()
                self.assert_scope_preserved(result)
                self.assertNotIn('researchAttempt', result)
                self.assertNotIn('listingAttempt', result)
                self.assertNotEqual(agent.load_workspace()['products'][0]['material'],
                                    result['snapshot']['product']['material'])
                for mocked in self.no_external.values():
                    mocked.assert_not_called()

    def test_free_recheck_preserves_scope_and_does_not_reenable_sourcing(self):
        self.prepare()
        self.mutate_task(status='blocked', cursor=4,
                         results={'plan': {'ok': True}, 'facts': {'ok': True},
                                  'research': {'ok': True}, 'listing': {'ok': False}},
                         listingAttempt={'state': 'saved', 'sha256': 'offline'},
                         listingDraftAvailable=True)
        before = self.stored()
        agent.recheck(1, self.tid)
        task = self.stored()
        self.assertEqual(task['executionScope'], 'selection_to_copy')
        self.assertEqual(task['copyHandoff'], before['copyHandoff'])
        self.assertEqual(task['listingAttempt'], before['listingAttempt'])
        self.assertFalse(task['autoSourcing'])
        self.assertEqual(task['status'], 'queued')
        self.assertEqual(task['cursor'], 1)
        for mocked in self.no_external.values():
            mocked.assert_not_called()

    def test_mock_listing_is_saved_once_and_requires_adoption_and_review(self):
        self.prepare()
        with patch('provider.settings_public', return_value={'hasKey': True}), \
                patch('provider.generate_listing', return_value={'copy': self.listing,
                                                               'model': 'offline-model'}) as generate:
            first = self.run_sync()
            self.assert_scope_preserved(first)
            self.assertTrue(first['listingDraftAvailable'])
            self.assertEqual(first['listingAttempt']['state'], 'saved')
            self.assertEqual(agent.load_workspace()['copy'], {})
            self.assertEqual(agent.listing_draft(1, self.tid)['title'], self.listing['title'])
            agent.recheck(1, self.tid)
            second = self.run_sync()
            self.assert_scope_preserved(second)
            self.assertEqual(generate.call_count, 1)
            adopted = agent.adopt_listing(1, self.tid)
            self.assertFalse(adopted['state']['reviews'][self.pid]['copy'])
            agent.recheck(1, self.tid)
            third = self.run_sync()
            self.assert_scope_preserved(third)
            self.assertEqual(generate.call_count, 1)
            self.assertFalse(third['results']['listing']['ok'])

    def test_mock_research_then_listing_uses_durable_report_and_still_stops_for_review(self):
        self.product.pop('competitorResearch')
        self.save_workspace()
        self.prepare(self.data(researchAsins='B087654321'))
        report = {'market': 'US', 'sources': [{'status': 'ok', 'asin': 'B087654321'}],
                  'keywords': [{'phrase': 'cotton pouch', 'selected': True}],
                  'model': 'offline-model', 'usage': {'prompt_tokens': 5, 'completion_tokens': 7}}
        with patch('provider.settings_public', return_value={'hasKey': True}), \
                patch('sellersprite.public', return_value={'hasKey': True}), \
                patch('competitors.analyse', return_value=report) as analyse, \
                patch('provider.generate_listing', return_value={'copy': self.listing}) as generate:
            first = self.run_sync()
            self.assert_scope_preserved(first)
            self.assertTrue(first['researchReportAvailable'])
            self.assertTrue(first['listingDraftAvailable'])
            self.assertEqual(first['researchAttempt']['state'], 'saved')
            self.assertIn('competitorResearch', generate.call_args.args[0])
            agent.recheck(1, self.tid)
            self.assert_scope_preserved(self.run_sync())
            self.assertEqual(analyse.call_count, 1)
            self.assertEqual(generate.call_count, 1)


if __name__ == '__main__':
    unittest.main()
