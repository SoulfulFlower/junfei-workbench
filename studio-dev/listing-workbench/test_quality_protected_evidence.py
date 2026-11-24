import json,tempfile,unittest,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import quality_protected_evidence as evidence
import automatic_image_quality as quality
from test_automatic_image_quality import accepted

class ProtectedEvidence(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.run=self.root/'canonical';self.run.mkdir()
  self.source=Image.new('RGBA',(100,100),(216,179,173,255));a=np.zeros((100,100),'uint8');a[30:90,30:90]=255;self.mask=Image.fromarray(a)
  rgb=np.asarray(self.source).copy();rgb[a>0,:3]=[100,100,100];self.output=Image.fromarray(rgb)
  h=np.zeros((100,100),'uint8');h[5:25,5:25]=14;np.savez(self.run/'local-labels.npz',human=h)
  self.source.save(self.run/'source.png');self.receipt={'version':'automatic-garment-selection-fixture','runPath':str(self.run),
   'sourceHashEncoding':'rgba8_top_to_bottom','maskHashEncoding':'l8_top_to_bottom','sourceSize':[100,100],
   'sourcePixelSha256':hashlib.sha256(self.source.tobytes()).hexdigest(),'maskPixelSha256':hashlib.sha256(self.mask.tobytes()).hexdigest(),
   'accepted':True,'verified':True,'independentReview':{'accepted':True}}
 def test_unchanged_skin_evidence_does_not_confuse_adjacent_changed_cloth(self):
  image,meta=evidence.build(self.source,self.mask,self.output,self.receipt,self.root)
  self.assertIsNotNone(image);self.assertEqual(meta['tiles'][0]['semanticRegionChangedRgbaPixels'],0)
  self.assertFalse(meta['certifiesPreservation']);self.assertEqual(meta['tiles'][0]['semanticRegionSelectedPixels'],0)
 def test_actual_skin_change_is_visible_and_counted(self):
  b=np.asarray(self.output).copy();b[10,10,:3]=[100,100,100]
  _,meta=evidence.build(self.source,self.mask,Image.fromarray(b),self.receipt,self.root)
  self.assertEqual(meta['tiles'][0]['semanticRegionChangedRgbaPixels'],1)
 def test_bad_source_and_cross_account_evidence_are_rejected(self):
  with self.assertRaises(ValueError):evidence.build(self.source,self.mask,self.output,self.receipt,self.root/'other')
  Image.new('RGBA',(100,100)).save(self.run/'source.png')
  with self.assertRaises(ValueError):evidence.build(self.source,self.mask,self.output,self.receipt,self.root)
 def test_numeric_zero_never_overrides_a_false_independent_preservation_flag(self):
  def vision(instruction,context,images):
   self.assertEqual(context['protectedInspection']['tiles'][0]['semanticRegionChangedRgbaPixels'],0)
   reply=accepted();reply.update(blocking=True,protectedPartsPreserved=False,category='selection',issues=['uncertain source ownership'],locations=[{'kind':'leak','point':[.1,.1],'reason':'uncertain source ownership'}]);return reply
  result=quality.check_colour(self.source,self.mask,self.output,'#646464',vision=vision,cache_root=self.root/'qa',selection_receipt=self.receipt)
  self.assertFalse(result['passed']);self.assertFalse(result['protectedPartsPreserved']);self.assertIn('protected.png',result['artifactSha256'])
 def test_protected_artifact_tampering_cannot_reuse_a_pass(self):
  calls=[]
  def vision(*args):calls.append(1);return accepted()
  args={'vision':vision,'cache_root':self.root/'qa','selection_receipt':self.receipt,'vision_identity':{'provider':'fixture','model':'fixture'}}
  one=quality.check_colour(self.source,self.mask,self.output,'#646464',**args)
  (Path(one['auditPath']).parent/'protected.png').write_bytes(b'tampered')
  two=quality.check_colour(self.source,self.mask,self.output,'#646464',**args)
  self.assertFalse(two['cacheHit']);self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
