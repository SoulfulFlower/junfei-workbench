"""Composition policy tests use real raster bytes; no network or paid models."""
import io
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
import image_composition as composition
import image_quality


def raster(kind='large', background='#f3f5f7', size=(400,400)):
    image = Image.new('RGB', size, background)
    draw = ImageDraw.Draw(image)
    w, h = size
    if kind == 'narrow':
        box = (w*.2, 0, w*.8-1, h-1)
    elif kind == 'boxed':
        box = (w*.23, h*.23, w*.77, h*.95)
        draw.text((w*.07,h*.07), 'Detailed Hem', fill='black')
    elif kind == 'chart':
        for y in range(90,310,35):
            draw.line((25,y,w-25,y),fill='black',width=2)
            for x in range(40,w-25,55):
                draw.text((x,y+4),'123',fill='black')
        box = None
    elif kind == 'empty':
        box = None
    elif kind == 'tiny_chart':
        draw.text((180,180), 'S 96 60', fill='black')
        box = None
    else:
        box = (w*.08,h*.04,w*.92,h*.96)
    if box:
        draw.rectangle(box, fill='#21334f')
        draw.line((box[0]+5,box[1]+5,box[2]-5,box[3]-5),fill='#829fc7',width=4)
    out = io.BytesIO(); image.save(out,'PNG')
    return out.getvalue()


def pale_ribbed_photo(inset=False, noisy_card=False):
    """Fabric and padding have overlapping RGB, but only fabric has ribs."""
    image = Image.new('RGB', (400,400), (230,224,220))
    if noisy_card:
        rng = np.random.default_rng(8)
        pixels = np.asarray(image).astype('int16')
        pixels += rng.integers(-4,5,(400,400,1))
        image = Image.fromarray(pixels.clip(0,255).astype('uint8'))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = (130,140,270,300) if inset else (40,40,360,400)
    draw.rectangle((left,top,right,bottom), fill=(232,226,218))
    for x in range(left,right,8):
        draw.rectangle((x,top,x+3,bottom), fill=(212,206,200))
    if inset:
        draw.rectangle((180,110,220,160), fill='#bb8766')
        draw.rectangle((165,280,235,310), fill='#203b58')
        draw.text((30,30),'Sleeve Detail',fill='black')
    else:
        draw.rectangle((170,0,230,170), fill='#bb8766')
        draw.rectangle((100,350,300,400), fill='#203b58')
    out = io.BytesIO(); image.save(out,'PNG')
    return out.getvalue()


