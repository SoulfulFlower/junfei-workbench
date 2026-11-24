import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,verifyPublication} from './ego-publish-native.mjs';
import {extractSourceIdentifiers} from './ego-uk-draft.mjs';
import {requiredAttributesSourceFingerprint} from './ego-publication-required-attributes.mjs';
import {repairNativeIdentifiers,identifierExemptionProof,existingIdentifierExemptionProof,SWEATSHIRT_IDENTIFIER_PROFILE,introducedIdentifiers,buildIdentifierRepairSource,patchIdentifierRepairSavePayload,installIdentifierSaveGuard,identifierConfirmationStable,submitNativeIdentifierSave} from './ego-publication-identifiers.mjs';
const clone=v=>structuredClone(v),endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/json-update';
function baseFixture(){
 const assets=Array.from({length:14},(_,i)=>({sha256:createHash('sha256').update('required-'+i).digest('hex')})),urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/u/11/26/11/'+i+'.png']));
 const goodsItems=['Blue','Pink'].map((color,i)=>({sku:'Parent-'+color+'-S',color,size:'S',price:'15.19',quantity:88,imageIndices:Array.from({length:7},(_,n)=>i*7+n)}));
 const input={accountId:2,productId:'product',jobId:'job',sha256:'snapshot',marketplace:'UK',mode:'draft',store:'Original UK',masterColor:'Blue',assets,urls,goodsItems,handlingDays:3,
  goods:{parentSku:'Parent',title:'Original Sweatshirt',brand:'Brand',manufacturer:'Maker',description:'Material: 100% polyester\nCuffs and hem: Ribbed',bullets:['Original bullet'],terms:'terms',sourceUrl:'https://detail.1688.com/offer/123456789.html'},
  destination:{destinationId:'uk',draftId:'101',marketId:'92',erpAccountId:'11',countryCode:'GB',marketplaceId:'GBMARKET',languageTag:'en_GB',schemaHash:'gb-schema',variationFields:{color:'color.0.value',size:'apparel_size.0.size'},sizeValues:{S:'s'}}};
 const common={fabric_type:[{value:'100% polyester',language_tag:'en_GB',marketplace_id:'GBMARKET'}],supplier_declared_dg_hz_regulation:[{value:'not_applicable'}],unit_count:[{value:'1'}],fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',lead_time_to_ship_max_days:'3'}],color:[{value:'Blue'}],apparel_size:[{size:'s'}]};
 const accepted={code:0,data:{id:202,uid:11,market_id:92,country_code:'GB',market:{alias:input.store},sku:'Parent',title:input.goods.title,brand:'Brand',manufacturer:'Maker',quantity:88,price:'15.19',cost_price:'38.00',country_of_origin:'CN',list_price:null,part_number:null,pallet_goods_id:null,pallet_service_unique:null,standard_product_id:null,standard_product_type:'UPC',variation_theme:'COLOR_NAME/SIZE_NAME',product_type_name:'SHIRT',category_path:'category',main_image:urls[assets[0].sha256],status:'publishing',errors:[],extra:{images:[urls[assets[0].sha256]],keywords:'terms',product_description:input.goods.description,bullet_point:input.goods.bullets,attributes:common},
  items:goodsItems.map((g,i)=>({id:203+i,pid:202,uid:11,sku:g.sku,quantity:88,price:'15.19',cost_price:'38.00',title:null,list_price:null,standard_product_type:null,standard_product_id:null,status:'accepted',main_image:urls[assets[g.imageIndices[0]].sha256],extra:{images:g.imageIndices.map(n=>urls[assets[n].sha256]),keywords:null,product_description:'',bullet_point:null,message:null,attributes:{color:[{value:g.color,marketplace_id:'GBMARKET'}],apparel_size:[{size:'s',marketplace_id:'GBMARKET'}],supplier_declared_has_product_identifier_exemption:[{value:true}]}}}))}};
 const response=clone(accepted);response.data.status='failed';for(const row of response.data.items){row.status='failed';row.extra.message=['外部材料','编织类型','产品类型名称'].map(field=>({code:'90220',message:field+' 为必填项，但缺失。',severity:'ERROR'}));response.data.errors.push(...row.extra.message.map(m=>({...m,sku:row.sku})));}
 const record={publishId:'202',fingerprint:publicationFingerprint(assertPublicationInput(input)),identity:verifyPublication(accepted,input,'202'),sourceEvidence:clone(accepted.data),sourceLink:{publishId:'202',draftId:'101'},phase:'publication_failed',status:'failed',mediaRecovery:{intent:{keep:true}},mainImageRepair:{saveIntent:{keep:true}}};record.failureObservation=publicationFailureObservation(response,input,'202');record.latestObservation=clone(record.failureObservation);
 const localized={type:'array',items:{type:'object',properties:{value:{type:'string'},language_tag:{type:'string'},marketplace_id:{type:'string'}}}};
 const meta={country_code:'GB',locale:'en_GB',product_type_name:'SHIRT',hash:'gb-schema',schema_content:{$defs:{marketplace_id:{default:'GBMARKET'}},properties:Object.fromEntries(['brand','manufacturer','item_name','country_of_origin','product_description','bullet_point','fabric_type','weave_type','item_type_name'].map(k=>[k,clone(localized)]))}};
 meta.schema_content.properties.unit_count={items:{properties:{value:{type:'number'}}}};meta.schema_content.properties.list_price={items:{properties:{currency:{enum:['GBP']},value_with_tax:{type:'number',minimum:0,description:'If you are unable to provide a value, enter 0.'}}}};
 const amendment={id:'required-amendment',scope:'repair_original_failed_required_attributes',marketplace:'UK',authorizedAt:123,retryOriginalTaskAfterVerifiedSave:true,
  accountId:2,productId:'product',jobId:'job',snapshotSha256:'snapshot',publishId:'202',destinationId:'uk',draftId:'101',erpAccountId:'11',marketId:'92',countryCode:'GB',store:'Original UK',parentSku:'Parent',schemaHash:'gb-schema',
  children:record.failureObservation.children.map(r=>({id:r.childId,sku:r.sku})),failureResponseFingerprint:record.failureObservation.responseFingerprint,sourceFingerprint:requiredAttributesSourceFingerprint(response.data),
  facts:{outerMaterial:'100% polyester',weaveType:'Knit',itemTypeName:'Sweatshirt'},representation:{explicitCommonAttributes:true,exactNumericTypes:true,independentInventory:true,unknownGbpRrpZero:true},runtime:{pythonExecutable:'fixture-python'},
  evidence:{sourceUrl:input.goods.sourceUrl,materialText:'100%',weaveText:'工艺\n针织',itemTitle:'长袖卫衣',categoryPath:'Fashion Sweatshirts',artifacts:[{path:'cached-supplier-page',sha256:'a'.repeat(64)}]}};
 const preview={};for(const k of ['market_id','title','id','brand','price','quantity','country_code','pallet_service_unique','pallet_goods_id','part_number','standard_product_type','standard_product_id','list_price','cost_price','manufacturer','country_of_origin','variation_theme','main_image','product_type_name','category_path','sku'])preview[k]=response.data[k];
 Object.assign(preview,{keywords:'terms',product_description:input.goods.description,bullet_point:input.goods.bullets,parent_sku:'Parent',variation:{},images:Object.values(urls),attributes:{},items:response.data.items.map(row=>({id:row.id,attributes:{},keywords:null,list_price:null,product_description:'',price_info:{'purchasable_offer.0.maximum_seller_allowed_price.0.schedule.0.value_with_tax':'','purchasable_offer.0.minimum_seller_allowed_price.0.schedule.0.value_with_tax':''},bullet_point:null,title:null,main_image:row.main_image,images:clone(row.extra.images),variation:{'color.0.value':row.extra.attributes.color[0].value,'apparel_size.0.size':'s'},standard_product_type:'UPC',cost_price:'38.00',price:'15.19',quantity:88,title_differentiation:'',sku:row.sku,standard_product_id:null}))});
 return{input,accepted,response,record,meta,amendment,preview};
}

function fixture(){
 const f=baseFixture(),sourceEvidence=clone(f.accepted.data);sourceEvidence.id=303;sourceEvidence.country_code='US';sourceEvidence.market_id=91;
 sourceEvidence.standard_product_type='UPC';sourceEvidence.standard_product_id=null;for(const row of sourceEvidence.items){row.standard_product_type=null;row.standard_product_id=null;}
 for(const data of [f.accepted.data,f.response.data]){data.seller_id='SELLER';data.standard_product_type='UPC';data.standard_product_id='796225904178';for(const [n,row]of data.items.entries()){row.standard_product_type=null;row.standard_product_id='796225904'+String(185+n).padStart(3,'0');row.extra.attributes.brand=[{value:'Brand',language_tag:'en_GB',marketplace_id:'GBMARKET'}];row.extra.attributes.supplier_declared_has_product_identifier_exemption=[{value:true}];}data.extra.attributes.brand=[{value:'Brand',language_tag:'en_GB',marketplace_id:'GBMARKET'}];data.extra.attributes.supplier_declared_has_product_identifier_exemption=[{value:true}];}
 f.response.data.errors=[];for(const row of f.response.data.items){row.extra.message=['8566','8572','13013'].map(code=>({code,message:'original identifier error '+code,severity:'ERROR'}));f.response.data.errors.push(...row.extra.message.map(m=>({...m,sku:row.sku})));}
 f.record.identity=verifyPublication(f.accepted,f.input,'202');f.record.sourceEvidence=clone(f.accepted.data);f.record.failureObservation=publicationFailureObservation(f.response,f.input,'202');f.record.latestObservation=clone(f.record.failureObservation);
 const exemptionRecord={phase:'allowed',applicationState:'available',applyRequests:[{}],applyIntent:{armedAt:'original-once'},nativeScope:{seller_id:'SELLER',country_code:'GB',primary_category_name:'Fashion',product_type_name:'SHIRT',brand:'Brand'},applyResponse:{response:{httpStatus:200,body:{code:0,data:{id:573}}}},latestCheck:{status:'available',ui:{store:f.input.store,nativeMarketId:'92'}},allowedAt:'known'};
 const amendment={...f.amendment,id:'identifier-amendment',scope:'repair_original_failed_identifiers',sourceFingerprint:requiredAttributesSourceFingerprint(f.response.data),sourceEvidenceFingerprint:requiredAttributesSourceFingerprint(sourceEvidence),sourceIdentifiers:extractSourceIdentifiers(sourceEvidence),introducedIdentifiers:introducedIdentifiers(f.response.data),failureResponseFingerprint:f.record.failureObservation.responseFingerprint,exemption:identifierExemptionProof(exemptionRecord,f.input)};
 for(const row of f.preview.items){const actual=f.response.data.items.find(r=>r.id===row.id);row.standard_product_id=actual.standard_product_id;}
 f.preview.standard_product_id=f.response.data.standard_product_id;
 const ui={url:'https://www.junfeikuajing.com/#/amazon/product/202?type=publish',store:f.input.store,brand:'Brand',nativeMarketId:'92',status:'UPC豁免：允许销售'};
 return{...f,sourceEvidence,exemptionRecord,amendment,ui};
}
function runner(f,extra={}){
 let current=clone(f.response),saves=0,retries=0,reads=0;const options={amendment:f.amendment,sourceEvidence:f.sourceEvidence,exemptionRecord:f.exemptionRecord,schemaObservation:f.meta,
  read:async()=>{reads++;return{response:clone(current),meta:f.meta,ui:f.ui};},validate:async(meta,rows)=>({passed:true,checkedCount:rows.length,schemaHash:meta.hash}),remote:async(_u,a)=>({sha256:a.sha256,bytes:100}),
  save:async(_p,_i,r,_persist,{planned,armSaveIntent})=>{await armSaveIntent();saves++;assert.ok(r.identifierRepair.saveIntent);current={code:0,data:clone(planned)};},retry:async(_p,_i,view,_persist,{armIntent})=>{await armIntent();retries++;assert.ok(view.mediaRecovery.intent);view.mediaRecovery.nativeRequests=[{response:{httpStatus:200,body:{code:0}}}];},...extra};
 return{run:()=>repairNativeIdentifiers({},f.input,f.record,async()=>{},options),setCurrent:r=>current=clone(r),counts:()=>({saves,retries,reads})};
}

function sweatshirtFixture(){
 const f=fixture(),sizes=['S','M','L','XL','XXL'],values=['s','m','l','x_l','xx_l'];
 f.input.assets=Array.from({length:105},(_,i)=>({sha256:createHash('sha256').update('sweatshirt-'+i).digest('hex')}));
 f.input.urls=Object.fromEntries(f.input.assets.map((a,i)=>[a.sha256,'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/u/11/original/'+i+'.png']));
 f.input.goodsItems=Array.from({length:75},(_,i)=>({sku:'Parent-Color'+Math.floor(i/5)+'-'+sizes[i%5],color:'Color'+Math.floor(i/5),size:sizes[i%5],price:'15.19',quantity:88,imageIndices:Array.from({length:7},(_,n)=>Math.floor(i/5)*7+n)}));
 f.input.masterColor='Color0';f.input.destination.sizeValues=Object.fromEntries(sizes.map((s,i)=>[s,values[i]]));f.input.destination.shippingTemplate={id:'real-template',name:'Original'};
 const parent=f.accepted.data,template=clone(parent.items[0]);parent.product_type_name='SWEATSHIRT';parent.main_image=f.input.urls[f.input.assets[0].sha256];parent.extra.images=[parent.main_image];parent.extra.attributes.color=[{value:'Color0'}];
 parent.items=f.input.goodsItems.map((v,i)=>({...clone(template),id:203+i,pid:202,sku:v.sku,status:'accepted',asin:null,price:v.price,quantity:v.quantity,standard_product_type:null,standard_product_id:String(796225905000+i),main_image:f.input.urls[f.input.assets[v.imageIndices[0]].sha256],extra:{...clone(template.extra),images:v.imageIndices.map(n=>f.input.urls[f.input.assets[n].sha256]),message:null,attributes:{...clone(template.extra.attributes),color:[{value:v.color,marketplace_id:'GBMARKET'}],apparel_size:[{size:values[i%5],marketplace_id:'GBMARKET'}]}}}));
 f.response=clone(f.accepted);f.response.data.status='failed';f.response.data.errors=[];
 for(const row of f.response.data.items){row.status='failed';row.extra.message=[{code:'100980',message:'条码 '+row.standard_product_id.padStart(14,'0')+' 已关联 B0BXRQ33RM',severity:'ERROR'},{code:'13013',message:'尚未进入型录',severity:'ERROR'}];f.response.data.errors.push(...row.extra.message.map(m=>({...m,sku:row.sku})));}
 f.sourceEvidence=clone(parent);f.sourceEvidence.id=303;f.sourceEvidence.country_code='US';f.sourceEvidence.market_id=91;f.sourceEvidence.standard_product_id=null;
 for(const row of f.sourceEvidence.items){row.pid=303;row.standard_product_id=null;row.standard_product_type=null;}
 f.meta.product_type_name='SWEATSHIRT';f.record.fingerprint=publicationFingerprint(assertPublicationInput(f.input));f.record.identity=verifyPublication(f.accepted,f.input,'202');f.record.sourceEvidence=clone(parent);
 f.record.failureObservation=publicationFailureObservation(f.response,f.input,'202');f.record.latestObservation=clone(f.record.failureObservation);
 f.record.requiredAttributeRepair={saveIntent:{keep:'original-unknown'},retry:{intent:{keep:'original-consumed'}},phase:'original'};
 const observedAt=new Date().toISOString();f.record.readiness={checkedAt:new Date(Date.now()-172800000).toISOString(),store:f.input.store,brand:'Brand',brandStatus:'UPC豁免：允许销售',shippingTemplate:f.input.destination.shippingTemplate,handlingDays:'3'};
 const request={kind:'check',method:'POST',url:'https://app.junfeikuajing.com/api/amazon/category/upc-exemption/check',payload:{seller_id:'SELLER',country_code:'GB',primary_category_name:'Fashion',product_type_name:'SWEATSHIRT',brand:'bRaNd'},sentAt:observedAt,response:{httpStatus:200,body:{code:0,data:{status:'available',status_map:{available:'允许销售'}}}}};
 const fresh={observedAt,accountId:f.input.accountId,productId:f.input.productId,jobId:f.input.jobId,snapshotSha256:f.input.sha256,publishId:'202',schemaHash:f.input.destination.schemaHash,ui:clone(f.ui),request,guardProof:{present:true,token:'check-only-fixture',bindings:{open:true,send:true,fetch:true},error:null,requests:[clone(request)]}};
 f.amendment={...f.amendment,identifierProfile:SWEATSHIRT_IDENTIFIER_PROFILE,productType:'SWEATSHIRT',childCount:75,expectedErrorCodes:['100980','13013'],authorizedAt:Date.now()/1000,
  children:f.record.failureObservation.children.map(r=>({id:r.childId,sku:r.sku})),failureResponseFingerprint:f.record.failureObservation.responseFingerprint,sourceFingerprint:requiredAttributesSourceFingerprint(f.response.data),sourceEvidenceFingerprint:requiredAttributesSourceFingerprint(f.sourceEvidence),sourceIdentifiers:extractSourceIdentifiers(f.sourceEvidence),introducedIdentifiers:introducedIdentifiers(f.response.data),exemption:{freshExemptionCheck:fresh}};
 f.amendment.exemption=existingIdentifierExemptionProof(f.record,f.input,f.amendment);f.exemptionRecord=null;
 const previewChild=clone(f.preview.items[0]);f.preview={...f.preview,product_type_name:'SWEATSHIRT',main_image:parent.main_image,images:Object.values(f.input.urls),items:parent.items.map(row=>({...clone(previewChild),id:row.id,sku:row.sku,main_image:row.main_image,images:clone(row.extra.images),standard_product_type:'UPC',standard_product_id:row.standard_product_id,variation:{'color.0.value':row.extra.attributes.color[0].value,'apparel_size.0.size':row.extra.attributes.apparel_size[0].size}}))};
 return f;
}

test('75 SWEATSHIRT GTIN conflict restores all76 exact original IDs/types and preserves105 image refs and all other business',()=>{
 const f=sweatshirtFixture(),before=clone(f.response.data),planned=buildIdentifierRepairSource(before,f.input,f.amendment);
 assert.equal(planned.standard_product_type,'UPC');assert.equal(planned.standard_product_id,null);assert.equal(planned.items.length,75);assert.equal(f.input.assets.length,105);
 for(const row of planned.items){const old=before.items.find(x=>x.id===row.id);assert.deepEqual(row,{...old,standard_product_type:null,standard_product_id:null});assert.equal(row.price,'15.19');assert.equal(row.quantity,88);}assert.deepEqual(f.response.data,before);
});
test('new profile requires fresh same-task same-seller non-apply allowed CHECK and preserves original SHIRT apply rule',async()=>{
 for(const change of [f=>delete f.amendment.exemption.freshExemptionCheck,
  f=>f.amendment.exemption.freshExemptionCheck.observedAt=new Date(Date.now()-960000).toISOString(),
  f=>f.amendment.exemption.freshExemptionCheck.accountId=3,
  f=>f.amendment.exemption.freshExemptionCheck.ui.nativeMarketId='OTHER',
  f=>f.amendment.exemption.freshExemptionCheck.request.payload.brand='Other',
  f=>f.amendment.exemption.freshExemptionCheck.request.kind='apply',
  f=>f.amendment.exemption.freshExemptionCheck.request.response.body.data.status='applying',
  f=>f.amendment.exemption.freshExemptionCheck.guardProof.bindings.fetch=false,
  f=>f.record.readiness.brand='Other']){
  const f=sweatshirtFixture();change(f);const r=runner(f);await assert.rejects(r.run);assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,0);
 }
 const legacy=fixture();legacy.exemptionRecord.applyRequests=[];await assert.rejects(runner(legacy).run,/单次豁免/);
});
test('75 child source/codes/barcodes/price and already-created ASIN are exact gates before any write',async()=>{
 for(const change of [f=>f.sourceEvidence.items[0].standard_product_id='123456789012',
  f=>f.response.data.items[0].extra.message[0].message='条码 00999999999999',
  f=>f.response.data.items[0].extra.message[0].code='8566',
  f=>f.response.data.items[0].price='99.00',f=>f.response.data.items[0].asin='B0BXRQ33RM',
  f=>f.meta.product_type_name='SHIRT',f=>f.amendment.childCount=74]){
  const f=sweatshirtFixture();change(f);const r=runner(f);await assert.rejects(r.run);assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,0);
 }
});
test('75 profile performs one identifier Save plus one original-family retry without replaying required-attribute journals',async()=>{
 const f=sweatshirtFixture(),history=clone({accepted:f.record.sourceEvidence,identity:f.record.identity,failure:f.record.failureObservation,required:f.record.requiredAttributeRepair,media:f.record.mediaRecovery,main:f.record.mainImageRepair});const r=runner(f);await r.run();await r.run();
 assert.equal(r.counts().saves,1);assert.equal(r.counts().retries,1);assert.equal(f.record.identifierRepair.schemaAfterSave.checkedCount,76);
 assert.deepEqual({accepted:f.record.sourceEvidence,identity:f.record.identity,failure:f.record.failureObservation,required:f.record.requiredAttributeRepair,media:f.record.mediaRecovery,main:f.record.mainImageRepair},history);
});
test('75 unknown Save stays readonly and a late exact readback can consume its separate original retry only once',async()=>{
 const f=sweatshirtFixture();let calls=0;const oldRequired=clone(f.record.requiredAttributeRepair),r=runner(f,{save:async(_p,_i,_r,_persist,{armSaveIntent})=>{await armSaveIntent();calls++;throw Error('lost75Save');}});
 await assert.rejects(r.run,/lost75Save/);await assert.rejects(r.run,/回读不符/);assert.equal(calls,1);
 r.setCurrent({code:0,data:f.record.identifierRepair.plannedSource});await r.run();await r.run();assert.equal(calls,1);assert.equal(r.counts().retries,1);assert.deepEqual(f.record.requiredAttributeRepair,oldRequired);
});
test('75 actual serialized source-preserving guard restores child null type despite native-form UPC default',()=>{
 const f=sweatshirtFixture(),planned=buildIdentifierRepairSource(f.response.data,f.input,f.amendment),plan={source:f.response.data,variationFields:f.input.destination.variationFields,guardId:'75guard',identifiers:{parent:{standard_product_type:planned.standard_product_type,standard_product_id:null},children:Object.fromEntries(planned.items.map(r=>[String(r.id),{standard_product_type:null,standard_product_id:null}]))}},sent=[];
 class XHR{open(){}addEventListener(){}send(body){sent.push(JSON.parse(body));}}
 const context=vm.createContext({window:{fetch:()=>{}},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com'},plan,payload:f.preview,endpoint});vm.runInContext('('+installIdentifierSaveGuard.toString()+')(plan)',context);
 vm.runInContext('(()=>{const x=new XMLHttpRequest();x.open("POST",endpoint);x.send(JSON.stringify(payload));})()',context);
 assert.equal(sent.length,1);assert.equal(sent[0].standard_product_type,'UPC');assert.equal(sent[0].standard_product_id,null);assert.equal(sent[0].items.length,75);
 for(const row of sent[0].items){const old=f.response.data.items.find(x=>x.id===row.id);assert.equal(row.standard_product_type,null);assert.equal(row.standard_product_id,null);assert.deepEqual(row.attributes,old.extra.attributes);assert.deepEqual(row.images,old.extra.images);assert.equal(row.price,old.price);assert.equal(row.quantity,old.quantity);}
});
test('identifier-only candidate restores original nulls and retains original parent UPC type, all attrs images and other business',()=>{
 const f=fixture(),before=clone(f.response.data),planned=buildIdentifierRepairSource(before,f.input,f.amendment);assert.equal(planned.standard_product_type,'UPC');assert.equal(planned.standard_product_id,null);
 for(const row of planned.items){assert.equal(row.standard_product_type,null);assert.equal(row.standard_product_id,null);const old=before.items.find(r=>r.id===row.id);assert.deepEqual(row.extra,old.extra);assert.equal(row.price,old.price);assert.equal(row.quantity,old.quantity);}assert.deepEqual(f.response.data,before);
});
test('one dedicated Save and original parent retry retain original accepted, failure, media and MAIN history',async()=>{
 const f=fixture(),history=clone({identity:f.record.identity,source:f.record.sourceEvidence,failure:f.record.failureObservation,media:f.record.mediaRecovery,main:f.record.mainImageRepair}),r=runner(f);await r.run();await r.run();assert.equal(r.counts().saves,1);assert.equal(r.counts().retries,1);
 assert.deepEqual({identity:f.record.identity,source:f.record.sourceEvidence,failure:f.record.failureObservation,media:f.record.mediaRecovery,main:f.record.mainImageRepair},history);
});
test('unknown Save never repeats and exact original readback permits only its separate retry',async()=>{
 const f=fixture();let attempts=0;const r=runner(f,{save:async(_p,_i,_r,_persist,{armSaveIntent})=>{await armSaveIntent();attempts++;throw Error('lost Save');}});await assert.rejects(r.run,/lost Save/);await assert.rejects(r.run,/回读不符/);assert.equal(attempts,1);r.setCurrent({code:0,data:f.record.identifierRepair.plannedSource});await r.run();assert.equal(attempts,1);assert.equal(r.counts().retries,1);
});
test('unknown retry is permanently original-ID readonly without another Save or apply',async()=>{
 const f=fixture();let calls=0;const r=runner(f,{retry:async(_p,_i,_r,_persist,{armIntent})=>{await armIntent();calls++;throw Error('lost retry');}});await assert.rejects(r.run,/lost retry/);await r.run();await r.run();assert.equal(calls,1);assert.equal(r.counts().saves,1);
});
test('wrong identifiers source or exemption evidence and unrelated failure codes stop before writes',async()=>{
 for(const mutate of [f=>f.sourceEvidence.items[0].standard_product_id='123456789012',f=>f.amendment.sourceFingerprint='f'.repeat(64),f=>f.exemptionRecord.latestCheck.status='applying',f=>f.response.data.items[0].extra.message.push({code:'18320',message:'other'}),f=>f.ui.brand='Other',f=>f.amendment.children.reverse()]){const f=fixture();mutate(f);const r=runner(f);await assert.rejects(r.run);assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,0);}
});
test('new foreign identifiers or changed gallery attributes inventory or brand cannot reach retry',async()=>{
 for(const mutate of [r=>r.items[0].extra.images.reverse(),r=>r.items[0].quantity=1,r=>r.brand='Other',r=>r.items[0].standard_product_id='new-code',r=>r.items[0].extra.attributes.brand[0].value='Other']){const f=fixture();let current=f.response;const r=runner(f,{read:async()=>({response:clone(current),meta:f.meta,ui:f.ui}),save:async(_p,_i,_r,_save,{planned,armSaveIntent})=>{await armSaveIntent();current={code:0,data:clone(planned)};mutate(current.data);}});await assert.rejects(r.run);assert.equal(r.counts().retries,0);}
});
test('healthy/pending before Save consumes this amendment and never clears identifiers if failures return later',async()=>{
 const f=fixture(),r=runner(f);r.setCurrent(f.accepted);await r.run();r.setCurrent(f.response);await r.run();assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,0);assert.equal(f.record.identifierRepair.consumedWithoutWrite,true);
});
test('actual serialized identifier guard sends one exact original payload with only IDs corrected and blocks extra flags/wrong ID/other endpoints',()=>{
 for(const bad of [null,'id','extra','endpoint']){const f=fixture(),planned=buildIdentifierRepairSource(f.response.data,f.input,f.amendment),plan={source:f.response.data,variationFields:f.input.destination.variationFields,guardId:'g',identifiers:{parent:{standard_product_type:planned.standard_product_type,standard_product_id:planned.standard_product_id},children:Object.fromEntries(planned.items.map(r=>[String(r.id),{standard_product_type:r.standard_product_type,standard_product_id:r.standard_product_id}]))}},sent=[],payload=clone(f.preview);if(bad==='id')payload.id=999;if(bad==='extra')payload.publish=true;
  class XHR{open(){}addEventListener(){}send(body){sent.push(JSON.parse(body));}}
  const context=vm.createContext({window:{fetch:()=>{}},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com'},plan,payload,endpoint:bad==='endpoint'?endpoint.replace('json-update','re-publish'):endpoint});vm.runInContext('('+installIdentifierSaveGuard.toString()+')(plan)',context);
  const send=()=>vm.runInContext('(()=>{const x=new XMLHttpRequest();x.open("POST",endpoint);x.send(JSON.stringify(payload));})()',context);
  if(bad){assert.throws(send);assert.equal(sent.length,0);}else{send();assert.deepEqual(sent[0],patchIdentifierRepairSavePayload(payload,plan));assert.equal(sent[0].standard_product_id,null);assert.equal(sent[0].items[0].standard_product_id,null);assert.throws(send);assert.equal(sent.length,1);}
 }
});

function nativeSavePage(f,{loseBinding=false}={}){
 const clicked=[],sent=[];let visible=false,opacity='0.5';
 const button=(text,parent)=>({innerText:text,disabled:false,parentElement:parent,getBoundingClientRect:()=>({x:20,y:20,width:100,height:25}),setAttribute(){},scrollIntoView(){}});
 const toolbar={querySelectorAll:()=>[save,publish]},save=button('保存',toolbar),publish=button('保存并发布',toolbar),confirm=button('确定',{});
 const box={innerText:'颜色：Blue，Pink 不在亚马逊选项中。确定要保存吗？',getBoundingClientRect:()=>({x:10,y:10,width:visible?200:0,height:100}),querySelectorAll:()=>[confirm]};
 class XHR{open(){}addEventListener(_event,cb){this.done=cb;}send(body){sent.push(JSON.parse(body));this.status=200;this.responseText='{"code":0}';this.done?.();}}
 const originalFetch=()=>{},context=vm.createContext({window:{fetch:originalFetch},XMLHttpRequest:XHR,URL,Date,innerWidth:1280,innerHeight:900,getComputedStyle:()=>({opacity,visibility:'visible',pointerEvents:'auto'}),location:{href:'https://www.junfeikuajing.com/#/amazon/product/202?type=publish'},document:{readyState:'complete',title:'Amazon产品编辑 - 钧飞跨境',querySelector:s=>s==='input[placeholder="店铺"]'?{value:f.input.store}:s==='input[placeholder="产品标题"]'?{value:f.response.data.title}:null,querySelectorAll:s=>s==='.el-table__body-wrapper tr'?f.response.data.items.map(r=>({querySelector:()=>({value:r.sku})})):s==='button'?[save,publish]:s==='.el-message-box'?[box]:[],elementFromPoint:()=>confirm},payload:f.preview,endpoint});
 const page={evaluate:async(fn,arg)=>{context.arg=arg;return clone(vm.runInContext('('+fn.toString()+')(arg)',context));},
  waitForFunction:async(fn,arg)=>{context.waitArg=arg;for(let n=0;n<8;n++){if(fn===identifierConfirmationStable&&n===1)opacity='1';if(vm.runInContext('('+fn.toString()+')(waitArg)',context)){if(fn===identifierConfirmationStable&&loseBinding)context.window.fetch=()=>{};return;}}throw Error('fake native timeout');},
  click:async selector=>{clicked.push(selector);assert.equal(selector,'[data-required-save]');visible=true;},
  focus:async selector=>assert.equal(selector,'[data-required-confirm]'),
  press:async(selector,key)=>{assert.equal(selector,'[data-required-confirm]');assert.equal(key,'Enter');clicked.push(selector);vm.runInContext('(()=>{const x=new XMLHttpRequest();x.open("POST",endpoint);x.send(JSON.stringify(payload));})()',context);visible=false;}};
 return{page,clicked,sent,context};
}

test('native identifier Save waits for opacity and stable confirmation then sends exact restored original identifiers once',async()=>{
 const f=fixture(),native=nativeSavePage(f),planned=buildIdentifierRepairSource(f.response.data,f.input,f.amendment);f.record.identifierRepair={};
 await submitNativeIdentifierSave(native.page,f.input,f.record,async()=>{},{source:f.response.data,planned,amendment:f.amendment,armSaveIntent:async()=>{f.record.identifierRepair.saveIntent={publishId:'202'};}});
 assert.deepEqual(native.clicked,['[data-required-save]','[data-required-confirm]']);assert.equal(native.sent.length,1);assert.equal(native.sent[0].standard_product_type,'UPC');assert.equal(native.sent[0].standard_product_id,null);
 for(const row of native.sent[0].items){assert.equal(row.standard_product_type,null);assert.equal(row.standard_product_id,null);const original=f.response.data.items.find(r=>r.id===row.id);assert.deepEqual(row.attributes,original.extra.attributes);assert.deepEqual(row.images,original.extra.images);}
 assert.equal(f.record.identifierRepair.confirmGuardProof.prototypeBound,true);assert.equal(f.record.identifierRepair.confirmGuardProof.fetchBound,true);assert.equal(f.record.identifierRepair.confirmMethod,'native_focus_enter');assert.equal(native.context.window.__identifierRepairSave,undefined);
});

test('identifier confirmation refuses a binding replaced after stable observations with zero confirmation sends',async()=>{
 const f=fixture(),native=nativeSavePage(f,{loseBinding:true}),planned=buildIdentifierRepairSource(f.response.data,f.input,f.amendment);f.record.identifierRepair={};
 await assert.rejects(()=>submitNativeIdentifierSave(native.page,f.input,f.record,async()=>{},{source:f.response.data,planned,amendment:f.amendment,armSaveIntent:async()=>{f.record.identifierRepair.saveIntent={publishId:'202'};}}),/护栏失效/);
 assert.deepEqual(native.clicked,['[data-required-save]']);assert.equal(native.sent.length,0);assert.equal(f.record.identifierRepair.confirmGuardProof,undefined);
});

test('missing identifier guard installation never clicks either Save or confirmation',async()=>{
 const f=fixture();f.record.identifierRepair={};let clicks=0;const page={waitForFunction:async()=>{},click:async()=>clicks++,evaluate:async fn=>fn===installIdentifierSaveGuard?undefined:{present:false,requests:[]}};
 await assert.rejects(()=>submitNativeIdentifierSave(page,f.input,f.record,async()=>{},{source:f.response.data,planned:buildIdentifierRepairSource(f.response.data,f.input,f.amendment),amendment:f.amendment,armSaveIntent:async()=>{f.record.identifierRepair.saveIntent={publishId:'202'};}}),/护栏未绑定/);assert.equal(clicks,0);
});
