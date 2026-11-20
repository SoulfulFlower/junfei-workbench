"""Validate CLI deliverables without extracting archives or editing workbench data."""
import csv
import hashlib
import io
import json
from pathlib import PurePosixPath
from pathlib import Path
import re
import zipfile

from PIL import Image

FIELDS = ('title', 'highlights', 'bullets', 'description', 'terms')
IMAGE_LIMIT = 5 * 1024 * 1024
SKU = re.compile(r'[A-Za-z0-9_-]{1,40}')
ASIN = re.compile(r'[A-Z0-9]{10}')


def normalized_listing(value, parent):
    if not isinstance(value, dict) or value.get('sku') != parent:
        raise ValueError('Listing 父 SKU 与冻结交付范围不符')
    result = {key: value.get(key, '') for key in FIELDS}
    bullets = result['bullets']
    if isinstance(bullets, str):
        bullets = [line.strip() for line in bullets.splitlines() if line.strip()]
    if (not isinstance(bullets, list) or len(bullets) != 5
            or any(not isinstance(line, str) or not line.strip() or len(line) > 500 for line in bullets)):
        raise ValueError('Listing 须有五条有效五点，每条至多 500 字符')
    for key, low, high in (('title', 60, 75), ('highlights', 0, 125),
                           ('description', 1, 2000), ('terms', 1, 249)):
        value = result[key]
        if not isinstance(value, str) or len(value.strip()) < low:
            raise ValueError('Listing 字段不完整：' + key)
        if len(value.encode('utf-8') if key == 'terms' else value) > high:
            raise ValueError('Listing 字段超限：' + key)
    return {**result, 'bullets': bullets}


def validate_scope(value, row):
    if (not isinstance(value, dict) or set(value) != {'source_id', 'marketplace', 'parent_sku', 'variants'}
            or value['source_id'] != row['source_id'] or value['marketplace'] != row['market']
            or not isinstance(value['parent_sku'], str) or not SKU.fullmatch(value['parent_sku'])
            or not isinstance(value['variants'], list) or not value['variants']):
        raise ValueError('交付范围须包含本任务的源 ASIN、站点、父 SKU 和已核对的子体')
    seen = set()
    asins = set()
    for variant in value['variants']:
        if (not isinstance(variant, dict) or set(variant) != {'sku', 'source_asin', 'color', 'size', 'color_key'}
                or any(not isinstance(item, str) or not item or item != item.strip() for item in variant.values())
                or not ASIN.fullmatch(variant['source_asin']) or variant['source_asin'] in asins
                or variant['sku'] == value['parent_sku'] or variant['sku'] in seen):
            raise ValueError('交付子体须有唯一子 SKU、源 ASIN、颜色、尺码及颜色键')
        seen.add(variant['sku'])
        asins.add(variant['source_asin'])
    return value


def image_digest(raw):
    if len(raw) >= IMAGE_LIMIT:
        raise ValueError('成品图片必须小于 5MB')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG', 'JPEG') or min(image.size) < 1600:
                raise ValueError('成品图片须为 PNG/JPEG，且宽高至少 1600')
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError('成品图片无法完整解码') from exc
    return hashlib.sha256(raw).hexdigest()


def gallery(scope, rows, count):
    if not isinstance(rows, list):
        raise ValueError('成品须逐色逐图位提交图片清单')
    expected = {(v['color_key'], slot) for v in scope['variants'] for slot in range(count)}
    result = {}
    for item in rows:
        if not isinstance(item, dict) or not isinstance(item.get('colorKey'), str) or type(item.get('slot')) is not int:
            raise ValueError('图片清单颜色或图位无效')
        key = item['colorKey'], item['slot']
        if key not in expected or key in result:
            raise ValueError('图片清单包含越界或重复图位')
        result[key] = item
    if result.keys() != expected:
        raise ValueError('成品须覆盖每个已核对子体颜色的全部图位')
    return result


def validate_images(scope, rows, files, count):
    images = gallery(scope, rows, count)
    paths = [item.get('file') for item in images.values()]
    if any(not isinstance(path, str) for path in paths) or set(paths) != set(files) or len(set(paths)) != len(paths):
        raise ValueError('图片清单与提交的实际文件不一致')
    return [{'colorKey': color, 'slot': slot, 'sha256': image_digest(files[item['file']])}
            for (color, slot), item in images.items()]


