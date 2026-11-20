// EGO native publication. Only the normal ERP UI sends the observed publish
// request; every uncertain intent is reconciled rather than submitted again.
import {createHash} from 'node:crypto';
import {readPersistedDraft,verifyPersistedDraft} from './ego-draft-readback.mjs';
import {ensureExplicitDraftGalleries} from './ego-explicit-galleries.mjs';
import {queryDrafts} from './ego-collection-lookup.mjs';
import {setTimeout as waitForPublication} from 'node:timers/promises';

export const publicationFingerprint=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const id=value=>/^\d+$/.test(String(value))&&Number(value)>0;
const onlineStatuses=['buyable','discoverable','online','active'];
const fields=input=>({accountId:input.accountId,productId:input.productId,snapshotSha256:input.sha256,
 destinationId:input.destination?.destinationId,draftId:String(input.destination?.draftId),marketId:String(input.destination?.marketId),
 erpAccountId:String(input.destination?.erpAccountId),countryCode:input.destination?.countryCode,store:input.store,
 parentSku:input.goods?.parentSku,children:input.goodsItems?.map(v=>({sku:v.sku,color:v.color,size:v.size,imageIndices:v.imageIndices}))});

export function assertPublicationInput(input){
 const expected=fields(input);
 if(!expected.accountId||!expected.productId||!expected.snapshotSha256||!expected.destinationId||!id(expected.draftId)||!id(expected.marketId)||!id(expected.erpAccountId)||!expected.store||!['US','GB'].includes(expected.countryCode)||!expected.parentSku||!expected.children?.length)throw Error('发布缺少明确账号、店铺、草稿或快照身份');
 if(new Set(expected.children.map(v=>v.sku)).size!==expected.children.length||expected.children.some(v=>!v.sku||!v.color||!v.size))throw Error('发布子SKU或颜色尺码身份不完整');
 if(!input.urls||input.assets?.some(v=>!input.urls[v.sha256]))throw Error('发布缺少原图片回读URL，不重新上传');
 return expected;
}

export function normalizePublication(data,input){
 const response=structuredClone(data),d=response?.data;
 if(!d||String(d.uid)!==String(input.destination.erpAccountId))throw Error('ERP发布记录账号不符');
 const variation=input.destination.variationFields||{color:'color.0.value',size:'apparel_size.0.size'};
 const get=(object,path)=>path.split('.').reduce((v,k)=>v?.[k],object);
 for(const row of d.items||[]){
  if(String(row.uid)!==String(input.destination.erpAccountId))throw Error('ERP发布子体账号不符');
  row.variation??={};
  for(const path of Object.values(variation)){
   const actual=get(row.extra?.attributes,path);
   if(actual===undefined)throw Error('ERP发布子体缺少真实颜色尺码');
   if(row.variation[path]!==undefined&&row.variation[path]!==actual)throw Error('ERP发布子体颜色尺码冲突');
   row.variation[path]=actual;
  }
 }
 return response;
}

const materialAdvisoryText='您提交的内容缺少一些关键属性：material。 缺少这些属性不会阻止您的商品在亚马逊上展示。 然而，这会影响您的商品信息的整体质量。';
function isMaterialAdvisory(value,data,child){
 // Match the observed UK notice and its metadata. Unknown notice shapes
 // continue through the normal failure checks.
 return data.country_code==='GB'&&Boolean(child)&&value.code==='18448'&&value.severity==='WARNING'&&
  value.message===materialAdvisoryText&&Array.isArray(value.attributeNames)&&value.attributeNames.length===1&&
  value.attributeNames[0]==='material'&&Array.isArray(value.categories)&&value.categories.length===2&&
  value.categories.includes('MISSING_ATTRIBUTE')&&value.categories.includes('PRODUCT')&&
  !('enforcements' in value)&&
  (value.sku===undefined||value.sku===child.sku)&&(value.solution===undefined||value.solution==='')&&
  Object.keys(value).every(key=>['code','message','severity','attributeNames','categories','sku','solution'].includes(key));
}

