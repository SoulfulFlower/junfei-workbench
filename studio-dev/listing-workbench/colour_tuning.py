"""Shared, deterministic colour controls for a single frame and a full gallery."""
import math

# Defaults preserve old saved recipes; new controls never imply new generation.
CONTROLS = {
    'saturation': (1., 0., 2.),
    'contrast': (0., -50., 50.),
    'shadows': (0., -25., 25.),
    'highlights': (0., -25., 25.),
    'colorDetail': (0., 0., 1.),
    'hue': (0., -180., 180.),
    'brightness': (0., -50., 50.),
    'lighting': (1., 0., 1.),
    'edgeFeather': (0., 0., 3.),
}


def controls(data):
    result = {}
    for name, (default, low, high) in CONTROLS.items():
        value = data.get(name, default)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('颜色细调参数无效：' + name)
        result[name] = value
    remove=data.get('removeCast',False)
    if type(remove) is not bool:raise ValueError('去除杂色参数无效')
    result['removeCast']=remove
    balance=data.get('colorBalance',{})
    if not isinstance(balance,dict) or set(balance)-{'shadows','midtones','highlights'}:raise ValueError('色彩平衡参数无效')
    result['colorBalance']={}
    for tone in ('shadows','midtones','highlights'):
        values=balance.get(tone,[0,0,0])
        if not isinstance(values,(list,tuple)) or len(values)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not -100<=v<=100 for v in values):raise ValueError('色彩平衡参数无效：'+tone)
        result['colorBalance'][tone]=list(values)
    curves=data.get('curves',{})
    if not isinstance(curves,dict) or set(curves)-{'rgb','red','green','blue'}:raise ValueError('曲线通道无效')
    result['curves']={}
    for channel in ('rgb','red','green','blue'):
        points=curves.get(channel,[[0,0],[255,255]])
        if not isinstance(points,(list,tuple)) or not 2<=len(points)<=16:raise ValueError('曲线需要2–16个控制点')
        if any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=255 for v in p) for p in points):raise ValueError('曲线坐标无效')
        if points[0][0]!=0 or points[-1][0]!=255 or any(b[0]-a[0]<1 for a,b in zip(points,points[1:])):raise ValueError('曲线横坐标须递增，首尾为0和255')
        result['curves'][channel]=[list(p) for p in points]
    return result


def grade(rgb,tuning):
    """Apply balanced tonal RGB offsets and channel LUTs before alpha blending."""
    import numpy as np
    color=np.asarray(rgb,dtype=np.float64).copy()
    light=color@np.array([.2126,.7152,.0722])
    shadow=np.clip(1-2*light,0,1);high=np.clip(2*light-1,0,1);mid=1-shadow-high
    for tone,weight in (('shadows',shadow),('midtones',mid),('highlights',high)):
        color+=weight[:,:,None]*np.array(tuning['colorBalance'][tone])/255
    color=color.clip(0,1)
    points=np.array(tuning['curves']['rgb'])
    color=np.interp(color*255,points[:,0],points[:,1])/255
    for i,channel in enumerate(('red','green','blue')):
        points=np.array(tuning['curves'][channel]);color[:,:,i]=np.interp(color[:,:,i]*255,points[:,0],points[:,1])/255
    return color
