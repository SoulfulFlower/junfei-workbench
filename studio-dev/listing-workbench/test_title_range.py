"""Title boundaries, local rewrites and a single, isolated length repair."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import provider


class TitleRangeTests(unittest.TestCase):
    def test_rewrite_rejects_short_and_long_titles_without_touching_input(self):
        request={'field':'title','market':'UK','mode':'concise','text':'Existing title','product':{'name':'Cardigan'}}
        for count in (59,60,75,76):
            with self.subTest(count=count),patch.object(provider,'research_json',return_value={'text':'a'*count}):
                if 60<=count<=75:
                    self.assertEqual(provider.rewrite_field(request)['text'],'a'*count)
                else:
                    with self.assertRaisesRegex(ValueError,'60–75'):
                        provider.rewrite_field(request)
        self.assertEqual(request['text'],'Existing title')

    def test_short_title_gets_one_targeted_repair_then_validation(self):
        points='\n'.join(f'[Heading {i}] '+str(i)*240 for i in range(5))
        draft={'title':'Button Cardigan','highlights':'Button closure','bullets':points,
               'description':'Cardigan for Layering\nClosure: Button front\n\n1 Pcs x cardigan',
               'terms':'layering','zh':'','warnings':''}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}
        valid='Button Front Knit Cardigan with Long Sleeves for Everyday Layering'
        for replacement,success in ((valid,True),('Still too short',False),('x'*76,False)):
            repair={'fields':{'title':replacement},'translations':{'title':'纽扣开衫'}}
            with self.subTest(replacement=replacement),tempfile.TemporaryDirectory() as tmp, \
                 patch.object(provider.app_paths,'DATA',Path(tmp)), \
                 patch.dict(provider.SETTINGS,{'provider':'deepseek','api_key':'test','model':'test'}), \
                 patch.object(provider,'text_completion',return_value=response), \
                 patch.object(provider,'polish_listing',side_effect=lambda draft,**_:draft), \
                 patch.object(provider,'review_listing_bullets',return_value=[]), \
                 patch.object(provider,'validate_backend_length'), \
                 patch.object(provider,'research_json',return_value=repair) as model:
                if success:
                    result=provider.generate_listing({'name':'Cardigan','style':'Button front','packageContents':'1 x cardigan'},'US')['copy']
                    self.assertEqual(result['title'],valid)
                    self.assertEqual(result['highlights'],draft['highlights'])
                else:
                    with self.assertRaises(ValueError):
                        provider.generate_listing({'name':'Cardigan','style':'Button front','packageContents':'1 x cardigan'},'US')
                model.assert_called_once()
                self.assertEqual(model.call_args.args[1]['fields'],{'title':'Button Cardigan'})
                self.assertEqual(model.call_args.args[1]['minimums'],{'title':60})


if __name__=='__main__':
    unittest.main()
