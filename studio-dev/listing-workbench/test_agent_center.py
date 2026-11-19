import io
import json
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import agent_center as agent
import agent_research


class AgentCenterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(agent, 'DATA', self.root), patch.object(agent, 'DB', self.root / 'agent.sqlite3')]
        for p in self.patches: p.start()
        self.product = dict(id='p1', name='真实产品测试夹具', market='US', sourceUrl='https://example.com/item', material='cotton',
                            dimensions='10cm', packageContents='1 item', colorNames='Black', sizeNames='M', packageWeight='100g',
                            masterColor='Black', supplierColorReferences=[{'url': 'reference.png', 'color': 'Black'}],
                            competitorResearch={'US': {'sources': [{'status': 'ok'}], 'keywords': [{'phrase': 'cotton item', 'selected': True}]}})
        self.listing = dict(title='Test product', bullets='one\ntwo\nthree\nfour\nfive', description='Test description', terms='cotton item')
        self.workspace = {'products': [self.product], 'copy': {'p1-US': self.listing}, 'reviews': {'p1': {'copy': True, 'images': True}}}
        self.workspace_patch = patch.object(agent, 'load_workspace', side_effect=lambda: json.loads(json.dumps(self.workspace)))
        self.workspace_patch.start()
        self.profile = agent.save_profile(1, dict(name='US店铺', store='Store A', marketplace='US', shippingTemplate='FBM', quantity=88))

    def tearDown(self):
        self.workspace_patch.stop()
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def create(self, **extra):
        if any(extra.get(key) is True for key in ('aiPlanning', 'autoResearch', 'autoListing')):
            extra.setdefault('budgetCny', 5)
        return agent.create(1, dict(goal='检查并制作', profileId=self.profile['id'], productId='p1', **extra))

    def run_sync(self, task):
        # Suppress thread dispatch to exercise the same persisted runner synchronously.
        with patch('agent_center.threading.Thread.start'):
            agent.start(1, task['id'])
        agent.run(1, task['id'])
        return agent.detail(1, task['id'])

    def historical_library_task(self):
        """An existing pre-migration record, rather than the disabled create API."""
        created=self.create(taskMode='production',autoSourcing=False)
        with closing(agent.connect()) as c,c:
            task=agent.owned(c,1,created['id'])
            task['libraryDraftOnly']=True
            task.pop('legacyERPDisabled',None)
            agent.put(c,task)
        return agent.public(task)

    def all_images(self):
        return {'sets': {'gallery': {'_projectId': 'master', 'images': [
            {'final_url': 'image', '_status': 'approved', 'human_reviewed': True, 'render_qa': {'ready': True}} for _ in range(7)]}}}

    def test_date_policy_refresh_archives_old_policy_without_changing_snapshot_shape(self):
        old = {'freshnessBasis': 'seller_listing'}
        new = {'freshnessBasis': 'sellersprite_product_listing', 'windowDays': 7}
        with patch('agent_selection.current_policy', return_value=old):
            task = self.create()
        self.assertEqual(agent.detail(1, task['id'])['selectionPolicy'], old)
        self.run_sync(task)
        with patch('agent_selection.current_policy', return_value=new):
            agent.recheck(1, task['id'])
        current = agent.detail(1, task['id'])
        self.assertEqual(current['selectionPolicy'], new)
        self.assertEqual(set(current['snapshot']), {'product', 'listing', 'review'})
        with closing(agent.connect()) as c:
            saved = agent.owned(c, 1, task['id'])
        self.assertEqual(saved['revisions'][-1]['selectionPolicy'], old)

    def test_ownership_and_profile_isolation(self):
        self.assertEqual(agent.profiles(2), [])
        task = self.create()
        for method in (agent.detail, agent.start, agent.pause, agent.download):
            with self.assertRaises(ValueError): method(2, task['id'])
        self.assertEqual(agent.overview(2)['tasks'], [])

    def test_erp_routes_only_exact_current_snapshot_and_explicit_library_binding(self):
        task=agent.detail(1,self.create()['id'])
        import agent_erp,agent_library
        with patch.object(agent_erp,'binding',side_effect=ValueError('no existing draft')), \
                patch.object(agent_library,'binding',return_value=({},{})), \
                patch.object(agent_library,'sync_library',return_value={'ok':False,'librarySaved':True}) as execute:
            self.assertTrue(agent.sync_erp(1,task)['librarySaved']);execute.assert_called_once_with(1,task)
            self.workspace['products'][0]['material']='changed after snapshot'
            with self.assertRaisesRegex(ValueError,'旧快照'):agent.sync_erp(1,task)
            self.assertEqual(execute.call_count,1)

    def test_library_only_waits_for_explicit_save_and_stops_at_verified_receipt(self):
        task = self.historical_library_task()
        with patch.dict(agent.TOOLS, {step: lambda task: {'ok': True} for step in agent.STEPS}), \
                patch('agent_library.package_for'), \
                patch('agent_library.sync_library', return_value={
                    'librarySaved': True, 'published': False, 'libraryId': '123'}) as save, \
                patch.object(agent, 'sync_erp') as old_erp:
            ready = self.run_sync(task)
            self.assertEqual(ready['status'], 'library_ready')
            save.assert_not_called()
            with self.assertRaises(ValueError):
                agent.start(1, task['id'])
            with self.assertRaises(ValueError):
                agent.start(2, task['id'], save_library=True)
            self.workspace['products'][0]['material'] = 'changed'
            with self.assertRaisesRegex(ValueError, '旧快照'):
                agent.start(1, task['id'], save_library=True)
            self.workspace['products'][0]['material'] = 'cotton'
            with patch('agent_center.threading.Thread.start'):
                agent.start(1, task['id'], save_library=True)
                with self.assertRaises(ValueError):
                    agent.start(1, task['id'], save_library=True)
            agent.run(1, task['id'], save_library=True)
            saved = agent.detail(1, task['id'])
            self.assertEqual(saved['status'], 'done')
            self.assertEqual(saved['results']['publish']['libraryId'], '123')
            self.assertNotIn('verify', saved['results'])
            save.assert_called_once()
            old_erp.assert_not_called()

    def test_library_only_unknown_save_cannot_be_requeued(self):
        task = self.historical_library_task()
        with patch.dict(agent.TOOLS, {step: lambda task: {'ok': True} for step in agent.STEPS}), \
                patch('agent_library.package_for'), patch('agent_library.sync_library', return_value={}):
            self.run_sync(task)
            with patch('agent_center.threading.Thread.start'):
                agent.start(1, task['id'], save_library=True)
            agent.run(1, task['id'], save_library=True)
        self.assertEqual(agent.detail(1, task['id'])['status'], 'needs_review')
        with self.assertRaisesRegex(ValueError, '不能从此处重发'):
            agent.resume_after_review(1, task['id'], '已检查')
        with self.assertRaises(ValueError):
            agent.start(1, task['id'], save_library=True)

    def test_erp_missing_bindings_cannot_fall_through_to_new_library_creation(self):
        task=agent.detail(1,self.create()['id'])
        import agent_erp,agent_library
        with patch.object(agent_erp,'binding',side_effect=ValueError('no draft')), \
                patch.object(agent_library,'binding',side_effect=ValueError('no library')), \
                patch.object(agent_library,'sync_library') as execute:
            self.assertFalse(agent.sync_erp(1,task)['ok']);execute.assert_not_called()

    def test_listing_inspection_blocks_supplier_and_third_party_marks(self):
        task = agent.detail(1, self.create()['id'])
        task['snapshot']['product'].update(
            brand='Generic', brandExclusions=['3M'],
            sourceImport={'supplier': {'attributes': {'品牌': '祥亚'}}})
        task['snapshot']['listing']['description'] += ' with 3M adhesive from 祥亚'
        result = agent.inspect_listing(task)
        self.assertFalse(result['ok'])
        self.assertTrue(any('3M' in issue and '祥亚' in issue for issue in result['issues']))

    def test_unverified_market_candidate_blocks_paid_research(self):
        self.product['selectionResearch'] = {'reference': {'asin': 'B012345678'}}
        task = self.create(taskMode='production', autoResearch=True, researchAsins='B012345678')
        with patch.object(agent_research, 'collect') as collect:
            result = self.run_sync(task)
        collect.assert_not_called()
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['results']['facts']['selection']['ok'])
        self.assertTrue(any('月度市场候选' in s for s in result['results']['facts']['issues']))

    def test_partial_supplier_variants_block_paid_research_before_invocation(self):
        self.product.update(sourceUrl='https://detail.1688.com/offer/123.html',
            sourceImport={'amazon': {'variants': [
                {'asin':'A1','color_name':'Black','size_name':'M'},
                {'asin':'A2','color_name':'Brown','size_name':'5X-Large'}]}},
            supplierVariantCoverage={'productId':'p1','sourceUrl':'https://detail.1688.com/offer/123.html',
                'checkedAt':'2026-11-05T05:12:32.465Z','evidence':'supplier-page.json',
                'supplierObservedColors':['Black'],'supplierObservedSizes':['M']})
        task = self.create(taskMode='production', autoResearch=True, researchAsins='B012345678')
        with patch('agent_selection.inspect',return_value={'ok':True,'issues':[]}), \
                patch.object(agent_research,'collect') as collect:
            result = self.run_sync(task)
        collect.assert_not_called()
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['results']['facts']['supplierVariantCoverage']['unverifiedColors'],['Brown'])
        self.assertEqual(result['results']['facts']['supplierVariantCoverage']['unverifiedSizes'],['5X-Large'])

    def test_recheck_refreshes_snapshot_and_preserves_history(self):
        task = self.create()
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, task['id'])
            stored.update(status='inspection_done', cursor=6, results={'plan': {'ok': True}, 'facts': {'ok': False}})
            agent.put(c, stored)
        self.product['material'] = 'updated cotton'
        result = agent.recheck(1, task['id'])
        self.assertEqual(result['status'], 'queued')
        self.assertEqual(result['cursor'], 1)
        self.assertEqual(list(result['results']), ['plan'])
        self.assertNotIn('revisions', result)
        stored = agent.detail(1, task['id'])
        self.assertEqual(stored['snapshot']['product']['material'], 'updated cotton')
        self.assertEqual(stored['revisions'][0]['snapshot']['product']['material'], 'cotton')
        self.assertFalse(stored['revisions'][0]['results']['facts']['ok'])

    def test_recheck_refuses_uncertain_external_and_foreign_tasks(self):
        task = self.create()
        with self.assertRaises(ValueError): agent.recheck(2, task['id'])
        for status, results, exported in [('needs_review', {}, False), ('running', {}, False),
                                          ('blocked', {'publish': {'ok': False}}, False),
                                          ('blocked', {}, True)]:
            with agent.LOCK, closing(agent.connect()) as c, c:
                stored = agent.owned(c, 1, task['id'])
                stored.update(status=status, results=results, exportAvailable=exported)
                agent.put(c, stored)
            with self.assertRaises(ValueError): agent.recheck(1, task['id'])

    def test_profile_snapshot_and_market_mismatch(self):
        task = self.create()
        agent.save_profile(1, dict(self.profile, quantity=12))
        self.assertEqual(agent.detail(1, task['id'])['profile']['quantity'], 88)
        wrong = agent.save_profile(1, dict(name='UK', store='B', marketplace='UK', shippingTemplate='B'))
        with self.assertRaises(ValueError): agent.create(1, dict(goal='x', profileId=wrong['id'], productId='p1'))

    def test_public_sourcing_is_default_for_production_but_disabled_for_inspection(self):
        production = self.create(taskMode='production')
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, production['id'])
            stored['status'] = 'blocked'
            agent.put(c, stored)
        inspection = self.create(taskMode='inspect')
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, inspection['id'])
            stored['status'] = 'blocked'
            agent.put(c, stored)
        opt_out = self.create(taskMode='production', autoSourcing=False)
        self.assertTrue(agent.detail(1, production['id'])['autoSourcing'])
        self.assertFalse(agent.detail(1, inspection['id'])['autoSourcing'])
        self.assertFalse(agent.detail(1, opt_out['id'])['autoSourcing'])

    def test_quantity_and_budget_validation(self):
        for invalid in ({'targetCount': 2}, {'targetCount': 0}, {'budgetCny': float('nan')}, {'budgetCny': -1}):
            with self.assertRaises(ValueError): self.create(**invalid)

    def listing_generation_fixture(self):
        self.workspace['copy'] = {}
        self.workspace['reviews'] = {}
        task = self.create(taskMode='production', autoListing=True)
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, task['id'])
            stored.update(status='running', results={'facts': {'ok': True}, 'research': {'ok': True}})
            agent.put(c, stored)
        return stored

    def test_auto_listing_requires_production_mode(self):
        with self.assertRaises(ValueError): self.create(autoListing=True)
        with self.assertRaisesRegex(ValueError, '必须为本任务填写人民币费用预算'):
            agent.create(1, dict(goal='检查并制作', profileId=self.profile['id'], productId='p1', taskMode='production', autoListing=True))
        with self.assertRaisesRegex(ValueError, '必须为本任务填写人民币费用预算'):
            agent.create(1, dict(goal='检查并制作', profileId=self.profile['id'], productId='p1', aiPlanning=True))
        with self.assertRaisesRegex(ValueError, '必须为本任务填写人民币费用预算'):
            agent.create(1, dict(goal='检查并制作', profileId=self.profile['id'], productId='p1', taskMode='production', autoResearch=True))

    def research_fixture(self):
        self.product['competitorResearch'] = {}
        self.workspace['copy'] = {}
        self.workspace['reviews'] = {}
        task = self.create(taskMode='production', autoResearch=True, autoListing=True, researchAsins='B0FVS1X3SP')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as c, c:
            c.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            c.execute('INSERT INTO workspace VALUES(1,1,?)', (json.dumps(self.workspace),))
        self.workspace_patch.stop()
        return task

    def research_report(self):
        return {'market': 'US', 'source': 'sellersprite',
                'sources': [{'asin': 'B0FVS1X3SP', 'url': 'https://www.amazon.com/dp/B0FVS1X3SP', 'status': 'ok', 'title': 'Cotton item'}],
                'keywords': [{'phrase': 'cotton item', 'selected': True, 'metrics': [{'searches': None}]}],
                'structure': 'Fixture analysis', 'warnings': 'Fixture only'}

    def test_auto_research_input_requires_explicit_production_scope(self):
        with self.assertRaises(ValueError): self.create(autoResearch=True)
        for asins in ('https://example.com', '123', 'B0FVS1X3SP;wrong'):
            with self.subTest(asins=asins), self.assertRaises(ValueError):
                self.create(taskMode='production', autoResearch=True, researchAsins=asins)

    def test_research_plan_task_accepts_empty_asins_then_attaches_verified_input(self):
        self.product['competitorResearch'] = {}
        task = self.create(taskMode='production', autoResearch=True)
        self.assertEqual(task['researchAsins'], [])
        updated = agent.set_research_asins(1, task['id'], 'b0fvs1x3sp, B0FVS1X3SP')
        self.assertEqual(updated['researchAsins'], ['B0FVS1X3SP'])
        self.assertEqual(agent.detail(1, task['id'])['events'][-1]['kind'], 'research_asins_set')
        with self.assertRaises(ValueError): agent.set_research_asins(1, task['id'], '')

    def test_missing_research_asins_persist_browser_plan_for_download(self):
        self.product['competitorResearch'] = {}
        task = self.create(taskMode='production', autoResearch=True)
        result = agent_research.collect(1, agent.detail(1, task['id']))
        self.assertTrue(result['needsCompetitorAsins'])
        self.assertTrue(result['researchSearchPlan']['amazonUrl'])
        stored = agent.detail(1, task['id'])
        self.assertTrue(stored['researchPlanAvailable'])
        self.assertEqual(agent_research.plan_report(1, task['id'])['amazonUrl'], result['researchSearchPlan']['amazonUrl'])
        self.assertIn('research_plan_saved', [event['kind'] for event in stored['events']])

    def test_research_candidates_are_selected_only_from_matching_front_search_observations(self):
        self.product['competitorResearch'] = {}
        self.product['name'] = 'Silicone Door Weather Stripping Seal 45mm 5m'
        self.product['selectionResearch'] = {'reference': {'asin': 'B012345678'}}
        self.product['selectionObservations'] = [{
            'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_front_search',
            'url': 'https://www.amazon.com/s?k=Silicone+Door+Weather+Stripping+Seal',
            'capturedAt': '2026-11-01T10:00:00Z',
            'search': {'query': 'Silicone Door Weather Stripping Seal', 'results': [
                {'asin': 'B012345678', 'title': 'Silicone Door Weather Stripping Seal'},
                {'asin': 'B099999999', 'title': 'Silicone Door Weather Stripping Seal 45mm 5m Brown'},
                {'asin': 'B088888888', 'title': 'Unrelated garden watering hose'},
            ]}}, {
            'asin': 'B012345678', 'marketplace': 'UK', 'captureType': 'browser_front_search',
            'url': 'https://www.amazon.co.uk/s?k=Silicone+Door+Weather+Stripping+Seal',
            'search': {'query': 'Silicone Door Weather Stripping Seal', 'results': [
                {'asin': 'B077777777', 'title': 'Silicone Door Weather Stripping Seal 45mm 5m'}]}}
        ]
        task = self.create(taskMode='production', autoResearch=True)
        choices = agent_research.observed_competitors(agent.detail(1, task['id']))
        self.assertEqual([row['asin'] for row in choices], ['B099999999'])
        self.assertGreaterEqual(choices[0]['score'], 0.25)
        self.assertEqual(choices[0]['status'], 'research_candidate_unverified')

    def test_research_candidate_selector_rejects_wrong_domain_and_low_similarity(self):
        product = {'name': 'Silicone Door Weather Stripping Seal',
                   'selectionResearch': {'reference': {'asin': 'B012345678'}},
                   'selectionObservations': [
                       {'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_front_search',
                        'url': 'https://evil.example/s?k=Silicone+Door+Weather+Stripping+Seal',
                        'search': {'query': 'Silicone Door Weather Stripping Seal',
                                   'results': [{'asin': 'B099999999', 'title': 'Silicone Door Weather Stripping Seal'}]}},
                       {'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_front_search',
                        'url': 'https://www.amazon.com/s?k=Silicone+Door+Weather+Stripping+Seal',
                        'search': {'query': 'Silicone Door Weather Stripping Seal',
                                   'results': [{'asin': 'B088888888', 'title': 'Garden hose nozzle'}]}}]}
        self.assertEqual(agent_research.observed_competitors({'snapshot': {'product': product},
                            'profile': {'marketplace': 'US'}}), [])

    def test_automatic_research_selection_is_persisted_before_external_call(self):
        self.product['competitorResearch'] = {}
        self.product['name'] = 'Silicone Door Weather Stripping Seal 45mm 5m'
        self.product['asin'] = 'B012345678'
        self.product['selectionObservations'] = [{
            'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_front_search',
            'url': 'https://www.amazon.com/s?k=Silicone+Door+Weather+Stripping+Seal',
            'capturedAt': '2026-11-01T10:00:00Z',
            'search': {'query': 'Silicone Door Weather Stripping Seal', 'results': [
                {'asin': 'B099999999', 'title': 'Silicone Door Weather Stripping Seal 45mm 5m Brown'}]}}]
        task = self.create(taskMode='production', autoResearch=True)
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as c, c:
            c.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            c.execute('INSERT INTO workspace VALUES(1,1,?)', (json.dumps(self.workspace),))
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, task['id'])
            stored.update(status='running', results={'facts': {'ok': True}})
            agent.put(c, stored)
        agent.ACTIVE.add(task['id'])
        def analyse(payload):
            persisted = agent.detail(1, task['id'])
            self.assertEqual(persisted['researchAsins'], ['B099999999'])
            self.assertEqual(persisted['researchCandidateSelection'][0]['status'], 'research_candidate_unverified')
            return self.research_report()
        with patch('provider.settings_public', return_value={'hasKey': True}), \
             patch('sellersprite.public', return_value={'hasKey': True}), \
             patch('competitors.analyse', side_effect=analyse) as external:
            result = agent_research.collect(1, agent.detail(1, task['id']))
        agent.ACTIVE.discard(task['id'])
        self.assertTrue(result['ok'])
        self.assertEqual(external.call_args.args[0]['asins'], 'B099999999')
        event_kinds = [event['kind'] for event in agent.detail(1, task['id'])['events']]
        self.assertLess(event_kinds.index('research_candidates_selected'), event_kinds.index('research_started'))

    def test_adopt_sourcing_candidate_requires_observed_offer_and_updates_product(self):
        self.product['competitorResearch'] = {}
        self.product['selectionObservations'] = [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {
            'offers': [{'url': 'https://detail.1688.com/offer/705907720182.html', 'offerId': '705907720182'}]}}]
        task = self.create(taskMode='production')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1, 1, ?)', (json.dumps(self.workspace),))
        updated = agent.adopt_sourcing_candidate(1, task['id'], 'https://detail.1688.com/offer/705907720182.html')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db:
            saved = json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
        self.assertEqual(saved['products'][0]['sourceUrl'], 'https://detail.1688.com/offer/705907720182.html')
        self.assertEqual(updated['workspaceRevision'], 2)
        self.assertEqual(agent.detail(1, task['id'])['events'][-1]['kind'], 'sourcing_candidate_adopted')
        with self.assertRaises(ValueError): agent.adopt_sourcing_candidate(1, task['id'], 'https://detail.1688.com/offer/999999999.html')

    def test_verify_sourcing_candidate_persists_human_checklist_before_adoption(self):
        self.product['competitorResearch'] = {}
        self.product['selectionObservations'] = [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {
            'offers': [{'url': 'https://detail.1688.com/offer/705907720182.html'}]}}]
        task = self.create(taskMode='production')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1, 1, ?)', (json.dumps(self.workspace),))
        checks = {key: True for key in ('sameProduct', 'exactVariant', 'priceConfirmed',
                                        'weightConfirmed', 'imageRights', 'brandRights')}
        result = agent.verify_sourcing_candidate(1, task['id'],
                                                 'https://detail.1688.com/offer/705907720182.html',
                                                 checks, '已打开详情页逐项核对并保留页面截图')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db:
            saved = json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])['products'][0]
        self.assertEqual(saved['sourceCandidateReviews'][0]['status'], 'human_reviewed')
        self.assertEqual(saved['sourceUrl'], 'https://example.com/item')
        self.assertEqual(result['workspaceRevision'], 2)
        self.assertEqual(result['sourceCandidateReviews'][0]['status'], 'human_reviewed')
        self.assertIn('sourcing_candidate_verified', [e['kind'] for e in agent.detail(1, task['id'])['events']])
        with self.assertRaises(ValueError): agent.verify_sourcing_candidate(1, task['id'],
            'https://detail.1688.com/offer/705907720182.html', {'sameProduct': True}, 'x')

    def test_default_supplier_adoption_records_policy_without_inventing_verification(self):
        self.product['selectionObservations'] = [{'captureType': 'browser_1688_image_search',
            'capturedAt': '2026-11-03', 'sourcingSearch': {'offers': [{
                'url': 'https://detail.1688.com/offer/705907720182.html', 'raw': '已售2万+件'}]}}]
        task = self.create(taskMode='production')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1,1,?)', (json.dumps(self.workspace),))
        policy = {'sourcingPolicy': {'information_adoption_policy': 'supplier_page_default_use',
            'additional_supplier_confirmation_required': False,
            'policy_authorization': {'date': '2026-11-03', 'instruction': '按销量默认采用'}}}
        with patch('agent_selection.current_policy', return_value=policy):
            result = agent.adopt_sourcing_candidate(1, task['id'],
                'https://detail.1688.com/offer/705907720182.html')
        self.assertTrue(result['supplierDefaultUse'])
        decision = result['sourceCandidateReviews'][-1]
        self.assertEqual(decision['status'], 'user_default_adopted')
        self.assertEqual(decision['checks'], {})
        self.assertFalse(decision['supplierLicenseObtained'])
        self.assertEqual(decision['salesRaw'], '已售2万+件')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db:
            product = json.loads(db.execute('SELECT body FROM workspace').fetchone()[0])['products'][0]
        self.assertEqual(product['packageWeight'], '100g')
        self.assertEqual(product['sourceCandidateReviews'][-1], decision)

    def test_adopt_sourcing_candidate_reads_observation_added_after_task_creation(self):
        self.product['competitorResearch'] = {}
        task = self.create(taskMode='production')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            latest = json.loads(json.dumps(self.workspace))
            latest['products'][0]['selectionObservations'] = [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {'offers': [{'url': 'https://detail.1688.com/offer/705907720182.html'}]}}]
            db.execute('INSERT INTO workspace VALUES(1, 1, ?)', (json.dumps(latest),))
        agent.adopt_sourcing_candidate(1, task['id'], 'https://detail.1688.com/offer/705907720182.html')

    def test_adopt_sourcing_candidate_archives_blocked_audit_and_queues_fresh_check(self):
        self.product['competitorResearch'] = {}
        self.product['selectionObservations'] = [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {
            'offers': [{'url': 'https://detail.1688.com/offer/705907720182.html'}]}}]
        task = self.create(taskMode='production')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1, 1, ?)', (json.dumps(self.workspace),))
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, task['id'])
            stored.update(status='blocked', cursor=4, reason='缺少货源链接',
                          results={'plan': {'ok': True}, 'facts': {'ok': False, 'issues': ['缺货源']},
                                   'research': {'ok': False}})
            agent.put(c, stored)
        result = agent.adopt_sourcing_candidate(1, task['id'], 'https://detail.1688.com/offer/705907720182.html')
        self.assertEqual(result['status'], 'queued')
        self.assertEqual(result['cursor'], 1)
        self.assertEqual(list(result['results']), ['plan'])
        detail = agent.detail(1, task['id'])
        self.assertEqual(len(detail['revisions']), 2)
        self.assertEqual(detail['revisions'][0]['reason'], '采用人工确认的1688候选链接')
        self.assertEqual(detail['revisions'][1]['reason'], '缺少货源链接')
        kinds = [event['kind'] for event in detail['events']]
        self.assertIn('sourcing_candidate_adopted', kinds)
        self.assertIn('snapshot_refreshed', kinds)
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db:
            saved = json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
        self.assertEqual(saved['products'][0]['sourceUrl'], 'https://detail.1688.com/offer/705907720182.html')

    def test_adopt_sourcing_candidate_rejects_concurrent_workspace_change(self):
        self.product['competitorResearch'] = {}
        self.product['selectionObservations'] = [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {
            'offers': [{'url': 'https://detail.1688.com/offer/705907720182.html'}]}}]
        task = self.create(taskMode='production')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1, 1, ?)', (json.dumps(self.workspace),))
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, task['id'])
            stored['workspaceRevision'] = 1
            stored['status'] = 'blocked'
            agent.put(c, stored)
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('UPDATE workspace SET revision=2')
        with self.assertRaisesRegex(ValueError, '资料在任务创建后已变化'):
            agent.adopt_sourcing_candidate(1, task['id'], 'https://detail.1688.com/offer/705907720182.html')
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT revision FROM workspace WHERE id=1').fetchone()[0], 2)

    def test_new_task_persists_workspace_revision_for_concurrency_guard(self):
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1, 7, ?)', (json.dumps(self.workspace),))
        task = self.create(taskMode='production')
        self.assertEqual(task['workspaceRevision'], 7)

    def test_production_runner_stops_after_failed_research_gate(self):
        task = self.create(taskMode='production', autoResearch=True, researchAsins='B0FVS1X3SP')
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, task['id'])
            stored.update(status='queued', cursor=2, results={'plan': {'ok': True}, 'facts': {'ok': True}})
            agent.put(c, stored)
        with patch('agent_research.collect', return_value={'ok': False, 'issues': ['研究失败']}):
            with patch('agent_center.threading.Thread.start'):
                agent.start(1, task['id'])
            agent.run(1, task['id'])
            result = agent.detail(1, task['id'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['cursor'], 3)
        self.assertNotIn('listing', result['results'])
        self.assertIn('竞品关键词检查未通过', result['reason'])

    def test_research_then_listing_runner_uses_saved_evidence_once(self):
        task = self.research_fixture()
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('sellersprite.public', return_value={'hasKey': True}), patch('competitors.analyse', return_value=self.research_report()) as analyse, patch('provider.generate_listing', return_value={'copy': self.listing}) as generate, patch.dict(agent.TOOLS, {'images': lambda task: {'ok': True}}):
            result = self.run_sync(task)
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue(result['researchReportAvailable'])
            self.assertTrue(result['listingDraftAvailable'])
            self.assertTrue(result['results']['research']['ok'])
            self.assertFalse(result['exportAvailable'])
            self.assertIsNone(result['paidSpendCny'])
            used_product = generate.call_args.args[0]
            self.assertEqual(used_product['competitorResearch']['US']['keywords'][0]['phrase'], 'cotton item')
            saved = agent.load_workspace()['products'][0]['competitorResearch']['US']
            self.assertEqual(saved['sources'][0]['asin'], 'B0FVS1X3SP')
            self.assertIsNone(saved['keywords'][0]['metrics'][0]['searches'])
            agent.recheck(1, task['id'])
            self.run_sync(task)
            self.assertEqual(analyse.call_count, 1)
            self.assertEqual(generate.call_count, 1)
        with self.assertRaises(ValueError): agent_research.report(2, task['id'])

    def test_research_usage_and_model_are_saved_without_sensitive_fields(self):
        task = self.research_fixture()
        report = self.research_report()
        report.update({
            'usage': {
                'prompt_tokens': 12,
                'completion_tokens': 34,
                'total_tokens': 46,
                'secret': 'drop',
                'raw_response': {'token': 'drop'},
            },
            'model': 'fixture-research-model',
            'api_key': 'drop',
        })
        with patch('provider.settings_public', return_value={'hasKey': True}), \
             patch('sellersprite.public', return_value={'hasKey': True}), \
             patch('competitors.analyse', return_value=report), \
             patch('provider.generate_listing', return_value={'copy': self.listing}), \
             patch.dict(agent.TOOLS, {'images': lambda task: {'ok': True}}):
            self.run_sync(task)
        saved = agent.detail(1, task['id'])['researchAttempt']
        self.assertEqual(saved['usage'], {'prompt_tokens': 12, 'completion_tokens': 34, 'total_tokens': 46})
        self.assertEqual(saved['model'], 'fixture-research-model')
        events = agent.detail(1, task['id'])['events']
        self.assertTrue(any(item['kind'] == 'research_applied' for item in events))
        research_event = next(item for item in reversed(events) if item['kind'] == 'research_saved')
        self.assertEqual(research_event['usage'], saved['usage'])
        self.assertEqual(research_event['model'], saved['model'])
        self.assertNotIn('secret', saved['usage'])
        self.assertNotIn('api_key', research_event)
        report = agent_research.report(1, task['id'])
        self.assertEqual(report['usage'], saved['usage'])
        self.assertNotIn('api_key', report)
        self.assertNotIn('raw_response', report)

    def test_failed_research_saved_without_requery_or_overwrite(self):
        task = self.research_fixture()
        failed = {'market': 'US', 'sources': [{'asin': 'B0FVS1X3SP', 'status': 'failed', 'error': 'Login required'}], 'keywords': []}
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('sellersprite.public', return_value={'hasKey': True}), patch('competitors.analyse', return_value=failed) as analyse, patch('provider.generate_listing') as generate, patch.dict(agent.TOOLS, {'images': lambda task: {'ok': True}}):
            result = self.run_sync(task)
            self.assertFalse(result['results']['research']['ok'])
            self.assertTrue(result['researchReportAvailable'])
            self.assertEqual(agent.load_workspace()['products'][0]['competitorResearch'], {})
            agent.recheck(1, task['id'])
            self.run_sync(task)
            self.assertEqual(analyse.call_count, 1)
            generate.assert_not_called()

    def test_research_timeout_remains_uncertain_without_retry(self):
        task = self.research_fixture()
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('sellersprite.public', return_value={'hasKey': True}), patch('competitors.analyse', side_effect=TimeoutError) as analyse:
            result = self.run_sync(task)
            self.assertEqual(result['status'], 'needs_review')
            self.assertEqual(result['researchAttempt']['state'], 'started')
            with self.assertRaises(ValueError): agent.recheck(1, task['id'])
            with self.assertRaises(ValueError): agent.start(1, task['id'])
            self.assertEqual(analyse.call_count, 1)

    def test_missing_research_credentials_do_not_consume_attempt(self):
        task = self.research_fixture()
        with patch('provider.settings_public', return_value={'hasKey': False}), patch('competitors.analyse') as analyse, patch('provider.generate_listing') as generate, patch.dict(agent.TOOLS, {'images': lambda task: {'ok': True}}):
            result = self.run_sync(task)
            self.assertEqual(result['status'], 'blocked')
            self.assertNotIn('researchAttempt', result)
            analyse.assert_not_called()
            generate.assert_not_called()

    def test_research_does_not_overwrite_changes_during_collection(self):
        task = self.research_fixture()
        def changed_report(data):
            with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as c, c:
                body = json.loads(c.execute('SELECT body FROM workspace').fetchone()[0])
                body['products'][0]['material'] = 'Updated during request'
                c.execute('UPDATE workspace SET revision=2,body=?', (json.dumps(body),))
            return self.research_report()
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('sellersprite.public', return_value={'hasKey': True}), patch('competitors.analyse', side_effect=changed_report) as analyse, patch.dict(agent.TOOLS, {'images': lambda task: {'ok': True}}):
            result = self.run_sync(task)
            self.assertFalse(result['results']['research']['ok'])
            self.assertTrue(result['researchReportAvailable'])
            saved = agent.load_workspace()['products'][0]
            self.assertEqual(saved['material'], 'Updated during request')
            self.assertEqual(saved['competitorResearch'], {})
            agent.recheck(1, task['id'])
            result = self.run_sync(task)
            self.assertFalse(result['results']['research']['ok'])
            self.assertEqual(analyse.call_count, 1)

    def test_generate_durable_draft_once_without_overwriting(self):
        task = self.listing_generation_fixture()
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('provider.generate_listing', return_value={'copy': self.listing, 'usage': {'prompt_tokens': 12, 'completion_tokens': 34, 'total_tokens': 46, 'secret': 'drop'}, 'model': 'fixture-model'}) as generate:
            result = agent.generate_task_listing(1, task)
            self.assertTrue(result['draftAvailable'])
            self.assertFalse(result['ok'])
            agent.generate_task_listing(1, task)
            self.assertEqual(generate.call_count, 1)
        self.assertEqual(self.workspace['copy'], {})
        self.assertEqual(agent.listing_draft(1, task['id'])['title'], self.listing['title'])
        self.assertIsNone(agent.detail(1, task['id'])['paidSpendCny'])
        saved = agent.detail(1, task['id'])['listingAttempt']
        self.assertEqual(saved['usage'], {'prompt_tokens': 12, 'completion_tokens': 34, 'total_tokens': 46})
        self.assertEqual(saved['model'], 'fixture-model')
        public=agent.public(agent.detail(1,task['id']))
        self.assertEqual(public['aiUsage']['usage']['total_tokens'],46)
        self.assertIsNone(public['aiUsage']['costCny'])
        self.assertNotIn('snapshot',public)
        with self.assertRaises(ValueError): agent.listing_draft(2, task['id'])
        path = self.root / 'agent-results' / task['id'] / 'listing-draft.json'
        path.write_text('{}')
        with self.assertRaises(ValueError): agent.listing_draft(1, task['id'])

    def test_generation_timeout_is_not_retried(self):
        task = self.listing_generation_fixture()
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('provider.generate_listing', side_effect=TimeoutError) as generate:
            with self.assertRaises(TimeoutError): agent.generate_task_listing(1, task)
            with self.assertRaises(ValueError): agent.generate_task_listing(1, task)
            self.assertEqual(generate.call_count, 1)

    def test_runner_stops_for_draft_review_and_recheck_does_not_regenerate(self):
        self.workspace['copy'] = {}
        self.workspace['reviews'] = {}
        task = self.create(taskMode='production', autoListing=True)
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('provider.generate_listing', return_value={'copy': self.listing}) as generate, patch.dict(agent.TOOLS, {'images': lambda task: {'ok': True}}):
            result = self.run_sync(task)
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue(result['listingDraftAvailable'])
            self.assertFalse(result['exportAvailable'])
            agent.recheck(1, task['id'])
            result = self.run_sync(task)
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(generate.call_count, 1)

    def test_generation_requires_checks_key_and_unchanged_input(self):
        task = self.listing_generation_fixture()
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('provider.generate_listing') as generate:
            task['results']['facts']['ok'] = False
            self.assertFalse(agent.generate_task_listing(1, task)['ok'])
            task['results']['facts']['ok'] = True
            self.product['material'] = 'changed after creation'
            self.assertFalse(agent.generate_task_listing(1, task)['ok'])
            generate.assert_not_called()

    def test_draft_adoption_checks_snapshot_and_leaves_review_pending(self):
        task = self.listing_generation_fixture()
        with patch('provider.settings_public', return_value={'hasKey': True}), patch('provider.generate_listing', return_value={'copy': self.listing}):
            agent.generate_task_listing(1, task)
        with agent.LOCK, closing(agent.connect()) as c, c:
            stored = agent.owned(c, 1, task['id']); stored['status'] = 'blocked'; agent.put(c, stored)
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as c, c:
            c.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            changed = json.loads(json.dumps(self.workspace))
            changed['copy']['p1-US'] = {'title': 'later user edits'}
            c.execute('INSERT INTO workspace VALUES (1,7,?)', (json.dumps(changed),))
        with self.assertRaises(ValueError): agent.adopt_listing(1, task['id'])
        with closing(sqlite3.connect(self.root / 'studio.sqlite3')) as c, c:
            self.assertEqual(json.loads(c.execute('SELECT body FROM workspace').fetchone()[0])['copy']['p1-US']['title'], 'later user edits')
            c.execute('UPDATE workspace SET body=?', (json.dumps(self.workspace),))
        adopted = agent.adopt_listing(1, task['id'])
        self.assertEqual(adopted['revision'], 8)
        self.assertFalse(adopted['state']['reviews']['p1']['copy'])
        self.assertEqual(adopted['state']['copy']['p1-US']['title'], self.listing['title'])
        with self.assertRaises(ValueError): agent.adopt_listing(1, task['id'])
        task = self.create(budgetCny=25)
        self.assertEqual(task['budgetCny'], 25)

    def test_duplicate_and_repeated_start_are_rejected(self):
        task = self.create()
        with self.assertRaises(ValueError): self.create()
        with patch('agent_center.threading.Thread.start'):
            agent.start(1, task['id'])
            with self.assertRaises(ValueError): agent.start(1, task['id'])
        agent.run(1, task['id'])

    def test_inspection_collects_all_issues_without_paid_tools(self):
        self.workspace['copy'] = {}
        task = self.create()
        with patch('studio_bridge.get_view', return_value={'sets': {}}), patch('colour_sets.list_sets', return_value={'sets': []}), \
             patch('visual_studio.model_json') as model, patch('delivery_export.build') as export:
            done = self.run_sync(task)
        self.assertEqual(done['status'], 'inspection_done')
        self.assertFalse(done['results']['listing']['ok'])
        self.assertFalse(done['results']['images']['ok'])
        self.assertTrue(done['results']['export']['skipped'])
        self.assertNotIn('publish', done['results'])
        self.assertFalse(done['exportAvailable'])
        model.assert_not_called(); export.assert_not_called()

    def test_production_with_missing_images_does_not_export(self):
        task = self.create(taskMode='production')
        with patch('studio_bridge.get_view', return_value={'sets': {}}), patch('colour_sets.list_sets', return_value={'sets': []}), patch('delivery_export.build') as export:
            done = self.run_sync(task)
        self.assertEqual(done['status'], 'blocked')
        export.assert_not_called()

    def test_image_inspection_surfaces_saved_runs_without_replaying_them(self):
        task = self.create()
        task['snapshot'] = {'product': self.product, 'review': {'images': True}}
        visual_db = self.root / 'visual_studio.sqlite3'
        c = sqlite3.connect(visual_db)
        with c:
            c.executescript('CREATE TABLE projects (id TEXT PRIMARY KEY, product_id TEXT, body TEXT, created REAL); CREATE TABLE runs (id TEXT PRIMARY KEY, project_id TEXT, body TEXT, updated REAL);')
            c.execute('INSERT INTO projects VALUES (?,?,?,?)', ('project-1', 'p1', '{}', 1))
            c.execute('INSERT INTO runs VALUES (?,?,?,?)', ('run-1', 'project-1', json.dumps({'id':'run-1','slot':2,'status':'generating','jobId':'provider-1','prompt':'private prompt','references':['private image']}), 2))
            c.execute('INSERT INTO runs VALUES (?,?,?,?)', ('run-2', 'project-1', json.dumps({'id':'run-2','slot':3,'status':'awaiting_manual','jobIds':['provider-2']}), 3))
        c.close()
        self.assertEqual(len(agent.image_run_history('p1')), 2)
        with patch('studio_bridge.get_view', return_value={'sets': {}}), patch('colour_sets.list_sets', return_value={'sets': []}):
            result = agent.inspect_images(task)
        self.assertEqual(result['activeImageRuns'], 1)
        self.assertEqual(result['imageRunsAwaitingAttention'], 1)
        self.assertEqual({r['id'] for r in result['imageRuns']}, {'run-1', 'run-2'})
        self.assertNotIn('prompt', result['imageRuns'][0])
        self.assertNotIn('references', result['imageRuns'][0])

    def test_image_history_is_read_only_when_database_is_missing(self):
        self.assertEqual(agent.image_run_history('p1'), [])
        self.assertFalse((self.root / 'visual_studio.sqlite3').exists())

    def test_full_discovery_stops_honestly(self):
        task = agent.create(1, dict(goal='选10款', profileId=self.profile['id'], taskMode='production'))
        done = self.run_sync(task)
        self.assertEqual(done['status'], 'blocked')
        self.assertEqual(list(done['results']), ['plan'])

    def test_restart_requires_review_and_cannot_repeat(self):
        task = self.create()
        with patch('agent_center.threading.Thread.start'): agent.start(1, task['id'])
        agent.ACTIVE.discard(task['id'])  # simulate dead process
        result = agent.detail(1, task['id'])
        self.assertEqual(result['status'], 'needs_review')
        with self.assertRaises(ValueError): agent.start(1, task['id'])

    def test_pause_after_tool_and_resume_without_repeating_tool(self):
        task = self.create()
        started = threading.Event(); release = threading.Event()
        def slow_plan(t):
            started.set(); release.wait(3); return {'ok': True}
        with patch.dict(agent.TOOLS, {'plan': slow_plan}), patch('studio_bridge.get_view', return_value={'sets': {}}), patch('colour_sets.list_sets', return_value={'sets': []}):
            agent.start(1, task['id']); self.assertTrue(started.wait(3)); agent.pause(1, task['id']); release.set()
            # A bounded event wait, not polling worker state.
            with agent.LOCK: pass
            import time
            deadline = time.monotonic() + 3
            while task['id'] in agent.ACTIVE and time.monotonic() < deadline: time.sleep(.01)
            paused = agent.detail(1, task['id']); self.assertEqual(paused['status'], 'paused')
            self.assertEqual(paused['cursor'], 1)
            done = self.run_sync(paused)
        starts = [e for e in done['events'] if e.get('tool') == 'plan' and e['kind'] == 'tool_started']
        self.assertEqual(len(starts), 1)

    def test_optional_ai_calls_existing_model_once_and_rejects_unknown_tools(self):
        task = self.create(aiPlanning=True, budgetCny=5)
        with patch('visual_studio.model_json', return_value={'summary': 'do it', 'steps': [{'tool': 'shell', 'purpose': 'bad'}], 'missing': []}) as model:
            done = self.run_sync(task)
        self.assertEqual(done['status'], 'needs_review')
        model.assert_called_once()
        self.assertEqual(done['cursor'], 0)
        with self.assertRaises(ValueError): agent.start(1, task['id'])

    def test_ai_output_is_only_a_plan_and_cannot_skip_checks(self):
        task = self.create(aiPlanning=True, budgetCny=5)
        with patch('visual_studio.model_json', return_value={'summary': '先发布', 'steps': [{'tool': 'publish', 'purpose': '立即发布'}], 'missing': []}), \
             patch('studio_bridge.get_view', return_value={'sets': {}}), patch('colour_sets.list_sets', return_value={'sets': []}):
            done = self.run_sync(task)
        self.assertEqual(done['status'], 'inspection_done')
        self.assertIn('images', done['results'])
        self.assertNotIn('publish', done['results'])

    def test_approved_master_without_other_colors_is_not_ready(self):
        task = self.create()
        self.product['supplierColorReferences'].append({'url': 'green.png', 'color': 'Green'})
        task['snapshot'] = {'product': self.product, 'review': {'images': True}}
        with patch('studio_bridge.get_view', return_value=self.all_images()), patch('colour_sets.list_sets', return_value={'sets': []}):
            result = agent.inspect_images(task)
        self.assertFalse(result['ok']); self.assertTrue(any('Green' in i for i in result['issues']))

    def test_delivery_hash_and_publish_block(self):
        task = self.create(taskMode='production')
        buffer = io.BytesIO()
        from PIL import Image
        picture = io.BytesIO(); Image.new('RGB', (1600, 1600), 'white').save(picture, 'PNG')
        with zipfile.ZipFile(buffer, 'w') as z:
            entries = [{'file': 'sku/Black' + str(n) + '.png', 'color': 'Black', 'slot': n} for n in range(7)]
            z.writestr('sku/image-manifest.json', json.dumps({'missing': [], 'excluded': [], 'images': entries}))
            for entry in entries: z.writestr(entry['file'], picture.getvalue())
            z.writestr('sku/listing.txt', 'test fixture')
        with patch('studio_bridge.get_view', return_value=self.all_images()), patch('colour_sets.list_sets', return_value={'sets': []}), patch('delivery_export.build', return_value=buffer.getvalue()):
            done = self.run_sync(task)
        self.assertEqual(done['status'], 'blocked')
        self.assertTrue(done['exportAvailable'])
        self.assertEqual(agent.download(1, task['id']), buffer.getvalue())
        (self.root / 'agent-results' / task['id'] / 'delivery.zip').write_bytes(b'changed')
        with self.assertRaises(ValueError): agent.download(1, task['id'])

    def test_export_refuses_changed_product_snapshot(self):
        task = self.create(taskMode='production')
        task = agent.detail(1, task['id'])
        task['results'] = dict.fromkeys(('facts', 'research', 'listing', 'images'), {'ok': True})
        self.workspace['products'][0]['material'] = 'different'
        with patch('delivery_export.build') as export:
            result = agent.export_delivery(task)
        self.assertFalse(result['ok']); export.assert_not_called()

    def make_preflight_archive(self, task, *, explicit_prices=True, include_aplus=False):
        task=agent.detail(1,task['id'])
        from PIL import Image
        archive = io.BytesIO(); image = io.BytesIO(); Image.new('RGB',(40,40),'white').save(image,'PNG')
        entries=[]
        variants=[]
        for color in ('Black','Blue'):
            if include_aplus:
                entries.append({'file':f'SKU/aplus/{color}01.png','color':color,'slot':0,'kind':'aplus'})
            for slot in range(7):
                name=f'SKU/{color}{slot+1:02d}.png'; entries.append({'file':name,'color':color,'slot':slot})
            for size in ('M','L'):
                variants.append({'sku':f'SKU-{color}-{size}','color':color,'size':size})
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('SKU/SKU-listing.json',json.dumps({'title':'Title','highlights':'Highlights','bullets':['a','b','c','d','e'],'description':'Desc','terms':'cotton shirt'}))
            output=io.StringIO();writer=__import__('csv').DictWriter(output,fieldnames=['sku','color','size']);writer.writeheader();writer.writerows(variants)
            z.writestr('SKU/variants.csv','\ufeff'+output.getvalue())
            z.writestr('SKU/image-manifest.json',json.dumps({'images':entries,'missing':[],'excluded':[]}))
            for e in entries:z.writestr(e['file'],image.getvalue())
        path=self.root/'agent-results'/task['id'];path.mkdir(parents=True,exist_ok=True)
        raw=archive.getvalue();(path/'delivery.zip').write_bytes(raw)
        task['exportAvailable']=True;task['results']['export']={'sha256':__import__('hashlib').sha256(raw).hexdigest()}
        task['snapshot']['product'].update(sku='SKU',brand='Generic',purchasePrice='¥43',packageWeight='390 g',packageDimensions='20 x 10 x 2 cm',
          supplierColorReferences=[{'url':'black','color':'Black'},{'url':'blue','color':'Blue'}],
          purchasePriceUniformAcrossVariants=True,packageWeightUniformAcrossVariants=True)
        if explicit_prices:
            task['snapshot']['product']['junfeiVariantPrices'] = {v['sku']: '31.06' for v in variants}
        with agent.LOCK, agent.closing(agent.connect()) as c, c:
            saved=agent.owned(c,1,task['id']);saved['snapshot']=task['snapshot'];saved['exportAvailable']=True;saved['results']['export']=task['results']['export'];agent.put(c,saved)
        return task

    def test_junfei_preflight_never_attaches_aplus_as_variant_gallery(self):
        task=self.make_preflight_archive(self.create(taskMode='production'),include_aplus=True)
        def command(args,**kwargs):
            product=json.loads(Path(args[args.index('--products')+1]).read_text(encoding='utf8'))[0]
            for variant in product['variants']:
                self.assertEqual(variant['mainImage'],f"SKU/{variant['color']}01.png")
                self.assertEqual(len(variant['images']),6)
                self.assertFalse(any('/aplus/' in path for path in variant['images']))
            out=Path(args[args.index('--output')+1]);out.mkdir(parents=True,exist_ok=True)
            (out/'plan.json').write_text('[]')
            return type('Result',(),{'returncode':0,'stdout':'ok','stderr':''})()
        with patch.object(agent.subprocess,'run',side_effect=command):
            self.assertTrue(agent.junfei_preflight(task)['ok'])

    def test_junfei_preflight_maps_each_color_and_stays_local(self):
        task=self.create(taskMode='production')
        task=self.make_preflight_archive(task)
        with patch.object(agent.subprocess,'run') as run:
            def command(args,**kwargs):
                self.assertNotIn('--run',args);self.assertNotIn('--publish',args);self.assertFalse(kwargs['shell'])
                products=json.loads(Path(args[args.index('--products')+1]).read_text(encoding='utf-8'))[0]
                self.assertIs(products['draftOnly'], True)
                self.assertEqual(len(products['variants']),4)
                for variant in products['variants']:
                    self.assertTrue(variant['mainImage'].startswith('SKU/'+variant['color']))
                    self.assertEqual(len(variant['images']),6)
                out=Path(args[args.index('--output')+1]);out.mkdir(parents=True,exist_ok=True);(out/'plan.json').write_text('[]')
                return type('Result',(),{'returncode':0,'stdout':'ok','stderr':''})()
            run.side_effect=command
            result=agent.junfei_preflight(task)
        self.assertTrue(result['ok']);self.assertTrue((self.root/'agent-results'/task['id']/'junfei-preflight'/'run-output'/'plan.json').is_file())
        task['junfeiPlanAvailable']=True
        with agent.LOCK, agent.closing(agent.connect()) as c, c:
            saved=agent.owned(c,1,task['id']);saved['junfeiPlanAvailable']=True;agent.put(c,saved)
        persisted=agent.detail(1,task['id'])
        record={'taskId':task['id'],'deliverySha256':persisted['results']['export']['sha256'],'artifacts':[
            {'path':'plan.json','sha256':__import__('hashlib').sha256(b'[]').hexdigest()}]}
        folder=self.root/'agent-results'/task['id']/'junfei-preflight';(folder/'preflight-record.json').write_text(json.dumps(record),encoding='utf-8')
        package=agent.download_junfei_plan(1,task['id'])
        with zipfile.ZipFile(io.BytesIO(package)) as z:
            self.assertIn('products.json',z.namelist())
            self.assertIn('SKU/Black01.png',z.namelist())
            self.assertIn('run-output/plan.json',z.namelist())

    def test_refresh_local_preflight_archives_plan_without_replaying_erp(self):
        task=self.make_preflight_archive(self.create(taskMode='production'))
        self.workspace['products']=[task['snapshot']['product']]
        folder=self.root/'agent-results'/task['id']/'junfei-preflight'
        folder.mkdir();(folder/'old-plan.json').write_text('34.08')
        task.update(status='blocked',junfeiPlanAvailable=True)
        task['results']['junfeiPreflight']={'ok':True,'oldPrice':'34.08'}
        task['results']['publish']={'ok':False,'reason':'此账号任务未绑定可执行的ERP草稿或产品库；未操作ERP'}
        with agent.LOCK,agent.closing(agent.connect()) as c,c:agent.put(c,task)
        with patch.object(agent,'junfei_preflight',return_value={'ok':True,'planAvailable':True,'newPrice':'31.06'}),patch.object(agent,'sync_erp') as erp:
            updated=agent.refresh_local_preflight(1,task['id'])
        erp.assert_not_called();self.assertEqual(updated['status'],'blocked')
        persisted=agent.detail(1,task['id'])
        self.assertEqual(persisted['results']['publish'],task['results']['publish'])
        archive=Path(persisted['localPreflightRevisions'][0]['archive'])
        self.assertEqual((archive/'old-plan.json').read_text(),'34.08')
        with self.assertRaises(ValueError):agent.refresh_local_preflight(2,task['id'])
        with agent.LOCK,agent.closing(agent.connect()) as c,c:
            persisted['status']='needs_review';agent.put(c,persisted)
        with patch.object(agent,'junfei_preflight') as preflight:
            with self.assertRaisesRegex(ValueError,'禁止重算'):agent.refresh_local_preflight(1,task['id'])
        preflight.assert_not_called()

    def test_junfei_preflight_blocks_unparseable_price_or_weight(self):
        task=self.create(taskMode='production');task=self.make_preflight_archive(task, explicit_prices=False)
        task['snapshot']['product']['purchasePrice']='18–24元'
        policy = {'method':'quote_cost_markup','draft_estimation':{'scope':'draft_only'}}
        with patch('quote_pricing.policy',return_value=policy), patch.object(agent.subprocess,'run') as run:
            result=agent.junfei_preflight(task)
        self.assertFalse(result['ok']);self.assertTrue(any('采购价' in i for i in result['issues']));run.assert_not_called()

    def test_junfei_preflight_reports_listing_field_gaps_before_node(self):
        task=self.create(taskMode='production');task=self.make_preflight_archive(task)
        archive=Path(agent.DATA)/'agent-results'/task['id']/'delivery.zip'
        with zipfile.ZipFile(archive) as source:
            entries={name:source.read(name) for name in source.namelist()}
        listing=json.loads(entries['SKU/SKU-listing.json'])
        listing.update(title=' ',description='',terms='x'*251,bullets=['a','b','','d','e'])
        entries['SKU/SKU-listing.json']=json.dumps(listing).encode('utf-8')
        rebuilt=io.BytesIO()
        with zipfile.ZipFile(rebuilt,'w') as target:
            for name,data in entries.items():target.writestr(name,data)
        raw=rebuilt.getvalue();archive.write_bytes(raw)
        task['results']['export']['sha256']=__import__('hashlib').sha256(raw).hexdigest()
        with patch.object(agent.subprocess,'run') as run:
            result=agent.junfei_preflight(task)
        self.assertFalse(result['ok'])
        self.assertTrue(any('标题为空' in issue for issue in result['issues']))
        self.assertTrue(any('描述为空' in issue for issue in result['issues']))
        self.assertTrue(any('251 UTF-8字节' in issue for issue in result['issues']))
        self.assertTrue(any('五点存在空项' in issue for issue in result['issues']))
        run.assert_not_called()

    def test_junfei_preflight_blocks_unlicensed_marks_before_node(self):
        task=self.create(taskMode='production');task=self.make_preflight_archive(task)
        task['snapshot']['product']['brandExclusions']=['3M']
        task['snapshot']['product']['sourceImport']={'supplier':{'attributes':{'品牌':'祥亚'}}}
        archive=Path(agent.DATA)/'agent-results'/task['id']/'delivery.zip'
        with zipfile.ZipFile(archive) as source:
            entries={name:source.read(name) for name in source.namelist()}
        listing=json.loads(entries['SKU/SKU-listing.json']);listing['title']='3M Door Seal'
        entries['SKU/SKU-listing.json']=json.dumps(listing).encode('utf-8')
        rebuilt=io.BytesIO()
        with zipfile.ZipFile(rebuilt,'w') as target:
            for name,data in entries.items():target.writestr(name,data)
        raw=rebuilt.getvalue();archive.write_bytes(raw)
        task['results']['export']['sha256']=__import__('hashlib').sha256(raw).hexdigest()
        with patch.object(agent.subprocess,'run') as run:
            result=agent.junfei_preflight(task)
        self.assertFalse(result['ok'])
        self.assertTrue(any('3M' in issue for issue in result['issues']))
        run.assert_not_called()

    def test_junfei_preflight_requires_uniform_variant_price_and_weight_confirmation(self):
        task=self.create(taskMode='production');task=self.make_preflight_archive(task, explicit_prices=False)
        task['snapshot']['product']['packageWeightUniformAcrossVariants']=False
        policy = {'method':'quote_cost_markup','draft_estimation':{'scope':'draft_only'}}
        with patch('quote_pricing.policy',return_value=policy), patch.object(agent.subprocess,'run') as run:
            result=agent.junfei_preflight(task)
        self.assertFalse(result['ok']);self.assertTrue(any('包装重量适用于全部' in i for i in result['issues']));run.assert_not_called()

    def test_junfei_preflight_accepts_explicit_non_us_variant_prices(self):
        task=self.create(taskMode='production');task=self.make_preflight_archive(task)
        task['profile']['marketplace']='UK';task['snapshot']['product']['junfeiVariantPrices']={f'SKU-{color}-{size}':'19.99' for color in ('Black','Blue') for size in ('M','L')}
        with patch.object(agent.subprocess,'run') as run:
            def command(args,**kwargs):
                products=json.loads(Path(args[args.index('--products')+1]).read_text(encoding='utf-8'))[0]
                self.assertTrue(all(v['price']=='19.99' and 'costRmb' not in v for v in products['variants']))
                out=Path(args[args.index('--output')+1]);out.mkdir(parents=True,exist_ok=True);(out/'plan.json').write_text('[]')
                return type('Result',(),{'returncode':0,'stdout':'ok','stderr':''})()
            run.side_effect=command
            result=agent.junfei_preflight(task)
        self.assertTrue(result['ok'])

    def test_junfei_preflight_preserves_cited_category_recommendation(self):
        task=self.create(taskMode='production');task=self.make_preflight_archive(task)
        task['snapshot']['product']['selectionResearch']={'reference':{
            'asin':'B012345678','category':'Tools & Home Improvement > Weather Stripping','source':'SellerSprite'}}
        with patch.object(agent.subprocess,'run') as run:
            def command(args,**kwargs):
                products=json.loads(Path(args[args.index('--products')+1]).read_text(encoding='utf-8'))
                recommendation=products[0]['categoryRecommendation']
                self.assertEqual(recommendation['categoryPath'],'Tools & Home Improvement > Weather Stripping')
                self.assertEqual(recommendation['referenceAsin'],'B012345678')
                self.assertEqual(recommendation['confidence'],'reference_only')
                out=Path(args[args.index('--output')+1]);out.mkdir(parents=True,exist_ok=True);(out/'plan.json').write_text('[]')
                return type('Result',(),{'returncode':0,'stdout':'ok','stderr':''})()
            run.side_effect=command
            result=agent.junfei_preflight(task)
        self.assertTrue(result['ok'])
        self.assertEqual(result['categoryRecommendation']['source'],'SellerSprite')
        self.assertIn('仅供页面核对',result['note'])
        task['junfeiPlanAvailable']=True
        with agent.LOCK, agent.closing(agent.connect()) as c, c:
            saved=agent.owned(c,1,task['id']);saved['junfeiPlanAvailable']=True;agent.put(c,saved)
        package=agent.download_junfei_plan(1,task['id'])
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            products=json.loads(archive.read('products.json').decode('utf-8'))
        self.assertEqual(products[0]['categoryRecommendation']['categoryPath'],
                         'Tools & Home Improvement > Weather Stripping')

    def test_public_responses_hide_workspace_snapshot(self):
        task = self.create()
        self.assertNotIn('snapshot', task)
        self.assertNotIn('snapshot', agent.overview(1)['tasks'][0])


if __name__ == '__main__': unittest.main()
