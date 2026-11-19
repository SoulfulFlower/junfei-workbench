// Existing UK task only. Attribute representation and fact repair have their
// own durable Save/retry intents; neither can replay MAIN/media recovery.
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,readNativePublication} from './ego-publish-native.mjs';
import {patchMainImageSavePayload,mainImageBusinessProjection,mainImageSaveConfirmationStable,mainImageSaveGuardSnapshot} from './ego-publication-main-image.mjs';
import {installUkSchemaObservation,ukSchemaObservationSnapshot,ukSchemaObservationReady,releaseUkSchemaObservation} from './ego-uk-draft.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';
import {submitNativeMediaRecovery} from './ego-publication-recovery.mjs';

const clone=v=>structuredClone(v),canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
export const requiredAttributesSourceFingerprint=value=>createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const schemaOf=m=>typeof m.schema_content==='string'?JSON.parse(m.schema_content):m.schema_content;
const records=s=>[{id:s.sku,attributes:s.extra.attributes},...s.items.map(r=>({id:r.sku,attributes:r.extra.attributes}))];
const fields=['outer.material','weave_type','item_type_name'];
const messageField=m=>/外部材料|outer material/i.test(m)?fields[0]:/编织类型|weave type/i.test(m)?fields[1]:/产品类型名称|item type name/i.test(m)?fields[2]:null;

export function assertRequiredAttributeFailure(observation,amendment,{fingerprint=false}={}){
 if(!observation||observation.status!=='failed'||observation.identityVerified!==true||observation.unscopedMessageCount!==0||
    observation.count!==observation.childCount||observation.acceptedCount!==0||observation.messageCount!==observation.childCount*3||
    observation.children.some(row=>row.status!=='failed'||row.imagesSource!=='child_gallery'||row.messages.length!==3||
     row.messages.some(m=>m.code!=='90220'||!messageField(m.message))||new Set(row.messages.map(m=>messageField(m.message))).size!==3)||
    (fingerprint&&observation.responseFingerprint!==amendment.failureResponseFingerprint))throw Error('仅可修复原英国任务全部子体的三项90220必填属性缺失');
 if(!same(observation.children.map(r=>({id:String(r.childId),sku:r.sku})),amendment.children))throw Error('90220原子体ID或SKU范围变化');
}

function authorize(input,record,amendment){
 const expected=assertPublicationInput(input),publishId=String(record.publishId);
 if(input.marketplace!=='UK'||input.destination.countryCode!=='GB'||!/^\d+$/.test(publishId)||
    record.fingerprint!==publicationFingerprint(expected)||String(record.identity?.publishId)!==publishId||
    String(record.sourceLink?.publishId)!==publishId||String(record.sourceLink?.draftId)!==String(input.destination.draftId))throw Error('必填属性修复缺少原英国受理身份');
 if(!amendment?.id||amendment.scope!=='repair_original_failed_required_attributes'||amendment.marketplace!=='UK'||
    amendment.retryOriginalTaskAfterVerifiedSave!==true||!Number.isFinite(amendment.authorizedAt)||amendment.authorizedAt<=0||
    !/^[a-f0-9]{64}$/.test(amendment.sourceFingerprint||'')||!/^[a-f0-9]{64}$/.test(amendment.failureResponseFingerprint||'')||
    !same(amendment.facts,{outerMaterial:'100% polyester',weaveType:'Knit',itemTypeName:'Sweatshirt'})||
    !same(amendment.representation,{explicitCommonAttributes:true,exactNumericTypes:true,independentInventory:true,unknownGbpRrpZero:true}))throw Error('缺少冻结的三事实和显式属性表示修复授权');
 for(const [k,v]of Object.entries({accountId:input.accountId,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,
  publishId,destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),erpAccountId:String(input.destination.erpAccountId),
  marketId:String(input.destination.marketId),countryCode:'GB',store:input.store,parentSku:input.goods.parentSku,schemaHash:input.destination.schemaHash})){
  if(v===undefined||amendment[k]===undefined||String(amendment[k])!==String(v))throw Error('必填修复原身份不符：'+k);
 }
 if(!record.sourceEvidence||publicationFailureObservation({code:0,data:record.sourceEvidence},input,publishId)!==null)throw Error('原英国受理历史不完整');
 if(record.requiredAttributeRepair&&record.requiredAttributeRepair.amendmentId!==amendment.id)throw Error('已有另一必填修复检查点');
 const e=amendment.evidence;
 if(!e||e.sourceUrl!==input.goods.sourceUrl||!/^https:\/\/detail\.1688\.com\/offer\/\d+\.html$/.test(e.sourceUrl)||
    !/Material:\s*100%\s*polyester(?:\n|$)/i.test(input.goods.description.replace(/<br\s*\/?\s*>/gi,'\n'))||
    !/工艺\s*[:：]?\s*针织/.test(e.weaveText||'')||!e.materialText?.includes('100%')||!e.itemTitle?.includes('卫衣')||
    !/Sweatshirts\s*$/i.test(e.categoryPath||'')||!Array.isArray(e.artifacts)||!e.artifacts.length||
    e.artifacts.some(x=>!x.path||!/^[a-f0-9]{64}$/.test(x.sha256||'')))throw Error('三项事实缺少同款供应商直接证据');
 return publishId;
}

