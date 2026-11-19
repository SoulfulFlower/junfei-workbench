import io
import unittest
import zipfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from PIL import Image
from openpyxl import load_workbook
import product_table_export as export


class ProductTableTests(unittest.TestCase):
    def setUp(self):
        self.product = {'id':'one', 'sku':'SKU-1', 'name':'测试开衫', 'colorNames':'Red,Blue',
            'sourceImport':{'asin':'B0HQ6T361R', 'market':'US', 'amazon':{
                'title':"Women's Fuzzy & Loose Cardigan", 'referenceImages':['https://m.media-amazon.com/images/I/product.jpg']}}}
        self.state = {'products':[self.product, {'id':'other','name':'Other account text'}],
                      'copy':{'one-US':{'title':'=not_a_formula()'}}}
        buffer = io.BytesIO();Image.new('RGB',(32,48),'red').save(buffer,'PNG');self.png=buffer.getvalue()

    def test_xlsx_contains_embedded_image_asin_and_clickable_original_title_search(self):
        with patch.object(export.image_provider,'jobs',return_value={'jobs':[]}), \
             patch.object(export.image_provider,'remote_reference',return_value=(self.png,'image/png')):
            raw=export.build(self.state,['one'],'http://127.0.0.1:18765')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(len([n for n in archive.namelist() if n.startswith('xl/media/')]),1)
        sheet=load_workbook(io.BytesIO(raw)).active
        self.assertEqual(sheet.max_row,2)
        self.assertEqual(sheet['D2'].value,'B0HQ6T361R')
        self.assertEqual(sheet['D2'].hyperlink.target,'https://www.amazon.com/dp/B0HQ6T361R')
        search=sheet['F2'].hyperlink.target
        self.assertEqual(urlsplit(search).hostname,'www.amazon.com')
        self.assertEqual(parse_qs(urlsplit(search).query)['k'],[self.product['sourceImport']['amazon']['title']])
        self.assertEqual(sheet['Q2'].data_type,'s')
        self.assertEqual(sheet['Q2'].value,'=not_a_formula()')
        self.assertEqual(sheet.freeze_panes,'D2')

    def test_unknown_product_rejected_before_reading_jobs_or_fetching_images(self):
        with patch.object(export.image_provider,'jobs') as jobs:
            with self.assertRaisesRegex(ValueError,'当前账号'):export.build(self.state,['missing'],'http://localhost')
        jobs.assert_not_called()

    def test_missing_picture_and_title_stay_explicit_without_invented_search(self):
        p={'id':'blank','name':'中文名称','sourceImport':{'market':'UK'}}
        with patch.object(export.image_provider,'jobs',return_value={'jobs':[]}):
            raw=export.build({'products':[p]},['blank'],'http://localhost')
        sheet=load_workbook(io.BytesIO(raw)).active
        self.assertIsNone(sheet['D2'].value)
        self.assertIsNone(sheet['F2'].value)
        self.assertEqual(sheet['V2'].value,'缺少产品图片')

    def test_invalid_local_or_remote_image_does_not_expose_files(self):
        with patch.object(export.image_provider,'local_image',side_effect=ValueError('invalid')) as local, \
             patch.object(export.image_provider,'remote_reference',side_effect=ValueError('invalid')) as remote:
            raw,url=export.thumbnail(['/uploads/../private.json','http://127.0.0.1/private'])
        self.assertIsNone(raw)
        self.assertEqual(local.call_count,1);self.assertEqual(remote.call_count,1)


if __name__ == '__main__':unittest.main()
