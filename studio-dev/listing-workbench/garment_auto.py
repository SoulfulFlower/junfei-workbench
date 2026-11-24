"""Prompt-free local clothing parsing, followed by source-pixel edge refinement.

U2Net clothes supplies coarse garment semantics; SCHP proposes body/accessory
protection and MobileSAM resolves object boundaries. All prompts and source
colour samples are produced here. No user points or product-specific coordinates,
colour keys or polygons are required. Models are pinned with licences.
"""
import hashlib,json,threading,time
from pathlib import Path
import numpy as np
from PIL import Image

VERSION='auto-cloth-v15-semantic-protection'
LOCK=threading.RLock()
_parser=None
_human_parser=None


def category(product):
    # The product, not the amount of visible trousers on a model, defines the SKU.
    text=' '.join(str(product.get(k) or '') for k in ('name','title','productName','category','categoryName')).lower()
    import re
    if re.search(r'连衣裙|连体|\b(dress|dresses|jumpsuit|romper|overalls)\b',text):return 'full'
    if re.search(r'半身裙|短裙|长裙|中裙|迷你裙|及膝裙|包臀裙|百褶裙|a字裙|裤|\b(skirt|skirts|pants|trousers|jeans|shorts|leggings)\b',text):return 'lower'
    if re.search(r'上衣|罩衫|衬衫|卫衣|外套|毛衣|开衫|套头衫|\b(top|tops|tunic|tunics|shirt|blouse|sweater|jacket|coat|hoodie|sweatshirt|pullover|cardigan)\b',text):return 'upper'
    return 'auto'


class ClothParser:
    def __init__(self,model_dir=None):
        import onnxruntime as ort
        folder=Path(model_dir or Path(__file__).parent/'models/cloth-parser')
        self.manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
        path=folder/self.manifest['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=self.manifest['sha256']:raise ValueError('自动识别模型校验失败，请恢复固定版本模型文件')
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])

    def predict(self,source):
        im=source.convert('RGB').resize((768,768),Image.Resampling.LANCZOS)
        arr=np.asarray(im,dtype='float32');arr/=max(float(arr.max()),1e-6)
        arr=(arr-np.array(self.manifest['mean'],dtype='float32'))/np.array(self.manifest['std'],dtype='float32')
        values=self.session.run([self.session.get_outputs()[0].name],{self.session.get_inputs()[0].name:arr.transpose(2,0,1)[None]})[0]
        if values.shape!=(1,4,768,768) or not np.isfinite(values).all():raise ValueError('自动识别模型输出异常')
        # Interpolate scores, never class IDs, to preserve narrow sleeve gaps.
        import cv2
        scores=np.stack([cv2.resize(x,source.size,interpolation=cv2.INTER_LINEAR) for x in values[0]])
        return scores.argmax(axis=0).astype('uint8')


def parser():
    global _parser
    if _parser is None:
        try:_parser=ClothParser()
        except (ImportError,FileNotFoundError) as error:raise ValueError('自动衣服识别组件未安装完整，请恢复models/cloth-parser模型及onnxruntime') from error
    return _parser


class HumanParser:
    """Pinned MIT SCHP/ATR ONNX; no downloaded Python or remote inference."""
    def __init__(self,model_dir=None):
        import onnxruntime as ort
        folder=Path(model_dir or Path(__file__).parent/'models/human-parser')
        self.manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
        path=folder/self.manifest['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=self.manifest['sha256']:
            raise ValueError('人体部位识别模型校验失败，请恢复固定版本模型文件')
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])

    @staticmethod
    def input(source):
        # The original SCHP extractor uses cv2 BGR, then this BGR-indexed
        # normalisation. RGB with those constants changes skin/cloth predictions.
        rgb=np.asarray(source.convert('RGB').resize((512,512),Image.Resampling.BILINEAR),dtype='float32')
        bgr=rgb[:,:,::-1]/255
        values=(bgr-np.array([.406,.456,.485],dtype='float32'))/np.array([.225,.224,.229],dtype='float32')
        return values.transpose(2,0,1)[None].copy()

    def predict(self,source):
        import cv2
        values=self.session.run(['logits'],{'pixel_values':self.input(source)})[0]
        if values.shape!=(1,18,512,512) or not np.isfinite(values).all():
            raise ValueError('人体部位识别模型输出异常')
        scores=np.stack([cv2.resize(value,source.size,interpolation=cv2.INTER_LINEAR) for value in values[0]])
        return scores.argmax(axis=0).astype('uint8')


def human_parser():
    global _human_parser
    if _human_parser is None:
        try:_human_parser=HumanParser()
        except (ImportError,FileNotFoundError) as error:
            raise ValueError('自动保护识别组件未安装完整，请运行install_colour_models.py恢复human-parser模型') from error
    return _human_parser


def choose(labels,kind,human=None):
    if kind not in ('auto','upper','lower','full'):raise ValueError('衣服类别无效')
    counts=[int(np.count_nonzero(labels==n)) for n in (1,2,3)]
    if kind=='auto':
        # Prefer a visible top/dress; otherwise a standalone lower garment.
        minimum=max(50,labels.size*.001)
        n=max((1,3),key=lambda k:counts[k-1]) if max(counts[0],counts[2])>=minimum else 2
    else:n={'upper':1,'lower':2,'full':3}[kind]
    mask=labels==n
    if n==1 and kind=='upper' and human is not None:
        # Editorial text can be misclassified as a top. Only a real body/cloth
        # domain can seed the garment, never a detached headline above it.
        mask &= body_domain(human)
    if (n==1 and kind=='upper' and human is not None and
            mask.sum()<max(50,labels.size*.001)):
        # A tight detail photo can leave the primary parser with only the
        # styling trousers. Use the independent upper-clothes class where the
        # primary parser has no conflicting garment label.
        # A long top over trousers may be classified as a full garment. The
        # independent upper-clothes class can resolve that ambiguity, while a
        # conflicting lower-garment label remains excluded.
        support=np.isin(labels,[0,3])&(human==4)
        if support.sum()>=max(50,labels.size*.01):mask=support
    if (n==2 and kind=='lower' and human is not None and
            mask.sum()<max(50,labels.size*.001)):
        # A distant wearer can be one full-garment region in U2Net. Recover
        # only independently identified skirt/trouser pixels, never the coat,
        # dress, skin or a conflicting primary upper-garment label.
        support=np.isin(labels,[0,3])&np.isin(human,[5,6])
        if support.sum()>=max(50,labels.size*.01):mask=support
    if mask.sum()<max(50,labels.size*.001):raise ValueError('未识别到该产品的衣服区域，请检查原图是否清晰、主体是否完整')
    if mask.mean()>.95:raise ValueError('自动选区异常覆盖整幅图片，已停止换色')
    return mask,('upper','lower','full')[n-1],counts


