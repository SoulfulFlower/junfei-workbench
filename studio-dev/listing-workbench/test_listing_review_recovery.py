"""Original-task review recovery: isolated databases and mocked model transport only."""
import copy
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import unittest
from unittest.mock import patch
import provider
import listing_jobs as jobs
import test_listing_jobs as job_fixtures


def issue(number=1,quote='Visible detail',kind='padding'):
    return {'bullet':number,'kind':kind,'quote':quote,'reason':'Exact supported quotation'}


def raw(value):
    return {'id':'fixture-response','choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}


class ReviewContractTests(unittest.TestCase):
    def setUp(self):
        self.bullets='\n'.join('[Topic '+str(n)+'] Visible detail '+str(n)+'. More source information.' for n in range(1,6))
        self.valid=[issue((n%5)+1,'Visible detail '+str((n%5)+1)) for n in range(7)]
        self.invalid=issue(1,'half zip fleece','missing_phrase')
        self.review={'issues':[*self.valid,self.invalid]}

    def test_selected_phrase_never_in_draft_is_invalid_and_seven_real_quotes_are_not_passed(self):
        valid,invalid=provider.bullet_review_findings(self.review,self.bullets,[])
        self.assertEqual(valid,self.valid);self.assertEqual(invalid,[self.invalid])
        with patch('visual_studio.model_json',return_value={'replacements':[{'invalidIndex':0,'issue':None,'reason':'Never in the draft'}]}) as model:
            findings=provider.recheck_invalid_bullet_review(self.review,self.bullets,market='US',facts={},draft_keyword_hits=[])
        self.assertEqual(findings,self.valid);self.assertEqual(model.call_count,1)
        self.assertEqual(model.call_args.kwargs['purpose'],'listing_bullet_review_recovery')
        self.assertEqual(model.call_args.args[1]['alreadyValidIssues'],self.valid)

    def test_malformed_recheck_or_second_bad_quote_stops_after_one_call(self):
        cases=[{}, {'replacements':[]}, {'replacements':[{'invalidIndex':1,'issue':None,'reason':'Wrong index'}]},
               {'replacements':[{'invalidIndex':0,'issue':issue(1,'Absent quotation','padding'),'reason':'Still unmatched'}]},
               {'replacements':[{'invalidIndex':0,'reason':'Missing issue key'}]}]
        for response in cases:
            with self.subTest(response=response),patch('visual_studio.model_json',return_value=response) as model:
                with self.assertRaises(ValueError):provider.recheck_invalid_bullet_review(self.review,self.bullets,market='US',facts={},draft_keyword_hits=[])
                self.assertEqual(model.call_count,1)
        with patch('visual_studio.model_json') as model:
            with self.assertRaisesRegex(ValueError,'没有可恢复'):provider.recheck_invalid_bullet_review({'issues':self.valid},self.bullets,market='US',facts={},draft_keyword_hits=[])
            model.assert_not_called()

    def test_recovered_valid_issues_still_trigger_targeted_repair_and_fresh_checks(self):
        result={'bullets':self.bullets,'translations':{'bullets':'一\n二\n三\n四\n五'},'warnings':''}
        revised='\n'.join('[Topic '+str(n)+'] '+'x'*250 for n in range(1,6))
        with patch.object(provider,'listing_bullet_issues',side_effect=[self.valid,[]]) as checks, \
             patch.object(provider,'trim_bullet_restatements',return_value={}), \
             patch('visual_studio.model_json',return_value={'revisions':[{'bullet':n,'text':revised.splitlines()[n-1],'translation':'修订'} for n in range(1,6)]}) as model:
            count=provider.ensure_listing_bullets(result,market='US',facts={},draft_keyword_hits=[],first_semantic_issues=self.valid)
        self.assertEqual(count,1);self.assertEqual(model.call_count,1);self.assertEqual(checks.call_count,2)
        self.assertEqual(checks.call_args_list[0].kwargs['semantic_issues'],self.valid)
        self.assertNotIn('semantic_issues',checks.call_args_list[1].kwargs)

    def test_known_returned_false_missing_finding_has_counterproof_and_no_model_call(self):
        false=issue(1,'Visible detail 1','missing_phrase');events=[]
        with patch('visual_studio.model_json') as model:
            findings=provider.reconcile_returned_bullet_review(self.review,
                {'replacements':[{'invalidIndex':0,'issue':false,'reason':'Returned but incorrect'}]},
                self.bullets,[],checkpoint=lambda phase,details:events.append(details))
            model.assert_not_called()
        self.assertEqual(findings,self.valid)
        proof=events[0]['deterministicDispositions'][0]
        self.assertEqual(proof['actualDraftPositions'],[]);self.assertEqual(proof['currentPositions'],[1])
        with provider.listing_response_scope({'jobId':'fixture'}),patch('visual_studio.model_json',return_value={'issues':[false,*self.valid]}):
            self.assertEqual(provider.review_listing_bullets(self.bullets,market='US',facts={},draft_keyword_hits=[]),self.valid)
            self.assertEqual(len(provider.LISTING_RESPONSE_CONTEXT.dispositions),1)

    def test_receipt_resume_skips_initial_generation_and_polish_but_runs_original_final_checks(self):
        title="Women's Fleece Pullover with Stand Collar and Two Front Pockets"
        bullets='\n'.join('[Feature '+str(n)+'] '+('Source detail '+str(n)+' ')*20 for n in range(1,6))
        terms='textile garment apparel layering weekend daily casual travel walking streetwear classic wardrobe autumn coldseason outdoor commute leisure clothing overlayer packing workday transitional midweight styling relaxed casualwear'
        value={'title':title,'highlights':'Chest zipper and kangaroo pocket','bullets':bullets,
               'description':'Fleece Pullover\nMaterial: Polyester\n\nProduct: fleece pullover','terms':terms,'zh':'','warnings':'','translations':{}}
        product={'id':'P','name':'Fleece pullover','brand':'Generic','manufacturer':'Generic','material':'Polyester','features':'Stand collar, pockets'}
        sentinel=[issue(1,'Source detail 1')]
        with patch.object(provider,'text_settings',return_value={'api_key':'fixture','model':'offline','provider':'deepseek'}), \
             patch.object(provider,'text_completion',side_effect=AssertionError('No initial resubmit')) as initial, \
             patch.object(provider,'polish_listing',side_effect=AssertionError('No polish resubmit')) as polish, \
             patch.object(provider,'recheck_invalid_bullet_review',return_value=sentinel) as recheck, \
             patch.object(provider,'ensure_listing_bullets',return_value=1) as ensure, \
             patch.object(provider,'research_json',side_effect=AssertionError('No unexpected model')), \
             patch.object(provider.product_insights,'context',return_value={}), \
             patch.object(provider.listing_skills,'current',return_value={}), \
             patch.object(provider,'editorial_guidance',return_value=''):
            result=provider.resume_listing_review(product,'US',initial_raw=raw(value),polished_raw=raw(value),old_review=raw(self.review),receipt_id='a'*32)
        initial.assert_not_called();polish.assert_not_called();recheck.assert_called_once()
        self.assertEqual(ensure.call_args.kwargs['first_semantic_issues'],sentinel)
        self.assertTrue(result['copy']['generationEngine']['bulletReview']['passed'])
        self.assertEqual(result['responseReceipt'],'a'*32)


class RecoveryJobTests(unittest.TestCase):
    setUp=job_fixtures.ListingJobTests.setUp
    state=job_fixtures.ListingJobTests.state
    change=job_fixtures.ListingJobTests.change
    start=job_fixtures.ListingJobTests.start

    def failed(self):
        job=self.start();self.model.side_effect=ValueError('五点语义审校未完成：五点语义审校标记的问题无法与原文核对；初稿回执 '+'a'*32)
        jobs.execute(2,job['id']);job=jobs.status(2,job['id'])
        with jobs.database() as conn:private=jobs.owned(conn,2,job['id'])
        value={'title':'Saved jacket','highlights':'Saved highlights','bullets':'\n'.join('[Topic '+str(n)+'] Visible detail '+str(n)+'.' for n in range(1,6)),
               'description':'Jacket\nClosure: Zip\n\nProduct: jacket','terms':'saved terms','warnings':'','zh':'','translations':{}}
        records={'initial':{'market':'US','response':raw(value)},'polish':{'market':'US','purpose':'listing_unslop','response':raw(value)},
                 'review':{'market':'US','purpose':'listing_bullet_review','response':raw({'issues':[issue(1,'Visible detail 1'),issue(1,'never in draft','missing_phrase')]})}}
        folder=self.root/'listing-responses';folder.mkdir();refs={};self.originalBytes={}
        for key,ident in [('initial','a'*32),('polish','b'*32),('review','c'*32)]:
            record=records[key];record['createdAt']=datetime.fromtimestamp(private['createdAt'],timezone.utc).isoformat()
            b=json.dumps(record).encode();(folder/(ident+'.json')).write_bytes(b);self.originalBytes[ident]=b
            refs[key]={'id':ident,'sha256':hashlib.sha256(b).hexdigest()}
        self.threads.reset_mock();self.model.reset_mock()
        return {'id':job['id'],'requestId':'original-review-recovery-001','receipts':refs}

    def test_once_only_original_task_apply_keeps_receipts_old_error_and_history(self):
        request=self.failed();result={'copy':{'title':'Recovered title'},'responseReceipt':'a'*32}
        def resumed(*args,**kwargs):
            kwargs['checkpoint']('re_review_intent',{'validIssueCount':1})
            provider.save_listing_response(raw({'replacements':[]}), 'US',purpose='listing_bullet_review_recovery')
            kwargs['checkpoint']('re_review_verified',{'validIssueCount':1})
            return copy.deepcopy(result)
        with patch.object(provider.app_paths,'DATA',self.root),patch.object(provider,'resume_listing_review',side_effect=resumed) as model:
            one=jobs.resume_review(2,request);two=jobs.resume_review(2,{**request,'requestId':'another-click-002'})
            self.assertTrue(two['reused']);self.assertEqual(one['id'],two['id']);self.assertEqual(self.threads.call_count,1)
            jobs.execute_review_recovery(2,one['id']);jobs.execute_review_recovery(2,one['id'])
            final=jobs.status(2,one['id']);self.assertEqual(final['status'],'applied');self.assertEqual(model.call_count,1)
            self.assertEqual(final['reviewRecovery']['phase'],'completed');self.assertEqual(len(final['reviewRecovery']['stageResponses']),1)
            self.assertIn('原文核对',final['reviewRecovery']['originalError'])
            self.assertEqual(jobs.resume_review(2,request)['status'],'applied')
        self.model.assert_not_called()
        self.assertEqual(self.state()[1]['copy']['P-US']['title'],'Recovered title')
        self.assertEqual(len(self.state()[1]['products'][0]['copyHistory']),2)
        for ident,content in self.originalBytes.items():self.assertEqual((self.root/'listing-responses'/(ident+'.json')).read_bytes(),content)

    def test_changed_facts_cross_owner_hash_market_and_overlap_stop_before_new_model(self):
        request=self.failed()
        with patch.object(provider,'resume_listing_review') as model:
            with self.assertRaisesRegex(ValueError,'没有此'):jobs.resume_review(3,request)
            bad=copy.deepcopy(request);bad['receipts']['polish']['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'SHA256'):jobs.resume_review(2,bad)
            path=self.root/'listing-responses'/('b'*32+'.json');original=path.read_bytes();record=json.loads(original);record['market']='UK';path.write_text(json.dumps(record))
            bad=copy.deepcopy(request);bad['receipts']['polish']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'站点'):jobs.resume_review(2,bad)
            path.write_bytes(original)
            with jobs.database() as conn:
                original_job=jobs.owned(conn,2,request['id']);other=copy.deepcopy(original_job);other['id']='d'*32
                conn.execute('INSERT INTO listing_generation_jobs VALUES(?,?,?,?,?,?,?,?,?)',(other['id'],2,'OTHER','US','running',other['createdAt'],other['updatedAt'],'overlap-fixture',json.dumps(other)))
            with self.assertRaisesRegex(ValueError,'时间窗'):jobs.resume_review(2,request)
            with jobs.database() as conn:conn.execute('DELETE FROM listing_generation_jobs WHERE id=?',('d'*32,))
            self.change(lambda state:state['products'][0].update(material='Changed material'))
            with self.assertRaisesRegex(ValueError,'已变化'):jobs.resume_review(2,request)
            model.assert_not_called();self.threads.assert_not_called()

    def test_unknown_recovery_or_worker_restart_never_arms_second_review(self):
        request=self.failed()
        with patch.object(provider,'resume_listing_review',side_effect=TimeoutError('returned review status unknown')) as model:
            job=jobs.resume_review(2,request);jobs.execute_review_recovery(2,job['id'])
            final=jobs.status(2,job['id']);self.assertEqual(final['status'],'needs_review')
            self.assertTrue(jobs.resume_review(2,request)['reused']);self.assertEqual(model.call_count,1)
            self.assertEqual(self.start(requestId='never-new-model-002')['id'],job['id'])
            self.assertEqual(self.state()[1]['copy']['P-US'],self.old_copy)
        self.model.assert_not_called()

    def test_restart_before_dispatch_and_late_copy_change_are_read_only(self):
        request=self.failed();job=jobs.resume_review(2,request);jobs.ACTIVE.clear()
        with patch.object(jobs,'RUNTIME','new-runtime'),patch.object(provider,'resume_listing_review') as model:
            read=jobs.status(2,job['id']);self.assertEqual(read['reviewRecovery']['phase'],'interrupted_unknown')
            self.assertTrue(jobs.resume_review(2,request)['reused']);model.assert_not_called()
        self.assertEqual(self.threads.call_count,1)

    def test_late_fact_change_stops_before_recovery_intent_and_keeps_original_copy(self):
        request=self.failed();job=jobs.resume_review(2,request)
        self.change(lambda state:state['copy']['P-US'].update(title='Edited during queue'))
        with patch.object(provider,'resume_listing_review') as model:
            jobs.execute_review_recovery(2,job['id']);model.assert_not_called()
        with jobs.database() as conn:private=jobs.owned(conn,2,job['id'])
        self.assertNotIn('intent',private['reviewRecovery'])
        self.assertEqual(self.state()[1]['copy']['P-US']['title'],'Edited during queue')

    def test_invalid_time_purpose_lineage_or_existing_unknown_result_never_arms(self):
        request=self.failed();path=self.root/'listing-responses'/('b'*32+'.json');original=path.read_bytes()
        variants=[{'purpose':'listing_bullet_repair'}, {'createdAt':'2000-01-01T00:00:00+00:00'},
                  {'listingTask':{'jobId':'OTHER','owner':2,'productId':'P','inputDigest':'x'}}]
        with patch.object(provider,'resume_listing_review') as model:
            for changes in variants:
                with self.subTest(changes=changes):
                    record=json.loads(original);record.update(changes);path.write_text(json.dumps(record))
                    payload=copy.deepcopy(request);payload['receipts']['polish']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                    with self.assertRaises(ValueError):jobs.resume_review(2,payload)
            path.write_bytes(original)
            with jobs.database() as conn:private=jobs.owned(conn,2,request['id'])
            result=jobs.result_path(private);result.parent.mkdir();result.write_text('{incomplete')
            with self.assertRaisesRegex(ValueError,'只允许'):jobs.resume_review(2,request)
            model.assert_not_called();self.threads.assert_not_called()

    def known_returned(self):
        request=self.failed()
        response={'replacements':[{'invalidIndex':0,'issue':issue(1,'Visible detail 1','missing_phrase'),
                                  'reason':'An incorrect but complete returned assertion'}]}
        def first(*args,**kwargs):
            kwargs['checkpoint']('re_review_intent',{})
            provider.save_listing_response(raw(response),'US',purpose='listing_bullet_review_recovery')
            kwargs['checkpoint']('re_review_returned',{'response':response})
            raise ValueError('局部重审仍含无法对应原文的问题；未再次调用模型')
        with patch.object(provider.app_paths,'DATA',self.root),patch.object(provider,'resume_listing_review',side_effect=first):
            job=jobs.resume_review(2,request);jobs.execute_review_recovery(2,job['id'])
        latest=jobs.status(2,job['id']);rec=latest['reviewRecovery'];stage=rec['stageResponses'][0]
        self.threads.reset_mock()
        return {'id':job['id'],'reviewRecoveryId':rec['id'],'requestId':'continue-known-returned-001',
                'returnedReceipt':{'id':stage['receiptId'],'sha256':stage['sha256']}}

    def test_explicit_known_returned_continuation_preserves_original_intent_and_never_rechecks(self):
        request=self.known_returned()
        with jobs.database() as conn:old=copy.deepcopy(jobs.owned(conn,2,request['id'])['reviewRecovery'])
        def follow(*args,**kwargs):
            self.assertIn('returned_review',kwargs)
            kwargs['checkpoint']('targeted_repair_intent',{'bullets':[1]})
            return {'copy':{'title':'Original known review repaired'},'responseReceipt':'a'*32}
        with patch.object(provider,'recheck_invalid_bullet_review',side_effect=AssertionError('No second re-review')) as recheck, \
             patch.object(provider,'resume_listing_review',side_effect=follow) as resumed:
            one=jobs.continue_returned_review(2,request);two=jobs.continue_returned_review(2,request)
            self.assertTrue(two['reused']);self.assertEqual(self.threads.call_count,1)
            jobs.execute_review_recovery(2,one['id']);self.assertEqual(jobs.status(2,one['id'])['status'],'applied')
            self.assertTrue(jobs.continue_returned_review(2,request)['reused'])
            self.assertEqual(resumed.call_count,1);recheck.assert_not_called()
        with jobs.database() as conn:latest=jobs.owned(conn,2,request['id'])['reviewRecovery']
        self.assertEqual(latest['id'],old['id']);self.assertEqual(latest['intent'],old['intent'])
        self.assertEqual(latest['receipts'],old['receipts']);self.assertEqual(latest['stageResponses'],old['stageResponses'])
        self.assertIn('intent',latest['continuation']);self.assertEqual(len(latest['continuation']['diagnostic']['issues']),1)
        self.assertEqual(len(latest['continuation']['diagnostic']['deterministicDispositions']),1)

    def test_known_returned_unknown_after_continuation_is_never_replayed(self):
        request=self.known_returned()
        with patch.object(provider,'resume_listing_review',side_effect=TimeoutError('targeted repair unknown')) as model:
            job=jobs.continue_returned_review(2,request);jobs.execute_review_recovery(2,job['id'])
            self.assertEqual(jobs.status(2,job['id'])['status'],'needs_review')
            self.assertTrue(jobs.continue_returned_review(2,request)['reused'])
            self.assertEqual(model.call_count,1);self.assertEqual(self.state()[1]['copy']['P-US'],self.old_copy)

    def test_wrong_returned_hash_or_later_paid_stage_blocks_before_continuation(self):
        request=self.known_returned();bad=copy.deepcopy(request);bad['returnedReceipt']['sha256']='0'*64
        with self.assertRaises(ValueError):jobs.continue_returned_review(2,bad)
        with jobs.database() as conn:
            job=jobs.owned(conn,2,request['id']);job['reviewRecovery']['history'].append({'phase':'targeted_repair_intent'})
            jobs.save(conn,job)
        with patch.object(provider,'resume_listing_review') as model:
            with self.assertRaisesRegex(ValueError,'提交意图'):jobs.continue_returned_review(2,request)
            model.assert_not_called();self.threads.assert_not_called()


if __name__=='__main__':unittest.main()
