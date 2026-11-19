import unittest,io,json,zipfile,csv,tempfile
from pathlib import Path
from unittest.mock import patch
import delivery_export as d
class ExportTest(unittest.TestCase):
 def test_aplus_is_separate_and_never_shifts_gallery_numbering(self):
  image=lambda rid:{'_runId':rid,'final_url':'url','_status':'approved','human_reviewed':True,'render_qa':{'ready':True}}
  view={'sets':{'aplus':{'images':[image('aplus')]},'gallery':{'images':[image('main'),image('detail')]}}}
  with patch.object(d.studio_bridge,'result_image',side_effect=lambda rid:(rid.encode(),'image/png')),patch.object(d.colour_sets,'list_sets',return_value={'sets':[]}):
   raw=d.build({'id':'p','sku':'SKU','masterColor':'Red'},{'title':'Saved'},view)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertEqual(z.read('SKU/Red01.png'),b'main')
   self.assertEqual(z.read('SKU/Red02.png'),b'detail')
   self.assertEqual(z.read('SKU/aplus/Red01.png'),b'aplus')
   self.assertEqual(len(z.namelist()),len(set(z.namelist())))

 def test_observed_sparse_variants_do_not_expand_to_cartesian_or_depend_on_reference_order(self):
  p={'colorNames':'Brown, Camel, Light Pink, Yellow','sizeNames':'Small, Medium, Large, X-Large',
     'supplierColorReferences':[{'color':'Yellow','url':'yellow'},{'color':'Brown','url':'brown'}],
     'sourceImport':{'amazon':{'variants':[{'asin':'A','color_name':'Light Pink','size_name':'Large'},
      {'asin':'B','color_name':'Brown','size_name':'Small'}]}}}
  rows=list(d.variant_rows(p,'SKU'))
  self.assertEqual(len(rows),2);self.assertEqual([r[0] for r in rows],['SKU-C03-L','SKU-C01-S'])
  self.assertEqual(rows[0][-1],'A');self.assertEqual(rows[0][4],'');self.assertEqual(rows[1][4],'brown')
 def test_explicit_empty_or_ambiguous_observed_variants_never_invent_children(self):
  p={'supplierColorReferences':[{'color':'Red','url':'red'}],'sizeNames':'S,M','sourceImport':{'amazon':{'variants':[]}}}
  self.assertEqual(list(d.variant_rows(p,'SKU')),[])
  p['sourceImport']['amazon']['variants']=[{'color_name':'Red','size_name':'S'},{'color_name':'Red','size_name':'S'}]
  with self.assertRaisesRegex(ValueError,'重复'):list(d.variant_rows(p,'SKU'))
 def test_images_with_unreviewed_status_are_never_exported(self):
  view={'sets':{'gallery':{'images':[{'_runId':'candidate','final_url':'local:x','_status':'local_recolor_candidate'}]}}}
  variants={'sets':[{'id':'red','color':'Red','items':[{'slot':0,'status':'reviewing','image':'local:y'}]}]}
  with patch.object(d.studio_bridge,'result_image') as master,patch.object(d.colour_sets,'image_bytes') as variant,patch.object(d.colour_sets,'list_sets',return_value=variants):
   raw=d.build({'id':'p','sku':'S'},{'title':'Saved'},view)
  master.assert_not_called();variant.assert_not_called()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   manifest=json.loads(z.read('S/image-manifest.json'));self.assertEqual(manifest['images'],[]);self.assertEqual(len(manifest['excluded']),2)
 def test_missing_main_keeps_secondary_number_and_excludes_failed_image(self):
  view={'sets':{'gallery':{'images':[{}, {'_runId':'good','final_url':'url','_status':'awaiting_manual'}, {'_runId':'bad','final_url':'url','_status':'needs_revision'}]}}}
  with patch.object(d.studio_bridge,'result_image',return_value=(b'good','image/png')) as read,patch.object(d.colour_sets,'list_sets',return_value={'sets':[]}):
   raw=d.build({'id':'p','sku':'SKU1'},{'title':'Saved'},view)
  read.assert_called_once_with('good')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertIn('SKU1/A2.png',z.namelist());self.assertNotIn('SKU1/A1.png',z.namelist())
   manifest=json.loads(z.read('SKU1/image-manifest.json'))
   self.assertEqual(manifest['missing'],['gallery/1','gallery/3'])
   self.assertEqual(manifest['excluded'][0]['runId'],'bad')
 def test_replacement_master_excludes_old_colour_artwork(self):
  view={'sets':{'gallery':{'_projectId':'new','images':[]}}}
  variants={'sets':[{'id':'old-red','masterId':'old','color':'Red','items':[{'slot':0,'image':'old','status':'done'}]}]}
  with patch.object(d.colour_sets,'list_sets',return_value=variants),patch.object(d.colour_sets,'image_bytes') as read:
   raw=d.build({'id':'p','sku':'S'},{'title':'Replacement'},view)
  read.assert_not_called()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertEqual(json.loads(z.read('S/image-manifest.json'))['images'],[])
 def test_partial_variant_export_maps_images_and_missing_slots(self):
  p={'id':'p','sku':'SKU1','masterColor':'Black','supplierColorReferences':[{'color':'Red','english':'Red','url':'source'}],'sizeNames':'XS,S'}
  sets={'sets':[{'id':'red','color':'Red','items':[{'slot':0,'status':'awaiting_manual','image':'out'},{'slot':1,'status':'queued'}],'referenceWarnings':['finish uncertain']}]}
  view={'sets':{'gallery':{'images':[{'_runId':'base','final_url':'url','_status':'awaiting_manual'}]}}}
  with patch.object(d.studio_bridge,'result_image',return_value=(b'base','image/png')),patch.object(d.colour_sets,'image_bytes',return_value=(b'red','image/png')),patch.object(d.colour_sets,'list_sets',return_value=sets):
   raw=d.build(p,{'title':'Saved title'},view)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertIsNone(z.testzip());manifest=json.loads(z.read('SKU1/image-manifest.json'));self.assertEqual(manifest['missing'],['Red/2']);self.assertEqual(len(manifest['images']),2);self.assertEqual(manifest['images'][1]['referenceWarnings'],['finish uncertain']);self.assertFalse(manifest['images'][1]['humanReviewed']);self.assertEqual(z.read('SKU1/Red01.png'),b'red')
   variants=list(csv.DictReader(io.StringIO(z.read('SKU1/variants.csv').decode('utf-8-sig'))))
   self.assertEqual(len(variants),2)
   for variant in variants:
    self.assertEqual(variant['main_image'],'SKU1/Red01.png');self.assertEqual(variant['generated_images'],'SKU1/Red01.png');self.assertEqual(variant['image_count'],'1')

 def test_review_binds_complete_colour_gallery_to_only_matching_children(self):
  gray='https://example.test/gray.jpg';red='https://example.test/red.jpg';source='https://detail.1688.com/offer/123.html'
  children=[{'sku':'GRAY-S','color_name':'Dark Gray','size_name':'Small'},
            {'sku':'GRAY-M','color_name':'Dark Gray','size_name':'Medium'},
            {'sku':'RED-S','color_name':'Red','size_name':'Small'},
            {'sku':'RED-M','color_name':'Red','size_name':'Medium'},
            {'sku':'BLACK-S','color_name':'Black','size_name':'Small'}]
  p={'id':'p','sku':'P','masterColor':'深灰','sourceUrl':source,
     'supplierColorReferences':[{'url':gray,'color':'深灰','english':'Dark Gray'},{'url':red,'color':'红色','english':'Red'}],
     'sourceImport':{'amazon':{'variants':children}},
     'supplierVariantCoverage':{'productId':'p','sourceUrl':source,'evidence':'supplier option fixture',
       'checkedAt':'2026-11-08T12:00:00+08:00','supplierObservedColors':['Dark Gray','Red'],
       'supplierObservedSizes':['S','M']}}
  images=[{'_runId':str(i),'final_url':'url','_status':'approved','human_reviewed':True} for i in range(7)]
  view={'sets':{'gallery':{'_projectId':'plan','product_source_url':gray,'images':images},
                'aplus':{'images':images[:1]}}}
  variant={'id':'red','productId':'p','masterId':'plan','color':'红色','colorKey':'red','reference':red,
           'status':'awaiting_manual','validated':True,'items':[{'slot':i,'status':'awaiting_manual','image':'out','qc':{'pass':True,'warnings':['Minor cosmetic fringe']}}
                                               for i in reversed(range(7))]}

  def export_rows():
   raw=d.build(p,{'title':'Saved'},view)
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    manifest=json.loads(z.read('P/image-manifest.json'))['images']
    rows=list(csv.DictReader(io.StringIO(z.read('P/variants.csv').decode('utf-8-sig'))))
    draft={row['sku']:row for row in csv.DictReader(io.StringIO(z.read('P/draft-variant-image-bindings.csv').decode('utf-8-sig')))}
    if view['sets']['gallery']['product_source_url']==gray:
     self.assertEqual(draft['RED-S']['image_count'],'7')
     self.assertEqual(draft['RED-S']['draft_generated_images'],draft['RED-M']['draft_generated_images'])
     self.assertEqual(draft['RED-S']['warnings'],'Minor cosmetic fringe')
     self.assertEqual(draft['RED-S']['human_reviewed'],str(d.colour_sets.get('red').get('manual',False)))
     self.assertEqual(draft['BLACK-S']['image_count'],'0')
    else:self.assertTrue(all(row['image_count']=='0' for row in draft.values()))
    return {row['sku']:row for row in rows},{image['file']:image for image in manifest}

  with tempfile.TemporaryDirectory() as folder, \
       patch.object(d.colour_sets,'DB',Path(folder)/'sets.sqlite3'), \
       patch.object(d.studio_bridge,'latest_project',return_value={'id':'plan','references':[gray]}), \
       patch.object(d.studio_bridge,'result_image',return_value=(b'master','image/png')), \
       patch.object(d.colour_sets,'image_bytes',return_value=(b'red','image/png')):
   d.colour_sets.save(variant)
   before,_=export_rows()
   self.assertEqual(before['RED-S']['image_count'],'0')
   self.assertEqual(before['GRAY-S']['image_count'],'7')
   automatic=d.colour_sets.current_sets('p',p)['sets'][0]
   self.assertFalse(automatic.get('manual',False))
   self.assertEqual(automatic['skuBinding']['skus'],['RED-S','RED-M'])
   automatic_rows,automatic_manifest=export_rows()
   self.assertEqual(automatic_rows['RED-S']['image_count'],'7')
   self.assertEqual(automatic_rows['RED-S']['generated_images'],automatic_rows['RED-M']['generated_images'])
   automatic_files=automatic_rows['RED-S']['generated_images'].split('|')
   self.assertTrue(all(automatic_manifest[file]['skuBindingReady'] and not automatic_manifest[file]['humanReviewed'] for file in automatic_files))
   with self.assertRaisesRegex(ValueError,'没有关联'):
    d.colour_sets.select_variant(p,'red',gray)
   d.colour_sets.approve({'id':'red','checked':True},p)
   after,manifest=export_rows()
   self.assertEqual(after['BLACK-S']['image_count'],'0')
   for left,right,key in [('GRAY-S','GRAY-M','dark gray'),('RED-S','RED-M','red')]:
    files=after[left]['generated_images'].split('|')
    self.assertEqual(after[left]['generated_images'],after[right]['generated_images'])
    self.assertEqual(after[left]['main_image'],files[0])
    self.assertEqual([manifest[file]['slot'] for file in files],list(range(7)))
    self.assertTrue(all(manifest[file]['colorKey']==key for file in files))
   view['sets']['gallery']['product_source_url']=red
   mismatch,_=export_rows()
   self.assertEqual(mismatch['GRAY-S']['image_count'],'0')
   self.assertEqual(mismatch['RED-S']['image_count'],'0')

 def backup_fixture(self):
  colors=['Black','White','Red','Brown','Gray'];excluded=['Blue','Pink','Green','Purple','Yellow']
  sizes=['S','M','L','XL','XXL','3XL'];source='https://detail.1688.com/offer/123.html'
  children=[{'sku':f'P-{color}-{size}','asin':f'B{n:09d}','color_name':color,'size_name':size}
            for n,(color,size) in enumerate((color,size) for color in colors+excluded for size in sizes)]
  p={'id':'p','sku':'P','masterColor':'Black','colorNames':','.join(colors+excluded),'sourceUrl':source,
     'supplierColorReferences':[{'url':f'https://example.test/{color}.jpg','color':color} for color in colors],
     'sourceImport':{'amazon':{'variants':children,'listingEligibleVariants':children[:30],
                              'excludedVariants':[{**row,'reason':'no same-colour supplier evidence'} for row in children[30:]]}},
     'supplierVariantCoverage':{'productId':'p','sourceUrl':source,'evidence':'supplier evidence fixture',
       'checkedAt':'2026-11-15T12:00:00+08:00','supplierObservedColors':colors,'supplierObservedSizes':sizes}}
  view={'sets':{'gallery':{'_projectId':'plan','product_source_url':'https://example.test/Black.jpg',
        'images':[{'_runId':f'master-{i}','final_url':'saved','_status':'awaiting_manual',
                   'human_reviewed':False,'render_qa':{'ready':True}} for i in range(7)]}}}
  sets=[{'id':color,'productId':'p','masterId':'plan','color':color,'colorKey':color.lower(),
         'reference':f'https://example.test/{color}.jpg','status':'awaiting_manual','validated':True,
         'skuBinding':{'mode':'automatic_qc','status':'linked','masterId':'plan','colorKey':color.lower()},
         'items':[{'slot':i,'status':'awaiting_manual','image':f'{color}-{i}',
                   'qc':{'pass':True,'warnings':['minor fringe']}} for i in range(7)]}
        for color in colors[1:]]
  return p,view,sets

 def backup_archive(self,p,view,sets):
  with patch.object(d.generated_gallery,'export_images',return_value=None), \
       patch.object(d.colour_sets,'list_sets',return_value={'sets':sets}), \
       patch.object(d.colour_sets,'binding_ready',return_value=True), \
       patch.object(d.studio_bridge,'result_image',side_effect=lambda rid:(rid.encode(),'image/png')), \
       patch.object(d.colour_sets,'image_bytes',side_effect=lambda sid,slot:(f'{sid}-{slot}'.encode(),'image/png')), \
       patch.object(d.image_budget,'configuration',return_value={'gallery_count':7}):
   return d.build(p,{'title':'Saved'},view)

 def test_backup_exports_30_original_children_excludes_history_and_maps_black_master(self):
  p,view,sets=self.backup_fixture();before=json.dumps(p,sort_keys=True)
  raw=self.backup_archive(p,view,sets)
  self.assertEqual(json.dumps(p,sort_keys=True),before)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   manifest=json.loads(z.read('P/image-manifest.json'))
   images={image['file']:image for image in manifest['images']}
   expected={row['sku'] for row in p['sourceImport']['amazon']['listingEligibleVariants']}
   self.assertEqual(len(images),35);self.assertFalse(manifest['reviewRequired']);self.assertFalse(manifest['humanReviewed'])
   self.assertEqual(manifest['reviewIssues'],[]);self.assertEqual(manifest['childSkuCount'],30)
   self.assertTrue(manifest['parentSkuIsGroupingOnly']);self.assertEqual(len(manifest['excludedVariants']),30)
   self.assertTrue(all(row['reason']=='no same-colour supplier evidence' for row in manifest['excludedVariants']))
   self.assertIn('P/备份说明.txt',z.namelist());self.assertNotIn('P/审核说明.txt',z.namelist())
   for filename,image_field,main_field in [('variants.csv','generated_images','main_image'),
                                         ('draft-variant-image-bindings.csv','draft_generated_images','draft_main_image')]:
    rows=list(csv.DictReader(io.StringIO(z.read('P/'+filename).decode('utf-8-sig'))))
    self.assertEqual(len(rows),30);self.assertEqual({row['sku'] for row in rows},expected)
    for row in rows:
     files=row[image_field].split('|');self.assertEqual(row['image_count'],'7');self.assertEqual(row[main_field],files[0])
     self.assertEqual([images[file]['slot'] for file in files],list(range(7)))
     self.assertTrue(all(images[file]['colorKey']==row['color_key'] for file in files))
   self.assertEqual(z.read('P/Black01.png'),b'master-0');self.assertEqual(z.read('P/Black07.png'),b'master-6')
   self.assertEqual(images['P/Black01.png']['bindingSource']['mode'],'current_master_gallery')
   self.assertEqual(images['P/White01.png']['skuBinding']['mode'],'automatic_qc')

 def test_backup_explicit_empty_eligibility_does_not_restore_excluded_or_make_combinations(self):
  p,view,sets=self.backup_fixture();p['sourceImport']['amazon']['listingEligibleVariants']=[]
  with zipfile.ZipFile(io.BytesIO(self.backup_archive(p,view,sets))) as z:
   for filename in ['variants.csv','draft-variant-image-bindings.csv']:
    self.assertEqual(list(csv.DictReader(io.StringIO(z.read('P/'+filename).decode('utf-8-sig')))),[])
   manifest=json.loads(z.read('P/image-manifest.json'));self.assertEqual(manifest['childSkuCount'],0)
   self.assertTrue(manifest['reviewRequired']);self.assertEqual(len(manifest['excludedVariants']),60)

 def test_backup_review_required_tracks_actual_missing_image_instead_of_human_flag(self):
  p,view,sets=self.backup_fixture();sets[0]['items'][6]['qc']['pass']=False
  with zipfile.ZipFile(io.BytesIO(self.backup_archive(p,view,sets))) as z:
   manifest=json.loads(z.read('P/image-manifest.json'));self.assertTrue(manifest['reviewRequired'])
   self.assertEqual({issue['code'] for issue in manifest['reviewIssues']},
                    {'missing_images','incomplete_child_image_bindings'})
   gaps=next(issue['items'] for issue in manifest['reviewIssues'] if issue['code']=='incomplete_child_image_bindings')
   self.assertEqual(len(gaps),6);self.assertTrue(all(row['colorKey']=='white' for row in gaps))
if __name__=='__main__':unittest.main()
