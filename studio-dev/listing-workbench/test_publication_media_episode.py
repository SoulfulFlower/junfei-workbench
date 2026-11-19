"""Independent media episode boundary tests; no ERP/browser/filesystem business mutation."""
import copy
from datetime import datetime
import unittest
import publication_media_episode as media


def fixture():
    job={'id':'job','accountId':2,'productId':'P','destinationId':'US','status':'needs_reconciliation'}
    assets=[{'sha256':f'{i:064x}','width':1600,'height':1600} for i in range(35)]
    urls={a['sha256']:f'{media.REGIONAL}/u/11/26/11/s_{i}.png' for i,a in enumerate(assets)}
    variants=[{'sku':f'P-{c}-{s}','color':c,'size':s,'imageIndices':list(range(i*7,i*7+7))}
              for i,c in enumerate(['white','black','brown','gray','red']) for s in ['S','M','L','XL','XXL','3XL']]
    source={'jobId':'job','accountId':2,'productId':'P','sha256':'a'*64,'store':'US store','goods':{'parentSku':'P'},
            'destination':{'destinationId':'US','draftId':'101','erpAccountId':'11','marketId':'91','countryCode':'US'},
            'assets':assets,'urls':urls,'goodsItems':variants}
    children=[{'childId':str(203+i),'sku':v['sku'],'color':v['color'],'size':v['size'],'status':'accepted',
               'main':urls[assets[v['imageIndices'][0]]['sha256']],
               'images':[urls[assets[n]['sha256']] for n in v['imageIndices']],'imagesSource':'child_gallery','messages':[]}
              for i,v in enumerate(variants)]
    black=next(c for c in children if c['sku']=='P-black-M');gray=next(c for c in children if c['sku']=='P-gray-XXL')
    messages=[{'childId':black['childId'],'sku':black['sku'],'code':'20000','message':'Download timeout '+black['images'][4].replace('oss-cn-shenzhen','oss-accelerate')},
              {'childId':gray['childId'],'sku':gray['sku'],'code':'18320','message':'Main image missing'}]
    for child,message in zip([black,gray],messages): child.update(status='failed',messages=[message])
    observation={'publishId':'202','accountId':2,'productId':'P','snapshotSha256':'a'*64,'destinationId':'US','draftId':'101',
                 'erpAccountId':'11','marketId':'91','countryCode':'US','store':'US store','parentSku':'P','status':'failed',
                 'observedAt':'2026-11-17T05:00:00Z','verification':'failed','failed':True,'identityVerified':True,
                 'responseFingerprint':'f'*64,'count':2,'childCount':30,'acceptedCount':28,'messageCount':2,'unscopedMessageCount':0,
                 'failedChildIds':[black['childId'],gray['childId']],'skus':[black['sku'],gray['sku']],'messages':messages,'children':children}
    request={'method':'POST','url':'https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish','payload':{'ids':[202]},
             'sentAt':'2026-11-17T00:00:00Z','response':{'httpStatus':200,'body':{'code':0}}}
    main_amendment={'failedChildId':gray['childId'],'failedSku':gray['sku'],'mainImageUrl':gray['main'],'failureResponseFingerprint':'b'*64}
    source['publicationMainImageRepair']=main_amendment
    us={'publishId':'202','phase':'publication_failed','identity':{'publishId':'202'},'sourceLink':{'publishId':'202','draftId':'101'},
        'sourceEvidence':{'id':202},'latestObservation':observation,'failureObservation':copy.deepcopy(observation),
        'mediaRecovery':{'intent':{'publishId':'202'},'nativeRequests':[copy.deepcopy(request)]},
        'mainImageRepair':{'saveVerified':True,'persistedSchemaValidation':{'passed':True,'checkedCount':31},
                           'amendment':main_amendment,'retry':{'intent':{'publishId':'202'},'requestAccepted':True,'nativeRequests':[copy.deepcopy(request)]}}}
    record={'jobId':'job','accountId':2,'productId':'P','snapshotSha256':'a'*64,'usPublish':us,'ukPublish':{'publishId':'303','phase':'publication_failed'}}
    now=datetime.fromisoformat('2026-11-17T05:30:00+00:00').timestamp()
    return job,record,source,now


