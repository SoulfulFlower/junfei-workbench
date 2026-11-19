import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import provider
import visual_studio


class ModelReceiptsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.data=patch.object(provider.app_paths,'DATA',self.root)
        self.data.start()

    def tearDown(self):
        self.data.stop()
        self.temp.cleanup()

    def receipts(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in (self.root/'listing-responses').glob('*.json')]

    def test_text_success_keeps_usage_but_not_request_headers_or_context(self):
        raw={'id':'response1','model':'model','usage':{'total_tokens':27},'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],'headers':{'Authorization':'never-save'}}
        with patch.dict(provider.SETTINGS,{'api_key':'test-key','model':'model','provider':'deepseek'}),patch.object(provider,'urlopen',return_value=io.BytesIO(json.dumps(raw).encode())) as remote:
            self.assertEqual(visual_studio.model_json('private instruction',{'market':'US','private':'not-receipt'},[]),{'ok':True})
        remote.assert_called_once()
        record=self.receipts()[0]
        self.assertEqual(record['response']['usage']['total_tokens'],27)
        self.assertEqual(record['provider'],'DeepSeek')
        self.assertNotIn('headers',record['response'])
        self.assertNotIn('test-key',json.dumps(record))
        self.assertNotIn('private instruction',json.dumps(record))
        self.assertNotIn('not-receipt',json.dumps(record))

    def test_codex_proxy_uses_compatible_chat_payload_and_labels_receipt(self):
        raw={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
        with patch.dict(provider.SETTINGS,{'provider':'codex_tools','proxy_model':'gpt-6-sol'}), \
             patch.object(provider,'proxy_key',return_value='test-proxy-key'), \
             patch.object(provider.codex_tools,'request_json',return_value=raw) as proxy, \
             patch.object(provider,'urlopen') as direct:
            self.assertEqual(visual_studio.model_json('Inspect',{},[]),{'ok':True})
        direct.assert_not_called()
        endpoint,payload=proxy.call_args.args
        self.assertEqual(endpoint,'http://127.0.0.1:8787/v1/chat/completions')
        body=json.loads(payload)
        self.assertEqual(body['model'],'gpt-6-sol')
        self.assertNotIn('response_format',body)
        self.assertNotIn('thinking',body)
        self.assertEqual(self.receipts()[0]['provider'],'Codex Tools')

    def test_vision_parse_failure_retains_response_without_retry(self):
        raw={'id':'vision1','model':'vision','choices':[{'finish_reason':'stop','message':{'content':'not JSON'}}],'usage':{'total_tokens':5}}
        with patch.object(visual_studio.image_provider,'api',return_value=raw) as remote:
            with self.assertRaisesRegex(ValueError,'回执 [a-f0-9]{32}'):
                visual_studio.model_json('Inspect',{},['https://example.test/reference.jpg'])
        remote.assert_called_once()
        self.assertEqual(self.receipts()[0]['provider'],'APIMart')
        self.assertEqual(self.receipts()[0]['response'],raw)
        self.assertNotIn('reference.jpg',json.dumps(self.receipts()[0]))

    def test_truncated_nonobject_and_null_outputs_are_retained_not_adopted(self):
        for reason,content in [('length','{"incomplete":'),('stop','[]'),('stop',None)]:
            with patch.object(visual_studio.image_provider,'api',return_value={'choices':[{'finish_reason':reason,'message':{'content':content}}]}) as remote:
                with self.assertRaisesRegex(ValueError,'原始响应已保存'):
                    visual_studio.model_json('Inspect',{},['https://example.test/reference.jpg'])
            remote.assert_called_once()
        self.assertEqual(len(self.receipts()),3)

    def test_disk_failure_after_response_does_not_send_second_request(self):
        with patch.object(visual_studio.image_provider,'api',return_value={'choices':[]}) as remote,patch.object(provider,'save_listing_response',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(ValueError,'回执保存失败'):
                visual_studio.model_json('Inspect',{},['https://example.test/reference.jpg'])
        remote.assert_called_once()

    def test_account_runtime_directories_stay_separate(self):
        raw={'id':'account-a','choices':[]}
        a=provider.save_listing_response(raw,'analysis',purpose='visual_or_auxiliary',provider_name='APIMart')
        other=self.root/'other-account'
        with patch.object(provider.app_paths,'DATA',other):
            b=provider.save_listing_response({'id':'account-b','choices':[]},'analysis')
        self.assertFalse((self.root/'listing-responses'/f'{b}.json').exists())
        self.assertFalse((other/'listing-responses'/f'{a}.json').exists())


if __name__=='__main__':unittest.main()
