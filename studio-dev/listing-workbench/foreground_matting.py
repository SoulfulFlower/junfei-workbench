"""Pinned local foreground alpha; source RGB is never generated or repainted."""
import hashlib,json,subprocess,threading,uuid
from pathlib import Path
import numpy as np
from PIL import Image
import app_paths

VERSION='original-foreground-birefnet-matting-v1'
LOCK=threading.RLock()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def settings():
    config=app_paths.APP/'models'/'foreground-matting'/'runtime.json'
    if not config.is_file():raise ValueError('高质量原片抠像工具尚未配置，未退回粗人体标签抠图')
    value=json.loads(config.read_text('utf8'))
    for key in ('python','worker'):
        if not Path(value[key]).is_file():raise ValueError('原片抠像运行文件缺失：'+key)
    if sha(value['worker'])!=value['workerSha256']:raise ValueError('原片抠像工具文件发生变化，先核对版本')
    if value['device']not in ('cpu','cuda'):raise ValueError('原片抠像设备配置无效')
    return value

def identity():
    value=settings()
    return {'version':VERSION,'workerSha256':value['workerSha256'],'weightSha256':value['weightSha256'],
        'device':value['device'],'size':value.get('size',1024),'threads':value.get('threads',4)}

def matte(source):
    rgb=np.asarray(source.convert('RGB')).copy();rgba=np.asarray(source.convert('RGBA'))
    policy=identity();config=settings()
    source_hash=hashlib.sha256(rgba.tobytes()+str(source.size).encode()).hexdigest()
    key=hashlib.sha256(json.dumps({'source':source_hash,'identity':policy},sort_keys=True).encode()).hexdigest()
    folder=app_paths.DATA/'foreground-matting'/key
    with LOCK:
        completed=folder/'completed.json'
        if completed.is_file():
            saved=json.loads(completed.read_text('utf8'));output=folder/saved['directory']
            if output.parent.resolve()!=folder.resolve():raise ValueError('抠像缓存目录不在当前源图范围内')
            receipt_file=output/'receipt.json'
            if sha(receipt_file)!=saved['receiptSha256']:raise ValueError('原片抠像缓存回执哈希不符')
        else:
            folder.mkdir(parents=True,exist_ok=True);input_file=folder/'input.png';source.convert('RGBA').save(input_file)
            output=folder/('r-'+uuid.uuid4().hex[:8]);receipt_file=output/'receipt.json'
            command=[config['python'],'-B','-X','utf8',config['worker'],'--input',str(input_file),'--output-dir',str(output),
                '--device',config['device'],'--size',str(policy['size']),'--threads',str(policy['threads'])]
            # No network or paid request is made by this worker. A timeout is
            # a local failure, preserved for diagnosis rather than hidden.
            with (folder/(output.name+'.log')).open('w',encoding='utf8')as log:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=900)
            if result.returncode or not receipt_file.is_file():raise ValueError('本地高质量抠像失败，诊断已保存；未交付粗选区')
        receipt=json.loads(receipt_file.read_text('utf8'))
        if (receipt.get('sourceRgbSha256')!=hashlib.sha256(rgb.tobytes()).hexdigest()or receipt.get('sourceSize')!=list(source.size)
                or receipt.get('workerSha256')!=policy['workerSha256']or receipt.get('weightSha256')!=policy['weightSha256']
                or receipt.get('sourceRgbPreserved')is not True):raise ValueError('原片抠像回执与实际源图或模型不匹配')
        path=output/'alpha.npy'
        if sha(path)!=receipt['files']['alpha.npy']['sha256']:raise ValueError('原片抠像alpha文件哈希不符')
        alpha=np.load(path,allow_pickle=False).astype('float64')
        if alpha.shape!=(source.height,source.width)or not np.isfinite(alpha).all()or alpha.min()<0 or alpha.max()>1:raise ValueError('原片抠像alpha尺寸或覆盖率无效')
        if not completed.is_file():completed.write_text(json.dumps({'directory':output.name,'receiptSha256':sha(receipt_file)}),'utf8')
        return rgb.astype('float64')/255,alpha,{**receipt,'adapterVersion':VERSION,'sourcePixelSha256':source_hash,
            'sourcePixelsNeverRedrawn':True,'semanticReviewStillRequired':True,'receiptPath':str(receipt_file),'humanReviewed':False}