def model_prompts(mask,labels,source=None):
    """Seed disconnected cloth and diverse excluded regions from semantic labels."""
    import cv2
    minimum=max(6,round(mask.size/160000));fg=[]
    # Eroding breaks accidental pixel bridges around fingers, exposing islands.
    narrow=cv2.erode(mask.astype('uint8'),np.ones((5,5),np.uint8))
    for layer in (mask.astype('uint8'),narrow):
        n,parts,stats,_=cv2.connectedComponentsWithStats(layer)
        for i in sorted(range(1,n),key=lambda k:stats[k,cv2.CC_STAT_AREA],reverse=True)[:12]:
            if stats[i,cv2.CC_STAT_AREA]<minimum:continue
            dist=cv2.distanceTransform((parts==i).astype('uint8'),cv2.DIST_L2,5)
            y,x=np.unravel_index(dist.argmax(),dist.shape)
            if all(np.hypot(x-p[0],y-p[1])>12 for p in fg):fg.append([int(x),int(y)])
    excluded=~mask;bg=[]
    if source is not None:
        # Do not turn a parser's uncertain same-fabric hole into a hard negative
        # prompt. This matters for pale cloth against a similarly coloured set.
        rgb=np.asarray(source.convert('RGB'));lab=cv2.cvtColor(rgb.astype('float32')/255,cv2.COLOR_RGB2LAB)
        samples=lab[mask];samples=samples[::max(1,len(samples)//2500)]
        cv2.setRNGSeed(0)
        _,_,centres=cv2.kmeans(samples.astype('float32'),min(8,len(samples)),None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,.2),1,cv2.KMEANS_PP_CENTERS)
        distance=np.min(np.stack([np.linalg.norm(lab-c,axis=2) for c in centres]),axis=0)
        excluded=excluded&(distance>12)
        if not excluded.any():excluded=~mask
    # Grid sampling gives hands, hair, interior openings and other garments
    # their own negative prompts, instead of only choosing the white border.
    h,w=mask.shape
    for gy in range(6):
        for gx in range(6):
            x0,x1=round(w*gx/6),round(w*(gx+1)/6);y0,y1=round(h*gy/6),round(h*(gy+1)/6)
            patch=excluded[y0:y1,x0:x1].astype('uint8')
            if patch.size==0 or not patch.any():continue
            distance=cv2.distanceTransform(patch,cv2.DIST_L2,5)
            yy,xx=np.unravel_index(distance.argmax(),distance.shape)
            if distance[yy,xx]>=2:bg.append([x0+int(xx),y0+int(yy)])
    if not fg or not bg:raise ValueError('自动识别未获得可靠的衣服和非衣服区域')
    return fg[:24],bg[:48]


def fabric_distance(source,semantic):
    """Learn the garment's interior shades, excluding narrow semantic islands."""
    import cv2
    rgb=np.asarray(source.convert('RGB'))
    depth=cv2.distanceTransform(semantic.astype('uint8'),cv2.DIST_L2,5)
    core=depth>depth.max()*.4
    lab=cv2.cvtColor(rgb.astype('float32')/255,cv2.COLOR_RGB2LAB)
    samples=lab[core];samples=samples[::max(1,len(samples)//2500)]
    cv2.setRNGSeed(0)
    _,assignments,centres=cv2.kmeans(samples.astype('float32'),min(6,len(samples)),None,
        (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,.2),1,cv2.KMEANS_PP_CENTERS)
    weights=np.bincount(assignments.ravel(),minlength=len(centres))/len(samples)
    dominant=centres[int(weights.argmax())]
    # A small background opening is not an additional fabric palette. Preserve
    # the garment's neighbouring light/shadow clusters, and genuinely large
    # second colours, without certifying a rare, distant chair/skin colour.
    centres=centres[(np.linalg.norm(centres-dominant,axis=1)<=24)|(weights>=.2)]
    return np.min(np.stack([np.linalg.norm(lab-centre,axis=2) for centre in centres]),axis=0)


def component_points(layer,minimum=0,limit=2):
    import cv2
    count,parts,stats,_=cv2.connectedComponentsWithStats(layer.astype('uint8'))
    points=[]
    for index in sorted(range(1,count),key=lambda k:stats[k,cv2.CC_STAT_AREA],reverse=True)[:limit]:
        if stats[index,cv2.CC_STAT_AREA]<minimum:continue
        depth=cv2.distanceTransform((parts==index).astype('uint8'),cv2.DIST_L2,5)
        y,x=np.unravel_index(depth.argmax(),depth.shape)
        points.append([int(x),int(y)])
    return points


def cropped_upper_points(semantic):
    """Place deep seeds across the visible upper garment in a tight crop."""
    import cv2
    depth=cv2.distanceTransform(semantic.astype('uint8'),cv2.DIST_L2,5)
    x,y,w,h=cv2.boundingRect(cv2.findNonZero(semantic.astype('uint8')))
    minimum=max(3,min(w,h)*.025)
    points=[]
    for row in range(2):
        for column in range(2):
            x0=x+w*column//2;x1=x+w*(column+1)//2
            y0=y+h*row//2;y1=y+h*(row+1)//2
            patch=depth[y0:y1,x0:x1]
            if patch.size and patch.max()>=minimum:
                py,px=np.unravel_index(patch.argmax(),patch.shape)
                points.append([x0+int(px),y0+int(py)])
    return points


def contrast_components(candidate,distance,threshold=24):
    """A contrasting seam anchors the whole agreed non-target garment region.

    Black denim's shadows can match a black top. A per-pixel colour threshold
    protects only its highlights and leaves the rest free to flood. Expand the
    evidence within the two models' agreed connected region, while an isolated
    same-fabric sleeve misclassification has no contrasting anchor.
    """
    import cv2
    count,parts,stats,_=cv2.connectedComponentsWithStats(candidate.astype('uint8'))
    anchors=np.bincount(parts[candidate&(distance>threshold)],minlength=count)
    keep=[index for index in range(1,count)
          if anchors[index]>=max(12,stats[index,cv2.CC_STAT_AREA]*.01)]
    return np.isin(parts,keep)


def body_domain(human):
    """A body or garment of any class bounds recovery away from scene objects."""
    import cv2
    body=(human>0).astype('uint8')
    if body.sum()<max(20,body.size*.001):
        raise ValueError('人体或衣物轮廓识别不足，已停止自动扩展选区')
    # This is only a maximum recovery domain, not foreground truth. Close small
    # parsing voids (including truncated edge crops) so an uncertain body-label
    # hole cannot punch a new hole into otherwise supported clothing.
    closing=max(2,round(max(body.shape)*.015))
    body=cv2.morphologyEx(body,cv2.MORPH_CLOSE,np.ones((closing*2+1,)*2,'uint8'))
    radius=max(2,round(max(body.shape)/400))
    return cv2.dilate(body,np.ones((radius*2+1,)*2,'uint8'))>0


def texture_fields(source):
    """Local gradient orientation and multi-scale texture, from original pixels."""
    import cv2
    gray=cv2.cvtColor(np.asarray(source.convert('RGB')),cv2.COLOR_RGB2GRAY).astype('float32')
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3)/8
    gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)/8
    angle=np.mod(np.arctan2(gy,gx),np.pi)
    return {'bins':np.minimum(7,(angle*8/np.pi).astype('uint8')),'magnitude':np.hypot(gx,gy),
            'bands':[np.abs(gray-cv2.GaussianBlur(gray,(0,0),sigma)) for sigma in (1,2,4,8)]}


def fabric_reference(region,seed,clothing):
    import cv2
    reference=np.zeros(region.shape,bool)
    unit=max(2,round(max(region.shape)*.01))
    for radius in (unit,unit*2,unit*4):
        reference=(cv2.dilate(region.astype('uint8'),np.ones((radius*2+1,)*2,'uint8'))>0)&seed&clothing
        if reference.sum()>100:break
    return reference


def matching_texture(region,seed,clothing,fields):
    import cv2
    core=cv2.erode(region.astype('uint8'),np.ones((3,3),'uint8'))>0
    if core.sum()<10:core=region
    reference=fabric_reference(region,seed,clothing)
    if reference.sum()<20:return None
    def descriptor(mask):
        histogram=np.bincount(fields['bins'][mask],weights=fields['magnitude'][mask],minlength=8)
        histogram/=max(1e-6,np.linalg.norm(histogram))
        spectrum=np.array([float(band[mask].mean()) for band in fields['bands']])
        energy=float(spectrum[0]);spectrum/=max(1e-6,np.linalg.norm(spectrum))
        return histogram,spectrum,energy
    a,b,energy=descriptor(core);c,d,reference_energy=descriptor(reference)
    return {'orientation':float(a@c),'spectrum':float(b@d),
            'energyRatio':energy/max(reference_energy,1e-6),'referenceEnergy':reference_energy}


def near_hair_recovery(seed,hair,distance,clothing,source=None):
    """Recover small cloth-like omissions beside the best clothing object.

    Long dark hair can share the shirt's colour and a coarse clothing label.
    Its long connected region is not a garment-edge omission. Only small
    nearby fragments with independent clothing support are considered here.
    """
    import cv2
    _,_,w,h=cv2.boundingRect(cv2.findNonZero(seed.astype('uint8')));scale=max(w,h)
    near=cv2.distanceTransform((~seed).astype('uint8'),cv2.DIST_L2,5)<=max(2,round(scale*.02))
    candidate=hair&~seed&near&(distance<12)
    count,parts,stats,_=cv2.connectedComponentsWithStats(candidate.astype('uint8'))
    supports=np.bincount(parts[clothing],minlength=count);keep=[];fields=None
    for index in range(1,count):
        area=stats[index,cv2.CC_STAT_AREA]
        if area<4 or max(stats[index,cv2.CC_STAT_WIDTH],stats[index,cv2.CC_STAT_HEIGHT])>scale*.08:continue
        anchored=supports[index]>=max(2,area*.15)
        if source is None:
            if anchored:keep.append(index)
            continue
        if fields is None:fields=texture_fields(source)
        texture=matching_texture(parts==index,seed,clothing,fields)
        if texture is None:continue
        # Existing clothing anchors may support an irregular fold. An island
        # missed by both coarse models requires strong matching fine texture
        # from its nearby, independently selected garment instead.
        anchored_match=anchored and (texture['referenceEnergy']<.1 or
            texture['orientation']>=.5 and .25<=texture['energyRatio']<=4)
        texture_match=(area>=20 and texture['orientation']>=.75 and texture['spectrum']>=.98
                       and .5<=texture['energyRatio']<=1.6)
        if anchored_match or texture_match:keep.append(index)
    return np.isin(parts,keep)


def small_supported_fabric(seed,garment,distance,clothing,source):
    """Retain small fabric islands supported by SAM and human garment parsing.

    U2Net may call cloth behind a hair curl background. SAM can already select
    part of that island, but GrabCut then loses it among similar dark hair.
    Human parsing alone is not permission to add an island: its source texture
    must also agree with nearby independently selected clothing.
    """
    import cv2
    _,_,w,h=cv2.boundingRect(cv2.findNonZero(seed.astype('uint8')));scale=max(w,h)
    candidate=garment&(distance<12)
    count,parts,stats,_=cv2.connectedComponentsWithStats(candidate.astype('uint8'))
    seed_counts=np.bincount(parts[seed],minlength=count)
    clothing_counts=np.bincount(parts[clothing],minlength=count);keep=[];fields=None
    for index in range(1,count):
        area=stats[index,cv2.CC_STAT_AREA]
        if area<20 or max(stats[index,cv2.CC_STAT_WIDTH],stats[index,cv2.CC_STAT_HEIGHT])>scale*.08:continue
        # This is a repair for islands predominantly missed by the clothing
        # parser, not a second chroma test on already supported shirt edges.
        if clothing_counts[index]>=area*.2:continue
        if seed_counts[index]<max(5,area*.1):continue
        if fields is None:fields=texture_fields(source)
        texture=matching_texture(parts==index,seed,clothing,fields)
        if (texture is not None and texture['orientation']>=.75 and texture['spectrum']>=.98
                and .5<=texture['energyRatio']<=1.6):keep.append(index)
    recovery=np.zeros(seed.shape,bool);fibres=np.zeros(seed.shape,bool)
    if keep:
        chroma=cv2.cvtColor(np.asarray(source.convert('RGB')),cv2.COLOR_RGB2LAB)[:,:,1:].astype('float32')
        for index in keep:
            region=parts==index;reference=fabric_reference(region,seed,clothing)
            anchors=chroma[reference];centre=np.median(anchors,axis=0)
            spread=np.maximum(1,1.4826*np.median(np.abs(anchors-centre),axis=0))
            deviation=np.sqrt(np.sum(((chroma-centre)/spread)**2,axis=2))
            # The source cloth's own robust chroma distribution separates
            # warm foreground strands from dark fabric. This applies only to
            # a newly validated island, never to the already selected shirt.
            limit=max(2,float(np.quantile(deviation[reference],.95)))
            accepted=deviation<=limit
            recovery|=region&accepted;fibres|=region&~accepted
    return recovery,fibres


def prepare_matting(cache):
    """Select a writable account cache before any PyMatting/Numba JIT import."""
    import os
    folder=Path(cache).resolve();folder.mkdir(parents=True,exist_ok=True)
    os.environ['NUMBA_CACHE_DIR']=str(folder)
    import numba
    # The worker may have imported Numba before this request. Its dispatchers
    # must still use this account's cache rather than read-only site-packages.
    numba.config.CACHE_DIR=str(folder)
    import pymatting
    from local_mask_recolor import fabric_matte
    return fabric_matte


def automatic_edge_alpha(source,final,seed,evidence,protection,island):
    """Fuse only uncertain accessory edges and newly recovered cloth islands."""
    import cv2
    start=time.monotonic();shape=final.shape
    _,_,w,h=cv2.boundingRect(cv2.findNonZero(seed.astype('uint8')))
    radius=max(2,round(max(w,h)*.025))
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*radius+1,)*2)
    bag=evidence.get('bagLabels',np.zeros(shape,bool))
    near_bag=cv2.dilate(bag.astype('uint8'),kernel)>0
    reliable=cv2.dilate(seed.astype('uint8'),np.ones((5,5),'uint8'))>0
    weak=near_bag&~reliable&~evidence.get('clothing',np.zeros(shape,bool))
    # Opening supplies only a subtraction, and only in the uncertain region.
    # It cannot extend a sleeve into a protected bag or change reliable cloth.
    opened=cv2.morphologyEx(final.astype('uint8'),cv2.MORPH_OPEN,kernel)>0
    removed=final&weak&~opened;selected=final&~removed
    scope=(cv2.dilate(island.astype('uint8'),np.ones((7,7),'uint8'))>0)|weak
    band_kernel=np.ones((5,5),'uint8')
    band=(cv2.dilate(selected.astype('uint8'),band_kernel)>0)&~(cv2.erode(selected.astype('uint8'),band_kernel)>0)
    scope&=band
    alpha=selected.astype('float64');solves=0;largest=0
    if scope.any():
        matte=prepare_matting(evidence['matteCache'])
        count,parts,stats,_=cv2.connectedComponentsWithStats(scope.astype('uint8'))
        for index in range(1,count):
            if stats[index,cv2.CC_STAT_AREA]<4:continue
            x,y,w,h,_=map(int,stats[index])
            # A long edge is divided into small tiles. Padding supplies fixed
            # foreground/background; no 1600px full-frame sparse solve occurs.
            for yy in range(y,y+h,96):
                for xx in range(x,x+w,96):
                    x0=max(0,xx-12);y0=max(0,yy-12)
                    x1=min(source.width,xx+108,x+w+12);y1=min(source.height,yy+108,y+h+12)
                    allowed=parts[y0:y1,x0:x1]==index
                    window=np.zeros(allowed.shape,bool)
                    window[yy-y0:min(yy+96,y+h)-y0,xx-x0:min(xx+96,x+w)-x0]=True
                    allowed&=window
                    if allowed.sum()<4:continue
                    local_selected=selected[y0:y1,x0:x1]
                    local_protection=protection[y0:y1,x0:x1]
                    interior=cv2.erode(local_selected.astype('uint8'),band_kernel)>0
                    possible=cv2.dilate(local_selected.astype('uint8'),band_kernel)>0
                    if (local_selected.sum()<50 or not np.any(interior&~local_protection)
                            or not np.any(~possible|local_protection)):continue
                    values=matte(source.crop((x0,y0,x1,y1)),
                        Image.fromarray(local_selected.astype('uint8')*255),
                        Image.fromarray(local_protection.astype('uint8')*255),radius=2)
                    # Accessory-adjacent matting is also strictly subtractive.
                    values[near_bag[y0:y1,x0:x1]&~selected[y0:y1,x0:x1]]=0
                    alpha[y0:y1,x0:x1][allowed]=values[allowed]
                    solves+=1;largest=max(largest,(x1-x0)*(y1-y0))
    alpha[protection]=0
    if 'bodyDomain' in evidence:alpha[~evidence['bodyDomain']]=0
    evidence['edgeRefinement']={'method':'local-source-matting','radius':2,'maxTile':120,
        'trimmedPixels':int(removed.sum()),'softPixels':int(((alpha>0)&(alpha<1)).sum()),
        'roiCount':solves,'largestRoiPixels':largest,'seconds':round(time.monotonic()-start,3)}
    return Image.fromarray(np.rint(alpha*255).clip(0,255).astype('uint8'))


