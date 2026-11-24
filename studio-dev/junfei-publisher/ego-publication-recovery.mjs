// Explicit recovery of one existing failed US family. No draft, SKU, image or
// product content is created or edited. Native re-publish processes the family;
// the failed-child list is diagnostic evidence, not a child-only retry scope.
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,readNativePublication,queryPublicationRows,isUsApparelAdvisory} from './ego-publish-native.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';

const endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish';
const regional='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com';
const accelerated='https://junfeikuajing.oss-accelerate.aliyuncs.com';
const idsEqual=(a,b)=>Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&new Set(a.map(String)).size===a.length&&
 JSON.stringify(a.map(String).sort())===JSON.stringify(b.map(String).sort());

function assertAuthorization(input,record,amendment){
 const expected=assertPublicationInput(input),publishId=String(record.publishId);
 if(input.destination.countryCode!=='US'||!/^\d+$/.test(publishId)||!Number.isSafeInteger(Number(publishId))||Number(publishId)<1||
    record.fingerprint!==publicationFingerprint(expected)||String(record.identity?.publishId)!==publishId||
    String(record.sourceLink?.publishId)!==publishId||String(record.sourceLink?.draftId)!==String(input.destination.draftId))throw Error('恢复缺少原美国已受理任务关联，不能创建或替代刊登');
 if(!amendment||typeof amendment.id!=='string'||!amendment.id||amendment.scope!=='retry_original_failed_media'||amendment.marketplace!=='US'||
    String(amendment.publishId)!==publishId||amendment.snapshotSha256!==input.sha256||!/^[a-f0-9]{64}$/.test(amendment.failureResponseFingerprint||'')||
    !Array.isArray(amendment.failedChildIds)||!amendment.failedChildIds.length||new Set(amendment.failedChildIds.map(String)).size!==amendment.failedChildIds.length||
    !(typeof amendment.authorizedAt==='number'&&Number.isFinite(amendment.authorizedAt)&&amendment.authorizedAt>0))throw Error('缺少服务端冻结的原媒体失败恢复授权');
 for(const [key,value]of Object.entries({accountId:input.accountId,productId:input.productId,jobId:input.jobId,
  destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),erpAccountId:String(input.destination.erpAccountId),
  marketId:String(input.destination.marketId),countryCode:'US',store:input.store,parentSku:input.goods.parentSku})){
  if(amendment[key]===undefined||value===undefined||String(amendment[key])!==String(value))throw Error('恢复授权原账号、产品或任务身份不符：'+key);
 }
 if(!record.sourceEvidence||publicationFailureObservation({code:0,data:record.sourceEvidence},input,publishId)!==null)throw Error('恢复缺少与原冻结输入一致的历史受理证明');
 if(record.mediaRecovery&&record.mediaRecovery.amendmentId!==amendment.id)throw Error('已有原恢复检查点，不覆盖或再次提交');
 return publishId;
}

function assertMediaFailure(observation,amendment){
 if(!observation||observation.status!=='failed'||!observation.identityVerified||observation.unscopedMessageCount||!observation.count||
    observation.responseFingerprint!==amendment.failureResponseFingerprint||!idsEqual(observation.failedChildIds,amendment.failedChildIds)||
    observation.children.some(row=>row.imagesSource!=='child_gallery'||row.images.length!==7||new Set(row.images).size!==7)||observation.messages.some(message=>!['300060','18320'].includes(message.code)&&!isUsApparelAdvisory(message,message.sku))||
    !observation.messages.some(message=>['300060','18320'].includes(message.code)))throw Error('原任务状态、失败范围、图片或错误类型不支持此次媒体恢复');
 if(observation.children.some(row=>!['accepted','failed'].includes(row.status)||
    (row.status==='failed'&&!row.messages.some(message=>['300060','18320'].includes(message.code)))||
    (row.status==='accepted'&&row.messages.some(message=>!isUsApparelAdvisory(message,row.sku)))))throw Error('原子SKU失败状态或错误范围尚未完整核实');
 if(amendment.failedSkus&&!idsEqual(amendment.failedSkus,observation.skus))throw Error('恢复授权失败SKU与原任务不符');
}

