"""Reusable point-guided clothing selections; never generates product images.

MobileSAM ONNX preprocessing follows the converter's ImageEncoderOnnxModel:
resize the longest side to 1024, then pass unnormalised RGB HWC float pixels.
The encoder itself normalises and pads. See models/mobile-sam/manifest.json.
"""
import hashlib,json,os,time,uuid
from pathlib import Path
import numpy as np
from PIL import Image


class GarmentSelector:
 def __init__(self,model_dir,cache_dir):
  import onnxruntime as ort
  self.models=Path(model_dir);self.cache=Path(cache_dir);self.cache.mkdir(parents=True,exist_ok=True)
  manifest=json.loads((self.models/'manifest.json').read_text(encoding='utf8'))
  names=['mobile_sam_image_encoder.onnx','sam_mask_decoder_single.onnx']
  for name in names:
   expected=next(f['sha256'] for f in manifest['files'] if f['file']==name)
   if hashlib.sha256((self.models/name).read_bytes()).hexdigest()!=expected:raise ValueError('Selection model differs from its pinned manifest')
  self.version=manifest['revision'];opt=ort.SessionOptions();opt.intra_op_num_threads=4;opt.inter_op_num_threads=1
  self.encoder=ort.InferenceSession(str(self.models/names[0]),sess_options=opt,providers=['CPUExecutionProvider'])
  self.decoder=ort.InferenceSession(str(self.models/names[1]),sess_options=opt,providers=['CPUExecutionProvider'])

 @staticmethod
 def points(values,size):
  a=np.asarray(values,dtype=np.float32)
  if a.ndim!=2 or a.shape[1]!=2 or len(a)==0 or not np.isfinite(a).all():raise ValueError('Selection needs finite foreground/background point pairs')
  if np.any(a<0) or np.any(a[:,0]>=size[0]) or np.any(a[:,1]>=size[1]):raise ValueError('Selection point is outside the source image')
  return a

 @staticmethod
 def fill_unprompted_holes(mask,background):
  """Fill texture holes, retaining openings explicitly marked as background."""
  import cv2
  n,labels,stats,_=cv2.connectedComponentsWithStats((~mask).astype(np.uint8))
  border=np.unique(np.r_[labels[0],labels[-1],labels[:,0],labels[:,-1]])
  keep=set(border.tolist())|{int(labels[int(y),int(x)]) for x,y in background}
  return mask|np.isin(labels,[k for k in range(1,n) if k not in keep])

 @staticmethod
 def refine(source,selection,background,protected=None,foreground=None):
  """Refine one semantic selection against the actual original pixels."""
  import cv2
  image=np.asarray(source.convert('RGB'));mask=np.asarray(selection.convert('L'))>127
  if mask.shape!=image.shape[:2]:raise ValueError('Selection must match original dimensions')
  possible=cv2.dilate(mask.astype(np.uint8),np.ones((65,65),np.uint8))>0
  certain=cv2.erode(mask.astype(np.uint8),np.ones((21,21),np.uint8))>0
  gc=np.full(mask.shape,cv2.GC_BGD,np.uint8);gc[possible]=cv2.GC_PR_BGD;gc[mask]=cv2.GC_PR_FGD;gc[certain]=cv2.GC_FGD
  if foreground is not None:
   for x,y in GarmentSelector.points(foreground,source.size):cv2.circle(gc,(int(x),int(y)),2,cv2.GC_FGD,-1)
  for x,y in GarmentSelector.points(background,source.size):cv2.circle(gc,(int(x),int(y)),4,cv2.GC_BGD,-1)
  if protected is not None:
   p=np.asarray(protected.convert('L'))>127
   if p.shape!=mask.shape:raise ValueError('Protection must match source dimensions')
   gc[cv2.erode(p.astype(np.uint8),np.ones((3,3),np.uint8))>0]=cv2.GC_BGD
  cv2.setRNGSeed(0);cv2.grabCut(image.copy(),gc,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
  refined=np.isin(gc,[cv2.GC_FGD,cv2.GC_PR_FGD])
  return Image.fromarray(refined.astype(np.uint8)*255)

 def select(self,source,foreground,background):
  source=source.convert('RGB');w,h=source.size;p=self.points(foreground,source.size);n=self.points(background,source.size)
  digest=hashlib.sha256(source.tobytes()).hexdigest();key=hashlib.sha256((self.version+digest).encode()).hexdigest();path=self.cache/(key+'.npz');cached=path.exists();start=time.perf_counter()
  if cached:
   with np.load(path,allow_pickle=False) as data:embedding=data['embedding']
  else:
   scale=1024/max(w,h);resized=source.resize((int(w*scale+.5),int(h*scale+.5)),Image.Resampling.BILINEAR)
   embedding=self.encoder.run(None,{'input_image':np.asarray(resized,dtype=np.float32)})[0]
   temporary=self.cache/(key+'.'+uuid.uuid4().hex+'.npz');np.savez_compressed(temporary,embedding=embedding);os.replace(temporary,path)
  scale=np.array([int(w*1024/max(w,h)+.5)/w,int(h*1024/max(w,h)+.5)/h],np.float32)
  coords=np.vstack([p,n,[[0,0]]]).astype(np.float32)*scale
  labels=np.r_[np.ones(len(p)),np.zeros(len(n)),[-1]].astype(np.float32)
  output,score,_=self.decoder.run(None,{'image_embeddings':embedding,'point_coords':coords[None], 'point_labels':labels[None], 'mask_input':np.zeros((1,1,256,256),np.float32),'has_mask_input':np.zeros(1,np.float32),'orig_im_size':np.array([h,w],np.float32)})
  mask=output[0,0]>0
  if mask.shape!=(h,w) or not mask.any():raise ValueError('Invalid or empty garment selection')
  bad_fg=[(int(x),int(y)) for x,y in p if not mask[int(y),int(x)]];bad_bg=[(int(x),int(y)) for x,y in n if mask[int(y),int(x)]]
  if bad_fg or bad_bg:raise ValueError('Selection contradicts garment points '+str(bad_fg)+' or protection points '+str(bad_bg))
  mask=self.fill_unprompted_holes(mask,n)
  return Image.fromarray(mask.astype(np.uint8)*255),{'sourcePixelSha256':digest,'modelRevision':self.version,'encoderCacheHit':cached,'seconds':round(time.perf_counter()-start,3),'predictedIou':float(score.flat[0]),'foreground':p.tolist(),'background':n.tolist(),'humanReviewed':False}
