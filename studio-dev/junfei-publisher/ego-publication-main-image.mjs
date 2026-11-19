// Repair one original failed child's missing MAIN locator. Save and retry are
// separate one-shot intents; every uncertain continuation reads the original ID.
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,readNativePublication} from './ego-publish-native.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';
import {submitNativeMediaRecovery} from './ego-publication-recovery.mjs';

const saveEndpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/json-update';
const retryEndpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish';
const clone=value=>structuredClone(value),canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const normalizeText=value=>typeof value==='string'?value.replace(/<br\s*\/?\s*>/gi,'\n').replace(/\r\n/g,'\n'):value;
const id=value=>/^[1-9]\d*$/.test(String(value))&&Number.isSafeInteger(Number(value));
const schemaOf=meta=>typeof meta?.schema_content==='string'?JSON.parse(meta.schema_content):meta?.schema_content;

// Status, timestamps and error messages may change while Amazon processes the
// same task. Every remaining source business field and every original attribute
// is compared before and after Save, including all thirty independent galleries.
export function mainImageBusinessProjection(source){
 const row=value=>{
  const out={};
  for(const [key,v]of Object.entries(value)){
   if(['status','s3_status','created_at','updated_at','published_at','deleted_at','image_thumb','errors','message','market','goods','items','asin','parent_asin','child_asin'].includes(key))continue;
   if(key==='extra'){
    out.extra={};for(const [field,item]of Object.entries(v||{}))if(!['created_at','updated_at','message'].includes(field))out.extra[field]=field==='product_description'?normalizeText(item):clone(item);
   }else out[key]=clone(v);
  }
  return out;
 };
 return{parent:row(source),children:source.items.map(row)};
}

export async function readMainImageRepairSource(page,input,publishId){
 await page.evaluate(()=>{
  if(window.__mainImageSchemaRead)throw Error('已有主图schema观察');
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__mainImageSchemaRead={open,send,meta:null};
  XMLHttpRequest.prototype.open=function(method,url,...rest){const u=new URL(url,location.href);targets.set(this,String(method).toUpperCase()==='GET'&&u.origin==='https://app.junfeikuajing.com'&&u.pathname==='/api/amazon/category/get-product-type');return open.call(this,method,url,...rest);};
  XMLHttpRequest.prototype.send=function(body){if(targets.get(this))this.addEventListener('loadend',()=>{try{const result=JSON.parse(this.responseText);if(this.status===200&&result.code===0)window.__mainImageSchemaRead.meta=result.data;}catch{}},{once:true});return send.call(this,body);};
 });
 try{const response=await readNativePublication(page,publishId);await page.waitForFunction(()=>window.__mainImageSchemaRead?.meta,undefined,{timeout:20000});return{response,meta:await page.evaluate(()=>window.__mainImageSchemaRead.meta)};}
 finally{await page.evaluate(()=>{const state=window.__mainImageSchemaRead;if(state){XMLHttpRequest.prototype.open=state.open;XMLHttpRequest.prototype.send=state.send;delete window.__mainImageSchemaRead;}});}
}

