"""Source-guided clothing alpha under independently confirmed overlapping hair.

No RGB retouch, no product coordinates, no new vision request. The caller must
already own a bound source/QC/grounding and two source instance predictions.
The resulting alpha is an unverified candidate, never a colour-quality pass.
"""
import hashlib
import cv2
import numpy as np
from PIL import Image

VERSION='dual-instance-source-hair-matte-v3-paired-edge-matting'

def refine_paired(source,reference,old_alpha,cloth,non_target,human,unchanged,*,evidence_point):
    """Six-channel paired-observation CF matte; reference pixels stay evidence.

    Strict unchanged pixels supply hair interior seeds. Tiny JPEG/mixed pixels
    are solved from both actual observations, never relabelled unchanged by
    increasing the RGB tolerance. All native cloth remains immutable.
    """
    a=np.asarray(old_alpha.convert('L'));cm=np.asarray(cloth)>0;nm=np.asarray(non_target)>0
    if any(v.shape!=a.shape for v in (cm,nm,human,unchanged))or source.size!=old_alpha.size or reference.size!=source.size:
        raise ValueError('Paired hair matting requires exact native ROI dimensions')
    domain=nm&~cm&(human==2);ex,ey=evidence_point
    if not(0<=ex<a.shape[1]and 0<=ey<a.shape[0])or not(domain[ey,ex]and unchanged[ey,ex]and a[ey,ex]>0):
        raise ValueError('Paired matting lacks a strictly unchanged, grounded selected-hair witness')
    _,labels=cv2.connectedComponents(domain.astype('uint8'),8);component=labels==int(labels[ey,ex])
    trimap=np.ones(a.shape,'float64');trimap[a==0]=0;trimap[component]=.5
    trimap[component&unchanged]=0;trimap[cm]=1
    if (component&unchanged).sum()<8 or cm.sum()<8:raise ValueError('Paired matting lacks independent source interiors')
    features=np.concatenate([np.asarray(im.convert('RGB'),dtype='float64')/255 for im in (source,reference)],axis=2)
    matte,residual=solve_alpha(features,trimap)
    yy,xx=np.indices(a.shape);edge=np.minimum.reduce([xx,yy,a.shape[1]-1-xx,a.shape[0]-1-yy])
    predicted=np.rint(matte*255);result=a.copy()
    patch=np.rint(a-np.maximum(a-predicted,0)*np.clip(edge/8,0,1)).astype('uint8')
    result[component]=patch[component]
    if np.any(result>a)or np.any(result[cm]!=a[cm]):raise ValueError('Paired matting violated source cloth support')
    return Image.fromarray(result),{'version':VERSION,'method':'paired_observation_six_channel_closed_form_alpha',
        'changedPixels':int((result!=a).sum()),'strictUnchangedHairSeeds':int((component&unchanged).sum()),
        'mixedPixelsSolved':int((component&~unchanged).sum()),'relativeLinearResidual':residual,
        'nativeTargetClothChangedPixels':0,'semanticHairAndNonTargetRequired':True,'roiEdgeTaperPixels':8,
        'sourceRgbProcessed':False,'referencePixelsUsedAsOutput':False,'onlyGroundedConnectedDefect':True,
        'verified':False,'accepted':False,'alphaSha256':hashlib.sha256(result.tobytes()).hexdigest()}