function assertSchema(meta,input,frozen,amendment){
 if(meta.country_code!=='GB'||meta.locale!=='en_GB'||meta.product_type_name!=='SWEATSHIRT'||meta.hash!==amendment.schemaHash||
    frozen?.hash!==meta.hash||!same(schemaOf(meta),schemaOf(frozen))||schemaOf(meta)?.$defs?.marketplace_id?.default!==input.destination.marketplaceId)throw Error('缺少原英国SWEATSHIRT真实完整schema');
}

// Full explicit raw attributes, not an inherited validation projection.
export function buildRequiredAttributesSource(source,input,meta,amendment){
 const schema=schemaOf(meta),props=schema.properties,market=input.destination.marketplaceId,language=input.destination.languageTag;
 const localized=(key,value)=>{const p=props[key]?.items?.properties;if(!p?.value||typeof value!=='string'||!value.trim())throw Error('原公共字段或schema缺失：'+key);return{value,...(p.language_tag?{language_tag:language}:{}),...(p.marketplace_id?{marketplace_id:market}:{})};};
 const next=clone(source),parent=next.extra.attributes;
 const columns={brand:source.brand,manufacturer:source.manufacturer,item_name:source.title,country_of_origin:source.country_of_origin,product_description:source.extra.product_description};
 for(const [key,value]of Object.entries(columns)){const attr=[localized(key,value)];if(parent[key]&&!same(parent[key],attr))throw Error('原公共列与属性冲突：'+key);parent[key]=attr;}
 const bullets=source.extra.bullet_point?.map(value=>localized('bullet_point',value));if(!bullets?.length||parent.bullet_point&&!same(parent.bullet_point,bullets))throw Error('原五点字段缺失或冲突');parent.bullet_point=bullets;
 const facts={outer:[{material:[{value:amendment.facts.outerMaterial,language_tag:language}],marketplace_id:market}],
  weave_type:[localized('weave_type',amendment.facts.weaveType)],item_type_name:[localized('item_type_name',amendment.facts.itemTypeName)]};
 for(const [k,v]of Object.entries(facts)){if(parent[k]&&!same(parent[k],v))throw Error('已有属性与获授权事实冲突：'+k);parent[k]=v;}
 const lp=props.list_price?.items,p=lp?.properties;
 if(p?.currency?.enum?.length!==1||p.currency.enum[0]!=='GBP'||p.value_with_tax?.minimum!==0||
    !/unable to provide a value, enter 0/i.test(p.value_with_tax?.description||'')||source.list_price!==null)throw Error('未知GBP参考价缺少明确零占位依据');
 const sentinel=[{currency:'GBP',value_with_tax:0,marketplace_id:market}];if(parent.list_price&&!same(parent.list_price,sentinel))throw Error('不得覆盖原参考价');parent.list_price=sentinel;
 const handling=Number(input.handlingDays),fulfill=row=>{if(!Number.isSafeInteger(row.quantity)||row.quantity<0||!Number.isSafeInteger(handling)||handling<0||handling>30)throw Error('原独立库存或处理时间不完整');return[{fulfillment_channel_code:'DEFAULT',quantity:row.quantity,lead_time_to_ship_max_days:handling}];};
 const old=source.extra.attributes.fulfillment_availability;
 if(old?.length!==1||old[0].fulfillment_channel_code!=='DEFAULT'||Number(old[0].lead_time_to_ship_max_days)!==handling||
    old[0].is_inventory_available!==undefined||(old[0].quantity!==undefined&&Number(old[0].quantity)!==source.quantity))throw Error('原库存属性与实际列冲突');
 parent.fulfillment_availability=fulfill(source);
 const normalize=(v,d)=>{if(d?.$ref?.startsWith('#/$defs/'))d=schema.$defs[d.$ref.slice(8)];if(Array.isArray(v))return v.map(x=>normalize(x,d?.items));
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,normalize(x,d?.properties?.[k])]));
  if(typeof v==='string'&&['number','integer'].includes(d?.type)){if(!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(v))throw Error('原数值不能精确类型化');const n=Number(v);if(!Number.isFinite(n)||(d.type==='integer'&&!Number.isSafeInteger(n))||String(n)!==v.replace(/\.0+$/,''))throw Error('原数值类型化将改变值');return n;}return v;};
 next.extra.attributes=normalize(parent,{properties:props});
 const common=new Set(['neck','style','closure','fit_type','department','model_name','unit_count','fabric_type','model_number','target_gender','number_of_items','care_instructions','special_size_type','import_designation','item_package_weight','age_range_description','title_differentiation','item_package_dimensions','supplier_declared_dg_hz_regulation','condition_type','supplier_declared_has_product_identifier_exemption','merchant_shipping_group',...Object.keys(columns),'bullet_point',...Object.keys(facts),'list_price']);
 const privateKeys=new Set(['color','color_name','apparel_size','shirt_size','size','size_name','fulfillment_availability','parentage_level','child_parent_sku_relationship','variation_theme','skip_offer','relationships','parent_sku','relationship_type']);
 if(Object.keys(parent).some(k=>!common.has(k)&&!privateKeys.has(k)))throw Error('原公共属性包含未分类字段，不盲目继承');
 for(const row of next.items){const original=row.extra.attributes,attrs=Object.fromEntries([...common].filter(k=>Object.hasOwn(next.extra.attributes,k)).map(k=>[k,clone(next.extra.attributes[k])]));
  for(const [k,v]of Object.entries(original)){if(common.has(k)&&Object.hasOwn(attrs,k)&&!same(normalize(v,props[k]),attrs[k]))throw Error('子体公共事实与父公共事实冲突：'+row.sku+' '+k);attrs[k]=clone(v);}
  attrs.fulfillment_availability=fulfill(row);row.extra.attributes=normalize(attrs,{properties:props});
 }
 return next;
}