function assertSchema(meta,input,frozen){
 const schema=schemaOf(meta),original=schemaOf(frozen),field=schema?.properties?.main_product_image_locator;
 if(!frozen||!original||meta?.hash!==input.destination.schemaHash||frozen.hash!==meta.hash||meta.country_code!=='US'||meta.locale!=='en_US'||
    schema?.$defs?.marketplace_id?.default!==input.destination.marketplaceId||!same(schema,original)||
    field?.type!=='array'||field.items?.type!=='object'||!field.items.required?.includes('media_location')||
    field.items.properties?.media_location?.type!=='string'||!field.items.properties?.marketplace_id)throw Error('主图修复缺少绑定原美国站点和实际类目的MAIN schema');
 return meta;
}
function inspect(response,input,publishId){
 try{return{failure:publicationFailureObservation(response,input,publishId),pending:false};}
 catch(error){if(error.code==='ERP_PUBLICATION_PENDING')return{failure:null,pending:true,status:error.status};throw error;}
}
function expectedLocator(input,amendment){return[{marketplace_id:input.destination.marketplaceId,media_location:amendment.mainImageUrl}];}
function assertFailure(observation,amendment,{fingerprint=false}={}){
 if(!observation||observation.status!=='failed'||observation.count!==1||observation.unscopedMessageCount!==0||
    !same(observation.failedChildIds,[amendment.failedChildId])||!same(observation.skus,[amendment.failedSku])||
    observation.acceptedCount!==observation.childCount-1||observation.messages.length!==1||
    observation.messages[0].code!=='18320'||observation.messages[0].sku!==amendment.failedSku||
    observation.children.some(row=>row.imagesSource!=='child_gallery'||!['accepted','failed'].includes(row.status))||
    (fingerprint&&observation.responseFingerprint!==amendment.failureResponseFingerprint))throw Error('仅可修复原任务唯一18320主图失败，其余子体须已受理');
}
function assertAuthorization(input,record,amendment){
 const expected=assertPublicationInput(input),publishId=String(record.publishId);
 if(input.destination.countryCode!=='US'||!id(publishId)||record.fingerprint!==publicationFingerprint(expected)||
    String(record.identity?.publishId)!==publishId||String(record.sourceLink?.publishId)!==publishId||
    String(record.sourceLink?.draftId)!==String(input.destination.draftId))throw Error('主图修复缺少原已受理美国任务关联');
 if(!amendment||!amendment.id||amendment.scope!=='repair_original_failed_main_image'||amendment.marketplace!=='US'||
    amendment.retryOriginalTaskAfterVerifiedSave!==true||!id(amendment.failedChildId)||!amendment.failedSku||
    !/^[a-f0-9]{64}$/.test(amendment.assetSha256||'')||!/^[a-f0-9]{64}$/.test(amendment.failureResponseFingerprint||'')||
    typeof amendment.authorizedAt!=='number'||!Number.isFinite(amendment.authorizedAt)||amendment.authorizedAt<=0)throw Error('缺少服务端冻结的原MAIN修复授权');
 for(const [key,value]of Object.entries({accountId:input.accountId,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,publishId,
  destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),erpAccountId:String(input.destination.erpAccountId),
  marketId:String(input.destination.marketId),countryCode:'US',store:input.store,parentSku:input.goods.parentSku}))if(value===undefined||amendment[key]===undefined||String(amendment[key])!==String(value))throw Error('MAIN修复授权原身份不符：'+key);
 if(!record.sourceEvidence||publicationFailureObservation({code:0,data:record.sourceEvidence},input,publishId)!==null)throw Error('MAIN修复原受理历史身份不完整');
 const variant=input.goodsItems.find(row=>row.sku===amendment.failedSku),asset=variant&&input.assets[variant.imageIndices[0]];
 if(!asset||asset.sha256!==amendment.assetSha256||input.urls[asset.sha256]!==amendment.mainImageUrl)throw Error('MAIN修复只能复用该原SKU首图及原文件哈希');
 if(record.mainImageRepair&&record.mainImageRepair.amendmentId!==amendment.id)throw Error('已有原MAIN修复检查点，不覆盖或另建保存');
 return{publishId,asset};
}
function withLocator(source,input,amendment){
 const next=clone(source),row=next.items.find(value=>String(value.id)===String(amendment.failedChildId)&&value.sku===amendment.failedSku);
 if(!row||row.main_image!==amendment.mainImageUrl)throw Error('MAIN目标原子体编号或首图不符');
 row.extra.attributes.main_product_image_locator=expectedLocator(input,amendment);return next;
}
const records=source=>[{id:'parent',attributes:source.extra.attributes},...source.items.map(row=>({id:row.sku,attributes:row.extra.attributes}))];
const saveVersions=source=>({parent:source.updated_at,parentExtra:source.extra?.updated_at,children:source.items.map(row=>({id:String(row.id),updatedAt:row.updated_at,extraUpdatedAt:row.extra?.updated_at}))});

function assertCorrectiveAuthorization(input,record,amendment){
 const journal=record.mainImageRepair,correction=amendment.correctiveSave;
 if(!correction||typeof correction.id!=='string'||!correction.id||correction.scope!=='explicit_idempotent_original_main_resave'||correction.marketplace!=='US'||
    correction.originalMainAmendmentId!==amendment.id||correction.originalSaveIntentArmedAt!==journal.saveIntent?.armedAt||
    correction.retryOriginalTaskAfterVerifiedSave!==true||typeof correction.authorizedAt!=='number'||!Number.isFinite(correction.authorizedAt)||correction.authorizedAt<=0)throw Error('缺少独立显式的同原任务幂等纠正授权');
 for(const key of ['accountId','productId','jobId','snapshotSha256','publishId','destinationId','draftId','erpAccountId','marketId','countryCode','store','parentSku','failedChildId','failedSku','mainImageUrl','assetSha256','failureResponseFingerprint'])if(correction[key]===undefined||String(correction[key])!==String(amendment[key]))throw Error('幂等纠正授权原身份或媒体范围不符：'+key);
 if(journal.correctiveSave&&journal.correctiveSave.amendmentId!==correction.id)throw Error('已有独立纠正检查点，不覆盖或再创建保存');
 return correction;
}

