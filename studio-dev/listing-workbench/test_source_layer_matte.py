import unittest,sys,types
from unittest.mock import patch
import numpy as np
from PIL import Image
import image_fidelity
class OriginalOpaqueInteriors(unittest.TestCase):
    def run_matte(self,label,kind=None):
        rgb=np.full((100,100,3),145,np.uint8)
        human=np.zeros((100,100),np.uint8);human[10:90,25:75]=label
        class Parser:
            def predict(self,source):return human
        def alpha(source,trimap,**kwargs):return trimap.copy()
        with patch('garment_auto.human_parser',return_value=Parser()),patch.dict(sys.modules,{'pymatting':types.SimpleNamespace(estimate_alpha_cf=alpha)}):
            fg,a,receipt=image_fidelity.source_layer(Image.fromarray(rgb),kind=kind,backend='legacy')
        return rgb,fg,a
    def test_background_coloured_knit_grooves_stay_opaque_inside_semantic_sleeve(self):
        rgb,fg,a=self.run_matte(4)
        self.assertTrue((a[20:80,35:65]==1).all())
        out,stats=image_fidelity.composite_layer(Image.fromarray(rgb),Image.new('RGB',(100,100),'white'),fg,a)
        self.assertEqual(stats['immutableCoreChangedPixels'],0)
        self.assertTrue((np.asarray(out)[20:80,35:65]==rgb[20:80,35:65]).all())
    def test_lower_fringe_zone_is_not_filled_by_opaque_interior_rule(self):
        _,_,a=self.run_matte(6)
        self.assertTrue((a[30:60,35:65]==1).all())
        self.assertFalse(a[80:88,35:65].any())
        self.assertFalse(a[:5].any())
    def test_upper_product_keeps_non_target_pants_opaque_to_source_lower_edge(self):
        _,_,a=self.run_matte(6,kind='upper')
        self.assertTrue((a[80:86,35:65]==1).all())
    def test_existing_source_top_cut_stays_on_canvas_edge_without_stretch(self):
        from image_source_layers import compose
        source=Image.new('RGB',(100,100),(140,75,37))
        fg=np.asarray(source).astype(float)/255;alpha=np.zeros((100,100));alpha[:90,20:80]=1
        _,_,placements=compose(source,Image.new('RGB',(100,100),'white'),
            [{'kind':'wearer','crop':[0,0,1,1],'box':[.1,.1,.8,.8]}],fg,alpha,Image.fromarray((alpha*255).astype('uint8')),size=100)
        self.assertEqual(placements[0]['outputBoxPixels'],[10,0,80,80])
    def test_faint_white_border_alpha_cannot_reverse_planned_left_placement(self):
        from image_source_layers import compose
        source=Image.new('RGB',(100,200),'green');fg=np.asarray(source).astype(float)/255
        alpha=np.zeros((200,100));alpha[:,15:85]=1;alpha[:,[0,-1]]=.01
        _,_,p=compose(source,Image.new('RGB',(100,100),'white'),
            [{'kind':'wearer','crop':[0,0,1,1],'box':[.02,.02,.625,.962]}],fg,alpha,Image.new('L',source.size),size=100)
        self.assertFalse(p[0]['sourceCutEdges']['left']);self.assertFalse(p[0]['sourceCutEdges']['right'])
        self.assertLess(p[0]['outputBoxPixels'][0],20);self.assertEqual(p[0]['outputBoxPixels'][1:],[0,50,100])
        self.assertFalse(p[0]['stretched'])
    def test_real_bottom_cut_is_at_canvas_bottom_and_never_floats(self):
        from image_source_layers import compose
        source=Image.new('RGB',(100,200),'green');fg=np.asarray(source).astype(float)/255
        alpha=np.zeros((200,100));alpha[20:,20:80]=1
        _,_,p=compose(source,Image.new('RGB',(100,100),'white'),
            [{'kind':'wearer','crop':[0,0,1,1],'box':[.1,.1,.6,.8]}],fg,alpha,Image.new('L',source.size),size=100)
        x,y,w,h=p[0]['outputBoxPixels'];self.assertEqual(y+h,100)
        self.assertEqual(w/h,.5)
    def test_fully_tiled_model_detail_layers_are_not_replaced_by_one_generic_crop(self):
        from image_source_layers import tiled_details
        shot={'layout':'detail','copy':[],'sourceLayers':[
            {'kind':'detail','box':[0,0,1,.65],'crop':[0,0,1,.5]},
            {'kind':'detail','box':[0,.65,1,.35],'crop':[0,.5,1,.5]}]}
        self.assertTrue(tiled_details(shot));shot['sourceLayers'][1]['box']=[0,.7,1,.3]
        self.assertFalse(tiled_details(shot))
    def test_background_reuse_selects_final_cleanup_instead_of_rejected_original(self):
        from image_source_layers import reusable_plates
        parent={'request':{'apparelSuite':True},'plan':{'shots':[{'index':0,'layout':'main'},{'index':1,'layout':'scene'},{'index':2,'layout':'detail','copy':[]}]},
            'results':[{'index':1,'rawModelOutput':'/clean.png'}],
            'backgroundPlates':[{'index':1,'raw':'/rejected.png','emptyPlateCheck':{'clear':False}}],
            'backgroundCleanups':[{'index':1,'raw':'/clean.png','emptyPlateCheck':{'clear':True}}]}
        self.assertEqual(reusable_plates(parent)[0]['raw'],'/clean.png')
        parent['backgroundCleanups'][0]['emptyPlateCheck']['clear']=False
        with self.assertRaises(ValueError):reusable_plates(parent)
    def test_background_repair_preserves_portrait_product_aspect_on_square_canvas(self):
        import image_source_layers as layers,image_engine as engine
        source=Image.new('RGB',(300,600),'red');plate=Image.new('RGB',(1600,1600),'gray')
        foreground=np.asarray(source).astype(float)/255;alpha=np.ones((600,300));mask=Image.new('L',source.size,255)
        task={'results':[],'request':{'fidelityPolicy':{'garmentKind':'upper'},'neutralBackground':False}}
        saved=[]
        def cache(image):
            saved.append(image.copy());return {'url':'/saved-'+str(len(saved))+'.png','sha256':'sha'}
        with patch.object(engine,'asset',side_effect=lambda url:(source if url=='/source.png'else plate,'sha')),patch.object(engine,'cache',side_effect=cache),patch.object(engine,'save'),patch.object(layers,'prepare',return_value=(foreground,alpha,mask,{})),patch.object(layers,'check_plate',return_value={'clear':True}):
            result=layers.repair(task,'background only',['/source.png'],lambda *a,**k:{'raw':'/plate.png','aspectValid':True})
        self.assertEqual(saved[0].size,(300,600));self.assertEqual(saved[-1].size,(1600,1600))
        self.assertEqual(result['sourcePlacements'][0]['outputBoxPixels'][2:],[800,1600])
    def test_repair_reuse_requires_the_final_verified_plate_and_never_repays(self):
        from image_source_layers import reusable_repair_plate
        parent={'id':'original','status':'needs_revision','request':{'mode':'repair'},'results':[{'rawModelOutput':'/clean.png'}],
            'backgroundPlates':[{'raw':'/rejected.png','emptyPlateCheck':{'clear':False}}],
            'backgroundCleanups':[{'raw':'/clean.png','providerJobId':'original-paid-job','emptyPlateCheck':{'clear':True}}]}
        self.assertEqual(reusable_repair_plate(parent)['providerJobId'],'original-paid-job')
        parent['status']='submission_unknown'
        with self.assertRaises(ValueError):reusable_repair_plate(parent)
        parent['status']='needs_revision';parent['backgroundCleanups'][0]['emptyPlateCheck']['clear']=False
        with self.assertRaises(ValueError):reusable_repair_plate(parent)
