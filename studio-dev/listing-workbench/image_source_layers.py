"""Original-pixel product layers on original-template-directed artwork."""
import io,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,ImageDraw
import app_paths
import image_fidelity as fidelity

VERSION='original-product-layers-v7-confident-source-boundaries'

def neutralize_plate(image):
    """Neutralize the generated setting before any source photo is composited."""
    import cv2
    rgb=np.asarray(image.convert('RGB'))
    lab=cv2.cvtColor(rgb.astype('float32')/255,cv2.COLOR_RGB2LAB)
    original=np.median(lab[:,:,1:].reshape(-1,2),axis=0)
    lab[:,:,1:]=0
    converted=cv2.cvtColor(lab,cv2.COLOR_LAB2RGB)
    out=Image.fromarray(np.rint(converted*255).clip(0,255).astype('uint8'))
    return out,{'method':'neutral_Lab_generated_background_only','beforeMedianAB':original.tolist(),
                'productPixelsProcessed':False,'preservesBackgroundLightness':True}

def check_plate(engine,url,photographic=False):
    value=engine.json_model(
        'Inspect this EMPTY background design plate. Return {clear:bool,issues:[str]}. '
        'clear is true ONLY when there is no person, body part, clothing, shoe, product, product-detail photo or silhouette. '
        'Empty setting, background, unprinted design surfaces, hairlines or circular empty areas are permitted. '
        'Any garment or texture macro copied from the input must be removed before real source layers are composited.'+
        (' This is a REAL photographic scene: also reject dotted circles, arrows, infographic rings, blank cards, '
         'placeholder boxes and floating graphic panels. Real walls, floors, furniture and natural shadows are allowed.' if photographic else ''),
        {},[url],'original_product_background_plate_check')
    if type(value.get('clear')) is not bool:raise ValueError('背景检查未返回明确结论，未继续合成')
    return value

def normalized_box(value,name):
    if (not isinstance(value,list) or len(value)!=4 or any(type(v) not in (int,float) or not 0<=v<=1 for v in value)
            or value[2]<=0 or value[3]<=0 or value[0]+value[2]>1.001 or value[1]+value[3]>1.001):
        raise ValueError('原片图层的'+name+'需要有效归一化坐标')
    return value

def validate_layers(shot):
    layers=shot.get('sourceLayers')
    if not isinstance(layers,list) or not 1<=len(layers)<=4:raise ValueError('原片锁定模式需要1–4个有来源的真实图层')
    for layer in layers:
        if layer.get('kind') not in ('wearer','detail') or layer.get('shape','rectangle') not in ('rectangle','ellipse'):
            raise ValueError('原片图层类型无效')
        normalized_box(layer.get('box'),'画面位置');normalized_box(layer.get('crop',[0,0,1,1]),'原图裁切')
        if layer['kind']=='wearer' and layer.get('shape','rectangle')!='rectangle':raise ValueError('完整穿着图层不能做圆形裁切')
    return layers

def prepare(source,source_hash,kind):
    import foreground_matting
    model_identity=foreground_matting.identity()
    model_key=hashlib.sha256(json.dumps(model_identity,sort_keys=True).encode()).hexdigest()[:16]
    folder=app_paths.DATA/'source-product-layers'/source_hash;folder.mkdir(parents=True,exist_ok=True)
    store=folder/(VERSION+'-'+kind+'-'+model_key+'.npz');meta=folder/(VERSION+'-'+kind+'-'+model_key+'.json')
    if store.exists() and meta.exists():
        with np.load(store,allow_pickle=False) as values:
            foreground=values['foreground'];alpha=values['alpha'];mask=Image.fromarray(values['mask'])
        receipt=json.loads(meta.read_text('utf-8'))
        if alpha.shape!=(source.height,source.width):raise ValueError('原片图层缓存尺寸变化')
        return foreground,alpha,mask,receipt
    foreground,alpha,receipt=fidelity.source_layer(source,kind=kind)
    import garment_colour_mask
    mask,selection=garment_colour_mask.prepare(source,kind)
    protection,hardware=(fidelity.hardware_protection(source,mask) if kind=='lower' else
        (Image.new('L',source.size),{'method':'waist_hardware_heuristic_not_applied_to_upper','candidatePixels':0}))
    from PIL import ImageChops
    mask=ImageChops.subtract(mask,protection)
    receipt.update(sourceSha256=source_hash,version=VERSION,selection=selection,hardwareProtection=hardware,
        alphaSha256=hashlib.sha256(alpha.tobytes()).hexdigest(),humanReviewed=False)
    # Immutable named cache is reusable only for this exact source hash.
    np.savez_compressed(store,foreground=foreground,alpha=alpha,mask=np.asarray(mask))
    meta.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf-8')
    return foreground,alpha,mask,receipt

