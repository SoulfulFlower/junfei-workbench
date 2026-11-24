import unittest
import numpy as np
from PIL import Image
from garment_colour_mask import refine
from sku_colour_recipe import feedback
class NeutralFabric(unittest.TestCase):
    def fixture(self):
        rgb=np.full((100,100,3),40,np.uint8);rgb[10:90,20:80]=[213,203,201]
        cloth=np.zeros((100,100),np.uint8);cloth[10:90,20:80]=1
        human=np.zeros((100,100),np.uint8);human[10:90,20:80]=4;human[25:65,20:30]=14
        a=np.zeros((100,100),np.uint8);a[10:90,20:80]=255;a[25:65,20:30]=0
        return rgb,a,cloth,human
    def test_matching_clothing_arm_label_is_recovered_but_actual_skin_is_protected(self):
        rgb,a,c,h=self.fixture();rgb[75:85,20:30]=[198,150,120];h[75:85,20:30]=14
        out,r=refine(Image.fromarray(rgb),Image.fromarray(a),'upper',c,h)
        self.assertTrue((np.asarray(out)[30:60,23:28]>240).all())
        self.assertFalse(np.asarray(out)[78:82,23:28].any())
        self.assertGreater(r['armLabelFabricRecoveredPixels'],100)
    def test_second_clothing_evidence_and_explicit_protection_are_required(self):
        rgb,a,c,h=self.fixture();c[25:45,20:30]=0;p=np.zeros(a.shape,'uint8');p[50:55,20:30]=255
        out,r=refine(Image.fromarray(rgb),Image.fromarray(a),'upper',c,h,protected=Image.fromarray(p))
        self.assertFalse(np.asarray(out)[28:40,22:28].any());self.assertFalse(np.asarray(out)[50:55,22:28].any())
    def test_preview_feedback_anchors_actual_midtones_and_preserves_custom_curves(self):
        source=Image.new('RGBA',(100,100),(220,210,210,255));preview=Image.new('RGBA',(100,100),(63,61,64,255));mask=Image.new('L',(100,100),255)
        result=feedback(source,mask,'#2f2d30',preview,{'4':{'bAdjustLight':0}})
        self.assertTrue(result['audit']['applied']);self.assertEqual(result['settings']['8']['Rchannel'][1],{'x':63.,'y':47.})
        fixed=feedback(source,mask,'#2f2d30',preview,result['settings']);self.assertFalse(fixed['audit']['applied'])
    def test_feedback_rejects_spill(self):
        source=Image.new('RGBA',(100,100),'white');preview=Image.new('RGBA',(100,100),'gray');mask=Image.new('L',(100,100),255);mask.putpixel((0,0),0)
        with self.assertRaises(ValueError):feedback(source,mask,'#2f2d30',preview,{})
    def test_close_neutral_native_image_is_not_graded_through_a_broken_mask(self):
        from image_fidelity import calibrate
        source=Image.new('RGB',(100,100),(213,203,201));native=Image.new('RGB',(100,100),(220,205,207));a=np.ones((100,100),'uint8')*255;a[25:50,25:50]=0
        result,receipt=calibrate(source,native,Image.new('L',(100,100),255),Image.fromarray(a))
        self.assertTrue(np.array_equal(np.asarray(result),np.asarray(native)))
        self.assertEqual(receipt['allPixelsChanged'],0)
