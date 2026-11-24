"""One grounded local selection attempt; never edits RGB or resets the globe.

The authenticated caller owns account/product/QC lookups and Codex transport.
QC locations and model ribbons are hypotheses, not foreground truth. A fresh
local grounding, native source segmentation and a fresh whole-source review
are mandatory; colour acceptance remains a separate caller-owned check.
"""
from pathlib import Path
import copy
import hashlib
import json
import math
import threading
import time
import uuid
import cv2
import numpy as np
from PIL import Image, ImageDraw
import automatic_garment_selection as selection
import automatic_mask_revision as revision
import local_hair_matte
import reference_pose_evidence

VERSION='automatic-garment-selection-local-v10-paired-continuous-edges'
CACHE_DIR='ls1'
LOCK=threading.RLock()
POLICY={'maximumRegions':6,'maximumSidePixels':256,'minimumSidePixels':128,
    'preferredNativeSidePixels':256,'maximumUnionFraction':.35,'maximumLocalRounds':1,
    'qualityThresholdsUnchanged':True,'maximumLeakRemovedFraction':.0005,
    'maximumLeakRemovedPixels':512,'maximumRemovableAlpha':229,
    'maximumHairMatteChangedFraction':.005,'maximumHairMatteRoiFraction':.15}
GROUNDING_INSTRUCTION='''Inspect the immutable source and actual prior colour
output. Image 1 is the full original SOURCE, image 2 the actual OLD alpha
overlay, image 3 the QC-reviewed OUTPUT. Images 4 onward have aligned crops: SOURCE,
OLD ALPHA, OLD OVERLAY, OUTPUT. Each row uses ONE exact original-source bbox.
OLD ALPHA is white=255 selected, black=0 unselected, grey=fractional coverage.
Server QC locations are MACHINE HYPOTHESES, never true foreground labels.
Each region preserves reportedKind/reportReason as UNTRUSTED prior QC.
Additional same-hair-object coverage regions are AUTOMATIC source hypotheses,
not confirmed new defects. Inspect each actual source/alpha/output crop and
return no_edit_justified when already correct. Both
miss and possible leak reports may be investigated. true_leak is supported
ONLY for a small weak-alpha selection on a SOURCE-CONFIRMED non-target.
Confirmed overlapping HAIR also supports source-RGB-guided continuous alpha
matting after two native instances and independent semantic hair evidence.
Do not infer an alpha or delete green knit visible between hair strands.
For hair supply background points exclusively on clean interiors of that
same hair, and foreground points on the adjacent actual knit to preserve.
It requires a clean nearby target-cloth foreground point, actual non-target
background points, and evidencePoint on an actually selected dyed non-target
pixel. Precise material may be unknown if ownership as NON-TARGET is clear;
if it might be target clothing, return uncertain. Never relabel a real leak
as true_miss or no_edit_justified. Weak-selection hypotheses in context are
source pixel locations, NOT proof that the region should be deleted.
Inspect the ENTIRE crop, including nearby areas if the report point is on hair,
strap, already recoloured cloth or a mixed antialiasing pixel. A residual source
colour at fractional alpha is not automatically a solid missed cloth strip.
Use the saved subject to identify THIS product; do not infer hidden fabric or
include an inner garment, skin, hair, bag, strap or background.
Return JSON ONLY {"regions":[{"regionId":0,
"status":"true_miss|true_leak|no_edit_justified|uncertain",
"classification":"visible_target_cloth|mixed_edge|already_correct|non_target|uncertain",
"reason":"source-visible ownership and defect evidence",
"assessedEntireRegion":true,"nonTargetDyeObserved":false,"evidencePoint":[u,v],
"foreground":[{"point":[u,v],"evidence":"clean interior target cloth"}],
"background":[{"point":[u,v],"kind":"skin|hair|accessory|other_garment|background|gap","evidence":"actual non-target interior"}],
"occluder":[{"point":[u,v],"kind":"hair|accessory","evidence":"clean interior of the same local occluder"}]}]}.
Return exactly one row per requested regionId. Every coordinate is NORMALIZED
in the ORIGINAL full source, not crop/montage coordinates. true_miss requires
at least one CLEAN INSIDE target point and one actual non-target/background
point. A reported point is not automatically a clean point. Supply separate
clean occluder points only when an old MODEL ribbon is actually too wide and
the real occluder boundary is visible. Hard anatomy/explicit/background/true
negative protections cannot be released. If ownership or a clean interior is
uncertain, status=uncertain and STOP: do not guess a successful fix. For
no_edit_justified, explain concrete source ownership or expected matte mixing,
not just agreement with an old pass. non_target is permitted only when the
actual non-target is NOT dyed. true_leak requires classification=non_target
and nonTargetDyeObserved=true; true_miss and no_edit_justified require false.
Unknown ownership or dye must stop uncertain. true_leak background points
identify clean non-target material, foreground points identify actual target
cloth that must be kept; evidencePoint must identify the leaked selected pixel.
Such a finding still requires fresh
independent source and full colour review; it is not a pass.'''
GROUNDING_INSTRUCTION+='''
When referencePoseEvidence.accepted=true, the ALIGNED REAL REFERENCE column is the aligned
actual target SKU photo. Unchanged selected hair witnesses are hypotheses.
Use them only after independently checking visible source hair and actual dye;
do not pick an unselected/mixed pixel as the evidencePoint. Preserve changed
knit visible between strands. No reference RGB is copied to the output.
For a region with referenceWitnessesHypothesisOnly, true_leak MUST additionally
return evidenceWitnessId (integer index in that exact list). The server uses
that exact source pixel, not a rounded or newly invented evidencePoint.
The WITNESS MAP column marks these automatically proposed IDs; other source
columns are unmarked. Independently inspect actual raw SOURCE/ALPHA/OUTPUT.
Choose an ID only if you can confirm actual selected dyed hair at that source
pixel. If no proposed witness is actually confirmed, return uncertain; do not
invent a nearby replacement, classify knit as hair, or use an ID just to pass.'''
SOURCE_REVIEW_INSTRUCTION=selection.REVIEW_INSTRUCTION+'''
This is ONE new locally grounded candidate, not an inherited approval. The
local grounding and QC locations are hypotheses. Check source ownership,
including all aligned source/old-mask/current-mask/output evidence crops.
An auditOnly/no-change outcome is also UNVERIFIED until this actual review.
Minor physically mixed/antialiased boundary pixels are not automatically solid
unselected fabric. Do not approve a changed mask because a local model, IoU or
grounding status says so. Inspect the entire target and every changed patch;
numeric failures cannot be waived. This review does not certify colour output.'''
SOURCE_REVIEW_INSTRUCTION+='''
The OUTPUT column is the HISTORICAL QC image rendered with the OLD mask. No
new colour image has been rendered yet. Judge CURRENT ownership from image 2
and NEW OVERLAY, not by expecting the historical output to change. This does
not waive any current mask defect or later full colour QA.'''


class LocalSelectionRejected(ValueError):
    def __init__(self,message,receipt=None,*,code='automatic_local_selection_rejected'):
        super().__init__(message);self.receipt=receipt or {'state':'rejected','verified':False,'accepted':False};self.code=code


def _jsha(value):return selection._sha(selection._json(value).encode())


