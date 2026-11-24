"""Offline SDK/CLI fixtures only. Never navigate a live browser."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

import discovery_browser as browser
import test_discovery_browser as fixtures
RUN_LOCAL_FIXTURE = fixtures.RUN_LOCAL_FIXTURE


class NavigationTests(unittest.TestCase):
    run_capture = fixtures.CaptureTests.run_capture
    tearDown = fixtures.CaptureTests.tearDown

    def setUp(self):
        fixtures.CaptureTests.setUp(self)
        self.lease = object()
        self.guard = Mock()
        self.check = Mock(side_effect=self.check_lease)
        self.mark = Mock()
        self.module = types.SimpleNamespace(_browser_guard=self.guard,
            _check_lease=self.check, _dispatch_started=self.mark)
        extra = patch.dict(sys.modules, {'discovery_live': self.module})
        self.patches.append(extra)
        extra.start()
        self.mocks[-1].side_effect = self.run_navigation

    def check_lease(self, lease, user, request, kind, phase='before_dispatch'):
        if lease is not self.lease:
            raise ValueError('invalid_live_lease')
        if (self.root / 'stop').exists():
            raise ValueError('live_run_stopped')
        return {'cancelPath': str(self.root / 'stop'), 'deadline': time.time()+60}

    def raw_navigation(self):
        return {**copy.deepcopy(self.raw), 'navigationDispatched': True,
            'collectorDispatched': True, 'navigationPhase': 'finished',
            'navigationEvidence': {'spaceId': 3, 'name': 'fixture', 'label': 'p2',
                'destination': 'https://amazon.com/dp/B012345678',
                'selectedURL': 'https://www.amazon.com/dp/B012345678'}}

    def run_navigation(self, args, **kwargs):
        self.assertTrue(self.mark.called)
        self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
        self.assertLessEqual(kwargs['timeout'], 45)
        directory = Path(kwargs['cwd'])
        script = (directory / 'capture.mjs').read_text('utf-8')
        self.assertEqual(script.count('await page.goto('), 1)
        self.assertIn('taskSpace(p.spaceId)', script)
        self.assertIn('page.targetId!==before[0].targetId', script)
        self.assertIn('await cancelled()', script)
        for forbidden in ('takeOverTaskSpace', 'claimTaskSpace', '.reload(', '.click(',
                'newPage(', '.fetch(', '.cookies(', 'localStorage', 'process.env'):
            self.assertNotIn(forbidden, script)
        (directory / 'result.json').write_text(json.dumps(self.raw_navigation()), 'utf-8')
        return subprocess.CompletedProcess(args, 0)

    def capture(self, request=None, kind='seller'):
        return browser.capture_live(1, request or self.request, kind, self.lease)

    def test_private_navigation_and_replay(self):
        result = self.capture()
        self.assertEqual(result['status'], 'captured')
        self.assertEqual(result['sourceURL'], 'https://amazon.com/dp/B012345678')
        self.assertEqual(result['navigationEvidence']['selectedURL'], result['sourceURL'])
        self.assertFalse(result['qualificationEvaluated'])
        self.assertEqual(result, self.capture())
        self.assertEqual(self.mocks[-1].call_count, 1)
        self.assertEqual(self.mark.call_count, 1)
        self.assertEqual(self.guard.call_count, 1)
        with self.assertRaisesRegex(ValueError, 'Conflicting captureId'):
            browser.capture(1, self.request)


    def test_search_and_store_urls_only_from_saved_graph(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        product = {'asin': 'B012345679', 'title': 'Observed product title',
            'productURL': 'https://amazon.com/dp/B012345679'}
        parent = {'id': 'keyword1', 'kind': 'keyword', 'parentId': None,
            'sourceType': 'browser_visible', 'marketplace': 'US',
            'observedAt': (now-timedelta(minutes=2)).isoformat(),
            'asin': 'B012345678', 'sourceTitle': 'Fixture Product Title',
            'phrase': 'Fixture Product', 'url': 'https://amazon.com/dp/B012345678'}
        for kind in ('search', 'store'):
            if kind == 'search':
                request = {'captureId': 'search-navigation', 'cycleId': 'cycle',
                    'expectedRevision': 2, 'parentId': parent['id']}
                destination = 'https://amazon.com/s?k=Fixture+Product'
                identity = {'query': 'Fixture Product'}
            else:
                parent = {**self.raw, 'id': 'seller1', 'kind': 'seller',
                    'parentId': 'search1', 'sourceType': 'browser_visible',
                    'observedAt': (now-timedelta(minutes=1)).isoformat()}
                request = {'captureId': 'store-navigation', 'cycleId': 'cycle',
                    'expectedRevision': 2, 'parentId': parent['id'], 'sellerId': 'SELLER1'}
                destination = 'https://amazon.com/s?me=SELLER1'
                identity = {'sellerId': 'SELLER1'}
            self.report = {'revision': 2, 'events': [parent]}
            card = {**product, 'cardAsin': product['asin'], 'anchorHref': product['productURL'],
                'cardSelector': browser.SEARCH_CARD_SELECTOR,
                'titleSelector': browser.SEARCH_TITLE_SELECTOR if kind=='search' else browser.STORE_TITLE_SELECTOR,
                'visible': True, 'sponsored': False}
            if kind == 'search':
                card['directMainSlot'] = True
            raw = {'schemaVersion': 1, 'status': 'captured', 'marketplace': 'US',
                'url': destination, 'capturedAt': now.isoformat(), 'products': [product],
                **identity, 'evidence': {'selector': '.s-main-slot', **identity,
                    'marketplace': 'US', 'capturedAt': now.isoformat(), 'sourceURL': destination,
                    'cards': [card]},
                'navigationDispatched': True, 'collectorDispatched': True, 'navigationPhase': 'finished',
                'navigationEvidence': {'spaceId': 3, 'name': 'fixture', 'label': 'p2',
                    'destination': destination, 'selectedURL': destination}}
            with patch.object(self, 'raw_navigation', return_value=raw):
                result = self.capture(request, kind=kind)
            self.assertEqual(result['status'], 'captured', result)
            self.assertEqual(result['sourceURL'], destination)
            self.assertEqual(result['preparedBatch']['events'][0]['kind'], kind)

    def test_no_url_script_or_json_lease_input(self):
        for key in ('url', 'script', 'navigation', 'lease', 'privilegeToken'):
            with self.assertRaises(ValueError):
                self.capture({**self.request, key: 'https://evil.test/'})
        with self.assertRaisesRegex(ValueError, 'invalid_live_lease'):
            browser.capture_live(1, self.request, 'seller', {'runId': 'forged'})
        self.mocks[-1].assert_not_called()

    def test_manual_and_navigation_have_one_same_owner_barrier(self):
        entered, release = threading.Event(), threading.Event()
        results, errors = [], []
        def run(*args, **kwargs):
            entered.set()
            release.wait(5)
            return self.run_navigation(*args, **kwargs)
        self.mocks[-1].side_effect = run
        def worker():
            try:
                results.append(self.capture())
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(entered.wait(5))
        self.config['discovery_browser']['account_bindings']['2'] = copy.deepcopy(
            self.config['discovery_browser']['account_bindings']['1'])
        try:
            self.assertEqual(self.capture()['status'], 'capture_started')
            result = browser.capture(1, {**self.request, 'captureId': 'manual'})
            self.assertEqual(result['reason'], 'prior_capture_unresolved')
            other = browser.capture(2, {**self.request, 'captureId': 'other-manual'})
            self.assertEqual(other['reason'], 'prior_space_capture_unresolved')
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(errors)
        self.assertEqual(results[0]['status'], 'captured')
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_manual_run_guard_and_other_account_same_local_space(self):
        self.guard.side_effect = ValueError('live_run_active')
        result = browser.capture(1, self.request)
        self.assertEqual(result['reason'], 'live_run_active')
        self.mocks[-1].assert_not_called()
        self.guard.side_effect = None
        self.mocks[-1].side_effect = subprocess.TimeoutExpired('fixture', 45)
        self.assertEqual(self.capture({**self.request, 'captureId': 'unknown'})['status'], 'execution_unknown')
        self.config['discovery_browser']['account_bindings']['2'] = {
            **self.config['discovery_browser']['account_bindings']['1'], 'task_space_name': 'alias'}
        result = browser.capture(2, {**self.request, 'captureId': 'other-account'})
        self.assertEqual(result['reason'], 'prior_space_capture_unresolved')
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_stopped_before_dispatch_does_not_call_runtime(self):
        self.mark.side_effect = ValueError('live_run_stopped')
        result = self.capture()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['phase'], 'pre_dispatch')
        self.mocks[-1].assert_not_called()

    def test_stop_after_read_discards_evidence(self):
        def run(*args, **kwargs):
            result = self.run_navigation(*args, **kwargs)
            (self.root / 'stop').touch()
            return result
        self.mocks[-1].side_effect = run
        result = self.capture()
        self.assertEqual(result['status'], 'blocked')
        self.assertNotIn('preparedBatch', result)
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_missing_proof_wrong_identity_and_login_redirect_rejected(self):
        original = self.raw_navigation
        cases = [
            lambda raw: raw.pop('navigationEvidence'),
            lambda raw: raw['navigationEvidence'].update(spaceId=9),
            lambda raw: raw['navigationEvidence'].update(selectedURL='https://amazon.com/ap/signin'),
            lambda raw: raw['navigationEvidence'].update(selectedURL='https://amazon.co.uk/dp/B012345678'),
            lambda raw: raw['navigationEvidence'].update(selectedURL='https://amazon.com/dp/B012345679'),
            lambda raw: raw.update(navigationDispatched=False),
            lambda raw: raw.update(collectorDispatched=False),
            lambda raw: raw.update(navigationPhase='after_navigation'),
        ]
        for index, mutate in enumerate(cases):
            def raw():
                value = original()
                mutate(value)
                return value
            with patch.object(self, 'raw_navigation', side_effect=raw):
                result = self.capture({**self.request, 'captureId': 'proof-'+str(index)})
            self.assertEqual(result['status'], 'blocked')
            self.assertNotIn('preparedBatch', result)


    def blocked_diagnostic(self):
        return {'schemaVersion': 1, 'status': 'blocked', 'reason': 'page_or_ownership_changed',
            'navigationPhase': 'before_navigation', 'navigationDispatched': False,
            'collectorDispatched': False, 'navigationDiagnostics': {
                'checkpoint': 'page_handle',
                'checks': {'pageLabelMatches': True, 'pageSpaceMatches': False, 'pageTargetMatches': True},
                'types': {'pageLabel': 'string', 'pageSpace': 'undefined',
                    'pageTarget': 'string', 'tabTarget': 'string'}}}

    def test_redacted_diagnostic_roundtrips_only_as_blocked(self):
        raw = self.blocked_diagnostic()
        with patch.object(self, 'raw_navigation', return_value=raw):
            result = self.capture()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'page_or_ownership_changed')
        self.assertEqual(result['navigationDiagnostics'], raw['navigationDiagnostics'])
        self.assertEqual(browser.detail(1, self.request['captureId']), result)
        self.assertEqual(browser.history(1)['items'], [result])
        self.assertNotIn('preparedBatch', result)
        self.assertNotIn('navigationEvidence', result)
        self.assertEqual(self.capture(), result)
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_malformed_diagnostics_are_unknown_never_authorization(self):
        mutations = [
            lambda r: r.update(schemaVersion=True),
            lambda r: r.update(navigationDiagnostics=None),
            lambda r: r['navigationDiagnostics'].update(checkpoint='SECRET_URL'),
            lambda r: r['navigationDiagnostics'].update(secret='SECRET_URL'),
            lambda r: r['navigationDiagnostics']['checks'].update(pageSpaceMatches=1),
            lambda r: r['navigationDiagnostics']['checks'].update(pageSpaceMatches='SECRET_URL'),
            lambda r: r['navigationDiagnostics']['types'].update(pageSpace='SECRET_URL'),
            lambda r: r['navigationDiagnostics']['types'].update(pageSpace={}),
            lambda r: r['navigationDiagnostics']['types'].pop('pageSpace'),
            lambda r: r.update(navigationDispatched=True),
            lambda r: r.update(navigationPhase='finished'),
            lambda r: r.update(reason='captcha_or_challenge'),
            lambda r: r.update(status='captured'),
        ]
        for index, mutate in enumerate(mutations):
            raw = self.blocked_diagnostic()
            mutate(raw)
            with patch.object(browser, 'DB', self.root / ('diagnostic-'+str(index)+'.sqlite3')):
                with patch.object(self, 'raw_navigation', return_value=raw):
                    result = self.capture()
                self.assertEqual(result['status'], 'execution_unknown')
                self.assertNotIn('SECRET_URL', json.dumps(result))
                self.assertNotIn('navigationDiagnostics', result)
                self.assertNotIn('preparedBatch', result)
                later = self.capture({**self.request, 'captureId': 'later'})
                self.assertEqual(later['reason'], 'prior_capture_unresolved')

    def test_persisted_diagnostic_reads_fail_closed(self):
        with patch.object(self, 'raw_navigation', return_value=self.blocked_diagnostic()):
            result = self.capture()
        result['navigationDiagnostics']['types']['pageSpace'] = 'SECRET_URL'
        c = browser._connect(True)
        try:
            c.execute('UPDATE attempts SET receipt=? WHERE owner=1 AND id=?',
                (json.dumps(result), self.request['captureId']))
            c.commit()
        finally:
            c.close()
        for read in (lambda: browser.detail(1, self.request['captureId']),
                lambda: browser.history(1), self.capture):
            with self.assertRaisesRegex(ValueError, '^invalid_navigation_diagnostics$'):
                read()
        later = self.capture({**self.request, 'captureId': 'later'})
        self.assertEqual(later['reason'], 'prior_capture_unresolved')

    def test_config_and_graph_changes_invalidate(self):
        for index, change in enumerate((
                lambda: self.report.update(revision=3),
                lambda: self.config['discovery_browser']['account_bindings']['1'].update(page_label='p9'))):
            original_config, original_report = copy.deepcopy(self.config), copy.deepcopy(self.report)
            def run(*args, **kwargs):
                result = self.run_navigation(*args, **kwargs)
                change()
                return result
            self.mocks[-1].side_effect = run
            result = self.capture({**self.request, 'captureId': 'changed-'+str(index)})
            self.assertEqual(result['status'], 'blocked')
            self.assertNotIn('preparedBatch', result)
            self.config, self.report = original_config, original_report

    def test_oversized_or_failed_runtime_is_unknown_and_not_retried(self):
        for index, failure in enumerate(('oversized', 'exit', 'timeout')):
            with patch.object(browser, 'DB', self.root / ('failure-'+str(index)+'.sqlite3')):
                self.mocks[-1].reset_mock()
                def run(args, **kwargs):
                    if failure == 'timeout':
                        raise subprocess.TimeoutExpired(args, 45)
                    if failure == 'oversized':
                        (Path(kwargs['cwd'])/'result.json').write_text('x'*32769, 'utf-8')
                    return subprocess.CompletedProcess(args, 1 if failure=='exit' else 0)
                self.mocks[-1].side_effect = run
                result = self.capture()
                self.assertEqual(result['status'], 'execution_unknown')
                self.assertEqual(self.capture(), result)
                self.assertEqual(self.mocks[-1].call_count, 1)
                next_result = self.capture({**self.request, 'captureId': 'next'})
                self.assertEqual(next_result['reason'], 'prior_capture_unresolved')


class NavigationRuntimeTests(unittest.TestCase):
    run_capture = fixtures.CaptureTests.run_capture
    """Run generated scripts in plain Node against an entirely fake SDK."""
    def setUp(self):
        fixtures.CaptureTests.setUp(self)

    tearDown = fixtures.CaptureTests.tearDown

    @unittest.skipUnless(shutil.which('node'), 'Node required for offline SDK fixture')
    def test_navigation_stop_ownership_redirect_and_failure_boundaries(self):
        binding, _ = browser._binding(1)
        cases = [
            ({}, 'captured', 1, 1),
            ({'missingInventoryPage': True}, 'blocked', 0, 0),
            ({'sharedMalformedTarget': 7}, 'blocked', 0, 0),
            ({'sharedMalformedTarget': {'id': 'stable'}}, 'blocked', 0, 0),
            ({'openedBy': 'user'}, 'blocked', 0, 0),
            ({'pageOpenedBy': True}, 'blocked', 0, 0),
            ({'pageOwnerAfterGoto': True}, 'blocked', 1, 0),
            ({'pageOwnerAfterRead': True}, 'blocked', 1, 1),
            ({'openedBy': None}, 'blocked', 0, 0),
            ({'earlyDrift': 'openedBy'}, 'blocked', 0, 0),
            ({'earlyPageMissing': True}, 'blocked', 0, 0),
            ({'earlyPageField': 'label'}, 'blocked', 0, 0),
            ({'earlyPageField': 'spaceId'}, 'blocked', 0, 0),
            ({'earlyPageField': 'targetId'}, 'blocked', 0, 0),
            ({'earlyPageField': 'openedBy'}, 'blocked', 0, 0),
            ({'openedByAfterGoto': True}, 'blocked', 1, 0),
            ({'openedByAfterRead': True}, 'blocked', 1, 1),
            ({'gotoReceipt': {'dialog': {'type': 'alert'}}}, 'execution_unknown', 1, 0),
            ({'gotoReceipt': {'popups': ['other']}}, 'execution_unknown', 1, 0),
            ({'gotoReceipt': {'unknown': True}}, 'execution_unknown', 1, 0),
            ({'gotoReceipt': None}, 'execution_unknown', 1, 0),
            ({'gotoReceipt': []}, 'execution_unknown', 1, 0),
            ({'gotoReceipt': True}, 'execution_unknown', 1, 0),
            ({'beforeURL': 'https://amazon.com/s?k=fixture'}, 'captured', 1, 2),
            ({'beforeURL': 'https://evil.test/'}, 'blocked', 0, 0),
            ({'beforeURL': 'https://amazon.com/ap/signin'}, 'blocked', 0, 0),
            ({'beforeURL': 'https://amazon.com/dp/B012345678', 'access': True}, 'blocked', 0, 1),
            ({'ownership': 'user'}, 'blocked', 0, 0),
            ({'duplicate': True}, 'blocked', 0, 0),
            ({'stopBefore': True}, 'blocked', 0, 0),
            ({'deadline': True}, 'blocked', 0, 0),
            ({'stopDuringGoto': True}, 'blocked', 1, 0),
            ({'redirect': 'https://amazon.com/ap/signin'}, 'blocked', 1, 0),
            ({'redirect': 'https://amazon.com/dp/B012345678?m=OTHER1'}, 'blocked', 1, 0),
            ({'redirect': 'https://evil.test/dp/B012345678'}, 'blocked', 1, 0),
            ({'redirect': 'https://amazon.com/dp/B012345679'}, 'blocked', 1, 0),
            ({'targetChange': True}, 'blocked', 1, 0),
            ({'pageTargetAfterGoto': True}, 'blocked', 1, 0),
            ({'pageTargetAfterRead': True}, 'blocked', 1, 1),
            ({'ownershipChange': True}, 'blocked', 1, 0),
            ({'throwBefore': True}, 'execution_unknown', 0, 0),
            ({'throwGoto': True}, 'execution_unknown', 1, 0),
            ({'throwAfter': True}, 'execution_unknown', 1, 0),
            ({'throwRead': True}, 'execution_unknown', 1, 1),
            ({'stopDuringRead': True}, 'blocked', 1, 1),
            ({'missingPageLabel': True, 'badCheck': 'pageLabelMatches'}, 'blocked', 0, 0),
            ({'pageLabelValue': 7, 'badCheck': 'pageLabelMatches'}, 'blocked', 0, 0),
            ({'missingPageSpace': True, 'badCheck': 'pageSpaceMatches'}, 'blocked', 0, 0),
            ({'pageSpaceValue': '3', 'badCheck': 'pageSpaceMatches'}, 'blocked', 0, 0),
            ({'missingPageTarget': True, 'badCheck': 'pageTargetMatches'}, 'blocked', 0, 0),
            ({'pageTargetValue': 7, 'badCheck': 'pageTargetMatches'}, 'blocked', 0, 0),
            ({'pageTargetValue': 'other', 'badCheck': 'pageTargetMatches'}, 'blocked', 0, 0),
            ({'earlyDrift': 'tabTarget', 'badCheck': 'tabTargetMatches'}, 'blocked', 0, 0),
            ({'earlyDrift': 'tabURL', 'badCheck': 'urlMatches'}, 'blocked', 0, 0),
            ({'earlyDrift': 'ownership', 'badCheck': 'agentSpaceMatches'}, 'blocked', 0, 0),
            ({'earlyDrift': 'tabCount', 'badCheck': 'oneTab'}, 'blocked', 0, 0),
            ({'earlyDrift': 'pageTarget', 'badCheck': 'pageTargetMatches'}, 'blocked', 0, 0),
            ({'afterReadDrift': True, 'badCheck': 'tabTargetMatches'}, 'blocked', 1, 1),
        ]
        for index, (options, expected, navigations, evaluations) in enumerate(cases):
            stop = self.root / ('stop-'+str(index))
            output = self.root / ('node-result-'+str(index)+'.json')
            if options.get('stopBefore'):
                stop.touch()
            navigation = {'destination': 'https://amazon.com/dp/B012345678',
                'cancelPath': str(stop), 'deadline': time.time()+(-1 if options.get('deadline') else 60)}
            fixture = r"""
