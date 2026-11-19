"""Deterministic reference-calibrated recoloring. Never contacts a model/provider.

Masks are explicit product selections, not whole-image hue shifts. Output is a
review candidate until its mask edges and target SKU have been checked.
"""
import io
import numpy as np
from PIL import Image


def render_fabric(source, alpha, protected, target, *, texture=1., exposure=0., foreground=None, pattern=None, illumination=None, adjustments=(), saturation=1., contrast=0., shadows=0., highlights=0., colorDetail=0., hue=0., brightness=0., lighting=1., edgeFeather=0., removeCast=False, colorBalance=None, curves=None):
    """Authoritative selection-based renderer for preview, export and saved repair.

    Preserve the original spatial detail separately from broad lighting. Pale
    targets no longer reduce every luminance gradient to 35% of its amplitude.
    Protection always wins, including the original transparency channel.
    This is an independent implementation; it contains no vendor code.
    """
    import cv2
    from colour_tuning import controls,grade
    tuning=controls(dict(saturation=saturation,contrast=contrast,shadows=shadows,highlights=highlights,colorDetail=colorDetail,hue=hue,brightness=brightness,lighting=lighting,edgeFeather=edgeFeather,removeCast=removeCast,colorBalance={} if colorBalance is None else colorBalance,curves={} if curves is None else curves))
    rgb=np.asarray(source.convert('RGB'))
    a=np.asarray(alpha,dtype=np.float64)
    protection=np.asarray(protected.convert('L')) if isinstance(protected,Image.Image) else np.asarray(protected)
    if a.shape!=rgb.shape[:2] or protection.shape!=a.shape or not np.isfinite(a).all() or np.any((a<0)|(a>1)):
        raise ValueError('选区、保护区必须与母版尺寸相同，透明度必须为0–1')
    a=a.copy();a[protection>0]=0
    if np.count_nonzero(a>.9)<50:raise ValueError('请保留至少50个完整衣服选区像素')
    if not 0<=texture<=2 or not -15<=exposure<=15:raise ValueError('纹理或曝光参数超出范围')
    color=np.asarray(target,dtype=np.float32)
    if color.shape!=(3,) or not np.isfinite(color).all() or np.any((color<0)|(color>255)):raise ValueError('目标颜色无效')
    if hue:
        hsv=cv2.cvtColor((color/255).reshape(1,1,3),cv2.COLOR_RGB2HSV);hsv[:,:,0]=(hsv[:,:,0]+hue)%360
        color=cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)[0,0]*255
    original=rgb.astype(np.float64)/255
    if foreground is None:
        # Selection blending is deliberately convex, as in a mask-based colour
        # editor. Extrapolated foreground subtraction can produce cyan seams
        # when the cloth/hair decomposition is inaccurate. It is not used by
        # the interactive pipeline. Explicit legacy matting remains separate.
        foreground=original.copy()
    foreground=np.asarray(foreground,dtype=np.float64)
    if foreground.shape!=original.shape or not np.isfinite(foreground).all():raise ValueError('母版前景缓存无效')
    lab=cv2.cvtColor(foreground.astype(np.float32).clip(0,1),cv2.COLOR_RGB2LAB)
    target_lab=cv2.cvtColor((color/255).reshape(1,1,3),cv2.COLOR_RGB2LAB)[0,0]
    light=lab[:,:,0]
    # Normalised convolution prevents skin/background from bleeding into folds.
    weights=(a>.5).astype(np.float32)
    sigma=max(2.,min(source.size)/160)
    broad=cv2.GaussianBlur(light*weights,(0,0),sigma)/np.maximum(cv2.GaussianBlur(weights,(0,0),sigma),1e-5)
    broad=np.where(weights>0,broad,light)
    centre=float(np.median(light[a>.95]))
    mapped=lab.copy()
    relative=broad-centre
    tonal=.8*relative*(1+tuning['contrast']/100)*tuning['lighting']
    # Smooth, overlapping tonal weights prevent abrupt bands across folds.
    shade=np.clip(-relative/35,0,1);shine=np.clip(relative/35,0,1)
    shade=shade*shade*(3-2*shade);shine=shine*shine*(3-2*shine)
    mapped[:,:,0]=target_lab[0]+exposure+tuning['brightness']+tonal+texture*(light-broad)+tuning['shadows']*shade+tuning['highlights']*shine
    # Only the extreme shoulder is compressed; local knit detail below it is linear.
    high=mapped[:,:,0]>96
    mapped[:,:,0][high]=96+3*(1-np.exp(-(mapped[:,:,0][high]-96)/3))
    mapped[:,:,0]=mapped[:,:,0].clip(1,99)
    if illumination is not None:
        keep=np.asarray(illumination.convert('L') if isinstance(illumination,Image.Image) else illumination,dtype=float)/255
        if keep.shape!=a.shape or not np.isfinite(keep).all() or np.any((keep<0)|(keep>1)):raise ValueError('亮度保护必须与母版尺寸相同')
        mapped[:,:,0]=mapped[:,:,0]*(1-keep)+light*keep
    # Optional local colour variation belongs to the source fabric. Do not
    # transfer its old broad colour cast, or tint neutral black/white targets.
    mapped[:,:,1:]=target_lab[1:]*tuning['saturation']
    if tuning['colorDetail'] and not tuning['removeCast']:
        chroma=lab[:,:,1:]
        smooth=cv2.GaussianBlur(chroma*weights[:,:,None],(0,0),sigma)/np.maximum(cv2.GaussianBlur(weights,(0,0),sigma)[:,:,None],1e-5)
        residual=np.clip(chroma-smooth,-8,8)
        neutral=min(1.,float(np.linalg.norm(target_lab[1:]))/12)
        mapped[:,:,1:]+=tuning['colorDetail']*neutral*residual*tuning['saturation']
    if pattern:
        dot=np.asarray(pattern['color'],dtype=np.float32)/255
        dot_lab=cv2.cvtColor(dot.reshape(1,1,3),cv2.COLOR_RGB2LAB)[0,0]
        edge=float(pattern.get('threshold',55))/100*100
        t=np.clip((light-edge+7)/14,0,1);t=t*t*(3-2*t)
        if pattern.get('kind')=='light':t=1-t
        other=mapped.copy();other[:,:,0]=np.clip(dot_lab[0]+.8*(light-centre),1,99);other[:,:,1:]=dot_lab[1:]
        mapped=mapped*(1-t[:,:,None])+other*t[:,:,None]
    replacement=cv2.cvtColor(mapped.astype(np.float32),cv2.COLOR_LAB2RGB)
    replacement=grade(replacement,tuning)
    # Alpha expresses coverage. A half-selected edge must remain half mixed,
    # rather than becoming fully recoloured and spilling into hair or skin.
    weight=a*a*(3-2*a)
    if tuning['edgeFeather']:
        # Inward-only feather: never expand into skin, hair or protected pixels.
        softened=cv2.GaussianBlur(weight,(0,0),tuning['edgeFeather'])
        weight=np.minimum(weight,softened);weight[a==0]=0
    composed=original*(1-weight[:,:,None])+replacement*weight[:,:,None]
    # Local colour-cast adjustments are explicit, source-bound masks. They do
    # not invent texture or move an edge and are included in the same recipe.
    for adjustment in adjustments:
        mask=np.asarray(adjustment['mask'].convert('L'),dtype=float)/255
        if mask.shape!=a.shape:raise ValueError('局部去色边选区尺寸不匹配')
        mask=mask.copy();mask[a==0]=0
        corrected=cv2.cvtColor(composed.astype('float32').clip(0,1),cv2.COLOR_RGB2LAB)
        sample=cv2.cvtColor((np.asarray(adjustment['color'],dtype='float32')/255).reshape(1,1,3),cv2.COLOR_RGB2LAB)[0,0]
        corrected[:,:,1:]=sample[1:]
        if adjustment.get('sourceLightness'):corrected[:,:,0]=light
        corrected=cv2.cvtColor(corrected,cv2.COLOR_LAB2RGB)
        composed=composed*(1-mask[:,:,None])+corrected*mask[:,:,None]
    result=np.rint(composed*255).clip(0,255).astype('uint8')
    result[a==0]=rgb[a==0]
    output=Image.fromarray(result)
    if 'A' in source.getbands():output.putalpha(source.getchannel('A'))
    return output


