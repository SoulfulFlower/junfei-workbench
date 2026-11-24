import json,tempfile,unittest,hashlib,types
from pathlib import Path
import numpy as np
from PIL import Image
from sam2_local_backend import Sam2LocalBackend,sha,write,digest

class LocalCandidateIntegrity(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.calls=0;self.bad=None
  for name in ['worker.py','python.exe','dependencies.json']:(self.root/name).write_text('fixture-'+name,'utf8')
  write(self.root/'model.json',{'model':'fixture','revision':'test','weightSha256':'weight'})
  config={'schema':'junfei.sam2.local.runtime.v1','workerFile':'worker.py','modelManifestFile':'model.json','dependencyManifestFile':'dependencies.json',
   'workerSha256':sha(self.root/'worker.py'),'modelSha256':sha(self.root/'model.json'),'dependenciesSha256':sha(self.root/'dependencies.json'),
   'pythonExecutable':str(self.root/'python.exe'),'pythonSha256':sha(self.root/'python.exe'),'modelName':'fixture','revision':'test','weightSha256':'weight'}
  write(self.root/'runtime.json',config);self.config=config
  self.source=Image.new('RGBA',(20,20),(160,110,70,255))
  self.backend=Sam2LocalBackend(self.root/'runtime.json',runner=self.runner)
 def tearDown(self):self.temp.cleanup()
 def runner(self,command,**kwargs):
  self.calls+=1
  if self.bad=='failure':return types.SimpleNamespace(returncode=1)
  value=lambda flag:Path(command[command.index(flag)+1])
  params_path=value('--params');q=json.loads(params_path.read_text('utf8'));out=value('--output-dir')
  array=np.zeros((20,20),'uint8');array[3:13,3:13]=255
  if self.bad=='point':array[5,5]=0
  Image.fromarray(array).save(out/'mask.png')
  logits=np.where(array>0,4.,-4.).astype('float32');prob=1/(1+np.exp(-logits))
  np.save(out/'logits.npy',logits,allow_pickle=False);np.save(out/'probability.npy',prob,allow_pickle=False)
  write(out/'loading.json',{'missing_keys':[]})
  receipt={'sourceSize':q['sourceSize'],'sourcePixelSha256':q['sourcePixelSha256'],'sourceFileSha256':q['sourceFileSha256'],
   'paramsSha256':sha(params_path),'foreground':q['foreground'],'background':q['background'],'role':q['role'],'workerSha256':self.config['workerSha256'],
   'modelManifestSha256':self.config['modelSha256'],'dependencyManifestSha256':self.config['dependenciesSha256'],
   'model':'fixture','revision':'test','weightSha256':'weight','device':'cpu','unverifiedCandidate':True,
   'maskPixelSha256':hashlib.sha256(array.tobytes()).hexdigest(),'artifacts':{name:sha(out/name)for name in ['mask.png','probability.npy','logits.npy','loading.json']}}
  if self.config.get('inferenceContract')=='native_multimask_all_points_v1':
   np.savez_compressed(out/'proposals.npz',logits=np.stack([logits]*3),scores=np.array([.9,.8,.7]))
   receipt['artifacts']['proposals.npz']=sha(out/'proposals.npz')
   receipt['proposalSelection']={'selectedIndex':1 if self.bad=='choice'else 0,'maskPixelsForced':0}
  if self.bad=='binding':receipt['sourcePixelSha256']='another-source'
  write(out/'receipt.json',receipt);return types.SimpleNamespace(returncode=0)
 def predict(self,**kwargs):return self.backend.predict(self.source,[[5,5]],[[0,0]],cache_root=self.root/'cache',role='garment',**kwargs)
 def test_completed_candidate_replays_without_model_and_never_self_approves(self):
  mask,one=self.predict();second,two=self.predict()
  self.assertEqual(self.calls,1);self.assertEqual(mask.tobytes(),second.tobytes());self.assertTrue(two['cacheReused'])
  self.assertFalse(one['accepted']);self.assertFalse(one['verified']);self.assertTrue(one['unverifiedCandidate'])
  self.assertEqual(one['sourcePixelSha256'],hashlib.sha256(self.source.tobytes()).hexdigest())
 def test_invalid_and_conflicting_points_never_start_inference(self):
  for fg,bg in [([[True,5]],[[0,0]]),([[5,5]],[[5,5]]),([[21,5]],[[0,0]]),([],[[0,0]])]:
   with self.assertRaises(ValueError):self.backend.predict(self.source,fg,bg,cache_root=self.root/'cache',role='garment')
  self.assertEqual(self.calls,0)
 def test_worker_source_binding_failure_is_retained_and_not_retried(self):
  self.bad='binding'
  with self.assertRaisesRegex(ValueError,'source/points'):self.predict()
  self.bad=None
  with self.assertRaisesRegex(ValueError,'retained'):self.predict()
  self.assertEqual(self.calls,1)
 def test_point_contradiction_does_not_silently_force_pixels_or_fallback(self):
  self.bad='point'
  with self.assertRaisesRegex(ValueError,'contradicts'):self.predict()
  self.assertEqual(self.calls,1)
 def test_artifact_tampering_rejects_cache_without_fresh_inference(self):
  _,row=self.predict();path=Path(row['outputDirectory'])/'probability.npy';path.write_bytes(b'tampered')
  with self.assertRaisesRegex(ValueError,'artifact changed'):self.predict()
  self.assertEqual(self.calls,1)
 def test_runtime_file_changes_are_detected_before_model(self):
  (self.root/'worker.py').write_text('different worker','utf8')
  with self.assertRaisesRegex(ValueError,'artifact changed'):self.predict()
  self.assertEqual(self.calls,0)
 def test_failed_worker_is_not_relaunched_as_a_new_paid_or_local_intent(self):
  self.bad='failure'
  with self.assertRaisesRegex(ValueError,'worker failed'):self.predict()
  self.bad=None
  with self.assertRaisesRegex(ValueError,'retained'):self.predict()
  self.assertEqual(self.calls,1)
 def test_native_archive_is_checked_against_selected_logits_and_cache(self):
  self.config['inferenceContract']='native_multimask_all_points_v1';write(self.root/'runtime.json',self.config)
  _,row=self.predict();self.assertEqual(row['workerReceipt']['proposalSelection']['selectedIndex'],0)
  (Path(row['outputDirectory'])/'proposals.npz').write_bytes(b'tampered')
  with self.assertRaisesRegex(ValueError,'proposal artifact'):self.predict()
  self.assertEqual(self.calls,1)
 def test_lower_ranked_choice_cannot_be_substituted_in_native_receipt(self):
  self.config['inferenceContract']='native_multimask_all_points_v1';write(self.root/'runtime.json',self.config);self.bad='choice'
  with self.assertRaisesRegex(ValueError,'proposal selection'):self.predict()
 def test_source_and_object_role_have_separate_immutable_cache_keys(self):
  self.predict();self.backend.predict(self.source,[[5,5]],[[0,0]],cache_root=self.root/'cache',role='occluder')
  self.assertEqual(self.calls,2)
 def test_model_identity_cannot_change_under_an_unchanged_runtime_pin(self):
  write(self.root/'model.json',{'model':'another','revision':'test','weightSha256':'weight'})
  with self.assertRaisesRegex(ValueError,'artifact changed'):self.predict()
  self.assertEqual(self.calls,0)
if __name__=='__main__':unittest.main()