class MobileSAMLocalBackend:
    """Pinned existing ONNX backend; raw logits>0, no hole fill or RGB changes."""
    def identity(self):
        import garment_workflow
        models=Path(garment_workflow.__file__).parent/'models'/'mobile-sam'
        manifest=json.loads((models/'manifest.json').read_text('utf-8'))
        return {'backend':'existing_MobileSAM_ONNX_raw','manifest':manifest,
            'manifestSha256':selection._sha((models/'manifest.json').read_bytes())}

    def predict(self,source_crop,foreground,background,*,cache_root,role):
        import garment_workflow
        rgb=source_crop.convert('RGB');w,h=rgb.size
        with garment_workflow.LOCK:
            model=garment_workflow.selector(cache_root)
            fg=model.points(foreground,rgb.size);bg=model.points(background,rgb.size)
            key=selection._sha((model.version+selection._sha(rgb.tobytes())).encode())
            path=Path(cache_root)/(key+'.npz');path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists():
                with np.load(path,allow_pickle=False) as data:embedding=data['embedding']
            else:
                size=(int(w*1024/max(w,h)+.5),int(h*1024/max(w,h)+.5))
                resized=rgb.resize(size,Image.Resampling.BILINEAR)
                embedding=model.encoder.run(None,{'input_image':np.asarray(resized,dtype=np.float32)})[0]
                temp=path.with_name(key+'.'+uuid.uuid4().hex+'.npz');np.savez_compressed(temp,embedding=embedding);temp.replace(path)
            scale=np.array([int(w*1024/max(w,h)+.5)/w,int(h*1024/max(w,h)+.5)/h],np.float32)
            coords=np.vstack([fg,bg,[[0,0]]]).astype('float32')*scale
            labels=np.r_[np.ones(len(fg)),np.zeros(len(bg)),[-1]].astype('float32')
            logits,score,_=model.decoder.run(None,{'image_embeddings':embedding,'point_coords':coords[None],
                'point_labels':labels[None],'mask_input':np.zeros((1,1,256,256),np.float32),
                'has_mask_input':np.zeros(1,np.float32),'orig_im_size':np.array([h,w],np.float32)})
        if not np.isfinite(logits[0,0]).all():raise LocalSelectionRejected('局部MobileSAM logits不完整')
        mask=Image.fromarray((logits[0,0]>0).astype('uint8')*255)
        probabilities=1/(1+np.exp(-np.clip(logits[0,0],-40,40)))
        probability_path=Path(cache_root)/'p'/(_jsha({'source':selection._pixels(source_crop,'RGBA'),
            'foreground':foreground,'background':background,'role':role,'modelRevision':model.version})[:32]+'.npz')
        probability_path.parent.mkdir(exist_ok=True)
        temporary=probability_path.with_name(probability_path.stem+'.'+uuid.uuid4().hex+'.npz')
        np.savez_compressed(temporary,logits=logits[0,0],probabilities=probabilities);temporary.replace(probability_path)
        return mask,{'backend':'MobileSAM ONNX raw logits>0','modelRevision':model.version,'role':role,
            'sourcePixelSha256':selection._pixels(source_crop,'RGBA'),'maskPixelSha256':selection._pixels(mask,'L'),
            'foreground':foreground,'background':background,'predictedIoU':float(score.flat[0]),
            'probabilityArtifactPath':str(probability_path),'probabilityArtifactSha256':selection._sha(probability_path.read_bytes()),
            'scoreIsNotQualityAcceptance':True,'accepted':False,'verified':False,'unverifiedCandidate':True,
            'imageGenerationSubmitted':False}


def eligible(qc):
    """Investigate server-QC miss/leak hypotheses, including warning-only QC.

    This shape predicate proves neither ownership nor acceptance. A visual
    blocking=false cannot turn a top-level blocked/missing selection into pass.
    """
    if not isinstance(qc,dict):return False
    v=qc.get('visualReview');n=qc.get('numeric')
    if not isinstance(v,dict) or not isinstance(n,dict):return False
    locations=v.get('locations')
    if (qc.get('passed') is not False or qc.get('blocking') is not True or qc.get('nextAction')!='selection'
            or type(qc.get('protectedPartsPreserved')) is not bool or v.get('category')!='selection'
            or type(v.get('blocking')) is not bool or type(v.get('selectionComplete')) is not bool
            or type(v.get('protectedPartsPreserved')) is not bool
            or qc['protectedPartsPreserved']!=v['protectedPartsPreserved']
            or (v['selectionComplete'] and v['protectedPartsPreserved'])
            or any(v.get(k) is not True for k in ('identityPreserved','materialPreserved','colourPlausible'))
            or any(type(n.get(k)) is not int or n[k]!=0 for k in ('outsideChangedPixels','alphaChangedPixels'))
            or not isinstance(locations,list) or not 1<=len(locations)<=6):return False
    try:
        for row in locations:
            if (not isinstance(row,dict) or row.get('kind') not in ('miss','leak') or not isinstance(row.get('reason'),str)
                    or not row['reason'].strip()):return False
            selection._point(row.get('point'),(100,100))
        if not v['protectedPartsPreserved'] and (not v['blocking'] or not any(row['kind']=='leak' for row in locations)):return False
    except (ValueError,TypeError):return False
    return True


def _qc(qc,source,old_mask,output,old_receipt,subject,kind):
    if not eligible(qc):raise LocalSelectionRejected('QC不满足服务器阻断的有界选区研究范围，未授权局部更改')
    checked=copy.deepcopy(qc)
    binding=checked.get('binding')
    if not isinstance(binding,dict):raise LocalSelectionRejected('QC缺少实际图像绑定')
    actual=binding.get('output')
    for key,image,mode in (('source',source,'RGBA'),('mask',old_mask,'L')):
        value=binding.get(key)
        if not isinstance(value,dict) or value.get('size')!=list(source.size) or value.get('pixelSha256')!=selection._pixels(image,mode):
            raise LocalSelectionRejected('QC源/旧mask绑定不符')
    if (not isinstance(actual,dict) or actual.get('size')!=list(source.size)
            or actual.get('pixelSha256')!=selection._pixels(output,'RGBA')):
        raise LocalSelectionRejected('QC不是本次实际成图，禁止拿另一张图的报告修选区')
    expected={_jsha(old_receipt),_jsha({k:v for k,v in old_receipt.items() if k!='cacheReused'})}
    if binding.get('selectionReceiptSha256') not in expected:
        raise LocalSelectionRejected('QC与canonical旧选区回执不绑定')
    scoped=binding.get('subject')
    if not isinstance(scoped,dict) or scoped.get('role')!='source_garment':
        raise LocalSelectionRejected('QC缺少服务器源商品scope')
    for key in ('productName','target'):
        if key in scoped and key in subject and scoped[key]!=subject[key]:raise LocalSelectionRejected('QC商品身份不符')
    if 'kind' in scoped and scoped['kind']!=kind:raise LocalSelectionRejected('QC衣物类别不符')
    return checked


