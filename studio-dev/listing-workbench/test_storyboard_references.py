import unittest
import base64,hashlib
from unittest.mock import patch
import ivyea_pipeline
import visual_studio


class StoryboardReferenceTests(unittest.TestCase):
    def test_set_review_supplies_only_verified_unchanged_alternate_sources_once(self):
        import studio_bridge
        project=self.project();project['galleryDirection']='apparel_v2_no_filler'
        raw=b'actual encoded reference bytes';encoded='data:image/png;base64,'+base64.b64encode(raw).decode()
        project['analysis']['referenceHashes']={'hanging':hashlib.sha256(raw).hexdigest()}
        chosen={'identity':'same_sku','angle':'three-quarter','visible':['Sleeve and waist']}
        with patch('ivyea_pipeline.shot_source',return_value=('hanging',chosen,'')), \
             patch.object(visual_studio,'encode_reference',return_value=encoded) as encode:
            images,records=studio_bridge.verified_set_references(project,[{},{}])
        self.assertEqual(images,[encoded]);encode.assert_called_once_with('hanging')
        self.assertEqual(records[0]['inputImageNumber'],3)
        self.assertEqual(records[0]['slotNumbers'],[1,2])
        with patch('ivyea_pipeline.shot_source',return_value=('wrong-colour',{'identity':'different_sku'},'')):
            self.assertEqual(studio_bridge.verified_set_references(project,[{}]),([],[]))
        with patch('ivyea_pipeline.shot_source',return_value=('hanging',chosen,'')), \
             patch.object(visual_studio,'encode_reference',return_value='data:image/png;base64,eA=='):
            with self.assertRaisesRegex(ValueError,'内容已变化'):
                studio_bridge.verified_set_references(project,[{}])

    def project(self):
        return {'references':['worn','hanging','wrong-colour','neckline'],
            'analysis':{'referenceViews':[
                {'url':'worn','index':0,'identity':'primary','angle':'front-on','visible':['Worn front']},
                {'url':'hanging','index':1,'identity':'same_sku','angle':'front-on','visible':['Full front, ribbed hem and interior neck label']},
                {'url':'wrong-colour','index':2,'identity':'different_sku','angle':'front-on','visible':['Paler colour']},
                {'url':'neckline','index':3,'identity':'same_sku','angle':'front-on','visible':['Worn neckline detail']},
            ]},'uiPlan':{'style':{},'product_lock':'Pink ruffle sweatshirt',
                'product_profile':{'object_behavior':'soft_goods','reference_presentation':'worn'},
                'images':[{'shot_type':'white_main','layout':'white_main','product_presence':'hero',
                           'source_reference_indices':[1,0]}]}}

    def test_planner_selected_verified_photo_is_the_only_product_truth(self):
        project=self.project()
        self.assertEqual(visual_studio.slot_references(project,0),['hanging'])
        prompt=ivyea_pipeline.compile_project(project,0)
        self.assertIn('interior neck label',prompt)
        self.assertNotIn('Do not convert it to a flat lay',prompt)
        self.assertIn('remove the source hanger',prompt)
        self.assertNotIn('Use the ASIN reference',prompt)

    def test_detail_preserves_worn_rules_and_never_selects_different_sku(self):
        project=self.project();card=project['uiPlan']['images'][0]
        card.update(shot_type='detail',layout='detail_macro',source_reference_indices=[3,0])
        self.assertEqual(visual_studio.slot_references(project,0),['neckline'])
        self.assertIn('Detail crops must come from the observed worn front',ivyea_pipeline.compile_project(project,0))
        card['source_reference_indices']=[2,1]
        self.assertEqual(visual_studio.slot_references(project,0),['hanging'])
        card['source_reference_indices']=[True,99,'1']
        self.assertEqual(visual_studio.slot_references(project,0),['worn'])

    def test_verified_alternate_view_does_not_inherit_a_front_only_instruction(self):
        project=self.project();project['references'].append('rear-quarter')
        project['analysis']['referenceViews'].append({'url':'rear-quarter','index':4,'identity':'same_sku',
            'angle':'three-quarter','visible':['Worn rear-quarter sleeve and waist, neckline obscured']})
        project['uiPlan']['images'][0].update(shot_type='hero_feature',layout='poster_hero',
            product_presence='supporting',source_reference_indices=[4],camera_direction='Match the photographed rear-quarter sleeve and waist only.')
        self.assertEqual(visual_studio.slot_references(project,0),['rear-quarter'])
        prompt=ivyea_pipeline.compile_project(project,0)
        self.assertIn('actual observed view',prompt)
        self.assertIn('hidden construction stays hidden',prompt)
        self.assertNotIn('observed front construction',prompt)
        self.assertNotIn('Detail crops must come from the observed worn front',prompt)

    def test_scene_honors_linked_verified_photo_and_keeps_supplier_priority_within_candidates(self):
        project=self.project();project['analysis']['supplierReferences']=['hanging']
        card=project['uiPlan']['images'][0]
        card.update(shot_type='lifestyle',layout='human_context',source_reference_indices=[3],
                    scene_direction={'angle':'front-on'})
        self.assertEqual(ivyea_pipeline.shot_source(project,0)[0],'neckline')
        card['source_reference_indices']=[3,1]
        self.assertEqual(ivyea_pipeline.shot_source(project,0)[0],'hanging')
        project['analysis']['referenceViews'][3]['angle']='profile'
        card['source_reference_indices']=[3]
        self.assertEqual(ivyea_pipeline.shot_source(project,0)[0],'hanging')


if __name__=='__main__':unittest.main()
