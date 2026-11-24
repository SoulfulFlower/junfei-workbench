import unittest
import garment_auto as garment

class GarmentCategories(unittest.TestCase):
 def test_explicit_chinese_skirt_names_are_lower_garments(self):
  for name in ['女士仿麂皮绒蕾丝边开衩短裙','女士百褶裙','女士A字裙','女士半身裙','women skirt']:
   with self.subTest(name=name):self.assertEqual(garment.category({'name':name}),'lower')
 def test_existing_dress_upper_and_unknown_scopes_are_preserved(self):
  for name,kind in [('女士短款连衣裙','full'),('女士毛衣','upper'),('男士长裤','lower'),('白色陶瓷杯','auto')]:
   with self.subTest(name=name):self.assertEqual(garment.category({'name':name}),kind)

if __name__=='__main__':unittest.main()
