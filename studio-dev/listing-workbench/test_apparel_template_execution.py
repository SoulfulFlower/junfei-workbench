import copy
import unittest
from unittest.mock import patch
import apparel_art_direction as direction
import apparel_suite as apparel
import image_engine_prompts as prompts
from test_apparel_suite import template


class TemplateDirectionTests(unittest.TestCase):
    def fixture(self, no_text=False, **extra):
        recipe = apparel.freeze_request({'counts': {'seller': 1},
            'templatePolicy': 'point-only-v1', 'pointTemplateIds': [template()['id']],
            'artDirection': direction.POLICY, **extra}, ['/source.png'],
            reference_sha256=['a'*64], templates=[template()], count=1,
            no_text=no_text, brief='Keep actual colour, fine fringe and the original front view.')
        shot = {'kind':'seller','layout':'feature','sourceIndex':0,'question':'Construction',
            'evidence':'Visible front pockets and hem','scene':'A complete template-led poster',
            'camera':'Source-supported front view','copy':[] if no_text else ['Visible fringe'],
            'templateDesign': {'templateId':template()['id'], **{k:'Actual artwork observation '+k for k in direction.DESIGN_FIELDS}}}
        plan = apparel.normalize_plan({'identity':'Photographed trousers','style':{},'shots':[shot]}, recipe)
        shot = plan['shots'][0];shot['apparelReferenceRoles'] = apparel.render_references(recipe, shot)
        return recipe, plan, shot

    def test_wrong_or_missing_artwork_analysis_blocks_before_generation(self):
        recipe,plan,shot=self.fixture()
        for value in (None, {'templateId':'other'}, {k:v for k,v in shot['templateDesign'].items() if k!='hero'}):
            bad=copy.deepcopy(shot);bad['templateDesign']=value
            with self.assertRaises(ValueError):apparel.normalize_plan({'identity':'same','style':{},'shots':[bad]},recipe)

    def test_textless_compiler_keeps_same_design_and_reference_identity(self):
        recipe,plan,shot=self.fixture()
        before=copy.deepcopy(shot);with_text=prompts.compile_shot(plan,shot,recipe['brief'])
        without_text=prompts.compile_shot(plan,shot,recipe['brief'],no_text=True)
        self.assertEqual(shot,before)
        self.assertEqual(shot['apparelReferenceRoles'][1]['templateId'],template()['id'])
        self.assertIn(template()['prompt'],with_text)
        self.assertIn(template()['prompt'],without_text)
        self.assertIn('[EXACT ALLOWED ARTWORK COPY] []',without_text)
        self.assertIn('supporting-image groupings',without_text)
        self.assertNotIn('Exact product pixels',with_text)
        self.assertNotIn('http',with_text)

    def test_reference_reordering_remains_blocked(self):
        recipe,plan,shot=self.fixture();shot['apparelReferenceRoles'].reverse()
        with self.assertRaisesRegex(ValueError,'顺序或角色'):prompts.compile_shot(plan,shot,recipe['brief'])

    def test_new_planner_is_explicit_and_old_frozen_requests_stay_old(self):
        self.assertEqual(prompts.director_for({'apparelSuite':{'artDirection':direction.POLICY}}),direction.DIRECTOR)
        self.assertEqual(prompts.director_for({'apparelSuite':{'version':apparel.VERSION}}),apparel.DIRECTOR)
        with self.assertRaisesRegex(ValueError,'策略'):self.fixture(artDirection='unknown')
        with self.assertRaisesRegex(ValueError,'原片锁定'):self.fixture(sourcePixelMode=True)

    def test_natural_kind_does_not_gain_advertising_panels(self):
        r=apparel.freeze_request({'counts':{'ins':1},'templatePolicy':'point-only-v1','artDirection':direction.POLICY},
            ['/source.png'],reference_sha256=['a'*64],templates=[],count=1,no_text=False,brief='Natural scene')
        s={'kind':'ins','layout':'scene','sourceIndex':0,'question':'wear','evidence':'source',
            'scene':'natural','camera':'front','copy':[]}
        p=apparel.normalize_plan({'identity':'same','style':{},'shots':[s]},r);s=p['shots'][0]
        s['apparelReferenceRoles']=apparel.render_references(r,s)
        self.assertIn('NATIVE KIND WITHOUT SELLER TEMPLATE',prompts.compile_shot(p,s,r['brief']))

    def test_real_process_dispatches_selected_director_before_any_paid_render(self):
        import image_engine as engine
        recipe,plan,shot=self.fixture()
        task={'id':'test','productId':'p','status':'queued','results':[],
              'request':{'mode':'suite','references':['/source.png'],'count':1,'brief':recipe['brief'],
                         'noText':False,'officialTemplates':[template()],'apparelSuite':recipe}}
        class HaltBeforeNetwork(Exception):pass
        def capture(instruction,*args,**kwargs):
            self.assertIn(direction.DIRECTOR,instruction)
            self.assertIn('SHOT WIRE CONTRACT',instruction)
            raise HaltBeforeNetwork('isolated capture; no network')
        with patch.object(engine,'get',return_value=task),patch.object(engine,'assert_assets'),patch.object(engine,'save'),patch.object(engine,'json_model',side_effect=capture)as model:
            engine.process('test')
        self.assertEqual(model.call_count,1)
        self.assertEqual(task['status'],'failed')

    def test_complete_text_style_recovers_losslessly_without_new_planning(self):
        import image_engine as engine
        recipe,plan,shot=self.fixture()
        raw={'identity':'Source trousers','style':'Natural light, true garment chroma',
             'shots':[copy.deepcopy(shot)]}
        original=copy.deepcopy(raw)
        ready=engine.normalize_shots(copy.deepcopy(raw),1,1,False)
        self.assertEqual(raw,original)
        self.assertEqual(ready['style'],{'photography':original['style']})
        request={'mode':'suite','brief':recipe['brief'],'count':1,'noText':False,
                 'referenceSha256':['a'*64],'officialTemplates':[template()],'apparelSuite':recipe}
        parent={'id':'original','productId':'p','status':'failed',
                'error':'策划未返回商品身份与统一风格','results':[],'request':request,'plannerProposal':raw}
        recovered=engine.frozen_plan_recovery(copy.deepcopy(request),parent,'p')
        self.assertEqual(recovered['proposal'],raw)
        self.assertFalse(recovered['paidImageSubmissionReplayed'])
        for altered in ({'providerJobId':'already-paid'},{'pending':{'prompt':'unknown'}},{'status':'submission_unknown'}):
            with self.assertRaises(ValueError):engine.frozen_plan_recovery(request,{**parent,**altered},'p')
        with self.assertRaises(ValueError):engine.frozen_plan_recovery({**request,'brief':'changed'},parent,'p')


if __name__=='__main__':unittest.main()
