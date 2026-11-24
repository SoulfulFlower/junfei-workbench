import copy,itertools,unittest
from unittest.mock import Mock
import lifestyle_variety as variety
import apparel_suite as apparel
from test_apparel_suite import template

class LifestyleTemplateTests(unittest.TestCase):
 def plan(self):
  return {'shots':[{'index':i,'apparelKind':'ins','officialTemplate':template(str(200+i)),
    'lifestylePresentation':dict(zip(variety.FIELDS,values))} for i,values in enumerate([
    ('garden','blonde short curls','walking','three quarter','left lead','navy trousers'),
    ('home reading nook','brunette bob','seated','upper thigh','right lead','ivory jeans'),
    ('studio','black high ponytail','standing','knee up','centered','dark skirt')])]}
 def task(self):
  return {'plan':self.plan(),'request':{'brief':'Use different source-backed templates','references':['/source.png']},'results':[{'index':i,'image':f'/output{i}.png','review':{'blocking':False,'identityPreserved':True}} for i in range(3)]}
 def answer(self):
  return {'blocking':False,'issues':[],'warnings':[],'pairs':[{'left':a,'right':b,'sceneDistinct':True,'modelDistinct':True,'presentationDistinct':True,'evidence':'Visible scene and adult main wearer differences'} for a,b in itertools.combinations(range(3),2)]}
 def test_template_routing_keeps_all_seven_counts_and_separate_kinds(self):
  templates=[template(str(i)) for i in (101,102,201,202,203)]
  chart={'source':'https://supplier.test','units':'cm','measurementMethod':'Garment measurements','rows':[{'size':'M','Chest':'82'}]}
  recipe=apparel.freeze_request({'counts':{'white':1,'seller':2,'ins':3,'size':1},'shotOrder':['white','seller','seller','ins','ins','ins','size'],'templatePolicy':'point-only-v1','pointTemplateIds':['101','102'],'useLifestyleTemplates':True,'lifestyleTemplateIds':['201','202','203'],'sizeChart':chart},['/source.png'],reference_sha256=['a'*64],templates=templates,count=7,no_text=False,brief='Use original templates')
  self.assertEqual([s['officialTemplate']['id'] if s['officialTemplate'] else None for s in recipe['slots']],[None,'101','102','201','202','203',None])
  proposal={'shots':[{'kind':s['kind'],'layout':s['allowedLayouts'][0],'sourceIndex':0,'copy':['Pale pink jacket']} for s in recipe['slots']]}
  normal=apparel.normalize_plan(proposal,recipe)
  self.assertEqual(normal['shots'][3]['copy'],['Pale pink jacket'])
  self.assertEqual(normal['shots'][0]['copy'],[])
 def test_missing_or_repeated_template_and_repeated_model_do_not_pass(self):
  variety.validate_plan(self.plan())
  for field in ('settingFamily','modelAppearance','styling'):
   plan=self.plan();plan['shots'][1]['lifestylePresentation'][field]=plan['shots'][0]['lifestylePresentation'][field]
   with self.assertRaises(ValueError):variety.validate_plan(plan)
  plan=self.plan();plan['shots'][1]['officialTemplate']=copy.deepcopy(plan['shots'][0]['officialTemplate'])
  with self.assertRaises(ValueError):variety.validate_plan(plan)
 def test_actual_pair_rejection_cannot_be_overridden_by_top_level_pass(self):
  answer=self.answer();answer['pairs'][1]['modelDistinct']=False
  model=Mock(return_value=answer);review=variety.review_set(self.task(),model)
  self.assertTrue(review['blocking']);self.assertTrue(review['issues'])
  self.assertEqual(model.call_args.args[2],['/source.png','/output0.png','/output1.png','/output2.png'])
  self.assertFalse(review['automaticSetRegenerationPerformed'])
 def test_missing_pairs_or_unknown_conclusions_do_not_pass(self):
  for answer in [{**self.answer(),'pairs':self.answer()['pairs'][:2]},{**self.answer(),'blocking':None}]:
   with self.assertRaises(ValueError):variety.review_set(self.task(),Mock(return_value=answer))
 def test_single_image_failure_still_blocks_and_never_repeats_generation(self):
  task=self.task();task['results'][0]['review']['blocking']=True;model=Mock()
  self.assertTrue(variety.review_set(task,model)['blocking']);model.assert_not_called()
 def test_default_templates_are_distinct_original_assets(self):
  library=Mock();library.entries.return_value=[{'id':str(i),'style':s} for i,s in enumerate(['C15','C17','C30','C6'])]
  self.assertEqual(variety.choose_template_ids(library,3),['0','1','2'])
  with self.assertRaises(ValueError):variety.choose_template_ids(library,3,['0','0','1'])
 def test_planned_person_and_staging_reach_the_actual_render_prompt(self):
  from apparel_art_direction import compile_shot,DESIGN_FIELDS
  shot=self.plan()['shots'][0];shot['templateDesign']={'templateId':shot['officialTemplate']['id'],**{k:'Specific original artwork observation' for k in DESIGN_FIELDS}}
  recipe={'aspectRatio':'1:1','slots':[{'officialTemplate':shot['officialTemplate']}],'productFacts':{},'brief':'Different adult models and source-accurate garment'}
  prompt=compile_shot({'identity':'Same real jacket','style':{}},shot,recipe,shot['officialTemplate'],[],allow_text=False)
  self.assertIn(shot['lifestylePresentation']['modelAppearance'],prompt)
  self.assertIn(shot['lifestylePresentation']['styling'],prompt)
  self.assertIn('[CURRENT LIFESTYLE PERSON AND STAGING]',prompt)
  self.assertIn('not the identity or hairstyle',prompt)
 def recovery_fixture(self):
  task=self.task();task.update(id='parent',productId='own',status='needs_revision',automaticCorrections=[{'slot':0}],attempts=[])
  task['request'].update(mode='suite',count=3,lifestyleVarietyPolicy=variety.POLICY,referenceSha256=['a'*64],apparelSuite={})
  task['lifestyleSetReview']=self.answer();task['lifestyleSetReview']['blocking']=True;task['lifestyleSetReview']['pairs'][-1]['modelDistinct']=False
  for r in task['results']:r.update(providerJobId=str(r['index']),raw='raw'+str(r['index']),rawSha256='sha'+str(r['index']),prompt='Old prompt omitted the person field')
  asset=lambda url:(None,'sha'+url[-1] if url.startswith('raw') else 'outputhash')
  poll=lambda job:{'status':'completed','images':['raw'+job]}
  return task,asset,poll
 def test_proven_field_omission_keeps_passed_images_and_remaining_retry_budget(self):
  task,asset,poll=self.recovery_fixture();recipe=copy.deepcopy(task['request']);recipe['lifestylePromptPolicy']='explicit-presentation-v1'
  recovery=variety.prepare_recovery(recipe,task,'own',asset,poll)
  self.assertEqual(recovery['revisionSlots'],[1]);self.assertEqual(recovery['results'][0]['image'],'/output0.png')
  self.assertFalse(recovery['planningRepeated']);self.assertEqual(recovery['maximumCorrectionsPerSlotAcrossLineage'],1)
  for field,value in [('status','submission_unknown'),('productId','foreign')]:
   bad=copy.deepcopy(task);bad[field]=value
   with self.assertRaises(ValueError):variety.prepare_recovery(recipe,bad,'own',asset,poll)
 def test_recovery_rejects_fixed_prompt_recursive_retry_or_changed_input(self):
  task,asset,poll=self.recovery_fixture();recipe=copy.deepcopy(task['request'])
  for mutate in [lambda t:t['request'].update(lifestylePromptPolicy='explicit-presentation-v1'),
                 lambda t:t['results'][1].update(prompt=t['plan']['shots'][1]['lifestylePresentation']['modelAppearance']),
                 lambda t:t['automaticCorrections'].extend([{'slot':1},{'slot':2}])]:
   bad=copy.deepcopy(task);mutate(bad)
   with self.assertRaises(ValueError):variety.prepare_recovery(recipe,bad,'own',asset,poll)
  with self.assertRaises(ValueError):variety.prepare_recovery({**recipe,'brief':'different request'},task,'own',asset,poll)

if __name__=='__main__':unittest.main()