function businessWithoutAttributes(source){const p=mainImageBusinessProjection(source);delete p.parent.extra.attributes;for(const row of p.children)delete row.extra.attributes;return p;}
export function verifyRequiredAttributesReadback(source,planned){
 if(!same(businessWithoutAttributes(source),businessWithoutAttributes(planned))||!same(records(source),records(planned)))throw Error('原任务属性或非属性业务回读不符');return true;
}

export async function readRequiredAttributesSource(page,input,publishId){
 const token='required-schema:'+Date.now()+':'+Math.random();
 await page.evaluate(installUkSchemaObservation,token);
 try{const s=await page.evaluate(ukSchemaObservationSnapshot,token);if(!s.present||s.token!==token||!s.bindings.open||!s.bindings.send)throw Error('必填schema观察未绑定');
  const response=await readNativePublication(page,publishId);await page.waitForFunction(ukSchemaObservationReady,token,{timeout:20000});return{response,meta:await page.evaluate(()=>window.__ukSchema.data)};
 }finally{await page.evaluate(releaseUkSchemaObservation,token);}
}

export function patchRequiredAttributesSavePayload(body,plan){
 const out=patchMainImageSavePayload(body,plan);out.attributes=plan.attributes.parent;
 for(const row of out.items){const attrs=plan.attributes.children[String(row.id)];if(!attrs)throw Error('必填保存缺少原子体属性');row.attributes=attrs;}
 return out;
}
function installGuardBody(plan){
 if(window.__requiredAttributesSave)throw Error('已有必填保存观察');
 const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,fetch=window.fetch,targets=new WeakMap();
 const state={open,send,fetch,guardId:plan.guardId,requests:[],readOnlyQueries:[],error:null};window.__requiredAttributesSave=state;
 // These exact editor queries check language and an existing exemption.
 const readonly=(method,url,body)=>{
  if(method!=='POST'||url.origin!=='https://app.junfeikuajing.com')return false;let value;try{value=JSON.parse(body);}catch{return false;}
  const language=url.pathname==='/api/common/language-by-market'&&value&&Object.keys(value).length===0;
  const keys=['seller_id','country_code','primary_category_name','product_type_name','brand'];
  const check=url.pathname==='/api/amazon/category/upc-exemption/check'&&value&&JSON.stringify(Object.keys(value).sort())===JSON.stringify(keys.sort())&&
   value.seller_id===plan.source.seller_id&&value.country_code===plan.source.country_code&&value.primary_category_name==='Fashion'&&value.product_type_name===plan.source.product_type_name&&String(value.brand).toUpperCase()===String(plan.source.brand).toUpperCase();
  if(language||check){state.readOnlyQueries.push({method,url:url.href,payload:value,observedAt:new Date().toISOString()});return true;}return false;
 };
 const hookedOpen=function(m,u,...rest){targets.set(this,{method:String(m).toUpperCase(),url:new URL(u,location.href)});return open.call(this,m,u,...rest);};
 const hookedSend=function(body){const r=targets.get(this);if(!r||['GET','HEAD'].includes(r.method)||readonly(r.method,r.url,body))return send.call(this,body);
  try{if(state.error||state.requests.length||r.method!=='POST'||r.url.href!=='https://app.junfeikuajing.com/api/amazon/goods/publish/json-update')throw Error('拦截非原任务保存或重复写入');
   const payload=patchRequiredAttributesSavePayload(JSON.parse(body),plan),entry={method:r.method,url:r.url.href,payload,sentAt:new Date().toISOString(),response:null};state.requests.push(entry);
   this.addEventListener('loadend',()=>{let body;try{body=JSON.parse(this.responseText);}catch{}entry.response={httpStatus:this.status,body};},{once:true});return send.call(this,JSON.stringify(payload));
  }catch(e){state.error=e.message;throw e;}};
 state.hookedOpen=hookedOpen;state.hookedSend=hookedSend;XMLHttpRequest.prototype.open=hookedOpen;XMLHttpRequest.prototype.send=hookedSend;
 state.hookedFetch=function(input,init){const m=String(init?.method||input?.method||'GET').toUpperCase(),url=new URL(typeof input==='string'?input:input?.url,location.href);if(!['GET','HEAD'].includes(m)&&!readonly(m,url,typeof init?.body==='string'?init.body:'')){state.error='拦截非原XHR保存写入';return Promise.reject(Error(state.error));}return fetch.apply(this,arguments);};window.fetch=state.hookedFetch;
 return{installed:true,guardId:state.guardId};
}
export const installRequiredAttributesSaveGuard=new Function('plan','const patchMainImageSavePayload='+patchMainImageSavePayload.toString()+';const patchRequiredAttributesSavePayload='+patchRequiredAttributesSavePayload.toString()+';return ('+installGuardBody.toString()+')(plan);');
// A second narrowly authorized repair may reuse the same transport mechanics,
// while keeping its own patch function and browser observation namespace.
export function createSourcePreservingSaveGuard(patchFunction,stateName){
 if(typeof patchFunction!=='function'||!/^__[A-Za-z]+$/.test(stateName))throw Error('保存观察编译参数无效');
 return new Function('plan','const patchMainImageSavePayload='+patchMainImageSavePayload.toString()+';const patchRequiredAttributesSavePayload='+patchFunction.toString()+';return ('+installGuardBody.toString().replaceAll('__requiredAttributesSave',stateName)+')(plan);');
}
export const requiredAttributesSaveSnapshot=new Function('const snapshot=('+mainImageSaveGuardSnapshot.toString().replaceAll('__mainImageSave','__requiredAttributesSave')+')();snapshot.readOnlyQueries=window.__requiredAttributesSave?.readOnlyQueries||[];return snapshot;');
export const requiredAttributesConfirmationStable=new Function('expectedGuardId','return ('+mainImageSaveConfirmationStable.toString().replaceAll('__mainImageSave','__requiredAttributesSave')+')(expectedGuardId);');
const guardOk=(s,id)=>s?.present&&s.guardId===id&&s.prototypeBound&&s.fetchBound&&!s.requests.length&&!s.error;

