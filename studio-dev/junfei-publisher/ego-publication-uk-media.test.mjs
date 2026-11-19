import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,verifyPublication} from './ego-publish-native.mjs';
import {retryNativeUkMedia,ukMediaManifest} from './ego-publication-uk-media.mjs';
import {runPublicationWorkflow} from './ego-publication-workflow.mjs';

const clone=structuredClone,endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish';
function fixture(){
 const assets=Array.from({length:105},(_,i)=>({sha256:createHash('sha256').update('UKmedia-'+i).digest('hex'),width:1600,height:1600}));
 const urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,`https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/u/11/26/11/s_${i}.png`]));
 const sizes={S:'s',M:'m',L:'l',XL:'x_l',XXL:'xx_l'},goodsItems=Array.from({length:15},(_,c)=>Object.keys(sizes).map(size=>({sku:`Parent-${c}-${size}`,color:String(c),size,price:'15.19',quantity:88,imageIndices:Array.from({length:7},(_,i)=>c*7+i)}))).flat();
 const input={accountId:2,productId:'P',jobId:'job',sha256:'snapshot',marketplace:'UK',store:'UK store',masterColor:'0',assets,urls,goodsItems,
  goods:{parentSku:'Parent',title:'Original title',brand:'Original Brand',manufacturer:'Maker',description:'Original description',bullets:['Original bullet'],terms:'original terms'},
  destination:{destinationId:'UK',draftId:'101',marketId:'91',erpAccountId:'11',countryCode:'GB',marketplaceId:'GBMARKET',schemaHash:'GBschema',sizeValues:sizes,variationFields:{color:'color.0.value',size:'shirt_size.0.size'}}};
 const cover=urls[assets[0].sha256],accepted={code:0,data:{id:202,uid:11,market_id:91,country_code:'GB',market:{alias:'UK store'},sku:'Parent',title:input.goods.title,brand:input.goods.brand,manufacturer:'Maker',product_type_name:'SWEATSHIRT',price:'15.19',quantity:88,main_image:cover,status:'publishing',errors:[],standard_product_id:null,standard_product_type:'UPC',
  extra:{images:[cover],keywords:input.goods.terms,product_description:input.goods.description,bullet_point:input.goods.bullets,attributes:{}},
  items:goodsItems.map((v,i)=>({id:203+i,pid:202,uid:11,sku:v.sku,price:v.price,quantity:88,status:'accepted',standard_product_id:null,standard_product_type:null,main_image:urls[assets[v.imageIndices[0]].sha256],
   extra:{images:v.imageIndices.map(i=>urls[assets[i].sha256]),message:null,attributes:{color:[{value:v.color,marketplace_id:'GBMARKET'}],shirt_size:[{size:sizes[v.size],marketplace_id:'GBMARKET'}]}}}))}};
 const response=clone(accepted),child=response.data.items[2];response.data.status='failed';child.status='failed';
 const messages=[0,1,2,4,5,6].map(slot=>({sku:child.sku,code:'300060',severity:'ERROR',message:'Cannot access '+child.extra.images[slot].replace('oss-cn-shenzhen','oss-accelerate')}));
 messages.push({sku:child.sku,code:'18448',severity:'WARNING',attributeNames:['material'],categories:['MISSING_ATTRIBUTE','PRODUCT'],
  message:'您提交的内容缺少一些关键属性：material。 缺少这些属性不会阻止您的商品在亚马逊上展示。 然而，这会影响您的商品信息的整体质量。'});
 response.data.errors=messages;child.extra.message=messages;
 const prior={method:'POST',url:endpoint,payload:{ids:[202]},sentAt:'2026-11-18T04:00:00Z',response:{httpStatus:200,body:{code:0}}};
 const record={publishId:'202',phase:'publication_failed',fingerprint:publicationFingerprint(assertPublicationInput(input)),identity:verifyPublication(accepted,input,'202'),sourceLink:{publishId:'202',draftId:'101'},sourceEvidence:clone(accepted.data),
  requiredAttributeRepair:{keep:'all old data'},identifierRepair:{saveVerified:true,plannedSource:clone(accepted.data),retry:{intent:{publishId:'202'},requestAccepted:true,nativeRequests:[prior]}}};
 record.latestObservation=publicationFailureObservation(response,input,'202');record.failureObservation=clone(record.latestObservation);
 const obs=record.latestObservation,a={id:'a'.repeat(32),scope:'retry_original_uk_failed_media_once',marketplace:'UK',nativeScope:'original_parent_family',accountId:2,productId:'P',jobId:'job',snapshotSha256:'snapshot',publishId:'202',destinationId:'UK',draftId:'101',erpAccountId:'11',marketId:'91',countryCode:'GB',store:'UK store',parentSku:'Parent',schemaHash:'GBschema',variantCount:75,assetCount:105,saveProductData:false,replaceImages:false,failureResponseFingerprint:obs.responseFingerprint,failedChildIds:obs.failedChildIds,failedSkus:obs.skus,originalFailureObservation:clone(obs),nonBlockingWarnings:obs.messages.filter(m=>m.code==='18448'),assetManifest:ukMediaManifest(input),preservedSource:clone(accepted.data),failureObservedAt:'2026-11-18T05:00:00Z',cooldownNotBefore:Date.parse('2026-11-18T05:20:00Z')/1000,cooldownSeconds:1200,authorizedAt:Date.parse('2026-11-18T05:30:00Z')/1000};
 a.failedMedia=[0,1,2,4,5,6].map(slot=>({childId:String(child.id),sku:child.sku,code:'300060',slot,originalUrl:child.extra.images[slot],reportedUrl:child.extra.images[slot].replace('oss-cn-shenzhen','oss-accelerate'),assetSha256:assets[slot].sha256}));
 const meta={hash:'GBschema',country_code:'GB',locale:'en_GB',product_type_name:'SWEATSHIRT',schema_content:{type:'object'}};
 return {input,record,response,accepted,amendment:a,meta};
}
function adapters(f,overrides={}){return{amendment:f.amendment,schemaObservation:f.meta,now:()=>Date.parse('2026-11-18T05:30:00Z')/1000,
 read:async()=>f.response,observe:async()=>({response:f.response,meta:f.meta}),local:async()=>({passed:true,count:105}),
 validate:(_m,rows)=>({passed:true,checkedCount:rows.length}),remote:async(_u,a)=>({sha256:a.sha256,bytes:100}),decode:async(_p,urls)=>urls.map(url=>({url,decoded:true,width:1600,height:1600})),
 submit:async(_p,_i,proxy,_save,{armIntent})=>{assert.equal(proxy.mediaRecovery.intent,undefined);await armIntent();assert.ok(proxy.mediaRecovery.intent);proxy.mediaRecovery.nativeRequests=[{method:'POST',url:endpoint,payload:{ids:[202]},response:{httpStatus:200,body:{code:0}}}];},...overrides};}

