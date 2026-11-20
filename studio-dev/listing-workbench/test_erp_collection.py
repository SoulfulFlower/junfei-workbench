import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import erp_collection as erp
import hashlib
import subprocess
from contextlib import nullcontext
from types import SimpleNamespace

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.patch=patch.object(erp,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        self.product={'id':'P','sku':'SKU','sourceImport':{'amazon':{'variants':[{'sku':'SKU-Beige-S'}]}}}
        self.listing={'title':'A cardigan','highlights':'Side tie','bullets':'one\ntwo\nthree\nfour\nfive','description':'Verified description','terms':'cardigan'}
        self.workspace={'products':[self.product],'copy':{'P-US':self.listing}}
        self.destination={'id':'store','accountId':2,'store':'Target US','marketplace':'US','enabled':True}

    def test_double_click_returns_original_job_without_restarting_external_work(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread') as thread:
            a=erp.start(2,self.workspace,{'productId':'P','destinationId':'store','expectedListing':self.listing})
            b=erp.start(2,self.workspace,{'productId':'P','destinationId':'store','expectedListing':self.listing})
        self.assertEqual(a['id'],b['id']);self.assertTrue(b['reused']);self.assertEqual(thread.call_count,1)
        self.assertFalse(a['published'])

    def test_account_cannot_read_another_accounts_job(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread'):
            job=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
        with self.assertRaises(ValueError):erp.owned(3,job['id'])
        self.assertEqual(erp.owned(2,job['id'])['accountId'],2)

    def test_uncertain_result_is_not_retried_or_recreated(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread') as thread:
            result=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
            job=erp.owned(2,result['id']);job['status']='needs_reconciliation';job['draftId']='123';erp.persist(job)
            result=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
        self.assertEqual(result['draftId'],'123');self.assertEqual(result['status'],'needs_reconciliation');self.assertEqual(thread.call_count,1)

    def test_missing_target_unsaved_copy_or_client_browser_arguments_stop_before_queue(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread') as thread:
            for data in ({'productId':'P','destinationId':'other'},{'productId':'other','destinationId':'store'},
                         {'productId':'P','destinationId':'store','draftId':'999'},
                         {'productId':'P','destinationId':'store','expectedListing':{'title':'unsaved'}}):
                with self.assertRaises(ValueError):erp.start(2,self.workspace,data)
            thread.assert_not_called()

    def test_public_view_never_exposes_internal_paths_or_account_login_configuration(self):
        result=erp.public({'id':'a','status':'verified','draftId':'123','published':False,
            'imageReceipt':'private','password':'secret','accountId':2,'destination':{'page':'p1'}})
        self.assertNotIn('secret',json.dumps(result));self.assertNotIn('imageReceipt',result);self.assertNotIn('destination',result)

    def test_success_requires_real_collection_list_evidence_and_draft_readback(self):
        snapshot={'sha256':'hash','goodsItems':[{'sku':'a'}]}
        record={'status':'saved_reopened_verified','snapshotSha256':'hash','published':False,
                'draftId':'123','draftUrl':'draft','variantChecks':[{'sku':'a'}]}
        with self.assertRaises(ValueError):erp.verified_result({},record,snapshot)
        record['collection']={'id':'456','status':'list_verified','row':{'sourceMatch':True,'join_platform':[]}}
        job={};erp.verified_result(job,record,snapshot)
        self.assertEqual(job['collectionId'],'456');self.assertFalse(job['nativeJoined'])
        self.assertEqual(job['handoffMode'],'reuse_existing_draft')

    def test_changed_finished_version_cannot_reuse_old_success(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread'):
            result=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
            job=erp.owned(2,result['id']);job['status']='verified';erp.persist(job)
            folder=self.root/job['id'];folder.mkdir();(folder/'receipt.json').write_text('{}')
            (folder/'collection.json').write_text(json.dumps({'sha256':'old','goods':{'title':'Original'}}))
            with patch.object(erp,'finished_snapshot',return_value={'sha256':'new','goods':{'title':'Changed'}}):
                with self.assertRaisesRegex(ValueError,'当前成品与原采集版本不同'):
                    erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})

    def test_orphaned_worker_resumes_same_receipt_and_never_allocates_new_job(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread') as thread:
            first=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
            job=erp.owned(2,first['id']);job.update(status='running',runOwner='old-process',ownerPid=-1);erp.persist(job)
            erp.ACTIVE.discard(job['id'])
            folder=self.root/job['id'];folder.mkdir();(folder/'receipt.json').write_text(json.dumps({'status':'join_unknown','collection':{'id':'456'}}))
            result=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
        self.assertEqual(result['id'],first['id']);self.assertTrue(result['reused']);self.assertEqual(thread.call_count,2)
        self.assertEqual(json.loads((folder/'receipt.json').read_text())['collection']['id'],'456')

    def test_concurrent_clicks_queue_only_one_worker(self):
        from concurrent.futures import ThreadPoolExecutor
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp,'execute') as worker:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:erp.start(2,self.workspace,{'productId':'P','destinationId':'store'}),range(4)))
        self.assertEqual(len({r['id'] for r in results}),1);self.assertEqual(worker.call_count,1)

    def test_native_success_requires_same_collection_draft_and_real_join_response(self):
        snapshot={'sha256':'hash','goodsItems':[{'sku':'a'}],'assets':[{'sha256':'image'}],'destination':{'nativeCollectionId':'456'}}
        record={'status':'saved_reopened_verified','snapshotSha256':'hash','published':False,
            'draftId':'123','draftUrl':'draft','variantChecks':[{'sku':'a'}],
            'collection':{'id':'456','status':'list_verified','row':{'sourceMatch':True,'join_platform':['amazon']}}}
        with self.assertRaisesRegex(ValueError,'原生转入'):erp.verified_result({},record,snapshot)
        record['nativeTransfer']={'status':'native_join_verified','sent':1,'collectionId':'456','draftId':'123','response':{'body':{'code':0}}}
        with self.assertRaisesRegex(ValueError,'成品图片'):erp.verified_result({},record,snapshot)
        record['imageChecks']=[{'sha256':'image','remote':{'sha256':'image','bytes':123}}]
        job={};erp.verified_result(job,record,snapshot)
        self.assertTrue(job['nativeJoined']);self.assertEqual(job['handoffMode'],'native_transfer')
        record['nativeTransfer']['draftId']='124'
        with self.assertRaisesRegex(ValueError,'原生转入'):erp.verified_result({},record,snapshot)

    def preflight_evidence(self,script,*,after_import=False,entry_parent=None):
        script=Path(script).resolve()
        digest=hashlib.sha256(script.read_bytes()).hexdigest()
        key=hashlib.sha256((str(script)+':'+digest).encode()).hexdigest()
        ledger=self.root/'automation/data/ego-executions';ledger.mkdir(parents=True,exist_ok=True)
        entry=(entry_parent or self.root)/('round-'+'a'*32+'.mjs')
        message='专属采集浏览器连接已变化，请重新连接'
        guard='if(!connection)throw Error('+json.dumps(message,ensure_ascii=False)+');'
        imported='await import('+json.dumps(script.as_uri())+');'
        entry.write_text(('const connection=null;\n'+(imported+'\n'+guard if after_import else guard+'\n'+imported)),encoding='utf-8')
        record={'script':str(script),'sha256':digest,'browserBinding':'app','exitCode':1,'entry':str(entry),'status':'execution_unknown'}
        receipt=ledger/(key+'.json');receipt.write_text(json.dumps(record),encoding='utf-8')
        line=3 if after_import else 2
        return ('Error: '+message+'\n    at '+entry.as_uri()+':'+str(line)+':20\n').encode('utf-8'),receipt,record

    def test_preflight_proof_requires_matching_receipt_stack_guard_and_before_import(self):
        script=self.root/'collect.mjs';script.write_text('// business script',encoding='utf-8')
        with patch.object(erp,'PROJECT',self.root):
            output,receipt,record=self.preflight_evidence(script)
            proof=erp.browser_preflight_failure(script,output,'app')
            self.assertEqual(proof['line'],2);self.assertIn('连接已变化',proof['message'])
            caught=('__JUNFEI_EGO_APPLICATION_ERROR__'+json.dumps({'stack':output.decode('utf-8')},ensure_ascii=False)).encode('utf-8')
            self.assertEqual(erp.browser_preflight_failure(script,caught,'app')['line'],2)
            self.assertIsNone(erp.browser_preflight_failure(script,output,'other-binding'))
            self.assertIsNone(erp.browser_preflight_failure(script,b'Error: no stack frame','app'))
            record['sha256']='different';receipt.write_text(json.dumps(record))
            self.assertIsNone(erp.browser_preflight_failure(script,output,'app'))
            output,_,_=self.preflight_evidence(script,after_import=True)
            self.assertIsNone(erp.browser_preflight_failure(script,output,'app'))

    def test_preflight_proof_accepts_recorded_entry_alias_without_losing_guard_checks(self):
        script=self.root/'collect.mjs';script.write_text('// business script',encoding='utf-8')
        alias=self.root/'entry-path';alias.mkdir()
        with patch.object(erp,'PROJECT',self.root):
            output,_,_=self.preflight_evidence(script,entry_parent=alias/'..')
            proof=erp.browser_preflight_failure(script,output,'app')
            self.assertIsNotNone(proof)
            self.assertEqual(proof['line'],2)
            self.assertEqual(Path(proof['entry']),self.root.resolve()/('round-'+'a'*32+'.mjs'))
            self.assertIsNone(erp.browser_preflight_failure(script,output,'other-binding'))
            output,_,_=self.preflight_evidence(script,entry_parent=alias/'..',after_import=True)
            self.assertIsNone(erp.browser_preflight_failure(script,output,'app'))

    def test_bootstrap_failure_keeps_original_job_and_reports_proven_import_boundary(self):
        adapters=self.root/'automation'
        adapters.mkdir(exist_ok=True)
        for script in ('ego_browser.py','ziniao_plugin.py'):
            (adapters/script).touch()
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread'):
            first=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
        job=erp.owned(2,first['id'])
        destination={**self.destination,'browserBinding':'app','page':'p2','storeId':'123','storeName':'Store','seller':'Seller','erpAccount':'Account'}
        snapshot={'sha256':'frozen','goodsItems':[{'sku':'SKU-Beige-S'}],'assets':[],'destination':{}}
        def failed_browser(command,**kwargs):
            output,_,_=self.preflight_evidence(command[5])
            return SimpleNamespace(pid=-1,returncode=1,communicate=lambda **kw:(b'',output))
        with patch.object(erp,'PROJECT',self.root),patch.object(erp,'finished_snapshot',return_value=snapshot), \
             patch.object(erp,'browser_lease',return_value=nullcontext()), \
             patch.object(erp.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'',b'')), \
             patch.object(erp.subprocess,'Popen',side_effect=failed_browser) as browser:
            erp.execute(job,self.product,self.listing,destination)
        saved=erp.owned(2,first['id'])
        self.assertEqual(saved['id'],first['id']);self.assertEqual(saved['status'],'needs_reconciliation')
        self.assertIn('专属采集浏览器连接已变化',saved['error']);self.assertIn('本次执行已在业务脚本导入前停止',saved['error'])
        self.assertFalse((self.root/first['id']/'receipt.json').exists());self.assertNotIn('draftId',saved)
        self.assertEqual(browser.call_count,1)

    def test_transport_error_does_not_reuse_stale_business_receipt_error_or_clear_ids(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread'):
            first=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
        job=erp.owned(2,first['id']);job.update(draftId='123',collectionId='456')
        folder=self.root/first['id'];folder.mkdir()
        receipt=folder/'receipt.json';original=json.dumps({'status':'workflow_prepared','error':'stale category ambiguity','draftId':'123','collection':{'id':'456'}}).encode()
        receipt.write_bytes(original)
        destination={**self.destination,'browserBinding':'app','page':'p2','storeId':'123','storeName':'Store','seller':'Seller','erpAccount':'Account'}
        snapshot={'sha256':'frozen','goodsItems':[],'assets':[],'destination':{}}
        process=SimpleNamespace(pid=-1,returncode=1,communicate=lambda **kw:(b'',b'Failed to connect to ego_cli bootstrap\n'))
        with patch.object(erp,'finished_snapshot',return_value=snapshot),patch.object(erp,'browser_lease',return_value=nullcontext()), \
             patch.object(erp.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'',b'')), \
             patch.object(erp.subprocess,'Popen',return_value=process):
            erp.execute(job,self.product,self.listing,destination)
        saved=erp.owned(2,first['id']);attempt=saved['lastBrowserAttempt']
        self.assertEqual(saved['status'],'needs_reconciliation');self.assertEqual(saved['id'],first['id'])
        self.assertEqual((saved['collectionId'],saved['draftId']),('456','123'))
        self.assertIn('本轮 CLI bootstrap 连接失败',saved['error']);self.assertIn('原业务回执未更新',saved['error'])
        self.assertNotIn('stale category',saved['error']);self.assertNotIn('导入前停止',saved['error'])
        self.assertEqual(receipt.read_bytes(),original)
        self.assertEqual(attempt['receiptBeforeSha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(attempt['receiptBeforeSha256'],attempt['receiptAfterSha256']);self.assertFalse(attempt['receiptUpdated'])

    def test_updated_business_receipt_keeps_this_attempts_real_error(self):
        with patch.object(erp,'destinations',return_value=[self.destination]),patch.object(erp.threading,'Thread'):
            first=erp.start(2,self.workspace,{'productId':'P','destinationId':'store'})
        job=erp.owned(2,first['id']);folder=self.root/first['id'];folder.mkdir()
        receipt=folder/'receipt.json';receipt.write_text(json.dumps({'error':'stale category'}))
        def communicate(**kwargs):
            receipt.write_text(json.dumps({'status':'workflow_prepared','error':'current schema failure','draftId':'123','collection':{'id':'456'}}))
            return b'',b'current business error'
        destination={**self.destination,'browserBinding':'app','page':'p2','storeId':'123','storeName':'Store','seller':'Seller','erpAccount':'Account'}
        with patch.object(erp,'finished_snapshot',return_value={'sha256':'frozen','goodsItems':[],'assets':[],'destination':{}}), \
             patch.object(erp,'browser_lease',return_value=nullcontext()), \
             patch.object(erp.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'',b'')), \
             patch.object(erp.subprocess,'Popen',return_value=SimpleNamespace(pid=-1,returncode=1,communicate=communicate)):
            erp.execute(job,self.product,self.listing,destination)
        saved=erp.owned(2,first['id'])
        self.assertEqual(saved['error'],'current schema failure');self.assertTrue(saved['lastBrowserAttempt']['receiptUpdated'])
        self.assertEqual((saved['collectionId'],saved['draftId']),('456','123'))

if __name__=='__main__':unittest.main()
