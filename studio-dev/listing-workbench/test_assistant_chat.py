import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import assistant_chat as chat
import visual_studio as visual
from test_visual_studio import fixture, director_fixture

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(chat,'DB',Path(self.temp.name)/'chat.sqlite3'),patch.object(visual,'DB',Path(self.temp.name)/'visual.sqlite3')]
        for p in self.patches:p.start()
        self.user={'id':1};self.product={'id':'p','name':'Product'}
    def tearDown(self):
        for p in self.patches:p.stop()
        self.temp.cleanup()
    def send(self,answer,data=None):
        with patch.object(visual,'model_json',return_value=answer):
            return chat.send(data or {'text':'Hello'},self.user,self.product,{})
    def test_private_persistent_history_and_real_context(self):
        with patch.object(visual,'model_json',return_value={'reply':'hello','action':None}) as model:
            h=chat.send({'text':'Hi'},self.user,self.product,{'title':'Saved title'})
        self.assertEqual(model.call_args.args[1]['listing']['title'],'Saved title')
        self.assertEqual(len(h['messages']),2)
        self.assertEqual(chat.history(h['id'],1),h)
        with self.assertRaises(ValueError):chat.history(h['id'],2)
        self.assertEqual(chat.sessions(2,'p')['sessions'],[])
        with self.assertRaises(ValueError):chat.send({'chatId':h['id'],'text':'x'},self.user,{'id':'different'}, {})
    def test_all_selected_images_reach_model_in_order(self):
        with patch.object(visual,'encode_reference',side_effect=lambda ref:'encoded:'+ref),patch.object(visual,'model_json',return_value={'reply':'images received','action':None}) as model:
            h=chat.send({'text':'看图片','references':['primary','detail']},self.user,self.product,{})
        self.assertEqual(model.call_args.args[2],['encoded:primary','encoded:detail'])
        self.assertEqual(model.call_args.args[1]['imageCount'],2)
        self.assertEqual(h['messages'][0]['references'],['primary','detail'])
    def test_actions_require_click_and_never_double_execute(self):
        h=self.send({'reply':'propose','action':{'type':'plan_images','brief':'Soft daylight'}})
        m=h['messages'][-1]
        with patch.object(visual,'plan',return_value={'id':'plan-id'}) as plan:
            with self.assertRaises(ValueError):chat.execute({'chatId':h['id'],'messageId':m['id']},self.user,self.product,{})
            self.assertEqual(plan.call_count,0)
            result=chat.execute({'chatId':h['id'],'messageId':m['id'],'confirmed':True},self.user,self.product,{})
            self.assertEqual(plan.call_count,1)
            with self.assertRaises(ValueError):chat.execute({'chatId':h['id'],'messageId':m['id'],'confirmed':True},self.user,self.product,{})
        self.assertEqual(result['messages'][-1]['result']['kind'],'project')
    def test_no_fake_execution_on_model_failure_or_unknown_tools(self):
        h=self.send({'reply':'result','action':{'type':'run_shell','command':'anything'}})
        self.assertIsNone(h['messages'][-1]['action'])
        with patch.object(visual,'model_json',side_effect=ValueError('no provider')):
            h=chat.send({'chatId':h['id'],'text':'retry'},self.user,self.product,{})
        self.assertEqual(h['messages'][-1]['role'],'error')
    def test_plan_revision_is_new_unconfirmed_version(self):
        visual.save_project({'id':'old','productId':'p','references':[],'created':1,'confirmed':True,'plan':fixture()})
        h=self.send({'reply':'change','action':{'type':'revise_plan','plan':fixture()}})
        m=h['messages'][-1]
        result=chat.execute({'chatId':h['id'],'messageId':m['id'],'confirmed':True},self.user,self.product,{})
        project=visual.get_project(result['messages'][-1]['result']['id'])
        self.assertFalse(project['confirmed']);self.assertNotEqual(project['id'],'old')
        self.assertTrue(visual.get_project('old')['confirmed'])
        self.assertNotIn('aiStoryboard',project)
        self.assertNotIn('uiPlan',project)

    def native_project(self):
        native=director_fixture()
        native['images'][1]['product_presence']='environmental'
        native['images'][6].update(role='Size guide',size_chart=True)
        native['product_profile']={'object_behavior':'soft_goods'}
        views=[{'url':'source-'+str(index),'identity':'primary' if index==0 else 'same_sku',
                'angle':card['scene_direction']['angle'],'visible':['Observed garment front']}
               for index,card in enumerate((native['images'][1],native['images'][5]))]
        return {'id':'native','productId':'p','references':['source-0','source-1'],
                'created':1,'confirmed':True,'deliverable':'gallery','plan':fixture(),
                'uiPlan':native,'galleryDirection':'apparel_v1',
                'analysis':{'referenceViews':views},
                'sizeEvidence':{'units':'cm','sourcePage':'https://example.test/size',
                                'columns':['Size','Length'],'rows':[['S','60'],['M','62']]},
                'aiStoryboard':{'version':1,'origin':'workbench_ai_planner','model':'recorded-model'}}

    def test_native_revision_preserves_cards_sources_size_and_ai_provenance(self):
        old=self.native_project();visual.save_project(old)
        plan=copy.deepcopy(old['plan']);plan['lighting']='Slightly warmer daylight'
        h=self.send({'reply':'change lighting','action':{'type':'revise_plan','plan':plan}})
        message=h['messages'][-1]
        with patch.object(visual,'generate',side_effect=AssertionError('must not render')):
            result=chat.execute({'chatId':h['id'],'messageId':message['id'],'confirmed':True},self.user,self.product,{})
        saved=visual.get_project(result['messages'][-1]['result']['id'])
        self.assertEqual(result['messages'][-1]['status'],'executed')
        self.assertFalse(saved['confirmed']);self.assertEqual(saved['parent'],old['id'])
        self.assertEqual(saved['uiPlan']['images'],old['uiPlan']['images'])
        self.assertEqual(saved['uiPlan']['style']['lighting'],plan['lighting'])
        for key in ('references','analysis','sizeEvidence','aiStoryboard','galleryDirection'):
            self.assertEqual(saved[key],old[key])
        self.assertEqual(visual.get_project(old['id']),old)
        self.assertEqual(visual.list_projects('p')['runs'],[])
        for index in range(7):
            self.assertTrue(visual.check_render_prompt(saved,index))
        with self.assertRaisesRegex(visual.image_provider.StoryboardRequired,'确认'):
            visual.require_ai_storyboard(saved,'p',confirmed=True)

    def test_native_revision_changes_only_requested_card_and_keeps_other_deliverable(self):
        old=self.native_project();visual.save_project(old)
        plan=copy.deepcopy(old['plan']);plan['slots'][2]['headline']='Visible Knit Detail'
        h=self.send({'reply':'change headline','action':{'type':'revise_plan','plan':plan}})
        visual.save_project({**old,'id':'new-aplus','created':2,'deliverable':'aplus'})
        result=chat.execute({'chatId':h['id'],'messageId':h['messages'][-1]['id'],'confirmed':True},self.user,self.product,{})
        saved=visual.get_project(result['messages'][-1]['result']['id'])
        self.assertEqual(saved['uiPlan']['images'][2]['headline'],'Visible Knit Detail')
        for index in (0,1,3,4,5,6):
            self.assertEqual(saved['uiPlan']['images'][index],old['uiPlan']['images'][index])
        self.assertEqual(saved['uiPlan']['images'][2]['shot_type'],old['uiPlan']['images'][2]['shot_type'])

    def test_revision_retains_render_history_without_reusing_changed_card_qc(self):
        old=self.native_project()
        for index in (1,2):
            old['uiPlan']['images'][index].update(final_url='old-'+str(index),base_url='old-'+str(index),
                _runId='run-'+str(index),_status='approved',human_reviewed=True,render_qa={'ready':True})
        visual.save_project(old)
        plan=copy.deepcopy(old['plan']);plan['slots'][2]['headline']='Revised knit detail'
        saved=visual.save_plan_revision({'id':old['id'],'plan':plan})
        changed=saved['uiPlan']['images'][2]
        for key in ('final_url','base_url','_runId','_status','human_reviewed','render_qa'):
            self.assertNotIn(key,changed)
        self.assertIn({'url':'old-2','_runId':'run-2'},changed['versions'])
        self.assertEqual(saved['uiPlan']['images'][1],old['uiPlan']['images'][1])
        plan['lighting']='Different shared daylight'
        shared=visual.save_plan_revision({'id':old['id'],'plan':plan})
        self.assertNotIn('final_url',shared['uiPlan']['images'][1])
        self.assertIn({'url':'old-1','_runId':'run-1'},shared['uiPlan']['images'][1]['versions'])
        self.assertEqual(visual.get_project(old['id']),old)

    def test_chat_uses_current_native_roles_and_rejects_stale_revision(self):
        old=self.native_project();visual.save_project(old)
        with patch.object(visual,'model_json',return_value={'reply':'current roles','action':None}) as model:
            chat.send({'text':'Which slot is the size guide?'},self.user,self.product,{})
        context=model.call_args.args[1]['latestVisualProject']
        self.assertEqual(context['cards'][6]['role'],'Size guide')
        self.assertTrue(context['cards'][6]['size_chart'])
        self.assertNotIn('slot0白底主图、1生活场景',model.call_args.args[0])
        h=self.send({'reply':'revise','action':{'type':'revise_plan','plan':old['plan']}})
        visual.save_project({**old,'id':'newer-gallery','created':2})
        result=chat.execute({'chatId':h['id'],'messageId':h['messages'][-1]['id'],'confirmed':True},self.user,self.product,{})
        self.assertEqual(result['messages'][-1]['status'],'error')
        self.assertIn('分镜已变化',result['messages'][-1]['result']['text'])
    def test_generation_never_automatically_repairs_and_requires_confirmed_plan(self):
        visual.save_project({'id':'old','productId':'p','references':[],'created':1,'confirmed':True,'plan':fixture()})
        h=self.send({'reply':'generate','action':{'type':'generate_image','slot':0}});m=h['messages'][-1]
        with patch.object(visual,'generate',return_value={'id':'run'}) as generate:
            chat.execute({'chatId':h['id'],'messageId':m['id'],'confirmed':True},self.user,self.product,{})
        self.assertFalse(generate.call_args.args[0]['autoRepair'])
    def test_general_chat_has_no_product_write(self):
        with patch.object(visual,'model_json',return_value={'reply':'hello','action':{'type':'plan_images'}}):
            h=chat.send({'text':'hello'},self.user,None,{})
        self.assertIsNone(h['messages'][-1]['action'])

if __name__=='__main__':unittest.main()