def automatic_evidence(source,semantic,labels,human,selected,protected):
    import cv2
    distance=fabric_distance(source,semantic)
    skin=np.isin(human,[11,12,13,14,15])&(distance>18)
    accessories=np.isin(human,[8,16])
    # Arms are often mislabelled sleeves in cropped photos. Only bare-skin
    # colours become protection; the arm class alone never cuts a sleeve out.
    # A close crop can label a black shoulder as hair. Similar-colour pixels
    # remain uncertain here; the source/SAM boundaries decide them later.
    hair=(human==2)&(distance>12)
    proposal_protection=cv2.erode(((human==2)|skin|accessories).astype('uint8'),np.ones((5,5),'uint8'))>0
    protection=cv2.erode((hair|skin|accessories).astype('uint8'),np.ones((5,5),'uint8'))>0
    user_protection=np.asarray(protected.convert('L'))>0
    protection|=user_protection
    proposal_protection|=user_protection
    lower_non_target=(human==4)&(labels!=2) if selected=='lower' else np.zeros(semantic.shape,bool)
    # A same-colour jacket is still a different garment. When the coarse
    # parser merged an outfit, colour distance cannot protect its upper half.
    protection|=lower_non_target
    proposal_protection|=lower_non_target
    clean=semantic&~protection
    foreground=component_points(clean,limit=1)
    if not foreground:raise ValueError('自动保护后未获得可靠衣料区域，请检查原图')
    if selected=='upper':other=contrast_components((labels==2)&np.isin(human,[5,6]),distance)
    elif selected=='lower':other=lower_non_target
    else:other=np.zeros(semantic.shape,bool)
    h,w=semantic.shape
    border=[]
    # A crop may have clothing in a corner. Move that negative along the image
    # border to a semantic non-clothing pixel rather than contradicting it.
    edge=np.zeros(semantic.shape,bool);edge[[0,-1],:]=True;edge[:,[0,-1]]=True
    ys,xs=np.nonzero(edge&~semantic)
    for x,y in ((0,0),(w-1,0),(0,h-1),(w-1,h-1)):
        if len(xs):
            i=int(np.argmin((xs-x)**2+(ys-y)**2));point=[int(xs[i]),int(ys[i])]
            if point not in border:border.append(point)
    minimum=max(12,round(semantic.size/2560))
    negatives=[]
    for layer in (human==2,skin,human==16,other):
        negatives.extend(component_points(layer,minimum))
    if not border and not negatives:raise ValueError('自动识别没有可靠的非衣服区域')
    return {'foreground':foreground,'border':border,'background':negatives,'clean':clean,
            'protected':protection,'proposalProtection':proposal_protection,
            'userProtection':user_protection,
            'skinLabels':np.isin(human,[11,12,13,14,15]),
            'hairProtection':cv2.erode((human==2).astype('uint8'),np.ones((5,5),'uint8'))>0,
            'hairLabels':human==2,
            'humanClothing':np.isin(human,{'upper':[4,7],'lower':[5,6,7],'full':[4,5,6,7]}[selected]),
            'bagLabels':human==16,
            'bodyDomain':body_domain(human),'clothing':semantic,
            'proposalClean':semantic&~proposal_protection,'other':other,'distance':distance}


