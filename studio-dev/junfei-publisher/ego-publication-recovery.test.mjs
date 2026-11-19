import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,verifyPublication} from './ego-publish-native.mjs';
import {recoverNativeMediaPublication,installNativeMediaRecoveryGuard} from './ego-publication-recovery.mjs';

const endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish';
const regional='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com';
function fixture(){
 const assets=Array.from({length:35},(_,n)=>({sha256:createHash('sha256').update('isolated-'+n).digest('hex'),width:1600,height:1600}));
 const urls=Object.fromEntries(assets.map((a,n)=>[a.sha256,regional+'/u/19335/26/11/s_'+String(n).padStart(32,'0')+'.png']));
 const sizes={S:'s',M:'m',L:'l',XL:'x_l',XXL:'xx_l','3XL':'3x_l'},goodsItems=['White','Black','Brown','Gray','Red'].flatMap((color,c)=>Object.keys(sizes).map(size=>({sku:'Original-'+color+'-'+size,color,size,price:29,quantity:88,imageIndices:Array.from({length:7},(_,n)=>c*7+n)})));
 const input={accountId:2,productId:'isolated-shirt',jobId:'original-job',sha256:'immutable-snapshot',marketplace:'US',mode:'draft',store:'Original US Store',masterColor:'White',assets,urls,goodsItems,
  destination:{destinationId:'us-target',draftId:'101',marketId:'91',marketplaceId:'USMARKET',erpAccountId:'11',countryCode:'US',sizeValues:sizes},
  goods:{parentSku:'Original',title:'Original verified shirt',brand:'Actual Brand',manufacturer:'Actual Maker',description:'Original description',bullets:['Original bullet'],terms:'original terms'}};
 const cover=urls[assets[0].sha256],accepted={code:0,data:{id:202,uid:11,market_id:91,country_code:'US',market:{alias:input.store},sku:'Original',title:input.goods.title,brand:input.goods.brand,manufacturer:input.goods.manufacturer,status:'publishing',errors:[],
  main_image:cover,extra:{images:[cover],product_description:input.goods.description,bullet_point:input.goods.bullets,keywords:input.goods.terms},
  items:goodsItems.map((v,n)=>({id:203+n,pid:202,uid:11,sku:v.sku,status:'accepted',asin:null,price:v.price,quantity:v.quantity,main_image:urls[assets[v.imageIndices[0]].sha256],
   variation:{'color.0.value':v.color,'apparel_size.0.size':sizes[v.size]},extra:{images:v.imageIndices.map(i=>urls[assets[i].sha256]),message:null,attributes:{color:[{value:v.color}],apparel_size:[{size:sizes[v.size]}]}}}))}};
 const failed=structuredClone(accepted);failed.data.status='failed';
 for(const row of failed.data.items){
  if(!['Original-Brown-M','Original-Brown-XXL','Original-Gray-XXL'].includes(row.sku))continue;
  row.status='failed';row.extra.message=row.sku.includes('Brown')?row.extra.images.map(url=>({code:'300060',message:'Cannot access '+url.replace('oss-cn-shenzhen','oss-accelerate'),severity:'ERROR',sku:row.sku})):
   [{code:'18320',message:'Main image missing or incorrect',severity:'ERROR'}];
  failed.data.errors.push(...row.extra.message.map(message=>({...message,sku:row.sku})));
 }
 const record={publishId:'202',fingerprint:publicationFingerprint(assertPublicationInput(input)),identity:verifyPublication(accepted,input,'202'),sourceEvidence:structuredClone(accepted.data),sourceLink:{publishId:'202',draftId:'101'},status:'failed',phase:'publication_failed'};
 const f={input,accepted,failed,record};rebind(f);return f;
}
function rebind(f){
 f.record.failureObservation=publicationFailureObservation(f.failed,f.input,'202');f.record.latestObservation=f.record.failureObservation;
 f.amendment={id:'original-amendment',scope:'retry_original_failed_media',marketplace:'US',publishId:'202',snapshotSha256:f.input.sha256,
  failureResponseFingerprint:f.record.failureObservation.responseFingerprint,failedChildIds:[...f.record.failureObservation.failedChildIds],authorizedAt:1794830400.25,
  accountId:f.input.accountId,productId:f.input.productId,jobId:f.input.jobId,destinationId:f.input.destination.destinationId,draftId:'101',erpAccountId:'11',marketId:'91',countryCode:'US',store:f.input.store,parentSku:f.input.goods.parentSku,failedSkus:f.record.failureObservation.skus};
}
function acceptedRequest(record){record.mediaRecovery.nativeRequests=[{method:'POST',url:endpoint,path:'/api/amazon/goods/publish/re-publish',payload:{ids:[202]},response:{httpStatus:200,body:{code:0}}}];}
const remoteProof=async(_url,asset)=>({sha256:asset.sha256,bytes:100,verifiedAt:new Date().toISOString()});

