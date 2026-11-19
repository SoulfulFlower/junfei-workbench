// One later, explicitly frozen media failure episode. Never save or replace
// images; never reset the earlier mediaRecovery / mainImageRepair journals.
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,readNativePublication} from './ego-publish-native.mjs';
import {verifyRemoteAsset,imageDimensions} from './ego-draft-images.mjs';
import {readMainImageRepairSource,mainImageBusinessProjection} from './ego-publication-main-image.mjs';
import {submitNativeMediaRecovery} from './ego-publication-recovery.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';

const regional='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com',accelerated='https://junfeikuajing.oss-accelerate.aliyuncs.com';
const endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish';
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const equalIds=(a,b)=>Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&new Set(a.map(String)).size===a.length&&same(a.map(String).sort(),b.map(String).sort());
const epoch=value=>{const n=Date.parse(value)/1000;if(!Number.isFinite(n))throw Error('媒体episode观察或请求时间不完整');return n;};
const schemaOf=m=>typeof m?.schema_content==='string'?JSON.parse(m.schema_content):m?.schema_content;

export function mediaEpisodeAssetManifest(input){
 if(input.assets?.length!==35)throw Error('媒体episode须保留原35图片资产');
 const list=input.assets.map(a=>({sha256:a.sha256,url:input.urls[a.sha256],width:a.width,height:a.height}));
 for(const item of list){const u=new URL(item.url);if(!/^[a-f0-9]{64}$/.test(item.sha256)||u.origin!==regional||u.username||u.password||u.port||u.search||u.hash||!u.pathname.startsWith('/u/')||item.width!==1600||item.height!==1600)throw Error('媒体episode图片不是原1600像素区域对象');}
 if(new Set(list.map(a=>a.sha256)).size!==35||new Set(list.map(a=>a.url)).size!==35)throw Error('原35图片资产不唯一');return list;
}

function authorize(input,record,a,now){
 const publishId=String(record.publishId),expected=assertPublicationInput(input),main=record.mainImageRepair,old=record.mediaRecovery;
 if(!/^[1-9]\d*$/.test(publishId)||input.destination.countryCode!=='US'||record.fingerprint!==publicationFingerprint(expected)||
    String(record.identity?.publishId)!==publishId||String(record.sourceLink?.publishId)!==publishId||String(record.sourceLink?.draftId)!==String(input.destination.draftId)||
    !record.sourceEvidence||publicationFailureObservation({code:0,data:record.sourceEvidence},input,publishId)!==null)throw Error('媒体episode原美国受理身份不完整');
 if(!a||!/^[a-f0-9]{32}$/.test(a.id||'')||a.scope!=='retry_original_new_media_failure_episode'||a.marketplace!=='US'||a.nativeScope!=='original_parent_family'||a.variantCount!==30||a.assetCount!==35||a.saveProductData!==false||a.replaceImages!==false||a.requiresVerifiedOriginalMain!==true||!Number.isFinite(a.authorizedAt)||a.authorizedAt<=0||!/^[a-f0-9]{64}$/.test(a.failureResponseFingerprint||''))throw Error('缺少冻结的独立媒体episode授权');
 for(const [k,v]of Object.entries({accountId:input.accountId,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,publishId,
  destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),erpAccountId:String(input.destination.erpAccountId),marketId:String(input.destination.marketId),countryCode:'US',store:input.store,parentSku:input.goods.parentSku}))if(v===undefined||a[k]===undefined||String(v)!==String(a[k]))throw Error('媒体episode原身份不符：'+k);
 if(!same(a.assetManifest,mediaEpisodeAssetManifest(input))||input.goodsItems.length!==30)throw Error('媒体episode原图片或SKU范围不符');
 if(main?.saveVerified!==true||main.persistedSchemaValidation?.passed!==true||main.persistedSchemaValidation.checkedCount!==31||String(old?.intent?.publishId)!==publishId||String(main.retry?.intent?.publishId)!==publishId||main.retry.requestAccepted!==true)throw Error('原MAIN保存及旧恢复消耗证据不完整');
 const prior=[old,main.retry].map(j=>{const r=j.nativeRequests?.[0];if(j.nativeRequests?.length!==1||r.method!=='POST'||r.url!==endpoint||!same(r?.payload,{ids:[Number(publishId)]})||r.response?.httpStatus!==200||r.response.body?.code!==0)throw Error('原重试回执未知，不建立另一episode');return epoch(r.sentAt);});
 if([old.amendment?.failureResponseFingerprint,main.amendment?.failureResponseFingerprint].includes(a.failureResponseFingerprint))throw Error('此失败指纹已有旧恢复授权');
 if(a.cooldownSeconds!==1200||Math.abs(a.cooldownNotBefore-(Math.max(epoch(a.failureObservedAt),...prior)+1200))>.001||now<a.cooldownNotBefore)throw Error('媒体episode未满足首次同失败与原真实重试后的20分钟冷却');
 if(record.mediaEpisodes!==undefined&&(!Array.isArray(record.mediaEpisodes)||record.mediaEpisodes.length>1||record.mediaEpisodes.length===1&&record.mediaEpisodes[0].amendmentId!==a.id))throw Error('原任务已有独立媒体episode，不覆盖或新增');
 return publishId;
}

