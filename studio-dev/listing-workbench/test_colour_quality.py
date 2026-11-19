import unittest,hashlib,json,tempfile,io
from pathlib import Path
from unittest.mock import patch
import colour_quality as q
import colour_sets as c
import image_provider

class QualityTests(unittest.TestCase):
 def test_product_free_card_review_receives_saved_facts_and_exact_pixel_evidence(self):
  from PIL import Image
  b=io.BytesIO();Image.new('RGB',(30,30),'white').save(b,'PNG');raw=b.getvalue()
  project={'uiPlan':{'images':[{'product_presence':'absent','headline':'Composition','big_number':'100% polyester'}]},'productFacts':{'material':'100% Polyester; supplier stated'}}
  with patch.object(c.visual,'encode_reference',return_value='reference'),patch.object(image_provider,'local_image',return_value=raw),patch.object(c.visual,'get_project',return_value=project):
   _,evidence=c.review_inputs({'reference':'reference','masterId':'plan'},{'slot':0,'sourceUpload':'/uploads/master.png','image':'/uploads/result.png','localCorrection':{'method':'local_gallery_recolour'}})
  self.assertTrue(evidence['contentOnlyInformationCard']);self.assertTrue(evidence['unchangedPixels'])
  self.assertEqual(evidence['supplierVerifiedFacts'],project['productFacts'])
  self.assertEqual(evidence['plannedCopy']['big_number'],'100% polyester')
 def test_cosmetic_warning_is_usable_and_remains_visible(self):
  result=q.normalise({'decision':'warn','blockingIssues':[],'warnings':['Tiny hair-edge cast'],'observedColor':'beige'})
  self.assertTrue(result['pass']);self.assertEqual(result['issues'],[]);self.assertEqual(result['warnings'],['Tiny hair-edge cast'])
 def test_wrong_colour_or_structure_cannot_pass_by_setting_warning_decision(self):
  result=q.normalise({'decision':'warn','blockingIssues':['Wrong garment cut'],'warnings':[]})
  self.assertFalse(result['pass']);self.assertEqual(result['decision'],'fail')
 def test_legacy_rejection_is_never_automatically_downgraded(self):
  result=q.normalise({'pass':False,'issues':['Wrong size text']})
  self.assertFalse(result['pass']);self.assertEqual(result['issues'],['Wrong size text'])
 def test_invalid_and_empty_failure_are_rejected(self):
  for data in [None,{'decision':'fail','blockingIssues':[],'warnings':[]},{'decision':'warn','blockingIssues':[],'warnings':'minor'}]:
   with self.assertRaises(ValueError):q.normalise(data)
 def test_policy_rereview_is_hash_bound_once_only_and_never_submits_images(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(c,'DB',Path(folder)/'sets.sqlite3'),patch.object(image_provider,'local_image',return_value=b'unchanged'),patch.object(image_provider,'submit') as submit:
   sha=hashlib.sha256(b'unchanged').hexdigest()
   s={'id':'test','productId':'own','status':'needs_attention','reference':'ref','validated':True,'color':'Beige','items':[{'slot':0,'status':'needs_revision','image':'/uploads/old.png','sourceUpload':'/uploads/source.png','qc':{'pass':False,'issues':['tiny fringe']},'localCorrection':{'sha256':sha}}],
      'reviewResumes':[{'comparisonVersion':1,'reference':'ref','imageHashes':[sha]}]}
   c.save(s)
   with self.assertRaises(ValueError):c.resume_local_review({'id':'test','confirmed':True,'slots':[0]},{'id':'own'})
   data={'id':'test','confirmed':True,'slots':[0],'policyReview':q.POLICY}
   staged=c.resume_local_review(data,{'id':'own'})
   with patch.object(c,'review_inputs',return_value=([],{})),patch.object(c.visual,'model_json',return_value={'decision':'warn','blockingIssues':[],'warnings':['Minor edge cast']}):c.work(staged)
   saved=c.get('test');self.assertEqual(saved['status'],'awaiting_manual');self.assertFalse(saved.get('manual',False))
   self.assertEqual(saved['items'][0]['reviewHistory'][-1]['qc']['issues'],['tiny fringe'])
   saved['status']='needs_attention';saved['items'][0]['status']='needs_revision';c.save(saved)
   with self.assertRaisesRegex(ValueError,'已按本版标准'):c.resume_local_review(data,{'id':'own'})
   submit.assert_not_called()

if __name__=='__main__':unittest.main()