// Self-contained: this exact function is installed inside the native Save XHR
// hook. Its request shape was captured from the normal editor Save action.
export function patchMainImageSavePayload(body,plan){
 const clone=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value)),canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
 const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b)),text=value=>typeof value==='string'?value.replace(/<br\s*\/?\s*>/gi,'\n').replace(/\r\n/g,'\n'):value;
 const parentKeys=['keywords','product_description','bullet_point','market_id','title','id','brand','price','quantity','country_code','pallet_service_unique','pallet_goods_id','part_number','standard_product_type','standard_product_id','list_price','cost_price','manufacturer','parent_sku','country_of_origin','variation_theme','main_image','images','product_type_name','category_path','variation','sku','items','attributes'];
 const childKeys=['id','attributes','keywords','list_price','product_description','price_info','bullet_point','title','main_image','images','variation','standard_product_type','cost_price','price','quantity','title_differentiation','sku','standard_product_id'];
 const keys=(object,list)=>object&&equal(Object.keys(object).sort(),[...list].sort());
 const source=plan.source;if(!keys(body,parentKeys)||String(body.id)!==String(source.id)||body.sku!==source.sku||!Array.isArray(body.items)||body.items.length!==source.items.length)throw Error('保存请求原任务或字段范围变化，已拦截');
 const allImages=new Set(source.items.flatMap(row=>row.extra.images));
 if(!Array.isArray(body.images)||new Set(body.images).size!==body.images.length||body.images.some(url=>!allImages.has(url)))throw Error('保存预览出现非原图库，已拦截');
 const out=clone(body),extraKeys=['keywords','product_description','bullet_point','images'];
 for(const key of parentKeys){
  if(['attributes','items','images'].includes(key))continue;
  const actual=key==='parent_sku'?source.sku:key==='variation'?{}:extraKeys.includes(key)?source.extra[key]:source[key];
  if(key==='market_id'?String(body[key])!==String(actual):!equal(text(body[key]),text(actual)))throw Error('保存预览父业务字段变化：'+key);
  out[key]=clone(actual);
 }
 out.images=clone(source.extra.images);out.attributes=clone(source.extra.attributes);
 const used=new Set();out.items=body.items.map(row=>{
  if(!keys(row,childKeys))throw Error('保存子体字段范围变化，已拦截');
  const original=source.items.find(value=>String(value.id)===String(row.id)&&value.sku===row.sku);
  if(!original||used.has(String(original.id)))throw Error('保存子SKU集合变化，已拦截');used.add(String(original.id));
  const next=clone(row),get=path=>path.split('.').reduce((value,key)=>value?.[key],original.extra.attributes),variation=Object.fromEntries(Object.values(plan.variationFields).map(path=>[path,get(path)]));
  const pricePaths=['purchasable_offer.0.maximum_seller_allowed_price.0.schedule.0.value_with_tax','purchasable_offer.0.minimum_seller_allowed_price.0.schedule.0.value_with_tax'];
  const priceInfo=Object.fromEntries(pricePaths.map(path=>[path,get(path)??'']));
  if(!equal(row.variation,variation)||!equal(row.price_info,priceInfo)||row.title_differentiation!==(original.extra.attributes.title_differentiation?.[0]?.value??''))throw Error('保存颜色尺码或价格边界字段变化，已拦截');
  for(const key of childKeys){
   if(['attributes','variation','price_info','title_differentiation'].includes(key))continue;
   const actual=extraKeys.includes(key)?original.extra[key]:original[key];
   if(key==='standard_product_type'&&actual==null&&row[key]==='UPC'){next[key]=actual;continue;}
   if(!equal(text(row[key]),text(actual)))throw Error('保存子SKU业务字段变化：'+row.sku+' '+key);
   next[key]=clone(actual);
  }
  next.attributes=clone(original.extra.attributes);
  if(String(original.id)===String(plan.failedChildId)){
   if(original.sku!==plan.failedSku||original.main_image!==plan.mainImageUrl)throw Error('MAIN保存目标与原SKU首图不同');
   next.attributes.main_product_image_locator=[{marketplace_id:plan.marketplaceId,media_location:plan.mainImageUrl}];
  }
  return next;
 });
 return out;
}