def validate_export(path, scope, listing, finished_images, count):
    parent = scope['parent_sku']
    prefix = parent + '/'
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if (len(set(names)) != len(names) or any(
                    not name.startswith(prefix) or '\\' in name or '..' in PurePosixPath(name).parts
                    for name in names)):
                raise ValueError('交付 ZIP 包含重复或无效路径')

            def read(name, limit):
                if archive.getinfo(name).file_size >= limit:
                    raise ValueError('交付文件超限：' + name)
                return archive.read(name)

            exported = json.loads(read(prefix + parent + '-listing.json', 256 * 1024))
            if normalized_listing(exported, parent) != listing:
                raise ValueError('导出文案与已完成文案不一致')
            manifest = json.loads(read(prefix + 'image-manifest.json', 4 * 1024 * 1024))
            if (not isinstance(manifest, dict) or manifest.get('parentSku') != parent
                    or manifest.get('reviewRequired') is not False or manifest.get('missing')
                    or manifest.get('childSkuCount') != len(scope['variants'])
                    or not isinstance(manifest.get('images'), list)):
                raise ValueError('交付清单存在缺项或父子 SKU 不一致')
            if any(not isinstance(item, dict) for item in manifest['images']):
                raise ValueError('交付图片清单格式无效')
            images = gallery(scope, [item for item in manifest['images'] if item.get('kind') == 'gallery'], count)
            hashes = {(item['colorKey'], item['slot']): item['sha256'] for item in finished_images}
            names_seen = set()
            for item in manifest['images']:
                name = item.get('file')
                if not isinstance(name, str) or not name.startswith(prefix) or name in names_seen:
                    raise ValueError('交付图片路径缺失或重复')
                names_seen.add(name)
                raw = read(name, IMAGE_LIMIT)
                digest = image_digest(raw) if item.get('kind') == 'gallery' else hashlib.sha256(raw).hexdigest()
                if digest != item.get('sha256') or (item.get('kind') == 'gallery'
                        and digest != hashes.get((item['colorKey'], item['slot']))):
                    raise ValueError('导出图片哈希与已完成图位不一致')
            variants = list(csv.DictReader(io.StringIO(read(prefix + 'variants.csv', 4 * 1024 * 1024).decode('utf-8-sig'))))
            expected = {v['sku']: v for v in scope['variants']}
            if len(variants) != len(expected) or {v.get('sku') for v in variants} != expected.keys():
                raise ValueError('导出 CSV 的子 SKU 缺失、重复或超出冻结范围')
            for variant in variants:
                original = expected[variant['sku']]
                files = [images[original['color_key'], slot]['file'] for slot in range(count)]
                if (variant.get('parent_sku') != parent or any(variant.get(key) != original[key]
                      for key in ('source_asin', 'color', 'size', 'color_key'))
                        or variant.get('main_image') != files[0] or variant.get('generated_images') != '|'.join(files)
                        or variant.get('image_count') != str(count)):
                    raise ValueError('导出 CSV 的子体身份或图片顺序与冻结范围不符')
    except (KeyError, OSError, zipfile.BadZipFile, UnicodeError, RuntimeError) as exc:
        raise ValueError('交付 ZIP 缺少实际文案、变体清单或可读取图片') from exc


def original_delivery(db, job, stage):
    rows = db.execute("SELECT data FROM events WHERE job_id=? AND stage=? AND action='completed' LIMIT 2",
                      (job, stage)).fetchall()
    if len(rows) != 1:
        raise ValueError('缺少唯一的成品阶段回执：' + stage)
    data = json.loads(rows[0]['data'])
    if not {'listing': {'delivery_scope', 'finished_listing'}, 'images': {'finished_images'},
            'export': {'delivery_scope'}}[stage] <= data.keys():
        raise ValueError('旧成品回执缺少冻结的商品或文件资料，请先核对原交付记录：' + stage)
    return data


def artifact_records(db, row, stage, evidence, paths):
    if stage not in ('listing', 'images', 'export', 'publish'):
        return {}
    if stage == 'publish':
        exported = original_delivery(db, row['id'], 'export')
        return {'delivery_scope': validate_scope(exported['delivery_scope'], row)}
    if stage == 'listing':
        scope = validate_scope(evidence.get('delivery_scope'), row)
        if len(paths) != 1 or paths[0].suffix.lower() != '.json' or paths[0].stat().st_size >= 256 * 1024:
            raise ValueError('文案阶段须提交一份 256 KiB 以内的 Listing JSON')
        listing = json.loads(paths[0].read_text(encoding='utf-8-sig'))
        return {'delivery_scope': scope, 'finished_listing': normalized_listing(listing, scope['parent_sku'])}
    listing = original_delivery(db, row['id'], 'listing')
    scope = validate_scope(listing['delivery_scope'], row)
    count = json.loads(row['config'])['images'].get('gallery_count', 7)
    if type(count) is not int or not 1 <= count <= 9:
        raise ValueError('套图张数配置无效')
    if stage == 'images':
        files = {}
        for path in paths:
            with path.open('rb') as stream:
                files[str(path)] = stream.read(IMAGE_LIMIT)
        return {'finished_images': validate_images(scope, evidence.get('image_slots'), files, count)}
    images = original_delivery(db, row['id'], 'images')
    if len(paths) != 1 or paths[0].suffix.lower() != '.zip':
        raise ValueError('导出阶段须提交一份完整的工作台格式 ZIP')
    validate_export(paths[0], scope, listing['finished_listing'], images['finished_images'], count)
    return {'delivery_scope': scope}