def _protection_layers(source,old_mask,canonical,points,combined,garment_root,kind,explicit):
    run=Path(canonical['runPath']);entry=canonical['attempts'][-1];attempt=run/f"attempt-{entry['number']:02}"
    with np.load(run/'local-labels.npz',allow_pickle=False) as data:
        cloth,human=data['cloth'].copy(),data['human'].copy()
    expected=canonical.get('explicitProtectionSha256')
    if expected is not None:
        if not isinstance(explicit,Image.Image) or explicit.size!=source.size or selection._pixels(explicit,'L')!=expected:
            raise LocalSelectionRejected('旧显式保护缺少原件，不能推断哪些保护可以释放')
    elif explicit is not None:raise LocalSelectionRejected('不能在局部任务暗加不同的显式保护')
    base=selection._local_evidence(source,kind,cloth,human,explicit)
    hard=base['protected'].copy();artifacts={}
    for filename,key,count_fields in (
            ('background.png','sourceBackgroundSeparation',('protectedPixels','carriedSourceBackgroundPixels')),
            ('instance-protection.png','instanceSeparation',('protectedPixels',))):
        path=attempt/filename;meta=entry.get('compiled',{}).get(key,{})
        if path.is_file():
            revision._checked_path(str(path),run)
            layer=Image.open(path).convert('L')
            if layer.size!=source.size:raise LocalSelectionRejected('保护层尺寸不符')
            hard|=np.asarray(layer)>0;artifacts[filename]=selection._sha(path.read_bytes())
        elif any(meta.get(field,0) for field in count_fields):
            raise LocalSelectionRejected('已验证背景/其他服装保护缺原件，不释放保护')
    ribbons=np.zeros(hard.shape,'uint8')
    paths=entry.get('compiled',{}).get('protectionPaths',[])
    for row in paths:
        values=np.asarray(row.get('pointsPixels'),dtype='int32');width=row.get('widthPixels')
        if values.ndim!=2 or values.shape[1]!=2 or len(values)<2 or type(width) is not int or not 1<=width<=max(source.size):
            raise LocalSelectionRejected('canonical模型路径无效')
        if (values<0).any() or (values[:,0]>=source.width).any() or (values[:,1]>=source.height).any():
            raise LocalSelectionRejected('canonical模型路径越界')
        cv2.polylines(ribbons,[values],False,255,width)
    original=np.asarray(combined.convert('L'))>0
    hard|=original&(ribbons==0)
    for x,y in points['background']:hard[y,x]=True
    hard|=np.asarray(source.convert('RGBA'))[:,:,3]==0
    if ((np.asarray(old_mask)>0)&hard).any():
        raise LocalSelectionRejected('旧选区与当前硬保护冲突，不能在局部任务中隐藏修正')
    soft=original&~hard&(ribbons>0)
    return base,hard,soft,{'layerArtifactsSha256':artifacts,'hardPixelSha256':selection._sha(hard.astype('uint8').tobytes()),
        'modelHypothesisPixelSha256':selection._sha(soft.astype('uint8').tobytes()),
        'explicitProtectionVerified':expected is None or explicit is not None,
        'unknownCombinedProtectionRemainsHard':True},cloth,human


