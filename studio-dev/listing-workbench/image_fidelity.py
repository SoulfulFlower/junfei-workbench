"""Source-measured garment chroma and original-pixel construction references."""
import io,json,hashlib,threading
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import app_paths
import garment_auto

VERSION='source-chroma-and-fibres-v2-coverage'
LOCK=threading.RLock()


def selection(image,kind,cache_root=None,allow_full_frame=False):
    root=Path(cache_root or app_paths.DATA/'image-fidelity');root.mkdir(parents=True,exist_ok=True)
    raw=image.convert('RGB').tobytes()
    key=hashlib.sha256(raw+str(image.size).encode()+kind.encode()+garment_auto.VERSION.encode()+VERSION.encode()+str(allow_full_frame).encode()).hexdigest()
    file=root/(key+'.png');meta=root/(key+'.json')
    with LOCK:
        if file.is_file() and meta.is_file():
            mask=Image.open(file).copy();receipt=json.loads(meta.read_text(encoding='utf-8'))
        else:
            labels=garment_auto.parser().predict(image)
            semantic=labels=={'upper':1,'lower':2,'full':3}[kind]
            try:
                mask,receipt=garment_auto.identify(image,Image.new('L',image.size),app_paths.DATA/'garment-embeddings',kind)
            except ValueError as error:
                if semantic.sum()<100:raise
                if semantic.mean()>.95 and allow_full_frame:
                    from image_selection import protect
                    mask,receipt=protect(Image.fromarray(semantic.astype('uint8')*255),garment_auto.human_parser().predict(image))
                    receipt={**receipt,'method':'explicit_original_pixel_detail_full_frame','nativeBoundaryIssue':str(error)}
                else:
                    mask,recovery=refine_supported(image,semantic)
                    receipt={'nativeBoundaryIssue':str(error),'sourcePixelRecovery':recovery}
            core=cv2.erode(semantic.astype('uint8'),np.ones((9,9),'uint8'))>0
            coverage=float(((np.asarray(mask)>240)&core).sum()/max(1,core.sum()))
            if core.sum()>100 and coverage<.65:
                mask,recovery=refine_supported(image,semantic)
                receipt={**receipt,'coverageBeforeRecovery':coverage,'sourcePixelRecovery':recovery}
            temp=file.with_suffix('.tmp');mask.save(temp,'PNG');temp.replace(file)
            meta.write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
    return mask,{**receipt,'sourcePixelSha256':hashlib.sha256(raw).hexdigest()}


def reference_selection(image,kind):
    """Colour statistics require reliable interior cloth, not fragile matting."""
    labels=garment_auto.parser().predict(image)
    human=garment_auto.human_parser().predict(image)
    semantic=labels=={'upper':1,'lower':2,'full':3}[kind]
    if (semantic&(human>0)).sum()/max(1,semantic.sum())<.7:
        raise ValueError('参考图衣料缺少独立人体/服装支持')
    core=cv2.erode(semantic.astype('uint8'),np.ones((11,11),'uint8'))>0
    core[np.isin(human,[1,2,3,9,10,11,14,15,16,17])]=False
    if core.sum()<100:raise ValueError('参考图内无足够可信衣料内部区域')
    return Image.fromarray(core.astype('uint8')*255),{'method':'independent_cloth_interior_only','pixels':int(core.sum()),'edgeMask':False,'humanReviewed':False}


