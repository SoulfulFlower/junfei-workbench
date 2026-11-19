// Independent original-UK media retry. No product Save, upload, URL or ID edits.
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,readNativePublication,verifyPublication} from './ego-publish-native.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';
import {readMainImageRepairSource,mainImageBusinessProjection} from './ego-publication-main-image.mjs';
import {verifyMediaEpisodeLocalAssets,decodeMediaEpisodeUrls} from './ego-publication-media-episode.mjs';
import {submitNativeMediaRecovery} from './ego-publication-recovery.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';

const regional='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com',accelerated='https://junfeikuajing.oss-accelerate.aliyuncs.com';
const endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish';
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const epoch=value=>{const n=Date.parse(value)/1000;if(!Number.isFinite(n))throw Error('英国原媒体恢复时间无效');return n;};
const schemaOf=v=>typeof v?.schema_content==='string'?JSON.parse(v.schema_content):v?.schema_content;

export function ukMediaManifest(input){
 const result=(input.assets||[]).map(a=>({sha256:a.sha256,url:input.urls?.[a.sha256],width:a.width,height:a.height}));
 if(result.length!==105||new Set(result.map(a=>a.url)).size!==new Set(result.map(a=>a.sha256)).size)throw Error('英国媒体恢复缺少原105图位或同URL对应不同内容');
 for(const a of result){const u=new URL(a.url);if(!/^[a-f0-9]{64}$/.test(a.sha256)||u.origin!==regional||u.username||u.password||u.port||u.search||u.hash||!u.pathname.startsWith('/u/')||a.width!==1600||a.height!==1600)throw Error('英国原图片身份或尺寸不符');}
 return result;
}

function authorize(input,record,a,schema,now){
 const expected=assertPublicationInput(input),publishId=String(record.publishId),old=record.identifierRepair,retry=old?.retry,request=retry?.nativeRequests?.[0];
 if(input.marketplace!=='UK'||input.destination.countryCode!=='GB'||input.goodsItems.length!==75||record.fingerprint!==publicationFingerprint(expected)||String(record.identity?.publishId)!==publishId||String(record.sourceLink?.publishId)!==publishId||String(record.sourceLink?.draftId)!==String(input.destination.draftId))throw Error('英国原媒体任务受理身份不完整');
 if(!a||!/^[a-f0-9]{32}$/.test(a.id||'')||a.scope!=='retry_original_uk_failed_media_once'||a.marketplace!=='UK'||a.nativeScope!=='original_parent_family'||a.variantCount!==75||a.assetCount!==105||a.saveProductData!==false||a.replaceImages!==false||!/^[a-f0-9]{64}$/.test(a.failureResponseFingerprint||''))throw Error('缺少原英国唯一媒体恢复授权');
 for(const [k,v]of Object.entries({accountId:input.accountId,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,publishId,destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),erpAccountId:String(input.destination.erpAccountId),marketId:String(input.destination.marketId),countryCode:'GB',store:input.store,parentSku:input.goods.parentSku,schemaHash:input.destination.schemaHash}))if(v===undefined||a[k]===undefined||String(a[k])!==String(v))throw Error('英国媒体恢复身份不符 '+k);
 if(schema?.product_type_name!=='SWEATSHIRT'||schema.country_code!=='GB'||schema.locale!=='en_GB'||schema.hash!==a.schemaHash||!same(a.assetManifest,ukMediaManifest(input)))throw Error('英国原商品类型或资产变化');
 if(old?.saveVerified!==true||!same(old.plannedSource,a.preservedSource)||retry?.requestAccepted!==true||retry.nativeRequests?.length!==1||request.method!=='POST'||request.url!==endpoint||!same(request.payload,{ids:[Number(publishId)]})||request.response?.httpStatus!==200||request.response.body?.code!==0)throw Error('原英国旧修复或重试回执未知，不建立另一恢复');
 if(a.cooldownSeconds!==1200||Math.abs(a.cooldownNotBefore-(Math.max(epoch(a.failureObservedAt),epoch(request.sentAt))+1200))>.001||!Number.isFinite(a.authorizedAt)||a.authorizedAt<a.cooldownNotBefore||now<a.cooldownNotBefore)throw Error('原英国媒体恢复尚未满足已冻结冷却');
 if(record.mediaRecovery&&(record.mediaRecovery.amendmentId!==a.id||!same(record.mediaRecovery.amendment,a)))throw Error('原英国已有不同媒体恢复检查点');
 if(a.originalFailureObservation?.responseFingerprint!==a.failureResponseFingerprint)throw Error('英国冻结失败观察指纹不完整');
 ukMediaFailurePlan(input,a.originalFailureObservation,a);
 return publishId;
}

