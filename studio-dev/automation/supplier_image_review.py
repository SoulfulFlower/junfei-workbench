"""Download images already observed by the supplier queue and make review sheets.

Never requests supplier detail HTML, cookies or a browser session.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from PIL import Image, ImageDraw


def review(capture, output):
    raw = json.loads(Path(capture).read_text(encoding='utf-8-sig'))
    supplier = raw.get('body', raw)['supplier']
    if supplier.get('captureMethod') != 'ego-serial-browser':
        raise ValueError('仅处理正式供应商队列已采集的图片观察')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    observations = [(index, item) for index, item in enumerate(supplier['imageObservations'])
                    if item.get('origin') == 'supplier_detail' or item.get('width', 0) >= 700]

    def read(item):
        index, observation = item
        url = observation['url']
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'cbu01.alicdn.com' or
                not parsed.path.startswith('/img/ibank/')):
            raise ValueError('图片地址不在已观察的供应商图片CDN')
        record = {'index': index, 'url': url, 'origin': observation.get('origin')}
        try:
            with urlopen(url, timeout=25) as response:
                if urlsplit(response.url).netloc != parsed.netloc:
                    raise ValueError('图片重定向离开原CDN')
                data = response.read(12_000_001)
            if len(data) > 12_000_000:
                raise ValueError('图片过大')
            image = Image.open(io.BytesIO(data))
            image.load()
            extension = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}.get(image.format)
            if not extension:
                raise ValueError('未支持的图片格式')
            file = output / (f'{index:02d}' + extension)
            file.write_bytes(data)
            record.update(path=str(file), width=image.width, height=image.height,
                          sha256=hashlib.sha256(data).hexdigest(), visuallyReviewed=False)
        except Exception as error:
            record['error'] = str(error)
        return record

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(read, observations))
    valid = [record for record in records if 'path' in record]
    sheets = []
    for start in range(0, len(valid), 16):
        chunk = valid[start:start+16]
        sheet = Image.new('RGB', (1600, 450 * ((len(chunk)+3)//4)), (235, 235, 235))
        draw = ImageDraw.Draw(sheet)
        for index, record in enumerate(chunk):
            image = Image.open(record['path']).convert('RGB')
            image.thumbnail((390, 418))
            x, y = index % 4 * 400, index // 4 * 450
            sheet.paste(image, (x, y+25))
            draw.text((x+4, y+4), f"{record['index']} {record['width']}x{record['height']}", fill='black')
        file = output / f'review-{start//16+1}.jpg'
        sheet.save(file)
        sheets.append(str(file))
    report = {'sourceCapture': str(Path(capture).resolve()), 'sourceUrl': supplier['url'],
              'capturedAt': supplier['capturedAt'], 'supplierDetailRequests': 0,
              'images': records, 'reviewSheets': sheets, 'productionApproved': False}
    (output / 'images.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'downloaded': len(valid), 'errors': len(records)-len(valid), 'reviewSheets': sheets}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(review(args.capture, args.output_dir), ensure_ascii=False))