def _box(box,size):
    x,y,w,h=box;W,H=size
    return (round(x*W),round(y*H),round((x+w)*W),round((y+h)*H))

def source_cut_edges(alpha):
    """Only confident source coverage establishes a photographic frame cut.

    Very low matting alpha on white/JPEG borders is retained in compositing,
    but cannot override the planner's horizontal placement.
    """
    edges={'top':alpha[0],'bottom':alpha[-1],'left':alpha[:,0],'right':alpha[:,-1]}
    return {key:bool(np.count_nonzero(value>=.5)>=max(6,round(len(value)*.005)))for key,value in edges.items()}

def tiled_details(shot):
    """A fully covered real-photo collage needs no extra generated backdrop."""
    if shot.get('layout')!='detail' or shot.get('copy') or not shot.get('sourceLayers'):return False
    layers=validate_layers(shot)
    if any(p['kind']!='detail' or p.get('shape','rectangle')!='rectangle'for p in layers):return False
    cover=Image.new('L',(1600,1600));draw=ImageDraw.Draw(cover)
    for layer in layers:
        x0,y0,x1,y1=_box(layer['box'],cover.size)
        draw.rectangle((x0,y0,x1-1,y1-1),fill=255)
    return bool((np.asarray(cover)>0).all())

def compose(source,background,layers,foreground,alpha,garment_mask,size=1600):
    """Resample only real source pixels; no AI redraw of product or details."""
    canvas=ImageOps.fit(background.convert('RGB'),(size,size),method=Image.Resampling.LANCZOS)
    result_mask=Image.new('L',canvas.size)
    rgba=Image.fromarray(np.rint(foreground*255).clip(0,255).astype('uint8')).convert('RGBA')
    rgba.putalpha(Image.fromarray(np.rint(alpha*255).clip(0,255).astype('uint8')))
    placements=[]
    for layer in layers:
        crop=_box(layer.get('crop',[0,0,1,1]),source.size);box=_box(layer['box'],canvas.size)
        requested_crop=crop
        tw,th=box[2]-box[0],box[3]-box[1]
        if layer['kind']=='wearer':
            visible=Image.fromarray((alpha>1/255).astype('uint8')*255).getbbox()
            if visible:crop=(min(crop[0],visible[0]),min(crop[1],visible[1]),max(crop[2],visible[2]),max(crop[3],visible[3]))
            piece=rgba.crop(crop);mask=garment_mask.crop(crop)
            cuts=source_cut_edges(alpha)
            scale=min(tw/piece.width,th/piece.height)
            # A portrait cut by both source top and bottom must span the
            # output height; otherwise a real flat torso/jeans cut floats.
            if cuts['top'] and cuts['bottom'] and crop[1]==0 and crop[3]==source.height:
                scale=max(scale,size/piece.height)
            dims=(max(1,round(piece.width*scale)),max(1,round(piece.height*scale)))
            if dims[0]>size or dims[1]>size:raise ValueError('原片双边截断无法无损放入画布，未裁商品或拉伸')
            piece=piece.resize(dims,Image.Resampling.LANCZOS);mask=mask.resize(dims,Image.Resampling.LANCZOS)
            xy=(box[0]+(tw-dims[0])//2,box[1]+(th-dims[1])//2)
            # The source already cuts this wearer at the image edge. Keep that
            # real cut at the output edge instead of floating a flat torso cut
            # inside a new scene. Never synthesize a missing head or body.
            if crop[1]==0 and cuts['top']:xy=(xy[0],0)
            if crop[3]==source.height and cuts['bottom']:xy=(xy[0],size-dims[1])
            if cuts['left']!=cuts['right']:
                if crop[0]==0 and cuts['left']:xy=(0,xy[1])
                if crop[2]==source.width and cuts['right']:xy=(size-dims[0],xy[1])
        else:
            piece=ImageOps.fit(source.crop(crop).convert('RGBA'),(tw,th),method=Image.Resampling.LANCZOS)
            mask=ImageOps.fit(garment_mask.crop(crop),(tw,th),method=Image.Resampling.LANCZOS)
            if layer.get('shape')=='ellipse':
                stencil=Image.new('L',(tw,th));ImageDraw.Draw(stencil).ellipse((0,0,tw-1,th-1),fill=255)
                piece.putalpha(stencil)
                from PIL import ImageChops
                mask=ImageChops.multiply(mask,stencil)
            xy=box[:2];dims=(tw,th)
        canvas.paste(piece,xy,piece.getchannel('A'))
        # Last layer owns its covered pixels, including its protected background.
        result_mask.paste(mask,xy,piece.getchannel('A'))
        placements.append({'kind':layer['kind'],'sourceCropPixels':list(crop),'requestedCropPixels':list(requested_crop),'outputBoxPixels':[xy[0],xy[1],*dims],
                           'shape':layer.get('shape','rectangle'),'sourcePixelsNeverRedrawn':True,
                           **({'sourceCutEdges':cuts,'placementPolicy':'confident_source_edges_preserve_planned_horizontal_position',
                               'uniformScale':scale,'stretched':False}if layer['kind']=='wearer'else{})})
    return canvas,result_mask,placements

def plate_prompt(plan,shot,template,brief,no_text):
    from official_image_templates import raw_prompt_section
    copy=[] if no_text else shot.get('copy',[])
    return ('Create ONE SQUARE 1:1 ecommerce design background and typography plate. The next stage composites '
        'REAL source product pixels into the designated layers; do not draw any person, body, garment, product, '
        'product inset, simulated detail, silhouette, ghost shape or placeholder rectangle. All product areas must '
        'remain clean photographic background, continuous with their surroundings. Reference image 1 supplies '
        'camera perspective only. '+('Reference image 2 is the actual original template artwork.\n'+raw_prompt_section(template)if template else
            'This slot has NO seller template. Create a continuous natural photographic setting from the current scene description, without infographic panels or template graphics.')+
        '\nCURRENT SHOT: '+json.dumps(shot,ensure_ascii=False)+
        '\nSET STYLE: '+json.dumps(plan['style'],ensure_ascii=False)+
        '\nUSER REQUIREMENTS: '+brief+
        '\nThe exact product and all detail photography will be composited later from the real source. '+
        ('Use the original template composition, lighting hierarchy and design character for this square canvas; 'if template else
         'Use the current photographic scene and lighting for this square canvas; ')+
        'keep its foreground positions empty. Do NOT reproduce its example people or products. '
        'Neutral daylight, neutral surfaces, no amber/orange grading. No border or margin. '
        'Only this exact copy may appear: '+json.dumps(copy,ensure_ascii=False)+
        '. An empty list means absolutely no words, labels, logos, icons or captions. '
        'Native SQUARE 1:1 canvas. Never draw the source layers or show a blueprint. '+
        ('[FINAL CURRENT-SLOT OVERRIDE] This is ONE real fashion location photograph, not an infographic. '
         'Use the full original template only for photographic visual emphasis. Do not draw its ring, dotted lines, '
         'arrows, circular track, blank cards, bottom matrix, floating panels or placeholders. '
         'Continuous realistic neutral wall/floor/location. No graphic overlays or design slabs.' if shot['layout']=='scene' else ''))

def reusable_plates(parent):
    """Reuse the exact accepted background, including any completed cleanup."""
    originals=parent.get('backgroundPlates',[])+parent.get('backgroundCleanups',[])
    values=[]
    for shot in parent['plan']['shots']:
        if shot['layout']=='main' or (shot['layout']=='detail' and not shot.get('copy') and parent['request'].get('apparelSuite')):continue
        result=next((r for r in parent.get('results',[]) if r.get('index')==shot['index']),None)
        approved=next((r for r in originals if result and r.get('raw')==result.get('rawModelOutput')),None)
        if not approved or approved.get('emptyPlateCheck',{}).get('clear') is not True:
            raise ValueError('原任务没有可核对的已清理背景；不会复用未通过检查的原始背景')
        values.append({**approved,'index':shot['index'],'reusedFromResultIndex':result['index']})
    return values


def reusable_repair_plate(parent):
    if parent.get('status')not in ('completed','needs_revision')or parent.get('request',{}).get('mode')!='repair':raise ValueError('原修图尚无明确完成的背景')
    results=parent.get('results',[])
    final=next((result.get('rawModelOutput')for result in results if result.get('rawModelOutput')),None)
    plate=next((p for p in parent.get('backgroundPlates',[])+parent.get('backgroundCleanups',[])if p.get('raw')==final and p.get('emptyPlateCheck',{}).get('clear')is True),None)
    if not plate:raise ValueError('原修图没有已核验的最终空背景，未重发模型')
    return {**plate,'reusedFromTaskId':parent['id']}


def repair(task,prompt,refs,paid_image):
    """Explicit background-only repair; never imply original pixels were relit."""
    import image_engine as engine
    source,digest=engine.asset(refs[0])
    foreground,alpha,mask,receipt=prepare(source,digest,task['request']['fidelityPolicy']['garmentKind'])
    instruction=(prompt+'\n\n[EXPLICIT ORIGINAL-PIXEL BACKGROUND REPAIR]\n'
        'The actual wearer and garment are restored from the source photo after this step. '
        'Generate ONLY an empty photographic background satisfying the current background request. '
        'Remove all people, body parts, garments, shoes and product shapes. No silhouette, ghost, '
        'placeholder or garment texture remains. Preserve source camera perspective and floor plane. '
        'Use neutral D65 daylight, neutral surfaces and natural shadows; no added text. '
        'Do not attempt to relight, redraw or sharpen the garment; that is kept from source pixels. '
        'Deliver one native square background plate.')
    reused=task['request'].get('reusedRepairPlate')
    plate=(dict(reused)if reused else paid_image(task,instruction,refs,scope='source-locked-repair-plate'))
    task['backgroundPlates']=task.get('backgroundPlates',[])+[plate];engine.save(task)
    check=(plate['emptyPlateCheck']if reused else check_plate(engine,plate['raw'],True));plate['emptyPlateCheck']=check;engine.save(task)
    if not check['clear']:
        from official_image_templates import expert_prompt
        cleanup,audit=expert_prompt('99','Remove every person, body, garment, shoe, product, silhouette and ghost. Keep only a continuous empty photographic background, with no text or placeholders.',[])
        plate=paid_image(task,cleanup,[plate['raw']],scope='source-locked-repair-cleanup')
        plate['officialRepair']=audit
        task['backgroundCleanups']=task.get('backgroundCleanups',[])+[plate];engine.save(task)
        check=check_plate(engine,plate['raw'],True);plate['emptyPlateCheck']=check;engine.save(task)
        if not check['clear']:raise ValueError('修图背景仍有人物/商品，保留结果并停止，未叠加重复人物')
    background,_=engine.asset(plate['raw'])
    tone=None
    if task['request'].get('neutralBackground'):background,tone=neutralize_plate(background)
    # Keep exact original coordinates at the original source resolution. This
    # prevents a regenerated wearer or garment from leaking through the edges.
    artwork,pixels=fidelity.composite_layer(source,background,foreground,alpha)
    saved=engine.cache(artwork)
    # Fit the original photographed wearer naturally onto the square plate.
    # Resizing a portrait composite directly to a square stretches the product.
    square,_,placements=compose(source,background,[{'kind':'wearer','box':[0,0,1,1],'crop':[0,0,1,1]}],foreground,alpha,mask)
    delivered=engine.cache(square)
    return {'index':len(task['results']),'image':delivered['url'],'raw':saved['url'],'sha256':delivered['sha256'],
        'rawModelOutput':plate['raw'],'productionMethod':'original-pixel-background-repair-v2-natural-aspect',
        'source':refs[0],'sourceSha256':digest,'sourceLayerReceipt':receipt,'pixelCheck':pixels,
        'backgroundTone':tone,'sourcePlacements':placements,'aspectValid':True,'width':1600,'height':1600,'humanReviewed':False,
        'limitations':['保留原姿态及原商品像素；只调整背景，不声称商品本身已重新打光或补出新细节']}


def render(task,plan,shot,source_url,template,paid_image):
    import image_engine as engine
    source,digest=engine.asset(source_url)
    foreground,alpha,mask,receipt=prepare(source,digest,task['request']['fidelityPolicy']['garmentKind'])
    if shot['layout']=='main' or tiled_details(shot):
        layers=([{'kind':'wearer','box':[0,0,1,1],'crop':[0,0,1,1]}] if shot['layout']=='main' else validate_layers(shot))
        plate=Image.new('RGB',(1600,1600),'white');model_result=None
    else:
        layers=validate_layers(shot)
        reused=task['request'].get('reusedPlates',{}).get('plates',[])
        model_result=next((dict(r) for r in reused if r['index']==shot['index']),None)
        if model_result is None:
            model_result=paid_image(task,plate_prompt(plan,shot,template,task['request']['brief'],task['request']['noText']),[source_url]+([template['url']]if template else[]))
        # Persist the paid response before any local operation can fail.
        model_result.update(productionMethod='original-template-background-plate',shot=shot)
        task['backgroundPlates']=task.get('backgroundPlates',[])+[model_result];engine.save(task)
        check=(model_result['emptyPlateCheck'] if reused and model_result.get('emptyPlateCheck',{}).get('clear') is True else
               check_plate(engine,model_result['raw'],shot['layout']=='scene'))
        model_result['emptyPlateCheck']=check;engine.save(task)
        if not check['clear']:
            # One explicit cleanup through the original removal template, never
            # another attempt at generating the product or an unbounded retry.
            import official_image_templates as library
            prompt,expert=library.expert_prompt('99',
                'Remove ALL people, bodies, skin, sweaters, trousers, all garments and shoes, every photographed product and every product-detail inset. '
                'Keep ONLY the empty background and existing design surfaces/lines. Reconstruct a continuous clean empty setting, '
                'including floor and wall wherever the wearer/product was. No product, person, mannequin, silhouette, ghost, texture swatch or new object may remain. '
                'Remove empty infographic placeholder circles and guide lines as well; the real source-detail layers will supply the finished original-template hierarchy. '
                'Preserve the existing overall background palette, layout and perspective. This is an empty plate for later local compositing.',[])
            cleaned=paid_image(task,prompt,[model_result['raw']],scope='empty-background-cleanup')
            cleaned.update(officialRepair=expert,derivedFrom=model_result['raw'],productionMethod='verified-empty-template-background')
            task['backgroundCleanups']=task.get('backgroundCleanups',[])+[cleaned];engine.save(task)
            cleaned['emptyPlateCheck']=check_plate(engine,cleaned['raw'],shot['layout']=='scene');engine.save(task)
            if not cleaned['emptyPlateCheck']['clear']:raise ValueError('原修图移除模板后背景仍含商品；保留回执，未叠加成重复商品或盲目重试')
            model_result=cleaned
        plate,_=engine.asset(model_result['raw'])
        if not model_result['aspectValid'] and not task['request']['noText']:
            raise ValueError('含字版式的模型原生宽高比不符；保留原图，不裁切文字')
    tone=None
    if task['request'].get('neutralBackground'):plate,tone=neutralize_plate(plate)
    artwork,out_mask,placements=compose(source,plate,layers,foreground,alpha,mask)
    saved=engine.cache(artwork);saved_mask=engine.cache(out_mask)
    return {'index':len(task['results']),'image':saved['url'],'raw':saved['url'],'sha256':saved['sha256'],
        'rawModelOutput':model_result['raw'] if model_result else source_url,'aspectValid':True,'width':1600,'height':1600,
        'productionMethod':VERSION,'source':source_url,'sourceSha256':digest,'sourceLayerReceipt':receipt,
        'sourcePlacements':placements,'garmentMask':saved_mask['url'],'garmentMaskSha256':saved_mask['sha256'],
        'maskProvenance':{'method':VERSION,'sourceSha256':digest,'placements':placements},
        'officialTemplate':template,'backgroundTone':tone,'humanReviewed':False}
