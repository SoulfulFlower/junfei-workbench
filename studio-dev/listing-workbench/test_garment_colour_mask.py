import unittest
import numpy as np
from PIL import Image
from garment_colour_mask import refine


class FineSelectionTests(unittest.TestCase):
    def fixture(self):
        rgb=np.full((100,100,3),150,np.uint8);rgb[10:90,20:80]=[142,82,42]
        mask=np.zeros((100,100),np.uint8);mask[10:90,20:80]=255
        cloth=np.zeros((100,100),np.uint8);cloth[10:90,20:80]=2
        human=np.zeros((100,100),np.uint8);human[10:90,20:80]=6
        return rgb,mask,cloth,human

    def test_source_neutral_gaps_are_removed_from_coarse_solid_hem(self):
        rgb,mask,cloth,human=self.fixture()
        for x in range(23,78,6):rgb[75:90,x:x+2]=150
        out,receipt=refine(Image.fromarray(rgb),Image.fromarray(mask),'lower',cloth,human)
        a=np.asarray(out)
        for x in range(23,78,6):self.assertFalse(a[76:89,x:x+2].any())
        self.assertTrue((a[76:89,25:27]>240).all())
        self.assertGreater(receipt['neutralGapPixelsRemoved'],100)

    def test_neutral_interior_seam_is_not_mistaken_for_background(self):
        rgb,mask,cloth,human=self.fixture();rgb[35:55,45:48]=[90,90,90]
        out,_=refine(Image.fromarray(rgb),Image.fromarray(mask),'lower',cloth,human)
        self.assertTrue((np.asarray(out)[35:55,45:48]==255).all())

    def test_brown_hand_and_other_garment_remain_protected(self):
        rgb,mask,cloth,human=self.fixture();human[30:40,30:40]=14
        cloth[10:20,40:60]=1;human[10:20,40:60]=4
        out,_=refine(Image.fromarray(rgb),Image.fromarray(mask),'lower',cloth,human)
        self.assertFalse(np.asarray(out)[30:40,30:40].any());self.assertFalse(np.asarray(out)[10:20,40:60].any())

    def test_uncoloured_boot_and_explicit_hardware_protection_win(self):
        rgb,mask,cloth,human=self.fixture();rgb[85:90,30:40]=[15,15,15];human[85:90,30:40]=12
        p=np.zeros((100,100),np.uint8);p[30:35,40:45]=255
        out,_=refine(Image.fromarray(rgb),Image.fromarray(mask),'lower',cloth,human,protected=Image.fromarray(p))
        self.assertFalse(np.asarray(out)[85:90,30:40].any());self.assertFalse(np.asarray(out)[30:35,40:45].any())

    def test_neutral_cloth_does_not_activate_chromatic_edge_recovery(self):
        rgb,mask,cloth,human=self.fixture();rgb[10:90,20:80]=[90,90,90]
        out,r=refine(Image.fromarray(rgb),Image.fromarray(mask),'lower',cloth,human)
        self.assertFalse(r['chromaticContrastSupported']);self.assertTrue(r['limitations'])
        self.assertTrue((np.asarray(out)[30:60,30:60]==255).all())

    def test_whole_frame_without_target_semantic_evidence_is_rejected(self):
        rgb,mask,cloth,human=self.fixture();mask[:]=255;cloth[:]=0
        with self.assertRaises(ValueError):refine(Image.fromarray(rgb),Image.fromarray(mask),'lower',cloth,human)


if __name__=='__main__':unittest.main()
