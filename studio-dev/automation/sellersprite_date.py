"""Verify the original SellerSprite extension list export, without inferring dates."""
import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import BadZipFile


def export_row(path, market, asin):
    import openpyxl
    path = Path(path)
    if not path.is_absolute() or path.suffix.lower() != '.xlsx' or not path.is_file() or path.stat().st_size > 25_000_000:
        raise ValueError('需要原始SellerSprite XLSX导出文件')
    try:
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (BadZipFile, openpyxl.utils.exceptions.InvalidFileException, KeyError, OSError) as exc:
        raise ValueError('SellerSprite导出原件无法解析') from exc
    try:
        if market not in book.sheetnames or 'Note' not in book.sheetnames:
            raise ValueError('导出站点或来源说明缺失')
        notes = '\n'.join(str(row[0]) for row in book['Note'].iter_rows(values_only=True) if row and row[0])
        if '卖家精灵官网：https://www.sellersprite.com' not in notes:
            raise ValueError('不是可识别的SellerSprite原始导出')
        sheet = book[market]
        if sheet.max_row > 100_000 or sheet.max_column > 500:
            raise ValueError('导出表超出证据读取范围')
        headers = list(next(sheet.iter_rows(min_row=1, max_row=1, values_only=True)))
        required = ('ASIN', '上架时间', '商品标题', '商品详情页链接')
        if any(headers.count(h) != 1 for h in required):
            raise ValueError('导出缺少唯一ASIN和上架时间列')
        matches = []
        for number, cells in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
            if cells[headers.index('ASIN')] == asin:
                matches.append((number, dict(zip(headers, cells))))
        if len(matches) != 1:
            raise ValueError('ASIN在导出中不存在或不唯一，不借用父体或其它子体日期')
        number, row = matches[0]
        value = row['上架时间']
        if isinstance(value, datetime):
            value = value.date().isoformat()
        elif isinstance(value, date):
            value = value.isoformat()
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('该ASIN导出行没有明确上架日期')
        date.fromisoformat(value)
        if not isinstance(row['商品标题'], str) or not row['商品标题'].strip():
            raise ValueError('导出商品标题缺失')
        return number, row, value
    finally:
        book.close()


def export_source(path, market, asin, checked_at):
    path = Path(path).resolve()
    number, row, value = export_row(path, market, asin)
    return {'url': row['商品详情页链接'], 'checked_at': checked_at,
            'raw': 'ASIN: '+asin+'\n商品标题: '+row['商品标题']+'\n上架时间: '+value,
            'capture_type': 'sellersprite_extension_export', 'tool': 'SellerSprite', 'asin': asin,
            'artifact': str(path), 'artifact_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'sheet': market, 'row': number, 'listing_date': value}


def validate_export_source(source, market, asin, listed, expected_host):
    if source.get('capture_type') != 'sellersprite_extension_export' or source.get('tool') != 'SellerSprite' or source.get('asin') != asin:
        return False
    path = Path(source.get('artifact', ''))
    number, row, value = export_row(path, market, asin)
    if source.get('artifact_sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError('导出原件哈希不匹配')
    if source.get('sheet') != market or type(source.get('row')) is not int or source['row'] != number or value != listed.isoformat():
        raise ValueError('导出ASIN行、站点或日期不匹配')
    for address in (source.get('url', ''), row['商品详情页链接']):
        url = urlsplit(address)
        if url.scheme != 'https' or url.hostname != expected_host or url.path != '/dp/'+asin or url.username or url.password or url.port not in (None, 443):
            raise ValueError('导出商品链接与当前ASIN不匹配')
    if source.get('raw') != 'ASIN: '+asin+'\n商品标题: '+row['商品标题']+'\n上架时间: '+value:
        raise ValueError('日期转录与原始导出行不一致')
    return True
