"""Account lifecycle/FIFO recovery tests; no worker process or browser is launched."""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import account_spaces as spaces
import accounts
import app_paths
import supplier_capture as q

URL='https://detail.1688.com/offer/1001.html'
OTHER='https://detail.1688.com/offer/1002.html'
ROUTE={'spaceId':987,'name':'fixture session','label':'p1'}


class SupplierLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()
        self.main=self.root/'main';self.main.mkdir()
        self.workspaces=self.main/'account-workspaces'
        for uid in (2,3):
            (self.workspaces/str(uid)).mkdir(parents=True)
        self.scope=lambda uid:q.scope_for_data(self.main if uid==1 else self.workspaces/str(uid))
        self.patches=[patch.object(app_paths,'DATA',self.main),patch.object(app_paths,'WORKER_USER',0),
                      patch.object(q,'DB',self.main/'supplier-capture-queue.sqlite3'),patch.object(q,'SCOPE',self.scope(2)),
                      patch.object(accounts,'DB',self.root/'accounts.sqlite3'),patch.object(spaces,'WORKSPACE_ROOT',self.workspaces),
                      patch.object(spaces,'WORKERS',{}),patch.object(q,'kick'),patch.object(q,'browser_capture')]
        for p in self.patches:p.start()
        self.addCleanup(self.tmp.cleanup)
        for p in self.patches:self.addCleanup(p.stop)
        with accounts.connect() as c:
            for uid,role in ((1,'admin'),(2,'staff'),(3,'staff')):
                c.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',(uid,'user'+str(uid),'Fixture','fixture-only',role,'active'))
        self.actor={'id':1,'role':'admin'}

    def enqueue(self,uid,url):
        with patch.object(q,'SCOPE',self.scope(uid)):
            return q.request(url)

    def claim(self,uid):
        with patch.object(q,'SCOPE',self.scope(uid)):
            return q._claim()

    def test_head_owner_is_woken_without_another_visit_and_fifo_moves_to_next_account(self):
        self.enqueue(2,URL);self.enqueue(3,OTHER)
        with patch.object(q,'SCOPE',self.scope(3)),patch.object(spaces,'start') as start:
            self.assertEqual(spaces.dispatch_supplier_once(),2)
            start.assert_called_once_with(2)
        row,g=self.claim(2)
        q._finish(row,g,{'status':'collected','supplier':{'url':URL,'title':'Fixture valid product','images':['fixture']}})
        with patch.object(spaces,'start') as start:
            self.assertIsNone(spaces.dispatch_supplier_once())  # The original 90 second gate remains.
            start.assert_not_called()
        with closing(q.connect()) as c,c:
            g=q.gate(c);g['nextAt']=0;q.save_gate(c,g)
        with patch.object(spaces,'start') as start:
            self.assertEqual(spaces.dispatch_supplier_once(),3)
            start.assert_called_once_with(3)
        q.browser_capture.assert_not_called()

    def test_disable_cancels_only_unstarted_jobs_and_keeps_audit_and_other_accounts(self):
        first=self.enqueue(2,URL);self.enqueue(3,OTHER)
        accounts.update({'id':2,'status':'disabled'},self.actor)
        with closing(q.connect()) as c:
            self.assertEqual(c.execute('SELECT state FROM captures WHERE id=?',(first['id'],)).fetchone()[0],'cancelled')
            audit=c.execute('SELECT kind,body FROM capture_events WHERE capture_id=?',(first['id'],)).fetchone()
            self.assertEqual(audit['kind'],'cancelled_before_execution')
            self.assertEqual(json.loads(audit['body'])['accountStatus'],'disabled')
        with patch.object(spaces,'start') as start:
            self.assertEqual(spaces.dispatch_supplier_once(),3)
            start.assert_called_once_with(3)
        with self.assertRaisesRegex(ValueError,'已停用'):q.request(URL)
        accounts.update({'id':2,'status':'active'},self.actor)
        q.kick.reset_mock()
        q.maintain()
        q.kick.assert_not_called()  # Enabling alone does not resurrect cancelled work.
        self.assertEqual(q.request(URL)['status'],'queued')  # A fresh explicit request is allowed.

    def test_deleted_paused_account_cannot_be_purged_or_replayed_and_can_be_restored(self):
        self.enqueue(2,URL);self.enqueue(2,OTHER)
        row,g=self.claim(2)
        q._finish(row,g,{'status':'paused','reason':'login_or_verification','browser':ROUTE})
        file=self.workspaces/'2'/'original-receipt.json';file.write_text('fixture receipt')
        process=Mock();process.poll.return_value=None
        spaces.WORKERS[2]={'process':process}
        accounts.update({'id':2,'action':'delete'},self.actor)
        with self.assertRaisesRegex(ValueError,'原任务和回执'):
            accounts.update({'id':2,'action':'purge','confirmUsername':'user2'},self.actor)
        process.terminate.assert_not_called();self.assertTrue(file.is_file())
        with closing(q.connect()) as c:
            current=q.gate(c)
            self.assertEqual((current['active'],current['runId'],current['browser']),(row['id'],g['runId'],ROUTE))
            self.assertTrue(current['paused']);self.assertEqual(current['reason'],'login_or_verification')
        with patch.object(spaces,'start') as start:
            self.assertIsNone(spaces.dispatch_supplier_once());start.assert_not_called()
        q.maintain();q.browser_capture.assert_not_called()
        self.assertFalse(q.status()['canResume'])
        accounts.update({'id':2,'action':'restore'},self.actor)
        accounts.update({'id':2,'status':'active'},self.actor)
        self.assertTrue(q.status()['canResume'])
        q.browser_capture.return_value={'status':'collected','supplier':{'url':URL,'title':'Fixture valid product','images':['fixture']}}
        q.resume()
        self.assertEqual(q.browser_capture.call_args.args[:3],(URL,ROUTE,True))
        self.assertEqual(q.item(OTHER)['status'],'cancelled')

    def test_purge_archives_cache_and_removes_only_cancelled_account_directory(self):
        first=self.enqueue(3,URL)
        with patch.object(q,'SCOPE',self.scope(3)):
            q.remember({'url':OTHER,'title':'Fixture completed product','images':['fixture']})
        accounts.update({'id':3,'action':'delete'},self.actor)
        accounts.update({'id':3,'action':'purge','confirmUsername':'user3'},self.actor)
        self.assertFalse((self.workspaces/'3').exists());self.assertTrue((self.workspaces/'2').exists())
        with closing(q.connect()) as c:
            self.assertEqual(c.execute('SELECT state FROM captures WHERE id=?',(first['id'],)).fetchone()[0],'cancelled')
            self.assertEqual(c.execute('SELECT state FROM captures WHERE scope=? AND url=?',(self.scope(3),OTHER)).fetchone()[0],'archived')
        with patch.object(accounts,'password_hash',return_value='fixture hash'):
            accounts.register({'username':'new-user','password':'fixture-pass-1234'})
        self.assertEqual(accounts.users()['users'][-1]['id'],4)
        q.browser_capture.assert_not_called()

    def test_legacy_database_highest_id_is_not_reused_after_purge(self):
        # Users were inserted directly, with no new account_sequence migration yet.
        accounts.update({'id':3,'action':'delete'},self.actor)
        accounts.update({'id':3,'action':'purge','confirmUsername':'user3'},self.actor)
        with patch.object(accounts,'password_hash',return_value='fixture hash'):
            accounts.register({'username':'next-user','password':'fixture-pass-1234'})
        self.assertEqual(accounts.users()['users'][-1]['id'],4)

    def test_orphaned_queued_job_is_cancelled_but_orphaned_active_identity_is_preserved(self):
        orphan='scope-from-a-permanently-deleted-account'
        with patch.object(q,'SCOPE',orphan):first=q.request(URL)
        self.enqueue(3,OTHER)
        with patch.object(spaces,'start') as start:
            self.assertEqual(spaces.dispatch_supplier_once(),3);start.assert_called_once_with(3)
        with closing(q.connect()) as c,c:
            self.assertEqual(c.execute('SELECT state FROM captures WHERE id=?',(first['id'],)).fetchone()[0],'cancelled')
            c.execute("UPDATE captures SET state='reading' WHERE id=?",(first['id'],))
            q.save_gate(c,{'active':first['id'],'paused':True,'runId':'a'*32,'browser':ROUTE,'reason':'execution_unknown'})
        with patch.object(spaces,'start') as start:
            self.assertIsNone(spaces.dispatch_supplier_once());start.assert_not_called()
        with closing(q.connect()) as c:
            g=q.gate(c);self.assertEqual(g['active'],first['id']);self.assertEqual(g['runId'],'a'*32)
            self.assertTrue(g['paused']);self.assertEqual(g['browser'],ROUTE)
        q.browser_capture.assert_not_called()

    def test_runtime_maintenance_recovers_receipt_without_reopening_or_replaying(self):
        self.enqueue(2,URL);row,g=self.claim(2)
        target=self.workspaces/'2'/'supplier-capture-runs'/g['runId'];target.mkdir(parents=True)
        (target/'result.json').write_text(json.dumps({'status':'collected','supplier':{'url':URL,'title':'Fixture valid product','images':['fixture']}}))
        with closing(q.connect()) as c,c:
            g['startedAt']=time.time()-181;q.save_gate(c,g)
        with patch.object(app_paths,'DATA',self.workspaces/'2'):
            q.maintain()
        self.assertEqual(q.item(URL)['status'],'collected');q.browser_capture.assert_not_called()

    def test_runtime_maintenance_freezes_unknown_and_never_reopens_original_page(self):
        self.enqueue(2,URL);self.enqueue(2,OTHER);row,g=self.claim(2)
        with closing(q.connect()) as c,c:
            g['startedAt']=time.time()-181;q.save_gate(c,g)
        q.kick.reset_mock();q.maintain()
        with closing(q.connect()) as c:
            current=q.gate(c)
        self.assertEqual(current['active'],row['id']);self.assertTrue(current['paused'])
        self.assertEqual(current['reason'],'execution_unknown')
        q.kick.assert_not_called();q.browser_capture.assert_not_called()

    def test_explicit_runtime_start_hook_watches_queue_without_a_page_visit(self):
        observed=threading.Event()
        with patch.object(q,'_WATCH_THREAD',None),patch.object(q,'_WATCH_STOP',threading.Event()),patch.object(q,'maintain',side_effect=lambda:observed.set()):
            q.start_worker()
            try:self.assertTrue(observed.wait(2))
            finally:q.stop_worker();q._WATCH_THREAD.join(2)
        q.browser_capture.assert_not_called()

    def test_old_receipt_cannot_overwrite_a_new_resume_identity(self):
        self.enqueue(2,URL);row,g=self.claim(2)
        with closing(q.connect()) as c,c:
            current=q.gate(c);current['runId']='b'*32;q.save_gate(c,current)
        with self.assertRaisesRegex(ValueError,'采集会话状态已变化'):
            q._finish(row,g,{'status':'collected','supplier':{'url':URL,'title':'Fixture valid product','images':['fixture']}})

    def test_cancelled_read_stops_without_polling_or_requeueing(self):
        self.enqueue(2,URL)
        accounts.update({'id':2,'status':'disabled'},self.actor)
        # Model the caller that was waiting when its account was disabled.
        with patch.object(q,'request',return_value=q.item(URL)),patch.object(q.time,'sleep') as sleep:
            with self.assertRaises(q.Pending) as result:q.read(URL)
        self.assertEqual(result.exception.record['status'],'cancelled')
        self.assertIn('取消',str(result.exception));sleep.assert_not_called()
        q.browser_capture.assert_not_called()


if __name__=='__main__':unittest.main()
