"""Validate browser execution receipts and actual immutable outside pixels."""
import numpy as np
import hashlib
from PIL import Image
import official_image_templates as library

def validate(source,mask,rendered,receipt):
    if not isinstance(receipt,dict) or receipt.get('renderer') not in ('original-glsl-webgl1','original-glsl-webgl2-native-quad-v2'):raise ValueError('缺少原始GLSL执行回执')
    expected=library.colour_resources()
    if receipt.get('sourceHashes')!=expected['sourceHashes']:raise ValueError('着色器源码哈希与已核验原件不一致')
    passes=receipt.get('passes')
    filters=expected['config']['filters']
    if not isinstance(passes,list) or [(r.get('index'),r.get('fs')) for r in passes]!=[(r['index'],r['fs']) for r in filters]:
        raise ValueError('原始滤镜执行顺序不完整')
    if source.size!=rendered.size or source.size!=mask.size:raise ValueError('官方滤镜结果尺寸不匹配')
    original=np.asarray(source.convert('RGBA'));actual=np.asarray(rendered.convert('RGBA'));a=np.asarray(mask.convert('L'))
    if receipt['renderer']=='original-glsl-webgl2-native-quad-v2':
        if receipt.get('boundaryPolicy')!='preserve_outside_selection_source_rgba':raise ValueError('请显式启用选区外原像素保护；原生GPU输出仅作对照')
        if receipt.get('hashPixelOrder')!='rgba8_top_to_bottom' or receipt.get('outputSHA')!=hashlib.sha256(actual.tobytes()).hexdigest():
            raise ValueError('GPU输出回执与实际RGBA像素哈希不一致')
    if np.count_nonzero(a>240)<50:raise ValueError('需要有效商品选区')
    outside=int(np.any(actual[a==0]!=original[a==0],axis=-1).sum())
    alpha=int(np.count_nonzero(actual[:,:,3]!=original[:,:,3]))
    if outside or alpha:raise ValueError('官方滤镜结果改变了保护区域或透明度，不能保存为候选')
    return {'renderer':'official_original_glsl','passes':len(passes),'outsideChangedPixels':outside,
            'alphaChangedPixels':alpha,'sourceHashesValidated':True,'reportedExecution':'client_webgl',
            'boundaryPolicy':receipt.get('boundaryPolicy','legacy_restore_outside'),
            'nativeOutputSHA':receipt.get('nativeOutputSHA'),'outputSHA':receipt.get('outputSHA'),
            'reviewStillRequired':True,'humanReviewed':False}
