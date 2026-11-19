from datetime import date, timedelta
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import json
import agent_selection as selection
import agent_center as agent


class SelectionTests(unittest.TestCase):
    def test_any_seller_policy_accepts_candidate_rank_without_weakening_exact_match(self):
        task = self.task()
        evidence = task['snapshot']['product']['selectionEvidence']
        evidence['matchedAsin'] = evidence['asin']
        evidence['matchedRank']['asin'] = evidence['asin']
        self.assertFalse(selection.inspect(task)['ok'])  # preserve legacy snapshot
        task['selectionPolicy'] = {'sameProductRankPolicy': {
            'seller_scope': 'any_seller', 'instruction': '同款任意卖家有排名'}}
        self.assertTrue(selection.inspect(task)['ok'])
        self.assertIn('候选自身', selection.evidence_template(task)['_instructions']['matchedRank'])
        for field, value in [('match', 'similar'), ('matchSource', {}),
                             ('matchedRank', dict(evidence['matchedRank'], value=None)),
                             ('frontSearch', {})]:
            original = evidence[field]
            evidence[field] = value
            self.assertFalse(selection.inspect(task)['ok'])
            evidence[field] = original
        task['selectionPolicy']['sameProductRankPolicy']['instruction'] = ''
        self.assertFalse(selection.inspect(task)['ok'])

    def test_current_policy_snapshots_any_seller_rule(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(selection, 'project_root', return_value=Path(directory)):
            root = Path(directory)
            (root / 'automation').mkdir()
            rule = {'seller_scope': 'any_seller', 'instruction': '任意卖家'}
            (root / 'automation/config.json').write_text(json.dumps({'selection': {
                'same_product_rank_policy': rule}}), encoding='utf-8')
            self.assertEqual(selection.current_policy()['sameProductRankPolicy'], rule)

    def test_thirty_day_window_and_legacy_seven_day_snapshot(self):
        task = self.task()
        e = task['snapshot']['product']['selectionEvidence']
        e['sellerListedDate'] = (date.today()-timedelta(days=30)).isoformat()
        self.assertFalse(selection.inspect(task)['ok'])
        task['selectionPolicy'] = {'windowDays':30}
        self.assertTrue(selection.inspect(task)['ok'])
        e['sellerListedDate'] = (date.today()-timedelta(days=31)).isoformat()
        self.assertFalse(selection.inspect(task)['ok'])
        e['sellerListedDate'] = (date.today()+timedelta(days=1)).isoformat()
        self.assertFalse(selection.inspect(task)['ok'])
        for invalid in (0, -1, True, '30', 366):
            task['selectionPolicy']['windowDays'] = invalid
            self.assertFalse(selection.inspect(task)['ok'])

    def test_generic_only_and_user_patent_skip_need_truthful_evidence(self):
        task=self.task();instruction='用户要求不查专利'
        task['selectionPolicy']={'brandPolicy':{'mode':'generic_only'},'patentSearchPolicy':{'mode':'skip_by_user_instruction','instruction':instruction}}
        checks=task['snapshot']['product']['selectionEvidence']['ipChecks']
        checks['brand'].update(observedBrand='Generic',url='https://www.amazon.com/dp/B012345678',raw='Brand: Generic')
        for key in ('designPatent','utilityPatent'):
            checks[key]={'status':'skipped_by_user','searchPerformed':False,'instruction':instruction,'judgment':'按用户要求未检索，不作无专利结论'}
        self.assertTrue(selection.inspect(task)['ok'])
        checks['brand']['raw']='Brand: Kxyudcn'
        self.assertFalse(selection.inspect(task)['ok'])
        checks['brand']['raw']='Brand: Generic'
        checks['utilityPatent']['status']='clear'
        self.assertFalse(selection.inspect(task)['ok'])
        checks['utilityPatent']['status']='skipped_by_user'
        task['selectionPolicy']={}
        self.assertFalse(selection.inspect(task)['ok'])

    def test_design_screening_global_policy_requires_search_not_drawings(self):
        task=self.task();item=task['snapshot']['product']['selectionEvidence']['ipChecks']['designPatent']
        item.update(status='no_obvious_match',searchPerformed=True,obviousOverallMatchFound=False,drawingsAvailable=False)
        self.assertFalse(selection.inspect(task)['ok'])
        task['selectionPolicy']={'designPatentPolicy':{'mode':'obvious_overall_match_only','instruction':'以后所有产品'}}
        self.assertTrue(selection.inspect(task)['ok'])
        for field,value in [('searchPerformed',False),('obviousOverallMatchFound',True),('raw','')]:
            old=item[field];item[field]=value
            self.assertFalse(selection.inspect(task)['ok']);item[field]=old

    def test_user_default_supplier_image_policy_is_explicit_and_does_not_claim_supplier_license(self):
        task=self.task();item=task['snapshot']['product']['selectionEvidence']['ipChecks']['imageRights']
        item.update(status='user_default',basis='user_default_supplier_use_not_supplier_license',
                    url='https://detail.1688.com/offer/952542058876.html',visuallyReviewed=True,noUnauthorizedMarks=True)
        self.assertFalse(selection.inspect(task)['ok'])
        task['selectionPolicy']={'supplierImagePolicy':'user_default_supplier_images',
                                 'supplierImageAuthorization':{'instruction':'用户默认可用'}}
        self.assertTrue(selection.inspect(task)['ok'])
        for change in ({'noUnauthorizedMarks':False},{'url':'https://www.amazon.com/dp/B012345678'},
                       {'url':'https://detail.1688.com.evil.test/offer/952542058876.html'}, {'visuallyReviewed':False}):
            old=dict(item);item.update(change)
            self.assertFalse(selection.inspect(task)['ok']);item.clear();item.update(old)

    def test_local_ledger_rechecks_file_hash_duplicates_and_daily_seller_quota(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(selection, 'project_root', return_value=Path(directory)):
            root = Path(directory)
            (root / 'automation').mkdir()
            (root / 'automation/config.json').write_text(json.dumps({'selection': {
                'selected_ledger': 'ledger.csv', 'max_per_store_per_day': 2}}), encoding='utf-8')
            path = root / 'ledger.csv'
            header = 'marketplace,asin,selected_at,seller_id\n'
            path.write_text(header, encoding='utf-8')
            task = self.task()
            e = task['snapshot']['product']['selectionEvidence']
            r = selection.local_ledger_review(e)
            self.assertTrue(r['ok'])
            self.assertFalse(r['reservation'])
            e['dailyQuotaSource'] = dict(r, captureType='local_selection_ledger')
            self.assertTrue(selection.inspect(task)['ok'])
            e['dailyQuotaSource']['ledgerPath'] = str(root / 'other.csv')
            self.assertFalse(selection.inspect(task)['ok'])
            e['dailyQuotaSource'] = dict(r, captureType='local_selection_ledger')
            today = date.today().isoformat()
            path.write_text(header + f'US,B099999999,{today}T12:00:00+08:00,other\n', encoding='utf-8')
            self.assertFalse(selection.inspect(task)['ok'])  # stale hash, even though quota is still available
            e['dailyQuotaSource'] = dict(selection.local_ledger_review(e), captureType='local_selection_ledger')
            self.assertTrue(selection.inspect(task)['ok'])
            path.write_text(header + f'US,B012345678,{today}T12:00:00+08:00,other\n', encoding='utf-8')
            self.assertTrue(selection.local_ledger_review(e)['duplicate'])
            self.assertFalse(selection.local_ledger_review(e)['ok'])
            path.write_text(header + ''.join(f'US,B09999999{i},{today}T12:00:00+08:00,seller\n' for i in range(2)), encoding='utf-8')
            self.assertEqual(selection.local_ledger_review(e)['sameSellerToday'], 2)
            self.assertFalse(selection.local_ledger_review(e)['ok'])
            path.write_text(header + f'US,B099999999,{today}T12:00:00+08:00,\n', encoding='utf-8')
            self.assertIn('Seller ID', selection.local_ledger_review(e)['reason'])
            path.write_text(header + 'US,B099999999,not-a-date,seller\n', encoding='utf-8')
            self.assertFalse(selection.local_ledger_review(e)['ok'])

    def test_local_ledger_converts_utc_dates_to_china_day_and_rejects_old_proof(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(selection, 'project_root', return_value=Path(directory)):
            root = Path(directory)
            (root / 'automation').mkdir()
            (root / 'automation/config.json').write_text(json.dumps({'selection': {
                'selected_ledger': 'ledger.csv', 'max_per_store_per_day': 2}}), encoding='utf-8')
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            (root / 'ledger.csv').write_text('marketplace,asin,selected_at,seller_id\n' +
                f'US,B099999999,{yesterday}T18:00:00Z,seller\n', encoding='utf-8')
            e = self.task()['snapshot']['product']['selectionEvidence']
            self.assertEqual(selection.local_ledger_review(e)['sameSellerToday'], 1)
            e['collectionDate'] = yesterday
            self.assertFalse(selection.local_ledger_review(e)['ok'])

    def task(self):
        today = date.today().isoformat()
        def src(raw='Observed source text'):
            return dict(url='https://www.sellersprite.com/', checkedAt=today, raw=raw)
        evidence = dict(asin='B012345678', marketplace='US', sellerId='seller', sellerCountry='CN',
            sellerCountrySource=src(), fulfillment='FBM', fulfillmentSource=src(),
            collectionDate=today, sellerListedDate=today, freshnessScope='seller_listing', freshnessSource=src(),
            frontSearch=dict(src(), url='https://www.amazon.com/s?k=door+seal', status='opened'),
            matchedAsin='B087654321', match='strong', matchSource=src(),
            matchedRank=dict(src('Sales rank: 1,234'), source='SellerSprite same-product search', asin='B087654321', value=1234),
            ipChecks={k: dict(src(), status='clear', query='Recorded search', judgment='Recorded assessment') for k in selection.IP_CHECKS},
            dailyQuotaLedgerVerified=True, dailyQuotaSource=src())
        return dict(profile={'marketplace': 'US'}, snapshot={'product': {
            'selectionResearch': {'reference': {'asin': 'B012345678'}}, 'selectionEvidence': evidence}})

    def test_product_listing_policy_requires_explicit_scope_and_sprite_date(self):
        task = self.task()
        e = task['snapshot']['product']['selectionEvidence']
        e.update(productListedDate=date.today().isoformat(), freshnessScope=selection.PRODUCT_DATE)
        e['freshnessSource']['raw'] = '上架日期：' + e['productListedDate']
        self.assertFalse(selection.inspect(task)['ok'])  # legacy tasks cannot opt themselves in
        task['selectionPolicy'] = {'freshnessBasis': selection.PRODUCT_DATE}
        self.assertTrue(selection.inspect(task)['ok'])
        self.assertEqual(selection.evidence_template(task)['freshnessScope'], selection.PRODUCT_DATE)
        for key, value in [('url', 'https://www.amazon.com/dp/B012345678'),
                           ('url', 'https://sellersprite.com.evil.test/'),
                           ('raw', 'Date First Available: ' + e['productListedDate']),
                           ('raw', '上架月份：202611')]:
            old = e['freshnessSource'][key]
            e['freshnessSource'][key] = value
            self.assertFalse(selection.inspect(task)['ok'])
            e['freshnessSource'][key] = old
        for delta in (-8, 1):
            e['productListedDate'] = (date.today() + timedelta(days=delta)).isoformat()
            e['freshnessSource']['raw'] = '上架日期：' + e['productListedDate']
            self.assertFalse(selection.inspect(task)['ok'])

    def test_mcp_rank_requires_exact_asin_integer_and_credential_free_endpoint(self):
        import json
        task = self.task()
        rank = task['snapshot']['product']['selectionEvidence']['matchedRank']
        rank.update(captureType='sellersprite_mcp_asin_detail', url='https://mcp.sellersprite.com/mcp',
                    raw=json.dumps({'asin':'B087654321','bsrRank':1234}))
        self.assertTrue(selection.inspect(task)['ok'])
        for payload in ({'asin':'B012345678','bsrRank':1234}, {'asin':'B087654321','bsrRank':'1234'},
                        {'asin':'B087654321','bsrRank':True}, {'asin':'B087654321','bsrRank':1235}):
            rank['raw'] = json.dumps(payload)
            self.assertFalse(selection.inspect(task)['ok'])
        rank['raw'] = json.dumps({'asin':'B087654321','bsrRank':1234})
        for url in ('https://mcp.sellersprite.com/mcp?secret-key=not-a-key',
                    'https://example.com/mcp', 'https://mcp.sellersprite.com/other', 'https://mcp.sellersprite.com:bad/mcp'):
            rank['url'] = url
            self.assertFalse(selection.inspect(task)['ok'])

    def test_complete_fields_are_not_formal_selection(self):
        result = selection.inspect(self.task())
        self.assertTrue(result['ok'])
        self.assertIn('不自动写入正式入选表', result['note'])

    def test_wrong_rank_and_freshness_sources_fail(self):
        for key, value in [('matchedRank', {'source': 'Amazon BSR', 'value': 1}),
                           ('freshnessScope', 'firstAvailable'), ('matchedAsin', 'B012345678'),
                           ('dailyQuotaLedgerVerified', 'true'),
                           ('sellerListedDate', (date.today()-timedelta(days=8)).isoformat())]:
            with self.subTest(key=key):
                task = self.task()
                task['snapshot']['product']['selectionEvidence'][key] = value
                self.assertFalse(selection.inspect(task)['ok'])

    def test_sellersprite_rank_must_match_visible_numeric_source(self):
        invalid = [
            {'raw': '--', 'value': 1234},
            {'raw': '****', 'value': 1234},
            {'raw': 'Sales rank 987', 'value': 1234},
            {'raw': 'Price $1,234; 80 reviews', 'value': 1234},
            {'raw': 'Sales rank: 1,234; BSR: 5,678', 'value': 1234},
            {'raw': '1,234', 'value': 1234, 'url': 'https://amazon.com/s?k=seal'},
        ]
        for override in invalid:
            with self.subTest(override=override):
                task = self.task()
                rank = task['snapshot']['product']['selectionEvidence']['matchedRank']
                rank.update(override)
                self.assertFalse(selection.inspect(task)['ok'])

        task = self.task()
        rank = task['snapshot']['product']['selectionEvidence']['matchedRank']
        rank['raw'] = 'Sales rank: 1,234'
        self.assertTrue(selection.inspect(task)['ok'])

    def test_sellersprite_rank_suggestions_are_labeled_and_never_promote_gate(self):
        self.assertEqual(selection.sellersprite_rank_values('BSR: 12,345 · Price $8.99'), [12345])
        self.assertEqual(selection.sellersprite_rank_values('销量排名：2,345; 月销量 90'), [2345])
        self.assertEqual(selection.sellersprite_rank_values('Price $1,234; 80 reviews'), [])
        self.assertEqual(selection.sellersprite_rank_values('Sales rank 1,234; BSR 5,678'), [1234, 5678])
        task = self.task()
        task['snapshot']['product']['selectionObservations'] = [{
            'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_sellersprite_search',
            'url': 'https://www.sellersprite.com/v2/product-research', 'capturedAt': date.today().isoformat() + 'T10:00:00Z',
            'sellerSprite': {'rows': [{'asin': 'B087654321', 'text': 'BSR: 12,345 · $8.99'}]},
        }]
        draft = selection.evidence_draft(task)
        row = draft['_observations']['sellerSpriteRows'][0]
        self.assertEqual(row['rankSuggestions'], [12345])
        self.assertEqual(draft['matchedAsin'], '')
        self.assertIsNone(draft['matchedRank']['value'])
        task['snapshot']['product']['selectionEvidence'] = draft
        self.assertFalse(selection.inspect(task)['ok'])

    def test_sellersprite_listing_date_suggestions_require_explicit_iso_label(self):
        self.assertEqual(selection.sellersprite_listing_dates('Listing date: 2026-10-29 · Price $9.99'), ['2026-10-29'])
        self.assertEqual(selection.sellersprite_listing_dates('上架日期：2026-10-29'), ['2026-10-29'])
        self.assertEqual(selection.sellersprite_listing_dates('上架时间：2026-10-29'), ['2026-10-29'])
        self.assertEqual(selection.sellersprite_listing_dates('Date First Available: 2026-10-29'), [])
        self.assertEqual(selection.sellersprite_listing_dates('Listed on 2026-02-30'), [])
        self.assertEqual(selection.sellersprite_listing_dates('Listing date: 10/29/2026'), [])
        task = self.task()
        task['snapshot']['product']['selectionObservations'] = [{
            'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_sellersprite_search',
            'url': 'https://www.sellersprite.com/v2/product-research', 'capturedAt': date.today().isoformat() + 'T10:00:00Z',
            'sellerSprite': {'rows': [{'asin': 'B087654321', 'text': 'Listing date: 2026-10-29'}]},
        }]
        draft = selection.evidence_draft(task)
        row = draft['_observations']['sellerSpriteRows'][0]
        self.assertEqual(row['productListedDateSuggestions'], ['2026-10-29'])
        self.assertEqual(draft['sellerListedDate'], '')
        self.assertEqual(draft['freshnessScope'], 'seller_listing')
        task['snapshot']['product']['selectionEvidence'] = draft
        self.assertFalse(selection.inspect(task)['ok'])

    def test_malformed_nested_evidence_is_a_failure_not_exception(self):
        for key in ('ipChecks', 'matchedRank', 'frontSearch', 'sellerCountrySource'):
            for value in (None, [], 'invalid', {'url': {}}):
                with self.subTest(key=key, value=value):
                    task = self.task()
                    task['snapshot']['product']['selectionEvidence'][key] = value
                    self.assertFalse(selection.inspect(task)['ok'])

    def test_legacy_existing_product_is_not_recorded_as_scout_pass(self):
        task = self.task()
        del task['snapshot']['product']['selectionResearch']
        result = selection.inspect(task)
        self.assertTrue(result['skipped'])
        self.assertIn('不记录为新入选', result['note'])

    def test_template_is_candidate_specific_and_intentionally_blocked(self):
        task = self.task()
        template = selection.evidence_template(task)
        self.assertEqual(template['asin'], 'B012345678')
        self.assertEqual(template['marketplace'], 'US')
        self.assertEqual(set(template['ipChecks']), set(selection.IP_CHECKS))
        task['snapshot']['product']['selectionEvidence'] = template
        result = selection.inspect(task)
        self.assertFalse(result['ok'])
        self.assertTrue(any('Seller ID' in issue for issue in result['issues']))
        self.assertTrue(any('imageRights' in issue for issue in result['issues']))

    def test_template_not_created_for_non_candidate(self):
        self.assertIsNone(selection.evidence_template({'snapshot': {'product': {}}, 'profile': {'marketplace': 'US'}}))

    def test_observation_draft_prefills_sources_but_never_clears_selection_gate(self):
        today = date.today().isoformat()
        task = self.task()
        product = task['snapshot']['product']
        product['selectionObservations'] = [
            {'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_visible_product_page',
             'url': 'https://www.amazon.com/dp/B012345678', 'capturedAt': today + 'T10:00:00+00:00',
             'fields': {'sellerText': 'Sold by Example', 'fulfillmentText': 'Ships from Amazon'}},
            {'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_front_search',
             'url': 'https://www.amazon.com/s?k=door+seal', 'capturedAt': today + 'T10:01:00+00:00',
             'search': {'query': 'door seal', 'resultText': 'Results for door seal',
                        'results': [{'asin': 'B087654321', 'title': 'A possible match'}]}},
            {'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_sellersprite_search',
             'url': 'https://www.sellersprite.com/v2/product-research', 'capturedAt': today + 'T10:02:00+00:00',
             'sellerSprite': {'rows': [{'asin': 'B087654321', 'text': 'BSR --'}]}},
        ]
        draft = selection.evidence_draft(task)
        self.assertEqual(draft['frontSearch']['status'], 'opened')
        self.assertIn('door seal', draft['frontSearch']['raw'])
        self.assertEqual(draft['sellerCountrySource']['raw'], '')
        self.assertEqual(draft['fulfillmentSource']['raw'], 'Ships from Amazon')
        self.assertEqual(draft['sellerCountry'], '')
        self.assertEqual(draft['fulfillment'], '')
        self.assertEqual(draft['matchedAsin'], '')
        self.assertIsNone(draft['matchedRank']['value'])
        self.assertEqual(draft['_observations']['sellerSpriteRows'][0]['status'], 'unverified_observation')
        product['selectionEvidence'] = draft
        self.assertFalse(selection.inspect(task)['ok'])
        public = agent.public(task)
        self.assertIn('selectionEvidenceDraft', public)
        self.assertNotIn('snapshot', public)

    def test_observation_draft_ignores_other_candidate_observations(self):
        task = self.task()
        task['snapshot']['product']['selectionObservations'] = [{
            'asin': 'B099999999', 'marketplace': 'US', 'captureType': 'browser_front_search',
            'url': 'https://www.amazon.com/s?k=wrong', 'capturedAt': date.today().isoformat() + 'T10:00:00Z',
            'search': {'query': 'wrong', 'resultText': 'wrong candidate'},
        }]
        draft = selection.evidence_draft(task)
        self.assertEqual(draft['frontSearch']['status'], 'not_opened')
        self.assertEqual(draft['_observations']['sellerSpriteRows'], [])

    def test_seller_profile_address_prefills_its_own_source_without_certifying_country(self):
        task = self.task()
        task['snapshot']['product']['selectionObservations'] = [{
            'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_seller_profile',
            'url': 'https://www.amazon.com/sp?seller=SELLER12345',
            'capturedAt': date.today().isoformat() + 'T10:00:00Z',
            'sellerProfile': {'sellerId': 'SELLER12345', 'raw': 'Business Address: Hainan CN'},
        }]
        draft = selection.evidence_draft(task)
        self.assertEqual(draft['sellerCountrySource']['raw'], 'Business Address: Hainan CN')
        self.assertIn('/sp?seller=', draft['sellerCountrySource']['url'])
        self.assertEqual(draft['sellerCountry'], '')
        self.assertEqual(draft['sellerId'], '')
        self.assertEqual(draft['_observations']['sellerProfileSellerId'], 'SELLER12345')
        task['snapshot']['product']['selectionEvidence'] = draft
        self.assertFalse(selection.inspect(task)['ok'])

    def test_cross_source_candidates_are_prioritized_for_review_without_becoming_match_evidence(self):
        task = self.task()
        task['snapshot']['product']['selectionObservations'] = [
            {'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_front_search',
             'url': 'https://www.amazon.com/s?k=door+seal', 'capturedAt': date.today().isoformat() + 'T10:00:00Z',
             'search': {'query': 'door seal', 'resultText': 'results', 'results': [
                 {'asin': 'B087654321', 'title': 'Brown Door Seal'}, {'asin': 'B099999999', 'title': 'Other item'}]}},
            {'asin': 'B012345678', 'marketplace': 'US', 'captureType': 'browser_sellersprite_search',
             'url': 'https://www.sellersprite.com/v2/product-research', 'capturedAt': date.today().isoformat() + 'T10:02:00Z',
             'sellerSprite': {'rows': [
                 {'asin': 'B099999999', 'text': 'Sales rank: 25'},
                 {'asin': 'B087654321', 'text': 'Sales rank: 12,345'}]}},
        ]
        draft = selection.evidence_draft(task)
        rows = draft['_observations']['sellerSpriteRows']
        self.assertEqual(rows[0]['asin'], 'B087654321')
        self.assertTrue(rows[0]['alsoInAmazonSearch'])
        self.assertEqual(rows[0]['amazonSearchTitles'], ['Brown Door Seal'])
        self.assertEqual(rows[0]['reviewPriority'], 'cross_source_review')
        self.assertEqual(draft['matchedAsin'], '')
        self.assertEqual(draft['match'], '')
        self.assertIsNone(draft['matchedRank']['value'])
        self.assertFalse(selection.inspect({**task, 'snapshot': {'product': {
            **task['snapshot']['product'], 'selectionEvidence': draft}}})['ok'])


if __name__ == '__main__':
    unittest.main()