def _regions(source,feedback,old_mask=None,human=None):
    regions=[];union=np.zeros((source.height,source.width),bool)
    width=min(256,source.width);height=min(256,source.height)
    for i,row in enumerate(feedback['visualReview']['locations']):
        x,y=selection._point(row['point'],source.size)
        left=max(0,min(source.width-width,round(x-width/2)))
        top=max(0,min(source.height-height,round(y-height/2)))
        bbox=[left,top,left+width,top+height];union[top:top+height,left:left+width]=True
        regions.append({'regionId':i,'bboxPixels':bbox,'reportedPoint':row['point'],
            'reportedPointPixels':[x,y],'reportedKind':row['kind'],
            'reportReason':row['reason'],'reportIsHypothesis':True})
    if union.mean()>.35:raise LocalSelectionRejected('实际局部ROI总范围过大，不回退成全局修订')
    if old_mask is not None and human is not None:
        # A point report is not an extent. Cover the selected portion of the
        # SAME independently parsed hair object in one bounded correction.
        _,objects=cv2.connectedComponents((human==2).astype('uint8'),8)
        chosen=set()
        for row in regions:
            if row['reportedKind']=='leak':
                x,y=row['reportedPointPixels'];label=int(objects[y,x])
                if label:chosen.add(label)
        domain=np.isin(objects,list(chosen))&(np.asarray(old_mask)>0) if chosen else np.zeros(union.shape,bool)
        if domain.any():
            ys,xs=np.where(domain);candidates=[]
            positions=lambda lo,hi,total,side:sorted(set([max(0,min(total-side,v))for v in list(range(int(lo),int(hi)+1,192))+[int(hi)-side+1]]))
            for y0 in positions(ys.min(),ys.max(),source.height,height):
                for x0 in positions(xs.min(),xs.max(),source.width,width):candidates.append([x0,y0,x0+width,y0+height])
            pending=domain&~union
            while pending.any() and len(regions)<POLICY['maximumRegions']:
                box=max(candidates,key=lambda b:int(pending[b[1]:b[3],b[0]:b[2]].sum()))
                x0,y0,x1,y1=box;tile=pending[y0:y1,x0:x1]
                if not tile.any():break
                proposed=union.copy();proposed[y0:y1,x0:x1]=True
                if proposed.mean()>.35:break
                py,px=np.argwhere(tile)[len(np.argwhere(tile))//2];x,y=int(px+x0),int(py+y0)
                parent=next(row for row in regions if row['reportedKind']=='leak')
                regions.append({'regionId':len(regions),'bboxPixels':box,'reportedPoint':[x/(source.width-1),y/(source.height-1)],
                    'reportedPointPixels':[x,y],'reportedKind':'leak','reportReason':'Unverified coverage of selected pixels on the same parsed hair object; inspect actual ownership and dye.',
                    'parentReportPoint':parent['reportedPoint'],'roiOrigin':'automatic_same_source_hair_coverage','reportIsHypothesis':True})
                union=proposed;pending=domain&~union
    return regions


def _budgeted_reference_regions(source,regions,old_mask,human,unchanged,actual_output=None):
    """Cover same-object evidence with native context tiles within ORIGINAL caps.

    All windows are distinct actual source ROIs, not repeated slices of one
    oversized edit. Predict the maximum possible change BEFORE model calls.
    Full context avoids a dense 128px crop consuming its own 15% budget.
    """
    if any(row['reportedKind']!='leak' for row in regions):return regions
    _,objects=cv2.connectedComponents((human==2).astype('uint8'),8)
    chosen={int(objects[row['reportedPointPixels'][1],row['reportedPointPixels'][0]])for row in regions}
    chosen.discard(0)
    risk=(np.asarray(old_mask)>0)&np.isin(objects,list(chosen))
    if not risk.any():return regions
    ys,xs=np.where(risk);w=min(256,source.width);h=min(256,source.height)
    if min(w,h)<POLICY['minimumSidePixels']:raise LocalSelectionRejected('原图不支持有界参考选区')
    def starts(lo,hi,total,side):
        first=max(0,int(lo)-side+9);last=min(total-side,int(hi)-8)
        return sorted(set([first,last]+list(range(first,last+1,16))))
    cap=min(int(risk.size*POLICY['maximumHairMatteChangedFraction']),int(w*h*POLICY['maximumHairMatteRoiFraction']))
    candidates=[]
    for y in starts(ys.min(),ys.max(),source.height,h):
        for x in starts(xs.min(),xs.max(),source.width,w):
            n=int(risk[y:y+h,x:x+w].sum())
            if 0<n<=cap:candidates.append(([x,y,x+w,y+h],n))
    pending=risk.copy();done=[];union=np.zeros(risk.shape,bool)
    dye=(np.max(np.abs(np.asarray(source.convert('RGB'),dtype='int16')-np.asarray(actual_output.convert('RGB'),dtype='int16')),axis=2)
        if actual_output is not None else np.ones(risk.shape))
    while pending.any() and len(done)<POLICY['maximumRegions']:
        scored=[]
        for b,n in candidates:
            x0,y0,x1,y1=b;gain=int(pending[y0+8:y1-8,x0+8:x1-8].sum())
            if gain:scored.append((gain,-int((~union[y0:y1,x0:x1]).sum()),b,n))
        if not scored:break
        _,_,b,n=max(scored,key=lambda v:(v[0],v[1],tuple(-k for k in v[2])))
        x0,y0,x1,y1=b;tile=risk[y0+8:y1-8,x0+8:x1-8]&unchanged[y0+8:y1-8,x0+8:x1-8];positions=np.argwhere(tile)
        if not len(positions):raise LocalSelectionRejected('局部候选缺少严格配对未变发丝证据，未放宽RGB容差')
        py,px=positions[len(positions)//2];x,y=int(px+x0+8),int(py+y0+8)
        parent=min(regions,key=lambda row:(row['reportedPointPixels'][0]-x)**2+(row['reportedPointPixels'][1]-y)**2)
        # Rank automatically by actual dye visibility and spatial diversity.
        # Ranking is not ownership evidence; the model must confirm each ID.
        strengths=dye[positions[:,0]+y0+8,positions[:,1]+x0+8].astype(float)
        indices=[];distance=np.ones(len(positions))*max(w,h)
        for _ in range(min(8,len(positions))):
            scores=(1+strengths)*distance
            if indices:scores[indices]=-1
            idx=int(np.argmax(scores));indices.append(idx)
            distance=np.minimum(distance,np.linalg.norm(positions-positions[idx],axis=1))
        witnesses=[[int(positions[k,1]+x0+8),int(positions[k,0]+y0+8)]for k in indices]
        done.append({**parent,'regionId':len(done),'bboxPixels':b,'parentReportPoint':parent['reportedPoint'],
            'reportedPoint':[x/(source.width-1),y/(source.height-1)],'reportedPointPixels':[x,y],
            'roiOrigin':'automatic_same_object_native_context_budget',
            'reportReason':'Unverified source-selected same-object hair and paired unchanged evidence. Independently inspect actual hair, cloth and dye.',
            'referenceRiskUpperBound':n,'unchangedMaximumChangedPixels':cap,
            'referenceWitnessesHypothesisOnly':witnesses})
        union[y0:y1,x0:x1]=True;pending[y0+8:y1-8,x0+8:x1-8]=False
    if pending.any() or union.mean()>POLICY['maximumUnionFraction']:
        raise LocalSelectionRejected('参考对应证据不能在原区域数、面积与修改预算内完整覆盖，未提交付费分析')
    return done


def _montage(source,old_mask,output,regions,current_mask=None,aligned_reference=None):
    overlay=selection._overlay(source,old_mask)
    columns=[('SOURCE',source.convert('RGB')),('OLD ALPHA',old_mask.convert('RGB')),
        ('OLD OVERLAY',overlay),('OUTPUT',output.convert('RGB'))]
    if current_mask is not None:columns.append(('NEW OVERLAY',selection._overlay(source,current_mask)))
    if aligned_reference is not None:columns.append(('ALIGNED REAL REFERENCE',aligned_reference.convert('RGB')))
    if aligned_reference is not None:columns.append(('WITNESS MAP',source.convert('RGB')))
    panel=384;header=22;canvas=Image.new('RGB',(panel*len(columns),(panel+header)*len(regions)),'#f6f6f2')
    draw=ImageDraw.Draw(canvas)
    for i,row in enumerate(regions):
        bbox=tuple(row['bboxPixels'])
        for j,(label,image) in enumerate(columns):
            scale=min(panel/(bbox[2]-bbox[0]),panel/(bbox[3]-bbox[1]))
            size=(round((bbox[2]-bbox[0])*scale),round((bbox[3]-bbox[1])*scale))
            crop=image.crop(bbox).resize(size,Image.Resampling.NEAREST)
            canvas.paste(crop,(j*panel+(panel-size[0])//2,i*(panel+header)+header+(panel-size[1])//2))
            draw.text((j*panel+4,i*(panel+header)+4),f"R{row['regionId']} {label}",fill='black')
            if label=='WITNESS MAP':
                for wid,(wx,wy)in enumerate(row.get('referenceWitnessesHypothesisOnly',[])):
                    sx=j*panel+(panel-size[0])//2+(wx-bbox[0])*scale
                    sy=i*(panel+header)+header+(panel-size[1])//2+(wy-bbox[1])*scale
                    draw.ellipse((sx-3,sy-3,sx+3,sy+3),outline='#ff2345',width=1)
                    draw.text((sx+4,sy-8),str(wid),fill='#ff2345',stroke_width=1,stroke_fill='white')
    return canvas


def _grounded(result,regions,source):
    if not isinstance(result,dict) or not isinstance(result.get('regions'),list) or len(result['regions'])!=len(regions):
        raise LocalSelectionRejected('局部grounding未覆盖全部实际ROI')
    expected={row['regionId']:row for row in regions};seen=set();validated=[]
    for row in result['regions']:
        if not isinstance(row,dict) or type(row.get('regionId')) is not int or row['regionId'] not in expected or row['regionId'] in seen:
            raise LocalSelectionRejected('局部grounding regionId无效或重复')
        seen.add(row['regionId']);region=expected[row['regionId']];bbox=region['bboxPixels']
        status=row.get('status');classification=row.get('classification')
        if (status not in ('true_miss','true_leak','no_edit_justified','uncertain') or row.get('assessedEntireRegion') is not True
                or not isinstance(row.get('reason'),str) or not row['reason'].strip()):
            raise LocalSelectionRejected('局部grounding缺明确归属/缺陷证据')
        if status=='uncertain' or classification=='uncertain':raise LocalSelectionRejected('局部归属仍不确定，未强制修选区')
        if row.get('nonTargetDyeObserved') is not (status=='true_leak'):
            raise LocalSelectionRejected('缺陷类型与非目标染色证据矛盾或未排除')
        if status=='true_leak' and classification!='non_target':raise LocalSelectionRejected('去误选缺少明确非目标归属')
        if status=='true_miss' and classification!='visible_target_cloth':raise LocalSelectionRejected('缺陷不是真实目标衣料miss')
        if status=='no_edit_justified' and classification not in ('mixed_edge','already_correct','non_target'):
            raise LocalSelectionRejected('不改像素缺少具体源像素归属理由')
        def parse(key,minimum,maximum):
            values=row.get(key,[])
            if not isinstance(values,list) or not minimum<=len(values)<=maximum:raise LocalSelectionRejected('局部inside点/负点数量无效')
            result=[]
            for value in values:
                if not isinstance(value,dict) or not selection._evidence(value):raise LocalSelectionRejected('局部点缺源证据')
                xy=selection._point(value.get('point'),source.size)
                if not bbox[0]<=xy[0]<bbox[2] or not bbox[1]<=xy[1]<bbox[3]:raise LocalSelectionRejected('局部点越出其真实ROI')
                if key!='foreground' and value.get('kind') not in selection.NEGATIVE_KINDS:raise LocalSelectionRejected('局部非目标点缺合法用途')
                if key=='occluder' and value.get('kind') not in ('hair','accessory'):raise LocalSelectionRejected('释放模型ribbon须有真实局部occluder')
                result.append(xy)
            return result
        fg=parse('foreground',1 if status in ('true_miss','true_leak') else 0,6)
        bg=parse('background',1 if status in ('true_miss','true_leak') else 0,12);occ=parse('occluder',0,6)
        witness_id=None
        if status=='true_leak'and region.get('referenceWitnessesHypothesisOnly'):
            witness_id=row.get('evidenceWitnessId');witnesses=region['referenceWitnessesHypothesisOnly']
            if type(witness_id)is not int or not 0<=witness_id<len(witnesses):
                raise LocalSelectionRejected('同视角候选须核实真实源像素编号，不接受漂移坐标')
            ep=list(witnesses[witness_id])
        else:ep=selection._point(row.get('evidencePoint'),source.size)
        if not bbox[0]<=ep[0]<bbox[2] or not bbox[1]<=ep[1]<bbox[3]:raise LocalSelectionRejected('归属证据点不在ROI')
        validated.append({**region,'status':status,'classification':classification,'reason':row['reason'],
            'nonTargetDyeObserved':status=='true_leak','foreground':fg,'background':bg,'occluder':occ,'evidencePointPixels':ep,
            'backgroundKinds':sorted({value['kind']for value in row.get('background',[])}),
            'evidenceWitnessId':witness_id,'modelReportedEvidencePoint':row.get('evidencePoint')})
    return sorted(validated,key=lambda row:row['regionId'])


def _predict(backend,crop,fg,bg,cache,role):
    if not fg or not bg:raise LocalSelectionRejected('局部分割缺真正景/背景约束')
    mask,receipt=backend.predict(crop.copy(),copy.deepcopy(fg),copy.deepcopy(bg),cache_root=cache,role=role)
    if not isinstance(mask,Image.Image) or mask.size!=crop.size or mask.mode!='L' or not np.isin(np.asarray(mask),[0,255]).all():
        raise LocalSelectionRejected('局部backend须返回原尺寸raw二值Lmask')
    if (not isinstance(receipt,dict) or receipt.get('sourcePixelSha256')!=selection._pixels(crop,'RGBA')
            or receipt.get('maskPixelSha256')!=selection._pixels(mask,'L') or receipt.get('role')!=role):
        raise LocalSelectionRejected('局部backend回执未绑定实际source/mask/role')
    a=np.asarray(mask)
    if any(a[y,x]!=255 for x,y in fg) or any(a[y,x]!=0 for x,y in bg):
        raise LocalSelectionRejected('局部raw候选违背真实正负点，未按IoU宣称通过')
    return mask,receipt


def _weak_hypotheses(old_mask,regions):
    """Machine pixel proposals only; never delete or classify them here."""
    a=np.asarray(old_mask);distance=cv2.distanceTransform((a<230).astype('uint8'),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    result=[]
    for row in regions:
        x0,y0,x1,y1=row['bboxPixels'];roi=a[y0:y1,x0:x1]
        weak=(roi>0)&(roi<230)&(distance[y0:y1,x0:x1]>=1.5)
        n,labels,stats,_=cv2.connectedComponentsWithStats(weak.astype('uint8'),8)
        items=[]
        for i in range(1,n):
            if stats[i,cv2.CC_STAT_AREA]>512:continue
            ys,xs=np.where(labels==i)
            # A real selected source pixel nearest the reported issue, not an
            # agent supplied point or geometric centroid outside a component.
            px,py=row['reportedPointPixels'];j=int(np.argmin((xs+x0-px)**2+(ys+y0-py)**2))
            x,y=int(xs[j]+x0),int(ys[j]+y0)
            items.append({'pointPixels':[x,y],'point':[x/(a.shape[1]-1),y/(a.shape[0]-1)],
                'alpha':int(a[y,x]),'areaPixels':int(len(xs)),
                'distanceToOpaquePixels':float(distance[y,x]),'unverifiedHypothesis':True})
        items.sort(key=lambda p:sum((p['pointPixels'][i]-row['reportedPointPixels'][i])**2 for i in (0,1)))
        result.append({'regionId':row['regionId'],'weakSelectionPixels':items[:6],'certifiesNonTarget':False})
    return result


def _remove_confirmed_weak_leak(original,row,cloth,non_target,old_points):
    """Dual native instances may remove bounded soft alpha, never opaque cloth."""
    x0,y0,x1,y1=row['bboxPixels'];a=original[y0:y1,x0:x1]
    ca=np.asarray(cloth)>0;na=np.asarray(non_target)>0
    ex,ey=row['evidencePointPixels'];ex-=x0;ey-=y0
    allowed=(a>0)&(a<=POLICY['maximumRemovableAlpha'])&na&~ca
    if not allowed[ey,ex]:raise LocalSelectionRejected('去误选证据点未被双实例证实或属于不透明衣料')
    count,labels=cv2.connectedComponents(allowed.astype('uint8'),8)
    remove=labels==labels[ey,ex]
    cap=min(POLICY['maximumLeakRemovedPixels'],max(16,int(original.size*POLICY['maximumLeakRemovedFraction'])))
    if remove.sum()>cap:raise LocalSelectionRejected('去误选范围超出弱alpha有界修订上限')
    for key in ('foreground','sourceClothAnchors','sourceClothRidgePixels'):
        for x,y in old_points.get(key,[]):
            if x0<=x<x1 and y0<=y<y1 and remove[y-y0,x-x0]:raise LocalSelectionRejected('去误选与原真实衣料锚点冲突')
    if remove[[0,-1],:].any() or remove[:,[0,-1]].any():raise LocalSelectionRejected('去误选连通区触及ROI边缘，不能确认完整范围')
    changed=a.copy();changed[remove]=0
    return changed,{'removedPixels':int(remove.sum()),'maximumPixels':cap,
        'maximumRemovedAlpha':int(a[remove].max()),'opaqueClothRemovedPixels':0,
        'dualSourceInstancesRequired':True,'evidencePointSelectedBefore':int(a[ey,ex])}


def _source_fg_guard(base,old_mask,foreground,hard):
    """Local unknowns need existing 24-Lab/30px evidence, never colour alone."""
    human=base['human'];distance=base['distance']
    primary=base['primary']&~((human==0)&(distance>=16))
    target=np.isin(human,base['semanticGarmentClasses'])
    neighbourhood=cv2.boxFilter(target.astype('float32'),-1,(5,5),normalize=True,
        borderType=cv2.BORDER_CONSTANT)>=.6
    supported=(primary|(target&neighbourhood)|
        (np.isin(human,[4,5,6,7])&(distance<16)))&~base['protected']
    actual=(np.asarray(old_mask.convert('L'))>=230)&supported&~hard
    nearest=cv2.distanceTransform((~actual).astype('uint8'),cv2.DIST_L2,cv2.DIST_MASK_PRECISE) if actual.any() else None
    rows=[]
    for x,y in foreground:
        if hard[y,x]:raise LocalSelectionRejected('grounded衣料点落硬保护，禁止释放')
        independent=selection._foreground_supported(base,x,y)
        near=float(nearest[y,x]) if nearest is not None else None
        if not independent and (distance[y,x]>24 or near is None or near>30):
            raise LocalSelectionRejected('grounded点缺独立衣料/局部24Lab及30px源支持，未变成真实FG')
        rows.append({'pointPixels':[x,y],'sourceRGB':base['sourceRGB'][y,x].astype(int).tolist(),
            'clothingLabel':int(base['cloth'][y,x]),'humanLabel':int(human[y,x]),
            'sourceFabricDistanceLab':float(distance[y,x]),'distanceToOldOpaqueClothPixels':near,
            'branch':'existing_independent_support' if independent else 'source_supported_local_hypothesis',
            'hypothesisOnly':not independent,'requiresLocalInstanceAndFreshReviews':True})
    return {'points':rows,'fallbackMaximumSourceLabDistance':24,'fallbackMaximumOldClothDistancePixels':30,
        'qualityThresholdsChanged':False,'certifiesSelection':False}


def _unknown(root,identity,current):
    for path in Path(root).glob('*/*/receipt.json'):
        if path.resolve()==current.resolve():continue
        try:old=json.loads(path.read_text('utf-8'))
        except (OSError,ValueError):continue
        oid=old.get('identity',old)
        if oid.get('sourcePixelSha256')!=identity['sourcePixelSha256'] or oid.get('vision')!=identity['vision']:continue
        blocked=old.get('state') in ('processing','unknown')
        for filename in ('plan.json','review.json'):
            call=path.parent/filename
            if call.exists():
                try:blocked|=json.loads(call.read_text('utf-8')).get('state')!='completed'
                except (OSError,ValueError):blocked=True
        if blocked:raise LocalSelectionRejected('同源同模型有未决局部请求，先对账，未变更身份重付',
            {'state':'unknown','verified':False,'accepted':False,'blockingReceiptPath':str(path)},code='automatic_local_selection_unknown')


def correct(source,old_mask,old_receipt,*,kind,subject,qc,actual_output,vision,cache_root,
        garment_cache_root,vision_metadata,local_backend=None,explicit_protection=None,reference=None):
    """One local grounding + native source candidate + one fresh source review.

    Server must fetch all canonical inputs after account/product authorization.
    Return (new L mask, receipt). Even auditOnly requires actual fresh review;
    final colour QA is mandatory and belongs to the caller. No global fallback.
    """
    if not isinstance(source,Image.Image) or kind not in selection.TARGET or not callable(vision):raise LocalSelectionRejected('局部修订缺原图/品类/当前账号视觉接口')
    source=source.convert('RGBA')
    if any(not isinstance(im,Image.Image) or im.size!=source.size for im in (old_mask,actual_output)):
        raise LocalSelectionRejected('源/旧alpha/实际成图须为相同原尺寸')
    if min(source.size)<16 or max(source.size)>8192 or source.width*source.height>40_000_000:raise LocalSelectionRejected('局部源图尺寸不支持')
    old_mask=old_mask.convert('L');actual_output=actual_output.convert('RGBA');subject=selection._subject(subject)
    if not subject or subject.get('role')!='source_garment':raise LocalSelectionRejected('局部修订只能用于当前source garment')
    if not isinstance(vision_metadata,dict) or not vision_metadata:raise LocalSelectionRejected('须绑定实际Codex身份')
    try:
        canonical,old_points,combined,evidence,provenance=revision._load_evidence(source,old_mask,old_receipt,garment_cache_root,kind,subject)
        feedback=_qc(qc,source,old_mask,actual_output,old_receipt,subject,kind)
        base,hard,soft,layers,cloth,human=_protection_layers(source,old_mask,canonical,old_points,combined,garment_cache_root,kind,explicit_protection)
    except LocalSelectionRejected:raise
    except (revision.RevisionRejected,OSError,ValueError,KeyError,TypeError) as error:
        raise LocalSelectionRejected('canonical局部证据不可验证，未调用grounding：'+str(error)) from error
    pose={'audit':{'accepted':False,'reason':'no_bound_same_view_reference'}}
    if reference is not None:
        binding=feedback.get('binding',{}).get('reference',{})
        if not isinstance(reference,Image.Image) or binding.get('size')!=list(reference.size) or binding.get('pixelSha256')!=selection._pixels(reference,'RGBA'):
            raise LocalSelectionRejected('实际同款参考与服务器QC绑定不符，未调用付费分析')
        pose=reference_pose_evidence.analyze(source,reference,old_mask,base)
    regions=_regions(source,feedback,old_mask,human)
    if pose['audit']['accepted']:regions=_budgeted_reference_regions(source,regions,old_mask,human,pose['unchanged'],actual_output)
    backend=local_backend or MobileSAMLocalBackend()
    identity={'version':VERSION,'kind':kind,'subject':subject,'sourceSize':list(source.size),
        'sourcePixelSha256':selection._pixels(source,'RGBA'),'oldMaskPixelSha256':selection._pixels(old_mask,'L'),
        'actualOutputPixelSha256':selection._pixels(actual_output,'RGBA'),'oldReceiptSha256':_jsha(canonical),
        'serverQcSha256':_jsha(feedback),'vision':copy.deepcopy(vision_metadata),
        'backend':backend.identity(),'policy':POLICY,'protectionEvidence':layers,
        'selectionAlgorithmVersion':selection.ALGORITHM_VERSION,
        'sourceHairMatte':{'version':local_hair_matte.VERSION,'moduleSha256':selection._sha(Path(local_hair_matte.__file__).read_bytes())},
        'referencePoseEvidence':{**pose['audit'],'moduleSha256':selection._sha(Path(reference_pose_evidence.__file__).read_bytes())},
        'groundingInstructionSha256':selection._sha(GROUNDING_INSTRUCTION.encode()),
        'reviewInstructionSha256':selection._sha(SOURCE_REVIEW_INSTRUCTION.encode())}
    folder=Path(cache_root).resolve()/CACHE_DIR/_jsha(identity)[:32];manifest=folder/'receipt.json'
    with LOCK:
        if manifest.exists():
            old=json.loads(manifest.read_text('utf-8'))
            if old.get('identity')!=identity:raise LocalSelectionRejected('局部缓存身份不符',old)
            if old.get('verified') is True and old.get('accepted') is True:
                path=Path(old['maskPath'])
                if selection._within(path,folder) and selection._sha(path.read_bytes())==old.get('maskPngSha256'):
                    im=Image.open(path).convert('L')
                    if im.size==source.size and selection._pixels(im,'L')==old.get('maskPixelSha256'):return im,{**old,'cacheReused':True}
                raise LocalSelectionRejected('局部缓存mask不符，未重新付费',old)
            raise LocalSelectionRejected('同一局部意图已拒绝或未决，保留旧记录不重付',old,
                code='automatic_local_selection_unknown' if old.get('state') in ('processing','unknown') else 'automatic_local_selection_rejected')
        _unknown(cache_root,identity,manifest);folder.mkdir(parents=True,exist_ok=True)
        receipt={'version':VERSION,'identity':identity,'state':'processing','accepted':False,'verified':False,
            'kind':kind,'subject':subject,'sourceSize':list(source.size),'sourcePixelSha256':identity['sourcePixelSha256'],
            'sourceHashEncoding':'rgba8_top_to_bottom','humanReviewed':False,'imageGenerationSubmitted':False,
            'cacheManifestPath':str(manifest),'runPath':str(folder),'created':time.time(),'attempts':[]}
        selection._write(manifest,receipt)
        try:
            selection._save_image(source,folder/'source.png');selection._save_image(old_mask,folder/'old-mask.png')
            selection._save_image(actual_output,folder/'qc-output.png');np.savez_compressed(folder/'local-labels.npz',cloth=cloth,human=human)
            aligned=pose.get('aligned')
            if aligned is not None:
                selection._save_image(aligned,folder/'aligned-reference.png')
                selection._save_image(Image.fromarray(pose['unchanged'].astype('uint8')*255),folder/'unchanged-reference-evidence.png')
            montage=_montage(source,old_mask,actual_output,regions,aligned_reference=aligned);selection._save_image(montage,folder/'grounding-input.png')
            context={'phase':'local_grounding','subject':subject,'sourceSize':list(source.size),
                'sourcePixelSha256':identity['sourcePixelSha256'],'regions':regions,'policy':POLICY,
                'referencePoseEvidence':pose['audit'],
                'referenceUse':'When accepted, ALIGNED REAL REFERENCE is the mathematically aligned actual SKU reference; unchanged selected pixels are source hypotheses, not proof. Independently ground hair vs knit. Select evidenceWitnessId only after checking actual source and prior output. Never delete knit that changes between photos.',
                'cropDisplay':{'panelPixels':384,'columnRoles':['source','old_alpha','old_overlay','actual_output']+(['aligned_real_reference','witness_map']if aligned is not None else[]),
                    'resampling':'nearest_display_only','coordinatesRemainOriginalSource':True,
                    'regionScales':[{'regionId':row['regionId'],'scale':min(384/(row['bboxPixels'][2]-row['bboxPixels'][0]),384/(row['bboxPixels'][3]-row['bboxPixels'][1])),
                        'letterboxed':True} for row in regions]},
                'oldMaskPixelSha256':identity['oldMaskPixelSha256'],'actualOutputPixelSha256':identity['actualOutputPixelSha256'],
                'weakSelectionHypotheses':_weak_hypotheses(old_mask,regions),
                'cropImages':[{'imageIndex':i+4,'regionId':row['regionId']}for i,row in enumerate(regions)],
                'machineReportIsNotForegroundTruth':True}
            images=[source,selection._overlay(source,old_mask),actual_output]+[_montage(source,old_mask,actual_output,[row],aligned_reference=aligned)for row in regions]
            raw=selection._vision_call(vision,folder,'plan',GROUNDING_INSTRUCTION,context,images)
            grounded=_grounded(raw,regions,source);record=json.loads((folder/'plan.json').read_text('utf-8'))
            new=np.asarray(old_mask).copy();original=new.copy();new_soft=soft.copy();local_records=[];new_fg=[];new_bg=[]
            roi_union=np.zeros(new.shape,bool)
            for row in grounded:
                rid=row['regionId'];x0,y0,x1,y1=row['bboxPixels'];roi_union[y0:y1,x0:x1]=True
                point=row['evidencePointPixels'];row['sourcePixelEvidence']={'pointPixels':point,
                    'sourceRGBA':list(source.getpixel(tuple(point))),'oldAlpha':int(old_mask.getpixel(tuple(point))),
                    'qcOutputRGBA':list(actual_output.getpixel(tuple(point)))}
                if row['status']=='no_edit_justified':row['maskChangedPixels']=0;continue
                row['sourceForegroundGuard']=_source_fg_guard(base,old_mask,row['foreground'],hard)
                if row['status']=='true_leak':
                    if any(old_mask.getpixel((x,y))<230 for x,y in row['foreground']):
                        raise LocalSelectionRejected('去误选须有原已选中的不透明真实衣料保留点',receipt)
                    fg=[[x-x0,y-y0] for x,y in row['foreground']]
                    negatives=row['background']+[row['evidencePointPixels']]
                    bg=[[x-x0,y-y0] for x,y in negatives]
                    crop=source.crop((x0,y0,x1,y1))
                    cm,cr=_predict(backend,crop,fg,bg,Path(cache_root).resolve()/'models','target_cloth')
                    nm,nr=_predict(backend,crop,bg,fg,Path(cache_root).resolve()/'models','non_target')
                    selection._save_image(cm,folder/f'r{rid}-cloth.png');selection._save_image(nm,folder/f'r{rid}-non-target.png')
                    if row['backgroundKinds']==['hair']:
                        if pose['audit']['accepted']:
                            sr=np.asarray(crop.convert('RGB'),dtype='int16');rr=np.asarray(aligned.crop((x0,y0,x1,y1)).convert('RGB'),dtype='int16')
                            local_delta=np.max(np.abs(sr-rr),axis=2)
                            if not any(local_delta[y,x]>=reference_pose_evidence.POLICY['minimumClothChangeRGB']for x,y in fg):
                                raise LocalSelectionRejected('当前局部缺少独立核实且实际变色的真实衣料正点，未用参考猜发丝',receipt)
                            patch_image,guard=local_hair_matte.refine_paired(crop,aligned.crop((x0,y0,x1,y1)),old_mask.crop((x0,y0,x1,y1)),cm,nm,
                                human[y0:y1,x0:x1],pose['unchanged'][y0:y1,x0:x1],evidence_point=[point[0]-x0,point[1]-y0])
                        else:
                            patch_image,guard=local_hair_matte.refine(crop,old_mask.crop((x0,y0,x1,y1)),cm,nm,
                                human[y0:y1,x0:x1],fg,[[x-x0,y-y0]for x,y in row['background']],
                                evidence_point=[point[0]-x0,point[1]-y0])
                        patch=np.asarray(patch_image);prior=original[y0:y1,x0:x1]
                        if patch[point[1]-y0,point[0]-x0]>=prior[point[1]-y0,point[0]-x0]:
                            raise LocalSelectionRejected('连续alpha没有证实或修正实际发丝染色点，未冒充通过',receipt)
                        cap=min(int(original.size*POLICY['maximumHairMatteChangedFraction']),int(prior.size*POLICY['maximumHairMatteRoiFraction']))
                        if guard['changedPixels']>cap:raise LocalSelectionRejected('发丝matting超出有界源证据范围',receipt)
                        for key in ('foreground','sourceClothAnchors','sourceClothRidgePixels'):
                            for x,y in old_points.get(key,[]):
                                if x0<=x<x1 and y0<=y<y1 and patch[y-y0,x-x0]!=prior[y-y0,x-x0]:
                                    raise LocalSelectionRejected('发丝matting与原真实衣料锚点冲突',receipt)
                        guard.update(maximumPixels=cap,unverifiedUntilFreshSourceAndColourReviews=True)
                        selection._save_image(patch_image,folder/f'r{rid}-hair-matte.png')
                    else:patch,guard=_remove_confirmed_weak_leak(original,row,cm,nm,old_points)
                    before=new[y0:y1,x0:x1].copy();part=new[y0:y1,x0:x1]
                    decreases=patch<original[y0:y1,x0:x1];part[decreases]=np.minimum(part[decreases],patch[decreases])
                    row['maskChangedPixels']=int((before!=part).sum());row['leakRemovalGuard']=guard
                    local_records.append({'regionId':rid,'clothReceipt':cr,'nonTargetReceipt':nr,
                        'clothMaskPixelSha256':selection._pixels(cm,'L'),'nonTargetMaskPixelSha256':selection._pixels(nm,'L'),
                        'leakRemovalGuard':guard})
                    new_fg+=row['foreground'];new_bg+=(row['background'] if row['backgroundKinds']==['hair'] else negatives)
                    continue
                if not any(old_mask.getpixel((x,y))<230 for x,y in row['foreground']):
                    raise LocalSelectionRejected('true_miss只给了已完整选中的点，没有证实实际漏选内点',receipt)
                for x,y in row['foreground']:
                    if hard[y,x]:raise LocalSelectionRejected('grounded衣料点仍处硬保护，不能强吞保护',receipt)
                fg=[[x-x0,y-y0] for x,y in row['foreground']]
                bg=[[x-x0,y-y0] for x,y in row['background']+row['occluder']]
                crop=source.crop((x0,y0,x1,y1))
                cm,cr=_predict(backend,crop,fg,bg,Path(cache_root).resolve()/'models','target_cloth')
                selection._save_image(cm,folder/f'r{rid}-cloth.png');ca=np.asarray(cm)>0
                release=np.zeros(ca.shape,bool);needs=ca&new_soft[y0:y1,x0:x1]
                local={'regionId':rid,'clothReceipt':cr,'clothMaskPixelSha256':selection._pixels(cm,'L')}
                if needs.any():
                    if not row['occluder']:raise LocalSelectionRejected('要释放模型ribbon但没有独立局部occluder点',receipt)
                    ofg=[[x-x0,y-y0] for x,y in row['occluder']]
                    om,orr=_predict(backend,crop,ofg,fg,Path(cache_root).resolve()/'models','occluder')
                    selection._save_image(om,folder/f'r{rid}-occluder.png')
                    release=needs&(np.asarray(om)==0)&~hard[y0:y1,x0:x1]
                    local.update(occluderReceipt=orr,occluderMaskPixelSha256=selection._pixels(om,'L'),
                        releasedModelProtectionPixels=int(release.sum()))
                    if any(needs[y-y0,x-x0] and not release[y-y0,x-x0] for x,y in row['foreground']):
                        raise LocalSelectionRejected('局部双实例仍不能证实该保护内衣料，拒绝释放',receipt)
                new_soft[y0:y1,x0:x1]&=~release
                allowed=ca&~hard[y0:y1,x0:x1]&~new_soft[y0:y1,x0:x1]
                before=new[y0:y1,x0:x1].copy();new[y0:y1,x0:x1]=np.maximum(before,allowed.astype('uint8')*255)
                row['maskChangedPixels']=int((before!=new[y0:y1,x0:x1]).sum())
                local_records.append(local);new_fg+=row['foreground'];new_bg+=row['background']+row['occluder']
            if not np.array_equal(new[~roi_union],original[~roi_union]):raise LocalSelectionRejected('局部候选改变了ROI外旧alpha',receipt)
            for row in grounded:
                x0,y0,x1,y1=row['bboxPixels']
                row['maskChangedPixels']=int((new[y0:y1,x0:x1]!=original[y0:y1,x0:x1]).sum())
            protection=Image.fromarray((hard|new_soft).astype('uint8')*255)
            if ((new>0)&hard).any():raise LocalSelectionRejected('局部候选吞了硬保护',receipt)
            candidate=Image.fromarray(new);points=copy.deepcopy(old_points)
            points['foreground']+=new_fg;points['background']+=new_bg
            if any(new[y,x]>0 for x,y in points['background']):raise LocalSelectionRejected('局部候选包含真实负点',receipt)
            effective,recovery=selection._recover_domain(source,base,points,protection)
            numeric=selection._quality(candidate,source,points,protection,effective)
            changed=int((new!=original).sum());audit_only=(changed==0)
            if audit_only and any(row['status'] in ('true_miss','true_leak') for row in grounded):
                raise LocalSelectionRejected('声明真实缺陷却未产生可验证选区修正，未冒充auditOnly澄清',receipt)
            local_grounding={'sourcePixelSha256':identity['sourcePixelSha256'],'sourceSize':list(source.size),
                'regions':grounded,'auditOnly':audit_only,'maskChangedPixels':changed,'unverifiedForColourQA':True,
                'groundingInputSha256':record['signature'],'groundingOutputSha256':_jsha(record['raw']),
                'groundingRecordPath':str(folder/'plan.json'),'sourceModels':local_records,
                'outsideRoiChangedPixels':0,'hardProtectionChangedPixels':0,'maximumLocalRounds':1}
            receipt['localGrounding']=local_grounding
            attempt=folder/'attempt-01';attempt.mkdir(exist_ok=True)
            for name,image in [('protection.png',protection),('candidate-domain.png',effective['coarse']),
                    ('mask.png',candidate),('hard-protection.png',Image.fromarray(hard.astype('uint8')*255)),
                    ('model-protection.png',Image.fromarray(new_soft.astype('uint8')*255))]:selection._save_image(image,attempt/name)
            for name in ('background.png','instance-protection.png'):
                old_path=Path(canonical['runPath'])/f"attempt-{canonical['attempts'][-1]['number']:02}"/name
                if old_path.is_file():selection._save_image(Image.open(old_path).convert('L'),attempt/name)
            if explicit_protection is not None:selection._save_image(explicit_protection,folder/'explicit.png')
            selection._save_image(candidate,folder/'mask.png');overlay=selection._overlay(source,candidate)
            selection._save_image(overlay,folder/'overlay.png')
            review_montage=_montage(source,old_mask,actual_output,grounded,candidate)
            selection._save_image(review_montage,folder/'source-review.png')
            reviewed=selection._review(selection._vision_call(vision,folder,'review',
                SOURCE_REVIEW_INSTRUCTION.replace('{kind}',kind),{'phase':'local_source_review','kind':kind,
                    'subject':subject,'numericGate':numeric,'localGrounding':local_grounding,
                    'groundingIsNotAcceptance':True},[source,overlay]+[_montage(source,old_mask,actual_output,[row],candidate)for row in grounded]))
            compiled=copy.deepcopy(canonical['attempts'][-1]['compiled'])
            compiled['candidateDomainRecovery']=recovery
            compiled['automaticSourceConstraints']={**compiled.get('automaticSourceConstraints',{}),
                'protectedPixelSha256After':selection._pixels(protection,'L')}
            receipt.update(quality=numeric,independentReview=reviewed,canonicalProvenance=provenance,
                protectionEvidence=layers,oldReceiptPath=canonical['cacheManifestPath'],
                attempts=[{'number':1,'state':'accepted' if numeric['accepted'] and reviewed['accepted'] else 'rejected',
                    'points':points,'compiled':compiled,'quality':numeric,'independentReview':reviewed}],
                maskPath=str(folder/'mask.png'),overlayPath=str(folder/'overlay.png'),
                maskPixelSha256=selection._pixels(candidate,'L'),maskHashEncoding='l8_top_to_bottom',
                maskPngSha256=selection._sha((folder/'mask.png').read_bytes()),
                explicitProtectionSha256=canonical.get('explicitProtectionSha256'),completed=time.time())
            if not numeric['accepted'] or not reviewed['accepted']:raise LocalSelectionRejected('局部候选未通过原全局门禁/新独立复核',receipt)
            receipt.update(state='accepted',verified=True,accepted=True,colourQaRequired=True)
            selection._write(manifest,receipt);return candidate,receipt
        except selection.VisionCallUnknown as error:
            receipt.update(state='unknown',accepted=False,verified=False,error=str(error)[:2000]);selection._write(manifest,receipt)
            raise LocalSelectionRejected('局部视觉调用未决，保留请求不重付',receipt,code='automatic_local_selection_unknown') from error
        except Exception as error:
            receipt.update(state='rejected',accepted=False,verified=False,error=str(error)[:2000]);selection._write(manifest,receipt)
            if isinstance(error,LocalSelectionRejected):error.receipt=receipt;raise
            raise LocalSelectionRejected('局部工具失败，未global fallback：'+str(error),receipt) from error
