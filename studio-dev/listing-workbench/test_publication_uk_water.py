"""Explicit, evidence-backed amendment of an existing editable UK draft."""
import copy
import json
import unittest
from unittest.mock import patch
import publication_flow as flow
import test_publication_recovery as recovery_tests


class UkWaterAmendmentTests(unittest.TestCase):
    setUp = recovery_tests.PublicationRecoveryTests.setUp
    configure = recovery_tests.PublicationRecoveryTests.configure
    start = recovery_tests.PublicationRecoveryTests.start
    failed_job = recovery_tests.PublicationRecoveryTests.failed_job

    def editable_uk(self):
        job, packet, record = self.failed_job();folder=flow.ROOT/job['id']
        packet['input']['ukPreparation']={'shippingTemplate':{'name':'Observed UK template'}}
        record['usPublish'].update(phase='publishing_verified',status='publishing',
            latestObservation={'publishId':'789','status':'publishing','verification':'accepted','failed':False})
        record['ukCopy']={'draftId':'456','phase':'copy_verified'}
        record['ukPrepare']={'schemaValidationBeforeSave':{'passed':False,'errors':['missing explicit fact']}}
        flow.write_json(folder/'input.json',packet);flow.write_json(folder/'receipt.json',record)
        return job,packet,record

    def payload(self,job):
        return {'id':job['id'],'confirmed':True,'ukWaterResistanceLevel':'not_water_resistant',
                'waterResistanceEvidence':'Explicit user selection for this original UK draft; isolated fixture'}

    def test_explicit_level_merges_shipping_and_archives_evidence_without_changing_original_facts(self):
        job,packet,_=self.editable_uk();folder=flow.ROOT/job['id'];receipt_before=(folder/'receipt.json').read_bytes()
        with patch.object(flow.threading,'Thread'):
            result=flow.resume(2,self.payload(job))
        self.assertEqual(result['status'],'queued')
        amended=json.loads((folder/'input.json').read_text())
        self.assertEqual(amended['input']['ukPreparation'].pop('waterResistanceLevel'),'not_water_resistant')
        self.assertEqual(amended,packet);self.assertEqual((folder/'receipt.json').read_bytes(),receipt_before)
        archives=list((folder/'amendments').glob('*.json'));self.assertEqual(len(archives),1)
        archive=json.loads(archives[0].read_text());self.assertEqual(archive['previousInput'],packet)
        self.assertEqual(archive['evidence'],self.payload(job)['waterResistanceEvidence'])
        self.assertEqual(archive['kind'],'uk_water_resistance_level')
        self.assertNotIn('waterResistanceLevel',packet['input'].get('publicationFacts',{}))

    def test_invalid_level_missing_evidence_and_other_actions_never_start_or_change_input(self):
        job,_,_=self.editable_uk();folder=flow.ROOT/job['id'];before=(folder/'input.json').read_bytes()
        for changes in ({'ukWaterResistanceLevel':'water_resistant'},{'ukWaterResistanceLevel':True},
                        {'waterResistanceEvidence':''},{'waterResistanceEvidence':' '},
                        {'observeOnly':True},{'repairMainImage':True},{'retryMediaFailures':True}):
            with patch.object(flow.threading,'Thread') as thread:
                with self.assertRaises(ValueError):flow.resume(2,{**self.payload(job),**changes})
                thread.assert_not_called()
            self.assertEqual((folder/'input.json').read_bytes(),before)
        with self.assertRaises(ValueError):flow.resume(3,self.payload(job))

    def test_unverified_us_or_noneditable_uk_blocks_the_amendment(self):
        job,_,record=self.editable_uk();folder=flow.ROOT/job['id'];before=(folder/'input.json').read_bytes()
        for change in (lambda r:r['usPublish']['latestObservation'].update(verification='pending'),
                       lambda r:r['usPublish']['latestObservation'].update(failed=True),
                       lambda r:r['usPublish']['latestObservation'].update(publishId='other'),
                       lambda r:r['ukCopy'].update(phase='copy_unknown'),
                       lambda r:r['ukPrepare'].update(preparedInput={'frozen':True}),
                       lambda r:r['ukPrepare'].update(saveIntendedAt='before'),
                       lambda r:r['ukPublish'].update(intent={})):
            invalid=copy.deepcopy(record);change(invalid);flow.write_json(folder/'receipt.json',invalid)
            with patch.object(flow.threading,'Thread') as thread:
                with self.assertRaises(ValueError):flow.resume(2,self.payload(job))
                thread.assert_not_called()
            self.assertEqual((folder/'input.json').read_bytes(),before)

    def test_later_existing_shipping_amendment_preserves_explicit_water_level(self):
        job,_,_=self.editable_uk();folder=flow.ROOT/job['id']
        with patch.object(flow.threading,'Thread'):flow.resume(2,self.payload(job))
        job=flow.owned(2,job['id']);job['status']='needs_reconciliation';flow.persist(job);flow.ACTIVE.discard(job['id'])
        with patch.object(flow.threading,'Thread'):
            flow.resume(2,{'id':job['id'],'confirmed':True,'ukShippingTemplate':'New actual UK',
                           'shippingEvidence':'Observed changed UK template; isolated fixture'})
        preparation=json.loads((folder/'input.json').read_text())['input']['ukPreparation']
        self.assertEqual(preparation,{'shippingTemplate':{'name':'New actual UK'},'waterResistanceLevel':'not_water_resistant'})


if __name__=='__main__':unittest.main()
