import copy
import hashlib
import tempfile
import unittest
import json
import sys
import types
import threading
from unittest.mock import patch
from pathlib import Path
import numpy as np
from PIL import Image
import automatic_garment_selection as tool


class Backend:
    def __init__(self, masks=None):
        self.masks = masks
        self.selections = 0

    def labels(self, source):
        cloth = np.zeros((100, 100), 'uint8');cloth[15:90, 20:80] = 1
        human = np.zeros((100, 100), 'uint8');human[15:90, 20:80] = 4
        return cloth, human, {'clothing': 'isolated-cloth-fixture', 'human': 'isolated-human-fixture'}

    def select(self, source, coarse, protected, points, cache):
        self.selections += 1
        if self.masks:
            value = self.masks[min(self.selections - 1, len(self.masks) - 1)].copy()
        else:
            value = np.asarray(coarse).copy()
            value[np.asarray(protected) > 0] = 0
        return Image.fromarray(value), {'model': 'isolated-selection-fixture', 'points': points}

    def matte(self, source, mask, protected, points):
        return mask.copy(), {'method': 'isolated-matte-fixture'}


def source():
    rgb = np.full((100, 100, 3), 30, 'uint8');rgb[15:90, 20:80] = [213, 203, 201]
    return Image.fromarray(rgb)


def plan():
    return {'foreground': [
        {'point': [.35, .4], 'part': 'left garment', 'evidence': 'visible photographed cloth'},
        {'point': [.65, .5], 'part': 'right garment', 'evidence': 'visible photographed cloth'}],
        'background': [{'point': [.05, .05], 'kind': 'background', 'evidence': 'outside garment'}],
        'protections': [], 'visibleParts': ['upper garment'], 'limitations': []}


def review(accepted=True):
    return {'accepted': accepted, 'issues': [] if accepted else ['missing left sleeve'],
        'misses': [] if accepted else [{'point': [.3, .5], 'part': 'sleeve', 'evidence': 'visible sleeve remains natural'}],
        'leaks': []}


def inner_garment_fixture():
    image = source();rgb = np.asarray(image).copy()
    rgb[20:85, 45:55] = [190, 185, 180]
    image = Image.fromarray(rgb)
    proposal = plan()
    proposal['background'] += [{'point': [.5, v], 'kind': 'other_garment',
        'evidence': 'separate inner garment, visible source edge'} for v in (.3, .7)]
    checked = {'accepted': False, 'issues': ['separate inner garment selected'], 'misses': [],
        'leaks': [{'point': [.5, .5], 'kind': 'other_garment',
            'evidence': 'inner garment is visible between target edges'}]}
    return image, proposal, checked


def thin_fabric_fixture(kind='upper', human_class=4):
    rgb = np.full((100, 100, 3), 30, 'uint8')
    rgb[10:90, 50:85] = [210, 195, 195]
    rgb[20:80, 30:38] = [150, 130, 130]
    cloth = np.zeros((100, 100), 'uint8');human = np.zeros_like(cloth)
    for box in ((10, 90, 50, 85), (20, 80, 30, 38)):
        y0, y1, x0, x1 = box;cloth[y0:y1, x0:x1] = tool.TARGET[kind];human[y0:y1, x0:x1] = human_class
    points = {'foreground': [[65, 40], [70, 70]], 'background': [[5, 5]]}
    return Image.fromarray(rgb), cloth, human, points


def background_gap_fixture():
    rgb=np.full((100,100,3),[225,226,220],'uint8')
    rgb[15:90,20:40]=[120,70,40];rgb[15:90,60:80]=[120,70,40]
    cloth=np.zeros((100,100),'uint8');cloth[15:90,20:80]=2
    human=np.zeros((100,100),'uint8');human[15:90,20:40]=6;human[15:90,60:80]=6
    p={'foreground':[{'point':point,'part':'visible trouser leg','evidence':'source brown cloth'}
        for point in ([.3,.3],[.7,.7])],
        'background':[{'point':point,'kind':kind,'evidence':'source visible opening or external backdrop'}
            for point,kind in (([.5,.5],'gap'),([.05,.5],'background'),([.95,.5],'background'))],
        'protections':[],'visibleParts':['two legs'],'limitations':[]}
    r={'accepted':False,'issues':['background gap selected'],'misses':[],
        'leaks':[{'point':[.5,.6],'kind':'gap','evidence':'source backdrop visible between legs'}]}
    return Image.fromarray(rgb),cloth,human,p,r


def illuminated_gap_fixture():
    image,cloth,human,p,r=background_gap_fixture();rgb=np.asarray(image).copy()
    rgb[cloth==0]=[140,141,135]  # Shaded exterior, same background chroma.
    r['leaks'][0]['point']=[.5,.5]
    return Image.fromarray(rgb),cloth,human,p,r


class Vision:
    def __init__(self, answers=None):
        self.answers = answers
        self.calls = []

    def __call__(self, instruction, context, images):
        self.calls.append({'instruction': instruction, 'context': context, 'images': images})
        if self.answers is not None:
            answer = self.answers[len(self.calls) - 1]
        else:
            answer = review() if instruction.startswith('Independently') else plan()
        if isinstance(answer, Exception):raise answer
        return {'result': copy.deepcopy(answer), 'receipt': {'provider': 'isolated vision', 'id': len(self.calls)}}


class AutomaticSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def prepare(self, image=None, vision=None, backend=None, **kwargs):
        return tool.prepare(image or source(), 'upper', vision=vision or Vision(),
            cache_root=self.temp.name, local_backend=backend or Backend(),
            vision_metadata={'provider': 'isolated model', 'model': 'fixture'}, **kwargs)

    def test_acceptance_binds_actual_source_mask_and_independent_review(self):
        model = Vision();mask, receipt = self.prepare(vision=model)
        self.assertTrue(receipt['verified']);self.assertTrue(receipt['accepted'])
        self.assertFalse(receipt['humanReviewed']);self.assertFalse(receipt['imageGenerationSubmitted'])
        self.assertEqual(receipt['maskPixelSha256'], hashlib.sha256(mask.tobytes()).hexdigest())
        self.assertEqual(receipt['sourcePixelSha256'], hashlib.sha256(source().convert('RGBA').tobytes()).hexdigest())
        self.assertTrue(receipt['independentReview']['accepted'])
        self.assertEqual(len(model.calls), 2)
        self.assertIn('"foreground"', model.calls[0]['instruction'])
        self.assertEqual(model.calls[1]['images'][0].size, source().size)

    def test_category_disagreement_recovers_all_anchored_dark_panels_not_other_clothes(self):
        rgb = np.full((100, 100, 3), 220, 'uint8')
        rgb[15:90, 20:80] = 22;rgb[15:55, 20:80] = 48
        rgb[92:98, 20:80] = 22  # Same-colour trousers must not become jacket.
        image = Image.fromarray(rgb)
        cloth = np.zeros((100, 100), 'uint8');cloth[15:90, 20:80] = 3
        cloth[65:90, 70:80] = 1;cloth[92:98, 20:80] = 2
        human = np.zeros((100, 100), 'uint8');human[15:90, 20:80] = 4
        human[92:98, 20:80] = 6;human[30:35, 25:30] = 14
        explicit = Image.new('L', image.size);explicit.paste(255, (43, 20, 46, 75))
        e = tool._local_evidence(image, 'upper', cloth, human, explicit)
        p = plan();p['foreground'] += [
            {'point': [.35, .75], 'part': 'lower left', 'evidence': 'visible dark fabric'},
            {'point': [.75, .75], 'part': 'lower right', 'evidence': 'visible dark fabric'}]
        points, protection, audit = tool._compile_plan(p, image.size, e, explicit)
        before = protection.tobytes();effective, recovery = tool._recover_domain(image, e, points, protection)
        selected = np.asarray(effective['coarse']) > 0
        expected = (human == 4) & (np.asarray(protection) == 0)
        self.assertTrue(selected[expected].all())
        self.assertFalse(selected[92:98].any())
        self.assertEqual(protection.tobytes(), before)
        self.assertFalse(selected[np.asarray(protection) > 0].any())
        self.assertGreater(recovery['recoveredPixels'], 3500)
        self.assertEqual(len(points['foreground']), 4)
        self.assertFalse(recovery['certifiesSelection'])

    def test_recovered_domain_does_not_waive_source_coverage_gate(self):
        image = source();cloth, human, _ = Backend().labels(image)
        cloth[15:90, 20:70] = 3
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        points, protection, _ = tool._compile_plan(plan(), image.size, e, None)
        effective, _ = tool._recover_domain(image, e, points, protection)
        quality = tool._quality(e['coarse'], image, points, protection, effective)
        self.assertFalse(quality['accepted'])
        self.assertIn('independent_cloth_core_not_covered', quality['issues'])

    def test_same_colour_unanchored_garment_component_is_not_recovered(self):
        image = source();cloth, human, _ = Backend().labels(image)
        cloth[60:80, 20:80] = 0;human[60:80, 20:80] = 0
        cloth[80:90, 20:80] = 3
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        points, protection, _ = tool._compile_plan(plan(), image.size, e, None)
        effective, recovery = tool._recover_domain(image, e, points, protection)
        self.assertFalse(np.asarray(effective['coarse'])[80:90].any())

    def test_subject_is_bound_to_cache_and_both_actual_vision_contexts(self):
        model = Vision();subject = {'productName': 'saved jacket', 'role': 'source_garment', 'target': 'saved jacket'}
        _, first = self.prepare(vision=model, subject=subject)
        self.assertEqual(first['subject'], subject)
        self.assertEqual(first['algorithmVersion'], tool.ALGORITHM_VERSION)
        self.assertEqual(model.calls[0]['context']['subject'], subject)
        self.assertEqual(model.calls[1]['context']['subject'], subject)
        _, second = self.prepare(vision=model, subject={**subject, 'role': 'target_colour_reference'})
        self.assertNotEqual(first['cacheManifestPath'], second['cacheManifestPath'])
        with self.assertRaises(ValueError):self.prepare(subject={'brief': 'arbitrary requirements'})

    def test_algorithm_upgrade_does_not_reuse_old_accepted_cache(self):
        model = Vision()
        with patch.object(tool, 'ALGORITHM_VERSION', 'legacy-domain'):
            _, old = self.prepare(vision=model)
        old_bytes = Path(old['cacheManifestPath']).read_bytes()
        _, current = self.prepare(vision=model)
        self.assertEqual(len(model.calls), 4)
        self.assertNotEqual(old['cacheManifestPath'], current['cacheManifestPath'])
        self.assertEqual(Path(old['cacheManifestPath']).read_bytes(), old_bytes)

    def test_algorithm_subject_upgrade_cannot_bypass_prior_unknown_vision(self):
        model = Vision([RuntimeError('transport timeout')])
        with patch.object(tool, 'ALGORITHM_VERSION', 'legacy-domain'):
            with self.assertRaises(tool.SelectionRejected) as error:self.prepare(vision=model)
        old_manifest = Path(error.exception.receipt['cacheManifestPath']);before = old_manifest.read_bytes()
        new_model = Vision()
        with self.assertRaises(tool.SelectionRejected) as blocked:
            self.prepare(vision=new_model, subject={'role': 'target_colour_reference'})
        self.assertEqual(blocked.exception.code, 'automatic_selection_unknown')
        self.assertEqual(blocked.exception.receipt['blockingReceiptPath'], str(old_manifest))
        self.assertFalse(new_model.calls)
        self.assertEqual(old_manifest.read_bytes(), before)

    def test_rejected_legacy_manifest_with_pending_plan_also_blocks_upgrade(self):
        model = Vision()
        with patch.object(tool, 'ALGORITHM_VERSION', 'legacy-domain'):
            _, old = self.prepare(vision=model)
        path = Path(old['cacheManifestPath']);stored = json.loads(path.read_text('utf-8'))
        stored.update(state='rejected', accepted=False, verified=False);tool._write(path, stored)
        plan_path = path.parent / 'attempt-01' / 'plan.json'
        pending = json.loads(plan_path.read_text('utf-8'));pending['state'] = 'pending';tool._write(plan_path, pending)
        fresh = Vision()
        with self.assertRaises(tool.SelectionRejected):self.prepare(vision=fresh)
        self.assertFalse(fresh.calls)

    def test_same_label_inner_garment_requires_plan_review_and_source_boundary(self):
        image, proposal, checked = inner_garment_fixture()
        cloth, human, _ = Backend().labels(image)
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        _, _, old = tool._compile_plan(proposal, image.size, e, None)
        self.assertEqual(len(old['rejectedPoints']), 2)
        instance, audit = tool._instance_protection(image, proposal, e, checked)
        self.assertTrue(audit['acceptedRegions'])
        self.assertTrue((np.asarray(instance)[25:80, 48:52] > 0).all())
        points, protection, compiled = tool._compile_plan(proposal, image.size, e, None, instance)
        self.assertFalse(compiled['rejectedPoints'])
        self.assertEqual(len(points['background']), 3)
        self.assertTrue(all(protection.getpixel(tuple(point)) == 0 for point in points['foreground']))
        self.assertFalse(audit['certifiesSelection'])

    def test_inner_instance_colour_boundary_without_independent_review_is_not_used(self):
        image, proposal, _ = inner_garment_fixture();cloth, human, _ = Backend().labels(image)
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        instance, audit = tool._instance_protection(image, proposal, e, None)
        self.assertFalse(np.asarray(instance).any())
        self.assertEqual(audit['reason'], 'no_preceding_independent_rejected_review')

    def test_uniform_same_garment_cannot_be_cut_by_two_visual_claims(self):
        image = source();cloth, human, _ = Backend().labels(image)
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        proposal = plan();proposal['background'] += [
            {'point': [.5, v], 'kind': 'other_garment', 'evidence': 'incorrect uniform-cloth claim'}
            for v in (.25, .35)]
        checked = {'accepted': False, 'issues': ['claimed inner layer'], 'misses': [],
            'leaks': [{'point': [.5, .3], 'kind': 'other_garment', 'evidence': 'incorrect claim'}]}
        instance, audit = tool._instance_protection(image, proposal, e, checked)
        self.assertFalse(np.asarray(instance).any())
        self.assertTrue(any(row['reason'] == 'no_independent_source_colour_or_texture_boundary'
            for row in audit['rejectedRegions']))
        _, _, compiled = tool._compile_plan(proposal, image.size, e, None, instance)
        self.assertEqual(len(compiled['rejectedPoints']), 2)

    def test_review_other_component_cannot_certify_inner_garment_region(self):
        image, proposal, checked = inner_garment_fixture();cloth, human, _ = Backend().labels(image)
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        checked['leaks'][0]['point'] = [.05, .05]
        instance, audit = tool._instance_protection(image, proposal, e, checked)
        self.assertFalse(np.asarray(instance).any())
        self.assertTrue(all(not row['independentReviewSeeds'] for row in audit['rejectedRegions']))

    def test_only_one_plan_point_cannot_create_whole_other_garment_protection(self):
        image, proposal, checked = inner_garment_fixture();cloth, human, _ = Backend().labels(image)
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        proposal['background'].pop()
        instance, audit = tool._instance_protection(image, proposal, e, checked)
        self.assertFalse(np.asarray(instance).any())
        self.assertEqual(audit['reason'], 'insufficient_current_plan_instance_constraints')

    def test_automatic_second_attempt_separates_instance_and_still_reviews_actual_result(self):
        image, proposal, checked = inner_garment_fixture()
        model = Vision([proposal, checked, proposal, review()])
        mask, receipt = self.prepare(image=image, vision=model)
        self.assertTrue(receipt['accepted'])
        self.assertEqual(len(model.calls), 4)
        self.assertFalse(receipt['attempts'][0]['independentReview']['accepted'])
        first = receipt['attempts'][0]['compiled']['instanceSeparation']
        second = receipt['attempts'][1]['compiled']['instanceSeparation']
        self.assertEqual(first['protectedPixels'], 0)
        self.assertGreater(second['protectedPixels'], 500)
        self.assertEqual(mask.getpixel((50, 50)), 0)
        self.assertEqual(receipt['quality']['protectedChangedPixels'], 0)
        self.assertTrue(receipt['independentReview']['accepted'])

    def test_caller_initial_feedback_is_not_an_independent_instance_review(self):
        image, proposal, checked = inner_garment_fixture()
        model = Vision([proposal, checked, proposal, review()])
        _, receipt = self.prepare(image=image, vision=model,
            initial_feedback={'independentReview': checked})
        self.assertEqual(receipt['attempts'][0]['compiled']['instanceSeparation']['protectedPixels'], 0)
        self.assertGreater(receipt['attempts'][1]['compiled']['instanceSeparation']['protectedPixels'], 0)

    def test_human_dress_alias_requires_target_clothing_parser_corroboration(self):
        image = source();cloth, human, _ = Backend().labels(image);human[15:90, 20:80] = 7
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        self.assertEqual(e['semanticGarmentClasses'], [4, 7])
        points, protection, _ = tool._compile_plan(plan(), image.size, e, None)
        effective, audit = tool._recover_domain(image, e, points, protection)
        self.assertEqual(audit['semanticGarmentClasses'], [4, 7])
        # Isolated parser errors on a different class cannot alias that class.
        human[15:90, 20:80] = 6
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        self.assertEqual(e['semanticGarmentClasses'], [4])

    def test_thin_cloth_guidance_uses_continuous_source_ridges_not_point_islands(self):
        image, cloth, human, points = thin_fabric_fixture()
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        protection = Image.fromarray(e['protected'].astype('uint8')*255)
        anchors, audit = tool._source_cloth_anchors(image, e, points, protection)
        self.assertGreater(audit['ridgePixelCount'], len(anchors))
        points.update(sourceClothAnchors=anchors, sourceClothRidgePixels=audit['sourceClothRidgePixels'])
        refined = tool._refine_source_cloth(image, e['coarse'], points, protection)
        a = np.asarray(refined)
        self.assertTrue((a[25:75, 33:35] == 255).all())
        self.assertFalse(a[25:75, 40:45].any())
        self.assertTrue(audit['protectionPreserved'])
        self.assertFalse(audit['automaticSeedsExpandBeyondValidatedPixels'])

    def test_thin_guidance_never_erases_explicit_protections(self):
        image, cloth, human, points = thin_fabric_fixture()
        explicit = Image.new('L', image.size);explicit.paste(255, (30, 42, 38, 55))
        e = tool._local_evidence(image, 'upper', cloth, human, explicit)
        protection = Image.fromarray(e['protected'].astype('uint8')*255);before = protection.tobytes()
        anchors, audit = tool._source_cloth_anchors(image, e, points, protection)
        self.assertEqual(before, protection.tobytes())
        self.assertTrue(all(not protection.getpixel(tuple(p)) for p in audit['sourceClothRidgePixels']))
        points.update(sourceClothAnchors=anchors, sourceClothRidgePixels=audit['sourceClothRidgePixels'])
        mask = tool._refine_source_cloth(image, e['coarse'], points, protection)
        self.assertFalse(np.asarray(mask)[42:55, 30:38].any())

    def test_thin_bridge_requires_cloth_requested_kind_and_human_actual_garment(self):
        image, cloth, human, points = thin_fabric_fixture(kind='lower', human_class=4)
        e = tool._local_evidence(image, 'lower', cloth, human, None)
        protection = Image.fromarray(e['protected'].astype('uint8')*255)
        _, audit = tool._source_cloth_anchors(image, e, points, protection)
        self.assertTrue(audit['sourceClothRidgePixels'])
        self.assertTrue(all(cloth[y, x] == 2 and human[y, x] == 4 for x, y in audit['sourceClothRidgePixels']))
        human[20:80, 30:38] = 14  # A skin/arm label never bridges as cloth.
        e = tool._local_evidence(image, 'lower', cloth, human, None)
        _, blocked = tool._source_cloth_anchors(image, e, points, protection)
        self.assertFalse(any(30 <= x < 38 for x, y in blocked['sourceClothRidgePixels']))

    def test_thin_guidance_is_a_new_required_gate_not_a_coverage_waiver(self):
        image, cloth, human, points = thin_fabric_fixture()
        e = tool._local_evidence(image, 'upper', cloth, human, None)
        protection = Image.fromarray(e['protected'].astype('uint8')*255)
        anchors, audit = tool._source_cloth_anchors(image, e, points, protection)
        points.update(sourceClothAnchors=anchors, sourceClothRidgePixels=audit['sourceClothRidgePixels'])
        old = np.asarray(e['coarse']).copy();old[20:80, 30:38] = 0
        result = tool._quality(Image.fromarray(old), image, points, protection, e)
        self.assertGreater(result['semanticCoreCoverage'], .88)
        self.assertFalse(result['accepted'])
        self.assertIn('source_supported_thin_cloth_ridge_missing', result['issues'])

    def test_optional_third_attempt_keeps_both_real_failed_reviews(self):
        model = Vision([plan(), review(False), plan(), review(False), plan(), review()])
        _, receipt = self.prepare(vision=model, max_attempts=3)
        self.assertTrue(receipt['verified']);self.assertEqual(len(receipt['attempts']), 3)
        self.assertEqual(receipt['maxAttempts'], 3)
        self.assertFalse(receipt['attempts'][0]['independentReview']['accepted'])
        self.assertFalse(receipt['attempts'][1]['independentReview']['accepted'])
        self.assertEqual(len(model.calls), 6)
        for i in (1, 2):
            path = Path(receipt['runPath'])/f'attempt-{i:02}'/'review.json'
            self.assertFalse(json.loads(path.read_text('utf-8'))['result']['accepted'])

    def test_attempt_budget_is_bound_to_identity_and_cannot_be_unlimited(self):
        model = Vision();_, a = self.prepare(vision=model)
        _, b = self.prepare(vision=model, max_attempts=3)
        self.assertEqual(a['maxAttempts'], 2)
        self.assertNotEqual(a['cacheManifestPath'], b['cacheManifestPath'])
        for invalid in (0, 4, True, 2.0):
            with self.assertRaises(ValueError):self.prepare(max_attempts=invalid)

    def test_larger_attempt_budget_cannot_bypass_unknown_prior_paid_call(self):
        model = Vision([RuntimeError('actual request timeout')])
        with self.assertRaises(tool.SelectionRejected):self.prepare(vision=model)
        fresh = Vision()
        with self.assertRaises(tool.SelectionRejected) as error:self.prepare(vision=fresh, max_attempts=3)
        self.assertEqual(error.exception.code, 'automatic_selection_unknown')
        self.assertFalse(fresh.calls)

    def test_confirmed_source_background_carves_whole_gap_without_touching_true_fabric(self):
        image,cloth,human,p,r=background_gap_fixture()
        e=tool._local_evidence(image,'lower',cloth,human,None)
        mask,audit=tool._background_protection(image,p,e,r)
        a=np.asarray(mask)>0
        self.assertTrue(a[20:85,45:55].all())
        self.assertFalse(a[20:85,25:35].any());self.assertFalse(a[20:85,65:75].any())
        self.assertTrue(audit['acceptedRegions']);self.assertFalse(audit['certifiesSelection'])
        self.assertTrue(any(row['connectedToImageBorder'] for row in audit['acceptedRegions']))

    def test_background_colour_without_independent_review_does_not_delete_garment_mask(self):
        image,cloth,human,p,_=background_gap_fixture();e=tool._local_evidence(image,'lower',cloth,human,None)
        mask,audit=tool._background_protection(image,p,e,None)
        self.assertFalse(np.asarray(mask).any())
        self.assertEqual(audit['reason'],'no_preceding_independent_rejected_review')

    def test_background_carve_cannot_use_same_colour_fabric_or_double_garment_labels(self):
        image,cloth,human,p,r=background_gap_fixture()
        rgb=np.asarray(image).copy();rgb[:]=[120,70,40]
        e=tool._local_evidence(Image.fromarray(rgb),'lower',cloth,human,None)
        mask,_=tool._background_protection(Image.fromarray(rgb),p,e,r)
        self.assertFalse(np.asarray(mask).any())
        human[15:90,40:60]=6
        e=tool._local_evidence(image,'lower',cloth,human,None)
        mask,_=tool._background_protection(image,p,e,r)
        self.assertFalse(np.asarray(mask)[20:85,45:55].any())

    def test_human_cloth_supported_fringe_cannot_be_punched_by_mistaken_gap_point(self):
        image,cloth,human,points=thin_fabric_fixture(kind='lower',human_class=6)
        # A local cloth-parser omission cannot make this brown strip background.
        cloth[20:80,30:38]=0
        rgb=np.asarray(image).copy();rgb[50:70,60:80]=[150,130,130];image=Image.fromarray(rgb)
        p={'foreground':[{'point':[.65,.4],'part':'leg','evidence':'visible cloth'}],
            'background':[{'point':[.05,.05],'kind':'background','evidence':'external backdrop'},
                {'point':[.34,.5],'kind':'gap','evidence':'incorrect model gap coordinate'}],
            'protections':[]}
        e=tool._local_evidence(image,'lower',cloth,human,None)
        compiled,protection,audit=tool._compile_plan(p,image.size,e,None)
        self.assertEqual(len(compiled['background']),1)
        self.assertEqual(audit['rejectedPoints'][0]['reason'],'point_conflicts_with_visible_fabric')
        self.assertEqual(protection.getpixel((34,50)),0)

    def test_confirmed_background_does_not_erase_explicit_protection(self):
        image,cloth,human,p,r=background_gap_fixture();explicit=Image.new('L',image.size)
        explicit.paste(255,(25,20,28,80));e=tool._local_evidence(image,'lower',cloth,human,explicit)
        bg,audit=tool._background_protection(image,p,e,r)
        _,protection,_=tool._compile_plan(p,image.size,e,explicit,background_protection=bg)
        self.assertTrue((np.asarray(protection)[20:80,25:28]>0).all())

    def test_source_refined_strap_releases_cloth_margin_and_preserves_occluder_highlight(self):
        image=source();rgb=np.asarray(image).copy();rgb[20:85,55:59]=[150,180,100]
        rgb[45:48,55:59]=[213,203,201];image=Image.fromarray(rgb)
        cloth,human,_=Backend().labels(image);e=tool._local_evidence(image,'upper',cloth,human,None)
        p=plan();p['background'].append({'point':[.57,.4],'kind':'accessory','evidence':'visible green strap'})
        p['protections']=[{'kind':'accessory','path':[[.57,.25],[.57,.70]],'widthFraction':.04,
            'evidence':'visible narrow accessory over cloth'}]
        _,protection,audit=tool._compile_plan(p,image.size,e,None)
        refinement=audit['protectionPaths'][0]['sourceRefinement']
        self.assertEqual(refinement['method'],'source_pixel_occluder_grabcut')
        self.assertGreater(refinement['releasedSourceClothPixels'],0)
        self.assertEqual(protection.getpixel((54,40)),0)
        self.assertTrue((np.asarray(protection)[45:48,55:59]>0).all())
        self.assertGreater(protection.getpixel((56,40)),0)

    def test_strap_refinement_cannot_clear_original_explicit_or_skin_protection(self):
        image=source();rgb=np.asarray(image).copy();rgb[20:85,55:59]=[150,180,100]
        rgb[35:45,53:55]=[200,140,100];image=Image.fromarray(rgb)
        cloth,human,_=Backend().labels(image);human[35:45,53:55]=14
        explicit=Image.new('L',image.size);explicit.putpixel((54,50),255)
        e=tool._local_evidence(image,'upper',cloth,human,explicit);before=e['protected'].copy()
        p=plan();p['background'].append({'point':[.57,.4],'kind':'accessory','evidence':'visible green strap'})
        p['protections']=[{'kind':'accessory','path':[[.57,.25],[.57,.70]],'widthFraction':.04,
            'evidence':'visible narrow accessory'}]
        _,protection,_=tool._compile_plan(p,image.size,e,explicit)
        self.assertTrue((np.asarray(protection)[before]>0).all())
        self.assertEqual(protection.getpixel((54,50)),255)

    def test_confirmed_gap_proof_is_retained_when_next_review_finds_different_issue(self):
        image,cloth,human,p,r=background_gap_fixture()
        class GapBackend(Backend):
            def labels(self,image):return cloth.copy(),human.copy(),{'model':'isolated-gap-labels'}
        second={'accepted':False,'issues':['a different visible edge needs another review'],
            'misses':[{'point':[.3,.7],'part':'leg edge','evidence':'independent observation'}],'leaks':[]}
        model=Vision([p,r,p,second,p,review()])
        mask,receipt=tool.prepare(image,'lower',vision=model,cache_root=self.temp.name,
            local_backend=GapBackend(),vision_metadata={'provider':'isolated'},max_attempts=3)
        self.assertEqual(mask.getpixel((50,60)),0)
        attempt2=receipt['attempts'][1]['compiled']['sourceBackgroundSeparation']
        attempt3=receipt['attempts'][2]['compiled']['sourceBackgroundSeparation']
        self.assertGreater(attempt2['protectedPixels'],0)
        self.assertGreater(attempt3['carriedSourceBackgroundPixels'],0)
        self.assertTrue(attempt3['retainedProofSha256'])

    def test_current_foreground_cannot_be_silently_removed_by_prior_gap_proof(self):
        image,cloth,human,p,r=background_gap_fixture();e=tool._local_evidence(image,'lower',cloth,human,None)
        bg,_=tool._background_protection(image,p,e,r)
        p['foreground'].append({'point':[.5,.5],'part':'claimed fabric','evidence':'contradictory later claim'})
        points,protection,compiled=tool._compile_plan(p,image.size,e,None,background_protection=bg)
        # A single classifier's false foreground on source background is now
        # explicitly rejected, rather than poisoning the true-fabric palette.
        self.assertEqual(len(points['foreground']),2)
        self.assertTrue(any(row['type']=='foreground' and row['pointPixels']==[50,50]
            for row in compiled['rejectedPoints']))
        self.assertGreater(protection.getpixel((50,50)),0)

    def test_source_background_carve_uses_observed_palette_not_white_threshold(self):
        image,cloth,human,p,r=background_gap_fixture();rgb=np.asarray(image).copy()
        rgb[human==0]=[40,110,180];image=Image.fromarray(rgb)
        e=tool._local_evidence(image,'lower',cloth,human,None)
        bg,audit=tool._background_protection(image,p,e,r)
        self.assertTrue((np.asarray(bg)[20:85,45:55]>0).all())
        self.assertTrue(audit['acceptedRegions'])
        self.assertFalse(np.asarray(bg)[20:85,25:35].any())

    def test_pale_or_palette_contaminated_occluder_does_not_require_global_colour_distance(self):
        image=source();rgb=np.asarray(image).copy()
        rgb[20:45,22:45]=[150,180,100]  # A locally mislabelled accessory pollutes the colour clusters.
        rgb[20:85,55:59]=[150,180,100];image=Image.fromarray(rgb)
        cloth,human,_=Backend().labels(image);e=tool._local_evidence(image,'upper',cloth,human,None)
        self.assertLess(e['distance'][40,56],10)
        p=plan();p['background'].append({'point':[.57,.4],'kind':'accessory','evidence':'actual source strap'})
        p['protections']=[{'kind':'accessory','path':[[.57,.25],[.57,.70]],'widthFraction':.04,
            'evidence':'visible accessory centreline'}]
        points,protection,audit=tool._compile_plan(p,image.size,e,None)
        path=audit['protectionPaths'][0]
        self.assertFalse(path['sourceAnchored'])
        self.assertEqual(path['sourceRefinement']['method'],'source_pixel_occluder_grabcut')
        self.assertEqual(protection.getpixel((56,40)),255)
        self.assertEqual(protection.getpixel((54,40)),0)
        self.assertTrue(audit['restoredOccluderPoints'])
        self.assertIn([56,40],points['background'])

    def test_current_real_foreground_supplies_dark_cloth_exemplar_beside_strap(self):
        image=source();rgb=np.asarray(image).copy();rgb[20:85,55:59]=[150,180,100]
        rgb[20:85,53:55]=[70,30,35];image=Image.fromarray(rgb)
        cloth,human,_=Backend().labels(image);e=tool._local_evidence(image,'upper',cloth,human,None)
        self.assertGreater(e['distance'][49,54],10)
        p=plan();p['foreground'].append({'point':[54/99,49/99],'part':'dark cloth fold',
            'evidence':'source visible dark cloth alongside the accessory'})
        p['background'].append({'point':[.57,.4],'kind':'accessory','evidence':'actual green strap'})
        p['protections']=[{'kind':'accessory','path':[[.57,.25],[.57,.70]],'widthFraction':.04,
            'evidence':'visible accessory centreline'}]
        _,protection,audit=tool._compile_plan(p,image.size,e,None)
        self.assertEqual(protection.getpixel((54,49)),0)
        self.assertEqual(protection.getpixel((56,40)),255)
        self.assertEqual(audit['protectionPaths'][0]['sourceRefinement']['method'],'source_pixel_occluder_grabcut')

    def test_nearby_matching_exemplar_seeds_only_actual_pixels_inside_the_path(self):
        image=source();rgb=np.asarray(image).copy();rgb[20:85,55:59]=[150,180,100];image=Image.fromarray(rgb)
        cloth,human,_=Backend().labels(image);e=tool._local_evidence(image,'upper',cloth,human,None)
        p=plan();p['background'].append({'point':[56/99,72/99],'kind':'accessory',
            'evidence':'same visible accessory immediately beyond the path endpoint'})
        p['protections']=[{'kind':'accessory','path':[[.57,.25],[.57,.70]],'widthFraction':.04,
            'evidence':'visible accessory segment'}]
        _,_,audit=tool._compile_plan(p,image.size,e,None)
        refined=audit['protectionPaths'][0]['sourceRefinement']
        self.assertEqual(refined['method'],'source_pixel_occluder_grabcut')
        self.assertEqual(refined['occluderPointsPixels'],[[56,72]])
        self.assertTrue(all(y<=71 for x,y in refined['sourceOccluderSeedsPixels']))

    def test_distant_or_wrong_semantic_exemplar_cannot_speculatively_refine_path(self):
        for point,kind in (([.57,.84],'accessory'),([.57,.4],'hair')):
            image=source();rgb=np.asarray(image).copy();rgb[20:85,55:59]=[150,180,100];image=Image.fromarray(rgb)
            cloth,human,_=Backend().labels(image);e=tool._local_evidence(image,'upper',cloth,human,None)
            p=plan();p['background'].append({'point':point,'kind':kind,'evidence':'source observation'})
            p['protections']=[{'kind':'accessory','path':[[.57,.25],[.57,.70]],'widthFraction':.04,
                'evidence':'visible accessory segment'}]
            _,_,audit=tool._compile_plan(p,image.size,e,None)
            self.assertEqual(audit['protectionPaths'][0]['sourceRefinement']['method'],'conservative_model_ribbon')

    def test_nearby_wrong_colour_exemplar_cannot_replace_actual_occluder_boundary(self):
        image=source();rgb=np.asarray(image).copy();rgb[20:85,55:59]=[150,180,100];image=Image.fromarray(rgb)
        cloth,human,_=Backend().labels(image);e=tool._local_evidence(image,'upper',cloth,human,None)
        p=plan();p['background'].append({'point':[52/99,40/99],'kind':'accessory',
            'evidence':'incorrect nearby accessory point on actual pink cloth'})
        p['protections']=[{'kind':'accessory','path':[[.57,.25],[.57,.70]],'widthFraction':.04,
            'evidence':'visible accessory segment'}]
        _,protection,audit=tool._compile_plan(p,image.size,e,None)
        refined=audit['protectionPaths'][0]['sourceRefinement']
        self.assertNotEqual(refined['method'],'source_pixel_occluder_grabcut')
        self.assertEqual(protection.getpixel((56,40)),255)

    def test_next_plan_receives_compact_truth_about_rejected_model_foreground(self):
        class HairBackend(Backend):
            def labels(self,image):
                c,h,meta=super().labels(image);h[5:12,5:12]=2;return c,h,meta
        bad=plan();bad['foreground'].append({'point':[.08,.08],'part':'claimed cloth inside hair',
            'evidence':'incorrect source coordinate'})
        model=Vision([bad,review(False),plan(),review()])
        _,receipt=self.prepare(vision=model,backend=HairBackend())
        diagnostics=model.calls[2]['context']['previousFailure']['pointDiagnostics']
        row=diagnostics['rejectedPoints'][0]
        self.assertEqual(row['clothingLabel'],0);self.assertEqual(row['humanLabel'],2)
        self.assertEqual(row['sourceRGB'],[30,30,30])
        self.assertTrue(row['baseProtected']);self.assertTrue(row['didNotBecomeConstraint'])
        self.assertIn('accepted compiled foreground',diagnostics['foregroundCoverageMeaning'])
        self.assertNotIn('sourceClothRidgePixels',json.dumps(diagnostics))
        self.assertLess(len(json.dumps(diagnostics)),5000)
        self.assertEqual(model.calls[1]['context']['pointDiagnostics'],diagnostics)

    def test_local_foreground_protection_conflict_has_actionable_pixel_diagnostics(self):
        image=source();cloth,human,_=Backend().labels(image)
        e=tool._local_evidence(image,'upper',cloth,human,None)
        instance=Image.new('L',image.size);instance.putpixel((64,50),255)
        with self.assertRaises(tool.PlanValidationError) as error:
            tool._compile_plan(plan(),image.size,e,None,instance_protection=instance)
        row=error.exception.point_diagnostics['rejectedPoints'][0]
        self.assertEqual(row['pointPixels'],[64,50]);self.assertEqual(row['sourceRGB'],[213,203,201])
        self.assertFalse(row['baseProtected']);self.assertTrue(row['protectedAfterCurrentPlan'])

    def test_local_compile_error_diagnostics_reach_next_automatic_plan(self):
        conflict=Image.new('L',(100,100));conflict.putpixel((64,50),255)
        fixed=plan();fixed['foreground']=fixed['foreground'][:1]
        model=Vision([plan(),fixed,review()])
        with patch.object(tool,'_instance_protection',side_effect=[
                (conflict,{'method':'isolated-source-conflict'}),
                (Image.new('L',(100,100)),{'method':'isolated-source-clear'})]):
            _,receipt=self.prepare(vision=model)
        previous=model.calls[1]['context']['previousFailure']
        self.assertIn('error',previous)
        self.assertEqual(previous['pointDiagnostics']['rejectedPoints'][0]['pointPixels'],[64,50])
        self.assertEqual(previous['pointDiagnostics']['rejectedPoints'][0]['sourceRGB'],[213,203,201])
        self.assertTrue(previous['pointDiagnostics']['rejectedPoints'][0]['protectedAfterCurrentPlan'])

    def test_actual_corroborated_lit_gap_extends_palette_without_widening_gates(self):
        image,cloth,human,p,r=illuminated_gap_fixture();e=tool._local_evidence(image,'lower',cloth,human,None)
        bg,audit=tool._background_protection(image,p,e,r)
        self.assertTrue((np.asarray(bg)[20:85,45:55]>0).all())
        self.assertEqual(len(audit['localGapExemplars']),1)
        sample=audit['localGapExemplars'][0]
        self.assertGreater(sample['lightnessDifferenceToExterior'],18)
        self.assertLess(sample['chromaDistanceToExteriorLab'],6)
        self.assertEqual(sample['sourceRGB'],[225,226,220])
        self.assertEqual(sample['localBackgroundFraction'],1)
        self.assertEqual(audit['minimumFabricDistanceLab'],18)
        self.assertEqual(audit['maximumExteriorDistanceLab'],18)
        self.assertEqual(audit['maximumExteriorChromaDistanceLab'],6)
        self.assertFalse(np.asarray(bg)[20:85,25:35].any())

    def test_lit_gap_palette_still_requires_current_plan_and_review_colocation(self):
        image,cloth,human,p,r=illuminated_gap_fixture();e=tool._local_evidence(image,'lower',cloth,human,None)
        p['background'][0]['point']=[.5,.25]
        bg,audit=tool._background_protection(image,p,e,r)
        self.assertFalse(audit['localGapExemplars'])
        self.assertEqual(bg.getpixel((50,50)),0)

    def test_lit_gap_palette_cannot_override_double_garment_semantics_or_foreground_colour(self):
        image,cloth,human,p,r=illuminated_gap_fixture();human[15:90,40:60]=6
        e=tool._local_evidence(image,'lower',cloth,human,None)
        bg,audit=tool._background_protection(image,p,e,r)
        self.assertFalse(audit['localGapExemplars']);self.assertEqual(bg.getpixel((50,50)),0)
        image,cloth,human,p,r=illuminated_gap_fixture()
        p['background'][0]['point']=[.3,.5];r['leaks'][0]['point']=[.3,.5]
        cloth[45:55,25:35]=0  # Even one bad local model cannot delete real brown cloth.
        e=tool._local_evidence(image,'lower',cloth,human,None)
        bg,audit=tool._background_protection(image,p,e,r)
        self.assertFalse(audit['localGapExemplars']);self.assertEqual(bg.getpixel((30,50)),0)

    def test_new_gap_colour_must_match_observed_exterior_chroma(self):
        image,cloth,human,p,r=illuminated_gap_fixture();rgb=np.asarray(image).copy()
        rgb[15:90,40:60]=[40,130,190];image=Image.fromarray(rgb)
        e=tool._local_evidence(image,'lower',cloth,human,None)
        bg,audit=tool._background_protection(image,p,e,r)
        self.assertFalse(audit['localGapExemplars']);self.assertEqual(bg.getpixel((50,50)),0)

    def test_rejected_other_garment_model_point_cannot_poison_background_colour_evidence(self):
        image,cloth,human,p,r=illuminated_gap_fixture();rgb=np.asarray(image).copy()
        rgb[5:15,5:15]=[225,226,220];cloth[5:15,5:15]=1;human[5:15,5:15]=4
        image=Image.fromarray(rgb)
        p['foreground'].append({'point':[.1,.1],'part':'mistaken trouser edge',
            'evidence':'incorrect coordinate on another garment'})
        e=tool._local_evidence(image,'lower',cloth,human,None)
        self.assertFalse(tool._foreground_supported(e,10,10))
        bg,audit=tool._background_protection(image,p,e,r)
        self.assertTrue(audit['localGapExemplars']);self.assertGreater(bg.getpixel((50,50)),0)

    def test_mixed_source_edge_is_not_promoted_to_a_clean_gap_palette_sample(self):
        image,cloth,human,p,r=illuminated_gap_fixture();rgb=np.asarray(image).copy()
        rgb[50,51]=[120,70,40];image=Image.fromarray(rgb)
        e=tool._local_evidence(image,'lower',cloth,human,None)
        _,audit=tool._background_protection(image,p,e,r)
        self.assertFalse(audit['localGapExemplars'])

    def test_primary_only_on_human_background_needs_actual_fabric_colour_support(self):
        image,cloth,human,p,r=background_gap_fixture();e=tool._local_evidence(image,'lower',cloth,human,None)
        self.assertTrue(e['primary'][50,50]);self.assertEqual(e['human'][50,50],0)
        self.assertFalse(tool._foreground_supported(e,50,50))
        # Human garment-subtype disagreement with true cloth remains allowed.
        human[15:90,20:40]=4;e=tool._local_evidence(image,'lower',cloth,human,None)
        self.assertTrue(tool._foreground_supported(e,30,50))

    def test_internal_conservation_only_preserves_immediate_miss_only_candidate(self):
        image=source().convert('RGBA');old=Image.new('L',image.size);old.putpixel((35,40),186)
        new=Image.new('L',image.size);new.putpixel((65,50),255);protection=Image.new('L',image.size)
        prior={'mask':old,'quality':{'accepted':True},'review':review(False),'number':1,
            'sourcePixelSha256':tool._pixels(image,'RGBA'),'maskPath':'isolated-prior.png'}
        result,audit=tool._conserve_miss_only(image,new,protection,prior,tool._pixels(image,'RGBA'))
        self.assertTrue(audit['applied']);self.assertFalse(audit['passedStateInherited'])
        self.assertEqual(result.getpixel((35,40)),186);self.assertEqual(result.getpixel((65,50)),255)
        self.assertEqual(audit['inheritedPriorOnlyPixels'],1)
        self.assertEqual(audit['priorMaskPixelSha256'],tool._pixels(old,'L'))

    def test_internal_conservation_never_inherits_known_leaks_or_numeric_failure(self):
        image=source().convert('RGBA');old=Image.new('L',image.size,255);new=Image.new('L',image.size)
        for quality,checked in (({'accepted':False},review(False)),({'accepted':True},
                {'accepted':False,'misses':[{'point':[.3,.5]}],'leaks':[{'point':[.5,.5]}],'issues':['leak']})):
            prior={'mask':old,'quality':quality,'review':checked,'sourcePixelSha256':tool._pixels(image,'RGBA')}
            result,audit=tool._conserve_miss_only(image,new,Image.new('L',image.size),prior,tool._pixels(image,'RGBA'))
            self.assertFalse(audit['applied']);self.assertFalse(np.asarray(result).any())

    def test_internal_conservation_current_protection_and_original_alpha_win(self):
        image=source().convert('RGBA');image.putpixel((40,40),(100,100,100,0))
        old=Image.new('L',image.size);old.putpixel((35,40),255);old.putpixel((40,40),255)
        protection=Image.new('L',image.size);protection.putpixel((35,40),255);before=protection.tobytes()
        prior={'mask':old,'quality':{'accepted':True},'review':review(False),'sourcePixelSha256':tool._pixels(image,'RGBA')}
        result,audit=tool._conserve_miss_only(image,Image.new('L',image.size),protection,prior,tool._pixels(image,'RGBA'))
        self.assertFalse(np.asarray(result).any());self.assertEqual(before,protection.tobytes())
        self.assertEqual(audit['pixelsRemovedByCurrentProtection'],1)
        self.assertEqual(audit['pixelsRemovedBySourceAlpha'],1)

    def test_internal_conservation_rejects_different_source_or_size(self):
        image=source().convert('RGBA');prior={'mask':Image.new('L',image.size),'quality':{'accepted':True},
            'review':review(False),'sourcePixelSha256':'wrong-source'}
        with self.assertRaises(ValueError):
            tool._conserve_miss_only(image,Image.new('L',image.size),Image.new('L',image.size),prior,tool._pixels(image,'RGBA'))

    def test_internal_conservation_is_reviewed_as_a_new_candidate_without_extra_calls(self):
        complete=np.zeros((100,100),'uint8');complete[15:90,20:80]=255
        reduced=complete.copy();reduced[70:74,25:30]=0
        model=Vision([plan(),review(False),plan(),review()])
        mask,receipt=self.prepare(vision=model,backend=Backend([complete,reduced]))
        self.assertEqual(len(model.calls),4)
        self.assertEqual(mask.getpixel((26,71)),255)
        self.assertTrue(receipt['attempts'][1]['internalConservation']['applied'])
        self.assertTrue(model.calls[3]['context']['internalConservation']['applied'])
        self.assertTrue(receipt['independentReview']['accepted'])
        self.assertTrue((Path(receipt['runPath'])/'attempt-02'/'new-mask.png').is_file())

    def test_source_proposals_are_unverified_planner_context_with_unchanged_quality_gate(self):
        import garment_component_proposals as proposals
        c,h,_=Backend().labels(source());e=tool._local_evidence(source(),'upper',c,h,None)
        context=proposals.propose(source(),'upper',e)['context']
        model=Vision();_,receipt=self.prepare(vision=model)
        self.assertTrue(model.calls[0]['context']['sourceProposals']['unverifiedHypothesis'])
        self.assertFalse(model.calls[0]['context']['sourceProposals']['certifiesSelection'])
        self.assertEqual(receipt['identity']['proposalHelper']['version'],proposals.VERSION)
        self.assertTrue(Path(receipt['sourceProposals']['contextPath']).is_file())

    def test_actual_proposal_montage_is_planner_image_three_but_never_fills_mask(self):
        rgb=np.asarray(source()).copy();rgb[20:40,14:18]=[213,203,201];image=Image.fromarray(rgb)
        class IslandBackend(Backend):
            def labels(self,im):
                c,h,meta=super().labels(im);h[20:40,14:18]=4;return c,h,meta
        model=Vision();mask,receipt=self.prepare(image=image,vision=model,backend=IslandBackend())
        self.assertEqual(len(model.calls),2)
        self.assertEqual(len(model.calls[0]['images']),3)
        self.assertTrue(model.calls[0]['context']['sourceProposals']['regions'])
        self.assertIn('reject',model.calls[0]['instruction'])
        self.assertTrue(Path(receipt['sourceProposals']['montagePath']).is_file())
        # The fixture planner deliberately did not choose the proposal. It is
        # not adopted merely because a local model proposed it.
        self.assertFalse(np.asarray(mask)[20:40,14:18].any())

    def test_verified_cache_does_not_repeat_model_requests(self):
        model = Vision();mask, receipt = self.prepare(vision=model)
        cached, second = self.prepare(vision=model)
        self.assertTrue(second['cacheReused']);self.assertEqual(len(model.calls), 2)
        self.assertEqual(mask.tobytes(), cached.tobytes())

    def test_changed_source_gets_different_cache(self):
        model = Vision();_, first = self.prepare(vision=model)
        image = source();image.putpixel((30, 30), (212, 201, 200))
        _, second = self.prepare(image=image, vision=model)
        self.assertNotEqual(first['sourcePixelSha256'], second['sourcePixelSha256'])
        self.assertEqual(len(model.calls), 4)

    def test_tampered_cached_png_is_rejected_without_new_model_call(self):
        model = Vision();_, receipt = self.prepare(vision=model)
        Image.new('L', (100, 100)).save(receipt['maskPath'])
        with self.assertRaises(tool.SelectionRejected) as error:self.prepare(vision=model)
        self.assertEqual(error.exception.code, 'selection_cache_mismatch')
        self.assertEqual(len(model.calls), 2)

    def test_wrong_background_point_on_verified_cloth_is_filtered(self):
        proposal = plan();proposal['background'].append({'point': [.4, .4], 'kind': 'hair', 'evidence': 'vision coordinate mistake'})
        _, receipt = self.prepare(vision=Vision([proposal, review()]))
        rejected = receipt['attempts'][0]['compiled']['rejectedPoints']
        self.assertEqual(rejected[0]['reason'], 'point_conflicts_with_visible_fabric')

    def test_numeric_failure_cannot_be_waived_by_vision_acceptance(self):
        a = np.zeros((100, 100), 'uint8');a[15:90, 20:80] = 255;a[5, 5] = 255
        model = Vision([plan(), review(), plan(), review()])
        with self.assertRaises(tool.SelectionRejected) as error:self.prepare(vision=model, backend=Backend([a]))
        self.assertFalse(error.exception.receipt['verified'])
        self.assertEqual(len(error.exception.receipt['attempts']), 2)
        self.assertIn('explicit_background_or_protection_selected', error.exception.receipt['attempts'][0]['quality']['issues'])

    def test_one_automatic_correction_can_pass_and_is_recorded(self):
        bad = np.zeros((100, 100), 'uint8');bad[15:90, 50:80] = 255
        good = np.zeros((100, 100), 'uint8');good[15:90, 20:80] = 255
        model = Vision([plan(), review(False), plan(), review()])
        mask, receipt = self.prepare(vision=model, backend=Backend([bad, good]))
        self.assertTrue(receipt['verified']);self.assertEqual(len(receipt['attempts']), 2)
        self.assertIsNotNone(model.calls[2]['context']['previousFailure'])
        self.assertFalse(receipt['attempts'][0]['quality']['accepted'])

    def test_model_timeout_is_not_reissued_on_resume(self):
        model = Vision([RuntimeError('transport timeout')])
        with self.assertRaises(tool.SelectionRejected) as first:self.prepare(vision=model)
        self.assertEqual(first.exception.receipt['state'], 'unknown')
        with self.assertRaises(tool.SelectionRejected):self.prepare(vision=model)
        self.assertEqual(len(model.calls), 1)

    def test_large_protection_geometry_is_not_accepted_as_garment_segmentation(self):
        p = plan();p['protections'] = [{'kind': 'accessory', 'path': [[.2, .2], [.8, .8]], 'widthFraction': .5, 'evidence': 'invalid broad mask'}]
        with self.assertRaises(tool.SelectionRejected) as error:self.prepare(vision=Vision([p, p]))
        self.assertEqual(error.exception.receipt['state'], 'rejected')
        self.assertIn('保护路径须为窄线', error.exception.receipt['attempts'][0]['error'])

    def test_review_cannot_claim_pass_with_remaining_leaks(self):
        contradictory = review();contradictory['leaks'] = [{'point': [.2, .2], 'kind': 'accessory', 'evidence': 'leak remains'}]
        with self.assertRaises(tool.SelectionRejected):self.prepare(vision=Vision([plan(), contradictory, plan(), contradictory]))

    def test_explicit_protection_always_wins(self):
        explicit = Image.new('L', (100, 100));explicit.paste(255, (50, 25, 55, 80))
        mask, receipt = self.prepare(protected=explicit)
        self.assertFalse(np.asarray(mask)[25:80, 50:55].any())
        self.assertEqual(receipt['quality']['protectedChangedPixels'], 0)

    def test_invalid_or_bool_coordinates_are_not_coerced(self):
        for value in ([True, .4], [1.5, .4], [float('nan'), .4]):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):tool._point(value, (100, 100))

    def test_source_anchored_narrow_accessory_path_keeps_its_pale_highlight(self):
        image = source();rgb = np.asarray(image).copy();rgb[20:85, 55:59] = [150, 180, 100]
        rgb[45:48, 55:59] = [213, 203, 201]  # A highlight matches cloth RGB.
        image = Image.fromarray(rgb)
        c, h, _ = Backend().labels(image);e = tool._local_evidence(image, 'upper', c, h, None)
        p = plan();p['protections'] = [{'kind': 'accessory', 'path': [[.57, .25], [.57, .70]],
            'widthFraction': .03, 'evidence': 'visible narrow accessory across garment'}]
        points, protection, audit = tool._compile_plan(p, image.size, e, None)
        self.assertTrue(audit['protectionPaths'][0]['sourceAnchored'])
        self.assertGreater(np.asarray(protection)[46, 57], 0)

    def test_wrong_dimension_explicit_protection_cannot_reuse_a_cached_result(self):
        model = Vision();self.prepare(vision=model)
        with self.assertRaises(ValueError):self.prepare(vision=model, protected=Image.new('L', (200, 50)))
        self.assertEqual(len(model.calls), 2)

    def test_actual_downstream_feedback_starts_a_separate_auditable_intent(self):
        model = Vision();_, first = self.prepare(vision=model)
        feedback = {'issues': ['actual output still shows unselected sleeve'], 'source': 'downstream_visual_quality'}
        _, second = self.prepare(vision=model, initial_feedback=feedback)
        self.assertNotEqual(first['cacheManifestPath'], second['cacheManifestPath'])
        self.assertEqual(model.calls[2]['context']['previousFailure'], feedback)
        self.assertEqual(second['initialFeedback'], feedback)

    def test_nonblocking_warnings_do_not_fabricate_a_blocking_issue(self):
        checked = review();checked['warnings'] = ['minor source-edge antialiasing']
        _, receipt = self.prepare(vision=Vision([plan(), checked]))
        self.assertTrue(receipt['verified'])
        self.assertEqual(receipt['independentReview']['warnings'], ['minor source-edge antialiasing'])

    def test_known_local_io_failure_resumes_completed_plan_without_reissuing_it(self):
        class MissingEmbedding(Backend):
            def select(self, source, coarse, protected, points, cache):
                raise FileNotFoundError(2, 'No such file or directory', str(cache / ('a' * 64 + '.' + 'b' * 32 + '.npz')))
        model = Vision()
        with self.assertRaises(tool.SelectionRejected) as failure:self.prepare(vision=model, backend=MissingEmbedding())
        receipt = failure.exception.receipt;manifest = Path(receipt['cacheManifestPath'])
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(receipt['localFailure']['stage'], 'local_select')
        self.assertEqual(Path(receipt['embeddingsCachePath']), Path(self.temp.name).resolve() / 'embeddings')
        before = manifest.read_bytes()
        # Preserve the backend's stable identity: this is a local recovery of
        # the same adapters and source, not a new semantic/model configuration.
        backend = MissingEmbedding();backend.select = Backend().select
        mask, resumed = self.prepare(vision=model, backend=backend, resume_local_error=True)
        self.assertTrue(resumed['verified'])
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(model.calls[1]['instruction'].startswith('Independently'))
        archive = Path(resumed['resumedLocalFailure']['previousReceiptPath'])
        self.assertEqual(archive.read_bytes(), before)
        self.assertEqual(resumed['resumedLocalFailure']['previousReceiptSha256'], hashlib.sha256(before).hexdigest())

    def test_legacy_windows_style_local_embedding_failure_is_migrated_only_with_completed_plan(self):
        class MissingEmbedding(Backend):
            def select(self, source, coarse, protected, points, cache):
                raise FileNotFoundError(2, 'No such file or directory', str(cache / 'failed.npz'))
        model = Vision()
        with self.assertRaises(tool.SelectionRejected) as failure:self.prepare(vision=model, backend=MissingEmbedding())
        receipt = failure.exception.receipt;manifest = Path(receipt['cacheManifestPath'])
        receipt.pop('localFailure')
        receipt['error'] = str(FileNotFoundError(2, 'No such file or directory', str(manifest.parent / 'embeddings' / ('a' * 64 + '.' + 'b' * 32 + '.npz'))))
        manifest.write_text(json.dumps(receipt), 'utf-8')
        eligible = tool.local_failure_resume_info(receipt, manifest.parent, self.temp.name)
        self.assertTrue(eligible['eligible'])
        self.assertEqual(eligible['reason'], 'legacy_embedding_write_error')
        backend = MissingEmbedding();backend.select = Backend().select
        _, resumed = self.prepare(vision=model, backend=backend, resume_local_error=True)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(resumed['resumedLocalFailure']['reason'], 'legacy_embedding_write_error')

    def test_local_resume_flag_does_not_reset_unknown_visual_calls(self):
        model = Vision([RuntimeError('transport timeout')])
        with self.assertRaises(tool.SelectionRejected) as first:self.prepare(vision=model)
        manifest = Path(first.exception.receipt['cacheManifestPath']);before = manifest.read_bytes()
        with self.assertRaises(tool.SelectionRejected):self.prepare(vision=model, resume_local_error=True)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertFalse(list(manifest.parent.glob('lf-*.json')))

    def test_resume_does_not_waive_an_independent_quality_rejection(self):
        model = Vision([plan(), review(False), plan(), review(False)])
        with self.assertRaises(tool.SelectionRejected) as failure:self.prepare(vision=model)
        before = Path(failure.exception.receipt['cacheManifestPath']).read_bytes()
        with self.assertRaises(tool.SelectionRejected):self.prepare(vision=model, resume_local_error=True)
        self.assertEqual(len(model.calls), 4)
        self.assertEqual(Path(failure.exception.receipt['cacheManifestPath']).read_bytes(), before)

    def test_pending_review_prevents_local_error_resume(self):
        class MissingEmbedding(Backend):
            def select(self, source, coarse, protected, points, cache):
                raise FileNotFoundError(2, 'No such file or directory', str(cache / 'failed.npz'))
        model = Vision()
        with self.assertRaises(tool.SelectionRejected) as failure:self.prepare(vision=model, backend=MissingEmbedding())
        manifest = Path(failure.exception.receipt['cacheManifestPath'])
        (manifest.parent / 'attempt-01' / 'review.json').write_text('{"state":"pending"}', 'utf-8')
        with self.assertRaises(tool.SelectionRejected):self.prepare(vision=model, backend=MissingEmbedding(), resume_local_error=True)
        self.assertEqual(len(model.calls), 1)

    def test_known_sam_algorithm_failure_resumes_original_plan_and_keeps_all_old_artifacts(self):
        class Fragmented(Backend):
            def select(self, source, coarse, protected, points, cache):
                raise ValueError('Selection contradicts garment points [(40, 50)] or protection points []')
        model = Vision([plan(), plan(), review()])
        with self.assertRaises(tool.SelectionRejected) as failure:self.prepare(vision=model, backend=Fragmented())
        manifest = Path(failure.exception.receipt['cacheManifestPath']);old_root = manifest.parent
        old = {str(p.relative_to(old_root)): p.read_bytes() for p in old_root.rglob('*') if p.is_file()}
        backend = Fragmented();backend.select = Backend().select
        _, resumed = self.prepare(vision=model, backend=backend, resume_local_error=True)
        self.assertTrue(resumed['verified']);self.assertEqual(len(model.calls), 3)
        self.assertEqual(resumed['resumedLocalFailure']['reason'], 'known_local_sam_point_contradiction')
        self.assertEqual(Path(resumed['runPath']).name, 'r01')
        self.assertTrue(resumed['attempts'][0]['planReusedFrom'])
        self.assertEqual(Path(resumed['maskPath']).parent, Path(resumed['runPath']))
        for name, content in old.items():
            if name != 'receipt.json':self.assertEqual((old_root / name).read_bytes(), content)
        self.assertEqual(Path(resumed['resumedLocalFailure']['previousReceiptPath']).read_bytes(), old['receipt.json'])

    def test_new_actual_quality_feedback_has_new_intent_without_overwriting_old_second_plan(self):
        class Fragmented(Backend):
            def select(self, source, coarse, protected, points, cache):
                raise ValueError('Selection contradicts garment points [(40, 50)] or protection points []')
        model = Vision([plan(), plan(), review(False), plan(), review()])
        with self.assertRaises(tool.SelectionRejected) as failure:self.prepare(vision=model, backend=Fragmented())
        old_root = Path(failure.exception.receipt['cacheManifestPath']).parent
        old_second = (old_root / 'attempt-02' / 'plan.json').read_bytes()
        backend = Fragmented();backend.select = Backend().select
        _, resumed = self.prepare(vision=model, backend=backend, resume_local_error=True)
        self.assertEqual(len(model.calls), 5)
        self.assertEqual((old_root / 'attempt-02' / 'plan.json').read_bytes(), old_second)
        self.assertIn('independentReview', model.calls[3]['context']['previousFailure'])
        self.assertEqual(resumed['attempts'][1]['newPlanReason'], 'new_actual_local_or_quality_feedback')


