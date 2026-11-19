"""Local masked reference-colour transport; all outputs remain candidates until QA."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path('data/batch-20261030');OUT=ROOT/'variant-production'

def roi(name,slot,size):
    path=OUT/f'{name}-mask-{slot}.json'
    if not path.exists():return None
    m=Image.new('L',(1000,1000));d=ImageDraw.Draw(m)
    for r in json.loads(path.read_text(encoding='utf-8'))['regions']:
        d.polygon([tuple(x) for x in r['outer']],fill=255)
        for h in r.get('holes',[]):d.polygon([tuple(x) for x in h],fill=0)
    return np.asarray(m.resize(size))

def mask_for(name,slot,im):
    a=np.asarray(im).astype(np.float32);hsv=cv2.cvtColor(a/255,cv2.COLOR_RGB2HSV)
    region=roi(name,slot,im.size)
    if region is None:return None
    # Broaden rough polygons slightly, then use exact source fabric chroma.
    expanded=cv2.dilate(region,np.ones((35,35),np.uint8))>0
    if name=='jewelry':
        gate=(hsv[:,:,0]>155)&(hsv[:,:,0]<205)&(hsv[:,:,1]>.15)
        total,labels,stats,_=cv2.connectedComponentsWithStats(gate.astype(np.uint8),8)
        chosen=np.zeros(gate.shape,dtype=bool)
        for i in range(1,total):
            part=labels==i
            if stats[i,cv2.CC_STAT_AREA]>=12 and np.any(part & (region>0)):
                chosen|=part
        m=chosen.astype(np.uint8)*255
    elif name=='bag':
        lab=cv2.cvtColor(a/255,cv2.COLOR_RGB2Lab)
        gate=(a[:,:,0]>a[:,:,1]+2)&(a[:,:,0]>a[:,:,2]+1)&(hsv[:,:,2]<.79)
        seeds=np.full(region.shape,cv2.GC_BGD,np.uint8)
        seeds[expanded]=cv2.GC_PR_BGD;seeds[region>0]=cv2.GC_PR_FGD
        seeds[(region>0)&gate]=cv2.GC_FGD
        bg=np.zeros((1,65));fg=np.zeros((1,65))
        cv2.grabCut(np.asarray(im),seeds,None,bg,fg,3,cv2.GC_INIT_WITH_MASK)
        m=(((seeds==cv2.GC_FGD)|(seeds==cv2.GC_PR_FGD))&gate).astype(np.uint8)*255
    else:return None
    return Image.fromarray(m).filter(ImageFilter.GaussianBlur(.45))

def transport(im,mask,ref,box):
    a=np.asarray(im).astype(np.float32)/255;alpha=np.asarray(mask).astype(np.float32)/255
    sample=np.asarray(ref.crop(box)).astype(np.float32)/255
    lab=cv2.cvtColor(a,cv2.COLOR_RGB2Lab);tar=cv2.cvtColor(sample,cv2.COLOR_RGB2Lab).reshape(-1,3)
    src=lab[alpha>.9];target=np.median(tar,axis=0);center=np.median(src,axis=0)
    mapped=lab.copy()
    # Keep local weave/lighting differences; replace dominant dye chroma.
    mapped[:,:,0]=np.clip(target[0]+(lab[:,:,0]-center[0])*.75,0,100)
    mapped[:,:,1]=target[1]+(lab[:,:,1]-center[1])*.2
    mapped[:,:,2]=target[2]+(lab[:,:,2]-center[2])*.2
    rgb=cv2.cvtColor(mapped,cv2.COLOR_Lab2RGB)
    out=np.clip(a*(1-alpha[:,:,None])+rgb*alpha[:,:,None],0,1)
    return Image.fromarray(np.rint(out*255).astype(np.uint8))

def main():
    refs=json.loads((OUT/'sku-image-map.json').read_text(encoding='utf-8'))
    # These source variants share the original woven crosshatch construction.
    compatible=['PeacockBlue','Grey','White','Pink','Red','DeepPurple','Green','LakeBlue','Beige','Burgundy','DeepSeaBlue','OffWhite']
    for name in ['jewelry','bag']:
        if name=='jewelry':
            targets=[(c,OUT/'sku-references'/name/(c+'-full.jpg')) for c,_,_ in refs[name] if c in compatible and c!='PeacockBlue']
        else:targets=[(c,ROOT/'bag-detail'/f'color-{i}.image') for i,c in enumerate(['Black','Coffee','Green','Purple','Beige']) if c!='Coffee']
        for slot in range(1,8):
            src=ROOT/f'ai-master-{name}'/f'{slot}.png'
            if not src.exists():continue
            im=Image.open(src).convert('RGB');mask=mask_for(name,slot,im)
            if mask is None:continue
            mask.save(OUT/f'{name}-mask-{slot}.png')
            for color,path in targets:
                ref=Image.open(path).convert('RGB')
                if name=='jewelry':box=tuple(round(v*s) for v,s in zip([.32,.31,.55,.38],[ref.width,ref.height,ref.width,ref.height]))
                else:box=(255,555,505,705)
                dest=OUT/name/color;dest.mkdir(parents=True,exist_ok=True)
                transport(im,mask,ref,box).save(dest/f'{slot}.png')
            print('LOCAL',name,slot,len(targets),flush=True)

if __name__=='__main__':main()