test('authorized media recovery verifies eight original assets and their reported URLs before arming one existing-family request',async()=>{
 const f=fixture(),snapshots=[],calls=[];let submits=0,reads=0;
 const originalIdentity=structuredClone(f.record.identity),originalSource=structuredClone(f.record.sourceEvidence);
 const result=await recoverNativeMediaPublication({},f.input,f.record,async()=>snapshots.push(structuredClone(f.record.mediaRecovery)),{
  amendment:f.amendment,read:async(_page,id)=>{reads++;assert.equal(id,'202');return f.failed;},
  remote:async(url,asset)=>{calls.push(url);assert.equal(snapshots.at(-1).intent,undefined);return remoteProof(url,asset);},
  submit:async(_page,_input,record)=>{submits++;assert.ok(snapshots.at(-1).intent.armedAt);assert.equal(record.mediaRecovery.preflight.passed,true);acceptedRequest(record);}
 });
 assert.equal(reads,2);assert.equal(submits,1);assert.equal(calls.length,15);assert.equal(new Set(calls).size,15);
 assert.equal(result.preflight.uniqueAssetCount,8);assert.equal(result.preflight.urlCount,15);assert.equal(result.failedCount,3);assert.equal(result.acceptedCount,27);
 assert.equal(result.scope,'original_failed_family');assert.equal(result.requestAccepted,true);assert.equal(result.phase,'request_accepted');
 assert.equal(f.record.publishId,'202');assert.equal(f.record.phase,'publication_failed');assert.equal(f.record.status,'failed');
 assert.deepEqual(result.originalAcceptedIdentity,originalIdentity);assert.deepEqual(result.originalAcceptedSourceEvidence,originalSource);
 assert.notEqual(result.originalAcceptedSourceEvidence,f.record.sourceEvidence);
});

test('wrong, missing or stale authorization never reaches media requests or native submission',async()=>{
 for(const alter of [f=>delete f.amendment.jobId,f=>f.amendment.accountId=3,f=>f.amendment.publishId='303',f=>f.amendment.snapshotSha256='other',
  f=>f.amendment.failureResponseFingerprint='0'.repeat(64),f=>f.amendment.failedChildIds.pop(),f=>f.amendment.authorizedAt='2026-11-16',
  f=>delete f.record.sourceLink,f=>f.record.sourceEvidence.title='Other',f=>f.record.phase='publish_unknown']){
  const f=fixture();alter(f);let remotes=0,submits=0;
  await assert.rejects(()=>recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,remote:async()=>remotes++,submit:async()=>submits++}));
  assert.equal(remotes,0);assert.equal(submits,0);assert.equal(f.record.mediaRecovery?.intent,undefined);
 }
});

test('unsupported errors, unscoped messages and contradictory child states cannot authorize a family retry',async()=>{
 for(const alter of [
  f=>{f.failed.data.errors[0].code='90220';f.failed.data.items.find(row=>row.sku==='Original-Brown-M').extra.message[0].code='90220';},
  f=>f.failed.data.errors.push({sku:'Unknown',code:'300060',message:'Cannot access '+f.failed.data.items[13].extra.images[0],severity:'ERROR'}),
  f=>{f.failed.data.status='publishing';},
  f=>{const row=f.failed.data.items.find(row=>row.sku==='Original-Gray-XXL');row.extra.message=[];f.failed.data.errors=f.failed.data.errors.filter(message=>message.sku!==row.sku);},
  f=>{f.failed.data.items[0].extra.message=[{code:'18320',message:'Accepted child still has an error',severity:'ERROR'}];}
 ]){
  const f=fixture();alter(f);rebind(f);let remotes=0,submits=0;
  await assert.rejects(()=>recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,remote:async()=>remotes++,submit:async()=>submits++}));
  assert.equal(remotes,0);assert.equal(submits,0);assert.equal(f.record.mediaRecovery?.intent,undefined);
 }
});