function mediaPlan(input,observation){
 const assetsByUrl=new Map(),plans=new Map();
 for(const asset of input.assets){
  const url=input.urls[asset.sha256];
  if(assetsByUrl.has(url)&&assetsByUrl.get(url).sha256!==asset.sha256)throw Error('冻结图片URL不能唯一对应原文件');
  assetsByUrl.set(url,asset);
 }
 const add=(url,originalUrl,reason)=>{
  const asset=assetsByUrl.get(originalUrl),u=new URL(originalUrl);
  if(!asset||!/^[a-f0-9]{64}$/.test(asset.sha256)||u.origin!==regional||u.username||u.password||u.search||u.hash||!u.pathname.startsWith('/u/'))throw Error('恢复图片不属于已冻结的原区域对象');
  if(!plans.has(url))plans.set(url,{url,originalUrl,sha256:asset.sha256,reasons:[],asset});
  if(!plans.get(url).reasons.includes(reason))plans.get(url).reasons.push(reason);
 };
 for(const child of observation.children.filter(row=>row.status==='failed')){
  for(const message of child.messages){
   if(isUsApparelAdvisory(message,child.sku))continue;
   if(message.code==='18320'){add(child.main,child.main,'failed_main_image');continue;}
   for(const url of child.images)add(url,url,'failed_gallery');
   const reported=[...message.message.matchAll(/https?:\/\/[^\s"'<>]+/g)].map(match=>match[0]);
   if(!reported.length)throw Error('媒体访问错误没有可核对的实际URL');
   for(const url of reported){
    const actual=new URL(url);
    if(actual.href!==url||actual.protocol!=='https:'||actual.username||actual.password||actual.port||actual.search||actual.hash||![regional,accelerated].includes(actual.origin))throw Error('媒体错误URL不属于已观察到的原对象或加速域名');
    const original=child.images.filter(value=>new URL(value).pathname===actual.pathname);
    if(original.length!==1)throw Error('媒体错误URL无法唯一对应此失败SKU的原图');
    add(url,original[0],'reported_media_url');
   }
  }
 }
 return [...plans.values()];
}

// Self-contained browser hook; tests run this exact source in a fake XHR VM.
export function installNativeMediaRecoveryGuard({publishId}){
 if(window.__nativeMediaRecoveryWrite)throw Error('已有原媒体恢复请求观察');
 const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();
 const state={open,send,publishId:String(publishId),requests:[],error:null};window.__nativeMediaRecoveryWrite=state;
 const hookedOpen=function(method,url,...rest){targets.set(this,{method:String(method).toUpperCase(),url:new URL(url,location.href)});return open.call(this,method,url,...rest);};
 const hookedSend=function(body){
  const request=targets.get(this);if(!request||['GET','HEAD'].includes(request.method))return send.call(this,body);
  try{
   if(state.error||request.method!=='POST'||request.url.href!=='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish'||state.requests.length)throw Error('拦截非原任务、非原生入口或重复恢复请求');
   const payload=JSON.parse(body);
   if(!payload||Object.keys(payload).length!==1||!Object.hasOwn(payload,'ids')||!Array.isArray(payload.ids)||payload.ids.length!==1||
      !Number.isSafeInteger(payload.ids[0])||payload.ids[0]!==Number(publishId))throw Error('恢复请求只能包含原父任务ID');
   const record={method:request.method,url:request.url.href,path:request.url.pathname,payload,sentAt:new Date().toISOString(),response:null};state.requests.push(record);
   this.addEventListener('loadend',()=>{let value;try{value=JSON.parse(this.responseText);}catch{}record.response={httpStatus:this.status,body:value};},{once:true});
   return send.call(this,body);
  }catch(error){state.error=error.message;throw error;}
 };
 state.hookedOpen=hookedOpen;state.hookedSend=hookedSend;XMLHttpRequest.prototype.open=hookedOpen;XMLHttpRequest.prototype.send=hookedSend;
 return{installed:true,publishId:state.publishId};
}

export async function submitNativeMediaRecovery(page,input,record,persist,{query=queryPublicationRows,armIntent}={}){
 const recovery=record.mediaRecovery,publishId=String(record.publishId);
 if(!recovery||recovery.nativeRequests?.length||(armIntent!==undefined&&typeof armIntent!=='function')||
    (armIntent?Boolean(recovery.intent):!recovery.intent||recovery.intent.publishId!==publishId))throw Error('缺少已持久恢复意图或已有原请求，不再次点击');
 if(!['US','GB'].includes(input.destination?.countryCode)||!input.destination.marketId||!input.store)throw Error('原重试缺少已核对的店铺站点');
 const rows=await query(page,{sku:input.goods.parentSku}),matches=rows.filter(row=>String(row.id)===publishId&&row.sku===input.goods.parentSku&&
  String(row.market_id)===String(input.destination.marketId)&&row.country_code===input.destination.countryCode&&row.market?.alias===input.store&&row.status==='failed');
 if(matches.length!==1)throw Error('原失败任务行或店铺不唯一，未再次发布');
 const selector=await page.evaluate(({publishId,sku,store})=>{
  const rows=[...document.querySelectorAll('.el-table__body tr')].filter(row=>row.getBoundingClientRect().width&&row.cells[1]?.innerText.trim()===publishId&&row.cells[5]?.innerText.trim()===sku&&row.cells[4]?.innerText.trim()===store);
  if(rows.length!==1)throw Error('原失败刊登任务行不唯一');const buttons=[...rows[0].querySelectorAll('button')].filter(button=>button.innerText.trim()==='再次发布'&&!button.disabled);
  if(buttons.length!==1)throw Error('原任务没有唯一再次发布按钮');buttons[0].setAttribute('data-native-media-recovery','true');buttons[0].scrollIntoView({block:'center'});return '[data-native-media-recovery]';
 },{publishId,sku:input.goods.parentSku,store:input.store});
 await page.evaluate(installNativeMediaRecoveryGuard,{publishId});
 try{
  if(armIntent){
   const guarded=await page.evaluate(publishId=>{const s=window.__nativeMediaRecoveryWrite;return Boolean(s&&s.publishId===publishId&&XMLHttpRequest.prototype.open===s.hookedOpen&&XMLHttpRequest.prototype.send===s.hookedSend&&!s.error&&!s.requests.length);},publishId);
   if(!guarded)throw Error('原任务重试护栏未绑定，不建立提交意图');
   recovery.nativePreflightProof={publishId,countryCode:input.destination.countryCode,marketId:String(input.destination.marketId),store:input.store,uniqueNativeRow:true,uniqueNativeButton:true,guardBound:true,verifiedAt:new Date().toISOString()};
   await armIntent();
   if(!recovery.intent||recovery.intent.publishId!==publishId||recovery.nativeRequests?.length)throw Error('原任务重试提交意图未持久确认');
  }
  await page.click(selector);await page.waitForFunction(()=>window.__nativeMediaRecoveryWrite?.requests.some(value=>value.response)||window.__nativeMediaRecoveryWrite?.error,undefined,{timeout:25000});
 }
 finally{
  try{const observed=await page.evaluate(()=>({requests:window.__nativeMediaRecoveryWrite?.requests||[],error:window.__nativeMediaRecoveryWrite?.error}));recovery.nativeRequests=observed.requests;if(observed.error)recovery.guardError=observed.error;await persist();}
  finally{await page.evaluate(()=>{const state=window.__nativeMediaRecoveryWrite;if(state){if(XMLHttpRequest.prototype.open===state.hookedOpen)XMLHttpRequest.prototype.open=state.open;if(XMLHttpRequest.prototype.send===state.hookedSend)XMLHttpRequest.prototype.send=state.send;delete window.__nativeMediaRecoveryWrite;}});}
 }
}

export async function recoverNativeMediaPublication(page,input,record,persist,{amendment=input.publicationRecovery,...adapters}={}){
 const api={read:readNativePublication,query:queryPublicationRows,remote:verifyRemoteAsset,submit:submitNativeMediaRecovery,...adapters};
 const publishId=assertAuthorization(input,record,amendment);
 const journal=observation=>record.mediaRecovery??={amendmentId:amendment.id,amendment:structuredClone(amendment),publishId,
  scope:'original_failed_family',failedChildIds:[...observation.failedChildIds],failedSkus:[...observation.skus],failedCount:observation.count,
  acceptedChildIds:[...observation.acceptedChildIds],acceptedSkus:[...observation.acceptedSkus],acceptedCount:observation.acceptedCount,
  originalFailureObservation:structuredClone(observation),originalAcceptedIdentity:structuredClone(record.identity),
  originalAcceptedSourceEvidence:structuredClone(record.sourceEvidence),originalSourceLink:structuredClone(record.sourceLink),createdAt:new Date().toISOString(),requestAccepted:false};
 const readOnly=async(response,failure,pending)=>{
  const recovery=journal(record.failureObservation);
  recovery.lastObservation=failure||{publishId,status:pending?.status||response?.data?.status,observedAt:new Date().toISOString(),failed:false,verification:pending?'pending':'accepted'};
  recovery.lastReadAt=new Date().toISOString();if(!recovery.intent){recovery.phase='no_retry_needed';recovery.consumedWithoutWrite=true;}await persist();return recovery;
 };
 if(record.mediaRecovery?.intent||record.mediaRecovery?.consumedWithoutWrite||record.mediaRecovery?.phase==='no_retry_needed'){
  const response=await api.read(page,publishId);let failure;
  try{failure=publicationFailureObservation(response,input,publishId);}catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return readOnly(response,null,error);throw error;}
  return readOnly(response,failure);
 }
 if(record.phase!=='publication_failed'||record.failureObservation?.responseFingerprint!==amendment.failureResponseFingerprint||
    !idsEqual(record.failureObservation?.failedChildIds,amendment.failedChildIds))throw Error('缺少与授权匹配的原持久失败观察');
 const response=await api.read(page,publishId);let observation;
 try{observation=publicationFailureObservation(response,input,publishId);}catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return readOnly(response,null,error);throw error;}
 if(!observation)return readOnly(response,null);
 assertMediaFailure(observation,amendment);
 const plan=mediaPlan(input,observation),recovery=journal(observation);
 recovery.phase='media_preflight';recovery.preflight={startedAt:new Date().toISOString(),uniqueAssetCount:new Set(plan.map(value=>value.sha256)).size,urlCount:plan.length,objects:[]};await persist();
 try{
  for(let offset=0;offset<plan.length;offset+=4){
   const batch=plan.slice(offset,offset+4),results=await Promise.allSettled(batch.map(value=>api.remote(value.url,value.asset)));
   let failure;
   for(let i=0;i<batch.length;i++){
    const {asset,...planned}=batch[i],result=results[i];
    if(result.status==='rejected'){recovery.preflight.objects.push({...planned,error:String(result.reason?.message||result.reason)});failure??=result.reason;}
    else if(result.value?.sha256!==asset.sha256||!(result.value.bytes>0)){recovery.preflight.objects.push({...planned,error:'远端内容缺少原SHA256证明'});failure??=Error('远端图片内容未通过原SHA256核对');}
    else recovery.preflight.objects.push({...planned,remote:result.value});
   }
   await persist();if(failure)throw failure;
  }
  recovery.preflight.passed=true;recovery.preflight.completedAt=new Date().toISOString();await persist();
  const latest=await api.read(page,publishId),current=publicationFailureObservation(latest,input,publishId);
  if(!current)return readOnly(latest,null);assertMediaFailure(current,amendment);
 }catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return readOnly(null,null,error);recovery.phase='preflight_failed';recovery.lastError=String(error.message||error);await persist();throw error;}
 recovery.intent={publishId,scope:'original_failed_family',amendmentId:amendment.id,responseFingerprint:observation.responseFingerprint,armedAt:new Date().toISOString()};
 recovery.phase='retry_unknown';await persist();
 try{await api.submit(page,input,record,persist,{query:api.query});}
 catch(error){recovery.lastSubmitError=String(error.message||error);await persist();throw error;}
 const request=recovery.nativeRequests?.[0];
 if(recovery.nativeRequests?.length!==1||request.method!=='POST'||request.url!==endpoint||Object.keys(request.payload||{}).length!==1||
    request.payload?.ids?.length!==1||request.payload.ids[0]!==Number(publishId)||request.response?.httpStatus!==200||request.response.body?.code!==0){
  recovery.lastSubmitError='原生再次发布响应未确认，保留同一任务只读对账';await persist();throw Error(recovery.lastSubmitError);
 }
 recovery.requestAccepted=true;recovery.phase='request_accepted';recovery.requestAcceptedAt=new Date().toISOString();await persist();return recovery;
}

export const recoveryNative=recoverNativeMediaPublication;
