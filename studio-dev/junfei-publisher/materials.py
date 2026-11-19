"""只读取原始文案与图片清单，不推断颜色、重量或库存。"""
from pathlib import Path
import json
import zipfile
import xml.etree.ElementTree as ET

IMAGE_TYPES = {'.jpg', '.jpeg', '.png', '.webp'}


def read_docx(path):
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        item = archive.getinfo('word/document.xml')
        if item.file_size > 20_000_000:
            raise ValueError('Word 正文过大，请拆分产品资料')
        root = ET.fromstring(archive.read(item))
    return '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in root.findall('.//w:p', ns))


def inspect_folder(folder):
    folder = Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('请选择产品文件夹')
    files = sorted((p for p in folder.rglob('*') if p.is_file() and not p.is_symlink() and 'junfei-output' not in p.relative_to(folder).parts), key=lambda p: str(p).lower())
    result = {'folder': str(folder), 'documents': [], 'images': [], 'productFiles': [], 'errors': []}
    for file in files:
        relative = str(file.relative_to(folder))
        try:
            suffix = file.suffix.lower()
            if suffix in IMAGE_TYPES:
                result['images'].append(relative)
            elif suffix in {'.docx', '.txt', '.md'} and not file.name.startswith('~$'):
                content = read_docx(file) if suffix == '.docx' else file.read_text(encoding='utf-8-sig')
                result['documents'].append({'file': relative, 'text': content})
            elif suffix == '.json':
                data = json.loads(file.read_text(encoding='utf-8-sig'))
                if isinstance(data, list) and data and all(isinstance(p, dict) and 'variants' in p for p in data):
                    result['productFiles'].append(str(file))
        except Exception as error:
            result['errors'].append(f'{relative}: {error}')
    return result
