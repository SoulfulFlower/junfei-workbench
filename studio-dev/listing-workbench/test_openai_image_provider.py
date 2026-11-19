import base64
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import closing
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image

import image_provider as images
import image_budget
import openai_image_provider as custom


class CompatibleImagesTests(unittest.TestCase):
    def test_portrait_reference_uses_wide_carrier_without_stretching_the_product(self):
        source=io.BytesIO()
        Image.new('RGB',(200,400),'#802030').save(source,'PNG')
        ref='data:image/png;base64,'+base64.b64encode(source.getvalue()).decode()
        wide=custom.wide_reference(ref)
        with Image.open(io.BytesIO(base64.b64decode(wide.split(',',1)[1]))) as image:
            self.assertEqual(image.size,(1464,600))
            self.assertEqual(image.getpixel((732,300)),(128,32,48))
            self.assertEqual(image.getpixel((0,300)),(243,240,234))
        self.assertEqual(custom.wide_reference(wide),wide)

    def setUp(self):
        self.enterContext(patch.object(images, 'storyboard_submission', return_value={}))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.keys = {}
        for obj, name, value in [
            (custom, 'CONFIG', self.root/'custom.json'),
            (custom.app_paths, 'DATA', self.root),
            (images, 'ROOT', self.root),
            (custom.transport, 'CONFIG', self.root/'relay.json'),
        ]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        for p in [patch.object(custom.secrets_store, 'load', side_effect=lambda n:self.keys.get(n,'')),
                  patch.object(custom.secrets_store, 'save', side_effect=lambda n,v:self.keys.__setitem__(n,v)),
                  patch.object(custom.transport, '_validate_url', side_effect=lambda u:u)]:
            p.start(); self.addCleanup(p.stop)
        self.data = {'model':'gpt-image-2','productId':'P','slot':'main','prompt':'Exact product',
                     'size':'1:1','resolution':'2K','references':['/uploads/'+'a'*32+'.png']}
        buf = io.BytesIO(); Image.new('RGB',(32,48),'green').save(buf,'PNG'); self.png=buf.getvalue()
        path=self.root/self.data['references'][0].lstrip('/'); path.parent.mkdir(); path.write_bytes(self.png)
        images.configure({'provider':'openai','api_key':'test-only-key','activate':True})

    def paid_policy(self):
        self.enterContext(patch.object(images.image_budget,'limits',return_value={'enabled':True,'perProductFen':500,'dailyFen':20000}))
        self.enterContext(patch.object(images.image_budget,'verified_quote',return_value={'maximumFen':30,'source':'test-only'}))

    def test_repair_rejects_changed_source_bytes_before_provider_or_budget(self):
        original_hash=hashlib.sha256(self.png).hexdigest()
        path=self.root/self.data['references'][0].lstrip('/')
        path.write_bytes(b'changed since the original request')
        with patch.object(images,'begin_submission') as reserve,patch.object(custom,'submit') as dispatch:
            with self.assertRaises(images.ReferenceChanged):
                images.submit({**self.data,'expectedReferenceSha256':[original_hash]})
        reserve.assert_not_called()
        dispatch.assert_not_called()

    def test_account_key_and_current_service_are_separate(self):
        self.assertEqual(self.keys, {'openai_image':'test-only-key'})
        self.assertEqual(images.public()['provider'], custom.PROVIDER)
        self.assertFalse(images.public()['hasKey'] and 'test-only-key' in str(images.public()))
        self.assertNotIn('test-only-key', custom.CONFIG.read_text())
        images.configure({'activeProvider':'apimart'})
        self.assertEqual(images.public()['provider'],'APIMart')
        self.assertEqual(self.keys['openai_image'],'test-only-key')

    def test_codex_tools_models_request_bypasses_system_proxy_and_redirects(self):
        custom.configure({'base_url':custom.CODEX_TOOLS_BASE})
        response=MagicMock()
        response.read.return_value=b'{"data":[{"id":"gpt-image-2"}]}'
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value=response
        with patch.object(custom,'build_opener',return_value=opener) as build:
            result=custom.test_key({})
        self.assertTrue(result['ok'])
        self.assertEqual(result['models'],['gpt-image-2'])
        self.assertEqual(build.call_args.args[0].proxies,{})
        self.assertIsInstance(build.call_args.args[1],custom.transport._NoRedirect)
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,custom.CODEX_TOOLS_BASE+'/models')
        self.assertEqual(request.get_header('Authorization'),'Bearer test-only-key')

    def test_proxy_error_is_redacted_persisted_and_blocks_replay(self):
        self.paid_policy()
        # This transport test must not depend on the desktop's live route or accounts.
        self.enterContext(patch.object(image_budget.codex_tools_quota, 'verify',
            return_value={'accountingBasis':'chatgpt_subscription_quota','units':1,'unit':'request'}))
        custom.configure({'base_url':custom.CODEX_TOOLS_BASE})
        secret='test-only-key'
        message='upstream 403 '+secret+' Bearer sensitive-token user@example.com https://example.com/error?token=secret-query'
        error=HTTPError(custom.CODEX_TOOLS_BASE+'/images/edits',502,'bad gateway',{},io.BytesIO(json.dumps({'error':{'message':message}}).encode()))
        opener=MagicMock();opener.open.side_effect=error
        with patch.object(custom,'build_opener',return_value=opener):
            with self.assertRaises(custom.image_proxy_diagnostics.ProxyHTTPError) as caught:images.submit(self.data)
            with self.assertRaisesRegex(ValueError,'未核对'):images.submit(self.data)
        self.assertEqual(opener.open.call_count,1)
        diagnostic=caught.exception.diagnostic
        saved=(self.root/'image-errors'/(diagnostic['id']+'.json')).read_text(encoding='utf-8')
        for value in [secret,'sensitive-token','user@example.com','secret-query']:
            self.assertNotIn(value,saved+str(caught.exception))
        self.assertEqual(diagnostic['httpStatus'],502)
        self.assertIn('upstream 403',saved)
        with closing(images.storage()) as conn:
            record=json.loads(conn.execute('SELECT body FROM submission_attempts').fetchone()[0])
        self.assertEqual(record['status'],'submission_unknown')
        self.assertEqual(record['proxyDiagnostic']['id'],diagnostic['id'])

    def test_remote_http_error_body_is_never_read_or_saved(self):
        body=MagicMock();error=HTTPError('https://api.example/v1/images/edits',502,'bad gateway',{},body)
        with patch.object(custom.transport,'_open',side_effect=error):
            with self.assertRaisesRegex(ValueError,'HTTP 502'):custom.request_json(error.url,b'{}')
        body.read.assert_not_called()
        self.assertFalse((self.root/'image-errors').exists())

    def test_proxy_invalid_body_and_storage_failure_preserve_http_status(self):
        error=HTTPError(custom.CODEX_TOOLS_BASE+'/images/edits',502,'bad gateway',{},io.BytesIO(b'<html>private</html>'))
        with patch.object(Path,'mkdir',side_effect=OSError):
            diagnostic=custom.image_proxy_diagnostics.capture(error,error.url,'key')
        self.assertEqual(diagnostic['httpStatus'],502)
        self.assertFalse(diagnostic['saved'])
        self.assertNotIn('private',str(diagnostic))

    def test_real_pixels_cached_with_dimensions_and_hash(self):
        parsed=custom.parse_result({'data':[{'b64_json':base64.b64encode(self.png).decode()}]})
        self.assertEqual(parsed['status'],'completed')
        self.assertEqual((parsed['assets'][0]['width'],parsed['assets'][0]['height']),(32,48))
        self.assertEqual((self.root/parsed['images'][0].lstrip('/')).read_bytes(),self.png)
        with self.assertRaises(ValueError):
            custom.parse_result({'data':[{'b64_json':base64.b64encode(b'not pixels').decode()}]})

    def test_edits_quality_and_canvas_not_resolution_as_quality(self):
        self.paid_policy()
        with patch.object(custom,'request_json',return_value={'data':[{'b64_json':base64.b64encode(self.png).decode()}]}) as send:
            job=images.submit(self.data)
        self.assertEqual(job['status'],'completed')
        self.assertTrue(send.call_args.args[0].endswith('/images/edits'))
        body=send.call_args.args[1]
        self.assertIn(b'2048x2048',body); self.assertIn(b'medium',body)
        self.assertNotIn(b'input_fidelity',body)
        self.assertIn(b'name="image"',body)
        self.assertEqual(job['canvas'],'2048x2048')

    def test_codex_tools_1600_output_preserves_source_and_receipt_policy(self):
        self.paid_policy()
        self.enterContext(patch.object(image_budget.codex_tools_quota, 'verify',
            return_value={'accountingBasis':'chatgpt_subscription_quota','units':1,'unit':'request'}))
        custom.configure({'base_url':custom.CODEX_TOOLS_BASE})
        policy={'codex_tools':{'output_size':'1600x1600'}}
        payload={'data':[{'b64_json':base64.b64encode(self.png).decode()}]}
        with patch.object(image_budget,'configuration',return_value=policy), \
             patch.object(custom,'request_json',return_value=payload) as send:
            job=images.submit({**self.data,'resolution':'1600'})
        self.assertEqual(send.call_count,1)
        self.assertIn(b'1600x1600',send.call_args.args[1])
        asset=job['assets'][0]
        self.assertEqual((asset['width'],asset['height']),(1600,1600))
        self.assertTrue(asset['processing']['upscaled'])
        self.assertEqual((self.root/asset['sourceAsset']['url'].lstrip('/')).read_bytes(),self.png)
        with Image.open(self.root/asset['url'].lstrip('/')) as picture:
            self.assertEqual(picture.getpixel((0,800)),(255,255,255))
            self.assertEqual(picture.getpixel((800,800)),(0,128,0))
        # Recovery uses the policy in the response receipt, even after settings change.
        with patch.object(image_budget,'configuration',return_value={}), \
             patch.object(custom,'request_json',side_effect=AssertionError('no new generation')):
            restored=custom.recover(job['responseReceipt'],'P','main')
        self.assertEqual((restored['assets'][0]['width'],restored['assets'][0]['height']),(1600,1600))

    def test_fixed_square_policy_rejects_other_ratios_before_submission(self):
        custom.configure({'base_url':custom.CODEX_TOOLS_BASE})
        with patch.object(image_budget,'configuration',return_value={'codex_tools':{'output_size':'1600x1600'}}), \
             patch.object(images,'begin_submission') as reserve, patch.object(custom,'request_json') as send:
            with self.assertRaisesRegex(ValueError,'1:1'):images.submit({**self.data,'size':'4:5'})
        reserve.assert_not_called();send.assert_not_called()

    def test_codex_tools_aplus_uses_wide_native_edits_or_reference_free_generation(self):
        custom.configure({'base_url':custom.CODEX_TOOLS_BASE})
        base={**self.data,'size':'16:9','deliveryCanvas':'1464x600'}
        image='data:image/png;base64,'+base64.b64encode(self.png).decode()
        response={'data':[{'b64_json':base64.b64encode(self.png).decode()}]}
        with patch.object(image_budget,'configuration',return_value={'codex_tools':{'output_size':'1600x1600'}}), \
             patch.object(custom,'request_json',return_value=response) as send:
            edited=custom.submit(base,[image],custom.specification(base))
            request={**base,'references':[]}
            generated=custom.submit(request,[],custom.specification(request))
        edit,generate=send.call_args_list
        self.assertTrue(edit.args[0].endswith('/images/edits'))
        self.assertIn(b'1464x600',edit.args[1])
        self.assertTrue(generate.args[0].endswith('/images/generations'))
        body=json.loads(generate.args[1])
        self.assertEqual(body['size'],'1464x600')
        self.assertNotIn('image_urls',body)
        self.assertEqual(edited['assets'][0]['height'],48)
        self.assertEqual(generated['assets'][0]['height'],48)

    def test_reference_json_is_explicit_and_async_id_survives(self):
        self.paid_policy()
        images.configure({'provider':'openai','protocol':'reference_json'})
        with patch.object(custom,'request_json',return_value={'data':[{'task_id':'external_123'}]}) as send:
            job=images.submit(self.data)
        body=json.loads(send.call_args.args[1])
        self.assertEqual(body['quality'],'medium'); self.assertEqual(len(body['image_urls']),1)
        self.assertEqual(job['externalId'],'external_123')
        self.assertNotEqual(job['id'],'external_123')
        self.assertEqual(job['status'],'submitted')

    def test_codex_tools_square_information_slot_uses_reference_free_generation(self):
        custom.configure({'base_url':custom.CODEX_TOOLS_BASE})
        request={**self.data,'size':'1:1','references':[]}
        with patch.object(image_budget,'configuration',return_value={'codex_tools':{'output_size':'1600x1600'}}):
            spec=custom.specification(request)
        self.assertEqual((spec['protocol'],spec['canvas']),('generations','1600x1600'))

    def test_multiple_edit_references_use_array_field_and_exact_ratio(self):
        encoded='data:image/png;base64,'+base64.b64encode(self.png).decode()
        with patch.object(custom,'request_json',return_value={'data':[{'task_id':'two_refs'}]}) as send:
            custom.submit(self.data,[encoded,encoded],custom.specification(self.data))
        self.assertEqual(send.call_args.args[1].count(b'name="image[]"'),2)
        self.assertEqual(custom.canvas('3:4','1K'),'1008x1344')

    def test_url_result_download_never_receives_api_credentials(self):
        with patch.object(custom,'remote_image',return_value={'url':'/uploads/test.png','width':8,'height':8}) as get:
            result=custom.parse_result({'data':[{'url':'https://cdn.example/image.png?signature=1'}]})
        get.assert_called_once_with('https://cdn.example/image.png?signature=1')
        self.assertEqual(result['images'],['/uploads/test.png'])

    def test_timeout_does_not_retry_or_fall_back_and_blocks_resubmit(self):
        self.paid_policy()
        with patch.object(custom,'request_json',side_effect=TimeoutError) as send, patch.object(images,'api') as legacy:
            with self.assertRaises(TimeoutError):images.submit(self.data)
            with self.assertRaisesRegex(ValueError,'未核对'):images.submit(self.data)
        self.assertEqual(send.call_count,1); legacy.assert_not_called()

    def test_response_persisted_before_pixel_cache_and_restored_without_paid_request(self):
        self.paid_policy()
        with patch.object(custom,'request_json',return_value={'data':[{'b64_json':base64.b64encode(self.png).decode()}]}) as send:
            with patch.object(custom,'cache_image',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):images.submit(self.data)
            pending=images.jobs()['jobs'][0]
            self.assertTrue(pending.get('responseReceipt'))
            restored=images.poll({'id':pending['id']})
            self.assertEqual(restored['status'],'completed')
            self.assertEqual(send.call_count,1)

    def test_poll_pins_original_endpoint_after_active_service_changes(self):
        self.paid_policy()
        with patch.object(custom,'request_json',return_value={'data':[{'task_id':'external_123'}]}):job=images.submit(self.data)
        images.configure({'activeProvider':'apimart'})
        with patch.object(custom,'request_json',return_value={'data':{'status':'processing','progress':50}}) as read, patch.object(images,'api') as legacy:
            polled=images.poll({'id':job['id']})
        self.assertEqual(polled['status'],'processing')
        self.assertEqual(read.call_args.args[0],'https://api.openai.com/v1/tasks/external_123')
        legacy.assert_not_called()

    def test_invalid_4k_square_does_not_call_provider_or_reserve(self):
        with patch.object(images,'begin_submission') as reserve, patch.object(custom,'request_json') as send:
            with self.assertRaisesRegex(ValueError,'4K'):images.submit({**self.data,'resolution':'4K'})
        send.assert_not_called(); reserve.assert_not_called()

    def test_missing_key_is_rejected_before_reservation(self):
        self.keys.clear()
        with patch.object(images,'begin_submission') as reserve,patch.object(custom,'request_json') as send:
            with self.assertRaisesRegex(ValueError,'密钥'):images.submit(self.data)
        reserve.assert_not_called();send.assert_not_called()

    def test_new_endpoint_or_key_is_never_sent_to_original_job_host(self):
        self.paid_policy()
        with patch.object(custom,'request_json',return_value={'data':[{'task_id':'external_123'}]}):
            job=images.submit(self.data)
        images.configure({'provider':'openai','base_url':'https://new.example/v1','api_key':'different-key'})
        with patch.object(custom,'request_json') as request:
            with self.assertRaisesRegex(ValueError,'凭据配置已改变'):images.poll({'id':job['id']})
        request.assert_not_called()

    def test_completed_local_image_reaches_studio_and_export_consumers(self):
        import studio_bridge
        import generated_gallery
        url=self.data['references'][0]
        with patch.object(studio_bridge.visual,'get_run',return_value={'id':'a'*32,'image':url}):
            raw,mime=studio_bridge.result_image('a'*32)
        self.assertEqual(raw,self.png);self.assertEqual(mime,'image/png')
        self.assertEqual(generated_gallery.download(url),self.png)
        for url in ('/uploads/../private.png','/uploads/not-a-uuid.png'):
            with self.assertRaises(ValueError):images.local_image(url)

    def test_quote_cannot_reuse_other_protocol_or_quality(self):
        quote={'provider':custom.PROVIDER,'model':'gpt-image-2','endpoint':'https://api.openai.com/v1',
            'size':'1:1','resolution':'2K','quantity':1,'currency':'CNY','maximumRmb':'1.00',
            'verified':True,'source':'test-only','verifiedAt':image_budget.day(),'validUntil':image_budget.day(),
            'protocol':'edits','quality':'medium'}
        (self.root/'image-price-quotes.json').write_text(json.dumps({'quotes':[quote]}))
        data={**self.data,'providerEndpoint':quote['endpoint'],'protocol':'edits','quality':'high'}
        with self.assertRaises(ValueError):image_budget.verified_quote(self.root,custom.PROVIDER,data)
        data['quality']='medium'
        self.assertEqual(image_budget.verified_quote(self.root,custom.PROVIDER,data)['maximumFen'],100)


class EndpointValidationTests(unittest.TestCase):
    def test_only_exact_codex_tools_loopback_is_allowed(self):
        self.assertEqual(custom.validate_base('http://127.0.0.1:8787/v1/'),custom.CODEX_TOOLS_BASE)
        for value in ['http://localhost:8787/v1','http://127.0.0.1:8788/v1',
                      'http://127.0.0.1:8787/v1?x=y','http://127.0.0.1:8787/v1/other',
                      'http://user:pass@127.0.0.1:8787/v1','http://192.168.0.118:8787/v1',
                      'http://127.0.0.1:8787.evil.test/v1']:
            with self.subTest(value=value),self.assertRaises(ValueError):custom.validate_base(value)

    def test_public_services_still_use_the_existing_strict_validator(self):
        with patch.object(custom.transport,'_validate_url',return_value='validated') as validate:
            self.assertEqual(custom.validate_base('https://images.example/v1'),'validated')
        validate.assert_called_once_with('https://images.example/v1')


if __name__ == '__main__':unittest.main()
