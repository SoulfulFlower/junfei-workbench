"""Account-scoped product XLSX export, with embedded previews and source links."""
import io
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

from PIL import Image, ImageOps
from openpyxl import Workbook
from openpyxl.drawing.image import Image as SheetImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import image_provider

DOMAINS = {'US':'amazon.com', 'UK':'amazon.co.uk', 'GB':'amazon.co.uk',
           'DE':'amazon.de', 'FR':'amazon.fr', 'IT':'amazon.it', 'ES':'amazon.es',
           'CA':'amazon.ca', 'JP':'amazon.co.jp', 'AU':'amazon.com.au'}
MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
HEADERS = ['产品图片','产品SKU','产品名称','ASIN','亚马逊原始标题','亚马逊标题搜索链接',
           '货源链接','图片链接','站点','状态','颜色','尺码/规格','材质','尺寸','包装内容',
           '关键词','Listing标题','五点描述','详情描述','后台搜索词','来源记录ID','图片提示']


def text(value):
    if isinstance(value, list):
        value = '；'.join(str(v) for v in value)
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value or ''))[:32767]


def source_fields(product):
    source = product.get('sourceImport') or {}
    amazon = source.get('amazon') or {}
    asin = text(source.get('asin') or amazon.get('asin') or product.get('asin')).strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{10}', asin):
        asin = ''
    title = text(amazon.get('title')).strip()
    market = text(source.get('market') or product.get('market') or 'US').upper()
    domain = DOMAINS.get(market)
    search = 'https://www.'+domain+'/s?'+urlencode({'k':title}) if title and domain else ''
    return asin, title, market, search


def image_candidates(product, jobs):
    candidates = []
    selected = (product.get('generatedGallerySelection') or {}).get('items') or []
    for item in selected[:1]:
        job = jobs.get(item.get('jobId'))
        index = item.get('imageIndex', 0)
        if job and job.get('productId') == product['id'] and job.get('status') == 'completed':
            urls = job.get('images') or []
            if type(index) is int and 0 <= index < len(urls):
                candidates.append(urls[index])
    candidates.extend(a.get('url') for a in product.get('assets', []) if isinstance(a, dict))
    source = product.get('sourceImport') or {}
    for name, field in [('amazon','referenceImages'), ('supplier','images')]:
        candidates.extend((source.get(name) or {}).get(field) or [])
    return list(dict.fromkeys(u for u in candidates if isinstance(u, str) and u))


def thumbnail(urls):
    for url in urls[:3]:
        try:
            raw = image_provider.local_image(url) if url.startswith('/uploads/') else image_provider.remote_reference(url)[0]
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > 40_000_000:
                    continue
                source = ImageOps.exif_transpose(source).convert('RGBA')
                source.thumbnail((112,112), Image.Resampling.LANCZOS)
                picture = Image.new('RGB', (112,112), 'white')
                picture.paste(source, ((112-source.width)//2, (112-source.height)//2), source)
                buffer = io.BytesIO()
                picture.save(buffer, format='PNG')
                return buffer.getvalue(), url
        except Exception:
            continue
    return None, urls[0] if urls else ''


def build(state, ids, origin):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 200 or any(not isinstance(v,str) for v in ids):
        raise ValueError('请选择1–200款产品导出')
    ids = list(dict.fromkeys(ids))
    products = {p['id']:p for p in state.get('products', [])}
    if any(pid not in products for pid in ids):
        raise ValueError('所选产品不属于当前账号或已删除，请刷新后重新选择')
    selected = [products[pid] for pid in ids]
    jobs = {j['id']:j for j in image_provider.jobs()['jobs']}
    candidates = [image_candidates(p, jobs) for p in selected]
    with ThreadPoolExecutor(max_workers=4) as pool:
        pictures = list(pool.map(thumbnail, candidates))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '产品库'
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(name='Microsoft YaHei', bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='203F6A')
        cell.alignment = Alignment(vertical='center')
    sheet.row_dimensions[1].height = 28
    for row, (p, (preview, image_url)) in enumerate(zip(selected, pictures), 2):
        asin, title, market, search = source_fields(p)
        copy = state.get('copy', {}).get(p['id']+'-'+market) or {}
        supplier = (p.get('sourceImport') or {}).get('supplier') or {}
        image_link = origin+image_url if image_url.startswith('/uploads/') else image_url
        values = ['',p.get('sku'),p.get('name'),asin,title,search,supplier.get('url') or p.get('sourceUrl'),
                  image_link,market,p.get('status'),p.get('colorNames'),p.get('sizeNames'),p.get('material'),
                  p.get('dimensions'),p.get('packageContents'),p.get('keywords'),copy.get('title'),
                  copy.get('bullets'),copy.get('description'),copy.get('terms'),p['id'],
                  '已嵌入缩略图' if preview else '图片未加载，请查看图片链接' if image_link else '缺少产品图片']
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row, column, text(value))
            cell.data_type = 's'  # Product text beginning with '=' must never become a formula.
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            cell.font = Font(name='Microsoft YaHei', size=10)
            if column in (4,6,7,8) and value:
                target = 'https://www.'+DOMAINS[market]+'/dp/'+asin if column == 4 and market in DOMAINS else value
                if isinstance(target,str) and target.startswith(('https://','http://')):
                    cell.hyperlink = target
                    cell.style = 'Hyperlink'
        sheet.row_dimensions[row].height = 88
        if preview:
            image = SheetImage(io.BytesIO(preview))
            sheet.add_image(image, 'A'+str(row))
    widths = [17,23,32,16,48,35,35,35,10,14,28,25,28,28,28,35,48,48,48,35,25,30]
    for column, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.freeze_panes = 'D2'
    sheet.auto_filter.ref = sheet.dimensions
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