function publicationMessages(data){
 const messages=[],seen=new Map(),advisories=new Set();
 const add=(value,source,row)=>{
  if(value==null||value==='')return;
  if(typeof value==='string'){
   let parsed;try{parsed=JSON.parse(value);}catch{}
   if(parsed!==undefined&&parsed!==value)return add(parsed,source,row);
   value={message:value};
  }
  if(Array.isArray(value)){for(const message of value)add(message,source,row);return;}
  if(!value||typeof value!=='object'||(!Object.hasOwn(value,'message')&&!Object.hasOwn(value,'code')))throw Error('ERP发布错误信息结构未完整回读');
  if(row&&value.sku&&value.sku!==row.sku)throw Error('ERP发布子体错误信息的SKU不符');
  const sku=row?.sku||value.sku||null,child=row||data.items.find(item=>item.sku===sku);
  const message={sku,childId:child?String(child.id):null,code:value.code==null?null:String(value.code),
   message:typeof value.message==='string'?value.message:String(value.message??''),severity:value.severity??null};
  for(const key of ['categories','enforcements','solution'])if(value[key]!==undefined)message[key]=structuredClone(value[key]);
  const key=JSON.stringify([message.sku,message.code,message.message,message.severity]),previous=seen.get(key);
  const advisory=isMaterialAdvisory(value,data,child);
  if(previous){
   if(!advisory)advisories.delete(previous);
   if(!previous.sources.includes(source))previous.sources.push(source);
   for(const [field,v]of Object.entries(message))if(previous[field]===undefined)previous[field]=v;
   return;
  }
  if(advisory)advisories.add(message);
  message.sources=[source];seen.set(key,message);messages.push(message);
 };
 if(!Array.isArray(data.errors))throw Error('ERP发布错误状态未完整回读');
 add(data.errors,'data.errors');
 for(const row of data.items){add(row.errors,'child.errors',row);add(row.extra?.message,'child.extra.message',row);}
 return{messages,blockingMessages:messages.filter(message=>!advisories.has(message)),
  warnings:[...advisories].map(message=>({...message,attributeNames:['material']}))};
}

function makePublicationFailureObservation(data,input,checks,messages,blockingMessages,terminalFailures){
 const failed=data.items.filter(row=>terminalFailures.includes(row.status)||blockingMessages.some(message=>message.sku===row.sku));
 const failedIds=new Set(failed.map(row=>String(row.id))),accepted=data.items.filter(row=>!failedIds.has(String(row.id))&&['accepted','publishing'].includes(row.status));
 return{publishId:String(data.id),accountId:input.accountId,productId:input.productId,snapshotSha256:input.sha256,
  destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),erpAccountId:String(data.uid),marketId:String(data.market_id),
  countryCode:data.country_code,store:data.market.alias,parentSku:data.sku,status:data.status,observedAt:new Date().toISOString(),
  verification:'failed',failed:true,identityVerified:true,responseFingerprint:publicationFingerprint(data),
  failedChildIds:failed.map(row=>String(row.id)),skus:failed.map(row=>row.sku),count:failed.length,
  childCount:data.items.length,acceptedChildIds:accepted.map(row=>String(row.id)),acceptedSkus:accepted.map(row=>row.sku),acceptedCount:accepted.length,
  messages,messageCount:messages.length,unscopedMessageCount:messages.filter(message=>!message.childId).length,
  children:data.items.map(row=>{const check=checks.find(v=>v.sku===row.sku);return{childId:String(row.id),sku:row.sku,status:row.status,asin:row.asin??null,
   color:check.color,size:check.size,main:check.main,images:check.images,imagesSource:check.imagesSource,messages:messages.filter(message=>message.sku===row.sku)};})};
}

function publicationFailureMessage(observation){
 const codes=severity=>[...new Set(observation.messages.filter(message=>message.severity===severity&&
  /^[A-Z0-9][A-Z0-9_-]{0,31}$/.test(message.code??'')).map(message=>message.code))].sort();
 const errors=codes('ERROR'),warnings=codes('WARNING');
 const details=[`ERP原发布任务已失败或存在错误，涉及 ${observation.count} 个子 SKU，共 ${observation.messageCount} 条回执信息`];
 if(errors.length)details.push(`错误代码 ${errors.join('、')}`);
 if(warnings.length)details.push(`提醒代码 ${warnings.join('、')}`);
 if(errors.includes('300429'))details.push('Amazon 报告图片抓取遇到 HTTP 429 限流');
 details.push('保留原任务待修复');
 return details.join('。');
}

