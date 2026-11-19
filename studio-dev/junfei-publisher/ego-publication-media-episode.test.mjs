import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,verifyPublication} from './ego-publish-native.mjs';
import {retryNativeMediaEpisode,mediaEpisodeAssetManifest} from './ego-publication-media-episode.mjs';

const clone=structuredClone,endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish';
function fixture(){
 const assets=Array.from({length:35},(_,i)=>({sha256:createHash('sha256').update('episode-'+i).digest('hex'),width:1600,height:1600}));
 const urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,`https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/u/11/26/11/s_${i}.png`]));
 const sizes={S:'s',M:'m',L:'l',XL:'x_l',XXL:'xx_l','3XL':'3x_l'};
 const goodsItems=['01-white','01-black','01-brown','01-gray','01-red'].flatMap((color,c)=>Object.keys(sizes).map(size=>({sku:`Original-${color}-${size}`,color,size,price:'13.95',quantity:88,imageIndices:Array.from({length:7},(_,i)=>c*7+i)})));
 const input={accountId:2,productId:'original-product',jobId:'original-job',sha256:'original-sha',marketplace:'US',mode:'draft',store:'Original US Store',masterColor:'01-white',assets,urls,goodsItems,
  goods:{parentSku:'Original',title:'Original title',brand:'Original Brand',manufacturer:'Original Maker',description:'Original description',bullets:['Original bullet'],terms:'original terms'},
  destination:{destinationId:'us',draftId:'101',marketId:'91',erpAccountId:'11',countryCode:'US',marketplaceId:'USMARKET',schemaHash:'actual-us-hash',sizeValues:sizes,variationFields:{color:'color.0.value',size:'shirt_size.0.size'}}};
 const cover=urls[assets[0].sha256],accepted={code:0,data:{id:202,uid:11,market_id:91,country_code:'US',market:{alias:input.store},sku:'Original',title:input.goods.title,brand:input.goods.brand,manufacturer:input.goods.manufacturer,
  product_type_name:'SHIRT',category_path:'Original category',price:'13.95',quantity:88,main_image:cover,status:'publishing',errors:[],
  extra:{images:[cover],keywords:input.goods.terms,product_description:input.goods.description,bullet_point:input.goods.bullets,attributes:{}},
  items:goodsItems.map((v,i)=>({id:203+i,pid:202,uid:11,sku:v.sku,price:v.price,quantity:v.quantity,status:'accepted',main_image:urls[assets[v.imageIndices[0]].sha256],
   extra:{images:v.imageIndices.map(n=>urls[assets[n].sha256]),message:null,attributes:{fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:88,lead_time_to_ship_max_days:3}],parentage_level:[{value:'child'}],child_parent_sku_relationship:[{parent_sku:'Original',child_relationship_type:'variation'}],variation_theme:[{name:'COLOR_NAME/SIZE_NAME'}],color:[{value:v.color,marketplace_id:'USMARKET'}],shirt_size:[{size:sizes[v.size],marketplace_id:'USMARKET'}]}}}))}};
 const gray=accepted.data.items.find(c=>c.sku==='Original-01-gray-XXL');gray.extra.attributes.main_product_image_locator=[{marketplace_id:'USMARKET',media_location:gray.main_image}];
 const response=clone(accepted),black=response.data.items.find(c=>c.sku==='Original-01-black-M'),target=response.data.items.find(c=>c.id===gray.id);
 response.data.status='failed';black.status=target.status='failed';
 const reported=black.extra.images[4].replace('oss-cn-shenzhen','oss-accelerate');
 const messages=[{sku:black.sku,code:'20000',message:`Download timeout ${reported}`,severity:'ERROR'},{sku:target.sku,code:'18320',message:'Main image missing or incorrect',severity:'ERROR'}];
 response.data.errors=messages;black.extra.message=[messages[0]];target.extra.message=[messages[1]];
 const request={method:'POST',url:endpoint,payload:{ids:[202]},sentAt:'2026-11-17T00:00:00Z',response:{httpStatus:200,body:{code:0}}};
 const record={publishId:'202',phase:'publication_failed',fingerprint:publicationFingerprint(assertPublicationInput(input)),identity:verifyPublication(accepted,input,'202'),sourceEvidence:clone(accepted.data),sourceLink:{publishId:'202',draftId:'101'},
  mediaRecovery:{intent:{publishId:'202',old:'keep'},amendment:{failureResponseFingerprint:'1'.repeat(64)},nativeRequests:[clone(request)]},
  mainImageRepair:{saveVerified:true,persistedSchemaValidation:{passed:true,checkedCount:31},amendment:{failedChildId:String(gray.id),failedSku:gray.sku,mainImageUrl:gray.main_image,failureResponseFingerprint:'2'.repeat(64)},retry:{intent:{publishId:'202',old:'keep'},requestAccepted:true,nativeRequests:[clone(request)]}}};
 record.failureObservation=publicationFailureObservation(response,input,'202');record.latestObservation=record.failureObservation;
 const observation=record.latestObservation,amendment={id:'a'.repeat(32),scope:'retry_original_new_media_failure_episode',marketplace:'US',nativeScope:'original_parent_family',accountId:2,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,publishId:'202',destinationId:'us',draftId:'101',erpAccountId:'11',marketId:'91',countryCode:'US',store:input.store,parentSku:'Original',variantCount:30,assetCount:35,saveProductData:false,replaceImages:false,requiresVerifiedOriginalMain:true,
  failureResponseFingerprint:observation.responseFingerprint,failedChildIds:observation.failedChildIds,failedSkus:observation.skus,assetManifest:mediaEpisodeAssetManifest(input),failureObservedAt:'2026-11-17T05:00:00Z',cooldownNotBefore:Date.parse('2026-11-17T05:20:00Z')/1000,cooldownSeconds:1200,authorizedAt:Date.parse('2026-11-17T05:30:00Z')/1000,
  failedMedia:[{childId:String(black.id),sku:black.sku,code:'20000',slot:4,originalUrl:black.extra.images[4],reportedUrl:reported,assetSha256:assets[11].sha256},{childId:String(gray.id),sku:gray.sku,code:'18320',slot:0,originalUrl:gray.main_image,reportedUrl:gray.main_image,assetSha256:assets[21].sha256}]};
 const meta={hash:'actual-us-hash',country_code:'US',locale:'en_US',schema_content:{type:'object'}};
 return {input,accepted,response,record,amendment,meta};
}
function adapters(f,overrides={}){return {amendment:f.amendment,schemaObservation:f.meta,now:()=>Date.parse('2026-11-17T05:30:00Z')/1000,
 observe:async()=>({response:f.response,meta:f.meta}),read:async()=>f.response,
 validate:(_m,rows)=>({passed:rows.length===31,checkedCount:rows.length}),local:async()=>({passed:true,count:35}),
 remote:async(_url,asset)=>({sha256:asset.sha256,bytes:100}),decode:async(_p,urls)=>urls.map(url=>({url,decoded:true,width:1600,height:1600})),
 submit:async(_p,_i,proxy)=>{assert.equal(proxy.mediaRecovery,f.record.mediaEpisodes[0]);assert.notEqual(proxy.mediaRecovery,f.record.mediaRecovery);proxy.mediaRecovery.nativeRequests=[{method:'POST',url:endpoint,payload:{ids:[202]},response:{httpStatus:200,body:{code:0}}}];},...overrides};}