def sam_proposals(source,evidence,cache):
    """Evaluate automatic prompt alternatives; a bad semantic island is not truth."""
    import garment_workflow
    foreground=evidence['foreground'];border=evidence['border'];negative=evidence['background']
    variants=[border,negative,border+negative[:2],negative[-3:],border+negative[-2:]]
    candidates=[];diagnostics=[];seen=set()
    model=garment_workflow.selector(cache)
    for background in variants:
        key=tuple(tuple(point) for point in background)
        if not background or key in seen:continue
        seen.add(key)
        try:mask,receipt=model.select(source,foreground,background)
        except ValueError as error:
            diagnostics.append({'accepted':False,'reason':str(error)[:200]});continue
        pixels=np.asarray(mask)>127;area=max(1,int(pixels.sum()))
        clean=evidence.get('proposalClean',evidence['clean'])
        coverage=float((pixels&clean).sum()/max(1,clean.sum()))
        spill=float((pixels&evidence.get('proposalProtection',evidence['protected'])).sum()/area)
        other=float((pixels&evidence['other']).sum()/area)
        score=coverage-2*spill-2*other+.2*receipt.get('predictedIou',0)
        diagnostics.append({'accepted':True,'score':round(score,6),'semanticCoverage':round(coverage,6),
                            'protectedOverlap':round(spill,6),'predictedIou':receipt.get('predictedIou')})
        candidates.append((score,mask,receipt,background))
    if not candidates:raise ValueError('自动识别候选均未通过模型边界检查，请检查原图；未使用错误语义选区替代')
    score,best,receipt,background=max(candidates,key=lambda item:item[0])
    # Low-quality whole-person/background candidates must not enlarge the
    # final recovery domain. Comparable candidates still recover an occluded
    # sleeve absent from the best single decoder output.
    union=np.logical_or.reduce([np.asarray(item[1])>127 for item in candidates if item[0]>=score-.1])
    return best,union,background,{'engine':'MobileSAM ONNX','proposalChecks':diagnostics,
                                'selected':receipt,'edgeRefined':True}


