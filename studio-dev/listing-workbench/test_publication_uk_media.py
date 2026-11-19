"""Original UK media scope and host isolation; no live ERP/model/network."""
import copy
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import publication_uk_media as media
import publication_flow as flow


def fixture():
    now = media._time('2026-11-18T05:30:00Z')
    job = {'id':'job','accountId':2,'productId':'P','destinationId':'US','status':'needs_reconciliation'}
    assets = [{'sha256':f'{i:064x}','width':1600,'height':1600,'path':f'/original/{i}.png'} for i in range(105)]
    urls = {a['sha256']:f'{media.REGIONAL}/u/11/26/11/s_{i}.png' for i,a in enumerate(assets)}
    variants = [{'sku':f'P-{c}-{s}','color':str(c),'size':str(s),'imageIndices':list(range(c*7,c*7+7))} for c in range(15) for s in range(5)]
    source = {'accountId':2,'productId':'P','jobId':'job','sha256':'snapshot','marketplace':'US',
              'store':'US store','goods':{'parentSku':'P'},'goodsItems':variants,'assets':assets,'urls':urls,
              'ukTarget':{'id':'UK','storeName':'UK store'},'publicationIdentifierRepair':{'id':'old-keep'}}
    prepared = copy.deepcopy(source)
    prepared.update(marketplace='UK',store='UK store',destination={'destinationId':'UK','draftId':'101',
        'erpAccountId':'11','marketId':'91','countryCode':'GB','schemaHash':'GB-schema'})
    publication = {'publishId':'202','phase':'publication_failed','fingerprint':'original',
        'identity':{'publishId':'202'},'sourceLink':{'publishId':'202','draftId':'101'},'sourceEvidence':{'old':'accepted'}}
    request={'method':'POST','url':'https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish',
             'payload':{'ids':[202]},'sentAt':'2026-11-18T04:00:00Z','response':{'httpStatus':200,'body':{'code':0}}}
    publication['identifierRepair']={'saveVerified':True,'plannedSource':{'id':202,'preserve':'all business fields'},
                                     'retry':{'requestAccepted':True,'nativeRequests':[request]}}
    record={'accountId':2,'productId':'P','jobId':'job','snapshotSha256':'snapshot','usPublish':{'publishId':'1'},
        'ukPublish':publication,'ukCopy':{'phase':'copy_verified','draftId':'101'},
        'ukPrepare':{'phase':'uk_draft_verified','draftId':'101','preparedInput':prepared,'urls':urls,
                     'schemaObservation':{'hash':'GB-schema','product_type_name':'SWEATSHIRT','country_code':'GB',
                                          'locale':'en_GB','schema_content':{'type':'object'}}}}
    expected,_,_=media.context(job,record,source)
    children=[]
    for i,v in enumerate(variants):
        images=[urls[assets[n]['sha256']] for n in v['imageIndices']]
        children.append({'childId':str(203+i),'sku':v['sku'],'color':v['color'],'size':v['size'],
                         'status':'accepted','main':images[0],'images':images,'imagesSource':'child_gallery','messages':[]})
    failed=children[2];failed['status']='failed'
    messages=[{'sku':failed['sku'],'childId':failed['childId'],'code':'300060','severity':'ERROR',
               'message':'Cannot access '+failed['images'][i].replace('oss-cn-shenzhen','oss-accelerate')} for i in (0,1,2,4,5,6)]
    messages.append({'sku':failed['sku'],'childId':failed['childId'],'code':'18448','severity':'WARNING',
                     'message':'缺少关键属性：material。缺少这些属性不会阻止商品展示。'})
    failed['messages']=messages
    obs={k:v for k,v in expected.items() if k not in ('jobId','schemaHash')}
    obs.update(identityVerified=True,failed=True,verification='failed',status='failed',observedAt='2026-11-18T05:00:00Z',
        count=1,acceptedCount=74,childCount=75,failedChildIds=[failed['childId']],skus=[failed['sku']],
        children=children,messages=messages,messageCount=7,unscopedMessageCount=0,responseFingerprint='f'*64)
    publication.update(latestObservation=obs,failureObservation=copy.deepcopy(obs))
    return job,record,source,now