const o=OPTIONS, stop=STOP;
let lazyPages=0, gotos=0, evaluations=0, spaces=0, current=o.beforeURL||'about:blank', target='sharedMalformedTarget' in o?o.sharedMalformedTarget:'stable';
const fixtureFS=await import('node:fs/promises');
globalThis.listTaskSpaces=async()=>{
  spaces++;if(o.throwBefore)throw Error('before');
  return [{id:3,name:'fixture',ownership:(gotos && o.ownershipChange) || (spaces>1 && o.earlyDrift==='ownership')?'user':(o.ownership||'agent')}];
};
const page={
 get openedBy(){return o.pageOpenedBy || (gotos && o.pageOwnerAfterGoto) || (evaluations && o.pageOwnerAfterRead)?'user':'agent';},
 get label(){return o.missingPageLabel?undefined:('pageLabelValue' in o?o.pageLabelValue:'p2');},
 get spaceId(){return o.missingPageSpace?undefined:('pageSpaceValue' in o?o.pageSpaceValue:3);},
 get targetId(){if('sharedMalformedTarget' in o)return o.sharedMalformedTarget;return o.missingPageTarget?undefined:('pageTargetValue' in o?o.pageTargetValue:((spaces>1 && o.earlyDrift==='pageTarget') || (gotos && o.pageTargetAfterGoto) || (evaluations && o.pageTargetAfterRead)?'changed':'stable'));},
 goto:async(url,opts)=>{
   gotos++;if(!opts || opts.timeout<=0 || opts.timeout>20000)throw Error('timeout required');
   if(o.stopDuringGoto)await fixtureFS.writeFile(stop,'stopped');
   if(o.throwGoto)throw Error('goto unknown');
   current=o.redirect||url;if(o.targetChange)target='changed';
   return 'gotoReceipt' in o?o.gotoReceipt:{};
 },
 evaluate:async fn=>{
   evaluations++;
   if(!fn.toString().includes('visible_sold_by_link'))throw Error('fixed collector required');
   if(o.throwRead)throw Error('read unknown');
   if(o.stopDuringRead)await fixtureFS.writeFile(stop,'stopped');
   return o.access?{schemaVersion:1,status:'blocked',reason:'captcha_or_challenge'}:RAW;
 }};
