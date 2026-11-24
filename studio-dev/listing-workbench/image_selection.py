"""Final semantic protection after all automatic garment edge recovery."""
import numpy as np
import cv2
from PIL import Image

VERSION='semantic-protection-v1'


def protect(mask, human_labels, explicit=None):
    labels=np.asarray(human_labels)
    a=np.asarray(mask.convert('L')).copy()
    if labels.shape!=a.shape or not np.isin(labels,np.arange(18)).all():
        raise ValueError('人体保护语义与选区不匹配')
    # ATR: head/accessories, skin/limbs, shoes. Recovery passes must never turn
    # these back into fabric based only on similar brown/pink RGB values.
    excluded=np.isin(labels,[1,2,3,9,10,11,12,13,14,15,16,17]).astype('uint8')
    radius=max(1,min(3,round(min(mask.size)/650)))
    excluded=cv2.dilate(excluded,np.ones((radius*2+1,radius*2+1),'uint8'))>0
    if explicit is not None:
        p=np.asarray(explicit.convert('L'))
        if p.shape!=a.shape:raise ValueError('显式保护区尺寸无效')
        excluded|=p>0
    removed=int(((a>0)&excluded).sum())
    a[excluded]=0
    return Image.fromarray(a),{'version':VERSION,'semanticExcludedPixels':removed,'protectionRadius':radius}
