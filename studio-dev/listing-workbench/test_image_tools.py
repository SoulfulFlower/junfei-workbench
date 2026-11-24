import tempfile,unittest,hashlib,json,io
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import image_tools as tools
class DurableToolIntents(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=tools.DB;tools.DB=Path(self.temp.name)/'tools.db';tools.ACTIVE.clear()
        self.images={'/uploads/a.png':(Image.new('RGB',(20,20)), 'source-sha'),'/uploads/m.png':(Image.new('L',(20,20),255),'mask-sha'),'/uploads/o.png':(Image.new('RGB',(20,20)),'output-sha')}
        self.asset=patch('image_engine.asset',side_effect=lambda u:self.images[u]);self.asset.start()
        self.route=patch('image_tool_vision.identity',return_value={'provider':'Codex Tools','model':'fake'});self.route.start()
        self.threads=patch('image_tools.threading.Thread');self.t=self.threads.start()
    def tearDown(self):
        self.threads.stop();self.route.stop();self.asset.stop();tools.DB=self.old;tools.ACTIVE.clear();self.temp.cleanup()
    def request(self):return {'requestId':'stable-request-id','kind':'colour_check','source':'/uploads/a.png','mask':'/uploads/m.png','renderedImage':'/uploads/o.png','target':'#112233'}
    def test_replay_never_starts_a_second_model_worker(self):
        one=tools.start(self.request(),{'id':'p'});two=tools.start(self.request(),{'id':'p'})
        self.assertEqual(one['id'],two['id']);self.assertEqual(self.t.call_count,1)
        with self.assertRaises(ValueError):tools.start({**self.request(),'target':'#223344'},{'id':'p'})
    def test_quality_receipt_is_bound_to_product_target_and_actual_bytes(self):
        row=tools.start(self.request(),{'id':'p'});row.update(status='completed',result={'passed':False,'blocking':True,'identityPreserved':False});tools.save(row)
        data={**self.request(),'qualityCheckId':row['id']}
        self.assertTrue(tools.verified_colour(data,'p')['blocking'])
        with self.assertRaises(ValueError):tools.verified_colour(data,'other-product')
        with self.assertRaises(ValueError):tools.verified_colour({**data,'target':'#ffffff'},'p')
        with self.assertRaises(ValueError):tools.verified_colour(data,'p',garment_kind='upper')
        self.images['/uploads/o.png']=(Image.new('RGB',(20,20)),'changed-sha')
        with self.assertRaises(ValueError):tools.verified_colour(data,'p')
    def test_interrupted_running_check_is_not_resubmitted(self):
        row=tools.start(self.request(),{'id':'p'});row['status']='running';tools.save(row);tools.ACTIVE.clear()
        result=tools.poll(row['id']);self.assertEqual(result['status'],'interrupted');self.assertEqual(self.t.call_count,1)
    def test_selection_adapter_matches_the_real_module_signature(self):
        import inspect,automatic_garment_selection
        inspect.signature(automatic_garment_selection.prepare).bind(Image.new('RGBA',(20,20)),'upper',
            vision=lambda *a:None,cache_root=Path(self.temp.name),protected=None,vision_metadata={'provider':'Codex Tools','model':'fake'},initial_feedback=None,resume_local_error=True,
            subject={'productName':'actual jacket','target':'actual jacket','role':'source_garment'},max_attempts=3)
    def test_unresolved_paid_intent_blocks_another_request_even_after_version_change(self):
        row=tools.start(self.request(),{'id':'p'});row.update(status='failed',processorVersion='older',modelIntents=[{'status':'unknown'}]);tools.save(row)
        with self.assertRaisesRegex(ValueError,'未核对'):
            tools.start({**self.request(),'requestId':'different-durable-request'},{'id':'p'})
        self.assertEqual(self.t.call_count,1)
    def test_upgrade_preserves_failed_parent_and_derives_one_idempotent_new_task(self):
        request={'requestId':'selection-original-id','kind':'selection','source':'/uploads/a.png'}
        old=tools.start(request,{'id':'p','name':'actual saved garment'});old.update(status='failed',processorVersion='older',failureReceipt={'state':'rejected'},modelIntents=[{'status':'completed','receipt':{'rawModelText':'retained'}}]);tools.save(old)
        one=tools.retry_known_failure(old['id'],{'id':'p','name':'actual saved garment'});two=tools.retry_known_failure(old['id'],{'id':'p','name':'actual saved garment'})
        self.assertEqual(one['id'],two['id']);self.assertEqual(one['parentTaskId'],old['id']);self.assertEqual(tools.get(old['id'])['status'],'failed');self.assertEqual(self.t.call_count,2)
        old['modelIntents']=[{'status':'pending'}];tools.save(old)
        self.assertFalse(tools.upgrade_allowed(old))
        with self.assertRaises(ValueError):tools.retry_known_failure(old['id'],{'id':'p'})
    def test_selection_evidence_cannot_cross_product_kind_or_reference_role(self):
        selected={'kind':'selection','status':'completed','productId':'p','garmentKind':'lower','inputs':{'source':'/uploads/a.png'},'result':{'mask':{'url':'/uploads/m.png'},'receipt':{'verified':True}}}
        data={'selectionTaskId':'s','source':'/uploads/a.png','mask':'/uploads/m.png'}
        with patch.object(tools,'get',return_value=selected):
            self.assertTrue(tools.selected_receipt(data,{'productId':'p','garmentKind':'lower'})['verified'])
            for row in [{'productId':'other','garmentKind':'lower'},{'productId':'p','garmentKind':'upper'}]:
                with self.assertRaises(ValueError):tools.selected_receipt(data,row)
            selected['inputs']['role']='target_colour_reference'
            with self.assertRaises(ValueError):tools.selected_receipt(data,{'productId':'p','garmentKind':'lower'})
            selected['kind']='reference_sample'
            with self.assertRaises(ValueError):tools.selected_receipt(data,{'productId':'p','garmentKind':'lower'})
    def test_known_sample_rejection_can_upgrade_without_becoming_full_selection(self):
        request={'requestId':'sample-original-id','kind':'reference_sample','source':'/uploads/a.png','role':'target_colour_reference'}
        old=tools.start(request,{'id':'p','name':'actual jacket'});old.update(status='failed',processorVersion='older',failureReceipt={'state':'rejected','sampleVerified':False,'eligibleAsSourceSelection':False});tools.save(old)
        new=tools.retry_known_failure(old['id'],{'id':'p','name':'actual jacket'})
        self.assertEqual(new['kind'],'reference_sample');self.assertEqual(new['inputs']['role'],'target_colour_reference');self.assertEqual(new['parentTaskId'],old['id'])
    def test_known_artifact_io_failure_reuses_only_identical_completed_vision(self):
        parent=tools.start(self.request(),{'id':'p','name':'actual jacket'})
        picture=self.images['/uploads/a.png'][0];buffer=io.BytesIO();picture.save(buffer,'PNG')
        instruction='independent check';context={'scope':'current product'}
        receipt={'instructionSha256':hashlib.sha256(instruction.encode()).hexdigest(),'inputImageSha256':[hashlib.sha256(buffer.getvalue()).hexdigest()],'rawModelText':'{"blocking":false}'}
        parent.update(status='failed',processorVersion=tools.processor_version('colour_check').split(':',1)[0]+':old-storage',error="[Errno 2] No such file or directory: '"+str(tools.app_paths.DATA/'automatic-image-quality'/'key'/'quality.json.bad.tmp')+"'",modelCalls=[receipt],modelIntents=[{'status':'completed','contextSha256':hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}]);tools.save(parent)
        self.assertTrue(tools.known_quality_io_failure(parent))
        row=tools.retry_known_failure(parent['id'],{'id':'p','name':'actual jacket'})
        def check(*args,vision,**kwargs):return vision(instruction,context,[picture])
        with patch('automatic_image_quality.check_colour',side_effect=check),patch('image_tool_vision.call')as network:
            result=tools.perform(row)
        network.assert_not_called();self.assertEqual(result['result'],{'blocking':False});self.assertEqual(result['receipt']['reusedFromToolTaskId'],parent['id'])
        def changed(*args,vision,**kwargs):return vision(instruction,context,[Image.new('RGB',(20,20),'red')])
        with patch('automatic_image_quality.check_colour',side_effect=changed),patch('image_tool_vision.call')as network:
            with self.assertRaisesRegex(ValueError,'输入或商品范围变化'):tools.perform(row)
        network.assert_not_called()

    def correction_fixture(self):
        previous=tools.start({'requestId':'original-source-mask','kind':'selection','source':'/uploads/a.png'},{'id':'p','name':'pants'})
        previous.update(status='completed',garmentKind='lower',result={'mask':{'url':'/uploads/m.png'},'receipt':{'verified':True,'accepted':True}});tools.save(previous)
        qc=tools.start({**self.request(),'selectionTaskId':previous['id']},{'id':'p','name':'pants'})
        audit={'passed':False,'blocking':True,'nextAction':'selection','issues':['server-owned cloth miss'],'locations':[{'kind':'miss','point':[.3,.4],'reason':'cloth'}]}
        qc.update(status='completed',garmentKind='lower',result=audit);tools.save(qc)
        row=tools.start({'requestId':'source-mask-correction','kind':'selection','source':'/uploads/a.png','feedback':{'qualityCheckId':qc['id'],'previousSelectionTask':previous['id'],'issues':['fake client issue']}},{'id':'p','name':'pants'})
        row['garmentKind']='lower';tools.save(row)
        return previous,qc,row

    def test_correction_uses_server_owned_qc_instead_of_client_coordinates(self):
        previous,qc,row=self.correction_fixture()
        feedback,mask,audit=tools.correction_evidence(row['inputs'],row)
        self.assertEqual(feedback['issues'],['server-owned cloth miss'])
        self.assertEqual(feedback['locations'],qc['result']['locations'])
        self.assertEqual(mask.mode,'L');self.assertEqual(audit,qc['result'])
        self.assertEqual(row['correctionEvidence']['previousSelectionTask'],previous['id'])

    def test_correction_rejects_cross_product_wrong_mask_and_changed_bytes_before_vision(self):
        previous,qc,row=self.correction_fixture()
        for field,value in [('productId','another'),('garmentKind','upper'),('status','running')]:
            altered={**qc,field:value}
            with patch.object(tools,'get',side_effect=lambda identity: altered if identity==qc['id'] else previous):
                with self.assertRaises(ValueError):tools.correction_evidence(row['inputs'],row)
        bad={**previous,'result':{'mask':{'url':'/different-mask.png'}}}
        with patch.object(tools,'get',side_effect=lambda identity: qc if identity==qc['id'] else bad):
            with self.assertRaises(ValueError):tools.correction_evidence(row['inputs'],row)
        previous['inputs']['role']='target_colour_reference';tools.save(previous)
        with self.assertRaises(ValueError):tools.correction_evidence(row['inputs'],row)
        previous['inputs']['role']='source_garment';tools.save(previous)
        self.images['/uploads/m.png']=(Image.new('L',(20,20),255),'changed-mask-bytes')
        with self.assertRaisesRegex(ValueError,'文件已变化'):tools.correction_evidence(row['inputs'],row)

    def test_already_passed_qc_cannot_authorize_an_unnecessary_correction(self):
        previous,qc,row=self.correction_fixture();qc['result'].update(passed=True,blocking=False,nextAction='none');tools.save(qc)
        with self.assertRaisesRegex(ValueError,'没有明确要求'):tools.correction_evidence(row['inputs'],row)

    def test_grounded_local_route_does_not_reset_the_global_selection(self):
        previous,qc,row=self.correction_fixture()
        result_mask=Image.new('L',(20,20),255);receipt={'accepted':True,'verified':True,'localGrounding':{'auditOnly':True,'maskChangedPixels':0}}
        with patch('automatic_local_selection.eligible',return_value=True),patch('automatic_local_selection.correct',return_value=(result_mask,receipt))as correct,patch('automatic_garment_selection.prepare')as global_plan,patch('image_engine.cache',return_value={'url':'/local-mask.png'}):
            result=tools.perform(row)
        global_plan.assert_not_called();self.assertEqual(result['mask']['url'],'/local-mask.png')
        self.assertEqual(correct.call_args.args[2],previous['result']['receipt'])
        self.assertEqual(correct.call_args.kwargs['qc'],qc['result'])
        self.assertEqual(correct.call_args.kwargs['actual_output'].tobytes(),self.images['/uploads/o.png'][0].tobytes())

    def test_uncertain_local_ownership_stops_without_global_or_network_fallback(self):
        previous,qc,row=self.correction_fixture()
        with patch('automatic_local_selection.eligible',return_value=True),patch('automatic_local_selection.correct',side_effect=ValueError('uncertain local ownership')),patch('automatic_garment_selection.prepare')as global_plan,patch('image_tool_vision.call')as network:
            with self.assertRaisesRegex(ValueError,'uncertain'):tools.perform(row)
        global_plan.assert_not_called();network.assert_not_called()

    def test_out_of_scope_qc_stops_before_paid_global_replanning(self):
        previous,qc,row=self.correction_fixture()
        with patch('automatic_local_selection.eligible',return_value=False),patch('automatic_local_selection.correct')as local,patch('automatic_garment_selection.prepare')as global_plan,patch('image_tool_vision.call')as network:
            with self.assertRaisesRegex(ValueError,'未回退'):tools.perform(row)
        global_plan.assert_not_called();local.assert_not_called();network.assert_not_called()

    def test_historical_failed_report_can_be_researched_but_cannot_approve_delivery(self):
        previous,qc,row=self.correction_fixture();qc['processorVersion']='automatic-colour-quality-v3-details:short-path-v2';tools.save(qc)
        feedback,mask,audit=tools.correction_evidence(row['inputs'],row)
        self.assertEqual(feedback['qualityCheckId'],qc['id']);self.assertFalse(audit['passed'])
        with self.assertRaisesRegex(ValueError,'旧策略'):tools.verified_colour({**qc['inputs'],'qualityCheckId':qc['id']},'p')
