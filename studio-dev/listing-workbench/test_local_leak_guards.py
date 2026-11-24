"""Adversarial guards for deletion: no manually edited real-product fixtures."""
import unittest
import numpy as np
from PIL import Image
import automatic_local_selection as local

class BoundedLeakGuards(unittest.TestCase):
    def fixture(self,alpha=75):
        old=np.zeros((64,64),'uint8');old[20:30,10:20]=255;old[24,30]=alpha
        row={'bboxPixels':[0,0,64,64],'evidencePointPixels':[30,24]}
        cloth=Image.new('L',(64,64));non=Image.new('L',(64,64));non.putpixel((30,24),255)
        return old,row,cloth,non,{'foreground':[[15,25]]}
    def test_opaque_cloth_is_immutable(self):
        with self.assertRaises(local.LocalSelectionRejected):local._remove_confirmed_weak_leak(*self.fixture(255))
    def test_dual_instance_disagreement_stops(self):
        args=list(self.fixture());args[2].putpixel((30,24),255)
        with self.assertRaises(local.LocalSelectionRejected):local._remove_confirmed_weak_leak(*args)
    def test_evidence_must_be_actually_selected(self):
        with self.assertRaises(local.LocalSelectionRejected):local._remove_confirmed_weak_leak(*self.fixture(0))
    def test_old_source_anchor_cannot_be_deleted(self):
        args=list(self.fixture());args[4]['sourceClothAnchors']=[[30,24]]
        with self.assertRaises(local.LocalSelectionRejected):local._remove_confirmed_weak_leak(*args)
    def test_large_subtraction_cannot_hide_as_small_leak(self):
        args=list(self.fixture());args[0][22:28,27:34]=75;args[3]=Image.fromarray((args[0]==75).astype('uint8')*255)
        with self.assertRaises(local.LocalSelectionRejected):local._remove_confirmed_weak_leak(*args)
    def test_roi_clipped_connected_area_is_rejected(self):
        args=list(self.fixture());args[0][24,30:64]=75;args[3]=Image.fromarray((args[0]==75).astype('uint8')*255)
        with self.assertRaises(local.LocalSelectionRejected):local._remove_confirmed_weak_leak(*args)
    def test_fresh_leak_claim_cannot_be_audit_only_or_unconfirmed(self):
        source=Image.new('RGBA',(64,64));regions=[{'regionId':0,'bboxPixels':[0,0,64,64]}]
        row={'regionId':0,'status':'true_leak','classification':'non_target','reason':'actual source ownership',
            'assessedEntireRegion':True,'nonTargetDyeObserved':False,'evidencePoint':[.5,.5],
            'foreground':[{'point':[.2,.2],'evidence':'actual cloth'}],
            'background':[{'point':[.5,.5],'kind':'background','evidence':'actual non-target'}]}
        with self.assertRaises(local.LocalSelectionRejected):local._grounded({'regions':[row]},regions,source)
    def test_pixel_proposals_never_change_the_input_mask(self):
        old,*_=self.fixture();mask=Image.fromarray(old);before=mask.tobytes()
        rows=local._weak_hypotheses(mask,[{'regionId':0,'bboxPixels':[0,0,64,64],'reportedPointPixels':[30,24]}])
        self.assertEqual(mask.tobytes(),before);self.assertFalse(rows[0]['certifiesNonTarget'])

if __name__=='__main__':unittest.main()
