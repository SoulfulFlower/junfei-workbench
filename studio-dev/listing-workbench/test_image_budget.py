import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch
import image_budget as budget
import image_provider as images


class ImageBudgetTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(images, 'storyboard_submission', return_value={}))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = {'enabled': True, 'perProductFen': 500, 'dailyFen': 20000}
        self.mock_limits = patch.object(budget, 'limits', side_effect=lambda: dict(self.policy))
        self.mock_limits.start()
        self.addCleanup(self.mock_limits.stop)
        patcher = patch.object(images, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        relay = patch.object(images.aigocode_provider, 'public', return_value={'active': False})
        relay.start()
        self.addCleanup(relay.stop)
        (self.root / 'uploads').mkdir()
        self.reference = '/uploads/' + 'a' * 32 + '.png'
        (self.root / self.reference.lstrip('/')).write_bytes(b'\x89PNG\r\n\x1a\nreference')
        self.data = {'productId': 'P', 'slot': 'main', 'model': images.MODELS[0],
                     'prompt': 'Exact product', 'references': [self.reference]}
        self.quote = {'provider': 'APIMart', 'endpoint': 'https://api.apimart.ai/v1',
                      'model': self.data['model'], 'size': '1:1', 'resolution': '1K', 'quantity': 1,
                      'currency': 'CNY', 'maximumRmb': '3.00', 'source': 'test-only provider price evidence',
                      'verified': True, 'verifiedAt': budget.day(), 'validUntil': budget.day()}
        self.write_quote()

    def write_quote(self):
        (self.root / 'image-price-quotes.json').write_text(json.dumps({'quotes': [self.quote]}), encoding='utf-8')

    def submit(self, **changes):
        with patch.object(images, 'api', return_value={'data': [{'task_id': 'task-' + changes.get('slot', 'main')}]}) as api:
            job = images.submit({**self.data, **changes})
        self.assertEqual(api.call_count, 1)
        return job

    def test_reserve_before_call_enforces_product_limit_across_slots(self):
        def dispatch(*args):
            record = images.budget_status()['reservations'][0]
            self.assertEqual(record['reservedFen'], 300)
            return {'data': [{'task_id': 'known'}]}
        with patch.object(images, 'api', side_effect=dispatch):
            images.submit(self.data)
        with patch.object(images, 'api') as api, self.assertRaisesRegex(ValueError, '每款'):
            images.submit({**self.data, 'slot': 'secondary'})
        api.assert_not_called()
        self.assertEqual(len(images.budget_status()['reservations']), 1)

    def test_daily_limit_enforced_concurrently_across_products(self):
        self.policy['dailyFen'] = 500
        def run(product):
            try:
                return images.begin_submission({**self.data, 'productId': product,
                    'providerEndpoint': self.quote['endpoint']}, 'APIMart')['id']
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ['P1', 'P2']))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(images.budget_status()['reservations']), 1)

    def test_scoped_override_is_used_by_paid_reservations_only_for_named_product(self):
        self.policy['perProductOverridesFen']={'P':800}
        self.submit(slot='main');self.submit(slot='second')
        with patch.object(images,'api') as api,self.assertRaisesRegex(ValueError,'每款'):
            images.submit({**self.data,'slot':'third'})
        api.assert_not_called()
        self.submit(productId='Other',slot='other-main')
        with patch.object(images,'api') as api,self.assertRaisesRegex(ValueError,'每款'):
            images.submit({**self.data,'productId':'Other','slot':'other-second'})
        api.assert_not_called()
        with closing(images.storage()) as conn:
            record=json.loads(conn.execute("SELECT body FROM image_costs WHERE product_id='P' LIMIT 1").fetchone()[0])
        self.assertEqual(record['limits']['perProductFen'],800)

    def test_unknown_timeout_keeps_reservation_and_retry_block(self):
        with patch.object(images, 'api', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                images.submit(self.data)
        self.assertEqual(images.budget_status()['reservations'][0]['state'], 'reserved')
        with patch.object(images, 'api') as api, self.assertRaisesRegex(ValueError, '未核对'):
            images.submit(self.data)
        api.assert_not_called()

    def test_reconcile_bill_releases_only_verified_difference(self):
        self.submit()
        record = images.budget_status()['reservations'][0]
        result = images.settle_budget({'reservationId': record['reservationId'], 'actualRmb': '1.00',
                                     'externalId': 'task-main', 'evidence': 'test-only bill verified: CNY1.00'})
        self.assertEqual(result['actualFen'], 100)
        self.submit(slot='secondary')
        with self.assertRaisesRegex(ValueError, '已结算'):
            images.settle_budget({'reservationId': record['reservationId'], 'actualRmb': '0',
                                 'externalId': 'task-main', 'evidence': 'test-only duplicate bill'})

    def test_overcharge_is_recorded_and_blocks_all_products(self):
        self.submit()
        record = images.budget_status()['reservations'][0]
        result = images.settle_budget({'reservationId': record['reservationId'], 'actualRmb': '6',
                                     'externalId': 'task-main', 'evidence': 'test-only provider overcharge bill'})
        self.assertEqual(result['state'], 'over_budget')
        with patch.object(images, 'api') as api, self.assertRaisesRegex(ValueError, '超预算账单'):
            images.submit({**self.data, 'productId': 'other'})
        api.assert_not_called()

    def test_disabled_missing_expired_mismatched_and_invalid_quotes_never_call(self):
        for change in ({'verified': False}, {'validUntil': '2000-01-01'}, {'validUntil': 'zzzz'},
                       {'currency': 'USD'}, {'endpoint': 'https://other.example/v1'},
                       {'resolution': '2K'}, {'quantity': 7}, {'maximumRmb': 'NaN'}):
            original = dict(self.quote)
            self.quote.update(change)
            self.write_quote()
            with patch.object(images, 'api') as api, self.assertRaises(ValueError):
                images.submit(self.data)
            api.assert_not_called()
            self.quote = original
        self.write_quote()
        self.policy['enabled'] = False
        with patch.object(images, 'api') as api, self.assertRaisesRegex(ValueError, '关闭'):
            images.submit(self.data)
        api.assert_not_called()
        self.assertEqual(images.jobs()['jobs'], [])

    def test_unsettled_previous_day_still_consumes_daily_budget(self):
        self.policy['dailyFen'] = 500
        self.submit()
        with closing(sqlite3.connect(self.root / 'image_jobs.sqlite3')) as conn, conn:
            conn.execute("UPDATE image_costs SET day='2000-01-01'")
        with patch.object(images, 'api') as api, self.assertRaisesRegex(ValueError, '每日'):
            images.submit({**self.data, 'productId': 'other'})
        api.assert_not_called()

    def test_other_account_cannot_read_or_settle_reservation(self):
        self.submit()
        record = images.budget_status()['reservations'][0]
        other = self.root / 'other-account'
        with patch.object(images, 'ROOT', other):
            self.assertEqual(images.budget_status()['reservations'], [])
            with self.assertRaisesRegex(ValueError, '不存在'):
                images.settle_budget({'reservationId': record['reservationId'], 'actualRmb': '0',
                    'externalId': 'task-main', 'evidence': 'test-only other account billing note'})

    def test_no_bill_evidence_or_wrong_external_id_cannot_release(self):
        self.submit()
        record = images.budget_status()['reservations'][0]
        for update in ({'evidence': ''}, {'externalId': 'different-job'}):
            with self.assertRaises(ValueError):
                images.settle_budget({'reservationId': record['reservationId'], 'actualRmb': '0',
                    'externalId': 'task-main', 'evidence': 'test-only bill evidence', **update})
        self.assertEqual(images.budget_status()['reservations'][0]['state'], 'reserved')

    def usd_quote(self):
        self.quote.update(currency='USD', maximumUsd='0.015', fx={
            'currency':'USD/CNY', 'rate':'6.6652', 'date':budget.day(),
            'source':'https://www.boc.cn/sourcedb/whpj/', 'rateType':'bank_sell_per_usd'})
        self.quote.pop('maximumRmb',None)
        self.write_quote()
        return {'fx_budget_policy':{'mode':'daily_boc_usd_sell_buffer','enabled':True,'bufferPercent':20}}

    def test_usd_preview_and_reservation_are_explicit_estimates_not_bills(self):
        policy=self.usd_quote()
        self.quote['sourceEvidence']='/private/account/source.json'
        self.quote['fx']['sourceEvidence']='/private/account/fx.json'
        self.write_quote()
        with patch.object(budget,'configuration',return_value=policy),patch.object(images,'api') as api:
            result=images.budget_quote(self.data)
            self.assertEqual(result['quote']['maximumFen'],12)
            self.assertEqual(result['quote']['reservationBasis'],'usd_fx_budget_estimate')
            self.assertEqual(result['quote']['currency'],'USD')
            self.assertNotIn('/private/account',json.dumps(result))
            self.assertFalse(result['submitted']);self.assertFalse(result['settled']);self.assertFalse(result['reserved'])
            self.assertEqual(images.budget_status()['reservations'],[])
            api.assert_not_called()
        with patch.object(budget,'configuration',return_value=policy):self.submit()
        record=images.budget_status()['reservations'][0]
        self.assertEqual(record['reservedFen'],12);self.assertIsNone(record['actualFen'])

    def test_usd_policy_date_rate_and_evidence_fail_closed(self):
        policy=self.usd_quote()
        import copy
        original=copy.deepcopy(self.quote)
        invalid=[('policy',{}),('policy',{'fx_budget_policy':{**policy['fx_budget_policy'],'enabled':False}}),
                 ('policy',{'fx_budget_policy':{**policy['fx_budget_policy'],'bufferPercent':0}}),
                 ('fx',{'date':'2000-01-01'}),('fx',{'source':'https://other.example/'}),
                 ('fx',{'rate':'NaN'}),('fx',{'rate':'Infinity'}),('fx',{'rate':True}),
                 ('fx',{'rate':'-1'}),('fx',{'rateType':'bank_buy_per_usd'}),
                 ('quote',{'maximumUsd':'NaN'}),('quote',{'maximumUsd':'nonsense'}),
                 ('quote',{'maximumUsd':True}),('quote',{'verifiedAt':'2000-01-01'})]
        for kind,change in invalid:
            with self.subTest(kind=kind,change=change):
                self.quote=copy.deepcopy(original)
                if kind=='fx':self.quote['fx'].update(change)
                elif kind=='quote':self.quote.update(change)
                self.write_quote()
                with patch.object(budget,'configuration',return_value=change if kind=='policy' else policy),patch.object(images,'api') as api:
                    with self.assertRaises(ValueError):images.submit(self.data)
                    api.assert_not_called()
        self.assertEqual(images.budget_status()['reservations'],[])

    def test_usd_preview_allowed_before_policy_enabled_but_cannot_reserve(self):
        self.usd_quote()
        with patch.object(budget,'configuration',return_value={}),patch.object(images,'api') as api:
            result=images.budget_quote(self.data)
            self.assertEqual(result['quote']['maximumFen'],12)
            self.assertFalse(result['quote']['conversionPolicyEnabled'])
            with self.assertRaises(ValueError):images.submit(self.data)
            api.assert_not_called()
        self.assertEqual(images.budget_status()['reservations'],[])

    def test_desktop_operating_config_reads_live_project_and_fails_on_bad_pointer(self):
        app=self.root/'packaged';app.mkdir()
        live=self.root/'project';(live/'automation').mkdir(parents=True)
        source=live/'automation/config.json'
        source.write_text(json.dumps({'images':{'enabled':False,'per_product_budget_rmb':5,'daily_budget_rmb':200}}),encoding='utf-8')
        (app/'project-root.txt').write_text(str(live),encoding='utf-8')
        with patch.object(budget.app_paths,'APP',app):
            self.assertFalse(budget.configuration()['enabled'])
            source.write_text(json.dumps({'images':{'enabled':True,'per_product_budget_rmb':3,'daily_budget_rmb':50}}),encoding='utf-8')
            self.assertEqual(budget.configuration()['per_product_budget_rmb'],3)
            source.unlink()
            with self.assertRaises(OSError):budget.configuration()


class ProductBudgetOverrideTests(unittest.TestCase):
    def test_override_changes_only_authorized_product(self):
        config={'enabled':True,'per_product_budget_rmb':5,'daily_budget_rmb':200,
                'per_product_budget_overrides':{'cardigan':{'budget_rmb':8,'authorization':'User confirmed this cardigan only'}}}
        with patch.object(budget,'configuration',return_value=config):
            self.assertEqual(budget.product_limits('cardigan')['perProductFen'],800)
            self.assertEqual(budget.product_limits('another')['perProductFen'],500)
            self.assertEqual(budget.limits()['perProductFen'],500)
            self.assertEqual(budget.product_limits('cardigan')['dailyFen'],20000)
            with closing(sqlite3.connect(':memory:')) as conn:
                self.assertEqual(budget.status(conn,'cardigan')['limits']['perProductFen'],800)

    def test_override_without_authorization_fails_closed(self):
        config={'enabled':True,'per_product_budget_rmb':5,'daily_budget_rmb':200,
                'per_product_budget_overrides':{'cardigan':{'budget_rmb':8}}}
        with patch.object(budget,'configuration',return_value=config),self.assertRaises(ValueError):budget.product_limits('cardigan')

if __name__ == '__main__':
    unittest.main()
