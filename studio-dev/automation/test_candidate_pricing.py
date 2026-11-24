from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from candidate_pricing import calculate


class CandidateQuoteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root/'table.json').write_text(json.dumps({'records': [
            {'channel_code': 'apparel', 'country_code': country, 'start_weight': 450, 'end_weight': 700,
             'first_freight': 80, 'handling_fee': 10, 'source_row': 1} for country in ('US', 'GB')]}), encoding='utf-8')
        self.config = {'pricing': {'method': 'quote_cost_markup', 'volumetric_divisor': 8000,
            'exchange_rate_cny_per_usd': 6.8, 'platform_fee_rate': .15, 'cost_markup_rate': .5,
            'draft_estimation': {'scope': 'draft_only', 'surcharge_rmb': 0, 'other_costs_rmb': 0},
            'marketplace_policies': {'UK': {'platform_fee_rate': .15, 'cost_markup_rate': .5}},
            'preferred_channels_by_product_type': {'apparel': {'US': ['table.json|apparel'], 'UK': ['table.json|apparel']}}}}
        self.spec = {'supplierUrl': 'https://detail.1688.com/offer/123.html', 'purchaseCny': 30,
            'domesticCny': 7, 'packagedWeightG': 400, 'lengthCm': 40, 'widthCm': 25, 'heightCm': 4,
            'marketTotalUsd': 30, 'gbpFxEvidence': {'url': 'https://www.boc.cn/sourcedb/whpj/',
            'currency': 'GBP', 'basis': 'spot_sell_per_100', 'cnyPer100': '880',
            'publishedAt': datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')+' 12:00',
            'observedRaw': 'GBP spot sell880/100'}}

    def test_volume_takes_priority_and_domestic_freight_is_counted_once(self):
        result = calculate(self.spec, self.config, self.root)
        self.assertEqual(result['selected']['US']['billedWeightKg'], '0.5')
        self.assertEqual(result['selected']['US']['freightCny'], '50.0')
        self.assertEqual(result['selected']['US']['totalCostCny'], '87.0')
        self.assertEqual(result['selected']['US']['profitAtMarketPriceCny'], '86.400')
        self.assertNotEqual(result['selected']['US']['formulaPrice'], result['selected']['UK']['formulaPrice'])
        self.assertFalse(result['publicationReady'])

    def test_missing_packaging_and_stale_fx_fail_before_price_is_produced(self):
        for changed in ({'heightCm': 0}, {'packagedWeightG': True},
                        {'gbpFxEvidence': {**self.spec['gbpFxEvidence'], 'publishedAt': '2000-01-01'}}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                calculate({**self.spec, **changed}, self.config, self.root)

    def test_market_loss_is_not_hidden_by_automatically_marked_up_formula_price(self):
        result = calculate({**self.spec, 'marketTotalUsd': 5}, self.config, self.root)
        self.assertFalse(result['positiveEstimatedMarketProfit'])

