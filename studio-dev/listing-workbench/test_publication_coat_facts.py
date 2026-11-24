import copy
import json
from pathlib import Path
import tempfile
import unittest
import publication_coat_facts as module


class CoatFactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
        url='https://detail.1688.com/offer/123.html';image='https://example.test/photo.jpg'
        self.observed={'canonicalUrl':url,'offerId':'123','observedAt':'2026-11-21T12:00:00+00:00',
            'images':[image],'attributes':{'门襟':'拉链','袖型':'灯笼袖','袖长':'长袖',
            '衣长':'普通款(50cm<衣长≤65cm)','材质成分':'涤纶（聚酯纤维）:100%'}}
        self.file=self.folder/'source.json';self.write(self.file,self.observed)
        self.source={'accountId':1,'jobId':'job','productId':'p','sha256':'snapshot',
            'goods':{'sourceUrl':url,'description':'Material: 100% polyester\nClosure: Front half zipper with a long red pull\nStyle: Loose long sleeves and pullover hem'},
            'publicationFacts':{'waterResistanceLevelSource':{'basis':{'classification':'ordinary_apparel'}}}}
        self.product={'id':'p','cat':'服装','sourceUrl':url,'sourceImport':{'supplier':{'url':url,
            'attributes':{'材质成分':'涤纶（聚酯纤维）:100%'}}},
            'sourceEvidence':{'completeSourceObservation':str(self.file)},
            'assets':[{'originUrl':image,'sourceRole':'primary','sourceSupplierUrl':url}]}
        self.receipt={'accountId':1,'jobId':'job','productId':'p','snapshotSha256':'snapshot','phase':'us_preparation','usPublish':{},
            'usPrepare':{'schemaObservation':{'country_code':'US','product_type_name':'COAT'},
                         'schemaValidation':{'passed':False},'preparedInput':{'failedPreview':'retained'}}}
        self.job={'id':'job','accountId':1,'productId':'p'}

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False),'utf-8')

    def test_observed_source_and_frozen_text_are_both_required(self):
        before=copy.deepcopy(self.product);f=module.derive(self.product,self.source)
        self.assertEqual(f['sleeve']['value'],'Lantern Sleeve');self.assertEqual(f['itemLength']['value'],'Standard Length')
        self.assertFalse(f['humanReviewed']);self.assertFalse(f['dangerousGoods']['supplierVerified'])
        self.assertNotIn('supplierModelNumber',f);self.assertEqual(self.product,before)

    def raglan_fixture(self):
        self.observed['attributes']['袖型']='插肩袖'
        self.observed['attributes']['衣长']='普通款(50cm＜衣长≤65cm)'
        self.write(self.file,self.observed)
        self.product['sourceImport']['supplier']['attributes']=copy.deepcopy(self.observed['attributes'])
        self.source['goods']['description']='Material: 100% Polyester\nStyle: Fitted padded jacket\nFront: Full zipper; chevron quilting\nSleeves: Smooth raglan long sleeves; plain straight openings'

    def test_explicit_raglan_source_and_frozen_front_sleeves_map_without_lantern(self):
        self.raglan_fixture();before=copy.deepcopy((self.product,self.source));facts=module.derive(self.product,self.source)
        self.assertEqual(facts['sleeve']['value'],'Raglan Sleeve');self.assertEqual(facts['sleeve']['sourceValue'],'插肩袖')
        self.assertEqual(facts['closure']['frozenLineLabel'],'Front');self.assertEqual(facts['style']['value'],'Fitted padded jacket')
        self.assertFalse(facts['style']['supplierVerified']);self.assertEqual((self.product,self.source),before)

    def test_raglan_requires_matching_supplier_and_frozen_sleeve_style_lines(self):
        self.raglan_fixture()
        for edit in [lambda p,s:p['sourceImport']['supplier']['attributes'].update(袖型='灯笼袖'),
                     lambda p,s:s['goods'].update(description=s['goods']['description'].replace('raglan','puff')),
                     lambda p,s:s['goods'].update(description=s['goods']['description'].replace('Fitted padded jacket','Long trench coat')),
                     lambda p,s:s['goods'].update(description=s['goods']['description'].replace('Full zipper','Half zipper'))]:
            p,s=copy.deepcopy((self.product,self.source));edit(p,s)
            with self.assertRaises(ValueError):module.derive(p,s)

    def test_visible_same_offer_1688_colour_rendition_binds_only_exact_cdn_original(self):
        self.raglan_fixture();image='https://cbu01.alicdn.com/img/ibank/actual.jpg'
        self.product['assets'][0]['originUrl']=image
        self.observed['colourButtons']=[{'text':'Black','visible':True,'image':image+'_sum.jpg'}]
        self.write(self.file,self.observed);facts=module.derive(self.product,self.source)
        self.assertEqual(facts['observation']['colourButtonImageProofs'][0]['originalUrl'],image)
        for button in [{'visible':False,'image':image+'_sum.jpg'},
                       {'visible':True,'image':'https://other.test/actual.jpg_sum.jpg'},
                       {'visible':True,'image':image+'_sum.jpg?different=1'}]:
            self.observed['colourButtons']=[button];self.write(self.file,self.observed)
            with self.assertRaises(ValueError):module.derive(self.product,self.source)

    def test_foreign_unknown_and_unbound_observations_block(self):
        for change in [lambda x:x.update(canonicalUrl='other'),lambda x:x.update(offerId='456'),
                       lambda x:x.update(observedAt='2026-11-21'),lambda x:x.update(images=['other']),
                       lambda x:x['attributes'].update(袖型='未知'),lambda x:x['attributes'].update(门襟='纽扣'),
                       lambda x:x['attributes'].update(材质成分='未知'),lambda x:x['attributes'].update(衣长='长款')]:
            x=copy.deepcopy(self.observed);change(x);self.write(self.file,x)
            with self.subTest(x=x),self.assertRaises(ValueError):module.derive(self.product,self.source)
        self.write(self.file,self.observed)
        other=copy.deepcopy(self.source);other['goods']['description']=other['goods']['description'].replace('100% polyester','95% polyester')
        with self.assertRaises(ValueError):module.derive(self.product,other)

    def test_unsaved_failed_preview_is_archived_without_resetting_attempts(self):
        self.write(self.folder/'receipt.json',self.receipt);packet={'input':self.source};original=copy.deepcopy(packet)
        module.append(1,self.job,self.folder,packet,self.product,self.write)
        amended=json.loads((self.folder/'input.json').read_text('utf-8'));module.append(1,self.job,self.folder,amended,self.product,self.write)
        self.assertEqual(len(self.job['amendments']),1);self.assertEqual(packet,original)
        archive=json.loads(next((self.folder/'amendments').glob('*.json')).read_text('utf-8'))
        self.assertEqual(archive['previousInput'],original);self.assertEqual(archive['previousUsPreparation'],self.receipt['usPrepare'])
        self.assertEqual(json.loads((self.folder/'receipt.json').read_text('utf-8')),self.receipt)

    def test_other_account_saved_published_or_different_type_block(self):
        for edit in [lambda x:x.update(accountId=2),lambda x:x.update(usPublish={'publishId':'10'}),
                     lambda x:x['usPrepare'].update(saveIntendedAt='time'),lambda x:x['usPrepare'].update(requestSent=True),
                     lambda x:x['usPrepare'].update(submitted={'attributes':{}}),
                     lambda x:x['usPrepare']['schemaValidation'].update(passed=True),
                     lambda x:x['usPrepare']['schemaObservation'].update(product_type_name='SHIRT')]:
            r=copy.deepcopy(self.receipt);edit(r);self.write(self.folder/'receipt.json',r)
            with self.subTest(r=r),self.assertRaises(ValueError):module.append(1,self.job,self.folder,{'input':self.source},self.product,self.write)


