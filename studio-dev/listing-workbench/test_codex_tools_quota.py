import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import codex_tools_quota as quota
import image_budget


class CodexToolsQuotaTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.enterContext(patch.dict(quota.os.environ,{'APPDATA':str(self.root)}))
        self.store=self.root/'com.carry.codex-tools'/'accounts.json';self.store.parent.mkdir()
        self.write(['chatgpt'])
        self.policy={'enabled':True,'mode':'chatgpt_subscription_quota'}
        self.data={'providerEndpoint':quota.BASE,'model':'gpt-image-2','protocol':'edits'}

    def write(self,kinds):
        self.store.write_text(json.dumps({'accounts':[{'sourceKind':kind,'apiProxyEnabled':True} for kind in kinds],
                                         'settings':{'apiProxyPort':8787}}))

    def test_requires_explicit_policy_and_subscription_only_sources(self):
        self.assertIsNone(quota.verify(self.policy,self.data)['cashCost'])
        with self.assertRaises(ValueError):quota.verify({},self.data)
        for kinds in [[],['relay'],['chatgpt','relay'],['unknown']]:
            self.write(kinds)
            with self.subTest(kinds=kinds),self.assertRaises(ValueError):quota.verify(self.policy,self.data)

    def test_wrong_endpoint_model_protocol_cannot_use_quota(self):
        for key,value in [('providerEndpoint','https://api.openai.com/v1'),('model','other'),('protocol','reference_json')]:
            with self.subTest(key=key),self.assertRaises(ValueError):quota.verify(self.policy,{**self.data,key:value})

    def test_square_information_slot_can_reserve_a_reference_free_request(self):
        request={**self.data,'protocol':'generations','size':'1:1','references':[]}
        self.assertEqual(quota.verify(self.policy,request)['units'],1)
        with self.assertRaises(ValueError):
            quota.verify(self.policy,{**request,'references':['product']})

    def test_subscription_call_is_separate_from_cash_and_keeps_unknown(self):
        db=sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        attempt={'id':'submission-test','productId':'P','provider':'OpenAI-compatible'}
        with patch.object(image_budget,'limits',return_value={'enabled':True}),patch.object(image_budget,'configuration',return_value={'codex_tools':self.policy}):
            reservation=image_budget.reserve(db,self.root,attempt,self.data)
        self.assertEqual(reservation['accountingBasis'],'chatgpt_subscription_quota')
        self.assertIsNone(reservation['cashCost'])
        self.assertNotIn('reservedFen',reservation)
        quota.update(db,{**attempt,'status':'submission_unknown'})
        self.assertEqual(quota.status(db)[0]['state'],'submission_unknown')
        self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='image_costs'").fetchone())
        quota.update(db,{**attempt,'status':'recorded','externalId':'job-test','providerJob':{'status':'completed'}})
        self.assertEqual(quota.status(db)[0]['state'],'completed')


if __name__=='__main__':unittest.main()
