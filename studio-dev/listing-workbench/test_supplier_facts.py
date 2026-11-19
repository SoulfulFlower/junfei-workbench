import unittest
import supplier_facts as facts
import importer


class SupplierFactsTests(unittest.TestCase):
    def data(self):
        return {'skuRows': ['棕色45mm*5米 0-3cm缝135g左右\n¥4.66\n库存888787件',
                            '黑色25mm*1米\n¥0.57\n库存10件'],
                'packagingTables': [[['规格','长(cm)','宽(cm)','高(cm)','体积(cm³)','重量(g)'],
                    ['棕色45mm*5米 0-3cm缝135g左右','14','9','10','1260','135'],
                    ['黑色25mm*1米','14','9','10','1260','15']]]}

    def test_variant_quote_package_join_preserves_scope_and_unknowns(self):
        parsed = facts.normalize(self.data())
        brown, black = parsed['variants']
        self.assertEqual(brown['displayPriceCny'], 4.66)
        self.assertEqual(black['displayPriceCny'], .57)
        self.assertEqual(brown['itemPackage']['weightG'], 135)
        self.assertEqual(black['itemPackage']['weightG'], 15)
        self.assertEqual(brown['itemPackage']['weightScope'], 'supplier_item_weight_unspecified')
        self.assertFalse(brown['verifiedPurchasePrice'])
        self.assertEqual(facts.normalize({})['variants'], [])

    def test_headline_wrong_units_duplicates_and_unknown_price_not_promoted(self):
        data = self.data()
        data['skuRows'] += ['券后 ¥0.57起 ~ ¥94.05 1件起批', data['skuRows'][0], '其它规格 ¥0 库存0件']
        data['packagingTables'][0][0][1] = '长(mm)'
        result = facts.normalize(data)
        self.assertEqual(result['unparsedSkuRowCount'], 1)
        self.assertTrue(all('itemPackage' not in row for row in result['variants']))
        self.assertIn('conflict', result['variants'][0])
        self.assertIsNone(result['variants'][-1]['displayPriceCny'])

    def test_invalid_capture_fails_before_product_mutation(self):
        for data in ({'skuRows':None}, {'skuRows':[{}]}, {'packagingTables':[[None]]}):
            state = {'products': [], 'reviews': {}}
            with self.subTest(data=data), self.assertRaises(ValueError): importer.merge_browser_capture(state, data)
            self.assertEqual(state['products'], [])

    def test_capture_keeps_structured_reference_without_autofilling_cost_or_gross(self):
        state = {'products': [{'id':'target','name':'Test','status':'待补资料','purchasePrice':'manual cost',
                              'packageWeight':'manual gross','quantity':88}], 'reviews':{}}
        capture = dict(self.data(),url='https://detail.1688.com/offer/705907720182.html', title='自粘门窗密封条产品',
            attributes={'品牌':'祥亚'}, images=[],targetProductId='target',market='US',capturedAt='2026-11-01T10:00:00+08:00')
        importer.merge_browser_capture(state, capture)
        p = state['products'][0]
        self.assertEqual(p['purchasePrice'],'manual cost')
        self.assertEqual(p['packageWeight'],'manual gross')
        self.assertEqual(p['quantity'],88)
        self.assertEqual(p['sourceImport']['supplier']['variants'][0]['supplierStock'],888787)
        self.assertEqual(p['sourceImport']['supplier']['attributes']['品牌'],'祥亚')


if __name__ == '__main__': unittest.main()
