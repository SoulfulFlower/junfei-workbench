import copy
import unittest
from unittest.mock import patch
import agent_review as review
import agent_center


class AgentDraftReviewTests(unittest.TestCase):
    def setUp(self):
        self.worker=patch.object(review.app_paths,'WORKER_USER',1)
        self.worker.start();self.addCleanup(self.worker.stop)
        self.product={'id':'p','sku':'SKU','material':'PVC',
            'masterColor':'Clear','supplierColorReferences':[{'url':'source','color':'Clear'}],
            'generatedGallerySelection':{'version':1,'sourceStudioProjectId':None,'items':[
                {'jobId':'job'+str(i),'imageIndex':0,'sha256':str(i)*64} for i in range(7)]}}
        self.listing={'title':'PVC table pad','bullets':'One\nTwo\nThree\nFour\nFive',
            'description':'Clear PVC','terms':'desk'}
        self.jobs=[{'id':'job'+str(i),'productId':'p','status':'completed','images':['https://example.com/'+str(i)]} for i in range(7)]
        self.rows=[(s,j,0) for s,j in zip(self.product['generatedGallerySelection']['items'],self.jobs)]
        self.product['agentDraftReview']={'version':1,'scope':'draft_only','reviewerType':'agent',
            'accountId':1,'reviewer':'test reviewer','evidence':['test evidence'],
            'reviewedAt':'2026-11-03T01:00:00Z','productSha256':review.product_digest(self.product),
            'copy':{'sha256':review.digest(self.listing),'checks':dict.fromkeys(review.COPY_CHECKS,True)},
            'images':[{'slot':i,'jobId':j['id'],'imageIndex':0,'sourceSha256':str(i)*64,
                'checks':dict.fromkeys(review.IMAGE_CHECKS,True)} for i,j in enumerate(self.jobs)]}

    def test_content_bound_copy_and_images_accept_draft_without_human_flags(self):
        task={'profile':{'mode':'draft'},'snapshot':{'product':self.product,'listing':self.listing,'review':{}}}
        self.assertTrue(agent_center.inspect_listing(task)['ok'])
        with patch('studio_bridge.get_view',return_value={'sets':{}}),patch('colour_sets.list_sets',return_value={'sets':[]}),patch('generated_gallery.image_provider.jobs',return_value={'jobs':self.jobs}):
            result=agent_center.inspect_images(task)
        self.assertTrue(result['ok'],result['issues'])
        self.assertEqual(result['imageRunsAwaitingAttention'],0)
        self.assertTrue(all(not i['humanReviewed'] for i in result['selectedGeneratedImages']))
        task['profile']['mode']='publish'
        self.assertFalse(agent_center.inspect_listing(task)['ok'])

    def test_changed_facts_copy_image_order_or_account_invalidate(self):
        self.assertTrue(review.gallery_approved(self.product,self.rows))
        for mutate in [lambda p:p.update(material='rubber'),
                       lambda p:p['agentDraftReview'].update(accountId=2),
                       lambda p:p['agentDraftReview'].update(scope='publish'),
                       lambda p:p['agentDraftReview']['images'].reverse(),
                       lambda p:p['agentDraftReview']['images'][0]['checks'].update(visualQuality=False)]:
            p=copy.deepcopy(self.product);mutate(p)
            self.assertFalse(review.gallery_approved(p,self.rows))
        self.assertFalse(review.copy_approved(self.product,{**self.listing,'title':'Changed'}))
        self.assertFalse(review.gallery_approved(self.product,list(reversed(self.rows))))

    def test_selected_master_summary_reads_owned_metadata_and_existing_review_without_images(self):
        import generated_gallery as gallery
        with patch.object(gallery.image_provider,'jobs',return_value={'jobs':self.jobs}), \
             patch.object(gallery,'download') as download,patch.object(gallery,'image_bytes') as images, \
             patch.object(gallery.image_provider,'submit') as submit:
            summary=gallery.selection_summary(self.product,None)
        self.assertTrue(summary['ready'],summary)
        self.assertEqual(summary['imageCount'],7)
        self.assertEqual(summary['selection'],self.product['generatedGallerySelection'])
        self.assertEqual(summary['reviewScope'],'draft_only')
        download.assert_not_called();images.assert_not_called();submit.assert_not_called()

    def test_selected_master_summary_rejects_stale_unreviewed_foreign_or_incomplete_metadata(self):
        import generated_gallery as gallery
        with patch.object(gallery.image_provider,'jobs',return_value={'jobs':self.jobs}):
            self.assertFalse(gallery.selection_summary(self.product,'replacement')['ready'])
            for mutate in [lambda p:p.update(material='changed'),
                           lambda p:p['agentDraftReview'].update(accountId=2),
                           lambda p:p['agentDraftReview']['images'][0]['checks'].update(visualQuality=False),
                           lambda p:p['generatedGallerySelection']['items'].pop(),
                           lambda p:p['generatedGallerySelection']['items'].reverse()]:
                product=copy.deepcopy(self.product);mutate(product)
                summary=gallery.selection_summary(product,None)
                self.assertFalse(summary['ready']);self.assertTrue(summary['reason'])
        for jobs in [[],[{**job,'productId':'other'} for job in self.jobs],
                     [{**job,'status':'processing'} for job in self.jobs]]:
            with patch.object(gallery.image_provider,'jobs',return_value={'jobs':jobs}):
                self.assertFalse(gallery.selection_summary(self.product,None)['ready'])
        self.assertIsNone(gallery.selection_summary({'id':'p'},None))

    def test_primary_runtime_resolves_actual_legacy_owner_instead_of_worker_zero(self):
        with patch.object(review.app_paths,'WORKER_USER',0),patch('account_spaces.legacy_owner',return_value=1):
            self.assertTrue(review.copy_approved(self.product,self.listing))
        with patch.object(review.app_paths,'WORKER_USER',0),patch('account_spaces.legacy_owner',return_value=2):
            self.assertFalse(review.copy_approved(self.product,self.listing))

    def test_export_attests_draft_but_verifies_actual_source_bytes(self):
        import generated_gallery as gallery
        from PIL import Image
        import io
        out=io.BytesIO();Image.new('RGB',(1600,1600),'white').save(out,format='PNG')
        raw=out.getvalue();sha=gallery.hashlib.sha256(raw).hexdigest()
        for row,item in zip(self.product['generatedGallerySelection']['items'],self.product['agentDraftReview']['images']):
            row['sha256']=sha;item['sourceSha256']=sha
        self.product['agentDraftReview']['productSha256']=review.product_digest(self.product)
        with patch.object(gallery.image_provider,'jobs',return_value={'jobs':self.jobs}),patch.object(gallery,'image_bytes',return_value=(raw,gallery.inspect(raw))):
            images=gallery.export_images(self.product,None)
        self.assertTrue(all(i['agentReviewedForDraft'] and not i['productionApproved'] and not i['humanReviewed'] for _,i in images))
        self.product['generatedGallerySelection']['items'][0]['sha256']='a'*64
        with patch.object(gallery.image_provider,'jobs',return_value={'jobs':self.jobs}),patch.object(gallery,'image_bytes',return_value=(raw,gallery.inspect(raw))):
            with self.assertRaisesRegex(ValueError,'哈希'):gallery.export_images(self.product,None)

    def test_native_master_requires_current_qc_exact_final_bytes_and_agent_evidence(self):
        runs=[{'id':'run'+str(i),'productId':'p','projectId':'plan','slot':i,
            'status':'awaiting_manual','manual':False,
            'qc':[{'pass':False},{'pass':True,'issues':[], 'technical':{'sha256':str(i)*64}}]} for i in range(7)]
        hashes=[str(i)*64 for i in range(7)]
        self.product['agentDraftReview']['studioImages']=[{'slot':i,'runId':run['id'],
            'projectId':'plan','sourceSha256':hashes[i],'checks':dict.fromkeys(review.IMAGE_CHECKS,True)} for i,run in enumerate(runs)]
        self.assertTrue(review.studio_gallery_approved(self.product,'plan',runs,hashes))
        for change in [lambda r:r[0].update(projectId='old'),lambda r:r[0].update(productId='other'),
                       lambda r:r[0]['qc'][-1].update({'pass':False}),
                       lambda r:r[0]['qc'][-1].update(technical={'sha256':'f'*64}),
                       lambda r:r[0].update(status='needs_revision')]:
            bad=copy.deepcopy(runs);change(bad)
            self.assertFalse(review.studio_gallery_approved(self.product,'plan',bad,hashes))
        self.assertFalse(review.studio_gallery_approved(self.product,'plan',list(reversed(runs)),hashes))
        self.assertFalse(review.studio_gallery_approved(self.product,'plan',runs,['f'*64]+hashes[1:]))
        self.product['material']='changed'
        self.assertFalse(review.studio_gallery_approved(self.product,'plan',runs,hashes))
        self.assertTrue(all(not run['manual'] for run in runs))

    def test_native_local_colour_context_validates_bytes_before_creating_assets(self):
        import local_colour_sources as local
        import hashlib
        raw=b'actual-final-image';sha=hashlib.sha256(raw).hexdigest()
        runs=[{'id':'r'+str(i),'productId':'p','projectId':'plan','slot':i,'image':'local:final',
            'status':'awaiting_manual','manual':False,'qc':[{'pass':True,'issues':[],'technical':{'sha256':sha}}]} for i in range(7)]
        self.product['agentDraftReview']['studioImages']=[{'slot':i,'runId':r['id'],'projectId':'plan',
            'sourceSha256':sha,'checks':dict.fromkeys(review.IMAGE_CHECKS,True)} for i,r in enumerate(runs)]
        with patch.object(local.studio_bridge,'latest_project',return_value={'id':'plan','references':['source']}), \
             patch.object(local.visual,'require_ai_storyboard'), \
             patch.object(local.image_provider.image_budget,'configuration',return_value={'gallery_count':7}), \
             patch.object(local.generated_gallery,'selected',return_value=None), \
             patch.object(local.visual,'list_projects',return_value={'runs':runs}), \
             patch.object(local.studio_bridge,'result_image',return_value=(raw,'image/png')) as read, \
             patch.object(local,'_item',side_effect=lambda slot,raw,**kw:{'slot':slot,**kw}) as create:
            self.assertEqual(len(local.context(self.product)['items']),7)
            create.reset_mock();read.return_value=(b'changed','image/png')
            with self.assertRaisesRegex(ValueError,'哈希'):local.context(self.product)
            create.assert_not_called()


if __name__=='__main__':unittest.main()