class CompositionTests(unittest.TestCase):
    def setUp(self):
        composition._CACHE.clear()

    def codes(self, raw, **kwargs):
        return {i['code'] for i in composition.inspect(raw,**kwargs)['issues']}

    def test_narrow_main_is_blocked_without_stretching_pixels(self):
        raw = raster('narrow',background='white')
        self.assertIn('SUBJECT_TOO_SMALL',self.codes(raw,role='main'))
        self.assertFalse(image_quality.inspect(raw,main=True)['pass'])

    def test_large_main_and_natural_portrait_canvas_are_allowed(self):
        for size in ((400,400),(300,500)):
            with self.subTest(size=size):
                self.assertTrue(composition.inspect(raster(size=size),role='main')['pass'])

    def test_grey_white_and_warm_neutral_insets_are_blocked(self):
        for background in ('#f3f5f7','white','#e8e3df'):
            with self.subTest(background=background):
                self.assertIn('BOXED_SMALL_PHOTO',self.codes(raster('boxed',background)))

    def test_detached_header_does_not_inflate_photo_occupancy(self):
        result = composition.inspect(raster('boxed'))
        self.assertFalse(result['pass'])
        self.assertLess(result['contentEnvelope']['width'],.6)

    def test_large_supporting_photo_is_allowed(self):
        self.assertTrue(composition.inspect(raster())['pass'])

    def test_large_pale_ribbed_garment_is_content_even_when_it_matches_padding_colour(self):
        raw = pale_ribbed_photo()
        result = composition.inspect(raw)
        self.assertTrue(result['pass'],result)
        self.assertGreater(result['frame']['texturedContentFraction'],.4)
        self.assertEqual(result['contentEnvelope']['height'],1)

    def test_same_pale_fabric_in_a_small_card_is_still_blocked_with_mild_noise(self):
        for noisy in (False,True):
            for role in ('supporting','detail'):
                with self.subTest(noisy=noisy,role=role):
                    self.assertIn('BOXED_SMALL_PHOTO',self.codes(
                        pale_ribbed_photo(inset=True,noisy_card=noisy),role=role))

    def test_chart_uses_all_table_cells_and_skips_clothing_model(self):
        with patch.object(composition,'_garment',side_effect=AssertionError('chart is not a garment')):
            result = composition.inspect(raster('chart'),role='size_chart',garment_kind='upper')
        self.assertTrue(result['pass'],result)

    def test_tiny_chart_and_empty_image_block(self):
        self.assertIn('SIZE_CHART_TOO_SMALL',self.codes(raster('tiny_chart'),role='size_chart'))
        self.assertIn('EMPTY_COMPOSITION',self.codes(raster('empty')))

    def test_actual_garment_not_room_controls_scene_coverage(self):
        raw = raster(background='#765b4b')
        small = {'coverage':.07,'box':[.4,.2,.6,.5]}
        with patch.object(composition,'_garment',return_value=small) as model:
            result = composition.check(raw,slot=1,product={'name':'Women sweater'})
        self.assertFalse(result['pass'])
        self.assertEqual(result['issues'][0]['code'],'GARMENT_TOO_SMALL')
        self.assertEqual(model.call_args.args[1],'upper')

    def test_large_garment_scene_and_detail_pass(self):
        with patch.object(composition,'_garment',return_value={'coverage':.35,'box':[.1,.1,.9,.9]}):
            for role in ('supporting','detail'):
                self.assertTrue(composition.inspect(raster(),role=role,garment_kind='upper')['pass'])

    def test_detail_macro_skips_whole_body_parser_but_keeps_framing_gate(self):
        with patch.object(composition,'_garment',side_effect=AssertionError('partial garment')):
            self.assertTrue(composition.inspect(raster(),role='detail',garment_kind='lower')['pass'])
            self.assertIn('BOXED_SMALL_PHOTO', self.codes(raster('boxed'),role='detail',garment_kind='lower'))

    def test_model_failure_blocks_and_same_image_can_retry_after_repair(self):
        with patch.object(composition,'_garment',side_effect=ValueError('model missing')):
            failed = composition.inspect(raster(),garment_kind='upper')
        self.assertEqual(failed['issues'][0]['code'],'COMPOSITION_UNAVAILABLE')
        with patch.object(composition,'_garment',return_value={'coverage':.5,'box':[0,0,1,1]}):
            self.assertTrue(composition.inspect(raster(),garment_kind='upper')['pass'])

    def test_cached_results_cannot_be_mutated_to_bypass_failure(self):
        raw=raster('boxed');result=composition.inspect(raw)
        result['pass']=True;result['issues'].clear()
        self.assertFalse(composition.inspect(raw)['pass'])

    def test_cache_is_bound_to_pixels_role_and_product_kind(self):
        bad=raster('boxed');good=raster()
        self.assertFalse(composition.inspect(bad)['pass'])
        self.assertTrue(composition.inspect(good)['pass'])
        self.assertNotEqual(composition.inspect(bad)['sha256'],composition.inspect(good)['sha256'])

    def test_corrupt_images_fail_closed_and_invalid_roles_are_rejected(self):
        self.assertFalse(composition.inspect(b'not an image')['pass'])
        with self.assertRaises(ValueError):composition.inspect(raster(),role='skip')

    def test_require_cannot_be_overridden_by_old_approval_metadata(self):
        with self.assertRaisesRegex(ValueError,'第 2 张图片构图不通过'):
            composition.require(raster('boxed'),slot=1,product={'humanReviewed':True,'status':'approved'})

    def test_semantic_mask_ignores_detached_garment_like_text(self):
        import garment_auto
        labels=np.zeros((256,256),dtype=np.uint8)
        labels[50:180,60:190]=4
        labels[5:9,5:250]=4
        fake=type('Parser',(),{'predict':lambda self,image:labels})()
        cloth=type('Cloth',(),{'predict':lambda self,image:np.zeros_like(labels)})()
        with patch.object(garment_auto,'human_parser',return_value=fake), patch.object(garment_auto,'parser',return_value=cloth):
            result=composition._garment(Image.new('RGB',(256,256)),'upper')
        self.assertAlmostEqual(result['coverage'],130*130/(256*256),places=4)
        self.assertGreater(result['box'][1],.1)

    def test_clothes_parser_recovers_trousers_misclassified_as_upper_body(self):
        import garment_auto
        human=np.zeros((256,256),dtype=np.uint8);human[20:235,65:190]=4
        labels=np.zeros_like(human);labels[40:235,65:190]=2
        hp=type('Human',(),{'predict':lambda self,image:human})()
        cp=type('Cloth',(),{'predict':lambda self,image:labels})()
        with patch.object(garment_auto,'human_parser',return_value=hp),patch.object(garment_auto,'parser',return_value=cp):
            result=composition._garment(Image.new('RGB',(256,256)),'lower')
        self.assertGreater(result['coverage'],.35)

    def test_full_bleed_quality_boundary_does_not_waive_grey_box(self):
        result=image_quality.inspect(raster('boxed'),full_bleed=True)
        self.assertFalse(result['pass'])
        self.assertIn('BOXED_SMALL_PHOTO',{i['code'] for i in result['issues']})

    def test_lower_continuation_recovers_connected_legs_but_not_coat_or_separate_background(self):
        im=Image.new('RGB',(128,128),'white');d=ImageDraw.Draw(im)
        d.rectangle((35,0,89,119),fill='#45241b');d.rectangle((0,90,14,124),fill='#45241b')
        human=np.zeros((128,128),dtype='uint8');human[40:66,35:90]=6
        cloth=np.zeros_like(human);cloth[:120,35:90]=3;cloth[90:125,:15]=3
        base=human==6
        recovered,proof=composition._lower_continuation(im,human,cloth,base)
        self.assertTrue(recovered[110,60]);self.assertFalse(recovered[20,60]);self.assertFalse(recovered[110,5])
        self.assertGreater(proof['addedPixels'],0)

    def test_lower_continuation_without_real_lower_body_seeds_cannot_grow(self):
        human=np.zeros((64,64),dtype='uint8');cloth=np.full_like(human,3);base=np.zeros_like(human,dtype=bool)
        recovered,proof=composition._lower_continuation(Image.new('RGB',(64,64),'brown'),human,cloth,base)
        self.assertFalse(recovered.any());self.assertIsNone(proof)


if __name__ == '__main__':
    unittest.main()
