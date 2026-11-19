"""ERP consumes confirmed children without mutating the original observations."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import erp_collection as erp


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.product={'id':'P','sku':'P','masterColor':'Red','colorNames':'Red,Gray',
            'purchasePrice':'42','sourceUrl':'https://detail.1688.com/offer/123.html',
            'junfeiVariantPrices':{'P-Red-M':'31.25'},'sourceImport':{'amazon':{
                'variants':[
                    {'asin':'B000000001','sku':'P-Red-S','color_name':'Red','size_name':'Small'},
                    {'asin':'B000000002','sku':'P-Red-M','color_name':'Red','size_name':'Medium'},
                    {'asin':'B000000003','sku':'P-Gray-S','color_name':'Gray','size_name':'Small'}],
                'listingEligibleVariants':[{'asin':'B000000002'}],
                'excludedVariants':[{'asin':'B000000001','reason':'size unavailable'},
                                    {'asin':'B000000003','reason':'color unavailable'}]}}}
        self.destination={'id':'store','marketplace':'US','quantity':88,'handlingDays':3,
                          'store':'Store','baseUrl':'http://127.0.0.1:18775'}
        self.listing={'title':'A jacket','highlights':'Stand collar','bullets':['One','Two','Three','Four','Five'],
                      'description':'Verified description','terms':'jacket'}

    def test_prices_only_need_confirmed_skus_and_original_history_is_unchanged(self):
        before=copy.deepcopy(self.product)
        rows=erp.eligible_variant_rows(self.product)
        priced=erp.inputs.commerce(2,self.product,self.destination,rows)
        self.assertEqual(priced['variantPrices'],{'P-Red-M':'31.25'})
        self.assertEqual(rows[0][0:4],('P-Red-M','Red','Red','M'))
        self.assertEqual(rows[0][6],'B000000002')
        self.assertEqual(len(list(erp.delivery_export.variant_rows(self.product,'P'))),3)
        self.assertEqual(self.product,before)

    def test_empty_confirmed_list_never_falls_back_to_all_observations(self):
        self.product['sourceImport']['amazon']['listingEligibleVariants']=[]
        with patch.object(erp,'ROOT',self.root),patch.object(erp,'destinations',return_value=[self.destination]):
            result=erp.view(2,{'products':[self.product]},'P')
        self.assertEqual(result['variantCount'],0)
        self.assertEqual(erp.eligible_variant_rows(self.product),[])
        self.assertIn('没有可交付',result['issues'][0]['message'])

    def test_old_products_without_explicit_eligibility_keep_original_rows(self):
        del self.product['sourceImport']['amazon']['listingEligibleVariants']
        self.assertEqual([row[0] for row in erp.eligible_variant_rows(self.product)],
                         ['P-Red-S','P-Red-M','P-Gray-S'])

    def test_excluded_incomplete_observation_does_not_block_confirmed_child(self):
        self.product['sourceImport']['amazon']['variants'][0].pop('size_name')
        self.assertEqual([row[0] for row in erp.eligible_variant_rows(self.product)],['P-Red-M'])

    def test_finished_snapshot_omits_same_color_excluded_size_and_other_color(self):
        buffer=io.BytesIO()
        Image.new('RGB',(1600,1600),'white').save(buffer,format='PNG')
        images=[(buffer.getvalue(),{'slot':slot,'mime':'image/png','status':'awaiting_manual',
                                   'humanReviewed':False}) for slot in range(7)]
        groups={'red':{'key':'red','color':'Red','ready':True,
            'children':[{'sku':'P-Red-M','asin':'B000000002','size':'Medium'}],
            'references':[{'url':'/uploads/source.png','aliases':['Red']}]}}
        view={'sets':{'gallery':{'_projectId':'current','product_source_url':'/uploads/source.png'}}}
        before=copy.deepcopy(self.product)
        with patch.object(erp.variant_colours,'catalog',return_value=groups), \
                patch.object(erp.studio_bridge,'get_view',return_value=view), \
                patch.object(erp.generated_gallery,'export_images',return_value=images), \
                patch.object(erp.colour_sets,'list_sets',return_value={'sets':[]}), \
                patch.object(erp.inputs,'transport',return_value={}):
            snapshot=erp.finished_snapshot(2,self.product,self.listing,self.destination,self.root/'media')
        self.assertEqual([row['sku'] for row in snapshot['goodsItems']],['P-Red-M'])
        self.assertEqual(snapshot['goodsItems'][0]['sourceAsin'],'B000000002')
        self.assertEqual(snapshot['goodsItems'][0]['imageIndices'],list(range(7)))
        self.assertEqual(snapshot['goodsItems'][0]['price'],'31.25')
        self.assertEqual(self.product,before)

    def test_receipt_resume_uses_same_confirmed_price_scope_before_browser(self):
        job={'id':'saved','accountId':2,'productId':'P','status':'queued'}
        folder=self.root/job['id']
        folder.mkdir()
        (folder/'collection.json').write_text(json.dumps({'accountId':2,'productId':'P'}))
        with patch.object(erp,'ROOT',self.root),patch.object(erp,'persist'), \
                patch.object(erp.inputs,'commerce',side_effect=ValueError('stop before browser')) as commerce, \
                patch.object(erp,'browser_lease') as browser:
            erp.execute(job,self.product,self.listing,self.destination)
        self.assertEqual([row[0] for row in commerce.call_args.args[3]],['P-Red-M'])
        browser.assert_not_called()


if __name__=='__main__':unittest.main()
