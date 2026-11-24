import base64,copy,io,zipfile,hashlib
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw
from test_visual_studio import VisualTests,truth_fixture
import studio_bridge as bridge
import visual_studio as visual

class BridgeTests(VisualTests):
    def test_view_exposes_selected_gallery_review_separately_from_native_qa(self):
        import generated_gallery
        summary={'productId':'test-product','imageCount':7,'ready':True,'reviewScope':'draft_only'}
        product={'id':'test-product','generatedGallerySelection':{'version':1,'sourceStudioProjectId':'test','items':[]}}
        with patch.object(generated_gallery,'selection_summary',return_value=summary) as selected:
            view=bridge.get_view(product)
        selected.assert_called_once_with(product,'test')
        self.assertEqual(view['selectedGallery'],summary)
        self.assertTrue(all(not image.get('render_qa') for image in view['sets']['gallery']['images']))
        self.assertIsNone(view['sets']['gallery']['set_qa'])

    def test_aplus_card_preserves_wide_prompt_crops_result_and_exports_layered_psd(self):
        project={**self.project,'deliverable':'aplus','uiPlan':{'images':[
            {'role':'品牌首屏','shot_type':'aplus_banner','layout':'poster_hero','size':'1464x600',
             'product_presence':'supporting','render_prompt':'Sunlit garment from the front',
             'headline':'Designed for daily wear','text_on_image':True}
        ]}}
        visual.save_project(project)
        raw=io.BytesIO()
        image=Image.new('RGB',(1536,864),'#767e63')
        ImageDraw.Draw(image).rectangle((500,250,1000,600),fill='#282f25')
        image.save(raw,'PNG')
        with patch.object(visual.image_provider,'submit',return_value={'id':'wide-job'}) as submit, \
             patch.object(visual.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/banner.png']}), \
             patch.object(bridge,'result_image',return_value=(raw.getvalue(),'image/png')), \
             patch.object(visual,'review',return_value={'pass':True,'issues':[]}) as review:
            run=visual.generate({**self.options,'slot':0,'size':'16:9'})
            visual.advance(run['id'])
        recorded=visual.get_run(run['id'])
        request=submit.call_args.args[0]
        self.assertEqual(request['deliveryCanvas'],'1464x600')
        self.assertIn('WIDE BANNER FORMAT',request['prompt'])
        self.assertIn('central band',request['prompt'])
        self.assertEqual(recorded['qc'][0]['technical']['dimensions'],[1464,600])
        delivered=base64.b64decode(review.call_args.args[2].split(',',1)[1])
        with patch.object(bridge,'result_image',return_value=(delivered,'image/png')), \
             patch.object(visual,'encode_reference',return_value=truth_fixture()):
            psd,name=bridge.export_psd(run['id'])
        self.assertEqual(name,'aplus_01_DRAFT.psd')
        with Image.open(io.BytesIO(psd)) as document:
            self.assertEqual(document.size,(1464,600))
            self.assertEqual(document.format,'PSD')
            self.assertEqual([layer[0] for layer in document.layers],['final','product-source'])

    def test_set_review_transports_a_numbered_sheet_of_local_artwork(self):
        self.project['productFacts']={'packageContents':'1 pouch','copyNotes':'Accessories unconfirmed'}
        images=[{'_runId':'local-run','final_url':'local:local-run','render_qa':{'ready':True}}]
        artwork=io.BytesIO()
        image=Image.new('RGB',(80,60),'green')
        ImageDraw.Draw(image).rectangle((5,5,74,54),fill='#20a060')
        image.save(artwork,'PNG')
        with patch.object(bridge,'latest_project',return_value=self.project),patch.object(bridge,'native',return_value={'images':images}),patch.object(visual,'get_run',return_value={'image':'local:local-run'}),patch.object(bridge,'result_image',return_value=(artwork.getvalue(),'image/png')),patch.object(visual,'encode_reference',return_value='source'),patch.object(bridge,'task_new',return_value={}),patch.object(bridge,'task_save'),patch.object(bridge.threading,'Thread',side_effect=lambda target,daemon:SimpleNamespace(start=target)),patch.object(visual,'model_json',return_value={'ready':True,'issues':[]}) as model:
            task=bridge.review_set({}, {'id':'test-product'})
        self.assertEqual(task['status'],'done')
        source,sheet,*supplements=model.call_args.args[2]
        self.assertEqual(source,'source')
        self.assertEqual(len(supplements),1)
        self.assertEqual(base64.b64decode(supplements[0].split(',',1)[1]),artwork.getvalue())
        self.assertEqual(model.call_args.args[1]['supplementalImages'],[{'inputImageNumber':3,'slotNumber':1,'sourceSha256':hashlib.sha256(artwork.getvalue()).hexdigest()}])
        self.assertTrue(sheet.startswith('data:image/jpeg;base64,'))
        with Image.open(io.BytesIO(base64.b64decode(sheet.split(',',1)[1]))) as contact:
            self.assertEqual(contact.size,(420,420))
            self.assertGreater(contact.getpixel((210,210))[1],90)
        self.assertIn('printed SLOT labels',model.call_args.args[0])
        self.assertEqual(model.call_args.args[1]['productFacts'],self.project['productFacts'])
        self.assertIn('severity=error and ready=false',model.call_args.args[0])

    def test_set_review_keeps_close_feature_and_table_pixels_with_reference_numbering(self):
        # A tiny zipper and decimal measurement disappear in the sheet, yet
        # both must reach the real reviewer as their unchanged saved artwork.
        images=[{'_runId':str(n),'final_url':'local:'+str(n),'render_qa':{'ready':True},
                 'product_presence':presence} for n,presence in enumerate(['hero','hero','supporting','environmental','absent'])]
        pixels=[]
        for n in range(len(images)):
            out=io.BytesIO();picture=Image.new('RGB',(600,600),(25+n*20,95,75));draw=ImageDraw.Draw(picture)
            draw.rectangle((80,60,520,540),fill=(25+n*20,95,75));draw.line((300,150,305,450),fill='black',width=2)
            draw.text((305,300),'71.5' if n==4 else str(n),fill='white');picture.save(out,'PNG');pixels.append(out.getvalue())
        with patch.object(bridge,'latest_project',return_value=self.project),patch.object(bridge,'native',return_value={'images':images}), \
             patch.object(visual,'get_run',return_value={'image':'local:source'}), \
             patch.object(bridge,'result_image',side_effect=lambda rid:(pixels[int(rid)],'image/png')), \
             patch.object(visual,'encode_reference',return_value='source'),patch.object(bridge,'task_new',return_value={}), \
             patch.object(bridge,'task_save'),patch.object(bridge.threading,'Thread',side_effect=lambda target,daemon:SimpleNamespace(start=target)), \
             patch.object(bridge.image_quality,'duplicate_issues',return_value=[]), \
             patch.object(bridge,'verified_set_references',return_value=(['actual-extra-source'],[{'inputImageNumber':3}])), \
             patch.object(visual,'model_json',return_value={'ready':False,'issues':[{'code':'IDENTITY','severity':'error','message':'Mismatch remains'}]}) as model:
            task=bridge.review_set({}, {'id':'test-product'})
        self.assertEqual(task['status'],'done')
        transmitted=model.call_args.args[2]
        self.assertEqual(transmitted[2],'actual-extra-source')
        self.assertEqual([base64.b64decode(value.split(',',1)[1]) for value in transmitted[3:]],pixels)
        manifest=[{'inputImageNumber':n+4,'slotNumber':n+1,'sourceSha256':hashlib.sha256(raw).hexdigest()} for n,raw in enumerate(pixels)]
        self.assertEqual(model.call_args.args[1]['supplementalImages'],manifest)
        saved=visual.get_project(self.project['id'])['set_qa']
        self.assertEqual(saved['supplementalArtworkReferences'],manifest)
        self.assertFalse(saved['ready'])
        self.assertEqual(saved['issues'][0]['code'],'IDENTITY')

    def test_regeneration_invalidates_previous_set_review(self):
        self.project['set_qa']={'ready':True,'issues':[]};visual.save_project(self.project)
        with patch.object(bridge.threading.Thread,'start'):
            bridge.render({'confirmed':True,'indices':[0],'config':{'model':'gpt-image-2','size':'1:1','resolution':'2K'}},{'id':'test-product'})
        self.assertIsNone(visual.get_project('test')['set_qa'])

    def test_long_generated_prompt_does_not_block_editing_another_field(self):
        p=bridge.native(self.project,[])
        p['images'][1]['render_prompt']='Product identity and scene directions. '*200
        p['images'][1]['headline']='Pocket Detail'
        saved=bridge.persist({'projectId':'test','plan':p},{'id':'test-product'})
        self.assertEqual(visual.get_project(saved['id'])['uiPlan']['images'][1]['headline'],'Pocket Detail')

    def test_native_edit_preserves_unmodified_and_compiles_all_copy(self):
        p=bridge.native(self.project,[]);p['images'][1]['headline']='New Heading';p['images'][1]['callout']='Soft Finish'
        result=bridge.persist({'projectId':'test','plan':p},{'id':'test-product'})
        updated=visual.get_project(result['id'])
        self.assertIn('Soft Finish',visual.compile_prompt(updated,1))
        self.assertEqual(updated['plan']['slots'][1]['headline'],'New Heading')
        self.assertEqual(visual.get_project('test')['plan']['slots'][1]['headline'],'Blue Cotton Shirt')
        with self.assertRaises(ValueError):bridge.persist({'projectId':'test','plan':p},{'id':'test-product'})

    def test_supporting_shot_type_edit_is_versioned_and_preserves_original(self):
        p=bridge.native(self.project,[]);old=p['images'][1]['shot_type'];p['images'][1]['shot_type']='lifestyle' if old!='lifestyle' else 'detail'
        result=bridge.persist({'projectId':'test','plan':p},{'id':'test-product'})
        self.assertEqual(visual.get_project(result['id'])['uiPlan']['images'][1]['shot_type'],p['images'][1]['shot_type'])
        self.assertEqual(bridge.native(visual.get_project('test'),[])['images'][1]['shot_type'],old)

    def test_shot_type_edit_cannot_reclassify_main_or_inject_unknown_type(self):
        for index,value in [(0,'detail'),(1,'skip_checks')]:
            p=bridge.native(self.project,[]);p['images'][index]['shot_type']=value
            with self.assertRaises(ValueError):bridge.persist({'projectId':'test','plan':p},{'id':'test-product'})

    def test_history_restore_is_owned_and_resets_manual_approval(self):
        for rid in ('older','newer'):
            visual.save_run({'id':rid,'projectId':'test','slot':1,'status':'approved','manual':True,'image':'https://example.test/'+rid+'.png','qc':[{'pass':True,'issues':[]}]})
        p=bridge.native(self.project,visual.list_projects('test-product')['runs'])
        p['images'][1]['final_url']=p['images'][1]['versions'][0]['url'];p['images'][1]['human_reviewed']=False
        bridge.persist({'projectId':'test','plan':p},{'id':'test-product'})
        run=visual.list_projects('test-product')['runs'][0]
        self.assertEqual(run['image'],'https://example.test/older.png');self.assertEqual(run['status'],'awaiting_manual')
        p['images'][1]['final_url']='https://evil.test/image'
        with self.assertRaises(ValueError):bridge.persist({'projectId':'test','plan':p},{'id':'test-product'})

    def test_source_contains_license_and_no_runtime_data(self):
        with zipfile.ZipFile(io.BytesIO(bridge.source_archive())) as z:
            names=z.namelist();self.assertIn('LICENSE-AGPL-3.0.txt',names);self.assertIn('visual-ui/VisualStep.tsx',names)
            self.assertFalse(any(n.startswith('data/') or 'node_modules/' in n or n.endswith('.env') for n in names))

    def test_invalid_render_does_not_launch_paid_task(self):
        with patch.object(bridge,'task_new') as task:
            with self.assertRaises(ValueError):bridge.render({'confirmed':True,'indices':[1],'config':{'model':'invalid'}},{'id':'test-product'})
            task.assert_not_called()
