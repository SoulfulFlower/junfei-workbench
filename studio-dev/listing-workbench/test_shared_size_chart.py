import copy,hashlib,io,tempfile,unittest
from unittest.mock import patch
from PIL import Image
import shared_size_chart as shared
import pixel_recolour as pixel
import local_colour_tasks as local
import colour_sets as colours
import test_local_colour_tasks as fixtures

class SharedSizeTests(unittest.TestCase):
 def chart(self):
  return {'units':'cm','sourcePage':'https://supplier.test/same','columns':['Size','Chest','Length'],'rows':[['M','82','59'],['L','86','60']],'measurementBasis':'Source garment measurements'}
 def test_source_table_keeps_exact_values_and_requires_all_sizes(self):
  product={'sizeNames':'M, L','supplierSizeEvidence':self.chart()}
  wire=shared.from_product(product);self.assertEqual(shared.table(wire)['rows'],self.chart()['rows'])
  self.assertEqual(wire['sourceEvidence'],{**self.chart(),'sourceKind':'supplier'})
  with self.assertRaisesRegex(ValueError,'全部'):shared.from_product({**product,'sizeNames':'M, L, XL'})
  with self.assertRaises(ValueError):shared.from_product({'sizeNames':'M'})
 def test_local_chart_is_rendered_from_data_without_an_image_submission(self):
  outputs={}
  def cache(im):
   b=io.BytesIO();im.save(b,'PNG');url=str(len(outputs));outputs[url]=b.getvalue();return {'url':url}
  chart=shared.from_product({'supplierSizeEvidence':self.chart()})
  with patch.object(pixel.image_provider,'submit',side_effect=AssertionError('No model image request')):
   result=shared.render_candidate(chart,Image.new('RGB',(500,700),'pink'),6,cache)
  self.assertTrue(result['sharedAcrossAllVariants']);self.assertEqual(Image.open(io.BytesIO(outputs[result['image']])).size,(1600,1600))
  self.assertNotIn('rawModelOutput',result)
 def test_only_exact_current_size_chart_bytes_can_be_shared(self):
  raw=b'exact original image bytes';digest=hashlib.sha256(raw).hexdigest()
  item={'slot':6,'sharedSizeChart':{'sourceSha256':digest}}
  project={'uiPlan':{'images':[{}]*6+[{'size_chart':True}]},'sizeEvidence':self.chart()}
  self.assertTrue(shared.verify_reuse(item,raw,raw,project)['byteIdentical'])
  for changed in (raw+b'changed',b''):
   with self.assertRaises(ValueError):shared.verify_reuse(item,raw,changed,project)
  with self.assertRaises(ValueError):shared.verify_reuse({**item,'slot':0},raw,raw,project)
 def test_seven_has_two_details_three_scenes_and_no_slot_substitution(self):
  images=[{'shot_type':'white_main'},*[{'shot_type':'detail','layout':'detail_macro'} for _ in range(2)],*[{'shot_type':'lifestyle','layout':'human_context'} for _ in range(3)],{'size_chart':True,'shot_type':'specs','layout':'spec_grid'}]
  shared.check_seven(images)
  for n in range(1,6):
   broken=copy.deepcopy(images);broken[n]={'shot_type':'hero_feature','layout':'poster_hero'}
   with self.assertRaises(ValueError):shared.check_seven(broken)
 def test_formal_seven_policy_keeps_scene_diversity_and_legacy_limits(self):
  from ivyea_pipeline import check_apparel_gallery
  from storyboard_variety import gallery_issues
  images=[{'shot_type':'white_main','layout':'white_main'},*[{'shot_type':'detail','layout':'detail_macro'} for _ in range(2)],*[{'shot_type':'lifestyle','layout':'human_context','scene_direction':dict(pose=pose,angle='front-on',framing=framing,composition=composition)} for pose,framing,composition in [('standing','medium shot','centered symmetry'),('walking','close shot','diagonal leading lines'),('seated','three-quarter-length shot','layered foreground and background')]],{'size_chart':True,'shot_type':'specs','layout':'spec_grid'}]
  check_apparel_gallery(images,seven_policy=True)
  self.assertEqual(gallery_issues(images,shared_verified_angle=True,seven_policy=True),[])
  with self.assertRaises(ValueError):check_apparel_gallery(images)
  repeated=copy.deepcopy(images);repeated[4]['scene_direction']=copy.deepcopy(repeated[3]['scene_direction'])
  self.assertTrue(gallery_issues(repeated,shared_verified_angle=True,seven_policy=True))
 def test_local_batch_does_not_segment_or_render_shared_chart(self):
  fixture=fixtures.LocalColourTests();fixture.setUp();self.addCleanup(fixture.tearDown)
  source=fixture.context['items'][1];source['sharedSizeChart']={'policy':'all-variants-unchanged-v1','sourceSha256':source['sourceSha256']}
  fixture.configure();fixture.selection(0)
  with patch.object(pixel,'ensure_automatic_selections',return_value=[]) as selection:
   result=local.start(fixture.request(),fixture.product)
  self.assertEqual(selection.call_args.args[1],[0])
  task=result['sets'][0];actual_render=pixel.render
  with patch.object(pixel,'render',wraps=actual_render) as render:
   local.work(task,fixture.product)
  self.assertEqual(render.call_count,1)
  item=colours.get(task['id'])['items'][1]
  self.assertEqual(item['image'],source['sourceUpload'])
  receipt=item['localCorrection']['pixelRecipe'];self.assertEqual(receipt['sha256'],source['sourceSha256'])
  self.assertFalse(receipt['garmentSelectionPerformed']);self.assertFalse(receipt['imageGenerationSubmitted'])
  broken={**pixel.source_row(source),'sharedSizeChart':{'sourceSha256':'0'*64}}
  with self.assertRaises(ValueError):shared.reuse_receipt(broken,pixel.image_provider.local_image)
  row=pixel.source_row(source)
  with self.assertRaisesRegex(ValueError,'共用'):pixel.automatic_selection({**row,'revision':0},fixture.product)
  with self.assertRaisesRegex(ValueError,'共用'):pixel.render({**row,'revision':0,'target':'#000000'},fixture.product)

if __name__=='__main__':unittest.main()