function failurePlan(input,record,observation,a){
 if(!observation||observation.identityVerified!==true||observation.status!=='failed'||observation.count!==2||observation.childCount!==30||observation.acceptedCount!==28||observation.messageCount!==2||observation.unscopedMessageCount!==0||observation.responseFingerprint!==a.failureResponseFingerprint||!equalIds(observation.failedChildIds,a.failedChildIds)||!equalIds(observation.skus,a.failedSkus)||!same(observation.messages.map(m=>m.code).sort(),['18320','20000']))throw Error('最新原任务不是授权的2失败/28受理媒体episode');
 if(observation.children.some(c=>!['accepted','failed'].includes(c.status)||c.imagesSource!=='child_gallery'||c.images.length!==7||new Set(c.images).size!==7||(c.status==='failed')!==Boolean(c.messages.length)))throw Error('原30子体独立七图或状态未完整核对');
 const planned=observation.messages.map(message=>{
  const child=observation.children.find(c=>c.childId===message.childId&&c.sku===message.sku&&c.status==='failed');
  if(!child||!same(child.messages,[message]))throw Error('媒体episode消息归属不完整');
  let originalUrl,reportedUrl,slot;
  if(message.code==='18320'){
   const original=record.mainImageRepair.amendment;
   if(child.childId!==original.failedChildId||child.sku!==original.failedSku||child.main!==original.mainImageUrl)throw Error('18320不是已保存的原MAIN子体');
   originalUrl=reportedUrl=child.main;slot=0;
  }else{
   const urls=[...message.message.matchAll(/https?:\/\/[^\s"'<>]+/g)].map(m=>m[0]);if(urls.length!==1)throw Error('20000下载超时没有唯一原URL');
   reportedUrl=urls[0];const u=new URL(reportedUrl);
   if(![regional,accelerated].includes(u.origin)||u.username||u.password||u.port||u.search||u.hash)throw Error('20000媒体不是原区域或加速对象');
   const matches=child.images.map((url,i)=>({url,i})).filter(v=>new URL(v.url).pathname===u.pathname);if(matches.length!==1)throw Error('失败媒体无法唯一映射原SKU');
   originalUrl=matches[0].url;slot=matches[0].i;
  }
  const asset=input.assets.find(v=>input.urls[v.sha256]===originalUrl);if(!asset)throw Error('失败媒体不属于原文件');
  return {childId:child.childId,sku:child.sku,code:message.code,slot,originalUrl,reportedUrl,assetSha256:asset.sha256};
 });
 if(!same(planned,a.failedMedia))throw Error('媒体episode失败对象与冻结授权不一致');return planned;
}

function verifiedMainAndSchema(observed,input,record,frozen,validate){
 if(!frozen||observed.meta?.hash!==input.destination.schemaHash||observed.meta.hash!==frozen.hash||observed.meta.country_code!=='US'||observed.meta.locale!=='en_US'||!same(schemaOf(observed.meta),schemaOf(frozen)))throw Error('媒体episode原类目schema已变化');
 const source=observed.response?.data,original=record.mainImageRepair.amendment;
 const child=source?.items?.find(c=>String(c.id)===original.failedChildId&&c.sku===original.failedSku);
 const locator=[{marketplace_id:input.destination.marketplaceId,media_location:original.mainImageUrl}];
 if(!child||child.main_image!==original.mainImageUrl||!same(child.extra?.attributes?.main_product_image_locator,locator))throw Error('原gray MAIN字段不正确，禁止用重试替代字段修复');
 return validate(observed.meta,[{id:'parent',attributes:source.extra.attributes},...source.items.map(c=>({id:c.sku,attributes:c.extra.attributes}))],input);
}

export async function verifyMediaEpisodeLocalAssets(input){
 const proofs=[];
 for(const asset of input.assets){const data=await fs.readFile(asset.path),sha256=createHash('sha256').update(data).digest('hex'),dim=imageDimensions(data);
  if(sha256!==asset.sha256||dim.format!=='png'||dim.width!==1600||dim.height!==1600)throw Error('原35本地图片SHA或PNG尺寸不符');proofs.push({sha256,bytes:data.length,...dim});}
 return {passed:true,count:proofs.length,objects:proofs};
}

export async function decodeMediaEpisodeUrls(page,urls){
 return page.evaluate(async urls=>Promise.all(urls.map(async url=>{
  const image=new Image();image.src=url;
  let timer;try{await Promise.race([image.decode(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('原图片解码超时')),20000);})]);}
  finally{clearTimeout(timer);}
  if(image.naturalWidth!==1600||image.naturalHeight!==1600)throw Error('原图片浏览器解码尺寸不符');
  return {url,decoded:true,width:image.naturalWidth,height:image.naturalHeight};
 })),urls);
}