test('one new episode validates full family and assets, retries original parent once, preserves all old histories',async()=>{
 const f=fixture(),old=clone(f.record),snapshots=[];let writes=0;
 const result=await retryNativeMediaEpisode({},f.input,f.record,async()=>snapshots.push(clone(f.record)),adapters(f,{submit:async(p,i,proxy)=>{
  writes++;assert.ok(snapshots.at(-1).mediaEpisodes[0].intent);assert.equal(proxy.mediaRecovery.intent.variantCount,30);await adapters(f).submit(p,i,proxy);
 }}));
 assert.equal(result.requestAccepted,true);assert.equal(result.preflight.remoteObjects.length,4);assert.equal(writes,1);
 assert.deepEqual(f.record.mediaRecovery,old.mediaRecovery);assert.deepEqual(f.record.mainImageRepair,old.mainImageRepair);assert.equal(f.record.phase,old.phase);assert.deepEqual(f.record.sourceEvidence,old.sourceEvidence);
 await retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('never retry twice')}));assert.equal(f.record.mediaEpisodes.length,1);
});

test('cooldown, altered manifest, old MAIN not saved, changed code, missing locator and failed decode all stop before intent',async()=>{
 for(const mutate of [f=>f.amendment.cooldownNotBefore+=1200,f=>f.amendment.assetManifest[0].sha256='0'.repeat(64),f=>f.record.mainImageRepair.saveVerified=false,
  f=>f.amendment.failureResponseFingerprint='0'.repeat(64),f=>delete f.response.data.items.find(c=>c.sku==='Original-01-gray-XXL').extra.attributes.main_product_image_locator]){
  const f=fixture();mutate(f);await assert.rejects(()=>retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('blocked')})));assert.equal(f.record.mediaEpisodes?.[0]?.intent,undefined);
 }
 const f=fixture();await assert.rejects(()=>retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{decode:async()=>[]})));assert.equal(f.record.mediaEpisodes[0].intent,undefined);
});

test('unknown original-parent retry stays read-only even if failure later recurs',async()=>{
 const f=fixture();let writes=0;
 await assert.rejects(()=>retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>{writes++;throw Error('ack lost');}})),/ack lost/);
 assert.ok(f.record.mediaEpisodes[0].intent);
 await retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('no replay')}));assert.equal(writes,1);
 const other=clone(f.amendment);other.id='b'.repeat(32);await assert.rejects(()=>retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{amendment:other})),/不覆盖或新增/);
});

test('natural acceptance before or during preflight consumes episode without retry and later failure cannot reactivate it',async()=>{
 for(const during of [false,true]){const f=fixture();let reads=0;
  const options=adapters(f,{observe:async()=>({response:during&&++reads===1?f.response:f.accepted,meta:f.meta}),submit:async()=>assert.fail('no retry')});
  const result=await retryNativeMediaEpisode({},f.input,f.record,async()=>{},options);assert.equal(result.consumedWithoutWrite,true);assert.equal(result.intent,undefined);
  await retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{submit:async()=>assert.fail('not reactivated')}));assert.equal(result.intent,undefined);
 }
});

test('ordinary continuation reads only even when the frozen episode never armed an intent',async()=>{
 const f=fixture();const result=await retryNativeMediaEpisode({},f.input,f.record,async()=>{},adapters(f,{observeOnly:true,
  observe:async()=>assert.fail('no preflight'),local:async()=>assert.fail('no local replay'),remote:async()=>assert.fail('no media requests'),submit:async()=>assert.fail('no retry')}));
 assert.equal(result.intent,undefined);assert.equal(result.consumedWithoutWrite,true);assert.equal(result.lastObservation.count,2);
});
