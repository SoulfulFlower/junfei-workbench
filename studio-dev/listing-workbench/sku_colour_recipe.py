"""Measured SKU shade recipes using original GLSL controls, not model repainting."""
import math,re,hashlib,copy
VERSION='measured-sku-native-controls-v2-feedback'
def derive(anchor,target):
    if not isinstance(anchor,(list,tuple)) or len(anchor)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=255 for v in anchor):
        raise ValueError('源衣料主色必须是实测RGB')
    if not isinstance(target,str) or not re.fullmatch('#[a-fA-F0-9]{6}',target):raise ValueError('目标必须为真实色样RGB')
    rgb=[int(target[i:i+2],16) for i in (1,3,5)];source_v=max(anchor);target_v=max(rgb)
    if source_v<1:raise ValueError('源衣料主色过暗，无法可靠编译色样配方')
    settings={'2':{'sigma':0},'3':{'sigma':0},'4':{'clothingMainColor':list(anchor),'bSetMainColor':1,'bUseBlackFun':1,'bAdjustLight':0}}
    gain=1.;branch='measured_anchor_relative_hsv'
    # Targets with HSV saturation < .1 use the shader's separate Lab branch. Never
    # apply the coloured-target brightness formula to that native mapping.
    neutral=target_v==0 or (target_v-min(rgb))/target_v<.1
    if not neutral and target_v<source_v:
        settings['4']['bAdjustLight']=1
        native_mid=source_v+(target_v-source_v)*(source_v/255)
        gain=min(1.,max(0.,target_v/native_mid))
        settings['8']={'enable':1,'RGBchannel':[{'x':0.,'y':0.},{'x':255.,'y':255*gain}]}
        branch='native_light_blend_plus_multiplicative_curve'
    if neutral:branch='native_achromatic_Lab'
    return settings,{'version':VERSION,'sourceRGB':list(anchor),'targetRGB':rgb,'branch':branch,
        'curveGain':gain,'nativeParametersModified':True,'humanReviewed':False,
        'limitations':['色样中间调校准不是全画面或全部材质一致的证明；仍须检查阴影、高光、流苏和目标参考图']}
def compile(source,mask,target):
    from automatic_colour_reference import colour
    anchor=colour(source,mask)
    settings,audit=derive(anchor['rgb'],target)
    audit['sourceSampling']=anchor
    audit['sourcePixelSha256']=hashlib.sha256(source.convert('RGBA').tobytes()).hexdigest()
    audit['maskPixelSha256']=hashlib.sha256(mask.convert('L').tobytes()).hexdigest()
    return {'settings':settings,'audit':audit}

def feedback(source,mask,target,preview,settings):
    """One measured correction through the existing per-channel GPU curves."""
    import numpy as np
    from automatic_colour_reference import colour
    if source.size!=mask.size or preview.size!=source.size:raise ValueError('校准原片、预览与选区尺寸必须相同')
    outside=np.asarray(mask.convert('L'))==0
    if np.any(np.asarray(source.convert('RGBA'))[outside]!=np.asarray(preview.convert('RGBA'))[outside]):
        raise ValueError('预览已改变选区外原像素，不能作为色样校准依据')
    if not isinstance(settings,dict):raise ValueError('校准须保留初始GPU参数')
    baseline=copy.deepcopy(settings);sample=colour(preview,mask)
    desired=[int(target[i:i+2],16) for i in (1,3,5)] if isinstance(target,str) and re.fullmatch('#[a-fA-F0-9]{6}',target) else None
    if desired is None:raise ValueError('目标必须为真实色样RGB')
    audit={'version':VERSION,'method':'one_measured_native_channel_curve_correction','beforeSampling':sample,
        'targetRGB':desired,'previewPixelSha256':hashlib.sha256(preview.convert('RGBA').tobytes()).hexdigest(),
        'outsideChangedPixels':0,'applied':False,'humanReviewed':False}
    if max(abs(a-b) for a,b in zip(sample['rgb'],desired))<=1:
        audit['reason']='already_within_one_channel_step';return {'settings':baseline,'audit':audit}
    curve=baseline.get('8',{})
    identity=[{'x':0.,'y':0.},{'x':255.,'y':255.}]
    if curve.get('enable') and any(curve.get(k,identity)!=identity for k in ('RGBchannel','Rchannel','Gchannel','Bchannel')):
        audit['reason']='existing_curve_retained';return {'settings':baseline,'audit':audit}
    correction={'enable':1}
    for channel,measured,wanted in zip(('Rchannel','Gchannel','Bchannel'),sample['rgb'],desired):
        if not 0<measured<255:raise ValueError('预览通道已截断，不能用曲线虚构丢失的明暗')
        correction[channel]=[{'x':0.,'y':0.},{'x':float(measured),'y':float(wanted)},{'x':255.,'y':255.}]
    baseline['8']={**curve,**correction};audit['applied']=True;audit['reason']='measured_preview_midtones'
    return {'settings':baseline,'audit':audit}