export function verifyPublication(response,input,publishId,{allowOnline=false}={}){
 if(!id(publishId)||String(response?.data?.id)!==String(publishId))throw Error('真实发布任务编号不符');
 const normalized=normalizePublication(response,input),target=structuredClone(input);
 target.destination.draftId=String(publishId);
 // Old accepted tasks are reconciled without another publish. Their inherited
 // images remain explicitly unverified; new submissions must pass strict checks.
 const checks=verifyPersistedDraft(normalized,target,input.urls,{allowInherited:true}),d=response.data;
 if(d.items.some(row=>!id(row.id)||(row.market_id!=null&&String(row.market_id)!==String(d.market_id))||(row.country_code!=null&&row.country_code!==d.country_code))||
    new Set(d.items.map(row=>String(row.id))).size!==d.items.length)throw Error('ERP发布子体编号或店铺站点身份不符');
 const {messages,blockingMessages,warnings}=publicationMessages(d);
 const terminalFailures=['failed','error','rejected','cancelled','canceled'];
 const allChildrenOnline=d.items.every(v=>v.asin&&onlineStatuses.includes(v.status));
 if(blockingMessages.length||terminalFailures.includes(d.status)||d.items.some(v=>terminalFailures.includes(v.status))){
  const observation=makePublicationFailureObservation(d,input,checks,messages,blockingMessages,terminalFailures),error=Error(publicationFailureMessage(observation));
  error.code='ERP_PUBLICATION_FAILED';error.publishId=String(d.id);error.status=d.status;error.failureObservation=observation;throw error;
 }
 if(!['publishing','accepted'].includes(d.status)&&!(allowOnline&&onlineStatuses.includes(d.status)&&allChildrenOnline)){
  if(typeof d.status!=='string'||!d.status||onlineStatuses.includes(d.status))throw Error('ERP尚未完整回读已受理或在售状态');
  // A task may exist before the ERP starts processing it. All identity,
  // content, galleries and explicit errors were checked before this signal.
  const error=Error('ERP原发布任务尚未进入发布中，仅等待同一任务，不重复发布');
  error.code='ERP_PUBLICATION_PENDING';error.publishId=String(d.id);error.status=d.status;throw error;
 }
 if(warnings.length&&d.items.some(row=>!['accepted','publishing'].includes(row.status)&&
    !(typeof row.asin==='string'&&/^[A-Z0-9]{10}$/.test(row.asin)&&onlineStatuses.includes(row.status)))){
  throw Error('ERP尚未完整回读已受理或在售状态');
 }
 return{publishId:String(d.id),status:d.status,accountId:input.accountId,erpAccountId:String(d.uid),productId:input.productId,
  destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),marketId:String(d.market_id),countryCode:d.country_code,
  store:d.market.alias,parentSku:d.sku,children:checks.map(v=>{
   const child=d.items.find(row=>row.sku===v.sku);
   return{sku:v.sku,color:v.color,size:v.size,images:v.images,status:child.status,asin:child.asin??null};
  }),
  allChildrenOnline,imagePersistenceVerified:checks.every(v=>v.imagesSource==='child_gallery'),errors:[],...(warnings.length?{warnings}:{})};
}

// Pure accessor for the original task's recovery flow. Healthy, fully verified
// records return null; identity/readback failures still throw without a scope.
export function publicationFailureObservation(response,input,publishId){
 try{verifyPublication(response,input,publishId,{allowOnline:true});}
 catch(error){if(error.code==='ERP_PUBLICATION_FAILED')return structuredClone(error.failureObservation);throw error;}
 return null;
}

// Read an online record through its actual visible edit action. The API path
// is captured from that UI request, never fabricated from a presumed endpoint.
export async function readNativeOnline(page,onlineId,input){
 await queryPublicationRows(page,{sku:input.goods.parentSku,section:'online'});
 const action=await page.evaluate(({onlineId,sku,store})=>{
  const rows=[...document.querySelectorAll('.el-table__body tr')].filter(r=>r.getBoundingClientRect().width&&r.cells[1]?.innerText.trim()===onlineId&&r.cells[6]?.innerText.trim()===sku&&r.cells[4]?.innerText.trim()===store);
  if(rows.length!==1)throw Error('在线来源行不唯一');const es=[...rows[0].querySelectorAll('a,button')].filter(e=>['编辑','修改'].includes(e.innerText.trim())&&!e.disabled&&e.getAttribute('aria-disabled')!=='true'&&e.getBoundingClientRect().width&&getComputedStyle(e).visibility!=='hidden');
  if(es.length!==1)throw Error('在线来源缺少唯一原生编辑入口');es[0].setAttribute('data-native-online-read','true');
  const href=es[0].getAttribute('href');return href&&href!=='javascript:;'?{href:new URL(href,location.href).href}:{selector:'[data-native-online-read]'};
 },{onlineId:String(onlineId),sku:input.goods.parentSku,store:input.store});
 if(action.href&&!action.href.startsWith('https://www.junfeikuajing.com/'))throw Error('在线编辑入口来源不符');
 await page.evaluate(onlineId=>{
  if(window.__nativeOnlineRead)throw Error('已有在线回读');const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__nativeOnlineRead={open,send,result:null};
  XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.origin==='https://app.junfeikuajing.com'&&url.pathname.startsWith('/api/amazon/goods/online/')&&[...url.searchParams.values()].includes(onlineId));return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{window.__nativeOnlineRead.result={httpStatus:this.status,body:JSON.parse(this.responseText)};}catch{}},{once:true});return send.call(this,b);};
 },String(onlineId));
 let result;try{if(action.href)await page.goto(action.href);else await page.click(action.selector);await page.waitForFunction(()=>window.__nativeOnlineRead?.result,undefined,{timeout:20000});result=await page.evaluate(()=>window.__nativeOnlineRead.result);}
 finally{await page.evaluate(()=>{const s=window.__nativeOnlineRead;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__nativeOnlineRead;}});}
 if(result?.httpStatus!==200||result.body?.code!==0)throw Error('在线原记录详情未读到，不重发原发布');return result.body;
}

