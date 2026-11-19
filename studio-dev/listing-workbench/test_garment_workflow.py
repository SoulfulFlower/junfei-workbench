import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from PIL import Image
import garment_workflow as workflow
import test_pixel_recolour as fixtures
import pixel_recolour as pixel


class WorkflowTests(unittest.TestCase):
 def test_disconnected_cloth_is_union_of_independent_prompts_and_protection_wins(self):
  source=Image.new('RGB',(80,60),'white');base=Image.new('L',source.size)
  protection=np.zeros((60,80),dtype='uint8');protection[20:30,36:40]=255
  engine=Mock();calls=[]
  def decode(image,fg,bg):
   calls.append(fg);a=np.zeros((60,80),dtype='uint8')
   if fg[0][0]<40:a[10:50,10:40]=255
   else:a[22:28,45:50]=255
   return Image.fromarray(a),{'humanReviewed':False}
  engine.select.side_effect=decode
  result,receipt=workflow.select(source,base,Image.fromarray(protection),{'foreground':[[20,20],[47,25]],'background':[[70,55]],'operation':'replace','refineEdges':False},Path('unused'),engine)
  a=np.asarray(result);self.assertEqual(len(calls),2);self.assertEqual(a[25,47],255);self.assertEqual(a[15,15],255);self.assertEqual(a[25,38],0)
  self.assertFalse(receipt['imageGenerationSubmitted']);self.assertFalse(receipt['humanReviewed'])
 def test_add_preserves_existing_mask_and_negative_points_do_not_recolour_protected_skin(self):
  base=np.zeros((30,30),dtype='uint8');base[2:10,2:10]=255
  proposal=np.zeros_like(base);proposal[15:25,15:25]=255
  protected=np.zeros_like(base);protected[20:25,20:25]=255
  a=np.asarray(workflow.combine(Image.fromarray(base),Image.fromarray(proposal),Image.fromarray(protected),'add'))
  self.assertEqual(a[5,5],255);self.assertEqual(a[18,18],255);self.assertEqual(a[22,22],0)
 def test_invalid_points_and_protected_positive_never_load_model(self):
  source=Image.new('RGB',(30,30));blank=Image.new('L',source.size)
  with patch.object(workflow,'selector') as load:
   for data in ({'foreground':[[True,1]],'background':[[0,0]]},{'foreground':[[30,1]],'background':[[0,0]]},{'foreground':[[1,1]],'background':[]}):
    with self.assertRaises(ValueError):workflow.select(source,blank,blank,data,'unused')
   with self.assertRaisesRegex(ValueError,'保护区'):workflow.select(source,blank,Image.new('L',source.size,255),{'foreground':[[1,1]],'background':[[0,0]]},'unused')
   load.assert_not_called()
 def test_inspection_highlights_small_island_without_editing_or_auto_accepting_it(self):
  rgb=np.full((150,150,3),255,dtype='uint8');rgb[20:120,20:65]=[30,30,35];rgb[65:75,75:85]=[31,30,35]
  mask=np.zeros((150,150),dtype='uint8');mask[20:120,20:65]=255
  protect=np.zeros_like(mask);protect[65:75,80:85]=255
  result,report=workflow.inspect(Image.fromarray(rgb),Image.fromarray(mask),Image.fromarray(protect))
  a=np.asarray(result);self.assertEqual(a[68,77],255);self.assertEqual(a[68,82],0);self.assertTrue(report['suggestionOnly']);self.assertGreater(report['suspectPixels'],0)
  self.assertEqual(mask[68,77],0)
 def test_components_without_garment_prompts_are_removed(self):
  mask=np.zeros((60,60),dtype='uint8');mask[2:20,2:20]=255;mask[25:30,25:30]=255;mask[40:45,40:45]=255
  a=np.asarray(workflow.prompted_components(Image.fromarray(mask),[[5,5],[27,27]]))
  self.assertEqual(a[5,5],255);self.assertEqual(a[27,27],255);self.assertEqual(a[42,42],0)


class ProposalBoundaryTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.PixelTests('test_selection_restores_protection_and_optimistic_revision');self.fixture.setUp()
 def tearDown(self):self.fixture.tearDown()
 def test_proposal_does_not_save_or_overwrite_concurrent_selection(self):
  f=self.fixture;data={**f.row,'revision':0,'alpha':__import__('base64').b64encode(pixel.png(f.mask)).decode(),'protected':__import__('base64').b64encode(pixel.png(f.protect)).decode(),'foreground':[[10,5]],'background':[[0,0]]}
  with patch.object(workflow,'select',return_value=(f.mask,{'imageGenerationSubmitted':False})) as select:
   result=pixel.select_garment(data,f.product);self.assertFalse(result['saved']);self.assertIsNone(pixel.selection(f.row,f.product)['selection'])
   f.save()
   with self.assertRaisesRegex(ValueError,'版本'):pixel.select_garment(data,f.product)
   self.assertEqual(select.call_count,1)
   with self.assertRaises(ValueError):pixel.select_garment({**data,'sourceHash':'stale'},f.product)
   with self.assertRaises(ValueError):pixel.select_garment(data,{'id':'other'})


if __name__=='__main__':unittest.main()
