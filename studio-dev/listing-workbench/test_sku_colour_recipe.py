import unittest
from sku_colour_recipe import derive
class MeasuredRecipe(unittest.TestCase):
    def test_dark_colour_retains_native_light_blend_and_scales_curve(self):
        s,a=derive([138,75,37],'#412218')
        self.assertEqual(s['4']['bAdjustLight'],1)
        self.assertAlmostEqual(a['curveGain'],65/(138+(65-138)*138/255))
        self.assertEqual(s['8']['RGBchannel'][0],{'x':0.,'y':0.})
    def test_light_colours_do_not_add_shadow_crushing_curve(self):
        s,a=derive([138,75,37],'#c8b094');self.assertNotIn('8',s);self.assertEqual(s['4']['bAdjustLight'],0)
    def test_near_neutral_targets_follow_original_lab_branch(self):
        for target in ['#303030','#31302f','#000000']:
            s,a=derive([138,75,37],target);self.assertNotIn('8',s);self.assertEqual(a['branch'],'native_achromatic_Lab')
    def test_missing_or_invalid_measurements_fail(self):
        for anchor in ([0,0,0],[-1,5,6],[float('nan'),2,3]):
            with self.assertRaises(ValueError):derive(anchor,'#412218')