export function nativeSourceSaveReady(p){
 const rows=[...document.querySelectorAll('.el-table__body-wrapper tr')].filter(r=>r.querySelector('input[placeholder="sku"]'));
 const skus=rows.map(r=>r.querySelector('input[placeholder="sku"]').value);
 const buttons=[...document.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().width&&!b.disabled&&b.innerText.replace(/\s/g,'')==='保存'&&[...b.parentElement.querySelectorAll('button')].some(s=>s.innerText.replace(/\s/g,'')==='保存并发布'));
 return location.href===p.url&&document.readyState==='complete'&&document.title==='Amazon产品编辑 - 钧飞跨境'&&
  document.querySelector('input[placeholder="店铺"]')?.value===p.store&&document.querySelector('input[placeholder="产品标题"]')?.value===p.title&&
  skus.length===p.skus.length&&new Set(skus).size===skus.length&&JSON.stringify([...skus].sort())===JSON.stringify([...p.skus].sort())&&buttons.length===1&&
  ![...document.querySelectorAll('.el-message-box')].some(e=>e.getBoundingClientRect().width);
}

export async function submitNativeRequiredAttributesSave(page,input,record,persist,{source,planned,amendment,armSaveIntent}){
 const j=record.requiredAttributeRepair;if(!j||j.saveIntent||j.nativeRequests?.length||typeof armSaveIntent!=='function')throw Error('必填保存缺少点击前持久意图回调或已有意图');
 const plan={source,guardId:amendment.id,variationFields:input.destination.variationFields,attributes:{parent:planned.extra.attributes,children:Object.fromEntries(planned.items.map(r=>[String(r.id),r.extra.attributes]))}};
 await page.waitForFunction(nativeSourceSaveReady,{url:'https://www.junfeikuajing.com/#/amazon/product/'+source.id+'?type=publish',store:input.store,title:source.title,skus:source.items.map(r=>r.sku)},{timeout:60000});
 try{const installed=await page.evaluate(installRequiredAttributesSaveGuard,plan),proof=await page.evaluate(requiredAttributesSaveSnapshot);
  if(!installed?.installed||!guardOk(proof,amendment.id))throw Error('必填保存护栏未绑定，未点击');j.guardInstallProof=proof;await persist();
  const selector=await page.evaluate(()=>{const es=[...document.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().width&&!b.disabled&&b.innerText.replace(/\s/g,'')==='保存'&&[...b.parentElement.querySelectorAll('button')].some(s=>s.innerText.replace(/\s/g,'')==='保存并发布'));if(es.length!==1)throw Error('原任务保存按钮不唯一');es[0].setAttribute('data-required-save','true');es[0].scrollIntoView({block:'center'});return '[data-required-save]';});
  if(!guardOk(await page.evaluate(requiredAttributesSaveSnapshot),amendment.id))throw Error('点击保存前护栏失效');await armSaveIntent();
  if(!j.saveIntent||!guardOk(await page.evaluate(requiredAttributesSaveSnapshot),amendment.id))throw Error('保存意图持久化后护栏失效');await page.click(selector);
  await page.waitForFunction(()=>window.__requiredAttributesSave?.requests.some(r=>r.response)||window.__requiredAttributesSave?.error||[...document.querySelectorAll('.el-message-box')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:20000});
  const boxes=await page.evaluate(()=>[...document.querySelectorAll('.el-message-box')].filter(e=>e.getBoundingClientRect().width).map(e=>e.innerText));
  if(boxes.length){if(boxes.length!==1||!boxes[0].includes('颜色')||!boxes[0].includes('不在亚马逊选项中。确定要保存吗？')||/发布|删除/.test(boxes[0])||![...new Set(input.goodsItems.map(r=>r.color))].every(c=>boxes[0].includes(c)))throw Error('非原颜色确认，未继续');
   j.enumConfirmation=boxes[0];await persist();await page.waitForFunction(requiredAttributesConfirmationStable,amendment.id,{timeout:10000});
   const confirm=await page.evaluate(()=>{const boxes=[...document.querySelectorAll('.el-message-box')].filter(e=>e.getBoundingClientRect().width),es=boxes.length===1?[...boxes[0].querySelectorAll('button')].filter(b=>!b.disabled&&b.innerText.trim()==='确定'):[];if(es.length!==1)throw Error('原颜色确认不唯一');es[0].setAttribute('data-required-confirm','true');return '[data-required-confirm]';});
   await page.focus(confirm);
   const p=await page.evaluate(requiredAttributesSaveSnapshot);if(!guardOk(p,amendment.id)||p.url!==proof.url)throw Error('确认前必填保存护栏失效');j.confirmGuardProof=p;j.confirmMethod='native_focus_enter';await persist();await page.press(confirm,'Enter');
  }
  await page.waitForFunction(()=>window.__requiredAttributesSave?.requests.some(r=>r.response)||window.__requiredAttributesSave?.error,undefined,{timeout:25000});
 }finally{
  try{const s=await page.evaluate(requiredAttributesSaveSnapshot);j.lastGuardSnapshot=s;j.nativeRequests=s.requests;if(s.error)j.guardError=s.error;await persist();}
  finally{await page.evaluate(()=>{const s=window.__requiredAttributesSave;if(s){if(XMLHttpRequest.prototype.open===s.hookedOpen)XMLHttpRequest.prototype.open=s.open;if(XMLHttpRequest.prototype.send===s.hookedSend)XMLHttpRequest.prototype.send=s.send;if(window.fetch===s.hookedFetch)window.fetch=s.fetch;delete window.__requiredAttributesSave;}});}
 }
 const r=j.nativeRequests?.[0];if(j.nativeRequests?.length!==1||r.response?.httpStatus!==200||r.response.body?.code!==0)throw Error('必填保存结果未知，仅回读原ID');j.saveAcknowledgedAt=new Date().toISOString();await persist();
}

