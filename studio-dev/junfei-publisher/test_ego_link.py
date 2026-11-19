import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import ego_link


class EgoLinkTests(unittest.TestCase):
    def test_desktop_connect_reuses_configured_space_and_never_launches_edge(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cli=root/'ego-browser.exe'
            cli.touch()
            config={'engine':'ego-lite','cli':str(cli),'task_space_id':1,'script_directory':str(root/'scripts'),'fallback_to_edge':False}
            with patch.object(ego_link,'browser_config',return_value=config):
                command=ego_link.ego_connection_command()
                self.assertEqual(command[0],str(cli))
                script=next((root/'scripts').glob('*.mjs')).read_text(encoding='utf-8')
                self.assertIn('taskSpace(1)',script)
                self.assertNotIn('takeOverTaskSpace',script)
                with self.assertRaisesRegex(ValueError,'不会打开Edge'):
                    ego_link.require_legacy_browser()

    def test_bad_or_missing_runtime_cannot_fallback(self):
        with patch.object(ego_link,'browser_config',return_value={'engine':'ego-lite','task_space_id':True}):
            with self.assertRaises(ValueError):ego_link.ego_connection_command()

    def test_gui_runtime_stderr_is_accepted_only_for_valid_workspace_response(self):
        with patch.object(ego_link,'browser_config',return_value={'task_space_id':1}):
            valid=json.dumps({'browser':'ego-lite','spaceId':1,'tabs':[]})
            state=ego_link.parse_connection_result(subprocess.CompletedProcess([],0,'',valid))
            self.assertEqual(state['spaceId'],1)
            with self.assertRaises(ValueError):
                ego_link.parse_connection_result(subprocess.CompletedProcess([],0,'','warning only'))
            with self.assertRaises(ValueError):
                ego_link.parse_connection_result(subprocess.CompletedProcess([],0,valid.replace('1','2'),''))

    def test_draft_duplicate_barrier_ignores_request_filename_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cli=root/'ego-browser.exe';cli.touch()
            config={'engine':'ego-lite','cli':str(cli),'task_space_id':1,'script_directory':str(root/'scripts'),'pages':{'erp':'p1'}}
            request={'draftId':'172528873','store':'store','erpSku':'sku','patch':{'description':'verified copy'},'evidence':{'description':'source A'}}
            first=root/'first.json';first.write_text(json.dumps(request),encoding='utf-8')
            with patch.object(ego_link,'browser_config',return_value=config),patch.object(ego_link,'project_root',return_value=root):
                command=ego_link.ego_draft_command(first)
                self.assertEqual(command[0],str(cli))
                # Simulate a previous operation receipt with an unresolved result.
                import hashlib
                identity={key:request.get(key) for key in ('draftId','store','erpSku','patch')}
                digest=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
                receipt=root/'automation/data/ego-draft-executions'/f'{digest}.json'
                receipt.write_text('{"status":"save_unknown"}',encoding='utf-8')
                request['evidence']['description']='source B'
                second=root/'second.json';second.write_text(json.dumps(request),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'不重复保存'):
                    ego_link.ego_draft_command(second)

    def test_recovery_requires_terminal_before_save_and_keeps_same_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cli=root/'ego-browser.exe';cli.touch()
            config={'engine':'ego-lite','cli':str(cli),'task_space_id':1,'script_directory':str(root/'scripts'),'pages':{'erp':'p1'}}
            req={'draftId':'123','store':'store','erpSku':'sku','patch':{'brand':'Generic','manufacturer':'Generic'},'evidence':{'brand':'source','manufacturer':'source'}}
            request=root/'request.json';request.write_text(json.dumps(req),encoding='utf-8')
            reconciliation=root/'reconciliation.json'
            reconciliation.write_text(json.dumps({**{k:req[k] for k in ('draftId','store','erpSku')},'outcome':'confirmed_no_save','source':'Reloaded and compared persisted fields','persisted':{'copy':{'brand':'old','manufacturer':'old'}}}),encoding='utf-8')
            with patch.object(ego_link,'browser_config',return_value=config),patch.object(ego_link,'project_root',return_value=root):
                ego_link.ego_draft_command(request)
                records=root/'automation/data/ego-draft-executions'
                receipt=records/'original.json'
                import hashlib
                identity={key:req.get(key) for key in ('draftId','store','erpSku','patch')}
                receipt=records/(hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()+'.json')
                for status,attempt in [('save_unknown',1),('draft_saved_reopened_verified',1),('started',1),('stopped_before_save',2)]:
                    receipt.write_text(json.dumps({**req,'status':status,'attempt':attempt}),encoding='utf-8')
                    with self.assertRaisesRegex(ValueError,'不可重发'):ego_link.ego_draft_command(request,reconciliation)
                receipt.write_text(json.dumps({**req,'status':'stopped_before_save'}),encoding='utf-8')
                original=receipt.read_bytes()
                command=ego_link.ego_draft_command(request,reconciliation)
                script=max((root/'scripts').glob('*.mjs'),key=lambda p:p.stat().st_mtime_ns)
                text=script.read_text(encoding='utf-8')
                self.assertIn('previousSha256',text);self.assertIn('record.previousAttempts=[previous]',text)
                self.assertIn("fs.open(path+'.reconcile-lock','wx')",text)
                self.assertIn('await inspectDraft',text)
                self.assertEqual(receipt.read_bytes(),original)
                subprocess.run(['node','--check',str(script)],check=True,capture_output=True)

    def test_generic_brand_entry_rejects_arbitrary_and_partial_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'request.json'
            for patch_value in ({'brand':'OTHER','manufacturer':'OTHER'},{'brand':'Generic'}):
                p.write_text(json.dumps({'patch':patch_value}),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'同时设为Generic'):ego_link.ego_draft_command(p)

    def test_image_entry_persists_staging_and_save_identity_across_filename_and_evidence_changes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cli=root/'ego-browser.exe';cli.touch();image=root/'image.png';image.write_bytes(b'test')
            config={'engine':'ego-lite','cli':str(cli),'task_space_id':1,'script_directory':str(root/'scripts'),'pages':{'erp':'p1'}}
            a={'path':str(image),'sha256':'a'*64,'width':1600,'height':1600,'purpose':'reviewed_product_image','reviewed':True,'rightsVerified':True,'evidence':'Original artwork'}
            request={'draftId':'123','store':'Store','erpSku':'SKU','assets':[a]}
            p=root/'request.json';p.write_text(json.dumps(request),encoding='utf-8')
            with patch.object(ego_link,'browser_config',return_value=config),patch.object(ego_link,'project_root',return_value=root):
                command=ego_link.ego_image_command(p)
                self.assertEqual(command[0],str(cli))
                script=max((root/'scripts').glob('*.mjs'),key=lambda p:p.stat().st_mtime_ns)
                subprocess.run(['node','--check',str(script)],check=True,capture_output=True)
                text=script.read_text(encoding='utf-8')
                self.assertIn('taskSpace(1)',text);self.assertNotIn('takeOverTaskSpace',text)
                self.assertIn("fs.open(path,'wx')",text)
                self.assertIn("fs.open(lockPath,'wx')",text)
                self.assertIn('if(completed)await fs.unlink(lockPath)',text)
                identity={k:request[k] for k in ('draftId','store','erpSku')};identity['assetHashes']=['a'*64]
                digest=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                stage=root/'automation/data/ego-image-executions'/f'{digest}-stage.json'
                stage.write_text(json.dumps({**request,'status':'upload_unknown'}),encoding='utf-8')
                a['evidence']='Changed narrative';q=root/'other.json';q.write_text(json.dumps(request),encoding='utf-8')
                for save in (False,True):
                    with self.assertRaisesRegex(ValueError,'不重传'):ego_link.ego_image_command(q,save_library=save)
                request['assets'].append({**a,'sha256':'b'*64})
                q.write_text(json.dumps(request),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'不拆分重传'):ego_link.ego_image_command(q)
                request['assets'].pop();q.write_text(json.dumps(request),encoding='utf-8')
                stage.write_text(json.dumps({**request,'status':'image_staged_not_saved'}),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'已经暂存'):ego_link.ego_image_command(q)
                ego_link.ego_image_command(q,save_library=True)
                script=max((root/'scripts').glob('*.mjs'),key=lambda p:p.stat().st_mtime_ns)
                subprocess.run(['node','--check',str(script)],check=True,capture_output=True)
                save_path=stage.with_name(f'{digest}-save.json')
                save_path.write_text('{"status":"image_save_unknown"}',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'不重复保存'):ego_link.ego_image_command(q,save_library=True)

    def test_image_entry_rejects_calibration_save_and_purpose_upgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cli=root/'ego-browser.exe';cli.touch();image=root/'image.png';image.touch()
            config={'engine':'ego-lite','cli':str(cli),'task_space_id':1,'script_directory':str(root/'scripts'),'pages':{'erp':'p1'}}
            request={'draftId':'123','store':'Store','erpSku':'SKU','assets':[{'path':str(image),'sha256':'a'*64,'purpose':'calibration_only','width':1600,'height':1600}]}
            p=root/'request.json';p.write_text(json.dumps(request),encoding='utf-8')
            with patch.object(ego_link,'browser_config',return_value=config),patch.object(ego_link,'project_root',return_value=root):
                with self.assertRaisesRegex(ValueError,'校准图不能保存'):ego_link.ego_image_command(p,save_library=True)
                ego_link.ego_image_command(p)
                records=root/'automation/data/ego-image-executions'
                # Find the stable identity from the generated script without running a browser.
                import hashlib
                identity={k:request[k] for k in ('draftId','store','erpSku')};identity['assetHashes']=['a'*64]
                digest=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                (records/f'{digest}-stage.json').write_text(json.dumps({**request,'status':'image_staged_not_saved'}),encoding='utf-8')
                request['assets'][0].update(purpose='reviewed_product_image',reviewed=True,rightsVerified=True,evidence='Changed claim')
                p.write_text(json.dumps(request),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'不能转换校准用途'):ego_link.ego_image_command(p,save_library=True)


if __name__=='__main__':unittest.main()
