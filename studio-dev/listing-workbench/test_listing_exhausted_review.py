"""Original exhausted review continuation: captured text, temporary DBs and fake transport only."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import listing_jobs as jobs
import provider


FIXTURE = Path(__file__).with_name('test-fixtures') / 'listing-exhausted-original-nine.json'


def raw(value, ident):
    return {'id':ident, 'model':'gpt-6-sol', 'usage':{'total_tokens':1},
            'choices':[{'finish_reason':'stop', 'message':{'content':json.dumps(value, ensure_ascii=False)}}]}


class ExhaustedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.jid = self.fixture['originalJobId'];self.product = copy.deepcopy(self.fixture['product'])
        self.pid = self.product['id'];self.model_settings = {'provider':'codex_tools',
            'model':'gpt-6-sol', 'path':'/chat/completions', 'api_key':'isolated-not-a-credential'}
        self.patches = [patch.object(jobs,'DB',self.root/'studio.sqlite3'),
            patch.object(jobs,'THREAD_FACTORY'), patch.object(jobs,'ACTIVE',set()),
            patch.object(jobs,'RUNTIME','isolated-exhausted-runtime'),
            patch.object(jobs.app_paths,'WORKER_USER',0), patch.object(provider.app_paths,'DATA',self.root),
            patch.object(provider,'text_settings',side_effect=lambda:copy.deepcopy(self.model_settings)),
            patch.object(provider.listing_skills,'current',return_value={'version':1,'rules':{}}),
            patch.object(provider.product_insights,'context',return_value={}),
            patch.object(provider,'text_completion',side_effect=AssertionError('Unexpected model call')),
            patch.object(provider,'polish_listing',side_effect=AssertionError('Never replay polish')),
            patch.object(provider,'research_json',side_effect=AssertionError('No extra model fallback'))]
        values = [p.start() for p in self.patches]
        for p in self.patches:self.addCleanup(p.stop)
        self.threads = values[1];self.model = values[9];self.polish = values[10];self.extra = values[11]
        self.initial = {'products':[copy.deepcopy(self.product), *[
            {'id':'OTHER'+str(i),'name':'Protected '+str(i),'status':'制作中','facts':{'version':i}} for i in range(5)]],
            'copy':{'OTHER'+str(i)+'-US':{'title':'Old '+str(i)} for i in range(5)},
            'reviews':{'OTHER'+str(i):{'copy':True,'images':True} for i in range(5)}}
        base = time.time() - 60
        snapshot = jobs.input_snapshot(self.initial, self.initial['products'][0], 'US')
        self.job = {'id':self.jid,'owner':2,'productId':self.pid,'market':'US','status':'needs_review',
            'stage':'生成结果待核对','message':'Isolated captured exhaustion','createdAt':base-1,
            'updatedAt':base+10,'requestId':'isolated-original-generation','runOwner':jobs.RUNTIME,
            'inputDigest':jobs.digest(snapshot),'inputSnapshot':snapshot,'sourceRevision':118}
        self.records=[];self.refs=[];self.original_bytes={}
        folder=self.root/'listing-responses';folder.mkdir()
        for index, entry in enumerate(self.fixture['responses']):
            record=copy.deepcopy(entry['record'])
            # These are explicitly isolated lineage/times, never production receipts.
            record['listingTask']={'jobId':self.jid,'owner':2,'productId':self.pid,'inputDigest':self.job['inputDigest']}
            record['createdAt']=datetime.fromtimestamp(base+index,timezone.utc).isoformat()
            data=json.dumps(record,ensure_ascii=False).encode();rid=entry['originalReceiptId']
            (folder/(rid+'.json')).write_bytes(data);self.original_bytes[rid]=data
            self.records.append(record);self.refs.append({'id':rid,'sha256':hashlib.sha256(data).hexdigest()})
        issue=provider.response_json(self.records[-1]['response'])['issues'][0]
        self.job['error']='五点未通过检查，已达到自动返修次数，未覆盖现有文案：第 3 条：'+issue['reason']+'；初稿回执 '+self.refs[0]['id']
        self.initial['products'][0]['listingGeneration']={'US':{'status':'uncertain','jobId':self.jid}}
        with jobs.database() as db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1,118,?)',(json.dumps(self.initial,ensure_ascii=False),))
            db.execute('INSERT INTO listing_generation_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                (self.jid,2,self.pid,'US','needs_review',self.job['createdAt'],self.job['updatedAt'],
                 self.job['requestId'],json.dumps(self.job,ensure_ascii=False)))
        self.frozen=provider.reconstruct_exhausted_listing(self.product,'US',self.records)
        self.request={'id':self.jid,'requestId':'isolated-exhausted-once-001','inputDigest':self.job['inputDigest'],
            'receipts':copy.deepcopy(self.refs),'bulletsSha256':self.frozen['bulletsSha256'],'targetBullets':[3]}

    def state(self):
        with jobs.database() as db:return jobs.workspace(db)

    def private(self):
        with jobs.database() as db:return jobs.owned(db,2,self.jid)

    def change(self, action):
        with jobs.database() as db:
            revision,state=jobs.workspace(db);action(state)
            db.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',
                       (revision+1,json.dumps(state,ensure_ascii=False)))

    def repaired(self):
        # Synthetic fake-model output for isolated tests; never adopted as product copy.
        line=self.frozen['result']['bullets'].splitlines()[2]
        line=line.replace('Ribbed cuffs finish the sleeves at the wrists.',
            'Choose a fitted underlayer when matching the sleeve volume to the rest of an outfit.')
        self.assertTrue(250<=len(line)<=500)
        return raw({'revisions':[{'bullet':3,'text':line,'translation':'[袖型] 隔离测试返回的忠实翻译。'}],
                    'warnings':''},'isolated-exhausted-repair-response')

    def answers(self, review=None):
        return [self.repaired(),raw({'issues':[]} if review is None else review,'isolated-exhausted-review-response')]

    def execute(self):
        jobs.continue_exhausted_review(2,self.request)
        jobs.execute_exhausted_review(2,self.jid)
        return jobs.status(2,self.jid)

    def assert_originals_and_others(self):
        state=self.state()[1]
        self.assertEqual(state['products'][1:],self.initial['products'][1:])
        for key,value in self.initial['copy'].items():self.assertEqual(state['copy'][key],value)
        for key,value in self.initial['reviews'].items():self.assertEqual(state['reviews'][key],value)
        for rid,data in self.original_bytes.items():
            self.assertEqual((self.root/'listing-responses'/(rid+'.json')).read_bytes(),data)

    def test_captured_nine_reconstruction_inserts_exact_cut_and_keeps_valid_last_issue(self):
        self.model.assert_not_called();self.polish.assert_not_called();self.extra.assert_not_called()
        self.assertEqual(self.frozen['bulletSha256s'],self.fixture['expectedFinalBulletSha256s'])
        self.assertEqual([len(x) for x in self.frozen['result']['bullets'].splitlines()],self.fixture['expectedBulletLengths'])
        self.assertEqual(self.frozen['iterations'][-1]['exactCutsInserted'],[4])
        self.assertEqual(self.frozen['lastIssues'][0]['bullet'],3)
        self.assertIn(self.frozen['lastIssues'][0]['quote'],self.frozen['result']['bullets'].splitlines()[2])
        self.assertEqual(len(self.frozen['result']['translations']['bullets'].splitlines()),5)

    def test_explicit_target_vector_rejects_ambiguous_or_non_bullet_values(self):
        for targets in (None, [], [True], [0], [6], [3,2], [2,2,3], '2,3,5'):
            with self.assertRaises(ValueError):provider.exhausted_targets(targets)
        self.assertEqual(provider.exhausted_targets([2,3,5]),[2,3,5])
        self.model.assert_not_called()

    def multi_scope(self):
        # Synthetic frozen reconstruction for transport/state-machine tests.
        # Strict nine-response reconstruction is tested independently above.
        frozen=copy.deepcopy(self.frozen);frozen['targetBullets']=[2,3,5]
        lines=frozen['result']['bullets'].splitlines();issue=frozen['lastIssues'][0]
        frozen['lastIssues']=[{**issue,'bullet':2,'quote':lines[1],'reason':'Isolated heading2 needs editing'},
                             issue,
                             {**issue,'bullet':5,'quote':lines[4],'reason':'Isolated heading5 needs editing'}]
        frozen['repairInstruction']='Repair only explicitly frozen bullets2,3,5; all other fields immutable.'
        self.job['error']='五点未通过检查，已达到自动返修次数，未覆盖现有文案：'+ ';'.join(
            finding['reason'] for finding in frozen['lastIssues'])+'；初稿回执 '+self.refs[0]['id']
        with jobs.database() as db:jobs.save(db,self.job)
        self.request['targetBullets']=[2,3,5]
        values=provider.response_json(self.repaired());revisions=values['revisions']
        for number in (2,5):
            line=lines[number-1];tail=line.split(']',1)[1]
            heading='[Updated Buttons]' if number == 2 else '[Updated Styling]'
            revisions.append({'bullet':number,'text':heading+tail,
                              'translation':'[主题修订] 隔离测试翻译。'})
        values['revisions']=sorted(revisions,key=lambda row:row['bullet'])
        return frozen,values

    def test_multiple_targets_preserve_every_untargeted_field_and_translation(self):
        frozen,values=self.multi_scope();result=copy.deepcopy(frozen['result'])
        result['bullets'],zh=provider.merge_bullet_revisions(result['bullets'],
            result['translations']['bullets'],[2,3,5],values['revisions'],require_translation=True)
        result['translations']['bullets']=zh
        provider._assert_exhausted_fields_fixed(result,frozen)
        for key in ('title','highlights','description','terms'):
            altered=copy.deepcopy(result);altered[key]+=' changed'
            with self.assertRaises(ValueError):provider._assert_exhausted_fields_fixed(altered,frozen)
        for index in (0,3):
            altered=copy.deepcopy(result);lines=altered['bullets'].splitlines();lines[index]+=' changed'
            altered['bullets']='\n'.join(lines)
            with self.assertRaises(ValueError):provider._assert_exhausted_fields_fixed(altered,frozen)

    def test_multiple_targets_share_one_repair_one_review_and_one_original_job(self):
        frozen,answer=self.multi_scope()
        self.model.side_effect=[raw(answer,'isolated-multi-repair'),raw({'issues':[]},'isolated-multi-review')]
        with patch.object(provider,'reconstruct_exhausted_listing',return_value=frozen):final=self.execute()
        self.assertEqual(final['status'],'applied');self.assertEqual(self.model.call_count,2)
        saved=self.state()[1]['copy'][self.pid+'-US'];old=frozen['result']
        for index in (0,3):self.assertEqual(saved['bullets'].splitlines()[index],old['bullets'].splitlines()[index])
        for index in (1,2,4):self.assertNotEqual(saved['bullets'].splitlines()[index],old['bullets'].splitlines()[index])
        scope=self.private()['exhaustedContinuation']
        self.assertEqual(scope['limits'],{'targetBullets':[2,3,5],'repairCalls':1,'freshReviewCalls':1,'initialCalls':0,'polishCalls':0})
        self.assertEqual(json.loads(self.model.call_args_list[0].args[0]['messages'][1]['content'])['rewrite_bullets'],[2,3,5])
        self.assertEqual(json.loads(self.model.call_args_list[1].args[0]['messages'][1]['content'])['review_bullets'],[1,2,3,4,5])
        self.assertTrue(jobs.continue_exhausted_review(2,self.request)['reused'])
        self.assertEqual(self.model.call_count,2);self.assert_originals_and_others()

    def test_multiple_targets_noop_for_one_target_stops_before_fresh_review(self):
        frozen,answer=self.multi_scope();answer['revisions'][0]['text']=frozen['result']['bullets'].splitlines()[1]
        self.model.side_effect=[raw(answer,'isolated-multi-noop')]
        with patch.object(provider,'reconstruct_exhausted_listing',return_value=frozen):final=self.execute()
        self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,1)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_multiple_targets_cannot_add_an_unrequested_bullet(self):
        frozen,answer=self.multi_scope();answer['revisions'].append({'bullet':4,'text':'Forbidden4','translation':'禁止'})
        self.model.side_effect=[raw(answer,'isolated-multi-extra')]
        with patch.object(provider,'reconstruct_exhausted_listing',return_value=frozen):final=self.execute()
        self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,1)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_multiple_targets_full_review_can_reject_an_untargeted_bullet_without_loop(self):
        frozen,answer=self.multi_scope();finding={**frozen['lastIssues'][0],'bullet':1,
            'quote':frozen['result']['bullets'].splitlines()[0],'reason':'Isolated fresh full-review issue'}
        self.model.side_effect=[raw(answer,'isolated-multi-repair'),raw({'issues':[finding]},'isolated-multi-failed-review')]
        with patch.object(provider,'reconstruct_exhausted_listing',return_value=frozen):final=self.execute()
        self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,2)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_keyword_guard_allows_new_target_hit_while_preserving_original_positions(self):
        plan=[{'phrase':'collared cardigan','placement':'bullets'}]
        before=['[Collar] A collared cardigan.','[Buttons] Five buttons.','[Sleeves] Long sleeves.',
                '[Colors] Solid colors.','[Sizes] Two sizes.']
        after=list(before);after[2]='[Sleeves] Choose a collared cardigan for this outfit.'
        self.assertEqual(provider.draft_bullet_keyword_hits('\n'.join(before),plan)[0]['bullets'],[1])
        self.assertEqual(provider.draft_bullet_keyword_hits('\n'.join(after),plan)[0]['bullets'],[1,3])
        provider._assert_exhausted_keyword_positions('\n'.join(before),'\n'.join(after),plan)

    def test_keyword_guard_rejects_losing_an_original_position_even_if_phrase_survives_elsewhere(self):
        plan=[{'phrase':'collared cardigan','placement':'bullets'}]
        before=['[Collar] A collared cardigan.','[Buttons] Five buttons.',
                '[Sleeves] Choose a collared cardigan.','[Colors] Solid colors.','[Sizes] Two sizes.']
        after=list(before);after[2]='[Sleeves] Long sleeves.'
        with self.assertRaisesRegex(ValueError,'关键词原位置'):
            provider._assert_exhausted_keyword_positions('\n'.join(before),'\n'.join(after),plan)

    def test_success_is_one_original_job_two_calls_and_atomic_apply_with_fixed_four_bullets(self):
        self.model.side_effect=self.answers()
        one=jobs.continue_exhausted_review(2,self.request)
        two=jobs.continue_exhausted_review(2,{**self.request,'requestId':'another-click-cannot-rearm'})
        self.assertTrue(two['reused']);self.assertEqual(one['id'],self.jid);self.assertEqual(self.threads.call_count,1)
        jobs.execute_exhausted_review(2,self.jid);jobs.execute_exhausted_review(2,self.jid)
        final=jobs.status(2,self.jid);self.assertEqual(final['status'],'applied');self.assertEqual(self.model.call_count,2)
        self.polish.assert_not_called();self.extra.assert_not_called()
        saved=self.state()[1]['copy'][self.pid+'-US'];old=self.frozen['result']
        for key in ('title','highlights','description','terms'):self.assertEqual(saved[key],old[key])
        for index in (0,1,3,4):self.assertEqual(saved['bullets'].splitlines()[index],old['bullets'].splitlines()[index])
        self.assertEqual(saved['generationEngine']['bulletReview'],{'passed':True,'repairCount':4})
        scope=self.private()['exhaustedContinuation'];self.assertEqual(scope['phase'],'completed')
        self.assertEqual([row['operation'] for row in scope['stageResponses']],['repair','review'])
        self.assertEqual(len(scope['intents']),2);self.assertEqual(scope['originalError'],self.job['error'])
        for row in scope['stageResponses']:
            record=json.loads((self.root/'listing-responses'/(row['receiptId']+'.json')).read_text())
            self.assertEqual(record['listingTask']['exhaustedContinuationId'],scope['id'])
            self.assertEqual(record['listingTask']['inputDigest'],self.job['inputDigest'])
        first_body=self.model.call_args_list[0].args[0]
        self.assertEqual(json.loads(first_body['messages'][1]['content'])['rewrite_bullets'],[3])
        second_body=self.model.call_args_list[1].args[0]
        self.assertEqual(json.loads(second_body['messages'][1]['content'])['review_bullets'],[1,2,3,4,5])
        self.assert_originals_and_others()

    def test_existing_invalid_and_returned_review_contracts_are_not_loosened(self):
        with self.assertRaisesRegex(ValueError,'不是已返回的审校引用错误'):
            jobs.resume_review(2,{'id':self.jid,'requestId':'wrong-old-recovery-path',
                'receipts':dict(zip(('initial','polish','review'),self.refs[:3]))})
        with self.assertRaisesRegex(ValueError,'恢复意图不属于'):
            jobs.continue_returned_review(2,{'id':self.jid,'reviewRecoveryId':'a'*32,
                'requestId':'wrong-returned-path','returnedReceipt':self.refs[-1]})
        self.model.assert_not_called();self.threads.assert_not_called()

    def test_hash_order_owner_input_and_explicit_target_are_required_before_dispatch(self):
        mutations=[lambda q:q.update(targetBullets=[2,3]),lambda q:q.update(inputDigest='0'*64),
            lambda q:q.update(bulletsSha256='0'*64),lambda q:q['receipts'][3].update(sha256='0'*64),
            lambda q:q['receipts'].reverse(),lambda q:q['receipts'].pop()]
        for mutation in mutations:
            request=copy.deepcopy(self.request);mutation(request)
            with self.assertRaises(ValueError):jobs.continue_exhausted_review(2,request)
        with self.assertRaisesRegex(ValueError,'没有此'):jobs.continue_exhausted_review(3,self.request)
        self.model.assert_not_called();self.threads.assert_not_called()

    def test_foreign_lineage_wrong_time_or_additional_returned_stage_blocks(self):
        path=self.root/'listing-responses'/(self.refs[-1]['id']+'.json');old=path.read_bytes()
        for mutation in (lambda r:r['listingTask'].update(owner=3),
                         lambda r:r.update(createdAt=datetime.now(timezone.utc).isoformat())):
            record=json.loads(old);mutation(record);data=json.dumps(record).encode();path.write_bytes(data)
            request=copy.deepcopy(self.request);request['receipts'][-1]['sha256']=hashlib.sha256(data).hexdigest()
            with self.assertRaises(ValueError):jobs.continue_exhausted_review(2,request)
            path.write_bytes(old)
        extra=copy.deepcopy(self.records[-1]);(self.root/'listing-responses'/('f'*32+'.json')).write_text(json.dumps(extra))
        with self.assertRaisesRegex(ValueError,'后续模型回执'):jobs.continue_exhausted_review(2,self.request)
        self.model.assert_not_called();self.threads.assert_not_called()

    def test_changed_facts_or_locks_block_before_arming(self):
        self.change(lambda state:state['products'][0].update(material='Changed material'))
        with self.assertRaisesRegex(ValueError,'已变化'):jobs.continue_exhausted_review(2,self.request)
        self.model.assert_not_called();self.threads.assert_not_called()

    def test_model_routing_change_before_start_or_credential_change_before_dispatch_is_frozen(self):
        self.model_settings['model']='different-model'
        with self.assertRaisesRegex(ValueError,'当前模型与原'):jobs.continue_exhausted_review(2,self.request)
        self.model_settings['model']='gpt-6-sol'
        jobs.continue_exhausted_review(2,self.request)
        self.model_settings['api_key']='different-isolated-credential'
        jobs.execute_exhausted_review(2,self.jid)
        self.assertEqual(jobs.status(2,self.jid)['status'],'needs_review');self.model.assert_not_called()

    def test_queued_source_change_and_restart_never_submit(self):
        jobs.continue_exhausted_review(2,self.request)
        self.change(lambda state:state['copy'].update({self.pid+'-US':{'lockedFields':['title']}}))
        jobs.execute_exhausted_review(2,self.jid)
        self.assertEqual(jobs.status(2,self.jid)['status'],'needs_review');self.model.assert_not_called()
        self.assertTrue(jobs.continue_exhausted_review(2,self.request)['reused'])

    def test_restart_before_dispatch_marks_unknown_and_does_not_rearm(self):
        jobs.continue_exhausted_review(2,self.request);jobs.ACTIVE.clear()
        with patch.object(jobs,'RUNTIME','different-process-runtime'):
            final=jobs.status(2,self.jid)
            self.assertEqual(final['exhaustedContinuation']['phase'],'interrupted_unknown')
            self.assertTrue(jobs.continue_exhausted_review(2,self.request)['reused'])
        self.model.assert_not_called();self.assertEqual(self.threads.call_count,1)

    def test_timeout_on_first_or_second_call_retains_exact_intent_without_replay(self):
        self.model.side_effect=TimeoutError('Isolated uncertain repair response')
        final=self.execute();scope=self.private()['exhaustedContinuation']
        self.assertEqual(final['status'],'needs_review');self.assertEqual(scope['pendingOperations'],['repair'])
        self.assertEqual(scope['phase'],'needs_reconciliation');self.assertEqual(self.model.call_count,1)
        self.assertTrue(jobs.continue_exhausted_review(2,{**self.request,'requestId':'different-does-not-retry'})['reused'])
        jobs.execute_exhausted_review(2,self.jid);self.assertEqual(self.model.call_count,1)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy']);self.assert_originals_and_others()

    def test_review_timeout_does_not_repeat_successful_repair_or_unknown_review(self):
        self.model.side_effect=[self.repaired(),TimeoutError('Isolated uncertain review response')]
        final=self.execute();scope=self.private()['exhaustedContinuation']
        self.assertEqual(final['status'],'needs_review');self.assertEqual(scope['pendingOperations'],['review'])
        self.assertEqual(len(scope['stageResponses']),1);self.assertEqual(self.model.call_count,2)
        self.assertTrue(jobs.continue_exhausted_review(2,self.request)['reused'])
        jobs.execute_exhausted_review(2,self.jid);self.assertEqual(self.model.call_count,2)

    def test_malformed_repair_cannot_change_another_bullet_or_advance_to_paid_review(self):
        answer=self.repaired();value=provider.response_json(answer)
        value['revisions'].append({'bullet':4,'text':'Forbidden other bullet','translation':'不得修改'})
        self.model.side_effect=[raw(value,'isolated-invalid-repair')]
        final=self.execute();self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,1)
        self.assertEqual(len(self.private()['exhaustedContinuation']['stageResponses']),1)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_a_returned_noop_cannot_erase_the_known_valid_issue_with_a_new_review(self):
        self.model.side_effect=[raw({'revisions':[{'bullet':3,
            'text':self.frozen['result']['bullets'].splitlines()[2],'translation':'隔离测试翻译'}],
            'warnings':''},'isolated-noop-repair')]
        final=self.execute();self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,1)
        self.assertIn('未移除',final['error']);self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_wrong_returned_model_identity_is_saved_but_never_advances_to_fresh_review(self):
        answer=self.repaired();answer['model']='unexpected-model'
        self.model.side_effect=[answer]
        final=self.execute();self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,1)
        self.assertEqual(len(self.private()['exhaustedContinuation']['stageResponses']),1)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_fresh_review_valid_issue_stops_at_two_calls_without_loop(self):
        line=provider.response_json(self.repaired())['revisions'][0]['text']
        review={'issues':[{'bullet':3,'kind':'padding','quote':line,'reason':'Still a valid cited issue'}]}
        self.model.side_effect=self.answers(review)
        final=self.execute();self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,2)
        self.assertEqual(self.private()['exhaustedContinuation']['pendingOperations'],[])
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])
        self.assertTrue(jobs.continue_exhausted_review(2,self.request)['reused'])

    def test_fresh_review_invalid_quote_is_not_silently_discarded(self):
        self.model.side_effect=self.answers({'issues':[{'bullet':3,'kind':'padding','quote':'Absent quote',
                                                       'reason':'An invalid quote must stop'}]})
        final=self.execute();self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,2)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_model_identity_change_or_source_change_during_repair_stops_before_review(self):
        def returned(*args,**kwargs):
            self.change(lambda state:state['products'][0].update(features='Changed during call'))
            return self.repaired()
        self.model.side_effect=returned
        final=self.execute();self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,1)
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy'])

    def test_result_receipt_keeps_completed_copy_when_last_moment_input_conflict_prevents_apply(self):
        self.model.side_effect=self.answers();original_save=jobs.save_result_receipt
        def saved(job,result):
            original_save(job,result)
            self.change(lambda state:state['products'][0].update(features='Changed after all checks'))
        with patch.object(jobs,'save_result_receipt',side_effect=saved):final=self.execute()
        self.assertEqual(final['status'],'ready');self.assertTrue(final['resultAvailable'])
        self.assertNotIn(self.pid+'-US',self.state()[1]['copy']);self.assertEqual(self.model.call_count,2)
        self.assertTrue(jobs.continue_exhausted_review(2,self.request)['reused']);self.assert_originals_and_others()

    def recovered_before_worker_returns(self, *, fail_after_recovery):
        self.model.side_effect=self.answers();original_save=jobs.save_result_receipt
        def saved(job,result):
            original_save(job,result)
            # A second runtime sees the durable result before the original
            # executor regains its DB transaction, and applies it first.
            with patch.object(jobs,'RUNTIME','isolated-second-runtime'):
                recovered=jobs.status(2,self.jid)
            self.assertEqual(recovered['status'],'applied')
            if fail_after_recovery:raise OSError('Late bookkeeping failure after another runtime applied')
        with patch.object(jobs,'save_result_receipt',side_effect=saved):final=self.execute()
        self.assertEqual(final['status'],'applied');self.assertEqual(self.model.call_count,2)
        self.assertEqual(self.private()['exhaustedContinuation']['phase'],'completed')
        self.assertEqual(self.state()[1]['products'][0]['listingGeneration']['US']['status'],'completed')
        self.assertIn(self.pid+'-US',self.state()[1]['copy']);self.assert_originals_and_others()

    def test_another_runtime_result_recovery_cannot_be_demoted_by_successful_old_executor(self):
        self.recovered_before_worker_returns(fail_after_recovery=False)

    def test_another_runtime_result_recovery_cannot_be_demoted_by_old_executor_exception(self):
        self.recovered_before_worker_returns(fail_after_recovery=True)

    def test_receipt_write_failure_preserves_unknown_intent_after_one_paid_attempt(self):
        self.model.side_effect=[self.repaired()]
        with patch.object(provider,'save_listing_response',side_effect=OSError('Isolated receipt disk failure')):
            final=self.execute()
        self.assertEqual(final['status'],'needs_review');self.assertEqual(self.model.call_count,1)
        self.assertEqual(self.private()['exhaustedContinuation']['pendingOperations'],['repair'])
        self.assertTrue(jobs.continue_exhausted_review(2,self.request)['reused'])


if __name__=='__main__':unittest.main()