test('UK75 original parent once-only,12 exact URL proofs,all old journals and data remain',async()=>{
 const f=fixture(),old=clone(f.record),snapshots=[];let writes=0;
 const result=await retryNativeUkMedia({},f.input,f.record,async()=>snapshots.push(clone(f.record)),adapters(f,{submit:async(...args)=>{writes++;await adapters(f).submit(...args);}}));
 assert.equal(result.requestAccepted,true);assert.equal(result.preflight.remoteObjects.length,12);assert.equal(result.intent.variantCount,75);assert.equal(writes,1);
 assert.deepEqual(f.record.identifierRepair,old.identifierRepair);assert.deepEqual(f.record.requiredAttributeRepair,old.requiredAttributeRepair);assert.deepEqual(f.record.sourceEvidence,old.sourceEvidence);assert.equal(f.record.phase,old.phase);
 assert.ok(snapshots.some(r=>r.mediaRecovery.intent&&r.mediaRecovery.phase==='retry_unknown'));
 await retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('one parent retry only')}));
});

test('105 original positions may share91 exact same-content files without replacing assets',()=>{
 const f=fixture();for(let c=1;c<15;c++)f.input.assets[c*7+3]=clone(f.input.assets[3]);
 const list=ukMediaManifest(f.input);assert.equal(list.length,105);assert.equal(new Set(list.map(a=>a.sha256)).size,91);
});

