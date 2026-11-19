// Restore identifiers introduced by native UK copy/editor to the exact
// original US source values. No brand change, code generation or application.
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation} from './ego-publish-native.mjs';
import {extractSourceIdentifiers} from './ego-uk-draft.mjs';
import {readUkExemptionUi} from './ego-uk-exemption.mjs';
import {mainImageBusinessProjection,patchMainImageSavePayload} from './ego-publication-main-image.mjs';
import {readRequiredAttributesSource,requiredAttributesSourceFingerprint,createSourcePreservingSaveGuard,requiredAttributesSaveSnapshot,requiredAttributesConfirmationStable,nativeSourceSaveReady} from './ego-publication-required-attributes.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';
import {submitNativeMediaRecovery} from './ego-publication-recovery.mjs';

const clone=v=>structuredClone(v),canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const schemaOf=m=>typeof m.schema_content==='string'?JSON.parse(m.schema_content):m.schema_content;
const idRow=r=>({standard_product_type:r.standard_product_type,standard_product_id:r.standard_product_id});
export const introducedIdentifiers=source=>({parent:idRow(source),children:Object.fromEntries(source.items.map(r=>[r.sku,idRow(r)]))});
const records=s=>[{id:s.sku,attributes:s.extra.attributes},...s.items.map(r=>({id:r.sku,attributes:r.extra.attributes}))];
const guardOk=(s,id)=>s?.present&&s.guardId===id&&s.prototypeBound&&s.fetchBound&&!s.requests.length&&!s.error;
export const SWEATSHIRT_IDENTIFIER_PROFILE='copied_sweatshirt_gtin_catalog_conflict';
const fold=value=>String(value??'').trim().toLowerCase();
function repairProfile(amendment,input){
 if(amendment?.identifierProfile===SWEATSHIRT_IDENTIFIER_PROFILE){
  if(amendment.productType!=='SWEATSHIRT'||amendment.childCount!==75||amendment.children?.length!==75||
     !same(amendment.expectedErrorCodes,['100980','13013'])||(input&&input.goodsItems.length!==75))throw Error('SWEATSHIRT编码纠正缺少原75SKU/两项错误范围');
  return{type:'SWEATSHIRT',codes:['100980','13013'],count:75};
 }
 if(amendment?.identifierProfile!==undefined)throw Error('未知编码纠正失败profile');
 return{type:'SHIRT',codes:['13013','8566','8572'],count:null};
}

// This legacy task has a real allowed readiness record but no new application.
// A fresh guarded CHECK is required at authorization; each runtime read also
// checks the current native UI before any source-preserving Save.
export function existingIdentifierExemptionProof(record,input,amendment){
 const historical=record.readiness,stored=amendment.exemption,fresh=stored?.freshExemptionCheck,
  ui=fresh?.ui,request=fresh?.request,guard=fresh?.guardProof,payload=request?.payload,response=request?.response;
 const observed=Date.parse(fresh?.observedAt),sent=Date.parse(request?.sentAt),authorized=amendment.authorizedAt*1000;
 const expected={accountId:input.accountId,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,publishId:String(record.publishId),schemaHash:input.destination.schemaHash};
 if(!historical||historical.store!==input.store||fold(historical.brand)!==fold(input.goods.brand)||
    !String(historical.brandStatus).replace(/\s/g,'').includes('UPC豁免：允许销售')||!same(historical.shippingTemplate,input.destination.shippingTemplate)||
    String(historical.handlingDays)!==String(input.handlingDays)||!Number.isFinite(Date.parse(historical.checkedAt))||Date.parse(historical.checkedAt)>observed)
  throw Error('缺少原英国同店品牌允许销售的真实历史证据');
 if(!fresh||!Number.isFinite(observed)||!Number.isFinite(sent)||!Number.isFinite(authorized)||authorized-observed < -60000||authorized-observed>900000||observed-sent<0||observed-sent>900000||
    Object.entries(expected).some(([k,v])=>String(fresh[k])!==String(v))||ui?.url!=='https://www.junfeikuajing.com/#/amazon/product/'+record.publishId+'?type=publish'||
    ui.store!==input.store||fold(ui.brand)!==fold(input.goods.brand)||String(ui.nativeMarketId)!==String(input.destination.marketId)||!String(ui.status).replace(/\s/g,'').includes('UPC豁免：允许销售')||
    request?.kind!=='check'||request.method!=='POST'||request.url!=='https://app.junfeikuajing.com/api/amazon/category/upc-exemption/check'||
    !same(Object.keys(payload||{}).sort(),['seller_id','country_code','primary_category_name','product_type_name','brand'].sort())||
    !payload.seller_id||payload.seller_id!==record.sourceEvidence?.seller_id||payload.country_code!=='GB'||payload.primary_category_name!=='Fashion'||payload.product_type_name!=='SWEATSHIRT'||fold(payload.brand)!==fold(input.goods.brand)||
    response?.httpStatus!==200||response.body?.code!==0||response.body.data?.status!=='available'||response.body.data.status_map?.available!=='允许销售'||
    guard?.present!==true||!guard.token||!same(guard.bindings,{open:true,send:true,fetch:true})||guard.error!==null||!same(guard.requests,[request]))
  throw Error('缺少新鲜原英国SWEATSHIRT同店品牌允许销售的非申请只读检查证据');
 return{kind:'existing_allowed_and_fresh_native_check',historicalReadiness:clone(historical),freshExemptionCheck:clone(fresh),singleApplyCount:0};
}

