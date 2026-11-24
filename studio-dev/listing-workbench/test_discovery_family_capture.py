"""Synthetic isolated integration of guarded current-page family observations."""
import copy
from contextlib import closing
from datetime import datetime, timezone
import subprocess
import unittest
from unittest.mock import patch
import discovery_browser as browser
import test_discovery_browser as fixtures


class FamilyCaptureTests(unittest.TestCase):
    tearDown = fixtures.CaptureTests.tearDown
    def run_capture(self, args, **kwargs):
        if not getattr(self, 'keep_timestamp', False):
            self.raw['capturedAt'] = datetime.now(timezone.utc).isoformat()
        return fixtures.CaptureTests.run_capture(self, args, **kwargs)

    def setUp(self):
        fixtures.CaptureTests.setUp(self)
        self.parent.update(query='fixture', sourceType='browser_visible', parentId='root')
        self.parent['products'] = [{'asin': self.request['asin'], 'title': 'Fixture product'}]
        self.raw = {'schemaVersion': 1, 'status': 'captured',
            'reason': 'visible_variant_controls_observed',
            'capturedAt': datetime.now(timezone.utc).isoformat(),
            'marketplace': 'US', 'asin': self.request['asin'],
            'url': 'https://amazon.com/dp/' + self.request['asin'],
            'selectedAsin': self.request['asin'],
            'controls': [{'containerId': 'variation_color_name',
                'selector': '#variation_color_name li[data-asin] a[href]',
                'source': 'visible_twister_anchor', 'asin': self.request['asin'],
                'dataAsin': self.request['asin'], 'href': 'https://amazon.com/dp/' + self.request['asin'],
                'label': 'Blue', 'selectedMarker': 'swatchSelect'},
               {'containerId': 'variation_color_name',
                'selector': '#variation_color_name li[data-asin] a[href]',
                'source': 'visible_twister_anchor', 'asin': 'B012345679',
                'dataAsin': 'B012345679', 'href': 'https://amazon.com/dp/B012345679',
                'label': 'Green', 'selectedMarker': ''}]}

    def test_capture_is_receipt_only_and_replays_without_browser(self):
        result = browser.capture_family(1, self.request)
        self.assertEqual(result['status'], 'captured', result)
        self.assertEqual(result['captureKind'], 'family')
        self.assertNotIn('preparedBatch', result)
        self.assertEqual(result['familyEvidence'], result['evidence'])
        self.assertEqual(result['familyEvidence']['selectedAsin'], self.request['asin'])
        self.assertEqual(browser.capture_family(1, self.request), result)
        self.assertEqual(self.mocks[-1].call_count, 1)
        self.assertEqual(browser.history(2), {'items': []})
        with self.assertRaises(ValueError): browser.capture(1, self.request)

    def test_any_unknown_stops_all_four_capture_kinds(self):
        self.mocks[-1].side_effect = subprocess.TimeoutExpired('fixture', 45)
        result = browser.capture_family(1, self.request)
        self.assertEqual(result['status'], 'execution_unknown')
        requests = [(browser.capture, {**self.request, 'captureId': 'seller'}),
                    (browser.capture_family, {**self.request, 'captureId': 'family2'}),
                    (browser.capture_search, {k:v for k,v in {**self.request, 'captureId':'search'}.items() if k!='asin'}),
                    (browser.capture_store, {**{k:v for k,v in self.request.items() if k!='asin'}, 'sellerId':'SELLER1', 'captureId':'store'})]
        for call, request in requests:
            receipt = call(1, request)
            self.assertEqual(receipt['reason'], 'prior_capture_unresolved')
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_unrecognized_and_corrupt_history_blocks_direct_capture(self):
        import json
        for i, status in enumerate(('unknown', 'running', 'unexpected', 'captured')):
            with closing(browser._connect(True)) as conn, conn:
                conn.execute('DELETE FROM attempts')
                raw = json.dumps(dict(captureId='prior',cycleId='other',parentId='p',captureKind='family',status=status)) if status != 'captured' else '{broken'
                conn.execute('INSERT INTO attempts VALUES (?,?,?,?,?)',(1,'prior','x',status,raw))
            result=browser.capture_family(1,{**self.request,'captureId':'next-'+str(i)})
            self.assertEqual(result['reason'],'prior_capture_unresolved')
        self.mocks[-1].assert_not_called()

    def test_wrong_target_controls_time_and_scope_fail_closed(self):
        original = copy.deepcopy(self.raw)
        variants = [dict(asin='B012345679'), dict(selectedAsin='B012345679'),
                    dict(marketplace='UK'), dict(url='https://example.com/dp/B012345678'),
                    dict(capturedAt='2000-01-01T00:00:00+00:00'), dict(controls=[])]
        for i, changes in enumerate(variants):
            self.raw = {**copy.deepcopy(original), **changes}
            self.keep_timestamp = 'capturedAt' in changes
            result = browser.capture_family(1, {**self.request, 'captureId':'bad-'+str(i)})
            self.assertEqual(result['status'], 'blocked', result)
            self.assertNotIn('familyEvidence', result)
            self.assertNotIn('preparedBatch', result)

    def test_family_parent_cannot_select_unrecorded_product(self):
        for i, changes in enumerate(({'asin':'B099999999'}, {'expectedRevision':1}, {'parentId':'other'})):
            result = browser.capture_family(1, {**self.request, **changes, 'captureId':'scope-'+str(i)})
            self.assertEqual(result['reason'], 'parent_or_revision_invalid')
        self.mocks[-1].assert_not_called()

    def test_keyword_source_is_supported_but_other_asin_is_not(self):
        self.parent.clear()
        self.parent.update(id='search1', kind='keyword', parentId=None, marketplace='US',
            sourceType='browser_visible', observedAt='2025-01-01T00:00:00+00:00',
            asin=self.request['asin'], sourceTitle='Fixture product', phrase='Fixture',
            url='https://amazon.com/dp/'+self.request['asin'])
        result=browser.capture_family(1,self.request)
        self.assertEqual(result['status'],'captured',result)
        self.assertEqual(self.mocks[-1].call_count,1)

    def test_scope_change_after_dispatch_discards_family_evidence(self):
        def run(*args,**kwargs):
            result=self.run_capture(*args,**kwargs)
            self.config['discovery_browser']['account_bindings']['1']['page_label']='changed'
            return result
        self.mocks[-1].side_effect=run
        result=browser.capture_family(1,self.request)
        self.assertEqual(result['status'],'blocked')
        self.assertNotIn('familyEvidence',result)


if __name__ == '__main__': unittest.main()