export function assertRequiredAttributesPreclickEligibility(j,amendment){
 const url='https://www.junfeikuajing.com/#/amazon/product/'+amendment.publishId+'?type=publish';
 const suffix='; last URL was "'+url+'"; last title was "Amazon产品编辑 - 钧飞跨境".';
 if(!j||j.amendmentId!==amendment.id||j.phase!=='save_unknown'||!j.saveIntent?.armedAt||
  j.saveIntent.scope!=='one_original_task_native_save'||String(j.saveIntent.publishId)!==String(amendment.publishId)||
  typeof j.lastSaveError!=='string'||!/^page\.waitForFunction timed out after 20000ms on page p\d+;/.test(j.lastSaveError)||!j.lastSaveError.endsWith(suffix)||
  ['guardInstallProof','lastGuardSnapshot','nativeRequests','guardError','saveVerified','preclickSaveRecovery'].some(k=>Object.hasOwn(j,k))||
  j.retry?.intent||!j.beforeSource||!j.plannedSource||requiredAttributesSourceFingerprint(j.beforeSource)!==amendment.sourceFingerprint)throw Error('不是已核实的原20秒页面就绪前超时，不能建立另一保存机会');
}

function preclickSaveJournal(j,amendment){
 const a=amendment.preclickSaveRecovery;if(!a)return j;
 if(!a.id||a.scope!=='resume_original_required_attributes_preclick_save'||!Number.isFinite(a.authorizedAt)||a.authorizedAt<=0||
  a.originalMainAmendmentId!==amendment.id||a.originalSaveIntentArmedAt!==j.saveIntent?.armedAt||a.originalLastSaveError!==j.lastSaveError||
  a.beforeSourceFingerprint!==requiredAttributesSourceFingerprint(j.beforeSource)||a.plannedSourceFingerprint!==requiredAttributesSourceFingerprint(j.plannedSource)||
  !same(a.children,amendment.children)||a.retryOriginalTaskAfterVerifiedSave!==true)throw Error('页面就绪前纠正缺少独立冻结范围');
 for(const key of ['accountId','productId','jobId','snapshotSha256','publishId','destinationId','draftId','erpAccountId','marketId','countryCode','store','parentSku','schemaHash','sourceFingerprint','failureResponseFingerprint'])if(String(a[key])!==String(amendment[key]))throw Error('页面就绪前纠正原身份变化：'+key);
 if(j.preclickSaveRecovery){if(j.preclickSaveRecovery.amendmentId!==a.id)throw Error('已有另一页面就绪前纠正检查点');return j.preclickSaveRecovery;}
 assertRequiredAttributesPreclickEligibility(j,amendment);
 return j.preclickSaveRecovery={amendmentId:a.id,amendment:clone(a),phase:'preflight',publishId:j.publishId,originalSaveIntent:clone(j.saveIntent),originalLastSaveError:j.lastSaveError};
}

