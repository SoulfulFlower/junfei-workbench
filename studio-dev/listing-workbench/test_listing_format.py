import unittest
import provider
class ListingFormatTests(unittest.TestCase):
 def test_five_heading_paragraphs_preserve_content_as_five_bullets(self):
  text='\n\n'.join(f'Heading {i}\nBody {i} with details.' for i in range(5))
  lines=provider.normalize_bullet_lines(text).splitlines()
  self.assertEqual(lines,[f'Heading {i} Body {i} with details.' for i in range(5)])
 def test_ten_ungrouped_lines_are_not_guessed_into_five_bullets(self):
  text='\n'.join(f'Unrelated item {i}' for i in range(10))
  self.assertEqual(provider.normalize_bullet_lines(text),text)
 def test_chinese_polish_cannot_replace_english_bullets(self):
  with self.assertRaises(ValueError):
   provider.validate_market_language({'bullets':'修身剪裁'},'US')
  provider.validate_market_language({'bullets':'Slim fit crop top'},'US')
  provider.validate_market_language({'bullets':'日本語の商品説明'},'JP')
 def test_multibyte_budget_and_whole_tokens(self):
  result=provider.fit_backend_bytes('夹克 外套 jacket jacket coat',18)
  self.assertLessEqual(len(result.encode('utf-8')),18)
  self.assertEqual(len(result.split()),len(set(result.split())))
  self.assertIn('夹克',result)
 def test_notes_are_exact_and_not_duplicated(self):
  text=provider.ensure_description_notes('Fabric Name: Faux suede\n\nNotes:\nold notice')
  self.assertTrue(text.endswith(provider.DESCRIPTION_NOTES))
  self.assertEqual(provider.ensure_description_notes(text),text)
  self.assertNotIn('old notice',text)

 def test_observed_chinese_remark_heading_does_not_duplicate_fixed_notes(self):
  original='女士抓绒套头衫\n材质: 聚酯纤维\n\n产品: 套头衫\n\n备注:\n1. 原测量说明\n2. 原颜色说明'
  result=provider.ensure_description_notes(original,chinese=True)
  self.assertNotIn('备注:',result)
  self.assertEqual(result.count('1. '),1)
  self.assertEqual(result.count('2. '),1)
  self.assertEqual(provider.ensure_description_notes(result,chinese=True),result)

 def test_description_rewrite_preserves_format_and_confirmed_quantity(self):
  from unittest.mock import patch
  request={'field':'description','market':'US','mode':'keywords','text':'Earlier description',
           'product':{'name':'Cardigan','packageContents':'1件开衫'}}
  valid='Button Front Knit Cardigan\nClosure: Button front\n\n1 Pcs x knit cardigan\nNotes:\nOld text'
  with patch('provider.research_json',return_value={'text':valid}):
   self.assertEqual(provider.rewrite_field(request)['text'],valid.split('\nNotes:')[0]+'\n\n'+provider.DESCRIPTION_NOTES)
  for invalid in ('An ordinary paragraph.',valid.replace('1 Pcs','2 Pcs')):
   with patch('provider.research_json',return_value={'text':invalid}),self.assertRaises(ValueError):
    provider.rewrite_field(request)
  with self.assertRaises(ValueError):provider.format_english_description(valid,'未确认')

 def test_description_rejects_invented_count_and_requires_localised_layout(self):
  wrong='Cardigan for Layering\nClosure: Button front\n\n9 Pcs x cardigan'
  with self.assertRaisesRegex(ValueError,'已有数量资料不符'):
   provider.format_english_description(wrong,'1 x cardigan')
  with self.assertRaisesRegex(ValueError,'包装数量缺少依据'):
   provider.format_english_description(wrong,'Cardigan, quantity unknown')
  for observed in ('1 x cardigan','1×cardigan','1件开衫'):
   correct=provider.format_english_description(wrong.replace('9 Pcs','1 Pcs'),observed)
   self.assertTrue(correct.endswith(provider.DESCRIPTION_NOTES))
  with self.assertRaisesRegex(ValueError,'产品描述未按'):
   provider.format_listing_description('Eine Strickjacke mit Knöpfen.','1 x cardigan','DE')
  german=provider.format_listing_description('Strickjacke\nVerschluss: Knöpfe\n\n1 Stk. x Strickjacke','1 x cardigan','DE')
  self.assertIn('\n\n1 Stk. x Strickjacke\n\nHinweise:\n1. ',german)
  self.assertEqual(len(german.split('Hinweise:\n',1)[1].splitlines()),2)

 def test_description_preserves_size_columns_when_attribute_label_is_too_long(self):
  label='Garment measurements'
  columns='(cm; bust/body length/sleeve length/shoulder width)'
  values='S 96/50/57/38; M 100/51/58/39'
  original=f'Knit Wrap Top\n{label} {columns}: {values}\n\n1 Pcs x knit cardigan'
  self.assertIn(f'{label}: {columns} {values}',provider.format_english_description(original,'1件开衫'))

 def test_backend_rewrite_drops_title_overlap_and_quantity_words(self):
  from unittest.mock import patch
  with patch.object(provider,'research_json',return_value={'text':'CARDIGAN, Long Knit, five two long 7'}) as model:
   with self.assertRaisesRegex(ValueError,'去重后为 4 字符'):
    provider.rewrite_field({'field':'terms','market':'US','mode':'concise','text':'Previous',
        'currentTitle':'Knit Cardigan','product':{'name':'Cardigan'}})
  self.assertEqual(model.call_args.args[1]['currentTitle'],'Knit Cardigan')

 def test_listing_length_boundaries(self):
  for count in (60,75):
   provider.validate_title_fields({'title':'a b '+('c'*(count-4)),'highlights':'Button closure'})
  for count in (59,76):
   with self.assertRaises(ValueError):
    provider.validate_title_fields({'title':'a b '+('c'*(count-4)),'highlights':'Button closure'})
  bullets=[f'[Point {i}] '.ljust(250,str(i)) for i in range(5)]
  provider.validate_bullets('\n'.join(bullets))
  with self.assertRaisesRegex(ValueError,'249'):
   provider.validate_bullets('\n'.join([bullets[0][:-1],*bullets[1:]]))
  for count in (200,249):
   provider.validate_backend_length('a'*count)
  for terms in ('a'*199,'a'*251,'é'*200):
   with self.assertRaises(ValueError):
    provider.validate_backend_length(terms)

 def test_bullet_prose_rejects_repeated_pocket_location_but_allows_a_new_use(self):
  with self.assertRaisesRegex(ValueError,'第 2 条五点重复解释口袋位置'):
   provider.validate_bullet_prose(
    '[Fabric] A cable-knit texture.\n'
    '[Pockets] This cardigan has pockets set into the front of the garment. '
    'They give you a place for small items. The pockets sit on the same front as the button closure.')
  provider.validate_bullet_prose('[Pockets] The cardigan has front pockets. Tuck your keys or a folded list into a pocket.')
  with self.assertRaisesRegex(ValueError,'重复解释口袋用途'):
   provider.validate_bullet_prose('[Pockets] This cardigan with pockets has front pockets.')
  with self.assertRaisesRegex(ValueError,'重复解释口袋用途'):
   provider.validate_bullet_prose('[Pockets] Keep small items close at hand. They stay within reach as you walk.')

 def test_draft_rejects_short_terms_if_optional_request_fails(self):
  import json,tempfile
  from pathlib import Path
  from unittest.mock import patch
  points='\n'.join(f'[Heading {i}] '+str(i)*240 for i in range(5))
  generated={'title':'Button Front Knit Cardigan with Ribbed Cuffs and Front Button Closure','highlights':'Button closure','bullets':points,
             'description':'Cardigan for Layering\nClosure: Button front\n\n1 Pcs x cardigan',
             'terms':'CARDIGAN, layering two 5','zh':'','warnings':''}
  facts={'name':'Cardigan','style':'Button front','packageContents':'1 x cardigan',
         'competitorResearch':{'US':{'keywords':[{'phrase':'long cardigan','selected':True,'monthlySearches':800}]}}}
  def response(values):
   return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(values)}}]}
  with tempfile.TemporaryDirectory() as tmp,patch.object(provider.app_paths,'DATA',Path(tmp)), \
       patch.dict(provider.SETTINGS,{'provider':'deepseek','api_key':'test','model':'test'}), \
       patch.object(provider,'text_completion',return_value=response(generated)) as main, \
       patch.object(provider,'research_json',side_effect=ValueError('optional backend HTTP 502')) as optional, \
       patch.object(provider,'polish_listing',side_effect=lambda draft,**_:draft), \
       patch.object(provider,'review_listing_bullets',return_value=[]), \
       patch('visual_studio.model_json') as editor:
   with self.assertRaisesRegex(ValueError,'后台词去重后为 8 字符'):
    provider.generate_listing(facts,'US')
   main.assert_called_once()
   editor.assert_not_called()
   self.assertEqual(optional.call_args.args[1]['allowedNewWords'],'long')
   for changes,error in (
       ({'title':'Waterproof Cardigan'},'受限宣称'),
       ({'highlights':'Free Gift'},'受限宣称'),
       ({'bullets':'\n'.join(f'[Heading {i}] Same body.' for i in range(5))},'五点格式未通过检查')):
    main.return_value=response({**generated,**changes})
    editor.side_effect=ValueError('repair unavailable')
    with self.assertRaisesRegex(ValueError,error):
     provider.generate_listing(facts,'US')

 def test_measured_keyword_order_and_coverage_use_returned_values(self):
  research={'keywords':[
   {'phrase':'womens knit cardigan','monthlySearches':7900,'metrics':[{'purchaseRate':0.02}]},
   {'phrase':'button front cardigan','monthlySearches':500,'metrics':[{'purchaseRate':'0.10'}]},
   {'phrase':'outerwear','monthlySearches':15000}, {'phrase':'layering knitwear'},
   {'phrase':'unchecked','selected':False,'monthlySearches':1200}]}
  plan=provider.selected_keyword_plan(research,[])
  self.assertEqual([item['phrase'] for item in plan],['button front cardigan','womens knit cardigan','outerwear','layering knitwear'])
  copy={'title':'Button-Front Cardigan','highlights':'','description':'For layering','bullets':'Button front','terms':''}
  reported={'outerwear':{'placement':'title'}}
  self.assertEqual([(item['phrase'],item['placement']) for item in provider.actual_keyword_placements(copy,plan,reported)],
                   [('button front cardigan','title')])

 def test_listing_json_contract_preserves_unparseable_response_without_retry(self):
  import io,json,tempfile
  from pathlib import Path
  from unittest.mock import patch
  raw={'id':'test-response','choices':[{'finish_reason':'stop','message':{'content':'invalid JSON'}}],
       'usage':{'total_tokens':17},'headers':{'Authorization':'must-not-persist'}}
  with tempfile.TemporaryDirectory() as tmp, patch.object(provider.app_paths,'DATA',Path(tmp)), \
       patch.dict(provider.SETTINGS,{'provider':'deepseek','api_key':'test-only','model':'test-model'}), \
       patch.object(provider,'urlopen',return_value=io.BytesIO(json.dumps(raw).encode())) as remote:
   with self.assertRaisesRegex(ValueError,'原始响应已保存'):
    provider.generate_listing({'name':'Toiletry Bag','style':'Zipper pouch'},'US')
   self.assertEqual(remote.call_count,1)
   sent=json.loads(remote.call_args.args[0].data)
   self.assertEqual(sent['response_format'],{'type':'json_object'})
   files=list((Path(tmp)/'listing-responses').glob('*.json'))
   self.assertEqual(len(files),1)
   record=json.loads(files[0].read_text(encoding='utf-8'))
   self.assertEqual(record['response']['choices'][0]['message']['content'],'invalid JSON')
   self.assertEqual(record['response']['usage']['total_tokens'],17)
   self.assertNotIn('headers',record['response'])
