"""Composition rejection persists the original run; no paid repair or approval."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import image_composition
import visual_studio as studio
from test_image_composition import raster
from test_visual_studio import fixture


class GenerationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        for target,name,value in ((studio,'DB',root/'visual.sqlite3'),
                                   (studio.image_provider,'ROOT',root),
                                   (studio.provider.app_paths,'DATA',root)):
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
        self.project=studio.save_project({'id':'test','productId':'P','created':1,'brief':'','references':['/uploads/'+'a'*32+'.png'],
            'plan':studio.validate_plan(fixture()),'confirmed':True,
            'aiStoryboard':{'version':1,'origin':'workbench_ai_planner','model':'test'}})

    def run_image(self, raw, slot):
        with patch.object(studio.image_provider,'submit',return_value={'id':'original'}) as submit, \
             patch.object(studio.image_provider,'poll',return_value={'status':'completed','images':['https://example.test/original.png']}), \
             patch('studio_bridge.result_image',return_value=(raw,'image/png')), \
             patch.object(studio,'review') as review:
            run=studio.generate({'id':'test','slot':slot,'model':'test','autoRepair':True})
            studio.advance(run['id'])
        submit.assert_called_once();review.assert_not_called()
        result=studio.get_run(run['id'])
        self.assertEqual(result['status'],'needs_revision')
        self.assertEqual(result['image'],'https://example.test/original.png')
        with self.assertRaises(ValueError):studio.approve({'runId':result['id'],'checked':True})
        return result

    def test_small_main_keeps_original_job_and_blocks_approval_without_repair(self):
        result=self.run_image(raster('narrow',size=(1600,1600)),0)
        self.assertIn('SUBJECT_TOO_SMALL',{i['code'] for i in result['qc'][-1]['technical']['issues']})

    def test_small_scene_garment_is_rejected_before_paid_vision_review(self):
        self.project['productFacts']={'name':'Women sweater'};studio.save_project(self.project)
        with patch.object(image_composition,'_garment',return_value={'coverage':.05,'box':[.4,.4,.6,.6]}):
            result=self.run_image(raster(background='#765b4b',size=(1600,1600)),1)
        self.assertIn('GARMENT_TOO_SMALL',{i['code'] for i in result['qc'][-1]['technical']['issues']})


if __name__=='__main__':unittest.main()
