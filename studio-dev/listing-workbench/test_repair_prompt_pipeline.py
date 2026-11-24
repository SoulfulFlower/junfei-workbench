import copy
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

import repair_prompt_pipeline as repair


def row():
    config = {'prompt': '把[示例商品]放到[示例场景]中', 'needOptimize': True,
              'optimizePrompt': '完整原始策略\n' + '保持可见商品结构。' * 600
                                + '\n用户：{customer_keywords}\n比例：{ListingUserSelectedSize}',
              'optimizeProvider': 'original-source-only',
              'systemPrompt': 'Do not forward this automatically as the user instruction.'}
    return {'id': '116', 'name': '商品主图精修', 'config': config,
            'entryValue': json.dumps(config, ensure_ascii=False), 'entrySha256': 'original-sha'}


def capabilities():
    return {'localTextExpansion': True,
            'source': {'kind': 'local_text_optimizer', 'provider': 'Codex Tools',
                       'baseUrl': 'http://127.0.0.1:8787/v1', 'model': 'actual-text-model'}}


class RepairPromptTests(unittest.TestCase):
    def test_ordered_slots_do_not_submit_unfilled_example(self):
        nodes = repair.template_objects('A[示例商品]B[示例场景]C')
        self.assertEqual(repair.objects_prompt(nodes), 'ABC')
        nodes[1]['text'] = '这条流苏裤'
        nodes += [{'type': 'newLine'}, {'type': 'text', 'text': '白底'}]
        text = repair.objects_prompt(nodes)
        self.assertEqual(text, 'A这条流苏裤BC\n白底')
        prompt, audit = repair.compile_repair(row(), text, [], objects=nodes)
        self.assertNotIn('示例商品', prompt)
        self.assertNotIn('示例场景', prompt)
        self.assertEqual(audit['objects'], nodes)
        self.assertEqual(audit['objects'][3]['placeholder'], '示例场景')

    def test_default_direct_edit_keeps_user_text_and_config_without_model_call(self):
        original = row()
        frozen = copy.deepcopy(original)
        call = Mock(side_effect=AssertionError('must not call a model'))
        brief = 'Remove only the grey background. Keep this product unchanged.'
        prompt, audit = repair.compile_repair(original, brief, ['source'], optimizer=call)
        self.assertTrue(prompt.startswith(brief))
        self.assertFalse(audit['effectiveNeedOptimize'])
        self.assertTrue(audit['templateRequestedOptimize'])
        self.assertFalse(audit['requestedNeedOptimize'])
        self.assertEqual(audit['rawConfig'], original['config'])
        self.assertEqual(audit['entryValue'], original['entryValue'])
        self.assertEqual(original, frozen)
        self.assertNotIn('Do not forward this', prompt)
        self.assertEqual(audit['requestedSize'], '')
        self.assertNotIn('aspect ratio', prompt)
        call.assert_not_called()

    def test_model_name_or_native_flag_does_not_enable_local_optimizer(self):
        call = Mock(side_effect=AssertionError('must not call a model'))
        for caps in (None, {'provider': 'GPT_2_5_IMAGE', 'supportPromptExpand': True},
                     {'localTextExpansion': True, 'source': 'unverified'},
                     {'localTextExpansion': True, 'source': {'kind': 'local_text_optimizer',
                       'provider': 'Other', 'model': 'actual-model'}}):
            _, audit = repair.compile_repair(row(), '白底，保留原图流苏。', [],
                                            need_optimize=True, image_capabilities=caps, optimizer=call)
            self.assertTrue(audit['requestedNeedOptimize'])
            self.assertFalse(audit['effectiveNeedOptimize'])
            self.assertEqual(audit['optimizationReason'], 'local_optimizer_capability_unverified')
        call.assert_not_called()

    def test_full_policy_and_runtime_bindings_reach_local_codex_optimizer(self):
        original = row()
        call = Mock(return_value='Remove only the background; preserve product identity and fringe.')
        prompt, audit = repair.compile_repair(original, '去掉背景，保留全部流苏。', ['ref1', 'ref2'], 'auto',
                                            need_optimize=True, image_capabilities=capabilities(), optimizer=call)
        sent, images = call.call_args.args
        self.assertEqual(images, ['ref1', 'ref2'])
        bound = original['config']['optimizePrompt'].replace('{customer_keywords}', '去掉背景，保留全部流苏。').replace('{ListingUserSelectedSize}', 'auto')
        self.assertIn(bound, sent)
        self.assertEqual(audit['optimizerPolicyOriginal'], original['config']['optimizePrompt'])
        self.assertTrue(audit['effectiveNeedOptimize'])
        self.assertTrue(audit['optimizationAccepted'])
        self.assertFalse(audit['builtinProviderExpansion'])
        self.assertTrue(audit['localTextExpansion'])
        self.assertFalse(audit['privateServerPromptKnown'])
        self.assertEqual(audit['runtimeBindings']['ListingUserSelectedSize'], 'auto')
        self.assertNotIn('Requested aspect ratio', prompt)

    def test_verbose_response_preserved_without_paid_retry(self):
        answer = 'unsupported verbose description ' * 200
        call = Mock(return_value=answer)
        prompt, audit = repair.compile_repair(row(), '白底，保留原色。', [], '4:5', need_optimize=True,
                                            image_capabilities=capabilities(), optimizer=call)
        self.assertTrue(prompt.startswith('白底，保留原色。'))
        self.assertEqual(audit['optimizedPrompt'], answer)
        self.assertFalse(audit['optimizationAccepted'])
        self.assertEqual(audit['optimizationReason'], 'verbose_output_retained_original_input')
        self.assertIn('Requested aspect ratio: 4:5.', prompt)
        call.assert_called_once()

    def test_compact_preservation_is_auditable_and_does_not_invent_fringe(self):
        prompt, audit = repair.compile_repair(row(), 'Clean the background.', [],
                                            preservation={'neutralWhiteBalance': False})
        self.assertLess(len(prompt), 600)
        self.assertIn('Where visible', prompt)
        self.assertNotIn('warm/yellow', prompt)
        self.assertEqual([x['id'] for x in audit['preservation']],
                         ['identity', 'noNewFacts', 'fringeTexture'])

    def test_invalid_or_stale_nodes_and_empty_slots_stop_before_call(self):
        call = Mock()
        for brief, nodes in [('Changed current input', [{'type': 'text', 'text': 'stale'}]),
                             ('', [{'type': 'tag', 'text': '', 'placeholder': 'not a fact'}]),
                             ('abc', [{'type': 'unknown', 'text': 'abc'}])]:
            with self.assertRaises(ValueError):
                repair.compile_repair(row(), brief, [], objects=nodes, optimizer=call)
        call.assert_not_called()

    def test_default_optimizer_fails_closed_on_non_codex_route(self):
        fake_visual = types.SimpleNamespace(proxy_vision_settings=Mock(return_value=None), model_prompt=Mock())
        fake_provider = types.SimpleNamespace(text_provider_name=Mock(return_value='Other'))
        with patch.dict(sys.modules, {'visual_studio': fake_visual, 'provider': fake_provider}):
            with self.assertRaisesRegex(ValueError, 'Codex Tools'):
                repair.compile_repair(row(), 'Keep neutral colours.', ['ref'], need_optimize=True,
                                      image_capabilities=capabilities())
        fake_visual.model_prompt.assert_not_called()

    def test_default_optimizer_uses_existing_codex_model_prompt(self):
        fake_visual = types.SimpleNamespace(proxy_vision_settings=Mock(return_value={'model': 'actual-text-model'}),
                                           model_prompt=Mock(return_value='Keep neutral colours.'))
        fake_provider = types.SimpleNamespace(text_provider_name=Mock(return_value='Codex Tools'))
        with patch.dict(sys.modules, {'visual_studio': fake_visual, 'provider': fake_provider}):
            _, audit = repair.compile_repair(row(), 'Keep neutral colours.', ['ref'], need_optimize=True,
                                            image_capabilities=capabilities())
        self.assertTrue(audit['optimizationAccepted'])
        self.assertEqual(fake_visual.model_prompt.call_args.kwargs,
                         {'market': 'analysis', 'purpose': 'official_repair_original_optimizer'})
        self.assertEqual(fake_visual.model_prompt.call_args.args[1], ['ref'])

    def test_library_wrapper_preserves_positional_call_and_forwards_new_fields(self):
        import official_image_templates as library
        original = row()
        with patch.object(library, 'get', return_value=original):
            prompt, audit = library.expert_prompt('116', '保留原色，改白底。', ['ref'])
            self.assertTrue(prompt.startswith('保留原色，改白底。'))
            self.assertEqual(audit['id'], '116')
            self.assertFalse(audit['requestedNeedOptimize'])
            nodes = [{'type': 'text', 'text': 'Clean the background.'}]
            prompt, audit = library.expert_prompt('116', 'Clean the background.', ['ref'], 'auto',
                                                  objects=nodes, need_optimize=False,
                                                  image_capabilities=capabilities())
            self.assertEqual(audit['objects'], nodes)
            self.assertEqual(audit['requestedSize'], 'auto')
            self.assertFalse(audit['effectiveNeedOptimize'])


if __name__ == '__main__':
    unittest.main()
