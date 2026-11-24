import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server
import secrets_store


class CloudTests(unittest.TestCase):
    def test_forwarded_https_requires_explicit_loopback_trust(self):
        handler = object.__new__(server.Handler)
        handler.connection = object()
        handler.headers = {'X-Forwarded-Proto': 'https', 'Host': '203.0.113.10'}
        handler.client_address = ('127.0.0.1', 1234)
        with patch.dict(os.environ, {'JUNFEI_TRUST_PROXY': '0'}):
            self.assertFalse(handler.secure_request())
        with patch.dict(os.environ, {'JUNFEI_TRUST_PROXY': '1'}):
            self.assertTrue(handler.secure_request())
            self.assertEqual(handler.origin(), 'http://127.0.0.1:18765')
            handler.client_address = ('198.51.100.1', 1234)
            self.assertFalse(handler.secure_request())

    def test_linux_secrets_need_master_key_and_reject_wrong_key(self):
        from cryptography.fernet import Fernet
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder)/'master.key'
            key.write_bytes(Fernet.generate_key())
            with patch.object(secrets_store, 'WINDOWS', False), patch.dict(os.environ, {'JUNFEI_MASTER_KEY_FILE': str(key)}):
                encrypted = secrets_store.crypt(b'fake-test-key')
                self.assertNotIn(b'fake-test-key', encrypted)
                self.assertEqual(secrets_store.crypt(encrypted, True), b'fake-test-key')
                key.write_bytes(Fernet.generate_key())
                with self.assertRaises(ValueError):
                    secrets_store.crypt(encrypted, True)
