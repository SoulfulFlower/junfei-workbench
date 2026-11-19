"""Isolated identifier evidence, API and original-UK host tests."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import publication_flow as flow
import publication_identifiers as ids


def fixture():
    variants = [{'sku': 'P-Blue-S' + str(i), 'color': 'Blue', 'size': 'S' + str(i),
                 'imageIndices': list(range(7))} for i in range(30)]
    assets = [{'sha256': str(i) * 64} for i in range(7)]
    urls = {a['sha256']: 'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/' + str(i) + '.png'
            for i, a in enumerate(assets)}
    source = {'accountId': 2, 'productId': 'P', 'jobId': 'job', 'sha256': 'snapshot',
        'goods': {'parentSku': 'P', 'brand': 'Brand'}, 'goodsItems': variants, 'assets': assets,
        'destination': {'marketId': '91'}, 'ukTarget': {'id': 'UK', 'storeName': 'Shop-UK'}}
    prepared = {**copy.deepcopy(source), 'marketplace': 'UK', 'store': 'Shop-UK',
        'destination': {'countryCode': 'GB', 'marketId': '92', 'erpAccountId': '11', 'destinationId': 'UK',
                        'draftId': '101', 'schemaHash': 'schema'}}
    meta = {'hash': 'schema', 'country_code': 'GB', 'locale': 'en_GB', 'product_type_name': 'SHIRT',
            'schema_content': {'properties': {}}}
    attrs = {'brand': [{'value': 'Brand'}], 'supplier_declared_has_product_identifier_exemption': [{'value': True}]}
    raw = {'id': 202, 'uid': 11, 'market_id': 92, 'country_code': 'GB', 'market': {'alias': 'Shop-UK'},
        'brand': 'Brand', 'sku': 'P', 'product_type_name': 'SHIRT', 'standard_product_type': 'UPC',
        'standard_product_id': '796225904178', 'extra': {'attributes': copy.deepcopy(attrs)},
        'items': [{'id': 203 + i, 'pid': 202, 'sku': v['sku'], 'standard_product_type': None,
                   'standard_product_id': '796225904' + str(185 + i), 'main_image': urls[assets[0]['sha256']],
                   'extra': {'images': list(urls.values()), 'attributes': copy.deepcopy(attrs)}}
                  for i, v in enumerate(variants)]}
    original = copy.deepcopy(raw);original.update(id=303, country_code='US', market_id=91, standard_product_id=None)
    for row in original['items']:row.update(standard_product_id=None, standard_product_type=None)
    expected = {'accountId': 2, 'productId': 'P', 'jobId': 'job', 'snapshotSha256': 'snapshot',
        'publishId': '202', 'destinationId': 'UK', 'draftId': '101', 'erpAccountId': '11', 'marketId': '92',
        'countryCode': 'GB', 'store': 'Shop-UK', 'parentSku': 'P', 'schemaHash': 'schema'}
    failure = {**expected, 'observedAt': 'first', 'responseFingerprint': 'a' * 64, 'identityVerified': True,
        'failed': True, 'verification': 'failed', 'status': 'failed', 'count': 30, 'childCount': 30,
        'acceptedCount': 0, 'unscopedMessageCount': 0, 'messageCount': 90,
        'children': [{'childId': str(r['id']), 'sku': r['sku'], 'status': 'failed', 'imagesSource': 'child_gallery',
                      'main': r['main_image'], 'images': list(urls.values()),
                      'messages': [{'code': c} for c in ('8566', '8572', '13013')]} for r in raw['items']]}
    exemption = {'phase': 'allowed', 'applicationState': 'available', 'applyIntent': {'armedAt': 'one'},
        'applyRequests': [{}], 'nativeScope': {'seller_id': 'SELLER', 'country_code': 'GB',
            'primary_category_name': 'Fashion', 'product_type_name': 'SHIRT', 'brand': 'Brand'},
        'applyResponse': {'response': {'httpStatus': 200, 'body': {'code': 0, 'data': {'id': 57373}}}},
        'latestCheck': {'status': 'available', 'ui': {'store': 'Shop-UK', 'nativeMarketId': '92'}}, 'allowedAt': 'once'}
    record = {'accountId': 2, 'productId': 'P', 'jobId': 'job', 'snapshotSha256': 'snapshot',
        'usPublish': {'publishId': '303'}, 'ukCopy': {'phase': 'copy_verified', 'draftId': '101', 'sourceEvidence': original},
        'ukPrepare': {'phase': 'uk_draft_verified', 'draftId': '101', 'preparedInput': prepared,
                      'schemaObservation': meta, 'urls': urls, 'brandExemption': exemption},
        'ukPublish': {'publishId': '202', 'identity': {'publishId': '202'}, 'fingerprint': 'accepted',
            'sourceLink': {'publishId': '202', 'draftId': '101'}, 'sourceEvidence': {'accepted': True},
            'latestObservation': failure, 'failureObservation': copy.deepcopy(failure)}}
    evidence = {'response': {'code': 0, 'data': raw}, 'meta': meta, 'failure': copy.deepcopy(failure),
        'sourceFingerprint': ids.fingerprint(raw), 'sourceEvidenceFingerprint': ids.fingerprint(original),
        'introducedIdentifiers': ids.introduced_identifiers(raw), 'exemption': ids.exemption_proof(exemption, prepared)}
    evidence['failure']['observedAt'] = 'later fresh getter'
    job = {'id': 'job', 'accountId': 2, 'productId': 'P', 'status': 'needs_reconciliation', 'destinationId': 'US'}
    return job, record, source, evidence


def sweatshirt_fixture():
    job, record, source, evidence = fixture()
    prepared = record['ukPrepare']['preparedInput'];raw = evidence['response']['data']
    variants = [{**copy.deepcopy(source['goodsItems'][0]), 'sku': 'P-Blue-S' + str(i),
                 'price': '15.19', 'quantity': 88} for i in range(75)]
    source['goodsItems'] = copy.deepcopy(variants);prepared['goodsItems'] = copy.deepcopy(variants)
    prepared['handlingDays'] = 3;prepared['destination']['shippingTemplate'] = {'id': 'real-template', 'name': 'Original'}
    meta = record['ukPrepare']['schemaObservation'];meta['product_type_name'] = 'SWEATSHIRT'
    evidence['meta'] = copy.deepcopy(meta);record['ukPrepare']['brandExemption'] = None
    raw.update(product_type_name='SWEATSHIRT', seller_id='SELLER', status='failed', asin=None, price='15.19', quantity=88)
    template = raw['items'][0]
    raw['items'] = [{**copy.deepcopy(template), 'id': 203 + i, 'sku': v['sku'], 'status': 'failed',
                     'asin': None, 'price': '15.19', 'quantity': 88, 'standard_product_id': str(796225905000 + i)}
                    for i, v in enumerate(variants)]
    original = copy.deepcopy(raw);original.update(id=303, country_code='US', market_id=91, standard_product_id=None)
    for row in original['items']:row.update(standard_product_id=None, standard_product_type=None)
    record['ukCopy']['sourceEvidence'] = original
    accepted = copy.deepcopy(raw);accepted['status'] = 'publishing'
    record['ukPublish']['sourceEvidence'] = accepted
    failure = evidence['failure'];failure.update(childCount=75, count=75, messageCount=150)
    failure['children'] = [{'childId': str(r['id']), 'sku': r['sku'], 'status': 'failed', 'imagesSource': 'child_gallery',
        'main': r['main_image'], 'images': r['extra']['images'], 'messages': [
            {'code': '100980', 'message': '条码 ' + r['standard_product_id'].zfill(14) + ' 已关联 B0BXRQ33RM'},
            {'code': '13013', 'message': '尚未进入型录'}]} for r in raw['items']]
    record['ukPublish']['latestObservation'] = copy.deepcopy(failure)
    record['ukPublish']['failureObservation'] = copy.deepcopy(failure)
    now = datetime.now(timezone.utc)
    historical = {'checkedAt': (now - timedelta(days=2)).isoformat(), 'store': prepared['store'], 'brand': 'Brand',
        'brandStatus': 'UPC豁免：允许销售', 'shippingTemplate': prepared['destination']['shippingTemplate'], 'handlingDays': '3'}
    record['ukPublish']['readiness'] = historical
    request = {'kind': 'check', 'method': 'POST', 'url': 'https://app.junfeikuajing.com/api/amazon/category/upc-exemption/check',
        'payload': {'seller_id': 'SELLER', 'country_code': 'GB', 'primary_category_name': 'Fashion', 'product_type_name': 'SWEATSHIRT', 'brand': 'bRaNd'},
        'sentAt': (now - timedelta(seconds=1)).isoformat(), 'response': {'httpStatus': 200, 'body': {'code': 0,
            'data': {'status': 'available', 'status_map': {'available': '允许销售'}}}}}
    expected = {key: failure[key] for key in ids.IDENTITY}
    fresh = {**{key: expected[key] for key in ('accountId', 'productId', 'jobId', 'snapshotSha256', 'publishId', 'schemaHash')},
        'observedAt': now.isoformat(), 'ui': {'url': 'https://www.junfeikuajing.com/#/amazon/product/202?type=publish',
        'store': prepared['store'], 'brand': 'Brand', 'nativeMarketId': '92', 'status': 'UPC豁免：允许销售'}, 'request': request,
        'guardProof': {'present': True, 'token': 'real-check-fixture', 'bindings': {'open': True, 'send': True, 'fetch': True},
                       'error': None, 'requests': [copy.deepcopy(request)]}}
    evidence.update(freshExemptionCheck=fresh, sourceFingerprint=ids.fingerprint(raw), sourceEvidenceFingerprint=ids.fingerprint(original),
                    introducedIdentifiers=ids.introduced_identifiers(raw))
    evidence['exemption'] = ids.existing_allowed_exemption_proof(record['ukPublish'], prepared, expected, fresh, raw)
    record['ukPublish']['requiredAttributeRepair'] = {'saveIntent': {'original': True}, 'retry': {'intent': {'consumed': True}}, 'keep': 'unchanged'}
    source['publicationRequiredAttributeRepair'] = {'id': 'original-required-amendment'}
    return job, record, source, evidence


class IdentifierTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.workspace = Path(tmp.name)
        self.root = self.workspace / 'studio-dev/listing-workbench/data/account-workspaces/2/publication-flow'
        self.enterContext(patch.object(flow, 'ROOT', self.root))
        self.enterContext(patch.object(flow, 'PROJECT', self.workspace / 'studio-dev'))
        self.enterContext(patch.object(flow.threading, 'Thread'))
        flow.ACTIVE.clear();self.addCleanup(flow.ACTIVE.clear)
        self.job, self.record, self.source, evidence = fixture()
        self.packet = {'input': self.source, 'connection': {'browserBinding': 'erp', 'page': 'p2'}}
        self.folder = self.root / 'job'
        flow.write_json(self.folder / 'input.json', self.packet);flow.write_json(self.folder / 'receipt.json', self.record)
        with flow.connect() as db, db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', ('job', 2, 'P', 'US', 'needs_reconciliation', json.dumps(self.job)))
        self.path = self.workspace / 'research-identifiers/current.json';flow.write_json(self.path, evidence)
        self.reference = {'path': str(self.path), 'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest()}
        self.payload = {'id': 'job', 'confirmed': True, 'repairIdentifiers': True, 'identifierEvidence': self.reference}

    def terminal(self):
        job = flow.owned(2, 'job');job['status'] = 'needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()

    def test_scope_matches_complete_fresh_data_except_observed_at_and_preserves_receipt_and_other_amendments(self):
        self.source['publicationMediaEpisodes'] = [{'id': 'old-keep'}]
        flow.write_json(self.folder / 'input.json', self.packet)
        before = (self.folder / 'receipt.json').read_bytes();flow.resume(2, self.payload)
        amended = json.loads((self.folder / 'input.json').read_text())
        scope = amended['input'].pop('publicationIdentifierRepair');self.assertEqual(amended, self.packet)
        self.assertEqual(scope['scope'], ids.SCOPE);self.assertEqual(len(scope['children']), 30)
        self.assertIsNone(scope['sourceIdentifiers']['parent']['standard_product_id'])
        self.assertEqual(scope['sourceIdentifiers']['parent']['standard_product_type'], 'UPC')
        self.assertEqual((self.folder / 'receipt.json').read_bytes(), before)
        self.terminal();frozen = (self.folder / 'input.json').read_bytes();flow.resume(2, {'id': 'job', 'confirmed': True})
        self.assertEqual((self.folder / 'input.json').read_bytes(), frozen)
        self.assertTrue(flow.owned(2, 'job')['identifierRepairOnly']);self.assertFalse(flow.owned(2, 'job').get('mediaEpisodeOnly'))
        self.terminal()
        with self.assertRaises(ValueError):flow.resume(2, self.payload)

    def test_wrong_real_source_identifier_partial_failure_gallery_brand_schema_or_exemption_never_freezes(self):
        changes = [lambda r,e:r['ukCopy']['sourceEvidence']['items'][0].update(standard_product_id='real-code'),
            lambda r,e:e['failure']['children'][0]['messages'].pop(),
            lambda r,e:e['response']['data']['items'][0]['extra']['images'].reverse(),
            lambda r,e:e['response']['data'].update(brand='Other'),lambda r,e:e['meta'].update(hash='wrong'),
            lambda r,e:r['ukPrepare']['brandExemption']['applyRequests'].append({})]
        for change in changes:
            r = copy.deepcopy(self.record);e = json.loads(self.path.read_text());change(r,e)
            with self.assertRaises(ValueError):ids.freeze_scope(self.job, r, self.source, e, self.reference)

    def test_research_evidence_hash_path_and_exclusive_flag_enforced(self):
        for extra in ({'observeOnly': True}, {'retryMediaEpisode': True}, {'repairIdentifiers': False}):
            with self.assertRaises(ValueError):flow.resume(2, {**self.payload, **extra})
        with self.assertRaises(ValueError):flow.resume(3, self.payload)
        bad = copy.deepcopy(self.payload);bad['identifierEvidence']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):flow.resume(2, bad)
        with self.assertRaises(ValueError):ids.read_evidence(self.workspace, {'path': str(self.workspace.parent / 'outside.json'), 'sha256': '0' * 64})

    def test_targeted_host_logs_into_uk_only_and_does_not_route_to_old_us_episode(self):
        flow.resume(2, self.payload);job = flow.owned(2, 'job')
        with patch.object(flow.collection, 'browser_lease', return_value=nullcontext()), \
                patch.object(flow, 'login') as login, patch.object(flow, 'run_browser', return_value=self.record) as run:
            flow.execute(job)
        self.assertEqual(login.call_args.args[2], 'UK');self.assertEqual(run.call_args.args[2], 'uk_identifiers')
        self.assertEqual(login.call_count, 1);self.assertEqual(run.call_count, 1)
        self.assertEqual(flow.owned(2, 'job')['status'], 'needs_reconciliation')


class SweatshirtIdentifierTests(unittest.TestCase):
    def test_75_profile_freezes_exact_null_restore_keeps_parent_upc_and_other_journals(self):
        job, record, source, evidence = sweatshirt_fixture();before = copy.deepcopy((record, source))
        scope = ids.freeze_scope(job, record, source, evidence, {'path': 'research/test.json', 'sha256': 'a' * 64})
        self.assertEqual(scope['identifierProfile'], ids.SWEATSHIRT_PROFILE)
        self.assertEqual(scope['childCount'], 75);self.assertEqual(len(scope['children']), 75)
        self.assertEqual(scope['sourceIdentifiers']['parent'], {'standard_product_type': 'UPC', 'standard_product_id': None})
        self.assertTrue(all(x == {'standard_product_type': None, 'standard_product_id': None} for x in scope['sourceIdentifiers']['children'].values()))
        self.assertEqual(scope['exemption']['singleApplyCount'], 0);self.assertEqual((record, source), before)

    def test_historical_allowed_alone_stale_cross_scope_apply_or_pending_never_authorizes(self):
        changes = [lambda r,e:e.pop('freshExemptionCheck'),
            lambda r,e:e['freshExemptionCheck'].update(observedAt=(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat()),
            lambda r,e:e['freshExemptionCheck'].update(accountId=3),
            lambda r,e:e['freshExemptionCheck']['ui'].update(nativeMarketId='other'),
            lambda r,e:e['freshExemptionCheck']['request']['payload'].update(seller_id='OTHER'),
            lambda r,e:e['freshExemptionCheck']['request']['payload'].update(product_type_name='SHIRT'),
            lambda r,e:e['freshExemptionCheck']['request'].update(kind='apply', url='https://app.junfeikuajing.com/api/amazon/category/upc-exemption/apply'),
            lambda r,e:e['freshExemptionCheck']['request']['response']['body']['data'].update(status='applying'),
            lambda r,e:e['freshExemptionCheck']['guardProof']['bindings'].update(fetch=False),
            lambda r,e:r['ukPublish']['readiness'].update(brand='Other')]
        for change in changes:
            with self.subTest(change=change):
                j,r,s,e=sweatshirt_fixture();change(r,e)
                with self.assertRaises(ValueError):ids.freeze_scope(j,r,s,e,{})

    def test_known_us_identifier_mismatched_barcode_mixed_error_or_business_change_blocks(self):
        changes = [lambda r,e:r['ukCopy']['sourceEvidence']['items'][0].update(standard_product_id='real-id'),
            lambda r,e:e['failure']['children'][0]['messages'][0].update(message='条码 00999999999999'),
            lambda r,e:e['failure']['children'][0]['messages'][0].update(code='8566'),
            lambda r,e:e['response']['data']['items'][0].update(price='99.00'),
            lambda r,e:e['response']['data']['items'][0].update(asin='B0BXRQ33RM'),
            lambda r,e:e['response']['data']['items'][0]['extra']['images'].reverse(),
            lambda r,e:e['response']['data']['items'][0].pop('standard_product_type')]
        for change in changes:
            with self.subTest(change=change):
                j,r,s,e=sweatshirt_fixture();change(r,e)
                r['ukPublish']['latestObservation']=copy.deepcopy(e['failure'])
                e['sourceFingerprint']=ids.fingerprint(e['response']['data']);e['sourceEvidenceFingerprint']=ids.fingerprint(r['ukCopy']['sourceEvidence']);e['introducedIdentifiers']=ids.introduced_identifiers(e['response']['data']) if 'standard_product_type' in e['response']['data']['items'][0] else {}
                with self.assertRaises(ValueError):ids.freeze_scope(j,r,s,e,{})

    def test_stale_canonical_accepted_and_wrong_type_or_count_do_not_use_fresh_artifact_as_override(self):
        for mutate in (lambda r:r['ukPublish']['latestObservation'].update(verification='accepted', failed=False),
                       lambda r:r['ukPrepare']['schemaObservation'].update(product_type_name='SHIRT'),
                       lambda r:r['ukPrepare']['preparedInput']['goodsItems'].pop()):
            j,r,s,e=sweatshirt_fixture();mutate(r)
            with self.assertRaises(ValueError):ids.freeze_scope(j,r,s,e,{})

    def test_formal_resume_keeps_old_required_intents_and_reuses_only_original_identifier_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory);root=workspace/'studio-dev/listing-workbench/data/account-workspaces/2/publication-flow'
            with patch.object(flow,'ROOT',root), patch.object(flow,'PROJECT',workspace/'studio-dev'), patch.object(flow.threading,'Thread'):
                flow.ACTIVE.clear();j,r,s,e=sweatshirt_fixture();packet={'input':s,'connection':{'browserBinding':'erp','page':'p2'}};folder=root/'job'
                flow.write_json(folder/'input.json',packet);flow.write_json(folder/'receipt.json',r)
                with flow.connect() as db,db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',('job',2,'P','US','needs_reconciliation',json.dumps(j)))
                path=workspace/'research-identifiers/fresh.json';flow.write_json(path,e)
                payload={'id':'job','confirmed':True,'repairIdentifiers':True,'identifierEvidence':{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
                receipt_before=(folder/'receipt.json').read_bytes();flow.resume(2,payload)
                amended=json.loads((folder/'input.json').read_text());scope=amended['input'].pop('publicationIdentifierRepair')
                self.assertEqual(amended,packet);self.assertEqual(scope['childCount'],75);self.assertEqual((folder/'receipt.json').read_bytes(),receipt_before)
                job=flow.owned(2,'job');job['status']='needs_reconciliation';flow.persist(job);flow.ACTIVE.clear();frozen=(folder/'input.json').read_bytes()
                flow.resume(2,{'id':'job','confirmed':True});self.assertEqual((folder/'input.json').read_bytes(),frozen)
                job=flow.owned(2,'job');job['status']='needs_reconciliation';flow.persist(job);flow.ACTIVE.clear()
                with self.assertRaises(ValueError):flow.resume(2,payload)
                flow.ACTIVE.clear()


if __name__ == '__main__':unittest.main()