globalThis.taskSpace=async()=>({spaceId:3,name:'fixture',ownership:'agent',
 tabs:async()=>{
   if(gotos && o.throwAfter)throw Error('after goto');
   const tab={label:'p2',page:o.missingInventoryPage?undefined:page,
     openedBy:(spaces>1 && o.earlyDrift==='openedBy') || (gotos && o.openedByAfterGoto) || (evaluations && o.openedByAfterRead)?'user':('openedBy' in o?o.openedBy:'agent'),targetId:(spaces>1 && o.earlyDrift==='tabTarget') || (evaluations && o.afterReadDrift)?'changed':target,
     url:spaces>1 && o.earlyDrift==='tabURL'?'https://amazon.com/dp/B012345679':current};
   if(spaces>1 && o.earlyPageMissing)delete tab.page;
   if(spaces>1 && o.earlyPageField)tab.page={label:'p2',spaceId:3,targetId:target,openedBy:'agent',[o.earlyPageField]:'changed'};
   return o.duplicate || (spaces>1 && o.earlyDrift==='tabCount')?[tab,tab]:[tab];
 },page:label=>{
   // Official SDK lazy handle: identity is unavailable until resolve, unlike
   // the hydrated inventory Page. The fixed runtime must never request this.
   lazyPages++;
   let resolved=false;
   return {label,spaceId:3,get targetId(){return resolved?target:undefined;},
     resolve:async()=>{resolved=true;return target;},
     goto:async(...args)=>{resolved=true;return page.goto(...args);},
     evaluate:async(...args)=>{resolved=true;return page.evaluate(...args);}};
 }});