function installMainImageSaveGuardBody(plan){
 if(window.__mainImageSave)throw Error('已有原MAIN保存观察');
 const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,fetch=window.fetch,targets=new WeakMap(),state={open,send,fetch,guardId:plan.guardId,requests:[],error:null};window.__mainImageSave=state;
 XMLHttpRequest.prototype.open=function(method,url,...rest){targets.set(this,{method:String(method).toUpperCase(),url:new URL(url,location.href)});return open.call(this,method,url,...rest);};
 XMLHttpRequest.prototype.send=function(body){
  const request=targets.get(this);if(!request||['GET','HEAD'].includes(request.method))return send.call(this,body);
  try{
   if(state.error||state.requests.length||request.method!=='POST'||request.url.href!=='https://app.junfeikuajing.com/api/amazon/goods/publish/json-update')throw Error('拦截非原任务保存或重复写入');
   const payload=patchMainImageSavePayload(JSON.parse(body),plan),record={method:request.method,url:request.url.href,payload,sentAt:new Date().toISOString(),response:null};state.requests.push(record);
   this.addEventListener('loadend',()=>{let value;try{value=JSON.parse(this.responseText);}catch{}record.response={httpStatus:this.status,body:value};},{once:true});return send.call(this,JSON.stringify(payload));
  }catch(error){state.error=error.message;throw error;}
 };
 state.hookedOpen=XMLHttpRequest.prototype.open;state.hookedSend=XMLHttpRequest.prototype.send;
 if(typeof fetch==='function'){
  window.fetch=function(input,init){const method=String(init?.method||input?.method||'GET').toUpperCase();if(!['GET','HEAD'].includes(method)){state.error='拦截非原XHR保存写入';return Promise.reject(Error(state.error));}return fetch.apply(this,arguments);};
  state.hookedFetch=window.fetch;
 }
 return{installed:true,guardId:state.guardId,requestCount:state.requests.length};
}
// Construct the self-contained callback in Node. The Page receives a function
// and JSON argument, with no in-page eval or dependency on string semantics.
export const installMainImageSaveGuard=new Function('plan','const patchMainImageSavePayload='+patchMainImageSavePayload.toString()+';return ('+installMainImageSaveGuardBody.toString()+')(plan);');

export function mainImageSaveGuardSnapshot(){
 const state=window.__mainImageSave,boxes=[...document.querySelectorAll('.el-message-box')].filter(box=>box.getBoundingClientRect().width);
 return{present:Boolean(state),guardId:state?.guardId,prototypeBound:Boolean(state)&&XMLHttpRequest.prototype.open===state.hookedOpen&&XMLHttpRequest.prototype.send===state.hookedSend,
  fetchBound:Boolean(state?.hookedFetch)&&window.fetch===state.hookedFetch,url:location.href,requests:state?.requests||[],error:state?.error||null,
  colorWarnings:boxes.map(box=>box.innerText),observedAt:new Date().toISOString()};
}

export function mainImageSaveConfirmationStable(expectedGuardId){
 const state=window.__mainImageSave;
 if(!state||!expectedGuardId||state.guardId!==expectedGuardId||XMLHttpRequest.prototype.open!==state.hookedOpen||
    XMLHttpRequest.prototype.send!==state.hookedSend||!state.hookedFetch||window.fetch!==state.hookedFetch||state.error||state.requests.length)throw Error('MAIN确认护栏已失效或已有请求，未点击确认');
 const boxes=[...document.querySelectorAll('.el-message-box')].filter(box=>box.getBoundingClientRect().width);
 if(boxes.length!==1)return false;const buttons=[...boxes[0].querySelectorAll('button')].filter(button=>!button.disabled&&button.innerText.trim()==='确定');
 if(buttons.length!==1)return false;const button=buttons[0],rect=button.getBoundingClientRect(),boxRect=boxes[0].getBoundingClientRect(),style=getComputedStyle(button),boxStyle=getComputedStyle(boxes[0]);
 if(!rect.width||!rect.height||style.pointerEvents==='none'||style.visibility==='hidden'||Number(boxStyle.opacity??1)!==1){state.confirmStable=null;return false;}
 const x=rect.x+rect.width/2,y=rect.y+rect.height/2,hit=document.elementFromPoint(x,y);
 if(x<0||y<0||x>=innerWidth||y>=innerHeight||!hit||(hit!==button&&!button.contains(hit))){state.confirmStable=null;return false;}
 const fingerprint=JSON.stringify([rect.x,rect.y,rect.width,rect.height,boxRect.x,boxRect.y,boxRect.width,boxRect.height,boxes[0].innerText]);
 state.confirmStable=state.confirmStable?.fingerprint===fingerprint?{fingerprint,count:state.confirmStable.count+1}:{fingerprint,count:1};return state.confirmStable.count>=3;
}

