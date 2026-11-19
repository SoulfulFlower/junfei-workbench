"""Read-only team catalog and copy-on-claim into a private workspace."""
import json
import io
import re
import shutil
import sqlite3
from contextlib import closing
from urllib.parse import urlsplit, urlunsplit
from PIL import Image, ImageOps, UnidentifiedImageError

import app_paths
import asin_reference
import product_archive
import product_sku


FILENAME = 'shared-product-library.sqlite3'
FACTS = ('name','cat','style','material','features','dimensions','packageDimensions','packageWeight',
         'productWeight','packageContents','colorNames','sizeNames','targetAudience','market','brand','manufacturer','sourceUrl','purchasePrice')
ASSET = re.compile(r'/uploads/([a-f0-9]{32}\.(?:png|jpg|webp))')
ASIN = re.compile(r'[A-Z0-9]{10}')


def discovery_research(product):
    selection = product.get('selectionResearch') or {}
    if selection.get('sourceMonth') != 'cyclic-discovery':
        return {}
    return selection


def asin_cover(reference):
    images = reference.get('referenceImages') or []
    return images[0] if images and asin_reference.media_key(images[0]) else ''


def discovery_snapshot(product):
    selection = discovery_research(product)
    if not selection:
        return {}
    reference = selection['reference']
    market, asin = reference['market'], reference['asin']
    competitors = selection.get('rankedCompetitors') or []
    parents = {row['parent_asin'] for row in competitors}
    asins = [row['asin'] for row in competitors]
    if not 3 <= len(asins) == len(parents) == len(set(asins)) <= 5:
        raise ValueError('循环选品须核实 3–5 个不同父体且有销售排名的竞品 ASIN')
    captured = product.get('editorAsinReference') or {}
    if (captured.get('asin') != asin or captured.get('market') != market
            or not captured.get('title') or not asin_cover(captured)):
        raise ValueError('请先采集本款 ASIN 的商品资料及主图')
    keywords = (product.get('competitorResearch') or {}).get(market) or {}
    reviews = (product.get('reviewResearch') or {}).get(market) or {}
    if (keywords.get('source') != 'sellersprite' or not keywords.get('keywords')
            or set(re.findall(ASIN, keywords.get('input') or '')) != set(asins)):
        raise ValueError('请先用已核实的竞品 ASIN 获取卖家精灵关键词')
    if (not reviews.get('samples') or not reviews.get('analysis')
            or set(re.findall(ASIN, reviews.get('input') or '')) != set(asins)):
        raise ValueError('请先获取并分析这批竞品 ASIN 的买家评论')
    extra = reviews.get('supplement')
    if extra is not None:
        from discovery_review import original_empty
        original_sources = [source for source in reviews['sources'] if source.get('asin') in asins]
        if (not original_empty({**reviews, 'samples': [], 'sources': original_sources}, market, asins)
                or extra.get('asin') in {asin, *asins} or extra.get('parentAsin') in {asin, captured.get('parentAsin'), *parents}
                or extra.get('market') != market or not extra.get('structureEvidence')
                or type(extra.get('rank')) is not int or extra['rank'] <= 0
                or not ASIN.fullmatch(extra.get('parentAsin') or '')
                or not ASIN.fullmatch(extra.get('asin') or '')
                or any(row.get('asin') != extra['asin'] or not str(row.get('text') or '').strip() for row in reviews['samples'])):
            raise ValueError('补充评论来源与原竞品或评论正文不匹配，请重新采集')
    return {
        'editorAsinReference': {key: captured[key] for key in (
            'asin','selectedAsin','parentAsin','market','url','title','bullets','description',
            'brand','referenceImages','variants','colors','capturedAt'
        ) if key in captured},
        'selectionResearch': {'sourceMonth': selection['sourceMonth'], 'reference': reference,
                              'rankedCompetitors': competitors},
        'competitorResearch': {market: {key: value for key, value in keywords.items() if key != 'reviewReport'}},
        'reviewResearch': {market: reviews},
    }


