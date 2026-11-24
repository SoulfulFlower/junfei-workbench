import json,unittest
import image_engine
class StructuredEvidence(unittest.TestCase):
    def plan(self):
        return {'identity':'same trousers','style':{},'shots':[{'layout':'main','sourceIndex':0,'evidence':{'verified':[],'visible':['original fringe gaps'],'inferences':[]},'question':'shape','scene':'white','camera':'front','copy':[]}]}
    def test_preserves_typed_observations_without_replanning(self):
        p=self.plan();result=image_engine.normalize_shots(p,1,1,True)
        self.assertEqual(json.loads(result['shots'][0]['evidence']),result['shots'][0]['evidenceDetails'])
        self.assertEqual(result['shots'][0]['evidenceDetails']['visible'],['original fringe gaps'])
    def test_empty_or_nontext_evidence_is_rejected(self):
        for evidence in ({},{'visible':[]},{'visible':[{'fabric':'invented'}]}):
            with self.subTest(evidence=evidence):
                p=self.plan();p['shots'][0]['evidence']=evidence
                with self.assertRaises(ValueError):image_engine.normalize_shots(p,1,1,True)
