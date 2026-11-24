"""Real bad raster must not escape through approved/export/ERP/publish paths."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import colour_sets
import delivery_export
import erp_collection as erp
import publication_flow as publication
from test_image_composition import raster


class DeliveryGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.product={'id':'P','sku':'P','masterColor':'Red','sourceUrl':'https://detail.1688.com/offer/123.html',
                      'purchasePrice':'42','junfeiVariantPrices':{'P-Red-M':'31.25'},
                      'sourceImport':{'amazon':{'variants':[{'asin':'B000000002','sku':'P-Red-M','color_name':'Red','size_name':'M'}]}}}
        self.destination={'id':'store','accountId':2,'marketplace':'US','quantity':88,'handlingDays':3,
                          'store':'Store','baseUrl':'http://127.0.0.1:18775'}
        self.listing={'title':'A garment','bullets':['One','Two','Three','Four','Five'],'description':'Description','terms':'garment'}
        self.groups={'red':{'key':'red','color':'Red','ready':True,
                            'children':[{'sku':'P-Red-M','asin':'B000000002','size':'M'}],
                            'references':[{'url':'/uploads/source.png','aliases':['Red']}]}}
        self.view={'sets':{'gallery':{'_projectId':'current','product_source_url':'/uploads/source.png',
                   'images':[{'_runId':f'run{i}','final_url':'url','_status':'approved','human_reviewed':True,
                              'render_qa':{'ready':True}} for i in range(7)]}}}

    def snapshot(self,raw):
        rows=[(raw,{'slot':i,'mime':'image/png','status':'approved','humanReviewed':True}) for i in range(7)]
        with patch.object(erp.variant_colours,'catalog',return_value=self.groups), \
             patch.object(erp.studio_bridge,'get_view',return_value=self.view), \
             patch.object(erp.generated_gallery,'export_images',return_value=rows), \
             patch.object(erp.colour_sets,'list_sets',return_value={'sets':[]}), \
             patch.object(erp.inputs,'transport',return_value={}):
            return erp.finished_snapshot(2,self.product,self.listing,self.destination,self.root/'media')

    def test_approved_but_small_main_cannot_enter_erp(self):
        with self.assertRaisesRegex(ValueError,'构图不通过'):
            self.snapshot(raster('narrow',background='white',size=(1600,1600)))
        self.assertFalse(list((self.root/'media').glob('*.png')))

    def test_passing_snapshot_contains_actual_hash_bound_report(self):
        result=self.snapshot(raster(size=(1600,1600)))
        for asset in result['assets']:
            self.assertTrue(asset['compositionCheck']['pass'])
            self.assertEqual(asset['compositionCheck']['sha256'],asset['sha256'])
        self.assertEqual(len(result['goodsItems']),1)

    def test_export_blocks_bad_pixels_even_when_old_review_is_approved(self):
        with patch.object(delivery_export.generated_gallery,'export_images',return_value=None), \
             patch.object(delivery_export.studio_bridge,'result_image',return_value=(raster('narrow'),'image/png')), \
             patch.object(delivery_export.colour_sets,'list_sets',return_value={'sets':[]}):
            with self.assertRaisesRegex(ValueError,'构图不通过'):
                delivery_export.build(self.product,{**self.listing,'bullets':'One\nTwo\nThree\nFour\nFive'},self.view)

    def test_publication_rechecks_pixels_before_new_job_or_browser(self):
        old=self.snapshot(raster(size=(1600,1600)))
        rows=[(raster('boxed',size=(1600,1600)),{'slot':i,'mime':'image/png','humanReviewed':True}) for i in range(7)]
        workspace={'products':[self.product],'copy':{'P-US':self.listing}}
        with patch.object(publication,'ROOT',self.root/'publication'), \
             patch.object(erp,'destinations',return_value=[self.destination]), \
             patch.object(publication,'source_receipt',return_value=({'id':'old'},old,{'draftId':'123'})), \
             patch.object(publication,'pairs',return_value=[]), \
             patch.object(erp.variant_colours,'catalog',return_value=self.groups), \
             patch.object(erp.studio_bridge,'get_view',return_value=self.view), \
             patch.object(erp.generated_gallery,'export_images',return_value=rows), \
             patch.object(erp.colour_sets,'list_sets',return_value={'sets':[]}), \
             patch.object(erp.inputs,'transport',return_value={}), \
             patch.object(publication.threading,'Thread') as worker:
            with self.assertRaisesRegex(ValueError,'构图不通过'):
                publication.start(2,workspace,{'productId':'P','destinationId':'store','confirmed':True})
            self.assertEqual(publication.list_jobs(2),[])
            worker.assert_not_called()

    def test_bad_recolour_stops_before_paid_review_or_binding(self):
        project={'id':'master','uiPlan':{'images':[{}]}}
        job={'id':'set','productId':'P','masterId':'master','reference':'target','validated':True,
             'items':[{'slot':0,'status':'reviewing','image':'/uploads/result.png'}]}
        with patch.object(colour_sets.visual,'get_project',return_value=project), \
             patch.object(colour_sets.image_provider,'local_image',return_value=raster('narrow')), \
             patch.object(colour_sets,'save'), patch.object(colour_sets,'bind_finished') as bind, \
             patch.object(colour_sets.visual,'model_json') as model, \
             patch.object(colour_sets.image_provider,'submit') as submit:
            colour_sets.work(job)
        self.assertEqual(job['items'][0]['status'],'needs_revision')
        self.assertFalse(job['items'][0]['qc']['composition']['pass'])
        model.assert_not_called();submit.assert_not_called();bind.assert_not_called()


if __name__=='__main__':unittest.main()