class MediaEpisodeTests(unittest.TestCase):
    def test_build_preserves_old_failed_uk_and_us_histories_and_freezes_original_full_family(self):
        job,record,source,now=fixture(); original=copy.deepcopy((record,source))
        amendment=media.build_media_episode(job,record,source,now=now)
        self.assertEqual((record,source),original)
        self.assertEqual(amendment['nativeScope'],'original_parent_family')
        self.assertEqual(len(amendment['assetManifest']),35)
        self.assertEqual({m['code'] for m in amendment['failedMedia']},{'20000','18320'})
        source['publicationMediaEpisodes']=[amendment]
        self.assertEqual(media.validate_media_episode(job,record,source,amendment),amendment)

    def test_one_episode_ever_and_same_old_failure_fingerprint_cannot_get_another_authorization(self):
        for existing in ('source','receipt','old_failure'):
            job,record,source,now=fixture()
            if existing=='source':source['publicationMediaEpisodes']=[{'id':'old'}]
            elif existing=='receipt':record['usPublish']['mediaEpisodes']=[{'amendmentId':'old'}]
            else:source['publicationRecovery']={'failureResponseFingerprint':'f'*64}
            with self.subTest(existing=existing),self.assertRaises(ValueError):media.build_media_episode(job,record,source,now=now)

    def test_identical_fresh_read_uses_original_anchor_instead_of_resetting_twenty_minutes(self):
        job,record,source,now=fixture(); anchor=copy.deepcopy(record['usPublish']['latestObservation'])
        for field in ('latestObservation','failureObservation'):record['usPublish'][field]['observedAt']='2026-11-17T05:29:59Z'
        amendment=media.build_media_episode(job,record,source,failure_anchor=anchor,now=now)
        self.assertEqual(amendment['failureObservedAt'],'2026-11-17T05:00:00Z')
        self.assertEqual(amendment['cooldownNotBefore'],now-600)
        anchor['messages'][0]['code']='other'
        with self.assertRaises(ValueError):media.build_media_episode(job,record,source,failure_anchor=anchor,now=now)

    def test_cooldown_non_media_codes_missing_main_wrong_identity_and_seven_image_drift_are_blocked(self):
        def bad_image(r,s):r['usPublish']['latestObservation']['children'][0]['images'].reverse()
        def bad_code(r,s):r['usPublish']['latestObservation']['messages'][0]['code']='90220'
        def bad_main(r,s):r['usPublish']['mainImageRepair']['saveVerified']=False
        def bad_request(r,s):r['usPublish']['mediaRecovery']['nativeRequests'][0]['url']='https://elsewhere.example/'
        def bad_identity(r,s):r['accountId']=3
        for mutate in (bad_image,bad_code,bad_main,bad_request,bad_identity):
            job,record,source,now=fixture();mutate(record,source)
            with self.subTest(mutate=mutate.__name__),self.assertRaises(ValueError):media.build_media_episode(job,record,source,now=now)
        job,record,source,now=fixture()
        with self.assertRaisesRegex(ValueError,'冷却20分钟'):media.build_media_episode(job,record,source,now=now-1000)

    def test_continuation_does_not_need_failed_state_again_but_cannot_replace_frozen_manifest_or_journal(self):
        job,record,source,now=fixture();amendment=media.build_media_episode(job,record,source,now=now)
        source['publicationMediaEpisodes']=[amendment];record['usPublish']['phase']='waiting'
        record['usPublish']['mediaEpisodes']=[{'amendmentId':amendment['id'],'intent':{'original':'keep'}}]
        self.assertEqual(media.validate_media_episode(job,record,source,amendment),amendment)
        record['usPublish']['mediaEpisodes'][0]['amendmentId']='another'
        with self.assertRaises(ValueError):media.validate_media_episode(job,record,source,amendment)


if __name__=='__main__': unittest.main()
