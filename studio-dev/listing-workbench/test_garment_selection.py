import unittest
import numpy as np
from garment_selection import GarmentSelector

class SelectionTests(unittest.TestCase):
 def test_rejects_invalid_points_before_inference(self):
  for points in [[],[[1]],[[float('nan'),2]],[[-1,3]],[[10,3]],[[2,10]]]:
   with self.assertRaises(ValueError):GarmentSelector.points(points,(10,10))
 def test_texture_holes_fill_but_real_opening_and_border_remain(self):
  mask=np.zeros((20,20),bool);mask[2:18,2:18]=True;mask[5:7,5:7]=False;mask[10:13,10:13]=False
  out=GarmentSelector.fill_unprompted_holes(mask,np.array([[11,11]]))
  self.assertTrue(out[5,5]);self.assertFalse(out[11,11]);self.assertFalse(out[0,0])

if __name__=='__main__':unittest.main()
