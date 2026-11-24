import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
import automatic_garment_selection as selection
import automatic_local_selection as tool

SUBJECT={'productName':'fixture coat','target':'fixture coat','role':'source_garment'}
META={'provider':'isolated Codex fixture','model':'fixture'}


def accepted_review():return {'accepted':True,'issues':[],'misses':[],'leaks':[],'warnings':[]}


class OriginalBackend:
    def __init__(self,missing=True,soft=False,leak=False):self.missing=missing;self.soft=soft;self.leak=leak
    def identity(self):return {'fixture':'canonical-global','missing':self.missing,'soft':self.soft,'leak':self.leak}
    def labels(self,source):
        c=np.zeros((512,512),'uint8');h=np.zeros_like(c);c[64:448,128:384]=1;h[64:448,128:384]=4
        if not self.soft:h[180:340,282:289]=16
        return c,h,{'fixture':'pinned-synthetic-labels'}
    def select(self,source,coarse,protected,points,cache):
        rgb=np.asarray(source.convert('RGB'));a=((np.asarray(coarse)>0)&(rgb[:,:,0]>rgb[:,:,1])).astype('uint8')*255
        if self.missing:a[250:262,250:262]=0
        if self.leak:a[256,120]=75
        a[np.asarray(protected)>0]=0
        return Image.fromarray(a),{'fixture':'canonical-source-candidate'}
    def matte(self,source,mask,protected,points):return mask,{'fixture':'no-new-matte'}


class OriginalVision:
    def __init__(self,soft=False):self.soft=soft
    def __call__(self,instruction,context,images):
        if instruction.startswith('Independently'):return {'result':accepted_review(),'receipt':{'fixture':'canonical-review'}}
        p={'foreground':[{'point':p,'part':'cloth','evidence':'visible fixture cloth'} for p in ([.35,.3],[.65,.7])],
            'background':[{'point':[.05,.05],'kind':'background','evidence':'actual external background'}],
            'protections':[],'visibleParts':['body'],'limitations':[]}
        if self.soft:p['protections']=[{'kind':'accessory','path':[[285/511,180/511],[285/511,339/511]],
            'widthFraction':.04,'evidence':'model ribbon hypothesis without a separate occluder point'}]
        return {'result':p,'receipt':{'fixture':'canonical-plan'}}


class LocalBackend:
    def __init__(self,bad_hash=False,missing_occluder=False):self.calls=[];self.bad_hash=bad_hash;self.missing_occluder=missing_occluder
    def identity(self):return {'fixture':'native-local-pixel-classifier','badHash':self.bad_hash,'missingObject':self.missing_occluder}
    def predict(self,crop,foreground,background,*,cache_root,role):
        self.calls.append({'source':crop.copy(),'foreground':foreground,'background':background,'role':role})
        rgb=np.asarray(crop.convert('RGB'))
        selected=rgb[:,:,0]>rgb[:,:,1] if role=='target_cloth' else rgb[:,:,1]>rgb[:,:,0]
        if role=='occluder' and self.missing_occluder:selected[:]=True
        mask=Image.fromarray(selected.astype('uint8')*255)
        return mask,{'role':role,'sourcePixelSha256':'wrong' if self.bad_hash else selection._pixels(crop,'RGBA'),
            'maskPixelSha256':selection._pixels(mask,'L'),'accepted':False,'verified':False,'rawLogitMask':True}


