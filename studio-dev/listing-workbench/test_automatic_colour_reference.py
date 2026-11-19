import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import automatic_colour_reference as ref
import garment_auto
import pixel_recolour as pixel
import test_pixel_recolour as fixtures


class AutomaticReferenceTests(unittest.TestCase):
 def test_only_linked_variant_main_is_eligible_not_supplier_or_another_colour(self):
  group={'references':[{'referenceType':'supplier_product_image','url':'supplier'},{'referenceType':'amazon_variant_main','sourceAsin':'real-child','url':'main'}]}
  self.assertEqual(ref.main_reference(group,'supplier')['url'],'main')
  with self.assertRaises(ValueError):ref.main_reference({'references':group['references'][:1]})
 def test_samples_fabric_without_skin_background_watch_or_crop_points(self):
  rgb=np.full((100,100,4),255,'uint8');rgb[10:90,10:90]=[180,55,70,255];rgb[30:55,30:55]=[180,130,110,255]
  mask=np.zeros((100,100),'uint8');mask[10:90,10:90]=255;mask[30:55,30:55]=0
  shade=ref.colour(Image.fromarray(rgb),Image.fromarray(mask));np.testing.assert_allclose(shade['rgb'],[180,55,70],atol=1)
  self.assertGreater(shade['fabricPixels'],1000)
 def test_white_and_black_variants_are_sampled_from_their_fabric(self):
  for n in (7,245):
   result=ref.colour(Image.new('RGB',(40,40),(n,n,n)),Image.new('L',(40,40),255));np.testing.assert_allclose(result['rgb'],n,atol=1)


class AutomaticMigrationTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.PixelTests('test_selection_restores_protection_and_optimistic_revision');self.fixture.setUp()
 def tearDown(self):self.fixture.tearDown()
 def test_legacy_selection_is_replaced_with_versioned_auto_mask_without_erasing_history(self):
  f=self.fixture;old=f.save()
  def infer(source,protected,cache,kind):
   self.assertFalse(np.asarray(protected).any());return f.mask,{'type':'automatic-clothing','automatic':True,'version':garment_auto.VERSION}
  with patch.object(garment_auto,'identify',side_effect=infer):new=pixel.ensure_automatic_selections(f.product,[0],refresh_legacy=True)[0]
  self.assertEqual(new['revision'],2);self.assertEqual(new['automaticSelection']['version'],garment_auto.VERSION)
  c=pixel.connection()
  try:self.assertEqual(c.execute('SELECT count(*) FROM selections').fetchone()[0],2)
  finally:c.close()
  with patch.object(garment_auto,'identify') as model:
   pixel.ensure_automatic_selections(f.product,[0],refresh_legacy=True);model.assert_not_called()
  self.assertFalse(new['humanReviewed'])


if __name__=='__main__':unittest.main()
