import tempfile,io
from PIL import Image
import unittest
from pathlib import Path
from unittest.mock import patch
import colour_sets as colours
import visual_studio as visual
import image_provider

class ColourSetTests(unittest.TestCase):
 def test_recolour_keeps_noncolour_headline_and_uses_observed_pale_shade(self):
  self.master['uiPlan']={'images':[{'headline':'Ribbed Finish','text_on_image':True},{'headline':'Red wrap front','text_on_image':True}]}
  visual.save_project(self.master)
  s={**self.s,'color':'Gray','masterColor':'Red','referenceCheck':{'targetColor':'light heather gray'}}
  prompt=colours.variant_artwork_instruction(s,{'slot':0})
  self.assertIn('"headline": "Ribbed Finish"',prompt)
  self.assertNotIn('Gray Ribbed Finish',prompt)
  self.assertIn('light heather gray',prompt)
  self.assertIn('Pale colours must stay pale',prompt)
  self.assertIn('"headline": "Gray wrap front"',colours.variant_artwork_instruction(s,{'slot':1}))

 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);(root/'uploads').mkdir()
  self.patches=[patch.object(colours,'DB',root/'colour.sqlite3'),patch.object(visual,'DB',root/'visual.sqlite3'),patch.object(image_provider,'ROOT',root),patch.object(visual,'encode_reference',return_value='data:image/png;base64,AA==')]
  for p in self.patches:p.start()
  self.s={'id':'set1','productId':'own','masterId':'master','storyboardProjectId':'master','color':'Red','reference':'target','status':'queued','model':'gpt-image-2','validated':True,'items':[{'slot':i,'baseRun':'base'+str(i),'status':'queued'} for i in range(2)]}
  self.master=visual.save_project({'id':'master','productId':'own','created':1,'references':['source'],'confirmed':True,'aiStoryboard':{'version':1,'origin':'workbench_ai_planner','model':'test-planner'},'plan':{'slots':[{},{}]}})
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def test_amazon_colour_links_legacy_child_without_granting_sku_readiness(self):
  black={'asin':'B000000001','color':'Black','size':'Small'}
  blue={'asin':'B000000002','color':'Blue','size':'Small'}
  image={'url':'https://m.media-amazon.com/images/I/black.jpg','sourceAsin':black['asin'],
         'sourceUrl':'https://www.amazon.com/dp/'+black['asin'],'checkedAt':'2026-11-09T02:00:00Z'}
  reference={'market':'US','variants':[black,blue],'colors':[{'color':'Black','mainImage':image}]}
  product={'id':'own','sourceImport':{'market':'US','amazon':{
      'variants':[black,blue],'listingEligibleVariants':[black]}},'editorAsinReference':reference}
  groups=colours.variant_colours.catalog(product)
  self.assertEqual(list(groups),['black'])
  self.assertEqual(groups['black']['references'][0]['sourceAsin'],black['asin'])
  self.assertEqual(groups['black']['references'][0]['url'],image['url'])
  self.assertFalse(groups['black']['ready'])
  with self.assertRaises(ValueError):colours.select_variant(product,'black',image['url'])
  reference['variants']=[{**black,'color':'Blue'},blue]
  self.assertEqual(colours.variant_colours.catalog(product)['black']['references'],[])
 def test_generation_failure_never_repeats_ambiguous_paid_submit(self):
  with patch.object(colours.studio_bridge,'result_image',return_value=(b'\x89PNG\r\n\x1a\nphoto','image/png')),patch.object(image_provider,'submit',side_effect=ValueError('timeout')) as submit:
   colours.work(self.s)
  saved=colours.get('set1');self.assertEqual(saved['status'],'needs_attention');self.assertEqual(saved['items'][0]['status'],'submit_unknown');self.assertEqual(saved['items'][1]['status'],'queued');submit.assert_called_once()
  with self.assertRaises(ValueError):colours.retry({'id':'set1','slot':0,'confirmed':True},{'id':'own'})
 def test_excluded_colour_is_visible_with_original_reference_but_cannot_generate(self):
  white={'asin':'B000000001','color_name':'White','size_name':'Small','sku':'own-white-S'}
  gray={'asin':'B000000002','color_name':'Dark Gray','size_name':'Small','sku':'own-gray-S'}
  image={'url':'https://m.media-amazon.com/images/I/gray.jpg','sourceAsin':gray['asin'],
         'sourceUrl':'https://www.amazon.com/dp/'+gray['asin'],'checkedAt':'2026-11-12T00:00:00Z'}
  product={'id':'own','market':'US','masterColor':'White',
      'sourceImport':{'market':'US','amazon':{'variants':[white,gray],
       'listingEligibleVariants':[white],'excludedVariants':[{**gray,'reason':'当前选定货源仅白色'}]}},
      'editorAsinReference':{'market':'US','variants':[
       {'asin':white['asin'],'color':'White','size':'Small'},
       {'asin':gray['asin'],'color':'Dark Gray','size':'Small'}],
       'colors':[{'color':'Dark Gray','mainImage':image}]}}
  with patch.object(colours.image_provider.image_budget,'configuration',return_value={'gallery_count':7}):
   view=colours.current_sets('own',product)
  groups={g['key']:g for g in view['colors']}
  self.assertEqual(set(groups),{'white','dark gray'})
  self.assertEqual(groups['dark gray']['references'][0]['sourceAsin'],gray['asin'])
  self.assertEqual(groups['dark gray']['references'][0]['url'],image['url'])
  self.assertEqual(groups['dark gray']['children'][0]['sku'],'own-gray-S')
  self.assertEqual(groups['dark gray']['exclusionReasons'],['当前选定货源仅白色'])
  self.assertFalse(groups['dark gray']['listingEligible'])
  self.assertFalse(groups['dark gray']['ready'])
  self.assertEqual(list(colours.variant_colours.catalog(product)),['white'])
  with patch.object(image_provider,'submit') as submit:
   with self.assertRaises(ValueError):colours.select_variant(product,'dark gray',image['url'])
  submit.assert_not_called()
  self.assertEqual(product['sourceImport']['amazon']['listingEligibleVariants'],[white])
 def test_identity_failure_stops_later_slots_and_retains_master(self):
  self.s['items'][0].update(status='reviewing',image='https://example/image.png',sourceUpload='/uploads/source.png')
  with patch.object(visual,'model_json',return_value={'pass':False,'issues':['Logo moved to skin'],'observedColor':'red'}),patch.object(image_provider,'submit') as submit:
   colours.work(self.s)
  self.assertEqual(colours.get('set1')['items'][0]['status'],'needs_revision');self.assertEqual(self.s['masterId'],'master');submit.assert_not_called()
 def test_ambiguous_slot_is_not_resubmitted_or_marked_complete(self):
  self.s['items'][0].update(status='submit_unknown',error='timeout')
  self.s['items'][1].update(status='awaiting_manual',image='existing')
  with patch.object(image_provider,'submit') as submit:
   colours.work(self.s)
  result=colours.get('set1');submit.assert_not_called()
  self.assertEqual(result['status'],'needs_attention')
  self.assertEqual(result['items'][0]['status'],'submit_unknown')
  self.assertEqual(result['items'][1]['image'],'existing')
 def test_wrong_account_cannot_retry_and_history_survives_explicit_retry(self):
  self.s['status']='needs_attention';self.s['items'][0].update(status='needs_revision',image='old',qc={'pass':False});colours.save(self.s)
  with self.assertRaises(ValueError):colours.retry({'id':'set1','slot':0,'confirmed':True},{'id':'other'})
  result=colours.retry({'id':'set1','slot':0,'confirmed':True},{'id':'own'})
  self.assertEqual(result['items'][0]['history'][0]['image'],'old');self.assertNotIn('image',result['items'][0]);self.assertEqual(result['items'][0]['status'],'queued')
 def test_repair_uses_original_master_and_specific_prior_defect(self):
  self.s['items']=self.s['items'][:1]
  self.s['items'][0]['history']=[{'image':'rejected-output','qc':{'issues':['denim texture changed']}}]
  with patch.object(colours.studio_bridge,'result_image',return_value=(b'\x89PNG\r\n\x1a\nphoto','image/png')),patch.object(image_provider,'submit',return_value={'id':'new-job'}) as submit,patch.object(image_provider,'poll',return_value={'status':'generating'}):
   colours.work(self.s)
  payload=submit.call_args.args[0]
  self.assertIn('denim texture changed',payload['prompt']);self.assertIn('ORIGINAL locked master',payload['prompt'])
  self.assertNotIn('rejected-output',payload['references']);self.assertEqual(self.s['items'][0]['jobId'],'new-job')
 def test_colour_and_hardware_text_rule_is_shared_by_generation_and_review(self):
  self.s['items']=self.s['items'][:1]
  with patch.object(colours.studio_bridge,'result_image',return_value=(b'\x89PNG\r\n\x1a\nphoto','image/png')),patch.object(image_provider,'submit',return_value={'id':'job'}) as submit,patch.object(image_provider,'poll',return_value={'status':'completed','images':['https://example/result.png']}),patch.object(visual,'model_json',return_value={'pass':False,'issues':['buttons mismatch']}) as review:
   colours.work(self.s)
  for prompt in (submit.call_args.args[0]['prompt'],review.call_args.args[0]):
   self.assertIn(colours.TEXT_RULE,prompt)
   self.assertIn('Do not replace a hardware adjective with the garment colour name',prompt)
  self.assertEqual(colours.get('set1')['items'][0]['status'],'needs_revision')
 def test_local_repair_retains_failure_and_requires_fresh_qc(self):
  self.s['status']='needs_attention';self.s['items']=self.s['items'][:1]
  self.s['items'][0].update(status='needs_revision',image='old',sourceUpload='/uploads/base.png',qc={'pass':False,'issues':['skin recoloured']});colours.save(self.s)
  out=io.BytesIO();Image.new('RGB',(1600,1600),'yellow').save(out,'PNG');raw=out.getvalue()
  data={'id':'set1','slot':0,'previousImage':'old','image':'/uploads/fixed.png','note':'Restored original skin pixels','confirmed':True}
  with patch.object(image_provider,'local_image',return_value=raw),patch.object(image_provider,'submit') as submit:
   result=colours.repair_local(data,{'id':'own'})
  submit.assert_not_called();self.assertEqual(result['items'][0]['status'],'reviewing');self.assertNotIn('qc',result['items'][0]);self.assertEqual(result['items'][0]['history'][0]['qc']['pass'],False)
  self.assertFalse(result['items'][0]['localCorrection']['humanReviewed'])
  with self.assertRaises(ValueError):colours.repair_local(data,{'id':'own'})
 def test_local_batch_commits_once_and_keeps_both_slot_histories_without_image_submit(self):
  self.s['status']='needs_attention'
  for i in self.s['items']:i.update(status='needs_revision',image='old'+str(i['slot']),sourceUpload='/uploads/base.png',qc={'pass':False})
  colours.save(self.s);out=io.BytesIO();Image.new('RGB',(1600,1600),'pink').save(out,'PNG')
  changes=[{'slot':i,'previousImage':'old'+str(i),'image':'/uploads/new'+str(i)+'.png','note':'Source mask correction'} for i in range(2)]
  with patch.object(image_provider,'local_image',return_value=out.getvalue()),patch.object(image_provider,'submit') as submit,patch.object(colours,'save',wraps=colours.save) as save:
   result=colours.repair_local_batch({'id':'set1','confirmed':True,'changes':changes},{'id':'own'})
  self.assertEqual(save.call_count,1);submit.assert_not_called();self.assertEqual(result['status'],'reviewing')
  for index,item in enumerate(result['items']):
   self.assertEqual(item['status'],'reviewing');self.assertEqual(item['history'][0]['image'],'old'+str(index));self.assertFalse(item['localCorrection']['humanReviewed'])
  self.assertFalse(result['localRepairBatches'][0]['imageSubmissionAllowed'])

 def test_invalid_batch_slot_cannot_partially_commit_prior_valid_slot(self):
  self.s['status']='needs_attention'
  for i in self.s['items']:i.update(status='needs_revision',image='old'+str(i['slot']),sourceUpload='/uploads/base.png')
  colours.save(self.s);out=io.BytesIO();Image.new('RGB',(1600,1600),'pink').save(out,'PNG')
  changes=[{'slot':i,'previousImage':'old'+str(i),'image':'/uploads/new.png','note':'Correction'} for i in range(2)];changes[1]['previousImage']='stale'
  with patch.object(image_provider,'local_image',return_value=out.getvalue()),patch.object(colours,'save',wraps=colours.save) as save:
   with self.assertRaises(ValueError):colours.repair_local_batch({'id':'set1','confirmed':True,'changes':changes},{'id':'own'})
   save.assert_not_called()
  self.assertEqual(colours.get('set1'),self.s)

 def test_review_timeout_can_resume_existing_image_without_image_generation(self):
  raw=b'unchanged-local-candidate';import hashlib
  self.s['status']='needs_attention';self.s['items']=self.s['items'][:1]
  self.s['items'][0].update(status='reviewing',image='/uploads/candidate.png',sourceUpload='/uploads/base.png',localCorrection={'sha256':hashlib.sha256(raw).hexdigest()});colours.save(self.s)
  with patch.object(image_provider,'local_image',return_value=raw),patch.object(image_provider,'submit') as submit:
   resumed=colours.resume_local_review({'id':'set1','confirmed':True},{'id':'own'})
   with patch.object(visual,'model_json',return_value={'pass':True,'issues':[],'observedColor':'red'}):colours.work(resumed)
  submit.assert_not_called();self.assertEqual(colours.get('set1')['status'],'awaiting_manual')
  self.assertFalse(resumed['reviewResumes'][-1]['imageSubmissionAllowed'])

 def test_review_resume_rejects_other_product_changed_image_and_generation(self):
  self.s['status']='needs_attention';self.s['items']=self.s['items'][:1]
  self.s['items'][0].update(status='reviewing',image='/uploads/candidate.png',localCorrection={'sha256':'different'});colours.save(self.s)
  with self.assertRaises(ValueError):colours.resume_local_review({'id':'set1','confirmed':True},{'id':'other'})
  with patch.object(image_provider,'local_image',return_value=b'changed'):
   with self.assertRaises(ValueError):colours.resume_local_review({'id':'set1','confirmed':True},{'id':'own'})
  self.s['items'][0]['status']='generating';colours.save(self.s)
  with self.assertRaises(ValueError):colours.resume_local_review({'id':'set1','confirmed':True},{'id':'own'})
 def test_local_batch_reviews_all_existing_images_even_when_first_fails(self):
  for i in self.s['items']:i.update(status='reviewing',image='/uploads/result.png',sourceUpload='/uploads/base.png',localCorrection={'method':'uploaded_local_correction'})
  with patch.object(colours,'review_inputs',return_value=(['source','target','result'],{})),patch.object(visual,'model_json',side_effect=[{'pass':False,'issues':['remaining red']},{'pass':True,'issues':[]}]) as review,patch.object(image_provider,'submit') as submit:
   colours.work(self.s)
  self.assertEqual(review.call_count,2);submit.assert_not_called()
  saved=colours.get('set1');self.assertEqual([i['status'] for i in saved['items']],['needs_revision','awaiting_manual'])

 def test_batch_stays_busy_until_remaining_local_reviews_finish(self):
  for i in self.s['items']:i.update(status='reviewing',image='/uploads/result.png',sourceUpload='/uploads/base.png',localCorrection={'method':'uploaded_local_correction'})
  count=0
  def review(*args):
   nonlocal count
   count+=1
   if count==2:
    self.assertEqual(colours.get('set1')['status'],'reviewing')
    with self.assertRaises(ValueError):colours.repair_local_batch({'id':'set1','confirmed':True,'changes':[{'slot':0,'previousImage':'/uploads/result.png','image':'/uploads/replacement.png','note':'Must not race active QA'}]},{'id':'own'})
   return {'pass':False,'issues':['real visible defect']}
  with patch.object(colours,'review_inputs',return_value=(['source','target','result'],{})),patch.object(visual,'model_json',side_effect=review):colours.work(self.s)
  self.assertEqual(count,2);self.assertEqual(colours.get('set1')['status'],'needs_attention')

 def test_inflight_lease_blocks_repair_even_if_persisted_status_is_stale(self):
  self.s['status']='needs_attention';colours.save(self.s)
  with patch.object(colours,'IN_FLIGHT',{'set1'}),patch.object(colours,'save') as save:
   with self.assertRaises(ValueError):colours.repair_local_batch({'id':'set1','confirmed':True,'changes':[{'slot':0,'previousImage':'old','image':'/uploads/new.png','note':'Must wait for current worker'}]},{'id':'own'})
   save.assert_not_called()

 def test_enlarged_comparisons_come_from_actual_source_and_current_pixels(self):
  def png(colour):
   out=io.BytesIO();Image.new('RGB',(100,100),colour).save(out,'PNG');return out.getvalue()
  item={'slot':2,'sourceUpload':'/uploads/base.png','image':'/uploads/current.png','localCorrection':{'method':'uploaded_local_correction'}}
  with patch.object(image_provider,'local_image',side_effect=[png('red'),png('blue')]):refs,evidence=colours.review_inputs(self.s,item)
  self.assertEqual(len(refs),4);self.assertEqual(len(evidence['enlargedComparisons']),1)
  self.assertEqual(evidence['changedBounds'],(0,0,100,100));self.assertTrue(refs[-1].startswith('data:image/jpeg;base64,'))
  self.assertEqual(evidence['comparisonMode'],'local_context')

 def test_explicit_review_covers_both_sides_and_lower_boundaries_without_slot_coordinates(self):
  import base64,copy,hashlib
  from PIL import ImageDraw
  source=Image.new('RGB',(320,320),'#dddddd');ImageDraw.Draw(source).rectangle((90,90,230,280),fill='red')
  result=source.copy();ImageDraw.Draw(result).rectangle((90,90,230,280),fill='blue')
  def png(image):
   raw=io.BytesIO();image.save(raw,'PNG');return raw.getvalue()
  original,current=png(source),png(result);sha=hashlib.sha256(current).hexdigest()
  s=copy.deepcopy(self.s);s['reviewResumes']=[{'slots':[0,6],'reference':s['reference'],'imageHashes':[sha],'comparisonVersion':1}]
  item={'slot':6,'sourceUpload':'/uploads/base.png','image':'/uploads/current.png','localCorrection':{'sha256':sha},
        'qc':{'pass':False,'issues':['unresolved left shoulder']},'reviewHistory':[{'qc':{'pass':False,'issues':['old review']}}]}
  before_s=copy.deepcopy(s);before_item=copy.deepcopy(item)
  with patch.object(image_provider,'local_image',side_effect=[original,current]):refs,evidence=colours.review_inputs(s,item)
  self.assertEqual(s,before_s);self.assertEqual(item,before_item)
  self.assertEqual(refs[:3],['data:image/png;base64,AA==']*3)
  self.assertEqual(len(refs),5);self.assertEqual(len(evidence['enlargedComparisons']),4)
  self.assertEqual(evidence['comparisonMode'],'explicit_local_rereview')
  self.assertEqual(evidence['changedBounds'],(90,90,231,281))
  self.assertEqual(evidence['comparisonBounds'],(58,58,263,313))
  rectangles=[entry['sourceRectangle'] for entry in evidence['enlargedComparisons']]
  for x,y in [(65,75),(255,75),(65,305),(255,305)]:
   self.assertTrue(any(left<=x<right and top<=y<bottom for left,top,right,bottom in rectangles),(x,y))
  self.assertEqual({entry['imageNumber'] for entry in evidence['enlargedComparisons']},{4,5})
  # The upper-left crop contains the actual original red / current blue pixels.
  entry=evidence['enlargedComparisons'][0];left,top,right,bottom=entry['sourceRectangle']
  with Image.open(io.BytesIO(base64.b64decode(refs[3].split(',',1)[1]))) as comparison:
   x,y=110-left,110-top+24;column_width=right-left
   a=comparison.getpixel((x,y));b=comparison.getpixel((column_width+x,y))
   self.assertGreater(a[0],220);self.assertLess(a[2],30)
   self.assertGreater(b[2],220);self.assertLess(b[0],30)
  item['slot']=0
  with patch.object(image_provider,'local_image',side_effect=[original,current]):_,other=colours.review_inputs(s,item)
  self.assertEqual(rectangles,[entry['sourceRectangle'] for entry in other['enlargedComparisons']])

 def test_explicit_comparison_requires_current_file_and_reference_not_an_old_resume(self):
  import hashlib
  raw=io.BytesIO();Image.new('RGB',(80,100),'white').save(raw,'PNG');pixels=raw.getvalue()
  sha=hashlib.sha256(pixels).hexdigest()
  item={'slot':6,'sourceUpload':'/uploads/base.png','image':'/uploads/current.png','localCorrection':{'sha256':sha}}
  for resume in [{'slots':[6],'reference':'old-reference','imageHashes':[sha]},
                 {'slots':[6],'reference':self.s['reference'],'imageHashes':['old-hash']},
                 {'slots':[5],'reference':self.s['reference'],'imageHashes':[sha]}]:
   self.s['reviewResumes']=[resume]
   with patch.object(image_provider,'local_image',return_value=pixels):refs,evidence=colours.review_inputs(self.s,item)
   self.assertEqual(len(refs),4);self.assertEqual(evidence['comparisonMode'],'local_context')
   self.assertIsNone(evidence['changedBounds']);self.assertEqual(evidence['comparisonBounds'],(0,0,80,100))

 def test_unavailable_comparison_does_not_discard_originals_or_mark_qc_pass(self):
  item={'slot':6,'sourceUpload':'/uploads/base.png','image':'/uploads/current.png','localCorrection':{'method':'local'},'qc':{'pass':False,'issues':['real defect']}}
  with patch.object(image_provider,'local_image',return_value=b'invalid-image'):refs,evidence=colours.review_inputs(self.s,item)
  self.assertEqual(len(refs),3);self.assertTrue(evidence['comparisonUnavailable'])
  self.assertFalse(item['qc']['pass']);self.assertEqual(item['qc']['issues'],['real defect'])
 def test_review_reference_change_requires_same_colour_catalogue_and_keeps_prior_evidence(self):
  import hashlib
  raw=b'current-image';self.s.update(status='needs_attention',colorKey='gray',color='Gray')
  self.s['items']=self.s['items'][:1];self.s['items'][0].update(status='needs_revision',image='/uploads/current.png',qc={'pass':False,'issues':['colour uncertainty']},localCorrection={'sha256':hashlib.sha256(raw).hexdigest()});colours.save(self.s)
  data={'id':'set1','slots':[0],'confirmed':True,'reference':'asin-main','referenceReason':'Existing user rule: ASIN white-background main when supplier has no white-background image'}
  ref={'url':'asin-main','referenceType':'amazon_variant_main','sourceAsin':'B000000001','sourceUrl':'https://www.amazon.com/dp/B000000001'}
  with patch.object(colours,'select_variant',side_effect=ValueError('wrong colour')):
   with self.assertRaises(ValueError):colours.resume_local_review(data,{'id':'own'})
  with patch.object(colours,'select_variant',return_value={'references':[ref]}) as select,patch.object(image_provider,'local_image',return_value=raw),patch.object(image_provider,'submit') as submit:
   result=colours.resume_local_review(data,{'id':'own'})
  select.assert_called_once_with({'id':'own'},'gray','asin-main');submit.assert_not_called()
  self.assertEqual(result['referenceHistory'][-1]['reference'],'target');self.assertEqual(result['reference'],'asin-main');self.assertFalse(result['validated'])
  self.assertEqual(result['items'][0]['qcReference'],'target')
 def test_supplier_reference_amendment_clears_stale_amazon_attribution_only(self):
  import hashlib
  raw=b'current-image';self.s.update(status='needs_attention',colorKey='gray',color='Gray',referenceEvidenceType='amazon_variant_main',referenceSourceAsin='B000000001',referenceSourceUrl='https://www.amazon.com/dp/B000000001')
  self.s['items']=self.s['items'][:1];self.s['items'][0].update(status='needs_revision',image='/uploads/current.png',qc={'pass':False,'issues':['colour uncertainty']},localCorrection={'sha256':hashlib.sha256(raw).hexdigest()});colours.save(self.s)
  data={'id':'set1','slots':[0],'confirmed':True,'reference':'verified-supplier','referenceReason':'Recorded sourcing decision uses the actual supplier dark gray.','referenceOnly':True}
  with patch.object(colours,'select_variant',return_value={'references':[{'url':'verified-supplier','referenceType':'supplier_product_image'}]}),patch.object(image_provider,'local_image',return_value=raw),patch.object(image_provider,'submit') as submit:
   result=colours.resume_local_review(data,{'id':'own'})
  submit.assert_not_called();self.assertEqual(result['referenceEvidenceType'],'supplier_product_image');self.assertNotIn('referenceSourceAsin',result);self.assertNotIn('referenceSourceUrl',result)
  self.assertEqual(result['referenceHistory'][-1]['evidence']['referenceSourceAsin'],'B000000001');self.assertEqual(result['items'][0]['image'],'/uploads/current.png');self.assertEqual(result['items'][0]['status'],'needs_revision')
 def test_local_repair_rejects_wrong_product_stale_or_unknown_submission(self):
  self.s['status']='needs_attention';self.s['items'][0].update(status='needs_revision',image='old');colours.save(self.s)
  data={'id':'set1','slot':0,'previousImage':'stale','image':'/uploads/fixed.png','note':'Fix','confirmed':True}
  with self.assertRaises(ValueError):colours.repair_local(data,{'id':'other'})
  with self.assertRaises(ValueError):colours.repair_local(data,{'id':'own'})
 def test_unapproved_candidate_can_be_corrected_without_granting_human_review(self):
  self.s['status']='awaiting_manual';self.s['items']=self.s['items'][:1]
  self.s['items'][0].update(status='awaiting_manual',image='old',sourceUpload='/uploads/base.png',qc={'pass':True,'issues':[]});colours.save(self.s)
  out=io.BytesIO();Image.new('RGB',(20,20)).save(out,'PNG')
  with patch.object(image_provider,'local_image',return_value=out.getvalue()):
   result=colours.repair_local({'id':'set1','slot':0,'previousImage':'old','image':'/uploads/fixed.png','note':'Visual inspection found recoloured fingernails','confirmed':True},{'id':'own'})
  self.assertEqual(result['items'][0]['status'],'reviewing');self.assertFalse(result['items'][0]['localCorrection']['humanReviewed'])
  self.assertTrue(result['items'][0]['history'][-1]['qc']['pass'])

 def test_refused_request_requires_exact_receipt_for_local_only_candidate(self):
  self.s['status']='needs_attention';self.s['items']=self.s['items'][:1]
  self.s['items'][0].update(status='submit_unknown',error='receipt refusal-1',sourceUpload='/uploads/base.png');colours.save(self.s)
  attempt={'id':'submission-1','productId':'own','slot':'换色 Red 1','status':'submission_unknown','proxyDiagnostic':{'id':'refusal-1','provider':'Codex Tools','httpStatus':400,'path':'/v1/images/edits','message':'Your request was rejected by the safety system.'}}
  data={'id':'set1','slot':0,'previousImage':None,'image':'/uploads/fixed.png','note':'Deterministic correction from accepted master; no provider replay','confirmed':True}
  out=io.BytesIO();Image.new('RGB',(20,20)).save(out,'PNG')
  with patch.object(image_provider,'jobs',return_value={'jobs':[attempt]}),patch.object(image_provider,'local_image',return_value=out.getvalue()),patch.object(image_provider,'submit') as submit:
   with self.assertRaises(ValueError):colours.repair_local(data,{'id':'own'})
   result=colours.repair_local({**data,'refusalDiagnosticId':'refusal-1'},{'id':'own'})
  submit.assert_not_called();self.assertEqual(attempt['status'],'submission_unknown')
  self.assertEqual(result['items'][0]['history'][-1]['status'],'submit_unknown')
  self.assertEqual(result['items'][0]['localCorrection']['recordedRefusal']['submissionId'],'submission-1')
  self.assertFalse(result['items'][0]['localCorrection']['providerRequestReplayed'])
  self.s['items'][0]['status']='submit_unknown';colours.save(self.s);data['previousImage']='old'
  with self.assertRaises(ValueError):colours.repair_local(data,{'id':'own'})
 def test_continue_other_slots_does_not_approve_or_retry_rejected_image(self):
  self.s['status']='needs_attention';self.s['items'][0].update(status='needs_revision',image='rejected',qc={'pass':False,'issues':['defect']});colours.save(self.s)
  result=colours.continue_remaining({'id':'set1','confirmed':True},{'id':'own'})
  self.assertEqual(result['status'],'queued');self.assertEqual(result['items'][0]['status'],'needs_revision');self.assertFalse(result['items'][0]['qc']['pass'])
  self.assertFalse(result['continuations'][0]['reviewGranted'])
  with patch.object(colours.studio_bridge,'result_image',return_value=(b'\x89PNG\r\n\x1a\nphoto','image/png')),patch.object(image_provider,'submit',return_value={'id':'new-job'}) as submit,patch.object(image_provider,'poll',return_value={'status':'generating'}):colours.work(result)
  submit.assert_called_once();self.assertEqual(result['items'][0]['image'],'rejected');self.assertEqual(result['items'][1]['jobId'],'new-job')
 def test_explicit_refusal_can_leave_other_slots_running_without_replaying_refusal(self):
  self.s['status']='needs_attention';self.s['items'][0].update(status='submit_unknown',error='error receipt refusal-1');colours.save(self.s)
  attempt={'id':'submission-1','productId':'own','slot':'换色 Red 1','status':'submission_unknown',
           'proxyDiagnostic':{'id':'refusal-1','provider':'Codex Tools','httpStatus':400,
                              'path':'/v1/images/edits','message':'Your request was rejected by the safety system.'}}
  with patch.object(image_provider,'jobs',return_value={'jobs':[attempt]}):
   result=colours.continue_remaining({'id':'set1','confirmed':True},{'id':'own'})
  self.assertEqual(result['items'][0]['status'],'submit_unknown')
  self.assertEqual(result['continuations'][-1]['recordedRefusals'][0]['submissionId'],'submission-1')
  with patch.object(colours.studio_bridge,'result_image',return_value=(b'photo','image/png')),patch.object(image_provider,'submit',return_value={'id':'only-independent-slot'}) as submit,patch.object(image_provider,'poll',return_value={'status':'generating'}):colours.work(result)
  submit.assert_called_once()
  self.assertEqual(submit.call_args.args[0]['slot'],'换色 Red 2')
  self.assertEqual(result['items'][0]['status'],'submit_unknown')
  self.s.update(status='needs_attention');colours.save(self.s)
  for changes in ({'externalId':'maybe-started'},{'productId':'other'}, {'proxyDiagnostic':{**attempt['proxyDiagnostic'],'httpStatus':500}}):
   with patch.object(image_provider,'jobs',return_value={'jobs':[{**attempt,**changes}]}):
    with self.assertRaises(ValueError):colours.continue_remaining({'id':'set1','confirmed':True},{'id':'own'})
 def test_same_product_gate_prevents_paid_generation(self):
  self.s.pop('validated')
  with patch.object(visual,'model_json',side_effect=[{'sameProduct':False,'issues':['different cut'],'targetColor':'red'},{'sameConstruction':False,'differences':['different cut']}]),patch.object(image_provider,'submit') as submit:
   colours.work(self.s)
  self.assertEqual(colours.get('set1')['status'],'needs_attention');submit.assert_not_called()
 def test_material_concern_retained_for_colour_only_draft(self):
  self.s.pop('validated');self.s['items']=[]
  with patch.object(visual,'model_json',side_effect=[{'sameProduct':False,'issues':['fabric finish uncertain'],'targetColor':'red'},{'sameConstruction':True,'differences':[],'materialConcern':'finish uncertain'}]):
   colours.work(self.s)
  result=colours.get('set1');self.assertTrue(result['colorOnlyDraft']);self.assertEqual(result['referenceWarnings'],['fabric finish uncertain']);self.assertFalse(result.get('manual',False));self.assertEqual(result['status'],'awaiting_manual')
 def test_revalidate_retains_history_and_completed_output(self):
  self.s.pop('validated');self.s.update(status='needs_attention',referenceCheck={'sameProduct':False});self.s['items'][0].update(status='awaiting_manual',image='existing');colours.save(self.s)
  result=colours.retry({'id':'set1','confirmed':True,'revalidate':True},{'id':'own'})
  self.assertEqual(result['items'][0]['image'],'existing');self.assertEqual(len(result['referenceHistory']),1)
 def test_cache_slot_does_not_block_complete_master(self):
  runs=[{'id':'cache','projectId':'master','slot':99,'status':'colour_cache','image':'cached'}]+[{'id':'run'+str(i),'projectId':'master','slot':i,'status':'awaiting_manual','image':'image'} for i in range(2)]
  with patch.object(colours.studio_bridge,'latest_project',return_value=self.master),patch.object(visual,'list_projects',return_value={'runs':runs}):
   result=colours.start({'confirmed':True,'color':'Red','reference':'target'},{'id':'own'})
  self.assertEqual([i['slot'] for i in result['items']],[0,1])
 def test_batch_reuses_existing_set_without_duplicate_generation(self):
  runs=[{'id':'run'+str(i),'projectId':'master','slot':i,'status':'awaiting_manual','image':'image'} for i in range(2)]
  self.s.update(color='Red',reference='target',status='generating');colours.save(self.s)
  with patch.object(colours.studio_bridge,'latest_project',return_value=self.master),patch.object(visual,'list_projects',return_value={'runs':runs}):
   result=colours.start({'confirmed':True,'color':'Red','reference':'target'},{'id':'own'},_batch=True)
  self.assertEqual(result['id'],'set1');self.assertEqual(len(colours.list_sets('own')['sets']),1)
 def test_master_requires_complete_quality_passed_set(self):
  with patch.object(colours.studio_bridge,'latest_project',return_value=self.master),patch.object(visual,'list_projects',return_value={'runs':[]}):
   with self.assertRaisesRegex(ValueError,'母版'):colours.start({'confirmed':True,'color':'Red','reference':'target'},{'id':'own'})

if __name__=='__main__':unittest.main()

