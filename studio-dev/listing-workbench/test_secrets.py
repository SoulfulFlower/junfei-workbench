import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import secrets_store


class SecretTests(unittest.TestCase):
    def test_encrypted_roundtrip_and_delete(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(secrets_store, 'ROOT', Path(folder)):
            for service in ('deepseek', 'apimart'):
                secrets_store.save(service, 'fake-secret-roundtrip')
                self.assertNotIn(b'fake-secret-roundtrip', secrets_store.location(service).read_bytes())
                self.assertEqual(secrets_store.load(service), 'fake-secret-roundtrip')
                secrets_store.save(service, '')
                self.assertEqual(secrets_store.load(service), '')

    def test_shared_mcp_uses_central_file_and_refreshes(self):
        import os
        import sellersprite
        with tempfile.TemporaryDirectory() as folder:
            shared=Path(folder)/'shared'
            with patch.dict(os.environ, {'JUNFEI_SHARED_CREDENTIALS':str(shared), 'SELLERSPRITE_MCP_KEY':''}):
                with patch.object(secrets_store,'ROOT',Path(folder)/'admin'):
                    secrets_store.save('sellersprite','shared-one')
                with patch.object(secrets_store,'ROOT',Path(folder)/'employee'):
                    self.assertEqual(sellersprite.Client().key,'shared-one')
                    self.assertEqual(secrets_store.load('deepseek'),'')
                    secrets_store.save('sellersprite','shared-two')
                    self.assertEqual(sellersprite.Client().key,'shared-two')
                    secrets_store.save('sellersprite','')
                    self.assertFalse(sellersprite.public()['hasKey'])
                    with self.assertRaises(ValueError):sellersprite.Client()
