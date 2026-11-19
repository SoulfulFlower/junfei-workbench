import unittest
import listing_brand_policy as policy


class ListingBrandPolicyTests(unittest.TestCase):
    def test_supplier_brand_and_adhesive_mark_are_excluded_without_authorization(self):
        product = {'brand': 'Generic', 'sourceImport': {'supplier': {
            'attributes': {'品牌': '祥亚', '背胶': '3M背胶'}}}}
        terms = policy.excluded_brand_terms(product)
        self.assertEqual(set(terms), {'祥亚', '3M'})
        self.assertEqual(policy.find_in_listing({'title': '3m Adhesive Seal'}, terms), ['3M'])
        self.assertEqual(policy.find_in_listing({'description': 'Length 3mm'}, terms), [])

    def test_alternatives_and_translations_are_checked_but_internal_warnings_are_not(self):
        self.assertEqual(policy.find_in_listing({'alternatives': {'titles': ['3M seal']}}, ['3M']), ['3M'])
        self.assertEqual(policy.find_in_listing({'translations': {'title': '祥亚密封条'}}, ['祥亚']), ['祥亚'])
        self.assertEqual(policy.find_in_listing({'warnings': '不得使用3M品牌'}, ['3M']), [])

    def test_authorization_does_not_override_explicit_exclusions(self):
        product = {'brand': 'OwnBrand', 'brandUseAuthorized': True, 'brandExclusions': ['OwnBrand']}
        self.assertEqual(policy.excluded_brand_terms(product), ['OwnBrand'])