def evidence(folder,job,record,source,now):
    scope=media.scope(job,record,source,now=now);objects=[]
    for row in scope['failedMedia']:
        asset=next(a for a in source['assets'] if a['sha256']==row['assetSha256'])
        objects.append({**{k:row[k] for k in ('sku','childId','slot','code')},'url':row['reportedUrl'],
            'localPath':asset['path'],'sha256':asset['sha256'],'expectedSha256':asset['sha256'],
            'localSha256':asset['sha256'],'sameOriginalBytes':True,'officialVerifierPassed':True,
            'response':{'status':200,'finalUrl':row['reportedUrl'],'bodySha256':asset['sha256'],'bodyBytes':100},
            'decoded':{'passed':True,'fullPillowDecode':True,'format':'PNG','width':1600,'height':1600}})
    anchor={'accountId':2,'observations':[{'jobId':job['id'],'observation':record['ukPublish']['latestObservation']}]}
    read={'accountId':2,'jobId':job['id'],'publishId':'202','sku':scope['failedSkus'][0],
          'failureResponseFingerprint':'f'*64,'allSixPassed':True,'requestCount':6,
          'startedAt':'2026-11-18T05:10:00Z','objects':objects}
    refs={};folder.mkdir(parents=True,exist_ok=True)
    for name,value in [('failureAnchor',anchor),('mediaReadcheck',read)]:
        p=folder/(name+'.json');p.write_text(json.dumps(value),encoding='utf-8')
        refs[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    return refs


class UkMediaScopeTests(unittest.TestCase):
    def test_original_shared_picture_keeps105_positions_and91_files(self):
        j,r,s,now=fixture();prepared=r['ukPrepare']['preparedInput'];common=copy.deepcopy(prepared['assets'][3])
        for color in range(1,15):
            prepared['assets'][color*7+3]=copy.deepcopy(common)
            s['assets'][color*7+3]=copy.deepcopy(common)
            for child in r['ukPublish']['latestObservation']['children']:
                if child['color']==str(color):child['images'][3]=prepared['urls'][common['sha256']]
        result=media.scope(j,r,s,now=now)
        self.assertEqual(len(result['assetManifest']),105)
        self.assertEqual(len({a['sha256'] for a in result['assetManifest']}),91)

    def test_scope_preserves_all_assets_old_repairs_and_warning_and_cooldown_anchor(self):
        job,record,source,now=fixture();before=copy.deepcopy((record,source))
        result=media.scope(job,record,source,now=now)
        self.assertEqual(len(result['assetManifest']),105);self.assertEqual(len(result['failedMedia']),6)
        self.assertEqual(result['nonBlockingWarnings'][0]['severity'],'WARNING')
        self.assertEqual((record,source),before)
        anchor=copy.deepcopy(record['ukPublish']['latestObservation'])
        record['ukPublish']['latestObservation']['observedAt']='2026-11-18T05:29:00Z'
        self.assertEqual(media.scope(job,record,source,anchor=anchor,now=now)['cooldownNotBefore'],result['cooldownNotBefore'])

    def test_wrong_owner_media_scope_gallery_warning_or_unknown_old_retry_reject(self):
        changes=[lambda j,r,s:j.update(accountId=3),lambda j,r,s:r['ukPublish']['identifierRepair']['retry'].update(requestAccepted=False),
                 lambda j,r,s:r['ukPublish']['latestObservation'].update(count=2),
                 lambda j,r,s:r['ukPublish']['latestObservation']['messages'][-1].update(severity='ERROR'),
                 lambda j,r,s:r['ukPublish']['latestObservation']['messages'][0].update(message='Cannot access https://foreign.example/a.png'),
                 lambda j,r,s:r['ukPublish']['latestObservation']['children'][0]['images'].reverse(),
                 lambda j,r,s:r['ukPrepare']['preparedInput']['assets'][0].update(width=1200)]
        for i,change in enumerate(changes):
            with self.subTest(case=i):
                j,r,s,now=fixture();change(j,r,s)
                with self.assertRaises((ValueError,KeyError)):media.scope(j,r,s,now=now)
        j,r,s,now=fixture()
        with self.assertRaisesRegex(ValueError,'冷却'):media.scope(j,r,s,now=now-1000)

    def test_hashed_artifacts_validate_exact_six_bytes_and_cannot_escape_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp);j,r,s,now=fixture();refs=evidence(workspace/'research-UK',j,r,s,now)
            a=media.freeze(j,r,s,workspace,refs,now=now);s['publicationUkMediaRecovery']=a
            self.assertEqual(media.validate(j,r,s),a)
            with self.assertRaisesRegex(ValueError,'唯一'):media.freeze(j,r,s,workspace,refs,now=now)
            a['failedMedia'][0]['slot']=3
            with self.assertRaisesRegex(ValueError,'范围'):media.validate(j,r,s)
            j,r,s,now=fixture();bad=copy.deepcopy(refs);bad['mediaReadcheck']['sha256']='0'*64
            with self.assertRaises(ValueError):media.freeze(j,r,s,workspace,bad,now=now)
            bad=copy.deepcopy(refs);bad['failureAnchor']['path']=str(workspace/'outside.json')
            with self.assertRaises(ValueError):media.freeze(j,r,s,workspace,bad,now=now)


class UkMediaFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.ws=Path(self.temp.name)
        self.root=self.ws/'studio-dev/account2/publication-flow';self.job,self.record,self.source,self.now=fixture()
        self.folder=self.root/'job';self.packet={'input':self.source,'connection':{'browserBinding':'ERP','page':'p2'}}
        for p in (patch.object(flow,'ROOT',self.root),patch.object(flow,'PROJECT',self.ws/'studio-dev'),patch.object(flow.threading,'Thread')):
            p.start();self.addCleanup(p.stop)
        flow.ACTIVE.clear();self.addCleanup(flow.ACTIVE.clear)
        flow.write_json(self.folder/'input.json',self.packet);flow.write_json(self.folder/'receipt.json',self.record)
        with flow.connect() as db,db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',('job',2,'P','US','needs_reconciliation',json.dumps(self.job)))
        self.refs=evidence(self.ws/'research-UK',self.job,self.record,self.source,self.now)
        self.payload={'id':'job','confirmed':True,'retryUkMediaFailures':True,'ukMediaEvidence':self.refs}

    def terminal(self):
        j=flow.owned(2,'job');j['status']='needs_reconciliation';flow.persist(j);flow.ACTIVE.discard('job');return j

    def test_first_freeze_keeps_old_packet_receipt_and_old_identifier_auth_then_plain_is_readonly(self):
        before=(self.folder/'receipt.json').read_bytes()
        result=flow.resume(2,self.payload);frozen=json.loads((self.folder/'input.json').read_text())
        a=frozen['input'].pop('publicationUkMediaRecovery');self.assertEqual(frozen,self.packet)
        self.assertEqual(a['variantCount'],75);self.assertTrue(result['ukMediaRecovery']['authorized'])
        self.assertFalse(result['ukMediaObserveOnly']);self.assertEqual((self.folder/'receipt.json').read_bytes(),before)
        self.terminal()
        with self.assertRaisesRegex(ValueError,'唯一'):flow.resume(2,self.payload)
        result=flow.resume(2,{'id':'job','confirmed':True});self.assertTrue(result['ukMediaObserveOnly'])
        self.assertEqual((self.folder/'receipt.json').read_bytes(),before)
        self.assertEqual(len(list((self.folder/'amendments').glob('*.json'))),1)

    def test_wrong_account_and_combined_actions_never_freeze(self):
        with self.assertRaises(ValueError):flow.resume(3,self.payload)
        for flag in ('observeOnly','repairIdentifiers','retryMediaFailures','repairRequiredAttributes'):
            with self.subTest(flag=flag),self.assertRaises(ValueError):flow.resume(2,{**self.payload,flag:True})
        self.assertNotIn('publicationUkMediaRecovery',json.loads((self.folder/'input.json').read_text())['input'])

    def test_host_uk_only_first_login_then_plain_observation_without_login(self):
        flow.resume(2,self.payload);job=flow.owned(2,'job')
        with patch.object(flow.collection,'browser_lease',return_value=nullcontext()),patch.object(flow,'login') as login,patch.object(flow,'run_browser',return_value=self.record) as run:
            flow.execute(job)
            login.assert_called_once_with(job,self.packet['connection'],'UK')
            run.assert_called_once_with(job,self.packet['connection'],'uk_media_recovery')
        self.assertEqual(job['status'],'needs_reconciliation')
        self.terminal();flow.resume(2,{'id':'job','confirmed':True});job=flow.owned(2,'job')
        with patch.object(flow.collection,'browser_lease',return_value=nullcontext()),patch.object(flow,'login') as login,patch.object(flow,'run_browser',return_value=self.record):
            flow.execute(job);login.assert_not_called()

if __name__=='__main__':unittest.main()
