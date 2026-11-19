import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import image_provider as provider


class ResultCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = patch.object(provider, 'ROOT', Path(self.tmp.name))
        root.start(); self.addCleanup(root.stop)
        self.job = {'id':'original-task', 'productId':'one', 'status':'completed',
                    'images':['https://example.com/temporary.png'], 'cost':0.015}
        provider.save(self.job)

    def test_completed_poll_saves_local_result_once_without_provider_request(self):
        asset = {'url':'/uploads/'+'a'*32+'.png', 'sha256':'b'*64}
        with patch.object(provider.custom_images, 'remote_image', return_value=asset) as download, \
             patch.object(provider, 'api', side_effect=AssertionError('no provider request')):
            result = provider.poll({'id':self.job['id']})
            again = provider.poll({'id':self.job['id']})
        self.assertEqual(result['images'], [asset['url']])
        self.assertEqual(result['providerImages'], self.job['images'])
        self.assertEqual(result['cost'], 0.015)
        self.assertEqual(again, result)
        self.assertEqual(download.call_count, 1)

    def test_download_failure_keeps_completion_and_retries_only_the_download(self):
        asset = {'url':'/uploads/'+'a'*32+'.png'}
        with patch.object(provider.custom_images, 'remote_image', side_effect=[OSError(),asset]) as download, \
             patch.object(provider, 'api', side_effect=AssertionError('no generation or task request')):
            failed_cache = provider.poll({'id':self.job['id']})
            self.assertEqual(failed_cache['status'], 'completed')
            self.assertEqual(failed_cache['images'], self.job['images'])
            self.assertEqual(failed_cache['resultCache']['status'], 'pending')
            recovered = provider.poll({'id':self.job['id']})
        self.assertEqual(recovered['resultCache']['status'], 'saved')
        self.assertEqual(download.call_count, 2)

    def test_non_completed_job_is_not_downloaded(self):
        self.job['status'] = 'failed'
        provider.save(self.job)
        with patch.object(provider.custom_images, 'remote_image') as download:
            self.assertEqual(provider.poll({'id':self.job['id']})['status'], 'failed')
        download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
