import copy
import hashlib
import unittest
import numpy as np
import cv2
from PIL import Image
from garment_component_proposals import propose


def fixture():
    rgb = np.full((256, 256, 3), [35, 35, 35], 'uint8'); rgb[40:220, 60:210] = [105, 135, 110]
    primary = np.zeros((256, 256), bool); primary[40:220, 60:210] = True
    primary[100:112, 110:122] = False
    human = np.zeros(primary.shape, 'uint8'); human[40:220, 60:210] = 4
    evidence = {'primary': primary, 'human': human, 'distance': np.full(primary.shape, 2., 'float32'),
        'protected': np.zeros(primary.shape, bool), 'sourceRGB': rgb.copy(),
        'sourceLab': cv2.cvtColor(rgb.astype('float32')/255, cv2.COLOR_RGB2LAB),
        'opaqueSource': np.ones(primary.shape, bool), 'semanticGarmentClasses': [4],
        'kind': 'upper', 'other': np.zeros(primary.shape, bool)}
    return Image.fromarray(rgb), evidence


class ProposalTests(unittest.TestCase):
    def test_deepest_point_is_actual_stable_component_interior_and_only_a_hypothesis(self):
        source, evidence = fixture(); before = {k: v.copy() for k, v in evidence.items() if isinstance(v, np.ndarray)}
        original = source.tobytes(); result = propose(source, 'upper', evidence)
        context = result['context']; region = context['regions'][0]; x, y = region['pointPixels']
        self.assertTrue(110 < x < 121 and 100 < y < 111)
        self.assertFalse(evidence['primary'][y, x]); self.assertEqual(evidence['human'][y, x], 4)
        self.assertEqual(region['componentPixels'], 144); self.assertEqual(region['stableInteriorPixels'], 100)
        self.assertGreaterEqual(region['deepestInteriorDistancePixels'], 6)
        self.assertEqual(region['point'], [x/255, y/255])
        self.assertTrue(context['unverifiedHypothesis']); self.assertFalse(context['certifiesSelection'])
        self.assertFalse(context['modifiesMask']); self.assertIn('not_evaluated', context['foregroundAnchorStatus'])
        self.assertEqual(source.tobytes(), original)
        for key, value in before.items():self.assertTrue(np.array_equal(evidence[key], value))

    def test_wrong_hue_protected_anatomy_hair_other_and_transparent_do_not_propose(self):
        for defect in ('hue', 'protected', 'arm', 'hair', 'other', 'transparent'):
            source, evidence = fixture(); a = (slice(100, 112), slice(110, 122))
            if defect == 'hue':evidence['distance'][a] = 25
            if defect == 'protected':evidence['protected'][a] = True
            if defect == 'arm':evidence['human'][a] = 14
            if defect == 'hair':evidence['human'][a] = 2
            if defect == 'other':evidence['other'][a] = True
            if defect == 'transparent':
                rgba = np.asarray(source.convert('RGBA')).copy(); rgba[a[0], a[1], 3] = 0
                source = Image.fromarray(rgba); evidence['opaqueSource'][a] = False
            with self.subTest(defect=defect):
                result = propose(source, 'upper', evidence)
                self.assertEqual(result['context']['regions'], []); self.assertIsNone(result['montage'])

    def test_far_background_large_inner_garment_and_no_stable_interior_are_filtered(self):
        for defect in ('far', 'large', 'thin'):
            source, evidence = fixture(); evidence['human'][100:112, 110:122] = 0
            if defect == 'far':
                evidence['human'][5:15, 5:15] = 4
            if defect == 'large':
                evidence['primary'][70:120, 80:130] = False  # 2500px same-colour inner clothing hypothesis
            if defect == 'thin':
                evidence['primary'][140:142, 100:120] = False
            with self.subTest(defect=defect):
                self.assertEqual(propose(source, 'upper', evidence)['context']['regions'], [])

    def test_region_limit_and_single_montage_are_bounded(self):
        source, evidence = fixture()
        for y in (65, 95, 125, 155):
            for x in (80, 140):evidence['primary'][y:y+8, x:x+8] = False
        all_result = propose(source, 'upper', evidence); limited = propose(source, 'upper', evidence, max_regions=2)
        self.assertEqual(len(all_result['context']['regions']), 6)
        self.assertEqual(len(limited['context']['regions']), 2)
        self.assertEqual(limited['montage'].size, (512, 560))
        self.assertGreater(all_result['context']['candidateRegionsBeforeLimit'], 6)
        disabled = propose(source, 'upper', evidence, max_regions=0)
        self.assertIsNone(disabled['montage'])
        for value in (7, -1, True, 1.2):
            with self.subTest(value=value), self.assertRaises(ValueError):propose(source, 'upper', evidence, max_regions=value)

    def test_original_crop_and_overlay_pixels_have_exact_global_mapping_and_hashes(self):
        source, evidence = fixture(); rgb = np.asarray(source).copy()
        yy, xx = np.indices(rgb.shape[:2]); rgb[:, :, 0] = xx; rgb[:, :, 1] = yy
        source = Image.fromarray(rgb); evidence['sourceRGB'] = rgb.copy()
        evidence['sourceLab'] = cv2.cvtColor(rgb.astype('float32')/255, cv2.COLOR_RGB2LAB)
        result = propose(source, 'upper', evidence); montage = np.asarray(result['montage'])
        region = result['context']['regions'][0]; x0, y0, x1, y1 = region['cropBBoxPixels']
        self.assertTrue(0 <= x0 < x1 <= 256 and 0 <= y0 < y1 <= 256)
        self.assertGreaterEqual(region['displayScale'], 2.)
        self.assertEqual(region['cropPixelSha256'], hashlib.sha256(rgb[y0:y1, x0:x1].tobytes()).hexdigest())
        self.assertEqual(region['sourcePixelSha256'], hashlib.sha256(source.convert('RGBA').tobytes()).hexdigest())
        mask = np.zeros((256, 256), 'uint8'); mask[100:112, 110:122] = 255
        self.assertEqual(region['componentPixelSha256'], hashlib.sha256(mask.tobytes()).hexdigest())
        for column, box in enumerate(region['panelBoxesPixels']):
            for dx, dy in ((0, 0), (128, 128), (255, 255)):
                sx = x0+int((dx+.5)*(x1-x0)/256); sy = y0+int((dy+.5)*(y1-y0)/256)
                pixel = rgb[sy, sx]
                if column and mask[sy, sx]:pixel = np.rint(pixel*.4+np.array([20, 150, 240])*.6).astype('uint8')
                self.assertTrue(np.array_equal(montage[box[1]+dy, box[0]+dx], pixel))

    def test_kind_semantics_do_not_promote_another_garment(self):
        source, evidence = fixture()
        with self.assertRaises(ValueError):propose(source, 'lower', evidence)
        evidence['kind'] = 'lower'; evidence['semanticGarmentClasses'] = [5, 6]
        self.assertEqual(propose(source, 'lower', evidence)['context']['regions'], [])
        evidence['human'][100:112, 110:122] = 6
        self.assertEqual(len(propose(source, 'lower', evidence)['context']['regions']), 1)

    def test_source_evidence_mismatch_invalid_arrays_and_empty_body_fail_closed(self):
        source, evidence = fixture(); stale = copy.deepcopy(evidence); stale['sourceRGB'][0, 0] = 255
        with self.assertRaises(ValueError):propose(source, 'upper', stale)
        for key, value in (('distance', np.zeros((10, 10))), ('human', np.full((256, 256), 18)),
                ('distance', np.full((256, 256), float('nan')))):
            invalid = {**evidence, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):propose(source, 'upper', invalid)
        evidence['primary'][:] = False
        self.assertIsNone(propose(source, 'upper', evidence)['montage'])


if __name__ == '__main__':unittest.main()
