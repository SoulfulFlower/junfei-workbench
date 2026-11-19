import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import aigocode_provider as relay
import image_provider as images

class RelayTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(images, 'storyboard_submission', return_value={}))
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.config=patch.object(relay,'CONFIG',self.root/'aigocode.json');self.config.start()
        self.imagesroot=patch.object(images,'ROOT',self.root);self.imagesroot.start()
        self.data=patch.object(relay.app_paths,'DATA',self.root);self.data.start()
        self.keys={}
        self.keyload=patch.object(relay.secrets_store,'load',side_effect=lambda name:self.keys.get(name,''));self.keyload.start()
        self.keysave=patch.object(relay.secrets_store,'save',side_effect=lambda name,value:self.keys.__setitem__(name,value));self.keysave.start()
    def tearDown(self):
        self.keysave.stop();self.keyload.stop();self.data.stop();self.config.stop();self.imagesroot.stop();self.tmp.cleanup()
    def test_config_key_is_separate_and_active_models(self):
        out=relay.configure({'api_key':'private-key','base_url':'https://api.aigocode.dev/v1','model':'img-custom','models':['img-custom'],'activate':True})
        self.assertEqual(self.keys,{'aigocode':'private-key'})
        self.assertEqual(out['model'],'img-custom');self.assertTrue(out['active'])
        self.assertFalse(out['baseUrl'].startswith('http://'))
    def test_image_settings_configure_keeps_public_response_shape(self):
        out=images.configure({'provider':'aigocode','api_key':'private-key','base_url':'https://api.aigocode.dev/v1','model':'img-custom','activate':True})
        self.assertIn('aigocode',out)
        self.assertTrue(out['aigocode']['hasKey'])
        self.assertEqual(out['aigocode']['model'],'img-custom')
    def test_refuses_http_and_private_endpoints(self):
        for url in ['http://example.com/v1','https://127.0.0.1/v1','https://example.com/v1?x=y']:
            with self.assertRaises(ValueError):relay.configure({'base_url':url})
    def test_generation_uses_edits_and_b64_cache(self):
        relay.configure({'api_key':'own-key','activate':True,'model':'img-custom','models':['img-custom'],'base_url':'https://api.aigocode.dev/v1'})
        image=b'\x89PNG\r\n\x1a\nreal-pixels'
        response=io.BytesIO(json.dumps({'data':[{'b64_json':base64.b64encode(image).decode()}]}).encode())
        response.__enter__=lambda:response;response.__exit__=lambda *args:None
        self.assertEqual(relay._multipart('m','p','1024x1024','2k',['data:image/png;base64,'+base64.b64encode(image).decode()])[1].split(';')[0],'multipart/form-data')
        with patch.object(relay,'_open',return_value=response) as call:
            url=relay.generate('img-custom','make it','1024x1024','2k',['data:image/png;base64,'+base64.b64encode(image).decode()])
        self.assertIn('/uploads/',url)
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith('/images/edits'))
        self.assertIn(b'name="image"',req.data)
        self.assertEqual(Path(self.root/'uploads'/url.split('/')[-1]).read_bytes(),image)
    def test_submission_pins_active_provider_completed_local_result(self):
        relay.configure({'api_key':'own-key','activate':True,'model':'img-custom','models':['img-custom'],'base_url':'https://api.aigocode.dev/v1'})
        (self.root/'uploads').mkdir(exist_ok=True); name='a'*32+'.png';(self.root/'uploads'/name).write_bytes(b'\x89PNG\r\n\x1a\nref')
        with patch.object(relay,'generate',return_value='/uploads/'+'b'*32+'.png') as gen, patch.object(images.image_budget,'limits',return_value={'enabled':True,'perProductFen':500,'dailyFen':20000}), patch.object(images.image_budget,'verified_quote',return_value={'maximumFen':30,'source':'test-only quote'}):
            job=images.submit({'model':'img-custom','prompt':'same exact product','references':['/uploads/'+name],'productId':'P','slot':'main'})
        self.assertEqual(job['status'],'completed');self.assertEqual(job['provider'],'AIGoCode')
        gen.assert_called_once()
    def test_model_query_returns_openai_ids(self):
        payload=json.dumps({'data':[{'id':'image-alpha'},{'id':'text-only'}]}).encode()
        response=io.BytesIO(payload);response.__enter__=lambda:response;response.__exit__=lambda *args:None
        with patch.object(relay,'_open',return_value=response):
            result=relay.test_key({'api_key':'key'})
        self.assertEqual(result['models'],['image-alpha','text-only'])
if __name__=='__main__':unittest.main()