export function identifierExemptionProof(record,input){
 const response=record?.applyResponse?.response,scope=record?.nativeScope;
 if(record?.applyRequests?.length!==1||!record.applyIntent||record.phase!=='allowed'||record.applicationState!=='available'||
    response?.httpStatus!==200||response.body?.code!==0||!response.body.data?.id||record.latestCheck?.status!=='available'||
    scope?.country_code!=='GB'||scope.product_type_name!=='SHIRT'||scope.primary_category_name!=='Fashion'||
    String(scope.brand).toUpperCase()!==input.goods.brand.toUpperCase()||record.latestCheck?.ui?.store!==input.store||
    record.latestCheck.ui.nativeMarketId!==String(input.destination.marketId))throw Error('缺少原英国单次豁免申请和允许销售证据，不再次申请');
 return{applicationId:String(response.body.data.id),nativeScope:clone(scope),applyIntent:clone(record.applyIntent),allowedAt:record.allowedAt,singleApplyCount:1};
}

export function assertIdentifierFailure(observation,amendment,{fingerprint=false}={}){
 const profile=repairProfile(amendment);
 if(!observation||observation.identityVerified!==true||observation.status!=='failed'||observation.count!==observation.childCount||
    (profile.count!==null&&observation.childCount!==profile.count)||
    observation.acceptedCount!==0||observation.unscopedMessageCount!==0||observation.messageCount!==observation.childCount*profile.codes.length||
    observation.children.some(r=>r.status!=='failed'||r.imagesSource!=='child_gallery'||r.messages.length!==profile.codes.length||
      !same(r.messages.map(m=>String(m.code)).sort(),profile.codes)||
      (profile.count!==null&&!same((r.messages.find(m=>String(m.code)==='100980')?.message||'').match(/(?<!\d)\d{14}(?!\d)/g),[String(amendment.introducedIdentifiers.children[r.sku]?.standard_product_id||'').padStart(14,'0')])) )||
    !same(observation.children.map(r=>({id:String(r.childId),sku:r.sku})),amendment.children)||
    (fingerprint&&observation.responseFingerprint!==amendment.failureResponseFingerprint))throw Error('仅可纠正原英国完整SKU对应profile的编码失败');
}

