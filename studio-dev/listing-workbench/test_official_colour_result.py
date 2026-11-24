import unittest,hashlib
from unittest.mock import patch
import numpy as np
from PIL import Image
import official_colour_result as module


class ReceiptTests(unittest.TestCase):
    def fixture(self):
        source=Image.new('RGBA',(40,40),(120,80,40,255));a=np.zeros((40,40),np.uint8);a[8:32,8:32]=255;mask=Image.fromarray(a)
        pixels=np.asarray(source).copy();pixels[8:32,8:32,:3]=[190,160,150];result=Image.fromarray(pixels)
        resources={'sourceHashes':{'original':'verified'},'config':{'filters':[{'index':'0','fs':'original.fs'}]}}
        receipt={'renderer':'original-glsl-webgl2-native-quad-v2','sourceHashes':resources['sourceHashes'],
            'passes':[{'index':'0','fs':'original.fs'}],'boundaryPolicy':'preserve_outside_selection_source_rgba',
            'hashPixelOrder':'rgba8_top_to_bottom','outputSHA':hashlib.sha256(pixels.tobytes()).hexdigest(),'nativeOutputSHA':'n'*64}
        return source,mask,result,resources,receipt

    def test_quality_boundary_hash_and_pixels_are_independently_verified(self):
        source,mask,result,resources,receipt=self.fixture()
        with patch.object(module.library,'colour_resources',return_value=resources):
            checked=module.validate(source,mask,result,receipt)
        self.assertEqual(checked['outsideChangedPixels'],0);self.assertEqual(checked['nativeOutputSHA'],'n'*64)

    def test_native_parity_output_is_not_mislabelled_as_protected_delivery(self):
        s,m,r,c,receipt=self.fixture();receipt['boundaryPolicy']='native_filter_output'
        with patch.object(module.library,'colour_resources',return_value=c),self.assertRaises(ValueError):module.validate(s,m,r,receipt)

    def test_forged_sha_or_reordered_pass_is_rejected(self):
        s,m,r,c,receipt=self.fixture()
        with patch.object(module.library,'colour_resources',return_value=c):
            with self.assertRaises(ValueError):module.validate(s,m,r,{**receipt,'outputSHA':'wrong'})
            with self.assertRaises(ValueError):module.validate(s,m,r,{**receipt,'passes':[]})

    def test_even_a_matching_claimed_sha_cannot_authorize_outside_spill(self):
        s,m,r,c,receipt=self.fixture();pixels=np.asarray(r).copy();pixels[0,0,0]+=1;r=Image.fromarray(pixels)
        receipt['outputSHA']=hashlib.sha256(pixels.tobytes()).hexdigest()
        with patch.object(module.library,'colour_resources',return_value=c),self.assertRaises(ValueError):module.validate(s,m,r,receipt)


if __name__=='__main__':unittest.main()
