import io
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from colour_tuning import controls
from local_mask_recolor import render_fabric
import colour_reference


class ToneTests(unittest.TestCase):
    def test_soft_edge_coverage_does_not_expand_half_selected_pixels(self):
        source = Image.new('RGB', (30, 30), (120, 30, 45))
        alpha = np.ones((30, 30)); alpha[:, :5] = 0; alpha[:, 5:10] = .5
        protected = Image.new('L', source.size)
        result = np.asarray(render_fabric(source, alpha, protected, [220, 210, 195]))
        np.testing.assert_array_equal(result[:, :5], np.asarray(source)[:, :5])
        expected = (np.asarray(source)[15, 7].astype(float) + result[15, 20]) / 2
        np.testing.assert_allclose(result[15, 7], expected, atol=1)

    def test_shadows_and_highlights_are_independent_and_never_edit_protection(self):
        source = np.repeat(np.linspace(35, 210, 100).astype('uint8')[:, None, None], 30, axis=1)
        source = Image.fromarray(np.repeat(source, 3, axis=2))
        alpha = np.ones((100, 30)); protected = np.zeros((100, 30), dtype='uint8'); protected[:, :3] = 255
        before = np.asarray(render_fabric(source, alpha, protected, [150, 150, 150]))
        shade = np.asarray(render_fabric(source, alpha, protected, [150, 150, 150], shadows=12))
        shine = np.asarray(render_fabric(source, alpha, protected, [150, 150, 150], highlights=-12))
        self.assertGreater(int(shade[5, 10, 0]), int(before[5, 10, 0]))
        np.testing.assert_array_equal(shade[80, 10], before[80, 10])
        self.assertLess(int(shine[90, 10, 0]), int(before[90, 10, 0]))
        np.testing.assert_array_equal(shine[10, 10], before[10, 10])
        np.testing.assert_array_equal(shine[:, :3], np.asarray(source)[:, :3])

    def test_neutral_target_does_not_inherit_red_fabric_cast(self):
        rgb = np.full((30, 30, 3), [120, 30, 45], dtype='uint8'); rgb[::2, :, 0] += 20
        result = np.asarray(render_fabric(Image.fromarray(rgb), np.ones((30, 30)), np.zeros((30, 30)), [45, 45, 45], colorDetail=1))
        self.assertLessEqual(np.max(np.abs(result[:, :, 0].astype(int) - result[:, :, 1])), 1)

    def test_controls_reject_nonfinite_boolean_and_out_of_range_values(self):
        for data in ({'shadows': True}, {'contrast': 51}, {'saturation': float('nan')}, {'highlights': float('inf')}, {'colorDetail': -1}):
            with self.subTest(data=data), self.assertRaises(ValueError): controls(data)

    def test_balance_curves_hue_are_shared_and_leave_skin_alpha_and_background_exact(self):
        source=Image.new('RGBA',(40,40),(120,35,50,170));alpha=np.zeros((40,40));alpha[5:35,5:35]=1
        protected=np.zeros((40,40),dtype='uint8');protected[12:18,12:18]=255
        result=np.asarray(render_fabric(source,alpha,protected,[80,120,160],hue=30,brightness=5,colorBalance={'midtones':[15,-5,10]},curves={'red':[[0,0],[128,165],[255,255]]}))
        untouched=(alpha==0)|(protected>0)
        np.testing.assert_array_equal(result[untouched],np.asarray(source)[untouched]);np.testing.assert_array_equal(result[:,:,3],170)
        base=np.asarray(render_fabric(source,alpha,protected,[80,120,160]))
        self.assertGreater(np.count_nonzero(result!=base),500)

    def test_curves_and_balance_reject_invalid_shapes_nonfinite_and_duplicate_x(self):
        invalid=[{'curves':{'other':[[0,0],[255,255]]}},{'curves':{'rgb':[[0,0],[0,10],[255,255]]}},{'curves':{'rgb':[[0,0],[128,float('nan')],[255,255]]}},{'colorBalance':{'shadows':[0,True,0]}},{'colorBalance':{'midtones':[101,0,0]}},{'removeCast':1}]
        for data in invalid:
            with self.subTest(data=data),self.assertRaises(ValueError):controls(data)


class SamplingTests(unittest.TestCase):
    def raw(self, rgb):
        out = io.BytesIO(); Image.fromarray(rgb).save(out, 'PNG'); return out.getvalue()

    def test_patch_ignores_white_background_and_a_few_specular_pixels(self):
        rgb = np.full((100, 100, 3), 255, dtype='uint8'); rgb[20:80, 20:80] = [176, 52, 66]; rgb[30:33, 30:33] = 255
        with patch.object(colour_reference.image_provider, 'local_image', return_value=self.raw(rgb)):
            sample = colour_reference.sample('/uploads/fixture.png', [.25, .25, .75, .75])
        np.testing.assert_allclose(sample['rgb'], [176, 52, 66], atol=1)
        self.assertEqual(sample['pixelBox'], [25, 25, 75, 75]); self.assertFalse(sample['imageGenerationSubmitted'])

    def test_black_and_white_products_are_valid_samples(self):
        for value in (8, 245):
            with patch.object(colour_reference.image_provider, 'local_image', return_value=self.raw(np.full((20, 20, 3), value, dtype='uint8'))):
                sample = colour_reference.sample('/uploads/fixture.png', [0, 0, 1, 1])
            np.testing.assert_allclose(sample['rgb'], value, atol=1)

    def test_invalid_or_tiny_regions_cannot_read_images(self):
        with patch.object(colour_reference.image_provider, 'local_image') as read:
            for box in (None, [0, 0, 2, 1], [True, 0, 1, 1], [0, 0, float('nan'), 1]):
                with self.assertRaises(ValueError): colour_reference.sample('/uploads/fixture.png', box)
            read.assert_not_called()
        with patch.object(colour_reference.image_provider, 'local_image', return_value=self.raw(np.zeros((20, 20, 3), dtype='uint8'))):
            with self.assertRaisesRegex(ValueError, '太小'): colour_reference.sample('/uploads/fixture.png', [0, 0, .01, .01])

    def test_transparent_background_never_becomes_a_black_fabric_sample(self):
        rgb = np.zeros((30, 30, 4), dtype='uint8'); rgb[8:22, 8:22] = [175, 55, 70, 255]
        with patch.object(colour_reference.image_provider, 'local_image', return_value=self.raw(rgb)):
            result = colour_reference.sample('/uploads/fixture.png', [0, 0, 1, 1])
            np.testing.assert_allclose(result['rgb'], [175, 55, 70], atol=1)
            with self.assertRaisesRegex(ValueError, '透明背景'): colour_reference.sample('/uploads/fixture.png', [0, 0, .2, .2])


if __name__ == '__main__': unittest.main()
