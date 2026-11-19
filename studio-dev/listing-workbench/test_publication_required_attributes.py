"""Isolated authorization/host tests. No ERP, browser, network or model calls."""
import copy
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
import unittest
from unittest.mock import patch
import publication_flow as flow
import publication_required_attributes as required
import test_publication_recovery as recovery


class RequiredAttributeRepairTests(unittest.TestCase):
    setUp = recovery.PublicationRecoveryTests.setUp
    configure = recovery.PublicationRecoveryTests.configure
    start = recovery.PublicationRecoveryTests.start
    failed_job = recovery.PublicationRecoveryTests.failed_job
    both_linked = recovery.PublicationRecoveryTests.both_linked

    def fixture(self):
        job, packet, record = self.both_linked()
        source = packet['input']
        goods = {'sourceUrl': 'https://detail.1688.com/offer/123456789.html',
                 'description': 'Material: 100% polyester\nCuffs and hem: Ribbed', 'parentSku': 'P'}
        source['goods'].update(goods)
        prepared = record['ukPrepare']['preparedInput']
        prepared['goods'].update(goods)
        prepared['marketplace'] = 'UK'
        prepared['destination']['schemaHash'] = 'gb-schema'
        prepared['urls'] = source['urls']
        record['ukPrepare']['urls'] = source['urls']
        record['ukPrepare']['schemaObservation'] = {'country_code': 'GB', 'locale': 'en_GB',
            'product_type_name': 'SWEATSHIRT', 'hash': 'gb-schema', 'schema_content': {'properties': {}}}
        publication = record['ukPublish']
        publication['identity']['publishId'] = '790'
        publication.update(fingerprint='accepted-fingerprint', sourceEvidence={'historicalAccepted': True},
                           sourceLink={'publishId': '790', 'draftId': '456'})
        observation = copy.deepcopy(record['usPublish']['latestObservation'])
        # The existing fixture's US observation is accepted-only. Build a new
        # complete original-UK failure while retaining original child galleries.
        _, _, old = recovery.PublicationRecoveryTests.failed_job(self)
        template = old['usPublish']['failureObservation']
        observation = copy.deepcopy(template)
        observation.update(publishId='790', destinationId='US-UK', draftId='456', marketId='22',
                           countryCode='GB', store='Shop-UK', count=2, acceptedCount=0,
                           acceptedChildIds=[], acceptedSkus=[], status='failed', failed=True,
                           verification='failed', messageCount=6)
        messages = []
        for row in observation['children']:
            row['status'] = 'failed'
            row['messages'] = [{'childId': row['childId'], 'sku': row['sku'], 'code': '90220',
                                'message': name + ' 为必填项，但缺失。'}
                               for name in ('外部材料', '编织类型', '产品类型名称')]
            messages.extend(row['messages'])
        observation.update(messages=messages, failedChildIds=[x['childId'] for x in observation['children']],
                           skus=[x['sku'] for x in observation['children']])
        publication.update(status='failed', phase='publication_failed',
                           latestObservation=observation, failureObservation=copy.deepcopy(observation))
        job.update(status='needs_reconciliation', error='Original UK90220; original US pending audit')
        flow.persist(job)
        folder = flow.ROOT / job['id']
        flow.write_json(folder / 'input.json', packet)
        flow.write_json(folder / 'receipt.json', record)
        cache = folder / 'public-supplier-cache'
        cache.mkdir(exist_ok=True)
        self.enterContext(patch.object(required, 'ARTIFACT_ROOT', cache))
        artifacts = []
        for name, body in [('page.json', {'url': goods['sourceUrl'], 'text': '商品属性\n面料名称\n聚酯纤维（涤纶）\n工艺\n针织'}),
                           ('attributes.json', {'url': goods['sourceUrl'], 'title': '长袖卫衣',
                            'attributes': {'材质成分': '涤纶（聚酯纤维）:100%'}})]:
            path = cache / name
            path.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
            artifacts.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        request = {'sourceFingerprint': '1' * 64, 'schemaHash': 'gb-schema',
                   'facts': copy.deepcopy(required.FACTS), 'representation': copy.deepcopy(required.REPRESENTATION),
                   'evidence': {'sourceUrl': goods['sourceUrl'], 'materialText': '100% polyester',
                                'weaveText': '工艺\n针织', 'itemTitle': '长袖卫衣',
                                'categoryPath': 'Fashion Sweatshirts', 'artifacts': artifacts}}
        payload = {'id': job['id'], 'confirmed': True, 'repairRequiredAttributes': True,
                   'requiredAttributeRepair': request}
        return job, packet, record, payload

    def test_freeze_explicit_original_uk_scope_and_cached_supplier_evidence_without_changing_old_receipt(self):
        job, packet, record, payload = self.fixture()
        folder = flow.ROOT / job['id']
        receipt_before = (folder / 'receipt.json').read_bytes()
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, payload)
        amended = json.loads((folder / 'input.json').read_text())
        authorization = amended['input'].pop('publicationRequiredAttributeRepair')
        self.assertEqual(amended, packet)
        self.assertEqual((folder / 'receipt.json').read_bytes(), receipt_before)
        self.assertEqual(authorization['publishId'], '790')
        self.assertEqual(authorization['facts'], required.FACTS)
        self.assertEqual(authorization['representation'], required.REPRESENTATION)
        self.assertEqual(authorization['children'], [{'id': '2001', 'sku': 'P-White-S'}, {'id': '2002', 'sku': 'P-Blue-M'}])
        archives = list((folder / 'amendments').glob('*.json'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(json.loads(archives[0].read_text())['previousInput'], packet)

    def test_plain_continue_is_not_new_authorization_and_existing_unknown_retains_same_scope(self):
        job, _, record, payload = self.fixture()
        folder = flow.ROOT / job['id']
        before = (folder / 'input.json').read_bytes()
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), before)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, payload)
        amended = json.loads((folder / 'input.json').read_text())['input']['publicationRequiredAttributeRepair']
        record['ukPublish']['requiredAttributeRepair'] = {'amendmentId': amended['id'], 'publishId': '790',
                                                         'saveIntent': {'armedAt': 'unknown'}}
        flow.write_json(folder / 'receipt.json', record)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        frozen = (folder / 'input.json').read_bytes()
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), frozen)
        self.assertTrue(flow.owned(2, job['id'])['requiredAttributeRepairOnly'])
        self.assertEqual(len(list((folder / 'amendments').glob('*.json'))), 1)

    def test_unsupported_error_foreign_scope_changed_images_and_missing_cached_knit_evidence_never_freeze(self):
        job, packet, record, payload = self.fixture();folder = flow.ROOT / job['id']
        changes = [lambda r:r['ukPublish']['latestObservation'].update(publishId='999'),
                   lambda r:r['ukPublish']['latestObservation']['children'][0]['messages'][0].update(code='300060'),
                   lambda r:r['ukPublish']['latestObservation']['children'][0]['images'].reverse(),
                   lambda r:r['ukPrepare']['schemaObservation'].update(product_type_name='SHIRT')]
        for change in changes:
            invalid = copy.deepcopy(record);change(invalid);flow.write_json(folder / 'receipt.json', invalid)
            with patch.object(flow.threading, 'Thread') as thread, self.assertRaises(ValueError):
                flow.resume(2, payload)
            thread.assert_not_called()
            self.assertNotIn('publicationRequiredAttributeRepair', json.loads((folder / 'input.json').read_text())['input'])
        flow.write_json(folder / 'receipt.json', record)
        path = Path(payload['requiredAttributeRepair']['evidence']['artifacts'][0]['path'])
        path.write_text(json.dumps({'url': packet['input']['goods']['sourceUrl'], 'text': '商品属性\n袖口罗纹'}), encoding='utf-8')
        payload['requiredAttributeRepair']['evidence']['artifacts'][0]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch.object(flow.threading, 'Thread'), self.assertRaises(ValueError):flow.resume(2, payload)

    def test_flags_are_explicit_exclusive_and_another_account_cannot_authorize(self):
        job, _, _, payload = self.fixture()
        for extra in ({'observeOnly': True}, {'retryMediaFailures': True}, {'repairMainImage': True}, {'repairRequiredAttributes': False}):
            with self.assertRaises(ValueError):flow.resume(2, {**payload, **extra})
        with self.assertRaises(ValueError):flow.resume(3, payload)
        malformed = copy.deepcopy(payload);malformed['requiredAttributeRepair']['representation']['explicitCommonAttributes'] = 1
        with self.assertRaises(ValueError):flow.resume(2, malformed)

    def test_targeted_host_only_logs_into_uk_and_never_requires_or_writes_us(self):
        job, _, record, payload = self.fixture()
        with patch.object(flow.threading, 'Thread'):flow.resume(2, payload)
        job = flow.owned(2, job['id'])
        with patch.object(flow.collection, 'browser_lease', return_value=nullcontext()), \
                patch.object(flow, 'login') as login, patch.object(flow, 'run_browser', return_value=record) as run:
            flow.execute(job)
        self.assertEqual(login.call_args.args[2], 'UK')
        self.assertEqual(run.call_args.args[2], 'uk_required_attributes')
        self.assertEqual(login.call_count, 1);self.assertEqual(run.call_count, 1)
        self.assertEqual(flow.owned(2, job['id'])['status'], 'needs_reconciliation')

    def preclick_fixture(self):
        job, packet, record, payload = self.fixture()
        before = {'original': 'full source'}
        payload['requiredAttributeRepair']['sourceFingerprint'] = required.source_fingerprint(before)
        folder = flow.ROOT / job['id']
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, payload)
        packet = json.loads((folder / 'input.json').read_text())
        amendment = packet['input']['publicationRequiredAttributeRepair']
        record['ukPublish']['requiredAttributeRepair'] = {
            'amendmentId': amendment['id'], 'publishId': amendment['publishId'], 'phase': 'save_unknown',
            'saveIntent': {'publishId': amendment['publishId'], 'armedAt': 'original-preclick',
                           'scope': 'one_original_task_native_save'},
            'lastSaveError': 'page.waitForFunction timed out after 20000ms on page p2; last URL was '
                '"https://www.junfeikuajing.com/#/amazon/product/790?type=publish"; '
                'last title was "Amazon产品编辑 - 钧飞跨境".',
            'beforeSource': before, 'plannedSource': {'original': 'same facts explicitly represented'}, 'retry': {}}
        flow.write_json(folder / 'receipt.json', record)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        return job, packet, record

    def test_preclick_explicit_scope_archives_input_preserves_old_receipt_and_plain_continue_reuses_it(self):
        job, packet, record = self.preclick_fixture()
        folder = flow.ROOT / job['id'];old_receipt = (folder / 'receipt.json').read_bytes()
        payload = {'id': job['id'], 'confirmed': True, 'resumeRequiredAttributesPreclick': True}
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, payload)
        amended = json.loads((folder / 'input.json').read_text())
        recovery_scope = amended['input']['publicationRequiredAttributeRepair'].pop('preclickSaveRecovery')
        self.assertEqual(amended, packet)
        self.assertEqual(recovery_scope['scope'], 'resume_original_required_attributes_preclick_save')
        self.assertEqual(recovery_scope['originalSaveIntentArmedAt'], 'original-preclick')
        self.assertEqual((folder / 'receipt.json').read_bytes(), old_receipt)
        frozen = (folder / 'input.json').read_bytes()
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), frozen)
        self.assertEqual(len(list((folder / 'amendments').glob('*.json'))), 2)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        with patch.object(flow.threading, 'Thread'), self.assertRaises(ValueError):
            flow.resume(2, payload)

    def test_preclick_rejects_any_guard_history_other_timeout_retry_or_other_error_codes(self):
        job, packet, record = self.preclick_fixture()
        mutations = [lambda j:j.update(nativeRequests=[]), lambda j:j.update(guardInstallProof=None),
                     lambda j:j.update(lastGuardSnapshot={}), lambda j:j.update(saveVerified=False),
                     lambda j:j.update(lastSaveError='page.waitForFunction timed out after 25000ms'),
                     lambda j:j['retry'].update(intent={'armedAt': 'already'}),
                     lambda j:j['beforeSource'].update(changed=True)]
        for mutate in mutations:
            changed = copy.deepcopy(record);mutate(changed['ukPublish']['requiredAttributeRepair'])
            with self.assertRaises(ValueError):required.freeze_preclick_recovery(job, changed, packet['input'])
        changed = copy.deepcopy(record)
        changed['ukPublish']['latestObservation']['children'][0]['messages'][0]['code'] = '18320'
        with self.assertRaises(ValueError):required.freeze_preclick_recovery(job, changed, packet['input'])
        for extra in ({'observeOnly': True}, {'resumeRequiredAttributesPreclick': False}):
            with self.assertRaises(ValueError):flow.resume(2, {'id': job['id'], 'confirmed': True,
                'resumeRequiredAttributesPreclick': True, **extra})

    def retry_preflight_fixture(self):
        job, packet, record = self.preclick_fixture()
        folder = flow.ROOT / job['id']
        with patch.object(flow.threading, 'Thread'):
            flow.resume(2, {'id': job['id'], 'confirmed': True, 'resumeRequiredAttributesPreclick': True})
        packet = json.loads((folder / 'input.json').read_text())
        main = packet['input']['publicationRequiredAttributeRepair'];journal = record['ukPublish']['requiredAttributeRepair']
        journal.update(saveVerified=True, saveVerifiedAt='original-verified-save', phase='retry_unknown',
            schemaValidationAfterSave={'passed': True, 'checkedCount': 3, 'schemaHash': 'gb-schema'},
            preclickSaveRecovery={'amendmentId': main['preclickSaveRecovery']['id'], 'saveVerified': True,
                'nativeRequests': [{'method': 'POST', 'url': 'https://app.junfeikuajing.com/api/amazon/goods/publish/json-update',
                                    'response': {'httpStatus': 200, 'body': {'code': 0}}}]},
            retry={'intent': {'publishId': '790', 'armedAt': 'original-rejected-retry', 'scope': 'original_family_all_children'},
                   'lastError': '原失败任务行或店铺不唯一，未再次发布'})
        flow.write_json(folder / 'receipt.json', record)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        return job, packet, record

    def test_retry_preflight_recovery_is_separate_once_only_authorization_and_never_overwrites_saved_history(self):
        job, packet, record = self.retry_preflight_fixture();folder = flow.ROOT / job['id']
        before = (folder / 'receipt.json').read_bytes()
        payload = {'id': job['id'], 'confirmed': True, 'resumeRequiredAttributesRetryPreflight': True}
        with patch.object(flow.threading, 'Thread'):flow.resume(2, payload)
        amended = json.loads((folder / 'input.json').read_text())
        recovery_scope = amended['input']['publicationRequiredAttributeRepair'].pop('retryPreflightRecovery')
        self.assertEqual(amended, packet);self.assertEqual((folder / 'receipt.json').read_bytes(), before)
        self.assertEqual(recovery_scope['originalRetryIntentArmedAt'], 'original-rejected-retry')
        self.assertEqual(recovery_scope['scope'], 'resume_original_required_attributes_retry_preflight')
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        frozen = (folder / 'input.json').read_bytes()
        with patch.object(flow.threading, 'Thread'):flow.resume(2, {'id': job['id'], 'confirmed': True})
        self.assertEqual((folder / 'input.json').read_bytes(), frozen)
        job = flow.owned(2, job['id']);job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
        with patch.object(flow.threading, 'Thread'), self.assertRaises(ValueError):flow.resume(2, payload)

    def test_retry_preflight_requires_exact_query_rejection_absent_write_guard_and_verified_save(self):
        job, packet, record = self.retry_preflight_fixture()
        changes = [lambda j:j['retry'].update(nativeRequests=[]), lambda j:j['retry'].update(guardError=None),
            lambda j:j['retry'].update(lastError='other timeout'), lambda j:j.update(saveVerified=False),
            lambda j:j['preclickSaveRecovery']['nativeRequests'][0]['response']['body'].update(code=1),
            lambda j:j['schemaValidationAfterSave'].update(checkedCount=1)]
        for change in changes:
            changed = copy.deepcopy(record);change(changed['ukPublish']['requiredAttributeRepair'])
            with self.assertRaises(ValueError):required.freeze_retry_preflight_recovery(job, changed, packet['input'])


if __name__ == '__main__':
    unittest.main()
