import unittest
import amazon_selection_capture as capture


class AmazonSelectionCaptureTests(unittest.TestCase):
    def test_actual_air_image_search_route_is_allowed_without_allowing_other_air_apps(self):
        data = self.payload()
        data.update(captureType='browser_1688_image_search',
                    url='https://air.1688.com/kapp/1688-search/pc-image-search/?tab=imageSearch&imageId=1549408876533674324',
                    offers=[{'offerId':'705907720182','title':'5米自粘门窗密封条',
                             'url':'https://detail.1688.com/offer/705907720182.html'}])
        observed = capture.validate(data)
        self.assertEqual(observed['sourcingSearch']['offers'][0]['offerId'], '705907720182')
        self.assertEqual(observed['trust'], 'unverified_observation')
        for url in ('https://air.1688.com/other/?imageId=1',
                    'https://air.1688.com/kapp/1688-search/pc-image-search/unrelated?imageId=1',
                    'https://air.1688.com.evil.example/kapp/1688-search/pc-image-search/?imageId=1',
                    'https://user@air.1688.com/kapp/1688-search/pc-image-search/?imageId=1',
                    'https://air.1688.com:8443/kapp/1688-search/pc-image-search/?imageId=1'):
            data['url'] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                capture.validate(data)

    def payload(self):
        return {
            'asin': 'B012345678', 'marketplace': 'US',
            'url': 'https://www.amazon.com/dp/B012345678',
            'capturedAt': '2026-11-01T12:00:00Z', 'title': 'Observed title',
            'brand': 'Observed brand', 'displayedPrice': '$9.99',
            'sellerText': 'Seller shown on page', 'fulfillmentText': 'Ships from Amazon',
            'dateFirstAvailable': 'Date First Available: January 1, 2020'
        }

    def test_valid_capture_is_explicitly_unverified(self):
        observation = capture.validate(self.payload())
        self.assertEqual(observation['trust'], 'unverified_observation')
        self.assertIn('不证明中国卖家', observation['limitations'])

    def test_seller_profile_requires_matching_identity_and_keeps_address_separate(self):
        data = {**self.payload(), 'captureType': 'browser_seller_profile',
                'url': 'https://www.amazon.com/sp?seller=SELLER12345',
                'sellerId': 'SELLER12345', 'sellerProfileText': 'Business Address: Hainan CN'}
        observed = capture.validate(data)
        self.assertEqual(observed['sellerProfile']['raw'], 'Business Address: Hainan CN')
        self.assertEqual(observed['trust'], 'unverified_observation')
        self.assertNotIn('sellerCountry', observed)
        for change in ({'sellerId': 'OTHER12345'}, {'url': 'https://www.amazon.co.uk/sp?seller=SELLER12345'},
                       {'url': 'https://www.amazon.com/dp/B012345678?seller=SELLER12345'},
                       {'url': 'https://user@www.amazon.com/sp?seller=SELLER12345'},
                       {'url': 'https://www.amazon.com:8443/sp?seller=SELLER12345'},
                       {'sellerProfileText': ''}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                capture.validate({**data, **change})

    def test_rejects_domain_marketplace_and_asin_mismatch(self):
        for key, value in [('url', 'https://www.amazon.com/dp/B000000000'),
                           ('url', 'https://example.com/dp/B012345678'),
                           ('marketplace', 'UK'), ('asin', 'invalid')]:
            with self.subTest(key=key, value=value):
                data = self.payload(); data[key] = value
                with self.assertRaises(ValueError): capture.validate(data)

    def test_front_search_requires_current_amazon_search_url_and_keeps_results_observational(self):
        data = self.payload()
        data.update(captureType='browser_front_search', url='https://www.amazon.com/s?k=door+seal',
                    visibleResultCount='1,234', searchResults=[{'asin':'B087654321','title':'Possible door seal'},
                    {'asin':'B012399999','title':'Unrelated kitchen tool'}])
        observation = capture.validate(data)
        self.assertEqual(observation['search']['query'], 'door seal')
        self.assertEqual(observation['search']['visibleResultCount'], 1234)
        self.assertEqual(observation['search']['results'][0]['asin'], 'B087654321')
        data['url'] = 'https://www.amazon.com/dp/B012345678'
        with self.assertRaises(ValueError): capture.validate(data)

    def test_sellersprite_search_is_captured_as_raw_observation_only(self):
        data = self.payload()
        data.update(captureType='browser_sellersprite_search',
                    url='https://www.sellersprite.com/v3/product-research?keyword=door',
                    pageTitle='SellerSprite product search',
                    visibleRows=[{'asin':'B087654321','text':'Door seal · Sales rank 1,234'}])
        observation = capture.validate(data)
        self.assertEqual(observation['sellerSprite']['rows'][0]['asin'], 'B087654321')
        self.assertIn('1,234', observation['sellerSprite']['rows'][0]['text'])
        self.assertIn('不抽取或认证销售排名', observation['sellerSprite']['warning'])
        self.assertNotIn('selectionEvidence', observation)
        data['url'] = 'https://seller-sprite.com/search'
        with self.assertRaises(ValueError): capture.validate(data)
        data['url'] = 'https://www.sellersprite.com/search?secret-key=do-not-save'
        self.assertNotIn('do-not-save', capture.validate(data)['url'])
        data['visibleRows'] = []
        with self.assertRaises(ValueError): capture.validate(data)

    def test_lexical_match_sorting_is_only_a_human_review_aid(self):
        ranked = capture.rank_visible_results('45mm silicone self adhesive door weather seal', [
            {'asin':'B000000002','title':'Silicone weather strip self adhesive door seal 45mm'},
            {'asin':'B000000001','title':'Kitchen organizer'}])
        self.assertEqual(ranked[0]['asin'], 'B000000002')
        self.assertGreater(ranked[0]['lexicalScore'], ranked[1]['lexicalScore'])
        self.assertIn('仅关键词排序', ranked[0]['reviewStatus'])

    def test_attaches_only_to_matching_selection_candidate_and_never_to_gate_evidence(self):
        observation = capture.validate(self.payload())
        workspace = {'products': [{
            'id': 'candidate', 'name': 'Observed target title',
            'selectionResearch': {'reference': {'asin': 'B012345678', 'market': 'US'}},
            'selectionEvidence': {'sellerCountry': '', 'fulfillment': ''}
        }]}
        product_id, count = capture.attach(workspace, observation)
        self.assertEqual((product_id, count), ('candidate', 1))
        product = workspace['products'][0]
        self.assertEqual(product['selectionEvidence'], {'sellerCountry': '', 'fulfillment': ''})
        self.assertEqual(product['selectionObservations'][0], observation)
        capture.attach(workspace, observation)
        self.assertEqual(len(product['selectionObservations']), 1)

    def test_sellersprite_observation_attaches_to_candidate_without_changing_gate(self):
        data = self.payload()
        data.update(captureType='browser_sellersprite_search',
                    url='https://www.sellersprite.com/v3/product-research',
                    pageTitle='SellerSprite search',
                    visibleRows=[{'asin':'B087654321','text':'Sales rank 1,234'}])
        observation = capture.validate(data)
        product = {'id':'candidate','selectionResearch':{'reference':{'asin':'B012345678','market':'US'}},
                   'selectionEvidence':{'matchedRank':{'value':None}}}
        capture.attach({'products':[product]}, observation)
        self.assertEqual(product['selectionObservations'][0]['sellerSprite']['rows'][0]['asin'],'B087654321')
        self.assertEqual(product['selectionEvidence']['matchedRank']['value'], None)

    def test_1688_image_search_results_are_bounded_supplier_observations(self):
        data = self.payload()
        data.update(captureType='browser_1688_image_search',
                    url='https://s.1688.com/selloffer/offer_search.htm?keywords=door+seal',
                    offers=[{'offerId':'705907720182','title':'5米自粘门窗密封条',
                             'url':'https://detail.1688.com/offer/705907720182.html?spm=tracking',
                             'imageUrl':'https://cbu01.alicdn.com/img/ibank/O1CN01.jpg?x=1',
                             'priceText':'¥4.66','supplierText':'测试店铺','text':'棕色45mm*5米 ¥4.66'}])
        observation = capture.validate(data)
        offer = observation['sourcingSearch']['offers'][0]
        self.assertEqual(offer['offerId'], '705907720182')
        self.assertEqual(offer['url'], 'https://detail.1688.com/offer/705907720182.html')
        self.assertEqual(offer['imageUrl'], 'https://cbu01.alicdn.com/img/ibank/O1CN01.jpg')
        self.assertIn('未验证同款', observation['sourcingSearch']['warning'])
        data['offers'][0]['url'] = 'https://detail.1688.com/offer/999999999999.html'
        with self.assertRaises(ValueError): capture.validate(data)
        data['url'] = 'https://evil.example/selloffer/search'
        with self.assertRaises(ValueError): capture.validate(data)

    def test_rejects_no_candidate_or_ambiguous_account_match(self):
        observation = capture.validate(self.payload())
        for products in ([], [
            {'id': 'one', 'selectionResearch': {'reference': {'asin': 'B012345678', 'market': 'US'}}},
            {'id': 'two', 'selectionResearch': {'reference': {'asin': 'B012345678', 'market': 'US'}}}
        ]):
            with self.subTest(products=len(products)):
                with self.assertRaises(ValueError): capture.attach({'products': products}, observation)

    def test_seller_store_capture_requires_matching_seller_search_and_stays_unverified(self):
        payload = {
            'url': 'https://www.amazon.com/s?me=SELLER12345&s=date-desc-rank&ref=tracking',
            'sellerId': 'SELLER12345', 'capturedAt': '2026-11-01T12:00:00Z',
            'pageTitle': 'Storefront', 'pageSummary': '1-2 of 2 results',
            'products': [
                {'asin': 'B012345678', 'title': 'Observed product', 'brandText': 'Brand text',
                 'priceText': '$9.99', 'imageUrl': 'https://m.media-amazon.com/images/I/test.jpg',
                 'raw': 'Observed card'},
                {'asin': 'B012345678', 'title': 'Duplicate ignored'},
                {'asin': 'B087654321', 'title': 'Second product',
                 'imageUrl': 'https://evil.example/image.jpg'},
            ]}
        observation = capture.validate_seller_store(payload)
        self.assertEqual(observation['marketplace'], 'US')
        self.assertEqual(len(observation['products']), 2)
        self.assertEqual(observation['products'][0]['imageUrl'], 'https://m.media-amazon.com/images/I/test.jpg')
        self.assertEqual(observation['products'][1]['imageUrl'], '')
        self.assertNotIn('tracking', observation['url'])
        self.assertIn('不证明近7天', observation['limitations'])
        workspace = {}
        saved, count = capture.attach_seller_store(workspace, observation)
        self.assertEqual((saved, count), (observation, 1))
        capture.attach_seller_store(workspace, observation)
        self.assertEqual(len(workspace['sellerScoutObservations']), 1)

    def test_seller_store_capture_rejects_wrong_market_seller_and_untrusted_bulk(self):
        payload = {'url': 'https://www.amazon.com/s?me=SELLER12345', 'sellerId': 'SELLER12345', 'marketplace': 'US',
                   'capturedAt': '2026-11-01T12:00:00Z',
                   'products': [{'asin': 'B012345678', 'title': 'Observed product'}]}
        for change in ({'url': 'https://www.amazon.co.uk/s?me=SELLER12345'},
                       {'sellerId': 'SELLER99999'},
                       {'url': 'http://www.amazon.com/s?me=SELLER12345'},
                       {'products': [{'asin': 'bad', 'title': 'Bad'}]},
                       {'products': [{'asin': 'B012345678', 'title': 'x'}] * 51}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    capture.validate_seller_store({**payload, **change})


if __name__ == '__main__':
    unittest.main()