test('foreign or unrelated reported media URLs block without uploading or arming intent',async()=>{
 for(const replacement of ['https://other.example/u/19335/26/11/file.png',regional+'/u/19335/26/11/not-original.png']){
  const f=fixture(),row=f.failed.data.items.find(row=>row.sku==='Original-Brown-M');row.extra.message[0].message='Cannot access '+replacement;
  f.failed.data.errors.find(message=>message.sku===row.sku).message=row.extra.message[0].message;rebind(f);let submits=0;
  await assert.rejects(()=>recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,remote:remoteProof,submit:async()=>submits++}));
  assert.equal(submits,0);assert.equal(f.record.mediaRecovery?.intent,undefined);
 }
});

test('legacy inherited galleries remain readable evidence but cannot authorize a retry',async()=>{
 const f=fixture();f.input.assets=f.input.assets.slice(0,7);f.input.urls=Object.fromEntries(f.input.assets.map(asset=>[asset.sha256,f.input.urls[asset.sha256]]));
 const images=Object.values(f.input.urls);for(const v of f.input.goodsItems)v.imageIndices=[0,1,2,3,4,5,6];
 f.accepted.data.extra.images=[...images];for(const row of f.accepted.data.items){row.main_image=images[0];row.extra.images=[...images];}
 f.failed=structuredClone(f.accepted);f.failed.data.status='failed';
 for(const row of f.failed.data.items)if(['Original-Brown-M','Original-Brown-XXL','Original-Gray-XXL'].includes(row.sku)){
  row.status='failed';row.extra.message=[{code:'18320',message:'Main image missing',severity:'ERROR'}];f.failed.data.errors.push({...row.extra.message[0],sku:row.sku});
 }
 f.failed.data.items[0].extra.images=null;
 f.record.sourceEvidence=structuredClone(f.accepted.data);f.record.identity=verifyPublication(f.accepted,f.input,'202');f.record.fingerprint=publicationFingerprint(assertPublicationInput(f.input));rebind(f);
 assert.equal(f.record.failureObservation.children[0].imagesSource,'parent_shared_gallery');let remoteCalls=0;
 await assert.rejects(()=>recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,
  remote:async()=>remoteCalls++,submit:async()=>assert.fail('must not retry inherited galleries')}));
 assert.equal(remoteCalls,0);assert.equal(f.record.mediaRecovery?.intent,undefined);
});

test('known bad media proof is journaled without an armed intent and can be rechecked before any native write',async()=>{
 const f=fixture();let submits=0;
 await assert.rejects(()=>recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,
  remote:async()=>({sha256:'wrong',bytes:100}),submit:async()=>submits++}));
 assert.equal(submits,0);assert.equal(f.record.mediaRecovery.phase,'preflight_failed');assert.equal(f.record.mediaRecovery.intent,undefined);
 assert.ok(f.record.mediaRecovery.preflight.objects.some(row=>row.error));
 await recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,remote:remoteProof,submit:async(_p,_i,record)=>{submits++;acceptedRequest(record);}});
 assert.equal(submits,1);assert.equal(f.record.mediaRecovery.requestAccepted,true);
});

test('once armed, unknown recovery resumes only its original task, including pending and healthy reads',async()=>{
 const f=fixture();let submits=0;
 await assert.rejects(()=>recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,remote:remoteProof,
  submit:async()=>{submits++;throw Error('connection lost after native click');}}),/connection lost/);
 assert.ok(f.record.mediaRecovery.intent);assert.equal(f.record.mediaRecovery.requestAccepted,false);
 const pending=structuredClone(f.accepted);pending.data.status='waiting';pending.data.items.forEach(row=>row.status='waiting');
 for(const response of [f.failed,pending,f.accepted]){
  let reads=0;const result=await recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,
   read:async(_page,id)=>{reads++;assert.equal(id,'202');return response;},remote:async()=>assert.fail('must not fetch again'),query:async()=>assert.fail('must not select another row'),submit:async()=>assert.fail('must not click again')});
  assert.equal(reads,1);assert.equal(result.requestAccepted,false);
 }
 assert.equal(submits,1);assert.equal(f.record.mediaRecovery.lastObservation.verification,'accepted');
});

