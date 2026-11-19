"""Listing task recovery tests: temporary SQLite and mocked text models only."""
import copy
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import listing_jobs as jobs


class ListingJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.real_thread=threading.Thread
        self.patch_db=patch.object(jobs,'DB',self.root/'studio.sqlite3')
        self.patch_thread=patch.object(jobs,'THREAD_FACTORY')
        self.patch_settings=patch.object(jobs.provider,'text_settings',return_value={'api_key':'isolated-fixture','model':'mock-text'})
        self.patch_provider=patch.object(jobs.provider,'generate_listing',return_value={
            'copy':{'title':'Generated title','highlights':'Generated highlight','bullets':'One\nTwo\nThree\nFour\nFive',
                'description':'Generated description','terms':'generated terms','translations':{'title':'生成标题'},
                'generationKeywordInput':{'keywords':[{'phrase':'jacket with pockets','placement':'bullets'}]}},
            'model':'mock-text','provider':'fixture-only','responseReceipt':'saved-provider-response','usage':{'total_tokens':42}})
        self.patch_account=patch.object(jobs.app_paths,'WORKER_USER',0)
        self.patch_active=patch.object(jobs,'ACTIVE',set())
        for target in (self.patch_db,self.patch_thread,self.patch_settings,self.patch_provider,self.patch_account,self.patch_active):
            value=target.start();self.addCleanup(target.stop)
            if target is self.patch_thread:self.threads=value
            if target is self.patch_provider:self.model=value
        self.product={'id':'P','name':'Saved jacket','style':'Verified stand collar',
            'status':'制作中','sourceImport':{'market':'US'},'copyHistory':[{'market':'US','date':'old','source':'manual','copy':{'title':'Older'}}],
            'pendingCopy':{'US':{'copy':{'title':'Old pending'}},'UK':{'copy':{'title':'UK pending'}}},
            'listingGeneration':{'US':{'status':'completed','message':'Old generation'}}}
        self.old_copy={'title':'Original title','highlights':'Original highlight','bullets':'Original bullets',
                       'description':'Original description','terms':'original terms','translations':{'title':'原始标题'}}
        self.initial={'products':[copy.deepcopy(self.product)],'copy':{'P-US':copy.deepcopy(self.old_copy)},
                      'reviews':{'P':{'copy':True,'images':True,'note':'Old review'}}}
        with closing(sqlite3.connect(jobs.DB)) as conn,conn:
            conn.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            conn.execute('INSERT INTO workspace VALUES(1,1,?)',(json.dumps(self.initial),))

    def state(self):
        with closing(sqlite3.connect(jobs.DB)) as conn:
            revision,raw=conn.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
        return revision,json.loads(raw)

    def change(self,action):
        revision,state=self.state();action(state)
        with closing(sqlite3.connect(jobs.DB)) as conn,conn:
            conn.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(state)))

    def start(self,**kwargs):
        return jobs.start(2,{'productId':'P','market':'US','requestId':'fixture-request-001',**kwargs})

    def execute(self,job):
        jobs.execute(2,job['id'])
        return jobs.status(2,job['id'])

    def test_double_click_and_lost_start_response_reuse_one_durable_task(self):
        one=self.start();two=self.start(requestId='different-click-002')
        self.assertEqual(one['id'],two['id']);self.assertTrue(two['reused'])
        self.assertEqual(self.threads.call_count,1);self.model.assert_not_called()
        complete=self.execute(one)
        again=self.start()
        self.assertEqual(again['id'],complete['id']);self.assertEqual(again['status'],'applied')
        self.assertEqual(self.threads.call_count,1)

    def test_closed_page_does_not_control_completion_and_reopen_finds_result(self):
        started=threading.Event();release=threading.Event()
        answer=copy.deepcopy(self.model.return_value)
        def blocked(*args,**kwargs):
            started.set();release.wait(3);return answer
        self.model.side_effect=blocked
        with patch.object(jobs,'THREAD_FACTORY',self.real_thread):
            first=self.start()
            self.assertTrue(started.wait(2))
            self.assertEqual(jobs.status(2,first['id'])['status'],'running')
            # No browser callback or save occurs. Only the server worker finishes.
            release.set()
            deadline=time.monotonic()+3
            while first['id'] in jobs.ACTIVE and time.monotonic()<deadline:time.sleep(.01)
        reopened=jobs.list_jobs(2,productId='P',market='US')[0]
        self.assertEqual(reopened['status'],'applied');self.assertTrue(reopened['resultAvailable'])
        self.assertNotIn('result',reopened)
        self.assertEqual(jobs.status(2,first['id'])['result']['copy']['title'],'Generated title')
        self.assertEqual(self.state()[1]['copy']['P-US']['title'],'Generated title')
        self.model.assert_called_once()

    def test_history_and_pending_sites_and_reviews_are_preserved(self):
        job=self.execute(self.start())
        revision,state=self.state();product=state['products'][0]
        self.assertEqual(job['status'],'applied');self.assertEqual(job['workspaceRevision'],revision)
        self.assertEqual(product['copyHistory'][0],self.product['copyHistory'][0])
        self.assertEqual(product['copyHistory'][-1]['copy'],self.old_copy)
        self.assertEqual(product['copyHistory'][-1]['jobId'],job['id'])
        self.assertEqual(product['copyHistory'][-1]['market'],'US')
        self.assertNotIn('US',product['pendingCopy']);self.assertEqual(product['pendingCopy']['UK'],self.product['pendingCopy']['UK'])
        self.assertEqual(product['listingGenerationHistory'][0]['outcome'],self.product['listingGeneration']['US'])
        self.assertEqual(product['listingGeneration']['US']['status'],'completed')
        self.assertFalse(state['reviews']['P']['copy']);self.assertTrue(state['reviews']['P']['images'])
        before=copy.deepcopy(state)
        self.assertTrue(jobs.apply(2,job['id'])['applied'])
        self.assertEqual(self.state()[1],before)

    def test_product_or_copy_or_lock_or_review_change_retains_final_result(self):
        mutations=[lambda s:s['products'][0].update(style='Changed feature'),
                   lambda s:s['copy']['P-US'].update(description='Manual edit'),
                   lambda s:s['copy']['P-US'].update(lockedFields=['title']),
                   lambda s:s['reviews']['P'].update(copy=False)]
        for index,change in enumerate(mutations):
            with self.subTest(index=index):
                # New isolated workspace for each conflict; retained jobs remain historical.
                with closing(sqlite3.connect(jobs.DB)) as conn,conn:
                    conn.execute('UPDATE workspace SET revision=1,body=? WHERE id=1',(json.dumps(self.initial),))
                    if index:conn.execute('DELETE FROM listing_generation_jobs')
                job=self.start(requestId='conflict-'+str(index)+'-request')
                self.change(change)
                before=self.state()[1]
                final=self.execute(job)
                self.assertEqual(final['status'],'ready');self.assertTrue(final['resultAvailable'])
                self.assertEqual(self.state()[1]['copy'],before['copy'])
                self.assertEqual(len(self.state()[1]['products'][0]['copyHistory']),1)
                self.assertEqual(jobs.apply(2,job['id'])['status'],'ready')
                self.assertEqual(self.start(requestId='another-request-'+str(index))['id'],job['id'])

    def test_unrelated_product_save_does_not_block_automatic_replacement(self):
        job=self.start()
        self.change(lambda s:s['products'].append({'id':'OTHER','name':'Other product','style':'Other facts'}))
        self.assertEqual(self.execute(job)['status'],'applied')
        state=self.state()[1]
        self.assertEqual(state['products'][1]['name'],'Other product')

    def test_original_field_locks_and_translation_survive_and_result_matches_saved_copy(self):
        self.change(lambda s:s['copy']['P-US'].update(lockedFields=['title']))
        final=self.execute(self.start())
        saved=self.state()[1]['copy']['P-US']
        self.assertEqual(saved['title'],'Original title');self.assertEqual(saved['translations']['title'],'原始标题')
        self.assertEqual(saved['description'],'Generated description');self.assertEqual(saved['lockedFields'],['title'])
        self.assertEqual(final['result']['copy'],saved)

    def test_restart_with_no_result_is_needs_review_and_cannot_reissue(self):
        job=self.start()
        jobs.ACTIVE.clear()
        with patch.object(jobs,'RUNTIME','new-runtime'):
            reopened=jobs.status(2,job['id'])
            again=self.start(requestId='new-click-after-restart')
        self.assertEqual(reopened['status'],'needs_review');self.assertFalse(reopened['resultAvailable'])
        self.assertEqual(again['id'],job['id']);self.model.assert_not_called()
        self.assertEqual(self.state()[1]['products'][0]['listingGeneration']['US']['status'],'uncertain')

    def test_atomic_final_receipt_recovers_after_response_before_sql_commit(self):
        job=self.start()
        with patch.object(jobs,'apply_result',side_effect=SystemExit('simulated interruption')):
            with self.assertRaises(SystemExit):jobs.execute(2,job['id'])
        self.assertTrue((self.root/'listing-generation-results'/(job['id']+'.json')).is_file())
        with patch.object(jobs,'RUNTIME','restarted-runtime'):
            final=jobs.status(2,job['id'])
        self.assertEqual(final['status'],'applied');self.assertEqual(final['responseReceipt'],'saved-provider-response')
        self.assertEqual(len(self.state()[1]['products'][0]['copyHistory']),2)
        self.assertEqual(jobs.status(2,job['id'])['status'],'applied')
        self.assertEqual(len(self.state()[1]['products'][0]['copyHistory']),2)
        self.model.assert_called_once()

    def test_restart_recovered_receipt_still_respects_concurrent_edit(self):
        job=self.start()
        with patch.object(jobs,'apply_result',side_effect=SystemExit):
            with self.assertRaises(SystemExit):jobs.execute(2,job['id'])
        self.change(lambda s:s['copy']['P-US'].update(description='Keep this manual edit'))
        with patch.object(jobs,'RUNTIME','restarted-runtime'):
            final=jobs.status(2,job['id'])
        self.assertEqual(final['status'],'ready');self.assertEqual(final['result']['copy']['description'],'Generated description')
        self.assertEqual(self.state()[1]['copy']['P-US']['description'],'Keep this manual edit')

    def test_receipt_with_another_identity_is_never_adopted(self):
        job=self.start()
        with jobs.database() as conn:record=jobs.owned(conn,2,job['id'])
        jobs.save_result_receipt(record,self.model.return_value)
        path=jobs.result_path(record);body=json.loads(path.read_text());body['owner']=999;path.write_text(json.dumps(body))
        jobs.ACTIVE.clear()
        with patch.object(jobs,'RUNTIME','restart'):
            final=jobs.status(2,job['id'])
        self.assertEqual(final['status'],'needs_review');self.assertFalse(final['resultAvailable'])
        self.assertEqual(self.state()[1]['copy']['P-US'],self.old_copy)

    def test_provider_error_keeps_task_and_does_not_automatically_retry(self):
        job=self.start();self.model.side_effect=TimeoutError('fixture response unknown')
        final=self.execute(job)
        self.assertEqual(final['status'],'needs_review');self.assertIn('unknown',final['error'])
        self.assertEqual(self.start(requestId='retry-click-request')['id'],job['id'])
        self.model.assert_called_once()

    def test_apply_before_a_result_does_not_change_running_task_state(self):
        job=self.start()
        before=self.state()
        with self.assertRaisesRegex(ValueError,'尚无可恢复'):jobs.apply(2,job['id'])
        self.assertEqual(jobs.status(2,job['id'])['status'],'queued')
        self.assertEqual(self.state(),before)
        self.model.assert_not_called()

    def test_workspace_and_result_are_atomic_if_lock_validation_rejects(self):
        job=self.start()
        with patch.object(jobs.listing_locks,'validate_state',side_effect=ValueError('fixture lock changed')):
            final=self.execute(job)
        self.assertEqual(final['status'],'ready');self.assertTrue(final['resultAvailable'])
        self.assertEqual(self.state()[1]['copy']['P-US'],self.old_copy)
        self.assertEqual(len(self.state()[1]['products'][0]['copyHistory']),1)

    def test_failure_after_workspace_update_rolls_back_replacement_and_history(self):
        job=self.start()
        original=jobs.save
        failed=[]
        def fail_once(conn,current):
            if current['status']=='applied' and not failed:
                failed.append(True)
                raise sqlite3.OperationalError('fixture job save failed after workspace update')
            return original(conn,current)
        with patch.object(jobs,'save',side_effect=fail_once):
            final=self.execute(job)
        self.assertEqual(final['status'],'ready');self.assertTrue(final['resultAvailable'])
        self.assertEqual(self.state()[1]['copy']['P-US'],self.old_copy)
        self.assertEqual(self.state()[1]['products'][0]['copyHistory'],self.product['copyHistory'])
        recovered=jobs.apply(2,job['id'])
        self.assertEqual(recovered['status'],'applied')
        self.assertEqual(self.state()[1]['copy']['P-US']['title'],'Generated title')
        self.assertEqual(len(self.state()[1]['products'][0]['copyHistory']),2)
        jobs.apply(2,job['id'])
        self.assertEqual(len(self.state()[1]['products'][0]['copyHistory']),2)
        self.model.assert_called_once()

    def test_start_acknowledges_its_progress_revision_and_does_not_hide_interruption(self):
        job=self.start(expectedRevision=1)
        self.assertEqual(job['workspaceRevision'],self.state()[0])
        self.assertEqual(job['workspaceRevision'],2)
        jobs.ACTIVE.clear()
        with patch.object(jobs,'RUNTIME','restart'):
            interrupted=jobs.status(2,job['id'])
        self.assertEqual(interrupted['workspaceRevision'],self.state()[0])
        self.assertGreater(interrupted['workspaceRevision'],job['workspaceRevision'])

    def test_expected_revision_invalid_product_or_all_locks_stop_before_model(self):
        with self.assertRaisesRegex(ValueError,'版本'):self.start(expectedRevision=99)
        with self.assertRaisesRegex(ValueError,'没有该产品'):self.start(productId='OTHER')
        self.change(lambda s:s['copy']['P-US'].update(lockedFields=list(jobs.FIELDS)))
        with self.assertRaisesRegex(ValueError,'全部'):self.start()
        self.threads.assert_not_called();self.model.assert_not_called()

    def test_expected_revision_rejects_bool_negative_and_non_integer(self):
        for value in (True,False,-1,'1',1.0,None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,'非负整数'):self.start(expectedRevision=value)
        self.threads.assert_not_called();self.model.assert_not_called()

    def test_legacy_uncertain_marker_requires_review_before_a_new_request(self):
        self.change(lambda s:s['products'][0]['listingGeneration']['US'].update(status='uncertain'))
        with self.assertRaisesRegex(ValueError,'结果未知'):self.start()
        self.threads.assert_not_called();self.model.assert_not_called()

    def test_server_saved_facts_and_research_are_authoritative(self):
        job=self.execute(self.start())
        args,kwargs=self.model.call_args
        self.assertEqual(args[0]['name'],'Saved jacket')
        self.assertEqual(kwargs['evidence_product']['style'],'Verified stand collar')
        with self.assertRaisesRegex(ValueError,'参数'):self.start(product={'name':'Client invented facts'})
        self.assertNotIn('inputSnapshot',job);self.assertNotIn('runOwner',job)

    def test_account_boundaries_apply_to_status_list_and_apply(self):
        job=self.start()
        self.assertEqual(jobs.list_jobs(3),[])
        for action in (jobs.status,jobs.apply):
            with self.assertRaisesRegex(ValueError,'没有此'):action(3,job['id'])
        with patch.object(jobs.app_paths,'WORKER_USER',2):
            with self.assertRaisesRegex(ValueError,'账号'):jobs.list_jobs(3)

    def test_same_request_id_cannot_change_its_product_or_market(self):
        self.start()
        with self.assertRaisesRegex(ValueError,'其他产品或站点'):self.start(market='UK')

    def test_concurrent_start_creates_only_one_worker_and_preserves_order(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda i:self.start(requestId='concurrent-'+str(i)+'-request'),range(4)))
        self.assertEqual(len({r['id'] for r in results}),1);self.assertEqual(self.threads.call_count,1)
        first=results[0];self.execute(first)
        second=self.start(requestId='intentional-new-generation')
        self.assertNotEqual(first['id'],second['id'])
        listed=jobs.list_jobs(2,productId='P',market='US')
        self.assertEqual([j['id'] for j in listed],[second['id'],first['id']])
        self.assertNotIn('result',listed[1]);self.assertEqual(self.threads.call_count,2)

    def test_older_unresolved_job_is_retained_beyond_the_recent_history_limit(self):
        current=self.start()
        with jobs.database() as conn:
            for index in range(105):
                jid=f'{index+1:032x}'
                body={'id':jid,'owner':2,'productId':'P','market':'US','status':'applied',
                    'createdAt':current['createdAt']+index+1,'updatedAt':current['createdAt']+index+1,
                    'stage':'Old finished','message':'Finished'}
                conn.execute('INSERT INTO listing_generation_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                    (jid,2,'P','US','applied',body['createdAt'],body['updatedAt'],'old-'+jid,json.dumps(body)))
        listed=jobs.list_jobs(2)
        self.assertIn(current['id'],{job['id'] for job in listed})
        self.assertEqual(len(listed),101)
        self.assertEqual(listed[-1]['id'],current['id'])
        self.model.assert_not_called()


if __name__=='__main__':unittest.main()
