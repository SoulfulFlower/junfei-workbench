"""Source-bound protected-part comparisons. Evidence only, never a pass flag."""
import hashlib
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw

def build(source,mask,output,receipt,allowed_root):
    empty={'tiles':[],'certifiesPreservation':False}
    if not isinstance(receipt,dict)or not receipt.get('runPath')or allowed_root is None:return None,empty
    root=Path(receipt['runPath']).resolve();allowed=Path(allowed_root).resolve()
    if not root.is_relative_to(allowed):raise ValueError('Protected evidence is outside this account evidence root')
    labels=root/'local-labels.npz';original=root/'source.png'
    if not labels.is_file()or not original.is_file():return None,{**empty,'reason':'legacy_source_has_no_local_labels'}
    for path in (labels,original):
        if not path.resolve().is_relative_to(root):raise ValueError('Protected source evidence escaped canonical folder')
    rgba=np.asarray(source.convert('RGBA'));result=np.asarray(output.convert('RGBA'));alpha=np.asarray(mask.convert('L'))
    if Image.open(original).convert('RGBA').tobytes()!=source.convert('RGBA').tobytes():raise ValueError('Protected evidence original does not match actual source')
    with np.load(labels,allow_pickle=False)as archive:human=archive['human']
    if human.shape!=rgba.shape[:2]or not np.isin(human,np.arange(18)).all():raise ValueError('Protected evidence labels are invalid')
    # Existing parser labels 14/15 are arms/hands; these remain hypotheses.
    count,components,stats,_=cv2.connectedComponentsWithStats(np.isin(human,[14,15]).astype('uint8'),8)
    selected=sorted(range(1,count),key=lambda i:(-int(stats[i,cv2.CC_STAT_AREA]),i))[:2]
    rows=[];images=[];sha=lambda a:hashlib.sha256(a.tobytes()).hexdigest()
    for label in selected:
        if stats[label,cv2.CC_STAT_AREA]<32:continue
        region=components==label;ys,xs=np.where(region)
        bbox=[max(0,int(xs.min())-12),max(0,int(ys.min())-12),min(source.width,int(xs.max())+13),min(source.height,int(ys.max())+13)]
        x0,y0,x1,y1=bbox;diff=np.max(np.abs(rgba.astype('int16')-result.astype('int16')),axis=2)
        rows.append({'bboxPixels':bbox,'bboxEncoding':'xyxy_half_open_original_source_pixels',
            'semanticLabelHypothesis':[14,15],'semanticRegionIsNotOwnershipProof':True,
            'semanticRegionPixels':int(region.sum()),'semanticRegionSelectedPixels':int(((alpha>0)&region).sum()),
            'semanticRegionChangedRgbaPixels':int(((diff>0)&region).sum()),'semanticRegionMaximumRgbaDifference':int(diff[region].max()),
            'sourceCropRgbaSha256':sha(rgba[y0:y1,x0:x1]),'outputCropRgbaSha256':sha(result[y0:y1,x0:x1])})
        delta=Image.fromarray(np.repeat(np.clip(diff*4,0,255).astype('uint8')[:,:,None],3,axis=2))
        images.append([im.crop(tuple(bbox)).convert('RGB')for im in (source,mask,output,delta)])
    if not rows:return None,empty
    panel=256;header=24;canvas=Image.new('RGB',(panel*4,(panel+header)*len(rows)),'#f4f4f0');draw=ImageDraw.Draw(canvas)
    for i,crops in enumerate(images):
        for j,(crop,title)in enumerate(zip(crops,['SOURCE','ALPHA','OUTPUT','RGBA DIFF x4'])):
            size=(crop.width,crop.height);scale=min(panel/size[0],panel/size[1]);display=(max(1,round(size[0]*scale)),max(1,round(size[1]*scale)))
            x=j*panel+(panel-display[0])//2;y=i*(panel+header)+header+(panel-display[1])//2
            canvas.paste(crop.resize(display,Image.Resampling.NEAREST),(x,y));draw.text((j*panel+4,i*(panel+header)+4),f'P{i} {title}',fill='black')
    return canvas,{'tiles':rows,'sourceSize':list(source.size),'labelArtifactSha256':hashlib.sha256(labels.read_bytes()).hexdigest(),
        'columnRoles':['source','actual_alpha','output','absolute_rgba_difference_display_gain4'],
        'certifiesPreservation':False,'zeroDifferenceMeansOnlyThoseExactPixelsUnchanged':True}
