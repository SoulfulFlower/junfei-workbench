"""Regression checks use temporary ledgers and real local pixels, never paid APIs."""
import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
import local_colour_tasks as local
import colour_sets as colours
import pixel_recolour as pixel
import image_provider
import workbench_image_tasks as image_tasks
import workbench_overview as home
from test_local_colour_tasks import LocalColourTests


class LocalRecoveryTests(LocalColourTests):
 def test_missing_corrupt_or_changed_result_is_not_reused(self):
  item=self.previous(['awaiting_manual','awaiting_manual'])['items'][0]
  self.assertTrue(local._passed(item))
  raw=pixel.image_provider.local_image(item['image'])
  item['localCorrection']={'sha256':'0'*64};self.assertFalse(local._passed(item))
  item['localCorrection']['sha256']=hashlib.sha256(raw).hexdigest();self.assertTrue(local._passed(item))
  path=self.root/item['image'].lstrip('/');path.write_bytes(b'broken image');self.assertFalse(local._passed(item))
  path.unlink();self.assertFalse(local._passed(item))

 def test_malformed_input_stops_persistently_instead_of_hanging(self):
  self.ready();s=local.start(self.request(),self.product)['sets'][0]
  del s['items'][0]['localInput'];colours.save(s)
  local.work(s,self.product);saved=colours.get(s['id'])
  self.assertEqual(saved['status'],'needs_attention');self.assertEqual(saved['localTask']['lastError']['type'],'KeyError')
  self.assertEqual(saved['items'][0]['status'],'local_failed')

 def test_bad_job_and_corrupt_row_do_not_starve_next_job(self):
  self.ready();bad=local.start(self.request(),self.product)['sets'][0]
  del bad['localTask'];colours.save(bad)
  good=copy.deepcopy(bad);good['id']='second';good['localTask']={'id':'new','pendingSlots':[0,1],'recipe':local.parameters(self.configure())};colours.save(good)
  with closing(colours.db()) as c,c:
   c.execute("INSERT INTO sets VALUES('corrupt','own','not json',0)");c.commit()
  with closing(sqlite3.connect(self.root/'studio.sqlite3')) as c,c:
   c.execute('CREATE TABLE workspace(id INTEGER,body TEXT)');c.execute('INSERT INTO workspace VALUES(1,?)',(json.dumps({'products':[self.product]}),))
  with patch.object(local.app_paths,'DATA',self.root):local.run_pending()
  self.assertEqual(colours.get(bad['id'])['status'],'needs_attention')
  self.assertEqual(colours.get('second')['status'],'reviewing')

 def test_pause_mid_render_retains_result_and_resume_does_not_render_it_twice(self):
  self.ready();s=local.start(self.request(),self.product)['sets'][0];render=pixel.render
  def pause_after_render(data,product):
   out=render(data,product)
   local.control('pause',{'id':s['id'],'confirmed':True},product)
   return out
  with patch.object(pixel,'render',side_effect=pause_after_render) as r:local.work(s,self.product)
  saved=colours.get(s['id']);self.assertEqual(saved['status'],'local_paused');self.assertEqual(r.call_count,1)
  self.assertEqual(saved['items'][0]['status'],'local_ready');first=copy.deepcopy(saved['items'][0])
  with self.assertRaises(ValueError):local.control('resume',{'id':s['id'],'confirmed':True},{'id':'another'})
  with self.assertRaises(local.NotReady):local.start(self.request(),self.product)
  local.control('resume',{'id':s['id'],'confirmed':True},self.product)
  with patch.object(pixel,'render',wraps=render) as r:local.work(colours.get(s['id']),self.product)
  self.assertEqual(r.call_count,1);saved=colours.get(s['id']);self.assertEqual(saved['status'],'reviewing')
  self.assertEqual(saved['items'][0]['image'],first['image'])

 def test_preserved_approved_slot_does_not_make_completed_set_fail(self):
  self.configure();self.selection(1);self.previous(['approved','needs_revision'])
  s=local.start(self.request(),self.product)['sets'][0];local.work(s,self.product)
  s=colours.get(s['id']);s['validated']=True
  with patch.object(colours,'review_inputs',return_value=([],{})),patch.object(colours.visual,'model_json',return_value={'decision':'pass','blockingIssues':[],'warnings':[]}):colours.work(s)
  saved=colours.get(s['id']);self.assertEqual(saved['status'],'awaiting_manual');self.assertFalse(saved['manual'])
  self.assertEqual(saved['items'][0]['status'],'approved')

 def test_unknown_action_cannot_start_a_job(self):
  with self.assertRaisesRegex(ValueError,'未知'):local.action('typo',self.request(),self.product)
  self.assertEqual(colours.list_sets('own')['sets'],[])

 def test_corrupt_ledger_blocks_new_submission_and_preserves_original_record(self):
  self.ready()
  with closing(colours.db()) as c,c:c.execute("INSERT INTO sets VALUES('broken','own','not json',0)")
  with self.assertRaisesRegex(local.NotReady,'台账有损坏'):local.start(self.request(),self.product)
  with closing(colours.db()) as c:self.assertEqual(c.execute('SELECT id,body FROM sets').fetchall(),[('broken','not json')])


class OverviewTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.products={p:{'id':p,'name':p,'status':'制作中'} for p in ['one','two']}
  self.put('studio.sqlite3','workspace',{'products':list(self.products.values()),'copy':{}})
 def tearDown(self):self.temp.cleanup()
 def put(self,filename,table,body):
  with closing(sqlite3.connect(self.root/filename)) as c,c:
   c.execute('CREATE TABLE IF NOT EXISTS '+table+'(id INTEGER DEFAULT 1,body TEXT)');c.execute('INSERT INTO '+table+'(body) VALUES(?)',(json.dumps(body),))
 def colour(self,sid,pid,status,master='m'):
  self.put('colour_sets.sqlite3','sets',{'id':sid,'productId':pid,'masterId':master,'model':'local-pixel','color':'Beige','status':status,'created':2,'items':[{'slot':0,'status':status}]})
 def test_home_counts_colour_jobs_and_deduplicates_pending_products(self):
  self.colour('a','one','local_rendering');self.colour('b','one','awaiting_manual');self.colour('c','two','needs_attention')
  self.colour('foreign','not-owned','local_rendering')
  with patch.object(home.discovery_intake,'overview',return_value=[]):out=home.overview(self.root,2)
  self.assertEqual(out['metrics']['imagesRunning'],1);self.assertEqual(out['metrics']['qualityPending'],2)
  self.assertEqual(out['metrics']['failed'],1);self.assertEqual(out['metrics']['erpPending'],0);self.assertEqual(len(out['recent']),3)
 def test_task_controls_and_superseded_master_filter(self):
  self.put('visual_studio.sqlite3','projects',{'id':'current','productId':'one','created':10})
  self.colour('stale','one','needs_attention','old');self.colour('now','one','local_paused','current')
  jobs=image_tasks.snapshot(self.root);self.assertEqual([j['id'] for j in jobs],['now'])
  self.assertTrue(jobs[0]['canResume']);self.assertFalse(jobs[0]['canPause'])
 def test_corrupt_ledger_is_not_shown_as_no_tasks(self):
  self.colour('x','one','local_rendering')
  with closing(sqlite3.connect(self.root/'colour_sets.sqlite3')) as c,c:c.execute("UPDATE sets SET body='bad json'")
  with self.assertRaises(ValueError):image_tasks.snapshot(self.root)


class SubmissionHistoryTests(unittest.TestCase):
 def test_explicit_refusal_is_annotated_without_changing_durable_unknown_state(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(image_provider,'ROOT',Path(folder)):
   job={'id':'blocked','productId':'p','slot':'Beige 3','status':'submission_unknown','proxyDiagnostic':{'httpStatus':400,'message':'Your request was rejected by the safety system.','id':'evidence'}}
   with closing(image_provider.storage()) as c,c:c.execute('INSERT INTO submission_attempts VALUES(?,?,?,?,?)',('blocked','p','Beige 3','submission_unknown',json.dumps(job)))
   out=image_provider.jobs()['jobs'][0];self.assertEqual(out['providerRejection']['kind'],'safety_refusal')
   self.assertEqual(out['status'],'submission_unknown')
   with closing(image_provider.storage()) as c:
    row=c.execute('SELECT state,body FROM submission_attempts').fetchone()
   self.assertEqual(row[0],'submission_unknown');self.assertNotIn('providerRejection',json.loads(row[1]))
 def test_generic_http_error_is_not_mislabelled_as_refusal(self):
  for status,msg in [(400,'invalid request'),(500,'rejected by the safety system'),(400,'network timeout')]:
   self.assertIsNone(image_provider.provider_rejection({'proxyDiagnostic':{'httpStatus':status,'message':msg}}))


if __name__=='__main__':unittest.main()