test('a task that becomes healthy before arming skips the request and permits normal publication reconciliation',async()=>{
 for(const recoverAfterPreflight of [false,true]){
  const f=fixture();let reads=0,remotes=0,submits=0;
  const result=await recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,
   read:async()=>++reads===1&&recoverAfterPreflight?f.failed:f.accepted,remote:async(url,asset)=>{remotes++;return remoteProof(url,asset);},submit:async()=>submits++});
  assert.equal(submits,0);assert.equal(result.intent,undefined);assert.equal(result.phase,'no_retry_needed');assert.equal(result.requestAccepted,false);
  assert.equal(result.consumedWithoutWrite,true);f.record.phase='publishing_verified';
  for(const response of [f.accepted,f.failed]){
   await recoverNativeMediaPublication({},f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>response,
    remote:async()=>assert.fail('consumed authorization must not preflight again'),submit:async()=>assert.fail('consumed authorization must not click')});
   assert.equal(result.intent,undefined);assert.equal(result.consumedWithoutWrite,true);
  }
  assert.equal(remotes,recoverAfterPreflight?15:0);
 }
});

function xhrContext(){
 const sent=[];
 class XHR{
  constructor(){this.listeners=[];}
  open(method,url){this.method=method;this.url=url;}
  send(body){sent.push({method:this.method,url:this.url,body});}
  addEventListener(_type,listener){this.listeners.push(listener);}
  finish(status,body){this.status=status;this.responseText=JSON.stringify(body);for(const listener of this.listeners)listener();}
 }
 const context=vm.createContext({window:{},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com/#/goods/amazon/publish'}});
 return{context,sent,fire(method='POST',url=endpoint,payload={ids:[202]}){const xhr=new context.XMLHttpRequest();xhr.open(method,url);xhr.send(JSON.stringify(payload));return xhr;}};
}

test('the actual native XHR guard rejects wrong endpoints, IDs, extra keys, child scopes and duplicate writes',()=>{
 for(const [method,url,payload]of [['POST',endpoint,{ids:[203]}],['POST',endpoint,{ids:[202,203]}],['POST',endpoint,{ids:[202],store:'Other'}],
  ['POST',endpoint,{ids:['202']}],['POST',endpoint+'?draft=1',{ids:[202]}],['POST',endpoint.replace('re-publish','publish'),{ids:[202]}],['PUT',endpoint,{ids:[202]}]]){
  const session=xhrContext();vm.runInContext('('+installNativeMediaRecoveryGuard.toString()+')({publishId:"202"})',session.context);
  assert.throws(()=>session.fire(method,url,payload));assert.equal(session.sent.length,0);assert.throws(()=>session.fire());
 }
 const session=xhrContext();vm.runInContext('('+installNativeMediaRecoveryGuard.toString()+')({publishId:"202"})',session.context);
 session.fire();assert.equal(session.sent.length,1);assert.deepEqual(JSON.parse(session.sent[0].body),{ids:[202]});assert.throws(()=>session.fire());assert.equal(session.sent.length,1);
});

test('normal native retry button is the sole POST and its acknowledgement does not mark publication verified',async()=>{
 const f=fixture(),session=xhrContext();let clicks=0,queries=0;
 const button={innerText:'再次发布',disabled:false,setAttribute(){},scrollIntoView(){}},row={cells:[{}, {innerText:'202'}, {}, {}, {innerText:f.input.store}, {innerText:'Original'}],getBoundingClientRect:()=>({width:100}),querySelectorAll:()=>[button]};
 session.context.document={querySelectorAll:()=>[row]};
 const page={evaluate:async(fn,arg)=>{session.context.arg=arg;return structuredClone(vm.runInContext('('+fn.toString()+')(arg)',session.context));},
  click:async selector=>{assert.equal(selector,'[data-native-media-recovery]');assert.ok(f.record.mediaRecovery.intent);clicks++;session.fire().finish(200,{code:0});},
  waitForFunction:async fn=>assert.equal(vm.runInContext('('+fn.toString()+')()',session.context),true)};
 const result=await recoverNativeMediaPublication(page,f.input,f.record,async()=>{}, {amendment:f.amendment,read:async()=>f.failed,remote:remoteProof,
  query:async()=>{queries++;assert.ok(f.record.mediaRecovery.intent);return[{id:202,sku:'Original',market_id:91,country_code:'US',market:{alias:f.input.store},status:'failed'}];}});
 assert.equal(clicks,1);assert.equal(queries,1);assert.equal(session.sent.length,1);assert.equal(result.requestAccepted,true);assert.equal(result.scope,'original_failed_family');
 assert.equal(f.record.phase,'publication_failed');assert.equal(f.record.publishId,'202');assert.equal(session.context.window.__nativeMediaRecoveryWrite,undefined);
});