export async function submitNativeMainImageSave(page,input,record,persist,{source,amendment}={}){
 const journal=record.mainImageRepair;
 if(!journal?.saveIntent||journal.nativeRequests?.length||String(journal.saveIntent.publishId)!==String(record.publishId))throw Error('缺少原MAIN持久保存意图或已有请求，不再次保存');
 const plan={source,guardId:amendment.id,variationFields:input.destination.variationFields,failedChildId:amendment.failedChildId,failedSku:amendment.failedSku,mainImageUrl:amendment.mainImageUrl,marketplaceId:input.destination.marketplaceId};
 await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(button=>button.getBoundingClientRect().width&&!button.disabled&&button.innerText.replace(/\s/g,'')==='保存'&&[...button.parentElement.querySelectorAll('button')].some(sibling=>sibling.innerText.replace(/\s/g,'')==='保存并发布')),undefined,{timeout:20000});
 try{
  const installed=await page.evaluate(installMainImageSaveGuard,plan),guard=await page.evaluate(mainImageSaveGuardSnapshot);
  if(installed?.installed!==true||installed.guardId!==amendment.id||!guard.present||guard.guardId!==amendment.id||!guard.prototypeBound||!guard.fetchBound||guard.requests.length||guard.error)throw Error('原MAIN保存护栏未完成安装核验，未点击任何保存按钮');
  journal.guardInstallProof={guardId:guard.guardId,prototypeBound:guard.prototypeBound,fetchBound:guard.fetchBound,url:guard.url,observedAt:guard.observedAt};await persist();
  const selector=await page.evaluate(()=>{const buttons=[...document.querySelectorAll('button')].filter(button=>button.getBoundingClientRect().width&&!button.disabled&&button.innerText.replace(/\s/g,'')==='保存'&&[...button.parentElement.querySelectorAll('button')].some(sibling=>sibling.innerText.replace(/\s/g,'')==='保存并发布'));if(buttons.length!==1)throw Error('原任务保存按钮不唯一');buttons[0].setAttribute('data-original-main-save','true');buttons[0].scrollIntoView({block:'center'});return '[data-original-main-save]';});
  await page.click(selector);
  await page.waitForFunction(()=>window.__mainImageSave?.requests.some(request=>request.response)||window.__mainImageSave?.error||[...document.querySelectorAll('.el-message-box')].some(box=>box.getBoundingClientRect().width),undefined,{timeout:20000});
  const boxes=await page.evaluate(()=>[...document.querySelectorAll('.el-message-box')].filter(box=>box.getBoundingClientRect().width).map(box=>box.innerText));
  if(boxes.length){
   const colors=[...new Set(input.goodsItems.map(row=>row.color))];
   if(boxes.length!==1||!boxes[0].includes('颜色')||!boxes[0].includes('不在亚马逊选项中。确定要保存吗？')||/发布|删除/.test(boxes[0])||!colors.every(color=>boxes[0].includes(color)))throw Error('MAIN保存出现非原颜色确认，未继续');
   journal.enumConfirmation=boxes[0];await persist();
   await page.waitForFunction(mainImageSaveConfirmationStable,amendment.id,{timeout:10000});
   const confirm=await page.evaluate(()=>{const boxes=[...document.querySelectorAll('.el-message-box')].filter(box=>box.getBoundingClientRect().width);if(boxes.length!==1)throw Error('颜色保存确认不唯一');const buttons=[...boxes[0].querySelectorAll('button')].filter(button=>!button.disabled&&button.innerText.trim()==='确定');if(buttons.length!==1)throw Error('颜色保存确认按钮不唯一');buttons[0].setAttribute('data-original-main-confirm','true');return '[data-original-main-confirm]';});
   const confirmGuard=await page.evaluate(mainImageSaveGuardSnapshot);
   if(!confirmGuard.present||confirmGuard.guardId!==amendment.id||!confirmGuard.prototypeBound||!confirmGuard.fetchBound||confirmGuard.requests.length||confirmGuard.error||confirmGuard.url!==journal.guardInstallProof.url)throw Error('MAIN确认前护栏或页面发生变化，未点击确认');
   journal.confirmGuardProof={guardId:confirmGuard.guardId,prototypeBound:confirmGuard.prototypeBound,fetchBound:confirmGuard.fetchBound,url:confirmGuard.url,observedAt:confirmGuard.observedAt};await persist();
   await page.click(confirm);
  }
  await page.waitForFunction(()=>window.__mainImageSave?.requests.some(request=>request.response)||window.__mainImageSave?.error,undefined,{timeout:25000});
 }finally{
  try{const state=await page.evaluate(mainImageSaveGuardSnapshot);journal.lastGuardSnapshot=state;journal.nativeRequests=state.requests;if(state.error)journal.guardError=state.error;await persist();}
  finally{await page.evaluate(()=>{const state=window.__mainImageSave;if(state){XMLHttpRequest.prototype.open=state.open;XMLHttpRequest.prototype.send=state.send;if(state.hookedFetch&&window.fetch===state.hookedFetch)window.fetch=state.fetch;delete window.__mainImageSave;}});}
 }
 const request=journal.nativeRequests?.[0];if(journal.nativeRequests?.length!==1||request.url!==saveEndpoint||request.response?.httpStatus!==200||request.response.body?.code!==0)throw Error(journal.guardError||'MAIN保存结果未知，仅回读原任务，不再次保存');
 journal.saveAcknowledgedAt=new Date().toISOString();await persist();return journal;
}

