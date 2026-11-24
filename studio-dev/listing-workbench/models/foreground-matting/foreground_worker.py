"""Offline, pinned BiRefNet-matting inference; never edit input pixels or prompts.

Contract: --input FILE --output-dir DIR [--device cpu|cuda] [--size 1024].
alpha.npy is float32 at the EXIF-oriented source size. source-rgba.png carries
the source RGB unchanged; its alpha is the prediction times any source alpha.
Model inference is not a semantic quality or product-identity acceptance.
"""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, json, os, sys, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
REVISION='eccde0a8cbdce7ac5fecfeb06340fe7b949e85d9'
WEIGHT_SHA='a9875de5b1e6c8eb5fdaa8c727a82927ce442cdc87ba3abee6a77e6fa46c25bb'
CODE_SHA={
 '__init__.py':'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'birefnet.py':'2a45b4e0ece72d7c4212bca1a988e7d7e52bfe9f98ec59c58b8809c8a8b7a831',
 'BiRefNet_config.py':'e7b8c2a74f6cea6a59553d517f71d47f2c1d90e670a13416af17c25fe2f3dc52',
 'config.json':'b2b235983b80fbff325976ca517bb7eda25e915b84a97b150eca41266cf8a13b',
 'model.safetensors':WEIGHT_SHA,
}

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def run(args):
    # These are set before importing model libraries. The implementation uses
    # local Python classes + safetensors, never dynamic hub execution or fetch.
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    source=Path(args.input).resolve(strict=True)
    output=Path(args.output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Output directory must be new or empty; existing evidence is never overwritten')
    source_hash=sha(source)
    worker_hash=sha(Path(__file__))
    model_dir=HERE/'model'
    for name,expected in CODE_SHA.items():
        if sha(model_dir/name)!=expected:raise ValueError(f'Pinned model integrity check failed: {name}')
    if args.size<256 or args.size>1536 or args.size%32:
        raise ValueError('size must be a multiple of 32 between 256 and 1536')
    # Transformers initialises a cache even for direct local class imports.
    # Keep that housekeeping inside this run, away from global user caches.
    cache=output/'.runtime-cache';cache.mkdir(parents=True,exist_ok=True)
    os.environ['HF_HOME']=str(cache)
    os.environ['HF_HUB_CACHE']=str(cache/'hub')
    import numpy as np
    from PIL import Image,ImageOps
    import torch
    import torch.nn.functional as F
    from torchvision import transforms
    from safetensors.torch import load_file
    from model.BiRefNet_config import BiRefNetConfig
    from model.birefnet import BiRefNet

    if args.device=='cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA was requested but this runtime has no CUDA device')
    torch.set_num_threads(args.threads)
    torch.set_float32_matmul_precision('high')
    if args.device=='cuda':torch.cuda.reset_peak_memory_stats()
    started=time.perf_counter()
    with Image.open(source) as raw:image=ImageOps.exif_transpose(raw).copy()
    original_alpha=np.asarray(image.getchannel('A'),dtype=np.float32)/255 if 'A' in image.getbands() else None
    image=image.convert('RGB');rgb=np.asarray(image).copy();w,h=image.size
    model=BiRefNet(config=BiRefNetConfig(bb_pretrained=False))
    state=load_file(str(model_dir/'model.safetensors'),device='cpu')
    model.load_state_dict(state,strict=True);del state
    model=model.eval().to(args.device)
    dtype=torch.float16 if args.device=='cuda' else torch.float32
    model=model.to(dtype=dtype)
    preprocessing=transforms.Compose([
        transforms.Resize((args.size,args.size)),transforms.ToTensor(),
        transforms.Normalize([.485,.456,.406],[.229,.224,.225]),
    ])
    tensor=preprocessing(image).unsqueeze(0).to(args.device,dtype=dtype)
    loaded=time.perf_counter()
    print(json.dumps({'state':'model_loaded','seconds':round(loaded-started,3),'device':args.device}),flush=True)
    with torch.inference_mode():
        prediction=model(tensor)[-1].float().sigmoid()
        # Resize floating alpha without a binary threshold. Hair, fringe and
        # anti-aliased hat contours need subpixel coverage retained.
        alpha=F.interpolate(prediction,size=(h,w),mode='bilinear',align_corners=False)[0,0].cpu().numpy().astype('float32')
    if original_alpha is not None:alpha*=original_alpha
    if not np.isfinite(alpha).all():raise ValueError('Model returned non-finite alpha')
    alpha=np.clip(alpha,0,1)
    inferred=time.perf_counter();output.mkdir(parents=True,exist_ok=True)
    np.save(output/'alpha.npy',alpha,allow_pickle=False)
    Image.fromarray(np.rint(alpha*65535).astype('uint16')).save(output/'alpha16.png')
    a8=np.rint(alpha*255).astype('uint8')
    Image.fromarray(a8).save(output/'alpha-preview.png')
    rgba=Image.fromarray(rgb,'RGB');rgba.putalpha(Image.fromarray(a8));rgba.save(output/'source-rgba.png')
    # Neutral checks are diagnostic composites, not edited image deliverables.
    for value,name in [(255,'white'),(48,'dark')]:
        composite=np.rint(rgb.astype('float32')*alpha[:,:,None]+value*(1-alpha[:,:,None])).clip(0,255).astype('uint8')
        Image.fromarray(composite).save(output/f'preview-{name}.png')
    versions={}
    for name in ['torch','torchvision','numpy','timm','transformers','safetensors','einops','kornia']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    receipt={'schema':'junfei.foreground-matting.v1','implementation':'pinned-offline-birefnet-matting-v1',
        'source':str(source),'sourceFileSha256':source_hash,'sourceRgbSha256':hashlib.sha256(rgb.tobytes()).hexdigest(),
        'sourceSize':[w,h],'model':'ZhengPeng7/BiRefNet-matting','modelRevision':REVISION,
        'weightSha256':WEIGHT_SHA,'workerSha256':worker_hash,
        'device':args.device,'deviceName':torch.cuda.get_device_name(0) if args.device=='cuda' else 'CPU',
        'dtype':str(dtype),'inferenceSize':[args.size,args.size],'threads':args.threads,'python':sys.executable,'packages':versions,
        'loadSeconds':round(loaded-started,3),'inferenceSeconds':round(inferred-loaded,3),
        'totalSeconds':round(time.perf_counter()-started,3),
        'peakCudaBytes':torch.cuda.max_memory_allocated() if args.device=='cuda' else None,
        'alphaMin':float(alpha.min()),'alphaMax':float(alpha.max()),
        'opaquePixels':int((alpha>=.99).sum()),'uncertainPixels':int(((alpha>.01)&(alpha<.99)).sum()),
        'sourceRgbPreserved':bool(np.array_equal(np.asarray(Image.open(output/'source-rgba.png'))[:,:,:3],rgb)),
        'semanticQualityPassed':None,'humanReviewed':False,
        'notice':'Model inference only. No semantic acceptance, generative task, SCHP forcing, or per-image mask coordinates.',
        'files':{name:{'path':str(output/name),'sha256':sha(output/name)} for name in ['alpha.npy','alpha16.png','alpha-preview.png','source-rgba.png','preview-white.png','preview-dark.png']}}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--size',type=int,default=1024)
    parser.add_argument('--threads',type=int,default=4)
    args=parser.parse_args()
    if args.threads<1 or args.threads>32:parser.error('--threads must be 1..32')
    run(args)

if __name__=='__main__':main()