function assertSchema(meta,input,frozen,amendment){
 const profile=repairProfile(amendment,input);
 if(meta?.country_code!=='GB'||meta.locale!=='en_GB'||meta.product_type_name!==profile.type||meta.hash!==amendment.schemaHash||
    frozen?.hash!==meta.hash||!same(schemaOf(meta),schemaOf(frozen))||schemaOf(meta)?.$defs?.marketplace_id?.default!==input.destination.marketplaceId)throw Error('原英国SHIRT完整schema不符');
}
function authorize(input,record,amendment,sourceEvidence,exemptionRecord){
 const profile=repairProfile(amendment,input);
 const expected=assertPublicationInput(input),publishId=String(record.publishId),proof=extractSourceIdentifiers(sourceEvidence);
 if(input.marketplace!=='UK'||input.destination.countryCode!=='GB'||record.fingerprint!==publicationFingerprint(expected)||
    String(record.identity?.publishId)!==publishId||String(record.sourceLink?.publishId)!==publishId||String(record.sourceLink?.draftId)!==String(input.destination.draftId)||
    !record.sourceEvidence||publicationFailureObservation({code:0,data:record.sourceEvidence},input,publishId)!==null)throw Error('编码纠正缺少原英国完整受理历史');
 if(!amendment?.id||amendment.scope!=='repair_original_failed_identifiers'||amendment.marketplace!=='UK'||
    !Number.isFinite(amendment.authorizedAt)||amendment.authorizedAt<=0||amendment.retryOriginalTaskAfterVerifiedSave!==true||
    !/^[a-f0-9]{64}$/.test(amendment.sourceFingerprint||'')||!/^[a-f0-9]{64}$/.test(amendment.failureResponseFingerprint||'')||
    amendment.sourceEvidenceFingerprint!==requiredAttributesSourceFingerprint(sourceEvidence)||!same(amendment.sourceIdentifiers,proof)||
    proof.parentSku!==input.goods.parentSku||String(sourceEvidence.uid)!==String(input.destination.erpAccountId)||
    sourceEvidence.items.length!==input.goodsItems.length||!same(Object.keys(proof.children).sort(),input.goodsItems.map(r=>r.sku).sort())||
     proof.parent.standard_product_id!==null||proof.parent.standard_product_type!=='UPC'||Object.values(proof.children).some(r=>r.standard_product_id!==null||r.standard_product_type!==null)||
    !same(amendment.exemption,profile.count===75?existingIdentifierExemptionProof(record,input,amendment):identifierExemptionProof(exemptionRecord,input)))throw Error('缺少原US空编码、英国引入编码及原豁免的独立纠正授权');
 for(const [k,v]of Object.entries({accountId:input.accountId,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,publishId,
  destinationId:input.destination.destinationId,draftId:String(input.destination.draftId),erpAccountId:String(input.destination.erpAccountId),
  marketId:String(input.destination.marketId),countryCode:'GB',store:input.store,parentSku:input.goods.parentSku,schemaHash:input.destination.schemaHash})){
  if(v===undefined||amendment[k]===undefined||String(amendment[k])!==String(v))throw Error('编码纠正原身份不符：'+k);
 }
 if(record.identifierRepair&&record.identifierRepair.amendmentId!==amendment.id)throw Error('已有另一编码纠正检查点');
 return publishId;
}

export function buildIdentifierRepairSource(source,input,amendment){
 const profile=repairProfile(amendment,input);
 if(!same(introducedIdentifiers(source),amendment.introducedIdentifiers))throw Error('英国当前引入编码与冻结观察不符');
 const all=[source,...source.items];
  if(all.some(r=>typeof r.standard_product_id!=='string'||!/^\d{12}$/.test(r.standard_product_id)||![null,'UPC'].includes(r.standard_product_type)||
    r.extra?.attributes?.supplier_declared_has_product_identifier_exemption?.[0]?.value!==true||
    r.extra?.attributes?.externally_assigned_product_identifier!==undefined||r.extra?.attributes?.brand?.[0]?.value!==input.goods.brand)||
    new Set(all.map(r=>r.standard_product_id)).size!==all.length||source.brand!==input.goods.brand)throw Error('仅可纠正已豁免且原US未提供的独立英国31类引入编码');
 if(profile.count===75&&(source.product_type_name!=='SWEATSHIRT'||source.items.length!==75||source.asin||
    String(source.price)!==String(input.goodsItems[0].price)||source.items.some((r,i)=>r.status!=='failed'||r.asin||r.sku!==input.goodsItems[i].sku||String(r.price)!==String(input.goodsItems[i].price)||r.quantity!==input.goodsItems[i].quantity)))throw Error('SWEATSHIRT原75SKU、未建ASIN或原价格库存范围不符');
 const next=clone(source);Object.assign(next,clone(amendment.sourceIdentifiers.parent));
 for(const row of next.items){const expected=amendment.sourceIdentifiers.children[row.sku];if(!expected)throw Error('缺少原US对应子SKU编码');Object.assign(row,clone(expected));}
 return next;
}
function withoutIdentifiers(source){const p=mainImageBusinessProjection(source);for(const r of [p.parent,...p.children]){delete r.standard_product_type;delete r.standard_product_id;}return p;}
function verifyReadback(source,planned){if(!same(withoutIdentifiers(source),withoutIdentifiers(planned))||!same(introducedIdentifiers(source),introducedIdentifiers(planned)))throw Error('原英国编码、属性或非编码业务回读不符');}
async function readSource(page,input,publishId){
 const observed=await readRequiredAttributesSource(page,input,publishId);
 await page.waitForFunction(p=>document.querySelector('input[placeholder="店铺"]')?.value===p.store&&document.querySelector('input[placeholder="品牌"]')?.value===p.brand&&document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.innerText.includes('UPC豁免：允许销售'),{store:input.store,brand:input.goods.brand},{timeout:20000});
 return{...observed,ui:await readUkExemptionUi(page)};
}
function assertUi(ui,input,publishId){if(ui?.url!=='https://www.junfeikuajing.com/#/amazon/product/'+publishId+'?type=publish'||ui.store!==input.store||ui.brand!==input.goods.brand||String(ui.nativeMarketId)!==String(input.destination.marketId)||!String(ui.status).includes('UPC豁免：允许销售'))throw Error('原英国品牌、店铺或当前豁免未核实，不保存或再申请');}

