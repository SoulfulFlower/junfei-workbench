import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import quote_pricing as q


class QuotePricingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);rates=root/'data/logistics';rates.mkdir(parents=True)
        self.raw={'source_header':'2023-06-26','records':[
            {'country_code':'US','channel_code':'CD','channel_name':'General cargo',
             'start_weight':700,'end_weight':999,'first_freight':'97.5','handling_fee':9,'source_row':9},
            {'country_code':'US','channel_code':'CLOTHING','start_weight':700,'end_weight':999,
             'first_freight':1,'handling_fee':0,'source_row':10}]}
        (rates/'rates.json').write_text(json.dumps(self.raw),encoding='utf-8')
        self.policy={'method':'quote_cost_markup','exchange_rate_cny_per_usd':6.8,'platform_fee_rate':.15,
            'cost_markup_rate':.5,'volumetric_divisor':8000,'preferred_channels':{'US':['rates.json|CD']},
            'draft_estimation':{'scope':'draft_only','surcharge_rmb':0,'other_costs_rmb':0}}
        self.product={'purchasePrice':'15.60','packageWeight':'975g','packageDimensions':'90 x 8 x 8 cm'}
        for p in [patch.object(q.app_paths,'APP',root),patch.object(q,'policy',return_value=self.policy)]:
            p.start();self.addCleanup(p.stop)

    def test_actual_quote_formula_ceil_cent_and_traceable_reference(self):
        result=q.estimate(self.product,'US')
        self.assertEqual(result['priceUsd'],'31.06')
        self.assertEqual(result['freightRmb'],'104.0625')
        self.assertEqual(result['chargeableKg'],'0.975')
        self.assertEqual(result['sourceRow'],9)
        self.assertEqual(result['sourceDate'],'2023-06-26')
        self.assertEqual(result['channel'],'rates.json|CD')
        self.assertFalse(result['finalPriceVerified'])
        self.assertEqual(len(result['quoteSha256']),64)

    def test_volumetric_weight_tier_boundary_and_no_silent_zero(self):
        p={**self.product,'packageDimensions':'100 x 10 x 8 cm'}
        with self.assertRaisesRegex(ValueError,'档位'):q.estimate(p,'US')
        result=q.calculate(self.policy,'15.60','.975',[90,8,8],97.5,9,5,2)
        self.assertEqual(result['priceUsd'],'32.88')
        for field in ('surcharge_rmb','other_costs_rmb'):
            with patch.object(q,'policy',return_value={**self.policy,'draft_estimation':{'scope':'draft_only',field:0}}):
                with self.assertRaises(ValueError):q.estimate(self.product,'US')

    def test_no_guessing_dimensions_or_other_variant_weights(self):
        for p in [{**self.product,'packageDimensions':'folded below 90cm'},
                  {**self.product,'purchasePrice':'15–20'},
                  {**self.product,'packageWeight':'unknown'}]:
            with self.assertRaises(ValueError):q.estimate(p,'US')
        with self.assertRaisesRegex(ValueError,'全部颜色'):q.estimate(self.product,'US',2)

    def test_adopted_supplier_row_requires_matching_source_and_weight(self):
        p={**self.product,'sourceUrl':'https://detail.1688.com/offer/1.html',
            'packageDimensions':'supplier label',
            'supplierPackageObservation':{'adoptedAsPackageWeight':True,'sourceUrl':'https://detail.1688.com/offer/1.html',
                'weightG':975,'lengthCm':90,'widthCm':8,'heightCm':8}}
        self.assertEqual(q.estimate(p,'US')['priceUsd'],'31.06')
        p['supplierPackageObservation']['weightG']=500
        with self.assertRaisesRegex(ValueError,'不同'):q.estimate(p,'US')


if __name__=='__main__':unittest.main()
