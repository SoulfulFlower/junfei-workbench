"""Authenticated route wiring with an isolated server and no model calls."""
import unittest
from unittest.mock import patch
import test_server as api_fixtures
import server

class ReviewRecoveryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):api_fixtures.StudioTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):api_fixtures.StudioTests.tearDownClass.__func__(cls)
    setUp=api_fixtures.StudioTests.setUp
    call=api_fixtures.StudioTests.call
    def test_explicit_resume_payload_preserves_owner_and_once_only_status(self):
        payload={'id':'a'*32,'requestId':'review-recovery-fixture-001','receipts':{key:{'id':ident*32,'sha256':'f'*64} for key,ident in [('initial','b'),('polish','c'),('review','d')]}}
        with patch.object(server.listing_jobs,'resume_review',return_value={'id':'a'*32,'reused':False}) as resume:
            code,body=self.call('/api/listing-jobs/resume-review',payload)
            self.assertEqual(code,202);self.assertEqual(body['job']['id'],'a'*32)
            self.assertEqual(resume.call_args.args,(1,payload))
            resume.return_value={'id':'a'*32,'reused':True,'status':'needs_review'}
            code,body=self.call('/api/listing-jobs/resume-review',payload)
            self.assertEqual(code,200);self.assertTrue(body['job']['reused'])
        with patch.object(server.listing_jobs,'resume_review') as resume:
            code,_=self.call('/api/listing-jobs/resume-review',[])
            self.assertEqual(code,400);resume.assert_not_called()
        continuation={'id':'a'*32,'reviewRecoveryId':'b'*32,'requestId':'continue-returned-fixture',
                      'returnedReceipt':{'id':'c'*32,'sha256':'d'*64}}
        with patch.object(server.listing_jobs,'continue_returned_review',return_value={'id':'a'*32,'reused':False}) as follow:
            code,_=self.call('/api/listing-jobs/continue-returned-review',continuation)
            self.assertEqual(code,202);self.assertEqual(follow.call_args.args,(1,continuation))
            follow.return_value={'id':'a'*32,'reused':True}
            code,_=self.call('/api/listing-jobs/continue-returned-review',continuation)
            self.assertEqual(code,200)

if __name__=='__main__':unittest.main()