function partialOnlineReadback(response,input,record,recordId){
 const expected=fields(input),identity=record.identity,link=record.sourceLink,publishId=String(record.publishId);
 const previous=record.latestObservation;
 if(record.phase==='publication_failed'||previous?.failed===true||previous?.verification==='failed')return;
 if(link.method!=='persisted_intent_unique_new_exact_identity'||link.publishId!==publishId||String(link.draftId)!==expected.draftId||
    !Array.isArray(link.beforePublishIds)||link.beforePublishIds.some(value=>String(value)===publishId)||
    !['accepted','publishing'].includes(identity.status)||identity.imagePersistenceVerified!==true)return;
 const scope={accountId:expected.accountId,productId:expected.productId,destinationId:expected.destinationId,draftId:expected.draftId,
  erpAccountId:expected.erpAccountId,marketId:expected.marketId,countryCode:expected.countryCode,store:expected.store,parentSku:expected.parentSku};
 if(Object.entries(scope).some(([key,value])=>identity[key]!==value))return;
 const d=response?.data,skus=new Set(expected.children.map(child=>child.sku));
 const exactSkus=rows=>Array.isArray(rows)&&rows.length===skus.size&&new Set(rows.map(row=>row.sku)).size===skus.size&&rows.every(row=>skus.has(row.sku));
 if(response?.code!==0||String(d?.id)!==recordId||!id(recordId)||String(d.uid)!==scope.erpAccountId||
    String(d.market_id)!==scope.marketId||d.country_code!==scope.countryCode||d.market?.alias!==scope.store||d.sku!==scope.parentSku||
    !onlineStatuses.includes(d.status)||!exactSkus(d.items)||!exactSkus(identity.children))return;
 if(new Set(d.items.map(row=>String(row.id))).size!==skus.size||d.items.some(row=>
    !id(row.id)||String(row.id)===recordId||String(row.pid)!==recordId||String(row.uid)!==scope.erpAccountId||
    (row.market_id!=null&&String(row.market_id)!==scope.marketId)||(row.country_code!=null&&row.country_code!==scope.countryCode)||
    (row.status!=null&&row.status!==''&&!onlineStatuses.includes(row.status))))return;
 const parentErrorsAvailable=Array.isArray(d.errors);
 if(!parentErrorsAvailable&&d.errors!=null)return;
 // Missing error fields are counted below. Any explicit message must remain
 // visible to the strict observer and can never turn into partial success.
 if(publicationMessages({...d,errors:parentErrorsAvailable?d.errors:[]}).messages.length)return;
 const master=input.goodsItems.find(child=>child.color===input.masterColor)||input.goodsItems[0];
 const cover=input.urls[input.assets[master.imageIndices[0]].sha256];
 if(!cover||!Array.isArray(d.extra?.images)||d.extra.images[0]!==cover)return;
 const exactCoverUrl=d.main_image===cover;
 if(!exactCoverUrl){
  let cdn;try{cdn=new URL(d.main_image);}catch{return;}
  if(cdn.origin!=='https://m.media-amazon.com'||cdn.username||cdn.password||!cdn.pathname.startsWith('/images/I/'))return;
 }
 return{verification:'partial_online_readback',publishId,recordId,...scope,snapshotSha256:expected.snapshotSha256,
  status:d.status,observedAt:new Date().toISOString(),identityVerified:true,responseFingerprint:publicationFingerprint(d),
  childCount:d.items.length,childrenWithAsin:d.items.filter(row=>typeof row.asin==='string'&&/^[A-Z0-9]{10}$/.test(row.asin)).length,
  childrenWithStatus:d.items.filter(row=>onlineStatuses.includes(row.status)).length,parentErrorsAvailable,
  childrenWithErrorFields:d.items.filter(row=>Object.hasOwn(row,'errors')||Object.hasOwn(row.extra||{},'message')).length,
  originalGalleryFirstVerified:true,exactCoverUrl,coverContentCompared:false,allChildrenOnline:false};
}

