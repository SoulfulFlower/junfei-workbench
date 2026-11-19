"""HTTP boundaries for explicitly isolated pilot, never production execution."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_discovery_api as fixtures
import cyclic_discovery as ledger
import discovery_browser as browser


class LiveAPITests(unittest.TestCase):
    call=fixtures.DiscoveryAPITests.call
    batch=fixtures.DiscoveryAPITests.batch
    setUpClass=classmethod(fixtures.DiscoveryAPITests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.DiscoveryAPITests.tearDownClass.__func__)
    setUp=fixtures.DiscoveryAPITests.setUp

    def request(self):
        return dict(runId='pilot-api',cycleId='api-cycle',expectedRevision=1,maxActions=3,
                    maxRounds=2,maxSeconds=60,planFingerprint='f'*64,sourceEventId='keyword-1')

    def test_start_stop_auth_origin_account_size_and_session_owner(self):
        import discovery_live as live
        rows=[('/api/discovery/start-live','start',self.request(),202),
              ('/api/discovery/stop-live','stop',dict(runId='pilot-api',cancel=True),200)]
        for route,method,payload,success in rows:
            with self.subTest(route=route),patch.object(live,method,return_value={'status':'fixture'}) as action:
                for headers,code in [({'authenticated':False},401),({'Origin':'https://external.invalid'},403),({'Origin':'chrome-extension://fixture'},403),({'X-Workspace-Account':'2'},409)]:
                    self.assertEqual(self.call(route,payload,**headers)[0],code)
                self.assertEqual(self.call(route,[])[0],400)
                self.assertEqual(self.call(route,{'padding':'x'*5000})[0],400)
                action.assert_not_called()
                self.assertEqual(self.call(route,payload),(success,{'status':'fixture'}))
                if method=='start':action.assert_called_once_with(1,payload)
                else:action.assert_called_once_with(1,'pilot-api',cancel=True)

    def test_stop_requires_explicit_boolean_and_exact_fields(self):
        import discovery_live as live
        with patch.object(live,'stop') as stop:
            for data in ({'runId':'pilot-api'}, {'runId':'pilot-api','cancel':1},
                         {'runId':'pilot-api','cancel':'false'}, {'runId':'pilot-api','cancel':False,'owner':2}):
                self.assertEqual(self.call('/api/discovery/stop-live',data)[0],400)
            stop.assert_not_called()

    def test_status_is_authenticated_and_uses_session_identity(self):
        import discovery_live as live
        with patch.object(live,'status',return_value={'status':'stopped'}) as status:
            self.assertEqual(self.call('/api/discovery/live-run?id=pilot-api',authenticated=False)[0],401)
            self.assertEqual(self.call('/api/discovery/live-run?id=pilot-api',**{'X-Workspace-Account':'2'})[0],409)
            status.assert_not_called()
            self.assertEqual(self.call('/api/discovery/live-run?id=pilot-api'),(200,{'status':'stopped'}))
            status.assert_called_once_with(1,'pilot-api')

    def test_default_environment_cannot_start_live_or_dispatch(self):
        import discovery_live as live
        db=Path(self.tempLedger.name)/'attempts.sqlite3'
        with patch.dict(os.environ,{'JUNFEI_DISCOVERY_LIVE':''}),patch.object(browser,'DB',db),patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser')):
            code,result=self.call('/api/discovery/start-live',self.request())
            self.assertEqual(code,400,result)
            self.assertFalse(db.exists())

    def test_missing_stop_and_status_do_not_create_database(self):
        db=Path(self.tempLedger.name)/'absent-attempts.sqlite3'
        with patch.object(browser,'DB',db):
            self.assertEqual(self.call('/api/discovery/live-run?id=missing')[0],400)
            self.assertEqual(self.call('/api/discovery/stop-live',{'runId':'missing','cancel':False})[0],400)
            self.assertFalse(db.exists())

    def test_manual_graph_write_is_guarded(self):
        import discovery_live as live
        with patch.object(live,'owner_write_guard',side_effect=ValueError('active isolated run')):
            code,result=self.call('/api/discovery/ingest',self.batch())
            self.assertEqual(code,400,result)
        self.assertFalse(self.path.exists())
        with patch.object(live,'assert_owner_idle',side_effect=ValueError('active isolated run')):
            self.assertEqual(self.call('/api/discovery/prepare-keyword',{})[0],400)
        self.assertFalse(self.path.exists())


if __name__=='__main__':unittest.main()
