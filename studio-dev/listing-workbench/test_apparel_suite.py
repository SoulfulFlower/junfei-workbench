import copy
import hashlib
import unittest

import apparel_suite as apparel
import image_engine_prompts as prompts


def template(identity='2095034520741818370'):
    raw = 'ORIGINAL COMPLETE PROMPT\nwarm orange example, simplified illustration\nEND OF ORIGINAL'
    return {'id': identity, 'style': 'C63', 'url': '/cache/template.png', 'sha256': 'b' * 64,
            'prompt': raw, 'promptSha256': hashlib.sha256(raw.encode()).hexdigest(),
            'originalSha256': 'c' * 64, 'originalImageKey': 'UPLOAD/MANAGE/original.PNG'}


class ApparelContractTests(unittest.TestCase):
    def freeze(self, config=None, count=3, no_text=True):
        return apparel.freeze_request(config or {}, ['/cache/original.png', '/cache/detail.png'],
            reference_sha256=['a' * 64, 'd' * 64], templates=[template()], count=count,
            no_text=no_text, brief='保留流苏原有疏密。\n[用户原始要求] 不偏暖，不补造背面。')

    def plan(self, recipe):
        shots = [{'kind': s['kind'], 'layout': s['allowedLayouts'][0], 'sourceIndex': 0,
                  'question': '买家问题', 'evidence': '原图可见', 'scene': '中性背景',
                  'camera': '与真值图一致', 'copy': ['unused text']} for s in recipe['slots']]
        return apparel.normalize_plan({'identity': '原片棕色流苏裤', 'style': {}, 'shots': shots}, recipe)

    def test_unknown_secondary_reference_cannot_establish_new_garment_view(self):
        recipe = self.freeze()
        self.assertEqual(recipe['references'][1]['role'], 'unverified')
        proposal = self.plan(recipe)
        proposal['shots'][1]['sourceIndex'] = 1
        with self.assertRaisesRegex(ValueError, '同款真值'):
            apparel.normalize_plan(proposal, recipe)
        with self.assertRaisesRegex(ValueError, '明确同款依据'):
            self.freeze({'referenceRoles': [{'role': 'primary', 'sameProduct': True},
                                            {'role': 'detail', 'sameProduct': False}]})

    def test_explicit_model_and_ins_roles_never_share_model_only_inputs(self):
        with self.assertRaisesRegex(ValueError, '真实模特参考'):
            self.freeze({'counts': {'model': 2, 'seller': 1}})
        cfg = {'counts': {'model': 1, 'ins': 1, 'seller': 1},
               'consistency': {'exactScene': True,
                 'modelReference': {'url': '/cache/model.png', 'sha256': 'e' * 64},
                 'sceneReference': {'url': '/cache/scene.png', 'sha256': 'f' * 64}}}
        recipe = self.freeze(cfg)
        plan = self.plan(recipe)
        model, ins = plan['shots'][:2]
        model_refs = apparel.render_references(recipe, model)
        ins_refs = apparel.render_references(recipe, ins)
        self.assertEqual([r['url'] for r in model_refs][-2:], ['/cache/model.png', '/cache/scene.png'])
        self.assertNotIn('/cache/model.png', [r['url'] for r in ins_refs])
        self.assertEqual([r['referenceImageIndex'] for r in model_refs], [1, 2, 3, 4])
        model['apparelReferenceRoles'] = model_refs
        # Reordering images must fail before submit, even when every URL remains valid.
        model['apparelReferenceRoles'][0], model['apparelReferenceRoles'][1] = (
            model['apparelReferenceRoles'][1], model['apparelReferenceRoles'][0])
        with self.assertRaisesRegex(ValueError, '顺序或角色'):
            prompts.compile_shot(plan, model, recipe['brief'])

    def test_template_full_text_retained_with_product_and_no_text_precedence(self):
        recipe = self.freeze()
        plan = self.plan(recipe)
        shot = plan['shots'][2]
        shot['apparelReferenceRoles'] = apparel.render_references(recipe, shot)
        output = prompts.compile_shot(plan, shot, recipe['brief'])
        self.assertIn(template()['prompt'], output)
        self.assertIn('[用户原始要求] 不偏暖，不补造背面。', output)
        self.assertIn('neutral D65', output.replace('Neutral', 'neutral'))
        self.assertIn('irregular strand length/spacing', output)
        self.assertIn('[EXACT ALLOWED ARTWORK COPY] []', output)
        self.assertNotIn('abstract composition blueprint', output)
        bad = copy.deepcopy(shot)
        bad['officialTemplate']['id'] = 'different-id'
        with self.assertRaisesRegex(ValueError, '实际模板'):
            apparel.render_references(recipe, bad)
        corrupted = template()
        corrupted['prompt'] += 'modified'
        with self.assertRaisesRegex(ValueError, '哈希'):
            apparel.freeze_request({}, ['/source'], reference_sha256=['a' * 64],
                templates=[corrupted], count=3, brief='Original brief')

    def test_candidate_cannot_bypass_formal_seven_size_gate_or_invent_size_data(self):
        with self.assertRaisesRegex(ValueError, '正式七图'):
            self.freeze({'deliverable': 'formal-seven'}, count=7)
        with self.assertRaisesRegex(ValueError, '真实数据'):
            self.freeze({'counts': {'seller': 2, 'size': 1}}, no_text=False)
        recipe = self.freeze(count=7)
        self.assertFalse(recipe['publicationEligible'])
        self.assertFalse(recipe['formalSizeChartGateBypassed'])
        with self.assertRaisesRegex(ValueError, '输出比例'):
            self.freeze({'aspectRatio': '1:1', 'targetWidth': 1536, 'targetHeight': 2048})

    def test_fact_sources_are_separate_and_a_detail_cannot_invent_full_product(self):
        cfg = {'referenceRoles': [{'role': 'primary', 'sameProduct': True},
                                 {'role': 'detail', 'sameProduct': True}],
               'productFacts': {'visible': [{'statement': '原片独立流苏间隙', 'sourceIndex': 1}],
                  'verified': [{'statement': '只含长裤', 'source': 'supplier exact product page'}],
                  'inferences': [{'statement': '可能为仿麂皮', 'basis': '视觉推断，不作成分事实'}]}}
        recipe = self.freeze(cfg)
        self.assertEqual(len(recipe['productFacts']['inferences']), 1)
        proposal = self.plan(recipe)
        proposal['shots'][1]['sourceIndex'] = 1
        with self.assertRaisesRegex(ValueError, '局部细节'):
            apparel.normalize_plan(proposal, recipe)
        self.assertEqual(recipe['slots'][1]['kind'], 'model')

    def test_legacy_dispatch_remains_opt_in(self):
        self.assertEqual(prompts.director_for({}), prompts.OFFICIAL_DIRECTOR)
        self.assertEqual(prompts.director_for({'apparelSuite': {'version': apparel.VERSION}}), apparel.DIRECTOR)
        self.assertTrue(callable(prompts.legacy_compile_shot))
        recipe = self.freeze({'counts': {'ins': 1}}, count=1)
        self.assertEqual(recipe['consistency'], {})
        plan = self.plan(recipe)
        with self.assertRaisesRegex(ValueError, '实际模型参考顺序'):
            prompts.compile_shot(plan, plan['shots'][0], recipe['brief'])

    def test_real_detail_requires_current_source_crop_and_formal_keeps_native_schema(self):
        recipe = self.freeze({'counts': {'seller': 1}}, count=1)
        proposal = self.plan(recipe)
        proposal['shots'][0]['layout'] = 'detail'
        with self.assertRaisesRegex(ValueError, 'sourceCrop'):
            apparel.normalize_plan(proposal, recipe)
        proposal['shots'][0]['sourceCrop'] = [.1, .6, .8, .3]
        ready = apparel.normalize_plan(proposal, recipe)
        self.assertEqual(ready['shots'][0]['sourceCrop'], [.1, .6, .8, .3])
        proposal['shots'][0]['sourceCrop'] = [.6, .6, .8, .3]
        with self.assertRaisesRegex(ValueError, 'sourceCrop'):
            apparel.normalize_plan(proposal, recipe)
        direction = apparel.formal_direction()
        self.assertIn('formal native.output schema', direction)
        self.assertIn('Image 7 remains the real size chart', direction)
        self.assertIn('not visual', direction.replace('never visual', 'not visual'))


if __name__ == '__main__':
    unittest.main()
