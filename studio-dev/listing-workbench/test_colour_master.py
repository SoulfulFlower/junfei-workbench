import copy
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import colour_master
import colour_sets
import generated_gallery
import image_provider


class SelectedColourMasterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); (self.root/'uploads').mkdir()
        out=io.BytesIO(); Image.new('RGB',(1600,1600),'brown').save(out,format='PNG')
        self.raw=out.getvalue(); self.sha=hashlib.sha256(self.raw).hexdigest()
        self.ref='/uploads/'+('1'*32)+'.png'; (self.root/self.ref.lstrip('/')).write_bytes(self.raw)
        self.job={'id':'job','productId':'p','status':'completed','images':[self.ref],'references':[self.ref],'storyboardProjectId':'plan','storyboardSlot':0}
        self.p={'id':'p','masterColor':'Brown','generatedGallerySelection':{'version':1,'sourceStudioProjectId':'plan','items':[{'jobId':'job','imageIndex':0,'sha256':self.sha}]}}
        self.project={'id':'plan','productId':'p','confirmed':True,'plan':{'slots':[{}]},'aiStoryboard':{'version':1,'origin':'workbench_ai_planner','model':'test-planner'}}
        for mock in [patch.object(image_provider,'ROOT',self.root),patch.object(image_provider,'jobs',return_value={'jobs':[self.job]}),patch.object(colour_master.studio_bridge,'latest_project',return_value=self.project),patch.object(colour_master.agent_review,'gallery_approved',return_value=True),patch.object(generated_gallery.image_budget,'configuration',return_value={'minimum_short_side':1600})]:
            mock.start();self.addCleanup(mock.stop)

    def test_freezes_reviewed_pixels_without_recreation_or_human_approval(self):
        with patch.object(image_provider,'submit') as submit:
            master=colour_master.prepare(self.p)
        submit.assert_not_called();self.assertEqual(master['items'][0]['sourceSha256'],self.sha)
        self.assertEqual(image_provider.local_image(master['items'][0]['sourceUpload']),self.raw)
        self.assertFalse(master['humanReviewed']);self.assertEqual(master['reviewScope'],'draft_only')

    def test_unreviewed_cross_product_and_modified_hash_are_rejected(self):
        with patch.object(colour_master.agent_review,'gallery_approved',return_value=False):
            with self.assertRaisesRegex(ValueError,'审核'):colour_master.prepare(self.p)
        self.job['productId']='other'
        with self.assertRaises(ValueError):colour_master.prepare(self.p)
        self.job['productId']='p';self.p['generatedGallerySelection']['items'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'哈希'):colour_master.prepare(self.p)

    def test_order_and_colour_changes_invalidate_master_identity(self):
        original=colour_master.selection_id(self.p);other=copy.deepcopy(self.p)
        other['masterColor']='Camel';self.assertNotEqual(original,colour_master.selection_id(other))
        other=copy.deepcopy(self.p);other['generatedGallerySelection']['items'][0]['sha256']='a'*64
        self.assertNotEqual(original,colour_master.selection_id(other))

    def test_worker_rejects_changed_frozen_image_before_paid_submit(self):
        master=colour_master.prepare(self.p);item=master['items'][0]
        (self.root/item['sourceUpload'].lstrip('/')).write_bytes(b'changed')
        s={'id':'s','productId':'p','masterId':master['id'],'storyboardProjectId':master['storyboardProjectId'],'validated':True,'status':'queued','items':[item]}
        with patch.object(colour_sets.visual,'get_project',return_value=self.project),patch.object(image_provider,'submit') as submit:
            with self.assertRaisesRegex(ValueError,'内容变化'):colour_sets.work(s)
        submit.assert_not_called()

    def test_current_view_excludes_colour_sets_bound_to_old_selection(self):
        sid=colour_master.selection_id(self.p)
        with patch.object(colour_sets,'list_sets',return_value={'sets':[{'id':'old','masterId':'old'},{'id':'new','masterId':sid}]}):
            self.assertEqual([s['id'] for s in colour_sets.current_sets('p',self.p)['sets']],['new'])


if __name__=='__main__':unittest.main()
