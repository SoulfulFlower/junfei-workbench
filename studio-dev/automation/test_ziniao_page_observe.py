import json
import unittest
from unittest.mock import patch
import ziniao_page_observe as observe


class NativeObservationTests(unittest.TestCase):
    def responses(self, label):
        return [
            {'ok':True,'data':{'data':{'url':'https://sellercentral.amazon.com/inventory',
             'title':'Inventory','targetId':'T','content':{'text':'Example Store 美国',
             'forms':[{'type':'hidden','value':'private-do-not-record'}],
             'headings':[],'buttons':[],'links':[]}}}},
            {'ok':True,'data':{'result':json.dumps({'origin':'https://sellercentral.amazon.com','labels':[label]})}}
        ]

    def test_exact_visible_header_and_target_required_hidden_fields_omitted(self):
        with patch.object(observe,'native_cli',return_value='cli'), patch.object(observe,'run',side_effect=self.responses('Example Store 美国')) as run:
            result=observe.observe('1','T','https://sellercentral.amazon.com','Example Store','美国')
        self.assertTrue(result['visibleIdentityVerified'])
        self.assertNotIn('private-do-not-record',json.dumps(result))
        self.assertTrue(all(call.args[-2:]==('--target-id','T') for call in run.call_args_list))
        self.assertEqual([call.args[1:3] for call in run.call_args_list],[('page','content'),('page','exec')])

    def test_body_contains_requested_market_but_actual_header_differs_is_rejected(self):
        with patch.object(observe,'native_cli',return_value='cli'), patch.object(observe,'run',side_effect=self.responses('Example Store 德国')):
            with self.assertRaisesRegex(ValueError,'市场身份不符'):
                observe.observe('1','T','https://sellercentral.amazon.com','Example Store','美国')