async function resolvePublicationReadback(page,input,record,adapters,observePartial){
 const api={read:readNativePublication,query:queryPublicationRows,readOnline:readNativeOnline,...adapters};
 if(!id(record.publishId))throw Error('缺少原真实发布任务编号');
 let response,publishReadError;
 try{response=await api.read(page,record.publishId);}catch(error){publishReadError=error;}
 if(response){
  // A readable but wrong/failed source is an identity failure, not evidence
  // that the task moved online. Never mask it by searching another record.
  const identity=verifyPublication(response,input,record.publishId,{allowOnline:true});
  return{response,identity,recordId:String(record.publishId),section:['publishing','accepted'].includes(identity.status)?'publish':'online'};
 }else{
  // Moving to online must never erase or replace the already observed task ID.
  if(!record.identity||record.identity.publishId!==String(record.publishId)||!record.sourceLink)throw publishReadError;
  const rows=await api.query(page,{sku:input.goods.parentSku,section:'online'}),matches=rows.filter(v=>v.sku===input.goods.parentSku&&String(v.market_id)===String(input.destination.marketId)&&v.country_code===input.destination.countryCode&&v.market?.alias===input.store);
  if(matches.length!==1)throw Error('原发布详情不可读，在线来源不唯一；仅对账，不重发');
  const recordId=String(matches[0].id),response=await api.readOnline(page,matches[0].id,input);
  let identity;
  try{identity=verifyPublication(response,input,recordId,{allowOnline:true});}
  catch(error){
   if(observePartial&&['持久父体封面不符','ERP发布错误状态未完整回读','ERP尚未完整回读已受理或在售状态'].includes(error.message)){
    const partial=partialOnlineReadback(response,input,record,recordId);
    if(partial)return{partial};
   }
   throw error;
  }
  if(!identity.allChildrenOnline)throw Error('原任务转在线尚无全部真实子体在售证据');
  return{response,identity,recordId:String(matches[0].id),section:'online'};
 }
}

export async function resolvePublicationSource(page,input,record,adapters={}){
 return resolvePublicationReadback(page,input,record,adapters,false);
}

// Historical evidence: browser-157.mjs / browser-166.mjs observes publish/index;
// browser-155.mjs observes the normal online SKU search. No auth is copied.
export async function queryPublicationRows(page,{sku,section='publish'}){
 if(!sku||!['publish','online'].includes(section))throw Error('发布查询条件无效');
 await page.goto('https://www.junfeikuajing.com/#/goods/amazon/'+section);await page.reload();
 await page.waitForSelector('input[placeholder="请输入sku"]',{state:'visible'});
 await page.evaluate(({sku,section})=>{
  if(window.__nativePublicationQuery)throw Error('已有发布查询');
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();
  window.__nativePublicationQuery={open,send,result:null};
  XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.origin==='https://app.junfeikuajing.com'&&url.pathname.startsWith('/api/amazon/goods/'+section+'/')&&url.searchParams.get('sku')===sku);return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{window.__nativePublicationQuery.result={httpStatus:this.status,body:JSON.parse(this.responseText)};}catch{}},{once:true});return send.call(this,b);};
 },{sku,section});
 let result;try{
  await page.fill('input[placeholder="请输入sku"]',sku);await page.fill('input[placeholder="请输入商品id"]','');await page.fill('input[placeholder="请输入商品标题"]','');
  await page.click('loc=role:button[name="搜索"]');await page.waitForFunction(()=>window.__nativePublicationQuery?.result,undefined,{timeout:15000});
  result=await page.evaluate(()=>window.__nativePublicationQuery.result);
 }finally{await page.evaluate(()=>{const s=window.__nativePublicationQuery;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__nativePublicationQuery;}});}
 const list=result?.body?.data?.list;
 if(result?.httpStatus!==200||result.body.code!==0||!Array.isArray(list?.data)||!Number.isInteger(Number(list.total))||Number(list.total)<0||Number(list.total)!==list.data.length)throw Error('发布查询不完整，禁止提交或再次提交');
 return list.data;
}

