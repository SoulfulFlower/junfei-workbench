"""Relocate a portable app and test only isolated local flows, with no provider credentials."""
import argparse
import http.cookiejar
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile


def clean_environment(data, port):
    allowed = ('SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA',
               'COMSPEC', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'PATHEXT')
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update(JUNFEI_ACCOUNT_DATA=str(data), JUNFEI_PORT=str(port), JUNFEI_OPEN_BROWSER='0',
               PATH=str(Path(os.environ['SystemRoot']) / 'System32'))
    return env


def request(opener, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    with opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=8) as response:
        return response.read()


def run_cli(exe, args, env, cwd, data=None):
    return subprocess.run([str(exe), *args], cwd=cwd, env=env, capture_output=True, timeout=40, input=data,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def smoke(folder):
    folder = Path(folder).resolve(strict=True)
    results = {'sameMachineRelocationOnly': True, 'secondComputerTested': False,
               'externalProvidersInvoked': False, 'erpActionsPerformed': False}
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with tempfile.TemporaryDirectory(prefix='aw-') as temp:
        root = Path(temp)
        copied = root / '迁移 folder' / 'Agent'
        shutil.copytree(folder, copied)
        exe = copied / 'AmazonAgentPortable.exe'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        data = root / 'fresh-profile'
        env = clean_environment(data, port)
        response = run_cli(exe, ['--workbench-tool', 'ego-browser', '--help'], env, root)
        if response.returncode != 0 or data.exists() or b'usage:' not in response.stdout.lower():
            raise RuntimeError('Bundled tool --help output missing, failed, or modified profile')
        results['bundledPythonHelpWithoutPythonOnPath'] = True
        schema_probe = {'schema': {'type': 'object', 'required': ['brand']},
                        'records': [{'id': 'fixture', 'attributes': {'brand': 'Generic'}}]}
        response = run_cli(exe, ['--workbench-tool', 'validate-attributes'], env, root,
                           json.dumps(schema_probe).encode('utf-8'))
        if response.returncode != 0 or data.exists() or json.loads(response.stdout).get('passed') is not True:
            raise RuntimeError('Bundled schema tool could not validate offline: ' + response.stderr.decode(errors='replace'))
        results['bundledAttributeValidation'] = True
        report = root / 'self-check.json'
        response = run_cli(exe, ['--self-check', str(report)], env, root)
        if response.returncode != 0 or data.exists():
            raise RuntimeError('Read-only self-check failed or modified profile')
        diagnostic = json.loads(report.read_text(encoding='utf-8'))
        if diagnostic.get('readyForUnattendedRun') is not False:
            raise RuntimeError('Clean package incorrectly claims unattended readiness')
        missing = [item['id'] for item in diagnostic['checks'] if not item['ok'] and not item['id'].startswith('ego-')]
        if missing:
            raise RuntimeError('Packaged runtime failed self-check: ' + ', '.join(missing))
        results['readOnlySelfCheck'] = True
        process = subprocess.Popen([str(exe)], cwd=root, env=env, creationflags=flags)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(120):
                if process.poll() is not None:
                    raise RuntimeError('Portable app exited early; inspect isolated desktop log')
                try:
                    health = json.loads(request(opener, base + '/api/desktop-health'))
                    if health.get('app') == 'amazon-listing-workbench' and process.poll() is None:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError('Portable app did not become healthy')
            credentials = {'username': 'portable' + secrets.token_hex(4),
                           'password': secrets.token_urlsafe(24) + 'Aa1!', 'name': 'Isolated Test'}
            request(opener, base + '/api/auth/setup', credentials)
            request(opener, base + '/api/auth/login', credentials)
            budget = json.loads(request(opener, base + '/api/image/budget'))
            if budget.get('limits', {}).get('enabled') is not False or budget.get('reservations') != []:
                raise RuntimeError('Portable package contains enabled paid settings or reservations')
            overview = json.loads(request(opener, base + '/api/agent/overview'))
            if overview.get('tasks'):
                raise RuntimeError('Portable package contains existing tasks')
            for asset in ('index.html', 'auth.js', 'agent-center.js', 'visual-studio.js', 'discovery-ui.js', 'discovery-browser-ui.js'):
                if not request(opener, base + '/' + asset):
                    raise RuntimeError('Missing frontend asset: ' + asset)
            extension = request(opener, base + '/api/auth/extension-download')
            with zipfile.ZipFile(io.BytesIO(extension)) as archive:
                version = json.loads(archive.read('extension/manifest.json'))['version']
                if not archive.read('extension/popup.js'):
                    raise RuntimeError('Extension download is incomplete')
            source_archive = request(opener, base + '/api/studio/source')
            with zipfile.ZipFile(io.BytesIO(source_archive)) as archive:
                needed = {'listing-workbench/desktop_launcher.py', 'listing-workbench/server.py',
                          'listing-workbench/portable_support.py', 'listing-workbench/visual-ui/NOTICE.md',
                          'listing-workbench/LICENSE-AGPL-3.0.txt', 'packaging/build_portable.py',
                          'AmazonAgentPortable.spec', 'automation/config.json',
                          'listing-workbench/AUTOMATION-RECOVERY.md',
                          'listing-workbench/test_workflow_recovery.py',
                          'listing-workbench/agent_handoff.py',
                          'listing-workbench/SELECTION-TO-COPY.md',
                          'listing-workbench/agent_image_preparation.py',
                          'listing-workbench/IMAGE-PREPARATION.md', 'automation/test_budget_carryover.py',
                          'listing-workbench/cyclic_discovery.py', 'listing-workbench/CYCLIC-DISCOVERY.md',
                          'listing-workbench/discovery_browser.py', 'listing-workbench/discovery-seller-collector.js',
                          'listing-workbench/DISCOVERY-BROWSER.md'}
                if not needed.issubset(set(archive.namelist())):
                    raise RuntimeError('Corresponding source archive is incomplete')
                if any(name.endswith(('.sqlite3', '.dpapi', '.fernet')) for name in archive.namelist()):
                    raise RuntimeError('Corresponding source contains private data files')
            results['correspondingSourceDownload'] = True
            results.update(health=True, freshSetupLogin=True, paidWorkDisabled=True,
                           emptyTaskLedger=True, frontendAssets=True, extensionVersion=version)
            runtime = data / 'portable-runtime'
            config = json.loads((runtime / 'automation/config.json').read_text(encoding='utf-8'))
            if config['browser']['cli'] or config['profiles']:
                raise RuntimeError('Runtime contains machine or store bindings')
            ego_env = dict(env, JUNFEI_PROJECT_ROOT=str(runtime))
            stopped = run_cli(exe, ['--workbench-tool', 'ego-browser', 'status'], ego_env, root)
            if stopped.returncode == 0 or not stopped.stderr.strip() or (runtime / 'automation/data').exists():
                raise RuntimeError('Unconfigured EGO did not fail closed')
            results['unconfiguredEgoStoppedWithoutReceipts'] = True
            node = copied / '_internal/node.exe'
            sharp = subprocess.run([str(node), '-e', "import('sharp').then(m=>m.default({create:{width:1,height:1,channels:3,background:'white'}}).png().toBuffer()).then(b=>{if(!b.length)process.exit(2)}).catch(()=>process.exit(3))"],
                        cwd=runtime / 'junfei-publisher', env=env, capture_output=True, timeout=30, creationflags=flags)
            if sharp.returncode:
                raise RuntimeError('Bundled Node/sharp native dependency failed')
            results['bundledNodeSharp'] = True
            other = clean_environment(root / 'other-isolated-profile', port)
            occupied = run_cli(exe, [], other, root)
            if occupied.returncode == 0:
                raise RuntimeError('Occupied port was mistaken for this new instance')
            results['occupiedPortRejected'] = True
            profile = json.loads(request(opener, base + '/api/agent/profile', {
                'name': 'Isolated queue fixture', 'store': 'Synthetic store',
                'marketplace': 'US', 'shippingTemplate': 'Synthetic shipping', 'quantity': 1,
            }))['profile']
            task = json.loads(request(opener, base + '/api/agent/create', {
                'goal': 'Offline queue smoke; no product or external calls',
                'profileId': profile['id'], 'taskMode': 'production',
                'autoSourcing': False, 'autoResearch': False,
                'autoListing': False, 'aiPlanning': False,
            }))['task']
            request(opener, base + '/api/agent/start', {'id': task['id']})
            for _ in range(80):
                queue_task = json.loads(request(opener, base + '/api/agent/task?id=' + task['id']))
                if queue_task.get('status') != 'running':
                    break
                time.sleep(.1)
            if (queue_task.get('status') != 'blocked' or queue_task.get('cursor') != 1
                    or not queue_task.get('executionId')
                    or set(queue_task.get('results', {})) != {'plan'}
                    or queue_task.get('paidSpendCny') != 0):
                raise RuntimeError('Packaged queue did not stop honestly before unimplemented selection')
            results['packagedExecutionIdentity'] = True
            results['syntheticSelectionStopsBeforeExternalWork'] = True
            try:
                request(opener, base + '/api/agent/prepare-copy-handoff', {
                    'id': task['id'], 'budgetCny': 1, 'researchAsins': '',
                    'confirmPaidText': True, 'acknowledgeBudgetNotHardCap': True,
                })
            except urllib.error.HTTPError as error:
                if error.code != 400:
                    raise RuntimeError('Copy handoff failed with an unexpected status') from error
            else:
                raise RuntimeError('Unqualified synthetic task unexpectedly enabled copy handoff')
            after_handoff = json.loads(request(opener, base + '/api/agent/task?id=' + task['id']))
            if after_handoff.get('copyHandoff') or after_handoff.get('autoResearch') or after_handoff.get('autoListing'):
                raise RuntimeError('Rejected handoff changed execution permission')
            results['copyHandoffRejectsUnqualifiedTask'] = True
            try:
                request(opener, base + '/api/agent/image-preparation?id=' + task['id'] + '&revision=0')
            except urllib.error.HTTPError as error:
                if error.code != 400: raise RuntimeError('Image preparation failed unexpectedly') from error
            else:
                raise RuntimeError('Unqualified synthetic task unexpectedly entered image preparation')
            results['imagePreparationRejectsUnqualifiedTask'] = True
            empty_discovery = json.loads(request(opener, base + '/api/discovery/history'))
            if empty_discovery != {'items': []}:
                raise RuntimeError('Portable package contains existing discovery records')
            state_before = request(opener, base + '/api/state')
            fixture = {'cycleId': 'synthetic-smoke', 'expectedRevision': 0, 'events': [{
                'id': 'synthetic-keyword', 'parentId': None, 'kind': 'keyword', 'marketplace': 'US',
                'observedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'sourceType': 'browser_visible', 'asin': 'B012345678',
                'sourceTitle': 'Synthetic Offline Pouch', 'phrase': 'Synthetic Offline',
                'url': 'https://www.amazon.com/dp/B012345678'}]}
            fixture['events'].append({'id': 'synthetic-search', 'parentId': 'synthetic-keyword',
                'kind': 'search', 'marketplace': 'US', 'sourceType': 'browser_visible',
                'observedAt': fixture['events'][0]['observedAt'], 'query': 'Synthetic Offline',
                'url': 'https://www.amazon.com/s?k=Synthetic+Offline',
                'products': [{'asin': 'B012345678', 'title': 'Synthetic Offline Pouch'}]})
            trace = json.loads(request(opener, base + '/api/discovery/ingest', fixture))
            replay = json.loads(request(opener, base + '/api/discovery/ingest', fixture))
            saved_trace = json.loads(request(opener, base + '/api/discovery/report?id=synthetic-smoke'))
            if (trace.get('revision') != 1 or replay != trace or saved_trace != trace
                    or trace.get('executionAllowed') is not False or trace.get('qualificationEvaluated') is not False
                    or trace.get('qualifiedCount') != 0 or trace.get('importedCount') != 0
                    or trace.get('externalCallsPerformed') != 0
                    or trace['events'][0].get('trust') != 'unverified_observation'):
                raise RuntimeError('Synthetic discovery ledger claimed production work or lost provenance')
            if request(opener, base + '/api/state') != state_before:
                raise RuntimeError('Discovery ledger unexpectedly changed the product workspace')
            results['syntheticDiscoveryLocalLedgerAndReplay'] = True
            results['discoveryDoesNotQualifyOrImportProducts'] = True
            if json.loads(request(opener, base + '/api/discovery/captures')) != {'items': []}:
                raise RuntimeError('Portable package contains previous browser captures')
            capture_request = {'captureId': 'synthetic-no-binding', 'cycleId': 'synthetic-smoke',
                'expectedRevision': 1, 'parentId': 'synthetic-search', 'asin': 'B012345678'}
            capture = json.loads(request(opener, base + '/api/discovery/capture-seller', capture_request))
            if capture.get('status') != 'configuration_blocked' or capture.get('preparedBatch'):
                raise RuntimeError('Unconfigured portable package unexpectedly enabled browser capture')
            if json.loads(request(opener, base + '/api/discovery/capture-seller', capture_request)) != capture:
                raise RuntimeError('Capture replay did not return original receipt')
            if json.loads(request(opener, base + '/api/discovery/capture?id=synthetic-no-binding')) != capture:
                raise RuntimeError('Missing blocked capture receipt')
            if request(opener, base + '/api/state') != state_before:
                raise RuntimeError('Blocked browser capture changed product workspace')
            results['unconfiguredDiscoveryCaptureBlocked'] = True
            results['unconfiguredDiscoveryCaptureReceiptReplay'] = True

            # Synthetic seller/listing observations exercise preparation, not a live store read.
            synthetic_later={'cycleId':'synthetic-smoke','expectedRevision':1,'events':[
                {'id':'synthetic-seller','kind':'seller','parentId':'synthetic-search','marketplace':'US',
                 'sourceType':'browser_visible','observedAt':fixture['events'][0]['observedAt'],
                 'asin':'B012345678','sellerId':'SMOKESELLER','sellerName':'Synthetic Seller',
                 'sellerLabel':'Sold by Synthetic Seller','sellerLinkSource':'visible_sold_by_link',
                 'sellerLink':'https://amazon.com/sp?seller=SMOKESELLER','url':'https://amazon.com/dp/B012345678'},
                {'id':'synthetic-store','kind':'store','parentId':'synthetic-seller','marketplace':'US',
                 'sourceType':'browser_visible','observedAt':fixture['events'][0]['observedAt'],
                 'sellerId':'SMOKESELLER','status':'captured','url':'https://amazon.com/s?me=SMOKESELLER',
                 'products':[{'asin':'B098765432','title':'Synthetic Linen Shirt'}]}]}
            listing_trace=json.loads(request(opener,base+'/api/discovery/ingest',synthetic_later))
            if listing_trace.get('revision')!=2 or listing_trace.get('eventCount')!=4:
                raise RuntimeError('Synthetic seller listing chain was not recorded')
            store_request={'captureId':'synthetic-store-no-binding','cycleId':'synthetic-smoke',
                           'expectedRevision':2,'parentId':'synthetic-seller','sellerId':'SMOKESELLER'}
            store_capture=json.loads(request(opener,base+'/api/discovery/capture-store',store_request))
            if store_capture.get('status')!='configuration_blocked' or store_capture.get('preparedBatch'):
                raise RuntimeError('Unconfigured portable package enabled seller listing capture')
            if json.loads(request(opener,base+'/api/discovery/capture-store',store_request))!=store_capture:
                raise RuntimeError('Store capture replay changed receipt')
            results['unconfiguredStoreCaptureBlockedAndReplay']=True
            keyword_request={'cycleId':'synthetic-smoke','expectedRevision':2,'parentId':'synthetic-store',
                             'asin':'B098765432','phrase':'Synthetic Linen'}
            prepared=json.loads(request(opener,base+'/api/discovery/prepare-keyword',keyword_request))
            if prepared.get('status')!='prepared' or prepared.get('sourceKind')!='seller_listing_card':
                raise RuntimeError('Packaged keyword preparation missing source scope')
            if json.loads(request(opener,base+'/api/discovery/report?id=synthetic-smoke'))!=listing_trace:
                raise RuntimeError('Keyword preview wrote observations')
            completed_trace=json.loads(request(opener,base+'/api/discovery/ingest',prepared['preparedBatch']))
            if completed_trace.get('revision')!=3 or completed_trace.get('eventCount')!=5 or completed_trace.get('roundCount')!=2:
                raise RuntimeError('Explicit title-prefix save lost chain')
            if completed_trace.get('qualificationEvaluated') is not False or completed_trace.get('qualifiedCount')!=0 or completed_trace.get('importedCount')!=0:
                raise RuntimeError('Title-prefix derivation incorrectly claimed qualification')
            if json.loads(request(opener,base+'/api/discovery/ingest',prepared['preparedBatch']))!=completed_trace:
                raise RuntimeError('Repeated title-prefix save changed graph')
            if request(opener,base+'/api/state')!=state_before:
                raise RuntimeError('Seller loop preparation changed product workspace')
            results['syntheticStoreTitlePreviewDoesNotWrite']=True
            results['syntheticStoreTitleExplicitSaveAndReplay']=True

            next_keyword=prepared['preparedBatch']['events'][0]
            search_request={'captureId':'synthetic-search-no-binding','cycleId':'synthetic-smoke',
                            'expectedRevision':3,'parentId':next_keyword['id']}
            search_capture=json.loads(request(opener,base+'/api/discovery/capture-search',search_request))
            if search_capture.get('status')!='configuration_blocked' or search_capture.get('preparedBatch'):
                raise RuntimeError('Unconfigured package enabled current search capture')
            if json.loads(request(opener,base+'/api/discovery/capture-search',search_request))!=search_capture:
                raise RuntimeError('Search capture replay changed receipt')
            results['unconfiguredSearchCaptureBlockedAndReplay']=True
            plan_request={'cycleId':'synthetic-smoke','expectedRevision':3,'maxActions':4,'maxRounds':2}
            plan=json.loads(request(opener,base+'/api/discovery/prepare-plan',plan_request))
            if plan.get('readOnly') is not True or plan.get('executionAllowed') is not False or plan.get('automaticNavigationImplemented') is not False:
                raise RuntimeError('Bounded plan incorrectly claims execution')
            if len(plan['actions'])>4 or any(action['proposedRound']>2 for action in plan['actions']):
                raise RuntimeError('Bounded plan exceeded explicit preview caps')
            if json.loads(request(opener,base+'/api/discovery/prepare-plan',plan_request))!=plan:
                raise RuntimeError('Unchanged plan preview is not deterministic')
            if json.loads(request(opener,base+'/api/discovery/report?id=synthetic-smoke'))!=completed_trace:
                raise RuntimeError('Plan preview wrote ledger')
            if request(opener,base+'/api/state')!=state_before:
                raise RuntimeError('Plan preview changed product workspace')
            results['boundedContinuationPlanReadOnlyAndDeterministic']=True
            results['automaticDiscoveryNavigationImplemented']=False
            family_request={'captureId':'synthetic-family-no-binding','cycleId':'synthetic-smoke',
                            'expectedRevision':3,'parentId':next_keyword['id'],'asin':next_keyword['asin']}
            family_capture=json.loads(request(opener,base+'/api/discovery/capture-family',family_request))
            if family_capture.get('status')!='configuration_blocked' or family_capture.get('familyEvidence') or family_capture.get('preparedBatch'):
                raise RuntimeError('Unconfigured portable package enabled family capture')
            if json.loads(request(opener,base+'/api/discovery/capture-family',family_request))!=family_capture:
                raise RuntimeError('Family capture replay changed receipt')
            results['unconfiguredFamilyCaptureBlockedAndReplay']=True
            assessment=json.loads(request(opener,base+'/api/discovery/assess-families',
                {'cycleId':'synthetic-smoke','expectedRevision':3}))
            if assessment.get('readOnly') is not True or assessment.get('executionAllowed') is not False or assessment['assessment'].get('dedupEligibleGroupCount')!=0:
                raise RuntimeError('Empty family evidence wrongly authorized deduplication')
            run_safety=json.loads(request(opener,base+'/api/discovery/inspect-run',plan_request))
            if run_safety.get('status')!='execution_disabled' or run_safety.get('automaticNavigationImplemented') is not False:
                raise RuntimeError('Offline controls enabled live discovery run')
            if json.loads(request(opener,base+'/api/discovery/report?id=synthetic-smoke'))!=completed_trace or request(opener,base+'/api/state')!=state_before:
                raise RuntimeError('Family assessment or run inspection wrote business data')
            results['familyAssessmentAndRunSafetyReadOnly']=True
            pilot_request={'runId':'portable-must-not-run','cycleId':'synthetic-smoke',
                'expectedRevision':3,'sourceEventId':next_keyword['id'],
                'maxActions':1,'maxRounds':2,'maxSeconds':30,'planFingerprint':plan['planFingerprint']}
            try:
                request(opener,base+'/api/discovery/start-live',pilot_request)
                raise RuntimeError('Portable package enabled isolated source-only runner')
            except urllib.error.HTTPError as error:
                if error.code!=400:raise
            if json.loads(request(opener,base+'/api/discovery/report?id=synthetic-smoke'))!=completed_trace:
                raise RuntimeError('Rejected live start changed graph')
            if request(opener,base+'/api/state')!=state_before:
                raise RuntimeError('Rejected live start changed workspace')
            results['portableLiveStartRejectedWithoutDataChanges']=True







        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    results = smoke(args.folder)
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=True))


if __name__ == '__main__':
    main()