class JointSamBranchTests(unittest.TestCase):
    def workflow(self, error=None, refined=None):
        calls = []
        class Model:
            def select(self, source, foreground, background):
                calls.append(('sam', copy.deepcopy(foreground), copy.deepcopy(background)))
                if error:raise error
                return Image.new('L', source.size, 255), {'predictedIou': .9}
        class Selector:
            @staticmethod
            def refine(source, proposal, background, protected, foreground):
                calls.append(('grabcut', np.asarray(proposal).copy(), foreground, background))
                return refined.copy() if refined else proposal.copy()
        def combine(base, proposal, protected, operation):
            a = np.asarray(proposal).copy();a[np.asarray(protected) > 0] = 0
            return Image.fromarray(a)
        workflow = types.SimpleNamespace(LOCK=threading.RLock(), selector=lambda cache: Model(),
            GarmentSelector=Selector, prompted_components=lambda mask, points: mask, combine=combine)
        return workflow, calls

    def test_all_verified_positive_points_are_sent_in_one_joint_decode(self):
        workflow, calls = self.workflow();image = source();coarse = Image.new('L', image.size)
        points = {'foreground': [[35, 40], [65, 50]], 'background': [[5, 5]]}
        with patch.dict(sys.modules, {'garment_workflow': workflow}):
            _, receipt = tool.LocalBackend().select(image, coarse, Image.new('L', image.size), points, Path('isolated-cache'))
        self.assertEqual(calls[0], ('sam', points['foreground'], points['background']))
        self.assertEqual(sum(c[0] == 'sam' for c in calls), 1)
        self.assertEqual(receipt['branch'], 'joint_sam_then_source_grabcut')

    def test_explicit_sam_point_contradiction_uses_source_grabcut_proposal_not_an_accepted_semantic_mask(self):
        error = ValueError('Selection contradicts garment points [(35, 40)] or protection points []')
        workflow, calls = self.workflow(error);image = source();coarse = Image.new('L', image.size, 17)
        points = {'foreground': [[35, 40], [65, 50]], 'background': [[5, 5]]}
        with patch.dict(sys.modules, {'garment_workflow': workflow}):
            _, receipt = tool.LocalBackend().select(image, coarse, Image.new('L', image.size), points, Path('isolated-cache'))
        self.assertTrue(np.array_equal(calls[1][1], np.asarray(coarse)))
        self.assertEqual(receipt['samDiagnostics'][0]['error'], str(error))
        self.assertEqual(receipt['branch'], 'source_grabcut_after_joint_sam_contradiction')
        self.assertTrue(receipt['numericAndIndependentReviewRequired'])
        self.assertNotIn('verified', receipt)

    def test_model_integrity_error_is_not_swallowed_as_a_segmentation_fallback(self):
        workflow, calls = self.workflow(ValueError('Selection model differs from its pinned manifest'))
        with patch.dict(sys.modules, {'garment_workflow': workflow}):
            with self.assertRaises(ValueError):tool.LocalBackend().select(source(), Image.new('L', (100, 100)),
                Image.new('L', (100, 100)), {'foreground': [[35, 40]], 'background': [[5, 5]]}, Path('isolated-cache'))
        self.assertEqual(len(calls), 1)

    def test_grabcut_fallback_cannot_bypass_foreground_gate_even_if_vision_says_pass(self):
        bad = Image.new('L', (100, 100));bad.paste(255, (50, 15, 80, 90))
        workflow, _ = self.workflow(ValueError('Selection contradicts garment points [(35, 40)] or protection points []'), refined=bad)
        class WithJointSam(Backend):
            def select(self, source, coarse, protected, points, cache):
                return tool.LocalBackend().select(source, coarse, protected, points, cache)
        model = Vision([plan(), review(), plan(), review()])
        with tempfile.TemporaryDirectory() as cache, patch.dict(sys.modules, {'garment_workflow': workflow}):
            with self.assertRaises(tool.SelectionRejected) as failure:
                tool.prepare(source(), 'upper', vision=model, cache_root=cache, local_backend=WithJointSam())
            self.assertFalse(failure.exception.receipt['verified'])
            self.assertIn('visible_fabric_constraint_missing', failure.exception.receipt['attempts'][0]['quality']['issues'])


if __name__ == '__main__':unittest.main()
