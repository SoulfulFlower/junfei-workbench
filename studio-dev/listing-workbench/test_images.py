import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import image_provider as images


class ImageTests(unittest.TestCase):
    def test_upstream_model_unavailable_is_not_reported_as_bad_key(self):
        from urllib.error import HTTPError
        failure = HTTPError('https://api.apimart.ai/v1/chat/completions', 503, 'Unavailable', {}, io.BytesIO(b'{"error":{"code":"model_not_found"}}'))
        with patch.object(images, 'KEY', 'test-key'), patch.object(images, 'urlopen', side_effect=failure) as request:
            with self.assertRaisesRegex(ValueError, '读图分析/图片策划模型通道不可用') as result:
                images.api('chat/completions', {'model':'test'})
            self.assertNotIn('请核对图片密钥', str(result.exception))
            self.assertEqual(request.call_count, 1)

    def setUp(self):
        self.enterContext(patch.object(images, 'storyboard_submission', return_value={}))
        self.temp = tempfile.TemporaryDirectory()
        self.root = patch.object(images, 'ROOT', Path(self.temp.name))
        self.root.start()
        self.budget_limits = patch.object(images.image_budget, 'limits', return_value={
            'enabled': True, 'perProductFen': 500, 'dailyFen': 20000})
        self.budget_limits.start()
        self.addCleanup(self.budget_limits.stop)
        self.quote = patch.object(images.image_budget, 'verified_quote', return_value={'maximumFen': 30, 'source': 'test-only quote'})
        self.quote.start()
        self.addCleanup(self.quote.stop)
        (images.ROOT / 'uploads').mkdir()
        self.name = 'a' * 32 + '.png'
        (images.ROOT / 'uploads' / self.name).write_bytes(b'\x89PNG\r\n\x1a\nreference')
        self.data = dict(model=images.MODELS[2], prompt='Keep product unchanged', references=['/uploads/' + self.name], productId='TEST', slot='主图')

    def tearDown(self):
        self.root.stop()
        self.temp.cleanup()

    def test_reference_encoding_and_persisted_task(self):
        with patch.object(images, 'api', return_value={'data': [{'task_id': 'test-task'}]}) as api:
            job = images.submit(self.data)
            sent = api.call_args.args[1]
            self.assertTrue(sent['image_urls'][0].startswith('data:image/png;base64,'))
            self.assertEqual(sent['n'], 1)
            self.assertEqual(job['id'], 'test-task')
        self.assertEqual(images.jobs()['jobs'][0]['id'], 'test-task')

    def test_submission_is_durable_before_provider_call_and_timeout_cannot_resubmit(self):
        def submit(*args):
            entries = images.jobs()['jobs']
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['status'], 'submitting')
            raise TimeoutError('provider timed out')
        with patch.object(images, 'api', side_effect=submit) as api:
            with self.assertRaises(TimeoutError):
                images.submit(self.data)
            pending = images.jobs()['jobs'][0]
            self.assertEqual(pending['status'], 'submission_unknown')
            changed = {**self.data, 'prompt': 'a changed prompt must not bypass uncertainty'}
            with self.assertRaisesRegex(ValueError, '未核对'):
                images.submit(changed)
            self.assertEqual(images.poll({'id': pending['id']})['status'], 'submission_unknown')
            self.assertEqual(api.call_count, 1)

    def test_job_persistence_failure_keeps_provider_id_and_prevents_second_charge(self):
        with patch.object(images, 'api', return_value={'data': [{'task_id': 'external-known'}]}) as api:
            with patch.object(images, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    images.submit(self.data)
            pending = images.jobs()['jobs'][0]
            self.assertEqual(pending['externalId'], 'external-known')
            self.assertEqual(pending['status'], 'submission_unknown')
            with self.assertRaisesRegex(ValueError, '未核对'):
                images.submit(self.data)
            self.assertEqual(api.call_count, 1)
            restored = images.poll({'id': pending['id']})
            self.assertEqual(restored['id'], 'external-known')
            self.assertEqual(restored['status'], 'submitted')
            self.assertEqual([job['id'] for job in images.jobs()['jobs']], ['external-known'])
            self.assertEqual(api.call_count, 1)

    def test_completed_provider_response_recovers_without_another_paid_call(self):
        result = dict(id='sync-complete', productId='TEST', slot='主图', status='completed',
                      images=['/uploads/'+'b'*32+'.png'], provider='AIGoCode')
        with patch.object(images, 'dispatch_submission', return_value=result) as dispatch:
            with patch.object(images, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    images.submit(self.data)
            pending = images.jobs()['jobs'][0]
            with patch.object(images, 'api') as api:
                restored = images.poll({'id': pending['id']})
                self.assertEqual(restored, result)
                self.assertEqual(images.poll({'id': restored['id']}), result)
            api.assert_not_called()
            self.assertEqual(dispatch.call_count, 1)

    def test_existing_provider_job_prevents_duplicate_slot_submission(self):
        images.save(dict(id='existing', productId='TEST', slot='主图', status='processing', images=[]))
        with patch.object(images, 'api') as api:
            with self.assertRaisesRegex(ValueError, '进行中任务'):
                images.submit(self.data)
        api.assert_not_called()

    def test_missing_product_or_slot_does_not_call_provider(self):
        for key in ('productId', 'slot'):
            with patch.object(images, 'api') as api:
                with self.assertRaisesRegex(ValueError, '产品ID和图位'):
                    images.submit({**self.data, key: ''})
            api.assert_not_called()

    def test_upstream_gpt_official_preserves_legacy_contract(self):
        self.data.update(model='gpt-image-2-official',size='16:9')
        with patch.object(images,'api',return_value={'data':[{'task_id':'gpt-task'}]}) as api:
            images.submit(self.data)
        body=api.call_args.args[1]
        self.assertEqual(body['input_fidelity'],'high')
        self.assertEqual(body['size'],'1464x600')
        self.assertNotIn('resolution',body)
        self.assertEqual(body['model'],'gpt-image-2-official')

    def test_gpt_image2_preserves_quoted_resolution_ratio_and_all_references(self):
        for tier in ('1K', '2K', '4K'):
            for ratio in ('1:1', '4:5', '3:4', '16:9'):
                with self.subTest(tier=tier, ratio=ratio):
                    refs = ['data:image/png;base64,ref'] * 4
                    with patch.object(images, 'api', return_value={'data':[{'task_id':'tier-task'}]}) as api:
                        images.dispatch_submission(self.data, {'active':False}, 'gpt-image-2',
                                                   'test prompt', [], ratio, tier, refs)
                    body=api.call_args.args[1]
                    self.assertEqual(body['size'], ratio)
                    self.assertEqual(body['resolution'], tier.lower())
                    self.assertEqual(body['image_urls'], refs)
                    self.assertEqual(body['n'], 1)

    def test_collected_reference(self):
        self.data['references'] = ['https://cbu01.alicdn.com/img/test.jpg']
        with patch.object(images, 'build_opener') as opener, patch.object(images, 'api', return_value={'data': [{'task_id': 'remote'}]}) as api:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'\xff\xd8\xffimage'
            images.submit(self.data)
            self.assertTrue(api.call_args.args[1]['image_urls'][0].startswith('data:image/jpeg;base64,'))
        for ref in ['https://127.0.0.1/a', 'https://cbu01.alicdn.com.evil.com/a']:
            with self.assertRaises(ValueError):
                images.remote_reference(ref)

    def test_outside_reference_blocked(self):
        self.data['references'] = ['/uploads/../../private.png']
        with patch.object(images, 'api') as api, self.assertRaises(ValueError):
            images.submit(self.data)
        api.assert_not_called()

    def test_poll_and_terminal_cache(self):
        images.save(dict(id='task-one', status='pending', images=[]))
        response = {'data': {'status': 'completed', 'progress': 100, 'result': {'images': [{'url': ['https://upload.apimart.ai/example.png']}]}}}
        with patch.object(images, 'api', return_value=response) as api:
            self.assertEqual(images.poll({'id': 'task-one'})['images'], ['https://upload.apimart.ai/example.png'])
            self.assertEqual(images.poll({'id': 'task-one'})['status'], 'completed')
            self.assertEqual(api.call_count, 1)

    def test_http_auth_error_no_key_leak(self):
        from urllib.error import HTTPError
        with patch.object(images, 'KEY', 'fake-secret'), patch.object(images, 'urlopen', side_effect=HTTPError('https://api.apimart.ai', 401, '', {}, None)):
            with self.assertRaises(ValueError) as error:
                images.api('images/generations', {})
            self.assertIn('401', str(error.exception))
            self.assertNotIn('fake-secret', str(error.exception))

    def test_empty_result_not_success(self):
        images.save(dict(id='empty', status='pending', images=[]))
        with patch.object(images, 'api', return_value={'data': {'status': 'completed', 'result': {}}}):
            self.assertEqual(images.poll({'id': 'empty'})['status'], 'failed')

    def test_key_models_filter_and_no_credential_return(self):
        payload = {'data': [{'id': images.MODELS[0], 'category': 'image'}, {'id': 'other-image', 'category': 'image'}, {'id': 'chat-model', 'category': 'chat'}]}
        with patch.object(images, 'KEY', ''), patch.object(images, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as mocked:
            result = images.test_key({'api_key': 'test-image-secret'})
            self.assertEqual(result['supportedModels'], [images.MODELS[0]])
            self.assertEqual(len(result['models']), 2)
            self.assertNotIn('test-image-secret', json.dumps(result))
            self.assertIn('/v1/models?expand=category&category=image', mocked.call_args.args[0].full_url)


if __name__ == '__main__':
    unittest.main()
