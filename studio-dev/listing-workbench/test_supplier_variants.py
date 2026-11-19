import copy
import unittest

import supplier_variants as v


class SupplierVariantTests(unittest.TestCase):
    def setUp(self):
        self.product = {'id': 'p1', 'sourceUrl': 'https://detail.1688.com/offer/123.html',
            'sourceImport': {'amazon': {'variants': [
                {'asin': 'A1', 'color_name': 'Brown', 'size_name': 'Small'},
                {'asin': 'A2', 'color_name': 'Light Pink', 'size_name': 'X-Large'}]}},
            'supplierVariantCoverage': {'productId': 'p1',
                'sourceUrl': 'https://detail.1688.com/offer/123.html?kj_agent_plugin=niubox',
                'checkedAt': '2026-11-05T05:12:32.465Z', 'evidence': 'observed-supplier-page.json',
                'supplierObservedColors': ['Brown', 'Light Pink'], 'supplierObservedSizes': ['S', 'XL']}}

    def test_matching_options_do_not_claim_stock_or_invent_cartesian_children(self):
        before = copy.deepcopy(self.product)
        result = v.inspect(self.product)
        self.assertTrue(result['ok'])
        self.assertEqual(result['observedChildCount'], 2)
        self.assertEqual(result['uncoveredChildren'], [])
        self.assertFalse(result['stockVerified'])
        self.assertEqual(self.product, before)

    def test_missing_colour_is_derived_even_when_client_clears_missing_list(self):
        self.product['supplierVariantCoverage'].update(supplierObservedColors=['Brown'], unverifiedSupplierColors=[])
        result = v.inspect(self.product)
        self.assertFalse(result['ok'])
        self.assertEqual(result['unverifiedColors'], ['Light Pink'])
        self.assertEqual(result['uncoveredChildren'], [{'asin': 'A2', 'color': 'Light Pink', 'size': 'X-Large', 'missing': ['color']}])

    def test_sparse_supplier_combinations_cannot_pass_from_overlapping_domains(self):
        self.product['supplierVariantCoverage']['supplierObservedVariants'] = [
            {'color':'Brown','size':'XL'}, {'color':'Light Pink','size':'S'}]
        result = v.inspect(self.product)
        self.assertFalse(result['ok'])
        self.assertEqual([x['missing'] for x in result['uncoveredChildren']], [['combination'],['combination']])

    def test_large_sizes_are_not_covered_by_small_sizes(self):
        self.product['sourceImport']['amazon']['variants'][1]['size_name'] = '5X-Large'
        result = v.inspect(self.product)
        self.assertFalse(result['ok'])
        self.assertEqual(result['unverifiedSizes'], ['5X-Large'])

    def test_common_size_aliases_preserve_distinct_sizes(self):
        for source, expected in [('Small','S'), ('X-Large','x_l'), ('XX-Large','XXL'),
                                 ('3X-Large','XXXL'), ('4X-Large','4XL'), ('XX-Small','2XS')]:
            with self.subTest(size=source):
                self.product['sourceImport']['amazon']['variants'][0]['size_name'] = source
                self.product['supplierVariantCoverage']['supplierObservedSizes'] = [expected, 'XL']
                self.assertTrue(v.inspect(self.product)['ok'])

    def test_colour_normalisation_does_not_merge_distinct_shades(self):
        self.product['supplierVariantCoverage']['supplierObservedColors'] = [' brown ', 'Pink']
        result = v.inspect(self.product)
        self.assertFalse(result['ok'])
        self.assertEqual(result['unverifiedColors'], ['Light Pink'])

    def test_source_switch_invalidates_old_observation(self):
        self.product['sourceUrl'] = 'https://detail.1688.com/offer/456.html'
        self.assertIn('货源变体观察与当前货源链接不一致，需重新核对', v.inspect(self.product)['issues'])

    def test_imported_supplier_conflict_is_not_hidden_by_top_level_url(self):
        self.product['sourceImport']['supplier'] = {'url': 'https://detail.1688.com/offer/456.html'}
        self.assertIn('采集货源与当前货源链接不一致，需重新核对', v.inspect(self.product)['issues'])

    def test_foreign_product_cannot_supply_coverage(self):
        self.product['supplierVariantCoverage']['productId'] = 'other'
        self.assertIn('货源变体观察不属于当前产品', v.inspect(self.product)['issues'])

    def test_missing_coverage_blocks_multi_variant_products(self):
        self.product.pop('supplierVariantCoverage')
        self.assertFalse(v.inspect(self.product)['ok'])

    def test_missing_evidence_or_timestamp_blocks_coverage(self):
        for key in ['evidence', 'checkedAt']:
            with self.subTest(key=key):
                p = copy.deepcopy(self.product)
                p['supplierVariantCoverage'].pop(key)
                self.assertFalse(v.inspect(p)['ok'])

    def test_bad_option_values_are_not_iterated_as_strings_or_objects(self):
        for value in ['Brown', ['Brown', None], {}, []]:
            with self.subTest(value=value):
                p = copy.deepcopy(self.product)
                p['supplierVariantCoverage']['supplierObservedColors'] = value
                self.assertFalse(v.inspect(p)['ok'])

    def test_malformed_and_empty_collected_children_cannot_pass(self):
        for children in [[], {}, [None], [{'color_name': 'Brown'}]]:
            with self.subTest(children=children):
                self.product['sourceImport']['amazon']['variants'] = children
                self.assertFalse(v.inspect(self.product)['ok'])

    def test_legacy_product_without_collected_variants_does_not_invent_a_domain(self):
        result = v.inspect({'colorNames': 'Brown,Pink', 'sizeNames': 'S,M'})
        self.assertTrue(result['ok'])
        self.assertFalse(result['required'])
        self.assertEqual(result['observedChildCount'], 0)

    def test_non_offer_urls_and_credentials_are_not_valid_bindings(self):
        for url in ['http://detail.1688.com/offer/123.html', 'https://evil.example/offer/123.html',
                    'https://detail.1688.com:8443/offer/123.html', 'https://user:pass@detail.1688.com/offer/123.html']:
            with self.subTest(url=url):
                self.product['supplierVariantCoverage']['sourceUrl'] = url
                self.assertFalse(v.inspect(self.product)['ok'])


if __name__ == '__main__':
    unittest.main()