def protect_unchanged_reference(old_alpha,cloth,non_target,human,unchanged,*,evidence_point):
    """Verified same-view evidence proposes alpha only; never copies reference RGB.

    Caller still enforces existing change budgets, all source protections,
    original cloth anchors, independent source review and final colour QA.
    """
    a=np.asarray(old_alpha.convert('L'));cm=np.asarray(cloth)>0;nm=np.asarray(non_target)>0
    if any(v.shape!=a.shape for v in (cm,nm,human,unchanged)):
        raise ValueError('Reference hair evidence must share exact native ROI dimensions')
    domain=nm&~cm&(human==2);ex,ey=evidence_point
    if not (0<=ex<a.shape[1] and 0<=ey<a.shape[0]) or not(domain[ey,ex] and unchanged[ey,ex] and a[ey,ex]>0):
        raise ValueError('Grounded dyed-hair point contradicts independent same-view/native evidence')
    _,labels=cv2.connectedComponents(domain.astype('uint8'),8);label=int(labels[ey,ex])
    eligible=(labels==label)&unchanged&(a>0)
    yy,xx=np.indices(a.shape);edge=np.minimum.reduce([xx,yy,a.shape[1]-1-xx,a.shape[0]-1-yy])
    result=a.copy();proposed=np.rint(a*(1-np.clip(edge/8,0,1))).astype('uint8')
    result[eligible]=proposed[eligible]
    if np.any(result>a) or np.any(result[cm]!=a[cm]):raise ValueError('Reference hair correction violated source cloth support')
    return Image.fromarray(result),{'version':VERSION,'method':'same_view_photometric_occlusion_alpha',
        'changedPixels':int((result!=a).sum()),'nativeTargetClothChangedPixels':0,
        'semanticHairAndNonTargetRequired':True,'roiEdgeTaperPixels':8,
        'sourceRgbProcessed':False,'referencePixelsUsedAsOutput':False,'onlyGroundedConnectedDefect':True,
        'verified':False,'accepted':False,'alphaSha256':hashlib.sha256(result.tobytes()).hexdigest()}

def colour_line_laplacian(rgb,known):
    """Vectorized r=1 colour-line matting Laplacian (Levin et al., 2007).

    Uses installed NumPy/SciPy, avoiding unrelated package-wide Numba JIT.
    Lij = delta_ij - (1 + (Ii-mu) inv(cov+eps/9 I) (Ij-mu))/9.
    """
    import scipy.sparse
    from numpy.lib.stride_tricks import sliding_window_view
    h,w,channels=rgb.shape
    if min(h,w)<3:raise ValueError('Matting ROI too small')
    windows=sliding_window_view(rgb,(3,3),axis=(0,1)).transpose(0,1,3,4,2).reshape(-1,9,channels)
    indices=sliding_window_view(np.arange(h*w).reshape(h,w),(3,3)).reshape(-1,9)
    relevant=~sliding_window_view(known,(3,3)).all(axis=(2,3)).ravel()
    windows=windows[relevant];indices=indices[relevant]
    centred=windows-windows.mean(axis=1,keepdims=True)
    cov=np.einsum('nki,nkj->nij',centred,centred)/9+np.eye(channels)[None]*(1e-7/9)
    weights=np.eye(9)[None]-(1+np.einsum('nki,nij,nlj->nkl',centred,np.linalg.inv(cov),centred))/9
    rows=np.broadcast_to(indices[:,:,None],weights.shape).ravel()
    cols=np.broadcast_to(indices[:,None,:],weights.shape).ravel()
    return scipy.sparse.coo_matrix((weights.ravel(),(rows,cols)),shape=(h*w,h*w)).tocsr()

def solve_alpha(rgb,trimap):
    from scipy.sparse.linalg import spsolve
    known=(trimap==0)|(trimap==1);unknown=~known.ravel();k=known.ravel()
    if not unknown.any():return trimap.copy(),0.
    lap=colour_line_laplacian(rgb,known)
    lhs=lap[unknown,:][:,unknown];rhs=-lap[unknown,:][:,k].dot(trimap.ravel()[k])
    result=spsolve(lhs,rhs)
    residual=float(np.linalg.norm(lhs.dot(result)-rhs)/(1+np.linalg.norm(rhs)))
    if not np.isfinite(result).all()or residual>1e-7:raise ValueError('Matting solver did not converge to the source constraints')
    alpha=trimap.copy().ravel();alpha[unknown]=np.clip(result,0,1)
    return alpha.reshape(trimap.shape),residual

