import copy
import unittest
from publication_inputs import publication_facts, uk_publication_inputs, uk_publication_requirements


class PublicationFactsTest(unittest.TestCase):
    def fixture(self):
        return {'cat': '服装', 'targetAudience': 'Women', 'style': '圆领修身长袖套头上衣',
                'sourceUrl': 'https://detail.1688.com/offer/821424146428.html',
                'sourceImport': {'supplier': {'url': 'https://detail.1688.com/offer/821424146428.html',
                    'title': '2024秋季新品欧美亚马逊时尚女士长袖弹力圆领罗纹修身T恤上衣',
                    'attributes': {'货号': '1156', '尺码': 'S,M,L,XL,XXL,XXXL', '衣长': '普通款(50cm<衣长≤65cm)'}}}}

    def zip_fixture(self):
        # Relevant real saved fields from zip-postlisting-state-readback.json;
        # this pure fixture does not load account data or publication receipts.
        return {'id': 'IMP-US-B0HPSJPMK4', 'cat': '服装', 'targetAudience': 'Women',
                'name': "Women's Stand Collar Half Zip Fleece Pullover with Pockets",
                'style': 'Women stand-collar half-zip pullover, regular cut, dropped shoulders, long sleeves, vertical zip chest pocket and kangaroo pocket',
                'features': 'Stand collar; half-zip front; vertical zipper pocket at left chest; kangaroo pocket; horizontal chest seam; dropped shoulders; long sleeves with narrow cuffs; visible fleece texture; solid colors. No waterproof or performance claim.',
                'sourceUrl': 'https://detail.1688.com/offer/1094860853637.html',
                'sourceImport': {'supplier': {'url': 'https://detail.1688.com/offer/1094860853637.html',
                    'title': '2026欧美跨境秋冬新爆款女装摇粒绒立领加绒拉链口袋外套女时尚',
                    'attributes': {'货号': '26FC198', '尺码': 'S,M,L,XL,XXL,XXXL',
                                   '衣长': '普通款(50cm<衣长≤65cm)', '材质成分': '氨纶:5%,涤纶（聚酯纤维）:95%'}}}}

    def test_ordinary_womens_top_classification_and_new_condition_keep_distinct_source_evidence(self):
        product = self.fixture();before = copy.deepcopy(product)
        facts = publication_facts(product)
        self.assertEqual(facts['itemCondition'], 'new_new')
        self.assertEqual(facts['itemConditionEvidence']['text'], product['sourceImport']['supplier']['title'])
        self.assertEqual(facts['specialSizeType'], 'Standard')
        evidence = facts['specialSizeTypeEvidence']
        self.assertTrue(evidence['inferred'])
        self.assertEqual(evidence['source'], 'inferred_workbench_classification')
        self.assertEqual(evidence['basis']['supplierSizes'], 'S,M,L,XL,XXL,XXXL')
        self.assertEqual(evidence['basis']['supplierLength'], '普通款(50cm<衣长≤65cm)')
        self.assertEqual(product, before)

    def confirmed_condition(self, product):
        return {'source': 'user_confirmation', 'productId': product['id'],
                'confirmedAt': '2026-11-18T18:00:00+08:00',
                'instruction': 'Test-only user confirmation: this product is brand new.'}

    def test_explicit_user_confirmed_condition_preserves_exact_evidence_without_supplier_inference(self):
        product = self.zip_fixture()
        product.update(itemCondition='new_new', itemConditionEvidence=self.confirmed_condition(product))
        before = copy.deepcopy(product)
        facts = publication_facts(product)
        self.assertEqual(facts['itemCondition'], 'new_new')
        self.assertEqual(facts['itemConditionEvidence'], product['itemConditionEvidence'])
        self.assertEqual(product, before)
        product['itemConditionEvidence']['instruction'] = 'Changed after freeze'
        self.assertEqual(facts['itemConditionEvidence'], before['itemConditionEvidence'])
        # A real product confirmation does not borrow a mismatched supplier's facts.
        product['sourceImport']['supplier']['url'] = 'https://detail.1688.com/offer/other.html'
        facts = publication_facts(product)
        self.assertEqual(facts['itemConditionEvidence']['source'], 'user_confirmation')
        self.assertNotIn('modelName', facts)

    def test_invalid_explicit_condition_cannot_silently_fall_back_to_a_new_supplier_title(self):
        original = self.fixture()
        original['id'] = 'condition-product'
        original.update(itemCondition='new_new', itemConditionEvidence=self.confirmed_condition(original))
        changes = [
            lambda p: p.update(itemCondition='used_like_new'),
            lambda p: p.update(itemCondition=True),
            lambda p: p.update(itemCondition=''),
            lambda p: p.update(itemConditionEvidence=None),
            lambda p: p.update(itemConditionEvidence='confirmed'),
            lambda p: p['itemConditionEvidence'].update(source='agent_inference'),
            lambda p: p['itemConditionEvidence'].update(productId='other-product'),
            lambda p: p['itemConditionEvidence'].update(instruction=' '),
            lambda p: p['itemConditionEvidence'].update(instruction=True),
            lambda p: p['itemConditionEvidence'].update(confirmedAt='2026-11-18T10:00:00'),
            lambda p: p['itemConditionEvidence'].update(confirmedAt='not-a-time'),
            lambda p: p['itemConditionEvidence'].pop('confirmedAt'),
            lambda p: p.pop('id'),
        ]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                product = copy.deepcopy(original);change(product);before = copy.deepcopy(product)
                with self.assertRaisesRegex(ValueError, '商品成色'):
                    publication_facts(product)
                self.assertEqual(product, before)

    def test_empty_condition_fields_keep_legacy_supplier_title_fallback_and_unknowns(self):
        product = self.fixture()
        product.update(itemCondition='', itemConditionEvidence={})
        self.assertEqual(publication_facts(product)['itemConditionEvidence']['source'], 'supplier_title')
        product = self.zip_fixture()
        product.update(itemCondition=None, itemConditionEvidence=None)
        self.assertNotIn('itemCondition', publication_facts(product))

    def test_global_policy_overrides_old_product_origin_and_care_without_changing_explicit_size_classification(self):
        product = self.fixture()
        product.update(countryOfOrigin='US', careInstructions='Hand Wash Only', specialSizeType='Petite')
        facts = publication_facts(product)
        self.assertEqual(facts['countryOfOrigin'], 'CN')
        self.assertEqual(facts['careInstructions'], 'Machine Wash')
        self.assertEqual(facts['sourceProductFacts'], {'countryOfOrigin': 'US', 'careInstructions': 'Hand Wash Only'})
        self.assertEqual({e['field'] for e in facts['policyContradictions']}, {'countryOfOrigin', 'careInstructions'})
        self.assertEqual(facts['specialSizeType'], 'Petite')
        self.assertFalse(facts['specialSizeTypeEvidence']['inferred'])
        self.assertEqual(facts['countryOfOriginSource']['source'], 'user_configured_defaults')
        self.assertEqual(facts['careInstructionsSource']['source'], 'user_configured_defaults')

    def test_unknown_or_different_source_never_generates_condition_or_size_classification(self):
        for change in (
                lambda p: p['sourceImport']['supplier'].update(url='https://detail.1688.com/offer/other.html'),
                lambda p: p['sourceImport']['supplier'].update(title='供应商商品资料不完整'),
                lambda p: p.update(sourceImport={})):
            product = self.fixture();change(product);facts = publication_facts(product)
            self.assertNotIn('itemCondition', facts)
            self.assertNotIn('specialSizeType', facts)
        product = self.fixture();product['sourceImport']['supplier']['title'] = '二手非新品女士上衣'
        self.assertNotIn('itemCondition', publication_facts(product))
        for change in (
                lambda p: p['sourceImport']['supplier']['attributes'].update(尺码='3XL'),
                lambda p: p['sourceImport']['supplier']['attributes'].update(衣长='长款'),
                lambda p: p.update(style='Plus Size 大码上衣'),
                lambda p: p.update(cat='日用百货')):
            product = self.fixture();change(product)
            self.assertNotIn('specialSizeType', publication_facts(product))

    def test_ordinary_clothing_without_water_claim_uses_the_new_user_policy_without_mutation(self):
        product=self.fixture();before=copy.deepcopy(product);facts=publication_facts(product)
        self.assertEqual(facts['waterResistanceLevel'],'not_water_resistant')
        self.assertEqual(facts['waterResistanceLevelSource']['source'],'user_configured_defaults')
        self.assertEqual(facts['waterResistanceLevelSource']['configuredAt'],'2026-11-17')
        self.assertIn('ordinary_apparel',facts['waterResistanceLevelSource']['scope'])
        self.assertEqual(product,before)

    def test_saved_zip_exact_no_claim_marker_allows_the_clothing_default_without_mutation(self):
        product=self.zip_fixture();before=copy.deepcopy(product);facts=publication_facts(product)
        self.assertEqual(facts['waterResistanceLevel'], 'not_water_resistant')
        self.assertEqual(facts['waterResistanceLevelSource']['source'], 'user_configured_defaults')
        self.assertEqual(facts['waterResistanceLevelSource']['configuredAt'], '2026-11-17')
        self.assertTrue(facts['waterResistancePolicyDecision']['applied'])
        self.assertNotIn('waterResistanceDeclarations', facts.get('sourceProductFacts', {}))
        self.assertEqual(product, before)
        product['features']='Stand collar pullover\nNo waterproof or performance claim.'
        self.assertEqual(publication_facts(product)['waterResistanceLevel'], 'not_water_resistant')

    def test_exact_no_claim_marker_never_hides_real_water_claims_in_the_same_field(self):
        for claim in ('Waterproof coating.', 'Water-resistant finish.', '防泼水面料'):
            with self.subTest(claim=claim):
                product=self.zip_fixture();product['features']+=' '+claim
                before=copy.deepcopy(product);facts=publication_facts(product)
                self.assertNotIn('waterResistanceLevel', facts)
                self.assertFalse(facts['waterResistancePolicyDecision']['applied'])
                self.assertEqual(facts['sourceProductFacts']['waterResistanceDeclarations'],
                                 [{'source': 'product_text', 'path': 'features', 'value': product['features']}])
                self.assertEqual(product, before)

    def test_no_claim_handling_is_exact_and_preserves_explicit_water_fields_and_special_product_gates(self):
        for text in ('No waterproof or performance claims.',
                     'Supplier wording: No waterproof or performance claim.',
                     'No waterproof or performance claim. Waterproof jacket.'):
            with self.subTest(text=text):
                product=self.zip_fixture();product['features']=text
                self.assertNotIn('waterResistanceLevel', publication_facts(product))
        product=self.zip_fixture();product['waterResistanceLevel']='water_resistant'
        before=copy.deepcopy(product);facts=publication_facts(product)
        self.assertEqual(facts['waterResistanceLevel'], 'water_resistant')
        self.assertEqual(facts['waterResistanceLevelSource']['source'], 'product_field')
        self.assertFalse(facts['waterResistancePolicyDecision']['applied'])
        self.assertEqual(product, before)
        product=self.zip_fixture()
        product['sourceImport']['supplier']['attributes']['防水性能']='No waterproof or performance claim.'
        facts=publication_facts(product)
        self.assertNotIn('waterResistanceLevel', facts)
        self.assertEqual(facts['sourceProductFacts']['waterResistanceDeclarations'][0]['path'],
                         'sourceImport.supplier.attributes.防水性能')
        for change in (lambda p:p.update(style='Protective raincoat'),
                       lambda p:p.update(cat='家居')):
            product=self.zip_fixture();change(product)
            self.assertNotIn('waterResistanceLevel', publication_facts(product))

    def test_explicit_water_level_is_preserved_and_never_replaced_by_the_default(self):
        product=self.fixture();product['waterResistanceLevel']='water_resistant';before=copy.deepcopy(product)
        facts=publication_facts(product)
        self.assertEqual(facts['waterResistanceLevel'],'water_resistant')
        self.assertEqual(facts['waterResistanceLevelSource']['source'],'product_field')
        self.assertFalse(facts['waterResistancePolicyDecision']['applied'])
        self.assertEqual(facts['sourceProductFacts']['waterResistanceDeclarations'][0]['value'],'water_resistant')
        self.assertEqual(product,before)

    def test_supplier_claims_and_special_clothing_block_default_without_guessing_a_water_level(self):
        for change in (lambda p:p['sourceImport']['supplier']['attributes'].update(功能='防水、防污'),
                       lambda p:p['sourceImport']['supplier']['attributes'].update(防水性能='5000mm'),
                       lambda p:p.update(style='Water-resistant jacket'),lambda p:p.update(style='医用防护服')):
            product=self.fixture();change(product);facts=publication_facts(product)
            self.assertNotIn('waterResistanceLevel',facts)
            self.assertFalse(facts['waterResistancePolicyDecision']['applied'])
            self.assertTrue(facts['sourceProductFacts']['waterResistanceDeclarations'])

    def test_other_categories_and_unidentified_clothing_never_receive_water_defaults(self):
        for product in ({'cat':'日用百货','title':'T-Shirt storage bag'}, {'cat':'家居','style':'Water bottle'},
                        {'cat':'服装','style':'未知商品'}, {}):
            self.assertNotIn('waterResistanceLevel',publication_facts(product))