function retryPreflightJournal(j,amendment){
 const a=amendment.retryPreflightRecovery;if(!a)return j.retry;
 const original=j.retry,saved=j.preclickSaveRecovery||j,request=saved.nativeRequests?.[0],proof=j.schemaValidationAfterSave;
 if(!a.id||a.scope!=='resume_original_required_attributes_retry_preflight'||!Number.isFinite(a.authorizedAt)||a.authorizedAt<=0||
  a.originalMainAmendmentId!==amendment.id||a.originalRetryIntentArmedAt!==original.intent?.armedAt||
  a.originalRetryLastError!==original.lastError||original.lastError!=='原失败任务行或店铺不唯一，未再次发布'||
  Object.hasOwn(original,'nativeRequests')||Object.hasOwn(original,'guardError')||original.intent?.scope!=='original_family_all_children'||
  String(original.intent?.publishId)!==String(amendment.publishId)||j.saveVerified!==true||a.originalSaveVerifiedAt!==j.saveVerifiedAt||
  a.plannedSourceFingerprint!==requiredAttributesSourceFingerprint(j.plannedSource)||saved.saveVerified!==true||saved.nativeRequests?.length!==1||
  request?.method!=='POST'||request.url!=='https://app.junfeikuajing.com/api/amazon/goods/publish/json-update'||request.response?.httpStatus!==200||request.response.body?.code!==0||
  !proof?.passed||proof.checkedCount!==amendment.children.length+1||proof.schemaHash!==amendment.schemaHash||!same(a.children,amendment.children))throw Error('缺少原保存已核实且重试前置行拒绝的独立范围');
 for(const key of ['accountId','productId','jobId','snapshotSha256','publishId','destinationId','draftId','erpAccountId','marketId','countryCode','store','parentSku','schemaHash','sourceFingerprint','failureResponseFingerprint'])if(String(a[key])!==String(amendment[key]))throw Error('重试前置纠正原身份变化：'+key);
 if(j.retryPreflightRecovery){if(j.retryPreflightRecovery.amendmentId!==a.id)throw Error('已有另一原任务重试前置纠正');return j.retryPreflightRecovery;}
 return j.retryPreflightRecovery={amendmentId:a.id,amendment:clone(a),phase:'preflight',originalRetry:clone(original)};
}