def refine_supported(image,semantic):
    """Recover a collapsed boundary proposal with source-pixel GrabCut evidence."""
    rgb=np.asarray(image.convert('RGB'));human=garment_auto.human_parser().predict(image)
    from image_selection import protect
    protected,_=protect(Image.new('L',image.size,255),human)
    protection=np.asarray(protected)==0
    semantic=semantic&~protection
    domain=garment_auto.body_domain(human)
    semantic&=domain
    distance=garment_auto.fabric_distance(image,semantic)
    possible=cv2.dilate(semantic.astype('uint8'),np.ones((25,25),'uint8'))>0
    gc=np.full(semantic.shape,cv2.GC_BGD,'uint8');gc[possible&domain]=cv2.GC_PR_BGD
    gc[semantic]=cv2.GC_PR_FGD
    certain=(cv2.erode(semantic.astype('uint8'),np.ones((9,9),'uint8'))>0)&(distance<18)
    gc[certain]=cv2.GC_FGD;gc[protection]=cv2.GC_BGD
    cv2.setRNGSeed(0);cv2.grabCut(rgb.copy(),gc,None,np.zeros((1,65)),np.zeros((1,65)),4,cv2.GC_INIT_WITH_MASK)
    result=np.isin(gc,[cv2.GC_FGD,cv2.GC_PR_FGD]);result[protection]=False
    mask=Image.fromarray(result.astype('uint8')*255)
    core=cv2.erode(semantic.astype('uint8'),np.ones((9,9),'uint8'))>0
    coverage=float((result&core).sum()/max(1,core.sum()))
    if coverage<.75:raise ValueError('衣料边界与独立衣料证据仍冲突，不能自动换色')
    return mask,{'method':'cloth_semantics_plus_original_pixel_grabcut','coreCoverage':coverage,
                 'skinProtectedPixels':int(protection.sum()),'humanReviewed':False}


def centre(image,mask):
    a=np.asarray(mask.convert('L'))>245
    lab=cv2.cvtColor(np.asarray(image.convert('RGB'),dtype=np.float32)/255,cv2.COLOR_RGB2LAB)
    core=cv2.erode(a.astype('uint8'),np.ones((5,5),'uint8'))>0
    if core.sum()<100:core=a
    if core.sum()<50:raise ValueError('没有足够真实衣料像素进行色度校准')
    samples=lab[core];lo,hi=np.percentile(samples[:,0],[25,75]);mid=samples[(samples[:,0]>=lo)&(samples[:,0]<=hi)]
    return np.median(mid,axis=0),lab


def calibrate(source,result,source_mask,result_mask):
    """Match source midtone Lab; keep local light/shadow contrast and geometry."""
    target,_=centre(source,source_mask);before,lab=centre(result,result_mask)
    original=np.asarray(result.convert('RGB'))
    a=np.asarray(result_mask.convert('L'),dtype=np.float32)/255
    delta=target-before
    # Pale fabrics are easily posterised when a categorical mask has holes.
    # If the native result is already close, retain every original pixel and
    # leave the actual colour/structure decision to the independent review.
    if np.linalg.norm(target[1:])<12 and np.linalg.norm(before[1:])<12 and np.linalg.norm(delta)<6:
        return result.copy(),{'version':VERSION,'sourceLab':target.tolist(),'beforeLab':before.tolist(),'afterLab':before.tolist(),
            'chromaErrorBefore':float(np.linalg.norm(delta[1:])),'chromaErrorAfter':float(np.linalg.norm(delta[1:])),
            'medianDeltaEBefore':float(np.linalg.norm(delta)),'medianDeltaEAfter':float(np.linalg.norm(delta)),
            'outsideChangedPixels':0,'allPixelsChanged':0,'method':'retained_near_neutral_native_output_no_hard_mask_grade',
            'reviewRequired':True,'humanReviewed':False}
    mapped=lab.copy();mapped+=delta;mapped[:,:,0]=mapped[:,:,0].clip(0,100)
    corrected=cv2.cvtColor(mapped,cv2.COLOR_LAB2RGB).clip(0,1)
    weight=a*a*(3-2*a)
    rgb=np.rint((original/255*(1-weight[:,:,None])+corrected*weight[:,:,None])*255).clip(0,255).astype('uint8')
    rgb[a==0]=original[a==0]
    out=Image.fromarray(rgb)
    if 'A' in result.getbands():out.putalpha(result.getchannel('A'))
    after,_=centre(out,result_mask)
    return out,{'version':VERSION,'sourceLab':target.tolist(),'beforeLab':before.tolist(),'afterLab':after.tolist(),
        'chromaErrorBefore':float(np.linalg.norm(before[1:]-target[1:])),
        'chromaErrorAfter':float(np.linalg.norm(after[1:]-target[1:])),
        'outsideChangedPixels':int(np.any(rgb[a==0]!=original[a==0],axis=-1).sum()),
        'medianDeltaEBefore':float(np.linalg.norm(before-target)),
        'medianDeltaEAfter':float(np.linalg.norm(after-target)),
        'method':'source_measured_Lab_offset_keep_local_light_contrast','humanReviewed':False}


