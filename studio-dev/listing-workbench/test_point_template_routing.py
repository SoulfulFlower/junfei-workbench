import copy,hashlib,json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import app_paths,apparel_suite as apparel,image_engine as engine,official_image_templates as library

def template(identity):
 text='完整官方版式原文 '+identity
 return {'id':identity,'style':'C'+identity,'url':'/template-'+identity+'.png','sha256':identity[0]*64,
  'prompt':text,'promptSha256':hashlib.sha256(text.encode()).hexdigest()}

class PointTemplateRouting(unittest.TestCase):
 def freeze(self,cfg,templates=None,count=3):
  return apparel.freeze_request(cfg,['/source.png'],reference_sha256=['a'*64],templates=templates or[template('1'),template('2')],count=count,no_text=False,brief='保持真实商品结构')
 def test_only_seller_slots_bind_templates_and_each_selected_id_is_used_once(self):
  cfg={'templatePolicy':'point-only-v1','pointTemplateIds':['2','1'],
   'counts':{'white':1,'ins':1,'seller':2,'model':1,'size':1},
   'consistency':{'modelReference':{'url':'/model.png','sha256':'b'*64}},
   'sizeChart':{'source':'isolated fixture','units':'cm','measurementMethod':'fixture','rows':[{'size':'M','length':'60'}]}}
  r=self.freeze(cfg,count=6)
  self.assertEqual([s['officialTemplate']['id']if s['officialTemplate']else None for s in r['slots']],[None,None,None,'2','1',None])
  self.assertEqual(r['templateInvocation']['boundKinds'],['seller'])
 def test_selected_template_count_and_ids_are_checked_before_model_calls(self):
  for ids in [['1'],['1','1'],['missing','2']]:
   with self.subTest(ids=ids),self.assertRaises(ValueError):
    self.freeze({'templatePolicy':'point-only-v1','pointTemplateIds':ids,'counts':{'ins':1,'seller':2}},count=3)
 def test_natural_kind_does_not_need_advertising_assets(self):
  r=apparel.freeze_request({'templatePolicy':'point-only-v1','counts':{'ins':1}},['/source.png'],reference_sha256=['a'*64],templates=[],count=1,no_text=False,brief='自然穿搭')
  self.assertIsNone(r['slots'][0]['officialTemplate'])
  p={'identity':'same top','style':{},'shots':[{'index':0,'kind':'ins','layout':'scene','sourceIndex':0,'copy':['unwanted slogan'],'scene':'window','camera':'front','question':'wearing','evidence':'visible'}]}
  p=apparel.normalize_plan(p,r);s=p['shots'][0];s['apparelReferenceRoles']=apparel.render_references(r,s)
  self.assertEqual(s['copy'],[]);self.assertEqual([v['url']for v in s['apparelReferenceRoles']],['/source.png'])
  prompt=apparel.compile_shot(p,s,r['brief']);self.assertNotIn('OFFICIAL ORIGINAL TEMPLATE id=',prompt)
 def test_legacy_explicit_creative_layouts_keep_their_frozen_meaning(self):
  r=self.freeze({'counts':{'ins':1,'seller':2}})
  self.assertNotIn('templatePolicy',r)
  self.assertEqual([s['officialTemplate']['id']for s in r['slots']],['1','2','1'])
 def test_new_default_uses_ins_without_promising_a_selected_model(self):
  r=self.freeze({'templatePolicy':'point-only-v1'})
  self.assertEqual([s['kind']for s in r['slots']],['white','ins','seller'])
  self.assertIsNone(r['slots'][1]['officialTemplate']);self.assertEqual(r['consistency'],{})
 def test_source_locked_natural_scene_accepts_no_template(self):
  import image_source_layers as layers
  prompt=layers.plate_prompt({'style':{}},{'layout':'scene','copy':[]},None,'natural window scene',True)
  self.assertIn('NO seller template',prompt);self.assertNotIn('Reference image 2',prompt)

class EnginePointIntegration(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  for m,k,v in [(app_paths,'DATA',root),(engine,'DB',root/'engine.sqlite3')]:
   p=patch.object(m,k,v);p.start();self.addCleanup(p.stop)
  self.source=engine.cache(Image.new('RGB',(100,100),'navy'))['url']
  self.ts=[]
  for i,c in [('1','white'),('2','gray')]:
   asset=engine.cache(Image.new('RGB',(100,100),c));t=template(i);t.update(url=asset['url'],sha256=asset['sha256']);self.ts.append(t)
 def start(self,cfg,count,**extra):
  body={'requestId':uuid.uuid4().hex,'mode':'suite','references':[self.source],'brief':'真实服装','count':count,'noText':False,'apparelSuite':cfg,**extra}
  with patch.object(engine,'require_codex',return_value={'outputSize':'1600x1600'}),patch.object(engine,'launch'),patch.object(library,'assignments',return_value=self.ts)as assign:
   task=engine.start(body,{'id':'p','name':'women pants'})
  return task,assign
 def test_server_resolves_selected_seller_ids_without_assigning_to_ins(self):
  t,assign=self.start({'counts':{'ins':1,'seller':2},'pointTemplateIds':['2','1']},3)
  self.assertEqual(assign.call_args.kwargs['requested'],['2','1']);self.assertEqual(assign.call_args.args[1],2)
  r=t['request']['apparelSuite'];self.assertEqual(r['templatePolicy'],'point-only-v1');self.assertIsNone(r['slots'][0]['officialTemplate'])
  self.assertEqual([s['officialTemplate']['id']for s in r['slots'][1:]],['2','1'])
  self.assertEqual(t['request']['pointStyles'][0]['materialSource'],2)
  self.assertEqual(t['request']['pointStyles'][0]['tabType'],'1')
 def test_server_natural_only_does_not_load_unrelated_templates(self):
  t,assign=self.start({'counts':{'ins':1}},1)
  assign.assert_not_called();self.assertEqual(t['request']['officialTemplates'],[])
 def test_explicit_single_free_template_is_not_discarded_as_white_main(self):
  t,_=self.start({},1,layoutTemplateIds=['1'])
  self.assertEqual(t['request']['apparelSuite']['slots'][0]['kind'],'seller')
  self.assertEqual(t['request']['apparelSuite']['slots'][0]['officialTemplate']['id'],'1')
 def test_model_review_receives_selected_person_and_scene_and_blocks_mismatch(self):
  person=self.ts[0]['url'];scene=self.ts[1]['url']
  task={'request':{'mode':'suite','brief':'同一模特场景','apparelSuite':{'templatePolicy':'point-only-v1',
   'consistency':{'modelReference':{'url':person},'sceneReference':{'url':scene},'exactScene':True}}}}
  result={'image':self.source,'shot':{'apparelKind':'model','apparelReferenceRoles':[
   {'url':person,'purpose':'selected consistent model identity only'}, {'url':scene,'purpose':'selected scene/background reference only'}]}}
  with patch.object(engine,'save'),patch.object(engine,'json_model',return_value={'blocking':False,'identityPreserved':True,'modelConsistencyPreserved':False,'sceneConsistencyPreserved':True,'issues':[]})as review:
   engine.review(task,result,self.source)
  self.assertEqual(review.call_args.args[2][-2:],[person,scene]);self.assertTrue(result['review']['blocking'])

if __name__=='__main__':unittest.main()
