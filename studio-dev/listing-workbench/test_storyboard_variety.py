import copy
import unittest

from ivyea_pipeline import check_apparel_gallery
from storyboard_variety import gallery_issues


def apparel_cards():
    return [
        {'layout': 'white_main', 'product_presence': 'hero'},
        {'layout': 'human_context', 'product_presence': 'environmental'},
        {'layout': 'spec_grid', 'product_presence': 'supporting',
         'size_chart': True, 'supporting_text': 'Size | Bust (cm)\nS | 92\nM | 96'},
    ]


class ApparelStoryboardPolicyTests(unittest.TestCase):
    def test_new_artwork_typography_preserves_photo_or_table_emphasis(self):
        from ivyea_render_core import _compile_copy_section
        card={'text_on_image':True,'headline':'Crew Neckline','subline':'A rounded front edge.'}
        legacy=_compile_copy_section(card,{})
        self.assertIn('headline dominant',legacy)
        photo=_compile_copy_section({**card,'photo_led_typography':True},{})
        self.assertIn('subordinate to the photograph',photo)
        self.assertNotIn('headline dominant',photo)
        chart=_compile_copy_section({**card,'photo_led_typography':True,'size_chart':True},{})
        self.assertIn('measurement table is the dominant information',chart)
        self.assertNotIn('headline dominant',chart)

    def test_new_policy_rejects_absent_copy_cards_but_preserves_legacy(self):
        for headline in ('Crew Neckline', '95% Polyester', 'One Top Included'):
            with self.subTest(headline=headline):
                cards = apparel_cards()
                cards.insert(2, {'layout': 'trust_close', 'product_presence': 'absent',
                                 'headline': headline})
                check_apparel_gallery(cards)
                with self.assertRaisesRegex(ValueError, '纯文字卡'):
                    check_apparel_gallery(cards, forbid_filler=True)

    def test_quantity_cannot_be_the_job_even_with_a_product_inset(self):
        cards = apparel_cards()
        cards[1]['buyer_question'] = 'What is included?'
        with self.assertRaisesRegex(ValueError, '包装或件数'):
            check_apparel_gallery(cards, forbid_filler=True)

    def test_quantity_annotation_and_complete_size_guide_are_allowed(self):
        cards = apparel_cards()
        cards[1].update(buyer_question='How does the top drape while seated?',
                        subline='One top included; trousers are styling only.')
        cards[-1]['product_presence'] = 'absent'
        check_apparel_gallery(cards, forbid_filler=True)
        cards[-1]['supporting_text'] = 'Choose your size'
        with self.assertRaisesRegex(ValueError, '纯文字卡'):
            check_apparel_gallery(cards, forbid_filler=True)

    def test_verified_front_angle_can_repeat_only_with_meaningful_shot_changes(self):
        first = {'layout': 'human_context', 'product_presence': 'environmental',
                 'scene_direction': {'pose': 'standing', 'angle': 'front-on',
                                     'framing': 'full-length shot',
                                     'composition': 'centered symmetry'}}
        second = copy.deepcopy(first)
        second['scene_direction'].update(pose='seated', framing='medium shot')
        self.assertEqual(gallery_issues([first, second], shared_verified_angle=True), [])
        self.assertTrue(gallery_issues([first, second]))
        second['scene_direction']['pose'] = 'standing'
        self.assertTrue(gallery_issues([first, second], shared_verified_angle=True))
        second['scene_direction'].update(pose='walking', framing='full-length shot')
        self.assertTrue(gallery_issues([first, second], shared_verified_angle=True))


if __name__ == '__main__':
    unittest.main()
