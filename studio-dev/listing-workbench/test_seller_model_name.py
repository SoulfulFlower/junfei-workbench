import copy
import unittest
from publication_inputs import publication_facts


class SellerModelNameTest(unittest.TestCase):
    def fixture(self):
        p = {'id':'isolated-coat', 'sku':'TEST-PARENT-1', 'cat':'服装',
             'sourceUrl':'https://detail.1688.com/offer/123.html',
             'sourceImport':{'supplier':{'url':'https://detail.1688.com/offer/123.html', 'attributes':{}}}}
        p['publicationAttributeDefaults'] = {'modelName':{
            'value':p['sku'], 'productId':p['id'], 'source':'user_configured_defaults',
            'scope':'missing_catalogue_attribute_only', 'supplierVerified':False,
            'configuredAt':'2026-11-21T14:00:00+00:00', 'instruction':'Isolated seller assignment'}}
        return p

    def test_seller_assignment_is_separate_from_supplier_number_and_immutable(self):
        p=self.fixture();before=copy.deepcopy(p);f=publication_facts(p)
        self.assertEqual(f['modelName'],p['sku'])
        self.assertEqual(f['modelNameEvidence']['assignment'],'seller_parent_sku')
        self.assertFalse(f['modelNameEvidence']['supplierVerified'])
        self.assertNotIn('supplierModelNumber',f)
        self.assertNotIn('supplierModelNumberEvidence',f)
        self.assertEqual(p,before)

    def test_no_implicit_assignment_or_cross_product_authority(self):
        p=self.fixture();del p['publicationAttributeDefaults']
        self.assertNotIn('modelName',publication_facts(p))
        for key,value in [('value','FAKE-SUPPLIER-MODEL'),('productId','other'),
                          ('source','agent_guess'),('scope','all'),('supplierVerified',True),
                          ('configuredAt','2026-11-21'),('instruction','')]:
            p=self.fixture();p['publicationAttributeDefaults']['modelName'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):publication_facts(p)
        for sku in ['', ' wrong ', 'a\nb', 'a'*121]:
            p=self.fixture();p['sku']=sku;p['publicationAttributeDefaults']['modelName']['value']=sku
            with self.subTest(sku=sku),self.assertRaises(ValueError):publication_facts(p)

    def test_real_same_source_supplier_number_has_priority(self):
        p=self.fixture();p['sourceImport']['supplier']['attributes']['货号']='ACTUAL-123'
        f=publication_facts(p)
        self.assertEqual(f['modelName'],'ACTUAL-123')
        self.assertEqual(f['supplierModelNumber'],'ACTUAL-123')
        self.assertEqual(f['modelNameEvidence']['source'],'supplier_attribute')


if __name__ == '__main__':unittest.main()
