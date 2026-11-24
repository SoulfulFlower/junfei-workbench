import unittest,numpy as np,importlib.util
from pathlib import Path
worker=Path(__file__).with_name('sam2_local_worker.py')
if not worker.exists():worker=Path(__file__).parent/'models/local-instance/sam2_local_worker.py'
spec=importlib.util.spec_from_file_location('tested_native_worker',worker);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
choose_native_proposal=module.choose_native_proposal

class NativeProposals(unittest.TestCase):
 def test_wrong_higher_score_cannot_override_protection(self):
  candidates=np.full((3,16,16),-4.,'float32');candidates[:,5,5]=4;candidates[0,0,0]=4
  before=candidates.copy();i,r=choose_native_proposal(candidates,[.99,.82,.8],[[5,5]],[[0,0]])
  self.assertEqual(i,1);self.assertEqual(r['maskPixelsForced'],0);self.assertTrue(np.array_equal(before,candidates))
 def test_no_candidate_is_never_painted_into_compliance(self):
  candidates=np.ones((3,16,16),'float32');before=candidates.copy()
  with self.assertRaises(ValueError):choose_native_proposal(candidates,[.9,.8,.7],[[5,5]],[[0,0]])
  self.assertTrue(np.array_equal(before,candidates))
 def test_all_positive_and_negative_points_required(self):
  candidates=np.full((3,16,16),-2.,'float32');candidates[:,5,5]=2;candidates[2,6,6]=2
  i,_=choose_native_proposal(candidates,[.9,.8,.7],[[5,5],[6,6]],[[0,0]])
  self.assertEqual(i,2)
 def test_original_single_mask_token_is_kept_when_multimask_tokens_fail(self):
  c=np.ones((4,16,16),'float32');c[:,5,5]=4;c[3,0,0]=-4
  self.assertEqual(choose_native_proposal(c,[.99,.98,.97,.8],[[5,5]],[[0,0]])[0],3)
 def test_nonfinite_evidence_rejects_and_ties_are_deterministic(self):
  c=np.zeros((3,16,16),'float32');c[:,5,5]=2
  self.assertEqual(choose_native_proposal(c,[.8,.8,.8],[[5,5]],[[0,0]])[0],0)
  c[0,2,2]=np.nan
  with self.assertRaises(ValueError):choose_native_proposal(c,[.8,.8,.8],[[5,5]],[[0,0]])

if __name__=='__main__':unittest.main()
