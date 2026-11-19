import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import creative_skills as skills
import visual_studio as visual
from test_visual_studio import fixture, identity_fixture, director_fixture


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.object(skills,'DB',Path(self.temp.name)/'skills.sqlite3');self.patch.start()

    def tearDown(self):
        self.patch.stop();self.temp.cleanup()

    def test_versions_reject_stale_saves_and_preserve_snapshot(self):
        snapshot=skills.select({'name':'hoodie jacket'})
        changed=dict(skills.DEFAULTS);changed['apparel']='New apparel rule'
        self.assertEqual(skills.save({'version':0,'rules':changed})['version'],1)
        with self.assertRaises(ValueError):skills.save({'version':0,'rules':changed})
        self.assertNotIn('New apparel rule',skills.instruction(snapshot,'plan'))
        self.assertIn('New apparel rule',skills.instruction(skills.select({'name':'hoodie'}),'plan'))
        self.assertEqual(skills.select({'name':'kitchen organiser'})['category'],'household')

    def test_plan_render_review_use_same_skill_snapshot(self):
        with patch.object(visual,'encode_reference',return_value='ref'),patch.object(visual,'save_project',side_effect=lambda p:p),patch.object(visual,'model_json',side_effect=[identity_fixture(),director_fixture()]) as model:
            p=visual.plan({'references':['source']},{'id':'test','name':'jacket'}, {})
        self.assertIn(skills.DEFAULTS['apparel'],model.call_args.args[0])
        changed=dict(skills.DEFAULTS);changed['apparel']='Changed rule after plan'
        skills.save({'version':0,'rules':changed})
        self.assertIn(skills.DEFAULTS['apparel'],visual.compile_prompt(p,1))
        self.assertNotIn('Changed rule after plan',visual.compile_prompt(p,1))
        answer={'identityPass':True,'textPass':True,'readablePass':True,'technicalPass':True,'observedText':'Blue Cotton Shirt Easy everyday layering','issues':[]}
        with patch.object(visual,'encode_reference',return_value='ref'),patch.object(visual,'model_json',return_value=answer) as model:
            visual.review(p,1,'generated')
        self.assertIn(skills.DEFAULTS['quality'],model.call_args.args[0])
        self.assertIn(skills.DEFAULTS['apparel'],model.call_args.args[0])

    def test_invalid_rules_rejected(self):
        with self.assertRaises(ValueError):skills.save({'version':0,'rules':{}})
        rules=dict(skills.DEFAULTS);rules['planning']=''
        with self.assertRaises(ValueError):skills.save({'version':0,'rules':rules})
