import base64
import copy
import io
import hashlib
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
import visual_studio as studio

def raster_fixture():
    image=Image.new('RGB',(64,64),'#9dc5d9')
    ImageDraw.Draw(image).rectangle((3,3,60,60),fill='blue')
    stream=io.BytesIO()
    image.save(stream,'JPEG')
    return stream.getvalue(),'image/jpeg'

def truth_fixture(size=180):
    raw,_=raster_fixture()
    canvas=Image.new('RGB',(180,180),'white')
    with Image.open(io.BytesIO(raw)) as product:
        canvas.paste(product,(58,58))
    encoded=io.BytesIO()
    canvas.resize((size,size)).save(encoded,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(encoded.getvalue()).decode()


def review_scores(fidelity=100):
    return dict(product_fidelity=fidelity,realism=100,composition=100,typography=100,
                copy_accuracy=100,commercial_readiness=100)


def fixture():
    return {'identity':'Exact blue shirt, two visible buttons; back not shown','palette':['#FFFFFF','#EEEEEE','#223344','#556677','#8899AA'],'lighting':'Soft daylight','typography':'Simple clear sans serif','audience':'Adults','warnings':['Verify size measurements'],'slots':[{'index':i,'question':'What does it show?','evidence':'Visible product reference','composition':'Natural grounded photographic view with right aligned type','headline':'' if i==0 else 'Blue Cotton Shirt','caption':'' if i==0 else 'Easy everyday layering','purpose':'Test purpose'} for i in range(7)]}

def director_fixture():
    layouts=['white_main','human_context','detail_macro','trust_close','poster_hero','scenario_mosaic','spec_grid']
    kinds=['white_main','lifestyle','detail','trust','hero_feature','comparison','specs']
    from storyboard_variety import SCENE_FIELDS
    return {'style':{'palette':'#FFFFFF #EEEEEE #223344 #556677 #8899AA'},'product_lock':fixture()['identity'],
            'images':[{'layout':layout,'shot_type':kind,'product_presence':'hero' if i==0 else 'supporting',
                       'buyer_question':'What does it show?','evidence':'Visible product reference',
                       'scene':'Natural everyday setting','headline':'' if i==0 else 'Blue Cotton Shirt',
                       'subline':'' if i==0 else 'Easy everyday layering',
                       'scene_direction':{key:list(options)[i//2] for key,(_,options) in SCENE_FIELDS.items()}}
                      for i,(layout,kind) in enumerate(zip(layouts,kinds))]}

def identity_fixture():
    return {'category_family':'apparel','object_behavior':'soft_goods','fidelity_anchors':[fixture()['identity']]}

class VisualTests(unittest.TestCase):
    def test_aplus_history_cannot_hide_current_gallery_results(self):
        studio.save_run({'id':'gallery-master','projectId':self.project['id'],'slot':0,'status':'approved'})
        for n in range(40):
            studio.save_project({**self.project,'id':f'aplus-{n}','deliverable':'aplus','created':self.project['created']+n+1})
            for slot in range(5):
                studio.save_run({'id':f'aplus-{n}-{slot}','projectId':f'aplus-{n}','slot':slot,'status':'awaiting_manual'})
        other={**self.project,'id':'other-account-product','productId':'other','created':self.project['created']+100}
        studio.save_project(other)
        studio.save_run({'id':'other-run','projectId':other['id'],'slot':0,'status':'approved'})
        result=studio.list_projects(self.project['productId'])
        ids={r['id'] for r in result['runs']}
        self.assertIn('gallery-master',ids)
        self.assertIn(self.project['id'],{p['id'] for p in result['projects']})
        self.assertNotIn('other-run',ids)

    def test_apparel_aplus_last_module_keeps_real_measurement_table_and_supplier_truth(self):
        import ivyea_pipeline
        supplier='/uploads/'+'b'*32+'.png'
        chart={'sourcePage':'https://detail.1688.com/offer/123.html','units':'cm',
               'columns':['Size','Bust','Length'],'rows':[['S','96','50'],['M','100','51']]}
        reference=self.project['references'][0]
        output=director_fixture()
        output['images']=output['images'][1:6]
        product={'id':'aplus-product','cat':'服装','name':'Cardigan','supplierSizeEvidence':chart,
                 'assets':[{'url':supplier,'source':'供应商图'}]}
        with patch.object(studio,'encode_reference',return_value=truth_fixture()), \
             patch.object(studio,'model_json',side_effect=[identity_fixture(),output]) as model:
            plan=ivyea_pipeline.plan_project({'references':[reference,supplier],'deliverable':'aplus','count':5},product,{})
        last=plan['uiPlan']['images'][-1]
        self.assertTrue(last['size_chart'])
        self.assertEqual(plan['sizeEvidence']['rows'],chart['rows'])
        self.assertEqual(last['product_presence'],'supporting')
        prompt=studio.check_render_prompt(plan,4)
        self.assertIn('Verified measurement table',prompt)
        self.assertIn('"96"',prompt)
        self.assertNotIn('headline large and dominant',prompt)
        self.assertIn('not size letters alone',model.call_args.args[0])

    def test_product_led_result_layout_keeps_product_in_frame(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        project['uiPlan']['images'][1].update(layout='result_showcase',product_presence='hero')
        prompt=studio.compile_prompt(project,1)
        self.assertNotIn('physical product itself stays out of frame',prompt)
        self.assertIn('Layout family: poster_hero',prompt)

    def test_directed_scene_is_not_named_dimension_by_position(self):
        project={'uiPlan':director_fixture(),'plan':fixture()}
        self.assertIn('trust',studio.slot_name(project,3))
        self.assertNotIn('尺寸',studio.slot_name(project,3))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.p=patch.object(studio,'DB',Path(self.temp.name)/'visual.sqlite3');self.p.start()
        self.receipt_path=patch.object(studio.provider.app_paths,'DATA',Path(self.temp.name));self.receipt_path.start()
        self.image_root=patch.object(studio.image_provider,'ROOT',Path(self.temp.name));self.image_root.start()
        self.project=studio.save_project({'id':'test','productId':'test-product','references':['/uploads/'+'a'*32+'.png'],'brief':'','created':1,'plan':studio.validate_plan(fixture()),'confirmed':True,'aiStoryboard':{'version':1,'origin':'workbench_ai_planner','model':'test-planner'}})
        self.options={'id':'test','slot':1,'model':'test-model','autoRepair':True}

    def tearDown(self):
        self.image_root.stop();self.receipt_path.stop();self.p.stop();self.temp.cleanup()

    def revision_fixture(self):
        """Real cached result bytes and the server-native inherited display."""
        p=copy.deepcopy(self.project);p['uiPlan']=director_fixture()
        p['analysis']={'referenceHashes':{p['references'][0]:'verified-source-sha'}}
        p['productFacts']={'material':'Polyester','packageContents':'1 cardigan'}
        cache=Path(self.temp.name)/'studio-results';cache.mkdir(exist_ok=True)
        runs=[];hashes=[]
        for index,image in enumerate(p['uiPlan']['images']):
            rid=f'{index+1:032x}';url=f'https://example.test/expired-{index}.jpg'
            canvas=Image.new('RGB',(64,64),(50+index,80,120));out=io.BytesIO();canvas.save(out,'PNG')
            raw=out.getvalue();digest=hashlib.sha256(raw).hexdigest();hashes.append(digest)
            qc={'pass':True,'issues':[],'technical':{'sha256':digest,'issues':[]}}
            run={'id':rid,'projectId':p['id'],'productId':p['productId'],'slot':index,
                 'status':'awaiting_manual','image':url,'qc':[qc],'selectedJobId':f'job-{index}',
                 'candidates':[{'jobId':f'job-{index}','qc':qc}],'manual':False}
            studio.save_run(run);runs.append(run)
            (cache/(rid+'-'+hashlib.sha256(url.encode()).hexdigest()[:16]+'.image')).write_bytes(raw)
            image.update(_runId=rid,_status=run['status'],final_url='/api/studio/image?runId='+rid,
                         base_url='/api/studio/image?runId='+rid,render_qa={'ready':True},human_reviewed=False)
        p['set_qa']={'ready':True,'issues':[],'imageHashes':hashes,'reviewInput':'numbered_contact_sheet'}
        p['uiPlan']['set_qa']=copy.deepcopy(p['set_qa'])
        studio.save_project(p)
        return p,runs

    def revision_runs(self,p):
        return sorted((r for r in studio.list_projects(p['productId'])['runs'] if r['projectId']==p['id']),key=lambda r:r['slot'])

    def test_confirmation_clones_seven_native_bindings_without_scene_directions(self):
        import studio_bridge
        p,runs=self.revision_fixture()
        # Six inherited cards plus one current own result matches the actual
        # legacy confirmation failure without copying any live business data.
        child={**copy.deepcopy(p),'id':'child','parent':p['id'],'created':2}
        studio.save_project(child)
        own={**runs[5],'id':'f'*32,'projectId':child['id']};studio.save_run(own)
        suffix='-'+hashlib.sha256(own['image'].encode()).hexdigest()[:16]+'.image'
        cache=Path(self.temp.name)/'studio-results'
        (cache/(own['id']+suffix)).write_bytes((cache/(runs[5]['id']+suffix)).read_bytes())
        with patch.object(studio.image_provider,'api') as api,patch('studio_bridge.build_opener') as network:
            saved=studio.update({'id':child['id'],'plan':child['plan'],'confirmed':True})
            copied=self.revision_runs(saved)
            self.assertEqual(len(copied),7)
            for index,run in enumerate(copied):
                origin=own if index==5 else runs[index]
                self.assertNotEqual(run['id'],origin['id'])
                self.assertEqual(run['inheritedFrom']['runId'],origin['id'])
                self.assertEqual(run['status'],origin['status']);self.assertFalse(run['manual'])
                self.assertEqual(run['qc'],origin['qc']);self.assertEqual(run['candidates'],origin['candidates'])
                self.assertEqual(hashlib.sha256(studio_bridge.result_image(run['id'])[0]).hexdigest(),p['set_qa']['imageHashes'][index])
            api.assert_not_called();network.assert_not_called()
        self.assertEqual(saved['set_qa'],p['set_qa'])
        self.assertFalse(saved['revisionRetention']['requiresSetReview'])
        self.assertEqual(studio.get_project(p['id']),p)
        self.assertEqual(studio.get_run(runs[0]['id']),runs[0])

    def test_unchanged_confirmation_preserves_exact_hash_bound_set_review(self):
        import studio_bridge
        p,runs=self.revision_fixture()
        saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
        self.assertEqual(saved['set_qa'],p['set_qa'])
        self.assertEqual(saved['uiPlan']['set_qa'],p['set_qa'])
        self.assertTrue(saved['revisionRetention']['setQaPreserved'])
        self.assertFalse(saved['revisionRetention']['requiresSetReview'])
        self.assertEqual(saved['uiPlan']['style'],p['uiPlan']['style'])
        copied=self.revision_runs(saved)
        self.assertEqual([i['_runId'] for i in studio_bridge.native(saved,copied)['images']],[r['id'] for r in copied])

    def test_inherited_binding_survives_project_list_pruning(self):
        p,runs=self.revision_fixture()
        current=p
        for index in range(35):
            current={**copy.deepcopy(current),'id':f'child-{index}','parent':current['id'],'created':index+2}
            studio.save_project(current)
        self.assertNotIn(p['id'],{project['id'] for project in studio.list_projects(p['productId'])['projects']})
        saved=studio.update({'id':current['id'],'plan':current['plan'],'confirmed':True})
        self.assertEqual(len(self.revision_runs(saved)),7)
        self.assertEqual(saved['set_qa'],p['set_qa'])

    def test_inherited_display_does_not_change_when_ancestor_has_a_newer_run(self):
        p,runs=self.revision_fixture()
        child={**copy.deepcopy(p),'id':'child-displaying-original','parent':p['id'],'created':2};studio.save_project(child)
        newer={**copy.deepcopy(runs[0]),'id':'newer-ancestor-run','image':'https://example.test/new.jpg'}
        studio.save_run(newer)
        saved=studio.update({'id':child['id'],'plan':child['plan'],'confirmed':True})
        self.assertEqual(self.revision_runs(saved)[0]['inheritedFrom']['runId'],runs[0]['id'])
        self.assertEqual(saved['set_qa'],p['set_qa'])
        self.assertEqual(studio.get_run(newer['id']),newer)

    def test_changed_card_keeps_history_and_only_clones_other_six(self):
        p,runs=self.revision_fixture();plan=copy.deepcopy(p['plan'])
        plan['slots'][5]['composition']='Tight crop showing the wavy front hem'
        saved=studio.update({'id':p['id'],'plan':plan,'confirmed':True})
        self.assertEqual([r['slot'] for r in self.revision_runs(saved)],[0,1,2,3,4,6])
        image=saved['uiPlan']['images'][5]
        self.assertEqual(image['versions'][-1]['_runId'],runs[5]['id'])
        self.assertTrue(all(key not in image for key in ('final_url','base_url','_runId','render_qa','human_reviewed')))
        self.assertIsNone(saved['set_qa'])

    def test_shared_visual_or_fact_change_in_ancestor_blocks_inheritance(self):
        for change in ('style','references','referenceHashes','productFacts','sizeEvidence','crop'):
            with self.subTest(change=change):
                p,runs=self.revision_fixture()
                child={**copy.deepcopy(p),'id':'changed-'+change,'parent':p['id'],'created':2}
                if change=='style':child['uiPlan']['style']['lighting']='Different light'
                elif change=='references':child['references']=list(reversed([*p['references'],'another']))
                elif change=='referenceHashes':child['analysis']['referenceHashes'][p['references'][0]]='changed'
                elif change=='productFacts':child['productFacts']['material']='Different material'
                elif change=='sizeEvidence':child['sizeEvidence']={'rows':[['S','110']]}
                else:child['uiPlan']['images'][1]['source_crop']=[0,0,0.5,0.5]
                studio.save_project(child)
                saved=studio.update({'id':child['id'],'plan':child['plan'],'confirmed':True})
                slots=[r['slot'] for r in self.revision_runs(saved)]
                self.assertEqual(slots,[0,2,3,4,5,6] if change=='crop' else [])
                self.assertIsNone(saved['set_qa'])

    def test_changed_then_restored_ancestor_card_does_not_revive_old_render(self):
        p,runs=self.revision_fixture()
        middle={**copy.deepcopy(p),'id':'middle','parent':p['id'],'created':2}
        middle['uiPlan']['images'][2]['headline']='A different card';studio.save_project(middle)
        current={**copy.deepcopy(p),'id':'restored','parent':middle['id'],'created':3};studio.save_project(current)
        saved=studio.update({'id':current['id'],'plan':current['plan'],'confirmed':True})
        self.assertEqual([r['slot'] for r in self.revision_runs(saved)],[0,1,3,4,5,6])

    def test_unknown_active_and_unfinished_latest_runs_never_revive_cached_approved_image(self):
        for status in ('submitting','generating','reviewing','repairing','submit_unknown','interrupted','failed','review_error'):
            with self.subTest(status=status):
                p,runs=self.revision_fixture()
                newer={**runs[1],'id':'latest-'+status,'status':status};newer.pop('image')
                studio.save_run(newer)
                saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
                self.assertNotIn(1,[r['slot'] for r in self.revision_runs(saved)])
                self.assertNotIn('_runId',saved['uiPlan']['images'][1]);self.assertIsNone(saved['set_qa'])

    def test_each_allowed_terminal_state_is_retained_without_changing_approval(self):
        p,runs=self.revision_fixture()
        for index,status in enumerate(('approved','awaiting_manual','needs_revision')):
            runs[index].update(status=status,manual=status=='approved');studio.save_run(runs[index])
        saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
        for original,copied in zip(runs,self.revision_runs(saved)):
            self.assertEqual((copied['status'],copied['manual']),(original['status'],original['manual']))
        self.assertIsNone(saved['set_qa'])

    def test_failed_set_review_is_retained_exactly_and_manual_review_is_not_invented(self):
        p,runs=self.revision_fixture()
        p['set_qa'].update(ready=False,issues=[{'code':'REPETITIVE_COMPOSITION','severity':'error','message':'Slots 1 and 6'}])
        runs[0]['status']='needs_revision';studio.save_run(runs[0]);studio.save_project(p)
        saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
        self.assertEqual(saved['set_qa'],p['set_qa']);self.assertFalse(saved['set_qa']['ready'])
        p,runs=self.revision_fixture();p['set_qa']['semanticReview']='manual_confirmed';studio.save_project(p)
        saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
        self.assertIsNone(saved['set_qa']);self.assertTrue(all(not r['manual'] for r in self.revision_runs(saved)))
        p,runs=self.revision_fixture();runs[0]['candidates'][0]['qc']['pass']=False;studio.save_run(runs[0])
        saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
        self.assertIsNone(saved['set_qa'])
        self.assertEqual(len(self.revision_runs(saved)),7)

    def test_forged_foreign_wrong_slot_and_invalid_ancestor_bindings_are_not_cloned(self):
        for defect in ('foreign','slot','url','cycle','missing','deliverable'):
            with self.subTest(defect=defect):
                p,runs=self.revision_fixture()
                child={**copy.deepcopy(p),'id':'invalid-'+defect,'parent':p['id'],'created':2}
                if defect=='foreign':p['productId']='other';studio.save_project(p)
                elif defect=='slot':runs[0]['slot']=1;studio.save_run(runs[0])
                elif defect=='url':child['uiPlan']['images'][0]['final_url']='/api/studio/image?runId='+runs[1]['id']
                elif defect=='cycle':child['parent']=child['id']
                elif defect=='missing':child['parent']='not-present'
                else:p['deliverable']='aplus';studio.save_project(p)
                studio.save_project(child)
                saved=studio.update({'id':child['id'],'plan':child['plan'],'confirmed':True})
                self.assertNotIn(0,[r['slot'] for r in self.revision_runs(saved)])
                self.assertNotIn(runs[0]['id'],[version.get('_runId') for version in saved['uiPlan']['images'][0].get('versions',[])])
                self.assertIsNone(saved['set_qa'])

    def test_client_run_ids_are_ignored_and_only_latest_displayed_result_is_cloned(self):
        p,runs=self.revision_fixture()
        request=copy.deepcopy(p['plan']);request['_runId']='untrusted';request['slots'][0]['_runId']=runs[1]['id']
        old={**runs[0],'id':'old-result'};studio.save_run(old);studio.save_run(runs[0])
        saved=studio.update({'id':p['id'],'plan':request,'confirmed':True,'_runId':'untrusted'})
        copied=self.revision_runs(saved)
        self.assertEqual(len(copied),7);self.assertEqual(copied[0]['inheritedFrom']['runId'],runs[0]['id'])

    def test_set_review_clears_for_missing_changed_or_reordered_real_bytes(self):
        for defect in ('missing','changed','reordered','reviewHash'):
            with self.subTest(defect=defect):
                p,runs=self.revision_fixture();run=runs[0]
                path=Path(self.temp.name)/'studio-results'/(run['id']+'-'+hashlib.sha256(run['image'].encode()).hexdigest()[:16]+'.image')
                if defect=='missing':path.unlink()
                elif defect=='changed':path.write_bytes(b'changed actual bytes')
                elif defect=='reordered':p['set_qa']['imageHashes'].reverse();studio.save_project(p)
                else:run['candidates'][0]['qc']['technical']['sha256']='incorrect';studio.save_run(run)
                saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
                self.assertEqual(len(self.revision_runs(saved)),7 if defect=='reordered' else 6)
                if defect!='reordered':self.assertNotIn('_runId',saved['uiPlan']['images'][0])
                self.assertIsNone(saved['set_qa']);self.assertTrue(saved['revisionRetention']['requiresSetReview'])

    def test_local_result_clone_keeps_same_product_source_bytes(self):
        import studio_bridge
        p,runs=self.revision_fixture();run=runs[0]
        raw,_=raster_fixture();digest=hashlib.sha256(raw).hexdigest()
        run['image']='local:'+run['id'];run['qc'][-1]['technical']['sha256']=digest
        run['candidates'][0]['qc']['technical']['sha256']=digest;studio.save_run(run)
        (Path(self.temp.name)/'studio-results'/(run['id']+'.image')).write_bytes(raw)
        p['set_qa']['imageHashes'][0]=digest;studio.save_project(p)
        saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True});copied=self.revision_runs(saved)[0]
        self.assertEqual(copied['image'],run['image'])
        self.assertEqual(studio_bridge.result_image(copied['id'])[0],raw)
        self.assertEqual(saved['set_qa'],p['set_qa'])
        foreign={**run,'id':'e'*32,'productId':'other'};studio.save_run(foreign)
        run['image']='local:'+foreign['id'];studio.save_run(run)
        rejected=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
        self.assertNotIn(0,[r['slot'] for r in self.revision_runs(rejected)])

    def test_confirm_retains_approved_account_uploads_without_a_studio_image_cache(self):
        import studio_bridge
        p,runs=self.revision_fixture();uploads=Path(self.temp.name)/'uploads';uploads.mkdir()
        originals={}
        for index in (3,5,6):
            run=runs[index];cache=Path(self.temp.name)/'studio-results'
            old=cache/(run['id']+'-'+hashlib.sha256(run['image'].encode()).hexdigest()[:16]+'.image')
            raw=old.read_bytes();old.unlink();url='/uploads/'+hashlib.sha256(raw).hexdigest()[:32]+'.png'
            (uploads/url.rsplit('/',1)[-1]).write_bytes(raw);originals[index]=raw
            run.update(image=url,status='approved',manual=True,approvedAt=1);studio.save_run(run)
            self.assertFalse((cache/(run['id']+'-'+hashlib.sha256(url.encode()).hexdigest()[:16]+'.image')).exists())
        with patch.object(studio.image_provider,'api') as api,patch('studio_bridge.build_opener') as network, \
             patch.object(studio.image_provider,'local_image',wraps=studio.image_provider.local_image) as local:
            saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
            copied=self.revision_runs(saved)
            self.assertEqual(len(copied),7);self.assertEqual(local.call_count,3)
            for index,raw in originals.items():
                self.assertEqual(copied[index]['status'],'approved');self.assertTrue(copied[index]['manual'])
                self.assertEqual(copied[index]['inheritedFrom']['runId'],runs[index]['id'])
                self.assertEqual(studio_bridge.result_image(copied[index]['id'])[0],raw)
                self.assertEqual(studio.get_run(runs[index]['id']),runs[index])
            api.assert_not_called();network.assert_not_called()
        self.assertEqual(saved['set_qa'],p['set_qa']);self.assertFalse(saved['revisionRetention']['requiresSetReview'])

    def test_uncached_account_upload_still_rejects_wrong_bytes_missing_or_unsafe_path(self):
        for defect in ('changed','missing','unsafe'):
            with self.subTest(defect=defect):
                p,runs=self.revision_fixture();run=runs[3]
                run['image']='/uploads/'+('a'*32)+'.png'
                uploads=Path(self.temp.name)/'uploads';uploads.mkdir(exist_ok=True)
                path=uploads/(('a'*32)+'.png')
                if path.exists():path.unlink()
                if defect=='changed':path.write_bytes(raster_fixture()[0])
                elif defect=='unsafe':run['image']='/uploads/../outside.png'
                studio.save_run(run)
                with patch.object(studio.image_provider,'api') as api,patch('studio_bridge.build_opener') as network:
                    saved=studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
                    api.assert_not_called();network.assert_not_called()
                self.assertNotIn(3,[r['slot'] for r in self.revision_runs(saved)])
                self.assertNotIn('_runId',saved['uiPlan']['images'][3]);self.assertIsNone(saved['set_qa'])

    def test_revision_and_clones_roll_back_together_when_insert_fails(self):
        p,runs=self.revision_fixture()
        with closing(studio.db()) as c,c:
            before=c.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
            c.execute("CREATE TRIGGER fail_revision BEFORE INSERT ON runs WHEN json_extract(NEW.body,'$.inheritedFrom') IS NOT NULL AND json_extract(NEW.body,'$.slot')=1 BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaisesRegex(Exception,'fixture failure'):
            studio.update({'id':p['id'],'plan':p['plan'],'confirmed':True})
        with closing(studio.db()) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM projects').fetchone()[0],before)
        self.assertEqual(studio.get_project(p['id']),p)

    def test_unplanned_and_direct_requests_stop_before_submission(self):
        provider = studio.image_provider
        with patch.object(provider, 'begin_submission') as reserve:
            with self.assertRaises(provider.StoryboardRequired):
                provider.submit({'productId':'test-product','storyboardProjectId':'test','storyboardSlot':1})
            with self.assertRaises(provider.StoryboardRequired):
                provider.storyboard_submission({'productId':'other-product'}, 'test', 1)
            legacy = {**self.project, 'aiStoryboard': {'planner':'ai'}}
            studio.save_project(legacy)
            with self.assertRaises(provider.StoryboardRequired):
                studio.generate(self.options)
        reserve.assert_not_called()
        self.assertEqual(studio.list_projects('test-product')['runs'], [])

    def test_compiler_has_exact_artwork_copy_and_identity(self):
        main=studio.compile_prompt(self.project,0);secondary=studio.compile_prompt(self.project,1)
        for prompt in (main,secondary):
            self.assertTrue(prompt.startswith('[PRODUCT PRESENCE] REFERENCE IMAGE 1'))
        self.assertIn('Pure #FFFFFF',main)
        self.assertNotIn('Blue Cotton Shirt',main)
        self.assertIn('FINAL ARTWORK COPY',secondary)
        self.assertIn('exactly once',secondary)
        self.assertIn('Blue Cotton Shirt',secondary)
        self.assertIn(self.project['plan']['identity'],secondary)

    def test_directed_gallery_keeps_type_zone_and_full_bleed_without_overriding_crop(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        card=project['uiPlan']['images'][2]
        card.update(camera_direction='Tight crop of both collar edges',text_on_image=True,
                    text_zone='bottom-right',layout_style='minimal')
        prompt=studio.check_render_prompt(project,2)
        self.assertIn('Tight crop of both collar edges',prompt)
        self.assertIn('bottom-right area',prompt)
        self.assertIn('without a title box',prompt)
        self.assertIn('Fill all four edges',prompt)
        self.assertNotIn('whole product is visible and never cropped',prompt)

    def test_updated_card_takes_priority_over_the_original_set_brief(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        project['uiPlan']['creative_brief']='All modules show a full-body wearer with a right-hand title.'
        card=project['uiPlan']['images'][2]
        card.update(camera_direction='Tight ribbed cuff crop',text_zone='top-left',layout_style='minimal',text_on_image=True)
        prompt=studio.check_render_prompt(project,2)
        self.assertIn('Tight ribbed cuff crop',prompt)
        self.assertIn('top-left area',prompt)
        self.assertIn('do not replace them with directions from this context',prompt)
        self.assertNotIn('Highest-priority creative requirement',prompt)

    def test_white_bands_on_secondary_trigger_only_one_repair_with_original_reference(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        studio.save_project(project)
        image=Image.new('RGB',(160,160),'white')
        ImageDraw.Draw(image).rectangle((0,25,159,134),fill='#898568')
        stream=io.BytesIO()
        image.save(stream,'PNG')
        with patch.object(studio.image_provider,'submit',side_effect=[{'id':'original'},{'id':'repair'}]) as submit, \
             patch.object(studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/image.png']}), \
             patch('studio_bridge.result_image',return_value=(stream.getvalue(),'image/png')):
            run=studio.generate(self.options)
            studio.advance(run['id'])
            studio.advance(run['id'])
        result=studio.get_run(run['id'])
        self.assertEqual(result['status'],'needs_revision')
        self.assertEqual(result['qc'][0]['technical']['issues'][-1]['code'],'WHITE_PADDING')
        self.assertEqual(submit.call_count,2)
        self.assertEqual(submit.call_args_list[0].args[0]['references'],submit.call_args_list[1].args[0]['references'])

    def test_square_provider_result_is_reviewed_at_the_delivery_size(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        studio.save_project(project)
        with patch.object(studio.image_provider,'submit',return_value={'id':'original'}), \
             patch.object(studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/image.png']}), \
             patch('studio_bridge.result_image',return_value=raster_fixture()), \
             patch.object(studio.image_provider.custom_images,'cache_image',return_value={'url':'/uploads/normalised.png'}) as cache, \
             patch.object(studio,'review',return_value={'pass':True,'issues':[]}) as review:
            run=studio.generate({**self.options,'slot':0})
            studio.advance(run['id'])
        result=studio.get_run(run['id'])
        self.assertEqual(result['image'],'/uploads/normalised.png')
        self.assertEqual(result['qc'][0]['technical']['providerOutput']['dimensions'],[64,64])
        self.assertEqual(result['qc'][0]['technical']['dimensions'],[1600,1600])
        with Image.open(io.BytesIO(cache.call_args.args[0])) as image:
            self.assertEqual(image.size,(1600,1600))
        self.assertTrue(review.call_args.args[2].startswith('data:image/png;base64,'))

    def test_square_secondary_uses_original_api_pixels_before_legacy_white_padding(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        studio.save_project(project)
        image=Image.new('RGB',(120,160),'#898568')
        ImageDraw.Draw(image).rectangle((20,30,100,126),fill='#415337')
        original=io.BytesIO()
        image.save(original,'PNG')
        padded=Image.new('RGB',(160,160),'white')
        padded.paste(image,(20,0))
        display=io.BytesIO()
        padded.save(display,'PNG')
        result_url='https://example.test/padded.png'
        original_url='/uploads/'+'f'*32+'.png'
        job={'status':'completed','images':[result_url],'assets':[{
            'url':result_url,'processing':{'method':'contain_lanczos'},'sourceAsset':{'url':original_url},
        }]}
        with patch.object(studio.image_provider,'submit',return_value={'id':'original'}), \
             patch.object(studio.image_provider,'poll',return_value=job), \
             patch.object(studio.image_provider,'local_image',return_value=original.getvalue()) as load, \
             patch('studio_bridge.result_image',return_value=(display.getvalue(),'image/png')), \
             patch.object(studio.image_provider.custom_images,'cache_image',return_value={'url':'/uploads/normalised.png'}) as cache, \
             patch.object(studio,'review',return_value={'pass':True,'issues':[]}):
            run=studio.generate(self.options)
            studio.advance(run['id'])
        load.assert_called_once_with(original_url)
        result=studio.get_run(run['id'])
        self.assertEqual(result['status'],'awaiting_manual')
        self.assertEqual(result['qc'][0]['technical']['providerOutput']['dimensions'],[120,160])
        with Image.open(io.BytesIO(cache.call_args.args[0])) as image:
            self.assertEqual(image.getpixel((0,0)),(137,133,104))

    def test_size_card_compiles_and_reviews_a_single_structured_table(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        chart={'columns':['Size','Bust','Shoulder','Length'],'rows':[['S','112','46','63']],
               'units':'cm','sourcePage':'https://example.test/chart'}
        project['sizeEvidence']=chart
        project['uiPlan']['images'][6].update(size_chart=True,text_on_image=True,headline='Size Guide',
                                             subline='',supporting_text='Size | Bust | Shoulder | Length')
        project['references']=['white','supplier']
        project['analysis']={'supplierReferences':['supplier'],'referenceViews':[
            {'url':'white','identity':'primary','angle':'front-on','visible':['Front']},
            {'url':'supplier','identity':'same_sku','angle':'front-on','visible':['Worn front']},
        ]}
        self.assertEqual(studio.slot_references(project,0),['white'])
        self.assertEqual(studio.slot_references(project,1),['supplier'])
        self.assertEqual(studio.slot_references(project,6),['supplier'])
        prompt=studio.check_render_prompt(project,6)
        self.assertIn('single header row',prompt)
        self.assertNotIn('Size | Bust',prompt)
        observed={key:chart[key] for key in ('columns','rows','units')}
        answer=dict(scores=review_scores(),identityPass=True,textPass=True,readablePass=True,technicalPass=True,
                    observedText='Size Guide Size Bust Shoulder Length cm S 112 46 63',issues=[],
                    observedSizeChart={**observed,'singleHeader':True})
        with patch.object(studio,'encode_reference',return_value='supplier-image'), \
             patch.object(studio,'model_json',side_effect=[answer,
                 {**answer,'observedSizeChart':{**observed,'singleHeader':False}},
                 {**answer,'observedSizeChart':observed,'singleHeader':True},
                 {**answer,'singleHeader':False},
                 {**answer,'observedSizeChart':{**observed,'rows':[['S','113','46','63']]},'singleHeader':True}]):
            self.assertTrue(studio.review(project,6,'rendered-chart')['pass'])
            self.assertFalse(studio.review(project,6,'rendered-chart')['pass'])
            self.assertTrue(studio.review(project,6,'rendered-chart')['pass'])
            self.assertFalse(studio.review(project,6,'rendered-chart')['pass'])
            self.assertFalse(studio.review(project,6,'rendered-chart')['pass'])

    def test_worn_garment_occlusion_overrides_label_visibility(self):
        prompt=studio.compile_prompt(self.project,1)
        self.assertIn('[WEARABLE PHYSICS]',prompt)
        self.assertIn('physical occlusion overrides',prompt)
        self.assertIn('Skin must be free',prompt)
        self.assertIn('identityPass=false',studio.QC_INSTRUCTION)

    def test_new_apparel_policy_checks_actual_pixels_in_addition_to_planner_labels(self):
        project=copy.deepcopy(self.project)
        project.update(uiPlan=director_fixture(),galleryDirection='apparel_v2_no_filler')
        project['uiPlan']['images'][3].update(headline='',subline='',text_on_image=False)
        answer=dict(scores=review_scores(),identityPass=True,textPass=True,readablePass=True,
                    technicalPass=False,observedText='',issues=['Quantity poster contains no useful garment view'])
        def judge(instruction,context,images,**kwargs):
            self.assertIn('inspect actual output pixels',instruction)
            self.assertIn('token tiny',instruction)
            return answer
        with patch.object(studio,'encode_reference',return_value='verified-source'), \
             patch.object(studio,'model_json',side_effect=judge):
            result=studio.review(project,3,'actual-output')
        self.assertFalse(result['pass'])
        self.assertIn('Quantity poster',result['issues'][0])

    def test_recompile_removes_stale_canonical_instructions(self):
        project=copy.deepcopy(self.project)
        project['plan']['slots'][1]['composition']=(
            'New composition [PRODUCT PRESENCE] obsolete instruction [/PRODUCT PRESENCE] '
            '[WEARABLE PHYSICS] obsolete physics [/WEARABLE PHYSICS] '
            '[PHYSICAL INTEGRITY] obsolete physical integrity [/PHYSICAL INTEGRITY]')
        prompt=studio.compile_prompt(project,1)
        self.assertNotIn('obsolete instruction',prompt)
        self.assertNotIn('obsolete physics',prompt)
        self.assertNotIn('obsolete physical integrity',prompt)
        self.assertEqual(prompt.count('[PRODUCT PRESENCE]'),1)
        self.assertEqual(prompt.count('[WEARABLE PHYSICS]'),1)
        self.assertIn('New composition',prompt)

    def test_legacy_storyboard_edit_reaches_the_render_request(self):
        self.project['uiPlan']=director_fixture()
        self.project['uiPlan']['images'][1].update(camera_direction='Old full-length camera direction')
        studio.save_project(self.project)
        edited=copy.deepcopy(self.project['plan'])
        edited['slots'][1].update(composition='New tight framing of the folded collar',headline='Folded Knit Collar',caption='')
        revision=studio.update({'id':'test','plan':edited,'confirmed':True})
        with patch.object(studio.image_provider,'submit',return_value={'id':'job'}) as submit:
            studio.generate({**self.options,'id':revision['id']})
        prompt=submit.call_args.args[0]['prompt']
        self.assertIn('New tight framing',prompt)
        self.assertIn('Folded Knit Collar',prompt)
        self.assertNotIn('Old full-length camera direction',prompt)
        self.assertNotIn('Blue Cotton Shirt',prompt)
        self.assertIn('Old full-length camera direction',studio.compile_prompt(studio.get_project('test'),1))

    def test_invalid_main_text_and_missing_palette_rejected(self):
        bad=fixture();bad['slots'][0]['headline']='New'
        with self.assertRaises(ValueError):studio.validate_plan(bad)
        bad=fixture();bad['palette']=['red']
        with self.assertRaises(ValueError):studio.validate_plan(bad)

    def test_vision_uses_primary_image_and_no_invented_fallback(self):
        proposal=director_fixture()
        # The primary-vision regression uses the current user-requested seven
        # slots. Other fixture consumers retain their original historical sets.
        for index in (1,2):proposal['images'][index].update(layout='detail_macro',shot_type='detail')
        for index in (3,4,5):proposal['images'][index].update(layout='human_context',shot_type='lifestyle')
        with patch.object(studio,'encode_reference',return_value=truth_fixture()),patch.object(studio,'model_json',side_effect=[identity_fixture(),proposal]) as model:
            result=studio.plan({'references':['primary','detail'],'brief':'Clean','visual_tone':'editorial'}, {'id':'new','name':'Shirt','market':'UK'}, {'title':'Shirt'})
        self.assertFalse(result['confirmed'])
        self.assertEqual(model.call_args_list[0].args[2],[truth_fixture()]*2)
        # The director now receives the real product AND each original template.
        self.assertEqual(len(model.call_args_list[1].args[2]),1+len(result['analysis']['layoutTemplates']))
        self.assertTrue(all(row['originalSha256'] and row['promptSha256'] for row in result['analysis']['layoutTemplates']))
        self.assertEqual(result['engine']['version'],5)
        self.assertFalse(result['apparelOrchestration']['formalSizeChartGateBypassed'])
        self.assertEqual(result['productionMode'],'ai_master')
        provider = studio.image_provider
        with self.assertRaises(provider.StoryboardRequired):
            provider.storyboard_submission({'productId':'new'}, result['id'], 0)
        confirmed = studio.update({'id':result['id'],'plan':result['plan'],'confirmed':True})
        self.assertEqual(provider.storyboard_submission({'productId':'new'}, confirmed['id'], 0),
                         {'storyboardProjectId':confirmed['id'],'storyboardSlot':0})
        self.assertIn('AI MASTER PRODUCTION',model.call_args_list[1].args[0])
        self.assertIn('Tone requested: editorial',model.call_args_list[1].args[0])
        self.assertEqual(result['uiPlan']['visual_tone'],'editorial')
        self.assertIn('USER-REQUESTED SEVEN-IMAGE CONTRACT',model.call_args_list[1].args[0])
        self.assertNotIn('PRODUCTION ECONOMY:',model.call_args_list[1].args[0])
        with patch.object(studio,'encode_reference',side_effect=ValueError('bad reference')):
            with self.assertRaises(ValueError):studio.plan({'references':['bad']},{'id':'new'}, {})

    def test_planned_scene_uses_only_its_verified_product_photo_through_repair(self):
        import studio_bridge
        proposal=director_fixture()
        proposal['images'][5]['layout']='poster_hero'
        proposal['images'][1]['scene_direction']['angle']='front-on'
        identity={**identity_fixture(),'reference_views':[
            {'index':0,'identity_match':'primary','angle':'three-quarter','visible':['Side buttons']},
            {'index':1,'identity_match':'different_sku','angle':'front-on','visible':['Wrong variant']},
            {'index':2,'identity_match':'same_sku','angle':'front-on','visible':['Square front placket'],
             'url':'https://untrusted.test/overridden.png'},
        ]}
        refs=['primary','different','verified']
        stages=[]
        with patch.object(studio,'encode_reference',return_value=truth_fixture()),patch.object(
            studio,'model_json',side_effect=[identity,proposal]
        ) as model:
            p=studio.plan({'references':refs}, {'id':'pouch','name':'Pouch'}, {},
                          lambda stage, *_: stages.append(stage))
        self.assertEqual(stages,['white','identity','templates','plan','compile'])
        planner_instruction=model.call_args.args[0]
        self.assertIn('Square front placket',planner_instruction)
        self.assertNotIn('Wrong variant',planner_instruction)
        card=studio_bridge.native(p,[])['images'][1]
        self.assertEqual(card['product_source_url'],'verified')
        p['confirmed']=True
        studio.save_project(p)
        failed={'pass':False,'issues':['Incorrect crop']}
        with patch.object(studio.image_provider,'submit',side_effect=[{'id':'job1'},{'id':'job2'}]) as submit,patch.object(
            studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/art.png'],
                                                       'referenceSha256':['recorded-hash']}
        ),patch.object(studio,'review',return_value=failed) as review,patch(
            'studio_bridge.result_image',return_value=raster_fixture()
        ):
            run=studio.generate({**self.options,'id':p['id'],'slot':1,'autoRepair':True})
            studio.advance(run['id'])
        first, retry=[call.args[0] for call in submit.call_args_list]
        self.assertEqual(first['references'][0],'verified')
        self.assertEqual(len(first['references']),2)
        self.assertEqual(first['references'][1],p['uiPlan']['images'][1]['template_url'])
        self.assertNotIn('layout_blueprint',p['uiPlan']['images'][1])
        official=p['uiPlan']['images'][1]['official_template']
        self.assertEqual(official['url'],first['references'][1])
        self.assertIn(official['prompt'],first['prompt'])
        self.assertNotIn('Abstract coloured rectangles',first['prompt'])
        self.assertEqual(first['expectedProductReferenceSha256'],p['analysis']['referenceHashes']['verified'])
        self.assertEqual(retry['references'],first['references'])
        self.assertEqual(retry['expectedReferenceSha256'],['recorded-hash'])
        self.assertEqual(review.call_args.kwargs['submitted_references'],first['references'])
        self.assertTrue(first['prompt'].startswith('[PRODUCT PRESENCE]'))
        self.assertEqual(first['prompt'].count('[SOURCE EVIDENCE]'),1)
        self.assertIn('Square front placket',first['prompt'])
        self.assertIn('camera front-on',first['prompt'])

    def test_missing_scene_angle_blocks_submission_and_allows_storyboard_edit(self):
        import studio_bridge
        from ivyea_pipeline import normalize_reference_views
        p=self.project
        p['uiPlan']=director_fixture()
        p['references']=['primary','different']
        p['uiPlan']['images'][1]['scene_direction']['angle']='front-on'
        p['uiPlan']['images'][1]['template_url']='https://example.test/competing-front.png'
        p['analysis']={'referenceViews':normalize_reference_views([
            {'index':0,'angle':'three-quarter','visible':['Side buttons']},
            {'index':1,'identity_match':'different_sku','angle':'front-on','visible':['Wrong variant']},
        ],p['references'])}
        studio.save_project(p)
        with patch.object(studio.image_provider,'submit') as submit:
            with self.assertRaisesRegex(ValueError,'缺少可核实的同款正面实拍'):
                studio.generate({**self.options,'slot':1})
        submit.assert_not_called()
        self.assertEqual(studio.list_projects(p['productId'])['runs'],[])
        view=studio_bridge.native(p,[])
        self.assertFalse(view['quality']['ready'])
        self.assertIn('缺少可核实',view['images'][1]['sourceIssue'])
        self.assertEqual(studio.slot_references(p,0),['primary'])
        view['images'][1]['headline']='A revised headline'
        saved=studio_bridge.persist({'projectId':p['id'],'plan':view},{'id':p['productId']})
        self.assertIn('sourceIssue',studio_bridge.native(studio.get_project(saved['id']),[])['images'][1])
        previous=studio.get_project(saved['id'])
        for slot in (0,1):
            raw,_=raster_fixture();url='https://example.test/verified-'+str(slot)+'.png';rid='original-'+str(slot)
            cache=Path(self.temp.name)/'studio-results';cache.mkdir(exist_ok=True)
            (cache/(rid+'-'+hashlib.sha256(url.encode()).hexdigest()[:16]+'.image')).write_bytes(raw)
            studio.save_run({'id':'original-'+str(slot),'projectId':previous['id'],'productId':p['productId'],
                             'slot':slot,'status':'approved','image':url,
                             'qc':[{'pass':True,'issues':[],'technical':{'sha256':hashlib.sha256(raw).hexdigest()}}]})
        direction={**previous['uiPlan']['images'][1]['scene_direction'],'angle':'three-quarter'}
        revised=studio.update({'id':previous['id'],'plan':previous['plan'],'confirmed':True,
                               'sceneDirections':{'1':direction}})
        self.assertEqual(studio.slot_references(revised,1),['primary','https://example.test/competing-front.png'])
        runs=studio.list_projects(p['productId'])['runs']
        self.assertEqual([r['slot'] for r in runs if r['projectId']==revised['id']],[0])

    def test_changed_source_bytes_are_rejected_before_an_image_api_call(self):
        provider=studio.image_provider
        ref='https://example.test/truth.png'
        p={**self.project,'references':[ref],'analysis':{'referenceHashes':{ref:'original-hash'}}}
        studio.save_project(p)
        with patch.object(provider,'active_provider',return_value='apimart'),patch.object(
            provider,'remote_reference',return_value=(b'changed source bytes','image/png')
        ),patch.object(provider,'api') as api:
            with self.assertRaisesRegex(provider.ReferenceChanged,'商品实拍内容已变化'):
                studio.generate({**self.options,'model':provider.MODELS[0]})
        api.assert_not_called()
        self.assertEqual(studio.list_projects(p['productId'])['runs'][0]['status'],'failed')

    def test_image_analysis_uses_vision_provider_not_text_provider(self):
        import base64
        import io
        from PIL import Image
        raw=io.BytesIO();Image.new('RGB',(16,16),'red').save(raw,'WEBP')
        reference='data:image/webp;base64,'+base64.b64encode(raw.getvalue()).decode()
        response={'choices':[{'finish_reason':'stop','message':{'content':'{"observed":true}'}}]}
        with patch.object(studio,'proxy_vision_settings',return_value=None),patch.object(studio.image_provider,'api',return_value=response) as vision,patch.object(studio.provider,'text_completion') as text:
            result=studio.model_json('Inspect',{},[reference])
        self.assertTrue(result['observed']);text.assert_not_called()
        body=vision.call_args.args[1]
        self.assertEqual(body['model'],'gemini-3-flash-preview')
        self.assertFalse(body['stream'])
        self.assertEqual(body['messages'][1]['content'][1]['type'],'image_url')
        encoded=body['messages'][1]['content'][1]['image_url']['url']
        self.assertTrue(encoded.startswith('data:image/jpeg;base64,'))
        decoded=Image.open(io.BytesIO(base64.b64decode(encoded.split(',',1)[1])))
        self.assertEqual(decoded.size,(16,16))
        self.assertGreater(decoded.getpixel((8,8))[0],200)

    def test_planning_retains_fact_snapshot_and_supplier_limitations_for_qc(self):
        product={'id':'pouch','name':'White pouch','market':'US','material':'',
                 'packageContents':'1 pouch','copyNotes':'Accessories and gross weight unconfirmed',
                 'api_key':'not-a-product-fact'}
        with patch.object(studio,'encode_reference',return_value=truth_fixture()),patch.object(studio,'model_json',side_effect=[identity_fixture(),director_fixture()]) as model:
            project=studio.plan({'references':['primary']},product,{'title':'Unverified listing claim'})
        product['packageContents']='4 pouches'
        saved=studio.get_project(project['id'])
        self.assertEqual(saved['productFacts']['packageContents'],'1 pouch')
        self.assertEqual(saved['productFacts']['material'],'')
        self.assertEqual(saved['productFacts']['copyNotes'],'Accessories and gross weight unconfirmed')
        self.assertNotIn('api_key',saved['productFacts'])
        self.assertEqual(model.call_args_list[0].args[1]['ownProductFacts'],saved['productFacts'])
        self.assertEqual(model.call_args_list[1].args[1]['facts'],saved['productFacts'])
        revised=studio.update({'id':saved['id'],'plan':saved['plan'],'confirmed':True})
        self.assertEqual(revised['productFacts'],saved['productFacts'])
        self.assertEqual(revised['plan']['slots'][1]['composition'],saved['plan']['slots'][1]['composition'])
        oversized=copy.deepcopy(saved['plan']);oversized['slots'][1]['composition']='x'*32001
        with self.assertRaises(ValueError):studio.validate_plan(oversized)

    def test_qc_receives_product_inputs_separate_from_planner_claims(self):
        self.project['productFacts']={'name':'White pouch','material':'','packageContents':'1 pouch',
                                     'copyNotes':'Included accessories unconfirmed; standing stability untested'}
        self.project['plan']['slots'][1].update(headline='Sturdy Upright Base',caption='',
                                              evidence='Planner says it stands on any flat surface')
        answer={'scores':review_scores(),'identityPass':True,'textPass':True,'readablePass':True,'technicalPass':False,
                'observedText':'Sturdy Upright Base','issues':['Unsupported self-standing performance claim']}
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',return_value=answer) as model:
            result=studio.review(self.project,1,'https://example.test/pouch.png')
        self.assertEqual(model.call_args.args[1]['productFacts'],self.project['productFacts'])
        self.assertIn('Planner says',model.call_args.args[1]['slotEvidence'])
        self.assertIn('not independent proof',model.call_args.args[0])
        self.assertIn('technicalPass=false',model.call_args.args[0])
        self.assertFalse(result['pass'])
        self.project.pop('productFacts')
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',return_value=answer) as model:
            studio.review(self.project,1,'https://example.test/pouch.png')
        self.assertEqual(model.call_args.args[1]['productFacts'],{})
        self.assertIn('legacy projects',model.call_args.args[0])

    def test_qc_checks_exact_copy_despite_model_pass_flag(self):
        answer={'scores':review_scores(),'identityPass':True,'textPass':True,'readablePass':True,'technicalPass':True,'observedText':'Wrong spelling','issues':[]}
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',return_value=answer):
            result=studio.review(self.project,1,'https://example.test/image.png')
        self.assertFalse(result['pass']);self.assertFalse(result['textPass'])

    def test_quantity_one_is_not_duplicated_by_material_percentage(self):
        self.project['uiPlan']=director_fixture()
        card=self.project['uiPlan']['images'][5]
        card.update(product_presence='absent',headline='One Sweatshirt Included',
                    subline='100% Polyester',big_number='1',scene_direction={})
        answer={'scores':review_scores(),'identityPass':True,'textPass':True,
                'readablePass':True,'technicalPass':True,
                'observedText':'1 One Sweatshirt Included 100% Polyester','issues':[]}
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',return_value=answer):
            self.assertTrue(studio.review(self.project,5,'candidate')['pass'])
        for text in ('One Sweatshirt Included 100% Polyester',
                     '1 1 One Sweatshirt Included 100% Polyester',
                     '1.5 One Sweatshirt Included 100% Polyester'):
            with self.subTest(text=text):
                with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',return_value={**answer,'observedText':text}):
                    self.assertFalse(studio.review(self.project,5,'candidate')['pass'])

    def test_approved_caption_substring_does_not_duplicate_its_separate_headline(self):
        headline='Sleeve And Waist';caption='See the ribbed sleeve and waist.'
        values=[headline,caption]
        normal=headline+'\n'+caption
        self.assertEqual(studio.artwork_copy_occurrences(normal,headline,values),1)
        self.assertEqual(studio.artwork_copy_occurrences(normal,caption,values),1)
        self.assertEqual(studio.artwork_copy_occurrences(caption,headline,values),0)
        self.assertEqual(studio.artwork_copy_occurrences(headline+'\n'+normal,headline,values),2)
        self.assertEqual(studio.artwork_copy_occurrences(normal+'\n'+caption,caption,values),2)
        self.assertEqual(studio.artwork_copy_occurrences('Sleeves And Waist\n'+caption,headline,values),0)

    def test_ivyea_fidelity_threshold_is_lower_only_for_environmental_shots(self):
        self.project['uiPlan']=director_fixture()
        def grade(*args):
            return {'scores':review_scores(fidelity=85),'identityPass':True,'textPass':True,
                    'readablePass':True,'technicalPass':True,
                    'observedText':'Blue Cotton Shirt Easy everyday layering','issues':[],
                    'shotChecks':{key:{'match':True,'observed':expected} for key,expected in args[1]['plannedShot'].items()}}
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',side_effect=grade):
            self.assertFalse(studio.review(self.project,1,'candidate')['pass'])
            self.project['uiPlan']['images'][1]['product_presence']='environmental'
            self.assertTrue(studio.review(self.project,1,'candidate')['pass'])

    def test_supporting_cosmetic_score_warns_but_semantic_errors_still_block(self):
        self.project['uiPlan']=director_fixture()
        card=self.project['uiPlan']['images'][1]
        card['product_presence']='supporting'
        def grade(*args):
            return {'scores':review_scores(fidelity=91),'identityPass':True,'textPass':True,
                    'readablePass':True,'technicalPass':True,
                    'observedText':'Blue Cotton Shirt Easy everyday layering','issues':[],
                    'shotChecks':{key:{'match':True,'observed':expected} for key,expected in args[1]['plannedShot'].items()}}
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',side_effect=grade):
            result=studio.review(self.project,1,'candidate')
            self.assertTrue(result['pass']);self.assertTrue(result['warnings'])
            card['product_presence']='hero'
            self.assertFalse(studio.review(self.project,1,'candidate')['pass'])
        card['product_presence']='supporting'
        def wrong(*args):
            result=grade(*args);result.update(identityPass=False,issues=['Wrong pocket construction'])
            return result
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',side_effect=wrong):
            self.assertFalse(studio.review(self.project,1,'candidate')['pass'])

    def test_front_on_shot_rejects_three_quarter_torso_despite_fidelity_pass(self):
        self.project['uiPlan']=director_fixture()
        card=self.project['uiPlan']['images'][1]
        card['scene_direction'].update(angle='front-on')
        def grade(*args):
            self.assertEqual(args[1]['plannedShot']['angle'],'front-on')
            checks={key:{'match':True,'observed':value} for key,value in args[1]['plannedShot'].items()}
            checks['angle']={'match':False,'observed':'Torso turned three-quarter'}
            return {'scores':review_scores(fidelity=98),'identityPass':True,'textPass':True,
                    'readablePass':True,'technicalPass':True,'observedText':'Blue Cotton Shirt Easy everyday layering',
                    'issues':[],'shotChecks':checks}
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',side_effect=grade):
            result=studio.review(self.project,1,'candidate')
        self.assertFalse(result['pass'])
        self.assertFalse(result['shotChecks']['angle']['match'])
        self.assertTrue(result['identityPass'])

    def test_pocket_crop_replaces_full_product_layout_defaults(self):
        self.project['uiPlan']=director_fixture()
        card=self.project['uiPlan']['images'][4]
        camera='Frame from waist to hem and show the patch pocket prominently.'
        card.update(camera_direction=camera,render_prompt=camera)
        prompt=studio.compile_prompt(self.project,4)
        self.assertEqual(prompt.count(camera),1)
        self.assertNotIn('whole product is visible',prompt)
        self.assertNotIn('never crop',prompt)

    def test_ivyea_white_selection_prefers_upload_and_rejects_a_scene(self):
        from ivyea_pipeline import select_product_truth
        raw=io.BytesIO()
        Image.new('RGB',(50,50),'green').save(raw,'PNG')
        non_white='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()
        refs=['https://example.test/scene','https://example.test/white','/uploads/white']
        encoded={refs[0]:non_white,refs[1]:truth_fixture(),refs[2]:truth_fixture()}
        ordered,_=select_product_truth(refs,encoded.__getitem__)
        self.assertEqual(ordered,[refs[2],refs[0],refs[1]])
        with self.assertRaisesRegex(ValueError,'白底检测'):
            select_product_truth(refs[:1],encoded.__getitem__)

    def test_explicit_captured_main_is_not_replaced_by_a_cleaner_secondary_sku(self):
        from ivyea_pipeline import select_product_truth
        main='https://example.test/captured-main';secondary='/uploads/catalog-render'
        original=Image.new('RGB',(640,800),'#777777');stream=io.BytesIO();original.save(stream,'PNG')
        encoded={main:'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode(),secondary:truth_fixture(640)}
        truth={'url':main,'kind':'asin_main','asin':'B0HR6DDC68'}
        ordered,_=select_product_truth([main,secondary],encoded.__getitem__,truth)
        self.assertEqual(ordered,[main,secondary])
        ordered,_=select_product_truth([secondary,main],encoded.__getitem__,truth)
        self.assertEqual(ordered,[secondary,main])
        ordered,_=select_product_truth([main,secondary],encoded.__getitem__,{'url':'another-main'})
        self.assertEqual(ordered,[secondary,main])

    def test_visual_editor_plans_from_product_materials_without_manual_selection(self):
        import studio_bridge
        from types import SimpleNamespace

        upload='/uploads/'+'b'*32+'.png'
        broken='https://example.test/unavailable.png'
        supplier='https://example.test/supplier.png'
        amazon='https://example.test/amazon.png'
        product={'id':'test-product','name':'Pouch','assets':[{'url':upload,'source':'实拍图'}],
                 'editorAsinReference':{'referenceImages':[amazon]},
                 'sourceImport':{'supplier':{'images':[broken,amazon,supplier]}}}
        encoded=truth_fixture(640)

        def encode(url):
            self.assertNotEqual(url,amazon)
            if url==broken:
                raise OSError('Unavailable')
            return encoded

        with patch.object(studio,'encode_reference',side_effect=encode),patch.object(
            studio,'model_json',side_effect=[identity_fixture(),director_fixture()]
        ) as model,patch.object(studio_bridge.threading,'Thread',
                                side_effect=lambda target,daemon:SimpleNamespace(start=target)):
            task=studio_bridge.start_plan({},product,{})
        self.assertEqual(task['status'],'done',task.get('error'))
        project=studio.get_project(task['projectId'])
        self.assertEqual(project['references'],[upload,supplier])
        self.assertEqual(project['uiPlan']['product_source_url'],upload)
        self.assertEqual(model.call_args_list[0].args[2],[encoded,encoded])

    def test_automatic_source_uses_clear_original_and_excludes_thumbnail_aliases(self):
        from ivyea_pipeline import select_automatic_product_truth

        original='https://cbu01.alicdn.com/img/product.jpg'
        converted=original+'_.webp'
        thumbnail=original+'_60x60q90.jpg'
        low_upload='/uploads/'+'b'*32+'.png'
        detail='https://cbu01.alicdn.com/img/detail.jpg'
        low=truth_fixture()
        clear=truth_fixture(720)
        encoded={low_upload:low, converted:clear, original:clear, detail:clear}
        refs=[thumbnail,low_upload,converted,detail,original]
        self.assertEqual(select_automatic_product_truth(refs,encoded.__getitem__),
                         [(original,clear),(detail,clear)])
        with self.assertRaisesRegex(ValueError,'500'):
            select_automatic_product_truth([thumbnail,low_upload],encoded.__getitem__)

    def test_automatic_source_uses_only_the_captured_product_main_as_fallback(self):
        from ivyea_pipeline import captured_asin_truth, select_automatic_product_truth

        asin='B0HQ6J6KWH'
        main='https://m.media-amazon.com/images/I/example.jpg'
        detail='/uploads/'+'b'*32+'.png'
        white='/uploads/'+'c'*32+'.png'
        product={'asin':asin,'market':'US','editorAsinReference':{
            'selectedAsin':asin,'market':'US','capturedAt':'2026-11-10','referenceImages':[main]}}
        capture=captured_asin_truth(product)
        self.assertEqual(capture,{'kind':'asin_main','asin':asin,'url':main})
        self.assertIsNone(captured_asin_truth({**product,'asin':'B0HQ6J6KWJ'}))
        self.assertIsNone(captured_asin_truth({**product,'market':'UK'}))
        image=io.BytesIO()
        from PIL import Image
        Image.new('RGB',(720,720),'maroon').save(image,'PNG')
        non_white='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
        encoded={main:non_white,detail:non_white,white:truth_fixture(720)}
        self.assertEqual(select_automatic_product_truth([detail],encoded.__getitem__,capture),
                         [(main,non_white),(detail,non_white)])
        self.assertEqual(select_automatic_product_truth([detail,white],encoded.__getitem__,capture)[0],
                         (white,encoded[white]))

    def test_master_truth_uses_verified_child_without_relabelling_entry_asin(self):
        from ivyea_pipeline import captured_asin_truth
        from copy import deepcopy
        entry='B000000001'; child='B000000002'
        main='https://m.media-amazon.com/images/I/brown.jpg'
        fallback='https://m.media-amazon.com/images/I/silver.jpg'
        row={'asin':child,'color_name':'Brown','size_name':'Small','sku':'own-brown-S'}
        product={'asin':entry,'market':'US','masterColor':'Brown',
            'sourceImport':{'market':'US','amazon':{'variants':[row],'listingEligibleVariants':[row]}},
            'editorAsinReference':{'selectedAsin':entry,'market':'US','capturedAt':'2026-11-20',
                'referenceImages':[fallback],'variants':[{'asin':child,'color':'Brown'}],
                'colors':[{'color':'Brown','mainImage':{'url':main,'sourceAsin':child,
                    'sourceUrl':'https://www.amazon.com/dp/'+child,'checkedAt':'2026-11-20'}}]}}
        original=deepcopy(product)
        self.assertEqual(captured_asin_truth(product),{'kind':'asin_main','asin':child,'url':main})
        self.assertEqual(product,original)
        product['editorAsinReference']['colors'][0]['mainImage']['sourceUrl']='https://www.amazon.com/dp/'+entry
        self.assertEqual(captured_asin_truth(product),{'kind':'asin_main','asin':entry,'url':fallback})
        product['market']='UK'
        self.assertIsNone(captured_asin_truth(product))

    def test_explicit_nonwhite_source_requires_selected_current_captured_asin_main(self):
        from ivyea_pipeline import captured_asin_truth, select_product_truth
        main='https://m.media-amazon.com/images/I/current.jpg'
        detail='/uploads/coffee.png'
        capture=captured_asin_truth({'asin':'B0HR6DDC68','market':'US','editorAsinReference':{
            'selectedAsin':'B0HR6DDC68','market':'US','capturedAt':'2026-11-15','referenceImages':[main]}})
        raw=io.BytesIO();Image.new('RGB',(720,720),'maroon').save(raw,'PNG')
        encoded='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()
        self.assertEqual(select_product_truth([detail,main],lambda _:encoded,capture),([main,detail],encoded))
        for refs,truth in [([detail],capture),([detail,main],None),([detail,main],{**capture,'url':'https://example.test/other.jpg'})]:
            with self.assertRaisesRegex(ValueError,'白底检测'):
                select_product_truth(refs,lambda _:encoded,truth)
        small=io.BytesIO();Image.new('RGB',(220,220),'maroon').save(small,'PNG')
        with self.assertRaisesRegex(ValueError,'白底检测'):
            select_product_truth([main],lambda _:'data:image/png;base64,'+base64.b64encode(small.getvalue()).decode(),capture)

    def test_qc_receives_unknown_construction_to_check_collage_insets(self):
        answer={'scores':review_scores(),'identityPass':True,'textPass':True,'readablePass':True,'technicalPass':False,'observedText':'Blue Cotton Shirt Easy everyday layering','issues':['Unsupported rear construction']}
        self.project['plan']['warnings']=['Rear construction unknown']
        with patch.object(studio,'encode_reference',return_value='image'),patch.object(studio,'model_json',return_value=answer) as model:
            result=studio.review(self.project,1,'https://example.test/image.png')
        self.assertEqual(model.call_args.args[1]['sourceUnknowns'],['Rear construction unknown'])
        self.assertIn('every inset',model.call_args.args[0])
        self.assertFalse(result['pass'])

    def test_only_one_automatic_repair_and_no_approval_on_failure(self):
        failed={'pass':False,'issues':['Wrong pocket geometry']}
        with patch.object(studio.image_provider,'submit',side_effect=[{'id':'job1'},{'id':'job2'}]) as submit,patch.object(studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/image.png']}),patch.object(studio,'review',return_value=failed),patch('studio_bridge.result_image',return_value=raster_fixture()):
            r=studio.generate(self.options)
            with self.assertRaises(ValueError):studio.generate(self.options)
            with self.assertRaisesRegex(ValueError,'下一张'):studio.generate({**self.options,'slot':2})
            studio.advance(r['id']);studio.advance(r['id'])
            result=studio.get_run(r['id'])
        self.assertEqual(submit.call_count,2)
        self.assertEqual(result['status'],'needs_revision');self.assertEqual(result['attempt'],1)
        with self.assertRaises(ValueError):studio.approve({'runId':r['id'],'checked':True})

    def test_manual_approval_and_immutable_new_version(self):
        with patch.object(studio.image_provider,'submit',return_value={'id':'job1'}),patch.object(studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/image.png']}),patch.object(studio,'review',return_value={'pass':True,'issues':[]}) as review,patch('studio_bridge.result_image',return_value=raster_fixture()):
            r=studio.generate(self.options);studio.advance(r['id'])
        self.assertTrue(review.call_args.args[2].startswith('data:image/jpeg;base64,'))
        self.assertEqual(studio.get_run(r['id'])['status'],'awaiting_manual')
        with self.assertRaises(ValueError):studio.approve({'runId':r['id'],'checked':False})
        approved=studio.approve({'runId':r['id'],'checked':True});self.assertTrue(approved['manual'])
        saved=studio.update({'id':'test','plan':fixture(),'confirmed':True})
        self.assertNotEqual(saved['id'],'test')
        self.assertEqual(studio.get_project('test')['plan'],self.project['plan'])
        r.update(status='awaiting_manual');studio.save_run(r)
        with self.assertRaises(ValueError):studio.approve({'runId':r['id'],'checked':True})

    def test_repair_budget_rejection_keeps_original_without_unknown_submission(self):
        blocked=studio.image_provider.image_budget.BudgetBlocked('每款预算不足')
        with patch.object(studio.image_provider,'submit',side_effect=[{'id':'original'},blocked]) as submit,patch.object(studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/original.png']}),patch.object(studio,'review',return_value={'pass':False,'issues':['Wrong shape']}),patch('studio_bridge.result_image',return_value=raster_fixture()):
            r=studio.generate(self.options)
            studio.advance(r['id'])
        result=studio.get_run(r['id'])
        self.assertEqual(result['status'],'needs_revision')
        self.assertEqual(result['jobId'],'original')
        self.assertEqual(result['jobIds'],['original'])
        self.assertEqual(result['image'],'https://example.test/original.png')
        self.assertIn('每款预算不足',result['error'])
        self.assertEqual(submit.call_count,2)
        with self.assertRaises(ValueError):studio.approve({'runId':r['id'],'checked':True})

    def test_ambiguous_submit_is_never_retried(self):
        with patch.object(studio.image_provider,'submit',side_effect=ValueError('timeout')) as submit:
            with self.assertRaises(ValueError):studio.generate(self.options)
        self.assertEqual(submit.call_count,1)
        r=studio.list_projects('test-product')['runs'][0]
        self.assertEqual(r['status'],'submit_unknown')

    def test_invalid_reference_is_rejected_before_submission_reservation(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        project['uiPlan']['images'][1]['template_url']=project['references'][0]
        studio.save_project(project)
        with patch.object(studio.image_provider,'submit') as submit:
            with self.assertRaises(ValueError):studio.generate(self.options)
        submit.assert_not_called()
        self.assertEqual(studio.list_projects('test-product')['runs'],[])

    def test_background_only_change_blocks_generation_even_with_different_camera_words(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        cards=project['uiPlan']['images']
        cards[5].update(scene='A different background',camera_direction='Fresh editorial composition',
                        scene_direction=copy.deepcopy(cards[1]['scene_direction']))
        studio.save_project(project)
        with patch.object(studio.image_provider,'submit') as submit:
            with self.assertRaisesRegex(ValueError,'姿势、镜头角度、景别、构图重复'):
                studio.generate(self.options)
        submit.assert_not_called()
        self.assertEqual(studio.list_projects('test-product')['runs'],[])

    def test_three_uses_of_same_layout_are_blocked_before_generation(self):
        project=copy.deepcopy(self.project)
        project['uiPlan']=director_fixture()
        for index in (1,3,5):
            project['uiPlan']['images'][index]['layout']='human_context'
        studio.save_project(project)
        with self.assertRaisesRegex(ValueError,'同一类版式'):
            studio.check_render_prompt(project,0)

    def test_generation_only_uses_truth_unless_a_layout_reference_is_bound(self):
        project=copy.deepcopy(self.project)
        project['references']=['identity','wearing','detail']
        project['uiPlan']=director_fixture()
        project['uiPlan']['images'][1]['source_reference_indices']=[2,2]
        project['uiPlan']['style']['materials']='Unverified cotton blend with resin buttons'
        self.assertEqual(studio.slot_references(project,1),['identity'])
        self.assertNotIn('Unverified cotton',studio.compile_prompt(project,1))
        template='https://example.test/layout.png'
        project['uiPlan']['images'][1]['template_url']=template
        studio.save_project(project)
        with patch.object(studio.image_provider,'submit',side_effect=[{'id':'job1'},{'id':'job2'}]) as submit, \
             patch.object(studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/image.png']}), \
             patch.object(studio,'review',return_value={'pass':False,'issues':['Wrong collar']}), \
             patch('studio_bridge.result_image',return_value=raster_fixture()):
            run=studio.generate(self.options)
            studio.advance(run['id'])
        self.assertEqual([call.args[0]['references'] for call in submit.call_args_list],
                         [['identity',template],['identity',template]])
        self.assertIn('REFERENCE IMAGE 2 is a layout template only',submit.call_args_list[0].args[0]['prompt'])

if __name__=='__main__':unittest.main()
