"""Read a linked variant main photo and sample only automatically parsed fabric."""
import hashlib,io
import numpy as np
from PIL import Image,ImageOps
import garment_auto
import image_provider

VERSION='variant-main-cloth-colour-v2'


def main_reference(group,preferred=None):
    rows=[r for r in group.get('references',[]) if r.get('referenceType')=='amazon_variant_main' and r.get('sourceAsin')]
    if not rows:raise ValueError('该颜色缺少已核对的变体主图，不能自动猜色')
    return next((r for r in rows if r['url']==preferred),rows[0])


def read(reference):
    return image_provider.local_image(reference) if reference.startswith('/uploads/') else image_provider.remote_reference(reference)[0]


def sample(raw,product,cache):
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.width*opened.height>18_000_000:raise ValueError('变体主图超过1800万像素')
        im=ImageOps.exif_transpose(opened).convert('RGBA')
    mask,receipt=garment_auto.identify(im,Image.new('L',im.size),cache,garment_auto.category(product))
    return colour(im,mask),receipt


def colour(image,mask):
    """A robust middle fabric shade; never infer RGB from the variant's name."""
    import cv2
    rgba=np.asarray(image.convert('RGBA'));a=np.asarray(mask.convert('L'))>230
    a&=rgba[:,:,3]>230
    core=cv2.erode(a.astype('uint8'),np.ones((5,5),'uint8'))>0
    if core.sum()<50:core=a
    minimum=max(50,int((rgba[:,:,3]>230).sum()*.005))
    if core.sum()<minimum:raise ValueError('变体主图中没有足够的可见衣料，请核对真实衣料区域后取色，未自动猜色')
    rgb=rgba[:,:,:3][core];rgb=rgb[::max(1,len(rgb)//12000)]
    lab=cv2.cvtColor(rgb.astype('float32')[None]/255,cv2.COLOR_RGB2LAB)[0]
    low,high=np.percentile(lab[:,0],[30,70]);middle=lab[(lab[:,0]>=low)&(lab[:,0]<=high)]
    if len(middle)<25:middle=lab
    centre=np.median(middle,axis=0);dist=np.linalg.norm(middle-centre,axis=1)
    centre=np.median(middle[dist<=np.percentile(dist,80)],axis=0)
    target=np.rint(cv2.cvtColor(centre.astype('float32')[None,None],cv2.COLOR_LAB2RGB)[0,0]*255).clip(0,255).astype(int)
    return {'target':'#'+''.join(f'{x:02x}' for x in target),'rgb':target.tolist(),'fabricPixels':int(core.sum()),'variation':round(float(np.percentile(dist,80)),2),'method':VERSION}


def identify(product,group,reference,cache):
    main=main_reference(group,reference);raw=read(main['url']);shade,selection=sample(raw,product,cache)
    return {**shade,'reference':main['url'],'referenceSourceAsin':main['sourceAsin'],'sourceSha256':hashlib.sha256(raw).hexdigest(),
        'source':'automatic_variant_main','automaticReferenceVersion':VERSION,'selectionVersion':garment_auto.VERSION,
        'referenceSelection':{k:selection[k] for k in ('engine','version','category','automatic','userPointsRequired')},
        'imageGenerationSubmitted':False,'humanReviewed':False}