def recolor_luminance(source, mask, reference, reference_box, *, tone_mapping='quantile', blend=True):
    """Transfer fabric shade without independent RGB curves producing false hues.

    Only source luminance supplies texture. The target sample supplies one Lab
    chroma and its luminance distribution; no reference texture is copied.
    """
    import cv2
    if mask.size != source.size:
        raise ValueError('Mask must match the original image dimensions')
    original=np.asarray(source.convert('RGB'))
    alpha=np.asarray(mask.convert('L'),dtype=np.float32)/255
    if np.count_nonzero(alpha>.9)<50:
        raise ValueError('A product fabric mask is required')
    x1,y1,x2,y2=reference_box
    if not (0<=x1<x2<=reference.width and 0<=y1<y2<=reference.height):
        raise ValueError('Reference sample must be inside the image')
    target=np.asarray(reference.convert('RGB'))[y1:y2,x1:x2]
    if target.shape[0]*target.shape[1]<50:
        raise ValueError('Reference fabric sample is too small')
    lab=cv2.cvtColor(original.astype(np.float32)/255,cv2.COLOR_RGB2LAB)
    ref=cv2.cvtColor(target.astype(np.float32)/255,cv2.COLOR_RGB2LAB)
    quantiles=[0,2,10,25,50,75,90,98,100]
    selected=lab[:,:,0][alpha>.9]
    before=np.percentile(selected,quantiles)
    after=np.percentile(ref[:,:,0],quantiles)
    before,indices=np.unique(before,return_index=True)
    mapped=lab.copy()
    if tone_mapping=='quantile':
        mapped[:,:,0]=np.interp(lab[:,:,0],before,after[indices])
    elif tone_mapping in ('affine','soft_affine'):
        # A single slope preserves local texture contrast. A steep segmented
        # curve can amplify the fine knit into a metallic-looking surface.
        low,high=np.percentile(selected,[10,90])
        target_low,target_high=np.percentile(ref[:,:,0],[10,90])
        ceiling=.45 if np.median(ref[:,:,0])>65 else 1
        gain=np.clip((target_high-target_low)/max(high-low,1),.35,ceiling) if ceiling<1 else 1.
        centre=np.median(ref[:,:,0]);delta=gain*(lab[:,:,0]-np.median(selected))
        if tone_mapping=='soft_affine':
            # Pale cloth must retain folds without clipping high points into
            # metallic white flecks. Smooth highlight compression is monotonic.
            delta=.6*(lab[:,:,0]-np.median(selected))
            room=np.where(delta>=0,max(100-centre,.01),max(centre,.01))
            mapped[:,:,0]=centre+room*np.tanh(delta/room)
        else:mapped[:,:,0]=np.clip(centre+delta,0,100)
    else:
        raise ValueError('Unknown fabric tone mapping')
    mapped[:,:,1:]=np.median(ref.reshape(-1,3),axis=0)[1:]
    mapped=cv2.cvtColor(mapped,cv2.COLOR_LAB2RGB)*255
    pixels=original*(1-alpha[:,:,None])+mapped*alpha[:,:,None] if blend else mapped
    result=np.rint(pixels).clip(0,255).astype('uint8')
    return Image.fromarray(result)