class LocalVision:
    def __init__(self,status='true_miss',review=None,fail_phase=None,include_occluder=False,fg=None):
        self.status=status;self.review=review or accepted_review();self.fail_phase=fail_phase
        self.include_occluder=include_occluder;self.fg=fg;self.calls=[]
    def __call__(self,instruction,context,images):
        self.calls.append({'instruction':instruction,'context':copy.deepcopy(context),'images':images})
        if context['phase']==self.fail_phase:raise RuntimeError('actual fixture transport timeout')
        if context['phase']=='local_source_review':return {'result':copy.deepcopy(self.review),'receipt':{'fixture':'fresh source review'}}
        rows=[]
        for region in context['regions']:
            point=self.fg or region['reportedPoint']
            row={'regionId':region['regionId'],'status':self.status,
                'classification':'visible_target_cloth' if self.status=='true_miss' else 'already_correct' if self.status=='no_edit_justified' else 'uncertain',
                'reason':'inspect actual aligned source alpha and output; source ownership evidence',
                'assessedEntireRegion':True,'nonTargetDyeObserved':False,'evidencePoint':point,
                'foreground':[], 'background':[], 'occluder':[]}
            if self.status=='true_miss':
                row['foreground']=[{'point':point,'evidence':'clean interior missing target cloth'}]
                row['background']=[{'point':[285/511,256/511],'kind':'accessory','evidence':'actual green local strap'}]
                if self.include_occluder:row['occluder']=copy.deepcopy(row['background'])
            rows.append(row)
        return {'result':{'regions':rows},'receipt':{'fixture':'fresh local grounding'}}


class AutomaticLocalSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def fixture(self,*,missing=True,soft=False,point=None,leak=False):
        rgb=np.full((512,512,3),[30,40,50],'uint8');rgb[64:448,128:384]=[200,150,150];rgb[180:340,282:289]=[90,200,100]
        source=Image.fromarray(rgb).convert('RGBA')
        old,receipt=selection.prepare(source,'upper',vision=OriginalVision(soft),cache_root=self.root/'garment',
            local_backend=OriginalBackend(missing,soft,leak),subject=SUBJECT,vision_metadata=META)
        out=np.asarray(source).copy();out[np.asarray(old)>0,:3]=[15,15,15];output=Image.fromarray(out)
        loc=point or ([276/511,256/511] if soft else [.5,.5])
        qc={'passed':False,'blocking':True,'nextAction':'selection','protectedPartsPreserved':True,
            'binding':{'source':{'size':[512,512],'pixelSha256':selection._pixels(source,'RGBA')},
                'mask':{'size':[512,512],'pixelSha256':selection._pixels(old,'L')},
                'output':{'size':[512,512],'pixelSha256':selection._pixels(output,'RGBA')},
                'selectionReceiptSha256':tool._jsha(receipt),'subject':{**SUBJECT,'kind':'upper'}},
            'numeric':{'outsideChangedPixels':0,'alphaChangedPixels':0},
            'visualReview':{'category':'selection','blocking':True,'selectionComplete':False,'protectedPartsPreserved':True,
                'identityPreserved':True,'materialPreserved':True,'colourPlausible':True,
                'locations':[{'kind':'miss','point':loc,'reason':'machine-reported possible miss, not a true foreground point'}]}}
        return source,old,receipt,output,qc
    def run_correct(self,data,vision=None,backend=None,**kwargs):
        source,old,receipt,output,qc=data
        return tool.correct(source,old,receipt,kind='upper',subject=SUBJECT,qc=qc,actual_output=output,
            vision=vision or LocalVision(),cache_root=self.root/'local',garment_cache_root=self.root/'garment',
            vision_metadata=META,local_backend=backend or LocalBackend(),**kwargs)

    def test_true_miss_requires_grounding_and_fresh_review_and_changes_only_roi_mask(self):
        data=self.fixture();before=data[0].tobytes();vision=LocalVision();backend=LocalBackend()
        mask,r=self.run_correct(data,vision,backend)
        self.assertTrue(r['verified']);self.assertTrue(r['accepted']);self.assertTrue(r['colourQaRequired'])
        self.assertEqual(len(vision.calls),2);self.assertEqual(len(backend.calls),1)
        self.assertEqual(mask.getpixel((256,256)),255);self.assertEqual(data[1].getpixel((256,256)),0)
        x0,y0,x1,y1=r['localGrounding']['regions'][0]['bboxPixels'];outside=np.ones((512,512),bool);outside[y0:y1,x0:x1]=False
        self.assertTrue(np.array_equal(np.asarray(mask)[outside],np.asarray(data[1])[outside]))
        self.assertEqual(data[0].tobytes(),before)
        self.assertFalse(r['localGrounding']['auditOnly']);self.assertGreater(r['localGrounding']['maskChangedPixels'],0)
        self.assertTrue(r['localGrounding']['unverifiedForColourQA'])
        self.assertTrue(Path(r['localGrounding']['groundingRecordPath']).is_file())

    def test_confirmed_weak_leak_requires_dual_instances_and_fresh_review(self):
        data=self.fixture(missing=False,leak=True,point=[120/511,256/511]);calls=[]
        def vision(instruction,context,images):
            calls.append(context['phase'])
            if context['phase']=='local_source_review':return {'result':accepted_review()}
            self.assertIn('weakSelectionHypotheses',context)
            return {'result':{'regions':[{'regionId':0,'status':'true_leak','classification':'non_target',
                'reason':'Source-visible non-target outside the target cloth; selected weak pixel is dyed',
                'assessedEntireRegion':True,'nonTargetDyeObserved':True,'evidencePoint':[120/511,256/511],
                'foreground':[{'point':[200/511,256/511],'evidence':'actual opaque target cloth interior'}],
                'background':[{'point':[120/511,256/511],'kind':'background','evidence':'actual non-target exterior'}],
                'occluder':[]}]}}
        backend=LocalBackend();mask,receipt=self.run_correct(data,vision,backend)
        self.assertEqual(mask.getpixel((120,256)),0);self.assertEqual(data[1].getpixel((120,256)),75)
        self.assertEqual([r['role']for r in backend.calls],['target_cloth','non_target'])
        self.assertEqual(calls,['local_grounding','local_source_review'])
        self.assertEqual(receipt['localGrounding']['maskChangedPixels'],1)
        self.assertEqual(receipt['localGrounding']['regions'][0]['leakRemovalGuard']['opaqueClothRemovedPixels'],0)
        self.assertTrue(receipt['colourQaRequired']);self.assertTrue(receipt['accepted'])

    def test_no_edit_justified_still_gets_fresh_numeric_and_source_review(self):
        data=self.fixture(missing=False);vision=LocalVision('no_edit_justified');backend=LocalBackend()
        mask,r=self.run_correct(data,vision,backend)
        self.assertTrue(r['accepted']);self.assertEqual(mask.tobytes(),data[1].tobytes())
        self.assertEqual(len(vision.calls),2);self.assertFalse(backend.calls)
        self.assertTrue(r['quality']['accepted']);self.assertTrue(r['independentReview']['accepted'])
        self.assertTrue(r['localGrounding']['auditOnly']);self.assertEqual(r['localGrounding']['maskChangedPixels'],0)
        self.assertEqual(r['localGrounding']['regions'][0]['sourcePixelEvidence']['oldAlpha'],255)

    def test_uncertain_ownership_stops_without_segmentation_or_review(self):
        data=self.fixture();vision=LocalVision('uncertain');backend=LocalBackend()
        with self.assertRaises(tool.LocalSelectionRejected) as error:self.run_correct(data,vision,backend)
        self.assertFalse(error.exception.receipt['verified']);self.assertEqual(len(vision.calls),1);self.assertFalse(backend.calls)

    def test_qc_output_binding_mismatch_stops_before_grounding(self):
        data=list(self.fixture());data[3]=data[3].copy();data[3].putpixel((10,10),(1,2,3,255));vision=LocalVision()
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(tuple(data),vision)
        self.assertFalse(vision.calls)

    def test_qc_mask_or_receipt_mismatch_stops_before_grounding(self):
        for key in ('mask','selectionReceiptSha256'):
            data=list(self.fixture());data[4]=copy.deepcopy(data[4])
            if key=='mask':data[4]['binding']['mask']['pixelSha256']='wrong'
            else:data[4]['binding'][key]='wrong'
            vision=LocalVision()
            with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(tuple(data),vision)
            self.assertFalse(vision.calls)

    def test_source_hard_anatomy_cannot_be_released_even_by_grounding_claim(self):
        data=self.fixture(point=[285/511,256/511]);vision=LocalVision();backend=LocalBackend()
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision,backend)
        self.assertEqual(len(vision.calls),1);self.assertFalse(backend.calls)

    def test_model_ribbon_release_requires_two_source_local_instances(self):
        data=self.fixture(soft=True);vision=LocalVision(include_occluder=True);backend=LocalBackend()
        mask,r=self.run_correct(data,vision,backend)
        self.assertEqual([c['role'] for c in backend.calls],['target_cloth','occluder'])
        self.assertEqual(mask.getpixel((276,256)),255);self.assertEqual(mask.getpixel((285,256)),0)
        self.assertGreater(r['localGrounding']['sourceModels'][0]['releasedModelProtectionPixels'],0)

    def test_model_ribbon_is_not_released_without_local_occluder_evidence(self):
        data=self.fixture(soft=True);vision=LocalVision(include_occluder=False)
        with self.assertRaises(tool.LocalSelectionRejected) as error:self.run_correct(data,vision,LocalBackend())
        self.assertFalse(error.exception.receipt['accepted']);self.assertEqual(len(vision.calls),1)

    def test_overlap_with_occluder_instance_never_releases_soft_protection(self):
        data=self.fixture(soft=True);vision=LocalVision(include_occluder=True)
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision,LocalBackend(missing_occluder=True))
        self.assertEqual(len(vision.calls),1)

    def test_backend_source_mask_binding_and_binary_shape_are_required(self):
        data=self.fixture();vision=LocalVision()
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision,LocalBackend(bad_hash=True))
        self.assertEqual(len(vision.calls),1)

    def test_true_miss_cannot_be_claimed_only_at_already_opaque_selected_points(self):
        data=self.fixture();vision=LocalVision(fg=[220/511,220/511])
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision)
        self.assertEqual(len(vision.calls),1)

    def test_rejected_source_review_does_not_inherit_canonical_pass(self):
        data=self.fixture();checked={'accepted':False,'issues':['new source leak'],'misses':[],
            'leaks':[{'point':[.5,.5],'kind':'accessory','evidence':'independent source finding'}]}
        with self.assertRaises(tool.LocalSelectionRejected) as error:self.run_correct(data,LocalVision(review=checked))
        self.assertFalse(error.exception.receipt['accepted']);self.assertFalse(error.exception.receipt['verified'])

    def test_audit_only_also_cannot_inherit_old_pass_after_new_review_rejects(self):
        data=self.fixture(missing=False);checked={'accepted':False,'issues':['unresolved source ownership'],'misses':[], 'leaks':[]}
        with self.assertRaises(tool.LocalSelectionRejected) as error:self.run_correct(data,LocalVision('no_edit_justified',review=checked))
        self.assertTrue(error.exception.receipt['localGrounding']['auditOnly']);self.assertFalse(error.exception.receipt['accepted'])

    def test_unknown_grounding_is_not_repaid(self):
        data=self.fixture();vision=LocalVision(fail_phase='local_grounding')
        with self.assertRaises(tool.LocalSelectionRejected) as error:self.run_correct(data,vision)
        self.assertEqual(error.exception.code,'automatic_local_selection_unknown')
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision)
        self.assertEqual(len(vision.calls),1)

    def test_unknown_review_is_not_repaid_or_reset_by_backend_version(self):
        data=self.fixture();vision=LocalVision(fail_phase='local_source_review')
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision)
        fresh=LocalVision()
        with self.assertRaises(tool.LocalSelectionRejected) as error:self.run_correct(data,fresh,LocalBackend(bad_hash=True))
        self.assertEqual(error.exception.code,'automatic_local_selection_unknown');self.assertFalse(fresh.calls)

    def test_success_cache_checks_actual_mask_bytes_without_new_calls(self):
        data=self.fixture();vision=LocalVision();mask,r=self.run_correct(data,vision)
        cached,rr=self.run_correct(data,vision);self.assertTrue(rr['cacheReused']);self.assertEqual(len(vision.calls),2)
        self.assertEqual(mask.tobytes(),cached.tobytes());Image.new('L',mask.size).save(r['maskPath'])
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision)
        self.assertEqual(len(vision.calls),2)

    def test_changed_explicit_protection_is_not_silently_introduced(self):
        data=self.fixture();vision=LocalVision()
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(data,vision,explicit_protection=Image.new('L',(512,512)))
        self.assertFalse(vision.calls)

    def test_new_receipt_still_passes_original_canonical_numeric_recheck(self):
        data=self.fixture();mask,r=self.run_correct(data)
        _,_,_,_,proof=tool.revision._load_evidence(data[0],mask,r,self.root/'local','upper',SUBJECT)
        self.assertTrue(proof['candidateNumericRecheck']['accepted'])

    def test_warning_only_visual_contradiction_allows_study_but_not_inherited_pass(self):
        data=list(self.fixture(missing=False));data[4]=copy.deepcopy(data[4]);data[4]['visualReview']['blocking']=False
        self.assertTrue(tool.eligible(data[4]));vision=LocalVision('no_edit_justified')
        _,receipt=self.run_correct(tuple(data),vision)
        self.assertEqual(len(vision.calls),2);self.assertTrue(receipt['localGrounding']['auditOnly'])
        self.assertFalse(data[4]['passed']);self.assertTrue(data[4]['blocking'])
        self.assertFalse(data[4]['visualReview']['blocking'])

    def test_mixed_miss_leak_reports_are_untrusted_research_with_fresh_gates(self):
        data=list(self.fixture(missing=False));qc=data[4]
        qc['visualReview']['locations'].append({'kind':'leak','point':[.51,.5],
            'reason':'possible leak ownership uncertain; warning only'})
        original=copy.deepcopy(qc);vision=LocalVision('no_edit_justified')
        self.assertTrue(tool.eligible(qc));_,receipt=self.run_correct(tuple(data),vision)
        regions=vision.calls[0]['context']['regions']
        self.assertEqual([row['reportedKind'] for row in regions],['miss','leak'])
        self.assertEqual(regions[1]['reportReason'],original['visualReview']['locations'][1]['reason'])
        self.assertTrue(all(row['reportIsHypothesis'] for row in regions))
        self.assertEqual(qc,original);self.assertEqual(len(vision.calls),2)
        self.assertTrue(receipt['localGrounding']['auditOnly']);self.assertTrue(receipt['colourQaRequired'])

    def test_actual_protection_failure_authorizes_only_bound_leak_research_not_delivery(self):
        data=list(self.fixture(missing=False));qc=data[4]
        qc['protectedPartsPreserved']=False
        qc['visualReview'].update(selectionComplete=True,protectedPartsPreserved=False,
            locations=[{'kind':'leak','point':[.5,.5],'reason':'Actual non-target dye requires source verification'}])
        self.assertTrue(tool.eligible(qc));self.assertFalse(qc['passed']);self.assertTrue(qc['blocking'])
        vision=LocalVision('uncertain');backend=LocalBackend()
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(tuple(data),vision,backend)
        self.assertEqual(len(vision.calls),1);self.assertFalse(backend.calls)
        qc['visualReview']['locations'][0]['kind']='miss';self.assertFalse(tool.eligible(qc))

    def test_actual_or_unexcluded_leak_cannot_be_relabelled_as_no_edit_or_miss(self):
        source,_,_,_,qc=self.fixture();regions=tool._regions(source,qc)
        regions[0]['reportedKind']='leak'
        for status in ('true_miss','no_edit_justified'):
            for leak in (True,None):
                raw=LocalVision(status)('',{'phase':'local_grounding','regions':regions},[])['result']
                raw['regions'][0]['nonTargetDyeObserved']=leak
                with self.assertRaises(tool.LocalSelectionRejected):tool._grounded(raw,regions,source)

    def test_leak_research_still_rejects_protection_failure_unknown_kind_and_uncertain(self):
        data=list(self.fixture());data[4]['visualReview']['locations'][0]['kind']='leak'
        qc=data[4]
        for path in ('top','visual'):
            altered=copy.deepcopy(qc)
            (altered if path=='top' else altered['visualReview'])['protectedPartsPreserved']=False
            self.assertFalse(tool.eligible(altered))
        altered=copy.deepcopy(qc);altered['visualReview']['locations'][0]['kind']='ownership_guess'
        self.assertFalse(tool.eligible(altered))
        vision=LocalVision('uncertain');backend=LocalBackend()
        with self.assertRaises(tool.LocalSelectionRejected):self.run_correct(tuple(data),vision,backend)
        self.assertEqual(len(vision.calls),1);self.assertEqual(backend.calls,[])

    def test_actual_roi_is_native_256_and_exact_half_open_source_coordinates(self):
        data=self.fixture();_,receipt=self.run_correct(data)
        for row in receipt['localGrounding']['regions']:
            x0,y0,x1,y1=row['bboxPixels'];self.assertEqual(x1-x0,256);self.assertEqual(y1-y0,256)

    def test_one_hair_point_gets_bounded_same_object_coverage_not_a_second_person(self):
        source=Image.new('RGBA',(935,1500));human=np.zeros((1500,935),'uint8');old=np.zeros_like(human)
        human[160:780,140:410]=2;old[170:770,150:400]=150
        human[1000:1300,700:900]=2;old[1000:1300,700:900]=150
        qc={'visualReview':{'locations':[{'kind':'leak','point':[.28,.34],'reason':'Source-bound hair report'}]}}
        regions=tool._regions(source,qc,Image.fromarray(old),human)
        self.assertGreater(len(regions),1);self.assertLessEqual(len(regions),6)
        union=np.zeros_like(human,dtype=bool)
        for row in regions:
            x0,y0,x1,y1=row['bboxPixels'];union[y0:y1,x0:x1]=True
            self.assertFalse(x0<=800<x1 and y0<=1100<y1)
        self.assertLessEqual(union.mean(),.35)
        self.assertTrue(any(row.get('roiOrigin')=='automatic_same_source_hair_coverage'for row in regions))
    def test_hair_object_coverage_cannot_be_inferred_from_a_miss_or_other_semantic_class(self):
        source=Image.new('RGBA',(512,1024));old=Image.new('L',source.size,255)
        human=np.full((1024,512),2,'uint8')
        qc={'visualReview':{'locations':[{'kind':'miss','point':[.5,.5],'reason':'Possible missing cloth'}]}}
        self.assertEqual(len(tool._regions(source,qc,old,human)),1)

    def test_unknown_near_cloth_point_is_only_a_local_hypothesis_not_accepted(self):
        data=self.fixture();source=data[0].copy();source.putpixel((120,256),(160,135,145,255))
        c,h,_=OriginalBackend().labels(source);base=selection._local_evidence(source,'upper',c,h,None)
        proof=tool._source_fg_guard(base,data[1],[[120,256]],base['protected'])
        row=proof['points'][0]
        self.assertEqual(row['branch'],'source_supported_local_hypothesis')
        self.assertTrue(row['hypothesisOnly']);self.assertFalse(proof['certifiesSelection'])
        self.assertLessEqual(row['sourceFabricDistanceLab'],24);self.assertLessEqual(row['distanceToOldOpaqueClothPixels'],30)

    def test_unknown_far_or_wrong_hue_source_point_cannot_be_grounded_to_fg(self):
        for point,colour in (((30,256),(160,135,145,255)),((120,256),(10,200,100,255))):
            data=self.fixture();source=data[0].copy();source.putpixel(point,colour)
            c,h,_=OriginalBackend().labels(source);base=selection._local_evidence(source,'upper',c,h,None)
            with self.assertRaises(tool.LocalSelectionRejected):tool._source_fg_guard(base,data[1],[list(point)],base['protected'])

    def test_existing_independent_garment_highlight_is_not_clipped_by_fallback_colour_limit(self):
        data=self.fixture();source=data[0].copy();source.putpixel((160,256),(255,250,250,255))
        c,h,_=OriginalBackend().labels(source);base=selection._local_evidence(source,'upper',c,h,None)
        self.assertGreater(base['distance'][256,160],24)
        proof=tool._source_fg_guard(base,data[1],[[160,256]],base['protected'])
        self.assertEqual(proof['points'][0]['branch'],'existing_independent_support')


if __name__=='__main__':unittest.main()
