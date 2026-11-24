import base64,copy,hashlib,json,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import local_colour_tasks as local
import pixel_recolour as pixel
import colour_sets as colours


class LocalColourTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'uploads').mkdir()
  self.product={'id':'own','masterColor':'Red'}
  self.groups={k:{'key':k,'color':k.title(),'ready':True,'issues':[],'children':[{'sku':k+'-S'}],
                'references':[{'url':'https://example.test/'+k+'.jpg','aliases':[k],'referenceType':'amazon_variant_main','sourceAsin':'TEST-'+k}]} for k in ['red','beige','black']}
  self.context={'id':'plan','storyboardProjectId':'plan','reference':self.groups['red']['references'][0]['url'],'count':2,'items':[]}
  self.patches=[patch.object(local,'DB',self.root/'recipes.sqlite3'),patch.object(pixel,'ROOT',self.root),patch.object(pixel.image_provider,'ROOT',self.root),
   patch.object(colours,'DB',self.root/'sets.sqlite3'),patch.object(local.local_colour_sources,'context',return_value=self.context),
   patch.object(colours.studio_bridge,'latest_project',return_value={'id':'plan'}),patch.object(local.variant_colours,'catalog',return_value=self.groups),
   patch.object(local,'start_worker'),patch.object(pixel.image_provider,'submit',side_effect=AssertionError('Paid image submission is forbidden'))]
  for p in self.patches:p.start()
  for slot in range(2):
   rgb=np.full((40,40,3),[120,30+slot*4,45],dtype='uint8');rgb[:,:8]=[230,228,225]
   url=pixel.asset(pixel.png(Image.fromarray(rgb)))
   self.context['items'].append({'slot':slot,'sourceUpload':url,'sourceSha256':hashlib.sha256(pixel.image_provider.local_image(url)).hexdigest(),'baseRun':'r'+str(slot)})
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def request(self,key='beige'):
  return {'colorKey':key,'reference':self.groups[key]['references'][0]['url'],'confirmed':True}
 def configure(self,key='beige'):
  return local.configure({**self.request(key),'target':'#e0d9ce','exposure':-3,'texture':.7},self.product)
 def test_agent_patch_recipe_binds_verified_photo_hash_and_asin_without_human_approval(self):
  evidence={'reference':self.request()['reference'],'box':[.3,.4,.4,.6],'target':'#e0d9ce','sourceSha256':'a'*64}
  with patch('colour_reference.sample',return_value=evidence):
   recipe=local.configure({**self.request(),'target':evidence['target'],'referenceSample':evidence,'reviewerType':'agent'},self.product)
  self.assertEqual(recipe['source'],'agent_verified_reference_patch');self.assertEqual(recipe['sourceSha256'],'a'*64)
  self.assertEqual(recipe['referenceSourceAsin'],'TEST-beige');self.assertFalse(recipe['humanReviewed'])
 def test_agent_patch_rejects_changed_photo_or_arbitrary_rgb(self):
  evidence={'reference':self.request()['reference'],'box':[.3,.4,.4,.6],'target':'#e0d9ce','sourceSha256':'a'*64}
  for change in [{'sourceSha256':'b'*64},{'target':'#000000'},{'reference':'https://example.test/other.jpg'}]:
   with patch('colour_reference.sample',return_value=evidence),self.assertRaises(ValueError):
    local.configure({**self.request(),'target':evidence['target'],'referenceSample':{**evidence,**change},'reviewerType':'agent'},self.product)
 def selection(self,slot,revision=0):
  source=pixel.source_row(self.context['items'][slot]);a=np.zeros((40,40),dtype='uint8');a[:,8:]=255
  encode=lambda arr:base64.b64encode(pixel.png(Image.fromarray(arr))).decode()
  import garment_auto
  return pixel.save_selection({**source,'revision':revision,'alpha':encode(a),'protected':encode(255-a)},self.product,automatic_provenance={'automatic':True,'version':garment_auto.VERSION})
 def ready(self):
  self.configure();self.selection(0);self.selection(1)
 def previous(self,statuses):
  s={'id':'previous','productId':'own','masterId':'plan','storyboardProjectId':'plan','masterColor':'Red','color':'Beige','colorKey':'beige',
     'reference':self.request()['reference'],'model':'gpt-image-2','status':'needs_attention','validated':True,'manual':False,
     'items':[{**self.context['items'][n],'status':status,'image':self.context['items'][n]['sourceUpload'],
               'qc':{'pass':status in ('approved','awaiting_manual'),'issues':[] if status in ('approved','awaiting_manual') else ['small edge']}} for n,status in enumerate(statuses)]}
  return colours.save(s)
 def test_first_local_product_uses_originals_without_needing_an_api_colour_job(self):
  rows=pixel.sources(self.product)['sources'];self.assertEqual([r['slot'] for r in rows],[0,1])
  self.assertEqual(colours.list_sets('own')['sets'],[])
 def test_fine_tuning_survives_configuration_and_reaches_every_frame(self):
  self.ready()
  recipe=local.configure({**self.request(),'target':'#b46a73','contrast':12,'shadows':8,'highlights':-5,'saturation':.8,'colorDetail':.2},self.product)
  s=local.start(self.request(),self.product)['sets'][0]
  local.work(s,self.product)
  for item in colours.get(s['id'])['items']:
   actual=item['localCorrection']['pixelRecipe']['recipe']
   for name in ('contrast','shadows','highlights','saturation','colorDetail'):self.assertEqual(actual[name],recipe[name])
  self.assertEqual(recipe['reference'],self.request()['reference'])
 def test_sampler_checks_variant_reference_before_reading_any_image(self):
  from colour_reference import sample
  with patch('colour_reference.sample',wraps=sample) as read:
   with self.assertRaises(ValueError):local.sample_reference({**self.request(),'reference':'https://elsewhere.test/a.jpg','box':[0,0,1,1]},self.product)
   read.assert_not_called()
 def test_missing_masks_and_colour_parameters_never_create_any_task(self):
  self.groups['beige']['references'][0]['referenceType']='supplier_product_image'
  with self.assertRaises(local.NotReady) as raised:local.start(self.request(),self.product)
  self.assertEqual(raised.exception.details['colors'][0]['missingSlots'],[0,1]);self.assertEqual(colours.list_sets('own')['sets'],[])
 def test_start_all_preflight_is_atomic(self):
  self.ready()
  self.groups['black']['ready']=False;self.groups['black']['issues']=['缺少供货核实']
  with self.assertRaises(local.NotReady):local.start({'confirmed':True},self.product,all_colors=True)
  self.assertEqual(colours.list_sets('own')['sets'],[])
 def test_automatic_batch_uses_each_variant_main_without_manual_configuration(self):
  import garment_auto
  ready=local.readiness({},self.product);self.assertTrue(ready['colors'][0]['automaticPreparationRequired']);self.assertEqual(ready['colors'][0]['issues'],[])
  def reference(product,group,url,cache):
   return {'target':'#337755' if group['key']=='beige' else '#224466','reference':url,'referenceSourceAsin':group['references'][0]['sourceAsin'],'source':'automatic_variant_main','sourceSha256':'fixture-'+group['key'],'automaticReferenceVersion':'fixture'}
  mask=np.zeros((40,40),'uint8');mask[:,8:]=255
  with patch.object(local.automatic_reference,'identify',side_effect=reference) as sample,patch.object(garment_auto,'identify',return_value=(Image.fromarray(mask),{'automatic':True,'version':garment_auto.VERSION})) as segment:
   result=local.start({'confirmed':True},self.product,all_colors=True)
  self.assertEqual(result['createdColors'],2);self.assertEqual(sample.call_count,2);self.assertEqual(segment.call_count,2)
  for s in result['sets']:
   self.assertEqual(s['localTask']['recipe']['target'],'#337755' if s['colorKey']=='beige' else '#224466')
   self.assertEqual(s['reference'],self.groups[s['colorKey']]['references'][0]['url'])
  self.assertFalse(result['imageGenerationSubmitted'])
 def test_one_click_prepares_missing_masks_without_human_points(self):
  self.configure()
  import garment_auto
  mask=Image.new('L',(40,40),255)
  with patch.object(garment_auto,'identify',return_value=(mask,{'automatic':True,'userPointsRequired':False,'humanReviewed':False})) as infer:
   result=local.start(self.request(),self.product)
  self.assertEqual(infer.call_count,2);self.assertEqual(result['createdColors'],1)
  for row in pixel.sources(self.product)['sources']:
   selection=pixel.selection(row,self.product)['selection'];self.assertEqual(selection['revision'],1);self.assertTrue(selection['edits'][-1]['automatic'])
 def test_parser_upgrade_resamples_failed_colour_and_preserves_recipe_history(self):
  old=self.configure();old.update(manualTuning=False,source='automatic_variant_main',automaticReferenceVersion=local.automatic_reference.VERSION,selectionVersion='retired-parser')
  group=self.groups['beige'];local.store_recipe(old,self.product,self.context,group,self.request()['reference'])
  self.selection(0);self.selection(1)
  ready=local.readiness({'colorKey':'beige'},self.product)
  self.assertTrue(ready['colors'][0]['automaticPreparationRequired'])
  sampled={'target':'#445566','reference':self.request()['reference'],'source':'automatic_variant_main','sourceSha256':'new-source',
   'automaticReferenceVersion':local.automatic_reference.VERSION,'selectionVersion':local.automatic_reference.garment_auto.VERSION}
  with patch.object(local.automatic_reference,'identify',return_value=sampled) as sample:
   recipe=local._automatic_recipe(self.product,self.context,group,self.request()['reference'])
  sample.assert_called_once();self.assertEqual(recipe['target'],'#445566')
  with closing(local.connect()) as db:
   history=[json.loads(r[0]) for r in db.execute('SELECT body FROM recipe_history')]
  self.assertTrue(any(r.get('selectionVersion')=='retired-parser' for r in history))
 def test_parser_upgrade_preserves_explicit_manual_tuning(self):
  original=self.configure();original.update(selectionVersion='retired-parser')
  local.store_recipe(original,self.product,self.context,self.groups['beige'],self.request()['reference'])
  with patch.object(local.automatic_reference,'identify',side_effect=AssertionError('manual tuning cannot be replaced')):
   recipe=local._automatic_recipe(self.product,self.context,self.groups['beige'],self.request()['reference'])
  self.assertEqual(recipe['target'],original['target']);self.assertTrue(recipe['manualTuning'])
 def test_other_failed_preflight_never_runs_automatic_selection(self):
  self.configure();self.groups['beige']['ready']=False;self.groups['beige']['issues']=['供货待核实']
  with patch.object(pixel,'ensure_automatic_selections') as infer,self.assertRaises(local.NotReady):local.start(self.request(),self.product)
  infer.assert_not_called();self.assertEqual(colours.list_sets('own')['sets'],[])
 def test_real_local_render_enters_native_qa_without_any_image_submit(self):
  self.ready();result=local.start(self.request(),self.product);s=result['sets'][0]
  self.assertFalse(result['imageGenerationSubmitted']);self.assertEqual(s['model'],'local-pixel')
  self.assertNotIn(s['status'],colours.ACTIVE)
  local.work(s,self.product);saved=colours.get(s['id'])
  self.assertEqual(saved['status'],'reviewing');self.assertTrue(all(i['status']=='reviewing' for i in saved['items']))
  for i in saved['items']:
   out=np.asarray(pixel.image(i['image']));original=np.asarray(pixel.image(i['sourceUpload']))
   np.testing.assert_array_equal(out[:,:8],original[:,:8]);self.assertFalse(i['localCorrection']['humanReviewed'])
  saved['validated']=True
  with patch.object(colours,'composition_review',return_value={'pass':True,'issues':[]}),patch.object(colours,'review_inputs',return_value=([],{})),patch.object(colours.visual,'model_json',return_value={'decision':'warn','blockingIssues':[],'warnings':['tiny edge']}):colours.work(saved)
  self.assertEqual(colours.get(s['id'])['status'],'awaiting_manual')
 def test_passed_slots_keep_exact_image_and_only_failed_slot_requires_a_mask(self):
  self.configure();self.selection(1);old=self.previous(['awaiting_manual','needs_revision']);kept=copy.deepcopy(old['items'][0])
  s=local.start(self.request(),self.product)['sets'][0]
  self.assertEqual(s['localTask']['pendingSlots'],[1])
  with patch.object(pixel,'render',wraps=pixel.render) as render:local.work(s,self.product)
  self.assertEqual(render.call_count,1);self.assertEqual(colours.get(s['id'])['items'][0],kept)
 def test_complete_sets_are_skipped_even_without_masks_or_calibration(self):
  before=self.previous(['awaiting_manual','awaiting_manual'])
  result=local.start(self.request(),self.product)
  self.assertEqual(result['createdColors'],0);self.assertEqual(colours.get(before['id']),before)
 def test_double_click_does_not_create_duplicate_task(self):
  self.ready();one=local.start(self.request(),self.product)['sets'][0]
  with self.assertRaises(local.NotReady):local.start(self.request(),self.product)
  self.assertEqual([s['id'] for s in colours.list_sets('own')['sets']],[one['id']])
 def test_ambiguous_existing_provider_request_is_never_overwritten(self):
  self.ready();before=self.previous(['submit_unknown','needs_revision'])
  with self.assertRaises(local.NotReady):local.start(self.request(),self.product)
  self.assertEqual(colours.get(before['id']),before)
 def test_mask_change_stops_frozen_local_task_without_api_fallback(self):
  self.ready();s=local.start(self.request(),self.product)['sets'][0];self.selection(0,revision=1)
  local.work(s,self.product);saved=colours.get(s['id'])
  self.assertEqual(saved['status'],'needs_attention');self.assertEqual(saved['items'][0]['status'],'local_failed')
 def test_process_interruption_resumes_only_unfinished_local_slot(self):
  self.ready();s=local.start(self.request(),self.product)['sets'][0];original=pixel.render
  def interrupt(data,product):
   if data['slot']==1:raise KeyboardInterrupt('simulated process exit')
   return original(data,product)
  with patch.object(pixel,'render',side_effect=interrupt):
   with self.assertRaises(KeyboardInterrupt):local.work(s,self.product)
  saved=colours.get(s['id']);first=copy.deepcopy(saved['items'][0])
  with patch.object(pixel,'render',wraps=original) as render:local.work(saved,self.product)
  self.assertEqual(render.call_count,1);self.assertEqual(colours.get(s['id'])['items'][0]['image'],first['image'])
 def test_native_queue_has_an_explicit_paid_api_guard_for_local_tasks(self):
  s={'id':'guard','productId':'own','model':'local-pixel','validated':True,'items':[{'slot':0,'status':'queued'}]}
  with self.assertRaisesRegex(ValueError,'禁止提交图片生成API'):colours.work(s)
 def test_running_local_task_cannot_be_overwritten_by_legacy_upload_repair(self):
  self.configure();self.selection(1);before=self.previous(['awaiting_manual','needs_revision'])
  s=local.start(self.request(),self.product)['sets'][0]
  data={'id':s['id'],'slot':0,'previousImage':before['items'][0]['image'],'image':before['items'][0]['image'],'note':'must not overwrite a running local task','confirmed':True}
  with self.assertRaises(ValueError):colours.repair_local(data,self.product)
  self.assertEqual(colours.get(s['id']),s)

if __name__=='__main__':unittest.main()
