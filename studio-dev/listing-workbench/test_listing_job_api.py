"""Durable Listing HTTP boundary, including a client closing its connection."""
from contextlib import closing
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import listing_jobs as jobs
import server


class ListingJobAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'studio.sqlite3'
        self.state={'products':[{'id':'P','name':'Saved product','material':'cotton','status':'制作中',
            'copyHistory':[{'market':'US','copy':{'title':'Older'}}]}],
            'copy':{'P-US':{'title':'Existing','lockedFields':['title'],'translations':{'title':'保留'}}},
            'reviews':{'P':{'copy':True,'images':True}}}
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1,1,?)',(json.dumps(self.state),))
        self.user={'id':2,'role':'admin','name':'Fixture'}
        self.patches=[patch.object(server,'DB',self.db),patch.object(jobs,'DB',self.db),
            patch.object(jobs,'ACTIVE',set()),patch.object(server.accounts,'identify',return_value=self.user),
            patch.object(server.account_spaces,'needs_proxy',return_value=False),
            patch.object(jobs.provider,'text_settings',return_value={'model':'mock','api_key':'fixture-only'})]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_http)

    def close_http(self):
        self.http.shutdown();self.http.server_close();self.thread.join(2)

    def call(self,path,data=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        connection.request('GET' if data is None else 'POST',path,
            body=json.dumps(data) if data is not None else None,
            headers={'Content-Type':'application/json',**(headers or {})})
        response=connection.getresponse();raw=response.read();status=response.status;connection.close()
        return status,json.loads(raw) if response.getheader('Content-Type','').startswith('application/json') else raw

    def start(self):
        return self.call('/api/listing-jobs/start',{'productId':'P','market':'US','requestId':'request-api-1','expectedRevision':1})

    def test_authentication_account_header_and_product_input_boundary(self):
        with patch.object(server.accounts,'identify',return_value=None):
            self.assertEqual(self.call('/api/listing-jobs/list')[0],401)
        self.assertEqual(self.call('/api/listing-jobs/list',headers={'X-Workspace-Account':'3'})[0],409)
        with patch.object(jobs,'THREAD_FACTORY') as factory:
            self.assertEqual(self.call('/api/listing-jobs/start',{'productId':'P','market':'US','product':{'name':'forged'}})[0],400)
            factory.assert_not_called()

    def test_default_start_returns_job_and_duplicate_request_reuses_it(self):
        with patch.object(jobs,'THREAD_FACTORY') as factory:
            status,first=self.start();again_status,again=self.start()
        self.assertEqual(status,202);self.assertEqual(again_status,200)
        self.assertEqual(first['job']['id'],again['job']['id']);self.assertTrue(again['job']['reused'])
        self.assertEqual(factory.call_count,1)
        self.assertEqual(self.call('/api/listing-jobs/list')[1]['jobs'][0]['id'],first['job']['id'])
        with patch.object(server.accounts,'identify',return_value={'id':3,'role':'staff'}):
            self.assertEqual(self.call('/api/listing-jobs/status?id='+first['job']['id'])[0],400)

    def test_closed_start_connection_does_not_lose_result_or_duplicate_history(self):
        entered=threading.Event();release=threading.Event()
        def model(product,market,**kwargs):
            self.assertEqual(product['name'],'Saved product');entered.set()
            if not release.wait(3):raise ValueError('fixture timeout')
            return {'copy':{'title':'Generated','description':'Server saved','translations':{'title':'新标题'}}}
        with patch.object(jobs.provider,'generate_listing',side_effect=model) as generate:
            status,response=self.start();self.assertEqual(status,202);jid=response['job']['id']
            self.assertTrue(entered.wait(2));release.set()
            # call() has closed the original HTTP connection. A new one recovers the same job.
            deadline=time.monotonic()+4
            while True:
                _,reopened=self.call('/api/listing-jobs/status?id='+jid)
                if reopened['job']['status']=='applied':break
                if time.monotonic()>deadline:self.fail(reopened)
                time.sleep(.02)
            self.assertEqual(generate.call_count,1)
        self.assertEqual(reopened['job']['result']['copy']['title'],'Existing')
        self.assertEqual(reopened['job']['result']['copy']['description'],'Server saved')
        self.call('/api/listing-jobs/apply',{'id':jid})
        with closing(sqlite3.connect(self.db)) as db:
            state=json.loads(db.execute('SELECT body FROM workspace WHERE id=1').fetchone()[0])
        self.assertEqual(len(state['products'][0]['copyHistory']),2)
        self.assertEqual(state['copy']['P-US']['translations']['title'],'保留')
        self.assertTrue(state['reviews']['P']['images']);self.assertFalse(state['reviews']['P']['copy'])

    def test_reopening_an_interrupted_task_without_receipt_never_resubmits_model(self):
        with patch.object(jobs,'THREAD_FACTORY'),patch.object(jobs.provider,'generate_listing') as model:
            _,first=self.start();jid=first['job']['id'];jobs.ACTIVE.clear()
            status,reopened=self.call('/api/listing-jobs/status?id='+jid)
            self.assertEqual(status,200);self.assertEqual(reopened['job']['status'],'needs_review')
            _,again=self.start();self.assertTrue(again['job']['reused'])
            self.assertEqual(again['job']['id'],jid);model.assert_not_called()


if __name__=='__main__':unittest.main()