// read-publish-detail.mjs observed this exact native GET and editor route.
export async function readNativePublication(page,publishId){
 if(!id(publishId))throw Error('发布任务编号无效');
 await page.goto('https://www.junfeikuajing.com/#/goods/amazon/publish');await page.waitForSelector('input[placeholder="请输入sku"]',{state:'visible'});
 await page.evaluate(publishId=>{
  if(window.__nativePublicationRead)throw Error('已有发布回读');
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__nativePublicationRead={open,send,result:null};
  XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.href==='https://app.junfeikuajing.com/api/amazon/goods/publish/show?id='+publishId);return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{window.__nativePublicationRead.result={httpStatus:this.status,body:JSON.parse(this.responseText)};}catch{}},{once:true});return send.call(this,b);};
 },String(publishId));
 let result;try{
  await page.goto('https://www.junfeikuajing.com/#/amazon/product/'+publishId+'?type=publish');
  await page.waitForFunction(()=>window.__nativePublicationRead?.result,undefined,{timeout:20000});result=await page.evaluate(()=>window.__nativePublicationRead.result);
 }finally{await page.evaluate(()=>{const s=window.__nativePublicationRead;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__nativePublicationRead;}});}
 if(result?.httpStatus!==200||result.body?.code!==0)throw Error('ERP发布详情读取失败');return result.body;
}

// Selectors and persisted attributes are observed in the existing collection
// and UK preparation modules. This reads the current draft; it never applies
// for an exemption or changes a shipping template on the user's behalf.
export async function readPublishReadiness(page,input,draft){
 await page.waitForFunction(()=>{
  const brand=document.querySelector('input[placeholder="品牌"]');
  return brand?.value&&brand.closest('.el-form-item')?.innerText.includes('UPC豁免：允许销售')&&document.querySelector('input[placeholder="亚马逊运输模板"]')?.value;
 },undefined,{timeout:20000});
 const ui=await page.evaluate(()=>({url:location.href,store:document.querySelector('input[placeholder="店铺"]')?.value,
  parentSku:document.querySelector('input[placeholder^="父Sku,"]')?.value,brand:document.querySelector('input[placeholder="品牌"]')?.value,
  brandStatus:document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.innerText,
  shippingTemplate:document.querySelector('input[placeholder="亚马逊运输模板"]')?.value,
  handlingDays:document.querySelector('input[placeholder="处理时间"]')?.value}));
 const a=draft?.data?.extra?.attributes,shipping=a?.merchant_shipping_group?.[0]?.value;
 if(ui.url!=='https://www.junfeikuajing.com/#/amazon/product/'+input.destination.draftId+'?type=draft'||ui.store!==input.store||ui.parentSku!==input.goods.parentSku||ui.brand!==input.goods.brand||!ui.brandStatus?.includes('UPC豁免：允许销售'))throw Error('当前草稿店铺、品牌或UPC豁免允许销售未核实');
 if(!ui.shippingTemplate?.trim()||!shipping||(input.destination.shippingTemplate?.name&&ui.shippingTemplate!==input.destination.shippingTemplate.name)||(input.destination.shippingTemplate?.id&&shipping!==input.destination.shippingTemplate.id)||a?.supplier_declared_has_product_identifier_exemption?.[0]?.value!==true)throw Error('当前草稿实际运输模板或豁免未核实');
 if(input.handlingDays===undefined||String(ui.handlingDays)!==String(input.handlingDays)||String(a?.fulfillment_availability?.[0]?.lead_time_to_ship_max_days)!==String(input.handlingDays))throw Error('当前草稿处理时间未核实');
 return{checkedAt:new Date().toISOString(),store:ui.store,brand:ui.brand,brandStatus:ui.brandStatus,shippingTemplate:{name:ui.shippingTemplate,id:shipping},handlingDays:ui.handlingDays};
}

