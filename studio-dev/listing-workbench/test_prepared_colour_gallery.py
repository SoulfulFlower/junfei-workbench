import copy,hashlib,io,json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import prepared_colour_gallery as prepared

class PreparedColourTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'sets.sqlite3'
        self.product={'id':'isolated-product','masterColor':'Brown'};self.reference='https://example.invalid/real-white.jpg'
        self.reference_upload='/uploads/'+'f'*32+'.png';self.raws={self.reference_upload:b'actual-reference-bytes'}
        sha=hashlib.sha256(self.raws[self.reference_upload]).hexdigest();self.artifacts=[]
        for slot in range(7):
            im=Image.new('RGB',(1600,1600),(slot*20+20,70,90));b=io.BytesIO();im.save(b,'PNG');raw=b.getvalue();url='/uploads/'+hashlib.sha256(raw).hexdigest()[:32]+'.png';self.raws[url]=raw
            proof={'method':'actual_variant_source_layout','productId':self.product['id'],'masterId':'master','referenceSha256':sha,'referenceUpload':self.reference_upload,'humanReviewed':False}
            self.artifacts.append({'slot':slot,'image':url,'sha256':hashlib.sha256(raw).hexdigest(),'provenance':proof})
        self.context={'id':'master','storyboardProjectId':'storyboard','reference':'verified-brown','count':7,'items':[{'slot':i,'baseRun':'run-'+str(i),'sourceUpload':'master-'+str(i),'sourceSha256':'old-'+str(i)} for i in range(7)]}
        self.group={'key':'white','color':'White','references':[{'url':self.reference,'referenceType':'amazon_variant_main','sourceAsin':'B012345678','sourceUrl':'https://example.invalid/child'}]}
        self.project={'uiPlan':{'images':[{'size_chart':i==6} for i in range(7)]}}
        self.patches=[patch.object(prepared.colours,'DB',self.db),patch.object(prepared.local_colour_sources,'context',return_value=self.context),patch.object(prepared.colours,'select_variant',return_value=self.group),patch.object(prepared.colours,'require_master_colour'),patch.object(prepared.visual,'get_project',return_value=self.project),patch.object(prepared.image_provider,'remote_reference',return_value=(self.raws[self.reference_upload],'image/png')),patch.object(prepared.image_provider,'local_image',side_effect=lambda u:self.raws[u]),patch.object(prepared.image_quality,'inspect',return_value={'pass':True}),patch.object(prepared.image_composition,'for_project',return_value={'pass':True})]
        for p in self.patches:p.start()
        self.data={'requestId':str(uuid.uuid4()),'confirmed':True,'masterId':'master','colorKey':'white','reference':self.reference,'artifacts':self.artifacts}
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_complete_candidate_starts_real_qa_and_never_claims_approval(self):
        s=prepared.adopt(self.data,self.product)
        self.assertEqual(s['status'],'validating');self.assertFalse(s['validated']);self.assertFalse(s['manual'])
        self.assertTrue(all(i['status']=='reviewing' and 'qc' not in i for i in s['items']))
        self.assertFalse(s['localTask']['imageApiSubmissionAllowed'])
        s['status']='awaiting_manual';prepared.colours.save(s)
        again=prepared.adopt(self.data,self.product);self.assertEqual(again['id'],s['id']);self.assertEqual(again['status'],'awaiting_manual')
    def test_foreign_product_reference_and_changed_bytes_block_before_reservation(self):
        for change in [{'productId':'foreign'},{'referenceSha256':'0'*64},{'humanReviewed':True}]:
            data=copy.deepcopy(self.data);data['artifacts'][0]['provenance'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):prepared.adopt(data,self.product)
        data=copy.deepcopy(self.data);data['artifacts'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'内容已变化'):prepared.adopt(data,self.product)
        self.assertEqual(prepared.colours.list_sets(self.product['id'])['sets'],[])
    def test_missing_duplicate_and_new_conflicting_gallery_cannot_replace_original(self):
        for artifacts in [self.artifacts[:-1],[self.artifacts[0]]*7]:
            with self.assertRaises(ValueError):prepared.adopt({**self.data,'artifacts':artifacts},self.product)
        prepared.adopt(self.data,self.product)
        data=copy.deepcopy(self.data);data['requestId']=str(uuid.uuid4());data['artifacts'][0]['image']=data['artifacts'][1]['image'];data['artifacts'][0]['sha256']=data['artifacts'][1]['sha256']
        with self.assertRaises(ValueError):prepared.adopt(data,self.product)
    def test_model_task_must_be_terminal_owned_and_bound_to_real_target(self):
        data=copy.deepcopy(self.data);a=data['artifacts'][1];proof=a['provenance'];proof.update(method='native_repair_lace_composite_on_exact_master_geometry',engineTaskId='engine',providerJobId='provider',donorImage=a['image'],donorSha256=a['sha256'],baseSource={'source':'master-1'},outsideChangedPixels=0)
        task={'productId':self.product['id'],'status':'needs_revision','request':{'referenceSha256':[proof['referenceSha256']]},'results':[{'aspectValid':True,'image':a['image'],'providerJobId':'provider','review':{'blocking':True}}]}
        for changed in [{'productId':'foreign'},{'status':'generating'},{'request':{'referenceSha256':['wrong']}}]:
            with self.subTest(changed=changed),patch.object(prepared.image_engine,'get',return_value={**task,**changed}),self.assertRaises(ValueError):prepared.adopt(data,self.product)
        with patch.object(prepared.image_engine,'get',return_value=task):s=prepared.adopt(data,self.product)
        self.assertEqual(s['items'][1]['status'],'reviewing');self.assertNotIn('qc',s['items'][1])

    def test_qa_source_layout_context_requires_current_reference_and_master_binding(self):
        s=prepared.adopt(self.data,self.product);item=s['items'][2]
        evidence=prepared.colours.prepared_artwork_context(s,item)
        self.assertEqual(evidence['method'],'actual_variant_source_layout');self.assertFalse(evidence['humanReviewed'])
        self.assertIn('grant no approval',evidence['instruction'])
        bad=copy.deepcopy(item);bad['localCorrection']['provenance']['masterId']='old-master'
        self.assertEqual(prepared.colours.prepared_artwork_context(s,bad),{})
        bad=copy.deepcopy(item);bad['localCorrection']['provenance']['referenceSha256']='wrong'
        self.assertEqual(prepared.colours.prepared_artwork_context(s,bad),{})

if __name__=='__main__':unittest.main()