def fabric_matte(source, selection, protected=None, radius=4, *, foreground_seeds=None, background_seeds=None):
    """Estimate cloth ownership at mixed hair/garment pixels, without a model."""
    import cv2
    from pymatting import estimate_alpha_cf
    if source.size!=selection.size or (protected is not None and protected.size!=source.size):
        raise ValueError('Selection and protection must match the source')
    if not isinstance(radius,int) or not 1<=radius<=12:
        raise ValueError('Matte radius must be between 1 and 12')
    selected=np.asarray(selection.convert('L'))>127
    if selected.sum()<50:raise ValueError('A product fabric selection is required')
    kernel=np.ones((radius*2+1,radius*2+1),np.uint8)
    inside=cv2.erode(selected.astype('uint8'),kernel)>0
    possible=cv2.dilate(selected.astype('uint8'),kernel)>0
    trimap=np.zeros(selected.shape,dtype=np.float64);trimap[possible]=.5;trimap[inside]=1
    if protected is not None:trimap[np.asarray(protected.convert('L'))>0]=0
    for seeds,value in ((foreground_seeds,1),(background_seeds,0)):
        if seeds is None:continue
        points=np.asarray(seeds,dtype=float)
        if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all():raise ValueError('Invalid matte constraint points')
        for x,y in points:
            if not (0<=x<source.width and 0<=y<source.height):raise ValueError('Matte constraint outside source')
            x,y=int(x),int(y)
            if value==1 and protected is not None and np.asarray(protected.convert('L'))[y,x]>0:raise ValueError('Foreground constraint conflicts with protection')
            # Thin cloth details and thin accessory gaps can disappear when
            # erosion builds the trimap. Retain their original semantic anchors.
            trimap[y,x]=value
    if not np.any(trimap==1):raise ValueError('A fabric interior must remain unprotected')
    if not np.any(trimap==.5):return trimap
    alpha=estimate_alpha_cf(np.asarray(source.convert('RGB'),dtype=np.float64)/255,trimap,cg_kwargs={'maxiter':1000})
    alpha[trimap==0]=0;alpha[trimap==1]=1
    alpha[alpha<1/255]=0
    return alpha


