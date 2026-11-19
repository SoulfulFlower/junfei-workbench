import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import colour_sets as colours
import colour_binding


class AutomaticColourBindingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
  self.product={'id':'coat','sku':'P','masterColor':'Gray','sourceUrl':'https://detail.1688.com/offer/1.html',
    'supplierColorReferences':[{'url':'https://example.test/gray.jpg','color':'Gray'}, {'url':'https://example.test/red.jpg','color':'Red'}],
    'sourceImport':{'amazon':{'variants':[{'sku':'GRAY-S','color_name':'Gray','size_name':'Small'},
      {'sku':'RED-S','color_name':'Red','size_name':'Small'},{'sku':'RED-M','color_name':'Red','size_name':'Medium'}]}},
    'supplierVariantCoverage':{'productId':'coat','sourceUrl':'https://detail.1688.com/offer/1.html','evidence':'Supplier fixture',
       'checkedAt':'2026-11-15T00:00:00Z','supplierObservedColors':['Gray','Red'],'supplierObservedSizes':['S','M']}}
  self.record={'id':'red','productId':'coat','masterId':'master','color':'Red','colorKey':'red','reference':'https://example.test/red.jpg',
    'status':'awaiting_manual','validated':True,'manual':False,'items':[{'slot':i,'status':'awaiting_manual','image':f'/uploads/result{i}.png',
       'qc':{'pass':True,'issues':[],'warnings':['Minor cosmetic fringe']}} for i in range(7)]}
  self.patches=[patch.object(colours,'DB',root/'colours.sqlite3'),
    patch.object(colours.studio_bridge,'latest_project',return_value={'id':'master','references':['https://example.test/gray.jpg']}),
    patch.object(colours.image_provider.image_budget,'configuration',return_value={'gallery_count':7}),
    patch.object(colours.image_provider,'submit'),patch.object(colours.visual,'model_json')]
  for p in self.patches:p.start()
  colours.save(self.record)
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def sync(self):return colours.current_sets('coat',self.product)['sets'][0]
 def test_links_exact_skus_in_slot_order_without_human_approval_and_is_idempotent(self):
  saved=self.sync();binding=saved['skuBinding']
  self.assertEqual(binding['skus'],['RED-S','RED-M'])
  self.assertEqual([i['slot'] for i in binding['images']],list(range(7)))
  self.assertFalse(saved['manual']);self.assertTrue(all(i['status']=='awaiting_manual' for i in saved['items']))
  self.assertEqual(self.sync()['skuBinding'],binding)
  self.assertNotIn('skuBindingHistory',self.sync())
  colours.image_provider.submit.assert_not_called();colours.visual.model_json.assert_not_called()
 def test_missing_failed_unknown_and_wrong_product_reference_never_bind(self):
  for mutation in (
   lambda r:r['items'].pop(),lambda r:r['items'][0].update(status='submit_unknown'),
   lambda r:r['items'][0]['qc'].update({'pass':False,'issues':[]}),
   lambda r:r['items'][0]['qc'].update(issues=['Wrong colour']),
   lambda r:r.update(reference='https://example.test/gray.jpg'),lambda r:r.update(validated=False)):
   with self.subTest(mutation=mutation):
    r=copy.deepcopy(self.record);mutation(r);colours.save(r)
    self.assertNotEqual((self.sync().get('skuBinding') or {}).get('status'),'linked')
 def test_changed_images_and_sku_eligibility_revoke_old_receipt(self):
  before=self.sync();changed=copy.deepcopy(before);changed['items'][0]['qc']={'pass':False,'issues':['Wrong colour']};colours.save(changed)
  after=self.sync();self.assertEqual(after['skuBinding']['status'],'blocked')
  self.assertEqual(after['skuBindingHistory'][0],before['skuBinding'])
  self.assertFalse(colours.binding_ready(after,self.product))
  self.assertFalse(after['manual'])
 def test_two_complete_versions_do_not_choose_skus_implicitly(self):
  other=copy.deepcopy(self.record);other['id']='red-second';colours.save(other)
  view=colours.current_sets('coat',self.product)
  self.assertTrue(all((s.get('skuBinding') or {}).get('status')!='linked' for s in view['sets']))
 def test_image_changes_and_availability_changes_invalidate_association(self):
  before=self.sync();changed=copy.deepcopy(before);changed['items'][0]['image']='/uploads/replaced.png';colours.save(changed)
  self.assertFalse(colours.binding_ready(changed,self.product))
  rebound=self.sync();self.assertNotEqual(rebound['skuBinding']['signature'],before['skuBinding']['signature'])
  self.product['supplierVariantCoverage']['supplierObservedColors']=['Gray']
  self.assertEqual(self.sync()['skuBinding']['status'],'blocked')
 def test_master_change_invalidates_old_binding(self):
  before=self.sync()
  with patch.object(colours.studio_bridge,'latest_project',return_value={'id':'another-master','references':['https://example.test/gray.jpg']}):
   self.assertFalse(colours.binding_ready(before,self.product))
   self.assertEqual(colours.current_sets('coat',self.product)['sets'],[])
 def test_concurrent_image_update_is_not_overwritten_by_binding_receipt(self):
  original=colour_binding.candidate;changed=False
  def concurrent(*args):
   nonlocal changed
   result=original(*args)
   if not changed:
    changed=True;new=colours.get('red');new['items'][0]['image']='/uploads/concurrent.png';colours.save(new)
   return result
  with patch.object(colour_binding,'candidate',side_effect=concurrent):view=self.sync()
  self.assertTrue(view['bindingPending'])
  self.assertEqual(colours.get('red')['items'][0]['image'],'/uploads/concurrent.png')
  self.assertNotIn('skuBinding',colours.get('red'))
  self.assertEqual(self.sync()['skuBinding']['images'][0]['image'],'/uploads/concurrent.png')
 def test_background_completion_binds_without_page_or_workspace_mutation(self):
  path=colours.DB.parent/'studio.sqlite3'
  body=json.dumps({'products':[self.product]})
  with closing(sqlite3.connect(path)) as conn:
   conn.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,body TEXT)')
   conn.execute('INSERT INTO workspace VALUES(1,?)',(body,))
   conn.commit()
  colours.bind_finished(self.record)
  self.assertEqual(colours.get('red')['skuBinding']['skus'],['RED-S','RED-M'])
  with closing(sqlite3.connect(path)) as conn:self.assertEqual(conn.execute('SELECT body FROM workspace').fetchone()[0],body)


if __name__=='__main__':unittest.main()