export async function repairNativeRequiredAttributes(page,input,record,persist,{amendment,schemaObservation,...adapters}={}){
 const publishId=authorize(input,record,amendment),api={read:readRequiredAttributesSource,save:submitNativeRequiredAttributesSave,validate:validateSchemaAttributes,remote:verifyRemoteAsset,retry:submitNativeMediaRecovery,...adapters};
 const runtimeInput={...input,runtime:amendment.runtime},observed=await api.read(page,runtimeInput,publishId);assertSchema(observed.meta,input,schemaObservation,amendment);
 let failure,pending=false;try{failure=publicationFailureObservation(observed.response,input,publishId);}catch(e){if(e.code==='ERP_PUBLICATION_PENDING')pending=true;else throw e;}
 let j=record.requiredAttributeRepair;
 if(!j){
  j=record.requiredAttributeRepair={amendmentId:amendment.id,amendment:clone(amendment),publishId,phase:'preflight',createdAt:new Date().toISOString(),
   originalAcceptedIdentity:clone(record.identity),originalAcceptedSourceEvidence:clone(record.sourceEvidence),originalSourceLink:clone(record.sourceLink),originalFailureObservation:clone(record.failureObservation),retry:{}};await persist();
 }
 const saveJournal=preclickSaveJournal(j,amendment);await persist();
 if(j.consumedWithoutWrite||saveJournal.consumedWithoutWrite)return record;
 if(!saveJournal.saveIntent&&!failure){saveJournal.consumedWithoutWrite=true;saveJournal.phase='source_no_longer_failed';saveJournal.observedPending=pending;await persist();return record;}
 if(!j.beforeSource){assertRequiredAttributeFailure(failure,amendment,{fingerprint:true});if(requiredAttributesSourceFingerprint(observed.response.data)!==amendment.sourceFingerprint)throw Error('原90220源资料指纹变化');j.beforeSource=clone(observed.response.data);j.plannedSource=buildRequiredAttributesSource(j.beforeSource,input,observed.meta,amendment);await persist();}
 const verify=async source=>{verifyRequiredAttributesReadback(source,j.plannedSource);const proof=await api.validate(observed.meta,records(source),runtimeInput);if(!proof.passed||proof.checkedCount!==source.items.length+1||proof.schemaHash!==observed.meta.hash)throw Error('必填修复完整raw schema证明不符');return proof;};
 if(!saveJournal.saveIntent){
  assertRequiredAttributeFailure(failure,amendment);if(!same(mainImageBusinessProjection(observed.response.data),mainImageBusinessProjection(j.beforeSource)))throw Error('原资料变化，未保存');
  if(saveJournal!==j&&requiredAttributesSourceFingerprint(observed.response.data)!==amendment.preclickSaveRecovery.beforeSourceFingerprint)throw Error('纠正前原完整资料或版本已变化');
  saveJournal.schemaValidationBeforeSave=await api.validate(observed.meta,records(j.plannedSource),runtimeInput);if(!saveJournal.schemaValidationBeforeSave.passed||saveJournal.schemaValidationBeforeSave.checkedCount!==input.goodsItems.length+1||saveJournal.schemaValidationBeforeSave.schemaHash!==observed.meta.hash)throw Error('候选raw schema未完整通过');await persist();
  saveJournal.remoteChecks=[];for(const asset of new Map(input.assets.map(a=>[a.sha256,a])).values()){const proof=await api.remote(input.urls[asset.sha256],asset);if(proof.sha256!==asset.sha256||!(proof.bytes>0))throw Error('原图片文件哈希不符');saveJournal.remoteChecks.push({sha256:asset.sha256,url:input.urls[asset.sha256],proof});await persist();}
  const fresh=await api.read(page,runtimeInput,publishId);assertSchema(fresh.meta,input,schemaObservation,amendment);
  let now;try{now=publicationFailureObservation(fresh.response,input,publishId);}catch(e){if(e.code==='ERP_PUBLICATION_PENDING')now=null;else throw e;}
  if(!now){saveJournal.consumedWithoutWrite=true;saveJournal.phase='source_no_longer_failed';await persist();return record;}
  assertRequiredAttributeFailure(now,amendment);if(!same(mainImageBusinessProjection(fresh.response.data),mainImageBusinessProjection(j.beforeSource)))throw Error('保存前原业务已变化');
  if(saveJournal!==j&&requiredAttributesSourceFingerprint(fresh.response.data)!==amendment.preclickSaveRecovery.beforeSourceFingerprint)throw Error('点击前原完整资料或版本变化');
  const armSaveIntent=async()=>{if(saveJournal.saveIntent)throw Error('已有保存意图，不重放');saveJournal.saveIntent={publishId,armedAt:new Date().toISOString(),scope:'one_original_task_native_save'};saveJournal.phase='save_unknown';await persist();};
  const view=saveJournal===j?record:{...record,requiredAttributeRepair:saveJournal};
  try{await api.save(page,runtimeInput,view,persist,{source:j.beforeSource,planned:j.plannedSource,amendment:saveJournal===j?amendment:amendment.preclickSaveRecovery,armSaveIntent});if(!saveJournal.saveIntent)throw Error('保存未持久记录意图');}
  catch(e){if(saveJournal.saveIntent)saveJournal.lastSaveError=String(e.message);else saveJournal.lastPreparationError=String(e.message);await persist();throw e;}
  const after=await api.read(page,runtimeInput,publishId);assertSchema(after.meta,input,schemaObservation,amendment);observed.response=after.response;
 }
 j.schemaValidationAfterSave=await verify(observed.response.data);j.saveVerified=true;j.saveVerifiedAt??=new Date().toISOString();j.phase='save_verified';if(!saveJournal.saveVerified){saveJournal.saveVerified=true;saveJournal.phase='save_verified';}await persist();
 let current;try{current=publicationFailureObservation(observed.response,input,publishId);}catch(e){if(e.code==='ERP_PUBLICATION_PENDING')current=null;else throw e;}
 const retry=retryPreflightJournal(j,amendment);await persist();if(retry.intent||retry.consumedWithoutWrite)return record;
 if(!current){retry.consumedWithoutWrite=true;retry.phase='source_no_longer_failed';await persist();return record;}
 assertRequiredAttributeFailure(current,amendment);
 const armIntent=async()=>{if(retry.intent)throw Error('原任务重试意图已消费');retry.intent={publishId,armedAt:new Date().toISOString(),scope:'original_family_all_children'};retry.phase='retry_unknown';j.phase='retry_unknown';await persist();};
 const view={publishId,mediaRecovery:retry};try{await api.retry(page,runtimeInput,view,persist,{armIntent});if(!retry.intent)throw Error('原任务重试未持久记录意图');}catch(e){if(retry.intent)retry.lastError=String(e.message);else retry.lastPreparationError=String(e.message);await persist();throw e;}
 const request=retry.nativeRequests?.[0];if(retry.nativeRequests?.length!==1||request.response?.httpStatus!==200||request.response.body?.code!==0)throw Error('原英国恢复结果未知，仅回读原ID');retry.requestAccepted=true;retry.phase='retry_acknowledged';j.phase='retry_acknowledged';await persist();return record;
}
