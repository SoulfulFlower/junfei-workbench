"""Strict same-view correspondence evidence. Never returns product RGB output."""
import hashlib
import cv2
import numpy as np
from PIL import Image

VERSION='same-view-reference-occlusion-evidence-v2-paired-observations'
POLICY={'minimumInliers':50,'maximumMedianReprojectionPixels':.5,'maximumP95ReprojectionPixels':1.,
    'maximumUnchangedRGBDifference':3,'minimumNonTargetStableFraction':.8,
    'minimumClothChangeRGB':20,'minimumProtectedInliers':20}

def pixels(image):return hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest()

def analyze(source,reference,old_mask,base):
    audit={'version':VERSION,'sourcePixelSha256':pixels(source),'referencePixelSha256':pixels(reference),
        'policy':dict(POLICY),'accepted':False,'certifiesSelection':False,'referencePixelsUsedAsOutput':False}
    def reject(reason):return {'audit':{**audit,'reason':reason}}
    s=np.asarray(source.convert('RGB'));t=np.asarray(reference.convert('RGB'))
    cv2.setRNGSeed(0);sift=cv2.SIFT_create(nfeatures=6000)
    ks,ds=sift.detectAndCompute(cv2.cvtColor(s,cv2.COLOR_RGB2GRAY),None)
    kt,dt=sift.detectAndCompute(cv2.cvtColor(t,cv2.COLOR_RGB2GRAY),None)
    if ds is None or dt is None:return reject('insufficient_source_features')
    matches=[a for pair in cv2.BFMatcher().knnMatch(dt,ds,k=2)if len(pair)==2 for a,b in [pair]if a.distance<.7*b.distance]
    if len(matches)<POLICY['minimumInliers']:return reject('insufficient_correspondences')
    rp=np.float32([kt[m.queryIdx].pt for m in matches]);sp=np.float32([ks[m.trainIdx].pt for m in matches])
    matrix,flags=cv2.estimateAffinePartial2D(rp,sp,method=cv2.RANSAC,ransacReprojThreshold=1,maxIters=5000,confidence=.999)
    if matrix is None or not np.isfinite(matrix).all():return reject('no_source_transform')
    keep=flags.ravel()>0;errors=np.linalg.norm(cv2.transform(rp[:,None],matrix)[:,0]-sp,axis=1)
    scale=float(np.hypot(matrix[0,0],matrix[0,1]))
    audit.update(inliers=int(keep.sum()),matrix=matrix.tolist(),medianReprojectionPixels=float(np.median(errors[keep])),
        p95ReprojectionPixels=float(np.percentile(errors[keep],95)),scale=scale)
    if (keep.sum()<50 or audit['medianReprojectionPixels']>.5 or audit['p95ReprojectionPixels']>1 or not .5<=scale<=2):
        return reject('alignment_outside_fixed_confidence')
    human=base['human'];ix=np.clip(np.rint(sp[:,0]).astype(int),0,source.width-1);iy=np.clip(np.rint(sp[:,1]).astype(int),0,source.height-1)
    protected=np.isin(human,[2,9,10,11,12,13,14,15,16])
    if base['kind']=='upper':protected|=np.isin(human,[5,6])
    protected_matches=keep&protected[iy,ix]
    if protected_matches.sum()<20:return reject('not_enough_independent_occluder_matches')
    span=np.ptp(sp[protected_matches],axis=0)/np.array(source.size)
    if span[0]<.15 or span[1]<.2:return reject('occluder_correspondences_not_spatially_distributed')
    aligned=cv2.warpAffine(t,matrix,source.size,flags=cv2.INTER_LINEAR)
    coverage=cv2.warpAffine(np.full(t.shape[:2],255,'uint8'),matrix,source.size,flags=cv2.INTER_NEAREST)==255
    ref_alpha=cv2.warpAffine(np.asarray(reference.convert('RGBA'))[:,:,3],matrix,source.size,flags=cv2.INTER_NEAREST)
    coverage&=(ref_alpha==255)&(np.asarray(source.convert('RGBA'))[:,:,3]==255)
    difference=np.max(np.abs(s.astype('float32')-aligned.astype('float32')),axis=2)
    stable=coverage&(difference<=3)
    if (protected&coverage).sum()<500:return reject('not_enough_opaque_occluder_pixels')
    stable_fraction=float(stable[protected&coverage].mean());audit['nonTargetStableFraction']=stable_fraction
    if stable_fraction<.8:return reject('reference_changes_occluders_or_lighting')
    train=(np.asarray(old_mask)>=230)&base['primary']&np.isin(human,base['semanticGarmentClasses'])&~base['protected']&coverage
    train=cv2.erode(train.astype('uint8'),np.ones((5,5),'uint8'))>0
    if train.sum()<500:return reject('not_enough_confirmed_target_correspondences')
    median_shift=float(np.median(difference[train]));audit['clothMedianChangeRGB']=median_shift
    if median_shift<20:return reject('same_view_has_no_observable_cloth_colour_change')
    light=base['sourceLab'][:,:,0];centres=[];signal=[]
    for low in np.linspace(0,100,33)[:-1]:
        group=train&(light>=low)&(light<low+100/32)
        if group.sum()>=50:centres.append(low+50/32);signal.append(float(np.median(difference[group])))
    if len(centres)<4:return reject('insufficient_source_lighting_range')
    # Hair L describes hair, not the cloth it occludes. It cannot determine
    # hidden-cloth response. This mask only records paired unchanged pixels;
    # caller must separately confirm source ownership with two native instances,
    # semantic hair, grounding AND an actually changed local cloth positive.
    # This evidence never authorizes deletion of arbitrary unchanged pixels.
    unchanged=stable
    audit.update(accepted=True,protectedInliers=int(protected_matches.sum()),sourceSize=list(source.size),
        referenceSize=list(reference.size),alignedPixelSha256=pixels(Image.fromarray(aligned)),
        unchangedEvidencePixels=int(unchanged.sum()),expectedClothShiftBins=list(zip(centres,signal)),
        unchangedEvidenceSha256=hashlib.sha256(unchanged.astype('uint8').tobytes()).hexdigest())
    return {'audit':audit,'aligned':Image.fromarray(aligned),'unchanged':unchanged}
