"""Policy/identity tests with injected configuration, no browser or DB calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import publication_policy as policy


def settings():
    return {'publishing': {'cross_marketplace_followup': {
        'enabled': True, 'source_marketplace': 'US', 'target_marketplace': 'UK',
        'trigger': 'publishing', 'preserve_parent_sku': True, 'preserve_child_skus': True,
        'pricing': 'recalculate_target_currency', 'require_target_store_match': True,
        'require_gtin_exemption': True, 'require_shipping_template': True,
        'require_parent_child_sku_readback': True,
        'unknown_result_policy': 'reconcile_existing_record', 'apply_to_existing_products': False}}}


class PublicationPolicyTests(unittest.TestCase):
    def test_new_us_tasks_receive_exact_sku_defaults_and_explicit_executor_entry(self):
        config = settings(); before = copy.deepcopy(config)
        result = policy.default_followup('US', config=config)
        self.assertTrue(result['enabled']); self.assertEqual(result['targetMarketplace'], 'UK')
        self.assertEqual(result['trigger'], 'publishing')
        self.assertEqual(result['acceptedStatuses'], ['publishing', 'accepted'])
        self.assertTrue(result['preserveParentSku']); self.assertTrue(result['preserveChildSkus'])
        self.assertTrue(result['requiresPublishId']); self.assertTrue(result['executorAvailable'])
        self.assertEqual(result['entryPoint'], '/api/publication/start')
        self.assertFalse(result['applyToExistingProducts']); self.assertEqual(config, before)

    def test_uk_or_other_markets_do_not_chain_or_read_us_configuration(self):
        with patch.object(policy, '_configuration', side_effect=AssertionError('No config read')):
            for market in ('UK', 'DE', None, 'us'):
                self.assertIsNone(policy.default_followup(market))

    def test_disabled_missing_or_old_configuration_preserves_no_followup(self):
        self.assertIsNone(policy.default_followup('US', config={}))
        config = settings(); config['publishing']['cross_marketplace_followup']['enabled'] = False
        self.assertIsNone(policy.default_followup('US', config=config))

    def test_bad_config_cannot_relax_sku_or_operating_checks(self):
        for key, value in [('preserve_parent_sku', False), ('preserve_child_skus', False),
                           ('require_target_store_match', False), ('require_shipping_template', False),
                           ('require_gtin_exemption', False), ('require_parent_child_sku_readback', False),
                           ('pricing', 'copy_usd_number'), ('unknown_result_policy', 'retry'),
                           ('apply_to_existing_products', True), ('target_marketplace', 'DE'),
                           ('trigger', 'draft_saved')]:
            with self.subTest(key=key):
                config = settings(); config['publishing']['cross_marketplace_followup'][key] = value
                with self.assertRaises(ValueError):policy.default_followup('US', config=config)

    def test_executor_capability_is_owned_by_code_not_a_config_override(self):
        for value in (True,False,'invented'):
            config = settings(); config['publishing']['cross_marketplace_followup']['executorAvailable'] = value
            self.assertTrue(policy.default_followup('US', config=config)['executorAvailable'])

    def test_disk_loading_is_read_only_and_missing_config_does_not_enable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            with patch.object(policy, 'CONFIG', path):
                self.assertIsNone(policy.default_followup('US')); self.assertFalse(path.exists())
                path.write_text(json.dumps(settings()), encoding='utf-8'); before = path.read_bytes()
                self.assertTrue(policy.default_followup('US')['enabled']); self.assertEqual(path.read_bytes(), before)

    def test_returned_policy_is_not_shared_mutable_state(self):
        config = settings()
        first = policy.default_followup('US', config=config); first['acceptedStatuses'].clear()
        self.assertEqual(policy.default_followup('US', config=config)['acceptedStatuses'], ['publishing', 'accepted'])

    def test_publishing_and_accepted_with_real_id_do_not_require_online_children(self):
        for status in ('publishing', 'accepted'):
            for publish_id in (14978866, '14978866'):
                self.assertTrue(policy.ready_for_copy({'sourceMarketplace':'US', 'status':status,
                    'publishId':publish_id, 'allChildrenOnline':False, 'errors':[]}))

    def test_unknown_failed_or_identity_free_observations_do_not_trigger(self):
        base = {'sourceMarketplace':'US', 'status':'accepted', 'publishId':'14978866'}
        for change in ({'sourceMarketplace':'UK'}, {'sourceMarketplace':None}, {'status':'unknown'},
                       {'status':'draft_saved'}, {'status':'failed'}, {'publishId':None}, {'publishId':True},
                       {'publishId':0}, {'publishId':'0'}, {'publishId':' 14978866'}, {'publishId':1.5},
                       {'publishId':'task-unknown'}, {'resultUnknown':True}, {'submissionUnknown':True},
                       {'requiresReconciliation':True}, {'unknown':True}, {'errors':['rejected']}):
            with self.subTest(change=change):self.assertFalse(policy.ready_for_copy({**base, **change}))
        self.assertFalse(policy.ready_for_copy(None)); self.assertFalse(policy.ready_for_copy('accepted'))

    def test_exact_sku_strings_survive_erp_row_reordering_without_input_changes(self):
        source = ['P-White-S', 'P-White-M']; target = list(reversed(source))
        before = copy.deepcopy((source, target))
        self.assertTrue(policy.validate_copy_skus('P', source, 'P', target))
        self.assertEqual((source, target), before)

    def test_parent_or_child_suffix_renumbering_case_and_spacing_are_rejected(self):
        source = ['P-White-S', 'P-White-M']
        for parent, target in [('P-UK', source), ('p', source), ('P ', source),
                               ('P', ['P-White-S-UK', 'P-White-M-UK']),
                               ('P', ['P-White-S', 'P-White-M ']),
                               ('P', ['P-White-S', 'P-white-M']),
                               ('P', ['generated-1', 'generated-2'])]:
            with self.subTest(parent=parent, target=target):
                with self.assertRaises(ValueError):policy.validate_copy_skus('P', source, parent, target)

    def test_missing_duplicate_and_non_string_skus_are_rejected(self):
        for source, target in [([], []), (['S'], []), (['S'], ['S','M']), (['S','S'], ['S','S']),
                               (['S','M'], ['S','S']), (['S'], [1]), ([None], ['S']), ('S', ['S'])]:
            with self.subTest(source=source, target=target):
                with self.assertRaises(ValueError):policy.validate_copy_skus('P', source, 'P', target)


if __name__ == '__main__':unittest.main()
