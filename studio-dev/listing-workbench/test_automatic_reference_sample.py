import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import automatic_reference_sample as tool


SUBJECT = {'productName': 'saved outer garment', 'target': 'saved outer garment', 'role': 'target_colour_reference'}
META = {'provider': 'isolated Codex-compatible fixture', 'model': 'fixture', 'baseUrl': 'http://fixture.invalid'}


def source():
    pixels = np.full((100, 100, 3), 30, 'uint8');pixels[15:90, 20:80] = [105, 135, 110]
    return Image.fromarray(pixels)


def plan():
    return {'samples': [{'point': point, 'radiusFraction': .01, 'part': part,
        'tone': 'midtone', 'evidence': 'clean visible current target fabric'} for point, part in (
        ([.3, .3], 'left sleeve'), ([.6, .4], 'body'), ([.7, .7], 'right sleeve'))], 'limitations': []}


def review(accepted=True):
    return {'accepted': accepted, 'allSamplesOnTarget': accepted, 'representativeColour': accepted,
        'issues': [] if accepted else ['one sample is another garment'], 'warnings': [],
        'invalidSamples': [] if accepted else [{'point': [.6, .4], 'reason': 'visible separate inner garment'}]}


class Backend:
    def identity(self):return {'pinnedLocalModels': 'isolated-cloth-and-human-fixture-v1'}

    def labels(self, image):
        cloth = np.zeros((100, 100), 'uint8');cloth[15:90, 20:80] = 3
        human = np.zeros((100, 100), 'uint8');human[15:90, 20:80] = 4
        return cloth, human, {'clothing': 'isolated-incorrect-full-class', 'human': 'isolated-upper-class'}


class Vision:
    def __init__(self, answers=None):self.answers, self.calls = answers, []

    def __call__(self, instruction, context, images):
        self.calls.append({'instruction': instruction, 'context': context, 'images': images})
        answer = self.answers[len(self.calls)-1] if self.answers is not None else (
            review() if instruction.startswith('Independently') else plan())
        if isinstance(answer, Exception):raise answer
        return {'result': copy.deepcopy(answer), 'receipt': {'provider': 'isolated vision',
            'request': len(self.calls), 'rawModelText': json.dumps(answer)}}


class ReferenceSamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)

    def sample(self, image=None, vision=None, backend=None, subject=None, kind='upper', **kwargs):
        return tool.sample(image or source(), kind, subject=subject or SUBJECT,
            vision=vision or Vision(), cache_root=self.temp.name, vision_metadata=META,
            local_backend=backend or Backend(), **kwargs)

    def test_real_source_pixels_and_distinct_scope_are_bound_and_saved(self):
        vision = Vision();result = self.sample(vision=vision);r = result['receipt']
        self.assertEqual(result['target'], '#69876e')
        self.assertTrue(r['sampleVerified']);self.assertTrue(r['accepted'])
        self.assertEqual(r['verificationScope'], tool.SCOPE)
        self.assertFalse(r['verified']);self.assertFalse(r['eligibleAsSourceSelection'])
        self.assertFalse(r['completeGarmentSelectionVerified']);self.assertFalse(r['humanReviewed'])
        self.assertFalse(r['imageGenerationSubmitted']);self.assertEqual(len(vision.calls), 2)
        self.assertFalse(vision.calls[1]['context']['completeGarmentCoverageRequired'])
        self.assertEqual(r['sourcePixelSha256'], hashlib.sha256(source().convert('RGBA').tobytes()).hexdigest())
        mask = np.asarray(result['mask']);self.assertLess((mask > 0).mean(), .01)
        with np.load(r['samplePixelsPath'], allow_pickle=False) as data:
            xy = data['xy'];rgba = data['rgba']
            self.assertTrue(np.array_equal(rgba, np.asarray(source().convert('RGBA'))[xy[:, 1], xy[:, 0]]))
            self.assertEqual(set(np.unique(data['patch_index']).tolist()), {0, 1, 2})
        self.assertEqual(r['maskPixelSha256'], hashlib.sha256(result['mask'].tobytes()).hexdigest())

    def test_wrong_cloth_subcategory_does_not_require_full_target_mask(self):
        result = self.sample()
        self.assertTrue(result['receipt']['sampleVerified'])
        self.assertEqual(result['receipt']['quality']['cleanSampleCount'], 3)
        # Fixture cloth=3 and requested kind=upper(1), independent human=4.
        self.assertLess(result['receipt']['quality']['selectedFraction'], .01)

    def test_lower_kind_corroborates_wrong_human_upper_class_but_requires_review(self):
        class Pants(Backend):
            def labels(self, image):
                c, h, meta = super().labels(image);c[c > 0] = 2;return c, h, meta
        vision = Vision()
        result = self.sample(kind='lower', backend=Pants(), vision=vision)
        q = result['receipt']['quality']
        self.assertEqual(q['kindCorroboratedMismatchPixels'], q['sourcePixelCount'])
        self.assertEqual(q['requestedClothClass'], 2)
        self.assertTrue(q['targetIdentityRequiresIndependentReview'])
        self.assertEqual(len(vision.calls), 2)
        self.assertEqual(vision.calls[1]['context']['kind'], 'lower')
        self.assertEqual(vision.calls[1]['context']['numericGate']['samples'][0]['humanClasses'], [4])
        self.assertIn('another top, pants, dress', vision.calls[1]['instruction'])
        denied = Vision([plan(), review(False), plan(), review(False)])
        with self.assertRaises(tool.ReferenceSampleRejected) as error:
            self.sample(kind='lower', backend=Pants(), vision=denied,
                subject={**SUBJECT, 'target': 'independently rejected pants'})
        self.assertTrue(error.exception.receipt['attempts'][0]['quality']['accepted'])
        self.assertFalse(error.exception.receipt['sampleVerified'])

    def test_wrong_human_kind_without_exact_cloth_kind_cannot_be_generic_fabric_escape(self):
        vision = Vision()
        with self.assertRaises(tool.ReferenceSampleRejected) as error:
            self.sample(kind='lower', vision=vision)  # cloth full=3, human upper=4
        self.assertEqual(len(vision.calls), 0)
        self.assertFalse(error.exception.receipt['sampleVerified'])

    def test_exact_requested_cloth_does_not_override_anatomy_accessory_or_background(self):
        for protected in (0, 2, 8, 9, 11, 12, 14, 16, 17):
            class Protected(Backend):
                def labels(self, image):
                    c, h, meta = super().labels(image);c[c > 0] = 2;h[h > 0] = protected;return c, h, meta
            with self.subTest(protected=protected), tempfile.TemporaryDirectory() as root:
                vision = Vision()
                with self.assertRaises(tool.ReferenceSampleRejected):
                    tool.sample(source(), 'lower', subject=SUBJECT, vision=vision,
                        cache_root=root, vision_metadata=META, local_backend=Protected())
                self.assertFalse(vision.calls)  # no clean source cloth exists

    def test_known_rejection_is_preserved_when_new_algorithm_reanalyses(self):
        failed = Vision([plan(), review(False), plan(), review(False)])
        with patch.object(tool, 'VERSION', 'old-reference-version'):
            with self.assertRaises(tool.ReferenceSampleRejected) as error:self.sample(vision=failed)
        path = Path(error.exception.receipt['cacheManifestPath']);before = path.read_bytes()
        result = self.sample()
        self.assertTrue(result['receipt']['sampleVerified'])
        self.assertNotEqual(result['receipt']['cacheManifestPath'], str(path))
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_old_version_blocks_new_version_without_new_calls(self):
        failed = Vision([RuntimeError('timeout')])
        with patch.object(tool, 'VERSION', 'old-reference-version'):
            with self.assertRaises(tool.ReferenceSampleRejected) as error:self.sample(vision=failed)
        path = Path(error.exception.receipt['cacheManifestPath']);before = path.read_bytes();fresh = Vision()
        with self.assertRaises(tool.ReferenceSampleRejected) as retry:self.sample(vision=fresh, kind='lower')
        self.assertEqual(retry.exception.code, 'reference_sample_unknown')
        self.assertFalse(fresh.calls);self.assertEqual(path.read_bytes(), before)

    def test_cache_reuses_without_new_model_calls(self):
        vision = Vision();a = self.sample(vision=vision);b = self.sample(vision=vision)
        self.assertEqual(len(vision.calls), 2);self.assertTrue(b['receipt']['cacheReused'])
        self.assertEqual(a['mask'].tobytes(), b['mask'].tobytes())

    def test_target_is_an_actual_source_pixel_not_a_colour_name_guess(self):
        result = self.sample(subject={**SUBJECT, 'productName': 'Bright red blue white colour name'})
        self.assertEqual(result['target'], '#69876e')
        self.assertEqual(result['receipt']['quality']['targetSourcePixel']['rgba'][:3], [105, 135, 110])

    def test_dark_real_fabric_is_not_rejected_by_an_absolute_black_threshold(self):
        image = source();rgb = np.asarray(image).copy();rgb[15:90, 20:80] = [9, 10, 12]
        result = self.sample(image=Image.fromarray(rgb))
        self.assertEqual(result['target'], '#090a0c')

    def test_skin_and_background_samples_fail_without_invented_target(self):
        class Skin(Backend):
            def labels(self, image):
                c, h, meta = super().labels(image);h[25:35, 25:35] = 14;return c, h, meta
        vision = Vision()
        with self.assertRaises(tool.ReferenceSampleRejected) as error:self.sample(vision=vision, backend=Skin())
        r = error.exception.receipt
        self.assertFalse(r['sampleVerified']);self.assertEqual(len(r['attempts']), 2)
        self.assertEqual(len(vision.calls), 2)  # two plans; no invalid sample claimed as reviewed
        self.assertIn('fewer_than_three_clean_independent_source_samples', r['attempts'][0]['quality']['issues'])

    def test_transparent_pixels_cannot_be_sampled(self):
        image = source().convert('RGBA');a = np.asarray(image).copy();a[25:35, 25:35, 3] = 0
        with self.assertRaises(tool.ReferenceSampleRejected):self.sample(image=Image.fromarray(a))

    def test_source_extreme_shadow_patch_is_filtered_and_can_correct_once(self):
        image = source();rgb = np.asarray(image).copy();rgb[25:35, 25:35] = 2;image = Image.fromarray(rgb)
        fixed = plan();fixed['samples'][0]['point'] = [.4, .6]
        vision = Vision([plan(), fixed, review()])
        result = self.sample(image=image, vision=vision)
        self.assertEqual(len(result['receipt']['attempts']), 2)
        self.assertEqual(result['target'], '#69876e')
        self.assertIn('previousFailure', vision.calls[1]['context'])
        rejected = result['receipt']['attempts'][0]['quality']['rejectedSamples']
        self.assertEqual(rejected[0]['reason'], 'source_patch_is_extreme_fabric_shadow_or_highlight')

    def test_independent_review_rejection_is_not_overridden_by_numeric_success(self):
        vision = Vision([plan(), review(False), plan(), review(False)])
        with self.assertRaises(tool.ReferenceSampleRejected) as error:self.sample(vision=vision)
        r = error.exception.receipt
        self.assertTrue(r['attempts'][0]['quality']['accepted']);self.assertFalse(r['sampleVerified'])
        self.assertEqual(len(vision.calls), 4)

    def test_one_independent_review_correction_retains_old_rejection(self):
        vision = Vision([plan(), review(False), plan(), review()])
        result = self.sample(vision=vision);r = result['receipt']
        self.assertTrue(r['sampleVerified']);self.assertEqual(len(r['attempts']), 2)
        self.assertFalse(r['attempts'][0]['independentReview']['accepted'])
        first_path = Path(r['cacheManifestPath']).parent/'a1'/'review.json'
        self.assertFalse(json.loads(first_path.read_text('utf-8'))['result']['accepted'])

    def test_unknown_plan_is_not_reissued_same_identity(self):
        vision = Vision([RuntimeError('transport timeout')])
        with self.assertRaises(tool.ReferenceSampleRejected) as first:self.sample(vision=vision)
        with self.assertRaises(tool.ReferenceSampleRejected) as second:self.sample(vision=vision)
        self.assertEqual(first.exception.code, 'reference_sample_unknown')
        self.assertEqual(second.exception.code, 'reference_sample_unknown');self.assertEqual(len(vision.calls), 1)

    def test_unknown_plan_cannot_be_bypassed_by_subject_or_algorithm_change(self):
        vision = Vision([RuntimeError('transport timeout')])
        with self.assertRaises(tool.ReferenceSampleRejected) as first:self.sample(vision=vision)
        path = Path(first.exception.receipt['cacheManifestPath']);before = path.read_bytes();fresh = Vision()
        with patch.object(tool, 'ALGORITHM_VERSION', 'future-reference-algorithm'):
            with self.assertRaises(tool.ReferenceSampleRejected) as error:
                self.sample(vision=fresh, subject={**SUBJECT, 'target': 'changed saved identity'})
        self.assertEqual(error.exception.code, 'reference_sample_unknown')
        self.assertFalse(fresh.calls);self.assertEqual(path.read_bytes(), before)

    def test_unknown_review_is_not_reissued_or_relabelled_pass(self):
        vision = Vision([plan(), RuntimeError('review timeout')])
        with self.assertRaises(tool.ReferenceSampleRejected) as error:self.sample(vision=vision)
        self.assertEqual(error.exception.receipt['state'], 'unknown')
        with self.assertRaises(tool.ReferenceSampleRejected):self.sample(vision=vision)
        self.assertEqual(len(vision.calls), 2)

    def test_tampered_mask_is_not_used_or_reanalysed(self):
        vision = Vision();result = self.sample(vision=vision)
        Image.new('L', source().size).save(result['receipt']['maskPath'])
        with self.assertRaises(tool.ReferenceSampleRejected) as error:self.sample(vision=vision)
        self.assertEqual(error.exception.code, 'reference_sample_cache_mismatch');self.assertEqual(len(vision.calls), 2)

    def test_tampered_raw_source_samples_are_rejected(self):
        result = self.sample();path = Path(result['receipt']['samplePixelsPath'])
        with np.load(path, allow_pickle=False) as data:copy_data = {key: data[key].copy() for key in data.files}
        copy_data['rgba'][0, 0] += 1;np.savez_compressed(path, **copy_data)
        with self.assertRaises(tool.ReferenceSampleRejected):self.sample()

    def test_changed_source_subject_or_model_gets_new_identity(self):
        first = self.sample();second = self.sample(subject={**SUBJECT, 'target': 'another saved garment'})
        self.assertNotEqual(first['receipt']['cacheManifestPath'], second['receipt']['cacheManifestPath'])
        image = source();image.putpixel((50, 50), (106, 135, 110));third = self.sample(image=image)
        self.assertNotEqual(first['receipt']['sourcePixelSha256'], third['receipt']['sourcePixelSha256'])

    def test_oversized_geometry_duplicate_or_invalid_coordinates_cannot_pass(self):
        for mutate in ('radius', 'duplicate', 'bool'):
            p = plan()
            if mutate == 'radius':p['samples'][0]['radiusFraction'] = .5
            if mutate == 'duplicate':p['samples'][1]['point'] = p['samples'][0]['point']
            if mutate == 'bool':p['samples'][0]['point'] = [True, .3]
            with self.subTest(case=mutate):
                with tempfile.TemporaryDirectory() as root:
                    with self.assertRaises(tool.ReferenceSampleRejected):
                        tool.sample(source(), 'upper', subject=SUBJECT, vision=Vision([p, p]),
                            cache_root=root, vision_metadata=META, local_backend=Backend())

    def test_full_source_selection_role_is_not_accepted(self):
        with self.assertRaises(ValueError):self.sample(subject={**SUBJECT, 'role': 'source_garment'})

    def test_review_cannot_claim_pass_with_ownership_failure(self):
        bad = review();bad['allSamplesOnTarget'] = False
        with self.assertRaises(tool.ReferenceSampleRejected):self.sample(vision=Vision([plan(), bad, plan(), bad]))

    def test_windows_cache_names_are_short_and_full_identity_is_retained(self):
        result = self.sample();r = result['receipt'];path = Path(r['samplePixelsPath'])
        self.assertEqual(path.parent.name, 'a1');self.assertEqual(len(path.parent.parent.name), 32)
        self.assertEqual(path.parent.parent.parent.name, 'rs1')
        self.assertEqual(len(r['identitySha256']), 64)
        # A 140-character account root still keeps every output below MAX_PATH.
        self.assertLess(140+len(str(path.relative_to(self.temp.name)))+1, 260)


if __name__ == '__main__':unittest.main()
