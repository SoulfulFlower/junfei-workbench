import unittest
from unittest.mock import patch
import erp_collection_inputs as inputs

class InputsTests(unittest.TestCase):
    def setUp(self):
        self.p={'id':'P','sku':'P','purchasePrice':'CNY 42.00','junfeiVariantPrices':{'P-S':'31.25','P-M':'32.50'}}
        self.d={'id':'store-a','marketplace':'US','price':'25.64','quantity':88,'handlingDays':3,'baseUrl':'http://127.0.0.1:18775'}
        self.rows=[('P-S','Red','','S','','',''),('P-M','Red','','M','','','')]

    def test_new_product_prices_come_from_product_not_the_previous_cardigan_store_price(self):
        d=inputs.commerce(2,self.p,self.d,(r for r in self.rows))
        self.assertEqual(d['variantPrices'],{'P-S':'31.25','P-M':'32.50'});self.assertEqual(d['purchaseCny'],'42.00')
        p=dict(self.p);p.pop('junfeiVariantPrices')
        with patch.object(inputs,'selection_quote',return_value=None):
            with self.assertRaisesRegex(ValueError,'售价'):inputs.commerce(2,p,self.d,self.rows)

    def test_legacy_receipt_only_applies_to_its_original_account_product_and_market(self):
        p={'id':'P'};prior={'accountId':2,'productId':'P','marketplace':'US','destination':{'purchaseCny':'39'},'goodsItems':[{'sku':'P-S','price':'25.64'},{'sku':'P-M','price':'25.64'}]}
        with patch.object(inputs,'selection_quote',return_value=None):
            self.assertEqual(inputs.commerce(2,p,self.d,self.rows,prior)['price'],'25.64')
            for user,product in ((3,p),(2,{'id':'Other'})):
                with self.assertRaises(ValueError):inputs.commerce(user,product,self.d,self.rows,prior)

    def test_purchase_range_and_cross_currency_default_are_not_accepted(self):
        with self.assertRaisesRegex(ValueError,'价格区间'):inputs.purchase_price({'purchasePrice':'39–49元'})
        p=dict(self.p);p['junfeiVariantPrices']={}
        with patch.object(inputs,'selection_quote',return_value={'formula_price_usd':'25.64'}):
            with self.assertRaises(ValueError):inputs.commerce(2,p,{**self.d,'marketplace':'UK'},self.rows)
        with patch.object(inputs,'selection_quote',return_value=None):
            with self.assertRaises(ValueError):inputs.commerce(2,self.p,{**self.d,'marketplace':'UK'},self.rows)

    def test_source_identity_includes_account_product_and_destination(self):
        a=inputs.source_url(2,'P',self.d)
        self.assertNotEqual(a,inputs.source_url(3,'P',self.d));self.assertNotEqual(a,inputs.source_url(2,'P',{**self.d,'id':'store-b'}))
        self.assertNotEqual(a,inputs.source_url(2,'Q',self.d))

    def test_transport_needs_store_connection_but_never_a_product_binding(self):
        d={**self.d,'browserBinding':'app','page':'p1','storeId':'1','storeName':'Store','seller':'Seller','erpAccount':'ERP',
           'marketId':'2','marketplaceId':'US-ID','erpUserId':3,'currency':'USD','countryCode':'US','languageTag':'en_US','purchaseCny':'42'}
        self.assertNotIn('products',inputs.transport(2,self.p,d))
        del d['marketId']
        with self.assertRaisesRegex(ValueError,'只需配置一次'):inputs.transport(2,self.p,d)

    def test_verified_selection_keeps_supplier_cost_and_formula_as_business_facts(self):
        from discovery_intake import draft_pricing
        supply={'selected_quote':{'formula_price_usd':'25.64'}};url='https://detail.1688.com/offer/123.html'
        sources=[{'url':url,'checked_at':'2026-11-12T00:00:00Z','raw':'红色XL，采购¥39、运费¥7起、420g'}]
        result=draft_pricing(supply,sources,url,'US','evidence')
        self.assertEqual(result['purchaseCny'],'39');self.assertEqual(result['price'],'25.64')
        self.assertNotIn('cliJobId',result)
        sources[0]['raw']='采购¥39–49'
        self.assertIsNone(draft_pricing(supply,sources,url,'US','evidence'))

    def test_claimed_shared_pricing_does_not_need_access_to_another_accounts_cli(self):
        p={'id':'P','sourceUrl':'https://detail.1688.com/offer/123.html','erpDraftPricing':{'US':{
            'marketplace':'US','currency':'USD','price':'31.25','purchaseCny':'42','sourceUrl':'https://detail.1688.com/offer/123.html',
            'scope':'quote_based_draft_base_scenario','basisSha256':'proof'}}}
        with patch.object(inputs,'selection_quote',side_effect=AssertionError('must not read another account CLI')):
            result=inputs.commerce(9,p,self.d,self.rows)
        self.assertEqual(result['price'],'31.25');self.assertEqual(result['purchaseCny'],'42.00')

    def test_resume_digest_resolves_ordered_sku_images_despite_global_asset_reordering(self):
        import copy
        assets=[{'sha256':str(i)*64,'color':color,'slot':slot} for i,(color,slot) in enumerate([('red',0),('red',1),('blue',0),('blue',1)])]
        original={'accountId':2,'productId':'P','marketplace':'US','store':'Store','goods':{'title':'Top'},
                  'assets':assets,'goodsItems':[{'sku':'R-S','color':'red','price':'24.47','imageIndices':[0,1]},
                                              {'sku':'B-S','color':'blue','price':'24.47','imageIndices':[2,3]}]}
        reordered=copy.deepcopy(original);reordered['assets']=[assets[i] for i in [2,3,0,1]]
        reordered['goodsItems'][0]['imageIndices']=[2,3];reordered['goodsItems'][1]['imageIndices']=[0,1]
        self.assertEqual(inputs.content_digest(original),inputs.content_digest(reordered))
        for field,value in [('accountId',3),('store','Other')]:
            bad=copy.deepcopy(reordered);bad[field]=value
            self.assertNotEqual(inputs.content_digest(original),inputs.content_digest(bad))
        for indices in ([0,1],[3,2]):
            bad=copy.deepcopy(reordered);bad['goodsItems'][0]['imageIndices']=indices
            self.assertNotEqual(inputs.content_digest(original),inputs.content_digest(bad))
        bad=copy.deepcopy(reordered);bad['goodsItems'][0]['price']='19.99'
        self.assertNotEqual(inputs.content_digest(original),inputs.content_digest(bad))
        bad=copy.deepcopy(reordered);bad['assets'][0]['sha256']='changed'
        self.assertNotEqual(inputs.content_digest(original),inputs.content_digest(bad))
        for invalid in ([True],[4],[-1],['1']):
            bad=copy.deepcopy(reordered);bad['goodsItems'][0]['imageIndices']=invalid
            with self.assertRaisesRegex(ValueError,'图片索引无效'):inputs.content_digest(bad)

if __name__=='__main__':unittest.main()
