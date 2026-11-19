"""Authenticated read-only family/run HTTP boundaries; all data temporary."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cyclic_discovery as ledger
import discovery_browser as browser
import discovery_family_bridge as bridge
import discovery_run
import test_discovery_api as fixtures


class FamilyAPITests(unittest.TestCase):
    call = fixtures.DiscoveryAPITests.call
    batch = fixtures.DiscoveryAPITests.batch
    setUpClass = classmethod(fixtures.DiscoveryAPITests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.DiscoveryAPITests.tearDownClass.__func__)
    setUp = fixtures.DiscoveryAPITests.setUp

    def test_family_and_inspect_routes_are_session_scoped_and_bounded(self):
        rows = [('/api/discovery/capture-family',browser,'capture_family',
                 dict(captureId='family',cycleId='cycle',expectedRevision=1,parentId='search',asin='B012345678')),
                ('/api/discovery/assess-families',bridge,'assess',dict(cycleId='cycle',expectedRevision=1)),
                ('/api/discovery/inspect-run',discovery_run,'inspect',dict(cycleId='cycle',expectedRevision=1,maxActions=2,maxRounds=2))]
        for route,module,method,payload in rows:
            with self.subTest(route=route),patch.object(module,method,return_value={'readOnly':True}) as action:
                for headers,code in [({'authenticated':False},401),({'Origin':'https://external.invalid'},403),({'Origin':'chrome-extension://fixture'},403),({'X-Workspace-Account':'2'},409)]:
                    self.assertEqual(self.call(route,payload,**headers)[0],code)
                self.assertEqual(self.call(route,[])[0],400)
                self.assertEqual(self.call(route,{'padding':'x'*5000})[0],400)
                action.assert_not_called()
                self.assertEqual(self.call(route,payload),(200,{'readOnly':True}))
                action.assert_called_once_with(1,payload)

    def test_empty_assessment_and_run_inspection_never_write_or_dispatch(self):
        self.assertEqual(self.call('/api/discovery/ingest',self.batch())[0],200)
        before=ledger.report(1,'api-cycle')
        request={'cycleId':'api-cycle','expectedRevision':1}
        db=Path(self.tempLedger.name)/'browser.sqlite3'
        with patch.object(browser,'DB',db),patch.object(browser,'_binding',side_effect=ValueError('unconfigured')),patch.object(browser.subprocess,'run',side_effect=AssertionError('No browser permitted')):
            code,result=self.call('/api/discovery/assess-families',request)
            self.assertEqual(code,200,result)
            self.assertTrue(result['readOnly']);self.assertFalse(result['executionAllowed'])
            self.assertEqual(result['assessment']['dedupEligibleGroupCount'],0)
            self.assertFalse(db.exists())
            self.assertEqual(self.call('/api/discovery/assess-families',request)[1],result)
            self.assertEqual(self.call('/api/discovery/assess-families',{**request,'evidence':[]})[0],400)
            self.assertEqual(self.call('/api/discovery/assess-families',{**request,'owner':2})[0],400)
            self.assertEqual(self.call('/api/discovery/assess-families',{**request,'expectedRevision':0})[0],400)
            code,run=self.call('/api/discovery/inspect-run',{**request,'maxActions':2,'maxRounds':2})
            self.assertEqual(code,200,run)
            self.assertEqual(run['status'],'execution_disabled')
            self.assertFalse(run['automaticNavigationImplemented'])
            self.assertFalse(db.exists())
        self.assertEqual(ledger.report(1,'api-cycle'),before)

    def test_bridge_rejects_foreign_scope_and_changed_history(self):
        ledger.ingest(1,self.batch())
        request={'cycleId':'api-cycle','expectedRevision':1}
        with patch.object(browser,'DB',Path(self.tempLedger.name)/'browser.sqlite3'):
            with self.assertRaises(ValueError):bridge.assess(2,request)
            with patch('discovery_plan._attempts',side_effect=[([], 'a', []),([], 'b', [])]):
                with self.assertRaisesRegex(ValueError,'assessment_scope_changed'):bridge.assess(1,request)


if __name__=='__main__':unittest.main()
