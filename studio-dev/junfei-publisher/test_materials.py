import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from materials import inspect_folder, read_docx


class MaterialsTests(unittest.TestCase):
    def test_docx_keeps_table_text_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / '产品.docx'
            with ZipFile(file, 'w') as z:
                z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>标题</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>包装重量390g</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
            self.assertEqual(read_docx(file), '标题\n包装重量390g')

    def test_bad_document_does_not_hide_other_materials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '坏.docx').write_bytes(b'invalid')
            (root / '模板.txt').write_text('五点和完整描述', encoding='utf-8')
            (root / 'Black.jpg').write_bytes(b'placeholder')
            (root / 'junfei-output').mkdir()
            (root / 'junfei-output' / 'generated.jpg').write_bytes(b'placeholder')
            result = inspect_folder(root)
            self.assertEqual(len(result['errors']), 1)
            self.assertEqual(result['documents'][0]['text'], '五点和完整描述')
            self.assertEqual(result['images'], ['Black.jpg'])


if __name__ == '__main__':
    unittest.main()
