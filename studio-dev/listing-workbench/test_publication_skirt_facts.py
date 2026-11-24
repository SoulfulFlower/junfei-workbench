import copy
import json
import tempfile
import unittest
from pathlib import Path
import publication_skirt_facts as module


class SkirtFactsTests(unittest.TestCase):
    def fixture(self):
        url='https://detail.1688.com/offer/123.html'
        source={'accountId':1,'jobId':'job','productId':'p','sha256':'digest','goods':{'sourceUrl':url},
                'publicationFacts':{'supplierModelNumber':'K1','supplierModelNumberEvidence':{'sourceUrl':url}}}
        product={'id':'p','sourceUrl':url,'sourceImport':{'supplier':{'url':url,'title':'高腰蕾丝半身短裙',
                 'retrievedAt':'2026-11-21','attributes':{'货号':'K1','图案':'纯色'}}}}
        receipt={'accountId':1,'jobId':'job','productId':'p','snapshotSha256':'digest','phase':'us_preparation',
                 'usPublish':{},'usPrepare':{'schemaObservation':{'country_code':'US','product_type_name':'SKIRT'}}}
        return source,product,receipt

    def test_only_observed_same_supplier_facts_are_derived(self):
        source,product,_=self.fixture();fact=module.derive(product,source)
        self.assertEqual(fact['rise']['value'],'High Rise');self.assertEqual(fact['pattern']['value'],'Solid')
        self.assertFalse(fact['humanReviewed']);self.assertNotIn('skirtFacts',source)

    def test_unknown_conflicting_or_foreign_supplier_blocks(self):
        source,product,_=self.fixture()
        for edit in [lambda p:p.update(id='foreign'),lambda p:p.update(sourceUrl='other'),
                     lambda p:p['sourceImport']['supplier'].update(title='高腰中腰'),
                     lambda p:p['sourceImport']['supplier'].update(title='短裙'),
                     lambda p:p['sourceImport']['supplier']['attributes'].update(图案='未知'),
                     lambda p:p['sourceImport']['supplier']['attributes'].update(货号='foreign')]:
            changed=copy.deepcopy(product);edit(changed)
            with self.assertRaises(ValueError):module.derive(changed,source)

    def test_append_preserves_original_and_is_idempotent(self):
        source,product,receipt=self.fixture();packet={'input':source};original=copy.deepcopy(packet)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'receipt.json').write_text(json.dumps(receipt),'utf-8')
            job={'id':'job','accountId':1,'productId':'p'}
            def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),'utf-8')
            module.append(1,job,folder,packet,product,write)
            amended=json.loads((folder/'input.json').read_text('utf-8'));module.append(1,job,folder,amended,product,write)
            self.assertEqual(packet,original);self.assertEqual(len(job['amendments']),1)
            archive=json.loads(next((folder/'amendments').glob('*.json')).read_text('utf-8'))
            self.assertEqual(archive['previousInput'],original)

    def test_other_account_or_already_saved_or_published_blocks(self):
        source,product,receipt=self.fixture()
        edits=[lambda r:r.update(accountId=2),lambda r:r.update(usPublish={'publishId':'10'}),
               lambda r:r['usPrepare'].update(preparedInput={'frozen':True}),
               lambda r:r['usPrepare'].update(requestSent=True),
               lambda r:r['usPrepare']['schemaObservation'].update(product_type_name='PANTS')]
        for edit in edits:
            changed=copy.deepcopy(receipt);edit(changed)
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);(folder/'receipt.json').write_text(json.dumps(changed),'utf-8')
                with self.assertRaises(ValueError):module.append(1,{'id':'job','accountId':1,'productId':'p'},folder,{'input':source},product,lambda *a:None)


if __name__=='__main__':unittest.main()
