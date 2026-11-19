"""No provider generation, browser, or production database access."""
import copy
import hashlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw
import studio_artwork_review as review


class ExistingArtworkReviewTests(unittest.TestCase):
    def setUp(self):
        raw = io.BytesIO(); image=Image.new('RGB', (1600, 1600), '#886644'); draw=ImageDraw.Draw(image)
        for x in range(0,1600,8): draw.line((x,0,x,1600),fill=(80+x%130,55+x%110,35+x%90),width=3)
        draw.rectangle((100,100,800,400),fill='#eee8e2'); image.save(raw, 'PNG')
        self.raw = raw.getvalue()
        self.project = {'id':'current', 'productId':'P', 'plan':{'slots':[{}, {}]}, 'deliverable':'gallery'}
        self.source = {'id':'old', 'projectId':'previous', 'productId':'P', 'slot':1,
                       'status':'needs_revision', 'image':'local:old', 'qc':[{'pass':False, 'issues':['old layout']}], 'manual':False}
        self.data = {'productId':'P', 'projectId':'current', 'runId':'old', 'slot':1,
                     'sha256':hashlib.sha256(self.raw).hexdigest(), 'confirmed':True}
        self.saved = []
        patches = [(review.bridge,'latest_project',{'return_value':self.project}),
                   (review.visual,'get_run',{'side_effect':lambda _:copy.deepcopy(self.source)}),
                   (review.visual,'require_ai_storyboard',{}),
                   (review.bridge,'result_image',{'return_value':(self.raw,'image/png')}),
                   (review.visual,'list_projects',{'return_value':{'runs':[]}}),
                   (review.bridge,'get_view',{'return_value':{'jobs':{}}}),
                   (review.bridge,'task_new',{'return_value':{'id':'task','status':'running'}}),
                   (review.bridge,'task_save',{}),
                   (review.visual,'save_project',{}),
                   (review.visual,'save_run',{'side_effect':lambda r:self.saved.append(copy.deepcopy(r))}),
                   (review.visual,'review',{'return_value':{'pass':True,'issues':[]}}),
                   (review.threading,'Thread',{'side_effect':lambda target,daemon:SimpleNamespace(start=target)})]
        for module,name,kwargs in patches:
            p=patch.object(module,name,**kwargs);p.start();self.addCleanup(p.stop)

    def test_preserves_original_bytes_and_failed_history_without_generation(self):
        with patch.object(review.visual.image_provider,'submit') as submit:
            result=review.start(self.data,{'id':'P'})
        submit.assert_not_called()
        self.assertEqual(result['status'],'done')
        final=self.saved[-1]
        self.assertEqual(final['image'],'local:old')
        self.assertEqual(final['sourceRunId'],'old')
        self.assertEqual(final['qc'][0],self.source['qc'][0])
        self.assertTrue(final['qc'][-1]['pass'])
        self.assertEqual(final['qc'][-1]['technical']['sha256'],self.data['sha256'])
        self.assertFalse(final['manual'])

    def test_rejects_foreign_slot_unknown_submission_stale_plan_or_changed_bytes(self):
        for field,value in [('productId','other'),('slot',0),('status','submit_unknown')]:
            with self.subTest(field=field):
                old=self.source[field];self.source[field]=value
                with self.assertRaises(ValueError):review.start(self.data,{'id':'P'})
                self.source[field]=old
        for changes in [{'confirmed':False},{'projectId':'stale'},{'sha256':'0'*64}]:
            with self.assertRaises(ValueError):review.start({**self.data,**changes},{'id':'P'})
        self.assertEqual(self.saved,[])