class UkCoatWeaveTest(CoatFactsTest):
    def prepare_uk(self):
        self.source['usPreparation']={'coatFacts':{'productId':'p'}}
        self.receipt.update(phase='uk_preparation',ukCopy={'phase':'copy_verified'},ukPublish={},
            usPublish={'phase':'publishing_verified','publishId':'123'},ukPrepare={'schemaObservation':{
            'country_code':'GB','locale':'en_GB','product_type_name':'COAT','hash':'uk',
            'schema_content':{'properties':{'weave_type':{'items':{'properties':{'value':{'anyOf':[{'type':'string'},{'enum':['Plain']}]}}}}}}},
            'schemaValidationBeforeSave':{'passed':False}})
        return {'productId':'p','value':'Plain','source':'user_configured_defaults','supplierVerified':False,
                'scope':'missing_catalogue_attribute_only','instruction':'ordinary mandatory choices authorized',
                'configuredAt':'2026-11-21T15:00:00+00:00','schemaHash':'uk'}

    def test_uk_default_archives_original_and_is_idempotent(self):
        evidence=self.prepare_uk();self.write(self.folder/'receipt.json',self.receipt)
        packet={'input':self.source};module.append_uk_weave(1,self.job,self.folder,packet,evidence,self.write)
        amended=json.loads((self.folder/'input.json').read_text('utf8'))
        module.append_uk_weave(1,self.job,self.folder,amended,evidence,self.write)
        self.assertEqual(len(self.job['amendments']),1)
        self.assertFalse(amended['input']['ukPreparation']['coatWeave']['supplierVerified'])
        self.assertEqual(json.loads(next((self.folder/'amendments').glob('*.json')).read_text('utf8'))['previousUkPreparation'],self.receipt['ukPrepare'])

    def test_uk_default_blocks_foreign_product_saved_unknown_or_false_supplier_claims(self):
        evidence=self.prepare_uk()
        for change in [lambda x:x.update(accountId=2),lambda x:x.update(ukPublish={'intent':{}}),
                       lambda x:x['ukPrepare'].update(saveIntendedAt=1),lambda x:x['ukPrepare'].update(submitted={'x':1}),
                       lambda x:x['ukPrepare'].update(preparedInput={'x':1}),lambda x:x['ukPrepare']['schemaObservation'].update(hash='different')]:
            r=copy.deepcopy(self.receipt);change(r);self.write(self.folder/'receipt.json',r)
            with self.assertRaises(ValueError):module.append_uk_weave(1,self.job,self.folder,{'input':self.source},evidence,self.write)
        self.write(self.folder/'receipt.json',self.receipt)
        for change in [lambda x:x.update(productId='other'),lambda x:x.update(supplierVerified=True),lambda x:x.update(value='Satin')]:
            e=copy.deepcopy(evidence);change(e)
            with self.assertRaises(ValueError):module.append_uk_weave(1,self.job,self.folder,{'input':self.source},e,self.write)

if __name__=='__main__':unittest.main()
