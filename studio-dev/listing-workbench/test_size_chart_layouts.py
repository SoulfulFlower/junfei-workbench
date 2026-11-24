import io,copy,unittest
from PIL import Image,ImageDraw
import size_chart_layouts as layout
import shared_size_chart as shared

class SizeLayoutTests(unittest.TestCase):
 def chart(self):return {'columns':['Size','Chest','Length','Sleeve length'],'units':'cm','rows':[['M','82','59','71'],['L','86','60','71.5'],['XL','90','61','72'],['2XL','94','62','72.5']]}
 def test_exact_four_source_rows_and_units_remain_in_the_rendered_layout(self):
  image=Image.new('RGB',(600,800),'white');ImageDraw.Draw(image).rectangle((150,100,450,800),fill='pink')
  chart=self.chart();raw,receipt=layout.editorial(image,chart)
  self.assertEqual(Image.open(io.BytesIO(raw)).size,(2000,2000))
  self.assertEqual(receipt['chartRows'],chart['rows']);self.assertEqual(receipt['chartColumns'],chart['columns']);self.assertEqual(receipt['units'],'cm')
  self.assertLessEqual(receipt['photoCropPixels'][0],150);self.assertGreaterEqual(receipt['photoCropPixels'][2],450)
  self.assertFalse(receipt['garmentPixelsRepainted'])
 def test_size_data_are_not_truncated_or_filled_when_invalid(self):
  for chart in [{**self.chart(),'rows':[['M','82']]},{**self.chart(),'columns':['onlyone']}]:
   with self.assertRaises(ValueError):layout.editorial(Image.new('RGB',(200,200),'pink'),chart)
 def test_new_and_legacy_chart_styles_are_explicit_and_reusable(self):
  chart={'source':'https://supplier.test','units':'cm','measurementMethod':'Original garment chart','columns':self.chart()['columns'],'rows':[{'size':r[0],**dict(zip(self.chart()['columns'][1:],r[1:]))} for r in self.chart()['rows']]}
  def cache(im):return {'url':'asset-'+str(im.size)}
  classic=shared.render_candidate(chart,Image.new('RGB',(400,600),'pink'),0,cache)
  self.assertEqual(classic['sizeLayout']['style'],'classic-v1')
  modern=shared.render_candidate({**chart,'style':'editorial-split-v1'},Image.new('RGB',(400,600),'pink'),0,cache)
  self.assertTrue(modern['sharedAcrossAllVariants']);self.assertEqual(modern['sizeLayout']['style'],'editorial-split-v1')
 def test_fixed_chart_plan_has_the_same_layout_authority_as_the_renderer(self):
  chart={'style':'editorial-split-v1','source':'https://supplier.test','units':'cm'}
  plan=shared.size_plan({'sizeChart':chart,'primaryReferenceIndex':0,'count':1})
  self.assertIn('deterministic',plan['planSource']);self.assertIn('not an AI storyboard',plan['planSource'])
  self.assertIn('Right 50 percent is a warm ivory panel',plan['shots'][0]['scene'])
  self.assertEqual(plan['shots'][0]['copy'],['SIZE & FIT','Garment measurements / cm'])
 def test_new_design_declares_its_version_and_preserves_a_distinct_right_panel(self):
  raw,receipt=layout.editorial(Image.new('RGB',(300,500),'pink'),self.chart())
  image=Image.open(io.BytesIO(raw));self.assertEqual(receipt['rendererVersion'],2)
  self.assertEqual(image.getpixel((1990,10)),(247,241,232));self.assertEqual(image.getpixel((10,10)),(255,255,255))

if __name__=='__main__':unittest.main()