def seed(root):
    """Take a product-facts snapshot without modifying the source workspace."""
    if (root/FILENAME).exists():
        raise ValueError('共享产品库已经存在')
    with closing(sqlite3.connect((root/'studio.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
        row=db.execute('SELECT body FROM workspace WHERE id=1').fetchone()
    products=json.loads(row[0]).get('products',[]) if row else []
    with closing(connect(root)) as db, db:
        for p in products:
            add(db,root,p,root/'uploads')
    return len(products)


def connect(root):
    db=sqlite3.connect(root/FILENAME,timeout=30)
    db.execute('CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    return db


def copy_asset(source,destination):
    if source==destination:
        return
    if destination.is_symlink():
        raise ValueError('素材路径不受支持')
    if not destination.exists():
        shutil.copyfile(source,destination)
    elif source.read_bytes()!=destination.read_bytes():
        raise ValueError('素材中存在不同内容的同名文件')


def snapshot(root,product,uploads):
    source_id=product.get('librarySourceId') or product['id']
    item={key:product[key] for key in FACTS if isinstance(product.get(key),str)}
    if isinstance(product.get('erpDraftPricing'),dict):
        # Factual pricing only. Do not copy another account's CLI execution IDs.
        item['erpDraftPricing']=json.loads(json.dumps(product['erpDraftPricing']))
    url=urlsplit(item.get('sourceUrl',''))
    item['sourceUrl']=urlunsplit((url.scheme,url.netloc,url.path,'','')) if (
        url.scheme=='https' and url.hostname and not url.username and not url.password
    ) else ''
    supplier=(product.get('sourceImport') or {}).get('supplier') or {}
    if item['sourceUrl'] and isinstance(supplier,dict):
        item['supplierInfo']={key:supplier[key] for key in ('title','shop') if isinstance(supplier.get(key),str)}
    item.update(id=source_id,colors=product.get('colors',1),sizes=product.get('sizes',1),
                color=product.get('color') or '#a6b39a',assets=[])
    target=root/'shared-library-assets'
    for asset in product.get('assets',[]):
        if not isinstance(asset,dict) or asset.get('source') not in (
            '产品实拍','实拍图','供应商图','1688 采集图','1688采集图','1688货源采集','1688'
        ):
            continue
        match=ASSET.fullmatch(asset.get('url') or '')
        if not match:
            continue
        source=uploads/match[1]
        if source.is_file() and not source.is_symlink():
            target.mkdir(exist_ok=True)
            copy_asset(source,target/source.name)
            item['assets'].append({key:asset[key] for key in ('url','name','source','color')
                                   if isinstance(asset.get(key),str)})
    return item


def add(db,root,product,uploads,prepared=None):
    source_id=product.get('librarySourceId') or product['id']
    if db.execute('SELECT 1 FROM products WHERE id=?',(source_id,)).fetchone():
        return False
    item=snapshot(root,product,uploads)
    item.update(prepared or {})
    db.execute('INSERT INTO products VALUES(?,?)',(source_id,json.dumps(item,ensure_ascii=False)))
    return True


def add_product(product,uploads):
    root=app_paths.LIBRARY_ROOT
    with closing(connect(root)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if any(claim_id({'products':[product]},source_id)
               for source_id, in db.execute('SELECT id FROM products')):
            return False
        return add(db,root,product,uploads,discovery_snapshot(product))


def items():
    path=app_paths.LIBRARY_ROOT / FILENAME
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        return [json.loads(body) for body, in db.execute('SELECT body FROM products ORDER BY rowid DESC')]


def media(asset):
    match=ASSET.fullmatch(asset.get('url',''))
    if match:
        file=app_paths.LIBRARY_ROOT/'shared-library-assets'/match[1]
        if file.is_file() and not file.is_symlink():
            return file
    return None


def first_photo(product):
    for asset in product.get('assets',[]):
        path=media(asset)
        if path is not None:
            return path
    return None


def photo(source_id, thumbnail=False):
    if not source_id:
        return None
    library=app_paths.LIBRARY_ROOT/FILENAME
    if not library.is_file():
        return None
    with closing(sqlite3.connect(library.as_uri()+'?mode=ro',uri=True)) as db:
        row=db.execute('SELECT body FROM products WHERE id=?',(source_id,)).fetchone()
    path=first_photo(json.loads(row[0])) if row else None
    if path is None:
        return None
    if not thumbnail:
        return path.read_bytes(),{'.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'}[path.suffix]
    try:
        with Image.open(path) as original:
            image=ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((200,200),Image.Resampling.LANCZOS)
            output=io.BytesIO()
            image.save(output,format='JPEG',quality=83)
            return output.getvalue(),'image/jpeg'
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def claim_id(workspace, source_id):
    match=re.fullmatch(r'IMP-([A-Z]{2})-([A-Z0-9]{10})',source_id)
    return next((p['id'] for p in workspace.get('products',[]) if p.get('id')==source_id
                 or p.get('librarySourceId')==source_id
                 or (match and product_archive.matches(p,*match.groups()))),None)


def deleted_id(workspace,source_id):
    return claim_id({'products':[row.get('product') or {} for row in workspace.get('deletedProducts',[])]},
                    source_id)


def catalog(workspace, can_add=False):
    rows,existing=[],[]
    for p in items():
        personal_id=claim_id(workspace,p['id']) or deleted_id(workspace,p['id'])
        if personal_id:
            existing.append(personal_id)
        else:
            rows.append({**{key:p.get(key,'') for key in ('id',*FACTS)},
                         'supplierInfo':p.get('supplierInfo',{}),'hasPhoto':first_photo(p) is not None,
                         'asinCoverUrl':asin_cover(p.get('editorAsinReference') or {})})
    result={'products':rows,'canAdd':can_add,'claimedCount':len(existing)}
    if can_add:
        result['sharedPersonalIds']=existing
    return result


def claim(workspace,user,source_id,uploads):
    item=next((p for p in items() if p['id']==source_id),None)
    if item is None:
        raise ValueError('共享产品不存在')
    existing=claim_id(workspace,source_id)
    if existing:
        return existing,False
    if deleted_id(workspace,source_id):
        raise ValueError('此产品在个人档案的回收站，请先恢复原档案')
    product={**item,'librarySourceId':source_id,'owner':user['name'],'status':'待补资料','assets':[]}
    supplier=product.pop('supplierInfo',{})
    reference=re.fullmatch(r'IMP-([A-Z]{2})-([A-Z0-9]{10})',source_id)
    if reference or product.get('sourceUrl'):
        product['sourceImport']={'market':product.get('market') or (reference[1] if reference else ''),
                                 'asin':reference[2] if reference else '',
                                 'supplier':{**supplier,'url':product.get('sourceUrl','')}}
    uploads.mkdir(parents=True,exist_ok=True)
    for asset in item.get('assets',[]):
        source=media(asset)
        if source is None:
            continue
        copy_asset(source,uploads/source.name)
        product['assets'].append(asset)
    products=workspace.setdefault('products',[])
    product_sku.ensure(product,user,{p.get('sku') for p in products if p.get('sku')})
    products.insert(0,product)
    return product['id'],True
