import copy
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

import discovery_browser as browser
RUN_LOCAL_FIXTURE = subprocess.run


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cli = self.root / 'ego.exe'
        self.cli.touch()
        self.request = dict(captureId='capture1', cycleId='cycle', expectedRevision=2, parentId='search1', asin='B012345678')
        self.parent = dict(id='search1', kind='search', marketplace='US', products=[{'asin': 'B012345678'}], url='https://amazon.com/s?k=fixture', observedAt=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
        self.report = dict(revision=2, events=[self.parent])
        self.config = {'browser': {'engine': 'ego-lite', 'cli': str(self.cli), 'task_space_id': 4, 'task_space_name': 'erp'}, 'discovery_browser': {'engine': 'ego-lite', 'cli': str(self.cli), 'account_bindings': {'1': {'enabled': True, 'task_space_id': 3, 'task_space_name': 'fixture', 'page_label': 'p2'}}}}
        self.patches = [patch.object(browser, 'DB', self.root / 'discovery_browser.sqlite3'), patch.object(browser.ledger, 'report', side_effect=lambda *a: copy.deepcopy(self.report)), patch.object(browser.runtime_environment, 'configuration', side_effect=lambda: copy.deepcopy(self.config)), patch.object(browser.subprocess, 'run', side_effect=self.run_capture)]
        self.mocks = [p.start() for p in self.patches]
        self.raw = dict(schemaVersion=1, status='captured', reason='visible_sold_by_link_observed', url='https://amazon.com/dp/B012345678', capturedAt=datetime.now(timezone.utc).isoformat(), title='Fixture product', asin='B012345678', marketplace='US', sellerId='SELLER1', sellerName='Fixture Seller', sellerLabel='Sold by Fixture Seller', sellerLink='https://amazon.com/sp?seller=SELLER1', sellerLinkSource='visible_sold_by_link', evidence={'selector': '#merchant-info', 'labelText': 'Sold by Fixture Seller', 'anchorText': 'Fixture Seller', 'anchorHref': 'https://amazon.com/sp?seller=SELLER1'})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def run_capture(self, args, **kwargs):
        self.assertEqual(args[:3], [str(self.cli), 'nodejs', '-e'])
        self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        self.assertLessEqual(kwargs['timeout'], 45)
        directory = Path(kwargs['cwd'])
        script = (directory / 'capture.mjs').read_text(encoding='utf-8')
        for forbidden in ('takeOverTaskSpace', '.goto(', '.reload(', '.click(', 'newPage(', '.fetch(', '.cookies(', 'localStorage'):
            self.assertNotIn(forbidden, script)
        self.assertIn("s.ownership==='agent'", script)
        self.assertIn('taskSpace(p.spaceId)', script)
        self.assertIn('after[0].targetId!==before[0].targetId', script)
        self.assertLess(script.index('await task.tabs()'), script.index('task.page(p.label)'))
        self.assertIn("flag:'wx'", script)
        (directory / 'result.json').write_text(json.dumps(self.raw), encoding='utf-8')
        return subprocess.CompletedProcess(args, 0)

    def test_capture_replay_and_isolation(self):
        result = browser.capture(1, self.request)
        self.assertEqual(result['status'], 'captured')
        self.assertFalse(result['qualificationEvaluated'])
        self.assertEqual(result, browser.capture(1, self.request))
        self.assertEqual(self.mocks[-1].call_count, 1)
        self.assertEqual(browser.detail(1, 'capture1'), result)
        self.assertEqual(browser.history(2), {'items': []})
        with self.assertRaises(ValueError): browser.detail(2, 'capture1')
        with self.assertRaises(ValueError): browser.capture(1, {**self.request, 'asin': 'B012345679'})
        self.assertEqual(set(p.name for p in self.root.iterdir()), {'ego.exe', 'discovery_browser.sqlite3', 'discovery-captures'})


    def test_observed_us_combined_seller_label_and_ref_link(self):
        self.raw['sellerLabel']='Shipper / Seller Fixture Seller'
        self.raw['sellerLink']='https://amazon.com/gp/help/seller/at-a-glance.html/ref=dp_merchant_link?seller=SELLER1'
        self.raw['evidence'].update(labelText=self.raw['sellerLabel'],anchorHref=self.raw['sellerLink'])
        result=browser.capture(1,self.request)
        self.assertEqual(result['status'],'captured')
        expected='https://amazon.com/gp/help/seller/at-a-glance.html?seller=SELLER1'
        self.assertEqual(result['preparedBatch']['events'][0]['sellerLink'],expected)
        self.assertEqual(result['evidence']['anchorHref'],expected)
        self.assertFalse(result['qualificationEvaluated'])
        for n,label in enumerate(('Shipper Fixture Seller','Ships from Fixture Seller','Not a Shipper / Seller Fixture Seller')):
            self.raw['sellerLabel']=label;self.raw['evidence']['labelText']=label
            failed=browser.capture(1,{**self.request,'captureId':'label-'+str(n)})
            self.assertEqual(failed['status'],'blocked')
            self.assertNotIn('preparedBatch',failed)

    def test_missing_binding_and_target_modes_fail_closed(self):
        for n, (key, value) in enumerate([('account_bindings', {}), ('engine', 'edge'), ('cli', 'ego.exe'), ('cli', None)]):
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                self.config['discovery_browser'][key] = value
                result = browser.capture(1, {**self.request, 'captureId': key + str(n)})
                self.assertEqual(result['status'], 'configuration_blocked')
                self.config = config
        self.mocks[-1].assert_not_called()

    def test_dedicated_route_independent_of_erp(self):
        original = copy.deepcopy(self.config)
        route, fingerprint = browser._binding(1)
        self.assertEqual(route['spaceId'], 3)
        self.assertEqual(browser.capture(1, self.request)['target']['taskSpaceId'], 3)
        self.assertEqual(self.config, original)
        self.config['browser'].update(task_space_id=9, task_space_name='other-erp', cli='ignored.exe', engine='other')
        self.config['pricing'] = {'margin': 0.3}
        self.config['discovery_browser']['account_bindings']['2'] = {'enabled': False}
        self.assertEqual(browser._binding(1), (route, fingerprint))

    def test_legacy_only_and_missing_section_never_dispatch(self):
        dedicated = self.config.pop('discovery_browser')
        self.config['browser']['discovery_account_bindings'] = dedicated['account_bindings']
        self.config['browser'].update(task_space_id=3, task_space_name='fixture')
        for n, section in enumerate(('absent', None, {}, [])):
            if section != 'absent': self.config['discovery_browser'] = section
            result = browser.capture(1, {**self.request, 'captureId': 'legacy-' + str(n)})
            self.assertEqual(result['status'], 'configuration_blocked')
        self.mocks[-1].assert_not_called()

    def test_cli_never_falls_back_to_erp(self):
        for n, cli in enumerate((None, '', 'ego.exe', str(self.root / 'missing.exe'))):
            self.config['discovery_browser']['cli'] = cli
            result = browser.capture(1, {**self.request, 'captureId': 'cli-' + str(n)})
            self.assertEqual(result['status'], 'configuration_blocked')
        del self.config['discovery_browser']['cli']
        self.assertEqual(browser.capture(1, self.request)['status'], 'configuration_blocked')
        self.mocks[-1].assert_not_called()

    def test_erp_collision_never_dispatches(self):
        self.config['browser']['task_space_id'] = 3
        with self.assertRaisesRegex(ValueError, 'discovery_space_collides_with_erp'):
            browser._binding(1)
        self.assertEqual(browser.capture(1, self.request)['status'], 'configuration_blocked')
        self.mocks[-1].assert_not_called()

    def test_scope_changes_before_and_after_dispatch(self):
        original = copy.deepcopy(self.config)
        original_script = browser._script
        mutations = {
            'label': lambda: self.config['discovery_browser']['account_bindings']['1'].update(page_label='other'),
            'space': lambda: self.config['discovery_browser']['account_bindings']['1'].update(task_space_id=8),
            'name': lambda: self.config['discovery_browser']['account_bindings']['1'].update(task_space_name='other'),
            'disabled': lambda: self.config['discovery_browser']['account_bindings']['1'].update(enabled=False),
            'cli': lambda: self.config['discovery_browser'].update(cli=str(Path(__file__).resolve())),
            'engine': lambda: self.config['discovery_browser'].update(engine='edge'),
            'collision': lambda: self.config['browser'].update(task_space_id=3),
        }
        for phase in ('before', 'after'):
            for name, mutate in mutations.items():
                with self.subTest(phase=phase, change=name):
                    self.config = copy.deepcopy(original)
                    self.mocks[-1].reset_mock()
                    def script(*args):
                        result = original_script(*args)
                        if phase == 'before': mutate()
                        return result
                    def run(*args, **kwargs):
                        result = self.run_capture(*args, **kwargs)
                        if phase == 'after': mutate()
                        return result
                    self.mocks[-1].side_effect = run
                    with patch.object(browser, '_script', side_effect=script):
                        result = browser.capture(1, {**self.request, 'captureId': phase + '-' + name})
                    self.assertEqual(result['status'], 'blocked')
                    self.assertNotIn('preparedBatch', result)
                    self.assertEqual(self.mocks[-1].call_count, int(phase == 'after'))

    def test_unrelated_edits_during_capture_do_not_change_scope(self):
        original_script = browser._script
        def unrelated():
            self.config['browser'].update(task_space_id=8, task_space_name='other-erp', cli='irrelevant')
            self.config['pricing'] = {'margin': 0.5}
        def script(*args):
            result = original_script(*args)
            unrelated()
            return result
        def run(*args, **kwargs):
            result = self.run_capture(*args, **kwargs)
            self.config['browser']['task_space_id'] = 9
            self.config['pricing']['margin'] = 0.6
            return result
        self.mocks[-1].side_effect = run
        with patch.object(browser, '_script', side_effect=script):
            result = browser.capture(1, self.request)
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(result['target']['taskSpaceId'], 3)

    def test_invalid_parent_and_revision(self):
        for changes in ({'parentId': 'missing'}, {'expectedRevision': 1}, {'asin': 'B012345679'}):
            result = browser.capture(1, {**self.request, **changes, 'captureId': 'c' + str(len(browser.history(1)['items']))})
            self.assertEqual(result['status'], 'blocked')
        self.mocks[-1].assert_not_called()

    def test_unknown_never_retries_or_trusts_late_file(self):
        self.mocks[-1].side_effect = subprocess.TimeoutExpired('fixture', 45)
        result = browser.capture(1, self.request)
        self.assertEqual(result['status'], 'execution_unknown')
        for directory in (self.root / 'discovery-captures' / '1').iterdir():
            (directory / 'result.json').write_text(json.dumps(self.raw))
        self.assertEqual(browser.capture(1, self.request), result)
        self.assertEqual(browser.capture(1, {**self.request, 'captureId': 'next'})['reason'], 'prior_capture_unresolved')
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_concurrent_same_key_once(self):
        entered, release = threading.Event(), threading.Event()
        def run(*args, **kwargs):
            entered.set()
            release.wait(5)
            return self.run_capture(*args, **kwargs)
        self.mocks[-1].side_effect = run
        results = []
        thread = threading.Thread(target=lambda: results.append(browser.capture(1, self.request)))
        thread.start()
        self.assertTrue(entered.wait(5))
        try:
            self.assertEqual(browser.capture(1, self.request)['status'], 'capture_started')
            self.assertEqual(browser.capture(1, {**self.request, 'captureId': 'other'})['status'], 'blocked')
        finally:
            release.set()
            thread.join(5)
        self.assertEqual(results[0]['status'], 'captured')
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_post_capture_revision_or_config_change(self):
        for kind in ('revision', 'config'):
            def run(*args, **kwargs):
                result = self.run_capture(*args, **kwargs)
                if kind == 'revision': self.report['revision'] = 3
                else: self.config['discovery_browser']['account_bindings']['1']['page_label'] = 'changed'
                return result
            self.mocks[-1].side_effect = run
            result = browser.capture(1, {**self.request, 'captureId': kind})
            self.assertEqual(result['status'], 'blocked')
            self.assertNotIn('preparedBatch', result)
            self.report['revision'] = 2

    def test_forged_blocked_and_stale_evidence(self):
        variants = [{'status': 'blocked', 'reason': 'SECRET'}, {'asin': 'B012345679'}, {'marketplace': 'UK'}, {'sellerLinkSource': 'brand'}, {'capturedAt': self.parent['observedAt']}, {'evidence': {**self.raw['evidence'], 'anchorText': 'Forgery'}}, {'evidence': {**self.raw['evidence'], 'anchorHref': 'https://evil.test/sp?seller=SELLER1'}}]
        original = copy.deepcopy(self.raw)
        for n, changes in enumerate(variants):
            self.raw = {**original, **changes}
            result = browser.capture(1, {**self.request, 'captureId': 'variant' + str(n)})
            self.assertEqual(result['status'], 'blocked')
            self.assertNotIn('preparedBatch', result)
            self.assertNotIn('SECRET', json.dumps(result))

    def test_unknown_fields_removed_and_request_restricted(self):
        self.raw['secret'] = 'do-not-return'
        result = browser.capture(1, self.request)
        self.assertNotIn('do-not-return', json.dumps(result))
        for value in (True, 0, '1'):
            with self.assertRaises(ValueError): browser.capture(value, self.request)
        with self.assertRaises(ValueError): browser.capture(1, {**self.request, 'script': 'alert(1)'})

    @unittest.skipUnless(shutil.which('node'), 'Node required for offline script fixture')
    def test_offline_node_ownership_tab_and_after_checks(self):
        binding, _ = browser._binding(1)
        cases = [('agent', 'p2', False, 'captured'), ('agentDelegatedToUser', 'p2', False, 'blocked'), ('agent', 'p9', False, 'blocked'), ('agent', 'p2', True, 'blocked'), ('throws', 'p2', False, 'execution_unknown')]
        for n, (ownership, label, change, status) in enumerate(cases):
            output = self.root / ('node-result-' + str(n) + '.json')
            fixture = '''
globalThis.listTaskSpaces=async()=>{if(OWNERSHIP==='throws')throw Error('fixture');return [{id:3,name:'fixture',ownership:OWNERSHIP}];};
let calls=0, evaluations=0, tabs=0, resumes=0;
globalThis.taskSpace=async id=>{
 resumes++;
 if(id!==3 || typeof id!=='number') throw Error('unexpected space');
 return {spaceId:3,name:'fixture',ownership:OWNERSHIP,
 tabs:async()=>{tabs++;return [{label:LABEL,targetId:CHANGE && calls++ ? 'changed':'stable',url:'https://amazon.com/gp/product/B012345678'}];},
 page: label=>{if(label!=='p2') throw Error('unexpected page');return {evaluate:async fn=>{evaluations++;return RAW;}};}};
};
'''.replace('OWNERSHIP', json.dumps(ownership)).replace('LABEL', json.dumps(label)).replace('CHANGE', json.dumps(change)).replace('RAW', json.dumps(self.raw))
            script = self.root / ('fixture-' + str(n) + '.mjs')
            assertions = "\nif(evaluations!==%d || tabs!==%d || resumes!==%d)throw Error('fixture call count');" % ((1 if ownership == 'agent' and label == 'p2' else 0), (2 if ownership == 'agent' and label == 'p2' else 1 if ownership == 'agent' else 0), (1 if ownership == 'agent' else 0))
            script.write_text(fixture + browser._script(binding, self.request, 'US', output) + assertions, encoding='utf-8')
            result = RUN_LOCAL_FIXTURE([shutil.which('node'), str(script)], capture_output=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['status'], status)




REAL_LEDGER_REPORT = browser.ledger.report


class StoreCaptureTests(unittest.TestCase):
    tearDown = CaptureTests.tearDown
    run_capture = CaptureTests.run_capture

    def setUp(self):
        CaptureTests.setUp(self)
        self.seller_request = copy.deepcopy(self.request)
        self.seller_raw = copy.deepcopy(self.raw)
        self.search_parent = copy.deepcopy(self.parent)
        self.request = dict(captureId='store1', cycleId='cycle', expectedRevision=2, parentId='seller1', sellerId='SELLER1')
        self.parent = {k: v for k, v in self.seller_raw.items() if k not in ('schemaVersion', 'status', 'reason', 'capturedAt', 'title', 'evidence')}
        self.parent.update(id='seller1', kind='seller', parentId='search1', sourceType='browser_visible', observedAt=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat())
        self.report = dict(revision=2, events=[self.search_parent, self.parent])
        now = datetime.now(timezone.utc).isoformat()
        self.raw = dict(schemaVersion=1, status='captured', reason='visible_seller_listing_observed', url='https://www.amazon.com/s?me=SELLER1&marketplaceID=ATVPDKIKX0DER&token=SECRET', capturedAt=now, marketplace='US', sellerId='SELLER1', products=[{'asin': 'B012345679', 'title': 'Visible other product', 'productURL': 'https://amazon.com/Other/dp/B012345679/ref=sr_1_1?m=SELLER1&marketplaceID=ATVPDKIKX0DER&token=SECRET'}], evidence={'selector': browser.STORE_SELECTOR, 'sourceURL': 'https://amazon.com/s?me=SELLER1', 'sellerId': 'SELLER1', 'marketplace': 'US', 'capturedAt': now, 'cards': [{'asin': 'B012345679', 'cardAsin': 'B012345679', 'title': 'Visible other product', 'anchorHref': 'https://amazon.com/dp/B012345679', 'cardSelector': browser.STORE_CARD_SELECTOR, 'titleSelector': browser.STORE_TITLE_SELECTOR, 'visible': True, 'sponsored': False}]})

    def test_store_capture_prepared_only_and_replay(self):
        with patch.object(browser.ledger, 'ingest', side_effect=AssertionError('must not ingest')):
            result = browser.capture_store(1, self.request)
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(result['captureKind'], 'store')
        self.assertEqual(result['sourceURL'], 'https://amazon.com/s?me=SELLER1')
        for key in ('qualificationEvaluated','executionAllowed','publicationAllowed'): self.assertFalse(result[key])
        for key in ('qualifiedCount','paidExternalCallsPerformed'): self.assertEqual(result[key],0)
        event = result['preparedBatch']['events'][0]
        self.assertEqual(event['kind'], 'store');self.assertEqual(event['parentId'], 'seller1')
        self.assertEqual(event['products'], [{'asin': 'B012345679', 'title': 'Visible other product'}])
        self.assertEqual(result['evidence']['cards'][0]['productURL'], 'https://amazon.com/dp/B012345679')
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result, browser.capture_store(1, self.request))
        self.assertEqual(result, browser.detail(1, 'store1'))
        self.assertEqual(self.mocks[-1].call_count, 1)
        self.assertEqual(browser.history(2), {'items': []})
        with self.assertRaises(ValueError): browser.detail(2, 'store1')
        self.assertEqual(self.report['revision'], 2)

    def test_exact_store_request_contract(self):
        for changes in ({'script': 'evil'}, {'owner': 2}, {'asin': 'B012345678'}, {'marketplace': 'US'}, {'expectedRevision': True}, {'expectedRevision': -1}, {'sellerId': 'bad'}, {'sellerId': 'X'*31}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): browser.capture_store(1, {**self.request, **changes})
        for key in self.request:
            request = dict(self.request); request.pop(key)
            with self.assertRaises(ValueError): browser.capture_store(1, request)
        for owner in (True, 0, '1'):
            with self.assertRaises(ValueError): browser.capture_store(owner, self.request)
        self.mocks[-1].assert_not_called()

    def test_store_requires_exact_parent_seller_revision_and_observation(self):
        for n, changes in enumerate(({'parentId': 'search1'}, {'parentId': 'missing'}, {'sellerId': 'OTHER1'}, {'expectedRevision': 1})):
            self.assertEqual(browser.capture_store(1, {**self.request, **changes, 'captureId': 'bad-request-'+str(n)})['reason'], 'parent_or_revision_invalid')
        original = copy.deepcopy(self.parent)
        for n, changes in enumerate(({'kind': 'keyword'}, {'sourceType': 'brand'}, {'sellerLinkSource': 'brand'}, {'marketplace': 'UK'}, {'sellerId': 'OTHER1'}, {'sellerLink': 'https://amazon.com/stores/Brand'}, {'observedAt': 'no-time'})):
            self.parent.clear(); self.parent.update({**original, **changes})
            self.assertEqual(browser.capture_store(1, {**self.request, 'captureId': 'bad-parent-'+str(n)})['reason'], 'parent_or_revision_invalid')
        self.mocks[-1].assert_not_called()

    def test_parent_lookup_is_account_and_cycle_scoped(self):
        when = (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        keyword = dict(id='keyword1', kind='keyword', parentId=None, sourceType='browser_visible', marketplace='US', observedAt=when, url='https://amazon.com/dp/B012345678', asin='B012345678', sourceTitle='Fixture product', phrase='Fixture')
        search = {**self.search_parent, 'parentId': 'keyword1', 'sourceType': 'browser_visible', 'query': 'Fixture', 'url': 'https://amazon.com/s?k=Fixture', 'products': [{'asin': 'B012345678', 'title': 'Fixture product'}]}
        with patch.object(browser.ledger, 'DB', self.root/'ledger.sqlite3'), patch.object(browser.ledger, 'report', side_effect=REAL_LEDGER_REPORT):
            browser.ledger.ingest(1, dict(cycleId='cycle', expectedRevision=0, events=[keyword, search, self.parent]))
            self.config['discovery_browser']['account_bindings']['2'] = copy.deepcopy(self.config['discovery_browser']['account_bindings']['1'])
            self.assertEqual(browser.capture_store(2, {**self.request, 'expectedRevision': 1})['reason'], 'parent_or_revision_invalid')
            self.assertEqual(browser.capture_store(1, {**self.request, 'captureId': 'wrong-cycle', 'cycleId': 'other', 'expectedRevision': 1})['reason'], 'parent_or_revision_invalid')
            self.assertEqual(browser.capture_store(1, {**self.request, 'expectedRevision': 1})['status'], 'captured')
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_store_and_seller_capture_ids_share_one_namespace(self):
        self.assertEqual(browser.capture_store(1, self.request)['status'], 'captured')
        with self.assertRaisesRegex(ValueError, 'Conflicting captureId'): browser.capture(1, {**self.seller_request, 'captureId': self.request['captureId']})
        with self.assertRaisesRegex(ValueError, 'Conflicting captureId'): browser.capture_store(1, {**self.request, 'sellerId': 'OTHER1'})
        self.raw = self.seller_raw
        self.assertEqual(browser.capture(1, self.seller_request)['status'], 'captured')
        with self.assertRaisesRegex(ValueError, 'Conflicting captureId'): browser.capture_store(1, {**self.request, 'captureId': self.seller_request['captureId']})
        self.assertEqual(self.mocks[-1].call_count, 2)

    def test_legacy_seller_receipt_replays_without_capture_kind(self):
        old = {**self.seller_request, 'status': 'captured', 'reason': 'legacy-fixture'}
        conn = browser._connect(True)
        try:
            conn.execute('INSERT INTO attempts VALUES (?,?,?,?,?)', (1, self.seller_request['captureId'], browser._digest(self.seller_request), 'captured', json.dumps(old))); conn.commit()
        finally: conn.close()
        self.assertEqual(browser.capture(1, self.seller_request), old);self.mocks[-1].assert_not_called()

    def test_store_unknown_blocks_both_kinds_and_never_trusts_late_file(self):
        self.mocks[-1].side_effect = subprocess.TimeoutExpired('fixture', 45)
        unknown = browser.capture_store(1, self.request);self.assertEqual(unknown['status'], 'execution_unknown')
        for directory in (self.root/'discovery-captures'/'1').iterdir(): (directory/'result.json').write_text(json.dumps(self.raw), encoding='utf-8')
        self.assertEqual(browser.capture_store(1, self.request), unknown)
        self.assertEqual(browser.capture_store(1, {**self.request, 'captureId': 'later'})['reason'], 'prior_capture_unresolved')
        self.assertEqual(browser.capture(1, self.seller_request)['reason'], 'prior_capture_unresolved');self.assertEqual(self.mocks[-1].call_count, 1)

    def test_seller_unknown_blocks_store(self):
        self.mocks[-1].side_effect = subprocess.TimeoutExpired('fixture', 45)
        self.assertEqual(browser.capture(1, self.seller_request)['status'], 'execution_unknown')
        self.assertEqual(browser.capture_store(1, self.request)['reason'], 'prior_capture_unresolved');self.assertEqual(self.mocks[-1].call_count, 1)

    def test_concurrent_store_replay_and_seller_block(self): self._concurrent(True)
    def test_concurrent_seller_blocks_store(self): self._concurrent(False)

    def _concurrent(self, store_first):
        entered, release = threading.Event(), threading.Event()
        if not store_first: self.raw = self.seller_raw
        def run(*args, **kwargs):
            entered.set(); release.wait(5); return self.run_capture(*args, **kwargs)
        self.mocks[-1].side_effect = run
        first = browser.capture_store if store_first else browser.capture
        request = self.request if store_first else self.seller_request
        results=[];errors=[]
        def worker():
            try: results.append(first(1, request))
            except Exception as exc: errors.append(exc)
        thread=threading.Thread(target=worker);thread.start();self.assertTrue(entered.wait(5))
        try:
            self.assertEqual(first(1, request)['status'], 'capture_started')
            self.assertEqual(browser.capture_store(1, {**self.request, 'captureId':'parallel-store'})['reason'], 'prior_capture_unresolved')
            self.assertEqual(browser.capture(1, {**self.seller_request, 'captureId':'parallel-seller'})['reason'], 'prior_capture_unresolved')
        finally: release.set();thread.join(5)
        self.assertFalse(errors);self.assertEqual(results[0]['status'], 'captured');self.assertEqual(self.mocks[-1].call_count, 1)

    def test_store_source_and_card_evidence_rejected(self):
        original = copy.deepcopy(self.raw)
        changes = [lambda r:r.update(schemaVersion=True), lambda r:r.update(sellerId='OTHER1'), lambda r:r.update(marketplace='UK'), lambda r:r.update(url='https://amazon.com/stores/Brand?me=SELLER1'), lambda r:r.update(url='https://amazon.com/s?me=OTHER1'), lambda r:r.update(url='https://amazon.co.uk/s?me=SELLER1'), lambda r:r.update(url='https://amazon.com/s?me=SELLER1&ME=SELLER1'), lambda r:r.update(url='https://amazon.com/s?me=SELLER1&seller=OTHER1'), lambda r:r.update(url='https://amazon.com/s?me=SELLER1&marketplaceID=A1F83G8C2ARO7P'), lambda r:r.update(capturedAt=self.parent['observedAt']), lambda r:r.update(capturedAt=datetime.now().isoformat()), lambda r:r.update(capturedAt=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()), lambda r:r.update(products=[]), lambda r:r['products'].append(copy.deepcopy(r['products'][0])), lambda r:r['evidence'].update(sourceURL='https://amazon.com/s?me=OTHER1'), lambda r:r['evidence'].update(sellerId='OTHER1'), lambda r:r['evidence'].update(marketplace='UK'), lambda r:r['evidence'].update(capturedAt=self.parent['observedAt']), lambda r:r['evidence'].update(selector='.recommendations'), lambda r:r['evidence'].update(cards=[]), lambda r:r['evidence']['cards'][0].update(visible=False), lambda r:r['evidence']['cards'][0].update(visible=1), lambda r:r['evidence']['cards'][0].update(sponsored=True), lambda r:r['evidence']['cards'][0].update(sponsored=0), lambda r:r['evidence']['cards'][0].update(cardAsin='B012345678'), lambda r:r['evidence']['cards'][0].update(asin='B012345678'), lambda r:r['evidence']['cards'][0].update(title='Other title'), lambda r:r['evidence']['cards'][0].update(cardSelector='.carousel'), lambda r:r['evidence']['cards'][0].update(titleSelector='brand'), lambda r:r['evidence']['cards'][0].update(anchorHref='https://amazon.com/dp/B012345678'), lambda r:r['products'][0].update(productURL='https://evil.test/dp/B012345679'), lambda r:r['products'][0].update(productURL='https://amazon.com/dp/B012345679?m=OTHER1'), lambda r:r['products'][0].update(productURL='https://amazon.com/dp/B012345679?marketplaceID=A1F83G8C2ARO7P')]
        for n, mutate in enumerate(changes):
            with self.subTest(n=n):
                self.raw=copy.deepcopy(original);mutate(self.raw)
                result=browser.capture_store(1,{**self.request,'captureId':'bad-evidence-'+str(n)})
                self.assertEqual(result['status'],'blocked');self.assertNotIn('preparedBatch',result);self.assertNotIn('SECRET',json.dumps(result))

    def test_store_block_reasons_are_sanitized_and_empty_not_captured(self):
        for n, reason in enumerate(('SECRET','no_visible_store_products','captcha_or_challenge')):
            self.raw={'schemaVersion':1,'status':'blocked','reason':reason}
            result=browser.capture_store(1,{**self.request,'captureId':'block-'+str(n)})
            self.assertEqual(result['status'],'blocked');self.assertEqual(result['reason'],'browser_capture_blocked' if reason=='SECRET' else reason);self.assertNotIn('preparedBatch',result)

    def test_unknown_fields_are_not_retained(self):
        self.raw['secret']='DROP-ME';self.raw['evidence']['secret']='DROP-ME';self.raw['products'][0]['secret']='DROP-ME';self.raw['evidence']['cards'][0]['secret']='DROP-ME'
        result=browser.capture_store(1,self.request);self.assertEqual(result['status'],'captured');self.assertNotIn('DROP-ME',json.dumps(result))

    def test_scope_change_before_and_after_store_dispatch(self):
        original_config=copy.deepcopy(self.config);original_parent=copy.deepcopy(self.parent);original_script=browser._store_script
        mutations={'label':lambda:self.config['discovery_browser']['account_bindings']['1'].update(page_label='changed'),'owner':lambda:self.config['discovery_browser']['account_bindings'].pop('1'),'collision':lambda:self.config['browser'].update(task_space_id=3),'revision':lambda:self.report.update(revision=3),'parent':lambda:self.parent.update(sellerName='Changed Seller')}
        for phase in ('before','after'):
            for name, mutate in mutations.items():
                with self.subTest(phase=phase,name=name):
                    self.config=copy.deepcopy(original_config);self.parent.clear();self.parent.update(original_parent);self.report['revision']=2;self.mocks[-1].reset_mock()
                    def script(*args):
                        result=original_script(*args)
                        if phase=='before':mutate()
                        return result
                    def run(*args,**kwargs):
                        result=self.run_capture(*args,**kwargs)
                        if phase=='after':mutate()
                        return result
                    self.mocks[-1].side_effect=run
                    with patch.object(browser,'_store_script',side_effect=script): result=browser.capture_store(1,{**self.request,'captureId':phase+'-'+name})
                    self.assertEqual(result['status'],'blocked');self.assertNotIn('preparedBatch',result);self.assertEqual(self.mocks[-1].call_count,int(phase=='after'))

    def test_store_collector_change_before_or_after_dispatch_is_blocked(self):
        file=self.root/'collector.js';original=browser.STORE_COLLECTOR.read_bytes();original_script=browser._store_script
        for phase in ('before','after'):
            file.write_bytes(original);self.mocks[-1].reset_mock()
            def mutate():file.write_bytes(original+b'\n/* changed */\n')
            def script(*args):
                result=original_script(*args)
                if phase=='before':mutate()
                return result
            def run(*args,**kwargs):
                result=self.run_capture(*args,**kwargs)
                if phase=='after':mutate()
                return result
            self.mocks[-1].side_effect=run
            with patch.object(browser,'STORE_COLLECTOR',file),patch.object(browser,'_store_script',side_effect=script): result=browser.capture_store(1,{**self.request,'captureId':'collector-'+phase})
            self.assertEqual(result['status'],'blocked');self.assertNotIn('preparedBatch',result);self.assertEqual(self.mocks[-1].call_count,int(phase=='after'))

    def test_store_has_no_erp_fallback(self):
        self.config.pop('discovery_browser');result=browser.capture_store(1,self.request)
        self.assertEqual(result['status'],'configuration_blocked');self.mocks[-1].assert_not_called()

    @unittest.skipUnless(shutil.which('node'),'Node required for offline script fixture')
    def test_store_script_identity_and_ownership_guards(self):
        binding,_=browser._binding(1);good='https://www.amazon.com/s?me=SELLER1&marketplaceID=ATVPDKIKX0DER'
        cases=[({},'captured',1),({'ownership':'agentDelegatedToUser'},'blocked',0),({'label':'other'},'blocked',0),({'duplicate':True},'blocked',0),({'afterTarget':'changed'},'blocked',1),({'afterUrl':good+'&ref=changed'},'blocked',1),({'afterOwnership':'agentDelegatedToUser'},'blocked',1),({'throw':True},'execution_unknown',0)]
        cases += [({'url':url},'blocked',0) for url in ('https://amazon.com/s?k=product','https://amazon.com/stores/Brand?me=SELLER1','https://amazon.com/s?me=OTHER1','https://amazon.co.uk/s?me=SELLER1','https://amazon.com/s?me=SELLER1&ME=SELLER1','https://amazon.com/s?me=SELLER1&seller=OTHER1','https://amazon.com/s?me=SELLER1&marketplaceID=A1F83G8C2ARO7P','https://amazon.com/evil/../s?me=SELLER1')]
        for n,(changes,status,evaluations) in enumerate(cases):
            options={'ownership':'agent','label':'p2','url':good,**changes};output=self.root/('store-node-'+str(n)+'.json')
            fixture=r'''
const o=OPTIONS;let tabs=0,evaluations=0;
globalThis.listTaskSpaces=async()=>{if(o.throw)throw Error('fixture');return [{id:3,name:'fixture',ownership:tabs>1 && o.afterOwnership?o.afterOwnership:o.ownership}];};
globalThis.taskSpace=async id=>({spaceId:3,name:'fixture',ownership:o.ownership,
 tabs:async()=>{tabs++;const tab={label:o.label,targetId:tabs>1 && o.afterTarget?o.afterTarget:'stable',url:tabs>1 && o.afterUrl?o.afterUrl:o.url};return o.duplicate?[tab,tab]:[tab];},
 page:label=>{if(label!=='p2')throw Error('wrong label');return {evaluate:async fn=>{evaluations++;if(!fn.toString().includes('"sellerId": "SELLER1"') || !fn.toString().includes('"marketplace": "US"'))throw Error('missing fixed expected target');return RAW;}};}});
'''.replace('OPTIONS',json.dumps(options)).replace('RAW',json.dumps(self.raw))
            script=self.root/('store-fixture-'+str(n)+'.mjs')
            script.write_text(fixture+browser._store_script(binding,self.request,'US',output)+'\nif(evaluations!=='+str(evaluations)+")throw Error('evaluation count');",encoding='utf-8')
            result=RUN_LOCAL_FIXTURE([shutil.which('node'),str(script)],capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['status'],status)



class SearchCaptureTests(unittest.TestCase):
    tearDown = CaptureTests.tearDown
    run_capture = CaptureTests.run_capture

    def setUp(self):
        StoreCaptureTests.setUp(self)
        self.store_request = copy.deepcopy(self.request)
        self.store_raw = copy.deepcopy(self.raw)
        self.store_parent = copy.deepcopy(self.parent)
        self.request = dict(captureId='query1', cycleId='cycle', expectedRevision=2, parentId='keyword1')
        self.parent = dict(id='keyword1', kind='keyword', parentId=None, sourceType='browser_visible', marketplace='US', observedAt=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(), asin='B012345678', sourceTitle='Fixture Product Title', phrase='Fixture Product', url='https://amazon.com/dp/B012345678')
        self.report = dict(revision=2, events=[self.parent, self.search_parent, self.store_parent])
        now=datetime.now(timezone.utc).isoformat()
        self.raw = dict(schemaVersion=1, status='captured', marketplace='US', query='Fixture Product', url='https://www.amazon.com/s?k=Fixture+Product&ref=SECRET', capturedAt=now, products=[{'asin':'B012345679','title':'Observed product title','productURL':'https://amazon.com/Title/dp/B012345679/ref=sr_1_1?token=SECRET'}], evidence={'selector':browser.SEARCH_SELECTOR, 'query':'Fixture Product', 'marketplace':'US', 'sourceURL':'https://amazon.com/s?k=Fixture+Product', 'capturedAt':now, 'cards':[{'asin':'B012345679','cardAsin':'B012345679','title':'Observed product title','anchorHref':'https://amazon.com/dp/B012345679','cardSelector':browser.SEARCH_CARD_SELECTOR,'titleSelector':browser.SEARCH_TITLE_SELECTOR,'directMainSlot':True,'visible':True,'sponsored':False}]})

    def test_search_prepared_only_replay_scope_and_no_similarity_claims(self):
        self.raw['products'][0].update(similarity='EXACT',matchNotes='FORGED',brand='FORGED')
        self.raw['evidence']['cards'][0]['extra']='FORGED'
        with patch.object(browser.ledger,'ingest',side_effect=AssertionError('must not ingest')):result=browser.capture_search(1,self.request)
        self.assertEqual(result['status'],'captured');self.assertEqual(result['captureKind'],'search');self.assertEqual(result['sourceURL'],'https://amazon.com/s?k=Fixture+Product')
        event=result['preparedBatch']['events'][0]
        self.assertEqual(event['kind'],'search');self.assertEqual(event['parentId'],'keyword1');self.assertEqual(event['query'],self.parent['phrase']);self.assertEqual(event['marketplace'],'US')
        self.assertEqual(event['products'],[{'asin':'B012345679','title':'Observed product title'}]);self.assertEqual(result['evidence']['cards'][0]['productURL'],'https://amazon.com/dp/B012345679')
        for forbidden in ('SECRET','FORGED','EXACT','similarity'):self.assertNotIn(forbidden,json.dumps(result))
        for key in ('qualificationEvaluated','executionAllowed','publicationAllowed'):self.assertFalse(result[key])
        self.assertEqual(result['qualifiedCount'],0);self.assertEqual(result['paidExternalCallsPerformed'],0)
        self.assertEqual(browser.capture_search(1,self.request),result);self.assertEqual(browser.detail(1,'query1'),result);self.assertEqual(browser.history(2),{'items':[]});self.assertEqual(self.mocks[-1].call_count,1);self.assertEqual(self.report['revision'],2)

    def test_search_request_exact_keys(self):
        for changes in ({'query':'Other'},{'url':'https://amazon.com/s?k=Other'},{'script':'evil'},{'marketplace':'UK'},{'asin':'B012345678'},{'sellerId':'SELLER1'},{'owner':2},{'expectedRevision':True},{'expectedRevision':-1}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):browser.capture_search(1,{**self.request,**changes})
        for key in self.request:
            req=dict(self.request);req.pop(key)
            with self.assertRaises(ValueError):browser.capture_search(1,req)
        for owner in (True,0,'1'):
            with self.assertRaises(ValueError):browser.capture_search(owner,self.request)
        self.mocks[-1].assert_not_called()

    def test_keyword_parent_revision_and_market_revalidated(self):
        for n,changes in enumerate(({'parentId':'search1'},{'parentId':'seller1'},{'parentId':'missing'},{'expectedRevision':1})):
            self.assertEqual(browser.capture_search(1,{**self.request,**changes,'captureId':'request-'+str(n)})['reason'],'parent_or_revision_invalid')
        original=copy.deepcopy(self.parent)
        for n,changes in enumerate(({'kind':'search'},{'sourceType':'brand'},{'marketplace':'UK'},{'phrase':'Not a title prefix'},{'observedAt':'invalid'},{'url':'https://evil.test/dp/B012345678'})):
            self.parent.clear();self.parent.update({**original,**changes})
            self.assertEqual(browser.capture_search(1,{**self.request,'captureId':'parent-'+str(n)})['reason'],'parent_or_revision_invalid')
        self.mocks[-1].assert_not_called()

    def test_search_parent_lookup_owner_and_cycle_scoped(self):
        with patch.object(browser.ledger,'DB',self.root/'search-ledger.sqlite3'),patch.object(browser.ledger,'report',side_effect=REAL_LEDGER_REPORT):
            browser.ledger.ingest(1,dict(cycleId='cycle',expectedRevision=0,events=[self.parent]))
            self.assertEqual(browser.capture_search(2,{**self.request,'expectedRevision':1})['reason'],'parent_or_revision_invalid')
            self.assertEqual(browser.capture_search(1,{**self.request,'captureId':'wrong-cycle','cycleId':'other','expectedRevision':1})['reason'],'parent_or_revision_invalid')
            self.assertEqual(browser.capture_search(1,{**self.request,'expectedRevision':1})['status'],'captured')
        self.assertEqual(self.mocks[-1].call_count,1)

    def kinds(self):return [(browser.capture_search,self.request,self.raw),(browser.capture,self.seller_request,self.seller_raw),(browser.capture_store,self.store_request,self.store_raw)]

    def test_all_three_kinds_share_id_namespace_and_old_store_digest(self):
        kinds=self.kinds()
        for n,(first,request,raw) in enumerate(kinds):
            with patch.object(browser,'DB',self.root/('ids-'+str(n)+'.sqlite3')):
                self.raw=raw;self.assertEqual(first(1,request)['status'],'captured')
                for other,other_request,_ in kinds:
                    if other is not first:
                        with self.assertRaisesRegex(ValueError,'Conflicting captureId'):other(1,{**other_request,'captureId':request['captureId']})
        old={'status':'captured','reason':'legacy-store'};c=browser._connect(True)
        try:
            c.execute('INSERT INTO attempts VALUES (?,?,?,?,?)',(1,self.store_request['captureId'],browser._digest({'captureKind':'store','request':self.store_request}),'captured',json.dumps(old)));c.commit()
        finally:c.close()
        self.assertEqual(browser.capture_store(1,self.store_request),old)

    def test_each_unknown_kind_blocks_all_three_never_retries_late_result(self):
        kinds=self.kinds();self.mocks[-1].side_effect=subprocess.TimeoutExpired('fixture',45)
        for n,(first,request,_) in enumerate(kinds):
            self.mocks[-1].reset_mock()
            with patch.object(browser,'DB',self.root/('unknown-'+str(n)+'.sqlite3')):
                result=first(1,request);self.assertEqual(result['status'],'execution_unknown')
                for directory in (self.root/'discovery-captures'/'1').iterdir():(directory/'result.json').write_text(json.dumps(self.raw),encoding='utf-8')
                self.assertEqual(first(1,request),result)
                for other,other_request,_ in kinds:self.assertEqual(other(1,{**other_request,'captureId':'later-'+other.__name__})['reason'],'prior_capture_unresolved')
                self.assertEqual(self.mocks[-1].call_count,1)

    def test_concurrent_three_kinds_one_dispatch_barrier(self):
        kinds=self.kinds()
        for n,(first,request,raw) in enumerate(kinds):
            entered,release=threading.Event(),threading.Event();results=[];errors=[];self.raw=raw;self.mocks[-1].reset_mock()
            def run(*args,**kwargs):entered.set();release.wait(5);return self.run_capture(*args,**kwargs)
            self.mocks[-1].side_effect=run
            def worker():
                try:results.append(first(1,request))
                except Exception as exc:errors.append(exc)
            with patch.object(browser,'DB',self.root/('concurrent-'+str(n)+'.sqlite3')):
                thread=threading.Thread(target=worker);thread.start();self.assertTrue(entered.wait(5))
                try:
                    self.assertEqual(first(1,request)['status'],'capture_started')
                    for other,other_request,_ in kinds:self.assertEqual(other(1,{**other_request,'captureId':'parallel-'+other.__name__})['reason'],'prior_capture_unresolved')
                finally:release.set();thread.join(5)
                self.assertFalse(errors);self.assertEqual(results[0]['status'],'captured');self.assertEqual(self.mocks[-1].call_count,1)

    def test_search_raw_card_query_and_time_fail_closed(self):
        original=copy.deepcopy(self.raw)
        changes=[({},'schemaVersion',True),({},'query','fixture Product'),({},'marketplace','UK'),({},'url','https://amazon.com/s?k=Other'),({},'url','https://amazon.co.uk/s?k=Fixture+Product'),({},'url','https://amazon.com/s?k=Fixture+Product&me=SELLER1'),({},'url','https://amazon.com/s?k=Fixture+Product&rh=p_89:Brand'),({},'url','https://amazon.com/s?k=Fixture+Product&K=Fixture+Product'),({},'capturedAt',self.parent['observedAt']),({},'capturedAt',datetime.now().isoformat()),({},'capturedAt',(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()),({},'products',[]),('product','productURL','https://amazon.com/dp/B012345679?m=SELLER1'),('product','productURL','https://evil.test/dp/B012345679'),('evidence','query','Other'),('evidence','marketplace','UK'),('evidence','sourceURL','https://amazon.com/s?k=Other'),('evidence','selector','.recommendations'),('evidence','cards',[]),('evidence','capturedAt',self.parent['observedAt']),('card','cardAsin','B012345678'),('card','title','Brand'),('card','titleSelector','h2'),('card','cardSelector','.recommendations'),('card','directMainSlot',False),('card','directMainSlot',1),('card','visible',False),('card','sponsored',True),('card','anchorHref','https://amazon.com/dp/B012345678')]
        for n,(target,key,value) in enumerate(changes):
            with self.subTest(n=n):
                self.raw=copy.deepcopy(original)
                dst=self.raw['products'][0] if target=='product' else self.raw['evidence']['cards'][0] if target=='card' else self.raw['evidence'] if target=='evidence' else self.raw
                dst[key]=value;result=browser.capture_search(1,{**self.request,'captureId':'invalid-'+str(n)})
                self.assertEqual(result['status'],'blocked');self.assertNotIn('preparedBatch',result);self.assertNotIn('SECRET',json.dumps(result))
        self.raw=copy.deepcopy(original);self.raw['products'].append(copy.deepcopy(self.raw['products'][0]));self.assertEqual(browser.capture_search(1,{**self.request,'captureId':'duplicate'})['status'],'blocked')

    def test_delayed_empty_and_block_reasons(self):
        for n,reason in enumerate(('no_visible_search_products','not_keyword_search','SECRET')):
            self.raw={'schemaVersion':1,'status':'blocked','reason':reason};result=browser.capture_search(1,{**self.request,'captureId':'block-'+str(n)})
            self.assertEqual(result['status'],'blocked');self.assertNotIn('preparedBatch',result);self.assertEqual(result['reason'],'browser_capture_blocked' if reason=='SECRET' else reason)

    def test_scope_and_script_change_before_after_dispatch(self):
        config=copy.deepcopy(self.config);parent=copy.deepcopy(self.parent);original_script=browser._search_script;collector=self.root/'search-collector.js';original_bytes=browser.SEARCH_COLLECTOR.read_bytes()
        mutations={'parent':lambda:self.parent.update(sourceTitle='Fixture Product Title Changed'),'phrase':lambda:self.parent.update(phrase='Fixture'),'market':lambda:self.parent.update(marketplace='UK'),'revision':lambda:self.report.update(revision=3),'binding':lambda:self.config['discovery_browser']['account_bindings']['1'].update(page_label='changed'),'collector':lambda:collector.write_bytes(original_bytes+b'\n/* changed */')}
        for phase in ('before','after'):
            for name,mutate in mutations.items():
                with self.subTest(phase=phase,name=name):
                    self.config=copy.deepcopy(config);self.parent.clear();self.parent.update(parent);self.report['revision']=2;collector.write_bytes(original_bytes);self.mocks[-1].reset_mock()
                    def script(*args):
                        result=original_script(*args)
                        if phase=='before':mutate()
                        return result
                    def run(*args,**kwargs):
                        result=self.run_capture(*args,**kwargs)
                        if phase=='after':mutate()
                        return result
                    self.mocks[-1].side_effect=run
                    with patch.object(browser,'SEARCH_COLLECTOR',collector),patch.object(browser,'_search_script',side_effect=script):result=browser.capture_search(1,{**self.request,'captureId':phase+'-'+name})
                    self.assertEqual(result['status'],'blocked');self.assertNotIn('preparedBatch',result);self.assertEqual(self.mocks[-1].call_count,int(phase=='after'))

    def test_search_no_erp_or_browser_fallback(self):
        self.config.pop('discovery_browser');self.assertEqual(browser.capture_search(1,self.request)['status'],'configuration_blocked');self.mocks[-1].assert_not_called()

    @unittest.skipUnless(shutil.which('node'),'Node required for offline fixed-script fixture')
    def test_search_runtime_exact_query_and_ownership_guards(self):
        binding,_=browser._binding(1);good='https://www.amazon.com/s?k=Fixture+Product&crid=abc&sprefix=fixture&ref=nb_sb_noss_1'
        cases=[({},'captured',1),({'ownership':'agentDelegatedToUser'},'blocked',0),({'label':'other'},'blocked',0),({'duplicate':True},'blocked',0),({'afterTarget':'changed'},'blocked',1),({'afterUrl':good+'&qid=123'},'blocked',1),({'afterOwnership':'agentDelegatedToUser'},'blocked',1),({'throw':True},'execution_unknown',0)]
        cases += [({'url':url},'blocked',0) for url in ('https://amazon.com/s?me=SELLER1','https://amazon.com/stores/Brand?k=Fixture+Product','https://amazon.com/s?k=fixture+Product','https://amazon.co.uk/s?k=Fixture+Product','https://amazon.com/s?k=Fixture+Product&k=Fixture+Product','https://amazon.com/s?k=Fixture+Product&seller=OTHER1','https://amazon.com/s?k=Fixture+Product&rh=p_89:Brand','https://amazon.com/s?k=Fixture+Product&marketplaceID=A1F83G8C2ARO7P','https://amazon.com/evil/../s?k=Fixture+Product')]
        for n,(changes,status,evaluations) in enumerate(cases):
            options={'ownership':'agent','label':'p2','url':good,**changes};output=self.root/('search-node-'+str(n)+'.json')
            fixture=r'''
const o=OPTIONS;let tabs=0,evaluations=0;
globalThis.listTaskSpaces=async()=>{if(o.throw)throw Error('fixture');return [{id:3,name:'fixture',ownership:tabs>1 && o.afterOwnership?o.afterOwnership:o.ownership}];};
globalThis.taskSpace=async id=>({spaceId:3,name:'fixture',ownership:o.ownership,
 tabs:async()=>{tabs++;const tab={label:o.label,targetId:tabs>1 && o.afterTarget?o.afterTarget:'stable',url:tabs>1 && o.afterUrl?o.afterUrl:o.url};return o.duplicate?[tab,tab]:[tab];},
 page:label=>{if(label!=='p2')throw Error('wrong label');return {evaluate:async fn=>{evaluations++;if(!fn.toString().includes('"query": "Fixture Product"') || !fn.toString().includes('"marketplace": "US"'))throw Error('missing fixed expected target');return RAW;}};}});
'''.replace('OPTIONS',json.dumps(options)).replace('RAW',json.dumps(self.raw))
            script=self.root/('search-fixture-'+str(n)+'.mjs')
            script.write_text(fixture+browser._search_script(binding,{**self.request,'query':self.parent['phrase']},'US',output)+'\nif(evaluations!=='+str(evaluations)+")throw Error('evaluation count');",encoding='utf-8')
            result=RUN_LOCAL_FIXTURE([shutil.which('node'),str(script)],capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['status'],status)

if __name__ == '__main__':
    unittest.main()
