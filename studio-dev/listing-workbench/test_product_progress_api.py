import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import accounts
import server


class ProductProgressAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.patches = [patch.object(accounts, 'DB', cls.root / 'accounts.sqlite3'),
                       patch.object(server, 'DATA', cls.root),
                       patch.object(server.account_spaces, 'needs_proxy', return_value=False)]
        for item in cls.patches:
            item.start()
        accounts.register({'username': 'progress-test', 'password': 'isolated-password-12345'}, setup=True)
        cls.token, _ = accounts.login({'username': 'progress-test', 'password': 'isolated-password-12345'}, 'test')
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        for item in reversed(cls.patches):
            item.stop()
        cls.temp.cleanup()

    def call(self, auth=True, **headers):
        if auth:
            headers['Cookie'] = 'studio_session=' + self.token
        request = urllib.request.Request(self.base + '/api/products/progress', headers=headers)
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)
        with response:
            return response.status, json.load(response)

    def test_auth_and_account_scope_precede_read(self):
        with patch.object(server.product_progress, 'summary', return_value={'products': []}) as summary:
            self.assertEqual(self.call(auth=False)[0], 401)
            self.assertEqual(self.call(**{'X-Workspace-Account': '2'})[0], 409)
            summary.assert_not_called()
            self.assertEqual(self.call(**{'X-Workspace-Account': '1'}), (200, {'products': []}))
            summary.assert_called_once_with(self.root, 1)

    def test_damaged_ledger_is_a_read_failure_not_empty_success(self):
        with patch.object(server.product_progress, 'summary', side_effect=ValueError('damaged')):
            status, body = self.call()
            self.assertEqual(status, 503)
            self.assertIn('error', body)
            self.assertNotIn('products', body)


if __name__ == '__main__':
    unittest.main()
