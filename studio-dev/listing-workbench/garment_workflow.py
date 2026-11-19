"""Local prompt selection and coverage inspection for the recolour editor.

Each positive prompt is decoded separately, then unioned. Clothing split by a
hand therefore need not belong to the same connected component. No vendor
endpoint, credentials or image-generation provider is used.
"""
import threading
from pathlib import Path
import numpy as np
from PIL import Image
from garment_selection import GarmentSelector

LOCK=threading.RLock()
_selector=None


def selector(cache):
    global _selector
    # Account workers have separate processes; embeddings remain account-local.
    if _selector is None or _selector.cache!=Path(cache):
        try:_selector=GarmentSelector(Path(__file__).parent/'models'/'mobile-sam',cache)
        except (ImportError,FileNotFoundError) as error:raise ValueError('本机衣服识别组件未安装完整，请安装onnxruntime并恢复models/mobile-sam模型文件') from error
    return _selector


def prompts(data,size):
    foreground=data.get('foreground',[]);background=data.get('background',[])
    if not isinstance(foreground,list) or not 1<=len(foreground)<=24:
        raise ValueError('请在衣服和遗漏的小块衣料上标记保留点，最多24点')
    if not isinstance(background,list) or not 1<=len(background)<=48:
        raise ValueError('请至少在背景或皮肤上标记一个去除点，最多48点')
    # Bool must not silently become a valid coordinate.
    for points in (foreground,background):
        if any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(v) not in (int,float) for v in p) for p in points):
            raise ValueError('选点坐标无效')
    return GarmentSelector.points(foreground,size),GarmentSelector.points(background,size)


def combine(base,proposal,protected,operation):
    if operation not in ('replace','add'):raise ValueError('识别操作须为重新识别或补全选区')
    a=np.asarray(base.convert('L'));b=np.asarray(proposal.convert('L'));p=np.asarray(protected.convert('L'))
    if a.shape!=b.shape or a.shape!=p.shape:raise ValueError('识别选区尺寸不匹配')
    result=np.maximum(a,b) if operation=='add' else b.copy()
    result[p>0]=0
    return Image.fromarray(result.astype('uint8'))


def prompted_components(mask,foreground):
    """Discard disconnected noise unless a garment prompt explicitly selects it."""
    import cv2
    n,labels=cv2.connectedComponents((np.asarray(mask)>127).astype('uint8'))
    keep={int(labels[int(y),int(x)]) for x,y in foreground}-{0}
    return Image.fromarray(np.isin(labels,list(keep)).astype('uint8')*255)


def select(source,base,protected,data,cache,engine=None):
    foreground,background=prompts(data,source.size)
    protection=np.asarray(protected.convert('L'))
    if any(protection[int(y),int(x)]>0 for x,y in foreground):
        raise ValueError('保留点落在保护区中；请先擦除该处误保护，皮肤和五金仍保持保护')
    proposals=[];receipts=[]
    with LOCK:
        model=engine or selector(cache)
        for point in foreground:
            proposal,receipt=model.select(source,[point.tolist()],background.tolist())
            proposals.append(np.asarray(proposal));receipts.append(receipt)
    proposal=Image.fromarray(np.maximum.reduce(proposals).astype('uint8'))
    if type(data.get('refineEdges',True)) is not bool:raise ValueError('边缘细化参数无效')
    if data.get('refineEdges',True):
        proposal=GarmentSelector.refine(source,proposal,background,protected,foreground)
    proposal=prompted_components(proposal,foreground)
    # Independent decodes can disagree; no negative point may survive the union.
    arr=np.asarray(proposal)
    if any(arr[int(y),int(x)]>127 for x,y in background):raise ValueError('识别结果仍包含去除点，请增加附近去除点后重试')
    result=combine(base,proposal,protected,data.get('operation','replace'))
    return result,{'engine':'MobileSAM ONNX','operation':data.get('operation','replace'),
        'foreground':foreground.tolist(),'background':background.tolist(),'components':receipts,'edgeRefined':data.get('refineEdges',True),
        'imageGenerationSubmitted':False,'humanReviewed':False}


def inspect(source,alpha,protected):
    """Suggest near-mask, similar-colour remnants; suggestions never edit pixels.

    This is an inspection aid, not semantic proof. Dark hair/trousers can look
    like black fabric; the UI must highlight and ask for a garment prompt.
    """
    import cv2
    scale=min(1.,800/max(source.size));size=tuple(max(1,round(v*scale)) for v in source.size)
    rgb=np.asarray(source.convert('RGB').resize(size,Image.Resampling.BILINEAR))
    a=np.asarray(alpha.convert('L').resize(size,Image.Resampling.NEAREST))>230
    p=np.asarray(protected.convert('L').resize(size,Image.Resampling.NEAREST))>0
    if not a.any():return Image.new('L',source.size),{'suspectPixels':0,'regions':[],'suggestionOnly':True}
    lab=cv2.cvtColor(rgb.astype('float32')/255,cv2.COLOR_RGB2LAB)
    samples=lab[a];samples=samples[::max(1,len(samples)//3000)]
    # Cluster source garment shades, retaining folds instead of a single mean.
    cv2.setRNGSeed(0)
    k=min(5,len(samples))
    _,_,centres=cv2.kmeans(samples.astype('float32'),k,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,.2),1,cv2.KMEANS_PP_CENTERS)
    distance=np.min(np.stack([np.linalg.norm(lab-c,axis=2) for c in centres]),axis=0)
    radius=max(9,round(45*scale));near=cv2.dilate(a.astype('uint8'),np.ones((radius*2+1,)*2,np.uint8))>0
    edge=cv2.dilate(a.astype('uint8'),np.ones((5,5),np.uint8))>0
    candidate=(distance<10)&near&~edge&~p
    n,labels,stats,centroids=cv2.connectedComponentsWithStats(candidate.astype('uint8'))
    rows=[];keep=[]
    for i in range(1,n):
        x,y,w,h,area=stats[i]
        if area<max(6,round(20*scale*scale)):continue
        keep.append(i);rows.append({'pixels':round(int(area)/scale**2),'box':[round(int(v)/scale) for v in (x,y,x+w,y+h)],'point':[round(float(v)/scale) for v in centroids[i]]})
    rows.sort(key=lambda v:v['pixels'],reverse=True)
    mask=Image.fromarray(np.isin(labels,keep).astype('uint8')*255).resize(source.size,Image.Resampling.NEAREST)
    return mask,{'suspectPixels':sum(r['pixels'] for r in rows),'regions':rows[:30],'suggestionOnly':True,
        'message':'黄色仅是疑似漏选：可能包含相近颜色的头发或裤子，请用保留点核对衣料；系统不会自动涂色。'}
