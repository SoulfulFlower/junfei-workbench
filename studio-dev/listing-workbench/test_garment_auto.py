import base64,unittest,os,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PIL import Image
import garment_auto as auto
import garment_workflow
import pixel_recolour as pixel
import test_pixel_recolour as fixtures


class AutomaticModelTests(unittest.TestCase):
 def test_product_category_does_not_choose_models_trousers_for_a_top(self):
  for name,expected in [('女士罗纹上衣','upper'),('Womens blouse','upper'),('女士连衣裙','full'),('Wide leg pants','lower'),('半身裙','lower'),('未知','auto'),("Women's Stand Collar Half Zip Fleece Pullover with Pockets",'upper'),('Collared Cardigan','upper')]:self.assertEqual(auto.category({'name':name}),expected)
  labels=np.zeros((100,100),'uint8');labels[5:35,5:25]=1;labels[40:95,5:95]=2
  mask,kind,counts=auto.choose(labels,auto.category({'name':'Womens blouse'}));self.assertEqual(kind,'upper');self.assertEqual(mask.sum(),600)
 def test_cropped_upper_can_use_independent_upper_cloth_labels_instead_of_styling_trousers(self):
  labels=np.zeros((100,100),'uint8');labels[60:100,5:35]=2
  human=np.zeros_like(labels);human[10:60,20:85]=4;human[60:100,5:35]=6
  mask,category,counts=auto.choose(labels,'upper',human)
  self.assertEqual(category,'upper');self.assertEqual(counts,[0,1200,0])
  np.testing.assert_array_equal(mask,human==4)
  with self.assertRaises(ValueError):auto.choose(labels,'upper',np.zeros_like(labels))
 def test_upper_fallback_does_not_override_conflicting_primary_clothing_labels(self):
  labels=np.zeros((100,100),'uint8');labels[55:90,20:80]=2
  human=np.zeros_like(labels);human[20:90,20:80]=4
  mask,_,_=auto.choose(labels,'upper',human)
  self.assertFalse(mask[60,55]);self.assertTrue(mask[30,55])
 def test_cropped_upper_has_deep_foreground_across_the_visible_garment(self):
  semantic=np.zeros((100,120),bool);semantic[10:90,10:108]=True
  semantic[10:90,55:64]=False
  points=auto.cropped_upper_points(semantic)
  self.assertEqual(len(points),4)
  self.assertTrue(all(semantic[y,x] for x,y in points))
  self.assertEqual({x<60 for x,_ in points},{False,True})
 def test_generated_prompts_include_disconnected_fabric_and_exclude_other_regions(self):
  labels=np.zeros((100,100),'uint8');labels[10:80,10:55]=1;labels[30:40,65:75]=1;labels[80:,20:70]=2
  mask=labels==1;fg,bg=auto.model_prompts(mask,labels)
  self.assertTrue(any(65<=x<75 and 30<=y<40 for x,y in fg));self.assertTrue(all(mask[y,x] for x,y in fg));self.assertTrue(all(not mask[y,x] for x,y in bg))
 def test_blank_or_whole_image_segmentation_is_not_reported_as_success(self):
  for labels in (np.zeros((100,100),'uint8'),np.ones((100,100),'uint8')):
   with self.assertRaises(ValueError):auto.choose(labels,'upper')
 def test_automatic_pipeline_requires_no_user_points_and_respects_protection(self):
  labels=np.zeros((100,100),'uint8');labels[20:80,20:80]=1
  rgb=np.full((100,100,3),255,'uint8');rgb[20:80,20:80]=[80,40,50]
  protected=np.zeros((100,100),'uint8');protected[25:30,25:30]=255
  class Engine:
   def predict(self,source):return labels
  class Human:
   def predict(self,source):return np.where(labels==1,4,0).astype('uint8')
  def select(source,evidence,cache):
   self.assertGreater(len(evidence['foreground']),0)
   return Image.fromarray((labels==1).astype('uint8')*255),labels==1,[[0,0]],{'humanReviewed':False}
  with patch.object(auto,'sam_proposals',side_effect=select):mask,receipt=auto.identify(Image.fromarray(rgb),Image.fromarray(protected),'unused','upper',Engine(),Human())
  self.assertTrue(receipt['automatic']);self.assertFalse(receipt['userPointsRequired']);self.assertFalse(receipt['imageGenerationSubmitted']);self.assertFalse(receipt['humanReviewed'])
  self.assertEqual(np.asarray(mask)[27,27],0)
 def test_human_parser_preserves_original_schp_bgr_training_order(self):
  source=Image.new('RGB',(2,2),(255,0,128));before=source.tobytes()
  values=auto.HumanParser.input(source)
  self.assertEqual(values.shape,(1,3,512,512))
  np.testing.assert_allclose(values[0,:,0,0],[(128/255-.406)/.225,(0-.456)/.224,(1-.485)/.229],rtol=1e-5)
  self.assertEqual(source.tobytes(),before)
 def test_false_semantic_hair_and_bag_islands_do_not_become_foreground_points(self):
  labels=np.zeros((100,100),'uint8');labels[30:90,10:60]=1;labels[10:40,70:90]=1
  rgb=np.full((100,100,3),240,'uint8');rgb[labels==1]=[40,40,40]
  rgb[10:40,70:90]=[145,95,40]
  human=np.zeros((100,100),'uint8');human[10:40,70:90]=2
  evidence=auto.automatic_evidence(Image.fromarray(rgb),labels==1,labels,human,'upper',Image.new('L',(100,100)))
  self.assertTrue(evidence['protected'][20,80])
  self.assertEqual(len(evidence['foreground']),1)
  self.assertTrue(all(10<=x<60 and 30<=y<90 for x,y in evidence['foreground']))
 def test_cropped_same_colour_sleeve_mislabelled_as_arm_or_pants_is_not_hard_background(self):
  labels=np.zeros((100,100),'uint8');labels[20:90,10:70]=1;labels[40:80,10:30]=2
  rgb=np.full((100,100,3),240,'uint8');rgb[20:90,10:70]=[40,40,40]
  human=np.zeros((100,100),'uint8');human[40:80,10:30]=6;human[40:80,30:45]=14
  evidence=auto.automatic_evidence(Image.fromarray(rgb),labels==1,labels,human,'upper',Image.new('L',(100,100)))
  self.assertFalse(evidence['other'][50,20]);self.assertFalse(evidence['protected'][50,35])
 def test_rejected_sam_candidates_never_fall_back_to_forced_semantic_union(self):
  class Model:
   def select(self,*args):raise ValueError('Contradictory automatic prompts')
  mask=np.zeros((30,30),bool);mask[10:20,10:20]=True
  evidence={'foreground':[[15,15]],'border':[[0,0]],'background':[],
   'clean':mask,'protected':~mask,'other':np.zeros(mask.shape,bool)}
  with patch.object(garment_workflow,'selector',return_value=Model()),self.assertRaisesRegex(ValueError,'候选均未通过'):
   auto.sam_proposals(Image.new('RGB',(30,30)),evidence,'unused')
 def test_semantic_letter_outside_all_sam_proposals_cannot_become_foreground(self):
  shape=(150,150);labels=np.zeros(shape,'uint8');labels[30:110,20:70]=1;labels[40:60,110:125]=1
  rgb=np.full((*shape,3),240,'uint8');rgb[labels==1]=[40,40,40]
  main=np.zeros(shape,bool);main[30:110,20:70]=True
  evidence={'foreground':[[45,70]],'clean':labels==1,'protected':np.zeros(shape,bool),
   'other':np.zeros(shape,bool),'distance':auto.fabric_distance(Image.fromarray(rgb),labels==1)}
  mask=auto.complete_edges(Image.fromarray(rgb),Image.fromarray(main.astype('uint8')*255),main,evidence,labels,'upper',[[0,0]])
  self.assertEqual(np.asarray(mask)[50,115],0);self.assertEqual(np.asarray(mask)[70,45],255)
 def test_contrasting_seams_protect_the_whole_agreed_dark_trousers_not_only_highlights(self):
  candidate=np.zeros((80,80),bool);candidate[30:75,20:65]=True;candidate[5:20,5:15]=True
  distance=np.zeros(candidate.shape,'float32');distance[30:75,20:23]=30
  result=auto.contrast_components(candidate,distance)
  self.assertTrue(result[50,50]);self.assertTrue(np.all(result[30:75,20:65]))
  self.assertFalse(result[10,10])
 def test_same_fabric_shoulder_mislabelled_as_hair_does_not_create_a_hard_hole(self):
  labels=np.zeros((100,100),'uint8');labels[30:90,10:90]=1
  rgb=np.full((100,100,3),240,'uint8');rgb[30:90,10:90]=[40,40,40]
  human=np.zeros((100,100),'uint8');human[30:60,60:90]=2;human[5:25,20:50]=2
  rgb[5:25,20:50]=[145,95,40]
  evidence=auto.automatic_evidence(Image.fromarray(rgb),labels==1,labels,human,'upper',Image.new('L',(100,100)))
  self.assertFalse(evidence['protected'][45,75]);self.assertTrue(evidence['protected'][15,35])
 def test_only_best_clothing_object_can_relax_false_hair_not_an_alternative_person_mask(self):
  shape=(150,150);main=np.zeros(shape,bool);main[40:120,55:120]=True
  hair=np.zeros(shape,bool);hair[10:100,20:40]=True;hair[70:90,70:90]=True
  union=main|hair;labels=np.zeros(shape,'uint8');labels[union]=1
  rgb=np.full((*shape,3),240,'uint8');rgb[union]=[40,40,40]
  evidence={'foreground':[[85,80]],'clean':labels==1,'protected':np.zeros(shape,bool),
   'hairProtection':hair,'other':np.zeros(shape,bool),'distance':auto.fabric_distance(Image.fromarray(rgb),labels==1)}
  mask=auto.complete_edges(Image.fromarray(rgb),Image.fromarray(main.astype('uint8')*255),union,evidence,labels,'upper',[[0,0]])
  self.assertEqual(np.asarray(mask)[50,30],0)
  self.assertEqual(np.asarray(mask)[80,80],255)
 def test_low_scoring_whole_person_candidate_does_not_expand_recovery_domain(self):
  shape=(100,100);main=np.zeros(shape,bool);main[20:80,30:70]=True
  protected=np.zeros(shape,bool);protected[:20,:]=True;protected[80:,:]=True
  class Model:
   calls=0
   def select(self,*args):
    self.calls+=1;mask=main if self.calls==1 else np.ones(shape,bool)
    return Image.fromarray(mask.astype('uint8')*255),{'predictedIou':.95}
  evidence={'foreground':[[50,50]],'border':[[0,0]],'background':[[99,99]],'clean':main,
   'protected':protected,'other':np.zeros(shape,bool)}
  with patch.object(garment_workflow,'selector',return_value=Model()):
   best,union,background,receipt=auto.sam_proposals(Image.new('RGB',(100,100)),evidence,'unused')
  np.testing.assert_array_equal(union,main)
 def test_semantic_and_sam_filled_elbow_opening_stays_background(self):
  shape=(150,150);main=np.zeros(shape,bool);main[20:130,20:130]=True
  labels=main.astype('uint8');rgb=np.full((*shape,3),240,'uint8');rgb[main]=[40,40,40]
  rgb[50:80,55:75]=[232,220,205]
  evidence={'foreground':[[95,95]],'clean':main,'protected':np.zeros(shape,bool),
   'other':np.zeros(shape,bool),'distance':auto.fabric_distance(Image.fromarray(rgb),main)}
  mask=auto.complete_edges(Image.fromarray(rgb),Image.fromarray(main.astype('uint8')*255),main,evidence,labels,'upper',[[0,0]])
  self.assertEqual(np.asarray(mask)[65,65],0)
  self.assertEqual(np.asarray(mask)[95,95],255)
 def test_body_domain_excludes_a_same_colour_window_frame_selected_by_sam(self):
  shape=(150,150);main=np.zeros(shape,bool);main[20:130,30:130]=True
  frame=np.zeros(shape,bool);frame[10:100,5:15]=True
  selected=main|frame;labels=selected.astype('uint8');human=np.where(main,4,0).astype('uint8')
  rgb=np.full((*shape,3),240,'uint8');rgb[selected]=[40,40,40]
  evidence={'foreground':[[95,95]],'clean':selected,'protected':np.zeros(shape,bool),'other':np.zeros(shape,bool),
   'distance':auto.fabric_distance(Image.fromarray(rgb),selected),'bodyDomain':auto.body_domain(human)}
  mask=auto.complete_edges(Image.fromarray(rgb),Image.fromarray(selected.astype('uint8')*255),selected,evidence,labels,'upper',[[0,0]])
  self.assertEqual(np.asarray(mask)[65,10],0);self.assertEqual(np.asarray(mask)[95,95],255)
 def test_body_domain_keeps_clothing_mislabelled_as_hair_pants_or_arm(self):
  human=np.zeros((100,100),'uint8');human[10:90,20:80]=4
  for index,label in enumerate([2,6,14,15]):human[20+index*10:30+index*10,30:60]=label
  domain=auto.body_domain(human)
  self.assertTrue(np.all(domain[10:90,20:80]))
  self.assertFalse(domain[0,0])
 def test_near_hair_recovery_requires_clothing_anchors_and_rejects_long_hair(self):
  shape=(200,200);seed=np.zeros(shape,bool);seed[20:180,60:170]=True
  hair=np.zeros(shape,bool);hair[40:48,55:60]=True;hair[60:150,55:60]=True;hair[155:163,55:60]=True
  clothing=seed.copy();clothing[40:48,55:60]=True;clothing[60:150,55:60]=True;clothing[155:156,55:60]=True
  recovered=auto.near_hair_recovery(seed,hair,np.zeros(shape),clothing)
  self.assertTrue(recovered[44,57])
  self.assertFalse(recovered[100,57])
  self.assertFalse(recovered[160,57])
 def test_body_domain_closes_an_internal_parser_void_without_including_a_far_window(self):
  human=np.zeros((200,200),'uint8');human[20:180,60:180]=4;human[80:86,110:116]=0
  domain=auto.body_domain(human)
  self.assertTrue(domain[82,112]);self.assertFalse(domain[80,20])
 def texture_fixture(self,crossed=False):
  shape=(200,200);y,x=np.indices(shape)
  seed=np.zeros(shape,bool);seed[20:180,60:170]=True
  hair=np.zeros(shape,bool);hair[60:70,54:60]=True
  gray=70+12*np.sin(x*2*np.pi/6)
  if crossed:gray[55:75,49:65]=(70+12*np.sin(y*2*np.pi/6))[55:75,49:65]
  source=Image.fromarray(np.repeat(gray.astype('uint8')[:,:,None],3,2))
  return seed,hair,source
 def test_fine_fabric_island_missed_by_both_parsers_can_use_nearby_matching_texture(self):
  seed,hair,source=self.texture_fixture();before=source.tobytes()
  recovered=auto.near_hair_recovery(seed,hair,np.zeros(seed.shape),seed,source)
  self.assertTrue(recovered[65,58]);self.assertFalse(recovered[65,54])
  self.assertEqual(source.tobytes(),before)
 def test_small_same_colour_hair_with_crossed_texture_is_not_recoloured(self):
  seed,hair,source=self.texture_fixture(crossed=True)
  recovered=auto.near_hair_recovery(seed,hair,np.zeros(seed.shape),seed,source)
  self.assertFalse(recovered.any())
 def supported_fabric_fixture(self,crossed=False):
  shape=(200,200);y,x=np.indices(shape)
  clothing=np.zeros(shape,bool);clothing[20:180,60:170]=True
  island=np.zeros(shape,bool);island[60:70,45:55]=True
  seed=clothing.copy();seed[63:68,52:55]=True
  gray=70+12*np.sin(x*2*np.pi/6)
  if crossed:gray[55:75,40:58]=(70+12*np.sin(y*2*np.pi/6))[55:75,40:58]
  source=Image.fromarray(np.repeat(gray.astype('uint8')[:,:,None],3,2))
  return seed,clothing,island,source
 def test_human_cloth_island_missed_by_u2net_requires_sam_support_and_source_texture(self):
  seed,clothing,island,source=self.supported_fabric_fixture()
  recovered,_=auto.small_supported_fabric(seed,island,np.zeros(seed.shape),clothing,source)
  self.assertTrue(np.all(recovered[island]))
  self.assertFalse(auto.small_supported_fabric(clothing,island,np.zeros(seed.shape),clothing,source)[0].any())
 def test_crossed_hair_texture_cannot_use_false_human_clothing_and_partial_sam(self):
  seed,clothing,island,source=self.supported_fabric_fixture(crossed=True)
  self.assertFalse(auto.small_supported_fabric(seed,island,np.zeros(seed.shape),clothing,source)[0].any())
 def test_supported_fabric_restoration_preserves_overlapping_distinct_colour_hair(self):
  seed,clothing,island,source=self.supported_fabric_fixture()
  distance=np.zeros(seed.shape);distance[60:70,49]=30
  recovered,_=auto.small_supported_fabric(seed,island,distance,clothing,source)
  self.assertTrue(recovered[65,52]);self.assertFalse(recovered[65,49])
 def test_new_fabric_island_keeps_warm_dark_strands_even_with_small_fabric_distance(self):
  seed,clothing,island,source=self.supported_fabric_fixture()
  rgb=np.asarray(source).copy();rgb[60:70,49]+=np.array([8,0,0],'uint8');source=Image.fromarray(rgb)
  recovered,fibres=auto.small_supported_fabric(seed,island,np.zeros(seed.shape),clothing,source)
  self.assertTrue(recovered[65,52]);self.assertFalse(recovered[65,49]);self.assertTrue(fibres[65,49])
 def test_already_supported_cloth_is_not_given_a_new_chroma_cut(self):
  seed,clothing,island,source=self.supported_fabric_fixture()
  rgb=np.asarray(source).copy();rgb[60:70,49]+=np.array([8,0,0],'uint8');source=Image.fromarray(rgb)
  recovered,fibres=auto.small_supported_fabric(seed,island,np.zeros(seed.shape),clothing|island,source)
  self.assertFalse(recovered.any());self.assertFalse(fibres.any())
 def test_matting_uses_explicit_account_cache_even_if_numba_was_imported_before(self):
  config=SimpleNamespace(CACHE_DIR='read-only-site-packages')
  with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,{'numba':SimpleNamespace(config=config),'pymatting':SimpleNamespace()}),patch.dict(os.environ,{'NUMBA_CACHE_DIR':'unwritable-user-default'}):
   for account in ['account-a','account-b']:
    folder=Path(tmp)/account/'numba-cache';auto.prepare_matting(folder)
    self.assertTrue(folder.is_dir());self.assertEqual(config.CACHE_DIR,str(folder.resolve()))
    self.assertEqual(os.environ['NUMBA_CACHE_DIR'],str(folder.resolve()))
 def test_reliable_clothing_has_no_accessory_smoothing_or_matting(self):
  shape=(180,180);selected=np.zeros(shape,bool);selected[20:160,20:130]=True
  bag=np.zeros(shape,bool);bag[40:150,130:170]=True
  evidence={'bagLabels':bag,'clothing':selected}
  with patch.object(auto,'prepare_matting') as factory:
   result=auto.automatic_edge_alpha(Image.new('RGB',(180,180)),selected,selected,evidence,np.zeros(shape,bool),np.zeros(shape,bool))
  factory.assert_not_called();np.testing.assert_array_equal(np.asarray(result)>127,selected)
 def test_weak_bag_edge_only_subtracts_and_local_solves_keep_core_and_protection(self):
  shape=(260,260);seed=np.zeros(shape,bool);seed[20:240,20:100]=True
  selected=seed.copy();selected[30:230,100:130]=True;selected[100:130,130:139]=True
  bag=np.zeros(shape,bool);bag[20:240,130:230]=True
  protection=np.zeros(shape,bool);protection[110:115,135:140]=True
  evidence={'bagLabels':bag,'clothing':seed,'matteCache':'isolated-account/numba-cache'}
  calls=[]
  def matte(source,mask,protected,radius):
   calls.append(source.size);values=np.asarray(mask,dtype=float)/255*.6;values[np.asarray(protected)>0]=0;return values
  original=Image.new('RGB',(260,260),(20,20,20));before=original.tobytes()
  with patch.object(auto,'prepare_matting',return_value=matte):
   result=np.asarray(auto.automatic_edge_alpha(original,selected,seed,evidence,protection,np.zeros(shape,bool)))
  self.assertGreater(evidence['edgeRefinement']['trimmedPixels'],0)
  self.assertTrue(calls);self.assertTrue(all(max(size)<=120 for size in calls))
  self.assertTrue(np.all(result[~selected]==0));self.assertTrue(np.all(result[protection]==0))
  self.assertEqual(result[130,60],255);self.assertTrue(np.any((result>0)&(result<255)))
  self.assertEqual(original.tobytes(),before)


class AutomaticBoundaryTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.PixelTests('test_selection_restores_protection_and_optimistic_revision');self.fixture.setUp()
 def tearDown(self):self.fixture.tearDown()
 def test_model_selection_saves_once_reuses_existing_and_rechecks_after_inference(self):
  f=self.fixture;data={**f.row,'revision':0}
  with patch.object(auto,'identify',return_value=(f.mask,{'automatic':True,'humanReviewed':False,'imageGenerationSubmitted':False})) as model:
   first=pixel.automatic_selection(data,f.product);self.assertEqual(first['selection']['revision'],1);self.assertFalse(first['selection']['humanReviewed'])
   again=pixel.automatic_selection({**data,'revision':1},f.product);self.assertTrue(again['reused']);self.assertEqual(model.call_count,1)
   with self.assertRaises(ValueError):pixel.automatic_selection(data,f.product)
 def test_concurrent_manual_save_is_preserved_instead_of_overwritten(self):
  f=self.fixture
  def infer(*args):f.save();return f.mask,{'automatic':True}
  with patch.object(auto,'identify',side_effect=infer),self.assertRaisesRegex(ValueError,'已被修改'):pixel.automatic_selection({**f.row,'revision':0},f.product)
  self.assertEqual(pixel.selection(f.row,f.product)['selection']['revision'],1)
 def test_uploaded_image_can_render_without_becoming_an_approved_product_master(self):
  f=self.fixture;upload=pixel.uploaded_source({'uploadedSource':f.url},f.product)['source'];self.assertEqual(upload['slot'],-1)
  with patch.object(auto,'identify',return_value=(f.mask,{'automatic':True})):
   selected=pixel.automatic_selection({**upload,'revision':0},f.product)
  result=pixel.render({**upload,'revision':1,'target':'#00913e'},f.product);self.assertEqual(result['slot'],-1)
  self.assertIsNone(pixel.selection(f.row,f.product)['selection']);self.assertEqual(len(pixel.sources(f.product)['sources']),1)
  with self.assertRaisesRegex(ValueError,'独立预览'):pixel.commit({'renderId':result['id'],'id':'set'},f.product)
  for url in ('https://example.test/source.png','/uploads/../other.png','/uploads/missing.png'):
   with self.assertRaises(ValueError):pixel.uploaded_source({'uploadedSource':url},f.product)
 def test_absent_product_card_is_preserved_without_running_segmentation(self):
  f=self.fixture;s=pixel.colour_sets.get('set');s['items'][0]['productAbsent']=True;pixel.colour_sets.save(s)
  with patch.object(auto,'identify') as model:
   record=pixel.automatic_selection({**f.row,'revision':0},f.product)['selection'];model.assert_not_called()
  self.assertTrue(record['preserveWholeImage']);self.assertTrue(np.all(np.asarray(pixel.image(record['protected']))==255))


if __name__=='__main__':unittest.main()
