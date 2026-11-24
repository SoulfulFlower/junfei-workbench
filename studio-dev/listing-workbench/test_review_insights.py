import unittest
from unittest.mock import patch
import review_insights as reviews

class ReviewTests(unittest.TestCase):
 def test_collect_deduplicates_and_bounds_queries(self):
  with patch('review_insights.sellersprite.Client') as factory:
   client=factory.return_value.connect.return_value;client.tools={'review':{}}
   client.call.side_effect=[{'items':[{'content':'Too small','title':'Size','star':2},{'content':'Too small','title':'Size','star':2}]},{'data':{'records':[{'reviewText':'Comfortable','rating':5}]}}]
   report=reviews.collect({'market':'UK','asins':'B0FVS1X3SP B0FVS1X3SP'})
  self.assertEqual(len(report['samples']),2);self.assertEqual(client.call.call_count,2)
  self.assertEqual(client.call.call_args_list[0].args[1]['starList'],[1,2,3]);self.assertEqual(report['sources'][0]['count'],2)
 def test_partial_failure_retains_sample(self):
  with patch('review_insights.sellersprite.Client') as factory:
   client=factory.return_value.connect.return_value;client.tools={'review':{}}
   client.call.side_effect=[{'items':[{'content':'Too small'}]},ValueError('quota')]
   report=reviews.collect({'market':'UK','asins':'B0FVS1X3SP'})
  self.assertEqual(report['sources'][0]['status'],'partial');self.assertEqual(len(report['samples']),1)
 def test_no_review_tool_or_bad_asin(self):
  with self.assertRaises(ValueError):reviews.collect({'market':'UK','asins':'not-asin'})
  with patch('review_insights.sellersprite.Client') as factory:
   factory.return_value.connect.return_value.tools={}
   with self.assertRaises(ValueError):reviews.collect({'market':'UK','asins':'B0FVS1X3SP'})
 def test_no_body_does_not_treat_rating_as_review(self):
  self.assertEqual(reviews.rows({'data':{'total':44}}),[])
  with patch('review_insights.sellersprite.Client') as factory:
   client=factory.return_value.connect.return_value;client.tools={'review':{}};client.call.return_value={'items':[{'rating':5}]}
   report=reviews.collect({'market':'UK','asins':'B0FVS1X3SP'})
  self.assertEqual(report['samples'],[]);self.assertEqual(report['sources'][0]['status'],'empty')
 def test_evidence_ids_checked(self):
  report={'market':'UK','samples':[{'id':'R1','asin':'B0FVS1X3SP','text':'Too small'}]}
  with patch('review_insights.provider.research_json',return_value={'keywords':[],'themes':[{'category':'pain_point','title':'Sizing','evidenceIds':['R999'],'recommendation':'check size'},{'category':'pain_point','title':'Sizing','evidenceIds':['R1'],'recommendation':'check size'}]}):
   result=reviews.analyse({'report':report,'facts':{}})
  self.assertEqual(len(result['themes']),1);self.assertEqual(result['themes'][0]['evidenceIds'],['R1'])
 def test_empty_samples_never_call_model(self):
  with patch('review_insights.provider.research_json') as model:
   with self.assertRaises(ValueError):reviews.analyse({'report':{'market':'UK','samples':[]}})
   model.assert_not_called()
 def test_joint_analysis_receives_reviews_and_keywords(self):
  import competitors
  source={'asin':'B0FVS1X3SP','status':'ok','title':'cotton shirt','bullets':[],'description':'','keywordData':[],'limitations':[]}
  report={'market':'UK','samples':[{'id':'R1','text':'Too small'}]}
  response={'keywords':[],'themes':[{'category':'pain_point','title':'尺码','evidenceIds':['R1'],'recommendation':'核对尺寸'}]}
  with patch('competitors.sellersprite.read_sources',return_value=[source]), patch('competitors.review_insights.collect',return_value=report), patch('competitors.provider.research_json',return_value=response) as model:
   result=competitors.analyse({'market':'UK','asins':'B0FVS1X3SP','source':'sellersprite','includeReviews':True})
  self.assertEqual(model.call_count,1)
  self.assertEqual(model.call_args.args[1]['samples'][0]['id'],'R1')
  self.assertEqual(result['reviewReport']['analysis']['themes'][0]['title'],'尺码')
 def test_review_failure_does_not_break_keywords(self):
  import competitors
  source={'asin':'B0FVS1X3SP','status':'ok','title':'shirt','bullets':[],'description':'','keywordData':[],'limitations':[]}
  with patch('competitors.sellersprite.read_sources',return_value=[source]), patch('competitors.review_insights.collect',side_effect=ValueError('quota')), patch('competitors.provider.research_json',return_value={'keywords':[]}):
   result=competitors.analyse({'market':'UK','asins':'B0FVS1X3SP','source':'sellersprite','includeReviews':True})
  self.assertEqual(result['reviewReport']['error'],'quota')
  self.assertEqual(result['sources'][0]['status'],'ok')
 def test_site_scoping(self):
  product={'reviewResearch':{'UK':{'analysis':{'themes':[{'title':'Sizing'}]}}}}
  self.assertEqual(reviews.context(product,'US'),{});self.assertEqual(len(reviews.context(product,'UK')['themes']),1)

if __name__=='__main__':unittest.main()
