import json,sqlite3,threading,unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import server,accounts
import local_colour_tasks as local
import test_local_colour_tasks as fixtures


class LocalApiTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.LocalColourTests('test_missing_masks_and_colour_parameters_never_create_any_task');self.fixture.setUp()
  root=self.fixture.root
  self.patches=[patch.object(server,'DB',root/'workspace.sqlite3'),patch.object(accounts,'DB',root/'accounts.sqlite3'),patch.object(server.account_spaces,'needs_proxy',return_value=False)]
  for p in self.patches:p.start()
  accounts.register({'username':'local-route-test','password':'test-only-password-12345'},setup=True)
  self.token,_=accounts.login({'username':'local-route-test','password':'test-only-password-12345'},'test')
  c=sqlite3.connect(server.DB);c.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)');c.execute('INSERT INTO workspace VALUES(1,1,?)',(json.dumps({'products':[self.fixture.product]}),));c.commit();c.close()
  self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.url='http://127.0.0.1:'+str(self.http.server_port)
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.http.shutdown();self.http.server_close();self.thread.join()
  for p in reversed(self.patches):p.stop()
  self.fixture.tearDown()
 def call(self,name,payload,authenticated=True,**headers):
  h={'Content-Type':'application/json',**headers}
  if authenticated:h['Cookie']='studio_session='+self.token
  path=name if name.startswith('/') else '/api/colours/local/'+name
  try:r=urlopen(Request(self.url+path,data=json.dumps(payload).encode(),headers=h))
  except HTTPError as r:return r.code,json.load(r)
  with r:return r.status,json.load(r)
 def test_local_routes_require_account_origin_and_owned_product(self):
  data={'productId':'own',**self.fixture.request()}
  self.assertEqual(self.call('start',data,authenticated=False)[0],401)
  self.assertEqual(self.call('start',data,Origin='https://another.example')[0],403)
  self.assertEqual(self.call('start',{**data,'productId':'other'})[0],400)
  self.assertEqual(self.call('readiness',[],True)[0],400)
  self.assertEqual(self.call('readiness',data,**{'X-Workspace-Account':'999'})[0],409)
 def test_missing_selection_is_explicit_and_does_not_fallback_to_api(self):
  self.fixture.groups['beige']['references'][0]['referenceType']='supplier_product_image'
  data={'productId':'own',**self.fixture.request()}
  code,ready=self.call('readiness',data);self.assertEqual(code,200);self.assertEqual(ready['colors'][0]['missingSlots'],[0,1])
  code,result=self.call('start',data);self.assertEqual(code,409);self.assertFalse(result['imageGenerationSubmitted'])
  self.assertIn('变体主图',result['error']);self.assertEqual(local.colours.list_sets('own')['sets'],[])
 def test_reference_sampling_is_authenticated_and_does_not_save_or_generate(self):
  data={'productId':'own',**self.fixture.request(),'box':[0,0,1,1]}
  self.assertEqual(self.call('sample-reference',data,authenticated=False)[0],401)
  self.assertEqual(self.call('sample-reference',{**data,'productId':'other'})[0],400)
  with patch.object(local.pixel.image_provider,'remote_reference',return_value=(local.pixel.png(local.pixel.Image.new('RGB',(50,50),(175,55,70))),'image/png')):
   code,result=self.call('sample-reference',data)
  self.assertEqual(code,200);self.assertEqual(result['target'],'#af3746');self.assertFalse(result['imageGenerationSubmitted'])
  self.assertEqual(local.colours.list_sets('own')['sets'],[])
 def test_prepare_automatically_reads_linked_variant_main_and_creates_no_colour_job(self):
  import garment_auto
  from PIL import Image
  data={'productId':'own',**self.fixture.request(),'slot':0}
  self.assertEqual(self.call('prepare',data,authenticated=False)[0],401)
  self.assertEqual(self.call('prepare',{**data,'productId':'other'})[0],400)
  with patch.object(local.automatic_reference,'identify',return_value={'target':'#e1d4b2','reference':data['reference'],'referenceSourceAsin':'TEST-beige','source':'automatic_variant_main','sourceSha256':'fixture'}),patch.object(garment_auto,'identify',return_value=(Image.new('L',(40,40),255),{'automatic':True,'version':garment_auto.VERSION})):
   code,result=self.call('prepare',data)
  self.assertEqual(code,200);self.assertEqual(result['recipe']['target'],'#e1d4b2');self.assertFalse(result['userPointsRequired'])
  self.assertEqual(result['recipe']['pipeline'],local.AUTOMATIC_PIPELINE);self.assertEqual(result['selection']['revision'],1)
  self.assertEqual(local.colours.list_sets('own')['sets'],[])
 def test_configure_and_start_route_creates_only_local_job_and_is_idempotent(self):
  self.fixture.selection(0);self.fixture.selection(1)
  data={'productId':'own',**self.fixture.request()}
  self.assertEqual(self.call('configure',{**data,'target':'#e0d9ce'})[0],200)
  code,result=self.call('start',data);self.assertEqual(code,200);self.assertEqual(result['sets'][0]['model'],'local-pixel')
  self.assertFalse(result['imageGenerationSubmitted']);self.assertEqual(self.call('start',data)[0],409)
  self.assertEqual(len(local.colours.list_sets('own')['sets']),1)
 def test_already_open_old_primary_buttons_cannot_submit_paid_images(self):
  self.fixture.groups['beige']['references'][0]['referenceType']='supplier_product_image'
  data={'productId':'own',**self.fixture.request(),'model':'gpt-image-2'}
  with patch.object(server.colour_sets,'start',side_effect=AssertionError('Old API generator must not run')) as api:
   self.assertEqual(self.call('/api/colours/start',data)[0],409)
   self.fixture.groups['beige']['references'][0]['referenceType']='amazon_variant_main';self.fixture.ready()
   code,result=self.call('/api/colours/start',data)
   self.assertEqual(code,200);self.assertEqual(result['sets'][0]['model'],'local-pixel');api.assert_not_called()
 def test_pause_resume_are_account_bound_and_confirmed(self):
  self.fixture.ready();data={'productId':'own',**self.fixture.request()}
  s=self.call('start',data)[1]['sets'][0];control={'productId':'own','id':s['id'],'confirmed':True}
  self.assertEqual(self.call('pause',control,authenticated=False)[0],401)
  self.assertEqual(self.call('pause',control,Origin='https://another.example')[0],403)
  self.assertEqual(self.call('pause',{**control,'productId':'other'})[0],400)
  self.assertEqual(self.call('pause',{**control,'confirmed':False})[0],400)
  code,out=self.call('pause',control);self.assertEqual(code,200);self.assertEqual(out['set']['status'],'local_paused')
  code,out=self.call('resume',control);self.assertEqual(code,200);self.assertEqual(out['set']['status'],'local_preparing')

if __name__=='__main__':unittest.main()
