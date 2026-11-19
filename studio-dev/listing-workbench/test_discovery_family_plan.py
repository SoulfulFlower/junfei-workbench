"""Real ledger + captured-receipt synthetic integration, never browser execution."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import unittest
from unittest.mock import patch
import test_discovery_plan as fixtures
import discovery_family as family

plan=fixtures.plan
A,B='B000000001','B000000002'


class FamilyPlanTests(unittest.TestCase):
    setUp=fixtures.PlanTests.setUp
    tearDown=fixtures.PlanTests.tearDown
    ingest=fixtures.PlanTests.ingest
    prepare=fixtures.PlanTests.prepare
    receipt=fixtures.PlanTests.receipt
    snapshot=fixtures.PlanTests.snapshot

    def seed(self):
        events=fixtures.chain()[:4]
        events[1]['products'].append({'asin':A,'title':'Cotton Shirt Women'})
        events[3]['products']=[{'asin':B,'title':'Cotton Shirt Blue'}, {'asin':'B000000003','title':'Different pants'}]
        self.ingest(events)

    def family_receipt(self,asin,targets=(A,B),owner=1):
        now=datetime.now(timezone.utc)
        raw=dict(schemaVersion=1,status='captured',reason='visible_variant_controls_observed',
            capturedAt=now.isoformat(),marketplace='US',asin=asin,selectedAsin=asin,
            url='https://amazon.com/dp/'+asin,
            controls=[dict(containerId='variation_color_name',selector='#variation_color_name li[data-asin] a[href]',
                source='visible_twister_anchor',asin=a,dataAsin=a,href='https://amazon.com/dp/'+a,
                label=a,selectedMarker='swatchSelect' if a==asin else '') for a in targets])
        return self.receipt('family-'+asin,owner=owner,captureKind='family',asin=asin,marketplace='US',
            sourceURL='https://amazon.com/dp/'+asin,startedAt=(now-timedelta(seconds=1)).isoformat(),
            finishedAt=(now+timedelta(seconds=1)).isoformat(),bindingDigest='b'*64,
            collectorSha256=hashlib.sha256(plan.browser.FAMILY_COLLECTOR.read_bytes()).hexdigest(),
            familyEvidence=family.normalize_capture(raw,marketplace='US',asin=asin,now=now))

    def test_reciprocal_receipts_suppress_only_repeated_title_not_seller(self):
        self.seed(); self.family_receipt(A);self.family_receipt(B)
        before=self.snapshot();result=self.prepare()
        self.assertEqual(result['familyDedup']['eligibleGroupCount'],1)
        self.assertTrue(any(x['reason']=='observed_family_title_already_handled' and x['sourceASIN']==B for x in result['skipped']))
        self.assertTrue(any(x['kind']=='seller_capture' and x['asin']==A for x in result['actions']))
        self.assertTrue(any(x['kind']=='title_phrase_capture' and x['asin']=='B000000003' for x in result['actions']))
        self.assertEqual(self.snapshot(),before)

    def test_one_sided_or_other_owner_receipts_never_suppress(self):
        self.seed();self.family_receipt(A);self.family_receipt(B,owner=2)
        result=self.prepare()
        self.assertEqual(result['familyDedup']['eligibleGroupCount'],0)
        self.assertTrue(any(x['kind']=='title_phrase_capture' and x['asin']==B for x in result['actions']))

    def test_capture_history_change_during_plan_rejects_stale_preview(self):
        self.seed()
        with patch.object(plan,'_attempts',side_effect=[([], 'first', []),([], 'new', [{'reason':'prior_capture_unresolved'}])]):
            with self.assertRaisesRegex(ValueError,'stale_capture_history'):self.prepare()

    def test_unknown_family_blocks_every_plan_action(self):
        self.seed();self.receipt('unresolved',status='execution_unknown',captureKind='family',asin=A)
        result=self.prepare()
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['actions'],[])

    def test_family_read_does_not_mark_seller_branch_captured(self):
        self.seed();self.family_receipt(A)
        result=self.prepare()
        self.assertTrue(any(x['kind']=='seller_capture' and x['asin']==A for x in result['actions']))
        self.assertFalse(any(x['reason']=='existing_capture_requires_review' and x['sourceASIN']==A for x in result['review']))


if __name__=='__main__':unittest.main()
