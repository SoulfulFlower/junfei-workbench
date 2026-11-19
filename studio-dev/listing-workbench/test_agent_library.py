import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image
import agent_library as library


class LibraryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.data = self.root/'account-1'; self.tid = 'a'*32
        self.folder = self.data/'agent-results'/self.tid; self.out = self.folder/'junfei-preflight'
        self.out.mkdir(parents=True); (self.root/'automation/data').mkdir(parents=True); (self.root/'scripts').mkdir()
        self.config = {'images':{'supplier_image_policy':'user_default_supplier_images'},'browser':{'engine':'ego-lite','script_directory':str(self.root/'scripts'),
            'erp_library_bindings':{'1':[{'enabled':True,'product_id':'p1','parent_sku':'PARENT','store':'Store','marketplace':'US','page':'p15'}]}}}
        self.save_config()
        (self.root/'automation/ego_browser.py').write_text('# fixture only',encoding='utf-8')
        self.task = {'id':self.tid,'productId':'p1','taskMode':'production','profile':{'store':'Store','marketplace':'US','mode':'draft'},
            'snapshot':{'product':{'id':'p1','sku':'PARENT','sourceUrl':'https://detail.1688.com/offer/952542058876.html','junfeiVariantPrices':{'CHILD':'1.23'}},
                'listing':{'title':'Fixture mat','description':'Fixture description','terms':'fixture','bullets':['one','two','three','four','five']},'review':{'copy':True,'images':True}},
            'results':{k:{'ok':True} for k in ('facts','research','listing','images','export','junfeiPreflight')}}
        image=io.BytesIO();Image.new('RGB',(1600,1600),'white').save(image,'PNG');self.image=image.getvalue()
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('p/main.png',self.image)
            z.writestr('PARENT/variants.csv','parent_sku,sku,color,size\nPARENT,CHILD,Clear,50x100\n')
            z.writestr('PARENT/image-manifest.json',json.dumps({'images':[{'file':'p/main.png','color':'Clear','slot':0}]}))
        raw=archive.getvalue();(self.folder/'delivery.zip').write_bytes(raw)
        self.task['results']['export']['sha256']=hashlib.sha256(raw).hexdigest()
        (self.out/'p').mkdir();(self.out/'p/main.png').write_bytes(self.image)
        self.plan={'parentSku':'PARENT','store':'Store','marketplace':'US','currency':'USD','brand':'Generic','sourceUrl':self.task['snapshot']['product']['sourceUrl'],
            'title':'Fixture mat','description':'Fixture description','searchTerms':'fixture','bullets':['one','two','three','four','five'],
            'variants':[{'sku':'CHILD','color':'Clear','size':'50x100','price':'1.23','mainImage':'p/main.png','images':[]}]}
        self.save_plan()
        (self.out/'preflight-record.json').write_text(json.dumps({'taskId':self.tid,'deliverySha256':self.task['results']['export']['sha256']}),encoding='utf-8')
        self.patches=[patch.object(library.agent_erp,'project_root',return_value=self.root),patch.object(library.app_paths,'DATA',self.data)]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def save_config(self):
        (self.root/'automation').mkdir(exist_ok=True)
        (self.root/'automation/config.json').write_text(json.dumps(self.config),encoding='utf-8')

    def save_plan(self):
        (self.out/'products.json').write_text(json.dumps([self.plan]),encoding='utf-8')

    def test_missing_interpreter_stops_before_lock_script_or_receipt(self):
        before = {str(p.relative_to(self.root)) for p in self.root.rglob('*')}
        with patch.object(library.runtime_environment, 'python_command', side_effect=ValueError('missing interpreter')), patch.object(library.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'missing interpreter'):
                library.sync_library(1, self.task)
            run.assert_not_called()
        self.assertEqual(before, {str(p.relative_to(self.root)) for p in self.root.rglob('*')})

    def test_package_is_account_bound_and_uses_verified_export_bytes_and_explicit_price(self):
        _,package=library.package_for(1,self.task)
        self.assertEqual(package['request']['commerce']['variants'][0]['price'],'1.23')
        self.assertEqual(package['assets'][0]['sha256'],hashlib.sha256(self.image).hexdigest())
        self.assertNotIn('rightsVerified',package['assets'][0]);self.assertEqual(package['bindings'],[{'sku':'CHILD','indices':[0]}])
        for user,change in [(2,{}),(1,{'productId':'other'}),(1,{'taskMode':'inspect'}),(1,{'profile':{'store':'Store','marketplace':'US','mode':'publish'}})]:
            with self.subTest(user=user,change=change),self.assertRaises(ValueError):library.package_for(user,{**self.task,**change})

    def test_draft_quote_price_is_recomputed_and_changed_quote_rejected(self):
        self.task['snapshot']['product']['junfeiVariantPrices']={}
        quote={'scope':'draft_estimate_only','priceUsd':'31.06','quoteSha256':'a'*64}
        self.plan['variants'][0]['price']='31.06'
        self.plan['pricingBasis']={'CHILD':quote}
        self.task['results']['junfeiPreflight']['pricingBasis']={'CHILD':quote}
        self.save_plan()
        with patch('quote_pricing.estimate',return_value=quote):
            _,package=library.package_for(1,self.task)
        self.assertEqual(package['request']['commerce']['price'],'31.06')
        with patch('quote_pricing.estimate',return_value={**quote,'quoteSha256':'b'*64}):
            with self.assertRaisesRegex(ValueError,'定价依据已变化'):library.package_for(1,self.task)

    def test_missing_review_price_or_failed_prerequisite_stops_before_browser(self):
        for change in ['review','price','facts','sku','policy']:
            task=copy.deepcopy(self.task)
            if change=='review':task['snapshot']['review']['images']=False
            if change=='price':task['snapshot']['product']['junfeiVariantPrices']={}
            if change=='facts':task['results']['facts']['ok']=False
            if change=='sku':task['snapshot']['product']['sku']='OTHER'
            if change=='policy':self.config['images']={};self.save_config()
            with self.subTest(change=change),patch.object(library.subprocess,'run') as run:
                with self.assertRaises(ValueError):library.sync_library(1,task)
                run.assert_not_called()

    def test_equivalent_price_format_is_accepted_without_using_legacy_pricing(self):
        self.task['snapshot']['product']['junfeiVariantPrices']['CHILD'] = '1.2'
        self.plan['variants'][0]['price'] = '1.20'; self.save_plan()
        _, package = library.package_for(1, self.task)
        self.assertEqual(package['request']['commerce']['variants'][0]['price'], '1.20')
        self.plan['variants'][0]['price'] = '1.21'; self.save_plan()
        with self.assertRaisesRegex(ValueError, '明确USD售价'):
            library.package_for(1, self.task)

    def test_changed_copy_export_and_image_are_rejected(self):
        self.plan['title']='changed';self.save_plan()
        with self.assertRaisesRegex(ValueError,'文案'):library.package_for(1,self.task)
        self.plan['title']='Fixture mat';self.save_plan();(self.out/'p/main.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'原交付包'):library.package_for(1,self.task)
        (self.out/'p/main.png').write_bytes(self.image);(self.folder/'delivery.zip').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'交付包已变化'):library.package_for(1,self.task)

    def test_changed_variant_mapping_is_rejected_against_original_export(self):
        for change in ['color', 'size', 'sku', 'duplicate', 'images']:
            original = copy.deepcopy(self.plan)
            if change == 'duplicate': self.plan['variants'].append(copy.deepcopy(self.plan['variants'][0]))
            elif change == 'images': self.plan['variants'][0]['images'] = ['p/main.png']
            else: self.plan['variants'][0][change] = 'changed'
            self.save_plan()
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, '原交付包'):
                library.package_for(1,self.task)
            self.plan = original

    def test_original_sku_operation_barrier_survives_new_task_or_changed_copy(self):
        prior=self.root/'automation/data/ego-library-draft-executions/1-PARENT.json';prior.parent.mkdir();prior.write_text('{"attemptNumber":2}')
        with patch.object(library.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'已有产品库操作'):library.sync_library(1,self.task)
            run.assert_not_called()

    def test_generated_script_is_valid_and_success_remains_partial(self):
        _,package=library.package_for(1,self.task);real_run=subprocess.run
        def fake(args,**kwargs):
            self.assertEqual(args[0], library.runtime_environment.python_command()[0])
            script=Path(args[args.index('run') + 1]);source=script.read_text(encoding='utf-8')
            with patch.object(library.subprocess,'run',real_run):real_run(['node','--check',str(script)],check=True,capture_output=True)
            self.assertIn("fs.open(receipt,'wx')",source);self.assertNotIn('publish(',source)
            receipt=self.root/'automation/data/ego-library-package-executions/1-PARENT.json'
            receipt.write_text(json.dumps({'accountId':1,'productId':'p1','sku':'PARENT','input':package,'status':'library_package_saved_reopened_verified','saved':True,'published':False,'libraryId':'123'}),encoding='utf-8')
            return subprocess.CompletedProcess(args,0,b'',b'')
        with patch.object(library.subprocess,'run',side_effect=fake):result=library.sync_library(1,self.task)
        self.assertFalse(result['ok']);self.assertFalse(result['published']);self.assertTrue(result['librarySaved'])
        self.assertFalse((self.root/'automation/data/ego-workbench.lock').exists())
        with patch.object(library.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'已有产品库操作'):library.sync_library(1,self.task)
            run.assert_not_called()

    def test_timeout_keeps_global_lock_and_does_not_restart(self):
        with patch.object(library.subprocess,'run',side_effect=subprocess.TimeoutExpired('ego',65)) as run:
            with self.assertRaisesRegex(ValueError,'结果未知'):library.sync_library(1,self.task)
            with self.assertRaisesRegex(ValueError,'未重复启动'):library.sync_library(1,self.task)
            self.assertEqual(run.call_count,1)
        self.assertTrue((self.root/'automation/data/ego-workbench.lock').exists())


if __name__=='__main__':unittest.main()