export function patchIdentifierRepairSavePayload(body,plan){
 const out=patchMainImageSavePayload(body,plan);Object.assign(out,plan.identifiers.parent);
 for(const row of out.items){const expected=plan.identifiers.children[String(row.id)];if(!expected)throw Error('编码保存缺少原子体计划');Object.assign(row,expected);}
 return out;
}
export const installIdentifierSaveGuard=createSourcePreservingSaveGuard(patchIdentifierRepairSavePayload,'__identifierRepairSave');
export const identifierSaveSnapshot=new Function('return ('+requiredAttributesSaveSnapshot.toString().replaceAll('__requiredAttributesSave','__identifierRepairSave')+')();');
export const identifierConfirmationStable=new Function('id','return ('+requiredAttributesConfirmationStable.toString().replaceAll('__requiredAttributesSave','__identifierRepairSave')+')(id);');

export async function repairNativeIdentifiers(page,input,record,persist,{amendment,sourceEvidence,exemptionRecord,schemaObservation,...adapters}={}){
 const publishId=authorize(input,record,amendment,sourceEvidence,exemptionRecord),api={read:readSource,validate:validateSchemaAttributes,remote:verifyRemoteAsset,save:submitNativeIdentifierSave,retry:submitNativeMediaRecovery,...adapters};
 const runtimeInput={...input,runtime:amendment.runtime};let observed=await api.read(page,input,publishId);assertSchema(observed.meta,input,schemaObservation,amendment);assertUi(observed.ui,input,publishId);
 let failure;try{failure=publicationFailureObservation(observed.response,input,publishId);}catch(e){if(e.code==='ERP_PUBLICATION_PENDING')failure=null;else throw e;}
 let j=record.identifierRepair;if(!j){j=record.identifierRepair={amendmentId:amendment.id,amendment:clone(amendment),publishId,phase:'preflight',originalAcceptedIdentity:clone(record.identity),originalAcceptedSourceEvidence:clone(record.sourceEvidence),originalSourceLink:clone(record.sourceLink),originalFailureObservation:clone(record.failureObservation),retry:{}};await persist();}
 if(j.consumedWithoutWrite)return record;
 if(!j.saveIntent&&!failure){j.consumedWithoutWrite=true;j.phase='source_no_longer_failed';await persist();return record;}
 if(!j.beforeSource){assertIdentifierFailure(failure,amendment,{fingerprint:true});if(requiredAttributesSourceFingerprint(observed.response.data)!==amendment.sourceFingerprint)throw Error('原英国编码源指纹变化');j.beforeSource=clone(observed.response.data);j.plannedSource=buildIdentifierRepairSource(j.beforeSource,input,amendment);await persist();}
 const validate=async(s,key)=>{const proof=await api.validate(observed.meta,records(s),runtimeInput);if(!proof.passed||proof.checkedCount!==input.goodsItems.length+1||proof.schemaHash!==amendment.schemaHash)throw Error('原英国完整raw schema证明不符');j[key]=proof;await persist();};
 if(!j.saveIntent){
  assertIdentifierFailure(failure,amendment);if(!same(mainImageBusinessProjection(observed.response.data),mainImageBusinessProjection(j.beforeSource)))throw Error('原英国编码资料已变化');
  await validate(j.beforeSource,'schemaBeforeOriginal');await validate(j.plannedSource,'schemaBeforeSave');j.remoteChecks=[];
  for(const asset of new Map(input.assets.map(a=>[a.sha256,a])).values()){const result=await api.remote(input.urls[asset.sha256],asset);if(result.sha256!==asset.sha256||!(result.bytes>0))throw Error('原文件SHA未核实');j.remoteChecks.push({sha256:asset.sha256,url:input.urls[asset.sha256],proof:result});await persist();}
  observed=await api.read(page,input,publishId);assertSchema(observed.meta,input,schemaObservation,amendment);assertUi(observed.ui,input,publishId);
  let fresh;try{fresh=publicationFailureObservation(observed.response,input,publishId);}catch(e){if(e.code==='ERP_PUBLICATION_PENDING')fresh=null;else throw e;}
  if(!fresh){j.consumedWithoutWrite=true;j.phase='source_no_longer_failed';await persist();return record;}assertIdentifierFailure(fresh,amendment);
  if(!same(mainImageBusinessProjection(observed.response.data),mainImageBusinessProjection(j.beforeSource)))throw Error('保存前原编码业务变化');
   const armSaveIntent=async()=>{if(j.saveIntent)throw Error('已有商品编码保存意图');j.saveIntent={publishId,armedAt:new Date().toISOString(),scope:'one_original_identifier_save'};j.phase='save_unknown';await persist();};
   try{await api.save(page,input,record,persist,{source:j.beforeSource,planned:j.plannedSource,amendment,armSaveIntent});if(!j.saveIntent)throw Error('编码保存未持久记录意图');}
   catch(e){if(j.saveIntent)j.lastSaveError=String(e.message);else j.lastPreparationError=String(e.message);await persist();throw e;}
  observed=await api.read(page,input,publishId);assertSchema(observed.meta,input,schemaObservation,amendment);assertUi(observed.ui,input,publishId);
 }
 verifyReadback(observed.response.data,j.plannedSource);await validate(observed.response.data,'schemaAfterSave');j.saveVerified=true;j.phase='save_verified';await persist();
 let current;try{current=publicationFailureObservation(observed.response,input,publishId);}catch(e){if(e.code==='ERP_PUBLICATION_PENDING')current=null;else throw e;}
  if(j.retry.intent||j.retry.consumedWithoutWrite)return record;if(!current){j.retry.consumedWithoutWrite=true;await persist();return record;}assertIdentifierFailure(current,amendment);
  const armIntent=async()=>{if(j.retry.intent)throw Error('原编码重试意图已消费');j.retry.intent={publishId,armedAt:new Date().toISOString(),scope:'original_family_all_children'};j.phase='retry_unknown';await persist();};
  try{await api.retry(page,input,{publishId,mediaRecovery:j.retry},persist,{armIntent});if(!j.retry.intent)throw Error('编码重试未持久记录意图');}
  catch(e){if(j.retry.intent)j.retry.lastError=String(e.message);else j.retry.lastPreparationError=String(e.message);await persist();throw e;}
 const request=j.retry.nativeRequests?.[0];if(j.retry.nativeRequests?.length!==1||request.response?.httpStatus!==200||request.response.body?.code!==0)throw Error('原英国编码恢复结果未知，仅回读原ID');j.retry.requestAccepted=true;j.phase='retry_acknowledged';await persist();return record;
}

