import copy
import unittest
from unittest.mock import patch

import discovery_review
import product_library


class DiscoveryReviewTests(unittest.TestCase):
    def setUp(self):
        self.asins = ['B000000001', 'B000000002', 'B000000003']
        self.original = {
            'market': 'US', 'input': '\n'.join(self.asins), 'samples': [],
            'sources': [{'asin': asin, 'status': 'empty', 'count': 0, 'pages': 2} for asin in self.asins],
        }
        self.search = {'keyword': 'hooded knit cardigan', 'url': 'https://www.amazon.com/s?k=hooded+knit+cardigan'}
        self.image = 'https://m.media-amazon.com/images/I/reference.jpg'
        self.target, self.parent = 'B000000010', 'B000000020'
        self.product = {
            'selectionResearch': {
                'sourceMonth': 'cyclic-discovery', 'reference': {'market': 'US', 'asin': self.target},
                'rankedCompetitors': [{'asin': asin, 'parent_asin': f'B00000003{i}', 'search': self.search}
                                      for i, asin in enumerate(self.asins)],
            },
            'editorAsinReference': {'market': 'US', 'asin': self.target, 'parentAsin': self.parent,
                                    'title': 'Hooded knit cardigan', 'referenceImages': [self.image]},
            'competitorResearch': {'US': {'source': 'sellersprite', 'input': self.original['input'],
                                         'keywords': [{'phrase': 'knit cardigan'}]}},
        }

    def test_an_empty_successful_original_group_can_add_one_separate_review_source(self):
        extra, duplicate, no_rank = 'B000000011', 'B000000012', 'B000000013'
        html = ''.join(f'<div data-asin="{asin}" data-component-type="s-search-result">'
                       '<h2>Hooded <span>knit cardigan</span></h2></div>'
                       for asin in [*self.asins, duplicate, no_rank, extra])
        old = copy.deepcopy(self.product)
        with patch('discovery_review.importer.fetch_amazon', return_value=html), \
             patch('discovery_review.sellersprite.Client') as service, \
             patch('discovery_review.visual_studio.encode_reference', return_value='image'), \
             patch('discovery_review.visual_studio.model_json', return_value={
                 'matches': [{'asin': duplicate, 'reason': 'same parent'},
                             {'asin': extra, 'reason': 'Same buttons and hood, different print'}],
             }) as vision, patch('discovery_review.review_insights.collect', return_value={
                 'samples': [{'id': 'R1', 'asin': extra, 'text': 'The buttons feel secure.'}],
                 'sources': [{'asin': extra, 'status': 'ok', 'count': 1}], 'fetchedAt': 'fixture',
             }) as fetch_reviews:
            client = service.return_value.connect.return_value
            client.call.side_effect = lambda _, args: {
                'asin': args['asin'], 'parent': self.parent if args['asin'] == duplicate else 'B000000021',
                'bsrRank': None if args['asin'] == no_rank else 12345, 'bsrLabel': 'Clothing',
                'imageUrl': self.image, 'ratings': 2,
            }
            report = discovery_review.supplement(self.product, self.original)
        self.assertEqual(self.product, old)
        self.assertEqual(report['input'], self.original['input'])
        self.assertEqual(report['sources'][:3], self.original['sources'])
        self.assertEqual(report['supplement']['asin'], extra)
        self.assertEqual([x['asin'] for x in vision.call_args.args[1]['candidates']], [extra])
        fetch_reviews.assert_called_once_with({'market': 'US', 'asins': extra}, client=client)
        report['analysis'] = {'themes': [{'evidenceIds': ['R1']}]}
        self.product['reviewResearch'] = {'US': report}
        snapshot = product_library.discovery_snapshot(self.product)
        self.assertEqual(snapshot['competitorResearch'], old['competitorResearch'])
        self.assertEqual(snapshot['reviewResearch']['US']['supplement']['asin'], extra)
        report['samples'][0]['asin'] = duplicate
        with self.assertRaisesRegex(ValueError, '评论正文不匹配'):
            product_library.discovery_snapshot(self.product)

    def test_failed_query_or_existing_comments_never_start_supplement(self):
        with patch('discovery_review.importer.fetch_amazon') as search:
            for report in ({**self.original, 'samples': [{'id': 'R1'}]},
                           {**self.original, 'sources': [{**self.original['sources'][0], 'status': 'failed'},
                                                        *self.original['sources'][1:]]}):
                with self.assertRaisesRegex(ValueError, '均查询成功'):
                    discovery_review.supplement(self.product, report)
            search.assert_not_called()
