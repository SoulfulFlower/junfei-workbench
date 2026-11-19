"""Explicit opt-in live browser read through isolated local HTTP and SQLite.
Never runs automatically. Never navigates, takes over, qualifies or publishes.
Source authenticity must be checked against the original capture evidence.
Replay protection is within this isolated run only. Never use a fresh output
directory to work around a previously uncertain browser execution.
"""
import argparse
import hashlib
import http.cookiejar
import io
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,required=True)
    parser.add_argument('--source-batch',type=Path,required=True)
    parser.add_argument('--asin',required=True)
    parser.add_argument('--phrase',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--read-bound-browser',action='store_true',required=True)
    args=parser.parse_args()
    root=args.project_root.resolve(strict=True);out=args.output.resolve()
    if not out.is_relative_to(root/'outputs') or out.exists():
        raise ValueError('Use a new output directory under this project outputs')
    if args.source_batch.stat().st_size>1024*1024:raise ValueError('Source batch too large')
    batch=json.loads(args.source_batch.read_text(encoding='utf-8'))
    events=batch.get('events',[])
    if len(events)!=3 or [e.get('kind') for e in events]!=['keyword','search','seller'] or events[1].get('parentId')!=events[0].get('id') or events[2].get('parentId')!=events[1].get('id') or batch.get('expectedRevision')!=0:
        raise ValueError('Use the existing actual keyword/search/seller chain')
    out.mkdir()
    data=out/'isolated-account-data';data.mkdir()
    for key in list(os.environ):
        if key.startswith('JUNFEI_') or key in ('OPENAI_API_KEY','DEEPSEEK_API_KEY','APIMART_API_KEY','SELLERSPRITE_MCP_KEY','OPENAI_BASE_URL'):
            os.environ.pop(key,None)
    os.environ.update(JUNFEI_ACCOUNT_DATA=str(data),JUNFEI_ACCOUNTS_DB=str(data/'accounts.sqlite3'),
                      JUNFEI_PROJECT_ROOT=str(root),JUNFEI_WORKER_USER='0',PYTHONDONTWRITEBYTECODE='1')
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(root/'listing-workbench'))
    report={'startedAt':datetime.now(timezone.utc).isoformat(),'success':False,
            'scope':'Supplied keyword/search/seller chain -> one current seller-list read -> isolated ledger -> recorded-title keyword preview/save.',
            'sourceAuthenticityIndependentlyCheckedByHarness':False,
            'replayProtectionScope':'current_isolated_database_only',
            'sourceBatchSha256':hashlib.sha256(args.source_batch.read_bytes()).hexdigest(),
            'realBrowserDispatches':0,'injectedTimeoutDispatches':0,'outsideDataConnectionsBlocked':0,
            'productionLedgerWritten':False,'productWorkspaceWritten':False,
            'qualifiedProducts':0,'productImports':0,'navigationPerformedByHarness':False,
            'paidProviderCalls':0,'published':False,'isolatedAccount':True}
    paths=set()
    original_sql=sqlite3.connect
    def guarded_sql(database,*a,**kw):
        raw=os.fspath(database)
        if raw!=':memory:':
            if raw.startswith('file:'):
                parsed=urllib.parse.urlsplit(raw);raw=urllib.parse.unquote(parsed.path)
                if len(raw)>3 and raw[0]=='/' and raw[2]==':':raw=raw[1:]
            target=Path(raw).resolve()
            if not target.is_relative_to(data):
                report['outsideDataConnectionsBlocked']+=1
                raise AssertionError('SQLite connection outside isolated data refused')
            paths.add(str(target.relative_to(data)))
        return original_sql(database,*a,**kw)
    sqlite3.connect=guarded_sql
    original_connect=socket.socket.connect;original_connect_ex=socket.socket.connect_ex
    def local_only(address):
        if not isinstance(address,tuple) or not ipaddress.ip_address(address[0]).is_loopback:
            raise AssertionError('External Python network forbidden')
    def connect(self,address):local_only(address);return original_connect(self,address)
    def connect_ex(self,address):local_only(address);return original_connect_ex(self,address)
    socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
    import server
    import discovery_browser as browser
    import cyclic_discovery as ledger
    binding,fingerprint=browser._binding(1)
    report['dedicatedBinding']={'spaceId':binding['spaceId'],'name':binding['name'],'label':binding['label']}
    report['bindingFingerprint']=fingerprint
    original_run=subprocess.run
    inject={'timeout':False}
    def allowed_run(args,*a,**kw):
        if not isinstance(args,list) or args[:3]!=[binding['cli'],'nodejs','-e']:
            raise AssertionError('Only fixed dedicated EGO capture subprocess is permitted')
        if inject['timeout']:
            report['injectedTimeoutDispatches']+=1
            raise subprocess.TimeoutExpired('explicit-isolated-fault-injection',45)
        report['realBrowserDispatches']+=1
        if report['realBrowserDispatches']>1:
            raise AssertionError('Unexpected live browser replay refused')
        return original_run(args,*a,**kw)
    subprocess.run=allowed_run
    server.Handler.log_message=lambda *a,**kw:None
    http_server=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http_server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(http_server.server_port)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path,body=None,headers=None):
        h={'Origin':base}
        if body is not None:h['Content-Type']='application/json'
        h.update(headers or {})
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=h)
        try:
            with opener.open(req,timeout=90) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:return error.code,json.loads(error.read())
    def save(name,value):
        with (out/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    try:
        assert call('/api/discovery/captures')[0]==401
        credentials={'username':'isolated'+secrets.token_hex(4),'password':secrets.token_urlsafe(24)+'Aa1!','name':'Isolated seller loop validation'}
        assert call('/api/auth/setup',credentials)[0] in (200,201)
        assert call('/api/auth/login',credentials)[0]==200
        credentials=None
        code,state_before=call('/api/state');assert code==200
        assert call('/api/discovery/captures')==(200,{'items':[]})
        code,source_graph=call('/api/discovery/ingest',batch)
        assert code==200 and source_graph['revision']==1 and source_graph['eventCount']==3
        save('source-graph.json',source_graph)
        request={'captureId':'real-isolated-store-read','cycleId':batch['cycleId'],'expectedRevision':1,
                 'parentId':events[2]['id'],'sellerId':events[2]['sellerId']}
        code,capture=call('/api/discovery/capture-store',request)
        save('real-store-capture-receipt.json',capture)
        report['actualCaptureStatus']=capture.get('status')
        report['actualCaptureReason']=capture.get('reason')
        if code!=200 or capture.get('status')!='captured':
            raise RuntimeError('Live store capture stopped safely: '+str(capture.get('reason','HTTP '+str(code))))
        assert capture['trust']=='unverified_observation' and capture['qualificationEvaluated'] is False
        assert capture['captureKind']=='store' and report['realBrowserDispatches']==1
        assert call('/api/discovery/capture-store',request)==(200,capture)
        assert call('/api/discovery/capture?id=real-isolated-store-read')==(200,capture)
        assert report['realBrowserDispatches']==1
        report['captureReplayDidNotDispatch']=True
        code,store_graph=call('/api/discovery/ingest',capture['preparedBatch'])
        assert code==200 and store_graph['revision']==2 and store_graph['eventCount']==4
        store=next(e for e in store_graph['events'] if e['kind']=='store')
        assert store['parentId']==events[2]['id'] and store['sellerId']==events[2]['sellerId']
        assert store['status']=='captured' and store['trust']=='unverified_observation'
        assert call('/api/discovery/ingest',capture['preparedBatch'])==(200,store_graph)
        save('recorded-store-graph.json',store_graph)
        listed=next((p for p in store['products'] if p['asin']==args.asin),None)
        assert listed is not None,'Selected new product no longer appears in captured visible seller listing'
        assert args.asin!=events[2]['asin'],'Select a different listed product'
        keyword_request={'cycleId':batch['cycleId'],'expectedRevision':2,'parentId':store['id'],
                         'asin':args.asin,'phrase':args.phrase}
        code,prepared=call('/api/discovery/prepare-keyword',keyword_request)
        assert code==200 and prepared['status']=='prepared' and prepared['readOnly']
        assert prepared['sourceKind']=='seller_listing_card' and prepared['qualificationEvaluated'] is False
        assert call('/api/discovery/prepare-keyword',keyword_request)==(200,prepared)
        assert call('/api/discovery/report?id='+urllib.parse.quote(batch['cycleId']))==(200,store_graph)
        assert report['realBrowserDispatches']==1
        save('prepared-new-keyword.json',prepared)
        code,graph=call('/api/discovery/ingest',prepared['preparedBatch'])
        assert code==200 and graph['revision']==3 and graph['eventCount']==5 and graph['roundCount']==2
        assert graph['qualificationEvaluated'] is False and graph['qualifiedCount']==graph['importedCount']==0
        new_keyword=next(e for e in graph['events'] if e['kind']=='keyword' and e['parentId']==store['id'])
        assert new_keyword['asin']==args.asin and new_keyword['sourceTitle']==listed['title']
        assert new_keyword['observedAt']==store['observedAt'] and new_keyword['trust']=='unverified_observation'
        assert all(e['trust']=='unverified_observation' for e in graph['edges'])
        assert {e['relation'] for e in graph['edges']}=={'title_generated_keyword','searched_to_product','sold_by_observed','seller_store_observed','store_listed_product'}
        assert call('/api/discovery/ingest',prepared['preparedBatch'])==(200,graph)
        save('recorded-loop-graph.json',graph)
        report.update(actualSellerId=store['sellerId'],isolatedEvents=graph['eventCount'],
                      observedSellerListCards=len(store['products']),newProductAsin=args.asin,
                      newProductListedTitle=listed['title'],newPhrase=new_keyword['phrase'],
                      sourceChainRecorded=True,keywordPreviewDidNotWrite=True,
                      newSearchPerformed=False,ingestReplayUnchanged=True)
        failure_checks={}
        bad_parent={**request,'captureId':'bad-parent','parentId':events[0]['id'],'expectedRevision':3}
        code,failed=call('/api/discovery/capture-store',bad_parent)
        failure_checks['wrongParentBlocked']=code==200 and failed.get('status')=='blocked' and 'preparedBatch' not in failed
        code,failed=call('/api/discovery/capture-store',{**request,'captureId':'wrong-seller','sellerId':'DIFFERENTSELLER','expectedRevision':3})
        failure_checks['wrongSellerBlocked']=code==200 and failed.get('status')=='blocked'
        code,failed=call('/api/discovery/capture-store',{**request,'captureId':'stale-revision'})
        failure_checks['staleRevisionBlocked']=code==200 and failed.get('status')=='blocked'
        failure_checks['crossOriginBlocked']=call('/api/discovery/capture-store',request,{'Origin':'https://external.invalid'})[0]==403
        failure_checks['wrongAccountHeaderBlocked']=call('/api/discovery/capture-store',request,{'X-Workspace-Account':'999'})[0]==409
        failure_checks['ownerPayloadRejected']=call('/api/discovery/capture-store',{**request,'owner':2})[0]==400
        seller_request={'captureId':request['captureId'],'cycleId':batch['cycleId'],'expectedRevision':3,
                        'parentId':events[1]['id'],'asin':events[2]['asin']}
        failure_checks['crossKindIdReuseRejected']=call('/api/discovery/capture-seller',seller_request)[0]==400
        failure_checks['nonPrefixKeywordRejected']=call('/api/discovery/prepare-keyword',{**keyword_request,'expectedRevision':3,'phrase':'invented unrelated phrase'})[0]==400
        failure_checks['keywordWrongOwnerRejected']=call('/api/discovery/prepare-keyword',{**keyword_request,'expectedRevision':3,'owner':2})[0]==400
        failure_checks['keywordStaleRevisionRejected']=call('/api/discovery/prepare-keyword',keyword_request)[0]==400
        failure_checks['keywordCrossOriginBlocked']=call('/api/discovery/prepare-keyword',{**keyword_request,'expectedRevision':3},{'Origin':'https://external.invalid'})[0]==403
        assert all(failure_checks.values()) and report['realBrowserDispatches']==1
        assert ledger.history(2)=={'items':[]}
        inject['timeout']=True
        timeout_request={**request,'captureId':'injected-store-timeout','expectedRevision':3}
        code,unknown=call('/api/discovery/capture-store',timeout_request)
        failure_checks['injectedTimeoutRetained']=code==200 and unknown.get('status')=='execution_unknown'
        save('simulated-timeout-receipt.json',unknown)
        assert call('/api/discovery/capture-store',timeout_request)==(200,unknown)
        code,following=call('/api/discovery/capture-store',{**request,'captureId':'after-unknown','expectedRevision':3})
        failure_checks['unknownStopsNewStoreRead']=code==200 and following.get('reason')=='prior_capture_unresolved'
        code,following=call('/api/discovery/capture-seller',{**seller_request,'captureId':'seller-after-store-unknown'})
        failure_checks['unknownStopsCrossKindRead']=code==200 and following.get('reason')=='prior_capture_unresolved'
        assert report['injectedTimeoutDispatches']==1 and report['realBrowserDispatches']==1 and all(failure_checks.values())
        report['failureChecks']=failure_checks
        assert call('/api/state')==(200,state_before)
        assert call('/api/discovery/report?id='+urllib.parse.quote(batch['cycleId']))==(200,graph)
        assert browser._binding(1)==(binding,fingerprint)
        assert report['outsideDataConnectionsBlocked']==0
        report.update(success=True,testWorkspaceUnchanged=True,bindingStable=True,
                      simulatedFailureScope='Timeout was intentionally injected after the real successful read; not an actual runtime failure.')
    except Exception as error:
        report.update(errorType=type(error).__name__,error=str(error)[:600])
        import traceback
        report['errorLocation']='; '.join(str(frame.lineno) for frame in traceback.extract_tb(error.__traceback__))
    finally:
        http_server.shutdown();http_server.server_close();thread.join(5)
        report['sqlitePaths']=sorted(paths)
        report['finishedAt']=datetime.now(timezone.utc).isoformat()
        save('live-http-verification.json',report)
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
