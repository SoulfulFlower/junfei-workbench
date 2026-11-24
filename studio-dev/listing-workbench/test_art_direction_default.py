import json,tempfile,uuid,unittest
from pathlib import Path
from unittest.mock import patch
import app_paths,image_engine as engine,official_image_templates as library
from PIL import Image
from test_apparel_suite import template

class PromotionTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
  for mod,key,value in [(app_paths,'DATA',root),(engine,'DB',root/'engine.sqlite3')]:
   mock=patch.object(mod,key,value);mock.start();self.addCleanup(mock.stop)
  self.source=engine.cache(Image.new('RGB',(100,100),'pink'))['url'];art=engine.cache(Image.new('RGB',(100,100),'white'));self.art=template();self.art.update(url=art['url'],sha256=art['sha256'])
 def data(self,**kwargs):
  return {'productId':'p','requestId':uuid.uuid4().hex,'mode':'suite','references':[self.source],
    'brief':'Actual jacket','count':1,'noText':False,'apparelSuite':{'counts':{'seller':1}},**kwargs}
 def start(self,data):
  with patch.object(engine,'require_codex',return_value={'outputSize':'1600x1600'}),patch.object(engine,'launch'),patch.object(library,'assignments',return_value=[self.art]):return engine.start(data,{'id':'p','name':'women jacket'})
 def test_new_default_is_applied_only_to_generative_creative_apparel(self):
  task=self.start(self.data());self.assertEqual(task['request']['apparelSuite']['artDirection'],'template-led-v1')
  locked=self.start(self.data(preserveSourcePixels=True));self.assertNotIn('artDirection',locked['request']['apparelSuite'])
  legacy=self.start(self.data(apparelSuite={'counts':{'seller':1},'artDirection':'legacy-v1'}));self.assertNotIn('artDirection',legacy['request']['apparelSuite'])
 def test_existing_legacy_intent_keeps_identical_signature_without_relaunch(self):
  data=self.data(apparelSuite={'counts':{'seller':1},'artDirection':'legacy-v1'});old=self.start(data)
  old['status']='submission_unknown';engine.save(old);data['apparelSuite'].pop('artDirection')
  again=self.start(data);self.assertEqual(again['id'],old['id']);self.assertEqual(again['signature'],old['signature']);self.assertEqual(again['status'],'submission_unknown')
 def test_recovery_inherits_original_policy_and_rejects_cross_product(self):
  old=self.start(self.data(apparelSuite={'counts':{'seller':1},'artDirection':'legacy-v1'}))
  self.assertEqual(engine.default_art_direction({'requestId':uuid.uuid4().hex,'reusePlanTaskId':old['id']},'p'),'legacy-v1')
  with self.assertRaises(ValueError):engine.default_art_direction({'requestId':uuid.uuid4().hex,'reusePlanTaskId':old['id']},'other')
  with self.assertRaises(ValueError):engine.default_art_direction({'requestId':old['requestId']},'other')
 def test_unknown_recovery_does_not_become_a_fresh_default(self):
  with self.assertRaises(ValueError):engine.default_art_direction({'requestId':uuid.uuid4().hex,'reusePlanTaskId':'missing'},'p')

if __name__=='__main__':unittest.main()
