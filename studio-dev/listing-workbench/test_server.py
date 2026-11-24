import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import provider
import server
import secrets_store
import accounts


VALID_BULLETS = [
    f'[Feature {i}] Supported detail {i}. ' + 'The supplied description gives the shopper additional context for comparing the available options and understanding how the item is intended to be used. Review the product information before choosing a configuration for your intended use.'
    for i in range(5)
]
VALID_TERMS = ('coat outerwear garment apparel layering weekend daily casual travel walking streetwear '
               'classic wardrobe autumn coldseason outdoor commute leisure clothing overlayer packing '
               'workday transitional midweight styling relaxed')
VALID_BULLET_TEXT = '\n'.join(VALID_BULLETS)


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.text_provider=patch.dict(provider.SETTINGS,{'provider':'deepseek'})
        self.text_provider.start();self.addCleanup(self.text_provider.stop)
        self.polish=patch.object(provider,'polish_listing',side_effect=lambda draft,**_:draft)
        self.polish.start();self.addCleanup(self.polish.stop)
        self.bullet_review=patch.object(provider,'review_listing_bullets',return_value=[])
        self.bullet_review.start();self.addCleanup(self.bullet_review.stop)
        self.bullet_edit=patch('visual_studio.model_json',side_effect=ValueError('offline optional editor'))
        self.bullet_edit.start();self.addCleanup(self.bullet_edit.stop)
        self.proxy=patch.object(server.account_spaces,'needs_proxy',return_value=False);self.proxy.start();self.addCleanup(self.proxy.stop)
        # Keep unrelated listing tests offline; dedicated tests cover backend expansion.
        self.backend_expansion=patch.object(provider,'research_json',return_value={'keywords':[]})
        self.backend_expansion.start();self.addCleanup(self.backend_expansion.stop)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.data_patch=patch.object(provider.app_paths,'DATA',Path(cls.temp.name))
        cls.data_patch.start()
        cls.secret_patch = patch.object(secrets_store, 'ROOT', Path(cls.temp.name) / 'credentials')
        cls.secret_patch.start()
        cls.preference_patch=patch.object(provider,'PREFERENCES',Path(cls.temp.name)/'model-preferences.json')
        cls.preference_patch.start()
        server.DATA = Path(cls.temp.name)
        (server.DATA / 'uploads').mkdir()
        server.DB = server.DATA / 'test.sqlite3'
        cls.account_patch = patch.object(accounts, 'DB', server.DATA / 'accounts.sqlite3')
        cls.account_patch.start()
        accounts.register({'username':'testadmin','password':'test-password-12345'}, setup=True)
        cls.token, _ = accounts.login({'username':'testadmin','password':'test-password-12345'}, 'test')
        with server.database() as conn:
            conn.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)')
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.temp.cleanup()
        cls.secret_patch.stop()
        cls.preference_patch.stop()
        cls.data_patch.stop()
        cls.account_patch.stop()

    def call(self, path, data=None, origin=None):
        headers = {'Content-Type': 'application/json', 'Cookie': 'studio_session='+self.token}
        if origin:
            headers['Origin'] = origin
        body = json.dumps(data).encode() if data is not None else None
        try:
            response = urllib.request.urlopen(urllib.request.Request(self.base + path, data=body, headers=headers))
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)
        with response:
            return response.status, json.load(response)

    def test_selection_import_conflict_is_atomic(self):
        code, current = self.call('/api/state')
        revision = current['revision']
        with patch.object(server.market_research, 'import_products', return_value={'added':[], 'skipped':[]}) as imp:
            code, result = self.call('/api/selection/import', {'reportId':'example','asins':['B012345678'],'revision':revision-1})
            self.assertEqual(code,409)
            imp.assert_not_called()
            code, result = self.call('/api/selection/import', {'reportId':'example','asins':['B012345678'],'revision':revision})
            self.assertEqual(code,200)
            self.assertEqual(result['revision'],revision+1)
            imp.assert_called_once()

    def test_product_table_download_is_authenticated_and_scoped_to_saved_products(self):
        from openpyxl import load_workbook
        with server.database() as conn:
            previous=conn.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
            conn.execute('INSERT OR REPLACE INTO workspace VALUES (1,1,?)',
                (json.dumps({'products':[{'id':'export-one','name':'Export item','sourceImport':{
                    'asin':'B0HQ6T361R','market':'US','amazon':{'title':'Original Amazon title'}}}]}),))
        try:
            body=json.dumps({'ids':['export-one']}).encode()
            headers={'Content-Type':'application/json','Cookie':'studio_session='+self.token}
            with patch.object(server.image_provider,'jobs',return_value={'jobs':[]}):
                with urllib.request.urlopen(urllib.request.Request(self.base+'/api/products/export-table',data=body,headers=headers)) as response:
                    self.assertEqual(response.headers['Content-Type'],'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    self.assertIn('products.xlsx',response.headers['Content-Disposition'])
                    sheet=load_workbook(io.BytesIO(response.read())).active
                    self.assertEqual(sheet['D2'].value,'B0HQ6T361R')
                self.assertEqual(self.call('/api/products/export-table',{'ids':['not-owned']})[0],400)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(self.base+'/api/products/export-table',data=body,
                    headers={'Content-Type':'application/json'}))
            self.assertEqual(caught.exception.code,401)
        finally:
            with server.database() as conn:
                conn.execute('DELETE FROM workspace WHERE id=1')
                if previous:conn.execute('INSERT INTO workspace VALUES (1,?,?)',previous)

    def test_review_routes_and_invalid_input(self):
        with patch('server.review_insights.collect', return_value={'samples': []}) as collect:
            code, report = self.call('/api/reviews/fetch', {'market': 'UK', 'asins': 'B0FVS1X3SP'})
            self.assertEqual(code, 200)
            self.assertEqual(report['samples'], [])
            collect.assert_called_once()
        self.assertEqual(self.call('/api/reviews/analyse', {'report': {}})[0], 400)
        self.assertEqual(self.call('/api/reviews/fetch', {'market': 'UK', 'asins': 'invalid'})[0], 400)

    def test_custom_listing_prompt_settings_are_removed(self):
        self.assertEqual(self.call('/api/listing/prompt')[0], 404)
        self.assertEqual(self.call('/api/listing/prompt', {'text': 'Custom instruction'})[0], 404)

    def test_listing_uses_metric_volumes_without_summing_or_sending_cost(self):
        captured={}
        def stop(request, **kwargs):
            captured.update(json.loads(request.data))
            raise urllib.error.URLError('test stops before paid call')
        product={'name':'test jacket','material':'polyester','purchasePrice':'CNY 50','competitorResearch':{'UK':{'keywords':[
            {'phrase':'winter jacket','metrics':[{'searches':1200},{'searches':'1500'}]},
            {'phrase':'coat','metrics':[{'searches':0}]},
            {'phrase':'unknown','metrics':[{'searches':None}]}
        ]}}}
        with patch.dict(provider.SETTINGS, {'api_key':'test','model':'test'}), patch('provider.urlopen', side_effect=stop):
            with self.assertRaises(ValueError):provider.generate_listing(product,'UK')
        payload=json.loads(captured['messages'][1]['content'])
        facts=payload['confirmed_product_facts'];plan=facts['keywordPlan']
        self.assertEqual(plan[0]['monthlySearches'],1500)
        self.assertEqual(plan[0]['volumePriority'],'primary_500_8000')
        self.assertEqual(plan[1]['monthlySearches'],0)
        self.assertIsNone(plan[2]['monthlySearches'])
        self.assertNotIn('purchasePrice',facts)
        prompt = captured['messages'][0]['content']
        self.assertIn('[LISTING EDITORIAL SKILLS', payload['editorial_guidance']['skills'])
        self.assertNotIn('customStyle', payload['editorial_guidance'])
        self.assertIn('500–8000', prompt)
        self.assertIn('CURRENT STAGE: FINAL LISTING', prompt)
        self.assertIn('Generate one title, one highlights string, one set of five bullets', prompt)
        self.assertIn('60–75 characters inclusive, including spaces', prompt)
        self.assertIn('125 characters including spaces', prompt)
        self.assertIn('square brackets', prompt)
        self.assertIn('Maximum 249 UTF-8 bytes', prompt)
        self.assertNotIn('editorialCandidates', facts)
        self.assertNotIn('bullets_a', prompt)
        self.assertNotIn('compliance_notes', prompt)
        self.assertIn('PRODUCT DESCRIPTION FORMAT', prompt)
        self.assertIn(provider.DESCRIPTION_NOTES, prompt)

    def test_generation_ignores_extra_alternatives_and_keeps_one_listing(self):
        copy={'title':"Women's Winter Jacket with Stand Collar and Front Zip Closure",'highlights':'Polyester','bullets':VALID_BULLET_TEXT,'description':'Jacket for Layering\nMaterial: Polyester\n\nProduct: Jacket','terms':'winter winter '+VALID_TERMS,'zh':'中文','warnings':'',
              'editorialPlan':{'audience':'unknown'},'alternatives':{'titles':['Valid title','x'*76,123], 'bulletsConversion':['a','b','c','d','e'],'bulletsQuestions':['invalid']}}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(copy)}}]}
        with patch.dict(provider.SETTINGS, {'api_key':'test','model':'test'}), patch('provider.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
            result=provider.generate_listing({'name':'Jacket','material':'polyester'},'UK')['copy']
        self.assertNotIn('alternatives',result)
        self.assertEqual(len(result['bullets'].splitlines()),5)
        self.assertEqual(result['title'],"Women's Winter Jacket with Stand Collar and Front Zip Closure")
        self.assertIn('unknown',result['editorialPlan'])
        self.assertEqual(result['terms'],VALID_TERMS)
        self.assertIn('version',result['listingSkills'])
        self.assertIn('conversion',result['listingSkills']['rules'])

    def test_bullet_editor_repairs_invalid_format_or_rejects_result(self):
        draft={'title':"Women's Winter Jacket with Stand Collar and Front Zip Closure",'highlights':'Stand collar','bullets':'One\nTwo\nThree\nFour\nFive',
               'description':'Jacket for Layering\nMaterial: Polyester\n\nProduct: Jacket','terms':VALID_TERMS,'zh':'','warnings':''}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}
        product={'name':'Jacket','material':'polyester'}
        with patch.dict(provider.SETTINGS,{'api_key':'test','model':'test'}),patch('provider.text_completion',return_value=response):
            with patch('visual_studio.model_json',return_value={'bullets':VALID_BULLETS,'translation':['译文 '+str(i) for i in range(5)]}):
                result=provider.generate_listing(product,'UK')['copy']
                self.assertEqual(result['bullets'].splitlines(),VALID_BULLETS)
            with patch('visual_studio.model_json',return_value={'bullets':['Supplier details not supplied']*5}), \
                 self.assertRaisesRegex(ValueError,'五点格式未通过检查'):
                provider.generate_listing(product,'UK')

    def test_local_rewrite_validation(self):
        with patch('provider.research_json',return_value={'keywords':[],'text':"Women's Winter Jacket with Stand Collar and Front Zip Closure"}) as model:
            result=provider.rewrite_field({'field':'title','market':'UK','mode':'natural','text':'Old title','product':{'material':'polyester','purchasePrice':'private'}})
            self.assertEqual(result['text'],"Women's Winter Jacket with Stand Collar and Front Zip Closure")
            self.assertNotIn('purchasePrice',model.call_args.args[1]['facts'])
            self.assertIn('[LISTING EDITORIAL SKILLS',model.call_args.args[1]['editorial_guidance']['skills'])
            self.assertNotIn('customStyle',model.call_args.args[1]['editorial_guidance'])
            self.assertNotIn('CURRENT STAGE: FINAL LISTING',model.call_args.args[0])
        with patch('provider.research_json',return_value={'keywords':[],'text':'one line'}):
            with self.assertRaises(ValueError):provider.rewrite_field({'field':'bullets','market':'UK','mode':'natural','text':'Old','product':{}})
        with self.assertRaises(ValueError):provider.rewrite_field({'field':'unknown'})

    def test_local_rewrite_receives_measured_keyword_volume(self):
        product={'name':'Jacket','material':'polyester','competitorResearch':{'UK':{'keywords':[{'phrase':'jacket','metrics':[{'searches':1200},{'searches':'1800'}]},{'phrase':'coat','selected':False}]}}}
        with patch('provider.research_json',return_value={'text':"Women's Winter Jacket with Stand Collar and Front Zip Closure"}) as model:
            provider.rewrite_field({'field':'title','market':'UK','mode':'keywords','text':'Old','product':product})
        self.assertEqual([(item['phrase'], item['monthlySearches'], item['volumePriority']) for item in model.call_args.args[1]['keywordPlan']], [('jacket', 1800, 'primary_500_8000')])

    def test_title_field_limits_include_spaces(self):
        provider.validate_title_fields({'title': 'a'*74+' ', 'highlights': 'b'*125})
        for copy in ({'title': 'a'*75+' ', 'highlights': 'ok'},
                     {'title': 'ok', 'highlights': 'b'*126},
                     {'title': 'ok', 'highlights': ''}):
            with self.assertRaises(ValueError):
                provider.validate_title_fields(copy)

    def test_generation_repairs_only_oversized_fields_once(self):
        draft={'title':"Women's Winter Jacket with Stand Collar and Front Zip Closure",'highlights':'x'*132,'bullets':VALID_BULLETS,'description':'Jacket for Layering\nMaterial: Polyester\n\nProduct: Jacket','terms':VALID_TERMS,'zh':'old','warnings':[]}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}
        repair={'keywords':[],'fields':{'highlights':'Polyester, fixed hood'},'translations':{'highlights':'聚酯纤维，固定帽子'}}
        with patch.dict(provider.SETTINGS,{'api_key':'test','model':'test'}),patch('provider.urlopen',return_value=io.BytesIO(json.dumps(response).encode())),patch('provider.research_json',return_value=repair) as model:
            result=provider.generate_listing({'name':'Jacket','material':'polyester'},'UK')['copy']
        self.assertEqual(result['highlights'],'Polyester, fixed hood')
        self.assertEqual(result['translations']['highlights'],'聚酯纤维，固定帽子')
        self.assertEqual(model.call_count,1)
        self.assertEqual(model.call_args.args[1]['fields'],{'highlights':'x'*132})

    def test_backend_does_not_become_a_variation_inventory(self):
        self.assertEqual(provider.clean_backend_variations('outerwear XS S M L XL 2XL navy khaki grey black red'),'outerwear')
        self.assertEqual(provider.clean_backend_variations('black winter outerwear'),'black winter outerwear')

    def test_listing_editor_uses_empty_draft_and_product_site(self):
        html = (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')
        js = (Path(__file__).parent / 'enhancements.js').read_text(encoding='utf-8')
        self.assertIn("function defaults(p){return {highlights:'',title:'',bullets:'',description:'',terms:'',zh:''}}", html)
        self.assertNotIn("['US','美国站'],['UK','英国站']", js)
        self.assertIn("market=productMarket;", html)
        self.assertIn('listingKeyConfigured', js)
        self.assertNotIn("Women's Cotton Crew Neck T-Shirt", html)
        prompt = (Path(__file__).parent / 'listing-generation-prompt.txt').read_text(encoding='utf-8')
        self.assertNotIn('effective July 27, 2026', prompt)

    def test_database_save_read_and_conflict(self):
        state = {'products': [{'id': 'TEST-1', 'name': '测试产品', 'cat': '服装', 'owner': '测试', 'status': '待补资料', 'color': '#aabbcc', 'colors': 1, 'sizes': 1}], 'copy': {}, 'reviews': {}}
        revision = self.call('/api/state')[1]['revision']
        self.assertEqual(self.call('/api/state', {'revision': revision, 'state': state})[0], 200)
        state['products'][0].update(brand='Generic', manufacturer='Generic')
        snapshot=self.call('/api/state')[1]
        saved=snapshot['state']
        sku=saved['products'][0]['sku']
        self.assertRegex(sku,r'^TESTADMIN\d{14}$')
        state['products'][0]['sku']=sku
        self.assertEqual(saved,state)
        self.assertEqual(self.call('/api/state', {'revision':snapshot['revision'],'state':state})[0],200)
        self.assertEqual(self.call('/api/state')[1]['state']['products'][0]['sku'],sku)
        self.assertEqual(self.call('/api/state', {'revision': revision, 'state': state})[0], 409)

    def test_large_library_delete_restore_and_conflict(self):
        product = {'id': 'LARGE-1', 'name': 'Large library', 'cat': '服装',
                   'owner': 'test', 'status': '待补资料', 'color': '#aabbcc',
                   'colors': 1, 'sizes': 1, 'notes': 'x' * (18 * 1024 * 1024)}
        state = {'products': [product], 'copy': {}, 'reviews': {}}
        revision = self.call('/api/state')[1]['revision']
        code, saved = self.call('/api/state', {'revision': revision, 'state': state})
        self.assertEqual(code, 200)
        state['products'] = []
        state['deletedProducts'] = [{'product': product, 'deletedAt': '2026-11-04'}]
        code, deleted = self.call('/api/state', {'revision': saved['revision'], 'state': state})
        self.assertEqual(code, 200)
        current = self.call('/api/state')[1]
        self.assertEqual(current['state']['products'], [])
        self.assertEqual(current['state']['deletedProducts'][0]['product']['notes'], product['notes'])
        self.assertEqual(self.call('/api/state', {'revision': saved['revision'], 'state': state})[0], 409)
        state['products'] = [product]
        state['deletedProducts'] = []
        self.assertEqual(self.call('/api/state', {'revision': deleted['revision'], 'state': state})[0], 200)
        self.assertEqual(self.call('/api/state')[1]['state']['products'][0]['id'], 'LARGE-1')

    def test_state_size_limit_remains_enforced(self):
        revision = self.call('/api/state')[1]['revision']
        with patch.object(server, 'STATE_BODY_LIMIT', 64):
            code, result = self.call('/api/state', {'revision': revision, 'state': {'products': [], 'copy': {}, 'reviews': {}, 'notes': 'x' * 100}})
        self.assertEqual(code, 400)
        self.assertIn('超过接口上限', result['error'])
        self.assertEqual(self.call('/api/state')[1]['revision'], revision)

    def test_reject_invalid_product(self):
        self.assertEqual(self.call('/api/state', {'revision': 0, 'state': {'products': [{}], 'copy': {}, 'reviews': {}}})[0], 400)

    def test_cross_origin_write_rejected(self):
        self.assertEqual(self.call('/api/settings', {}, 'https://example.com')[0], 403)

    def test_credential_never_returned(self):
        status, result = self.call('/api/settings', {'model': 'test-model', 'api_key': 'fake-test-key'})
        self.assertEqual(status, 200)
        self.assertTrue(result['hasKey'])
        self.assertNotIn('fake-test-key', json.dumps(self.call('/api/settings')))
        self.call('/api/settings', {'model': 'test-model', 'clearKey': True})

    def test_missing_configuration_blocks_generation(self):
        status, _ = self.call('/api/generate/listing', {'product': {'name': 't'}, 'market': 'US'})
        self.assertEqual(status, 400)

    def test_upload_validation_and_static_boundary(self):
        req = urllib.request.Request(self.base + '/api/upload', data=b'<html>not image</html>', method='POST', headers={'Cookie':'studio_session='+self.token})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req)
        self.assertEqual(error.exception.code, 400)
        # A valid tiny PNG; no external network requests.
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')
        req = urllib.request.Request(self.base + '/api/upload', data=png, method='POST', headers={'Cookie':'studio_session='+self.token})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 201)
            path = json.load(response)['url']
        with urllib.request.urlopen(urllib.request.Request(self.base + path, headers={'Cookie':'studio_session='+self.token})) as response:
            self.assertEqual(response.read(), png)
        self.assertEqual(self.call('/data/studio.sqlite3')[0], 404)

    def test_all_market_generation_routes_target_language(self):
        copy = dict(title="Women's Cotton Top with Long Sleeves and a Classic Round Neckline", highlights='Layering', bullets=VALID_BULLET_TEXT, description='Product Heading\nMaterial: Cotton\n\nProduct: Clothing', terms=VALID_TERMS, zh='中文', warnings='')
        for market, language in provider.MARKET_LANGUAGES.items():
            with self.subTest(market=market):
                locale=provider.DESCRIPTION_LOCALES.get(market)
                label=locale[0] if locale else 'Product'
                copy['description']='Product Heading\nMaterial: Cotton\n\n'+label+': Clothing'
                response = io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(copy)}, 'finish_reason': 'stop'}]}).encode())
                with patch.dict(provider.SETTINGS, {'model': 'test', 'api_key': 'fake'}), patch('provider.urlopen', return_value=response) as request:
                    result = provider.generate_listing({'name': 'Test', 'material': 'cotton'}, market)
                    body = json.loads(request.call_args.args[0].data)
                    facts = json.loads(body['messages'][1]['content'])
                    self.assertEqual(facts['target_language'], language)
                    self.assertEqual(result['copy']['title'], "Women's Cotton Top with Long Sleeves and a Classic Round Neckline")
        provider.validate_title_fields({'title': 'あ'*75, 'highlights': '商品亮点'}, 'JP')
        with self.assertRaises(ValueError):
            provider.validate_title_fields({'title': 'あ'*76, 'highlights': '商品亮点'}, 'JP')

    def test_adapter_mock_and_fact_allowlist(self):
        provider.configure({'model': 'test-model', 'api_key': 'fake-test-key'})
        copy = dict(title="Women's Cotton Top with Long Sleeves and a Classic Round Neckline", highlights='Everyday casual wear', bullets=VALID_BULLET_TEXT, description='Cotton Top\nFabric Name: Cotton\nSize: M\n\n1 Pcs x Cotton top', terms=VALID_TERMS, zh='中文', warnings='请审核', contentAudit={'keywordPlacements':[{'phrase':'cotton top','placement':'title','reason':'相关'}], 'omittedKeywords':[], 'factChecks':['核对材质']})
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(copy)}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 10}}).encode())
        facts = {'name': 'Top', 'material': 'cotton', 'dimensions': 'M', 'packageContents': 'one top', 'assets': [{'url': '/private.png'}], 'owner': 'private-owner', 'competitorResearch': {'UK': {'keywords': [{'phrase':'cotton top','monthlySearches':2500,'selected':True},{'phrase':'unsupported fabric','monthlySearches':6000,'selected':True}]}}}
        with patch('provider.urlopen', return_value=response) as mocked:
            result = provider.generate_listing(facts, 'UK')
            body = mocked.call_args.args[0].data.decode()
            self.assertEqual(mocked.call_args.args[0].full_url, 'https://api.deepseek.com/chat/completions')
            self.assertNotIn('private-owner', body)
            self.assertNotIn('/private.png', body)
            sent = json.loads(json.loads(body)['messages'][1]['content'])['confirmed_product_facts']
            self.assertEqual(sent['keywordPlanSummary']['primary_500_8000'], ['unsupported fabric', 'cotton top'])
            self.assertEqual(result['copy']['contentAudit']['keywordPlacements'][0]['phrase'], 'cotton top')
            self.assertIn('unsupported fabric', result['copy']['warnings'])
            self.assertIn('关键词落位说明未覆盖', result['copy']['warnings'])
        provider.configure({'model': 'test-model', 'clearKey': True})

    def test_adapter_malformed_output_preserves_failure(self):
        provider.configure({'model': 'test-model', 'api_key': 'fake-test-key'})
        response = io.BytesIO(b'{"choices":[{"message":{"content":"not json"}}]}')
        with patch('provider.urlopen', return_value=response), self.assertRaises(ValueError):
            provider.generate_listing({'name': 'Top', 'material': 'cotton', 'dimensions': 'M', 'packageContents': 'one top'}, 'US')
        provider.configure({'model': 'test-model', 'clearKey': True})

    def test_collected_facts_generate_without_package_contents(self):
        provider.configure({'model': 'test-model', 'api_key': 'fake-test-key'})
        copy = dict(title="Women's Fleece Jacket with Stand Collar and Front Zip Closure", highlights='For everyday layering', bullets=VALID_BULLET_TEXT, description='Jacket for Layering\nMaterial: Polyester\n\nProduct: Jacket', terms=VALID_TERMS, zh='中文', warnings='')
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(copy)}, 'finish_reason': 'stop'}]}).encode())
        try:
            with patch('provider.urlopen', return_value=response):
                result = provider.generate_listing({'name': 'Jacket', 'material': 'polyester', 'dimensions': 'S,M,L'}, 'UK')
                self.assertIn('包装内容', result['copy']['warnings'])
        finally:
            provider.configure({'model': 'test-model', 'clearKey': True})

    def test_key_test_fetches_models_without_saving_key(self):
        response = io.BytesIO(b'{"data":[{"id":"deepseek-flash"},{"id":"deepseek-v4-pro"},{"id":"deepseek-flash"}]}')
        with patch('provider.urlopen', return_value=response) as mocked:
            status, result = self.call('/api/settings/test', {'api_key': 'temporary-test-key'})
            self.assertEqual(status, 200)
            self.assertEqual(result['models'], ['deepseek-flash', 'deepseek-v4-pro'])
            self.assertEqual(mocked.call_args.args[0].full_url, 'https://api.deepseek.com/models')
            self.assertEqual(mocked.call_args.args[0].get_method(), 'GET')
        self.assertNotIn('temporary-test-key', json.dumps(provider.settings_public()))

    def test_settings_reject_invalid_replacement_and_record_saved_key_authentication(self):
        with patch('provider.urlopen', return_value=io.BytesIO(b'{"data":[{"id":"test-model"}]}')):
            status, result = self.call('/api/settings', {'model':'test-model','api_key':'valid-test-key','verifyKey':True})
        self.assertEqual(status, 200)
        self.assertEqual(result['credentialStatus']['status'], 'verified')
        rejected = urllib.error.HTTPError('https://api.deepseek.com/models',401,'invalid',None,None)
        with patch('provider.urlopen', side_effect=rejected):
            status, result = self.call('/api/settings', {'model':'test-model','api_key':'wrong-test-key','verifyKey':True})
            self.assertEqual(status, 400)
            self.assertEqual(secrets_store.load('deepseek'), 'valid-test-key')
            self.assertEqual(provider.settings_public()['credentialStatus']['status'], 'verified')
            self.assertEqual(self.call('/api/settings/test', {})[0], 400)
        self.assertEqual(provider.settings_public()['credentialStatus']['status'], 'unauthorized')
        self.call('/api/settings', {'model':'test-model','clearKey':True})

    def test_key_test_auth_error_is_readable(self):
        error = urllib.error.HTTPError('https://api.deepseek.com/models', 401, 'Unauthorized', {}, None)
        with patch('provider.urlopen', side_effect=error):
            status, result = self.call('/api/settings/test', {'api_key': 'fake-key'})
            self.assertEqual(status, 400)
            self.assertIn('认证失败', result['error'])

    def test_creative_skill_api_permissions_and_version_conflicts(self):
        import creative_skills
        with patch.object(creative_skills,'DB',server.DATA/'skills-test.sqlite3'):
            code,data=self.call('/api/creative-skills')
            self.assertEqual(code,200);self.assertTrue(data['editable'])
            payload={'version':data['version'],'rules':data['rules']}
            self.assertEqual(self.call('/api/creative-skills',payload)[0],200)
            self.assertEqual(self.call('/api/creative-skills',payload)[0],400)
            with patch.object(accounts,'identify',return_value={'id':'staff','role':'employee'}):
                self.assertTrue(self.call('/api/creative-skills')[1]['editable'])
                self.assertEqual(self.call('/api/creative-skills',payload)[0],400)

    def test_listing_skills_are_separate_and_admin_only(self):
        import listing_skills
        import creative_skills
        with patch.object(listing_skills,'DB',server.DATA/'listing-skills-test.sqlite3'),patch.object(creative_skills,'DB',server.DATA/'image-skills-separate.sqlite3'):
            code,data=self.call('/api/listing-skills')
            self.assertEqual(code,200)
            rules=dict(data['rules']);rules['conversion']='Custom editorial rule'
            payload={'version':data['version'],'rules':rules}
            self.assertEqual(self.call('/api/listing-skills',payload)[0],200)
            self.assertEqual(self.call('/api/listing-skills')[1]['rules']['conversion'],'Custom editorial rule')
            self.assertEqual(self.call('/api/creative-skills')[1]['version'],0)
            with patch.object(accounts,'identify',return_value={'id':2,'role':'employee'}):
                self.assertTrue(self.call('/api/listing-skills')[1]['editable'])
                self.assertEqual(self.call('/api/listing-skills',payload)[0],400)

    def test_reveal_requires_same_origin_and_explicit_request(self):
        with patch.dict(provider.SETTINGS, {'api_key':'fake-test-secret'}):
            self.assertEqual(self.call('/api/credentials/reveal',{'service':'deepseek'})[0],403)
            self.assertEqual(self.call('/api/credentials/reveal',{'service':'deepseek'},'https://example.com')[0],403)
            code,data=self.call('/api/credentials/reveal',{'service':'deepseek'},self.base)
            self.assertEqual(code,200)
            self.assertEqual(data['key'],'fake-test-secret')
            self.assertNotIn('fake-test-secret',json.dumps(self.call('/api/settings')[1]))


if __name__ == '__main__':
    unittest.main()
