import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import server
import accounts
import agent_center as agent
import market_research
import sqlite3
from contextlib import closing


class AgentAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        cls.patches = [patch.object(agent, 'DATA', folder), patch.object(agent, 'DB', folder / 'agent.sqlite3'),
                       patch.object(accounts, 'DB', folder / 'accounts.sqlite3'),
                       patch.object(server.account_spaces, 'needs_proxy', return_value=False),
                       patch.object(agent, 'load_workspace', return_value={'products': [{'id': 'test', 'name': '测试', 'market': 'US'}], 'copy': {}, 'reviews': {}})]
        for p in cls.patches: p.start()
        accounts.register({'username': 'agenttest', 'password': 'test-only-password-12345'}, setup=True)
        cls.token, _ = accounts.login({'username': 'agenttest', 'password': 'test-only-password-12345'}, 'test')
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join()
        for p in reversed(cls.patches): p.stop()
        cls.temp.cleanup()

    def call(self, path, data=None, authenticated=True, **headers):
        headers = {'Content-Type': 'application/json', **headers}
        if authenticated: headers['Cookie'] = 'studio_session=' + self.token
        request = urllib.request.Request(self.base + path, headers=headers, data=json.dumps(data).encode() if data is not None else None)
        try: response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as response: return response.code, json.load(response)
        with response: return response.status, json.load(response)


    def test_image_preparation_get_is_read_only_and_requires_account_and_revision(self):
        with patch.object(agent, 'image_preparation', return_value={'readOnly':True,'paidCallsAllowed':False}) as preview, \
                patch.object(agent, 'start') as start:
            self.assertEqual(self.call('/api/agent/image-preparation?id=fixture&revision=7',authenticated=False)[0],401)
            for suffix in ('', '&revision=', '&revision=bad', '&revision=-1'):
                self.assertEqual(self.call('/api/agent/image-preparation?id=fixture'+suffix)[0],400)
            preview.assert_not_called()
            code, body = self.call('/api/agent/image-preparation?id=fixture&revision=7')
            self.assertEqual(code,200)
            self.assertTrue(body['preparation']['readOnly'])
            self.assertFalse(body['preparation']['paidCallsAllowed'])
            preview.assert_called_once_with(1,'fixture',7)
            start.assert_not_called()
        with patch.object(agent, 'image_preparation', side_effect=ValueError('not owned')):
            self.assertEqual(self.call('/api/agent/image-preparation?id=other&revision=7')[0],400)

    def test_supplier_queue_routes_require_login_origin_and_explicit_resume(self):
        with patch.object(server.supplier_capture,'status',return_value={'paused':False,'items':[]}) as status, \
                patch.object(server.supplier_capture,'request',return_value={'status':'queued','id':'fixture'}) as request, \
                patch.object(server.supplier_capture,'resume',return_value={'paused':False}) as resume:
            self.assertEqual(self.call('/api/supplier-capture/status',authenticated=False)[0],401)
            self.assertEqual(self.call('/api/supplier-capture/request',{'url':'fixture'},authenticated=False)[0],401)
            self.assertEqual(self.call('/api/supplier-capture/request',{'url':'fixture'},Origin='https://elsewhere.example')[0],403)
            status.assert_not_called();request.assert_not_called()
            self.assertEqual(self.call('/api/supplier-capture/status')[0],200)
            self.assertEqual(self.call('/api/supplier-capture/request',{'url':'fixture'})[0],200)
            request.assert_called_once_with('fixture')
            self.assertEqual(self.call('/api/supplier-capture/resume',{})[0],400)
            resume.assert_not_called()
            self.assertEqual(self.call('/api/supplier-capture/resume',{'confirmed':True})[0],200)
            resume.assert_called_once()

    def test_supplier_missing_browser_reconnect_requires_confirmation_and_exact_boolean(self):
        with patch.object(server.supplier_capture, 'resume', return_value={'paused': False}) as resume:
            self.assertEqual(self.call('/api/supplier-capture/resume', {'reconnectMissingBrowser': True})[0], 400)
            self.assertEqual(self.call('/api/supplier-capture/resume', {'confirmed': True, 'reconnectMissingBrowser': 1})[0], 400)
            resume.assert_not_called()
            self.assertEqual(self.call('/api/supplier-capture/resume',
                {'confirmed': True, 'reconnectMissingBrowser': True})[0], 200)
            resume.assert_called_once_with(reconnect_missing_browser=True)

    def test_copy_handoff_route_requires_auth_origin_and_only_prepares(self):
        payload = {'id':'fixture-task','budgetCny':3,'researchAsins':'B012345678',
                   'confirmPaidText':True,'acknowledgeBudgetNotHardCap':True,
                   'workspaceRevision':7}
        with patch.object(agent, 'prepare_copy_handoff', return_value={'id':'fixture-task','status':'queued'}) as prepare, \
                patch.object(agent, 'start') as start:
            self.assertEqual(self.call('/api/agent/prepare-copy-handoff',payload,authenticated=False)[0],401)
            self.assertEqual(self.call('/api/agent/prepare-copy-handoff',payload,Origin='https://elsewhere.example')[0],403)
            prepare.assert_not_called()
            code, result = self.call('/api/agent/prepare-copy-handoff',payload)
            self.assertEqual(code,200)
            self.assertEqual(result['task']['status'],'queued')
            prepare.assert_called_once_with(1,'fixture-task',payload)
            start.assert_not_called()

    def test_direct_image_api_cannot_supply_its_own_storyboard_proof(self):
        request = {'productId':'test','slot':'main','prompt':'Draw this product',
                   'storyboardProjectId':'caller-chosen-id','storyboardSlot':0}
        with patch.object(server.image_provider, 'begin_submission') as reserve:
            status, response = self.call('/api/image/generate', request)
        self.assertEqual(status, 400)
        self.assertIn('AI 生成分镜', response['error'])
        reserve.assert_not_called()

    def test_agent_routes_require_login_and_origin(self):
        with patch.object(server.image_provider,'budget_quote') as preview:
            self.assertEqual(self.call('/api/image/budget-quote',{},authenticated=False)[0],401)
            self.assertEqual(self.call('/api/image/budget-quote',{},Origin='https://elsewhere.example')[0],403)
            preview.assert_not_called()
        self.assertEqual(self.call('/api/agent/observe-erp', {'id':'other'}, authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/agent/observe-erp', {'id':'other'}, Origin='https://elsewhere.example')[0], 403)
        self.assertEqual(self.call('/api/agent/observe-erp', {'id':'not-owned'})[0], 400)
        self.assertEqual(self.call('/api/agent/overview', authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/agent/listing-draft?id=other', authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/agent/research-report?id=other', authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/agent/sourcing-report?id=other', authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/agent/research-plan?id=other', authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/agent/sourcing-plan?id=other', authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/agent/sourcing-report?id=other')[0], 400)
        self.assertEqual(self.call('/api/agent/research-report?id=other')[0], 400)
        self.assertEqual(self.call('/api/agent/research-plan?id=other')[0], 400)
        self.assertEqual(self.call('/api/agent/sourcing-plan?id=other')[0], 400)
        self.assertEqual(self.call('/api/agent/listing-draft?id=other')[0], 400)
        self.assertEqual(self.call('/api/agent/adopt-listing', {'id': 'other'})[0], 400)
        self.assertEqual(self.call('/api/agent/adopt-listing', {'id': 'other'}, Origin='https://elsewhere.example')[0], 403)
        self.assertEqual(self.call('/api/agent/profile', {}, Origin='https://elsewhere.example')[0], 403)
        self.assertEqual(self.call('/api/agent/overview', **{'X-Workspace-Account': '999'})[0], 409)

    def test_image_quote_preview_route_does_not_generate_or_reserve(self):
        request={'model':'gpt-image-2','size':'1:1','resolution':'2K'}
        with patch.object(server.image_provider,'budget_quote',return_value={'submitted':False,'reserved':False}) as quote,patch.object(server.image_provider,'submit') as generate:
            code,body=self.call('/api/image/budget-quote',request)
        self.assertEqual(code,200);self.assertFalse(body['submitted']);self.assertFalse(body['reserved'])
        quote.assert_called_once_with(request);generate.assert_not_called()

    def test_erp_observation_preserves_stage_and_rejects_concurrent_changes(self):
        _, body = self.call('/api/agent/profile', {'name':'erp-read','store':'Test store','marketplace':'US','shippingTemplate':'FBM','quantity':88})
        _, body = self.call('/api/agent/create', {'goal':'ERP观察','profileId':body['profile']['id'],'productId':'test'})
        tid = body['task']['id']
        before = self.call('/api/agent/task?id='+tid)[1]
        observation = {'draftId':'123','differences':[], 'saved':False,'published':False}
        import agent_erp
        with patch.object(agent_erp, 'observe', return_value=observation):
            code, result = self.call('/api/agent/observe-erp', {'id':tid})
        self.assertEqual(code,200); self.assertEqual(result['observation'],observation)
        after = self.call('/api/agent/task?id='+tid)[1]
        for key in ('status','cursor','results'):
            self.assertEqual(before.get(key),after.get(key))
        self.assertEqual(after['erpObservation'],observation)
        def changed(user, task):
            with closing(agent.connect()) as c, c:
                current=agent.owned(c,user,tid);current['snapshot']['product']['name']='Changed';agent.put(c,current)
            return {'draftId':'wrong'}
        with patch.object(agent_erp,'observe',side_effect=changed):
            self.assertEqual(self.call('/api/agent/observe-erp',{'id':tid})[0],400)
        self.assertEqual(self.call('/api/agent/task?id='+tid)[1]['erpObservation'],observation)

    def test_profile_create_task_detail_and_duplicate(self):
        code, data = self.call('/api/agent/profile', {'name': 'fixture', 'store': 'Test store', 'marketplace': 'US', 'shippingTemplate': 'FBM', 'quantity': 88})
        self.assertEqual(code, 200)
        request = {'goal': '检查', 'profileId': data['profile']['id'], 'productId': 'test'}
        code, result = self.call('/api/agent/create', request)
        self.assertEqual(code, 201)
        tid = result['task']['id']
        self.assertNotIn('snapshot', result['task'])
        self.assertEqual(self.call('/api/agent/create', request)[0], 400)
        code, detail = self.call('/api/agent/task?id=' + tid)
        self.assertEqual(code, 200); self.assertEqual(len(detail['events']), 1)
        code, report = self.call('/api/agent/report?id=' + tid)
        self.assertEqual(code, 200); self.assertEqual(report['reportVersion'], 1)
        self.assertRegex(report['reportSha256'], r'^[a-f0-9]{64}$')
        self.assertEqual(len(report['events']), 1); self.assertNotIn('snapshot', report)
        self.assertNotIn('snapshot', detail)
        self.assertEqual(self.call('/api/agent/pause', {'id': tid})[0], 200)
        self.assertEqual(self.call('/api/agent/download?id=' + tid)[0], 400)
        self.assertEqual(self.call('/api/agent/junfei-plan?id=' + tid)[0], 400)
        self.assertEqual(self.call('/api/agent/task?id=not-owned')[0], 400)
        self.assertEqual(self.call('/api/agent/overview')[0], 200)

    def test_adopt_sourcing_candidate_api_forwards_task_and_url(self):
        seen = {}
        def adopt(user, tid, url):
            seen.update(user=user, tid=tid, url=url)
            return {'id': tid, 'status': 'queued'}
        with patch.object(server.agent_center, 'adopt_sourcing_candidate', side_effect=adopt):
            code, body = self.call('/api/agent/adopt-sourcing-candidate', {
                'id': 'task-1', 'url': 'https://detail.1688.com/offer/705907720182.html'})
        self.assertEqual(code, 200)
        self.assertEqual(body['task']['status'], 'queued')
        self.assertEqual(seen['tid'], 'task-1')
        self.assertEqual(seen['url'], 'https://detail.1688.com/offer/705907720182.html')

    def test_verify_sourcing_candidate_api_forwards_checklist_and_note(self):
        seen = {}
        def verify(user, tid, url, checks, note):
            seen.update(user=user, tid=tid, url=url, checks=checks, note=note)
            return {'id': tid, 'status': 'blocked'}
        checks = {'sameProduct': True, 'exactVariant': True}
        with patch.object(server.agent_center, 'verify_sourcing_candidate', side_effect=verify):
            code, body = self.call('/api/agent/verify-sourcing-candidate', {
                'id': 'task-1', 'url': 'https://detail.1688.com/offer/705907720182.html',
                'checks': checks, 'note': '核对记录'})
        self.assertEqual(code, 200)
        self.assertEqual(seen['checks'], checks)
        self.assertEqual(seen['note'], '核对记录')

    def test_resume_after_review_api_forwards_reconciliation(self):
        seen = {}
        def resume(user, tid, reconciliation):
            seen.update(user=user, tid=tid, reconciliation=reconciliation)
            return {'id': tid, 'status': 'queued'}
        with patch.object(server.agent_center, 'resume_after_review', side_effect=resume):
            code, body = self.call('/api/agent/resume-after-review', {
                'id': 'task-1', 'reconciliation': '已核对外部结果，确认未提交'} )
        self.assertEqual(code, 200)
        self.assertEqual(body['task']['status'], 'queued')
        self.assertEqual(seen['reconciliation'], '已核对外部结果，确认未提交')

    def test_start_queued_api_forwards_account(self):
        with patch.object(server.agent_center, 'start_queued', return_value={'started': [], 'errors': [], 'count': 0}) as start:
            code, body = self.call('/api/agent/start-queued', {})
        self.assertEqual(code, 202); self.assertEqual(body['count'], 0)
        self.assertEqual(start.call_args.args, (1,))

    def test_pause_running_api_forwards_account(self):
        with patch.object(server.agent_center, 'pause_running', return_value={'paused': [], 'errors': [], 'count': 0}) as pause:
            code, body = self.call('/api/agent/pause-running', {})
        self.assertEqual(code, 200); self.assertEqual(body['count'], 0)
        self.assertEqual(pause.call_args.args, (1,))

    def test_selection_intake_api_is_recoverable_and_checks_profile_before_import(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            studio = root / 'studio.sqlite3'
            def workspace():
                with closing(sqlite3.connect(studio)) as c:
                    row = c.execute('SELECT body FROM workspace WHERE id=1').fetchone()
                return json.loads(row[0]) if row else {'products': [], 'copy': {}, 'reviews': {}}
            with closing(sqlite3.connect(studio)) as c, c:
                c.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            with patch.object(server, 'DB', studio), patch.object(agent, 'DATA', root), patch.object(agent, 'DB', root/'tasks.sqlite3'), patch.object(market_research, 'DB', root/'reports.sqlite3'), patch.object(agent, 'load_workspace', side_effect=workspace):
                candidate = market_research.candidate({'asin': 'B012345678', 'title': 'Isolated candidate'}, 'US')
                market_research.save(dict(id='fixture',created=1,status='completed',request={'market':'US','month':'202609'},candidates=[candidate]))
                request = dict(reportId='fixture',asins=['B012345678'],revision=0,queueAgent=True,profileId='other-account')
                self.assertEqual(self.call('/api/selection/import', request, authenticated=False)[0], 401)
                self.assertEqual(self.call('/api/selection/import', request, Origin='https://elsewhere.example')[0], 403)
                self.assertEqual(self.call('/api/selection/import', request)[0], 400)
                self.assertEqual(workspace()['products'], [])
                _, result = self.call('/api/agent/profile', dict(name='Intake US',store='Test',marketplace='US',shippingTemplate='FBM'))
                request['profileId'] = result['profile']['id']
                with patch.object(agent, 'start', side_effect=lambda user, tid: agent.public(agent.detail(user, tid))) as start:
                    code, result = self.call('/api/selection/import', request)
                    self.assertEqual(code, 200)
                    first = result['agentIntake'][0]
                    self.assertEqual(first['status'], 'created')
                    self.assertNotIn('snapshot', first['task'])
                    self.assertEqual(start.call_count, 1)
                    self.assertEqual(self.call('/api/selection/import', request)[0], 409)
                    request['revision'] = result['revision']
                    code, repeat = self.call('/api/selection/import', request)
                    self.assertEqual(code, 200)
                    self.assertEqual(repeat['agentIntake'][0]['status'], 'reused')
                    self.assertEqual(repeat['agentIntake'][0]['task']['id'], first['task']['id'])
                    self.assertEqual(start.call_count, 1)
                    self.assertEqual(len(repeat['state']['products']), 1)
                    automatic = {'reportId':'fixture','autoSelect':True,'limit':10,
                                 'revision':repeat['revision'],'queueAgent':True,'profileId':request['profileId']}
                    code, picked = self.call('/api/selection/import', automatic)
                    self.assertEqual(code, 200)
                    self.assertEqual(picked['autoSelection']['candidates'][0]['asin'], 'B012345678')
                    self.assertEqual(picked['autoSelection']['candidates'][0]['status'], 'review_queue_only')
                    self.assertEqual(picked['agentIntake'][0]['status'], 'reused')

    def test_amazon_page_observation_is_capture_token_scoped_and_candidate_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            studio = Path(folder) / 'studio.sqlite3'
            with patch.object(server, 'DB', studio):
                with server.database() as conn:
                    conn.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)')
                    conn.execute('INSERT INTO workspace VALUES(1,0,?)', (json.dumps({'products': [{
                        'id': 'candidate', 'selectionResearch': {'reference': {'asin': 'B012345678', 'market': 'US'}}
                    }], 'copy': {}, 'reviews': {}}),))
                payload = {'asin':'B012345678','marketplace':'US','url':'https://www.amazon.com/dp/B012345678',
                           'capturedAt':'2026-11-01T12:00:00Z','title':'Observed title','brand':'Observed brand'}
                user = accounts.identify(self.token)
                capture = accounts.capture_token(user)['token']
                self.assertEqual(self.call('/api/selection/capture', payload, authenticated=False)[0], 401)
                code, result = self.call('/api/selection/capture', payload, authenticated=False, **{'X-Capture-Token':capture})
                self.assertEqual(code, 200)
                self.assertIn('不自动满足准入', result['message'])
                with server.database() as conn:
                    state = json.loads(conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
                product = state['products'][0]
                self.assertEqual(product['selectionObservations'][0]['fields']['title'], 'Observed title')
                self.assertNotIn('selectionEvidence', product)
                payload.update(captureType='browser_front_search', url='https://www.amazon.com/s?k=observed+title',
                               searchResults=[{'asin':'B087654321','title':'Possible match'}], resultText='1-48 of over 1,234 results')
                code, _ = self.call('/api/selection/capture', payload, authenticated=False, **{'X-Capture-Token':capture})
                self.assertEqual(code, 200)
                with server.database() as conn:
                    state = json.loads(conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
                self.assertEqual(state['products'][0]['selectionObservations'][-1]['search']['results'][0]['asin'], 'B087654321')
                payload.update(captureType='browser_sellersprite_search',
                               url='https://www.sellersprite.com/v3/product-research',
                               pageTitle='SellerSprite result',
                               visibleRows=[{'asin':'B087654321','text':'Sales rank 1,234'}])
                code, result = self.call('/api/selection/capture', payload, authenticated=False, **{'X-Capture-Token':capture})
                self.assertEqual(code, 200)
                self.assertIn('不自动满足准入', result['message'])
                with server.database() as conn:
                    state = json.loads(conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
                product = state['products'][0]
                self.assertEqual(product['selectionObservations'][-1]['sellerSprite']['rows'][0]['asin'], 'B087654321')
                self.assertNotIn('selectionEvidence', product)
                payload.update(captureType='browser_1688_image_search',
                               url='https://s.1688.com/selloffer/offer_search.htm?keywords=door',
                               offers=[{'offerId':'705907720182','title':'Observed supplier offer',
                                        'url':'https://detail.1688.com/offer/705907720182.html',
                                        'imageUrl':'https://cbu01.alicdn.com/image.jpg',
                                        'priceText':'¥4.66','supplierText':'Supplier','text':'Observed raw row'}])
                code, _ = self.call('/api/selection/capture', payload, authenticated=False, **{'X-Capture-Token':capture})
                self.assertEqual(code, 200)
                with server.database() as conn:
                    state = json.loads(conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
                product = state['products'][0]
                self.assertEqual(product['selectionObservations'][-1]['sourcingSearch']['offers'][0]['offerId'], '705907720182')
                self.assertNotIn('selectionEvidence', product)
                payload['asin'] = 'B000000000'
                self.assertEqual(self.call('/api/selection/capture', payload, authenticated=False, **{'X-Capture-Token':capture})[0], 400)

    def test_seller_store_capture_is_token_scoped_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            studio = Path(folder) / 'studio.sqlite3'
            reports = Path(folder) / 'reports.sqlite3'
            with patch.object(server, 'DB', studio), patch.object(market_research, 'DB', reports):
                with server.database() as conn:
                    conn.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)')
                    conn.execute('INSERT INTO workspace VALUES(1,0,?)', (json.dumps({'products': [], 'copy': {}, 'reviews': {}}),))
                payload = {'url':'https://www.amazon.com/s?me=SELLER123&s=price-asc-rank',
                           'sellerId':'SELLER123','marketplace':'US','capturedAt':'2026-11-01T12:00:00Z',
                           'pageTitle':'Amazon storefront','pageSummary':'1-2 of 2 results',
                           'products':[{'asin':'B012345678','title':'Visible product','brandText':'Brand',
                                        'priceText':'$9.99','imageUrl':'https://m.media-amazon.com/images/I/example.jpg','raw':'Visible card'}]}
                user = accounts.identify(self.token)
                capture = accounts.capture_token(user)['token']
                self.assertEqual(self.call('/api/selection/capture-seller-store', payload, authenticated=False)[0], 401)
                code, result = self.call('/api/selection/capture-seller-store', payload, authenticated=False,
                                         **{'X-Capture-Token':capture})
                self.assertEqual(code, 200)
                self.assertEqual(result['productCount'], 1)
                self.assertTrue(result['reportId'])
                with server.database() as conn:
                    state = json.loads(conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
                self.assertEqual(state['sellerScoutObservations'][0]['sellerId'], 'SELLER123')
                report = market_research.get(result['reportId'])
                self.assertEqual(report['candidates'][0]['asin'], 'B012345678')
                self.assertIsNone(report['candidates'][0]['monthlySales'])
                self.assertIn('不代表近7天新品', result['message'])


if __name__ == '__main__': unittest.main()
