import unittest
from unittest.mock import call, patch
import competitors
from pathlib import Path
import importer


class CompetitorTests(unittest.TestCase):
    def test_public_sources_use_requested_market_domain(self):
        for market, domain in importer.MARKET_DOMAINS.items():
            with self.subTest(market=market), patch('competitors.importer.fetch', return_value='captcha') as fetch, patch('competitors.provider.research_json') as model:
                result = competitors.analyse({'market': market, 'asins': 'B0FVS1X3SP'})
                expected = f'https://www.amazon.{domain}/dp/B0FVS1X3SP'
                fetch.assert_called_once_with(expected)
                self.assertEqual(result['sources'][0]['url'], expected)
                model.assert_not_called()

    def test_listing_research_is_saved_and_loaded_by_its_own_market(self):
        js = (Path(__file__).parent / 'competitors.js').read_text(encoding='utf-8')
        self.assertIn("current.competitorResearch[researchMarket]={...data,input}", js)
        self.assertIn("site.onchange=()=>{const matching=p.competitorResearch?.[site.value]", js)
        self.assertNotIn("targetMarket=market,researchMarket=document.getElementById('competitorMarket').value", js)

    def test_sections_nested_html(self):
        page = '<span id="productTitle">Fleece Jacket</span><div id="feature-bullets"><ul><li><span>Soft fleece</span></li><li>Hooded design</li></ul></div><div id="productDescription"><p>Everyday jacket</p></div>'
        result = importer.parse_amazon(page)
        self.assertIn('Soft fleece', result['bullets'])
        self.assertEqual(result['description'], 'Everyday jacket')

    def test_keywords_require_source_evidence(self):
        with patch('competitors.importer.fetch', return_value='<span id="productTitle">Mens Fleece Jacket</span>'), patch('competitors.provider.research_json', return_value={'keywords': [{'phrase': 'fleece jacket'}, {'phrase': 'waterproof coat'}], 'structure': 'title only'}):
            result = competitors.analyse({'market': 'UK', 'asins': 'B0FVS1X3SP', 'facts': {}})
        self.assertEqual([k['phrase'] for k in result['keywords']], ['fleece jacket'])
        self.assertEqual(result['keywords'][0]['sourceAsins'], ['B0FVS1X3SP'])

    def test_blocked_pages_do_not_call_model(self):
        with patch('competitors.importer.fetch', return_value='captcha'), patch('competitors.provider.research_json') as model:
            result = competitors.analyse({'market': 'UK', 'asins': 'B0FVS1X3SP'})
            self.assertEqual(result['keywords'], [])
            model.assert_not_called()

    def test_fallback_seed_and_recommendation_gates(self):
        facts = {'features': 'Cable knit cardigan with front pockets; not fleece lined'}
        proof = [{'field': 'features', 'quote': 'Cable knit cardigan with front pockets'}]
        source = {'asin': 'B0FVS1X3SP', 'status': 'ok', 'title': 'Cardigan',
                  'bullets': [], 'description': '', 'keywordData': [
                      {'keyword': 'cable knit cardigan', 'searches': None, 'trafficPercentage': 0}]}
        phrases = [('cable knit cardigan', 24000, 'title', 'core'),
                   ('cardigan with front pockets', 20000, 'bullets', 'attribute'),
                   ('front pocket cardigan', 2100, 'bullets', 'attribute'),
                   ('cardigan with side pockets', 3000, 'bullets', 'attribute'),
                   ('fleece lined cardigan', 4500, 'bullets', 'attribute'),
                   ('knit cardigan', 1000, 'invalid', 'core')]
        suggestions = [{'phrase': phrase, 'placement': place, 'type': kind,
                        'productEvidence': proof} for phrase, _, place, kind in phrases]
        mining = [{'seed': 'cable knit cardigan', 'items': [
            {'keyword': phrase, 'searches': volume} for phrase, volume, _, _ in phrases]}]
        targeted = [{'seed': 'cable knit cardigan', 'items': [
            row for row in mining[0]['items'] if 500 <= row['searches'] <= 8000]}]
        with patch('competitors.sellersprite.read_sources', return_value=[source]), patch(
            'competitors.sellersprite.mine_keywords', side_effect=[mining, targeted]
        ) as mine, patch('competitors.provider.research_json', side_effect=[
            {'keywords': [suggestions[0]], 'productSeeds': [suggestions[0]]},
            {'keywords': suggestions},
        ]) as model:
            report = competitors.analyse({'market': 'US', 'asins': source['asin'], 'source': 'sellersprite',
                                          'mineKeywords': True, 'facts': facts})
        self.assertEqual(mine.call_args_list, [
            call(['cable knit cardigan'], 'US'),
            call(['cable knit cardigan'], 'US', search_range=(500, 8000)),
        ])
        self.assertEqual(report['mining'][0]['seedSource'], 'product_facts')
        selected = [row for row in report['keywords'] if row['selected']]
        self.assertEqual([row['phrase'] for row in selected], [
            'cable knit cardigan', 'front pocket cardigan', 'cardigan with front pockets'])
        self.assertEqual(selected[0]['metrics'][1]['seedSource'], 'product_facts')
        self.assertEqual(selected[1]['bulletMiningSeeds'], ['cable knit cardigan'])
        self.assertEqual(len(selected[1]['metrics']), 1)
        dedicated = model.call_args.args[1]['bulletKeywordMining'][0]['items']
        self.assertTrue(all(500 <= row['searches'] <= 8000 for row in dedicated))
        self.assertEqual({row['phrase'] for row in report['keywords'] if not row['selected']},
                         {'cardigan with side pockets', 'fleece lined cardigan', 'knit cardigan'})

    def test_invalid_asin_rejected(self):
        with self.assertRaises(ValueError):
            competitors.analyse({'market': 'UK', 'asins': 'https://example.com'})

    def test_translation_preserves_keys(self):
        import provider
        with patch('provider.research_json',return_value={'keywords':[], 'translations':{'title':'外套'}}):
            self.assertEqual(provider.translate_text({'texts':{'title':'Jacket'}})['translations']['title'],'外套')
        with patch('provider.research_json',return_value={'keywords':[], 'translations':{}}):
            with self.assertRaises(ValueError):
                provider.translate_text({'texts':{'title':'Jacket'}})
