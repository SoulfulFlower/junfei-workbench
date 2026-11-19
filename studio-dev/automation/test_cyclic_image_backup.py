import unittest
from cyclic_image_backup import partition_backups


class BackupExceptionTests(unittest.TestCase):
    def setUp(self):
        self.row = {'url': 'https://example.com/dead.jpg', 'source': 'supplier_reference_pending_image_review',
                    'status': 'failed', 'error': 'Error: HTTP 404'}
        self.proof = {'url': self.row['url'], 'http_status': 404, 'reason': 'source link confirmed unavailable',
                      'evidence_file': 'source-image-evidence.json'}

    def test_unavailable_is_retained_and_never_counted_downloaded(self):
        downloaded, unavailable = partition_backups([self.row], [self.proof])
        self.assertEqual(downloaded, [])
        self.assertEqual(unavailable[0]['status'], 'failed')
        self.assertFalse(unavailable[0]['productionApproved'])

    def test_amazon_required_references_cannot_be_exempted(self):
        with self.assertRaises(ValueError):
            partition_backups([{**self.row, 'source': 'amazon_reference_only'}], [self.proof])

    def test_timeouts_and_other_http_errors_cannot_be_exempted(self):
        for error in ['Error: HTTP 500', 'TimeoutError']:
            with self.subTest(error=error), self.assertRaises(ValueError):
                partition_backups([{**self.row, 'error': error}], [self.proof])

    def test_unreviewed_failure_or_stale_exception_is_rejected(self):
        with self.assertRaises(ValueError):
            partition_backups([self.row])
        with self.assertRaises(ValueError):
            partition_backups([], [self.proof])