// Sole write is the exact UI / POST observed in browser-155/native-publish-response.
export async function submitNativePublication(page,input,record,persist){
 if(record.phase!=='publish_unknown'||String(record.intent?.draftId)!==String(input.destination.draftId)||record.nativeRequests?.length)throw Error('缺少已持久发布意图或已有原请求，禁止重发');
 const drafts=await queryDrafts(page,{sku:input.goods.parentSku});
 if(drafts.filter(r=>String(r.id)===String(input.destination.draftId)&&r.sku===input.goods.parentSku&&r.store===input.store).length!==1)throw Error('待发布原草稿查询结果不唯一，未点击发布');
 const selector=await page.evaluate(({draftId,sku,store})=>{
  const rows=[...document.querySelectorAll('.el-table__body tr')].filter(r=>r.getBoundingClientRect().width&&r.cells[1]?.innerText.trim()===draftId&&r.cells[5]?.innerText.trim()===sku&&r.cells[4]?.innerText.trim()===store);
  if(rows.length!==1)throw Error('待发布草稿行不唯一');const buttons=[...rows[0].querySelectorAll('button')].filter(b=>b.innerText.trim()==='发布');if(buttons.length!==1)throw Error('原生发布入口不唯一');buttons[0].setAttribute('data-native-publication','true');return '[data-native-publication]';
 },{draftId:String(input.destination.draftId),sku:input.goods.parentSku,store:input.store});
 await page.evaluate(draftId=>{
  if(window.__nativePublicationWrite)throw Error('已有发布写入');const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__nativePublicationWrite={open,send,requests:[]};
  XMLHttpRequest.prototype.open=function(m,u,...r){targets.set(this,{method:String(m).toUpperCase(),url:new URL(u,location.href)});return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(body){const q=targets.get(this),s=window.__nativePublicationWrite;if(q?.method==='POST'&&q.url.origin==='https://app.junfeikuajing.com'&&q.url.pathname.startsWith('/api/amazon/goods/')){
   const payload=JSON.parse(body);if(q.url.pathname!=='/api/amazon/goods/draft/publish'||s.requests.length||payload.ids?.length!==1||String(payload.ids[0])!==draftId)throw Error('拦截非目标或重复发布');
   const request={path:q.url.pathname,payload,sentAt:new Date().toISOString(),response:null};s.requests.push(request);this.addEventListener('loadend',()=>{let value;try{value=JSON.parse(this.responseText);}catch{}request.response={httpStatus:this.status,body:value};},{once:true});
  }return send.call(this,body);};
 },String(input.destination.draftId));
 try{await page.click(selector);await page.waitForFunction(()=>window.__nativePublicationWrite?.requests.some(v=>v.response),undefined,{timeout:25000});}
 finally{
  record.nativeRequests=await page.evaluate(()=>window.__nativePublicationWrite?.requests||[]);await persist();
  await page.evaluate(()=>{const s=window.__nativePublicationWrite;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__nativePublicationWrite;}});
 }
 const response=record.nativeRequests[0]?.response;
 if(response?.httpStatus!==200||response.body?.code!==0)throw Error('发布结果未确认，保留原任务待对账');
}

export async function publishNative(page,input,record,persist,adapters={}){
 return runNativePublication(page,input,record,persist,adapters,false);
}

export async function observePublishedNative(page,input,record,persist,adapters={}){
 if(!id(record.publishId))throw Error('只读核对缺少原真实发布任务编号');
 return runNativePublication(page,input,record,persist,adapters,true);
}

