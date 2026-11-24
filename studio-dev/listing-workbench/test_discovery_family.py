"""Offline variant evidence tests. No browser, DB, config, or production writes."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
import discovery_family as family

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
A, B, C = 'B000000001', 'B000000002', 'B000000003'


def graph(asins=(A, B, C), market='US'):
    return {'cycleId': 'fixture', 'revision': 1,
            'products': [{'id': market+':'+a, 'marketplace': market, 'asin': a,
                          'sources': [{'title': 'Same title', 'sellerId': 'SAMESELLER'}]} for a in asins],
            'events': [{'id': 'search1', 'kind': 'search', 'marketplace': market,
                        'observedAt': '2026-11-06T09:00:00Z',
                        'products': [{'asin': a} for a in asins]}],
            'edges': [{'relation': 'sold_by_observed', 'fromId': market+':'+A,
                       'toId': market+':SELLER1'}], 'queue': []}


def raw(asin=A, targets=(A, B), market='US', time='2026-11-06T10:00:00Z'):
    host = next(k for k, v in family.MARKETS.items() if v == market)
    return dict(schemaVersion=1, status='captured', reason='visible_variant_controls_observed',
                capturedAt=time, marketplace=market, asin=asin, selectedAsin=asin,
                url='https://'+host+'/dp/'+asin,
                controls=[dict(containerId='variation_color_name',
                    selector='#variation_color_name li[data-asin] a[href]',
                    source='visible_twister_anchor', asin=a, dataAsin=a,
                    href='https://'+host+'/dp/'+a, label='Label '+a,
                    selectedMarker='swatchSelect' if a == asin else '') for a in targets])


def normalized(asin=A, targets=(A, B), **kwargs):
    value = raw(asin, targets, **kwargs)
    return family.normalize_capture(value, marketplace=value['marketplace'], asin=asin, now=NOW)


def receipt(asin=A, targets=(A, B), **kwargs):
    return dict(captureId='capture-'+asin, captureKind='family', status='captured',
                cycleId='fixture', expectedRevision=1, parentId='search1',
                asin=asin, marketplace='US', startedAt='2026-11-06T09:59:59Z',
                finishedAt='2026-11-06T10:00:01Z', bindingDigest='b'*64,
                collectorSha256=hashlib.sha256(Path(family.__file__).with_name('discovery-family-collector.js').read_bytes()).hexdigest(),
                familyEvidence=normalized(asin, targets, **kwargs))


def hint(asin, detail=B, market='US'):
    host = next(k for k, v in family.MARKETS.items() if v == market)
    return dict(schemaVersion=1, kind='legacy_detail_asin', marketplace=market,
                asin=asin, sourceURL='https://'+host+'/dp/'+asin,
                observedAt='2026-11-06T10:00:00Z', detailAsin=detail)


class FamilyTests(unittest.TestCase):
    def test_empty_evidence_leaves_all_pending_and_original_graph_unchanged(self):
        value = graph(); original = copy.deepcopy(value)
        result = family.assess_graph(value, now=NOW)
        self.assertEqual(value, original)
        self.assertEqual(result['groups'], [])
        self.assertTrue(all(p['status'] == 'pending_verification' for p in result['products']))
        self.assertFalse(result['qualificationEvaluated'])
        self.assertTrue(result['sellerEvidencePreserved'])

    def test_no_db_files_or_network_used(self):
        with patch('builtins.open', side_effect=AssertionError('No I/O')):
            family.assess_graph(graph(), [normalized()], now=NOW)

    def test_reciprocal_import_supports_membership_but_never_suppresses(self):
        result = family.assess_graph(graph(), [normalized(A), normalized(B)], now=NOW)
        self.assertEqual(result['groups'][0]['status'], 'supported_visible_family')
        self.assertFalse(result['groups'][0]['dedupEligible'])
        self.assertIsNone(result['groups'][0]['formalParentAsin'])
        self.assertEqual(family.title_dedup_key(result, 'US', A), 'US:'+A)

    def test_recorded_reciprocal_only_deduplicates_title_planning(self):
        result = family.assess_recorded(graph(), [receipt(A), receipt(B)], now=NOW)
        group = result['groups'][0]
        self.assertTrue(group['dedupEligible'])
        self.assertEqual(group['dedupScope'], ['title_phrase_capture'])
        self.assertTrue(group['preserveSellerCapture'])
        self.assertEqual(family.title_dedup_key(result, 'US', A), family.title_dedup_key(result, 'US', B))
        self.assertEqual(family.title_dedup_key(result, 'US', C), 'US:'+C)

    def test_one_sided_anchor_and_shared_detail_remain_pending(self):
        for evidence in ([normalized(A)], [hint(A), hint(B)]):
            with self.subTest(evidence=evidence):
                result = family.assess_graph(graph(), evidence, now=NOW)
                self.assertEqual(result['pairs'][0]['status'], 'pending_verification')
                self.assertEqual(result['groups'], [])

    def test_no_transitive_group_without_full_clique(self):
        evidence = [receipt(A, (A,B)), receipt(B, (A,B,C)), receipt(C, (B,C))]
        result = family.assess_recorded(graph(), evidence, now=NOW)
        self.assertEqual(len(result['groups']), 1)
        self.assertEqual(result['groups'][0]['status'], 'pending_verification')
        self.assertEqual(result['dedupEligibleGroupCount'], 0)
        self.assertEqual(family.title_dedup_key(result, 'US', A), 'US:'+A)

    def test_complete_clique_can_group(self):
        result = family.assess_recorded(graph(), [receipt(a,(A,B,C)) for a in (A,B,C)], now=NOW)
        self.assertEqual(result['dedupEligibleGroupCount'], 1)
        self.assertEqual(result['groups'][0]['productIds'], ['US:'+a for a in (A,B,C)])

    def test_conflicting_same_time_snapshots_fail_closed(self):
        evidence=[normalized(A,(A,B)),normalized(A,(A,C)),normalized(B),normalized(C,(A,C))]
        result=family.assess_graph(graph(), evidence, now=NOW)
        self.assertEqual(result['groups'], [])
        self.assertTrue(all(p['status']=='pending_verification' for p in result['pairs']))

    def test_order_independence(self):
        a, b = normalized(A), normalized(B)
        x=family.assess_graph(graph(), [a,b], now=NOW)
        y=family.assess_graph(graph(), [b,a], now=NOW)
        self.assertEqual(x,y)

    def test_no_cross_market_merge(self):
        value=graph(); value['products'] += graph((B,), market='UK')['products']
        result=family.assess_graph(value, [hint(A), hint(B,market='UK')], now=NOW)
        self.assertEqual(result['pairs'], [])

    def test_shared_graph_references_are_allowed_without_mutation(self):
        value=graph(); value['nextActions']=value['queue']
        family.assess_graph(value, now=NOW)

    def test_selected_and_href_identity_conflicts(self):
        mutations=[lambda r:r.update(selectedAsin=B),
                   lambda r:r['controls'][1].update(dataAsin=C),
                   lambda r:r['controls'][1].update(href='https://amazon.com/dp/'+C),
                   lambda r:r['controls'][1].update(selectedMarker='swatchSelect'),
                   lambda r:r['controls'][0].update(selectedMarker=''),
                   lambda r:r['controls'][0].update(source='caller_verified'),
                   lambda r:r['controls'][0].update(selector='#recommendations a'),
                   lambda r:r['controls'][0].update(containerId='recommendations')]
        for mutate in mutations:
            value=raw(); mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                family.normalize_capture(value,marketplace='US',asin=A,now=NOW)

    def test_untrusted_boolean_or_parent_claims_rejected(self):
        for field in ('verified','isSameFamily','parentAsin','dedupEligible','authenticated'):
            value=raw(); value[field]=True
            with self.subTest(field=field), self.assertRaises(ValueError):
                family.normalize_capture(value,marketplace='US',asin=A,now=NOW)
        value=normalized(); value['dedupEligible']=True
        with self.assertRaises(ValueError): family.assess_graph(graph(),[value],now=NOW)

    def test_url_attacks_rejected(self):
        urls=['http://amazon.com/dp/'+A,'https://amazon.com.evil.test/dp/'+A,
              'https://user:secret@amazon.com/dp/'+A,'https://amazon.co.uk/dp/'+A,
              'https://amazon.com:8443/dp/'+A,'https://amazon.com/dp/'+A+'#secret',
              'https://amazon.com/dp/'+A+'?ASIN='+A,
              'https://amazon.com/x/../dp/'+A,'https://amazon.com/%2e%2e/dp/'+A,
              'https://amazon.com\\@evil.test/dp/'+A]
        for url in urls:
            value=raw();value['url']=url
            with self.subTest(url=url),self.assertRaises(ValueError):
                family.normalize_capture(value,marketplace='US',asin=A,now=NOW)

    def test_url_tracking_is_not_retained_or_parent_inferred(self):
        value=raw();value['url']+='?token=do-not-save'
        value['controls'][1]['href']+='/ref=twister_B099999999?psc=1'
        result=family.normalize_capture(value,marketplace='US',asin=A,now=NOW)
        self.assertNotIn('do-not-save',json.dumps(result))
        self.assertNotIn('B099999999',json.dumps(result))

    def test_time_controls_and_input_limits(self):
        for value in ('2026-11-06T10:00:00','2099-01-01T00:00:00Z','nope',True):
            item=raw();item['capturedAt']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                family.normalize_capture(item,marketplace='US',asin=A,now=NOW)
        with self.assertRaises(ValueError):
            family.normalize_capture(raw(),marketplace='US',asin=A,started_at='2026-11-06T10:00:01Z',now=NOW)
        item=raw();item['controls']*=101
        with self.assertRaises(ValueError): family.normalize_capture(item,marketplace='US',asin=A,now=NOW)
        with self.assertRaises(ValueError): family.assess_graph(graph(),[normalized()]*201,now=NOW)
        item=graph();item['recursive']=item
        with self.assertRaises(ValueError): family.assess_graph(item,now=NOW)
        item=graph();item['nan']=float('nan')
        with self.assertRaises(ValueError): family.assess_graph(item,now=NOW)

    def test_recorded_receipt_scope_corruption_rejected(self):
        mutations=[{'captureKind':'seller'},{'status':'blocked'},{'cycleId':'other'},
                   {'expectedRevision':2},{'expectedRevision':True},{'parentId':'absent'},
                   {'asin':C},{'marketplace':'UK'},{'collectorSha256':'invalid'},
                   {'bindingDigest':'forged'},{'startedAt':'2026-11-06T10:00:01Z'},
                   {'finishedAt':'2026-11-06T09:00:00Z'}]
        for change in mutations:
            item=receipt();item.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                family.assess_recorded(graph(),[item],now=NOW)
        item=receipt()
        with self.assertRaises(ValueError): family.assess_recorded(graph(),[item,copy.deepcopy(item)],now=NOW)

    def test_freshness_limits_do_not_suppress_old_or_distant_captures(self):
        from datetime import timedelta
        old = family.assess_recorded(graph(), [receipt(A),receipt(B)], now=NOW+timedelta(days=2))
        self.assertEqual(old['dedupEligibleGroupCount'],0)
        self.assertIn('recorded_evidence_expired_for_dedup',old['pairs'][0]['reasonCodes'])
        late = receipt(B,time='2026-11-06T10:16:00Z')
        late.update(startedAt='2026-11-06T10:15:59Z',finishedAt='2026-11-06T10:16:01Z')
        result = family.assess_recorded(graph(),[receipt(A),late],now=NOW)
        self.assertEqual(result['dedupEligibleGroupCount'],0)
        self.assertIn('reciprocal_captures_too_far_apart',result['pairs'][0]['reasonCodes'])

    def test_changed_membership_snapshot_never_combines_old_return_link(self):
        earlier = receipt(A)
        later = receipt(A,(A,C),time='2026-11-06T10:02:00Z')
        later.update(captureId='later-A',startedAt='2026-11-06T10:01:59Z',finishedAt='2026-11-06T10:02:01Z')
        result = family.assess_recorded(graph(),[earlier,later,receipt(B),receipt(C,(A,C))],now=NOW)
        self.assertEqual(result['dedupEligibleGroupCount'],0)
        self.assertFalse(any(p['dedupEligible'] for p in result['pairs']))

    def test_current_source_snapshot_not_old_nearby_capture_is_used(self):
        late = receipt(A,time='2026-11-06T10:20:00Z')
        late.update(captureId='later-A',startedAt='2026-11-06T10:19:59Z',finishedAt='2026-11-06T10:20:01Z')
        result = family.assess_recorded(graph(),[receipt(A),late,receipt(B)],now=NOW)
        self.assertEqual(result['dedupEligibleGroupCount'],0)
        self.assertIn('reciprocal_captures_too_far_apart',result['pairs'][0]['reasonCodes'])

    def test_real_ledger_report_with_shared_references_is_accepted(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory(prefix='family-ledger-test-') as root:
            with patch.dict(os.environ,{'JUNFEI_ACCOUNT_DATA':root}):
                import cyclic_discovery as ledger
            with patch.object(ledger,'DB',Path(root)/'synthetic.sqlite3'):
                event=dict(id='root',kind='keyword',parentId=None,marketplace='US',sourceType='browser_visible',
                    observedAt='2026-01-01T00:00:00Z',asin=A,sourceTitle='Cotton shirt women',phrase='Cotton shirt',
                    url='https://amazon.com/dp/'+A)
                ledger.ingest(1,dict(cycleId='fixture',expectedRevision=0,events=[event]))
                saved=ledger.report(1,'fixture')
                result=family.assess_recorded(saved,[],now=NOW)
                self.assertEqual(result['originalProductCount'],1)
                self.assertEqual(result['groups'],[])
                self.assertIs(saved['queue'],saved['nextActions'])

    def test_inline_radio_evidence_uses_actual_selector_and_no_fabricated_href(self):
        value=raw()
        for control in value['controls']:
            control.update(containerId='inline-twister-row-color_name',
                selector='#inline-twister-row-color_name li[data-asin] input[role="radio"]',
                source='visible_inline_twister_radio',href=None,
                selectedMarker='aria-checked+a-button-selected' if control['asin']==A else '')
        result=family.normalize_capture(value,marketplace='US',asin=A,now=NOW)
        self.assertTrue(all(x['href'] is None for x in result['controls']))
        self.assertEqual(result['collectorVersion'],2)
        value['controls'][1]['href']='https://amazon.com/dp/'+B
        with self.assertRaises(ValueError): family.normalize_capture(value,marketplace='US',asin=A,now=NOW)

    def test_obsolete_collector_receipts_remain_diagnostics_and_new_evidence_recovers(self):
        obsolete=receipt(A)
        obsolete.update(captureId='old-A',collectorSha256='a'*64,familyEvidence={'collectorVersion':0})
        result=family.assess_recorded(graph(),[obsolete,receipt(A),receipt(B)],now=NOW)
        self.assertEqual(result['dedupEligibleGroupCount'],1)
        self.assertEqual(result['historyDiagnostics']['obsoleteCollectorReceiptCount'],1)
        self.assertEqual(result['historyDiagnostics']['currentCollectorReceiptCount'],2)
        self.assertEqual(result['historyDiagnostics']['samples'][0]['reason'],'obsolete_collector_non_authorizing')
        only_old=family.assess_recorded(graph(),[obsolete],now=NOW)
        self.assertEqual(only_old['groups'],[])

    def test_more_than_200_historical_receipts_select_latest_per_source(self):
        records=[]
        for i in range(250):
            item=receipt(A if i%2 else B)
            item['captureId']='receipt-'+str(i)
            records.append(item)
        result=family.assess_recorded(graph(),records,now=NOW)
        self.assertEqual(result['dedupEligibleGroupCount'],1)
        diag=result['historyDiagnostics']
        self.assertEqual(diag['totalReceiptCount'],250)
        self.assertEqual(diag['selectedSourceCount'],2)
        self.assertEqual(diag['supersededReceiptCount'],248)

    def test_more_than_200_sources_are_bounded_without_deleting_graph_branches(self):
        asins=tuple('B'+str(i).zfill(9) for i in range(1,206))
        value=graph(asins);value['events']=[]
        records=[]
        for i,asin in enumerate(asins):
            value['events'].append(dict(id='k'+str(i),kind='keyword',marketplace='US',asin=asin,
                observedAt='2026-11-06T09:00:00Z'))
            item=receipt(asin,(asin,B if asin==A else A))
            item['parentId']='k'+str(i)
            records.append(item)
        result=family.assess_recorded(value,records,now=NOW)
        self.assertEqual(result['historyDiagnostics']['sourceLimitExcludedCount'],5)
        self.assertEqual(result['historyDiagnostics']['selectedSourceCount'],200)
        self.assertEqual(result['originalProductCount'],205)
        self.assertEqual(len(result['products']),205)
        self.assertEqual(result['dedupEligibleGroupCount'],0)

    def test_conflicting_same_time_label_receipt_is_not_hidden_by_latest_selection(self):
        altered=raw()
        altered['controls'][1]['label']='Conflicting color'
        item=receipt(A);item['captureId']='conflict-A'
        item['familyEvidence']=family.normalize_capture(altered,marketplace='US',asin=A,now=NOW)
        result=family.assess_recorded(graph(),[receipt(A),item,receipt(B)],now=NOW)
        self.assertEqual(result['dedupEligibleGroupCount'],0)
        self.assertEqual(result['historyDiagnostics']['conflictingSourceCount'],1)

    def test_large_valid_history_obeys_aggregate_byte_budget_without_poisoning_plan(self):
        asins=tuple('B'+str(i).zfill(9) for i in range(1000,1040))
        value=graph((A,B)+asins)
        extras=tuple('Z'+str(i).zfill(9) for i in range(150))
        records=[]
        # These small recent reciprocal captures remain usable even when valid
        # large historical source snapshots exceed the aggregate byte budget.
        for asin in (A,B):
            item=receipt(asin,time='2026-11-06T10:01:00Z')
            item.update(startedAt='2026-11-06T10:00:59Z',finishedAt='2026-11-06T10:01:01Z')
            records.append(item)
        for asin in asins:
            capture=raw(asin,(asin,)+extras)
            for control in capture['controls']:
                control['label']='x'*300
            item=receipt(asin,(asin,extras[0]))
            item['familyEvidence']=family.normalize_capture(capture,marketplace='US',asin=asin,now=NOW)
            records.append(item)
        # Keep conflict accounting even for a source excluded by byte budget.
        conflict=copy.deepcopy(records[2]);conflict['captureId']='conflicting-large-source'
        capture=raw(asins[0],(asins[0],)+extras)
        for control in capture['controls']:
            control['label']='y'*300
        conflict['familyEvidence']=family.normalize_capture(capture,marketplace='US',asin=asins[0],now=NOW)
        records.append(conflict)
        total=len(json.dumps([r['familyEvidence'] for r in records],ensure_ascii=True,allow_nan=False))
        self.assertGreater(total,family.MAX_EVIDENCE_BYTES)
        result=family.assess_recorded(value,records,now=NOW)
        diag=result['historyDiagnostics']
        self.assertGreater(diag['byteLimitExcludedCount'],0)
        self.assertEqual(diag['sourceLimitExcludedCount'],0)
        self.assertLessEqual(diag['selectedEvidenceBytes'],family.MAX_EVIDENCE_BYTES)
        self.assertEqual(diag['selectedEvidenceBytes'],len(json.dumps(result['evidence'],ensure_ascii=True,allow_nan=False)))
        self.assertEqual(diag['selectedSourceCount']+diag['byteLimitExcludedCount'],len(asins)+2)
        self.assertEqual(diag['conflictingSourceCount'],1)
        self.assertIn('US:'+asins[0],diag['byteLimitExcludedSourceIds'])
        self.assertEqual(result['dedupEligibleGroupCount'],1)
        self.assertEqual(result['originalProductCount'],len(asins)+2)
        self.assertEqual(len(result['products']),len(asins)+2)
        excluded=diag['byteLimitExcludedSourceIds'][0].split(':')[1]
        self.assertEqual(family.title_dedup_key(result,'US',excluded),'US:'+excluded)

    def test_saved_actual_pair_is_only_a_weak_shared_detail_hint(self):
        root=Path(__file__).resolve().parent.parent/'outputs'/'next-search-20261106'
        if not (root/'audited-chronological-graph.json').is_file():
            self.skipTest('Local real observation fixture not packaged')
        saved=json.loads((root/'audited-chronological-graph.json').read_text(encoding='utf-8-sig'))
        chain=json.loads((root/'source-chain.json').read_text(encoding='utf-8-sig'))
        source=chain['source'];candidate=next(x for x in chain['reviewedCandidates'] if x['asin']=='B0HJVZ4GTH')
        evidence=[dict(schemaVersion=1,kind='legacy_detail_asin',marketplace='US',asin=x['asin'],sourceURL=x['url'],observedAt=x['observedAt'],detailAsin=x['detailBulletASIN']) for x in (source,candidate)]
        before=copy.deepcopy(saved)
        result=family.assess_graph(saved,evidence,now=NOW)
        self.assertEqual(saved,before)
        self.assertEqual(result['groups'],[])
        self.assertEqual(result['pairs'][0]['productIds'],['US:B0HJVJJP8T','US:B0HJVZ4GTH'])
        self.assertEqual(result['pairs'][0]['status'],'pending_verification')
        self.assertFalse(result['pairs'][0]['dedupEligible'])
        self.assertIsNone(result['pairs'][0]['formalParentAsin'])


if __name__=='__main__':
    unittest.main()
