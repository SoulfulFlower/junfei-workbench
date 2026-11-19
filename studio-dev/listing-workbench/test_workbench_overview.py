"""Current pending work must not inherit superseded project failures."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
import workbench_overview as home


class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.state={'products':[{'id':'P','name':'Product','market':'US','status':'制作中'}],
                    'copy':{'P-US':{'title':'Existing'}}}
        self.put('studio.sqlite3','workspace','id INTEGER,body TEXT',[(1,json.dumps(self.state))])
        self.put('visual_studio.sqlite3','runs','updated REAL,body TEXT',[])
        self.put('image_jobs.sqlite3','jobs','body TEXT',[])
        self.original_colour_snapshot=home.workbench_image_tasks.snapshot
        for target in (patch.object(home.discovery_intake,'overview',return_value=[]),
                       patch.object(home.workbench_image_tasks,'snapshot',return_value=[])):
            target.start()
            self.addCleanup(target.stop)

    def put(self,file,table,schema,rows):
        with closing(sqlite3.connect(self.root/file)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS '+table+'('+schema+')')
            db.execute('DELETE FROM '+table)
            if rows:
                db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)

    def runs(self,*values):
        self.put('visual_studio.sqlite3','runs','updated REAL,body TEXT',[
            (time,json.dumps({'productId':'P','projectId':project,'slot':slot,'status':status}))
            for time,project,slot,status in values])

    def projects(self,*values):
        self.put('visual_studio.sqlite3','projects','body TEXT',[
            (json.dumps({'id':project,'productId':'P','created':created,'deliverable':kind}),)
            for project,created,kind in values])

    def metrics(self):return home.overview(self.root,2)['metrics']

    def test_submitted_and_processing_are_active_without_extra_visual_records(self):
        for status in ('pending','submitting','submitted','processing','completed','failed','cancelled'):
            with self.subTest(status=status):
                self.put('image_jobs.sqlite3','jobs','body TEXT',[(json.dumps({'productId':'P','status':status}),)])
                self.assertEqual(self.metrics()['imagesRunning'],int(status in home.IMAGE_JOB_ACTIVE))

    def test_foreign_product_is_not_counted(self):
        self.put('image_jobs.sqlite3','jobs','body TEXT',[(json.dumps({'productId':'OTHER','status':'processing'}),)])
        self.assertEqual(self.metrics()['imagesRunning'],0)

    def test_new_passed_project_replaces_old_failed_and_review_work(self):
        self.projects(('old',1,'gallery'),('new',2,'gallery'))
        self.runs((1,'old',0,'failed'),(1,'old',1,'needs_revision'),
                  (2,'new',0,'approved'),(2,'new',1,'approved'))
        self.assertEqual(self.metrics()['failed'],0)
        self.assertEqual(self.metrics()['qualityPending'],0)

    def test_new_plan_without_runs_still_supersedes_old_failures(self):
        self.projects(('old',1,'gallery'),('new',2,'gallery'))
        self.runs((1,'old',0,'failed'),(1,'old',1,'needs_revision'))
        self.assertEqual(self.metrics()['failed'],0)
        self.assertEqual(self.metrics()['qualityPending'],0)

    def test_current_aplus_remains_pending_when_gallery_is_replanned(self):
        self.projects(('old',1,'gallery'),('new',3,'gallery'),('aplus',2,'aplus'))
        self.runs((1,'old',0,'failed'),(2,'aplus',0,'needs_revision'),(3,'new',0,'approved'))
        self.assertEqual(self.metrics()['failed'],0)
        self.assertEqual(self.metrics()['qualityPending'],1)

    def test_superseded_inflight_work_remains_visible_as_running(self):
        self.projects(('old',1,'gallery'),('new',2,'gallery'))
        self.runs((3,'old',0,'generating'))
        self.assertEqual(self.metrics()['imagesRunning'],1)

    def test_superseded_local_colour_work_is_running_without_cloud_image_job(self):
        self.projects(('old',1,'gallery'),('new',2,'gallery'))
        self.put('colour_sets.sqlite3','sets','body TEXT',[(json.dumps({
            'id':'local','productId':'P','masterId':'old','color':'Red','model':'local-pixel',
            'status':'local_rendering','created':1,'items':[]}),)])
        with patch.object(home.workbench_image_tasks,'snapshot',self.original_colour_snapshot):
            self.assertEqual(home.workbench_image_tasks.snapshot(self.root),[])
            result=self.metrics()
        self.assertEqual(result['imagesRunning'],1)
        self.assertEqual(result['qualityPending'],0)
        self.assertEqual(result['failed'],0)

    def test_legacy_ledger_without_projects_uses_latest_run_project(self):
        self.runs((1,'old',0,'failed'),(1,'old',1,'needs_revision'),(2,'new',0,'approved'))
        self.assertEqual(self.metrics()['failed'],0)
        self.assertEqual(self.metrics()['qualityPending'],0)

    def test_newest_run_of_current_slot_replaces_its_failure(self):
        self.projects(('current',1,'gallery'))
        self.runs((1,'current',0,'failed'),(2,'current',0,'approved'))
        self.assertEqual(self.metrics()['failed'],0)

    def test_formal_listing_and_erp_ledgers_are_included_and_owner_scoped(self):
        self.put('studio.sqlite3','listing_generation_jobs','owner INTEGER,updated REAL,body TEXT',[
            (2,1,json.dumps({'id':'own','productId':'P','status':'running','updatedAt':1})),
            (3,2,json.dumps({'id':'foreign','productId':'P','status':'running','updatedAt':2}))])
        (self.root/'erp-collection').mkdir()
        self.put('erp-collection/jobs.sqlite3','jobs','account_id INTEGER,body TEXT',[
            (2,json.dumps({'id':'erp','productId':'P','status':'needs_reconciliation','updatedAt':1})),
            (3,json.dumps({'id':'foreign-erp','productId':'P','status':'running','updatedAt':2}))])
        result=home.overview(self.root,2)
        self.assertEqual(result['metrics']['listingRunning'],1)
        self.assertEqual(result['metrics']['erpPending'],1)
        self.assertEqual({r['source'] for r in result['recent']},{'文案任务','ERP采集'})
        self.assertEqual(len(result['recent']),2)


if __name__=='__main__':unittest.main()
