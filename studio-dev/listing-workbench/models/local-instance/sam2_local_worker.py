"""Offline CPU point predictor for a grounded LOCAL source crop; no acceptance."""
from pathlib import Path
import argparse,hashlib,importlib.metadata as md,json,os,sys,time

REV='665f8e2ad61cf5f53d65644ff27c8ee525124610'
WEIGHT='dc407dce21301fd94abb395c5099b4f2c455fdc8a8f261ac3d0ea6d4cd197230'
VERSION='sam2-grounded-local-worker-v3-native-single-and-multimask'

def choose_native_proposal(logits,scores,foreground,background):
 import numpy as np
 values=np.asarray(logits);quality=np.asarray(scores).reshape(-1)
 if values.ndim!=3 or len(quality)!=len(values)or not np.isfinite(values).all()or not np.isfinite(quality).all():
  raise ValueError('Native proposals are incomplete or non-finite')
 candidates=[]
 for i,mask in enumerate(values>0):
  hits=sum(bool(mask[int(y),int(x)])for x,y in foreground)
  leaks=sum(bool(mask[int(y),int(x)])for x,y in background)
  candidates.append({'index':i,'foregroundHits':hits,'foregroundCount':len(foreground),
   'backgroundHits':leaks,'valid':hits==len(foreground)and leaks==0,'predictedIou':float(quality[i])})
 valid=[r for r in candidates if r['valid']]
 if not valid:raise ValueError('No native SAM2 proposal satisfies every grounded point; not forcing pixels')
 chosen=max(valid,key=lambda r:(r['predictedIou'],-r['index']))['index']
 return chosen,{'method':'native_multimask_all_points_v1','selectedIndex':chosen,'candidates':candidates,
  'maskPixelsForced':0,'scoreIsNotQualityAcceptance':True}
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['source','params','model-manifest','dependencies','output-dir']:p.add_argument('--'+key,required=True)
 p.add_argument('--threads',type=int,default=4);a=p.parse_args()
 if not 1<=a.threads<=16:raise ValueError('CPU threads must be 1..16')
 source=Path(a.source).resolve(strict=True);params_path=Path(a.params).resolve(strict=True)
 out=Path(a.output_dir).resolve()
 if out.exists()and any(out.iterdir()):raise ValueError('Worker output must be new or empty')
 out.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
 q=json.loads(params_path.read_text('utf8'));manifest_path=Path(a.model_manifest).resolve(strict=True)
 m=json.loads(manifest_path.read_text('utf8'));deps=json.loads(Path(a.dependencies).read_text('utf8'))
 if q.get('schema')!='junfei.grounded-local-points.v1'or q.get('manualPointsAdded')is not False:raise ValueError('Local points require automatic provenance')
 if m.get('model')!='facebook/sam2.1-hiera-large'or m.get('revision')!=REV or m.get('weightSha256')!=WEIGHT:raise ValueError('Wrong model pin')
 for name,item in m['files'].items():
  path=(manifest_path.parent/'model'/name).resolve();path.relative_to((manifest_path.parent/'model').resolve())
  if sha(path)!=item['sha256']:raise ValueError('Model artifact hash mismatch: '+name)
 if sha(source)!=q['sourceFileSha256']:raise ValueError('Local source file changed')
 os.environ.update(HF_HOME=str(out/'cache'),HF_HUB_CACHE=str(out/'cache/hub'),HF_HUB_OFFLINE='1',
  TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_DISABLE_PROGRESS_BARS='1')
 import numpy as np
 from PIL import Image
 import torch
 import torch.nn.functional as F
 import transformers
 from transformers import Sam2Model,Sam2Processor
 import transformers.models.sam2.modeling_sam2 as modeling
 import transformers.models.sam2.processing_sam2 as processing
 import transformers.models.sam2.image_processing_sam2_fast as image_processing
 for name,expected in deps['versions'].items():
  if md.version(name)!=expected:raise ValueError('Local dependency version changed: '+name)
 module_files={'sam2Model':modeling.__file__,'sam2Processor':processing.__file__,'sam2ImageProcessor':image_processing.__file__,'torch':torch.__file__}
 for name,path in module_files.items():
  if sha(path)!=deps['moduleSha256'][name]:raise ValueError('Local dependency source changed: '+name)
 for name,path in {'torchBinding':torch._C.__file__,'torchCpu':Path(torch.__file__).parent/'lib/torch_cpu.dll'}.items():
  if sha(path)!=deps['nativeSha256'][name]:raise ValueError('Local CPU library changed: '+name)
 image=Image.open(source).convert('RGBA');w,h=image.size;pixel_sha=hashlib.sha256(image.tobytes()).hexdigest()
 if q['sourceSize']!=[w,h]or q['sourcePixelSha256']!=pixel_sha:raise ValueError('Decoded crop changed')
 if min(w,h)<16 or max(w,h)>2048:raise ValueError('Unsupported local crop size')
 points=[];labels=[]
 for field,label in [('foreground',1),('background',0)]:
  values=np.asarray(q[field],dtype='float32')
  if values.ndim!=2 or values.shape[1]!=2 or not 1<=len(values)<=128 or not np.isfinite(values).all():raise ValueError('Invalid local prompt')
  if np.any(values<0)or np.any(values[:,0]>=w)or np.any(values[:,1]>=h):raise ValueError('Local prompt outside crop')
  points+=values.tolist();labels += [label]*len(values)
 torch.set_num_threads(a.threads);torch.manual_seed(0)
 from transformers.utils import logging
 logging.set_verbosity_error();logging.disable_progress_bar()
 model,info=Sam2Model.from_pretrained(str(manifest_path.parent/'model'),local_files_only=True,
  output_loading_info=True,dtype=torch.float32,attn_implementation='sdpa')
 info=json.loads(json.dumps(info,default=lambda v:sorted(v)if isinstance(v,set)else str(v)))
 dump(out/'loading.json',info)
 if any(info.get(k)for k in ['missing_keys','mismatched_keys','error_msgs']):raise ValueError('Incomplete model load')
 model=model.eval().to('cpu');processor=Sam2Processor.from_pretrained(str(manifest_path.parent/'model'),local_files_only=True)
 for name,obj in [('sam2Processor',processor),('sam2ImageProcessor',processor.image_processor)]:
  if sha(sys.modules[obj.__class__.__module__].__file__)!=deps['moduleSha256'][name]:raise ValueError('Processor implementation changed')
 prepared=processor(images=image.convert('RGB'),input_points=[[points]],input_labels=[[labels]],return_tensors='pt')
 encoded=time.perf_counter()
 with torch.inference_mode():
  result=model(pixel_values=prepared['pixel_values'],input_points=prepared['input_points'],input_labels=prepared['input_labels'],multimask_output=True)
  low=result.pred_masks.float();all_logits=F.interpolate(low.reshape(-1,1,*low.shape[-2:]),size=(h,w),mode='bilinear',align_corners=False)[:,0].cpu().numpy().astype('float32')
  scores=result.iou_scores.detach().cpu().numpy().reshape(-1).astype('float32')
  # SAM2's single-mask token is NOT one of its three multimask tokens.
  # Retain the original native path too, with the exact same point guards.
  single=model(pixel_values=prepared['pixel_values'],input_points=prepared['input_points'],input_labels=prepared['input_labels'],multimask_output=False)
  low_single=single.pred_masks.float()
  single_logits=F.interpolate(low_single.reshape(-1,1,*low_single.shape[-2:]),size=(h,w),mode='bilinear',align_corners=False)[:,0].cpu().numpy().astype('float32')
  all_logits=np.concatenate([all_logits,single_logits]);scores=np.concatenate([scores,single.iou_scores.detach().cpu().numpy().reshape(-1).astype('float32')])
  np.savez_compressed(out/'proposals.npz',logits=all_logits,scores=scores)
  selected,proposal_selection=choose_native_proposal(all_logits,scores,q['foreground'],q['background'])
  logits=all_logits[selected];prob=1/(1+np.exp(-np.clip(logits,-40,40)))
 if prob.shape!=(h,w)or not np.isfinite(prob).all():raise ValueError('Invalid native local mask')
 mask=(logits>0).astype('uint8')*255
 Image.fromarray(mask).save(out/'mask.png');np.save(out/'probability.npy',prob,allow_pickle=False)
 np.save(out/'logits.npy',logits,allow_pickle=False)
 receipt={'version':VERSION,'device':'cpu','model':m['model'],'revision':REV,'weightSha256':WEIGHT,
  'sourceSize':[w,h],'sourcePixelSha256':pixel_sha,'sourceFileSha256':sha(source),'paramsSha256':sha(params_path),
  'role':q['role'],'foreground':q['foreground'],'background':q['background'],'workerSha256':sha(__file__),
  'dependencyManifestSha256':sha(a.dependencies),'modelManifestSha256':sha(manifest_path),
  'maskPixelSha256':hashlib.sha256(mask.tobytes()).hexdigest(),'artifacts':{n:sha(out/n)for n in ['mask.png','probability.npy','logits.npy','loading.json','proposals.npz']},
  'proposalSelection':proposal_selection,
  'unverifiedCandidate':True,'humanReviewed':False,'imageGenerationSubmitted':False,
  'inferenceSeconds':time.perf_counter()-encoded,'totalSeconds':time.perf_counter()-start,
  'predictedIou':result.iou_scores.detach().cpu().tolist()}
 dump(out/'receipt.json',receipt)
 print(json.dumps({'state':'completed','device':'cpu','seconds':receipt['totalSeconds']}))
if __name__=='__main__':main()
