import unittest
from unittest.mock import patch
import image_engine as engine
from PIL import Image
class PolishedColourGate(unittest.TestCase):
    def task(self):
        return {'id':'colour-test','productId':'p','productName':'actual jacket','status':'queued','results':[],
            'request':{'mode':'colour','references':['/source.png'],'brief':'change the jacket colour','options':{'mask':'/mask.png','target':'#202030','polish':True,'colourRenderer':'official-glsl','renderedImage':'/gpu.png','shaderReceipt':{},'qualityCheckId':'initial-proof'}}}
    def run_case(self,passed):
        task=self.task();images={'/source.png':Image.new('RGBA',(20,20),'pink'),'/mask.png':Image.new('L',(20,20),255),'/gpu.png':Image.new('RGBA',(20,20),'black'),'/generated.png':Image.new('RGBA',(20,20),'pink')}
        good={'passed':True,'blocking':False,'identityPreserved':True,'issues':[]};bad={'passed':False,'blocking':True,'identityPreserved':False,'issues':['wrong target colour']}
        with patch.object(engine,'get',return_value=task),patch.object(engine,'assert_assets'),patch.object(engine,'save'),patch.object(engine,'asset',side_effect=lambda url:(images[url],'sha')),patch.object(engine,'cache',return_value={'url':'/final.png','sha256':'final-sha'}),patch('official_colour_result.validate',return_value={}),patch('image_tools.colour_review',side_effect=[good if passed else bad,bad])as check,patch.object(engine,'paid_image',return_value={'index':1,'providerJobId':'polish','raw':'/generated.png','image':'/generated.png'})as paid,patch.object(engine,'review')as ordinary:
            engine.process(task['id'])
        return task,check,paid,ordinary
    def test_generated_polish_requires_new_target_colour_check(self):
        task,check,paid,ordinary=self.run_case(True)
        self.assertEqual(check.call_count,2);self.assertEqual(check.call_args.args[3],'/final.png');self.assertNotIn('quality_check_id',check.call_args.kwargs)
        self.assertEqual(task['status'],'needs_revision');self.assertTrue(task['results'][-1]['review']['blocking']);ordinary.assert_not_called()
    def test_unapproved_gpu_candidate_does_not_pay_for_polishing(self):
        task,check,paid,ordinary=self.run_case(False)
        paid.assert_not_called();self.assertEqual(check.call_count,1);self.assertIn('polishSkipped',task);self.assertEqual(task['status'],'needs_revision')
class BoundedImageCorrection(unittest.TestCase):
    def make(self,locked=False):
        result={'index':0,'providerJobId':'original-provider-job','image':'/original.png','raw':'/original.png','review':{'blocking':True,'identityPreserved':False,'issues':['wrong quilting']}}
        return {'request':{'preserveSourcePixels':locked},'results':[result]},result
    def test_correction_keeps_actual_failure_and_identical_source_references(self):
        task,result=self.make();refs=['/truth.png','/template.png']
        def review(task,row,source):row['review']={'blocking':False,'identityPreserved':True}
        with patch.object(engine,'save'),patch.object(engine,'review',side_effect=review),patch.object(engine,'paid_image',return_value={'index':0,'providerJobId':'second','raw':'/second.png','image':'/second.png','aspectValid':True})as paid:
            final=engine.automatic_image_correction(task,result,'original exact prompt',refs,'/truth.png')
        self.assertEqual(paid.call_args.args[2],refs);self.assertIn('original exact prompt',paid.call_args.args[1]);self.assertIn('wrong quilting',paid.call_args.args[1])
        self.assertEqual(task['attempts'][0]['providerJobId'],'original-provider-job');self.assertTrue(task['attempts'][0]['review']['blocking'])
        self.assertIs(task['results'][0],final);self.assertEqual(final['automaticAttempt'],2)
    def test_second_failed_attempt_never_loops_or_claims_success(self):
        task,result=self.make()
        def review(task,row,source):row['review']={'blocking':True,'identityPreserved':False}
        with patch.object(engine,'save'),patch.object(engine,'review',side_effect=review),patch.object(engine,'paid_image',return_value={'index':0,'providerJobId':'second','raw':'/second.png','image':'/second.png'})as paid:
            second=engine.automatic_image_correction(task,result,'prompt',['/truth.png'],'/truth.png')
            engine.automatic_image_correction(task,second,'prompt',['/truth.png'],'/truth.png')
        self.assertEqual(paid.call_count,1);self.assertTrue(second['review']['blocking'])
    def test_original_pixel_mode_and_original_crop_are_not_silently_redrawn(self):
        for locked,method in [(True,None),(False,'original-pixel-crop')]:
            task,result=self.make(locked);result['productionMethod']=method
            with patch.object(engine,'paid_image')as paid:out=engine.automatic_image_correction(task,result,'prompt',['/truth.png'],'/truth.png')
            paid.assert_not_called();self.assertIs(out,result)