def refine(source_crop,old_alpha,cloth,non_target,human,foreground,background,*,evidence_point):
    rgb=np.asarray(source_crop.convert('RGB'),dtype='float64')/255
    a=np.asarray(old_alpha.convert('L'));cm=np.asarray(cloth)>0;nm=np.asarray(non_target)>0
    if a.shape!=rgb.shape[:2] or human.shape!=a.shape or cm.shape!=a.shape or nm.shape!=a.shape:
        raise ValueError('Hair matting inputs must share exact native ROI dimensions')
    if not foreground or not background:raise ValueError('Hair matting requires independently grounded clean cloth and hair points')
    lab=cv2.cvtColor(rgb.astype('float32'),cv2.COLOR_RGB2LAB)
    fa=np.asarray([lab[y,x,1:]for x,y in foreground]);ba=np.asarray([lab[y,x,1:]for x,y in background])
    df=np.linalg.norm(lab[:,:,None,1:]-fa,axis=3).min(axis=2)
    db=np.linalg.norm(lab[:,:,None,1:]-ba,axis=3).min(axis=2)
    # Colour only proposes high-confidence trimap interiors; it never assigns
    # uncertain hair/fabric pixels directly. CF uses actual local RGB structure.
    sure_cloth=cm|((a>=230)&(df+2.5<db))
    sure_hair=nm&~cm&(human==2)&(db+2.5<df)
    trimap=np.full(a.shape,.5,'float64');trimap[sure_cloth]=1;trimap[sure_hair]=0
    for x,y in foreground:
        if not cm[y,x] or a[y,x]<230:raise ValueError('Grounded cloth point lacks original opaque cloth/native support')
        trimap[y,x]=1
    for x,y in background:
        if not nm[y,x] or cm[y,x] or not (human[max(0,y-3):y+4,max(0,x-3):x+4]==2).any():
            raise ValueError('Grounded hair point lacks native and independent semantic support')
        trimap[y,x]=0
    if (trimap==0).sum()<8 or (trimap==1).sum()<8:raise ValueError('Hair matte lacks sufficient independent source interiors')
    matte,residual=solve_alpha(rgb,trimap)
    if matte.shape!=a.shape or not np.isfinite(matte).all():raise ValueError('Hair matting did not return finite native alpha')
    predicted=np.rint(np.clip(matte,0,1)*255)
    # Preserve pixels whose measured source chroma favours the actual cloth,
    # including dark knit visible through an apparent "hair hole". Opaque
    # selections require the stronger source-hair margin; mixed weak alpha
    # may use the closer-source-material decision plus the two native instances.
    eligible=nm&~sure_cloth&(human==2)
    yy,xx=np.indices(a.shape);edge=np.minimum.reduce([xx,yy,a.shape[1]-1-xx,a.shape[0]-1-yy])
    weight=np.clip(edge/8,0,1)
    result=a.copy();corrected=np.rint(a-np.maximum(a-predicted,0)*weight).astype('uint8')
    result[eligible]=corrected[eligible]
    # Change the source-supported connected defect actually grounded by the
    # caller, rather than unrelated hair/noise anywhere else in the ROI.
    ex,ey=evidence_point
    if not (0<=ex<a.shape[1] and 0<=ey<a.shape[0]):raise ValueError('Hair evidence point outside native ROI')
    _,labels=cv2.connectedComponents((result<a).astype('uint8'),8)
    label=int(labels[ey,ex])
    if label==0:raise ValueError('Matting did not corroborate the grounded dyed-hair pixel')
    result[labels!=label]=a[labels!=label]
    if np.any(result>a):raise ValueError('Hair correction unexpectedly added selection')
    if np.any(result[cm]!=a[cm]):raise ValueError('Hair correction changed native target-cloth support')
    return Image.fromarray(result),{'version':VERSION,'method':'closed_form_RGB_guided_alpha_from_dual_source_instances',
        'chromaSeedMarginLabAB':2.5,'sureClothPixels':int((trimap==1).sum()),'sureHairPixels':int((trimap==0).sum()),
        'semanticHairAndNonTargetRequired':True,'nativeTargetClothChangedPixels':0,
        'sourceClothFavouredPixelsChanged':int(((result!=a)&(df<=db)).sum()),
        'sourceStrongClothFavouredPixelsChanged':int(((result!=a)&sure_cloth).sum()),
        'changedPixels':int((result!=a).sum()),'opaqueSelectedHairPixelsReduced':int(((result<a)&(a>=230)).sum()),
        'roiEdgeTaperPixels':8,'sourceRgbProcessed':False,'verified':False,'accepted':False,
        'onlyGroundedConnectedDefect':True,
        'solver':'vectorized_colour_line_LU','relativeLinearResidual':residual,
        'trimapSha256':hashlib.sha256(trimap.tobytes()).hexdigest(),
        'alphaSha256':hashlib.sha256(result.tobytes()).hexdigest()}
