import unittest
from unittest.mock import patch
import importer


class BrowserImportTests(unittest.TestCase):
    def test_amazon_wayfinding_keeps_full_path_links_and_node_evidence_for_erp(self):
        from erp_collection_inputs import category_hints
        page='''<span id="productTitle">Women's Ribbed Top</span>
        <div id="wayfinding-breadcrumbs_feature_div"><ul>
        <li><a href="/fashion?node=7141123011"><span>Clothing, Shoes &amp; Jewelry</span></a></li><li>›</li>
        <li><a href="/women?node=7147440011">Women</a></li><li>›</li>
        <li><a href="/tops?ie=UTF8&amp;node=2368343011">Tops, Tees &amp; Blouses</a></li>
        <li><a href="/tees?node=1044544">T-Shirts</a></li></ul></div>
        <div id="SalesRank">#8 in Clothing, Shoes &amp; Jewelry</div>'''
        amazon=importer.parse_amazon(page)
        expected='Clothing, Shoes & Jewelry > Women > Tops, Tees & Blouses > T-Shirts'
        self.assertEqual(amazon['category'],expected)
        crumbs=amazon['categoryEvidence']['breadcrumbs']
        self.assertEqual(crumbs[-1],{'name':'T-Shirts','url':'/tees?node=1044544','nodeId':'1044544'})
        self.assertEqual(crumbs[2]['url'],'/tops?ie=UTF8&node=2368343011')
        self.assertEqual(category_hints({'sourceImport':{'amazon':amazon}})['path'],expected)

    def test_missing_wayfinding_does_not_invent_category_from_title_bsr_or_navigation(self):
        amazon=importer.parse_amazon('<span id="productTitle">Women T-Shirts</span><nav><a href="/?node=1">Clothing</a></nav><div id="SalesRank">#1 in Clothing</div>')
        self.assertEqual(amazon['category'],'');self.assertIsNone(amazon['categoryEvidence'])

    def test_import_markets_match_sellersprite_and_correct_domain(self):
        self.assertEqual(set(importer.MARKET_DOMAINS), {'US','JP','UK','DE','FR','IT','ES','CA','IN','MX'})
        for market, domain in importer.MARKET_DOMAINS.items():
            with self.subTest(market=market), patch('sellersprite.Client') as client:
                client.return_value.connect.return_value.call.return_value={'title':'Test','features':['Detail']}
                result = importer.preview({'asin': 'B0FVS1X3SP', 'market': market})
                self.assertEqual(result['market'], market)
                self.assertEqual(result['amazonUrl'],'https://www.amazon.'+domain+'/dp/B0FVS1X3SP')
                self.assertEqual(result['amazon']['title'],'Test')
                client.return_value.connect.return_value.call.assert_called_once_with('asin_detail',{'marketplace':market,'asin':'B0FVS1X3SP'})

    def test_amazon_link_is_reference_not_supplier(self):
        with patch('sellersprite.Client') as client:
            client.return_value.connect.return_value.call.return_value={'title':'Robe','features':['Reference detail'],'imageUrl':'https://example.com/robe.jpg'}
            result=importer.preview({'market':'US','source':'https://www.amazon.de/dp/B07RKNSPBR?ref=test'})
        self.assertEqual(result['market'],'DE')
        self.assertEqual(result['asin'],'B07RKNSPBR')
        self.assertEqual(result['supplier']['url'],'')
        self.assertEqual(result['amazon']['referenceImages'],['https://example.com/robe.jpg'])
        self.assertNotIn('manualEntry',result['supplier'])

    def test_capture_creates_and_updates_without_duplicate(self):
        state = {'products': [], 'copy': {}, 'reviews': {}}
        data = {'url': 'https://detail.1688.com/offer/958196845665.html', 'title': '男士连帽抓绒外套商品', 'attributes': {'面料': '摇粒绒'}, 'images': [], 'asin': 'B0FVS1X3SP', 'market': 'UK'}
        pid = importer.merge_browser_capture(state, data)
        self.assertEqual(pid, 'IMP-UK-B0FVS1X3SP')
        state['products'][0]['status'] = '已通过'
        importer.merge_browser_capture(state, data)
        self.assertEqual(len(state['products']), 1)
        self.assertEqual(state['products'][0]['status'], '需修改')
        self.assertNotIn('dimensions', state['products'][0])

    def test_capture_rejects_non_product_page(self):
        with self.assertRaises(ValueError):
            importer.merge_browser_capture({'products': []}, {'url': 'https://evil.example/offer/123.html'})

    def test_preserves_image_dimensions_and_thumbnail_provenance_without_approval(self):
        original='https://cbu01.alicdn.com/img/ibank/garment.jpg'
        thumbnail=original+'_sum.jpg'
        state={'products':[],'copy':{},'reviews':{}}
        data={'url':'https://detail.1688.com/offer/958196845665.html','title':'女士丝绒长袖上衣商品',
              'attributes':{},'images':[original],'imageObservations':[{'url':original,'observedUrl':thumbnail,
              'origin':'supplier_detail','width':1200,'height':1200,'observedWidth':80,'observedHeight':80,
              'originalStatus':'browser_loaded_larger_original','visuallyReviewed':True,'productionApproved':True}]}
        importer.merge_browser_capture(state,data)
        supplier=state['products'][0]['sourceImport']['supplier'];row=supplier['imageObservations'][0]
        self.assertEqual(row['width'],1200);self.assertEqual(row['observedUrl'],thumbnail)
        self.assertFalse(row['visuallyReviewed']);self.assertFalse(row['productionApproved'])
        self.assertEqual(supplier['imageCaptureSummary']['largerOriginalsLoaded'],1)
        self.assertEqual(supplier['imageCaptureSummary']['thumbnailCount'],0)

    def test_unresolved_thumbnail_is_counted_and_untrusted_image_urls_removed(self):
        thumbnail='https://cbu01.alicdn.com/img/ibank/garment.jpg_sum.jpg'
        state={'products':[],'copy':{},'reviews':{}}
        data={'url':'https://detail.1688.com/offer/958196845665.html','title':'女士丝绒长袖上衣商品',
              'attributes':{},'images':[thumbnail,'https://cbu01.alicdn.com/img/ibank/evil.jpg\nheader'],
              'imageObservations':[{'url':thumbnail,'width':80,'height':80}]}
        importer.merge_browser_capture(state,data)
        supplier=state['products'][0]['sourceImport']['supplier']
        self.assertEqual(supplier['images'],[thumbnail]);self.assertEqual(supplier['imageCaptureSummary']['thumbnailCount'],1)

    def test_autofill_size_not_package_and_manual_override(self):
        p = {'sourceImport': {'supplier': {'url': 'https://detail.1688.com/offer/123.html', 'attributes': {'材质成分': '100%聚酯纤维', '尺码': 'S,M,L', '包装尺寸': '40x35x5cm', '颜色': '黑色,灰色', '款式': '连帽'}}}}
        importer.autofill_supplier(p)
        self.assertEqual(p['material'], '100%聚酯纤维')
        self.assertIn('S, M, L', p['dimensions'])
        self.assertNotIn('40x35', p['dimensions'])
        p['material'] = '手动修改'
        importer.autofill_supplier(p)
        self.assertEqual(p['material'], '手动修改')


