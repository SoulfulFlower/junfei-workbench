import atexit,hashlib,json,os,sqlite3,tempfile,threading,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
import urllib.request,urllib.error

_import=tempfile.TemporaryDirectory(prefix='rotation-setup-import-')
atexit.register(_import.cleanup)
os.environ['JUNFEI_ACCOUNT_DATA']=_import.name
os.environ['JUNFEI_WORKER_USER']='0'
import app_paths
import store_rotation_setup as setup

def payload(revision=0):
 return {'requestId':uuid.uuid4().hex,'revision':revision,'markets':['US','UK'],'targets':[
  {'ziniaoStoreName':'紫鸟测试店A','erpAccount':'测试ERP甲','usStoreName':'测试店A-US','ukStoreName':'测试店A-UK'},
  {'ziniaoStoreName':'紫鸟测试店B','erpAccount':'测试ERP乙','usStoreName':'测试店B-US','ukStoreName':'测试店B-UK'}]}

class SetupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  p=patch.object(app_paths,'DATA',Path(self.temp.name));p.start();self.addCleanup(p.stop)
 def test_empty_read_creates_no_file(self):
  self.assertEqual(setup.read(1),{'revision':0,'setup':None});self.assertFalse(setup.path().exists())
 def test_save_is_name_only_and_cannot_start_workers_or_publish(self):
  with patch('subprocess.Popen',side_effect=AssertionError('No worker')),patch.object(threading.Thread,'start',side_effect=AssertionError('No thread')):
   result=setup.save(1,payload())
  body=result['setup'];self.assertEqual(body['productsPerStoreTurn'],3)
  self.assertFalse(body['publishAuthorized']);self.assertFalse(body['codexStarted'])
  self.assertEqual(body['identityStatus'],'unverified_names')
  self.assertEqual([r['erpAccount']for r in body['targets']],['测试ERP甲','测试ERP乙'])
  self.assertEqual(setup.read(1)['setup'],body)
 def test_request_replay_is_idempotent_even_after_new_revision(self):
  data=payload();first=setup.save(1,data)
  self.assertEqual(setup.save(1,data)['setup'],first['setup'])
  newer=payload(1);newer['targets'].reverse();second=setup.save(1,newer)
  self.assertEqual(setup.save(1,data)['currentRevision'],2)
  self.assertEqual(setup.read(1)['setup'],second['setup'])
  self.assertEqual(setup.read(1,first['setup']['id'])['setup'],first['setup'])
 def test_different_input_cannot_reuse_request_id(self):
  data=payload();first=setup.save(1,data);data['targets'].reverse()
  with self.assertRaises(setup.Conflict):setup.save(1,data)
  self.assertEqual(setup.read(1)['setup'],first['setup'])
 def test_stale_page_cannot_overwrite_current_setup(self):
  first=setup.save(1,payload())
  with self.assertRaises(setup.Conflict):setup.save(1,payload())
  self.assertEqual(setup.read(1)['setup'],first['setup'])
 def test_account_and_worker_scope(self):
  first=setup.save(1,payload());self.assertIsNone(setup.read(2)['setup'])
  with self.assertRaises(ValueError):setup.read(2,first['setup']['id'])
  setup.save(2,payload())
  with patch.object(app_paths,'WORKER_USER',2):
   with self.assertRaises(ValueError):setup.save(1,payload(1))
   with self.assertRaises(ValueError):setup.read(1)
 def test_duplicate_target_and_invalid_names_rejected_before_write(self):
  for change in ('duplicate','empty','country','extra','control'):
   data=payload()
   if change=='duplicate':data['targets'][1]={**data['targets'][0],'ziniaoStoreName':'另一个紫鸟别名'}
   if change=='empty':data['targets'][0]['erpAccount']=' '
   if change=='country':data['markets']=['DE']
   if change=='extra':data['accountId']=2
   if change=='control':data['targets'][0]['usStoreName']='store\nother'
   with self.subTest(change=change),self.assertRaises(ValueError):setup.save(1,data)
  self.assertFalse(setup.path().exists())
 def test_us_only_does_not_inherit_hidden_uk_and_order_is_preserved(self):
  data=payload();data['markets']=['US'];data['targets'].reverse()
  body=setup.save(1,data)['setup']
  self.assertEqual(body['targets'][0]['ziniaoStoreName'],'紫鸟测试店B')
  self.assertTrue(all(row['ukStoreName']==''for row in body['targets']))
 def test_saved_names_are_metadata_not_code_or_verified_external_ids(self):
  data=payload();data['targets'][0]['ziniaoStoreName']='<img src=x onerror=alert(1)>'
  body=setup.save(1,data)['setup']
  self.assertEqual(body['targets'][0]['ziniaoStoreName'],data['targets'][0]['ziniaoStoreName'])
  self.assertNotIn('storeId',body['targets'][0]);self.assertNotIn('erpUserId',body['targets'][0])

class SetupAPITests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import server,accounts
  cls.server=server;cls.accounts=accounts;cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
  cls.patches=[patch.object(app_paths,'DATA',root),patch.object(accounts,'DB',root/'accounts.sqlite3'),
   patch.object(server.account_spaces,'needs_proxy',return_value=False),patch.dict(os.environ,{'JUNFEI_LOCAL_MODE':'0'})]
  for p in cls.patches:p.start()
  accounts.register({'username':'rotationtest','password':'synthetic-test-pass-12345'},setup=True)
  cls.token,_=accounts.login({'username':'rotationtest','password':'synthetic-test-pass-12345'},'test')
  cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
  cls.base='http://127.0.0.1:'+str(cls.http.server_port)
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close();cls.thread.join()
  for p in reversed(cls.patches):p.stop()
  cls.temp.cleanup()
 def call(self,data=None,auth=True,workspace=1):
  headers={'Content-Type':'application/json','X-Workspace-Account':str(workspace)}
  if auth:headers['Cookie']='studio_session='+self.token
  req=urllib.request.Request(self.base+'/api/agent/rotation-setup',headers=headers,data=json.dumps(data).encode()if data is not None else None)
  try:response=urllib.request.urlopen(req)
  except urllib.error.HTTPError as error:response=error
  with response:return response.status,json.loads(response.read())
 def test_auth_and_stale_account_required(self):
  self.assertEqual(self.call(auth=False)[0],401)
  self.assertIn(self.call(workspace=2)[0],(403,409))
 def test_config_save_read_and_conflict_through_real_handler(self):
  current=self.call()[1]['revision'];data=payload(current)
  status,saved=self.call(data);self.assertEqual(status,200)
  self.assertFalse(saved['setup']['codexStarted'])
  self.assertEqual(self.call()[1]['setup']['id'],saved['setup']['id'])
  self.assertEqual(self.call(payload(current))[0],409)
 def test_body_account_cannot_select_another_workspace(self):
  data=payload();data['accountId']=2;self.assertEqual(self.call(data)[0],400)

if __name__=='__main__':unittest.main()