def chromatic_fabric_recovery(rgb, seed, union, evidence):
    """Restore colour-distinct omissions connected to verified upper cloth."""
    import cv2

    clean = evidence['clean']
    distance = evidence['distance']
    anchors = seed & clean & (distance < 8)
    empty = np.zeros(seed.shape, bool)
    if anchors.sum() < 50:
        return empty, empty
    lab = cv2.cvtColor(rgb.astype('float32') / 255, cv2.COLOR_RGB2LAB)
    chroma = lab[:, :, 1:]
    samples = chroma[anchors]
    samples = samples[::max(1, len(samples) // 3000)]
    axis = np.median(samples, axis=0)
    strength = np.linalg.norm(axis)
    if strength < 19:
        return empty, empty
    axis /= strength
    magnitudes = np.linalg.norm(samples, axis=1)
    agreement = (samples @ axis) >= .96 * magnitudes
    if agreement.mean() < .85:
        return empty, empty

    # Body parsing can omit the top of an upper garment when the face and
    # shoulders are out of frame. Widen that bound only for a tight crop and
    # only for continuous, same-hue fabric supported by the clothing parser.
    domain = evidence['bodyDomain']
    crop_edges = (clean[0], clean[-1], clean[:, 0], clean[:, -1])
    cropped = clean.mean() >= .25 and max(edge.mean() for edge in crop_edges) >= .35
    human_cloth = evidence['humanClothing']
    near_clean = cv2.dilate(clean.astype('uint8'), np.ones((11, 11), 'uint8')) > 0
    support = ((clean & union) | (human_cloth & near_clean)) & domain
    if cropped:
        support |= clean
    length = np.linalg.norm(chroma, axis=2)
    projection = chroma[:, :, 0] * axis[0] + chroma[:, :, 1] * axis[1]
    lightness = lab[:, :, 0]
    reference_l = lightness[anchors]
    # Protect actual skin to its visible edge, including a thumbnail. An
    # arm label on a dark, same-hue fabric shadow does not count as bare skin.
    skin = evidence['skinLabels'] & (distance > 18) & (
        (lightness > np.median(reference_l) + 14) | (projection < .82 * length))
    evidence['chromaticSkinProtection'] = skin
    matched_edge = (projection >= .975 * length) & (length >= max(13, strength * .42)) & (
        lightness <= np.quantile(reference_l, .95) + 14)
    evidence['chromaticEdgeTone'] = matched_edge & ~(skin | evidence['other'] | evidence['bagLabels'] | evidence['userProtection'])
    reliable_highlight = (clean & human_cloth) & (projection >= .965 * length) & (length >= strength * .75)
    matching = support & ((distance < 16) | reliable_highlight) & (length >= max(9, strength * .37)) & (projection >= .93 * length)
    # Deep folds lose both lightness and chroma. The same hue still identifies
    # them inside the coarse cloth outline, away from its most uncertain edge.
    interior = cv2.erode(clean.astype('uint8'), np.ones((9, 9), 'uint8')) > 0
    shadow_lightness = np.quantile(reference_l, .25)
    shadows = interior & support & ~evidence['hairProtection'] & (lightness < shadow_lightness)
    matching |= shadows & (length >= 4) & (projection >= .87 * length)

    # A top-edge torso crop may confuse large fabric folds for hair or bare
    # arms. Inside the closed garment contour, colour still distinguishes dark
    # folded cloth from neutrals, even if both semantic outputs miss the fold.
    tightly_framed_torso = cropped and evidence['clothing'][0].mean() >= .35
    override = empty.copy()
    if tightly_framed_torso:
        stroke = max(5, round(max(clean.shape) * .022))
        coarse = evidence['clothing'].astype('uint8')
        closed = cv2.morphologyEx(coarse, cv2.MORPH_CLOSE, np.ones((stroke * 2 + 1,) * 2, 'uint8'))
        inner = cv2.erode(closed, np.ones((13, 13), 'uint8')) > 0
        override |= inner & (lightness < shadow_lightness) & (length >= 4) & (projection >= .90 * length)
        # Some folds are labelled background in both coarse outputs. A
        # matching fold can still be recovered inside the final cloth's
        # closed silhouette; this evidence alone cannot extend its outer edge.
        fold_tone = (projection >= .92 * length) & (length >= 4) & (
            (lightness < shadow_lightness) | (length >= strength * .60))
        fold_tone |= (lightness < min(5, shadow_lightness)) & (length >= 1.1) & (projection >= .80 * length)
        evidence['enclosedFoldTone'] = inner & fold_tone & ~(evidence['userProtection'] | evidence['other'] | evidence['bagLabels'] | skin)
        # Tinted edge pixels of a torso crop can be labelled hair even when
        # the adjacent source shows a continuous sleeve. Allow only strongly
        # cloth-coloured pixels to take part in the limited edge completion.
        evidence['croppedEdgeTone'] = (projection >= .96 * length) & (length >= max(13, strength * .44)) & ~(
            evidence['userProtection'] | evidence['other'] | evidence['bagLabels'] | skin)

    # A narrow object label can occur on dyed drawstrings. Restrict this
    # exception to thin, strongly colour-matched strips inside coarse cloth.
    if cropped:
        bag = evidence['bagLabels'].astype('uint8')
        bag_count, bag_parts, bag_stats, _ = cv2.connectedComponentsWithStats(bag)
        thin = [part for part in range(1, bag_count)
                if min(bag_stats[part, cv2.CC_STAT_WIDTH], bag_stats[part, cv2.CC_STAT_HEIGHT]) <= min(seed.shape) * .026
                and max(bag_stats[part, cv2.CC_STAT_WIDTH], bag_stats[part, cv2.CC_STAT_HEIGHT]) <= max(seed.shape) * .09]
        override |= np.isin(bag_parts, thin) & (evidence['clothing']) & (projection >= .97 * length) & (length >= strength * .62)
    override &= ~(evidence['userProtection'] | evidence['other'] | skin)
    matching = (matching & ~evidence['protected']) | override
    matching &= ~(evidence['other'] | skin)
    count, parts, stats, _ = cv2.connectedComponentsWithStats(matching.astype('uint8'))
    anchored = np.bincount(parts[anchors], minlength=count)
    keep = [part for part in range(1, count)
            if anchored[part] >= max(8, stats[part, cv2.CC_STAT_AREA] * .025)]
    retained = np.isin(parts, keep)
    return retained, retained & override


def complete_edges(source,mask,union,evidence,labels,selected,background):
    """Refine source pixels; semantic classes are never forced into foreground."""
    import cv2
    rgb=np.asarray(source.convert('RGB'));seed=np.asarray(mask)>127
    protection=evidence['protected'].copy()
    recovery=np.zeros(seed.shape,bool);island=np.zeros(seed.shape,bool)
    chromatic=np.zeros(seed.shape,bool)
    if selected=='upper' and 'humanClothing' in evidence:
        chromatic,overridden=chromatic_fabric_recovery(rgb,seed,union,evidence)
        protection|=evidence.get('chromaticSkinProtection',False)
        if chromatic.any():
            protection[overridden]=False
            evidence['bodyDomain'] |= chromatic
            evidence['chromaticRecoveryPixels']=int((chromatic&~seed).sum())
    if 'hairProtection' in evidence:
        # Relax a same-colour false hair patch only where the best SAM clothing
        # object also supports it. A weaker alternative may include real dark
        # hair, so its union must never authorise this protection change.
        supported=cv2.dilate(seed.astype('uint8'),np.ones((5,5),'uint8'))>0
        if 'clothing' in evidence:
            recovery=near_hair_recovery(seed,evidence.get('hairLabels',evidence['hairProtection']),
                                        evidence['distance'],evidence['clothing'],source)
            supported|=recovery
        protection|=evidence['hairProtection']&~(supported|chromatic)
    if 'humanClothing' in evidence and 'clothing' in evidence:
        fabric,fibres=small_supported_fabric(seed,evidence['humanClothing'],evidence['distance'],
                                             evidence['clothing'],source)
        recovery|=fabric;protection|=fibres
        island=fabric|fibres
    possible=np.zeros(seed.shape,'uint8')
    x,y,w,h=cv2.boundingRect(cv2.findNonZero(union.astype('uint8')));possible[y:y+h,x:x+w]=1
    possible=cv2.dilate(possible,np.ones((33,33),'uint8'))>0
    gc=np.full(seed.shape,cv2.GC_BGD,'uint8');gc[possible]=cv2.GC_PR_BGD
    # Alternative SAM proposals help recover a sleeve behind a hand. Their
    # union supplies only probable, same-fabric pixels, never certain pixels.
    distance=evidence['distance'];clean=evidence['clean']
    gc[(seed&(distance<24))|(union&(distance<12))]=cv2.GC_PR_FGD
    gc[recovery|chromatic]=cv2.GC_PR_FGD
    closed=cv2.morphologyEx(seed.astype('uint8'),cv2.MORPH_CLOSE,np.ones((21,21),'uint8'))
    # A parser and SAM hole filling can both call the chair seen through an
    # elbow gap clothing. Semantic agreement cannot turn a different-colour
    # interior opening into certain foreground.
    certain=(cv2.erode(closed,np.ones((17,17),'uint8'))>0)&(distance<12)
    certain|=cv2.erode(recovery.astype('uint8'),np.ones((3,3),'uint8'))>0
    certain|=cv2.erode(chromatic.astype('uint8'),np.ones((5,5),'uint8'))>0
    gc[certain]=cv2.GC_FGD;gc[protection|evidence['other']]=cv2.GC_BGD
    for x,y in background:
        if not chromatic[y,x]:cv2.circle(gc,(x,y),3,cv2.GC_BGD,-1)
    for x,y in evidence['foreground']:cv2.circle(gc,(x,y),2,cv2.GC_FGD,-1)
    gc[protection]=cv2.GC_BGD
    if 'bodyDomain' in evidence:gc[~evidence['bodyDomain']]=cv2.GC_BGD
    if not np.isin(gc,[cv2.GC_FGD,cv2.GC_PR_FGD]).any() or not np.isin(gc,[cv2.GC_BGD,cv2.GC_PR_BGD]).any():
        raise ValueError('自动识别没有同时获得可靠前景与背景，已停止换色，请核对原选区')
    cv2.setRNGSeed(0);cv2.grabCut(rgb.copy(),gc,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
    final=np.isin(gc,[cv2.GC_FGD,cv2.GC_PR_FGD])
    count,parts,stats,_=cv2.connectedComponentsWithStats(final.astype('uint8'))
    minimum=max(5,int(clean.sum()*.0001));keep=[]
    target={'upper':[1,3],'lower':[2,3],'full':[1,2,3]}[selected]
    clean_counts=np.bincount(parts[clean],minlength=count)
    union_counts=np.bincount(parts[union],minlength=count)
    target_counts=np.bincount(parts[np.isin(labels,target)],minlength=count)
    recovery_counts=np.bincount(parts[recovery],minlength=count)
    for index in range(1,count):
        if clean_counts[index]>minimum or recovery_counts[index]>=max(4,stats[index,cv2.CC_STAT_AREA]*.25) or (stats[index,cv2.CC_STAT_AREA]>1000
                and union_counts[index]>1000 and target_counts[index]>5):
            keep.append(index)
    final=np.isin(parts,keep);final[protection]=False
    if 'bodyDomain' in evidence:final[~evidence['bodyDomain']]=False
    crop_edge=np.zeros(seed.shape,bool)
    if 'chromaticEdgeTone' in evidence:
        kernel=np.ones((9,9),'uint8')
        near=cv2.dilate(final.astype('uint8'),kernel)>0
        edge=near&~final&evidence['chromaticEdgeTone']&evidence['bodyDomain']
        edge&=evidence['clothing']|evidence['humanClothing']|~evidence['hairProtection']
        final|=edge;protection[edge]=False;island|=edge
    if 'croppedEdgeTone' in evidence:
        contour_kernel=np.ones((13,13),'uint8')
        close_cloth=cv2.dilate(final.astype('uint8'),contour_kernel)>0
        inside_cloth=cv2.erode(final.astype('uint8'),contour_kernel)>0
        crop_edge=close_cloth&~inside_cloth&evidence['croppedEdgeTone']
        final|=crop_edge;protection[crop_edge]=False;evidence['bodyDomain']|=crop_edge
        island|=crop_edge
    if 'enclosedFoldTone' in evidence:
        radius=max(5,round(max(seed.shape)*.027))
        closed=cv2.morphologyEx(final.astype('uint8'),cv2.MORPH_CLOSE,np.ones((radius*2+1,)*2,'uint8'))
        inside=cv2.erode(closed,np.ones((15,15),'uint8'))>0
        folds=inside&evidence['enclosedFoldTone']&~final
        final|=folds;protection[folds]=False;evidence['bodyDomain']|=folds
        island|=folds
        evidence['chromaticRecoveryPixels']=evidence.get('chromaticRecoveryPixels',0)+int(folds.sum())
    if final.sum()<max(50,final.size*.001) or final.mean()>.95:
        raise ValueError('自动识别边界异常，已停止换色，请查看原图和任务记录')
    alpha=automatic_edge_alpha(source,final,seed,evidence,protection,island|(chromatic&~seed))
    if crop_edge.any():
        values=np.asarray(alpha).copy()
        values[crop_edge]=np.maximum(values[crop_edge],204)
        alpha=Image.fromarray(values)
    return alpha


def identify(source,protected,cache,kind='auto',engine=None,human_engine=None):
    """Return an unsaved, prompt-free proposal; existing explicit protection wins."""
    import garment_workflow
    start=time.monotonic();original_size=source.size;original_alpha=source.getchannel('A') if 'A' in source.getbands() else None
    if original_alpha is not None:
        white=Image.new('RGBA',source.size,'white');white.alpha_composite(source.convert('RGBA'));source=white.convert('RGB')
    if max(source.size)>2048:
        scale=2048/max(source.size);size=tuple(max(1,round(n*scale)) for n in source.size)
        source=source.resize(size,Image.Resampling.LANCZOS);protected=protected.resize(size,Image.Resampling.NEAREST)
    with LOCK:
        labels=(engine or parser()).predict(source)
        human=(human_engine or human_parser()).predict(source)
        if human.shape!=labels.shape or not np.isin(human,np.arange(18)).all():
            raise ValueError('人体部位识别结果无效')
        semantic,selected,counts=choose(labels,kind,human)
        upper_fallback=(selected=='upper' and kind=='upper' and
                        not np.array_equal(semantic,(labels==1)&body_domain(human)))
        lower_fallback=(selected=='lower' and kind=='lower' and
                        not np.array_equal(semantic,labels==2))
        evidence=automatic_evidence(source,semantic,labels,human,selected,protected)
        if upper_fallback:
            points=cropped_upper_points(evidence['clean'])
            if points:evidence['foreground']=points
        evidence['matteCache']=Path(cache).parent/'numba-cache'
        mask,union,background,detail=sam_proposals(source,evidence,cache)
        mask=complete_edges(source,mask,union,evidence,labels,selected,background)
        detail['automaticBoundary']=evidence.get('edgeRefinement',{})
        detail['automaticBoundary']['chromaticRecoveryPixels']=evidence.get('chromaticRecoveryPixels',0)
        foreground=evidence['foreground']
    from image_selection import protect as semantic_protect
    mask,semantic_receipt=semantic_protect(mask,human,protected)
    detail['finalSemanticProtection']=semantic_receipt
    if mask.size!=original_size:mask=mask.resize(original_size,Image.Resampling.NEAREST)
    if original_alpha is not None:
        arr=np.asarray(mask).copy();arr[np.asarray(original_alpha)==0]=0;mask=Image.fromarray(arr)
    return mask,{'type':'automatic-clothing','engine':'U2Net clothes + SCHP ATR + MobileSAM + GrabCut',
        'version':VERSION,'modelRevision':'rembg-v0.0.0-u2net-cloth-seg','humanModelRevision':'schp-atr-18-61f4ff3-int8',
        'category':selected,'classPixels':counts,
        'semanticSource':('schp_upper_clothes' if upper_fallback else
                          'schp_lower_clothes' if lower_fallback else 'u2net_clothes'),
        'automatic':True,'userPointsRequired':False,'generatedForegroundPoints':foreground,'generatedBackgroundPoints':background,
        'seconds':round(time.monotonic()-start,3),'selection':detail,'imageGenerationSubmitted':False,'humanReviewed':False}
