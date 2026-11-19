import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import random
from PIL import Image
import generated_gallery as gallery
import delivery_export
import agent_center


class GeneratedGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.raw=self.png((1600,1600))
        self.job={'id':'finished','productId':'p','slot':'main','status':'completed','images':['https://example.com/image.png']}
        self.product={'id':'p','sku':'SKU','masterColor':'Clear','generatedGallerySelection':{
            'version':1,'sourceStudioProjectId':None,'items':[{'jobId':'finished','imageIndex':0}]}}
        for p in [patch.object(gallery.image_provider,'ROOT',self.root),
                  patch.object(gallery.image_provider,'jobs',return_value={'jobs':[self.job]}),
                  patch.object(gallery.image_budget,'configuration',return_value={'minimum_short_side':1600})]:
            p.start();self.addCleanup(p.stop)

    @staticmethod
    def png(size):
        out=io.BytesIO();Image.new('RGB',size,'white').save(out,format='PNG');return out.getvalue()

    def test_selected_jobs_export_in_explicit_order_with_hash_and_no_approval(self):
        other={**self.job,'id':'secondary','slot':'detail'}
        self.product['generatedGallerySelection']['items']=[{'jobId':'secondary'}, {'jobId':'finished'}]
        with patch.object(gallery.image_provider,'jobs',return_value={'jobs':[self.job,other]}),patch.object(gallery,'download',return_value=self.raw) as fetch,patch.object(delivery_export.colour_sets,'list_sets',return_value={'sets':[]}):
            raw=delivery_export.build(self.product,{'title':'Draft title'}, {'sets':{}})
            self.assertEqual(fetch.call_count,2)
            # Cached exact job results work even after remote URLs expire.
            fetch.side_effect=AssertionError('must use cache')
            delivery_export.build(self.product,{'title':'Draft title'},{'sets':{}})
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            manifest=json.loads(z.read('SKU/image-manifest.json'))
            self.assertEqual([i['jobId'] for i in manifest['images']],['secondary','finished'])
            for i in manifest['images']:
                self.assertEqual(hashlib.sha256(z.read(i['file'])).hexdigest(),i['sha256'])
                self.assertFalse(i['humanReviewed']);self.assertFalse(i['productionApproved'])
            self.assertEqual(manifest['images'][0]['file'],'SKU/Clear01.png')
            self.assertTrue(manifest['reviewRequired'])

    def test_unknown_pending_other_product_or_invalid_index_stop_before_download(self):
        for mutation in [{'productId':'other'}, {'status':'processing'}, {'images':[]}]:
            with self.subTest(mutation=mutation),patch.object(gallery.image_provider,'jobs',return_value={'jobs':[{**self.job,**mutation}]}),patch.object(gallery,'download') as fetch:
                with self.assertRaises(ValueError):gallery.export_images(self.product,None)
                fetch.assert_not_called()

    def test_large_export_keeps_dimensions_order_and_source_hash(self):
        pixels = random.Random(19).randbytes(1600*1600*3)
        image = Image.frombytes('RGB', (1600,1600), pixels)
        buffer = io.BytesIO();image.save(buffer, format='PNG')
        original = buffer.getvalue()
        self.assertGreater(len(original), gallery.ERP_MAX_BYTES)
        self.product['generatedGallerySelection']['items'][0]['sha256'] = hashlib.sha256(original).hexdigest()
        with patch.object(gallery,'download',return_value=original),patch.object(delivery_export.colour_sets,'list_sets',return_value={'sets':[]}):
            archive = delivery_export.build(self.product, {'title':'Draft'}, {'sets':{}})
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            item=json.loads(z.read('SKU/image-manifest.json'))['images'][0]
            delivered=z.read(item['file'])
            self.assertEqual(item['file'],'SKU/Clear01.jpg')
            self.assertEqual(item['sourceSha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(item['sha256'],hashlib.sha256(delivered).hexdigest())
            self.assertEqual(item['dimensions'],[1600,1600])
            self.assertLess(len(delivered),gallery.ERP_MAX_BYTES)
            self.assertFalse(item['humanReviewed'])
            self.assertEqual(delivered,gallery.prepare_delivery(original)[0])

    def test_small_original_is_unchanged(self):
        raw, info=gallery.prepare_delivery(self.raw)
        self.assertEqual(raw,self.raw)
        self.assertNotIn('transformation',info)

    def test_different_account_store_cannot_export_owner_job(self):
        with patch.object(gallery.image_provider,'jobs',return_value={'jobs':[]}),patch.object(gallery,'download') as fetch:
            with self.assertRaises(ValueError):gallery.export_images(self.product,None)
            fetch.assert_not_called()

    def test_duplicate_and_stale_selection_are_rejected(self):
        self.product['generatedGallerySelection']['items']*=2
        with self.assertRaises(ValueError):gallery.export_images(self.product,None)
        self.product['generatedGallerySelection']['items']=self.product['generatedGallerySelection']['items'][:1]
        with self.assertRaises(ValueError):gallery.export_images(self.product,'replacement-project')

    def test_hash_mismatch_and_low_resolution_fail_without_silent_missing_image(self):
        self.product['generatedGallerySelection']['items'][0]['sha256']='0'*64
        with patch.object(gallery,'download',return_value=self.raw):
            with self.assertRaisesRegex(ValueError,'哈希'):gallery.export_images(self.product,None)
        with self.assertRaisesRegex(ValueError,'尺寸'):gallery.inspect(self.png((1024,1024)))
        with self.assertRaises(ValueError):gallery.inspect(b'not an image')

    def test_selected_gallery_replaces_old_master_and_excludes_unbound_colour_sets(self):
        self.product['generatedGallerySelection']['sourceStudioProjectId']='old-project'
        view={'sets':{'gallery':{'_projectId':'old-project','images':[{'_runId':'old','final_url':'url','_status':'approved'}]}}}
        variants={'sets':[{'id':'old-red','color':'Red','items':[{'slot':0,'status':'approved','image':'url'}]}]}
        with patch.object(gallery,'download',return_value=self.raw),patch.object(delivery_export.studio_bridge,'result_image') as old,patch.object(delivery_export.colour_sets,'list_sets',return_value=variants),patch.object(delivery_export.colour_sets,'image_bytes') as variant:
            raw=delivery_export.build(self.product,{'title':'Draft'},view)
        old.assert_not_called();variant.assert_not_called()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            manifest=json.loads(z.read('SKU/image-manifest.json'))
            self.assertEqual(len(manifest['images']),1)
            self.assertEqual(manifest['excluded'][0]['setId'],'old-red')

    def test_remote_source_rejects_private_http_credentials_and_redirects(self):
        for url in ['http://example.com/i','https://name:secret@example.com/i','https://example.com:444/i']:
            with self.subTest(url=url),self.assertRaises(ValueError):gallery.download(url)
        with patch.object(gallery.socket,'getaddrinfo',return_value=[(0,0,0,'',('127.0.0.1',443))]),patch.object(gallery,'build_opener') as opener:
            with self.assertRaises(ValueError):gallery.download('https://example.com/i')
            opener.assert_not_called()
        self.assertIsNone(gallery.image_provider.NoImageRedirect().redirect_request(None,None,302,'',{},'https://example.com/other'))

    def inspect_task(self, view=None, sets=None):
        task={'snapshot':{'product':self.product,'review':{'images':True}}}
        with patch('studio_bridge.get_view',return_value=view or {'sets':{}}), \
             patch('colour_sets.list_sets',return_value={'sets':sets or []}), \
             patch.object(gallery,'download') as download, \
             patch.object(agent_center,'image_run_history') as history:
            result=agent_center.inspect_images(task)
        download.assert_not_called();history.assert_not_called()
        return result

    def test_task_center_recognizes_ordered_jobs_without_approving_or_downloading(self):
        jobs=[{**self.job,'id':'job-'+str(n)} for n in range(7)]
        self.product['generatedGallerySelection']['items']=[{'jobId':j['id']} for j in reversed(jobs)]
        self.product['supplierColorReferences']=[{'url':'source','color':'Clear'}]
        with patch.object(gallery.image_provider,'jobs',return_value={'jobs':jobs}):
            result=self.inspect_task()
        self.assertEqual(result['galleryCount'],7)
        self.assertEqual(result['gallerySource'],'generated_jobs')
        self.assertEqual([i['jobId'] for i in result['selectedGeneratedImages']],[j['id'] for j in reversed(jobs)])
        self.assertFalse(result['ok'])
        self.assertTrue(any('未审核' in issue for issue in result['issues']))
        self.assertTrue(all(i['humanReviewed'] is False for i in result['selectedGeneratedImages']))
        self.assertNotIn('https://',json.dumps(result))

    def test_task_center_does_not_fall_back_to_old_approved_gallery(self):
        old={'sets':{'gallery':{'images':[{'final_url':'old','_status':'approved','human_reviewed':True}]*7}}}
        for jobs in [[],[{**self.job,'status':'processing'}],[{**self.job,'productId':'other'}]]:
            with self.subTest(jobs=jobs),patch.object(gallery.image_provider,'jobs',return_value={'jobs':jobs}):
                result=self.inspect_task(view=old)
            self.assertFalse(result['ok']);self.assertEqual(result['galleryCount'],0)
            self.assertEqual(result['selectedGeneratedImages'],[])

    def test_task_center_rejects_stale_selection_and_unbound_colour_coverage(self):
        result=self.inspect_task(view={'sets':{'gallery':{'_projectId':'replacement'}}})
        self.assertTrue(any('视觉方案已更换' in issue for issue in result['issues']))
        self.product['supplierColorReferences']=[{'url':'source','color':'Red'}]
        result=self.inspect_task(sets=[{'id':'old','color':'Red','items':[]}])
        self.assertEqual(result['variantSetCount'],0)
        self.assertTrue(any('缺少颜色图片：Red' in issue for issue in result['issues']))

    def test_task_center_counts_exact_master_derivatives_without_granting_approval(self):
        import colour_master
        self.product['supplierColorReferences']=[{'url':'source','color':'Red'}]
        variant={'id':'current','masterId':colour_master.selection_id(self.product),'color':'Red',
                 'items':[{'slot':n,'status':'awaiting_manual','image':'url','qc':{'pass':True}} for n in range(7)]}
        result=self.inspect_task(sets=[variant,{'id':'stale','masterId':'old','color':'Green','items':[]}])
        self.assertEqual(result['variantSetCount'],1)
        self.assertFalse(any('缺少颜色图片：Red' in issue for issue in result['issues']))
        self.assertIn('Red变体图未审核通过',result['issues'])
        self.assertFalse(result['ok'])


if __name__=='__main__':unittest.main()
