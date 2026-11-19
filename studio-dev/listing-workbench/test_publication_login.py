"""Inspect the actual helper command without browser, store or ERP operations."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import publication_flow as flow


class PublicationLoginMethodTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.policy = self.root / 'market-authorizations.json'
        for name, value in (('MARKET_DOM_AUTHORIZATIONS', self.policy), ('ROOT', self.root / 'jobs')):
            guard = patch.object(flow, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        self.job = {'id': 'original-job', 'accountId': 2}
        self.connection = {'accountId': 2, 'storeId': '27852913493513', 'storeName': '示例店铺',
                           'seller': 'Example Store', 'erpAccount': '示例ERP账号'}
        self.authorization = {'accountId': 2, 'storeId': self.connection['storeId'], 'seller': 'Example Store',
                              'market': 'UK', 'allowMarketDomClick': True,
                              'source': 'Explicit user authorization of this store market input method only',
                              'authorizedAt': '2026-11-17T10:41:04+08:00'}

    def save_policy(self, authorization=None, **changes):
        policy = {'version': 1, 'authorizations': [self.authorization if authorization is None else authorization]}
        policy.update(changes)
        self.policy.write_text(json.dumps(policy), encoding='utf-8')

    def command(self, market='UK'):
        with patch.object(flow.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            flow.login(self.job, self.connection, market)
        run.assert_called_once()
        return run.call_args.args[0]

    def test_exact_authorization_adds_flag_once_without_changing_business_input_or_receipt(self):
        self.save_policy()
        before = copy.deepcopy((self.job, self.connection))
        receipt = flow.ROOT / self.job['id'] / 'login-UK.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text('{"oldReceipt":"preserved"}', encoding='utf-8')
        command = self.command()
        self.assertEqual(command.count('--allow-market-dom-click'), 1)
        for flag, value in (('--store-id', self.connection['storeId']), ('--seller', 'Example Store'),
                            ('--market', 'UK'), ('--account', '示例ERP账号'), ('--receipt', str(receipt))):
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn('--ensure-site', command)
        self.assertEqual((self.job, self.connection), before)
        self.assertEqual(receipt.read_text(encoding='utf-8'), '{"oldReceipt":"preserved"}')

    def test_missing_or_unreadable_policy_keeps_existing_helper_command_without_method_flag(self):
        self.assertNotIn('--allow-market-dom-click', self.command())
        for invalid in ('{broken', '[]', 'null', '{"version":true,"authorizations":[]}'):
            self.policy.write_text(invalid, encoding='utf-8')
            self.assertNotIn('--allow-market-dom-click', self.command())

    def test_other_account_store_seller_or_market_cannot_inherit_current_authorization(self):
        self.save_policy()
        for changes in ({'accountId': 3}, {'storeId': '27852913493514'}, {'seller': 'Other'},
                        {'seller': 'marlowi'}, {'storeId': 27852913493513}, {'accountId': '2'}):
            with self.subTest(changes=changes):
                original = self.connection
                self.connection = {**original, **changes}
                try:
                    self.assertNotIn('--allow-market-dom-click', self.command())
                finally:
                    self.connection = original
        self.job['accountId'] = 3
        self.connection['accountId'] = 3
        self.assertNotIn('--allow-market-dom-click', self.command())
        self.job['accountId'] = self.connection['accountId'] = 2
        for market in ('US', 'GB', 'DE', 'uk'):
            self.assertNotIn('--allow-market-dom-click', self.command(market))

    def test_false_string_boolean_wildcard_or_incomplete_authorizations_fail_closed(self):
        for change in ({'allowMarketDomClick': False}, {'allowMarketDomClick': 'true'},
                       {'allowMarketDomClick': 1}, {'accountId': True}, {'storeId': '*'},
                       {'seller': '*'}, {'market': '*'}, {'source': ''}, {'authorizedAt': ''},
                       {'authorizedAt': '2026-11-17'}, {'authorizedAt': 'not-a-date'}):
            with self.subTest(change=change):
                self.save_policy({**self.authorization, **change})
                self.assertNotIn('--allow-market-dom-click', self.command())
        for field in self.authorization:
            incomplete = dict(self.authorization)
            incomplete.pop(field)
            self.save_policy(incomplete)
            self.assertNotIn('--allow-market-dom-click', self.command())

    def test_helper_failure_retains_original_error_contract_even_with_method_authorization(self):
        self.save_policy()
        with patch.object(flow.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as run:
            with self.assertRaisesRegex(ValueError, 'UK店铺、站点或插件登录未通过，原发布记录保留'):
                flow.login(self.job, self.connection, 'UK')
        self.assertIn('--allow-market-dom-click', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
