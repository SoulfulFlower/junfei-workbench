import hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PIL import Image
import foreground_matting as fg

class ForegroundAdapter(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.scope=patch.object(fg.app_paths,'DATA',self.root);self.scope.start();self.addCleanup(self.scope.stop)
        self.config={'python':'python','worker':'pinned-worker.py','workerSha256':'worker-sha','weightSha256':'weight-sha','device':'cpu','size':1024,'threads':4}
        self.cfg=patch.object(fg,'settings',return_value=self.config);self.cfg.start();self.addCleanup(self.cfg.stop)
        rgb=np.full((30,20,3),[125,145,185],dtype='uint8');rgb[5:20,2:8]=[245,235,215];self.source=Image.fromarray(rgb)
    def worker(self,command,**kwargs):
        source=Image.open(command[command.index('--input')+1]);rgb=np.asarray(source.convert('RGB'))
        output=Path(command[command.index('--output-dir')+1]);output.mkdir()
        alpha=np.zeros(rgb.shape[:2],dtype='float32');alpha[5:25,3:17]=1;alpha[4,3:17]=.4;np.save(output/'alpha.npy',alpha,allow_pickle=False)
        receipt={'sourceRgbSha256':hashlib.sha256(rgb.tobytes()).hexdigest(),'sourceSize':list(source.size),'workerSha256':'worker-sha','weightSha256':'weight-sha','sourceRgbPreserved':True,'files':{'alpha.npy':{'sha256':fg.sha(output/'alpha.npy')}}}
        (output/'receipt.json').write_text(json.dumps(receipt),'utf8');return SimpleNamespace(returncode=0)
    def test_cached_alpha_keeps_original_rgb_and_soft_coverage_without_another_worker(self):
        with patch.object(fg.subprocess,'run',side_effect=self.worker)as worker:
            rgb,alpha,receipt=fg.matte(self.source);again=fg.matte(self.source)
        self.assertTrue(np.array_equal(np.rint(rgb*255).astype('uint8'),np.asarray(self.source)));self.assertAlmostEqual(alpha[4,7],.4,places=6)
        self.assertEqual(worker.call_count,1);self.assertFalse(receipt['humanReviewed']);self.assertTrue(receipt['semanticReviewStillRequired'])
    def test_changed_alpha_is_rejected_without_recomputing(self):
        with patch.object(fg.subprocess,'run',side_effect=self.worker):fg.matte(self.source)
        path=next(self.root.rglob('alpha.npy'));np.save(path,np.ones((30,20),dtype='float32'))
        with patch.object(fg.subprocess,'run')as worker,self.assertRaisesRegex(ValueError,'哈希'):fg.matte(self.source)
        worker.assert_not_called()
    def test_missing_model_does_not_fall_back_to_semantic_cutout(self):
        import image_fidelity
        with patch.object(fg,'settings',side_effect=ValueError('not configured')),patch.object(image_fidelity,'legacy_source_layer')as old:
            with self.assertRaises(ValueError):image_fidelity.source_layer(self.source)
        old.assert_not_called()
