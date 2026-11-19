import copy
import json
import io
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import accounts
import server
import variant_colours as colours


def fixture(verified=False):
    rows = [{'asin':f'B00000000{i}', 'color_name':color, 'size_name':'Small', 'sku':'coat-'+color+'-S'}
            for i,color in enumerate(['White','Dark Gray','Light Brown'],1)]
    observed = rows if verified else rows[:1]
    return {'id':'coat','name':'Test coat','cat':'服装','owner':'tester','status':'制作中','color':'#fff',
        'colors':1,'sizes':1,'colorNames':'White','sizeNames':'S','masterColor':'White','market':'US',
        'sourceUrl':'https://detail.1688.com/offer/123.html',
        'sourceImport':{'market':'US','amazon':{'variants':rows,'listingEligibleVariants':rows[:1],
            'excludedVariants':[{**row,'reason':'原货源仅白色'} for row in rows[1:]]}},
        'supplierVariantCoverage':{'productId':'coat','sourceUrl':'https://detail.1688.com/offer/123.html',
            'checkedAt':'2026-11-13T00:00:00Z','evidence':'ISOLATED TEST source observation',
            'supplierObservedColors':[row['color_name'] for row in observed],'supplierObservedSizes':['S'],
            'supplierObservedVariants':[{'color':row['color_name'],'size':'S'} for row in observed]},
        'editorAsinReference':{'market':'US','variants':[{'asin':row['asin'],'color':row['color_name'],'size':'S'} for row in rows],
            'colors':[{'color':row['color_name'],'mainImage':{'url':'https://m.media-amazon.com/images/I/'+row['asin']+'.jpg',
                'sourceAsin':row['asin'],'sourceUrl':'https://www.amazon.com/dp/'+row['asin'],
                'checkedAt':'2026-11-13T00:00:00Z'}} for row in rows]}}


class AssociationTests(unittest.TestCase):
    def test_missing_supplier_evidence_cannot_restore_or_become_master(self):
        p=fixture();before=copy.deepcopy(p)
        self.assertFalse(colours.display_catalog(p)['dark gray']['canReinstate'])
        for action in (colours.reinstate,colours.set_master):
            with self.assertRaises(ValueError):action(p,{'confirmed':True,'colorKey':'dark gray'},{'id':2})
        self.assertEqual(p,before)

    def test_restore_preserves_exclusions_skus_and_is_idempotent(self):
        p=fixture(True);before=copy.deepcopy(p)
        self.assertTrue(colours.display_catalog(p)['dark gray']['canReinstate'])
        updated,changed=colours.reinstate(p,{'confirmed':True,'colorKey':'dark gray'},{'id':2,'name':'tester'})
        self.assertTrue(changed);self.assertEqual(p,before)
        amazon=updated['sourceImport']['amazon']
        self.assertEqual(amazon['excludedVariants'],p['sourceImport']['amazon']['excludedVariants'])
        self.assertEqual(amazon['variants'],p['sourceImport']['amazon']['variants'])
        self.assertEqual([r['sku'] for r in amazon['listingEligibleVariants']],['coat-White-S','coat-Dark Gray-S'])
        self.assertEqual(updated['colors'],2);self.assertEqual(updated['masterColor'],'White')
        self.assertEqual(amazon['variantEligibilityHistory'][0]['previousExclusions'][0]['reason'],'原货源仅白色')
        self.assertEqual(amazon['variantEligibilityHistory'][0]['actor']['id'],2)
        again,changed=colours.reinstate(updated,{'confirmed':True,'colorKey':'dark gray'},{'id':2})
        self.assertFalse(changed);self.assertEqual(again,updated)
        master,changed=colours.set_master(updated,{'confirmed':True,'colorKey':'dark gray'},{'id':2})
        self.assertTrue(changed);self.assertEqual(master['masterColor'],'Dark Gray')
        self.assertEqual(master['masterColorHistory'][0]['previous'],'White')

    def test_restore_checks_pairs_and_reference_and_requires_explicit_confirmation(self):
        for defect in ('pairs','reference','confirmation'):
            p=fixture(True);data={'confirmed':True,'colorKey':'dark gray'}
            if defect=='pairs':p['supplierVariantCoverage']['supplierObservedVariants']= [{'color':'White','size':'S'}]
            if defect=='reference':p['editorAsinReference']['colors']=[]
            if defect=='confirmation':data['confirmed']=False
            with self.subTest(defect=defect),self.assertRaises(ValueError):colours.reinstate(p,data,{'id':2})

    def test_old_state_save_cannot_switch_master_to_excluded_colour(self):
        p=fixture();changed=copy.deepcopy(p);changed['masterColor']='Dark Gray'
        with self.assertRaises(ValueError):colours.validate_master_changes({'products':[p]},{'products':[changed]})
        colours.validate_master_changes({'products':[p]},{'products':[copy.deepcopy(p)]})


class AssociationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.patches=[patch.object(server,'DB',root/'workspace.sqlite3'),patch.object(accounts,'DB',root/'accounts.sqlite3'),
            patch.object(server.account_spaces,'needs_proxy',return_value=False),
            patch.object(server.image_provider,'submit',side_effect=AssertionError('No generation allowed'))]
        for p in self.patches:p.start()
        accounts.register({'username':'association-test','name':'Tester','password':'test-password-12345'},setup=True)
        self.token,_=accounts.login({'username':'association-test','password':'test-password-12345'},'test')
        self.seed(fixture(True))
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def seed(self,p):
        with closing(sqlite3.connect(server.DB)) as c, c:
            c.execute('CREATE TABLE IF NOT EXISTS workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            c.execute('INSERT OR REPLACE INTO workspace VALUES(1,1,?)',(json.dumps({'products':[p],'copy':{'coat-US':{'title':'Retain copy'}},'reviews':{}}),))

    def call(self,action,data,authenticated=True,**headers):
        headers={'Content-Type':'application/json',**headers}
        if authenticated:headers['Cookie']='studio_session='+self.token
        path=action if action.startswith('/') else '/api/colours/'+action
        request=Request('http://127.0.0.1:'+str(self.http.server_port)+path,
                        data=json.dumps(data).encode(),headers=headers)
        try:response=urlopen(request)
        except HTTPError as error:response=error
        with response:return response.status,json.load(response)

    def test_owned_revisioned_restore_and_master_validation(self):
        data={'productId':'coat','colorKey':'dark gray','confirmed':True,'revision':1}
        self.assertEqual(self.call('reinstate',data,authenticated=False)[0],401)
        self.assertEqual(self.call('reinstate',data,Origin='https://elsewhere.example')[0],403)
        self.assertEqual(self.call('reinstate',{**data,'productId':'other'})[0],400)
        self.assertEqual(self.call('master',data)[0],400)
        code,result=self.call('reinstate',data);self.assertEqual(code,200);self.assertEqual(result['revision'],2)
        self.assertEqual(result['product']['masterColor'],'White')
        self.assertEqual(self.call('reinstate',data)[0],409)
        code,result=self.call('reinstate',{**data,'revision':2});self.assertEqual(code,200);self.assertFalse(result['changed'])
        self.assertEqual(result['revision'],2)
        self.assertEqual(self.call('master',{**data,'revision':2})[0],200)
        with closing(sqlite3.connect(server.DB)) as c:
            revision,body=c.execute('SELECT revision,body FROM workspace').fetchone()
        self.assertEqual(revision,3);self.assertEqual(json.loads(body)['copy']['coat-US']['title'],'Retain copy')

    def test_failed_supplier_check_is_atomic(self):
        self.seed(fixture())
        data={'productId':'coat','colorKey':'dark gray','confirmed':True,'revision':1}
        self.assertEqual(self.call('reinstate',data)[0],400)
        with closing(sqlite3.connect(server.DB)) as c:revision,body=c.execute('SELECT revision,body FROM workspace').fetchone()
        self.assertEqual(revision,1);self.assertEqual(json.loads(body)['products'][0],fixture())

    def test_legacy_full_state_save_cannot_bypass_master_check(self):
        self.seed(fixture())
        p=fixture();p['masterColor']='Dark Gray'
        self.assertEqual(self.call('/api/state',{'revision':1,'state':{'products':[p],'copy':{},'reviews':{}}})[0],400)
        with closing(sqlite3.connect(server.DB)) as c:revision,body=c.execute('SELECT revision,body FROM workspace').fetchone()
        self.assertEqual(revision,1);self.assertEqual(json.loads(body)['products'][0]['masterColor'],'White')

    def get(self,path,authenticated=True):
        headers={'Cookie':'studio_session='+self.token} if authenticated else {}
        request=Request('http://127.0.0.1:'+str(self.http.server_port)+path,headers=headers)
        try:response=urlopen(request)
        except HTTPError as error:response=error
        with response:return response.status,response.headers.get_content_type(),response.read()

    def test_extracted_get_routes_keep_authentication_and_account_workspace(self):
        self.assertEqual(self.get('/api/colours/sets?productId=coat',authenticated=False)[0],401)
        with patch.object(server.colour_sets,'current_sets',return_value={'sets':[],'colors':[]}) as read:
            code,mime,raw=self.get('/api/colours/sets?productId=coat')
            self.assertEqual(code,200);self.assertEqual(mime,'application/json')
            self.assertEqual(json.loads(raw),{'sets':[],'colors':[]})
            self.assertEqual(read.call_args.args[0],'coat')
            self.assertEqual(read.call_args.args[1],fixture(True))
            self.assertEqual(self.get('/api/colours/sets?productId=another-account-product')[0],400)
            read.assert_called_once()

    def test_extracted_image_and_export_keep_original_bytes_and_history_metadata(self):
        original={'id':'old-set','color':'Dark Gray','colorKey':'dark gray','status':'awaiting_manual',
            'manual':False,'referenceWarnings':['original reminder'],
            'items':[{'slot':0,'status':'awaiting_manual','image':'original-image',
                      'qc':{'pass':True,'issues':[],'warnings':['retained warning']}}]}
        before=copy.deepcopy(original)
        with patch.object(server.colour_sets,'get',return_value=original), \
             patch.object(server.colour_sets,'image_bytes',return_value=(b'original-png-bytes','image/png')):
            code,mime,raw=self.get('/api/colours/image?id=old-set&slot=0')
            self.assertEqual((code,mime,raw),(200,'image/png',b'original-png-bytes'))
            code,mime,raw=self.get('/api/colours/export?id=old-set')
            self.assertEqual((code,mime),(200,'application/zip'))
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                self.assertEqual(archive.read('Dark Gray01.png'),b'original-png-bytes')
                manifest=json.loads(archive.read('image-manifest.json'))
                self.assertFalse(manifest['humanReviewed'])
                self.assertEqual(manifest['referenceWarnings'],original['referenceWarnings'])
                self.assertEqual(manifest['items'][0]['qc'],original['items'][0]['qc'])
        self.assertEqual(original,before)