test('wrong owner/country,changed facts or URLs,unknown old retry,new error,wrong schema/cooldown/decode all stop before intent',async()=>{
 for(const change of [f=>f.input.accountId=3,f=>f.input.destination.countryCode='US',f=>f.response.data.items[0].price='99',f=>f.record.identifierRepair.retry.requestAccepted=false,f=>f.response.data.items[2].extra.message.push({sku:f.response.data.items[2].sku,code:'999',severity:'ERROR',message:'new error'}),f=>f.amendment.assetManifest[0].url+='?changed',f=>f.amendment.cooldownNotBefore+=1200,f=>f.meta.hash='new-schema']){
  const f=fixture();change(f);await assert.rejects(()=>retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('blocked')})));assert.equal(f.record.mediaRecovery?.intent,undefined);
 }
 const f=fixture();await assert.rejects(()=>retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{decode:async()=>[]})));assert.equal(f.record.mediaRecovery.intent,undefined);
});

test('ack unknown never reissues; another amendment cannot replace journal',async()=>{
 const f=fixture();let writes=0;
 await assert.rejects(()=>retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{submit:async(_p,_i,_r,_s,{armIntent})=>{await armIntent();writes++;throw Error('ack unknown');}})),/ack unknown/);
 await retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('unknown remains read only')}));assert.equal(writes,1);
 const a=clone(f.amendment);a.id='b'.repeat(32);await assert.rejects(()=>retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{amendment:a})),/不同/);
});

test('healthy or pending natural recovery consumes withoutwrite; later failure stays read-only',async()=>{
 for(const status of ['publishing','waiting']){const f=fixture(),fresh=clone(f.accepted);fresh.data.status=status;
  const j=await retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{observe:async()=>({response:fresh,meta:f.meta}),submit:async()=>assert.fail('do not write')}));
  assert.equal(j.consumedWithoutWrite,true);assert.equal(j.intent,undefined);
  await retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('never reactivate')}));
 }
});

test('ordinary continue and nonblocking material-only observation remain read-only without hiding warning',async()=>{
 const f=fixture();const j=await retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f,{observeOnly:true,observe:async()=>assert.fail('no preflight'),remote:async()=>assert.fail('no fetch'),submit:async()=>assert.fail('no write')}));assert.equal(j.intent,undefined);
 const g=fixture(),warning=clone(g.accepted);warning.data.errors=[g.response.data.errors.at(-1)];warning.data.items[2].extra.message=warning.data.errors;
 const result=await retryNativeUkMedia({},g.input,g.record,async()=>{},adapters(g,{observe:async()=>({response:warning,meta:g.meta}),submit:async()=>assert.fail('no media failure')}));
 assert.equal(result.consumedWithoutWrite,true);assert.equal(result.lastObservation.verification,'accepted');assert.equal(result.lastObservation.status,'publishing');
 assert.equal(result.lastObservation.warnings[0].code,'18448');assert.equal(result.lastObservation.failed,false);
 assert.equal(result.originalFailureObservation.failed,true);assert.equal(result.intent,undefined);
});