def recolor_matted(source, alpha, reference, reference_box, *, tone_mapping='affine', foreground=None):
    """Replace only the estimated cloth contribution, preserving mixed hair.

    I = alpha * F + (1-alpha) * B. Applying I + alpha*(newF-F)
    removes the original fabric contribution at soft edges instead of blending
    it into the replacement and leaving a red fringe.
    """
    from pymatting import estimate_foreground_ml
    original=np.asarray(source.convert('RGB'),dtype=np.float64)/255
    alpha=np.asarray(alpha,dtype=np.float64)
    if alpha.shape!=original.shape[:2] or not np.isfinite(alpha).all() or np.any((alpha<0)|(alpha>1)):
        raise ValueError('Invalid fabric alpha')
    if np.count_nonzero(alpha>.9)<50:raise ValueError('A fabric interior is required')
    foreground=estimate_foreground_ml(original,alpha) if foreground is None else np.asarray(foreground,dtype=np.float64)
    if foreground.shape!=original.shape or not np.isfinite(foreground).all():raise ValueError('Invalid cached fabric foreground')
    foreground_image=Image.fromarray(np.rint(foreground*255).clip(0,255).astype('uint8'))
    mapped=np.asarray(recolor_luminance(foreground_image,Image.fromarray(np.rint(alpha*255).astype('uint8')),reference,reference_box,tone_mapping=tone_mapping,blend=False),dtype=np.float64)/255
    result=np.rint((original+alpha[:,:,None]*(mapped-foreground))*255).clip(0,255).astype('uint8')
    result[alpha==0]=np.asarray(source.convert('RGB'))[alpha==0]
    return Image.fromarray(result)


def recolor(source, mask, reference, reference_box):
    original=np.asarray(source.convert('RGB'),dtype=np.float32)
    alpha=np.asarray(mask.convert('L').resize(source.size),dtype=np.float32)/255
    if not np.any(alpha>.5):
        raise ValueError('A product mask is required')
    target=np.asarray(reference.convert('RGB').crop(reference_box),dtype=np.float32).reshape(-1,3)
    if len(target)<50:
        raise ValueError('Reference fabric sample is too small')
    selected=original[alpha>.9]
    # Per-channel monotonic transport preserves weave and relative light/shadow.
    quantiles=[0,2,10,25,50,75,90,98,100]
    mapped=original.copy()
    for channel in range(3):
        before=np.percentile(selected[:,channel],quantiles)
        after=np.percentile(target[:,channel],quantiles)
        before,indices=np.unique(before,return_index=True)
        mapped[:,:,channel]=np.interp(original[:,:,channel],before,after[indices])
    result=np.rint(original*(1-alpha[:,:,None])+mapped*alpha[:,:,None]).clip(0,255).astype('uint8')
    return Image.fromarray(result)
