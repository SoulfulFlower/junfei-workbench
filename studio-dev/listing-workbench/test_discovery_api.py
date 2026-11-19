"""HTTP integration for a separate local discovery ledger, synthetic evidence only."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import cyclic_discovery as discovery
import test_agent_api as api_fixtures


class DiscoveryAPITests(unittest.TestCase):
    call = api_fixtures.AgentAPITests.call

    @classmethod
    def setUpClass(cls):
        api_fixtures.AgentAPITests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        api_fixtures.AgentAPITests.tearDownClass.__func__(cls)

    def setUp(self):
        self.tempLedger = tempfile.TemporaryDirectory(prefix='discovery-api-')
        self.addCleanup(self.tempLedger.cleanup)
        self.path = Path(self.tempLedger.name) / 'discovery.sqlite3'
        p = patch.object(discovery, 'DB', self.path)
        p.start()
        self.addCleanup(p.stop)

    def batch(self, cycle='api-cycle'):
        return {'cycleId':cycle, 'expectedRevision':0, 'events':[{
            'id':'keyword-1', 'parentId':None, 'kind':'keyword', 'marketplace':'US',
            'observedAt':datetime.now(timezone.utc).isoformat(), 'sourceType':'browser_visible',
            'asin':'B012345678', 'sourceTitle':'Cotton Pouches for Travel', 'phrase':'Cotton Pouches',
            'url':'https://www.amazon.com/dp/B012345678'}]}

    def test_discovery_script_is_served_on_first_load(self):
        import urllib.request
        from html.parser import HTMLParser
        class Scripts(HTMLParser):
            def __init__(self):
                super().__init__(); self.sources=[]
            def handle_starttag(self, tag, attrs):
                if tag == 'script':
                    src=dict(attrs).get('src', '')
                    if src and not src.startswith(('http:', 'https:', '//')):
                        self.sources.append('/' + src.lstrip('/'))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(self.base + '/index.html', timeout=5) as response:
            page=response.read().decode('utf-8')
        parser=Scripts(); parser.feed(page)
        self.assertIn('/discovery-ui.js', parser.sources)
        self.assertLess(parser.sources.index('/discovery-ui.js'), parser.sources.index('/selection.js'))
        for path in parser.sources:
            with self.subTest(path=path):
                with opener.open(self.base + path, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), 'text/javascript')
                    self.assertTrue(response.read())
        self.assertFalse(self.path.exists())

    def test_get_history_template_and_missing_report_never_create_ledger(self):
        self.assertEqual(self.call('/api/discovery/history',authenticated=False)[0],401)
        code, result = self.call('/api/discovery/history')
        self.assertEqual((code,result),(200,{'items':[]}))
        code, template = self.call('/api/discovery/template?market=JP')
        self.assertEqual(code,200)
        self.assertIn('eventTemplates',template)
        self.assertEqual(self.call('/api/discovery/template?market=XX')[0],400)
        self.assertEqual(self.call('/api/discovery/report?id=missing')[0],400)
        self.assertFalse(self.path.exists())

    def test_ingest_checks_auth_origin_and_rejects_non_object(self):
        payload = self.batch()
        self.assertEqual(self.call('/api/discovery/ingest',payload,authenticated=False)[0],401)
        self.assertEqual(self.call('/api/discovery/ingest',payload,Origin='https://external.invalid')[0],403)
        self.assertEqual(self.call('/api/discovery/ingest',payload,Origin='chrome-extension://synthetic')[0],403)
        self.assertEqual(self.call('/api/discovery/ingest',[])[0],400)
        self.assertFalse(self.path.exists())

    def test_real_ingest_report_history_idempotence_without_business_actions(self):
        payload = self.batch()
        with patch('market_research.start',side_effect=AssertionError('External research forbidden')), \
                patch('agent_center.start',side_effect=AssertionError('Task execution forbidden')), \
                patch('market_research.import_products',side_effect=AssertionError('Product import forbidden')):
            code, result = self.call('/api/discovery/ingest',payload)
            self.assertEqual(code,200)
            self.assertEqual(result['revision'],1)
            self.assertFalse(result['executionAllowed'])
            self.assertFalse(result['qualificationEvaluated'])
            self.assertEqual(result['qualifiedCount'],0)
            self.assertEqual(result['importedCount'],0)
            self.assertEqual(result['externalCallsPerformed'],0)
            self.assertEqual(self.call('/api/discovery/ingest',payload)[1]['revision'],1)
            code, saved = self.call('/api/discovery/report?id=api-cycle')
            self.assertEqual(code,200)
            self.assertEqual(saved,result)
            self.assertEqual(self.call('/api/discovery/history')[1]['items'][0]['cycleId'],'api-cycle')
            with self.assertRaises(ValueError):
                discovery.report(2,'api-cycle')
            self.assertEqual(discovery.history(2),{'items':[]})

    def test_stale_edit_is_not_blindly_retried(self):
        payload=self.batch()
        self.assertEqual(self.call('/api/discovery/ingest',payload)[0],200)
        later=self.batch()
        later['events'][0]['id']='keyword-2'
        self.assertEqual(self.call('/api/discovery/ingest',later)[0],400)
        report=self.call('/api/discovery/report?id=api-cycle')[1]
        self.assertEqual(report['eventCount'],1)
        self.assertEqual(report['revision'],1)

    def test_capture_routes_require_auth_same_origin_and_use_session_owner(self):
        import discovery_browser as browser
        payload = {'captureId':'capture-api','cycleId':'cycle','expectedRevision':1,'parentId':'search','asin':'B012345678'}
        with patch.object(browser,'capture',return_value={'captureId':'capture-api','status':'configuration_blocked'}) as capture:
            self.assertEqual(self.call('/api/discovery/capture-seller',payload,authenticated=False)[0],401)
            self.assertEqual(self.call('/api/discovery/capture-seller',payload,Origin='https://external.invalid')[0],403)
            self.assertEqual(self.call('/api/discovery/capture-seller',payload,Origin='chrome-extension://synthetic')[0],403)
            capture.assert_not_called()
            self.assertEqual(self.call('/api/discovery/capture-seller',[])[0],400)
            capture.assert_not_called()
            code,receipt=self.call('/api/discovery/capture-seller',payload)
            self.assertEqual(code,200);self.assertEqual(receipt['status'],'configuration_blocked')
            capture.assert_called_once_with(1,payload)

    def test_capture_history_detail_are_read_only_and_owner_scoped(self):
        import discovery_browser as browser
        path=Path(self.tempLedger.name)/'browser.sqlite3'
        with patch.object(browser,'DB',path):
            self.assertEqual(self.call('/api/discovery/captures',authenticated=False)[0],401)
            self.assertEqual(self.call('/api/discovery/captures'),(200,{'items':[]}))
            self.assertEqual(self.call('/api/discovery/capture?id=missing')[0],400)
            self.assertFalse(path.exists())
        with patch.object(browser,'detail',return_value={'captureId':'saved','status':'blocked'}) as detail:
            self.assertEqual(self.call('/api/discovery/capture?id=saved')[0],200)
            detail.assert_called_once_with(1,'saved')

    def test_unconfigured_real_capture_preserves_failure_without_browser_or_graph_mutation(self):
        import discovery_browser as browser
        batch=self.batch()
        batch['events'].append({'id':'search-1','parentId':'keyword-1','kind':'search','marketplace':'US',
            'sourceType':'browser_visible','observedAt':datetime.now(timezone.utc).isoformat(),
            'url':'https://www.amazon.com/s?k=Cotton+Pouches','query':'Cotton Pouches',
            'products':[{'asin':'B012345678','title':'Cotton Pouches'}]})
        self.assertEqual(self.call('/api/discovery/ingest',batch)[0],200)
        before=self.call('/api/discovery/report?id=api-cycle')[1]
        payload={'captureId':'offline-missing-binding','cycleId':'api-cycle','expectedRevision':1,'parentId':'search-1','asin':'B012345678'}
        with patch.object(browser,'DB',Path(self.tempLedger.name)/'browser.sqlite3'), \
             patch.object(browser,'_binding',side_effect=ValueError('missing binding')), \
             patch.object(browser.subprocess,'run',side_effect=AssertionError('Browser is forbidden')) as run:
            code,receipt=self.call('/api/discovery/capture-seller',payload)
            self.assertEqual(code,200);self.assertEqual(receipt['status'],'configuration_blocked')
            self.assertFalse(receipt['qualificationEvaluated']);self.assertNotIn('preparedBatch',receipt)
            self.assertEqual(self.call('/api/discovery/capture?id=offline-missing-binding')[1],receipt)
            self.assertEqual(self.call('/api/discovery/capture-seller',payload)[1],receipt)
            self.assertEqual(browser.history(2),{'items':[]})
            run.assert_not_called()
        self.assertEqual(self.call('/api/discovery/report?id=api-cycle')[1],before)

    def test_store_and_keyword_routes_enforce_auth_origin_account_and_size(self):
        import discovery_browser as browser
        routes = [('/api/discovery/capture-store', browser, 'capture_store',
                   {'captureId':'store-api','cycleId':'cycle','expectedRevision':1,'parentId':'seller','sellerId':'SELLER1'}),
                  ('/api/discovery/prepare-keyword', discovery, 'prepare_keyword',
                   {'cycleId':'cycle','expectedRevision':1,'parentId':'store','asin':'B012345678','phrase':'Cotton'})]
        for route, module, method, payload in routes:
            with self.subTest(route=route), patch.object(module, method, return_value={'status':'prepared'}) as action:
                self.assertEqual(self.call(route,payload,authenticated=False)[0],401)
                self.assertEqual(self.call(route,payload,Origin='https://external.invalid')[0],403)
                self.assertEqual(self.call(route,payload,Origin='chrome-extension://synthetic')[0],403)
                self.assertEqual(self.call(route,payload,**{'X-Workspace-Account':'2'})[0],409)
                self.assertEqual(self.call(route,[])[0],400)
                self.assertEqual(self.call(route,{'padding':'x'*4097})[0],400)
                action.assert_not_called()
                code, result=self.call(route,payload,Origin=self.base,**{'X-Workspace-Account':'1'})
                self.assertEqual((code,result),(200,{'status':'prepared'}))
                action.assert_called_once_with(1,payload)
        self.assertFalse(self.path.exists())

    def test_store_and_keyword_rejections_are_not_retried_or_started(self):
        import discovery_browser as browser
        for route,module,method in [('/api/discovery/capture-store',browser,'capture_store'),
                                    ('/api/discovery/prepare-keyword',discovery,'prepare_keyword')]:
            with self.subTest(route=route),patch.object(module,method,side_effect=ValueError('stale scope')) as action, \
                 patch('market_research.start',side_effect=AssertionError('No research')), \
                 patch('agent_center.start',side_effect=AssertionError('No production')), \
                 patch('market_research.import_products',side_effect=AssertionError('No import')):
                self.assertEqual(self.call(route,{'synthetic':'invalid'})[0],400)
                action.assert_called_once_with(1,{'synthetic':'invalid'})
        self.assertFalse(self.path.exists())

    def test_store_receipts_share_owner_scoped_history_and_detail(self):
        import discovery_browser as browser
        receipt={'captureId':'store-saved','captureKind':'store','status':'blocked'}
        with patch.object(browser,'history',return_value={'items':[receipt]}) as history, \
             patch.object(browser,'detail',return_value=receipt) as detail:
            self.assertEqual(self.call('/api/discovery/captures',**{'X-Workspace-Account':'2'})[0],409)
            self.assertEqual(self.call('/api/discovery/capture?id=store-saved',**{'X-Workspace-Account':'2'})[0],409)
            history.assert_not_called();detail.assert_not_called()
            self.assertEqual(self.call('/api/discovery/captures'),(200,{'items':[receipt]}))
            self.assertEqual(self.call('/api/discovery/capture?id=store-saved'),(200,receipt))
            history.assert_called_once_with(1);detail.assert_called_once_with(1,'store-saved')

    def test_real_unconfigured_store_capture_is_idempotent_and_never_writes_graph(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'store-cycle','expectedRevision':0,'events':chain()[:3]})
        before=discovery.report(1,'store-cycle')
        request={'captureId':'store-unconfigured','cycleId':'store-cycle','expectedRevision':1,'parentId':'s1','sellerId':'SELLER1'}
        with patch.object(browser,'DB',Path(self.tempLedger.name)/'browser.sqlite3'), \
             patch.object(browser,'_binding',side_effect=ValueError('missing binding')), \
             patch.object(browser.subprocess,'run',side_effect=AssertionError('No real browser')) as run:
            code,receipt=self.call('/api/discovery/capture-store',request)
            self.assertEqual(code,200);self.assertEqual(receipt['captureKind'],'store')
            self.assertEqual(receipt['status'],'configuration_blocked');self.assertNotIn('preparedBatch',receipt)
            self.assertEqual(self.call('/api/discovery/capture-store',request),(200,receipt))
            self.assertEqual(self.call('/api/discovery/capture?id=store-unconfigured'),(200,receipt))
            self.assertEqual(self.call('/api/discovery/captures')[1]['items'],[receipt])
            self.assertEqual(browser.history(2),{'items':[]});run.assert_not_called()
        self.assertEqual(discovery.report(1,'store-cycle'),before)

    def test_real_store_parent_and_revision_fail_before_browser(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'store-cycle','expectedRevision':0,'events':chain()[:3]})
        with patch.object(browser,'DB',Path(self.tempLedger.name)/'browser.sqlite3'), \
             patch.object(browser,'_binding',side_effect=AssertionError('No binding needed')) as binding, \
             patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser')) as run:
            for i,change in enumerate([{'parentId':'q1'},{'parentId':'missing'},{'sellerId':'OTHER1'},{'expectedRevision':0},{'cycleId':'foreign'}]):
                request={'captureId':'bad-store-'+str(i),'cycleId':'store-cycle','expectedRevision':1,'parentId':'s1','sellerId':'SELLER1',**change}
                code,receipt=self.call('/api/discovery/capture-store',request)
                self.assertEqual(code,200);self.assertEqual(receipt['status'],'blocked');self.assertNotIn('preparedBatch',receipt)
            binding.assert_not_called();run.assert_not_called()
        self.assertEqual(discovery.report(1,'store-cycle')['eventCount'],3)

    def test_real_keyword_preview_then_explicit_ingest_only(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'keyword-cycle','expectedRevision':0,'events':chain()[:4]})
        before=discovery.report(1,'keyword-cycle');before_bytes=self.path.read_bytes()
        request={'cycleId':'keyword-cycle','expectedRevision':1,'parentId':'t1','asin':'B000000003','phrase':'Linen Pants'}
        with patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser')), \
             patch('market_research.start',side_effect=AssertionError('No research')), \
             patch('agent_center.start',side_effect=AssertionError('No production')), \
             patch('market_research.import_products',side_effect=AssertionError('No product import')):
            code,preview=self.call('/api/discovery/prepare-keyword',request)
            self.assertEqual(code,200);self.assertEqual(preview['status'],'prepared');self.assertTrue(preview['readOnly'])
            self.assertEqual(preview['sourceKind'],'seller_listing_card')
            self.assertFalse(preview['qualificationEvaluated']);self.assertFalse(preview['executionAllowed'])
            self.assertEqual(self.path.read_bytes(),before_bytes)
            self.assertEqual(discovery.report(1,'keyword-cycle'),before)
            self.assertEqual(self.call('/api/discovery/prepare-keyword',request),(200,preview))
            code,saved=self.call('/api/discovery/ingest',preview['preparedBatch'])
            self.assertEqual(code,200);self.assertEqual(saved['eventCount'],5);self.assertEqual(saved['revision'],2)
            self.assertEqual(saved['qualifiedCount'],0);self.assertEqual(saved['importedCount'],0)
            event=saved['events'][-1]
            self.assertEqual((event['parentId'],event['asin'],event['sourceTitle']),('t1','B000000003','Linen Pants Women'))
            self.assertEqual(self.call('/api/discovery/ingest',preview['preparedBatch']),(200,saved))
            self.assertEqual(self.call('/api/discovery/prepare-keyword',request)[0],400)

    def test_keyword_preview_rejects_cross_owner_fabricated_product_and_nonprefix(self):
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'keyword-cycle','expectedRevision':0,'events':chain()[:4]})
        discovery.ingest(2,{'cycleId':'foreign-cycle','expectedRevision':0,'events':chain()[:4]})
        request={'cycleId':'keyword-cycle','expectedRevision':1,'parentId':'t1','asin':'B000000003','phrase':'Linen Pants'}
        before=self.path.read_bytes()
        for change in [{'cycleId':'foreign-cycle'},{'parentId':'s1'},{'asin':'B000000099'},{'phrase':'Pants Women'},{'sourceTitle':'Invented'},{'expectedRevision':0}]:
            with self.subTest(change=change):self.assertEqual(self.call('/api/discovery/prepare-keyword',{**request,**change})[0],400)
        self.assertEqual(self.path.read_bytes(),before)

    def test_search_and_plan_routes_require_auth_same_origin_owner_and_4kib(self):
        import discovery_browser as browser
        import discovery_plan as planner
        routes = [('/api/discovery/capture-search',browser,'capture_search',
                   {'captureId':'search-api','cycleId':'cycle','expectedRevision':1,'parentId':'keyword'}),
                  ('/api/discovery/prepare-plan',planner,'prepare',
                   {'cycleId':'cycle','expectedRevision':1,'maxActions':5,'maxRounds':2})]
        for route,module,method,payload in routes:
            with self.subTest(route=route),patch.object(module,method,return_value={'status':'test-only'}) as action:
                self.assertEqual(self.call(route,payload,authenticated=False)[0],401)
                self.assertEqual(self.call(route,payload,Origin='https://external.invalid')[0],403)
                self.assertEqual(self.call(route,payload,Origin='chrome-extension://synthetic')[0],403)
                self.assertEqual(self.call(route,payload,**{'X-Workspace-Account':'2'})[0],409)
                self.assertEqual(self.call(route,[])[0],400)
                self.assertEqual(self.call(route,{'padding':'x'*4097})[0],400)
                action.assert_not_called()
                self.assertEqual(self.call(route,payload,Origin=self.base,**{'X-Workspace-Account':'1'}),(200,{'status':'test-only'}))
                action.assert_called_once_with(1,payload)
        self.assertFalse(self.path.exists())

    def test_search_and_plan_errors_do_not_retry_start_or_import(self):
        import discovery_browser as browser
        import discovery_plan as planner
        for route,module,method in [('/api/discovery/capture-search',browser,'capture_search'),
                                    ('/api/discovery/prepare-plan',planner,'prepare')]:
            with self.subTest(route=route),patch.object(module,method,side_effect=ValueError('stale scope')) as action,                  patch('market_research.start',side_effect=AssertionError('No research')),                  patch('agent_center.start',side_effect=AssertionError('No production')),                  patch('market_research.import_products',side_effect=AssertionError('No import')):
                self.assertEqual(self.call(route,{'synthetic':'invalid'})[0],400)
                action.assert_called_once_with(1,{'synthetic':'invalid'})
        self.assertFalse(self.path.exists())

    def test_real_unconfigured_search_preserves_receipt_without_browser_or_graph_write(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'search-cycle','expectedRevision':0,'events':chain()[:1]})
        before=discovery.report(1,'search-cycle');before_bytes=self.path.read_bytes()
        request={'captureId':'search-unconfigured','cycleId':'search-cycle','expectedRevision':1,'parentId':'k1'}
        with patch.object(browser,'DB',Path(self.tempLedger.name)/'browser.sqlite3'),              patch.object(browser,'_binding',side_effect=ValueError('missing binding')),              patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser')) as run:
            code,receipt=self.call('/api/discovery/capture-search',request)
            self.assertEqual(code,200);self.assertEqual(receipt['captureKind'],'search')
            self.assertEqual(receipt['status'],'configuration_blocked')
            self.assertNotIn('preparedBatch',receipt);self.assertFalse(receipt['qualificationEvaluated'])
            self.assertEqual(self.call('/api/discovery/capture-search',request),(200,receipt))
            self.assertEqual(self.call('/api/discovery/capture?id=search-unconfigured'),(200,receipt))
            self.assertEqual(self.call('/api/discovery/captures')[1]['items'],[receipt])
            self.assertEqual(browser.history(2),{'items':[]});run.assert_not_called()
            with self.assertRaises(ValueError):browser.detail(2,request['captureId'])
        self.assertEqual(discovery.report(1,'search-cycle'),before)
        self.assertEqual(self.path.read_bytes(),before_bytes)

    def test_real_search_rejects_foreign_parent_stale_revision_and_extra_fields(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'search-cycle','expectedRevision':0,'events':chain()[:3]})
        discovery.ingest(2,{'cycleId':'foreign-cycle','expectedRevision':0,'events':chain()[:1]})
        before=self.path.read_bytes()
        request={'captureId':'bad-search','cycleId':'search-cycle','expectedRevision':1,'parentId':'k1'}
        with patch.object(browser,'DB',Path(self.tempLedger.name)/'browser.sqlite3'),              patch.object(browser,'_binding',side_effect=AssertionError('No binding')) as binding,              patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser')) as run:
            for i,change in enumerate([{'parentId':'q1'},{'parentId':'missing'},{'expectedRevision':0},{'cycleId':'foreign-cycle'}]):
                code,receipt=self.call('/api/discovery/capture-search',{**request,'captureId':'bad-search-'+str(i),**change})
                self.assertEqual(code,200);self.assertEqual(receipt['status'],'blocked')
                self.assertNotIn('preparedBatch',receipt)
            for field,value in [('owner',2),('query','fabricated'),('marketplace','UK'),('asin','B000000001')]:
                self.assertEqual(self.call('/api/discovery/capture-search',{**request,field:value})[0],400)
            binding.assert_not_called();run.assert_not_called()
        self.assertEqual(self.path.read_bytes(),before)

    def test_real_search_capture_id_cannot_cross_kinds_or_bypass_unknown(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'cross-kind-cycle','expectedRevision':0,'events':chain()[:3]})
        request={'captureId':'shared-id','cycleId':'cross-kind-cycle','expectedRevision':1,'parentId':'k1'}
        with patch.object(browser,'DB',Path(self.tempLedger.name)/'browser.sqlite3'),              patch.object(browser,'_binding',side_effect=ValueError('missing binding')),              patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser')) as run:
            self.assertEqual(self.call('/api/discovery/capture-search',request)[0],200)
            self.assertEqual(self.call('/api/discovery/capture-seller',{**request,'parentId':'q1','asin':'B000000002'})[0],400)
            self.assertEqual(self.call('/api/discovery/capture-store',{**request,'parentId':'s1','sellerId':'SELLER1'})[0],400)
            # Explicit fixture receipt, not a real browser timeout.
            import sqlite3
            with closing(sqlite3.connect(browser.DB)) as conn, conn:
                raw=conn.execute('SELECT receipt FROM attempts WHERE owner=1 AND id=?',(request['captureId'],)).fetchone()[0]
                unknown=json.loads(raw);unknown.update(status='execution_unknown',reason='synthetic_test_unknown')
                conn.execute('UPDATE attempts SET status=?,receipt=? WHERE owner=1 AND id=?',
                             ('execution_unknown',json.dumps(unknown),request['captureId']))
            for suffix,payload in [('search',{'parentId':'k1'}),('seller',{'parentId':'q1','asin':'B000000002'}),
                                   ('store',{'parentId':'s1','sellerId':'SELLER1'})]:
                code,receipt=self.call('/api/discovery/capture-'+suffix,{**request,'captureId':'new-'+suffix,**payload})
                self.assertEqual(code,200);self.assertEqual(receipt['reason'],'prior_capture_unresolved')
                self.assertNotIn('preparedBatch',receipt)
            run.assert_not_called()
        self.assertEqual(discovery.report(1,'cross-kind-cycle')['eventCount'],3)

    def test_real_plan_is_deterministic_readonly_bounded_and_never_ingests(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'plan-cycle','expectedRevision':0,'events':chain()[:5]})
        request={'cycleId':'plan-cycle','expectedRevision':1,'maxActions':2,'maxRounds':2}
        before=self.path.read_bytes()
        capture_path=Path(self.tempLedger.name)/'absent-browser.sqlite3'
        with patch.object(browser,'DB',capture_path),              patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser')),              patch('market_research.start',side_effect=AssertionError('No research')),              patch('agent_center.start',side_effect=AssertionError('No production')),              patch('market_research.import_products',side_effect=AssertionError('No import')),              patch.object(discovery,'ingest',side_effect=AssertionError('No ledger writes')):
            code,preview=self.call('/api/discovery/prepare-plan',request)
            self.assertEqual(code,200);self.assertEqual(preview['status'],'ready')
            self.assertTrue(preview['readOnly']);self.assertEqual(preview['owner'],1)
            self.assertFalse(preview['executionAllowed']);self.assertFalse(preview['automaticNavigationImplemented'])
            self.assertFalse(preview['qualificationEvaluated']);self.assertEqual(preview['qualifiedCount'],0)
            self.assertEqual(preview['importedCount'],0);self.assertEqual(preview['externalCallsPerformed'],0)
            self.assertEqual(preview['limits'],{'maxActions':2,'maxRounds':2})
            self.assertLessEqual(len(preview['actions']),2)
            self.assertTrue(all(a['proposedRound']<=2 and not a['executionAllowed'] for a in preview['actions']))
            action=next(a for a in preview['actions'] if a['kind']=='search_capture')
            self.assertEqual((action['sourceEventId'],action['query']),('k2','Linen Pants'))
            self.assertEqual(self.call('/api/discovery/prepare-plan',request),(200,preview))
        self.assertEqual(self.path.read_bytes(),before);self.assertFalse(capture_path.exists())

    def test_real_plan_rejects_foreign_cycle_stale_revision_and_invalid_limits(self):
        import discovery_browser as browser
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'plan-cycle','expectedRevision':0,'events':chain()[:1]})
        discovery.ingest(2,{'cycleId':'foreign-plan','expectedRevision':0,'events':chain()[:1]})
        request={'cycleId':'plan-cycle','expectedRevision':1,'maxActions':5,'maxRounds':2};before=self.path.read_bytes()
        capture_path=Path(self.tempLedger.name)/'absent-browser.sqlite3'
        changes=[{'cycleId':'foreign-plan'},{'expectedRevision':0},{'owner':2},{'execute':True}]
        for field in ('maxActions','maxRounds'):
            changes.extend({field:value} for value in (None,True,False,0,21,1.5,'2'))
        with patch.object(browser,'DB',capture_path):
            for change in changes:
                with self.subTest(change=change):self.assertEqual(self.call('/api/discovery/prepare-plan',{**request,**change})[0],400)
            for field in request:
                payload=dict(request);del payload[field]
                self.assertEqual(self.call('/api/discovery/prepare-plan',payload)[0],400)
        self.assertEqual(self.path.read_bytes(),before);self.assertFalse(capture_path.exists())

    def test_real_plan_unknown_history_is_owner_wide_barrier_not_a_retry(self):
        import discovery_browser as browser
        import sqlite3
        from test_cyclic_discovery import chain
        discovery.ingest(1,{'cycleId':'plan-cycle','expectedRevision':0,'events':chain()[:1]})
        request={'cycleId':'plan-cycle','expectedRevision':1,'maxActions':5,'maxRounds':2}
        capture_path=Path(self.tempLedger.name)/'browser.sqlite3'
        with patch.object(browser,'DB',capture_path):
            conn=browser._connect(True)
            try:
                receipt={'captureId':'old-unknown','captureKind':'store','cycleId':'different-cycle','parentId':'saved-seller','status':'execution_unknown'}
                conn.execute('INSERT INTO attempts VALUES (?,?,?,?,?)',(2,'old-unknown','synthetic',receipt['status'],json.dumps(receipt)))
                conn.commit()
            finally:conn.close()
            self.assertEqual(self.call('/api/discovery/prepare-plan',request)[1]['status'],'ready')
            with closing(sqlite3.connect(capture_path)) as conn, conn:conn.execute('UPDATE attempts SET owner=1')
            before=self.path.read_bytes();before_capture=capture_path.read_bytes()
            code,preview=self.call('/api/discovery/prepare-plan',request)
            self.assertEqual(code,200);self.assertEqual(preview['status'],'blocked');self.assertEqual(preview['actions'],[])
            self.assertTrue(any(b['reason']=='prior_capture_unresolved' for b in preview['blockers']))
            self.assertEqual(self.path.read_bytes(),before);self.assertEqual(capture_path.read_bytes(),before_capture)
