import unittest
from ziniao_inventory_observe import summarize_coverage


class InventoryCoverageTests(unittest.TestCase):
    def row(self,sku,skus=None,status='在售 完善商品信息'):
        return {'sku':sku,'skus':skus if skus is not None else [sku],'statusCellText':status}

    def test_exact_family_coverage_retains_actual_status(self):
        result=summarize_coverage(['A','B'],[self.row('A'),self.row('B',status='已禁止显示搜索结果')])
        self.assertTrue(result['coverageVerified'])
        self.assertEqual(result['statusCellCounts'],{'在售 完善商品信息':1,'已禁止显示搜索结果':1})

    def test_missing_or_duplicate_SKU_cannot_prove_coverage(self):
        for rows in ([self.row('A')],[self.row('A'),self.row('A'),self.row('B')]):
            self.assertFalse(summarize_coverage(['A','B'],rows)['coverageVerified'])

    def test_ambiguous_extra_wrapper_cannot_pass_even_with_all_normal_rows(self):
        result=summarize_coverage(['A','B'],[self.row('A'),self.row('B'),self.row(None,['A','B'],None)])
        self.assertFalse(result['coverageVerified'])
        self.assertEqual(result['ambiguousRows'],1)
        self.assertIn('UNRESOLVED_STATUS_CELL',result['statusCellCounts'])

    def test_visible_loading_does_not_pass_even_if_previous_rows_match(self):
        result=summarize_coverage(['A','B'],[self.row('A'),self.row('B')],loading=True)
        self.assertTrue(result['observationPending'])
        self.assertFalse(result['coverageVerified'])
