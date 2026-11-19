import io
import json
import unittest
from unittest.mock import patch
import sellersprite
import competitors


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {'Content-Type': 'application/json'}


class SellerSpriteTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.cache_tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.cache_tmp.cleanup)
        self.cache_patch=patch('sellersprite_cache.DB',Path(self.cache_tmp.name)/'shared.sqlite3')
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def test_shared_cache_reuses_across_clients_and_preserves_parameters(self):
        import sellersprite_cache
        a=sellersprite.Client('first');b=sellersprite.Client('second')
        with patch.object(a,'_call_remote',return_value={'title':'Robe'}) as first,patch.object(b,'_call_remote',return_value={'title':'Other'}) as second:
            self.assertEqual(a.call('asin_detail',{'asin':'b07rknspbr','marketplace':'de'}),{'title':'Robe'})
            self.assertEqual(b.call('asin_detail',{'marketplace':'DE','asin':'B07RKNSPBR'}),{'title':'Robe'})
            second.assert_not_called()
            b.call('asin_detail',{'marketplace':'US','asin':'B07RKNSPBR'})
            second.assert_called_once()
        self.assertEqual(sellersprite_cache.stats()['hits'],1)

    def test_cache_expiry_errors_and_empty_results(self):
        import sellersprite_cache
        a=sellersprite.Client('key');args={'asin':'B07RKNSPBR','marketplace':'DE'}
        with patch.object(a,'_call_remote',side_effect=[ValueError('failed'),{}, {'title':'Robe'},{'title':'Fresh'}]) as remote:
            with self.assertRaises(ValueError):a.call('asin_detail',args)
            self.assertEqual(a.call('asin_detail',args),{})
            self.assertEqual(a.call('asin_detail',args),{'title':'Robe'})
            with sellersprite_cache.connection() as c:c.execute('UPDATE cache SET expires=0')
            self.assertEqual(a.call('asin_detail',args),{'title':'Fresh'})
            self.assertEqual(remote.call_count,4)

    def test_cache_concurrent_requests_fetch_once(self):
        import sellersprite_cache,time
        from concurrent.futures import ThreadPoolExecutor
        def fetch():
            time.sleep(.1)
            return {'items':[{'keyword':'robe'}]}
        with patch('sellersprite_cache.time.sleep', wraps=time.sleep),patch.object(sellersprite.Client,'_call_remote',side_effect=lambda *a:fetch()) as remote:
            with ThreadPoolExecutor(2) as pool:
                results=list(pool.map(lambda _:sellersprite.Client('key').call('keyword_miner',{'keyword':'robe','marketplace':'DE','page':1}),range(2)))
            self.assertEqual(results[0],results[1])
            self.assertEqual(remote.call_count,1)

    def test_mining_merge_reselection_and_unselected_defaults(self):
        sources = [{'asin': 'B0FVS1X3SP', 'status': 'ok', 'title': 'Fleece coat', 'bullets': [],
            'description': '', 'brand': '', 'limitations': [], 'keywordData': [
                {'keyword': 'fleece coat', 'searches': 530, 'rankPosition': {'position': 8}}]}]
        mining = [{'seed': 'fleece coat', 'status': 'ok', 'items': [
            {'keyword': 'fleece coat', 'searches': 530},
            {'keyword': 'warm fleece coat', 'searches': 320},
            {'keyword': 'unrelated jacket', 'searches': None}]}]
        with patch('competitors.sellersprite.read_sources', return_value=sources), \
             patch('competitors.sellersprite.mine_keywords', side_effect=[mining, []]) as mine, \
             patch('competitors.provider.research_json', side_effect=[
                 {'keywords': [{'phrase': 'fleece coat', 'placement': 'bullets',
                                'productEvidence': [{'field': 'features', 'quote': 'warm fleece coat'}]}]},
                 {'keywords': [{'phrase': 'warm fleece coat', 'placement': 'bullets',
                                'productEvidence': [{'field': 'features', 'quote': 'warm fleece coat'}]},
                               {'phrase': 'invented words'}]}]):
            report = competitors.analyse({'market': 'UK', 'asins': 'B0FVS1X3SP', 'source': 'sellersprite',
                                          'mineKeywords': True, 'facts': {'features': 'warm fleece coat'}})
        self.assertEqual(mine.call_count, 2)
        self.assertEqual(mine.call_args.kwargs, {'search_range': (500, 8000)})
        self.assertEqual(len(report['keywords']), 3)
        self.assertEqual(report['keywords'][0]['phrase'], 'warm fleece coat')
        self.assertEqual(report['keywords'][0]['metrics'][0]['searches'], 320)
        self.assertEqual(report['keywords'][0]['sourceAsins'], [])
        self.assertIsNone(report['keywords'][0]['metrics'][0]['naturalRank'])
        merged = report['keywords'][1]
        self.assertEqual(set(merged['origins']), {'竞品反查', '关键词挖掘'})
        self.assertFalse(merged['selected'])
        self.assertFalse(merged['selectedByModel'])

    def test_miner_parameters_and_partial_failure(self):
        with patch('sellersprite.Client') as client:
            call = client.return_value.connect.return_value.call
            call.side_effect = [{'items': [{'keyword': 'coat', 'searches': 0}], 'total': 1}, ValueError('额度不足')]
            result = sellersprite.mine_keywords(['coat', 'coat', 'jacket'], 'UK')
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['items'][0]['searches'], 0)
        self.assertEqual(result[1]['status'], 'failed')
        self.assertEqual(call.call_args_list[0].args[0], 'keyword_miner')
        self.assertEqual(call.call_args_list[0].args[1]['keyword'], 'coat')

    def test_bullet_miner_sends_range_and_checks_returned_monthly_searches(self):
        with patch('sellersprite.Client') as client:
            connected = client.return_value.connect.return_value
            connected.tools = {'keyword_miner': {'inputSchema': {'properties': {'request': {
                'properties': {'minSearch': {}, 'maxSearch': {}},
            }}}}}
            connected.call.return_value = {'total': 4, 'items': [
                {'keyword': 'below', 'searches': 499},
                {'keyword': 'lower boundary', 'searches': 500},
                {'keyword': 'upper boundary', 'searches': 8000},
                {'keyword': 'above', 'searches': 8001},
            ]}
            result = sellersprite.mine_keywords(['coat'], 'US', search_range=(500, 8000))[0]
            params = connected.call.call_args.args[1]
            self.assertEqual((params['minSearch'], params['maxSearch']), (500, 8000))
            self.assertEqual(result['searchRange'], [500, 8000])
            self.assertEqual([row['keyword'] for row in result['items']], ['lower boundary', 'upper boundary'])

    def test_miner_paginates_and_preserves_partial_results(self):
        first=[{'keyword':'coat '+str(i),'searches':500,'purchaseRate':0.1} for i in range(100)]
        with patch('sellersprite.Client') as client:
            call=client.return_value.connect.return_value.call
            call.side_effect=[{'items':first,'total':250},{'items':[{'keyword':'extra','purchaseRate':0.2}],'total':250}]
            result=sellersprite.mine_keywords(['coat'],'US')[0]
        self.assertEqual(result['pages'],2)
        self.assertEqual(len(result['items']),101)
        self.assertEqual(call.call_args_list[1].args[1]['page'],2)
        with patch('sellersprite.Client') as client:
            client.return_value.connect.return_value.call.side_effect=[{'items':first,'total':250},ValueError('quota')]
            result=sellersprite.mine_keywords(['coat'],'US')[0]
        self.assertEqual(result['status'],'partial')
        self.assertEqual(len(result['items']),100)

    def test_nested_traffic_request_preserves_search_volume(self):
        client = sellersprite.Client('key')
        client.tools = {'traffic_keyword': {'inputSchema': {'properties': {'request': {
            'type': 'object', 'properties': {k: {} for k in ('asin', 'marketplace', 'page', 'size')},
            'required': ['asin', 'marketplace']}}, 'required': ['request']}}}
        args = {'asin': 'B0FVS1X3SP', 'marketplace': 'UK', 'page': 1, 'size': 100}
        with patch.object(client, 'rpc', return_value={'structuredContent': {'code': 'OK', 'data': {'items': [{'keyword': 'coat', 'searches': 530}]}}}) as rpc:
            result = client.call('traffic_keyword', args)
        self.assertEqual(rpc.call_args.args[1]['arguments'], {'request': args})
        self.assertEqual(result['items'][0]['searches'], 530)

    def test_official_url_parsing_and_secret_stays_private(self):
        self.assertEqual(sellersprite.key_value('https://mcp.sellersprite.com/mcp?secret-key=test%2Bkey'), 'test+key')
        with self.assertRaises(ValueError):
            sellersprite.key_value('https://evil.example/mcp?secret-key=test')
        with patch.object(sellersprite, 'current_key', return_value='private'):
            self.assertNotIn('private', json.dumps(sellersprite.public()))

    def test_json_and_sse_rpc(self):
        for sse in (False, True):
            def open_request(req, **kwargs):
                self.assertIn('secret-key=key', req.full_url)
                rid = json.loads(req.data)['id']
                payload = json.dumps({'jsonrpc': '2.0', 'id': rid, 'result': {'tools': []}}).encode()
                return Response(b'data: '+payload+b'\n\n' if sse else payload, {'Content-Type': 'text/event-stream' if sse else 'application/json', 'Mcp-Session-Id': 'session'})
            with patch('sellersprite.build_opener') as opener:
                opener.return_value.open.side_effect = open_request
                client = sellersprite.Client('key')
                self.assertEqual(client.rpc('tools/list'), {'tools': []})
                self.assertEqual(client.session, 'session')

    def test_tools_error_never_echoes_remote_secret(self):
        client = sellersprite.Client('key')
        client.tools = {'asin_detail': {'inputSchema': {'properties': {'asin': {}}, 'required': ['asin']}}}
        with patch.object(client, 'rpc', return_value={'isError': True, 'content': [{'type': 'text', 'text': 'secret-key=private'}]}):
            with self.assertRaises(ValueError) as error:
                client.call('asin_detail', {'asin': 'B0FVS1X3SP'})
            self.assertNotIn('private', str(error.exception))

    def test_actual_reverse_keyword_is_evidence_and_keeps_metrics(self):
        sources = [{'asin': 'B0FVS1X3SP', 'status': 'ok', 'title': 'Jacket', 'bullets': [], 'description': '', 'brand': '', 'limitations': [], 'keywordData': [{'keyword': 'fleece coat', 'keywordCn': '抓绒外套', 'searches': 530, 'rankPosition': {'position': 8}}]}]
        with patch('competitors.sellersprite.read_sources', return_value=sources), patch('competitors.provider.research_json', return_value={'keywords': [{'phrase': 'fleece coat'}, {'phrase': 'invented words'}]}):
            report = competitors.analyse({'market': 'UK', 'asins': 'B0FVS1X3SP', 'source': 'sellersprite'})
        self.assertEqual(len(report['keywords']), 1)
        self.assertEqual(report['keywords'][0]['translation'], '抓绒外套')
        self.assertEqual(report['keywords'][0]['metrics'][0]['searches'], 530)
        self.assertEqual(report['keywords'][0]['metrics'][0]['naturalRank'], 8)

    def test_detail_failure_still_preserves_reverse_keywords(self):
        with patch('sellersprite.Client') as client:
            client.return_value.connect.return_value.call.side_effect = [ValueError('详情未收录'), {'items': [{'keyword': 'coat'}], 'total': 3}]
            result = sellersprite.read_sources(['B0FVS1X3SP'], 'UK')[0]
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['description'], '')
        self.assertEqual(len(result['keywordData']), 1)
