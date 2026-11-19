"""Original-main-image amendment authorization; no external operations."""
import copy
import json
import unittest
from unittest.mock import patch
import publication_flow as flow
import test_publication_recovery as recovery_tests


class MainImageRepairTests(unittest.TestCase):
    setUp = recovery_tests.PublicationRecoveryTests.setUp
    configure = recovery_tests.PublicationRecoveryTests.configure
    start = recovery_tests.PublicationRecoveryTests.start
    failed_job = recovery_tests.PublicationRecoveryTests.failed_job

    def main_failure(self):
        job, packet, record = self.failed_job()
        observation = record['usPublish']['latestObservation']
        observation['messages'][0]['code'] = '18320'
        record['usPublish']['failureObservation'] = copy.deepcopy(observation)
        # Preserve a consumed earlier media retry independently of the repair.
        packet['input']['publicationRecovery'] = {'id': 'old-media-authorization', 'scope': 'retry_original_failed_media'}
        record['usPublish']['mediaRecovery'] = {'amendmentId': 'old-media-authorization', 'phase': 'request_accepted',
                                             'intent': {'publishId': '789'}, 'nativeRequests': [{'payload': {'ids': [789]}}]}
        folder = flow.ROOT / job['id']
        flow.write_json(folder / 'input.json', packet);flow.write_json(folder / 'receipt.json', record)
        return job, packet, record

    def test_explicit_repair_adds_only_one_bound_amendment_and_preserves_every_previous_field(self):
        job, packet, record = self.main_failure();folder = flow.ROOT / job['id']
        job['observationOnly'] = True;flow.persist(job)
        before_receipt = (folder / 'receipt.json').read_bytes()
        self.assertTrue(flow.public(job)['mainImageRepair']['canRepair'])
        with patch.object(flow.threading, 'Thread') as thread:
            result = flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
            after = json.loads((folder / 'input.json').read_text());amendment = after['input'].pop('publicationMainImageRepair')
            self.assertEqual(after, packet);self.assertEqual((folder / 'receipt.json').read_bytes(), before_receipt)
            self.assertEqual(amendment['scope'], 'repair_original_failed_main_image')
            self.assertEqual(amendment['publishId'], '789');self.assertEqual(amendment['failedChildId'], '2001')
            self.assertEqual(amendment['failedSku'], 'P-White-S');self.assertEqual(amendment['jobId'], job['id'])
            self.assertEqual(amendment['failureResponseFingerprint'], record['usPublish']['latestObservation']['responseFingerprint'])
            self.assertEqual(amendment['assetSha256'], packet['input']['assets'][0]['sha256'])
            self.assertEqual(amendment['mainImageUrl'], packet['input']['urls'][amendment['assetSha256']])
            self.assertTrue(amendment['retryOriginalTaskAfterVerifiedSave'])
            self.assertEqual(result['status'], 'queued');self.assertNotIn('observationOnly', flow.owned(2, job['id']))
            duplicate = flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
            self.assertTrue(duplicate['reused']);self.assertEqual(thread.call_count, 1)
        archives = list((folder / 'amendments').glob('*.json'));self.assertEqual(len(archives), 1)
        archived = json.loads(archives[0].read_text());self.assertEqual(archived['previousInput'], packet)
        self.assertEqual(archived['authorization'], amendment)

    def test_plain_continue_never_arms_repair_and_existing_repair_resumes_same_unknown_journal(self):
        job, _, record = self.main_failure();folder = flow.ROOT / job['id'];before = (folder / 'input.json').read_bytes()
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), before)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.discard(job['id'])
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
        amended = json.loads((folder / 'input.json').read_text())['input']['publicationMainImageRepair']
        record['usPublish']['mainImageRepair'] = {'amendmentId': amended['id'], 'publishId': '789',
                                                'phase': 'save_unknown', 'saveIntent': {'armedAt': 'now'}}
        flow.write_json(folder / 'receipt.json', record)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.discard(job['id'])
        frozen = (folder / 'input.json').read_bytes();result = flow.public(job)
        self.assertTrue(result['mainImageRepair']['authorized']);self.assertFalse(result['mainImageRepair']['canRepair'])
        self.assertTrue(result['mainImageRepair']['saveIntended']);self.assertNotIn('beforeSource', result['mainImageRepair'])
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), frozen)
        self.assertEqual(len(list((folder / 'amendments').glob('*.json'))), 1)

    def test_wrong_failure_scope_or_original_image_never_authorizes_a_save(self):
        job, _, record = self.main_failure();folder = flow.ROOT / job['id'];before = (folder / 'input.json').read_bytes()
        changes = [lambda o: o.update(identityVerified=False), lambda o: o.update(publishId='999'),
                   lambda o: o['messages'][0].update(code='300060'), lambda o: o.update(count=2),
                   lambda o: o['children'][0].update(main='https://different.example/new.png'),
                   lambda o: o['children'][0]['images'].reverse(), lambda o: o['children'][1].update(status='pending'),
                   lambda o: o.update(verification='accepted', failed=False, status='publishing')]
        for change in changes:
            invalid = copy.deepcopy(record);change(invalid['usPublish']['latestObservation'])
            flow.write_json(folder / 'receipt.json', invalid)
            self.assertFalse(flow.public(job)['mainImageRepair']['canRepair'])
            with patch.object(flow.threading, 'Thread') as thread:
                with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
                thread.assert_not_called()
            self.assertEqual((folder / 'input.json').read_bytes(), before)

    def test_repair_flag_is_strict_and_mutually_exclusive_with_other_actions(self):
        job, _, _ = self.main_failure();folder = flow.ROOT / job['id'];before = (folder / 'input.json').read_bytes()
        for other in ({'retryMediaFailures': True}, {'observeOnly': True}, {'ukCategoryPath': 'Actual'},
                      {'ukShippingTemplate': 'Actual'}, {'repairMainImage': False}):
            with patch.object(flow.threading, 'Thread') as thread:
                with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True, **other})
                thread.assert_not_called()
        with self.assertRaises(ValueError):flow.resume(3, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
        self.assertEqual((folder / 'input.json').read_bytes(), before)

    def test_mismatched_existing_repair_journal_blocks_continuation_without_overwriting(self):
        job, _, record = self.main_failure();folder = flow.ROOT / job['id']
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.discard(job['id'])
        record['usPublish']['mainImageRepair'] = {'amendmentId': 'other', 'publishId': '789'}
        flow.write_json(folder / 'receipt.json', record);before = (folder / 'input.json').read_bytes()
        with patch.object(flow.threading, 'Thread') as thread:
            with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True})
            thread.assert_not_called()
        self.assertEqual((folder / 'input.json').read_bytes(), before)

    def test_uk_amendment_waits_for_saved_main_and_current_healthy_us_observation(self):
        job, _, record = self.main_failure();folder = flow.ROOT / job['id']
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
        amendment = json.loads((folder / 'input.json').read_text())['input']['publicationMainImageRepair']
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.discard(job['id'])
        record['usPublish']['mainImageRepair'] = {'amendmentId': amendment['id'], 'publishId': '789', 'saveVerified': True}
        record['ukCopy'] = {'draftId': '456', 'phase': 'copy_verified'}
        flow.write_json(folder / 'receipt.json', record);before = (folder / 'input.json').read_bytes()
        with patch.object(flow.threading, 'Thread') as thread:
            with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True,
                'ukShippingTemplate': 'Actual UK', 'shippingEvidence': 'Observed actual UK template'})
            thread.assert_not_called()
        self.assertEqual((folder / 'input.json').read_bytes(), before)

    def test_verified_main_and_latest_accepted_us_allow_existing_editable_uk_repair(self):
        job, _, record = self.main_failure();folder = flow.ROOT / job['id']
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
        original = json.loads((folder / 'input.json').read_text())
        amendment = original['input']['publicationMainImageRepair']
        record['usPublish'].update(phase='publishing_verified', status='publishing',
            latestObservation={'publishId': '789', 'verification': 'accepted', 'failed': False, 'status': 'publishing'},
            mainImageRepair={'amendmentId': amendment['id'], 'publishId': '789', 'saveVerified': True})
        record['ukCopy'] = {'draftId': '456', 'phase': 'copy_verified'}
        flow.write_json(folder / 'receipt.json', record);receipt_bytes = (folder / 'receipt.json').read_bytes()
        job = flow.owned(2, job['id']);job.update(status='needs_reconciliation', error='ERP类目推荐有歧义')
        flow.persist(job);flow.ACTIVE.discard(job['id'])
        with patch.object(flow.threading, 'Thread'):
            result = flow.resume(2, {'id': job['id'], 'confirmed': True, 'ukShippingTemplate': 'Actual UK',
                                    'shippingEvidence': 'Observed actual UK template'})
        self.assertEqual(result['status'], 'queued')
        amended = json.loads((folder / 'input.json').read_text())
        self.assertEqual(amended['input'].pop('ukPreparation'), {'shippingTemplate': {'name': 'Actual UK'}})
        self.assertEqual(amended, original)
        self.assertEqual((folder / 'receipt.json').read_bytes(), receipt_bytes)

    def unknown_main_save(self):
        job, _, record = self.main_failure();folder = flow.ROOT / job['id']
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'repairMainImage': True})
        packet = json.loads((folder / 'input.json').read_text());amendment = packet['input']['publicationMainImageRepair']
        record['usPublish']['mainImageRepair'] = {'amendmentId': amendment['id'], 'amendment': copy.deepcopy(amendment),
            'publishId': '789', 'phase': 'save_unknown', 'saveIntent': {'publishId': '789', 'failedChildId': '2001',
            'amendmentId': amendment['id'], 'armedAt': '2026-11-17T03:21:44.408Z'}, 'nativeRequests': [],
            'lastSaveError': 'page.waitForFunction timed out after 25000ms on original page', 'retry': {},
            'beforeSource': {'updated_at': 'original', 'fixture': 'original business data'}}
        flow.write_json(folder / 'receipt.json', record)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.discard(job['id'])
        return job, packet, record

    def test_corrective_save_requires_explicit_action_and_freezes_once_without_replacing_unknown_history(self):
        job, packet, record = self.unknown_main_save();folder = flow.ROOT / job['id']
        before = (folder / 'input.json').read_bytes();receipt_bytes = (folder / 'receipt.json').read_bytes()
        self.assertTrue(flow.public(job)['mainImageRepair']['canCorrectSave'])
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), before)
        job = flow.owned(2, job['id']);job.update(status='needs_reconciliation', observationOnly=True);flow.persist(job);flow.ACTIVE.discard(job['id'])
        with patch.object(flow.threading, 'Thread') as thread:
            result = flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMainImageSave': True})
            after = json.loads((folder / 'input.json').read_text())
            corrective = after['input']['publicationMainImageRepair'].pop('correctiveSave')
            self.assertEqual(after, packet);self.assertEqual((folder / 'receipt.json').read_bytes(), receipt_bytes)
            self.assertEqual(corrective['scope'], 'explicit_idempotent_original_main_resave')
            self.assertEqual(corrective['originalMainAmendmentId'], packet['input']['publicationMainImageRepair']['id'])
            self.assertEqual(corrective['originalSaveIntentArmedAt'], record['usPublish']['mainImageRepair']['saveIntent']['armedAt'])
            self.assertEqual(corrective['publishId'], '789');self.assertEqual(corrective['failedSku'], 'P-White-S')
            self.assertTrue(result['mainImageRepair']['authorizedCorrectiveSave']);self.assertFalse(result['mainImageRepair']['canCorrectSave'])
            self.assertNotIn('observationOnly', flow.owned(2, job['id']))
            self.assertTrue(flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMainImageSave': True})['reused'])
            self.assertEqual(thread.call_count, 1)
        frozen = (folder / 'input.json').read_bytes()
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.discard(job['id'])
        record['usPublish']['mainImageRepair']['correctiveSave'] = {'amendmentId': corrective['id'], 'saveIntent': {'armedAt': 'second'}}
        flow.write_json(folder / 'receipt.json', record)
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), frozen)
        archives = [json.loads(path.read_text()) for path in (folder / 'amendments').glob('*.json')]
        corrective_archives = [row for row in archives if row['kind'] == 'explicit_idempotent_original_main_resave']
        self.assertEqual(len(corrective_archives), 1);self.assertEqual(corrective_archives[0]['previousInput'], packet)

    def test_corrective_save_rejects_any_recorded_request_guard_error_resolved_or_changed_failure(self):
        job, _, record = self.unknown_main_save();folder = flow.ROOT / job['id'];before = (folder / 'input.json').read_bytes()
        changes = [lambda j: j.pop('nativeRequests'), lambda j: j.update(nativeRequests=[{'payload': {'ids': [789]}}]),
                   lambda j: j.update(guardError='guard rejected'), lambda j: j.update(saveVerified=True),
                   lambda j: j.update(lastSaveError='different error'), lambda j: j.update(retry={'intent': {}}),
                   lambda j: j.update(correctiveSave={}), lambda j: j['saveIntent'].update(amendmentId='other')]
        for change in changes:
            invalid = copy.deepcopy(record);change(invalid['usPublish']['mainImageRepair'])
            flow.write_json(folder / 'receipt.json', invalid)
            self.assertFalse(flow.public(job)['mainImageRepair']['canCorrectSave'])
            with patch.object(flow.threading, 'Thread') as thread:
                with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMainImageSave': True})
                thread.assert_not_called()
            self.assertEqual((folder / 'input.json').read_bytes(), before)
        flow.write_json(folder / 'receipt.json', record)
        for other in ({'observeOnly': True}, {'repairMainImage': True}, {'retryMediaFailures': True},
                      {'ukShippingTemplate': 'Actual'}, {'retryMainImageSave': False}):
            with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMainImageSave': True, **other})

    def test_naturally_resolved_main_allows_uk_only_after_latest_us_is_accepted_without_claiming_a_save(self):
        job, _, record = self.unknown_main_save();folder = flow.ROOT / job['id']
        journal = record['usPublish']['mainImageRepair']
        journal.pop('saveIntent');journal.update(consumedWithoutWrite=True, resolvedNoWriteVerified=True, saveWasNeeded=False)
        record['ukCopy'] = {'draftId': '456', 'phase': 'copy_verified'}
        record['usPublish'].update(phase='publishing_verified', status='publishing',
            latestObservation={'publishId': '789', 'verification': 'accepted', 'failed': False, 'status': 'publishing'})
        flow.write_json(folder / 'receipt.json', record)
        self.assertFalse(flow.public(job)['mainImageRepair']['canCorrectSave'])
        self.assertIn('未重复保存或重试', flow.public(job)['mainImageRepair']['checkpoint'])
        before = json.loads((folder / 'input.json').read_text())
        with patch.object(flow.threading, 'Thread'):
            result = flow.resume(2, {'id': job['id'], 'confirmed': True, 'ukShippingTemplate': 'Actual UK', 'shippingEvidence': 'Observed UK'})
        self.assertEqual(result['status'], 'queued')
        after = json.loads((folder / 'input.json').read_text());after['input'].pop('ukPreparation')
        self.assertEqual(after, before)


if __name__ == '__main__':unittest.main()