class UkPublicationInputsTest(unittest.TestCase):
    def fixture(self):
        source = {'marketplace': 'US', 'productId': 'P', 'store': 'Actual US',
                  'destination': {'marketId': '11', 'marketplaceId': 'US-ID'},
                  'goodsItems': [{'sku': 'SKU-A', 'quantity': 88}, {'sku': 'SKU-B', 'quantity': 89}]}
        product = {'id': 'P', 'sourceUrl': 'https://detail.1688.com/offer/123.html',
                   'erpDelivery': {'UK': {'variantPrices': {'SKU-A': '18.12', 'SKU-B': '19.15'},
                                          'quantity': 20, 'handlingDays': 4}}}
        target = {'id': 'uk', 'storeName': 'Actual UK', 'shippingTemplate': {'name': 'UK Tracked'}}
        return source, product, target

    def test_explicit_per_sku_gbp_without_us_ids(self):
        source, product, target = self.fixture()
        original = copy.deepcopy((source, product, target))
        result = uk_publication_inputs(source, product, target)
        self.assertEqual(result['ukCommerce']['variantPrices'], {'SKU-A': '18.12', 'SKU-B': '19.15'})
        self.assertEqual(result['ukCommerce']['quantities'], {'SKU-A': 20, 'SKU-B': 20})
        self.assertEqual(result['ukTarget']['countryCode'], 'GB')
        self.assertNotIn('marketId', result['ukTarget'])
        self.assertEqual((source, product, target), original)

    def test_missing_gbp_never_uses_us_price_or_old_batch_defaults(self):
        source, product, target = self.fixture()
        product['erpDelivery']['UK'].pop('variantPrices')
        source['goodsItems'][0]['price'] = '29.55'
        with self.assertRaisesRegex(ValueError, 'GBP'):
            uk_publication_inputs(source, product, target)
        self.assertFalse(uk_publication_requirements(source, product, target)['ready'])

    def test_missing_stock_requires_explicit_source_inventory_policy(self):
        source, product, target = self.fixture()
        product['erpDelivery']['UK'].pop('quantity')
        with self.assertRaisesRegex(ValueError, '库存'):
            uk_publication_inputs(source, product, target)
        product['erpDelivery']['UK']['inventoryPolicy'] = 'preserve_source'
        result = uk_publication_inputs(source, product, target)
        self.assertEqual(result['ukCommerce']['quantities'], {'SKU-A': 88, 'SKU-B': 89})

    def test_country_store_ids_shipping_and_handling_must_be_uk(self):
        for mutation in (
                lambda s, p, t: t.update(storeName='Actual US'),
                lambda s, p, t: t.update(currency='USD'),
                lambda s, p, t: t.update(marketId='11'),
                lambda s, p, t: t.update(marketplaceId='US-ID'),
                lambda s, p, t: t.pop('shippingTemplate'),
                lambda s, p, t: p['erpDelivery']['UK'].pop('handlingDays'),
                lambda s, p, t: p['erpDelivery']['UK'].update(quantity=True),
                lambda s, p, t: p['erpDelivery']['UK'].update(handlingDays=3.5)):
            source, product, target = self.fixture()
            mutation(source, product, target)
            with self.assertRaises(ValueError):
                uk_publication_inputs(source, product, target)

    def test_saved_uk_quote_must_belong_to_same_source_and_currency(self):
        source, product, target = self.fixture()
        product['erpDelivery']['UK'].pop('variantPrices')
        quote = {'marketplace': 'UK', 'currency': 'GBP', 'sourceUrl': product['sourceUrl'],
                 'scope': 'quote_based_draft_base_scenario', 'basisSha256': 'proof', 'price': '18.89'}
        product['erpDraftPricing'] = {'UK': quote}
        result = uk_publication_inputs(source, product, target)
        self.assertEqual(result['ukCommerce']['variantPrices']['SKU-B'], '18.89')
        self.assertEqual(result['ukCommerce']['pricingBasis']['source'], 'saved_selection_quote')
        for key, value in [('sourceUrl', 'other product'), ('currency', 'USD'), ('basisSha256', '')]:
            original = quote[key]
            quote[key] = value
            with self.assertRaises(ValueError):
                uk_publication_inputs(source, product, target)
            quote[key] = original


if __name__ == '__main__':
    unittest.main()
