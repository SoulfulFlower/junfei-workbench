import copy
from contextlib import ExitStack
import hashlib
import json
import unittest
from unittest.mock import patch

import listing_format_recovery as recovery
import listing_jobs as jobs
import provider
from test_listing_jobs import ListingJobTests

ORIGINAL_GENERATE = provider.generate_listing


class FormatRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ListingJobTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        with jobs.database() as conn:
            rev, state = jobs.workspace(conn)
            state['products'][0]['sourceImport']['supplier'] = {'url':'https://detail.1688.com/offer/123456789012.html'}
            conn.execute('UPDATE workspace SET body=? WHERE id=1', (json.dumps(state),))
        self.job = self.fixture.start()
        jobs.ACTIVE.discard(self.job['id'])
        with jobs.database() as conn:
            job = jobs.owned(conn, 2, self.job['id'])
            job.update(status='needs_review', error=recovery.ERROR)
            jobs.save(conn, job)
        self.folder = jobs.DB.parent/'listing-responses'
        self.folder.mkdir()
        self.refs = {}
        self.records = {}
        self.identity = {k:job[k] for k in ['owner','productId','inputDigest']}
        self.identity['jobId'] = job['id']
        for i, stage in enumerate(['initial','polish'], 1):
            rid = str(i)*32
            record = {'market':'US','listingTask':self.identity,'provider':'fixture',
                'createdAt':f'2026-11-20T08:0{i}:00Z','response':{'id':'response-'+stage,'model':'mock-text',
                'choices':[{'finish_reason':'stop','message':{'content':'{"title":"Complete returned stage"}'}}]}}
            if stage == 'polish': record['purpose'] = 'listing_unslop'
            raw = json.dumps(record).encode()
            (self.folder/(rid+'.json')).write_bytes(raw)
            self.refs[stage] = {'id':rid,'sha256':hashlib.sha256(raw).hexdigest()}
            self.records[stage] = record
        with jobs.database() as conn:
            rev, state = jobs.workspace(conn)
            state['products'][0].update(packageContents='1 piece knit vest', packageContentsEvidence={
                'source':'supplier_page','sourceUrl':'https://detail.1688.com/offer/123456789012.html',
                'quantity':1,'raw':'组合形式: 单件','observedAt':'2026-11-20T08:00:00Z'})
            conn.execute('UPDATE workspace SET revision=?,body=? WHERE id=1', (rev+1,json.dumps(state)))
        self.settings = patch.object(provider,'text_provider_name',return_value='fixture').start()
        self.addCleanup(patch.stopall)
        self.request = {'id':job['id'],'requestId':'returned-format-once','receipts':self.refs}

    def test_reuses_same_task_and_receipts_and_applies_once(self):
        before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.glob('*.json')}
        answer = copy.deepcopy(self.fixture.model.return_value)
        answer['copy']['generationEngine'] = {'bulletReview':{'passed':True}}
        with patch.object(provider,'resume_listing_format',return_value=answer) as resume:
            first = recovery.start(2, self.request)
            duplicate = recovery.start(2, self.request)
            self.assertTrue(duplicate['reused'])
            self.assertEqual(first['id'],self.job['id'])
            recovery.execute(2, first['id'])
            final = jobs.status(2, first['id'])
            self.assertEqual(final['status'],'applied')
            self.assertEqual(final['formatRecovery']['phase'],'completed')
            resume.assert_called_once()
            self.assertEqual(resume.call_args.kwargs['initial_raw'],self.records['initial']['response'])
            self.assertEqual(resume.call_args.kwargs['polished_raw'],self.records['polish']['response'])
            self.assertEqual(resume.call_args.args[0]['packageContents'],'1 piece knit vest')
        self.fixture.model.assert_not_called()
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.glob('*.json')})
        self.assertEqual(len(jobs.list_jobs(2)),1)

    def test_foreign_owner_and_altered_hash_are_rejected(self):
        with self.assertRaises(ValueError): recovery.start(3,self.request)
        invalid = copy.deepcopy(self.request);invalid['receipts']['polish']['sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'哈希'): recovery.start(2,invalid)

    def test_extra_returned_stage_prevents_new_review(self):
        extra = {**self.records['polish'],'purpose':'listing_bullet_review'}
        (self.folder/('3'*32+'.json')).write_text(json.dumps(extra),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'后续响应'): recovery.start(2,self.request)

    def test_unrelated_product_change_is_not_amended(self):
        with jobs.database() as conn:
            rev, state = jobs.workspace(conn);state['products'][0]['material']='Changed fabric'
            conn.execute('UPDATE workspace SET body=? WHERE id=1',(json.dumps(state),))
        with self.assertRaisesRegex(ValueError,'原产品'): recovery.start(2,self.request)

    def test_once_started_different_request_cannot_replay(self):
        recovery.start(2,self.request)
        with self.assertRaisesRegex(ValueError,'已经存在'):
            recovery.start(2,{**self.request,'requestId':'another-format-attempt'})

    def test_provider_reaches_fresh_review_without_draft_or_polish_call(self):
        product = {'id':'P','name':'Knit vest','style':'Sleeveless','packageContents':'1 piece vest'}
        content = {'title':"Women's Mock Neck Sweater Vest with an Asymmetric Split Front",'highlights':'Knit vest',
            'bullets':'One\nTwo\nThree\nFour\nFive','description':'Knit Vest\nMaterial: Polyester\n1 Pcs x knit vest',
            'terms':'knit vest','zh':'','warnings':''}
        raw = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content)}}]}
        context = {'facts':{'name':'Knit vest','packageContents':'1 piece vest','keywordPlan':[]},
            'plan':[],'keywordPacking':None,'useSellerSprite':False,'keywordRows':[],'missing':[]}
        with ExitStack() as stack:
            stack.enter_context(patch.object(provider,'generate_listing',new=ORIGINAL_GENERATE))
            stack.enter_context(patch.object(provider,'listing_fact_context',return_value=context))
            initial = stack.enter_context(patch.object(provider,'text_completion'))
            polish = stack.enter_context(patch.object(provider,'polish_listing'))
            review = stack.enter_context(patch.object(provider,'ensure_listing_bullets',side_effect=RuntimeError('fresh-semantic-stage')))
            with self.assertRaisesRegex(RuntimeError,'fresh-semantic-stage'):
                provider.resume_listing_format(product,'US',initial_raw=raw,polished_raw=raw,receipt_id='1'*32)
            initial.assert_not_called();polish.assert_not_called();review.assert_called_once()
            self.assertNotIn('first_semantic_issues',review.call_args.kwargs)


if __name__ == '__main__': unittest.main()
