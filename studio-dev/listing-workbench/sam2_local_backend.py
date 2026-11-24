"""Pinned subprocess adapter. A local model prediction never approves a mask."""
from pathlib import Path
import hashlib,json,subprocess,threading,uuid,os
import numpy as np
from PIL import Image
VERSION='sam2-grounded-local-backend-v3-native-single-and-multimask';LOCK=threading.RLock()
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
class Sam2LocalBackend:
 def __init__(self,runtime_path=None,runner=None):
  self.path=Path(runtime_path)if runtime_path else Path(__file__).parent/'models/local-instance/runtime.json'
  self.runner=runner or subprocess.run
 def configuration(self):
  config=json.loads(self.path.read_text('utf8'));root=self.path.resolve().parent
  if config.get('schema')!='junfei.sam2.local.runtime.v1':raise ValueError('Unsupported local runtime contract')
  files={}
  for name,field in [('worker','workerFile'),('model','modelManifestFile'),('dependencies','dependencyManifestFile')]:
   path=(root/config[field]).resolve();path.relative_to(root)
   if sha(path)!=config[name+'Sha256']:raise ValueError('Local instance artifact changed: '+name)
   files[name]=path
  model=json.loads(files['model'].read_text('utf8'))
  if model.get('model')!=config['modelName']or model.get('revision')!=config['revision']or model.get('weightSha256')!=config['weightSha256']:raise ValueError('Local model identity changed')
  python=Path(config['pythonExecutable'])
  if sha(python)!=config['pythonSha256']:raise ValueError('Local instance interpreter changed')
  return config,files,python
 def identity(self):
  config,files,python=self.configuration()
  return {'version':VERSION,'model':config['modelName'],'revision':config['revision'],'device':'cpu',
   'inferenceContract':config.get('inferenceContract','legacy_single_mask'),
   'adapterSha256':sha(__file__),
   'runtimeSha256':sha(self.path),'workerSha256':config['workerSha256'],'modelManifestSha256':config['modelSha256'],
   'dependencyManifestSha256':config['dependenciesSha256'],'pythonSha256':config['pythonSha256'],'weightSha256':config['weightSha256']}
 def predict(self,source_crop,foreground,background,*,cache_root,role):
  if not isinstance(source_crop,Image.Image):raise ValueError('Local model requires an actual source crop')
  source=source_crop.convert('RGBA');w,h=source.size
  if min(w,h)<16 or max(w,h)>2048:raise ValueError('Unsupported local model crop size')
  if not isinstance(role,str)or not 1<=len(role)<=64:raise ValueError('Invalid local model role')
  actual={}
  for field,values in [('foreground',foreground),('background',background)]:
   if not isinstance(values,list)or not 1<=len(values)<=128:raise ValueError('Local model needs positive and negative points')
   for row in values:
    if not isinstance(row,(list,tuple))or len(row)!=2 or any(type(v)not in(int,float)or not np.isfinite(v)for v in row)or not(0<=row[0]<w and 0<=row[1]<h):raise ValueError('Invalid local point')
   actual[field]=[list(row)for row in values]
  if set(map(tuple,actual['foreground']))&set(map(tuple,actual['background'])):raise ValueError('Conflicting local point roles')
  config,files,python=self.configuration();identity=self.identity()
  binding={'version':VERSION,'sourcePixelSha256':hashlib.sha256(source.tobytes()).hexdigest(),'sourceSize':[w,h],
   'role':role,**actual,'model':identity};key=digest(binding)
  folder=Path(cache_root).resolve()/'sl1'/key[:32];manifest=folder/'receipt.json'
  with LOCK:
   if manifest.exists():
    cached=json.loads(manifest.read_text('utf8'))
    if cached.get('binding')!=binding or cached.get('recordSha256')!=digest({k:v for k,v in cached.items()if k!='recordSha256'}):raise ValueError('Local candidate cache binding changed')
    if cached.get('state')!='completed':raise ValueError('Prior local inference failed or is unresolved; original diagnostics retained')
    return self.checked(folder,cached,binding),{**cached,'cacheReused':True}
   folder.mkdir(parents=True,exist_ok=True);source.save(folder/'source.png')
   params={'schema':'junfei.grounded-local-points.v1','sourceSize':[w,h],'sourcePixelSha256':binding['sourcePixelSha256'],
    'sourceFileSha256':sha(folder/'source.png'),'manualPointsAdded':False,'role':role,**actual}
   write(folder/'params.json',params)
   row={'binding':binding,'state':'processing','accepted':False,'verified':False,'unverifiedCandidate':True,'cacheManifestPath':str(manifest)}
   self.persist(manifest,row);output=folder/('r-'+uuid.uuid4().hex[:8]);output.mkdir()
   try:
    command=[str(python),'-u','-B','-X','utf8',str(files['worker']),'--source',str(folder/'source.png'),'--params',str(folder/'params.json'),
     '--model-manifest',str(files['model']),'--dependencies',str(files['dependencies']),'--output-dir',str(output),'--threads','4']
    with(folder/'worker.log').open('w',encoding='utf8')as log:
     result=self.runner(command,stdout=log,stderr=subprocess.STDOUT,timeout=900,check=False,
      **({'creationflags':subprocess.CREATE_NO_WINDOW}if os.name=='nt'else{}))
    if result.returncode:raise ValueError('Local model worker failed; see saved worker.log')
    worker=json.loads((output/'receipt.json').read_text('utf8'))
    row.update(state='completed',outputDirectory=str(output),workerReceipt=worker,
     assets={'source.png':sha(folder/'source.png'),'params.json':sha(folder/'params.json')},
     workerReceiptSha256=sha(output/'receipt.json'),sourcePixelSha256=binding['sourcePixelSha256'],
     maskPixelSha256=worker.get('maskPixelSha256'),role=role)
    mask=self.checked(folder,row,binding);self.persist(manifest,row);return mask,row
   except Exception as error:
    row.update(state='failed',error=str(error)[:2000],outputDirectory=str(output));self.persist(manifest,row);raise
 def persist(self,path,row):
  row['recordSha256']=digest({k:v for k,v in row.items()if k!='recordSha256'});write(path,row)
 def checked(self,folder,row,binding):
  output=Path(row['outputDirectory']).resolve();output.relative_to(folder.resolve())
  for name,expected in row['assets'].items():
   if name not in('source.png','params.json')or sha(folder/name)!=expected:raise ValueError('Local inference source artifact changed')
  if sha(output/'receipt.json')!=row['workerReceiptSha256']:raise ValueError('Local worker receipt changed')
  receipt=row['workerReceipt'];identity=binding['model']
  if row.get('sourcePixelSha256')!=binding['sourcePixelSha256']or row.get('role')!=binding['role']or row.get('maskPixelSha256')!=receipt.get('maskPixelSha256'):raise ValueError('Local public receipt aliases changed')
  expected={'sourcePixelSha256':binding['sourcePixelSha256'],'sourceSize':binding['sourceSize'],'role':binding['role'],
   'foreground':binding['foreground'],'background':binding['background'],'workerSha256':identity['workerSha256'],
   'modelManifestSha256':identity['modelManifestSha256'],'dependencyManifestSha256':identity['dependencyManifestSha256'],
   'model':identity['model'],'revision':identity['revision'],'weightSha256':identity['weightSha256'],'device':'cpu'}
  if any(receipt.get(k)!=v for k,v in expected.items())or receipt.get('paramsSha256')!=sha(folder/'params.json')or receipt.get('sourceFileSha256')!=sha(folder/'source.png'):raise ValueError('Local model response does not match source/points/runtime')
  if receipt.get('unverifiedCandidate')is not True:raise ValueError('Local worker may not self-approve a mask')
  for name in ('mask.png','probability.npy','logits.npy','loading.json'):
   if sha(output/name)!=receipt['artifacts'].get(name):raise ValueError('Local model result artifact changed')
  mask=Image.open(output/'mask.png').convert('L');array=np.asarray(mask)
  if list(mask.size)!=binding['sourceSize']or hashlib.sha256(array.tobytes()).hexdigest()!=receipt['maskPixelSha256']or not np.isin(array,[0,255]).all():raise ValueError('Local mask is not the original-size binary prediction')
  probability=np.load(output/'probability.npy',allow_pickle=False);logits=np.load(output/'logits.npy',allow_pickle=False)
  if probability.shape!=array.shape or logits.shape!=array.shape or not np.isfinite(probability).all()or not np.isfinite(logits).all()or probability.min()<0 or probability.max()>1 or not np.array_equal(array,(logits>0).astype('uint8')*255):raise ValueError('Local probability/logit artifacts do not match the original mask')
  for field,label in [('foreground',255),('background',0)]:
   if any(mask.getpixel((int(x),int(y)))!=label for x,y in binding[field]):raise ValueError('Local model contradicts grounded point constraints')
  if identity.get('inferenceContract')=='native_multimask_all_points_v1':
   if sha(output/'proposals.npz')!=receipt['artifacts'].get('proposals.npz'):raise ValueError('Native proposal artifact changed')
   choice=receipt.get('proposalSelection',{});index=choice.get('selectedIndex')
   with np.load(output/'proposals.npz',allow_pickle=False)as archive:
    candidates=archive['logits'];scores=archive['scores']
   if candidates.ndim!=3 or type(index)is not int or not 0<=index<len(candidates)or not np.array_equal(candidates[index],logits):raise ValueError('Selected logits are not a native proposal')
   valid=[i for i,c in enumerate(candidates)if all(c[int(y),int(x)]>0 for x,y in binding['foreground'])and all(c[int(y),int(x)]<=0 for x,y in binding['background'])]
   if len(scores)!=len(candidates)or not np.isfinite(candidates).all()or not np.isfinite(scores).all()or not valid or index!=max(valid,key=lambda i:(float(scores[i]),-i))or choice.get('maskPixelsForced')!=0:
    raise ValueError('Native proposal selection did not preserve all point constraints')
  return mask