export async function repairNativeMainImage(page,input,record,persist,{amendment=input.publicationMainImageRepair,schemaObservation,...adapters}={}){
 const api={observe:readMainImageRepairSource,remote:verifyRemoteAsset,validate:validateSchemaAttributes,save:submitNativeMainImageSave,retry:submitNativeMediaRecovery,...adapters};
 const {publishId,asset}=assertAuthorization(input,record,amendment),read=async()=>{
  const observed=await api.observe(page,input,publishId);assertSchema(observed.meta,input,schemaObservation);
  const state=inspect(observed.response,input,publishId);return{...observed,...state};
 };
 let current=await read(),source=current.response.data,journal=record.mainImageRepair;
 const target=source.items.find(row=>String(row.id)===String(amendment.failedChildId)&&row.sku===amendment.failedSku),locator=target?.extra?.attributes?.main_product_image_locator;
 if(!target||target.main_image!==amendment.mainImageUrl)throw Error('当前MAIN目标原子体身份或图片不符');
 const validate=async(data,meta)=>{
  const proof=await api.validate(meta,records(data),input);if(proof?.passed!==true||proof.checkedCount!==input.goodsItems.length+1)throw Error('MAIN全部父子原schema检查没有完整通过');return proof;
 };
 const consumeNoWrite=async observation=>{
  const proof=await validate(observation.response.data,observation.meta);
  journal??={amendmentId:amendment.id,amendment:clone(amendment),publishId,beforeSource:clone(observation.response.data),createdAt:new Date().toISOString()};record.mainImageRepair=journal;
  Object.assign(journal,{phase:'source_no_longer_failed',consumedWithoutWrite:true,saveWasNeeded:false,resolvedNoWriteVerified:true,persistedSchemaValidation:proof,
   lastObservation:{status:observation.response.data.status,failed:Boolean(observation.failure),pending:observation.pending,observedAt:new Date().toISOString()}});
  await persist();return journal;
 };
 if(journal?.consumedWithoutWrite){journal.lastObservation={status:source.status,failed:Boolean(current.failure),pending:current.pending,observedAt:new Date().toISOString()};await validate(source,current.meta);await persist();return journal;}
 if(!current.failure&&!journal?.saveIntent)return consumeNoWrite(current);
 if(journal?.saveIntent&&amendment.correctiveSave){
  const correction=assertCorrectiveAuthorization(input,record,amendment);let corrective=journal.correctiveSave;
  if(corrective?.consumedWithoutWrite&&corrective.reason==='source_no_longer_failed'){await validate(source,current.meta);return journal;}
  if(!corrective?.saveIntent&&!corrective?.consumedWithoutWrite){
   // This is an explicit, separately authorized same-ID correction. The old
   // request remains unknown; an unchanged source is never labelled unsent.
   if(!Array.isArray(journal.nativeRequests)||journal.nativeRequests.length||journal.guardError||journal.saveVerified||journal.retry?.intent||
      typeof journal.lastSaveError!=='string'||!/timed out/i.test(journal.lastSaveError))throw Error('原保存状态不满足一次显式幂等纠正条件');
   corrective??={amendmentId:correction.id,amendment:clone(correction),publishId,scope:correction.scope,originalSaveIntent:clone(journal.saveIntent),originalLastSaveError:journal.lastSaveError,createdAt:new Date().toISOString()};journal.correctiveSave=corrective;
   if(!current.failure){corrective.consumedWithoutWrite=true;corrective.reason='source_no_longer_failed';corrective.phase='no_corrective_save_needed';corrective.persistedSchemaValidation=await validate(source,current.meta);journal.resolvedNoWriteVerified=true;await persist();return journal;}
   if(same(locator,expectedLocator(input,amendment))){corrective.consumedWithoutWrite=true;corrective.reason='original_MAIN_already_persisted';corrective.phase='no_corrective_save_needed';await persist();}
   else{
    const checkUnchanged=observation=>{assertFailure(observation.failure,amendment,{fingerprint:true});if(!same(mainImageBusinessProjection(observation.response.data),journal.beforeBusinessProjection)||!same(saveVersions(observation.response.data),saveVersions(journal.beforeSource)))throw Error('原业务或更新时间变化，不执行显式幂等纠正');};
    try{
     checkUnchanged(current);corrective.phase='preflight';await persist();corrective.beforeSchemaValidation=await validate(source,current.meta);corrective.plannedSchemaValidation=await validate(withLocator(source,input,amendment),current.meta);
     corrective.remote=await api.remote(amendment.mainImageUrl,asset);if(corrective.remote?.sha256!==asset.sha256||!(corrective.remote.bytes>0))throw Error('幂等纠正的原首图远端哈希未通过');
     current=await read();if(!current.failure){corrective.consumedWithoutWrite=true;corrective.reason='source_no_longer_failed';corrective.phase='no_corrective_save_needed';corrective.persistedSchemaValidation=await validate(current.response.data,current.meta);journal.resolvedNoWriteVerified=true;await persist();return journal;}checkUnchanged(current);
    }catch(error){corrective.phase='preflight_failed';corrective.lastPreflightError=String(error.message||error);await persist();throw error;}
    corrective.saveIntent={publishId,failedChildId:amendment.failedChildId,amendmentId:correction.id,scope:correction.scope,originalSaveIntentArmedAt:journal.saveIntent.armedAt,armedAt:new Date().toISOString()};corrective.phase='corrective_save_unknown';await persist();
    const view={publishId,mainImageRepair:corrective};
    try{await api.save(page,input,view,async()=>{journal.correctiveSave=view.mainImageRepair;await persist();},{source:journal.beforeSource,amendment:{...amendment,id:correction.id}});}
    catch(error){corrective.lastSaveError=String(error.message||error);await persist();throw error;}
    current=await read();source=current.response.data;
   }
  }
 }
 if(!journal){
  if(same(locator,expectedLocator(input,amendment))){const proof=await validate(source,current.meta);record.mainImageRepair={amendmentId:amendment.id,amendment:clone(amendment),publishId,phase:'already_correct',consumedWithoutWrite:true,saveWasNeeded:false,saveVerified:true,resolvedNoWriteVerified:true,persistedSchemaValidation:proof,lastObservedAt:new Date().toISOString()};await persist();return record.mainImageRepair;}
  if(locator!==undefined&&locator!==null&&!(Array.isArray(locator)&&locator.length===0))throw Error('原MAIN已有不同值，不能覆盖');
  assertFailure(current.failure,amendment,{fingerprint:true});
  if(record.failureObservation?.responseFingerprint!==amendment.failureResponseFingerprint)throw Error('MAIN修复缺少匹配的正式持久失败观察');
  journal=record.mainImageRepair={amendmentId:amendment.id,amendment:clone(amendment),publishId,phase:'preflight',beforeSource:clone(source),
   beforeBusinessProjection:mainImageBusinessProjection(source),beforeAttributes:{parent:clone(source.extra.attributes),children:source.items.map(row=>({id:String(row.id),sku:row.sku,attributes:clone(row.extra.attributes)}))},saveWasNeeded:true,retry:{},createdAt:new Date().toISOString()};
  await persist();
 }
 if(journal.consumedWithoutWrite)return journal;
 if(!journal.saveIntent){
  try{
   assertFailure(current.failure,amendment,{fingerprint:true});
   if(!same(mainImageBusinessProjection(source),journal.beforeBusinessProjection))throw Error('MAIN预检查原业务字段变化，未保存');
   journal.phase='preflight';await persist();journal.beforeSchemaValidation=await validate(source,current.meta);journal.plannedSchemaValidation=await validate(withLocator(source,input,amendment),current.meta);
   journal.remote=await api.remote(amendment.mainImageUrl,asset);if(journal.remote?.sha256!==asset.sha256||!(journal.remote.bytes>0))throw Error('原主图远端SHA256未通过，未保存');
   current=await read();if(!current.failure)return consumeNoWrite(current);assertFailure(current.failure,amendment,{fingerprint:true});
   if(!same(mainImageBusinessProjection(current.response.data),journal.beforeBusinessProjection))throw Error('MAIN保存前原业务字段变化，未保存');
  }catch(error){journal.phase='preflight_failed';journal.lastPreflightError=String(error.message||error);await persist();throw error;}
  journal.saveIntent={publishId,failedChildId:amendment.failedChildId,amendmentId:amendment.id,armedAt:new Date().toISOString()};journal.phase='save_unknown';await persist();
  try{await api.save(page,input,record,persist,{source:journal.beforeSource,amendment});}catch(error){journal.lastSaveError=String(error.message||error);await persist();throw error;}
  current=await read();source=current.response.data;
 }
 if(!journal.saveIntent)throw Error('原MAIN预检查未完成，未自动补发保存');
 const expected=withLocator(journal.beforeSource,input,amendment);
 if(!same(mainImageBusinessProjection(source),mainImageBusinessProjection(expected))){journal.phase='save_unknown';journal.lastReadAt=new Date().toISOString();await persist();throw Error('原MAIN保存尚未完整回读或其他业务字段变化，不再次保存');}
 journal.persistedSchemaValidation=await validate(source,current.meta);journal.saveVerified=true;journal.saveVerifiedAt=new Date().toISOString();
 if(journal.correctiveSave?.saveIntent){journal.correctiveSave.saveVerified=true;journal.correctiveSave.phase='corrective_save_verified';journal.correctiveSave.persistedSchemaValidation=clone(journal.persistedSchemaValidation);journal.correctiveSave.saveVerifiedAt=journal.saveVerifiedAt;journal.saveVerifiedByCorrectiveId=journal.correctiveSave.amendmentId;}
 journal.lastObservation={status:source.status,failed:Boolean(current.failure),pending:current.pending,observedAt:new Date().toISOString()};await persist();
 if(journal.retry?.intent)return journal;
 if(!current.failure){journal.phase='saved_no_retry_needed';await persist();return journal;}
 assertFailure(current.failure,amendment);
 journal.retry={intent:{publishId,scope:'original_failed_family',amendmentId:amendment.id,armedAt:new Date().toISOString()},phase:'retry_unknown',requestAccepted:false};journal.phase='retry_unknown';await persist();
 const view={publishId,mediaRecovery:journal.retry};
 try{await api.retry(page,input,view,async()=>{journal.retry=view.mediaRecovery;await persist();});}
 catch(error){journal.lastRetryError=String(error.message||error);await persist();throw error;}
 const request=journal.retry.nativeRequests?.[0];
 if(journal.retry.nativeRequests?.length!==1||request.method!=='POST'||request.url!==retryEndpoint||!same(request.payload,{ids:[Number(publishId)]})||request.response?.httpStatus!==200||request.response.body?.code!==0)throw Error('原任务MAIN恢复后的再次发布响应未知，仅回读同一任务');
 journal.retry.requestAccepted=true;journal.retry.phase='request_accepted';journal.phase='retry_request_accepted';await persist();return journal;
}
