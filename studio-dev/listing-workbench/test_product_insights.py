import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ivyea_pipeline
import product_insights
import provider
import studio_bridge


class ProductInsightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.enterContext(patch.object(product_insights,'DB',Path(temp.name)/'insights.sqlite3'))
        self.own = '/uploads/'+'a'*32+'.png'
        self.competitor = 'https://m.media-amazon.com/images/I/competitor.jpg'
        self.product = {'id':'p','name':'Cardigan','style':'Button front',
            'assets':[{'url':self.own,'source':'产品实拍'}],
            'sourceImport':{'amazon':{'referenceImages':[self.competitor]}}}
        self.result = {'observations':[{'kind':'可见结构','text':'可见翻领'},
            {'kind':'颜色与可见纹理','text':'麻花纹外观'}],'unknowns':['纤维成分无法从照片确认']}
        self.image = self.enterContext(patch.object(product_insights,'encode',return_value=('image','hash-a')))
        self.model = self.enterContext(patch('visual_studio.model_json',return_value=self.result))

    def confirm_first(self):
        report = product_insights.analyse(self.product,self.own)
        image = report['images'][0]
        return product_insights.confirm(self.product,{'url':self.own,'revision':image['revision'],'indices':[0]})

    def test_only_confirmed_own_photo_observations_survive_current_source_check(self):
        with self.assertRaisesRegex(ValueError,'当前产品'):
            product_insights.analyse(self.product,self.competitor)
        self.model.assert_not_called()
        pending = product_insights.analyse(self.product,self.own)
        self.assertEqual(pending['version'],'')
        self.assertEqual(product_insights.context(self.product),{})
        accepted = self.confirm_first()
        self.model.assert_called_once()
        evidence = product_insights.context(self.product)
        self.assertEqual(evidence['version'],accepted['version'])
        self.assertEqual([item['text'] for item in evidence['observations']],['可见翻领'])
        self.assertEqual(product_insights.context({**self.product,'style':'Changed style'}),{})
        self.image.return_value = ('image','hash-b')
        self.assertTrue(product_insights.report(self.product)['images'][0]['stale'])
        self.assertEqual(product_insights.context(self.product),{})

    def test_listing_and_storyboard_receive_the_same_confirmed_observation(self):
        self.confirm_first()
        expected = product_insights.context(self.product)['observations']
        with patch.dict(provider.SETTINGS,{'provider':'deepseek','api_key':'fixture','model':'fixture'}), \
             patch.object(provider,'text_completion',side_effect=ValueError('capture listing request')) as request:
            with self.assertRaisesRegex(ValueError,'capture listing'):
                provider.generate_listing(self.product,'US')
        payload = json.loads(request.call_args.args[0]['messages'][1]['content'])
        self.assertEqual(payload['confirmed_photo_observations'],expected)
        self.assertNotIn('可见翻领',json.dumps(payload['confirmed_product_facts'],ensure_ascii=False))

        self.model.return_value = {'fidelity_anchors':['cardigan'],'object_behavior':'soft_goods'}
        with patch.object(ivyea_pipeline,'select_product_truth',return_value=([self.own],'image')), \
             patch.object(ivyea_pipeline.core,'planning_prompt',side_effect=ValueError('capture storyboard request')) as planner:
            with self.assertRaisesRegex(ValueError,'capture storyboard'):
                ivyea_pipeline.plan_project({'references':[self.own],'deliverable':'aplus'},self.product,{})
        self.assertEqual(json.loads(planner.call_args.kwargs['img_sp']),expected)

    def test_paid_render_stops_on_changed_saved_listing(self):
        from product_insights import digest
        analysis = {'listingFingerprint':digest({'title':'Old','bullets':'','description':''})}
        with patch.object(studio_bridge,'latest_project',return_value={'id':'plan','analysis':analysis}), \
             patch.object(studio_bridge.visual,'generate') as generate:
            with self.assertRaisesRegex(ValueError,'Listing 文案已变化'):
                studio_bridge.render({'confirmed':True},self.product,{'title':'New'})
        generate.assert_not_called()

    def test_fact_only_storyboard_survives_the_first_listing_save(self):
        analysis = {'listingFingerprint':product_insights.digest(
            {'title':'','bullets':'','description':''})}
        with patch.object(studio_bridge,'latest_project',return_value={'id':'plan','analysis':analysis}), \
             patch.object(studio_bridge.visual,'require_ai_storyboard') as verified:
            with self.assertRaisesRegex(ValueError,'确认分镜与付费生成'):
                studio_bridge.render({},self.product,{'title':'First saved draft'})
        verified.assert_called_once()