""".replace('OPTIONS', json.dumps(options)).replace('STOP', json.dumps(str(stop))).replace('RAW', json.dumps(self.raw))
            fixture += browser._script(binding, self.request, 'US', output, navigation=navigation)
            fixture += '\nif(lazyPages!==0)throw Error("lazy Page used");\nif(gotos!=='+str(navigations)+' || evaluations!=='+str(evaluations)+")throw Error('unexpected dispatch count '+gotos+' '+evaluations);\n"
            if options.get('stopDuringGoto'):
                fixture += "if(spaces!==2)throw Error('SDK call occurred after stop');\n"
            script = self.root / ('fixture-'+str(index)+'.mjs')
            script.write_text(fixture, 'utf-8')
            result = RUN_LOCAL_FIXTURE([shutil.which('node'), str(script)], capture_output=True, timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            with self.subTest(options=options):
                self.assertEqual(result.returncode, 0, result.stderr)
                raw = json.loads(output.read_text('utf-8'))
                self.assertEqual(raw['status'], expected)
                self.assertEqual(raw['navigationDispatched'], bool(navigations))
                self.assertEqual(raw['collectorDispatched'], bool(evaluations and not options.get('access')))
                if 'sharedMalformedTarget' in options:
                    self.assertEqual(raw['reason'], 'navigation_source_not_public')
                    self.assertNotIn('navigationEvidence', raw)
                if expected=='captured':
                    self.assertEqual(raw['navigationEvidence']['destination'], navigation['destination'])
                    self.assertNotIn('navigationDiagnostics', raw)
                if options.get('badCheck'):
                    diagnostic = browser._navigation_diagnostic(raw)
                    checkpoint = 'before_navigation_recheck' if options.get('earlyDrift') else 'after_capture_recheck' if options.get('afterReadDrift') else 'page_handle'
                    self.assertEqual(diagnostic['checkpoint'], checkpoint)
                    self.assertIs(diagnostic['checks'][options['badCheck']], False)
                    serialized = json.dumps(diagnostic)
                    for forbidden in ('https:', 'fixture', 'stable', 'changed', 'p2', str(stop)):
                        self.assertNotIn(forbidden, serialized)
                    if options.get('missingPageSpace'):
                        self.assertEqual(diagnostic['types']['pageSpace'], 'undefined')
                    if 'pageSpaceValue' in options:
                        self.assertEqual(diagnostic['types']['pageSpace'], 'string')


if __name__ == '__main__':
    unittest.main()
