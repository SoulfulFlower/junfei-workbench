"""Isolated manual UI fixture: python test_ui_server.py (no paid generation)."""
import tempfile
from pathlib import Path
import accounts
import server
import visual_studio
from test_visual_studio import fixture
import json
import assistant_chat

if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as temp:
        server.DATA = Path(temp)
        (server.DATA/'uploads').mkdir()
        server.DB = server.DATA/'studio.sqlite3'
        accounts.DB = server.DATA/'accounts.sqlite3'
        visual_studio.DB = server.DATA/'visual.sqlite3'
        assistant_chat.DB = server.DATA/'assistant.sqlite3'
        server.image_provider.ROOT = server.DATA
        visual_studio.model_json = lambda instruction,*_: ({'reply':'我会先锁定主体外观，再为当前产品规划自然光、浅灰背景的一套图片。你可以继续告诉我想强调的材质或使用场景。','action':{'type':'plan_images','label':'策划这个产品的7张套图','brief':'自然光、简洁浅灰背景'}} if '钧飞跨境团队' in instruction else fixture())
        import base64
        image_name='a'*32+'.png'
        (server.DATA/'uploads'/image_name).write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6clQAAAAASUVORK5CYII='))
        with server.database() as c:
            c.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            product={'id':'UI-ONLY','name':'隔离测试产品','cat':'服装','owner':'测试','status':'制作中','color':'#446688','colors':1,'sizes':1,'market':'UK','material':'polyester','dimensions':'S / M','features':'crew neck; short sleeves','competitorResearch':{'US':{'market':'US','input':'B000000001','keywords':[],'sources':[],'warnings':'美国站隔离报告'},'UK':{'market':'UK','input':'B000000002','keywords':[],'sources':[],'warnings':'英国站隔离报告'}},'assets':[{'url':'/uploads/'+image_name,'name':'测试素材','color':'蓝色'}]}
            c.execute('INSERT INTO workspace VALUES (1,1,?)',(json.dumps({'products':[product],'copy':{},'reviews':{}}),))
        visual_studio.save_project({'id':'ui-plan','productId':'UI-ONLY','references':['/uploads/'+image_name],'brief':'自然光、简洁','created':1,'plan':visual_studio.validate_plan(fixture()),'confirmed':True,'deliverable':'gallery','language':'en'})
        def fake_generate(data):
            import uuid
            rid=uuid.uuid4().hex
            cache=server.DATA/'studio-results';cache.mkdir(exist_ok=True)
            (cache/(rid+'.image')).write_bytes((server.DATA/'uploads'/image_name).read_bytes())
            return visual_studio.save_run({'id':rid,'projectId':data['id'],'slot':data['slot'],'status':'awaiting_manual','image':'https://example.test/test.png','qc':[{'pass':True,'issues':[]}],'manual':False})
        visual_studio.generate=fake_generate
        accounts.register({'username':'uitest','name':'界面测试','password':'ui-test-only-12345'}, setup=True)
        server.image_provider.jobs = lambda: {'jobs': []}
        server.image_provider.poll = lambda _: {'jobs': []}
        server.image_provider.submit = lambda _: {'id':'test-only','status':'pending'}
        # Deterministic text responses exercise browser flows without spending credits.
        def ui_copy(product, market):
            return {'copy': {'title':'Polyester Test Jacket', 'highlights':'Polyester, hooded', 'bullets':'Material: polyester\nHood: attached\nColours: blue\nSizes: S and M\nStyle: plain', 'description':'A plain polyester jacket.', 'terms':'jacket polyester hooded', 'zh':'', 'warnings':'UI fixture', 'translations':{'title':'测试外套'}}}
        server.provider.generate_listing=ui_copy
        server.provider.rewrite_field=lambda data: {'text':'Rewritten '+data['text']}
        http=server.ThreadingHTTPServer(('127.0.0.1',18766),server.Handler)
        import threading
        threading.Thread(target=http.serve_forever,daemon=True).start()
        print('隔离 UI 测试服务：http://127.0.0.1:18766/?product=UI-ONLY',flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            http.shutdown()
            http.server_close()