export async function retryNativeMediaEpisode(page,input,record,persist,{amendment,schemaObservation,observeOnly=false,...adapters}={}){
 const api={read:readNativePublication,observe:readMainImageRepairSource,remote:verifyRemoteAsset,local:verifyMediaEpisodeLocalAssets,
  decode:decodeMediaEpisodeUrls,validate:validateSchemaAttributes,submit:submitNativeMediaRecovery,now:()=>Date.now()/1000,...adapters};
 const publishId=authorize(input,record,amendment,api.now());
 record.mediaEpisodes??=[];
 let journal=record.mediaEpisodes[0];
 if(!journal){if(record.phase!=='publication_failed'||(record.latestObservation||record.failureObservation)?.responseFingerprint!==amendment.failureResponseFingerprint)throw Error('原持久失败观察不属于此episode');journal={amendmentId:amendment.id,amendment:structuredClone(amendment),publishId,scope:'original_parent_family',variantCount:30,
  createdAt:new Date().toISOString(),originalFailureObservation:structuredClone(record.latestObservation||record.failureObservation),
  originalAcceptedIdentity:structuredClone(record.identity),originalSourceLink:structuredClone(record.sourceLink),requestAccepted:false};record.mediaEpisodes.push(journal);await persist();}
 if(!same(journal.amendment,amendment))throw Error('已有媒体episode授权不能替换');
 const consume=async(response,pending)=>{let observation;try{observation=publicationFailureObservation(response,input,publishId);}catch(error){if(error.code!=='ERP_PUBLICATION_PENDING')throw error;pending=error;}
  journal.lastObservation=observation||{publishId,status:pending?.status||response.data.status,failed:false,verification:pending?'pending':'accepted',observedAt:new Date().toISOString()};
  if(!journal.intent){journal.consumedWithoutWrite=true;journal.phase='source_no_longer_failed';}journal.lastReadAt=new Date().toISOString();await persist();return journal;};
 if(observeOnly||journal.intent||journal.consumedWithoutWrite)return consume(await api.read(page,publishId));
 journal.phase='preflight';await persist();
 try{
  const observed=await api.observe(page,input,publishId);let failure;
  try{failure=publicationFailureObservation(observed.response,input,publishId);}catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return consume(observed.response,error);throw error;}
  if(!failure)return consume(observed.response);
  const plan=failurePlan(input,record,failure,amendment);
  journal.preflight={startedAt:new Date().toISOString(),schemaValidation:verifiedMainAndSchema(observed,input,record,schemaObservation,api.validate),
   localAssets:await api.local(input),remoteObjects:[]};
  if(journal.preflight.localAssets?.passed!==true||journal.preflight.localAssets.count!==35||journal.preflight.schemaValidation?.passed!==true||journal.preflight.schemaValidation.checkedCount!==31)throw Error('原35图片或31组属性未完整通过');
  const urls=[...new Set(plan.flatMap(v=>[v.originalUrl,accelerated+new URL(v.originalUrl).pathname]))];
  const proofs=await Promise.all(urls.map(async url=>{const asset=input.assets.find(v=>new URL(input.urls[v.sha256]).pathname===new URL(url).pathname),remote=await api.remote(url,asset);
   if(remote?.sha256!==asset.sha256||!(remote.bytes>0))throw Error('原双域媒体SHA256不符');return {url,sha256:asset.sha256,remote};}));
  journal.preflight.remoteObjects=proofs;journal.preflight.browserDecode=await api.decode(page,urls);
  if(journal.preflight.browserDecode?.length!==4||journal.preflight.browserDecode.some(v=>v.decoded!==true||v.width!==1600||v.height!==1600)||!equalIds(journal.preflight.browserDecode.map(v=>v.url),urls))throw Error('原双域四个URL未全部解码核对');
  const latest=await api.observe(page,input,publishId);let current;
  try{current=publicationFailureObservation(latest.response,input,publishId);}catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return consume(latest.response,error);throw error;}
  if(!current)return consume(latest.response);failurePlan(input,record,current,amendment);
  verifiedMainAndSchema(latest,input,record,schemaObservation,api.validate);
  if(!same(mainImageBusinessProjection(observed.response.data),mainImageBusinessProjection(latest.response.data)))throw Error('复核期间原商品资料发生变化，未重试');
  journal.preflight.passed=true;journal.preflight.completedAt=new Date().toISOString();await persist();
 }catch(error){journal.phase='preflight_failed';journal.lastError=String(error.message||error);await persist();throw error;}
 if(api.now()<amendment.cooldownNotBefore)throw Error('媒体episode冷却未结束');
 journal.intent={publishId,amendmentId:amendment.id,scope:'original_parent_family',variantCount:30,responseFingerprint:amendment.failureResponseFingerprint,armedAt:new Date().toISOString()};
 journal.phase='retry_unknown';await persist();
 // This transparent wrapper points at the NEW journal only. Old mediaRecovery
 // remains untouched while the existing exact-parent native submitter is reused.
 const nativeRecord={publishId,mediaRecovery:journal};
 try{await api.submit(page,input,nativeRecord,persist);}catch(error){journal.lastSubmitError=String(error.message||error);await persist();throw error;}
 const request=journal.nativeRequests?.[0];
 if(journal.nativeRequests?.length!==1||request.method!=='POST'||request.url!==endpoint||!same(request.payload,{ids:[Number(publishId)]})||request.response?.httpStatus!==200||request.response.body?.code!==0){journal.lastSubmitError='原父任务重试回执未知，只读对账';await persist();throw Error(journal.lastSubmitError);}
 journal.requestAccepted=true;journal.phase='request_accepted';journal.requestAcceptedAt=new Date().toISOString();await persist();return journal;
}
