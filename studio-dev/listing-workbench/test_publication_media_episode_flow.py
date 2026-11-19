"""Formal action/evidence/host isolation; all state lives in a temporary workspace."""
import copy
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import publication_flow as flow
from test_publication_media_episode import fixture


class MediaEpisodeFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.workspace=Path(self.temp.name);self.root=self.workspace/'studio-dev/listing-workbench/data/account-workspaces/2/publication-flow'
        self.patches=[patch.object(flow,'ROOT',self.root),patch.object(flow,'PROJECT',self.workspace/'studio-dev'),patch.object(flow.threading,'Thread')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.addCleanup(flow.ACTIVE.clear);flow.ACTIVE.clear()
        self.job,self.record,self.source,self.now=fixture()
        for a in self.source['assets']:a['path']=str(self.workspace/'studio-dev/account2/media'/f"{a['sha256']}.png")
        self.packet={'input':self.source,'connection':{'browserBinding':'account2-ERP','page':'p2'}}
        self.folder=self.root/self.job['id'];flow.write_json(self.folder/'input.json',self.packet);flow.write_json(self.folder/'receipt.json',self.record)
        with flow.connect() as db,db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',('job',2,'P','US','needs_reconciliation',json.dumps(self.job)))
        evidence_folder=self.workspace/'research-episode';evidence_folder.mkdir()
        anchor={'sourceReceiptPath':str(self.folder/'receipt.json'),'observation':self.record['usPublish']['latestObservation']}
        scope=flow.media_episode.media_episode_scope(self.job,self.record,self.source,now=self.now)
        objects=[]
        for row in scope['failedMedia']:
            asset=next(a for a in self.source['assets'] if a['sha256']==row['assetSha256'])
            for url in [row['originalUrl'],row['originalUrl'].replace('oss-cn-shenzhen','oss-accelerate')]:
                objects.append({'sku':row['sku'],'code':row['code'],'slot':row['slot'],'url':url,'finalUrl':url,
                    'expectedSha256':asset['sha256'],'sha256':asset['sha256'],'localPath':asset['path'],
                    'status':200,'decoded':True,'sameOriginalBytes':True,'format':'PNG','width':1600,'height':1600})
        readcheck={'at':'2026-11-17T05:15:00Z','failureObservedAt':'2026-11-17T05:00:00Z','allAvailableAndExact':True,'objects':objects}
        self.references={}
        for key,value in [('failureAnchor',anchor),('mediaReadcheck',readcheck)]:
            path=evidence_folder/(key+'.json');flow.write_json(path,value)
            self.references[key]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        self.payload={'id':'job','confirmed':True,'retryMediaEpisode':True,'mediaEpisodeEvidence':self.references}

    def terminal(self):
        job=flow.owned(2,'job');job['status']='needs_reconciliation';flow.persist(job);flow.ACTIVE.discard('job');return job

    def test_formal_action_freezes_full_scope_old_packet_and_only_one_episode_then_plain_continue_is_readonly(self):
        old_receipt=(self.folder/'receipt.json').read_bytes()
        result=flow.resume(2,self.payload)
        frozen=json.loads((self.folder/'input.json').read_text())
        episode=frozen['input'].pop('publicationMediaEpisodes')[0]
        self.assertEqual(frozen,self.packet);self.assertEqual(episode['variantCount'],30);self.assertEqual(len(episode['assetManifest']),35)
        self.assertFalse(result['mediaEpisodeObserveOnly']);self.assertTrue(result['mediaEpisode']['authorized'])
        amendment=json.loads((self.folder/'amendments'/(episode['id']+'.json')).read_text())
        self.assertEqual(amendment['previousInput'],self.packet)
        self.assertEqual((self.folder/'receipt.json').read_bytes(),old_receipt)
        self.terminal()
        with self.assertRaisesRegex(ValueError,'唯一媒体episode'):flow.resume(2,self.payload)
        result=flow.resume(2,{'id':'job','confirmed':True})
        self.assertTrue(result['mediaEpisodeObserveOnly']);self.assertEqual((self.folder/'receipt.json').read_bytes(),old_receipt)
        self.assertEqual(len(list((self.folder/'amendments').glob('*.json'))),1)

    def test_mutually_exclusive_actions_wrong_account_unhashed_or_foreign_receipt_artifact_cannot_freeze(self):
        for extra in ({'observeOnly':True},{'retryMediaFailures':True},{'repairMainImage':True}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):flow.resume(2,{**self.payload,**extra})
        with self.assertRaises(ValueError):flow.resume(3,self.payload)
        for key,value in [('sha256','0'*64),('path',str(self.workspace/'outside.json'))]:
            bad=copy.deepcopy(self.payload);bad['mediaEpisodeEvidence']['failureAnchor'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):flow.resume(2,bad)
        path=Path(self.references['failureAnchor']['path']);value=json.loads(path.read_text());value['sourceReceiptPath']=str(self.root/'foreign/receipt.json');flow.write_json(path,value)
        bad=copy.deepcopy(self.payload);bad['mediaEpisodeEvidence']['failureAnchor']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'其他任务'):flow.resume(2,bad)
        self.assertNotIn('publicationMediaEpisodes',json.loads((self.folder/'input.json').read_text())['input'])

    def test_episode_host_runs_only_dedicated_us_phase_without_login_or_uk_and_returns_reconciliation(self):
        flow.resume(2,self.payload);job=flow.owned(2,'job');old_uk=copy.deepcopy(self.record['ukPublish'])
        with patch.object(flow.collection,'browser_lease',return_value=nullcontext()),patch.object(flow,'login') as login,\
                patch.object(flow,'run_browser',return_value=self.record) as run:
            flow.execute(job)
        login.assert_not_called();run.assert_called_once_with(job,self.packet['connection'],'us_media_episode')
        self.assertEqual(job['status'],'needs_reconciliation');self.assertEqual(self.record['ukPublish'],old_uk)


if __name__=='__main__':unittest.main()
