import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
import local_hair_matte as m

class SourceGuidedHairMatting(unittest.TestCase):
    def fixture(self):
        rgb=np.full((48,48,3),[40,85,45],'uint8');rgb[:,16:25]=[90,50,25]
        old=Image.new('L',(48,48),255)
        cm=np.ones((48,48),'uint8')*255;cm[:,14:27]=0
        nm=np.zeros((48,48),'uint8');nm[:,14:27]=255
        human=np.zeros((48,48),'uint8');human[:,14:27]=2
        return Image.fromarray(rgb),old,Image.fromarray(cm),Image.fromarray(nm),human,[[36,24]],[[20,24]]
    def test_laplacian_matches_independent_installed_reference_without_jit(self):
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp);rng=np.random.default_rng(23);rgb=rng.random((5,6,3));known=np.zeros((5,6),bool)
            known[:2,:2]=True;np.savez(p/'input.npz',rgb=rgb,known=known)
            code="import sys,numpy as np;from pymatting.laplacian.cf_laplacian import cf_laplacian;d=np.load(sys.argv[1]);np.save(sys.argv[2],cf_laplacian(d['rgb'],is_known=d['known']).toarray())"
            env={**os.environ,'NUMBA_DISABLE_JIT':'1'}
            subprocess.run([sys.executable,'-c',code,str(p/'input.npz'),str(p/'oracle.npy')],env=env,check=True,timeout=30,capture_output=True)
            actual=m.colour_line_laplacian(rgb,known).toarray();oracle=np.load(p/'oracle.npy')
            self.assertLess(np.max(np.abs(actual-oracle)),1e-10)
            self.assertLess(np.max(np.abs(actual-actual.T)),1e-10)
            self.assertLess(np.max(np.abs(actual@np.ones(30))),1e-10)
    def test_confirmed_hair_alpha_is_reduced_without_touching_native_cloth_or_source(self):
        args=self.fixture();before=args[0].tobytes();alpha,r=m.refine(*args,evidence_point=[20,24])
        self.assertEqual(alpha.getpixel((20,24)),0);self.assertEqual(alpha.getpixel((36,24)),255)
        self.assertEqual(args[0].tobytes(),before);self.assertEqual(r['nativeTargetClothChangedPixels'],0)
        self.assertEqual(r['sourceClothFavouredPixelsChanged'],0)
        self.assertFalse(r['accepted']);self.assertFalse(r['verified']);self.assertTrue(r['onlyGroundedConnectedDefect'])
        self.assertLess(r['relativeLinearResidual'],1e-7)
        self.assertTrue(np.array_equal(np.asarray(alpha)[0],np.asarray(args[1])[0]))
    def test_independent_semantic_hair_is_required(self):
        args=list(self.fixture());args[4][:]=4
        with self.assertRaises(ValueError):m.refine(*args,evidence_point=[20,24])
    def test_source_instance_disagreement_cannot_delete_a_cloth_point(self):
        args=list(self.fixture());args[2].putpixel((20,24),255)
        with self.assertRaises(ValueError):m.refine(*args,evidence_point=[20,24])
    def test_source_colour_ambiguity_cannot_become_automatic_hair_truth(self):
        args=list(self.fixture());args[0]=Image.new('RGB',(48,48),(50,80,50))
        with self.assertRaises(ValueError):m.refine(*args,evidence_point=[20,24])
    def test_grounded_target_point_must_be_original_opaque_cloth(self):
        args=list(self.fixture());args[1].putpixel((36,24),100)
        with self.assertRaises(ValueError):m.refine(*args,evidence_point=[20,24])

    def test_paired_matting_solves_a_jpeg_speck_without_increasing_unchanged_tolerance(self):
        source,old,cm,nm,human,fg,bg=self.fixture();target=np.asarray(source).copy()
        target[np.asarray(cm)>0]=[140,142,141];target[24,19]=np.asarray(source)[24,19]+5
        reference=Image.fromarray(target);unchanged=np.max(abs(np.asarray(source).astype(int)-target),axis=2)<=3
        self.assertFalse(unchanged[24,19]);before=(source.tobytes(),reference.tobytes(),old.tobytes())
        out,r=m.refine_paired(source,reference,old,cm,nm,human,unchanged,evidence_point=[20,24])
        self.assertLess(out.getpixel((19,24)),13);self.assertEqual(out.getpixel((36,24)),255)
        self.assertEqual(before,(source.tobytes(),reference.tobytes(),old.tobytes()))
        self.assertFalse(r['accepted']);self.assertLess(r['relativeLinearResidual'],1e-7)
    def test_paired_matting_preserves_physical_fractional_cloth_at_hair_edge(self):
        source,old,cm,nm,human,fg,bg=self.fixture();s=np.asarray(source).copy();t=s.copy()
        cloth=np.array([40,85,45]);other=np.array([90,50,25]);target=np.array([140,142,141])
        t[np.asarray(cm)>0]=target
        for x,alpha in [(14,.8),(15,.6),(16,.4),(17,.2)]:
            s[:,x]=np.rint(cloth*alpha+other*(1-alpha));t[:,x]=np.rint(target*alpha+other*(1-alpha))
        unchanged=np.max(abs(s.astype(int)-t),axis=2)<=3
        out,r=m.refine_paired(Image.fromarray(s),Image.fromarray(t),old,cm,nm,human,unchanged,evidence_point=[20,24])
        self.assertLess(abs(out.getpixel((16,24))-102),20)
        self.assertEqual(out.getpixel((20,24)),0);self.assertEqual(out.getpixel((36,24)),255)
    def test_paired_matting_cannot_use_a_changed_or_native_cloth_witness(self):
        source,old,cm,nm,human,*_=self.fixture();reference=source.copy();stable=np.ones((48,48),bool)
        stable[24,20]=False
        with self.assertRaises(ValueError):m.refine_paired(source,reference,old,cm,nm,human,stable,evidence_point=[20,24])
        stable[:]=True;cm.putpixel((20,24),255)
        with self.assertRaises(ValueError):m.refine_paired(source,reference,old,cm,nm,human,stable,evidence_point=[20,24])

if __name__=='__main__':unittest.main()