export function ukMediaFailurePlan(input,observation,a){
 if(!observation||observation.identityVerified!==true||observation.failed!==true||observation.status!=='failed'||observation.count!==1||observation.acceptedCount!==74||observation.childCount!==75||observation.unscopedMessageCount!==0||!same(observation.failedChildIds,a.failedChildIds)||!same(observation.skus,a.failedSkus))throw Error('英国最新失败不是原1失败74受理范围');
 if(observation.children.some(c=>c.imagesSource!=='child_gallery'||c.images.length!==7||new Set(c.images).size!==7||!['accepted','failed'].includes(c.status)||(c.status==='failed')!==Boolean(c.messages.length)))throw Error('英国75子体独立七图未全部核对');
 const child=observation.children.find(c=>c.childId===a.failedChildIds[0]&&c.sku===a.failedSkus[0]&&c.status==='failed');
 if(!child||!same(child.messages,observation.messages))throw Error('英国失败消息归属不完整');
 const errors=observation.messages.filter(m=>m.code==='300060'&&m.severity==='ERROR');
 const warnings=observation.messages.filter(m=>m.code==='18448'&&m.severity==='WARNING'&&/(^|[^a-z_])material([^a-z_]|$)/i.test(m.message)&&m.message.includes('不会阻止'));
 if(errors.length!==6||warnings.length>1||errors.length+warnings.length!==observation.messages.length||warnings.some(m=>!a.nonBlockingWarnings.some(w=>same(w,m))))throw Error('英国仅允许原六个媒体错误及原明确非阻断材质提醒');
 const plan=errors.map(m=>{
  const urls=[...m.message.matchAll(/https?:\/\/[^\s"'<>]+/g)].map(v=>v[0]);if(urls.length!==1||m.childId!==child.childId||m.sku!==child.sku)throw Error('英国错误缺少原SKU唯一媒体URL');
  const u=new URL(urls[0]);if(![regional,accelerated].includes(u.origin)||u.username||u.password||u.port||u.search||u.hash)throw Error('英国失败媒体来源不符');
  const matches=child.images.map((url,slot)=>({url,slot})).filter(v=>new URL(v.url).pathname===u.pathname);if(matches.length!==1)throw Error('英国错误图片不能唯一对应原七图');
  const {url,slot}=matches[0],asset=input.assets.find(v=>input.urls[v.sha256]===url);if(!asset)throw Error('英国错误媒体不属于原资产');
  return{childId:child.childId,sku:child.sku,code:'300060',slot,originalUrl:url,reportedUrl:urls[0],assetSha256:asset.sha256};
 }).sort((a,b)=>a.slot-b.slot);
 if(new Set(plan.map(v=>v.slot)).size!==6||!same(plan,a.failedMedia))throw Error('英国六图片对象与冻结范围不同');return plan;
}

function sourceProof(observed,input,a,frozen,validate){
 const meta=observed.meta,source=observed.response.data;
 if(meta?.hash!==a.schemaHash||meta.hash!==frozen.hash||meta.country_code!=='GB'||meta.locale!=='en_GB'||meta.product_type_name!=='SWEATSHIRT'||!same(schemaOf(meta),schemaOf(frozen)))throw Error('原英国实际schema已变化');
 if(!same(mainImageBusinessProjection(source),mainImageBusinessProjection(a.preservedSource)))throw Error('原英国SKU、价格、编码、属性或图片发生变化');
 return validate(meta,[{id:'parent',attributes:source.extra.attributes},...source.items.map(c=>({id:c.sku,attributes:c.extra.attributes}))],{...input,runtime:a.runtime});
}

export async function retryNativeUkMedia(page,input,record,persist,{amendment,schemaObservation,observeOnly=false,...adapters}={}){
 const api={read:readNativePublication,observe:readMainImageRepairSource,remote:verifyRemoteAsset,local:verifyMediaEpisodeLocalAssets,decode:decodeMediaEpisodeUrls,validate:validateSchemaAttributes,submit:submitNativeMediaRecovery,now:()=>Date.now()/1000,...adapters};
 const publishId=authorize(input,record,amendment,schemaObservation,api.now());
 let j=record.mediaRecovery;
 if(!j){if(record.phase!=='publication_failed'||(record.latestObservation||record.failureObservation)?.responseFingerprint!==amendment.failureResponseFingerprint)throw Error('原英国持久失败观察不属于此授权');ukMediaFailurePlan(input,record.latestObservation||record.failureObservation,amendment);
  j=record.mediaRecovery={amendmentId:amendment.id,amendment:structuredClone(amendment),publishId,scope:'original_parent_family',variantCount:75,originalAcceptedIdentity:structuredClone(record.identity),originalAcceptedSourceEvidence:structuredClone(record.sourceEvidence),originalSourceLink:structuredClone(record.sourceLink),originalFailureObservation:structuredClone(record.latestObservation||record.failureObservation),requestAccepted:false,createdAt:new Date().toISOString()};await persist();}
 const consume=async response=>{
  let observation;
  try{
   const identity=verifyPublication(response,input,publishId,{allowOnline:true});
   observation={publishId,status:identity.status,verification:'accepted',failed:false,...(identity.warnings?{warnings:identity.warnings}:{})};
  }catch(error){
   if(error.code==='ERP_PUBLICATION_FAILED')observation=structuredClone(error.failureObservation);
   else if(error.code==='ERP_PUBLICATION_PENDING')observation={publishId,status:error.status,verification:'pending',failed:false};
   else throw error;
  }
  j.lastObservation=observation;j.lastReadAt=new Date().toISOString();if(!j.intent){j.consumedWithoutWrite=true;j.phase='source_no_longer_failed';}
  await persist();return j;
 };
 if(observeOnly||j.intent||j.consumedWithoutWrite)return consume(await api.read(page,publishId));
 j.phase='preflight';await persist();
 try{
  const observed=await api.observe(page,input,publishId);let failure;
  try{failure=publicationFailureObservation(observed.response,input,publishId);}catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return consume(observed.response);throw error;}
  if(!failure||failure.messages.every(m=>amendment.nonBlockingWarnings.some(w=>same(w,m))))return consume(observed.response);
  const plan=ukMediaFailurePlan(input,failure,amendment),schemaValidation=sourceProof(observed,input,amendment,schemaObservation,api.validate);
  j.preflight={startedAt:new Date().toISOString(),schemaValidation,localAssets:await api.local(input),remoteObjects:[]};
  if(schemaValidation?.passed!==true||schemaValidation.checkedCount!==76||j.preflight.localAssets?.passed!==true||j.preflight.localAssets.count!==105)throw Error('英国原76属性组或105文件未全部通过');
  const urls=[...new Set(plan.flatMap(v=>[v.originalUrl,v.reportedUrl]))];
  for(let offset=0;offset<urls.length;offset+=3){const batch=urls.slice(offset,offset+3),results=await Promise.allSettled(batch.map(async url=>{const asset=input.assets.find(v=>new URL(input.urls[v.sha256]).pathname===new URL(url).pathname),remote=await api.remote(url,asset);if(remote.sha256!==asset.sha256||!(remote.bytes>0))throw Error('英国原图片完整SHA不符');return{url,sha256:asset.sha256,remote};}));let failed;
   for(let i=0;i<results.length;i++){const r=results[i];if(r.status==='fulfilled')j.preflight.remoteObjects.push(r.value);else{j.preflight.remoteObjects.push({url:batch[i],error:String(r.reason?.message||r.reason)});failed??=r.reason;}}await persist();if(failed)throw failed;}
  j.preflight.browserDecode=await api.decode(page,urls);
  if(j.preflight.browserDecode?.length!==urls.length||j.preflight.browserDecode.some(v=>v.decoded!==true||v.width!==1600||v.height!==1600)||!same(j.preflight.browserDecode.map(v=>v.url).sort(),[...urls].sort()))throw Error('英国原媒体未全部正常解码');
  const latest=await api.observe(page,input,publishId);let current;try{current=publicationFailureObservation(latest.response,input,publishId);}catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return consume(latest.response);throw error;}
  if(!current||current.messages.every(m=>amendment.nonBlockingWarnings.some(w=>same(w,m))))return consume(latest.response);ukMediaFailurePlan(input,current,amendment);sourceProof(latest,input,amendment,schemaObservation,api.validate);
  j.preflight.passed=true;j.preflight.completedAt=new Date().toISOString();await persist();
 }catch(error){j.phase='preflight_failed';j.lastError=String(error.message||error);await persist();throw error;}
 const armIntent=async()=>{if(api.now()<amendment.cooldownNotBefore)throw Error('英国媒体恢复冷却未结束');j.intent={publishId,amendmentId:amendment.id,scope:'original_parent_family',variantCount:75,responseFingerprint:amendment.failureResponseFingerprint,armedAt:new Date().toISOString()};j.phase='retry_unknown';await persist();};
 try{await api.submit(page,input,{publishId,mediaRecovery:j},persist,{armIntent});}catch(error){j.lastSubmitError=String(error.message||error);await persist();throw error;}
 const request=j.nativeRequests?.[0];if(!j.intent||j.nativeRequests?.length!==1||request.method!=='POST'||request.url!==endpoint||!same(request.payload,{ids:[Number(publishId)]})||request.response?.httpStatus!==200||request.response.body?.code!==0){j.lastSubmitError='原英国任务重试回执未知，只读对账';await persist();throw Error(j.lastSubmitError);}
 j.requestAccepted=true;j.phase='request_accepted';j.requestAcceptedAt=new Date().toISOString();await persist();return j;
}
