"""Original-job recovery authorization and no-write observation, all isolated."""
import copy
import json
from contextlib import nullcontext
import unittest
from unittest.mock import patch
import publication_flow as flow
import test_publication_flow as flow_tests


class PublicationRecoveryTests(unittest.TestCase):
    setUp = flow_tests.PublicationFlowTests.setUp
    configure = flow_tests.PublicationFlowTests.configure
    start = flow_tests.PublicationFlowTests.start

    def failed_job(self):
        self.snapshot['sha256'] = 'a' * 64
        self.snapshot['destination'].update(marketId='11', marketplaceId='US-MARKET', countryCode='US')
        self.snapshot['assets'] = [{'sha256': format(index, '064x')} for index in range(14)]
        self.snapshot['goodsItems'] = [{'sku': 'P-White-S', 'color': 'White', 'size': 'S', 'quantity': '18', 'imageIndices': list(range(7))},
                                      {'sku': 'P-Blue-M', 'color': 'Blue', 'size': 'M', 'quantity': '18', 'imageIndices': list(range(7, 14))}]
        self.receipt['uploads'] = {asset['sha256']: 'https://images.example/' + str(index) + '.png'
                                  for index, asset in enumerate(self.snapshot['assets'])}
        self.configure()
        with patch.object(flow.threading, 'Thread'):
            result = self.start()
        job = flow.owned(2, result['id']);job.update(status='needs_reconciliation', error='Original media failed');flow.persist(job)
        flow.ACTIVE.discard(job['id'])
        folder = flow.ROOT / job['id'];packet = json.loads((folder / 'input.json').read_text());source = packet['input']
        children = []
        for index, variant in enumerate(source['goodsItems']):
            images = [source['urls'][source['assets'][image]['sha256']] for image in variant['imageIndices']]
            children.append({'childId': str(2001 + index), 'sku': variant['sku'], 'color': variant['color'], 'size': variant['size'],
                             'status': 'failed' if index == 0 else 'accepted', 'images': images, 'main': images[0], 'imagesSource': 'child_gallery'})
        observation = {'accountId': 2, 'productId': 'P', 'snapshotSha256': source['sha256'], 'destinationId': 'US',
                       'draftId': '123', 'erpAccountId': '19335', 'marketId': '11', 'countryCode': 'US', 'store': 'Shop-US',
                       'parentSku': 'P', 'publishId': '789', 'status': 'failed', 'observedAt': '2026-11-16T12:00:00Z',
                       'verification': 'failed', 'failed': True, 'identityVerified': True, 'responseFingerprint': 'f' * 64,
                       'failedChildIds': ['2001'], 'skus': ['P-White-S'], 'count': 1, 'childCount': 2,
                       'acceptedChildIds': ['2002'], 'acceptedSkus': ['P-Blue-M'], 'acceptedCount': 1,
                       'messages': [{'childId': '2001', 'sku': 'P-White-S', 'code': '300060', 'message': 'Image processing error'}],
                       'messageCount': 1, 'unscopedMessageCount': 0, 'children': children}
        record = {'accountId': 2, 'productId': 'P', 'jobId': job['id'], 'snapshotSha256': source['sha256'],
                  'usPublish': {'publishId': '789', 'phase': 'publication_failed', 'status': 'failed',
                                'failureObservation': copy.deepcopy(observation), 'latestObservation': copy.deepcopy(observation)},
                  'ukCopy': {}, 'ukPrepare': {}, 'ukPublish': {}}
        flow.write_json(folder / 'receipt.json', record)
        return job, packet, record

    def both_linked(self):
        job, packet, record = self.failed_job();source = packet['input']
        prepared = copy.deepcopy(source);prepared['store'] = 'Shop-UK'
        prepared['destination'].update(countryCode='GB', destinationId='US-UK', draftId='456', marketId='22')
        for key, country, store, destination, publication in [('usPublish', 'US', 'Shop-US', 'US', '789'),
                                                            ('ukPublish', 'GB', 'Shop-UK', 'US-UK', '790')]:
            record[key] = {'publishId': publication, 'phase': 'publishing_verified', 'status': 'accepted',
                           'latestObservation': {'publishId': publication, 'verification': 'accepted', 'failed': False, 'status': 'accepted'},
                           'identity': {'accountId': 2, 'productId': 'P', 'countryCode': country, 'store': store, 'destinationId': destination,
                                        'parentSku': 'P', 'children': [{field: variant[field] for field in ('sku', 'color', 'size')} for variant in source['goodsItems']]}}
        record['ukCopy'] = {'draftId': '456', 'phase': 'copy_verified'}
        record['ukPrepare'] = {'phase': 'uk_draft_verified', 'draftId': '456', 'preparedInput': prepared}
        job['status'] = 'submitted';flow.persist(job)
        flow.write_json(flow.ROOT / job['id'] / 'receipt.json', record)
        return job, packet, record

    def test_public_later_failure_overrides_submitted_but_does_not_expose_media_or_override_later_success(self):
        job, _, record = self.failed_job();job['status'] = 'submitted';flow.persist(job)
        result = flow.public(job)
        self.assertEqual(result['status'], 'needs_reconciliation');self.assertFalse(result['publishSubmitted'])
        self.assertEqual(result['usFailure']['failedCount'], 1);self.assertEqual(result['usFailure']['totalCount'], 2)
        self.assertTrue(result['mediaRecovery']['canRetry'])
        self.assertNotIn('children', result['usPublicationObservation'])
        self.assertNotIn('images.example', json.dumps(result))
        record['usPublish']['latestObservation'] = {'publishId': '789', 'verification': 'accepted', 'failed': False, 'status': 'publishing'}
        flow.write_json(flow.ROOT / job['id'] / 'receipt.json', record)
        result = flow.public(job)
        self.assertEqual(result['status'], 'submitted');self.assertNotIn('usFailure', result)
        self.assertEqual(result['usPublicationObservation']['verification'], 'accepted')

    def test_public_browser_diagnostic_is_friendly_without_altering_raw_errors_or_business_facts(self):
        job, _, _ = self.failed_job();path = flow.ROOT / job['id'] / 'receipt.json'
        raw = path.read_bytes()
        for diagnostic in ['page.waitForFunction timed out after 25000ms on page p2; last URL https://example.test',
                           'page.click timed out after 3000ms on page p2', 'EGO_PAGE_CLOSED: target disappeared',
                           'ElementResolutionError: selector was obscured']:
            job['error'] = diagnostic
            self.assertEqual(flow.public(job)['error'], '浏览器操作未取得完整回执，请核对原记录后继续；不会自动重发')
            self.assertEqual(job['error'], diagnostic);self.assertEqual(path.read_bytes(), raw)
        for fact in ['ERP原发布任务已失败：18320 Missing MAIN image', 'schema 属性 country_of_origin 必填，请补齐真实产地']:
            job['error'] = fact
            self.assertEqual(flow.public(job)['error'], fact)
            self.assertEqual(job['error'], fact);self.assertEqual(path.read_bytes(), raw)

    def test_plain_continue_keeps_frozen_input_and_creates_no_retry_authorization(self):
        job, _, _ = self.failed_job();path = flow.ROOT / job['id'] / 'input.json';before = path.read_bytes()
        with patch.object(flow.threading, 'Thread'):
            result = flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual(result['id'], job['id']);self.assertEqual(path.read_bytes(), before)
        self.assertNotIn('publicationRecovery', json.loads(path.read_text())['input'])

    def test_explicit_retry_freezes_one_original_task_authorization_and_double_click_reuses_it(self):
        job, packet, record = self.failed_job();folder = flow.ROOT / job['id']
        with patch.object(flow.threading, 'Thread') as thread:
            result = flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMediaFailures': True})
            amended = json.loads((folder / 'input.json').read_text());authorization = amended['input'].pop('publicationRecovery')
            self.assertEqual(amended, packet)
            self.assertEqual(authorization['publishId'], '789');self.assertEqual(authorization['jobId'], job['id'])
            self.assertEqual(authorization['failedChildIds'], ['2001'])
            self.assertEqual(authorization['failureResponseFingerprint'], record['usPublish']['latestObservation']['responseFingerprint'])
            self.assertEqual(authorization['scope'], 'retry_original_failed_media')
            self.assertEqual(result['id'], job['id']);self.assertEqual(result['status'], 'queued')
            frozen = (folder / 'input.json').read_bytes()
            duplicate = flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMediaFailures': True})
            self.assertTrue(duplicate['reused']);self.assertEqual(thread.call_count, 1)
            original = flow.owned(2, job['id']);original['status'] = 'needs_reconciliation';flow.persist(original);flow.ACTIVE.discard(job['id'])
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMediaFailures': True})
            self.assertEqual((folder / 'input.json').read_bytes(), frozen)
        archives = list((folder / 'amendments').glob('*.json'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(json.loads(archives[0].read_text())['previousInput'], packet)

    def test_retry_rejects_other_errors_wrong_identity_stale_success_and_wrong_child_scope(self):
        job, _, record = self.failed_job();folder = flow.ROOT / job['id'];before = (folder / 'input.json').read_bytes()
        changes = [lambda o: o.update(identityVerified=False), lambda o: o.update(publishId='999'),
                   lambda o: o['messages'][0].update(code='99999'), lambda o: o.update(failedChildIds=['2002']),
                   lambda o: o['children'][0]['images'].reverse(),
                   lambda o: o.update(verification='accepted', failed=False, status='accepted')]
        for change in changes:
            invalid = copy.deepcopy(record);change(invalid['usPublish']['latestObservation'])
            flow.write_json(folder / 'receipt.json', invalid)
            with patch.object(flow.threading, 'Thread') as thread:
                with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True, 'retryMediaFailures': True})
                thread.assert_not_called()
            self.assertEqual((folder / 'input.json').read_bytes(), before)
        with self.assertRaises(ValueError):flow.resume(3, {'id': job['id'], 'confirmed': True, 'retryMediaFailures': True})

    def test_submitted_observation_queues_only_original_ids_without_changing_input_or_logging_in(self):
        job, _, record = self.both_linked();folder = flow.ROOT / job['id'];before = (folder / 'input.json').read_bytes()
        self.assertTrue(flow.public(job)['canObserveLatestReceipts'])
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'observeOnly': True})
        original = flow.owned(2, job['id']);self.assertTrue(original['observationOnly'])
        with patch.object(flow.collection, 'browser_lease', return_value=nullcontext()), \
                patch.object(flow, 'login') as login, patch.object(flow, 'run_browser', return_value=record) as browser:
            flow.execute(original)
        login.assert_not_called();self.assertEqual(browser.call_count, 1)
        self.assertEqual(browser.call_args.args[2], 'observe')
        self.assertEqual(flow.owned(2, job['id'])['status'], 'submitted')
        self.assertEqual((folder / 'input.json').read_bytes(), before)

    def test_unknown_observation_keeps_only_read_mode_on_plain_continue(self):
        job, _, _ = self.both_linked()
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'observeOnly': True})
        original = flow.owned(2, job['id'])
        with patch.object(flow.collection, 'browser_lease', return_value=nullcontext()), \
                patch.object(flow, 'login') as login, patch.object(flow, 'run_browser', side_effect=ValueError('original task failed')):
            flow.execute(original)
        login.assert_not_called()
        self.assertEqual(flow.owned(2, job['id'])['status'], 'needs_reconciliation')
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertTrue(flow.owned(2, job['id'])['observationOnly'])

    def test_observation_rejects_missing_or_mismatched_uk_record_and_mixed_recovery_actions(self):
        job, _, record = self.both_linked();folder = flow.ROOT / job['id']
        for change in (lambda r: r['ukPublish'].pop('publishId'),
                       lambda r: r['ukPrepare']['preparedInput'].update(productId='other'),
                       lambda r: r['ukCopy'].update(phase='copy_unknown'),
                       lambda r: r['ukPrepare'].update(draftId='999'),
                       lambda r: r['ukPrepare']['preparedInput']['destination'].update(destinationId='other')):
            invalid = copy.deepcopy(record);change(invalid);flow.write_json(folder / 'receipt.json', invalid)
            self.assertFalse(flow.public(job)['canObserveLatestReceipts'])
            with patch.object(flow.threading, 'Thread') as thread:
                with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True, 'observeOnly': True})
                thread.assert_not_called()
        with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True, 'observeOnly': True, 'retryMediaFailures': True})


if __name__ == '__main__':unittest.main()
