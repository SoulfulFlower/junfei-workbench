import io
import json
import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

import app_paths
import image_provider
import image_quality
import local_image_provider as local


def raster(size):
    image=Image.new('RGB',size,'white')
    ImageDraw.Draw(image).rectangle((12,12,size[0]//2,size[1]//2),fill='blue')
    out=io.BytesIO()
    image.save(out,'PNG')
    return out.getvalue()


class LocalImageTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.calls=[]
        self.graph={}
        self.reference='/uploads/'+'a'*32+'.png'
        (self.root/'uploads').mkdir()
        (self.root/self.reference.lstrip('/')).write_bytes(raster((64,64)))
        for module, name, value in ((app_paths,'DATA',self.root),(image_provider,'ROOT',self.root),
                                    (local,'CONFIG',self.root/'comfyui-image.json')):
            self.enterContext(patch.object(module,name,value))
        test=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def respond(self,data):
                self.send_response(200);self.end_headers()
                self.wfile.write(data if isinstance(data,bytes) else json.dumps(data).encode())
            def do_GET(self):
                test.calls.append(self.path)
                if self.path=='/system_stats':
                    self.respond({'devices':[{'name':'Fixture CUDA','type':'cuda','vram_total':8000}]})
                elif self.path=='/object_info/CheckpointLoaderSimple':
                    self.respond({'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['model.safetensors']]}}}})
                elif self.path.startswith('/history/'):
                    self.respond({test.task:{'status':{'completed':True},'outputs':{'10':{'images':[
                        {'filename':test.graph['10']['inputs']['filename_prefix']+'_00001_.png','type':'output','subfolder':''}]}}}})
                elif self.path.startswith('/view?'):
                    self.respond(raster((1024,1024)))
                else:self.send_error(404)
            def do_POST(self):
                test.calls.append(self.path)
                data=self.rfile.read(int(self.headers['Content-Length']))
                if self.path=='/upload/image':
                    filename=re.search(rb'filename="([^"]+)"',data)[1].decode()
                    self.respond({'name':filename,'subfolder':'','type':'input'})
                elif self.path=='/prompt':
                    document=json.loads(data);test.graph=document['prompt'];test.task=document['prompt_id']
                    self.respond({'prompt_id':test.task})
                else:self.send_error(404)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.addCleanup(server.server_close)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.shutdown)
        self.base=f'http://127.0.0.1:{server.server_port}'
        self.request={'productId':'p1','slot':'Main','model':'model.safetensors','prompt':'Blue product on white',
                      'references':[self.reference],'size':'1:1','resolution':'1K'}

    def test_local_job_uses_the_shared_journal_and_polls_after_switch_to_cloud(self):
        public=image_provider.configure({'provider':'comfyui','baseUrl':self.base,'checkpoint':'model.safetensors','activate':True})
        self.assertEqual(public['mode'],'local')
        with patch.object(image_provider,'storyboard_submission',return_value={'storyboardProjectId':'p','storyboardSlot':0}), \
             patch.object(image_provider.image_budget,'reserve',side_effect=AssertionError('cloud budget invoked')):
            job=image_provider.submit(self.request,expected_provider='comfyui')
        self.assertEqual(job['status'],'submitted')
        self.assertEqual(self.graph['5']['inputs']['text'],self.request['prompt'])
        self.assertEqual(self.graph['9']['inputs']['width'],1024)
        image_provider.select_provider('apimart')
        with patch.object(image_provider,'api',side_effect=AssertionError('cloud API invoked')):
            result=image_provider.poll({'id':job['id']})
        self.assertEqual(result['status'],'completed')
        info=image_quality.inspect(image_provider.local_image(result['images'][0]),expected=[1024,1024])
        self.assertTrue(info['pass'])
        self.assertEqual(info['dimensions'],[1024,1024])
        self.assertEqual(self.calls.count('/prompt'),1)

    def test_unsupported_reference_count_and_non_loopback_are_blocked_before_submit(self):
        with self.assertRaises(local.Unavailable):
            local.endpoint('http://127.0.0.1:8188@192.168.0.1')
        image_provider.configure({'provider':'comfyui','baseUrl':self.base,'checkpoint':'model.safetensors','activate':True})
        with patch.object(image_provider,'storyboard_submission',return_value={}), self.assertRaises(local.Unavailable):
            image_provider.submit(dict(self.request,references=[self.reference,self.reference]))
        self.assertNotIn('/prompt',self.calls)
        self.assertFalse((self.root/'image_jobs.sqlite3').exists())

    def test_quality_reports_corrupt_and_duplicate_bytes(self):
        data=raster((64,64))
        self.assertFalse(image_quality.inspect(b'not an image')['pass'])
        self.assertFalse(image_quality.inspect(data,expected=[1024,1024])['pass'])
        self.assertEqual(image_quality.duplicate_issues([data,data])[0]['code'],'DUPLICATE_FILE')
