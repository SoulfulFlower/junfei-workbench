import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from local_mask_recolor import recolor, recolor_luminance, fabric_matte, recolor_matted

class RecolorTests(unittest.TestCase):
    def test_background_unchanged_and_fabric_shading_monotonic(self):
        pixels=np.full((20,20,3),240,dtype='uint8')
        pixels[:,5:15]=np.arange(20,dtype='uint8')[:,None,None]*3+20
        source=Image.fromarray(pixels)
        mask=np.zeros((20,20),dtype='uint8');mask[:,5:15]=255
        target=Image.fromarray(np.tile(np.arange(100,200,dtype='uint8').reshape(10,10,1),(1,1,3)))
        result=np.asarray(recolor(source,Image.fromarray(mask),target,(0,0,10,10)))
        np.testing.assert_array_equal(result[:,:5],pixels[:,:5])
        self.assertTrue(np.all(np.diff(result[:,8,0].astype(int))>=0))
        self.assertGreater(int(result[10,8,0]),int(pixels[10,8,0]))

    def test_missing_mask_rejected(self):
        image=Image.new('RGB',(20,20),'brown')
        with self.assertRaises(ValueError):recolor(image,Image.new('L',(20,20)),image,(0,0,20,20))

    def test_black_transfer_preserves_background_and_has_no_green_shadows(self):
        pixels=np.full((40,40,3),210,dtype='uint8')
        for row in range(40):pixels[row,10:30]=[70+row*3,10+row,25+row]
        mask=np.zeros((40,40),dtype='uint8');mask[:,10:30]=255
        target=np.repeat(np.arange(15,55,dtype='uint8')[:,None,None],40,axis=1)
        target=np.repeat(target,3,axis=2)
        result=np.asarray(recolor_luminance(Image.fromarray(pixels),Image.fromarray(mask),Image.fromarray(target),(0,0,40,40)))
        np.testing.assert_array_equal(result[mask==0],pixels[mask==0])
        self.assertLessEqual(np.abs(result[:,20,0].astype(int)-result[:,20,1]).max(),1)
        self.assertTrue(np.all(np.diff(result[:,20,0].astype(int))>=0))
        self.assertGreater(int(result[-1,20,0]),int(result[0,20,0])+20)

    def test_luminance_transfer_rejects_resized_mask_or_invalid_sample(self):
        source=Image.new('RGB',(20,20),'red')
        with self.assertRaises(ValueError):recolor_luminance(source,Image.new('L',(10,10),255),source,(0,0,20,20))
        with self.assertRaises(ValueError):recolor_luminance(source,Image.new('L',(20,20),255),source,(-1,0,20,20))

    def test_pale_transfer_keeps_source_texture_instead_of_reference_pattern(self):
        source=np.full((40,40,3),[105,24,45],dtype='uint8')
        source[::2,10:30]+=np.array([8,4,5],dtype='uint8')
        mask=np.zeros((40,40),dtype='uint8');mask[:,10:30]=255
        ref=np.full((40,40,3),200,dtype='uint8');ref[:,::2]=220
        result=np.asarray(recolor_luminance(Image.fromarray(source),Image.fromarray(mask),Image.fromarray(ref),(0,0,40,40),tone_mapping='affine'))
        np.testing.assert_array_equal(result[mask==0],source[mask==0])
        self.assertTrue(np.all(result[0,10:30]==result[0,10]))
        self.assertGreater(int(result[0,15,0]),int(result[1,15,0]))
        self.assertLess(int(result[0,15,0])-int(result[1,15,0]),15)

    def test_matted_transfer_preserves_protected_pixels_and_needs_valid_alpha(self):
        pixels=np.full((30,30,3),[130,30,50],dtype='uint8');pixels[:,:8]=[70,45,25]
        source=Image.fromarray(pixels);mask=Image.new('L',(30,30),255)
        protected=np.zeros((30,30),dtype='uint8');protected[:,:8]=255
        alpha=fabric_matte(source,mask,Image.fromarray(protected),radius=1)
        self.assertTrue(np.all(alpha[:,:8]==0))
        result=np.asarray(recolor_matted(source,alpha,Image.new('RGB',(30,30),(200,180,170)),(0,0,30,30)))
        np.testing.assert_array_equal(result[:,:8],pixels[:,:8])
        self.assertGreater(result[15,20,1],pixels[15,20,1])
        with self.assertRaises(ValueError):recolor_matted(source,np.zeros((3,3)),source,(0,0,30,30))

    def test_mixed_pixels_replace_fabric_once_without_squared_alpha_fringe(self):
        foreground=np.full((30,30,3),[130,30,50],dtype=np.float64)/255
        alpha=np.ones((30,30));alpha[:,:5]=0;alpha[:,5:10]=.5
        background=np.array([70,45,25],dtype=np.float64)/255
        original=np.rint((alpha[:,:,None]*foreground+(1-alpha[:,:,None])*background)*255).astype('uint8')
        with patch('pymatting.estimate_foreground_ml',return_value=foreground):
            result=np.asarray(recolor_matted(Image.fromarray(original),alpha,Image.new('RGB',(30,30),(200,180,170)),(0,0,30,30)))
        np.testing.assert_array_equal(result[:,:5],original[:,:5])
        expected=original[15,7].astype(float)+.5*(result[15,20].astype(float)-np.array([130,30,50]))
        np.testing.assert_allclose(result[15,7],expected,atol=1)

    def test_soft_highlights_remain_monotonic_without_clipping_and_cache_avoids_reestimating(self):
        import cv2
        source=np.zeros((40,40,3),dtype='uint8')
        for row in range(40):source[row]=[70+row*4,15+row,30+row]
        mask=Image.new('L',(40,40),255);ref=Image.new('RGB',(40,40),(235,228,225))
        result=np.asarray(recolor_luminance(Image.fromarray(source),mask,ref,(0,0,40,40),tone_mapping='soft_affine'))
        light=cv2.cvtColor(result.astype('float32')/255,cv2.COLOR_RGB2LAB)[:,20,0]
        self.assertTrue(np.all(np.diff(light)>=-.05));self.assertLess(light[-1],100)
        foreground=source.astype(float)/255
        with patch('pymatting.estimate_foreground_ml',side_effect=AssertionError('Should use the shared cached foreground')):
            cached=np.asarray(recolor_matted(Image.fromarray(source),np.ones((40,40)),ref,(0,0,40,40),tone_mapping='soft_affine',foreground=foreground))
        np.testing.assert_array_equal(cached,result)

    def test_thin_fabric_and_accessory_constraints_survive_trimap_erosion(self):
        src=Image.new('RGB',(30,30),(100,20,40));mask=np.zeros((30,30),dtype='uint8');mask[:,13:17]=255
        with patch('pymatting.estimate_alpha_cf',side_effect=lambda image,trimap,**kwargs:trimap.copy()):
            alpha=fabric_matte(src,Image.fromarray(mask),radius=4,foreground_seeds=[[14,10]],background_seeds=[[15,20]])
        self.assertEqual(alpha[10,14],1);self.assertEqual(alpha[20,15],0)
        with self.assertRaises(ValueError):fabric_matte(src,Image.fromarray(mask),foreground_seeds=[[30,5]])
