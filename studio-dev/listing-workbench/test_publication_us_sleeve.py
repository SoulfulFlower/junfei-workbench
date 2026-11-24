"""Bound supplier-photo amendments never touch external saves or publications."""
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import publication_flow as flow


class SleeveAmendmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name);self.folder = self.root/'job';self.folder.mkdir()
        for name,value in [('DATA',self.root),('WORKER_USER',2)]:
            p=patch.object(flow.app_paths,name,value);p.start();self.addCleanup(p.stop)
        self.raw=b'isolated bound supplier photograph'
        sha=hashlib.sha256(self.raw).hexdigest();url='https://detail.1688.com/offer/12345.html'
        self.evidence={'value':'Cuff Sleeve','sourceUrl':url,'referenceImage':'/uploads/supplier.jpg',
                       'referenceSha256':sha,'observations':'Actual supply photo shows a smooth wrist cuff band.'}
        self.product={'id':'P','sourceUrl':url,'sourceImport':{'supplier':{'url':url}},
                      'assets':[{'url':'/uploads/supplier.jpg','source':'供应商图','sha256':sha}]}
        with closing(sqlite3.connect(self.root/'studio.sqlite3')) as db, db:
            db.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,body TEXT)')
            db.execute('INSERT INTO workspace VALUES(1,?)',(json.dumps({'products':[self.product]}),))
        self.packet={'input':{'sha256':'original-sha','goods':{'sourceUrl':url},
                            'publicationFacts':{'supplierModelNumberEvidence':{'sourceUrl':url}}}}
        self.job={'id':'original-job','productId':'P','accountId':2}
        self.receipt={'jobId':'original-job','productId':'P','accountId':2,'snapshotSha256':'original-sha',
                      'phase':'us_preparation','error':'Missing sleeve type',
                      'usPrepare':{'schemaObservation':{'country_code':'US','product_type_name':'SHIRT'}}}
        self.write_receipt()
        p=patch('image_provider.local_image',return_value=self.raw);self.image=p.start();self.addCleanup(p.stop)

    def write_receipt(self):
        (self.folder/'receipt.json').write_text(json.dumps(self.receipt),encoding='utf-8')

    def append(self,evidence=None):
        flow._append_us_sleeve_type(2,self.job,self.folder,self.packet,evidence or self.evidence)

    def test_amendment_preserves_original_input_and_marks_agent_provenance(self):
        original=copy.deepcopy(self.packet);self.append()
        amended=json.loads((self.folder/'input.json').read_text('utf-8'))
        fact=amended['input']['usPreparation']['sleeveType']
        self.assertEqual(self.packet,original);self.assertEqual(amended['input']['sha256'],'original-sha')
        self.assertEqual(fact['reviewerType'],'agent');self.assertIs(fact['humanReviewed'],False)
        self.assertEqual(len(list((self.folder/'amendments').glob('*.json'))),1)
        flow._append_us_sleeve_type(2,self.job,self.folder,amended,self.evidence)
        self.assertEqual(len(list((self.folder/'amendments').glob('*.json'))),1)

    def test_foreign_evidence_or_reference_bytes_cannot_be_frozen(self):
        for field,value in [('sourceUrl','https://detail.1688.com/offer/999.html'),('value','Ribbed Cuff'),
                            ('referenceImage','/uploads/other.jpg'),('referenceSha256','0'*64)]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.append({**self.evidence,field:value})
        self.image.return_value=b'changed'
        with self.assertRaises(ValueError):self.append()
        self.assertFalse((self.folder/'input.json').exists())

    def test_saved_or_published_and_foreign_receipts_are_never_amended(self):
        original=copy.deepcopy(self.receipt)
        mutations=[lambda r:r.update(accountId=3),lambda r:r.update(productId='other'),
                   lambda r:r.update(usPublish={'publishId':'real-original'}),
                   lambda r:r['usPrepare'].update(saveIntendedAt='already-intended'),
                   lambda r:r['usPrepare'].update(requestSent=True),
                   lambda r:r['usPrepare'].update(submitted={'id':'existing'})]
        for change in mutations:
            self.receipt=copy.deepcopy(original);change(self.receipt);self.write_receipt()
            with self.assertRaises(ValueError):self.append()
        self.assertFalse((self.folder/'input.json').exists())


if __name__=='__main__':unittest.main()
