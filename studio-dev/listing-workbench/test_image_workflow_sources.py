import os,sys,json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
from PIL import Image
source=Path(os.environ.get('JUNFEI_WORKFLOW_TEST_SOURCE',Path(__file__).resolve().parent))
sys.path.append(str(source))
import app_paths,image_engine as engine
from image_workflow_sources import list_sources

class SourceBoundary(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
  for obj,key,value in((app_paths,'DATA',root),(engine,'DB',root/'engine.sqlite3')):
   p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)
  self.image=engine.cache(Image.new('RGB',(80,80),'pink'))['url']
 def task(self,*,product='p',mode='suite',status='completed',kind='seller',blocking=False,template=True,receipt=True):
  result={'index':0,'image':self.image,'review':{'identityPreserved':True,'blocking':blocking},'shot':{'apparelKind':kind}}
  if template:result['shot']['officialTemplate']={'id':'template','style':'C63'}
  if receipt:result['templateExecution']={'artworkReferenceSubmitted':True,'completeOriginalPromptSubmitted':True}
  row={'id':uuid.uuid4().hex,'productId':product,'requestId':uuid.uuid4().hex,'created':1,'status':status,'request':{'mode':mode,'brief':'source'},'results':[result]}
  engine.save(row);return row
 def test_only_completed_same_product_real_template_mothers(self):
  expected=self.task()
  for args in({'product':'other'},{'status':'needs_revision'},{'status':'submission_unknown'},{'mode':'repair'},{'kind':'size'},{'blocking':True},{'template':False},{'receipt':False}):self.task(**args)
  result=list_sources('p');self.assertEqual([r['taskId']for r in result],[expected['id']])
 def test_original_white_main_needs_no_advertising_template(self):
  expected=self.task(kind='white',template=False,receipt=False)
  self.assertEqual(list_sources('p')[0]['taskId'],expected['id'])
 def test_missing_asset_is_not_offered_as_valid_source(self):
  self.task();(app_paths.DATA/self.image.lstrip('/')).unlink()
  self.assertEqual(list_sources('p'),[])
 def test_listing_sources_does_not_create_or_launch_jobs(self):
  self.task()
  with closing(engine.db())as c:before=c.execute('select count(*)from tasks').fetchone()[0]
  with patch.object(engine,'launch')as launch:
   list_sources('p');list_sources('p');launch.assert_not_called()
  with closing(engine.db())as c:self.assertEqual(c.execute('select count(*)from tasks').fetchone()[0],before)

if __name__=='__main__':unittest.main()