export async function submitNativeIdentifierSave(page,input,record,persist,{source,planned,amendment,armSaveIntent}){
 const j=record.identifierRepair;if(!j||j.saveIntent||j.nativeRequests?.length||typeof armSaveIntent!=='function')throw Error('商品编码保存缺少点击前持久意图回调或已有意图');
 const plan={source,guardId:amendment.id,variationFields:input.destination.variationFields,attributes:{parent:planned.extra.attributes,children:Object.fromEntries(planned.items.map(r=>[String(r.id),r.extra.attributes]))}};
 plan.identifiers={parent:{standard_product_type:planned.standard_product_type,standard_product_id:planned.standard_product_id},children:Object.fromEntries(planned.items.map(r=>[String(r.id),{standard_product_type:r.standard_product_type,standard_product_id:r.standard_product_id}]))};
 await page.waitForFunction(nativeSourceSaveReady,{url:'https://www.junfeikuajing.com/#/amazon/product/'+source.id+'?type=publish',store:input.store,title:source.title,skus:source.items.map(r=>r.sku)},{timeout:60000});
 try{const installed=await page.evaluate(installIdentifierSaveGuard,plan),proof=await page.evaluate(identifierSaveSnapshot);
  if(!installed?.installed||!guardOk(proof,amendment.id))throw Error('商品编码保存护栏未绑定，未点击');j.guardInstallProof=proof;await persist();
  const selector=await page.evaluate(()=>{const es=[...document.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().width&&!b.disabled&&b.innerText.replace(/\s/g,'')==='保存'&&[...b.parentElement.querySelectorAll('button')].some(s=>s.innerText.replace(/\s/g,'')==='保存并发布'));if(es.length!==1)throw Error('原任务保存按钮不唯一');es[0].setAttribute('data-required-save','true');es[0].scrollIntoView({block:'center'});return '[data-required-save]';});
   if(!guardOk(await page.evaluate(identifierSaveSnapshot),amendment.id))throw Error('点击保存前护栏失效');await armSaveIntent();
   if(!j.saveIntent||!guardOk(await page.evaluate(identifierSaveSnapshot),amendment.id))throw Error('编码保存意图持久化后护栏失效');await page.click(selector);
  await page.waitForFunction(()=>window.__identifierRepairSave?.requests.some(r=>r.response)||window.__identifierRepairSave?.error||[...document.querySelectorAll('.el-message-box')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:20000});
  const boxes=await page.evaluate(()=>[...document.querySelectorAll('.el-message-box')].filter(e=>e.getBoundingClientRect().width).map(e=>e.innerText));
  if(boxes.length){if(boxes.length!==1||!boxes[0].includes('颜色')||!boxes[0].includes('不在亚马逊选项中。确定要保存吗？')||/发布|删除/.test(boxes[0])||![...new Set(input.goodsItems.map(r=>r.color))].every(c=>boxes[0].includes(c)))throw Error('非原颜色确认，未继续');
   j.enumConfirmation=boxes[0];await persist();await page.waitForFunction(identifierConfirmationStable,amendment.id,{timeout:10000});
   const confirm=await page.evaluate(()=>{const boxes=[...document.querySelectorAll('.el-message-box')].filter(e=>e.getBoundingClientRect().width),es=boxes.length===1?[...boxes[0].querySelectorAll('button')].filter(b=>!b.disabled&&b.innerText.trim()==='确定'):[];if(es.length!==1)throw Error('原颜色确认不唯一');es[0].setAttribute('data-required-confirm','true');return '[data-required-confirm]';});
   await page.focus(confirm);
   const p=await page.evaluate(identifierSaveSnapshot);if(!guardOk(p,amendment.id)||p.url!==proof.url)throw Error('确认前商品编码保存护栏失效');j.confirmGuardProof=p;j.confirmMethod='native_focus_enter';await persist();await page.press(confirm,'Enter');
  }
  await page.waitForFunction(()=>window.__identifierRepairSave?.requests.some(r=>r.response)||window.__identifierRepairSave?.error,undefined,{timeout:25000});
 }finally{
  try{const s=await page.evaluate(identifierSaveSnapshot);j.lastGuardSnapshot=s;j.nativeRequests=s.requests;if(s.error)j.guardError=s.error;await persist();}
  finally{await page.evaluate(()=>{const s=window.__identifierRepairSave;if(s){if(XMLHttpRequest.prototype.open===s.hookedOpen)XMLHttpRequest.prototype.open=s.open;if(XMLHttpRequest.prototype.send===s.hookedSend)XMLHttpRequest.prototype.send=s.send;if(window.fetch===s.hookedFetch)window.fetch=s.fetch;delete window.__identifierRepairSave;}});}
 }
 const r=j.nativeRequests?.[0];if(j.nativeRequests?.length!==1||r.response?.httpStatus!==200||r.response.body?.code!==0)throw Error('商品编码保存结果未知，仅回读原ID');j.saveAcknowledgedAt=new Date().toISOString();await persist();
}

