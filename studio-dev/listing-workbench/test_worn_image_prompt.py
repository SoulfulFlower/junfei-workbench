import unittest
import creative_skills
import ivyea_pipeline
import visual_studio


class WornPromptTests(unittest.TestCase):
    def project(self,presentation):
        return {'references':['worn-photo'],'deliverable':'gallery','uiPlan':{'language':'en','style':{},'product_lock':'Exact brown cardigan',
            'product_profile':{'object_behavior':'soft_goods','reference_presentation':presentation,'fidelity_anchors':['visible placket']},
            'images':[{'shot_type':'detail','layout':'detail_macro','text_on_image':False,'product_presence':'hero'}]}}

    def test_observed_wearer_survives_bundle_exclusion(self):
        prompt=ivyea_pipeline.compile_project(self.project('worn'),0)
        self.assertNotIn('everything except the main unit is reference noise',prompt)
        self.assertNotIn('memory cards',prompt)
        self.assertIn('preserve the garment\'s observed front construction',prompt)
        self.assertIn('Detail crops must come from the observed worn front',prompt)
        self.assertIn('visible fasteners and buttonholes without adding hidden ones',prompt)

    def test_unknown_presentation_does_not_invent_a_wearer(self):
        prompt=ivyea_pipeline.compile_project(self.project('unknown'),0)
        self.assertNotIn('observed worn front',prompt)

    def test_product_free_card_does_not_inherit_worn_garment_commands(self):
        project=self.project('worn')
        project['uiPlan']['images'][0].update(shot_type='hero_feature',layout='result_showcase',product_presence='absent')
        prompt=ivyea_pipeline.compile_project(project,0)
        self.assertIn('physical product does NOT appear',prompt)
        self.assertNotIn('[OBSERVED PRESENTATION]',prompt)
        self.assertNotIn('preserve the garment\'s observed front construction',prompt)

    def test_detail_crop_does_not_require_the_whole_garment(self):
        project=self.project('worn')
        prompt=ivyea_pipeline.compile_project(project,0)
        self.assertIn('Use one continuous photograph',prompt)
        self.assertIn('Do not add a full-product inset, split view, grid or collage',prompt)
        self.assertNotIn('whole product',prompt)
        project['uiPlan']['images'][0].update(layout='white_main',shot_type='white_main')
        main=ivyea_pipeline.compile_project(project,0)
        self.assertIn('The complete product fills 80-90%',main)

    def test_preflight_rejects_conflicting_custom_detail_prompt(self):
        project=self.project('worn')
        card=project['uiPlan']['images'][0]
        self.assertIn('one continuous photograph',visual_studio.check_render_prompt(project,0))
        card['render_prompt']='Focus on a single stitch. The complete product must sit fully inside the frame.'
        with self.assertRaisesRegex(ValueError,'特写同时要求完整展示'):
            visual_studio.check_render_prompt(project,0)
        card.update(layout='white_main',text_on_image=True)
        with self.assertRaisesRegex(ValueError,'白底主图'):
            visual_studio.check_render_prompt(project,0)

    def test_apparel_gallery_keeps_distinct_roles_before_render(self):
        self.assertEqual(creative_skills.select({'name':'女士长款开衫'})['category'],'apparel')
        project=self.project('worn')
        project['galleryDirection']='apparel_v1'
        images=project['uiPlan']['images']=[
            {'shot_type':'white_main','layout':'white_main','product_presence':'hero'},
            {'shot_type':'hero_feature','layout':'poster_hero','product_presence':'supporting'},
            {'shot_type':'detail','layout':'detail_macro','product_presence':'supporting'},
            {'shot_type':'lifestyle','layout':'human_context','product_presence':'environmental'},
        ]
        self.assertIn('white_main',visual_studio.check_render_prompt(project,0))
        images.extend([{'shot_type':'detail','layout':'detail_macro','product_presence':'supporting'}]*4)
        with self.assertRaisesRegex(ValueError,'最多安排一张独立细节特写|使用同一类版式'):
            visual_studio.check_render_prompt(project,0)


if __name__=='__main__':unittest.main()