async function runNativePublication(page,input,record,persist,adapters,observePartial){
 const api={readDraft:readPersistedDraft,verifyDraft:verifyPersistedDraft,ensureImages:ensureExplicitDraftGalleries,readiness:readPublishReadiness,query:queryPublicationRows,read:readNativePublication,readOnline:readNativeOnline,submit:submitNativePublication,wait:waitForPublication,...adapters};
 const expected=assertPublicationInput(input),fingerprint=publicationFingerprint(expected);
 if(record.fingerprint&&record.fingerprint!==fingerprint)throw Error('发布回执属于其他账号、产品或草稿');
 record.fingerprint=fingerprint;record.identityExpected=expected;
 const exact=row=>row.sku===expected.parentSku&&String(row.market_id)===expected.marketId&&row.country_code===expected.countryCode&&row.market?.alias===expected.store;
 if(record.observedCandidate&&!record.publishId&&!record.intent)throw Error('原候选发布任务缺少持久意图，不重新提交');
 if(record.publishId&&record.observedCandidate&&String(record.publishId)!==String(record.observedCandidate.taskId))throw Error('已受理任务与原候选不符，不选择替代发布任务');
 const observeFailure=async error=>{
  if(!error.failureObservation)return;
  const observation=structuredClone(error.failureObservation);
  record.latestObservation=observation;record.failureObservation=observation;record.status=observation.status;record.currentStatus=observation.status;record.phase='publication_failed';
  if(record.observedCandidate)record.observedCandidate={...record.observedCandidate,status:observation.status,observedAt:observation.observedAt};
  // identity/sourceEvidence remain the historical accepted observation. A
  // later failure is separate evidence, never a replacement success receipt.
  await persist();
 };
 // A known task is always re-read, including when the local phase was complete.
 if(record.publishId){
  let current;
  for(let attempt=0;attempt<6;attempt++){
   try{current=await resolvePublicationReadback(page,input,record,api,observePartial);break;}
   catch(error){
    if(error.code!=='ERP_PUBLICATION_PENDING'){await observeFailure(error);throw error;}
    record.status=error.status;record.currentStatus=error.status;record.phase='publish_pending';
    record.latestObservation={publishId:String(record.publishId),status:error.status,verification:'pending',failed:false,observedAt:new Date().toISOString()};await persist();
    if(attempt===5)throw error;await api.wait(5000);
   }
  }
  if(current.partial){
   record.onlineReadback=current.partial;
   record.latestObservation=current.partial;
   await persist();return record;
  }
  if(current.section==='online'){
   record.onlineObservation={recordId:current.recordId,identity:current.identity,checkedAt:new Date().toISOString()};
   // Preserve the accepted publication observation and original publish ID.
   // The new online identity is separate evidence, never a replacement task.
   record.status='accepted';record.currentStatus=current.identity.status;
  }else{record.identity=current.identity;record.status=current.identity.status;record.sourceEvidence=current.response.data;}
  record.currentStatus=current.identity.status;record.latestObservation={publishId:String(record.publishId),recordId:current.recordId,status:current.identity.status,
   verification:'accepted',failed:false,observedAt:new Date().toISOString(),childCount:current.identity.children.length,allChildrenOnline:current.identity.allChildrenOnline,
   ...(current.identity.warnings?{warnings:current.identity.warnings}:{})};
  record.phase='publishing_verified';await persist();return record;
 }
 if(!record.intent){
  let draft=await api.readDraft(page,expected.draftId);
  if(String(draft?.data?.uid)!==expected.erpAccountId)throw Error('ERP源草稿账号不符');
  try{api.verifyDraft(draft,input,input.urls);}catch{
   draft=await api.ensureImages(page,input,input.urls,record,persist,{read:api.readDraft,initialResponse:draft});
   api.verifyDraft(draft,input,input.urls);
  }
  record.readiness=await api.readiness(page,input,draft);
  const before=await api.query(page,{sku:expected.parentSku}),online=await api.query(page,{sku:expected.parentSku,section:'online'});
  if(before.some(exact)||online.some(exact))throw Error('目标店铺已有同SKU发布记录但缺少本任务关联，先对账');
  record.intent={createdAt:new Date().toISOString(),draftId:expected.draftId,beforePublishIds:before.map(v=>String(v.id)),draftFingerprint:publicationFingerprint(draft.data)};
  record.phase='publish_unknown';await persist();
  // Persist the uncertain state BEFORE clicking. A crash at any later point
  // can only query the original identity, never automatically click again.
  try{await api.submit(page,input,record,persist);}catch(error){record.lastSubmitError=String(error.message);await persist();}
 }
 if(String(record.intent.draftId)!==expected.draftId||!Array.isArray(record.intent.beforePublishIds))throw Error('原发布意图与草稿不符，不重新提交');
 if(!record.observedCandidate){
  const rows=await api.query(page,{sku:expected.parentSku}),candidates=rows.filter(v=>exact(v)&&!record.intent.beforePublishIds.some(value=>String(value)===String(v.id)));
  if(candidates.length!==1||!id(candidates[0].id)){record.phase='publish_unknown';await persist();throw Error('未找到唯一的原草稿发布任务，不重复发布');}
  record.observedCandidate={taskId:String(candidates[0].id),status:candidates[0].status??null,observedAt:new Date().toISOString()};
  await persist();
 }
 const taskId=String(record.observedCandidate.taskId);
 if(!id(taskId)||record.intent.beforePublishIds.some(value=>String(value)===taskId))throw Error('原观察候选任务身份不符，不选择替代发布任务');
 let response,identity;
 for(let attempt=0;attempt<6;attempt++){
  response=await api.read(page,taskId);
  try{identity=verifyPublication(response,input,taskId);}
  catch(error){
   if(error.code!=='ERP_PUBLICATION_PENDING'){await observeFailure(error);throw error;}
   record.phase='publish_unknown';record.observedCandidate={...record.observedCandidate,status:error.status,observedAt:new Date().toISOString(),readCount:(record.observedCandidate.readCount||0)+1};
   await persist();
   if(attempt===5)throw error;
   await api.wait(5000);continue;
  }
  record.observedCandidate={...record.observedCandidate,status:identity.status,observedAt:new Date().toISOString(),readCount:(record.observedCandidate.readCount||0)+1};
  break;
 }
 Object.assign(record,{publishId:identity.publishId,status:identity.status,identity,sourceEvidence:response.data,phase:'publishing_verified',
  latestObservation:{publishId:identity.publishId,recordId:identity.publishId,status:identity.status,verification:'accepted',failed:false,observedAt:new Date().toISOString(),childCount:identity.children.length,allChildrenOnline:identity.allChildrenOnline,
   ...(identity.warnings?{warnings:identity.warnings}:{})},
  sourceLink:{draftId:expected.draftId,publishId:identity.publishId,method:'persisted_intent_unique_new_exact_identity',beforePublishIds:record.intent.beforePublishIds}});
 await persist();return record;
}
