import io
import unittest
from PIL import Image,ImageDraw
from product_pixels import primary_product_cutout
import product_artwork

class SourceArtworkTests(unittest.TestCase):
    def test_source_crop_keeps_exact_original_pixels_and_rejects_tiny_or_invalid_bounds(self):
        raw=self.source();cropped,proof=product_artwork.crop_source(raw,[.1,.1,.6,.6])
        original=Image.open(io.BytesIO(raw));actual=Image.open(io.BytesIO(cropped))
        self.assertEqual(actual.size,(200,200));self.assertEqual(actual.tobytes(),original.crop((40,40,240,240)).tobytes())
        self.assertEqual(proof['pixelBox'],[40,40,240,240])
        for box in [[0,0,.01,.1],[.5,.5,.1,.1],[0,0,2,1],[0,0,float('nan'),1],[0,0,.1,.2]]:
            with self.subTest(box=box),self.assertRaises(ValueError):product_artwork.crop_source(raw,box)

    def test_preview_escapes_source_text_and_marks_draft(self):
        import listing_preview
        html=listing_preview.render({'id':'test','market':'UK'},{'title':'<script>bad()</script>','description':'<img src=x onerror=bad()> '},{'sets':{}}).decode()
        self.assertNotIn('<script>',html)
        self.assertNotIn('<img src=x',html)
        self.assertIn('Listing 草稿预览，未发布',html)

    def source(self):
        im=Image.new('RGB',(400,400),'white');d=ImageDraw.Draw(im)
        d.rectangle((40,35,250,370),fill='#18304a');d.rectangle((290,25,360,105),fill='red')
        d.rectangle((100,95,180,120),fill='#eeeeee')
        out=io.BytesIO();im.save(out,'PNG');return out.getvalue()

    def test_detached_marketing_art_is_removed_without_redrawing_product(self):
        cut=primary_product_cutout(self.source())
        self.assertLess(cut.width,250)
        self.assertFalse(any(r>200 and g<80 and b<80 and a>20 for r,g,b,a in cut.getdata()))
        self.assertIn((24,48,74,255),list(cut.getdata()))

    def test_main_layout_is_full_square_and_keeps_product(self):
        raw=product_artwork.compose(self.source(),0,'Ignored main copy','No text')
        im=Image.open(io.BytesIO(raw))
        self.assertEqual(im.size,(2000,2000));self.assertEqual(im.getpixel((0,0)),(255,255,255))
        self.assertLess(im.getpixel((1000,1000))[0],100)

    def test_cropped_worn_source_main_does_not_add_an_interior_bottom_cut_line(self):
        source=Image.new('RGB',(200,400),'white')
        ImageDraw.Draw(source).rectangle((40,100,100,399),fill='#18304a')
        stream=io.BytesIO();source.save(stream,'PNG')
        raw=product_artwork.compose(stream.getvalue(),0,'','',preserve_full_source=True)
        actual=Image.open(io.BytesIO(raw))
        self.assertEqual(actual.size,(2000,2000))
        self.assertEqual(actual.getpixel((850,1999)),(24,48,74))
        self.assertEqual(actual.getpixel((0,1999)),(255,255,255))

    def test_complete_source_layout_preserves_detail_outside_primary_component(self):
        raw=product_artwork.compose(self.source(),4,'Real detail','Complete source photograph',preserve_full_source=True)
        image=Image.open(io.BytesIO(raw)).resize((200,200))
        self.assertTrue(any(r>200 and g<80 and b<80 for r,g,b in image.getdata()))

    def test_measurement_layout_changes_only_the_changed_table_cell(self):
        source=self.source()
        chart={'columns':['Size','Bust','Sleeve Length'],'units':'cm','measurementsScope':'garment_measurements',
               'rows':[['S','87','65.5'],['M','91','66']]}
        raw=product_artwork.compose_size_chart(source,chart,'Size Guide')
        changed={**chart,'rows':[['S','87','66.6'],['M','91','66']]}
        other=product_artwork.compose_size_chart(source,changed,'Size Guide')
        self.assertEqual(raw,product_artwork.compose_size_chart(source,chart,'Size Guide'))
        self.assertNotEqual(raw,other)
        before,after=[Image.open(io.BytesIO(value)) for value in (raw,other)]
        self.assertEqual(before.size,(2000,2000))
        self.assertEqual(before.crop((0,0,2000,600)).tobytes(),after.crop((0,0,2000,600)).tobytes())

    def test_two_size_chart_uses_canvas_without_changing_measurements_or_preview(self):
        import image_composition
        chart={'columns':['Size','Waist','Length'],'units':'cm','measurementsScope':'garment_measurements',
               'rows':[['S','64','41'],['M','68','42']]}
        original=__import__('copy').deepcopy(chart)
        raw=product_artwork.compose_size_chart(self.source(),chart,'Size Guide')
        self.assertEqual(chart,original)
        review=image_composition.inspect(raw,role='size_chart')
        self.assertTrue(review['pass'],review)
        self.assertGreater(review['contentEnvelope']['height'],.6)
        # The product preview and heading remain independent of table values.
        other=product_artwork.compose_size_chart(self.source(),{**chart,'rows':[['S','64','41'],['M','69','42']]},'Size Guide')
        before,after=[Image.open(io.BytesIO(v)) for v in [raw,other]]
        self.assertEqual(before.crop(product_artwork.SIZE_CHART_PREVIEW_BOX).tobytes(),after.crop(product_artwork.SIZE_CHART_PREVIEW_BOX).tobytes())
