"""Source-supported fine clothing selections, independent of the GPU renderer.

Coarse semantics cannot resolve every fringe gap. Refine only when measured
chromatic foreground is separated from neutral background; never infer a new
garment from a target colour. No image generation or account writes here.
"""
import hashlib
import numpy as np
import cv2
from PIL import Image

VERSION='garment-colour-mask-v2-supported-sleeves'


def refine(source,mask,kind,cloth,human,*,protected=None):
    rgb=np.asarray(source.convert('RGB'))
    original=np.asarray(mask.convert('L')).copy()
    if original.shape!=rgb.shape[:2] or cloth.shape!=original.shape or human.shape!=original.shape:
        raise ValueError('服装选区、语义及原图尺寸不匹配')
    if kind not in ('upper','lower','full'):raise ValueError('请明确服装部件')
    alpha=original.copy()
    lab=cv2.cvtColor(rgb.astype('float32')/255,cv2.COLOR_RGB2LAB)
    # ATR arm labels also cover sleeves. A second clothing parser plus matching
    # photographed fabric can resolve that conflict; arm labels alone cannot.
    arm_supported=np.zeros(alpha.shape,bool);interior_supported=np.zeros(alpha.shape,bool)
    if kind=='upper':
        core=cv2.erode(((alpha>240)&(cloth==1)&(human==4)).astype('uint8'),np.ones((5,5),'uint8'))>0
        if core.sum()>=100:
            mid=np.median(lab[core],axis=0)
            fabric=(np.linalg.norm(lab[:,:,1:]-mid[1:],axis=2)<6)&(np.abs(lab[:,:,0]-mid[0])<25)
            arm_supported=(cloth==1)&np.isin(human,[14,15])&fabric
            n,parts=cv2.connectedComponents(((alpha>240)|arm_supported).astype('uint8'))
            attached=np.unique(parts[alpha>240]);attached=attached[attached>0]
            arm_supported&=np.isin(parts,attached)
            consensus=cv2.erode(((cloth==1)&(human==4)).astype('uint8'),np.ones((3,3),'uint8'))>0
            near=cv2.dilate((alpha>240).astype('uint8'),np.ones((13,13),'uint8'))>0
            interior_supported=consensus&fabric&near
    skin=np.isin(human,[1,2,3,9,10,11,14,15,16,17])
    skin&=~arm_supported
    # Two independent parsers must agree before a different garment is removed.
    other=((cloth==1)&(human==4)) if kind=='lower' else ((cloth==2)&(human==6)) if kind=='upper' else np.zeros(alpha.shape,bool)
    protection=cv2.dilate(skin.astype('uint8'),np.ones((3,3),'uint8'))>0
    protection|=other
    if protected is not None:
        p=np.asarray(protected.convert('L'))
        if p.shape!=alpha.shape:raise ValueError('保护区必须与原图同尺寸')
        protection|=p>0
    alpha[protection]=0
    arm_recovered=arm_supported&~protection&(alpha<255)
    alpha[arm_recovered]=255
    interior_recovered=interior_supported&~protection&(alpha<255)
    alpha[interior_recovered]=255
    seed=alpha>240
    if seed.sum()<100:raise ValueError('可信衣料选区不足，未放大为整人选区')
    semantic_target=cloth=={'upper':1,'lower':2,'full':3}[kind]
    if (seed&semantic_target).sum()<max(100,seed.size*.005):
        raise ValueError('选区缺少当前服装部件的独立语义支持')
    interior=cv2.erode(seed.astype('uint8'),np.ones((5,5),'uint8'))>0
    if interior.sum()<100:interior=seed
    samples=lab[:,:,1:][interior]
    centre=np.median(samples,axis=0)
    strength=float(np.linalg.norm(centre))
    distance=np.linalg.norm(lab[:,:,1:]-centre,axis=2)
    spread=float(np.percentile(np.linalg.norm(samples-centre,axis=1),98))
    chroma=np.linalg.norm(lab[:,:,1:],axis=2)
    reliable_contrast=strength>=16
    added=removed=0
    if reliable_contrast:
        radius=max(2,min(8,round(min(source.size)*.005)))
        inside_distance=cv2.distanceTransform(seed.astype('uint8'),cv2.DIST_L2,5)
        rows=np.nonzero(seed)[0]
        hem_band=np.indices(seed.shape)[0]>=round(rows.min()+(rows.max()-rows.min())*.78)
        fine_scope=(inside_distance<=radius)|(hem_band if kind=='lower' else False)
        # Source-measured neutral holes are background, even inside a coarse
        # connected hem. Restrict this subtraction to measured colour contrast.
        neutral=(chroma<max(4.,strength*.18))&(distance>max(12.,strength*.55))&fine_scope
        removed=int(((alpha>0)&neutral).sum());alpha[neutral]=0
        near=cv2.dilate(seed.astype('uint8'),np.ones((2*radius+1,)*2,'uint8'))>0
        supported=(distance<min(22.,max(9.,spread+3)))&(chroma>max(8.,strength*.35))
        candidate=near&supported&~protection&(human>0)
        # Require a foreground component attached to existing cloth; no colour
        # island on a nearby hand, background or unrelated object is admitted.
        n,parts=cv2.connectedComponents(candidate.astype('uint8'))
        attached=np.unique(parts[candidate&seed]);attached=attached[attached>0]
        candidate=np.isin(parts,attached)&candidate
        added=int((candidate&(alpha==0)).sum())
        alpha[candidate]=255
        # Preserve partial source-colour edges instead of a solid binary curtain.
        low=max(4.,strength*.18);high=max(low+1.,strength*.45)
        uncertain=near&fine_scope&~protection&(alpha>0)&(chroma<high)
        alpha[uncertain]=np.minimum(alpha[uncertain],np.rint(np.clip((chroma[uncertain]-low)/(high-low),0,1)*255).astype('uint8'))
    # Shoes stay protected; a source-coloured fibre mislabelled as footwear can
    # survive only if it meets the strict attached chromatic evidence above.
    shoes=np.isin(human,[12,13])
    keep_fibre=(distance<min(18.,max(8.,spread+2)))&(chroma>max(10.,strength*.4)) if reliable_contrast else np.zeros(alpha.shape,bool)
    alpha[shoes&~keep_fibre]=0
    alpha[protection]=0
    if 'A' in source.getbands():alpha[np.asarray(source.getchannel('A'))==0]=0
    if kind=='lower':
        from image_fidelity import hardware_protection
        hardware,hardware_receipt=hardware_protection(source,Image.fromarray(alpha))
        alpha[np.asarray(hardware)>0]=0
    else:hardware_receipt={'method':'waist_hardware_heuristic_not_applied_to_upper','candidatePixels':0}
    return Image.fromarray(alpha),{
        'version':VERSION,'method':'independent_semantics_plus_source_chromatic_edge_evidence',
        'category':kind,'sourcePixelSha256':hashlib.sha256(rgb.tobytes()).hexdigest(),
        'selectedPixels':int((alpha>0).sum()),'softPixels':int(((alpha>0)&(alpha<255)).sum()),
        'neutralGapPixelsRemoved':removed,'attachedFabricPixelsRecovered':added,
        'armLabelFabricRecoveredPixels':int(arm_recovered.sum()),
        'consensusFabricInteriorRecoveredPixels':int(interior_recovered.sum()),
        'otherGarmentProtectedPixels':int(other.sum()),'skinProtectedPixels':int(protection.sum()),
        'measuredFabricChroma':strength,'chromaticContrastSupported':reliable_contrast,
        'hardwareProtection':hardware_receipt,'humanReviewed':False,
        'limitations':[] if reliable_contrast else ['中性衣料未启用色度细边恢复；保留原语义选区，复杂边缘仍需检查'],
    }


def prepare(source,kind,*,cache_root=None,protected=None):
    import image_fidelity,garment_auto
    mask,base=image_fidelity.selection(source,kind,cache_root)
    cloth=garment_auto.parser().predict(source)
    human=garment_auto.human_parser().predict(source)
    result,receipt=refine(source,mask,kind,cloth,human,protected=protected)
    return result,{**receipt,'baseSelection':base}
