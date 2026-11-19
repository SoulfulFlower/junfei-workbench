import base64,json,sqlite3,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from PIL import Image
import server,accounts,pixel_recolour as pixel

class PixelApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.patches=[patch.object(server,'DB',cls.root/'state.sqlite3'),patch.object(accounts,'DB',cls.root/'accounts.sqlite3'),patch.object(server.account_spaces,'needs_proxy',return_value=False),patch.object(pixel,'ROOT',cls.root),patch.object(pixel.image_provider,'ROOT',cls.root),patch.object(pixel.colour_sets,'DB',cls.root/'colors.sqlite3')]
        for p in cls.patches:p.start()
        accounts.register({'username':'pixel-test','password':'test-only-password-12345'},setup=True);cls.token,_=accounts.login({'username':'pixel-test','password':'test-only-password-12345'},'test')
        with sqlite3.connect(server.DB) as c:c.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)');c.execute('INSERT INTO workspace VALUES(1,1,?)',(json.dumps({'products':[{'id':'own'}]}),))
        c.close()
        url=pixel.asset(pixel.png(Image.new('RGB',(20,20),(120,30,40))))
        pixel.colour_sets.save({'id':'fixture','productId':'own','masterId':'master','items':[{'slot':0,'sourceUpload':url}]})
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.base='http://127.0.0.1:'+str(cls.http.server_port);cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()
        for p in reversed(cls.patches):p.stop()
        cls.tmp.cleanup()
    def call(self,name,payload,auth=True,**extra):
        headers={'Content-Type':'application/json',**extra}
        if auth:headers['Cookie']='studio_session='+self.token
        try:r=urlopen(Request(self.base+'/api/colours/pixel/'+name,headers=headers,data=json.dumps(payload).encode()))
        except HTTPError as r:return r.code,json.load(r)
        with r:return r.status,json.load(r)
    def test_routes_auth_origin_ownership_and_real_saved_assets(self):
        self.assertEqual(self.call('sources',{'productId':'own'},auth=False)[0],401)
        self.assertEqual(self.call('sources',{'productId':'own'},Origin='https://elsewhere.example')[0],403)
        self.assertEqual(self.call('sources',{'productId':'other'})[0],400)
        self.assertEqual(self.call('sources',[])[0],400)
        self.assertEqual(self.call('sources',{'productId':'own'},**{'X-Workspace-Account':'999'})[0],409)
        status,d=self.call('sources',{'productId':'own'});self.assertEqual(status,200);row=d['sources'][0]
        mask=base64.b64encode(pixel.png(Image.new('L',(20,20),255))).decode();protect=base64.b64encode(pixel.png(Image.new('L',(20,20)))).decode()
        status,record=self.call('save',{'productId':'own',**row,'revision':0,'alpha':mask,'protected':protect});self.assertEqual(status,200)
        self.assertTrue((self.root/record['alpha'].lstrip('/')).is_file())
        status,r=self.call('render',{'productId':'own',**row,'revision':record['revision'],'target':'#e0d9ce'});self.assertEqual(status,200);self.assertEqual(r['renderer'],pixel.VERSION)
        self.assertTrue((self.root/r['image'].lstrip('/')).is_file())
        self.assertEqual(self.call('save',{'productId':'own',**row,'revision':0,'alpha':mask,'protected':protect})[0],400)

    def test_local_segment_and_inspection_routes_share_auth_and_revision_boundary(self):
        import garment_workflow
        self.assertEqual(self.call('segment',{'productId':'own'},auth=False)[0],401)
        self.assertEqual(self.call('segment',{'productId':'other'})[0],400)
        self.assertEqual(self.call('inspect',{'productId':'own'},Origin='https://elsewhere.example')[0],403)
        row=self.call('sources',{'productId':'own'})[1]['sources'][0]
        current=self.call('selection',{'productId':'own',**row})[1]['selection']
        revision=current['revision'] if current else 0
        raw=base64.b64encode(pixel.png(Image.new('L',(20,20)))).decode()
        data={'productId':'own',**row,'revision':revision,'alpha':raw,'protected':raw,'foreground':[[8,8]],'background':[[0,0]]}
        with patch.object(garment_workflow,'select',return_value=(Image.new('L',(20,20),255),{'imageGenerationSubmitted':False})) as infer:
            code,result=self.call('segment',data);self.assertEqual(code,200);self.assertFalse(result['saved'])
            self.assertEqual(self.call('segment',{**data,'sourceHash':'stale'})[0],400)
            self.assertEqual(self.call('segment',{**data,'revision':revision+1})[0],400)
            self.assertEqual(infer.call_count,1)
        code,inspection=self.call('inspect',data);self.assertEqual(code,200);self.assertTrue(inspection['suggestionOnly'])
        self.assertEqual(self.call('selection',{'productId':'own',**row})[1]['selection'],current)

    def test_upload_automatic_routes_need_no_points_and_keep_master_untouched(self):
        import garment_auto
        row=self.call('sources',{'productId':'own'})[1]['sources'][0]
        self.assertEqual(self.call('uploaded-source',{'productId':'other','uploadedSource':row['source']})[0],400)
        self.assertEqual(self.call('auto',{'productId':'own'},auth=False)[0],401)
        code,uploaded=self.call('uploaded-source',{'productId':'own','uploadedSource':row['source']});self.assertEqual(code,200)
        data={'productId':'own',**uploaded['source'],'revision':0}
        with patch.object(garment_auto,'identify',return_value=(Image.new('L',(20,20),255),{'automatic':True,'userPointsRequired':False,'humanReviewed':False})) as model:
            code,result=self.call('auto',data);self.assertEqual(code,200);self.assertTrue(result['automatic']);self.assertFalse(result['userPointsRequired'])
            self.assertEqual(self.call('auto',data)[0],400);self.assertEqual(model.call_count,1)
        self.assertEqual(self.call('sources',{'productId':'own'})[1]['sources'],[row])

if __name__=='__main__':unittest.main()
