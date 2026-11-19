import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ivyea_copy_core
import ivyea_listing_trial as trial
import provider


class KeywordHandoffTests(unittest.TestCase):
    def test_oversized_record_does_not_hide_later_selected_keywords(self):
        report = {'source': 'sellersprite', 'keywords': [
            {'phrase': 'oversized evidence cardigan', 'placement': 'title', 'selected': True,
             'metrics': [{'asin': f'B{i:09}', 'searches': 12000, 'updatedTime': '2026-11-13'} for i in range(60)]},
            {'phrase': 'cardigan with pockets', 'placement': 'bullets', 'selected': True,
             'metrics': [{'seed': 'cardigan', 'searches': 3000}]},
        ]}
        packing = trial.keyword_input_report({'competitorResearch': {'US': report}}, 'US')
        self.assertEqual([row['phrase'] for row in packing['keywords']], ['cardigan with pockets'])
        self.assertEqual(packing['omitted'][0]['reason'], 'data_limit')
        self.assertEqual(packing['omitted'][0]['phrase'], 'oversized evidence cardigan')
        self.assertLessEqual(packing['dataCharacters'], trial.DATA_LIMIT)

    def test_five_bullet_terms_get_budget_before_extra_title_synonyms(self):
        metrics = [{'asin': f'B00000000{i}', 'searches': 12000, 'purchases': 1234,
                    'purchaseRate': .1028, 'trafficPercentage': 18.8, 'naturalRank': i,
                    'month': '2026-11', 'updatedTime': '2026-11-13 12:34:56'} for i in range(5)]
        selected = [{'phrase': phrase, 'selected': True, 'placement': 'title', 'metrics': metrics}
                    for phrase in ('womens cardigan', 'long cardigan sweater')]
        selected += [{'phrase': f'bullet phrase {i}', 'selected': True, 'placement': 'bullets',
                      'metrics': [{'seed': 'cardigan', 'searches': 2000}]} for i in range(5)]
        packing = trial.keyword_input_report({'competitorResearch': {'US': {'source': 'sellersprite', 'keywords': selected}}}, 'US')
        phrases = [row['phrase'] for row in packing['keywords']]
        self.assertEqual(phrases[0], 'womens cardigan')
        self.assertTrue(all(f'bullet phrase {i}' in phrases for i in range(5)))
        self.assertLessEqual(packing['dataCharacters'], 3000)

    def test_duplicate_selected_phrase_merges_metrics_and_keeps_sources(self):
        shared = {'searches': 3000, 'purchases': 100}
        keywords = [
            {'phrase': 'Cardigan with Pockets', 'selected': True, 'placement': 'bullets',
             'metrics': [{**shared, 'seed': 'cardigan', 'seedSource': 'reverse'}]},
            {'phrase': 'cardigan with pockets', 'selected': True, 'placement': 'bullets',
             'metrics': [{**shared, 'seed': 'knit cardigan', 'seedSource': 'product_facts'},
                         {**shared, 'seed': 'cardigan', 'seedSource': 'reverse'}]},
        ]
        packing = trial.keyword_input_report({'competitorResearch': {'US': {'source': 'sellersprite', 'keywords': keywords}}}, 'US')
        self.assertEqual(len(packing['keywords']), 1)
        self.assertEqual(packing['keywords'][0]['metrics'], [{**shared, 'seedSources': {
            'reverse': ['cardigan'], 'product_facts': ['knit cardigan']}}])
        self.assertEqual(packing['omitted'], [])

    def test_selected_invalid_records_have_auditable_omission_reasons(self):
        report = {'source': 'sellersprite', 'keywords': [
            {'phrase': 'without metrics', 'selected': True, 'placement': 'bullets'},
            {'phrase': 'unknown position', 'selected': True, 'placement': 'unsupported', 'metrics': [{'seed': 'cardigan'}]},
            {'phrase': 'cardigan with pockets', 'selected': True, 'placement': 'bullets', 'metrics': [{'seed': 'cardigan', 'searches': 3000}]},
        ]}
        packing = trial.keyword_input_report({'competitorResearch': {'US': report}}, 'US')
        self.assertEqual([row['reason'] for row in packing['omitted']], ['missing_metrics', 'invalid_placement'])

    def test_default_copy_persists_exact_input_and_omission_audit(self):
        product = {'name': 'Cardigan', 'features': 'Front pockets', 'packageContents': '1 x cardigan',
                   'competitorResearch': {'US': {'source': 'sellersprite', 'keywords': [
                       {'phrase': 'oversized evidence cardigan', 'placement': 'title', 'selected': True,
                        'metrics': [{'asin': f'B{i:09}', 'searches': 12000} for i in range(80)]},
                       {'phrase': 'cardigan with pockets', 'placement': 'bullets', 'selected': True,
                        'metrics': [{'seed': 'cardigan', 'searches': 3000}]},
                   ]}}}
        draft = {'title': "Women's Knit Cardigan with Front Pockets and Button Front Closure", 'highlights': 'A cardigan with pockets', 'bullets': self.rewrite_bullets(),
                 'description': 'Cardigan for Layering\nFeature: Front pockets\n\n1 Pcs x cardigan',
                 'terms': 'outerwear garment apparel layering weekend daily casual travel walking streetwear classic wardrobe '
                          'autumn coldseason outdoor commute leisure clothing overlayer packing workday transitional midweight styling relaxed',
                 'warnings': '', 'zh': ''}
        raw = {'choices': [{'message': {'content': json.dumps(draft)}}]}
        with tempfile.TemporaryDirectory() as temp, patch.object(provider.app_paths, 'DATA', Path(temp)), \
             patch.object(provider, 'text_settings', return_value={'api_key': 'fixture', 'model': 'fixture'}), \
             patch.object(provider, 'text_completion', return_value=raw) as generate, \
             patch.object(provider, 'polish_listing', side_effect=lambda value, **_: value), \
             patch.object(provider, 'review_listing_bullets', return_value=[]):
            copy = provider.generate_listing(product, 'US')['copy']
        payload = json.loads(generate.call_args.args[0]['messages'][1]['content'])
        actual = payload['Competitor Data (from market research)']
        self.assertEqual(copy['generationKeywordInput'], actual)
        self.assertEqual(copy['generationKeywordInputAudit']['keywords'], actual['keywords'])
        self.assertEqual(copy['generationKeywordInputAudit']['omitted'][0]['reason'], 'data_limit')
        self.assertIn('未入模关键词：oversized evidence cardigan', copy['warnings'])
        self.assertLessEqual(len(json.dumps(actual, ensure_ascii=False)), 3000)

    @staticmethod
    def rewrite_bullets():
        return '\n'.join(f'[Topic {i}] '+('Wear this cardigan with pockets. ' if i == 1 else f'Confirmed detail {i}. ')+str(i)*250+'.'
                         for i in range(1, 6))

    def rewrite_request(self, bullets):
        return {'field': 'bullets', 'market': 'US', 'mode': 'natural', 'text': bullets,
                'product': {'name': 'Cardigan', 'features': 'Front pockets', 'competitorResearch': {'US': {'keywords': [
                    {'phrase': 'cardigan with pockets', 'selected': True, 'placement': 'bullets'}]}}}}

    def test_clean_field_rewrite_gets_one_review_and_no_repair_call(self):
        bullets = self.rewrite_bullets()
        with patch.object(provider, 'research_json', return_value={'text': bullets}), \
             patch('visual_studio.model_json', return_value={'issues': []}) as model:
            self.assertEqual(provider.rewrite_field(self.rewrite_request(bullets))['text'], bullets)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.call_args.kwargs['purpose'], 'listing_bullet_review')

    def test_field_rewrite_repairs_regex_failure_only_and_keeps_passed_lines(self):
        clean = self.rewrite_bullets()
        bad = clean.replace('Wear this cardigan with pockets.', 'This cardigan with pockets has front pockets.')
        with patch.object(provider, 'research_json', return_value={'text': bad}), \
             patch('visual_studio.model_json', side_effect=[{'issues': []},
                 {'revisions': [{'bullet': 1, 'text': clean.splitlines()[0]}]}, {'issues': []}]) as model:
            output = provider.rewrite_field(self.rewrite_request(clean))['text']
        self.assertEqual(output, clean)
        self.assertEqual(model.call_args_list[1].args[1]['rewrite_bullets'], [1])
        self.assertEqual(model.call_args_list[2].args[1]['review_bullets'], [1])
        self.assertEqual(model.call_args_list[1].args[1]['draft_bullet_keyword_hits'],
                         [{'phrase': 'cardigan with pockets', 'bullets': [1]}])

    def test_field_rewrite_repairs_only_semantically_failed_numbers(self):
        clean = self.rewrite_bullets()
        issues = [{'bullet': i, 'kind': 'mixed_topic', 'quote': f'Other topic {i}.', 'reason': '混入其他卖点'}
                  for i in (1, 2, 4)]
        bad = '\n'.join(line+' '+f'Other topic {i}.' if i in (1, 2, 4) else line
                        for i, line in enumerate(clean.splitlines(), 1))
        with patch.object(provider, 'research_json', return_value={'text': bad}), \
             patch('visual_studio.model_json', side_effect=[{'issues': issues},
                 {'revisions': [{'bullet': i, 'text': clean.splitlines()[i-1]} for i in (1, 2, 4)]}, {'issues': []}]) as model:
            output = provider.rewrite_field(self.rewrite_request(clean))['text']
        self.assertEqual(output, clean)
        self.assertEqual(model.call_args_list[1].args[1]['rewrite_bullets'], [1, 2, 4])
        for i in (3, 5):
            self.assertEqual(output.splitlines()[i-1], bad.splitlines()[i-1])

    def test_field_rewrite_removes_proven_padding_without_model_repair_or_translation(self):
        clean = self.rewrite_bullets()
        quote = 'The pockets belong to the garment.'
        lines = clean.splitlines();lines[0] += ' '+quote;bad='\n'.join(lines)
        issue = {'bullet': 1, 'kind': 'padding', 'quote': quote, 'reason': '重复已有信息'}
        with patch.object(provider, 'research_json', return_value={'text': bad}), \
             patch('visual_studio.model_json', return_value={'issues': [issue]}) as model:
            output = provider.rewrite_field(self.rewrite_request(clean))['text']
        self.assertEqual(output, clean)
        self.assertEqual(model.call_count, 1)

    def test_field_rewrite_rejects_repair_that_changes_a_passed_number(self):
        clean = self.rewrite_bullets()
        bad = clean.replace('Wear this cardigan with pockets.', 'This cardigan with pockets has front pockets.')
        with patch.object(provider, 'research_json', return_value={'text': bad}), \
             patch('visual_studio.model_json', side_effect=[{'issues': []},
                 {'revisions': [{'bullet': 5, 'text': clean.splitlines()[4]}]}]):
            with self.assertRaisesRegex(ValueError, '未指定'):
                provider.rewrite_field(self.rewrite_request(clean))

    def test_draft_hits_locate_only_complete_selected_bullet_phrases(self):
        plan = [{'phrase': phrase, 'placement': placement} for phrase, placement in (
            ('cardigan with pockets', 'bullets'), ('long cardigan sweater', 'bullets'),
            ('button cardigans for women', 'bullets'), ('cable knit cardigan', 'title'),
        )]
        bullets = ['[Pockets] A Cardigan with Pockets.', '[Length] A long cardigan sweater.',
                   '[Buttons] A button cardigan for women.', '[Knit] A cable knit cardigan.',
                   '[Collar] Shawl collar.']
        self.assertEqual(provider.draft_bullet_keyword_hits(bullets, plan), [
            {'phrase': 'cardigan with pockets', 'bullets': [1]},
            {'phrase': 'long cardigan sweater', 'bullets': [2]},
        ])

    def test_bullet_review_checks_missing_phrase_against_draft_and_final(self):
        issue = {'bullet': 1, 'kind': 'missing_phrase', 'quote': 'cardigan with pockets',
                 'reason': '可自然保留原词组'}
        hits = [{'phrase': 'cardigan with pockets', 'bullets': [1]}]
        with patch('visual_studio.model_json', return_value={'issues': [issue]}):
            self.assertEqual(provider.review_listing_bullets(
                '[Pockets] Put a key in the front pocket.', market='US', facts={}, draft_keyword_hits=hits), [issue])
            self.assertEqual(provider.review_listing_bullets('[Pockets] Wear this cardigan with pockets.',
                market='US', facts={}, draft_keyword_hits=hits), [])

    def test_short_bullet_still_gets_repetition_and_topic_feedback(self):
        bullets = '\n'.join(('[Pockets] This cardigan with pockets has front pockets.',
                             '[Closure] Close the buttons below the wide collar.',
                             '[Color] Choose black or brown.', '[Length] This is a long layer.',
                             '[Texture] Look for the cable knit.'))
        mixed = {'bullet': 2, 'kind': 'mixed_topic', 'quote': 'the wide collar', 'reason': '混入领型'}
        with patch('visual_studio.model_json', return_value={'issues': [mixed]}):
            issues = provider.listing_bullet_issues(bullets, market='US', facts={}, draft_keyword_hits=[])
        self.assertIn('第 1 条须为 250–500 字符', issues[0])
        self.assertIn('第 1 条五点重复解释口袋用途', issues[-2])
        self.assertEqual(issues[-1], mixed)

    def test_partial_repair_cannot_edit_an_approved_bullet(self):
        bullets = '\n'.join(f'[Feature {i}] Original {i}.' for i in range(1, 6))
        translations = '\n'.join(f'原文 {i}' for i in range(1, 6))
        revisions = [{'bullet': i, 'text': f'[Feature {i}] Edited {i}.', 'translation': f'修订 {i}'}
                     for i in (1, 2, 4)]
        result, translated = provider.merge_bullet_revisions(bullets, translations, [1, 2, 4], revisions)
        for index in (2, 4):
            self.assertEqual(result.splitlines()[index], bullets.splitlines()[index])
            self.assertEqual(translated.splitlines()[index], translations.splitlines()[index])
        revisions[2]['bullet'] = 5
        with self.assertRaisesRegex(ValueError, '未指定'):
            provider.merge_bullet_revisions(bullets, translations, [1, 2, 4], revisions)

    def test_exact_restatement_cut_keeps_minimum_length(self):
        body = '[Feature] ' + 'a' * 245
        quote = 'so the same benefit remains obvious'
        issue = {'bullet': 1, 'kind': 'repetition', 'quote': quote}
        self.assertEqual(provider.trim_bullet_restatements(body + ', ' + quote + '.', [1], [issue]),
                         {1: body + '.'})
        self.assertEqual(provider.trim_bullet_restatements('[Short] A detail ' + quote + '.', [1], [issue]), {})

    def test_restatement_cut_removes_whole_sentence_and_preserves_keyword(self):
        phrase = 'cardigan with pockets'
        opening = '[Pockets] Wear this cardigan with pockets.'
        filler = 'The pockets belong to the garment.'
        remaining = ' A distinct use ' + 'x' * 220 + '.'
        issues = [{'bullet': 1, 'kind': 'padding', 'quote': filler}]
        hits = [{'phrase': phrase, 'bullets': [1]}]
        self.assertEqual(provider.trim_bullet_restatements(opening+' '+filler+remaining, [1], issues,
            keyword_hits=hits, allow_short=True), {1: (opening+remaining, True)})
        self.assertEqual(provider.trim_bullet_restatements(opening+' '+filler, [1], issues,
            keyword_hits=hits, allow_short=True), {1: (opening, False)})
        issues[0]['quote'] = 'Wear this cardigan with pockets.'
        self.assertEqual(provider.trim_bullet_restatements(opening+remaining, [1], issues,
            keyword_hits=hits, allow_short=True), {})

    def test_internal_note_is_a_numbered_bullet_issue(self):
        bullets = '\n'.join(f'[Feature {i}] Detail {i}. ' + 'x' * 250 for i in range(1, 6))
        bullets = bullets.replace('Detail 2.', 'The supplier has not confirmed the details.')
        with patch('visual_studio.model_json', return_value={'issues': []}):
            issues = provider.listing_bullet_issues(bullets, market='US', facts={}, draft_keyword_hits=[])
        self.assertEqual(len(issues), 1)
        self.assertIn('第 2 条包含内部资料说明', issues[0])

    def test_default_generation_repairs_flagged_bullets_and_reviews_them_again(self):
        bullets = '\n'.join(
            f'[Topic {i}] The garment detail for topic {i}. The product photos show the cable pattern across the front of the knit. '
            'The pattern runs vertically on both sides of the opening. The same texture is visible across the lower part of the cardigan in the front view.'
            for i in range(1, 6)
        )
        terms = ('outerwear garment apparel layering weekend daily casual travel walking streetwear classic wardrobe '
                 'autumn coldseason outdoor commute leisure clothing overlayer packing workday transitional midweight styling relaxed')
        draft = {'title': 'Cable Knit Cardigan with Front Buttons and Long Sleeves for Women', 'highlights': 'A long cardigan',
                 'bullets': bullets, 'description': 'Cardigan for Layering\nMaterial: Cotton\n\nProduct: Cardigan',
                 'terms': terms, 'warnings': '', 'zh': ''}
        polished = {**draft, 'highlights': 'Long cardigan with front buttons',
                    'bullets': bullets.replace('[Topic 2]', '[Topic 2] The pockets sit at the front.'),
                    'translations': {'highlights': '正面带纽扣的长款开衫'}}
        review = {'issues': [{'bullet': 2, 'kind': 'mixed_topic', 'quote': 'The pockets sit at the front.',
                              'reason': '该条混入了口袋卖点'}]}
        polished['translations']['bullets'] = '\n'.join(f'第 {i} 条翻译' for i in range(1, 6))
        repair = {'revisions': [{'bullet': 2, 'text': bullets.splitlines()[1], 'translation': '第二条修订'}], 'warnings': ''}

        def response(copy):
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(copy)}}]}

        with tempfile.TemporaryDirectory() as temp, patch.object(provider.app_paths, 'DATA', Path(temp)), \
             patch.object(provider, 'text_settings', return_value={'api_key': 'fixture', 'model': 'fixture'}), \
             patch.object(provider, 'text_completion', side_effect=map(response, (
                 draft, polished, review, repair, {'issues': []}))) as send:
            product = {'name': 'Cardigan', 'features': 'Long cardigan with front buttons'}
            result = provider.generate_listing(product, 'US')['copy']
            self.assertEqual(send.call_count, 5)
            second = send.call_args_list[1].args[0]['messages']
            self.assertIn('unslop-writing', second[0]['content'])
            self.assertEqual(json.loads(second[1]['content'])['draft']['highlights'], draft['highlights'])
            repaired_input = json.loads(send.call_args_list[3].args[0]['messages'][1]['content'])
            self.assertEqual(repaired_input['validationIssues'], review['issues'])
            self.assertEqual(repaired_input['rewrite_bullets'], [2])
            recheck = json.loads(send.call_args_list[4].args[0]['messages'][1]['content'])
            self.assertEqual(recheck['bullets'], bullets.splitlines())
            self.assertEqual(recheck['review_bullets'], [2])
            receipts = [json.loads(path.read_text(encoding='utf-8'))
                        for path in (Path(temp) / 'listing-responses').glob('*.json')]
            self.assertIn('listing_unslop', [record.get('purpose') for record in receipts])
            self.assertEqual(sum(record.get('purpose') == 'listing_bullet_review' for record in receipts), 2)
        self.assertEqual(result['highlights'], polished['highlights'])
        self.assertEqual(result['translations']['highlights'], polished['translations']['highlights'])
        self.assertEqual(result['generationEngine']['editingSkill'], 'unslop-writing')
        self.assertEqual(result['generationEngine']['bulletReview'], {'passed': True, 'repairCount': 1})
        self.assertEqual(result['bullets'], bullets)
        self.assertEqual(result['translations']['bullets'].splitlines()[2:], polished['translations']['bullets'].splitlines()[2:])
        self.assertTrue(result['description'].endswith(provider.DESCRIPTION_NOTES))

    def test_default_generation_sends_only_stored_selected_sellersprite_rows(self):
        report = {'source': 'sellersprite', 'keywords': [
            {'phrase': 'cable knit cardigan', 'placement': 'title', 'selected': True,
             'metrics': [{'seed': 'cardigan', 'searches': 3500}]},
            {'phrase': 'sherpa cardigan', 'selected': False,
             'metrics': [{'asin': 'B0HPNT73JL', 'searches': 4000}]},
        ]}
        product = {'id': 'test', 'name': 'Cardigan', 'style': 'Cable knit'}
        stored = {**product, 'competitorResearch': {'US': report}}
        with patch.object(provider, 'text_settings', return_value={'api_key': 'fixture', 'model': 'fixture'}), \
             patch.object(provider, 'text_completion', side_effect=ValueError('capture only')) as send:
            with self.assertRaisesRegex(ValueError, 'capture only'):
                provider.generate_listing(product, 'US', evidence_product=stored)
        system, user = send.call_args.args[0]['messages']
        self.assertIn('# IvyeaOps Listing Writing Rules', system['content'])
        self.assertIn('Generate exactly one title.', system['content'])
        self.assertNotIn('Generate exactly 5 title options.', system['content'])
        self.assertNotIn('Generate exactly 2 bullet point sets.', system['content'])
        self.assertIn(provider.DESCRIPTION_NOTES, system['content'])
        payload = json.loads(user['content'])
        self.assertEqual(payload['Competitor Data (from market research)']['keywords'], trial.keyword_input(stored, 'US'))
        self.assertNotIn('keywordPlan', payload['confirmed_product_facts'])
        self.assertNotIn('sherpa cardigan', user['content'])

    def test_title_priority_provenance_and_whole_rows_in_original_budget(self):
        reverse = {'asin': 'B0HPNT73JL', 'searches': 12000, 'purchaseRate': 0.12, 'trafficPercentage': 0.05}
        mining = {'seed': 'cable knit cardigan', 'searches': 1500, 'purchaseRate': 0.04, 'trafficPercentage': 0.91}
        selected = [
            {'phrase': 'cable knit cardigan', 'placement': 'title', 'selected': True, 'metrics': [reverse]},
            {'phrase': 'cable knit duster', 'placement': 'bullets', 'selected': True, 'metrics': [mining]},
            {'phrase': 'sherpa lined cardigan', 'placement': 'title', 'selected': False, 'metrics': [reverse]},
        ]
        selected.extend({'phrase': f'selected phrase {i}', 'placement': 'bullets', 'selected': True,
                         'reason': 'Relevant selected term. ' * 5, 'metrics': [mining]}
                        for i in range(40))
        product = {'competitorResearch': {'US': {'source': 'sellersprite', 'keywords': selected}}}
        rows = trial.keyword_input(product, 'US')
        self.assertEqual([row['phrase'] for row in rows[:2]], ['cable knit cardigan', 'cable knit duster'])
        self.assertEqual(rows[0]['metrics'][0]['trafficPercentage'], 0.05)
        self.assertNotIn('trafficPercentage', rows[1]['metrics'][0])
        self.assertNotIn('sherpa lined cardigan', [row['phrase'] for row in rows])
        self.assertLess(len(rows), len(selected) - 1)
        prompt = ivyea_copy_core._build_listing_prompt(
            'US', 'Cardigan', '', {}, {'available': True, 'data': {'keywords': rows}})
        sent = prompt.split('Competitor Data (from market research):\n')[1].split('\n\n', 1)[0]
        self.assertLessEqual(len(sent), 3000)
        self.assertEqual(json.loads(sent), {'keywords': rows})

    def test_exact_keyword_landing_identifies_the_candidate_and_sentence(self):
        rows = [{'phrase': 'cable knit'}, {'phrase': 'knit card'}]
        copy = {'titles': ['Cable-Knit Cardigan'], 'highlights': 'Layering',
                'bullets_a': ['A cable knit texture.'], 'bullets_b': ['Wide collar'],
                'search_terms': ['wardrobe']}
        results = trial.exact_placements(rows, copy)
        self.assertEqual(results[0]['matches'], [
            {'field': '标题 1', 'text': 'Cable-Knit Cardigan'},
            {'field': '五点 A 1', 'text': 'A cable knit texture.'},
        ])
        self.assertEqual(results[1]['matches'], [])

    def test_equal_mining_metrics_keep_all_seed_sources_in_one_record(self):
        same = {'searches': 6100, 'purchases': 400, 'purchaseRate': .065, 'month': '2026.10'}
        report = {'source': 'sellersprite', 'keywords': [{
            'phrase': 'cable knit cardigan', 'placement': 'bullets', 'selected': True,
            'metrics': [
                {**same, 'seed': 'cardigan', 'seedSource': 'reverse'},
                {**same, 'seed': 'long cardigan', 'seedSource': 'product_facts'},
                {**same, 'seed': 'knit cardigan', 'seedSource': 'product_facts'},
                {**same, 'seed': 'long cardigan', 'seedSource': 'product_facts'},
                {**same, 'seed': 'cardigan', 'seedSource': 'reverse', 'month': '2026.09'},
                {**same, 'asin': 'B0HPNT73JL', 'trafficPercentage': .08},
            ],
        }]}
        rows = trial.keyword_input({'competitorResearch': {'US': report}}, 'US')
        self.assertEqual(rows[0]['metrics'], [
            {**same, 'seedSources': {'reverse': ['cardigan'], 'product_facts': ['long cardigan', 'knit cardigan']}},
            {**same, 'seed': 'cardigan', 'seedSource': 'reverse', 'month': '2026.09'},
            {**same, 'asin': 'B0HPNT73JL', 'trafficPercentage': .08},
        ])