class SupplierLinkTests(unittest.TestCase):
    def test_source_only_import(self):
        page='<title>女士短袖纯色上衣-阿里巴巴</title><script type="application/ld+json">{"subject":"女士短袖纯色上衣","attributes":[{"name":"材质","value":"棉"}],"image":"https://cbu01.alicdn.com/img/ibank/test.jpg"}</script>'
        with patch('supplier_capture.request',return_value={'status':'collected','supplier':importer.parse_supplier(page,'https://detail.1688.com/offer/958196845665.html')}) as fetch:
            result=importer.preview({'market':'UK','source':'https://detail.1688.com/offer/958196845665.html'})
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(result['supplier']['attributes']['材质'],'棉')
        self.assertEqual(len(result['supplier']['images']),1)
        self.assertEqual(result['asin'],'')
    def test_blocked_source_waits_for_the_same_browser_queue(self):
        with patch('supplier_capture.request',return_value={'status':'paused','id':'capture-fixture','message':'等待验证'}):
            result=importer.preview({'market':'UK','source':'https://detail.1688.com/offer/958196845665.html'})
        self.assertEqual(result['supplier']['captureStatus'],'paused')
        self.assertEqual(result['supplier']['captureId'],'capture-fixture')
        self.assertFalse(result['supplier']['title'])
    def test_other_supplier_link_is_saved_without_fetch(self):
        with patch('importer.fetch') as fetch:
            result=importer.preview({'market':'UK','source':'https://supplier.example/product/123?variant=blue'})
        fetch.assert_not_called()
        self.assertEqual(result['supplier']['url'],'https://supplier.example/product/123?variant=blue')
        self.assertTrue(result['supplier']['manualEntry'])
        self.assertEqual(result['supplier']['images'],[])

    def test_invalid_supplier_link_rejected(self):
        for url in ('javascript:alert(1)','file:///etc/passwd','https://user:password@example.com/a','bad-link'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                importer.preview({'market':'UK','source':url})


class SupplierFactsSeparationTests(unittest.TestCase):
    def test_supplier_order_notice_is_not_a_colour_variant(self):
        p={'sourceImport':{'supplier':{'attributes':{'颜色':'黑色白点、酒红、一件不代发，慎拍！！！、白色、补差专拍','尺码':'XS,S,M,L'}}}}
        importer.autofill_supplier(p)
        self.assertEqual(p['colorNames'],'黑色白点,酒红,白色')
        self.assertEqual(p['colors']*p['sizes'],12)

    def test_conflicting_composition_is_not_promoted_to_listing_fact(self):
        p={'sourceImport':{'supplier':{'attributes':{'面料名称':'麂皮绒','材质成分':'聚酰胺纤维(锦纶):100%','主面料成分':'涤纶（聚酯纤维）','主面料成分的含量':'95%','颜色':'石墨色,军绿色,咖啡色,S-3XL，343g-435g,大量现货，长期供货'}}}}
        importer.autofill_supplier(p)
        self.assertIn('成分字段矛盾',p['material'])
        self.assertNotIn('100%',p['material'])
        self.assertEqual(p['colorNames'],'石墨色,军绿色,咖啡色')
        self.assertEqual(p['colors'],3)

    def test_supplier_logistics_fields_are_distinct_and_manual_values_preserved(self):
        p={'material':'手工核对材质','sourceImport':{'supplier':{'url':'https://detail.1688.com/offer/123.html','attributes':{'材质':'棉','价格':'CNY 12 / 10件起','产品尺寸':'20 × 30 cm','包装尺寸':'25 × 35 × 5 cm','净重':'200 g','毛重':'260 g'}}}}
        importer.autofill_supplier(p)
        self.assertEqual(p['material'],'手工核对材质')
        self.assertEqual(p['dimensions'],'20 × 30 cm')
        self.assertEqual(p['packageDimensions'],'25 × 35 × 5 cm')
        self.assertEqual(p['productWeight'],'200 g')
        self.assertEqual(p['packageWeight'],'260 g')
        self.assertEqual(p['purchasePrice'],'CNY 12 / 10件起')