test('workflow UK-only phase never prepares,copies or reads US and preserves old journals',async()=>{
 const f=fixture(),i={...clone(f.input),marketplace:'US',store:'US store',destination:{countryCode:'US'},ukTarget:{id:'UK',storeName:'UK store'},publicationUkMediaRecovery:f.amendment};
 const r={usPublish:{keep:'original-US'},ukCopy:{phase:'copy_verified',draftId:'101'},ukPrepare:{phase:'uk_draft_verified',draftId:'101',preparedInput:f.input,urls:f.input.urls,schemaObservation:f.meta},ukPublish:f.record};const oldUS=clone(r.usPublish),events=[];
 const forbidden=async()=>assert.fail('targeted UK only');
 await runPublicationWorkflow({},i,r,async()=>{},{phase:'uk_media_recovery',ukMediaObserveOnly:true,adapters:{prepareUs:forbidden,prepareUk:forbidden,copy:forbidden,recoverMedia:forbidden,repairIdentifiers:forbidden,retryUkMedia:async(_p,prepared,publication,_s,options)=>{assert.equal(prepared.destination.countryCode,'GB');assert.equal(options.observeOnly,true);events.push('UK-only');},publish:async(_p,prepared)=>{assert.equal(prepared.destination.countryCode,'GB');events.push('read-UK');}}});
 assert.deepEqual(events,['UK-only','read-UK']);assert.deepEqual(r.usPublish,oldUS);
 await assert.rejects(()=>runPublicationWorkflow({},i,r,async()=>{},{phase:'all'}),/专用/);
 r.ukCopy.draftId='foreign';await assert.rejects(()=>runPublicationWorkflow({},i,r,async()=>{},{phase:'uk_media_recovery'}),/冻结/);
});

test('consumed UK retry reports changed media errors and material warnings without sending again',async()=>{
 const f=fixture(),latest=clone(f.accepted);
 latest.data.status='failed';
 for(const [index,child] of latest.data.items.slice(0,6).entries()){
  child.status='failed';
  const report=(code,slot,message)=>({sku:child.sku,code,severity:'ERROR',
   message:message+' '+child.extra.images[slot].replace('oss-cn-shenzhen','oss-accelerate')});
  child.extra.message=[report('300060',index===5?2:5,'Cannot access'),{...f.response.data.errors.at(-1),sku:child.sku}];
  if(index===1)child.extra.message.push(report('300429',1,'HTTP status 429 when fetching'));
  latest.data.errors.push(...child.extra.message);
 }
 await retryNativeUkMedia({},f.input,f.record,async()=>{},adapters(f));
 const previousRequests=clone(f.record.mediaRecovery.nativeRequests),reads=[];
 const input={...clone(f.input),marketplace:'US',store:'US store',destination:{countryCode:'US'},
  ukTarget:{id:'UK',storeName:'UK store'},publicationUkMediaRecovery:f.amendment};
 const record={usPublish:{keep:'original-US'},ukCopy:{phase:'copy_verified',draftId:'101'},
  ukPrepare:{phase:'uk_draft_verified',draftId:'101',preparedInput:f.input,urls:f.input.urls,schemaObservation:f.meta},ukPublish:f.record};
 const forbidden=async()=>assert.fail('media observation must not write or run preflight');
 const read=async(_page,id)=>{reads.push(id);assert.equal(id,'202');return latest;};
 await assert.rejects(()=>runPublicationWorkflow({},input,record,async()=>{},{phase:'uk_media_recovery',ukMediaObserveOnly:true,
  adapters:{prepareUs:forbidden,prepareUk:forbidden,copy:forbidden,
   ukMediaAdapters:adapters(f,{read,observe:forbidden,remote:forbidden,submit:forbidden}),
   publishAdapters:{read,submit:forbidden}}}),error=>{
  assert.equal(error.code,'ERP_PUBLICATION_FAILED');assert.equal(error.status,'failed');assert.equal(error.publishId,'202');
  assert.equal(error.failureObservation.count,6);assert.equal(error.failureObservation.acceptedCount,69);
  assert.equal(error.failureObservation.messageCount,13);
  assert.match(error.message,/错误代码 300060、300429。提醒代码 18448。Amazon 报告图片抓取遇到 HTTP 429 限流/);
  assert.doesNotMatch(error.message,/https?:\/\//);
  assert.equal(record.error,error.message);
  return true;
 });
 assert.deepEqual(reads,['202','202']);assert.deepEqual(record.usPublish,{keep:'original-US'});
 assert.deepEqual(record.ukPublish.mediaRecovery.nativeRequests,previousRequests);
 assert.equal(record.ukPublish.latestObservation.count,6);
 assert.equal(record.ukPublish.mediaRecovery.lastObservation.count,6);
});
