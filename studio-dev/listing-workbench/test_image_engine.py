import os,sys,tempfile,unittest,json,uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image

ROOT=Path(__file__).parent
SOURCE=Path(json.loads((ROOT/'source-baseline.json').read_text(encoding='utf-8'))['source']) if (ROOT/'source-baseline.json').exists() else ROOT
_temp=tempfile.TemporaryDirectory()
os.environ['JUNFEI_ACCOUNT_DATA']=_temp.name
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(ROOT/'staged'))
import colour_transfer as colour
import image_engine as engine
import image_engine_prompts as prompts
import ivyea_render_core as core

class ColourTests(unittest.TestCase):
    def setUp(self):
        # Real texture gradients + a protected bright hardware strip and alpha.
        y,x=np.mgrid[:80,:80];l=25+x*1.7+8*np.sin(y*.8)
        rgb=np.stack([l,l*.85,l*.65,np.full_like(l,210)],axis=-1).clip(0,255).astype('uint8')
        self.source=Image.fromarray(rgb,'RGBA');m=np.zeros((80,80),np.uint8);m[8:72,8:72]=255;m[:,8]=128
        self.mask=Image.fromarray(m);p=np.zeros_like(m);p[20:35,20:35]=255;self.protect=Image.fromarray(p)
    def test_branch_texture_protection_and_alpha(self):
        for target,branch in [([30,90,190],'chromatic'),([235,235,235],'neutral'),([10,10,10],'neutral')]:
            out,stats=colour.transfer(self.source,self.mask,target,protected=self.protect)
            a=np.asarray(out);original=np.asarray(self.source)
            excluded=(np.asarray(self.mask)==0)|(np.asarray(self.protect)>0)
            np.testing.assert_array_equal(a[excluded],original[excluded]);np.testing.assert_array_equal(a[:,:,3],original[:,:,3])
            self.assertEqual(stats['branch'],branch);self.assertEqual(stats['outsideChangedPixels'],0)
            self.assertGreater(float(a[40:60,30:60,:3].std()),2)
    def test_reference_requires_selection(self):
        with self.assertRaises(ValueError):colour.transfer(self.source,self.mask,[20,30,40],reference=self.source)
    def test_invalid_mask_does_not_colour_whole_image(self):
        with self.assertRaises(ValueError):colour.transfer(self.source,Image.new('L',(80,80)),[40,70,200])
    def test_late_fabric_recovery_cannot_reselect_hands(self):
        from image_selection import protect
        labels=np.full((80,80),6,dtype='uint8');labels[20:35,20:35]=14
        mask,receipt=protect(Image.new('L',(80,80),255),labels)
        out,_=colour.transfer(self.source,mask,[196,143,139])
        np.testing.assert_array_equal(np.asarray(out)[20:35,20:35],np.asarray(self.source)[20:35,20:35])
        self.assertGreater(receipt['semanticExcludedPixels'],225)
    def test_textless_shots_allow_empty_text_zone_and_do_not_leak_other_shots(self):
        shot={'layout':'scene','sourceIndex':0,'evidence':'visible','question':'shape','scene':'stone street','camera':'front','copy':[], 'subjectBox':[0,0,1,1],'textBox':[0,0,0,0]}
        p=engine.normalize_shots({'identity':'brown trousers','style':{},'shots':[shot]},1,1,True)
        prompt=prompts.compile_shot(p,shot,'Create three images: main, scene, detail')
        self.assertNotIn('Create three images',prompt);self.assertIn('CURRENT OUTPUT ONLY',prompt)

class EngineTests(unittest.TestCase):
    def test_idempotent_saved_intent_and_account_product_binding(self):
        source=engine.cache(Image.new('RGB',(40,40),'#736143'))['url']
        data={'requestId':uuid.uuid4().hex,'mode':'repair','references':[source],'brief':'Remove only the background','editTask':'background'}
        with patch.object(engine,'require_codex'),patch.object(engine,'launch'):
            one=engine.start(data,{'id':'product-a'});two=engine.start(data,{'id':'product-a'})
            self.assertEqual(one['id'],two['id'])
            with self.assertRaises(ValueError):engine.start(data,{'id':'product-b'})
            with self.assertRaises(ValueError):engine.start({**data,'brief':'different'}, {'id':'product-a'})
        self.assertIsNone(one['skuBinding']);self.assertFalse(one['humanReviewed'])
    def test_linkage_cannot_be_supplied_by_request_json(self):
        task={'id':uuid.uuid4().hex,'productId':'p','requestId':uuid.uuid4().hex,'status':'submitting','pending':{'prompt':'exact'}}
        engine.save(task)
        self.assertEqual(engine.authorize(task['id'],{'prompt':'exact'})['imageEngineTaskId'],task['id'])
        with self.assertRaises(ValueError):engine.authorize(task['id'],{'prompt':'changed'})
    def test_restart_never_replays_paid_submit(self):
        task={'id':uuid.uuid4().hex,'productId':'p','requestId':uuid.uuid4().hex,'status':'submitting','pending':{'prompt':'exact'}}
        engine.save(task)
        with patch('image_provider.submit') as submit:
            result=engine.poll(task['id'])
        submit.assert_not_called();self.assertEqual(result['status'],'interrupted')
    def test_suite_prompts_have_no_conflicting_hero_quota(self):
        from types import SimpleNamespace
        p=core.planning_prompt(deliverable='gallery',count_rule='three',product_context='tent',approved='',product_profile_text='tent',img_sp='',template_text='',narrative_text='',deliverable_rules='',body=SimpleNamespace(visual_tone='natural',brief='',language='en'),color_directive='')
        self.assertNotIn('only 1-2',p);self.assertNotIn('≤2 per set',p);self.assertNotIn('At least one image must be absent',p)
        self.assertIn('no quota limiting hero',p)
    def test_plan_rejects_unbound_source_or_outside_geometry(self):
        plan={'identity':'tent','style':{},'shots':[{'layout':'scene','sourceIndex':9,'evidence':'visible','question':'shape','scene':'grass','camera':'front','copy':[], 'subjectBox':[0,0,1,1],'textBox':[0,0,.5,.1]}]}
        with self.assertRaises(ValueError):engine.normalize_shots(plan,1,1,True)
    def test_repair_keeps_original_intent_and_no_fact_expansion(self):
        self.assertIn('Change only the grey background',prompts.compile_edit('background','Change only the grey background'))
        with self.assertRaises(ValueError):prompts.compile_edit('invent','...')

if __name__=='__main__':unittest.main()
