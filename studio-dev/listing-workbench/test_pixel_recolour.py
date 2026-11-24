import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import pixel_recolour as pixel
from local_mask_recolor import render_fabric

class PixelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'uploads').mkdir()
        self.patches=[patch.object(pixel,'ROOT',self.root),patch.object(pixel.image_provider,'ROOT',self.root),patch.object(pixel.colour_sets,'DB',self.root/'sets.sqlite3')]
        for p in self.patches:p.start()
        arr=np.full((40,40,3),[120,35,50],dtype='uint8');arr[::2,8:32]+=8
        self.src=Image.fromarray(arr);self.url=pixel.asset(pixel.png(self.src));self.product={'id':'own'}
        self.set={'id':'set','productId':'own','masterId':'m','status':'needs_attention','color':'Beige','items':[{'slot':0,'sourceUpload':self.url,'image':self.url,'status':'needs_revision'}]}
        pixel.colour_sets.save(self.set);self.row=pixel.sources(self.product)['sources'][0]
        mask=np.zeros((40,40),dtype='uint8');mask[:,8:32]=255;protect=np.zeros_like(mask);protect[10:20,15:19]=255
        self.mask=Image.fromarray(mask);self.protect=Image.fromarray(protect)
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def save(self,**kw):
        return pixel.save_selection({**self.row,'revision':0,'alpha':base64.b64encode(pixel.png(self.mask)).decode(),'protected':base64.b64encode(pixel.png(self.protect)).decode(),**kw},self.product)
    def render(self,**kw):
        return pixel.render({**self.row,'revision':1,'target':'#e0d9ce','texture':1,'exposure':-3,**kw},self.product)
    def test_selection_restores_protection_and_optimistic_revision(self):
        record=self.save();read=pixel.selection(self.row,self.product)['selection'];self.assertEqual(record,read)
        a=np.asarray(pixel.image(record['alpha']));self.assertTrue((a[10:20,15:19]==0).all())
        with self.assertRaisesRegex(ValueError,'已被修改'):self.save()
        self.assertEqual(pixel.selection(self.row,self.product)['selection']['revision'],1)

    def test_parser_upgrade_preserves_real_saved_edits_without_faking_automatic_provenance(self):
        record=self.save(edits=[{'method':'source-bound prompted correction','humanReviewed':False}])
        self.assertNotIn('automaticSelection',record)
        self.assertFalse(pixel.selection_needs_refresh(record))
        with patch('garment_auto.identify',side_effect=AssertionError('saved editor mask must not be replaced')):
            kept=pixel.ensure_automatic_selections(self.product,refresh_legacy=True)[0]
        self.assertEqual(kept,record)
        for changed in [{'sourceHash':'different'},{'revision':2}]:
            stale={**record,'editedSelection':{**record['editedSelection'],**changed}}
            self.assertTrue(pixel.selection_needs_refresh(stale))
        automatic={**record,'automaticSelection':{'version':'old-parser'}};automatic.pop('editedSelection')
        self.assertTrue(pixel.selection_needs_refresh(automatic))

    def test_only_absent_product_storyboard_card_can_be_reused_whole(self):
        self.mask=Image.new('L',(40,40),0);self.protect=Image.new('L',(40,40),255)
        with self.assertRaisesRegex(ValueError,'无商品'):self.save(preserveWholeImage=True,confirmed=True)
        s=pixel.colour_sets.get('set');s['items'][0]['productAbsent']=True;pixel.colour_sets.save(s)
        self.row=pixel.sources(self.product)['sources'][0]
        with self.assertRaisesRegex(ValueError,'无商品'):self.save(preserveWholeImage=True,confirmed=False)
        record=self.save(preserveWholeImage=True,confirmed=True)
        self.assertTrue(record['preserveWholeImage']);result=self.render(target='#002200')
        np.testing.assert_array_equal(np.asarray(pixel.image(result['image'])),np.asarray(self.src))
        self.assertFalse(result['humanReviewed'])

    def test_automatic_chart_recolour_preserves_every_pixel_outside_source_photo(self):
        box=[12,3,30,17]
        chart=pixel.colour_sets.get('set')
        chart['items'][0]['sizeChartPreviewBox']=box
        pixel.colour_sets.save(chart)
        source=pixel.sources(self.product)['sources'][0]
        with patch('garment_auto.identify',return_value=(Image.new('L',(18,14),255),{'version':'test'})) as identify:
            selection=pixel.automatic_selection({**source,'revision':0,'sizeChartPreviewBox':[0,0,40,40]},self.product)['selection']
        self.assertEqual(identify.call_args.args[0].size,(18,14))
        self.assertEqual(selection['automaticSelection']['sizeChartPreviewBox'],box)
        result=pixel.render({**source,'revision':1,'target':'#0870ac'},self.product)
        original=np.asarray(self.src)
        actual=np.asarray(pixel.image(result['image']))
        outside=np.ones(original.shape[:2],dtype=bool)
        outside[3:17,12:30]=False
        np.testing.assert_array_equal(actual[outside],original[outside])
        self.assertTrue(np.any(actual[~outside]!=original[~outside]))
    def test_source_identity_and_product_isolation(self):
        self.save()
        with self.assertRaises(ValueError):pixel.selection(self.row,{'id':'other'})
        pixel.asset(pixel.png(Image.new('RGB',(40,40),'black')))
        changed=dict(self.set);changed['items']=[{**self.set['items'][0],'sourceUpload':pixel.asset(pixel.png(Image.new('RGB',(40,40),'black')))}];pixel.colour_sets.save(changed)
        with self.assertRaisesRegex(ValueError,'母版已变化'):pixel.selection(self.row,self.product)
    def test_preview_download_and_batch_are_identical_and_protected_exact(self):
        self.save();first=self.render();second=self.render();self.assertEqual(first,second)
        actual=np.asarray(pixel.image(first['image']));original=np.asarray(self.src)
        unchanged=(np.asarray(self.mask)==0)|(np.asarray(self.protect)>0)
        np.testing.assert_array_equal(actual[unchanged],original[unchanged])
        self.assertGreater(float(actual[0,10,1])-actual[1,10,1],3)
        self.assertFalse(first['humanReviewed'])
    def test_invalid_dimensions_stale_revision_and_bad_controls_rejected(self):
        bad=base64.b64encode(pixel.png(Image.new('L',(3,3),255))).decode()
        with self.assertRaises(ValueError):self.save(alpha=bad)
        self.save()
        for data in [{'revision':2},{'target':'red'},{'texture':float('nan')},{'exposure':100},{'pattern':{'kind':'other'}}]:
            with self.assertRaises(ValueError):self.render(**data)
    def test_commit_only_failed_same_source_and_keeps_real_qa_pending(self):
        self.save();r=self.render()
        saved=pixel.commit({'id':'set','renderId':r['id'],'previousImage':self.url},self.product)
        self.assertEqual(saved['items'][0]['status'],'reviewing');self.assertNotIn('qc',saved['items'][0])
        self.assertEqual(saved['items'][0]['history'][0]['image'],self.url)
        self.assertEqual(saved['items'][0]['localCorrection']['pixelRecipe']['id'],r['id'])
        with self.assertRaises(ValueError):pixel.commit({'id':'set','renderId':r['id'],'previousImage':self.url},self.product)
    def test_other_product_cannot_commit_render_or_target(self):
        self.save();r=self.render()
        with self.assertRaises(ValueError):pixel.commit({'id':'set','renderId':r['id'],'previousImage':self.url},{'id':'other'})
        other={**self.set,'id':'other','productId':'other'};pixel.colour_sets.save(other)
        with self.assertRaises(ValueError):pixel.commit({'id':'other','renderId':r['id'],'previousImage':self.url},self.product)
    def test_old_preview_cannot_replace_after_mask_edit(self):
        self.save();r=self.render();self.save(revision=1)
        with self.assertRaisesRegex(ValueError,'选区已更新'):pixel.commit({'id':'set','renderId':r['id'],'previousImage':self.url},self.product)
    def test_batch_failure_is_atomic_and_passed_slot_is_locked(self):
        self.save();r=self.render()
        before=pixel.colour_sets.get('set')
        with self.assertRaises(ValueError):pixel.commit_batch({'id':'set','changes':[{'renderId':r['id'],'previousImage':self.url},{'renderId':'missing','previousImage':self.url}]},self.product)
        self.assertEqual(pixel.colour_sets.get('set'),before)
        saved=pixel.commit_batch({'id':'set','changes':[{'renderId':r['id'],'previousImage':self.url}]},self.product)
        self.assertIn('pixelRecipe',saved['items'][0]['localCorrection'])
        self.assertEqual(saved['items'][0]['status'],'reviewing')
        saved['status']='awaiting_manual';saved['items'][0]['status']='awaiting_manual';pixel.colour_sets.save(saved)
        with self.assertRaises(ValueError):pixel.commit({'id':'set','renderId':r['id'],'previousImage':r['image']},self.product)
    def test_transparency_constant_and_dark_gray_are_finite(self):
        src=self.src.convert('RGBA');src.putalpha(Image.new('L',src.size,127))
        for target in ([5,5,5],[240,235,228]):
            out=render_fabric(src,np.asarray(self.mask)/255,self.protect,target)
            np.testing.assert_array_equal(np.asarray(out)[:,:,3],127)
            self.assertTrue(np.isfinite(np.asarray(out)).all())
    def test_soft_edges_cannot_create_cyan_from_warm_source_and_pale_target(self):
        alpha=np.asarray(self.mask,dtype=float)/255
        alpha[:,8:11]=[.1,.3,.6]
        source=np.asarray(self.src)
        for target in ([224,217,206],[246,217,222]):
            out=np.asarray(render_fabric(self.src,alpha,self.protect,target))
            self.assertTrue(np.all(out[:,:,0]>=out[:,:,1]))
            self.assertTrue(np.all(out[:,:,0]>=out[:,:,2]))
            np.testing.assert_array_equal(out[alpha==0],source[alpha==0])
    def test_luminance_protection_and_local_cast_layer_keep_geometry_and_background(self):
        import cv2
        region=Image.new('L',self.src.size);region.paste(255,(10,0,15,40))
        result=render_fabric(self.src,np.asarray(self.mask)/255,self.protect,[224,217,206],illumination=region,
            adjustments=[{'mask':region,'color':[156,105,72],'sourceLightness':True}])
        before=cv2.cvtColor(np.asarray(self.src).astype('float32')/255,cv2.COLOR_RGB2LAB)
        after=cv2.cvtColor(np.asarray(result).astype('float32')/255,cv2.COLOR_RGB2LAB)
        self.assertLess(float(np.abs(before[:,10:15,0]-after[:,10:15,0]).max()),1)
        np.testing.assert_array_equal(np.asarray(result)[:,:8],np.asarray(self.src)[:,:8])
    def test_adjustment_masks_survive_save_and_tamper_is_rejected(self):
        layer={'mask':base64.b64encode(pixel.png(self.mask)).decode(),'color':'target','sourceLightness':True}
        record=self.save(adjustments=[layer]);self.assertEqual(len(record['adjustments']),1)
        following=self.save(revision=1);self.assertEqual(following['adjustments'],record['adjustments'])
        path=self.root/following['adjustments'][0]['mask'].lstrip('/')
        path.write_bytes(pixel.png(Image.new('L',self.src.size,128)))
        with self.assertRaisesRegex(ValueError,'选区内容变化'):self.render(revision=2)

if __name__=='__main__':unittest.main()
