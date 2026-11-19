import argparse
import json
from pathlib import Path
import tempfile
import unittest
import workbench_batch as batch


class BatchInputTests(unittest.TestCase):
    def test_supplier_links_cannot_escape_official_detail_host(self):
        self.assertEqual(batch.supplier_url('https://detail.1688.com/offer/123.html?sourceId=x'),
                         'https://detail.1688.com/offer/123.html')
        for value in ['http://detail.1688.com/offer/123.html',
                      'https://detail.1688.com.evil/offer/123.html',
                      'https://u:p@detail.1688.com/offer/123.html',
                      'https://detail.1688.com/offer/123.html#x']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                batch.supplier_url(value)

    def test_protected_or_missing_workbench_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'spaces.json'
            for space_id in (0, 16, None):
                file.write_text(json.dumps({'accountId': 2, 'protectedSpaceIds': [16],
                    'workbench': {'id': space_id, 'name': 'batch', 'page': 'p1'}}), encoding='utf-8')
                with self.subTest(space_id=space_id), self.assertRaises(ValueError):
                    batch.load_session(file)

    def test_business_operations_require_explicit_flag_and_single_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'spaces.json'
            file.write_text(json.dumps({'accountId': 2,
                'workbench': {'id': 18, 'name': 'batch', 'page': 'p1'}}), encoding='utf-8')
            args = argparse.Namespace(session=str(file), supplier=['https://detail.1688.com/offer/123.html'],
                                      job=[], action='supplier-add', execute=False)
            with self.assertRaisesRegex(ValueError, '--execute'):
                batch.make_plan(args)
            args.execute = True
            self.assertEqual(batch.make_plan(args)['suppliers'], args.supplier)
            args.action = 'observe'
            args.job = ['a' * 32, 'b' * 32]
            with self.assertRaisesRegex(ValueError, '一个任务'):
                batch.make_plan(args)
