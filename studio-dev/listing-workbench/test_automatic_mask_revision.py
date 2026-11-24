import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
import automatic_garment_selection as selection
import automatic_mask_revision as tool

SUBJECT = {'productName': 'fixture jacket', 'target': 'fixture jacket', 'role': 'source_garment'}
META = {'provider': 'isolated fixture', 'model': 'fixture', 'baseUrl': 'http://fixture.invalid'}


class Vision:
    def __init__(self, answer=None):self.calls = []; self.answer = answer
    def __call__(self, instruction, context, images):
        self.calls.append((instruction, context, images))
        if isinstance(self.answer, Exception):raise self.answer
        answer = self.answer or {'accepted': True, 'issues': [], 'warnings': [], 'misses': [], 'leaks': []}
        return {'result': copy.deepcopy(answer), 'receipt': {'actualFixtureId': len(self.calls)}}


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.garments = self.root/'garments'; self.run = self.garments/'g1'
        self.attempt = self.run/'attempt-01'; self.attempt.mkdir(parents=True)
        rgb = np.full((300, 300, 4), [30, 30, 30, 255], 'uint8'); rgb[20:80, 20:80] = [105, 135, 110, 255]
        self.source = Image.fromarray(rgb)
        labels = np.zeros((300, 300), 'uint8'); labels[20:80, 20:80] = 1
        human = labels * 4
        np.savez_compressed(self.run/'local-labels.npz', cloth=labels, human=human)
        self.source.save(self.run/'source.png')
        self.protection = Image.new('L', (300, 300)); self.protection.putpixel((45, 45), 255)
        self.points = {'foreground': [[30, 25], [70, 70]], 'background': [[5, 5]], 'sourceClothAnchors': [], 'sourceClothRidgePixels': []}
        base = selection._local_evidence(self.source, 'upper', labels, human, None)
        evidence, recovery = selection._recover_domain(self.source, base, self.points, self.protection)
        self.protection.save(self.attempt/'protection.png'); evidence['coarse'].save(self.attempt/'candidate-domain.png')
        full = np.zeros((300, 300), 'uint8'); full[20:80, 20:80] = 255
        previous = full.copy(); previous[30:75, 30:33] = 0
        candidate = full.copy(); candidate[30:75, 60:63] = 0; candidate[45, 45] = 0
        self.previous = Image.fromarray(previous); self.candidate = Image.fromarray(candidate)
        self.candidate.save(self.run/'mask.png')
        quality = selection._quality(self.candidate, self.source, self.points, self.protection, evidence)
        self.assertTrue(quality['accepted'])
        self.receipt = {'version': selection.VERSION, 'kind': 'upper', 'subject': SUBJECT,
            'state': 'accepted', 'accepted': True, 'verified': True,
            'sourceSize': [300, 300], 'sourcePixelSha256': selection._pixels(self.source, 'RGBA'),
            'sourceHashEncoding': 'rgba8_top_to_bottom', 'maskHashEncoding': 'l8_top_to_bottom',
            'maskPixelSha256': selection._pixels(self.candidate, 'L'),
            'maskPngSha256': selection._sha((self.run/'mask.png').read_bytes()),
            'maskPath': str(self.run/'mask.png'), 'runPath': str(self.run),
            'cacheManifestPath': str(self.run/'receipt.json'),
            'attempts': [{'number': 1, 'state': 'accepted', 'quality': quality, 'points': self.points,
                'compiled': {'protectionPaths': [{'kind': 'accessory', 'pointsPixels': [[45, 44], [45, 46]], 'widthPixels': 1, 'supportedPixels': 1}],
                    'candidateDomainRecovery': recovery, 'automaticSourceConstraints': {'protectedPixelSha256After': selection._pixels(self.protection, 'L')}}}]}
        (self.run/'receipt.json').write_text(json.dumps(self.receipt), 'utf-8')
        self.feedback = {'qualityId': 'fixture-real-server-lookup', 'passed': False, 'blocking': True,
            'nextAction': 'selection', 'protectedPartsPreserved': True,
            'binding': {'source': {'size': [300, 300], 'pixelSha256': selection._pixels(self.source, 'RGBA')},
                'mask': {'size': [300, 300], 'pixelSha256': selection._pixels(self.previous, 'L')}},
            'numeric': {'outsideChangedPixels': 0, 'alphaChangedPixels': 0},
            'visualReview': {'category': 'selection', 'blocking': True, 'selectionComplete': False,
                'protectedPartsPreserved': True, 'identityPreserved': True, 'materialPreserved': True, 'colourPlausible': True,
                'locations': [{'kind': 'miss', 'point': [31/299, 50/299], 'reason': 'Visible source cloth strip remains unchanged'}]}}
        self.vision = Vision()

    def call(self, **kwargs):
        args = dict(source=self.source, previous_mask=self.previous, candidate_mask=self.candidate,
            candidate_receipt=self.receipt, kind='upper', subject=SUBJECT, vision=self.vision,
            cache_root=self.root/'revision', garment_cache_root=self.garments,
            vision_metadata=META, feedback=self.feedback)
        args.update(kwargs); return tool.revise(**args)

    def test_union_preserves_previous_cloth_adds_miss_and_protection_has_priority(self):
        original = (self.run/'receipt.json').read_bytes()
        mask, receipt = self.call(); a = np.asarray(mask); p = np.asarray(self.previous)
        self.assertEqual(a[50, 61], 255)  # old correct hair-loop strip survives new candidate omission
        self.assertEqual(a[50, 31], 255)  # candidate fills old miss
        self.assertEqual(a[45, 45], 0)  # current source protection overrides old selection
        self.assertTrue(np.all(a[np.asarray(self.protection) == 0] >= p[np.asarray(self.protection) == 0]))
        self.assertEqual(receipt['revision']['previousSelectedReducedOutsideProtectionPixels'], 0)
        self.assertEqual(receipt['revision']['previousSelectedRemovedForProtectionPixels'], 1)
        self.assertTrue(receipt['accepted']); self.assertTrue(receipt['verified'])
        self.assertFalse(receipt['humanReviewed']); self.assertFalse(receipt['imageGenerationSubmitted'])
        self.assertEqual(len(self.vision.calls), 1)
        self.assertTrue(self.vision.calls[0][1]['priorFlagsDoNotCertifyMergedMask'])
        self.assertEqual(receipt['attempts'][-1]['compiled'], self.receipt['attempts'][-1]['compiled'])
        self.assertEqual((self.run/'receipt.json').read_bytes(), original)

    def test_new_independent_rejection_cannot_inherit_two_old_passes(self):
        self.vision.answer = {'accepted': False, 'issues': ['new merged boundary leak'], 'misses': [],
            'leaks': [{'point': [.45, .45], 'kind': 'accessory', 'evidence': 'actual overlay'}]}
        with self.assertRaises(tool.RevisionRejected) as error:self.call()
        self.assertFalse(error.exception.receipt['verified']); self.assertTrue(error.exception.receipt['quality']['accepted'])

    def test_favourable_new_review_cannot_waive_original_numeric_gate(self):
        # A previous spill far outside source-derived clothing must remain a failure.
        a = np.asarray(self.previous).copy(); a[:10, :10] = 255
        previous = Image.fromarray(a); feedback = copy.deepcopy(self.feedback)
        feedback['binding']['mask']['pixelSha256'] = selection._pixels(previous, 'L')
        with self.assertRaises(tool.RevisionRejected) as error:self.call(previous_mask=previous, feedback=feedback)
        self.assertFalse(error.exception.receipt['accepted'])
        self.assertIn('explicit_background_or_protection_selected', error.exception.receipt['quality']['issues'])
        self.assertEqual(len(self.vision.calls), 1)

    def test_mixed_leak_unprotected_or_nonmiss_feedback_never_unions(self):
        for change in ('mixed', 'leak', 'protected', 'colour', 'no_locations'):
            feedback = copy.deepcopy(self.feedback)
            if change == 'mixed':feedback['visualReview']['category'] = 'mixed'
            if change == 'leak':feedback['visualReview']['locations'][0]['kind'] = 'leak'
            if change == 'protected':feedback['protectedPartsPreserved'] = False
            if change == 'colour':feedback['visualReview']['colourPlausible'] = False
            if change == 'no_locations':feedback['visualReview']['locations'] = []
            with self.subTest(change=change), self.assertRaises(tool.RevisionRejected):self.call(feedback=feedback)
        self.assertFalse(self.vision.calls)

    def test_different_source_previous_mask_kind_or_subject_is_rejected(self):
        source = self.source.copy(); source.putpixel((0, 0), (1, 2, 3, 255))
        for kwargs in ({'source': source}, {'previous_mask': self.candidate}, {'kind': 'lower'},
                {'subject': {**SUBJECT, 'target': 'other product'}}):
            with self.subTest(kwargs=list(kwargs)), self.assertRaises(tool.RevisionRejected):self.call(**kwargs)
        self.assertFalse(self.vision.calls)

    def test_evidence_outside_account_root_and_modified_protection_are_rejected(self):
        with self.assertRaises(tool.RevisionRejected):self.call(garment_cache_root=self.root/'other-account')
        self.protection.putpixel((40, 40), 255); self.protection.save(self.attempt/'protection.png')
        with self.assertRaises(tool.RevisionRejected):self.call()
        self.assertFalse(self.vision.calls)

    def test_canonical_receipt_and_candidate_domain_tampering_are_rejected(self):
        modified = copy.deepcopy(self.receipt); modified['attempts'][0]['points']['foreground'][0] = [50, 50]
        with self.assertRaises(tool.RevisionRejected):self.call(candidate_receipt=modified)
        Image.new('L', (100, 100), 255).save(self.attempt/'candidate-domain.png')
        with self.assertRaises(tool.RevisionRejected):self.call()
        self.assertFalse(self.vision.calls)

    def test_cached_result_reuses_no_model_and_tampered_mask_cannot_reanalyse(self):
        mask, receipt = self.call(); _, cached = self.call()
        self.assertTrue(cached['cacheReused']); self.assertEqual(len(self.vision.calls), 1)
        Image.new('L', mask.size).save(receipt['maskPath'])
        with self.assertRaises(tool.RevisionRejected) as error:self.call()
        self.assertEqual(error.exception.code, 'automatic_revision_cache_mismatch')
        self.assertEqual(len(self.vision.calls), 1)

    def test_unknown_review_is_not_reissued_even_under_new_version_or_feedback(self):
        self.vision.answer = RuntimeError('network timeout')
        with self.assertRaises(tool.RevisionRejected) as first:self.call()
        path = Path(first.exception.receipt['cacheManifestPath']); original = path.read_bytes()
        with self.assertRaises(tool.RevisionRejected) as same:self.call()
        self.assertEqual(same.exception.code, 'automatic_revision_unknown')
        fresh = Vision(); feedback = copy.deepcopy(self.feedback); feedback['qualityId'] = 'new-task'
        with patch.object(tool, 'VERSION', 'new-mask-revision-version'):
            with self.assertRaises(tool.RevisionRejected) as changed:self.call(vision=fresh, feedback=feedback)
        self.assertEqual(changed.exception.code, 'automatic_revision_unknown'); self.assertFalse(fresh.calls)
        self.assertEqual(path.read_bytes(), original); self.assertEqual(len(self.vision.calls), 1)

    def test_known_new_review_rejection_is_cached_without_fishing_for_pass(self):
        self.vision.answer = {'accepted': False, 'issues': ['visible source miss'], 'misses': [], 'leaks': []}
        with self.assertRaises(tool.RevisionRejected):self.call()
        self.vision.answer = None
        with self.assertRaises(tool.RevisionRejected):self.call()
        self.assertEqual(len(self.vision.calls), 1)

    def test_pure_can_revise_rejects_malformed_or_mixed_without_io_or_authorization_claim(self):
        self.assertTrue(tool.can_revise(self.feedback))
        for change in (None, {}, {'visualReview': []}, {'numeric': []}):
            self.assertFalse(tool.can_revise(change))
        for point in ([True, .2], [2, .2], [float('nan'), .2]):
            feedback = copy.deepcopy(self.feedback); feedback['visualReview']['locations'][0]['point'] = point
            self.assertFalse(tool.can_revise(feedback))
        feedback = copy.deepcopy(self.feedback); feedback['numeric']['outsideChangedPixels'] = False
        self.assertFalse(tool.can_revise(feedback))
        self.assertFalse(self.vision.calls)

    def test_local_label_tampering_must_revalidate_domain_and_never_calls_model(self):
        labels = np.zeros((100, 100), 'uint8'); labels[20:45, 20:80] = 1
        np.savez_compressed(self.run/'local-labels.npz', cloth=labels, human=labels*4)
        with self.assertRaises(tool.RevisionRejected):self.call()
        self.assertFalse(self.vision.calls)

    def test_cached_review_artifact_tampering_does_not_start_fresh_model_call(self):
        _, receipt = self.call(); review = Path(receipt['runPath'])/'review.json'
        review.write_text('{}', 'utf-8')
        with self.assertRaises(tool.RevisionRejected) as error:self.call()
        self.assertEqual(error.exception.code, 'automatic_revision_cache_mismatch')
        self.assertEqual(len(self.vision.calls), 1)

    def test_pending_intent_blocks_same_and_changed_feedback_without_repayment(self):
        _, receipt = self.call(); manifest = Path(receipt['cacheManifestPath'])
        receipt.update(state='processing', accepted=False, verified=False); tool._persist(manifest, receipt)
        review = Path(receipt['runPath'])/'review.json'; intent = json.loads(review.read_text('utf-8'))
        intent['state'] = 'pending'; review.write_text(json.dumps(intent), 'utf-8')
        original = manifest.read_bytes()
        with self.assertRaises(tool.RevisionRejected) as same:self.call()
        self.assertEqual(same.exception.code, 'automatic_revision_unknown')
        feedback = copy.deepcopy(self.feedback); feedback['qualityId'] = 'another-server-id'
        with self.assertRaises(tool.RevisionRejected) as changed:self.call(feedback=feedback)
        self.assertEqual(changed.exception.code, 'automatic_revision_unknown')
        self.assertEqual(len(self.vision.calls), 1); self.assertEqual(manifest.read_bytes(), original)

    def test_candidate_domain_replay_keeps_original_base_and_protection_separate(self):
        original = selection._recover_domain
        observed = []
        def replay(source, evidence, points, protection):
            observed.append(True)
            self.assertFalse(evidence['protected'][45, 45])
            self.assertEqual(protection.getpixel((45, 45)), 255)
            return original(source, evidence, points, protection)
        with patch.object(selection, '_recover_domain', side_effect=replay):
            tool._load_evidence(self.source, self.candidate, self.receipt, self.garments, 'upper', SUBJECT)
        self.assertEqual(observed, [True]); self.assertFalse(self.vision.calls)

    def test_roi_blocks_remote_55_new_pixels_but_repairs_actual_nearby_miss(self):
        candidate = np.asarray(self.candidate).copy(); candidate[200:205, 200:211] = 255
        self.candidate = Image.fromarray(candidate); self.candidate.save(self.run/'mask.png')
        self.receipt['maskPixelSha256'] = selection._pixels(self.candidate, 'L')
        self.receipt['maskPngSha256'] = selection._sha((self.run/'mask.png').read_bytes())
        (self.run/'receipt.json').write_text(json.dumps(self.receipt), 'utf-8')
        mask, receipt = self.call(); a = np.asarray(mask)
        self.assertEqual(a[50, 31], 255); self.assertEqual(a[50, 61], 255)
        self.assertEqual(int(a[200:205, 200:211].sum()), 0)
        self.assertEqual(receipt['revision']['candidateNewPixelsOutsideROISuppressed'], 55)
        self.assertEqual(receipt['revision']['candidateAlphaIncreasePixelsOutsideROISuppressed'], 55)
        self.assertEqual(receipt['revision']['finalAlphaIncreasePixelsOutsideROI'], 0)
        suppressed = receipt['identity']['suppressedCandidateChanges']
        self.assertEqual(suppressed['newSelectedPixels'], 55)
        self.assertEqual(suppressed['bboxPixels'], [200, 200, 211, 205])
        self.assertEqual(suppressed, receipt['revision']['suppressedCandidateChanges'])
        self.assertIn('roi.png', receipt['artifactSha256'])
        scope = receipt['revision']['correctionScope']
        self.assertEqual(scope, receipt['identity']['correctionScope'])
        roi = Image.open(Path(receipt['runPath'])/'roi.png').convert('L')
        self.assertEqual(selection._pixels(roi, 'L'), scope['unionMaskPixelSha256'])

    def test_old_alpha_outside_roi_is_retained_except_current_source_protection(self):
        previous = np.asarray(self.previous).copy(); previous[250, 250] = 123; previous[245, 245] = 210
        self.previous = Image.fromarray(previous)
        self.feedback['binding']['mask']['pixelSha256'] = selection._pixels(self.previous, 'L')
        self.protection.putpixel((250, 250), 255); self.protection.save(self.attempt/'protection.png')
        self.receipt['attempts'][0]['compiled']['automaticSourceConstraints']['protectedPixelSha256After'] = selection._pixels(self.protection, 'L')
        (self.run/'receipt.json').write_text(json.dumps(self.receipt), 'utf-8')
        mask, receipt = self.call()
        self.assertEqual(mask.getpixel((245, 245)), 210)
        self.assertEqual(mask.getpixel((250, 250)), 0)
        self.assertEqual(receipt['revision']['outsideROIAlphaDecreaseForProtectionPixels'], 1)
        self.assertEqual(receipt['revision']['finalAlphaIncreasePixelsOutsideROI'], 0)
        self.assertEqual(receipt['revision']['previousSelectedReducedOutsideProtectionPixels'], 0)

    def test_invalid_excessive_or_total_area_over_budget_rois_are_rejected(self):
        for points, size in (([], (300, 300)), ([[.5, .5]]*7, (300, 300)),
                ([[0, 0], [1, 1]], (300, 300)), ([[.5, .5]], (100, 100)),
                ([[float('nan'), .5]], (300, 300)), ([[True, .5]], (300, 300))):
            feedback = copy.deepcopy(self.feedback)
            feedback['visualReview']['locations'] = [{'kind': 'miss', 'point': point, 'reason': 'fixture'} for point in points]
            with self.subTest(points=points), self.assertRaises(tool.RevisionRejected):tool._revision_rois(size, feedback)
        allowed, scope = tool._revision_rois((1280, 1280), self.feedback)
        self.assertLessEqual(scope['unionImageFraction'], .35)
        self.assertEqual(scope['regions'][0]['bboxPixels'][2]-scope['regions'][0]['bboxPixels'][0], 256)
        self.assertEqual(allowed.shape, (1280, 1280)); self.assertFalse(self.vision.calls)

    def test_roi_policy_change_does_not_reuse_pass_and_keeps_old_record(self):
        _, first = self.call(); path = Path(first['cacheManifestPath']); original = path.read_bytes()
        with patch.dict(tool.ROI_POLICY, {'maximumSidePixels': 192}):
            _, second = self.call()
        self.assertNotEqual(first['identitySha256'], second['identitySha256'])
        self.assertEqual(len(self.vision.calls), 2); self.assertEqual(path.read_bytes(), original)

    def test_unknown_cannot_be_bypassed_by_roi_policy_change(self):
        self.vision.answer = RuntimeError('network timeout')
        with self.assertRaises(tool.RevisionRejected):self.call()
        with patch.dict(tool.ROI_POLICY, {'maximumSidePixels': 192}):
            with self.assertRaises(tool.RevisionRejected) as changed:self.call()
        self.assertEqual(changed.exception.code, 'automatic_revision_unknown')
        self.assertEqual(len(self.vision.calls), 1)

    def test_source_transparency_clears_previous_alpha_outside_roi_globally(self):
        source = np.asarray(self.source).copy(); source[250, 250, 3] = 0
        self.source = Image.fromarray(source); self.source.save(self.run/'source.png')
        previous = np.asarray(self.previous).copy(); previous[250, 250] = 87
        self.previous = Image.fromarray(previous)
        source_sha = selection._pixels(self.source, 'RGBA')
        self.receipt['sourcePixelSha256'] = source_sha
        self.feedback['binding']['source']['pixelSha256'] = source_sha
        self.feedback['binding']['mask']['pixelSha256'] = selection._pixels(self.previous, 'L')
        (self.run/'receipt.json').write_text(json.dumps(self.receipt), 'utf-8')
        mask, receipt = self.call()
        self.assertEqual(mask.getpixel((250, 250)), 0)
        self.assertEqual(receipt['revision']['outsideROIAlphaDecreaseForProtectionPixels'], 1)
        self.assertEqual(receipt['revision']['finalAlphaIncreasePixelsOutsideROI'], 0)


if __name__ == '__main__':unittest.main()
