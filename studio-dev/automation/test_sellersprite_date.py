import tempfile
import unittest
from datetime import date
from pathlib import Path
import openpyxl
from sellersprite_date import export_source, validate_export_source


class SellerSpriteExportDateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'original.xlsx'
        self.asin = 'B000000093'
        self.today = date.today()
        self.book = openpyxl.Workbook()
        s = self.book.active
        s.title = 'US'
        s.append(['ASIN','上架时间','商品标题','商品详情页链接'])
        s.append([self.asin,self.today.isoformat(),'Example product','https://www.amazon.com/dp/'+self.asin])
        s.append(['B000000094',None,'Other variant','https://www.amazon.com/dp/B000000094'])
        self.book.create_sheet('Note').append(['卖家精灵官网：https://www.sellersprite.com'])
        self.book.save(self.path)

    def tearDown(self):
        self.book.close()
        self.temp.cleanup()

    def source(self):
        return export_source(self.path,'US',self.asin,self.today.isoformat())

    def test_original_exact_asin_date_is_verified(self):
        self.assertTrue(validate_export_source(self.source(),'US',self.asin,self.today,'www.amazon.com'))

    def test_unreadable_export_fails_closed(self):
        self.path.write_bytes(b'not an xlsx file')
        with self.assertRaises(ValueError):
            self.source()

    def test_other_child_cannot_borrow_date(self):
        with self.assertRaises(ValueError):
            export_source(self.path,'US','B000000094',self.today.isoformat())

    def test_source_identity_row_and_transcript_cannot_be_swapped(self):
        good = self.source()
        for change in ({'artifact_sha256':'0'*64},{'row':3},{'sheet':'UK'},
                       {'url':'https://www.amazon.com/dp/B000000094'},
                       {'raw':good['raw']+'\n上架时间: 2000-01-01'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_export_source({**good,**change},'US',self.asin,self.today,'www.amazon.com')
        self.assertFalse(validate_export_source({**good,'tool':'Other'},'US',self.asin,self.today,'www.amazon.com'))

    def test_modified_original_and_duplicate_asin_are_rejected(self):
        good = self.source()
        self.book['US'].cell(2,3).value = 'Changed product'
        self.book.save(self.path)
        with self.assertRaises(ValueError):
            validate_export_source(good,'US',self.asin,self.today,'www.amazon.com')
        self.book['US'].append([self.asin,self.today.isoformat(),'Duplicate','https://www.amazon.com/dp/'+self.asin])
        self.book.save(self.path)
        with self.assertRaises(ValueError):
            self.source()

    def test_missing_source_note_or_date_header_is_rejected(self):
        del self.book['Note']
        self.book.save(self.path)
        with self.assertRaises(ValueError):
            self.source()
        self.book.create_sheet('Note').append(['卖家精灵官网：https://www.sellersprite.com'])
        self.book['US'].cell(1,2).value = 'Date First Available'
        self.book.save(self.path)
        with self.assertRaises(ValueError):
            self.source()