def construction_anchor(source,mask):
    box=mask.getbbox()
    if not box:raise ValueError('衣料选区为空')
    x1,y1,x2,y2=box
    crop=(x1,max(y1,round(y2-(y2-y1)*.27)),x2,min(source.height,y2+3))
    return source.crop(crop),crop


def source_layer(source,kind=None,*,backend='foreground'):
    if backend=='foreground':
        import foreground_matting
        return foreground_matting.matte(source)
    if backend!='legacy':raise ValueError('原片前景抠像方式无效')
    return legacy_source_layer(source,kind)


def legacy_source_layer(source,kind=None):
    """Matte the photographed wearer; preserve actual fibres and pocket pixels."""
    from pymatting import estimate_alpha_cf
    rgb=np.asarray(source.convert('RGB'),dtype=float)/255
    human=garment_auto.human_parser().predict(source)
    body=cv2.dilate((human>0).astype('uint8'),np.ones((7,7),'uint8'))>0
    w=source.width;edge=max(10,w//12)
    left=np.median(rgb[:,:edge],axis=1);right=np.median(rgb[:,-edge:],axis=1)
    frac=np.linspace(0,1,w)[None,:,None]
    background=left[:,None,:]*(1-frac)+right[:,None,:]*frac
    contrast=np.max(np.abs(rgb-background),axis=2)
    selected=body&(contrast>12/255)
    possible=cv2.dilate(selected.astype('uint8'),np.ones((7,7),'uint8'))>0
    inside=cv2.erode(selected.astype('uint8'),np.ones((5,5),'uint8'))>0
    trimap=np.zeros(selected.shape,float);trimap[possible]=.5;trimap[inside]=1
    # Thin brown fibres retain foreground anchors; neutral original background
    # in their gaps remains explicit background even inside the body outline.
    colour_range=np.max(rgb,axis=2)-np.min(rgb,axis=2)
    trimap[body&(contrast>50/255)&(colour_range>30/255)]=1
    trimap[contrast<6/255]=0
    trimap[(cv2.erode((human==0).astype('uint8'),np.ones((3,3),'uint8'))>0)]=0
    trimap[body&(colour_range<15/255)&(contrast<30/255)]=0
    # Opaque semantic interiors are source photograph pixels even when a knit
    # groove happens to match the estimated gray background. Keep those grooves
    # instead of punching holes through sleeves. Fine lower hems stay governed
    # by the original contrast trimap and matting boundaries.
    opaque=cv2.erode((human>0).astype('uint8'),np.ones((7,7),'uint8'))>0
    lower=np.isin(human,[6])
    ys=np.where(lower)[0]
    if len(ys) and kind!='upper':opaque[max(0,int(np.percentile(ys,80))):]=False
    trimap[opaque]=1
    alpha=estimate_alpha_cf(rgb,trimap,cg_kwargs={'maxiter':1000})
    alpha[trimap==1]=1;alpha[trimap==0]=0;alpha[alpha<1/255]=0
    foreground=rgb.copy();mixed=(alpha>.01)&(alpha<1)
    foreground[mixed]=(rgb[mixed]-(1-alpha[mixed,None])*background[mixed])/alpha[mixed,None]
    foreground=foreground.clip(0,1)
    return foreground,alpha,{'version':VERSION,'method':'original_wearer_closed_form_matte',
        'immutableCorePixels':int((alpha==1).sum()),'sourcePixelsNeverRedrawn':True,'humanReviewed':False}


def composite_layer(source,background,foreground,alpha):
    if background.size!=source.size:background=background.resize(source.size,Image.Resampling.LANCZOS)
    bg=np.asarray(background.convert('RGB'),dtype=float)/255
    out=np.rint((foreground*alpha[:,:,None]+bg*(1-alpha[:,:,None]))*255).clip(0,255).astype('uint8')
    src=np.asarray(source.convert('RGB'));out[alpha==1]=src[alpha==1]
    return Image.fromarray(out),{'immutableCorePixels':int((alpha==1).sum()),'immutableCoreChangedPixels':int(np.any(out[alpha==1]!=src[alpha==1],axis=-1).sum())}


def hardware_protection(image,mask):
    lab=cv2.cvtColor(np.asarray(image.convert('RGB'),dtype=np.float32)/255,cv2.COLOR_RGB2LAB)
    a=np.asarray(mask.convert('L'))>240;box=mask.getbbox();out=np.zeros(a.shape,'uint8')
    if not box:return Image.fromarray(out),{'candidatePixels':0}
    _,y1,_,y2=box
    candidate=a&(lab[:,:,0]>45)&(np.linalg.norm(lab[:,:,1:],axis=2)<20)
    candidate[round(y1+(y2-y1)*.3):]=False
    n,parts,stats,_=cv2.connectedComponentsWithStats(candidate.astype('uint8'))
    for i in range(1,n):
        x,y,w,h,area=stats[i]
        if 8<=area<=max(100,int(a.sum()*.004)) and .35<=w/max(h,1)<=2.8:out[parts==i]=255
    return Image.fromarray(out),{'method':'small_neutral_waist_hardware_candidates','candidatePixels':int((out>0).sum()),'humanReviewed':False}


def extend_chromatic_construction(image,mask):
    """Recover coloured attached fibres inside the real wearer domain."""
    rgb=np.asarray(image.convert('RGB'));lab=cv2.cvtColor(rgb.astype('float32')/255,cv2.COLOR_RGB2LAB)
    seed=np.asarray(mask.convert('L'))>240
    samples=lab[:,:,1:][seed]
    if len(samples)<50:raise ValueError('衣料锚点不足')
    centre=np.median(samples,axis=0);spread=np.percentile(np.linalg.norm(samples-centre,axis=1),98)
    tolerance=min(24.,max(12.,float(spread)+5))
    human=garment_auto.human_parser().predict(image)
    domain=garment_auto.body_domain(human)
    # Neutral black boots cannot be authorised by a trouser-class error.
    chroma=np.linalg.norm(lab[:,:,1:],axis=2)
    skin=np.isin(human,[1,2,3,11,14,15,16,17])
    tonal=(np.linalg.norm(lab[:,:,1:]-centre,axis=2)<tolerance)&domain&~skin
    tonal&=chroma>max(8.,float(np.linalg.norm(centre))*.32)
    ys=np.nonzero(seed)[0];tonal[:max(0,int(ys.min())-8)]=False
    # A shoe-class hem is recovered only when its observed colour is cloth-like
    # and attached to an already verified garment component.
    n,parts,_,_=cv2.connectedComponentsWithStats(tonal.astype('uint8'))
    keep=np.unique(parts[seed&tonal]);keep=keep[keep>0]
    result=np.isin(parts,keep)
    out=np.maximum(np.asarray(mask.convert('L')),result.astype('uint8')*255)
    out[skin]=0
    out[chroma<max(5.,float(np.linalg.norm(centre))*.2)]=0
    return Image.fromarray(out),{'method':'attached_source_chroma_fibre_recovery','addedPixels':int((result&~seed).sum()),'tolerance':tolerance,'humanReviewed':False}
