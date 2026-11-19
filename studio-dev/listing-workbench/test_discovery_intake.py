"""Loopback verification of CLI selection/sourcing → product and read-only task status."""
import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import sys

import agent_center
import app_paths
import cyclic_discovery
import discovery_intake
import product_library
import server
import test_agent_api as api_fixtures

ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, 'path', [str(ROOT / 'automation'), *sys.path]):
    import pipeline
    import test_pipeline


class DiscoveryIntakeTests(unittest.TestCase):
    call = api_fixtures.AgentAPITests.call

    @classmethod
    def setUpClass(cls):
        api_fixtures.AgentAPITests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        api_fixtures.AgentAPITests.tearDownClass.__func__(cls)

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='discovery-intake-')))
        self.workspace = self.root / 'studio.sqlite3'
        for module, name, value in ((server, 'DATA', self.root), (server, 'DB', self.workspace),
                                    (agent_center, 'DATA', self.root), (agent_center, 'DB', self.root / 'agent.sqlite3'),
                                    (cyclic_discovery, 'DB', self.root / 'graph.sqlite3')):
            self.enterContext(patch.object(module, name, value))
        with server.database() as db:
            db.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)')
            discovery_intake.ensure_schema(db)
        self.selected = self.root / 'selected.csv'
        self.selected.write_text('marketplace,asin,selected_at,source,status\n', encoding='utf-8')
        config = json.loads((ROOT / 'packaging/portable-config.json').read_text(encoding='utf-8'))
        config['selection'].update(selected_ledger=str(self.selected), freshness_basis='seller_listing')
        config['selection'].pop('brand_policy', None)
        config['selection'].pop('patent_search_policy', None)
        config['profiles'] = {'us': {'marketplace': 'US', 'store': 'isolated test store'}}
        self.cli_file = self.root / 'pipeline.sqlite3'
        self.p = pipeline.Pipeline(self.cli_file, config)
        self.addCleanup(self.p.db.close)
        now = datetime.now(timezone.utc).isoformat()
        common = {'sourceType': 'browser_visible', 'marketplace': 'US', 'observedAt': now}
        self.keys = ['B000000001', 'B000000002', 'B000000003', 'B000000004']
        graph = self.call('/api/discovery/ingest', {'cycleId': 'cycle', 'expectedRevision': 0, 'events': [
            {**common, 'kind': 'keyword', 'id': 'seed', 'parentId': None, 'asin': 'B012345678',
             'sourceTitle': 'Fixture product for testing', 'phrase': 'Fixture product',
             'url': 'https://www.amazon.com/dp/B012345678'},
            {**common, 'kind': 'search', 'id': 'search', 'parentId': 'seed', 'query': 'Fixture product',
             'url': 'https://www.amazon.com/s?k=Fixture+product',
             'products': [{'asin': asin, 'title': 'Fixture ' + asin} for asin in self.keys]},
        ]})
        self.assertEqual(graph[0], 200, graph)
        self.graph_revision = graph[1]['revision']

    def qualify(self, asin, profit='1.23', owner=1, competitors=None):
        job = self.p.add('US', asin, 'us')
        claim = self.p.claim(job)
        evidence = test_pipeline.PipelineTests.evidence(self, job, 'selection')
        if competitors is not None:
            evidence['selection_evidence'].update(candidate_parent_asin='B000000090',
                                                  ranked_competitors=competitors)
        self.p.finish(job, claim['token'], evidence)
        claim = self.p.claim(job)
        evidence = test_pipeline.PipelineTests.evidence(self, job, 'sourcing')
        evidence['sources'][0]['url'] = 'https://detail.1688.com/offer/1001.html'
        evidence['sourcing_evidence'] = {
            'accountId': owner, 'job_id': job, 'asin': asin, 'seller_id': 'A1234567890123',
            'qualified': True, 'supplier_id': '1001',
            'qualification_scope': 'positive_estimated_profit_under_configured_base_scenario',
            'selected_quote': {'scope': 'quote_based_draft_base_scenario', 'profit_at_market_price_rmb': profit},
        }
        self.p.finish(job, claim['token'], evidence)
        return job

    def promote(self, asins, revision=0, **changes):
        request = {'cycleId': 'cycle', 'expectedRevision': self.graph_revision, 'revision': revision,
                   'productKeys': ['US:' + asin for asin in asins], **changes}
        return self.call('/api/discovery/promote', request)

    def test_qualified_selection_goes_directly_to_account_archive_without_sharing(self):
        asin=self.keys[0]
        self.qualify(asin)
        with patch.object(product_library,'add_product',side_effect=AssertionError('sharing retired')), \
             patch.object(product_library,'claim',side_effect=AssertionError('claiming retired')):
            code,result=self.promote([asin])
            self.assertEqual(code,200,result)
            product=result['state']['products'][0]
            self.assertEqual(product['selectionResearch']['reference']['asin'],asin)
            self.assertNotIn('librarySourceId',product)
            self.assertEqual(len(result['state']['products']),1)
            code,reused=self.promote([asin],revision=result['revision'])
            self.assertEqual(code,200,reused)
            self.assertEqual(reused['state'],result['state'])
            self.assertEqual(reused['outcomes'][0]['status'],'reused')

    def test_ranked_competitors_follow_new_archive_into_research_input(self):
        asin = self.keys[0]
        search = 'https://www.amazon.com/s?k=Fixture+product'
        def row(child, parent, **changes):
            return {'asin': child, 'parent_asin': parent, 'marketplace': 'US',
                    'title': 'Same fixture style', 'match_level': 'exact',
                    'match_evidence': 'Same closure and outline', 'seller_id': 'A1234567890123',
                    'seller_name': 'Fixture Store',
                    'search': {'keyword': 'Fixture product', 'url': search},
                    'rank': {'value': 1900, 'category': 'Clothing', 'source': 'Amazon search page extension',
                             'url': search, 'raw': child + '\n#1,900 in Clothing',
                             'checked_at': datetime.now(timezone.utc).isoformat()}, **changes}

        valid = [row('B000000010', 'B000000020'), row('B000000011', 'B000000021'),
                 row('B000000012', 'B000000022')]
        unranked = row('B000000016', 'B000000026')
        unranked['rank']['raw'] = 'Estimated sales: 1900'
        self.qualify(asin, competitors=[
            row(asin, 'B000000029'), row('B000000013', 'B000000090'), valid[0],
            row('B000000015', 'B000000020'), unranked,
            row('B000000017', 'B000000027', marketplace='UK'), *valid[1:],
        ])
        code, result = self.promote([asin])
        self.assertEqual(code, 200, result)
        product = result['state']['products'][0]
        expected = [entry['asin'] for entry in valid]
        self.assertEqual(product['competitorResearch']['US']['input'].splitlines(), expected)
        self.assertEqual(product['competitorResearch']['US']['keywords'], [])
        self.assertEqual(product['selectionResearch']['rankedCompetitors'], [
            {**entry, 'product_url': f'https://www.amazon.com/dp/{entry["asin"]}'} for entry in valid
        ])
        self.assertEqual(self.promote([asin], revision=result['revision'])[1]['state'], result['state'])

        with patch.object(app_paths, 'LIBRARY_ROOT', self.root):
            endpoint = '/api/product-library/add'
            self.assertEqual(self.call(endpoint, {'id': product['id']})[0], 400)
            self.assertEqual(product_library.items(), [])
            cover = 'https://m.media-amazon.com/images/I/fixture.jpg'
            product['editorAsinReference'] = {'asin': asin, 'market': 'US', 'title': 'Fixture',
                                              'referenceImages': [cover]}
            input_text = '\n'.join(expected)
            product['competitorResearch']['US'].update(source='sellersprite',
                                                       keywords=[{'phrase': 'fixture item'}])
            product['reviewResearch'] = {'US': {'input': input_text, 'samples': [{'id': 'R1'}],
                                                'analysis': {'themes': []}}}
            with server.database() as conn:
                conn.execute('UPDATE workspace SET body=? WHERE id=1', (json.dumps(result['state']),))
            self.assertEqual(self.call(endpoint, {'id': product['id']}), (200, {'created': True}))
            self.assertEqual(self.call(endpoint, {'id': product['id']}), (200, {'created': False}))
            personal = {'products': []}
            self.assertEqual(product_library.catalog(personal)['products'][0]['asinCoverUrl'], cover)
            user = {'id': 2, 'name': 'Employee'}
            self.assertEqual(product_library.claim(personal, user, product['id'], self.root / 'employee-uploads'),
                             (product['id'], True))
            claimed = personal['products'][0]
            self.assertEqual(claimed['editorAsinReference']['referenceImages'], [cover])
            self.assertEqual(claimed['competitorResearch'], product['competitorResearch'])
            self.assertEqual(claimed['reviewResearch'], product['reviewResearch'])
            self.assertEqual(product_library.catalog(personal)['products'], [])
            self.assertNotIn('qualification', claimed['selectionResearch'])

    def test_new_receipt_without_ranked_competitors_shows_pending_instead_of_own_asin(self):
        asin = self.keys[0]
        self.qualify(asin, competitors=[])
        code, result = self.promote([asin])
        self.assertEqual(code, 200, result)
        research = result['state']['products'][0]['competitorResearch']['US']
        self.assertEqual(research['input'], '')
        self.assertIn('待补', research['warnings'])

    def test_batch_promotes_only_qualified_candidate_and_preserves_cli_authority(self):
        good, negative, other_owner, pending = self.keys
        job = self.qualify(good)
        self.qualify(negative, profit='-2')
        self.qualify(other_owner, owner=2)
        self.p.add('US', pending, 'us')
        before = hashlib.sha256(self.cli_file.read_bytes()).hexdigest()
        with patch.object(agent_center, 'start', side_effect=AssertionError('must not dispatch')):
            code, result = self.promote([good, negative, other_owner, pending, 'B012345678'])
        self.assertEqual(code, 200, result)
        self.assertEqual([r['status'] for r in result['outcomes']], ['created'] + ['blocked'] * 4)
        pid = 'IMP-US-' + good
        self.assertEqual([p['id'] for p in result['state']['products']], [pid])
        product = result['state']['products'][0]
        self.assertTrue(product['sku'])
        self.assertEqual(product['assets'], [])
        self.assertFalse(product['productionReview']['publishReady'])
        self.assertEqual(product['selectionResearch']['qualification']['cliJobId'], job)
        self.assertEqual(hashlib.sha256(self.cli_file.read_bytes()).hexdigest(), before)
        code, tasks = self.call('/api/agent/overview')
        self.assertEqual(code, 200)
        self.assertEqual(tasks['tasks'], [])
        self.assertEqual((tasks['cliTasks'][0]['id'], tasks['cliTasks'][0]['stage']), (job, 'research'))
        self.assertNotIn('config', tasks['cliTasks'][0])
        self.assertEqual(discovery_intake.overview(self.root, 2), [])
        claim = self.p.claim(job)
        self.p.hold(job, claim['token'], 'uncertain', 'fixture timeout')
        self.assertEqual(self.call('/api/agent/overview')[1]['cliTasks'][0]['status'], 'uncertain')
        self.assertEqual(self.promote([good], revision=result['revision'])[1]['outcomes'][0]['status'], 'reused')
        with self.assertRaisesRegex(ValueError, 'CLI'):
            discovery_intake.assert_web_available(self.root, 1, pid)

    def test_concurrent_intake_reuses_legacy_product_without_changing_its_contents(self):
        asin = self.keys[0]
        self.qualify(asin)
        prior = {'id': 'legacy', 'name': 'Existing facts', 'sku': 'KEEP-ME',
                 'sourceImport': {'market': 'US', 'asin': asin}}
        workspace = {'products': [prior], 'copy': {'legacy-US': {'title': 'Old copy'}}, 'reviews': {}}
        with server.database() as db:
            db.execute('INSERT INTO workspace VALUES(1,0,?)', (json.dumps(workspace),))
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.promote([asin]), range(2)))
        self.assertEqual(sorted(code for code, _ in replies), [200, 409])
        result = next(reply for code, reply in replies if code == 200)
        self.assertEqual(result['outcomes'][0]['status'], 'linked')
        self.assertEqual(result['state'], workspace)
        code, repeat = self.promote([asin], revision=result['revision'])
        self.assertEqual((code, repeat['revision'], repeat['outcomes'][0]['status']), (200, result['revision'], 'reused'))

    def test_bad_auth_stale_cycle_and_unavailable_ledger_fail_closed(self):
        asin = self.keys[0]
        payload = {'cycleId': 'cycle', 'expectedRevision': self.graph_revision,
                   'revision': 0, 'productKeys': ['US:' + asin]}
        self.assertEqual(self.call('/api/discovery/promote', payload, authenticated=False)[0], 401)
        self.assertEqual(self.call('/api/discovery/promote', payload, Origin='https://external.invalid')[0], 403)
        self.assertEqual(self.promote([asin], expectedRevision=self.graph_revision - 1)[0], 400)
        self.assertEqual(self.promote([asin], cycleId='other-account')[0], 400)
        with patch.object(discovery_intake, 'cli_path', side_effect=ValueError('not configured')):
            self.assertEqual(self.promote([asin])[0], 400)
        with server.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM workspace').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM discovery_product_links').fetchone()[0], 0)
