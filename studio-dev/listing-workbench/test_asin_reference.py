import json
import unittest

import asin_reference
import ivyea_asin_insights
import ivyea_asin_prompts as prompts


class AsinReferenceTests(unittest.TestCase):
    def test_only_observed_children_and_verified_colour_sources(self):
        children = {'B000000001': ['Black', 'Small'], 'B000000002': ['Black', 'Medium'],
                    'B000000003': ['Sky Blue', 'Medium']}
        root = 'https://m.media-amazon.com/images/I/'

        def page(asin, color):
            gallery = [{'large': root + color + str(i) + '.jpg'} for i in range(7)]
            twister = {
                'dimensions': ['color_name', 'size_name'], 'dimensionValuesDisplayData': children,
                'variationValues': {'color_name': ['Black', 'Sky Blue'], 'size_name': ['Small', 'Medium']},
                'currentAsin': asin, 'selectedVariationValues': {'color_name': int(color == 'blue')},
            }
            return (
                '<div id="wayfinding-breadcrumbs_feature_div"><a href="/women?node=7147440011">Women</a><a href="/tees?node=1044544">T-Shirts</a></div>'
                '<span id="productTitle">Example product</span>'
                f'<input id="ASIN" value="{asin}"><img id="landingImage" src="{gallery[0]["large"]}">'
                f'<script>{json.dumps(twister)}</script>'
                f"<script>'initial': A.$.parseJSON('{json.dumps(gallery)}')</script>"
            )

        calls = []

        def fetch(url):
            asin = url.rsplit('/', 1)[1]
            calls.append(asin)
            return page(asin, 'blue' if asin.endswith('3') else 'black')

        reference = asin_reference.capture('B000000001', 'US', fetch=fetch)
        self.assertEqual(reference['category'],'Women > T-Shirts')
        self.assertEqual(reference['categoryEvidence']['breadcrumbs'][-1]['nodeId'],'1044544')
        self.assertEqual(len(reference['referenceImages']), 7)
        self.assertEqual({row['asin'] for row in reference['variants']}, set(children))
        self.assertEqual([color['mainImage']['sourceAsin'] for color in reference['colors']],
                         ['B000000001', 'B000000003'])
        self.assertEqual(calls, ['B000000001', 'B000000003'])
        calls.clear()
        asin_reference.capture('B000000001', 'US', reference, fetch=fetch)
        self.assertEqual(calls, ['B000000001'])
        wrong_page = page('B000000003', 'black')
        with self.assertRaisesRegex(ValueError, '颜色'):
            asin_reference.checked_image(wrong_page, reference['variants'][-1], 'US')

    def test_insight_sends_gallery_in_original_order_without_variant_images(self):
        root = 'https://m.media-amazon.com/images/I/'
        gallery = [root + f'gallery-{i}.jpg' for i in range(7)]
        product = {'id': 'test', 'editorAsinReference': {
            'asin': 'B000000001', 'market': 'US', 'title': 'Example', 'capturedAt': 'test',
            'referenceImages': gallery, 'colors': [{'mainImage': {'url': root + 'variant.jpg'}}],
        }}
        calls = []

        def complete(prompt, images, **options):
            calls.append((prompt, images, options))
            return '{"usp":["Example"]}' if options.get('json_output') else 'Example'

        result = ivyea_asin_insights.analyze(product, complete=complete, encode=lambda url: url)
        self.assertEqual([call[1] for call in calls], [gallery[:4], gallery[4:], [], []])
        self.assertEqual(calls[0][0], prompts.image_batch(1, 4, 7))
        self.assertEqual(calls[1][0], prompts.image_batch(5, 7, 7))
        self.assertIn('[ASIN AUDIT METHODOLOGY]', calls[-1][0])
        self.assertEqual(result['structured'], {'usp': ['Example']})


if __name__ == '__main__':
    unittest.main()
