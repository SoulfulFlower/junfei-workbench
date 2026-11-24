import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import agent_center as agent
import agent_sourcing as sourcing
import agent_research
import importer


class AgentSourcingTests(unittest.TestCase):
    def test_shared_dimension_unit_does_not_match_only_last_axis(self):
        for observed in ('60 x 100 cm', '150 x 100 cm', '100 cm'):
            with self.subTest(observed=observed):
                _, matched = sourcing._attribute_signals({'dimensions': '50 x 100 cm'}, observed)
                self.assertEqual(matched, [])
        for observed in ('透明桌垫 50×100cm', '1000mm * 500mm', '0.5 x 1 m'):
            with self.subTest(observed=observed):
                _, matched = sourcing._attribute_signals({'dimensions': '50 x 100 cm'}, observed)
                self.assertEqual(len(matched), 1)

    def test_dimension_counts_and_inches_preserve_exact_variant(self):
        self.assertFalse(sourcing._dimensions_match('50 x 50 cm', '50 x 100 cm'))
        self.assertTrue(sourcing._dimensions_match('9in x 25in', '22.86 x 63.5 cm'))
        self.assertTrue(sourcing._dimensions_match('9 x 25 inches', '22.86 x 63.5 cm'))
        self.assertFalse(sourcing._dimensions_match('9in x 25in', '50 x 100 cm'))

    def test_explicit_supplier_wrong_axis_overrides_matching_title(self):
        known, matched, conflicts = sourcing._detail_attribute_signals(
            {'dimensions': '50 x 100 cm'},
            {'title': 'PVC 50 x 100 cm', 'attributes': {'尺寸': '60 x 100 cm'}})
        self.assertEqual(len(known), 1)
        self.assertEqual(matched, [])
        self.assertEqual(conflicts[0]['field'], 'dimensions')

    def test_sales_priority_keeps_offer_and_network_counts_separate(self):
        product = {'name': 'PVC mat', 'selectionObservations': [{
            'captureType': 'browser_1688_image_search', 'sourcingSearch': {'offers': [
                {'url': 'https://detail.1688.com/offer/1.html', 'title': 'PVC mat', 'raw': '全网销量10万+块'},
                {'url': 'https://detail.1688.com/offer/2.html', 'title': '透明桌垫', 'raw': '已售2.6万+块 全网销量10万+块'},
                {'url': 'https://detail.1688.com/offer/3.html', 'title': 'PVC mat', 'raw': '已售700+块'},
                {'url': 'https://detail.1688.com/offer/4.html', 'title': 'PVC mat', 'raw': '3500+评价 库存99999块'},
            ]}}]}
        with patch('agent_selection.current_policy', return_value={'sourcingPolicy': {
                'supplier_selection_policy': 'public_sales_descending'}}):
            result = sourcing.observed_candidates(product)
        self.assertEqual([x['url'].split('/')[-1] for x in result], ['2.html', '3.html', '1.html', '4.html'])
        self.assertEqual(result[0]['sales']['lowerBound'], 26000)
        self.assertEqual(result[0]['salesRankingBasis'], 'offer_sold')
        self.assertIsNone(result[-1]['sales'])

    def test_search_plan_builds_bounded_browser_handoff_without_claiming_supplier(self):
        plan = sourcing.search_plan({'name': '  45mm silicone self adhesive door seal  '})
        self.assertEqual(plan['status'], 'needs_browser')
        self.assertIn('keywords=45mm+silicone+self+adhesive+door+seal', plan['keywordUrl'])
        self.assertTrue(plan['requiresBrowserReview'])
        self.assertIn('不证明同款', plan['warning'])

    def test_search_plan_ranks_captured_offers_without_promoting_them(self):
        plan = sourcing.search_plan({
            'name': '45mm silicone self adhesive door seal',
            'selectionObservations': [{
                'captureType': 'browser_1688_image_search',
                'sourcingSearch': {'offers': [
                    {'offerId': '2', 'url': 'https://detail.1688.com/offer/2.html',
                     'title': 'other cotton bag', 'priceText': '¥3'},
                    {'offerId': '1', 'url': 'https://detail.1688.com/offer/1.html',
                     'title': '45mm silicone self adhesive door seal', 'priceText': '¥5',
                     'supplierText': 'Supplier'},
                ]}
            }]
        })
        self.assertEqual(plan['observedCandidates'][0]['offerId'], '1')
        self.assertEqual(plan['observedCandidates'][0]['status'], 'unverified_observation')
        self.assertEqual(plan['observedCandidates'][0]['priceText'], '¥5')
        self.assertIn('不证明同款', plan['warning'])

    def test_chinese_terms_and_known_attributes_improve_review_order_only(self):
        plan = sourcing.search_plan({
            'name': '门窗密封条', 'material': '硅胶', 'dimensions': '45mm x 5m', 'colorNames': '棕色',
            'selectionObservations': [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {'offers': [
                {'offerId': '1', 'url': 'https://detail.1688.com/offer/1.html', 'title': '硅胶密封条 防水家用'},
                {'offerId': '2', 'url': 'https://detail.1688.com/offer/2.html', 'title': '硅胶门窗密封条 45mm×5m 棕色'},
            ]}}]
        })
        candidates = plan['observedCandidates']
        self.assertEqual(candidates[0]['offerId'], '2')
        self.assertEqual(candidates[0]['lexicalScore'], 1.0)
        self.assertEqual(candidates[0]['attributeCoverage'], 1.0)
        self.assertEqual({x['field'] for x in candidates[0]['matchedAttributes']}, {'material', 'dimensions', 'colorNames'})
        self.assertEqual(candidates[0]['status'], 'unverified_observation')

    def test_unknown_attributes_do_not_distort_candidate_order(self):
        ranked = sourcing.observed_candidates({'name': 'door seal', 'material': 'unknown', 'colorNames': '待补',
            'selectionObservations': [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {'offers': [
                {'url': 'https://detail.1688.com/offer/1.html', 'title': 'door seal'},
            ]}}]})
        self.assertIsNone(ranked[0]['attributeCoverage'])
        self.assertEqual(ranked[0]['triageScore'], ranked[0]['lexicalScore'])
        self.assertEqual(ranked[0]['rankSignals'], ['title_terms'])

    def test_dimension_triage_matches_equivalent_metric_units_in_visible_card_text(self):
        ranked = sourcing.observed_candidates({
            'name': 'self adhesive weather stripping', 'dimensions': '45mm x 5m',
            'selectionObservations': [{'captureType': 'browser_1688_image_search', 'sourcingSearch': {'offers': [
                {'url': 'https://detail.1688.com/offer/1.html', 'title': 'self adhesive weather stripping',
                 'raw': '规格：宽4.5厘米，长度500厘米'},
                {'url': 'https://detail.1688.com/offer/2.html', 'title': 'self adhesive weather stripping',
                 'raw': '规格：宽4.5厘米'},
            ]}}]
        })
        self.assertEqual(ranked[0]['offerId'], '')
        self.assertEqual(ranked[0]['attributeCoverage'], 1.0)
        self.assertEqual(ranked[0]['attributeEvidence'], 'title_and_visible_card_text')
        self.assertEqual(ranked[1]['attributeCoverage'], 0.0)

    def test_missing_source_url_persists_search_plan(self):
        self.product['sourceUrl'] = ''
        self.product['name'] = '45mm silicone door seal'
        self.save()
        task = self.create()
        result = self.drive(task)
        self.assertTrue(result['results']['facts']['sourcingSearchPlan'])
        stored = agent.detail(1, task['id'])
        self.assertTrue(stored['sourcingPlanAvailable'])
        self.assertEqual(sourcing.plan_report(1, task['id'])['query'], '45mm silicone door seal')

    def test_search_observations_trigger_bounded_read_only_candidate_detail_probes(self):
        self.product['sourceUrl'] = ''
        self.product['name'] = 'silicone door seal'
        self.product['selectionObservations'] = [{
            'captureType': 'browser_1688_image_search',
            'sourcingSearch': {'offers': [
                {'offerId': str(index), 'url': f'https://detail.1688.com/offer/{index}.html',
                 'title': 'silicone door seal', 'priceText': '¥5'} for index in range(1, 7)]}}
        ]
        self.save()
        task = self.create()
        with patch('importer.read_supplier', side_effect=lambda url: importer.parse_supplier(self.html(),url)) as fetch:
            result = self.drive(task)
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(result['status'], 'blocked')
            plan = result['results']['facts']['sourcingSearchPlan']
            self.assertEqual(len(plan['observedCandidates']), 6)
            self.assertEqual([x['detailProbe']['status'] for x in plan['observedCandidates'][:3]],
                             ['collected', 'collected', 'collected'])
            self.assertIsNone(plan['observedCandidates'][3]['detailProbe'])
            saved_product = agent.load_workspace()['products'][0]
            self.assertEqual(saved_product['sourceUrl'], '')
            self.assertNotIn('supplier', saved_product.get('sourceImport', {}))
            stored = agent.detail(1, task['id'])['sourcingCandidateProbe']
            self.assertEqual(stored['state'], 'saved')
            self.assertEqual(len(stored['items']), 3)
            agent.recheck(1, task['id'])
            self.drive(task)
            self.assertEqual(fetch.call_count, 3)

    def test_untrusted_candidate_url_is_never_fetched(self):
        self.product['sourceUrl'] = ''
        self.product['name'] = 'silicone door seal'
        self.product['selectionObservations'] = [{'captureType': 'browser_1688_image_search',
            'sourcingSearch': {'offers': [{'url': 'https://detail.1688.com.evil/offer/12345678.html',
                                           'title': 'silicone door seal'}]}}]
        self.save()
        with patch('importer.read_supplier') as fetch:
            result = self.drive(self.create())
        fetch.assert_not_called()
        self.assertNotIn('sourcingCandidateProbe', result)

    def test_detail_attributes_change_recommendation_order(self):
        product = {'material': '硅胶', 'dimensions': '45mm x 5m'}
        plan = {'observedCandidates': [
            {'url': 'https://detail.1688.com/offer/1.html', 'title': 'door seal', 'lexicalScore': 0.8},
            {'url': 'https://detail.1688.com/offer/2.html', 'title': 'silicone 45mm 5m door seal', 'lexicalScore': 1.0},
        ]}
        probes = {
            'https://detail.1688.com/offer/1.html': {'status': 'collected', 'supplier': {
                'title': 'door seal', 'attributes': {'材质': '硅胶', '规格': '宽4.5厘米，长度500厘米'}}},
            'https://detail.1688.com/offer/2.html': {'status': 'collected', 'supplier': {
                'title': 'door seal', 'attributes': {'材质': 'cotton', '规格': '100厘米'}}},
        }
        sourcing.rank_detail_probes(plan, product, probes)
        self.assertEqual(plan['observedCandidates'][0]['detailRecommendedRank'], 1)
        self.assertEqual(plan['observedCandidates'][0]['detailAttributeCoverage'], 1.0)
        self.assertEqual(plan['observedCandidates'][1]['detailRecommendedRank'], 2)
        self.assertEqual(plan['observedCandidates'][1]['detailAttributeCoverage'], 0.0)
        self.assertEqual({x['field'] for x in plan['observedCandidates'][1]['detailAttributeConflicts']},
                         {'material', 'dimensions'})

    def test_research_plan_builds_frontend_and_sellersprite_handoff(self):
        plan = agent_research.search_plan({'profile': {'marketplace': 'US'},
                                           'snapshot': {'product': {'name': '45mm silicone door seal'}}})
        self.assertEqual(plan['status'], 'needs_browser')
        self.assertIn('amazon.com/s?k=45mm+silicone+door+seal', plan['amazonUrl'])
        self.assertEqual(plan['sellerSpriteUrl'], 'https://www.sellersprite.com/')
        self.assertTrue(plan['requiresBrowserReview'])
        self.assertIn('不会自动认定竞品', plan['warning'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.patches=[patch.object(agent,'DATA',self.root),patch.object(agent,'DB',self.root/'agent.sqlite3')]
        for item in self.patches:item.start()
        self.profile=agent.save_profile(1,dict(name='Source fixture',store='Test',marketplace='US',shippingTemplate='FBM'))
        self.product=dict(id='source-fixture',name='Fixture product',market='US',sourceUrl='https://detail.1688.com/offer/123.html',
                          packageWeight='manual gross 200g',purchasePrice='manual 12 CNY',quantity=88)
        self.workspace={'products':[self.product],'copy':{},'reviews':{self.product['id']:{'copy':True,'images':True}}}
        self.save()

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def save(self):
        with closing(sqlite3.connect(self.root/'studio.sqlite3')) as c,c:
            c.execute('CREATE TABLE IF NOT EXISTS workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            c.execute('INSERT OR REPLACE INTO workspace VALUES(1,1,?)',(json.dumps(self.workspace),))

    def create(self,**extra):
        if any(extra.get(key) is True for key in ('aiPlanning', 'autoResearch', 'autoListing')):
            extra.setdefault('budgetCny', 5)
        return agent.create(1,dict(goal='Collect supplier then continue',profileId=self.profile['id'],productId=self.product['id'],
                                   taskMode='production',autoSourcing=True,**extra))

    def drive(self,task):
        with patch('agent_center.threading.Thread.start'):agent.start(1,task['id'])
        agent.run(1,task['id'])
        return agent.detail(1,task['id'])

    def html(self):
        attrs={'材质':'cotton','产品尺寸':'10 x 20 cm','包装内容':'1 item','颜色':'Black','尺码':'M',
               '采购价':'unverified range','毛重':'unverified 10g'}
        return '<title>Supplier fixture product</title><script type="application/ld+json">'+json.dumps({
            'subject':'Supplier fixture product','attributes':[{'name':k,'value':v} for k,v in attrs.items()]})+'</script>'

    def test_public_source_updates_snapshot_and_chains_research_listing(self):
        task=self.create(autoResearch=True,researchAsins='B012345678',autoListing=True)
        research={'market':'US','sources':[{'status':'ok','asin':'B012345678','title':'Fixture competitor'}],
                  'keywords':[{'phrase':'cotton item','selected':True}], 'structure':'Fixture only'}
        listing={'title':'Cotton item','bullets':'a\nb\nc\nd\ne','description':'Fixture copy','terms':'cotton item'}
        with patch('importer.read_supplier',side_effect=lambda url: importer.parse_supplier(self.html(),url)) as fetch, patch('provider.settings_public',return_value={'hasKey':True}),patch('sellersprite.public',return_value={'hasKey':True}),patch('competitors.analyse',return_value=research) as analyse,patch('provider.generate_listing',return_value={'copy':listing}) as generate:
            result=self.drive(task)
        fetch.assert_called_once_with('https://detail.1688.com/offer/123.html')
        analyse.assert_called_once(); generate.assert_called_once()
        self.assertTrue(result['results']['facts']['ok'])
        self.assertTrue(result['sourcingReportAvailable'])
        self.assertTrue(result['listingDraftAvailable'])
        self.assertEqual(result['status'],'blocked')  # Draft needs review; no publication.
        used=generate.call_args.args[0]
        self.assertEqual(used['material'],'cotton')
        self.assertEqual(used['purchasePrice'],'manual 12 CNY')
        self.assertEqual(used['packageWeight'],'manual gross 200g')
        self.assertEqual(used['quantity'],88)
        self.assertEqual(sourcing.report(1,task['id'])['status'],'collected')
        self.assertFalse(agent.load_workspace()['reviews'][self.product['id']]['images'])

    def test_blocked_public_read_saves_report_and_recheck_does_not_repeat(self):
        task=self.create()
        with patch('importer.read_supplier',side_effect=TimeoutError()) as fetch:
            result=self.drive(task)
            self.assertEqual(sourcing.report(1,task['id'])['status'],'needs_browser')
            agent.recheck(1,task['id']);self.drive(task)
        self.assertEqual(fetch.call_count,1)
        self.assertFalse(result['results']['facts']['ok'])
        self.assertNotIn('material',agent.load_workspace()['products'][0])

    def test_concurrent_edits_preserved_old_report_not_applied_on_recheck(self):
        task=self.create()
        def fetch(url):
            self.product['material']='manual newer value';self.save();return importer.parse_supplier(self.html(),url)
        with patch('importer.read_supplier',side_effect=fetch) as request:
            result=self.drive(task)
            self.assertFalse(result['results']['facts']['ok'])
            agent.recheck(1,task['id']);result=self.drive(task)
        self.assertEqual(request.call_count,1)
        self.assertEqual(agent.load_workspace()['products'][0]['material'],'manual newer value')
        self.assertIn('旧货源',result['results']['facts']['issues'][0])

    def test_no_fetch_for_unverified_selection_or_unsupported_source(self):
        self.product['selectionResearch']={'reference':{'asin':'B012345678'}};self.save()
        with patch('importer.read_supplier') as fetch:self.drive(self.create())
        fetch.assert_not_called()
        for url in ('http://detail.1688.com/offer/123.html','https://detail.1688.com.evil/offer/123.html',
                    'https://user:secret@detail.1688.com/offer/123.html','https://detail.1688.com:443/offer/123.html'):
            self.assertIsNone(sourcing.source_url({'sourceUrl':url}))

    def test_report_account_and_hash_protection(self):
        task=self.create()
        with patch('importer.read_supplier',side_effect=lambda url: importer.parse_supplier(self.html(),url)):self.drive(task)
        with self.assertRaises(ValueError):sourcing.report(2,task['id'])
        (self.root/'agent-results'/task['id']/'sourcing-report.json').write_text('{}')
        with self.assertRaises(ValueError):sourcing.report(1,task['id'])

    def test_source_richer_evidence_and_known_cost_are_preserved(self):
        self.product['sourceImport']={'supplier':{'url':self.product['sourceUrl'],'attributes':{'材质':'verified wool'},
            'variants':[{'label':'exact variant'}],'images':['image reference'],'captureMethod':'browser-extension','retrievedAt':'old source time'}}
        self.save();task=self.create()
        with patch('importer.read_supplier',side_effect=lambda url: importer.parse_supplier(self.html(),url)):self.drive(task)
        p=agent.load_workspace()['products'][0]
        self.assertEqual(p['material'],'verified wool')
        self.assertEqual(p['sourceImport']['supplier']['variants'],[{'label':'exact variant'}])
        self.assertEqual(p['sourceImport']['supplier']['retrievedAt'],'old source time')

    def test_inspection_cannot_fetch_external_sources(self):
        with self.assertRaises(ValueError):agent.create(1,dict(goal='Inspect',profileId=self.profile['id'],productId=self.product['id'],autoSourcing=True))


if __name__=='__main__':unittest.main()
