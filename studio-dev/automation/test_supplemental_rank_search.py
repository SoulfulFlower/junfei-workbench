import unittest
from pipeline import _browser_rank_url_matches


class SupplementalRankSearchTest(unittest.TestCase):
    def setUp(self):
        self.asin = 'B0HQC8H1K5'
        self.front = 'https://www.amazon.com/s?k=Fleece+Balaclava'
        self.rank = {'url': 'https://www.amazon.com/s?k=' + self.asin, 'asin': self.asin, 'raw': self.asin + '\n#1002667\ninClothing, Shoes & Jewelry'}
        self.extra = {**self.rank, 'checked_at': '2026-11-06T08:30:00Z', 'purpose': 'candidate_asin_rank_lookup'}

    def matches(self, extra):
        return _browser_rank_url_matches(self.front, self.rank, extra, self.asin, 'US')

    def test_real_own_lookup_keeps_title_query_separate(self):
        self.assertTrue(self.matches(self.extra))

    def test_unrecorded_lookup_rejected(self):
        self.assertFalse(self.matches(None))

    def test_changed_raw_asin_or_purpose_rejected(self):
        for key, value in [('raw', 'unrelated #1002667'), ('asin', 'B012345678'), ('purpose', 'keyword_demand')]:
            self.assertFalse(self.matches({**self.extra, key: value}))

    def test_foreign_or_mixed_keyword_url_rejected(self):
        for url in ['https://evil.example/s?k=' + self.asin, 'https://www.amazon.com/s?k=Fleece+' + self.asin]:
            rank = {**self.rank, 'url': url}
            self.assertFalse(_browser_rank_url_matches(self.front, rank, {**self.extra, 'url': url}, self.asin, 'US'))

    def test_explicit_title_prefix_lookup_preserves_original_query_and_exact_asin(self):
        for phrase, expected in [('Fleece', True), ('Fleece+Balaclava', True), ('Balaclava', False), ('Unrelated', False), (self.asin, False)]:
            url = 'https://www.amazon.com/s?k='+phrase+'+'+self.asin
            rank = {**self.rank, 'url': url}
            extra = {**self.extra, 'url': url, 'purpose': 'candidate_title_prefix_asin_rank_lookup'}
            with self.subTest(phrase=phrase):
                self.assertEqual(_browser_rank_url_matches(self.front,rank,extra,self.asin,'US'),expected)
