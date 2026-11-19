import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import agent_erp as erp


class ERPBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root/'automation/data/ego-draft-executions').mkdir(parents=True)
        (self.root/'scripts').mkdir()
        self.binding = {'enabled':True,'product_id':'p1','draft_id':'123','erp_sku':'sku','store':'Store','marketplace':'US'}
        self.config = {'browser':{'engine':'ego-lite','script_directory':str(self.root/'scripts'),
                       'pages':{'erp':'p1'},'erp_account_bindings':{'1':[self.binding]}}}
        (self.root/'automation/config.json').write_text(json.dumps(self.config),encoding='utf-8')
        self.task = {'id':'a'*32,'productId':'p1','taskMode':'production','profile':{'store':'Store','marketplace':'US','mode':'draft'},
                     'snapshot':{'product':{'id':'p1'},'listing':{'title':'White pouch','highlights':'A zipper pouch',
                     'bullets':'one\ntwo\nthree\nfour\nfive','description':'A pouch.','terms':'pouch organizer'}},
                     'results':{k:{'ok':True} for k in ('facts','research','listing','images','export','junfeiPreflight')}}
        (self.root/'automation/ego_browser.py').write_text('# fixture only',encoding='utf-8')
        self.patches = [patch.object(erp,'project_root',return_value=self.root),patch.object(erp.app_paths,'DATA',self.root/'account-1')]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_other_account_product_store_market_and_publish_mode_cannot_use_binding(self):
        for user,change in [(2,{}),(1,{'productId':'other'}),(1,{'profile':{'store':'Other','marketplace':'US','mode':'draft'}}),
                            (1,{'profile':{'store':'Store','marketplace':'UK','mode':'draft'}}),
                            (1,{'profile':{'store':'Store','marketplace':'US','mode':'publish'}})]:
            with self.subTest(user=user,change=change), patch.object(erp.subprocess,'run') as run:
                with self.assertRaises(ValueError):erp.observe(user,{**self.task,**change})
                run.assert_not_called()

    def test_request_uses_exact_task_snapshot_and_shared_receipt_digest(self):
        _,req=erp.request_for(1,self.task)
        self.assertEqual(req['patch']['bullets'],['one','two','three','four','five'])
        self.assertEqual(req['patch']['brand'],req['patch']['manufacturer'])
        import hashlib
        identity={k:req[k] for k in ('draftId','store','erpSku','patch')}
        expected=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        self.assertEqual(erp.receipt_path(req).stem,expected)
        self.task['snapshot']['product'].update(brandUseAuthorized=True,brand='Authorized brand')
        with self.assertRaises(ValueError):erp.request_for(1,self.task)

    def fake_observation(self,args,**kwargs):
        self.assertNotIn('shell',kwargs)
        self.assertEqual(args[0], erp.runtime_environment.python_command()[0])
        script=Path(args[args.index('run') + 1]);text=script.read_text(encoding='utf-8')
        subprocess.run(['node','--check',str(script)],check=True,capture_output=True)
        self.assertNotIn('clickSaveDraft',text);self.assertIn('await page.reload()',text)
        # The generated output is account-local; do not run a real browser here.
        import re
        output=json.loads(re.search(r'await fs.writeFile\(("(?:[^"\\]|\\.)*")',text).group(1))
        Path(output).write_text(json.dumps({'draftId':'123','store':'Store','erpSku':'sku',
             'actual':{},'differences':[],'saved':False,'published':False,'observedAt':'now'}),encoding='utf-8')
        return subprocess.CompletedProcess(args,0,b'',b'')

    def test_read_only_observation_is_account_local_and_lock_released(self):
        real_run=subprocess.run
        def fake(args,**kwargs):
            with patch.object(erp.subprocess,'run',real_run):return self.fake_observation(args,**kwargs)
        with patch.object(erp.subprocess,'run',side_effect=fake):result=erp.observe(1,self.task)
        self.assertFalse(result['saved']);self.assertFalse(result['published'])
        self.assertFalse((self.root/'automation/data/ego-workbench.lock').exists())
        self.assertEqual(len(list((self.root/'account-1/agent-results').rglob('*-observation.json'))),1)

    def test_timeout_keeps_lock_and_never_restarts(self):
        with patch.object(erp.subprocess,'run',side_effect=subprocess.TimeoutExpired('ego',65)) as run:
            with self.assertRaisesRegex(ValueError,'结果未知'):erp.observe(1,self.task)
            with self.assertRaisesRegex(ValueError,'未重复启动'):erp.observe(1,self.task)
        self.assertEqual(run.call_count,1)
        self.assertTrue((self.root/'automation/data/ego-workbench.lock').exists())

    def test_unknown_receipt_and_missing_prerequisites_never_resubmit(self):
        _,req=erp.request_for(1,self.task);path=erp.receipt_path(req)
        path.write_text(json.dumps({**req,'status':'save_unknown'}),encoding='utf-8')
        with patch.object(erp.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'必须对账'):erp.sync_copy(1,self.task)
            self.task['results']['images']['ok']=False
            with self.assertRaisesRegex(ValueError,'全部通过'):erp.sync_copy(1,self.task)
        run.assert_not_called()

    def test_verified_shared_receipt_is_reconciled_without_save_and_remains_partial(self):
        _,req=erp.request_for(1,self.task)
        erp.receipt_path(req).write_text(json.dumps({**req,'status':'draft_saved_reopened_verified','published':False}),encoding='utf-8')
        with patch.object(erp,'_observe',return_value={'differences':[]}),patch.object(erp.subprocess,'run') as run:
            result=erp.sync_copy(1,self.task)
        run.assert_not_called();self.assertTrue(result['copySynced']);self.assertFalse(result['ok']);self.assertFalse(result['published'])
        with patch.object(erp,'_observe',return_value={'differences':['title']}),patch.object(erp.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'未覆盖或重发'):erp.sync_copy(1,self.task)
        run.assert_not_called()

    def test_sync_holds_browser_lock_during_reconciliation(self):
        _,req=erp.request_for(1,self.task)
        erp.receipt_path(req).write_text(json.dumps({**req,'status':'draft_saved_reopened_verified','published':False}),encoding='utf-8')
        def inspect(*args):
            with self.assertRaisesRegex(ValueError,'未重复启动'):
                erp.observe(1,self.task)
            return {'differences':[]}
        with patch.object(erp,'_observe',side_effect=inspect):erp.sync_copy(1,self.task)
        self.assertFalse((self.root/'automation/data/ego-workbench.lock').exists())


if __name__=='__main__':unittest.main()
