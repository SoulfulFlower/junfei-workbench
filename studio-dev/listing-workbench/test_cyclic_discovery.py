import copy
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

# Set account DATA before module import, including app_paths mkdir side effect.
_STAGE = tempfile.TemporaryDirectory(prefix='discovery-test-')
with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': _STAGE.name}):
    import cyclic_discovery as cd


def chain():
    def e(i, kind, parent, **kw):
        return dict(id=i, kind=kind, parentId=parent, marketplace='US', observedAt='2026-01-01T00:00:00Z', sourceType='browser_visible', **kw)
    return [
        e('k1', 'keyword', None, asin='B000000001', sourceTitle='Brand Cotton Shirt Women', brand='Brand', phrase='Cotton Shirt', url='https://www.amazon.com/dp/B000000001'),
        e('q1', 'search', 'k1', query='Cotton Shirt', url='https://amazon.com/s?k=Cotton+Shirt', products=[dict(asin='B000000002', title='Cotton Shirt Blue', brand='Other', similarity='EXACT')]),
        e('s1', 'seller', 'q1', asin='B000000002', sellerId='SELLER1', sellerName='Other', sellerLabel='Sold by Other', sellerLinkSource='visible_sold_by_link', sellerLink='https://amazon.com/sp?seller=SELLER1', url='https://amazon.com/dp/B000000002'),
        e('t1', 'store', 's1', sellerId='SELLER1', status='captured', url='https://amazon.com/s?me=SELLER1', products=[dict(asin='B000000003', title='Linen Pants Women')]),
        e('k2', 'keyword', 't1', asin='B000000003', sourceTitle='Linen Pants Women', phrase='Linen Pants', url='https://amazon.com/dp/B000000003'),
        e('q2', 'search', 'k2', query='Linen Pants', url='https://amazon.com/s?k=Linen+Pants', products=[dict(asin='B000000004', title='Linen Pants Tall', brand='Fourth')]),
        e('s2', 'seller', 'q2', asin='B000000004', sellerId='SELLER2', sellerName='Merchant', sellerLabel='Sold by Merchant', sellerLinkSource='visible_sold_by_link', sellerLink='https://amazon.com/sp?seller=SELLER2', url='https://amazon.com/dp/B000000004'),
        e('t2', 'store', 's2', sellerId='SELLER2', status='captured', url='https://amazon.com/s?me=SELLER2', products=[dict(asin='B000000005', title='Wool Coat Long')])]


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=_STAGE.name)
        self.p = patch.object(cd, 'DB', Path(self.temp.name) / 'cyclic_discovery.sqlite3')
        self.p.start()
    def tearDown(self):
        self.p.stop()
        self.temp.cleanup()
    def ingest(self, rows, revision=0, user=1):
        return cd.ingest(user, dict(cycleId='test', expectedRevision=revision, events=rows))
    def test_two_round_trace(self):
        r = self.ingest(chain())
        self.assertEqual(r['roundCount'], 2)
        self.assertEqual(r['counts']['discoveredProducts'], 5)
        self.assertEqual(len(r['sellers']), 2)
        self.assertEqual(len(r['stores']), 2)
        self.assertEqual({x['relation'] for x in r['edges']}, {'title_generated_keyword','searched_to_product','sold_by_observed','seller_store_observed','store_listed_product'})
        for edge in r['edges']:
            self.assertIn(edge['eventId'], [x['id'] for x in chain()])
            self.assertEqual(edge['trust'], 'unverified_observation')
            self.assertTrue(edge['sourceURL'])
        self.assertFalse(r['qualificationEvaluated'])
        self.assertFalse(r['executionAllowed'])
        self.assertEqual((r['qualifiedCount'],r['importedCount'],r['externalCallsPerformed']), (0,0,0))
        self.assertEqual(r['externalCallsScope'], 'ledger_ingestion_only')
        self.assertNotIn('Offline imported observations only', r['limitations'])
        self.assertEqual(cd.report(1,'test'),r)
    def test_brand_not_seller(self):
        r=self.ingest(chain()[:2])
        self.assertEqual(r['sellers'], [])
        self.assertNotIn('sold_by_observed',[e['relation'] for e in r['edges']])
        # Real seller and brand can legitimately have identical display names.
        self.assertEqual(self.ingest(chain()[2:3],1)['counts']['recordedSellers'],1)

    def test_observed_merchant_ref_path_is_canonicalized_narrowly(self):
        rows=chain()[:3]
        rows[2]['sellerLink']='https://amazon.com/gp/help/seller/at-a-glance.html/ref=dp_merchant_link?seller=SELLER1'
        result=self.ingest(rows)
        self.assertEqual(result['events'][2]['sellerLink'],'https://amazon.com/gp/help/seller/at-a-glance.html?seller=SELLER1')
        self.assertFalse(result['qualificationEvaluated'])
        for suffix in ('/ref=unknown','/ref=dp_merchant_link/extra','/ref=dp_merchant_link/../signin','/ref=dp_merchant_link%2Fextra'):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):
                cd._url('https://amazon.com/gp/help/seller/at-a-glance.html'+suffix+'?seller=SELLER1','US','seller','SELLER1')

    def test_bad_fields(self):
        changes=[(2,'sellerLink','https://other.com/sp?seller=SELLER1'),(2,'sellerLinkSource','brand_store'),(2,'sellerLink','https://amazon.com/stores/Other'),(2,'asin','B000000099'),(2,'parentId','k1'),(3,'sellerId','SELLER2'),(0,'phrase','Shirt Women'),(0,'url','https://u:p@amazon.com/dp/B000000001'),(0,'url','https://amazon.com:444/dp/B000000001'),(0,'url','https://amazon.co.uk/dp/B000000001'),(0,'observedAt','2026-01-01'),(0,'observedAt','2099-01-01T00:00:00Z'),(1,'observedAt','2025-01-01T00:00:00Z'),(1,'url','https://amazon.com/s?k=Cotton+Shirt&k=other'),(3,'url','https://amazon.com/s?me=SELLER1&seller=SELLER1'),(4,'sourceTitle','Fabric Pants Women')]
        for i,key,val in changes:
            with self.subTest(key=key,val=val):
                rows=chain();rows[i][key]=val
                with self.assertRaises(ValueError): self.ingest(rows)
                self.assertEqual(cd.history(1)['items'], [])
    def test_cycle_and_missing_parent(self):
        rows=chain();rows[0]['parentId']='t2'
        with self.assertRaises(ValueError):self.ingest(rows)
        rows=chain();rows[1]['parentId']='missing'
        with self.assertRaises(ValueError):self.ingest(rows)
    def test_idempotent_conflict_and_rollback(self):
        first=self.ingest(chain()[:2])
        self.assertEqual(first,self.ingest(chain()[:2],0))
        bad=chain()[0];bad['phrase']='Cotton'
        with self.assertRaises(ValueError):self.ingest([chain()[2],bad],1)
        self.assertEqual(cd.report(1,'test'),first)
        self.assertEqual(self.ingest(chain()[2:],1)['revision'],2)
    def test_owner_and_stale(self):
        self.ingest(chain()[:1])
        with self.assertRaises(ValueError):cd.report(2,'test')
        self.assertEqual(cd.history(2),{'items':[]})
        with self.assertRaises(ValueError):self.ingest(chain()[1:2],0)
        self.assertEqual(self.ingest(chain()[:1],0,user=2)['revision'],1)
        self.assertEqual(cd.report(1,'test')['eventCount'],1)
    def test_concurrent_revision_writers(self):
        self.ingest(chain()[:1])
        def writer(i):
            row=copy.deepcopy(chain()[1]);row['id']='search'+str(i)
            try:
                self.ingest([row],1)
                return 'committed'
            except ValueError:
                return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(writer,range(2)))
        self.assertCountEqual(outcomes,['committed','stale'])
        self.assertEqual(cd.report(1,'test')['revision'],2)
        self.assertEqual(cd.report(1,'test')['eventCount'],2)
    def test_read_no_database(self):
        self.assertFalse(cd.DB.exists())
        self.assertEqual(cd.history(1),{'items':[]})
        with self.assertRaises(ValueError):cd.report(1,'missing')
        self.assertFalse(cd.DB.exists())
    def test_clean_fields_urls_and_all_sources(self):
        rows=chain();rows[0]['verified']=True;rows[0]['url']+='?token=secret&email=a%40b.com'
        duplicate=copy.deepcopy(rows[0]);duplicate['id']='another';duplicate['phrase']='cotton shirt'
        r=self.ingest(rows+[duplicate])
        self.assertEqual(len(r['keywords']),2)
        self.assertEqual(len(r['keywords'][0]['sources']),2)
        self.assertEqual(len([e for e in r['edges'] if e['relation']=='title_generated_keyword']),3)
        self.assertNotIn('secret',str(r));self.assertNotIn("'verified'",str(r))
    def test_inaccessible_and_product_conflicts(self):
        rows=chain()[:4];rows[3].update(status='inaccessible',products=[],reason='Access unavailable')
        self.assertIn('needs_review',[q['status'] for q in self.ingest(rows)['queue']])
        rows=chain();rows[3]['products'].append(dict(asin='B000000003',title='Different'))
        with self.assertRaises(ValueError):self.ingest(rows,1)
    def test_partial_branching_and_duplicate_pause(self):
        rows=chain()
        rows[1]['products'].append(dict(asin='B000000099',title='Cotton Shirt Extra'))
        rows[3]['products'].append(dict(asin='B000000098',title='Cotton Shirt Extra'))
        r=self.ingest(rows)
        self.assertIn(('B000000099','needs_seller_capture'),[(q['sourceASIN'],q['status']) for q in r['queue']])
        self.assertIn(('B000000098','needs_title_phrase_capture'),[(q['sourceASIN'],q['status']) for q in r['queue']])
        dupe=copy.deepcopy(rows[0]);dupe['id']='dupe'
        r=self.ingest([dupe],1)
        self.assertIn('duplicate_keyword_already_searched',[q['status'] for q in r['queue']])
        empty=copy.deepcopy(rows[5]);empty['id']='empty';empty['products']=[]
        r=self.ingest([empty],2)
        self.assertIn('no_new_products',[q['status'] for q in r['queue']])
    def test_export_empty_search_and_exact_parent_ancestry(self):
        rows=chain()[:4]
        # A second title source normalizes to the existing keyword, but has its
        # own store parent and must remain independently reconstructable.
        rows[3]['products']=[dict(asin='B000000003',title='Cotton Shirt Extra')]
        derived=copy.deepcopy(rows[0])
        derived.update(id='derived', parentId='t1', asin='B000000003',
                       sourceTitle='Cotton Shirt Extra', phrase='cotton shirt',
                       url='https://amazon.com/dp/B000000003')
        derived.pop('brand')
        empty=copy.deepcopy(rows[1])
        empty.update(id='empty',parentId='derived',query='cotton shirt',
                     url='https://amazon.com/s?k=cotton+shirt&token=private',products=[],
                     verified=True,unrecognized={'secret':'do not preserve'})
        r=self.ingest(rows+[derived,empty])
        exported={e['id']:e for e in cd.report(1,'test')['events']}
        self.assertEqual(len(exported),6)
        e=exported['empty']
        self.assertEqual((e['query'],e['url'],e['observedAt']),
                         ('cotton shirt','https://amazon.com/s?k=cotton+shirt','2026-01-01T00:00:00+00:00'))
        self.assertEqual(e['products'],[])
        self.assertEqual((e['round'],e['trust']), (2,'unverified_observation'))
        self.assertNotIn('verified',e)
        self.assertNotIn('unrecognized',e)
        self.assertNotIn('private',str(r))
        ancestry=[]
        while e is not None:
            ancestry.append(e['id'])
            e=exported.get(e['parentId'])
        self.assertEqual(ancestry,['empty','derived','t1','s1','q1','k1'])
        self.assertEqual(len(r['keywords']),1)
        self.assertEqual({e['eventId']:e['parentId'] for e in r['keywords'][0]['sources']},
                         {'k1':None,'derived':'t1'})
        for edge in r['edges']:
            self.assertEqual(edge['parentId'],exported[edge['eventId']]['parentId'])
    def test_template_blank_and_limits(self):
        t=cd.template();self.assertEqual(t['events'],[])
        with self.assertRaises(ValueError):self.ingest(chain()[:1]*101)
        with self.assertRaises(ValueError):cd.ingest(True,dict(cycleId='c',expectedRevision=0,events=chain()[:1]))
        with self.assertRaises(ValueError):cd.ingest(1,t)

    def keyword_request(self, **changes):
        return {'cycleId':'test','expectedRevision':1,'parentId':'t1',
                'asin':'B000000003','phrase':'Linen Pants',**changes}

    def test_prepare_keyword_is_read_only_deterministic_and_preserves_source(self):
        before=self.ingest(chain()[:4])
        raw=cd.DB.read_bytes()
        first=cd.prepare_keyword(1,self.keyword_request())
        self.assertEqual(cd.prepare_keyword(1,self.keyword_request()),first)
        self.assertEqual(cd.DB.read_bytes(),raw)
        self.assertEqual(cd.report(1,'test'),before)
        self.assertTrue(first['readOnly'])
        self.assertEqual(first['sourceKind'],'seller_listing_card')
        self.assertFalse(first['qualificationEvaluated'])
        self.assertFalse(first['executionAllowed'])
        event=first['preparedBatch']['events'][0]
        self.assertEqual((event['sourceTitle'],event['observedAt'],event['parentId']),
                         ('Linen Pants Women','2026-01-01T00:00:00+00:00','t1'))
        self.assertEqual(first['derivedFrom']['sellerId'],'SELLER1')
        self.assertEqual(first['sourceObservationTime'],event['observedAt'])

    def test_prepared_keyword_explicit_save_replay_and_second_round(self):
        self.ingest(chain()[:4])
        prepared=cd.prepare_keyword(1,self.keyword_request())['preparedBatch']
        saved=cd.ingest(1,prepared)
        self.assertEqual((saved['revision'],saved['eventCount'],saved['roundCount']),(2,5,2))
        self.assertEqual(cd.ingest(1,prepared),saved)
        self.assertEqual((saved['qualifiedCount'],saved['importedCount']),(0,0))
        self.assertIn('pending_search_capture',[q['status'] for q in saved['queue']])
        next_prepared=cd.prepare_keyword(1,self.keyword_request(expectedRevision=2))['preparedBatch']
        self.assertEqual(next_prepared['events'],prepared['events'])
        self.assertEqual(cd.ingest(1,next_prepared),saved)

    def test_keyword_prepare_wrong_owner_parent_product_and_stale_are_rejected(self):
        saved=self.ingest(chain()[:4])
        for change in ({'parentId':'s1'},{'parentId':'missing'},{'asin':'B000000099'},
                       {'expectedRevision':0},{'expectedRevision':True},
                       {'phrase':'Pants Women'},{'phrase':''},{'phrase':'Imaginary Linen Pants'},
                       {'owner':2},{'title':'Invented Title'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                cd.prepare_keyword(1,self.keyword_request(**change))
        with self.assertRaises(ValueError):cd.prepare_keyword(2,self.keyword_request())
        self.assertEqual(cd.report(1,'test'),saved)

    def test_keyword_prepare_read_does_not_create_database(self):
        with self.assertRaises(ValueError):cd.prepare_keyword(1,self.keyword_request())
        self.assertFalse(cd.DB.exists())

    def test_keyword_prepare_inaccessible_listing_rejected(self):
        rows=chain()[:4];rows[-1].update(status='inaccessible',products=[],reason='Access unavailable')
        saved=self.ingest(rows)
        with self.assertRaises(ValueError):cd.prepare_keyword(1,self.keyword_request())
        self.assertEqual(cd.report(1,'test'),saved)

    def test_keyword_prepare_cannot_silently_save_after_revision_changes(self):
        self.ingest(chain()[:4])
        prepared=cd.prepare_keyword(1,self.keyword_request())['preparedBatch']
        other=copy.deepcopy(chain()[0]);other['id']='another-root'
        current=self.ingest([other],1)
        with self.assertRaises(ValueError):cd.ingest(1,prepared)
        self.assertEqual(cd.report(1,'test'),current)

    def test_keyword_prepare_preserves_optional_brand_without_inferring_seller(self):
        rows=chain()[:4];rows[3]['products'][0].update(title='ExampleBrand Linen Pants Women',brand='ExampleBrand')
        self.ingest(rows)
        prepared=cd.prepare_keyword(1,self.keyword_request())
        event=prepared['preparedBatch']['events'][0]
        self.assertEqual(event['brand'],'ExampleBrand')
        self.assertEqual(event['sourceTitle'],'ExampleBrand Linen Pants Women')
        self.assertEqual(prepared['derivedFrom']['sellerId'],'SELLER1')



if __name__ == '__main__':
    unittest.main()
