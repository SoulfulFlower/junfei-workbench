"""In-memory authenticated route tests: no socket, HTTP request, DB or model calls."""
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import server


class ExhaustedReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.user={'id':2,'role':'admin','name':'Isolated fixture'}
        self.patches=[patch.object(server.app_paths,'WORKER_USER',0),
            patch.object(server.accounts,'session_token',return_value='isolated-session'),
            patch.object(server.accounts,'identify',return_value=self.user),
            patch.object(server.account_spaces,'needs_proxy',return_value=False)]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def dispatch(self, payload, **headers):
        raw=json.dumps(payload).encode()
        replies=[]
        def reply(status,data):
            replies.append((status,data));return status,data
        handler=SimpleNamespace(path='/api/listing-jobs/continue-exhausted-review',
            headers={'Content-Length':str(len(raw)),'Host':'isolated.test','X-Workspace-Account':'2',**headers},
            rfile=io.BytesIO(raw), origin=lambda:'http://isolated.test',
            reply=reply)
        handler.read_body=lambda limit:server.Handler.read_body(handler,limit)
        server.Handler.do_POST(handler)
        return replies[-1]

    def payload(self):
        return {'id':'a'*32,'requestId':'isolated-exhausted-route-001','inputDigest':'b'*64,
                'bulletsSha256':'c'*64,'targetBullets':[3],
                'receipts':[{'id':format(n,'032x'),'sha256':'d'*64} for n in range(9)]}

    def test_explicit_new_route_passes_authenticated_owner_and_keeps_reuse_status(self):
        payload=self.payload()
        with patch.object(server.listing_jobs,'continue_exhausted_review',return_value={'id':'a'*32,'reused':False}) as follow, \
             patch.object(server.listing_jobs,'resume_review') as old, \
             patch.object(server.listing_jobs,'continue_returned_review') as returned:
            code,body=self.dispatch(payload)
            self.assertEqual(code,202);self.assertEqual(body['job']['id'],'a'*32)
            self.assertEqual(follow.call_args.args,(2,payload));old.assert_not_called();returned.assert_not_called()
            follow.return_value={'id':'a'*32,'reused':True,'status':'needs_review'}
            self.assertEqual(self.dispatch(payload)[0],200)

    def test_auth_account_origin_and_body_type_checks_precede_executor(self):
        with patch.object(server.listing_jobs,'continue_exhausted_review') as follow:
            with patch.object(server.accounts,'identify',return_value=None):
                self.assertEqual(self.dispatch(self.payload())[0],401)
            self.assertEqual(self.dispatch(self.payload(),**{'X-Workspace-Account':'3'})[0],409)
            self.assertEqual(self.dispatch(self.payload(),Origin='https://foreign.test')[0],403)
            self.assertEqual(self.dispatch([])[0],400)
            follow.assert_not_called()

    def test_new_scope_validation_failure_is_400_without_falling_back_to_generation(self):
        with patch.object(server.listing_jobs,'continue_exhausted_review',side_effect=ValueError('Frozen scope rejected')), \
             patch.object(server.listing_jobs,'start') as start:
            code,body=self.dispatch(self.payload())
            self.assertEqual(code,400);self.assertEqual(body['error'],'Frozen scope rejected')
            start.assert_not_called()


if __name__=='__main__':unittest.main()
