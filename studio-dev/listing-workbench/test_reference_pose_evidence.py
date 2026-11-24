import copy,unittest
import cv2,numpy as np
from PIL import Image
import reference_pose_evidence as m
import automatic_local_selection as local
import local_hair_matte as hair

class ReferenceEvidenceTests(unittest.TestCase):
    def fixture(self):
        rgb=np.random.default_rng(83).integers(35,200,(256,256,3),dtype='uint8')
        cloth=np.zeros((256,256),bool);cloth[40:216,40:216]=True
        human=np.full(cloth.shape,2,'uint8');human[cloth]=4
        target=rgb.copy();target[cloth]=(target[cloth].astype(int)+[35,-20,15]).astype('uint8')
        base={'human':human,'kind':'upper','primary':cloth,'semanticGarmentClasses':[4],
            'protected':~cloth,'sourceLab':cv2.cvtColor(rgb.astype('float32')/255,cv2.COLOR_RGB2LAB)}
        return Image.fromarray(rgb),Image.fromarray(target),Image.fromarray(cloth.astype('uint8')*255),base
    def test_real_same_view_colour_signal_is_evidence_not_acceptance(self):
        args=self.fixture();before=[x.tobytes()for x in args[:3]];r=m.analyze(*args)
        self.assertTrue(r['audit']['accepted']);self.assertFalse(r['audit']['certifiesSelection'])
        self.assertFalse(r['audit']['referencePixelsUsedAsOutput']);self.assertTrue(r['unchanged'][10,10]);self.assertFalse(r['unchanged'][100,100])
        self.assertEqual(before,[x.tobytes()for x in args[:3]])
    def test_same_image_without_cloth_colour_change_cannot_identify_hair(self):
        s,t,a,b=self.fixture();self.assertFalse(m.analyze(s,s,a,b)['audit']['accepted'])
    def test_changed_non_target_and_different_pose_are_rejected(self):
        s,t,a,b=self.fixture();changed=np.asarray(t).copy();changed[~b['primary']]=0
        self.assertFalse(m.analyze(s,Image.fromarray(changed),a,b)['audit']['accepted'])
        self.assertFalse(m.analyze(s,t.rotate(8),a,b)['audit']['accepted'])
    def test_zero_features_reject_without_guess(self):
        s,t,a,b=self.fixture();self.assertFalse(m.analyze(Image.new('RGB',s.size),t,a,b)['audit']['accepted'])
    def test_only_independently_supported_unchanged_hair_alpha_can_decrease(self):
        a=Image.new('L',(256,256),255);cm=np.full((256,256),255,'uint8');cm[30:220,100:120]=0
        nm=255-cm;h=np.where(nm>0,2,4);stable=nm>0;stable[80,110]=False
        before=a.tobytes();out,r=hair.protect_unchanged_reference(a,Image.fromarray(cm),Image.fromarray(nm),h,stable,evidence_point=[110,100])
        self.assertEqual(out.getpixel((110,100)),0);self.assertEqual(out.getpixel((110,80)),255)
        self.assertEqual(out.getpixel((200,100)),255);self.assertEqual(a.tobytes(),before);self.assertFalse(r['accepted'])
        with self.assertRaises(ValueError):hair.protect_unchanged_reference(a,Image.fromarray(cm),Image.fromarray(nm),h,stable,evidence_point=[110,80])
    def test_budget_planner_never_relaxes_existing_limits_or_edits_mask(self):
        source=Image.new('RGB',(1024,1024));a=Image.new('L',source.size,255);h=np.zeros((1024,1024),'uint8');h[400:570,400:435]=2
        u=h==2;rows=[{'regionId':0,'bboxPixels':[350,350,606,606],'reportedKind':'leak','reportedPoint':[420/1023,450/1023],'reportedPointPixels':[420,450]}]
        before=a.tobytes();planned=local._budgeted_reference_regions(source,rows,a,h,u)
        self.assertLessEqual(len(planned),6)
        covered=np.zeros(h.shape,bool)
        for row in planned:
            x0,y0,x1,y1=row['bboxPixels'];covered[y0+8:y1-8,x0+8:x1-8]=True
        self.assertFalse((u&~covered).any())
        for row in planned:self.assertLessEqual(row['referenceRiskUpperBound'],row['unchangedMaximumChangedPixels'])
        self.assertEqual(a.tobytes(),before)
        h[:]=0;h[100:270,100:135]=2
        rows[0]['reportedPointPixels']=[120,150]
        with self.assertRaises(local.LocalSelectionRejected):local._budgeted_reference_regions(source,rows,a,h,h==2)
        h[:]=2
        with self.assertRaises(local.LocalSelectionRejected):local._budgeted_reference_regions(source,rows,a,h,h==2)
    def test_unbound_reference_stops_before_paid_grounding(self):
        from test_automatic_local_selection import AutomaticLocalSelectionTests,LocalVision
        case=AutomaticLocalSelectionTests();case.setUp()
        try:
            data=case.fixture();vision=LocalVision()
            with self.assertRaises(local.LocalSelectionRejected):case.run_correct(data,vision,reference=data[0])
            self.assertEqual(vision.calls,[])
        finally:case.doCleanups()

    def test_machine_witness_requires_visual_choice_and_never_uses_drifting_coordinates(self):
        source=Image.new('RGB',(512,512));regions=[{'regionId':0,'bboxPixels':[128,128,384,384],
            'referenceWitnessesHypothesisOnly':[[220,220],[230,240]]}]
        row={'regionId':0,'status':'true_leak','classification':'non_target','reason':'actual source-visible dyed hair',
            'assessedEntireRegion':True,'nonTargetDyeObserved':True,'evidencePoint':[.7,.7],
            'foreground':[{'point':[.6,.6],'evidence':'actual source knit'}],
            'background':[{'point':[.4,.4],'kind':'hair','evidence':'actual source hair'}]}
        with self.assertRaises(local.LocalSelectionRejected):local._grounded({'regions':[row]},regions,source)
        row['evidenceWitnessId']=1;result=local._grounded({'regions':[row]},regions,source)[0]
        self.assertEqual(result['evidencePointPixels'],[230,240]);self.assertEqual(result['evidenceWitnessId'],1)
        row['evidenceWitnessId']=True
        with self.assertRaises(local.LocalSelectionRejected):local._grounded({'regions':[row]},regions,source)

if __name__=='__main__':unittest.main()
