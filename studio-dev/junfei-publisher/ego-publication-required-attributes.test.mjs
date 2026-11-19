import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,verifyPublication} from './ego-publish-native.mjs';
import {repairNativeRequiredAttributes,buildRequiredAttributesSource,requiredAttributesSourceFingerprint,patchRequiredAttributesSavePayload,installRequiredAttributesSaveGuard,requiredAttributesConfirmationStable,submitNativeRequiredAttributesSave} from './ego-publication-required-attributes.mjs';

const clone=v=>structuredClone(v),endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/json-update';
function fixture(){
 const assets=Array.from({length:14},(_,i)=>({sha256:createHash('sha256').update('required-'+i).digest('hex')})),urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/u/11/26/11/'+i+'.png']));
 const goodsItems=['Blue','Pink'].map((color,i)=>({sku:'Parent-'+color+'-S',color,size:'S',price:'15.19',quantity:88,imageIndices:Array.from({length:7},(_,n)=>i*7+n)}));
 const input={accountId:2,productId:'product',jobId:'job',sha256:'snapshot',marketplace:'UK',mode:'draft',store:'Original UK',masterColor:'Blue',assets,urls,goodsItems,handlingDays:3,
  goods:{parentSku:'Parent',title:'Original Sweatshirt',brand:'Brand',manufacturer:'Maker',description:'Material: 100% polyester\nCuffs and hem: Ribbed',bullets:['Original bullet'],terms:'terms',sourceUrl:'https://detail.1688.com/offer/123456789.html'},
  destination:{destinationId:'uk',draftId:'101',marketId:'92',erpAccountId:'11',countryCode:'GB',marketplaceId:'GBMARKET',languageTag:'en_GB',schemaHash:'gb-schema',variationFields:{color:'color.0.value',size:'apparel_size.0.size'},sizeValues:{S:'s'}}};
 const common={fabric_type:[{value:'100% polyester',language_tag:'en_GB',marketplace_id:'GBMARKET'}],supplier_declared_dg_hz_regulation:[{value:'not_applicable'}],unit_count:[{value:'1'}],fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',lead_time_to_ship_max_days:'3'}],color:[{value:'Blue'}],apparel_size:[{size:'s'}]};
 const accepted={code:0,data:{id:202,uid:11,market_id:92,country_code:'GB',market:{alias:input.store},sku:'Parent',title:input.goods.title,brand:'Brand',manufacturer:'Maker',quantity:88,price:'15.19',cost_price:'38.00',country_of_origin:'CN',list_price:null,part_number:null,pallet_goods_id:null,pallet_service_unique:null,standard_product_id:null,standard_product_type:'UPC',variation_theme:'COLOR_NAME/SIZE_NAME',product_type_name:'SWEATSHIRT',category_path:'category',main_image:urls[assets[0].sha256],status:'publishing',errors:[],extra:{images:[urls[assets[0].sha256]],keywords:'terms',product_description:input.goods.description,bullet_point:input.goods.bullets,attributes:common},
  items:goodsItems.map((g,i)=>({id:203+i,pid:202,uid:11,sku:g.sku,quantity:88,price:'15.19',cost_price:'38.00',title:null,list_price:null,standard_product_type:null,standard_product_id:null,status:'accepted',main_image:urls[assets[g.imageIndices[0]].sha256],extra:{images:g.imageIndices.map(n=>urls[assets[n].sha256]),keywords:null,product_description:'',bullet_point:null,message:null,attributes:{color:[{value:g.color,marketplace_id:'GBMARKET'}],apparel_size:[{size:'s',marketplace_id:'GBMARKET'}],supplier_declared_has_product_identifier_exemption:[{value:true}]}}}))}};
 const response=clone(accepted);response.data.status='failed';for(const row of response.data.items){row.status='failed';row.extra.message=['外部材料','编织类型','产品类型名称'].map(field=>({code:'90220',message:field+' 为必填项，但缺失。',severity:'ERROR'}));response.data.errors.push(...row.extra.message.map(m=>({...m,sku:row.sku})));}
 const record={publishId:'202',fingerprint:publicationFingerprint(assertPublicationInput(input)),identity:verifyPublication(accepted,input,'202'),sourceEvidence:clone(accepted.data),sourceLink:{publishId:'202',draftId:'101'},phase:'publication_failed',status:'failed',mediaRecovery:{intent:{keep:true}},mainImageRepair:{saveIntent:{keep:true}}};record.failureObservation=publicationFailureObservation(response,input,'202');record.latestObservation=clone(record.failureObservation);
 const localized={type:'array',items:{type:'object',properties:{value:{type:'string'},language_tag:{type:'string'},marketplace_id:{type:'string'}}}};
 const meta={country_code:'GB',locale:'en_GB',product_type_name:'SWEATSHIRT',hash:'gb-schema',schema_content:{$defs:{marketplace_id:{default:'GBMARKET'}},properties:Object.fromEntries(['brand','manufacturer','item_name','country_of_origin','product_description','bullet_point','fabric_type','weave_type','item_type_name'].map(k=>[k,clone(localized)]))}};
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
const remote=async(_url,a)=>({sha256:a.sha256,bytes:100});
const validate=async(meta,rows)=>{for(const row of rows){assert.equal(row.attributes.weave_type[0].value,'Knit');assert.equal(row.attributes.item_type_name[0].value,'Sweatshirt');assert.equal(row.attributes.fulfillment_availability[0].quantity,88);}return{passed:true,checkedCount:rows.length,schemaHash:meta.hash};};
function runFixture(f,extra={}){
 let current=clone(f.response),saves=0,retries=0,reads=0;
 const adapters={read:async()=>{reads++;return{response:clone(current),meta:clone(f.meta)};},validate,remote,
  save:async(_p,_i,r,persist,{planned,armSaveIntent})=>{await armSaveIntent();saves++;assert.ok(r.requiredAttributeRepair.saveIntent);current={code:0,data:clone(planned)};await persist();},
  retry:async(_p,_i,view,_persist,{armIntent})=>{await armIntent();retries++;assert.ok(view.mediaRecovery.intent);view.mediaRecovery.nativeRequests=[{response:{httpStatus:200,body:{code:0}}}];current.data.status='publishing';current.data.errors=[];for(const row of current.data.items){row.status='accepted';row.extra.message=null;}},...extra};
 return{run:()=>repairNativeRequiredAttributes({},f.input,f.record,async()=>{},{amendment:f.amendment,schemaObservation:f.meta,...adapters}),setCurrent:v=>{current=clone(v);},counts:()=>({saves,retries,reads}),get current(){return clone(current);}};
}

test('complete raw candidate materializes exact native common columns and independent inventory without copying parent roles',()=>{
 const f=fixture();f.response.data.extra.attributes.parentage_level=[{value:'parent'}];f.response.data.extra.attributes.skip_offer=[{value:true}];const before=clone(f.response.data),planned=buildRequiredAttributesSource(before,f.input,f.meta,f.amendment);
 assert.deepEqual(f.response.data,before);assert.equal(planned.extra.attributes.unit_count[0].value,1);assert.equal(planned.extra.attributes.list_price[0].value_with_tax,0);
 for(const row of planned.items){assert.equal(row.extra.attributes.parentage_level,undefined);assert.equal(row.extra.attributes.skip_offer,undefined);assert.equal(row.extra.attributes.brand[0].value,'Brand');assert.equal(row.extra.attributes.outer[0].material[0].value,'100% polyester');assert.deepEqual(row.extra.images,before.items.find(x=>x.id===row.id).extra.images);}
});
test('one explicit Save and original-family retry preserve every historical accepted and other recovery receipt',async()=>{
 const f=fixture(),history=clone({identity:f.record.identity,source:f.record.sourceEvidence,link:f.record.sourceLink,failure:f.record.failureObservation,main:f.record.mainImageRepair,media:f.record.mediaRecovery}),r=runFixture(f);await r.run();await r.run();
 assert.deepEqual(r.counts(),{saves:1,retries:1,reads:4});assert.equal(f.record.requiredAttributeRepair.saveVerified,true);assert.deepEqual({identity:f.record.identity,source:f.record.sourceEvidence,link:f.record.sourceLink,failure:f.record.failureObservation,main:f.record.mainImageRepair,media:f.record.mediaRecovery},history);
});
test('unknown Save never repeats and exact persisted readback can permit only the separately intended retry',async()=>{
 const f=fixture();let saves=0;const r=runFixture(f,{save:async(_p,_i,_r,_persist,{armSaveIntent})=>{await armSaveIntent();saves++;throw Error('timed out');}});await assert.rejects(r.run,/timed out/);await assert.rejects(r.run,/回读不符/);assert.equal(saves,1);assert.equal(r.counts().retries,0);
 r.setCurrent({code:0,data:f.record.requiredAttributeRepair.plannedSource});await r.run();assert.equal(saves,1);assert.equal(r.counts().retries,1);
});
test('unknown retry cannot arm another Save or retry on any later continuation',async()=>{
 const f=fixture();let retryCalls=0;const r=runFixture(f,{retry:async(_p,_i,_r,_persist,{armIntent})=>{await armIntent();retryCalls++;throw Error('lost retry response');}});await assert.rejects(r.run,/lost retry/);await r.run();await r.run();assert.equal(retryCalls,1);assert.equal(r.counts().saves,1);
});
test('foreign identity fingerprints schema evidence and extra errors stop before writes',async()=>{
 for(const mutate of [f=>f.amendment.accountId=9,f=>f.amendment.sourceFingerprint='f'.repeat(64),f=>f.amendment.evidence.weaveText='ribbed cuffs',f=>f.meta.country_code='US',f=>f.response.data.items[0].extra.message.push({code:'300060',message:'another error'}),f=>f.amendment.children.reverse()]){
  const f=fixture();mutate(f);const r=runFixture(f);await assert.rejects(r.run);assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,0);
 }
});
test('real schema or original image failures remain preflight and can recheck once without replacing immutable source',async()=>{
 const f=fixture();const r=runFixture(f,{remote:async()=>{throw Error('bad image');}});await assert.rejects(r.run,/bad image/);const original=clone(f.record.requiredAttributeRepair.beforeSource);assert.equal(f.record.requiredAttributeRepair.saveIntent,undefined);
 const good=runFixture(f);await good.run();assert.deepEqual(f.record.requiredAttributeRepair.beforeSource,original);assert.equal(good.counts().saves,1);
});
test('healthy before arming permanently consumes the authorization including when failure returns',async()=>{
 const f=fixture(),r=runFixture(f);r.setCurrent(f.accepted);await r.run();r.setCurrent(f.response);await r.run();assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,0);assert.equal(f.record.requiredAttributeRepair.consumedWithoutWrite,true);
});
test('readback nonattribute price gallery or foreign attribute drift blocks original-family retry',async()=>{
 for(const mutate of [s=>s.items[0].price='1.00',s=>s.items[0].extra.images.reverse(),s=>s.extra.attributes.manufacturer[0].value='Other']){
  const f=fixture();let current=f.response;const r=runFixture(f,{read:async()=>({response:clone(current),meta:f.meta}),save:async(_p,_i,record,_persist,{planned,armSaveIntent})=>{await armSaveIntent();current={code:0,data:clone(planned)};mutate(current.data);}});await assert.rejects(r.run,/回读不符|持久|七图/);assert.equal(r.counts().retries,0);
 }
});
test('actual serialized Save guard rebuilds only one original-task request and rejects wrong ID endpoint flags or duplicates',()=>{
 for(const bad of [null,'id','endpoint','publish']){
  const f=fixture(),planned=buildRequiredAttributesSource(f.response.data,f.input,f.meta,f.amendment),plan={source:f.response.data,variationFields:f.input.destination.variationFields,guardId:'g',attributes:{parent:planned.extra.attributes,children:Object.fromEntries(planned.items.map(x=>[String(x.id),x.extra.attributes]))}},payload=clone(f.preview),sent=[];
  if(bad==='id')payload.id=999;if(bad==='publish')payload.with_publish=true;
  class XHR{open(){}addEventListener(){}send(body){sent.push(JSON.parse(body));}}
  const context=vm.createContext({window:{fetch:()=>{}},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com/#/amazon/product/202?type=publish'},plan,payload,endpoint:bad==='endpoint'?endpoint.replace('json-update','re-publish'):endpoint});
  vm.runInContext('('+installRequiredAttributesSaveGuard.toString()+')(plan)',context);
  const send=()=>vm.runInContext('(()=>{const x=new XMLHttpRequest();x.open("POST",endpoint);x.send(JSON.stringify(payload));})()',context);
  if(bad){assert.throws(send);assert.equal(sent.length,0);}else{send();assert.deepEqual(sent[0],patchRequiredAttributesSavePayload(payload,plan));assert.throws(send);assert.equal(sent.length,1);}
 }
});
test('confirmation callback requires three stable hit tests and exact token XHR and fetch bindings',()=>{
 let opacity='.5';const confirm={innerText:'确定',disabled:false,getBoundingClientRect:()=>({x:5,y:5,width:30,height:20}),contains:()=>false},box={innerText:'warning',getBoundingClientRect:()=>({x:0,y:0,width:100,height:100}),querySelectorAll:()=>[confirm]},open=()=>{},send=()=>{},fetch=()=>{};
 const context=vm.createContext({window:{fetch,__requiredAttributesSave:{guardId:'g',hookedOpen:open,hookedSend:send,hookedFetch:fetch,requests:[],error:null}},XMLHttpRequest:{prototype:{open,send}},document:{querySelectorAll:()=>[box],elementFromPoint:()=>confirm},innerWidth:800,innerHeight:600,getComputedStyle:()=>({opacity,visibility:'visible',pointerEvents:'auto'})});
 const check=()=>vm.runInContext('('+requiredAttributesConfirmationStable.toString()+')("g")',context);assert.equal(check(),false);opacity='1';assert.equal(check(),false);assert.equal(check(),false);assert.equal(check(),true);context.window.fetch=()=>{};assert.throws(check,/护栏/);
});

test('only the two observed readonly POST shapes pass; wrong seller brand type or apply endpoints never reach transport',()=>{
 const f=fixture();f.response.data.seller_id='EXACT-SELLER';const scope={seller_id:'EXACT-SELLER',country_code:'GB',primary_category_name:'Fashion',product_type_name:'SWEATSHIRT',brand:'Brand'};
 const cases=[{path:'/api/common/language-by-market',payload:{},allowed:true},{path:'/api/amazon/category/upc-exemption/check',payload:scope,allowed:true},
  {path:'/api/common/language-by-market',payload:{country_code:'US'}},{path:'/api/amazon/category/upc-exemption/check',payload:{...scope,seller_id:'OTHER'}},
  {path:'/api/amazon/category/upc-exemption/check',payload:{...scope,brand:'Other'}},{path:'/api/amazon/category/upc-exemption/check',payload:{...scope,product_type_name:'SHIRT'}},
  {path:'/api/amazon/category/upc-exemption/apply',payload:scope}];
 for(const row of cases){let sends=0;class XHR{open(){}addEventListener(){}send(){sends++;}}
  const context=vm.createContext({window:{fetch:()=>{}},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com'},plan:{source:f.response.data,guardId:'g'},url:'https://app.junfeikuajing.com'+row.path,payload:row.payload});
  vm.runInContext('('+installRequiredAttributesSaveGuard.toString()+')(plan)',context);
  const send=()=>vm.runInContext('(()=>{const x=new XMLHttpRequest();x.open("POST",url);x.send(JSON.stringify(payload));})()',context);
  if(row.allowed){send();assert.equal(sends,1);assert.equal(context.window.__requiredAttributesSave.requests.length,0);assert.equal(context.window.__requiredAttributesSave.readOnlyQueries.length,1);}else{assert.throws(send);assert.equal(sends,0);}
 }
});
test('a missing guard installation can never click Save or confirmation',async()=>{
 const f=fixture();f.record.requiredAttributeRepair={};let clicks=0;const page={waitForFunction:async()=>{},click:async()=>clicks++,evaluate:async fn=>fn===installRequiredAttributesSaveGuard?undefined:{present:false,requests:[]}};
 await assert.rejects(()=>submitNativeRequiredAttributesSave(page,f.input,f.record,async()=>{},{source:f.response.data,planned:buildRequiredAttributesSource(f.response.data,f.input,f.meta,f.amendment),amendment:f.amendment,armSaveIntent:async()=>{f.record.requiredAttributeRepair.saveIntent={publishId:'202'};}}),/护栏未绑定/);assert.equal(clicks,0);
});

function nativeSavePage(f,{loseBinding=false}={}){
 const clicked=[],sent=[];let visible=false,opacity='0.5';
 const button=(text,parent)=>({innerText:text,disabled:false,parentElement:parent,getBoundingClientRect:()=>({x:20,y:20,width:100,height:25}),setAttribute(){},scrollIntoView(){}});
 const toolbar={querySelectorAll:()=>[save,publish]},save=button('保存',toolbar),publish=button('保存并发布',toolbar),confirm=button('确定',{});
 const box={innerText:'颜色：Blue，Pink 不在亚马逊选项中。确定要保存吗？',getBoundingClientRect:()=>({x:10,y:10,width:visible?200:0,height:100}),querySelectorAll:()=>[confirm]};
 class XHR{open(){}addEventListener(_event,cb){this.done=cb;}send(body){sent.push(JSON.parse(body));this.status=200;this.responseText='{"code":0}';this.done?.();}}
 const originalFetch=()=>{},context=vm.createContext({window:{fetch:originalFetch},XMLHttpRequest:XHR,URL,Date,innerWidth:1280,innerHeight:900,getComputedStyle:()=>({opacity,visibility:'visible',pointerEvents:'auto'}),location:{href:'https://www.junfeikuajing.com/#/amazon/product/202?type=publish'},document:{readyState:'complete',title:'Amazon产品编辑 - 钧飞跨境',querySelector:s=>s==='input[placeholder="店铺"]'?{value:f.input.store}:s==='input[placeholder="产品标题"]'?{value:f.response.data.title}:null,querySelectorAll:s=>s==='.el-table__body-wrapper tr'?f.response.data.items.map(r=>({querySelector:()=>({value:r.sku})})):s==='button'?[save,publish]:s==='.el-message-box'?[box]:[],elementFromPoint:()=>confirm},payload:f.preview,endpoint});
 const page={evaluate:async(fn,arg)=>{context.arg=arg;return clone(vm.runInContext('('+fn.toString()+')(arg)',context));},
  waitForFunction:async(fn,arg)=>{context.waitArg=arg;for(let n=0;n<8;n++){if(fn===requiredAttributesConfirmationStable&&n===1)opacity='1';if(vm.runInContext('('+fn.toString()+')(waitArg)',context)){if(fn===requiredAttributesConfirmationStable&&loseBinding)context.window.fetch=()=>{};return;}}throw Error('fake native timeout');},
  click:async selector=>{clicked.push(selector);assert.equal(selector,'[data-required-save]');visible=true;},
  focus:async selector=>assert.equal(selector,'[data-required-confirm]'),
  press:async(selector,key)=>{assert.equal(selector,'[data-required-confirm]');assert.equal(key,'Enter');clicked.push(selector);vm.runInContext('(()=>{const x=new XMLHttpRequest();x.open("POST",endpoint);x.send(JSON.stringify(payload));})()',context);visible=false;}};
 return{page,clicked,sent,context};
}

test('native original Save waits through opacity animation and submits exactly the rebuilt payload after stable confirmation',async()=>{
 const f=fixture(),native=nativeSavePage(f),planned=buildRequiredAttributesSource(f.response.data,f.input,f.meta,f.amendment);f.record.requiredAttributeRepair={};
 await submitNativeRequiredAttributesSave(native.page,f.input,f.record,async()=>{},{source:f.response.data,planned,amendment:f.amendment,armSaveIntent:async()=>{f.record.requiredAttributeRepair.saveIntent={publishId:'202'};}});
 assert.deepEqual(native.clicked,['[data-required-save]','[data-required-confirm]']);assert.equal(native.sent.length,1);assert.equal(native.sent[0].items[0].attributes.weave_type[0].value,'Knit');
 assert.equal(f.record.requiredAttributeRepair.confirmGuardProof.prototypeBound,true);assert.equal(f.record.requiredAttributeRepair.confirmGuardProof.fetchBound,true);assert.equal(f.record.requiredAttributeRepair.confirmMethod,'native_focus_enter');assert.equal(native.context.window.__requiredAttributesSave,undefined);
});

test('a binding replaced after stable confirmation observations results in zero confirmation clicks or sends',async()=>{
 const f=fixture(),native=nativeSavePage(f,{loseBinding:true}),planned=buildRequiredAttributesSource(f.response.data,f.input,f.meta,f.amendment);f.record.requiredAttributeRepair={};
 await assert.rejects(()=>submitNativeRequiredAttributesSave(native.page,f.input,f.record,async()=>{},{source:f.response.data,planned,amendment:f.amendment,armSaveIntent:async()=>{f.record.requiredAttributeRepair.saveIntent={publishId:'202'};}}),/护栏失效/);
 assert.deepEqual(native.clicked,['[data-required-save]']);assert.equal(native.sent.length,0);assert.equal(f.record.requiredAttributeRepair.confirmGuardProof,undefined);
});

function preclickFixture(){
 const f=fixture(),j={amendmentId:f.amendment.id,amendment:clone(f.amendment),publishId:'202',phase:'save_unknown',
  beforeSource:clone(f.response.data),plannedSource:buildRequiredAttributesSource(f.response.data,f.input,f.meta,f.amendment),retry:{},
  saveIntent:{publishId:'202',armedAt:'original-preclick-intent',scope:'one_original_task_native_save'},
  lastSaveError:'page.waitForFunction timed out after 20000ms on page p2; last URL was "https://www.junfeikuajing.com/#/amazon/product/202?type=publish"; last title was "Amazon产品编辑 - 钧飞跨境".'};
 f.record.requiredAttributeRepair=j;
 f.amendment.preclickSaveRecovery={...clone(f.amendment),id:'preclick-recovery',scope:'resume_original_required_attributes_preclick_save',
  originalMainAmendmentId:f.amendment.id,originalSaveIntentArmedAt:j.saveIntent.armedAt,originalLastSaveError:j.lastSaveError,
  beforeSourceFingerprint:requiredAttributesSourceFingerprint(j.beforeSource),plannedSourceFingerprint:requiredAttributesSourceFingerprint(j.plannedSource)};
 return f;
}

test('preclick correction preserves old intent error and source while allowing exactly one separate Save and original retry',async()=>{
 const f=preclickFixture(),old=clone(f.record.requiredAttributeRepair),r=runFixture(f);await r.run();await r.run();
 assert.equal(r.counts().saves,1);assert.equal(r.counts().retries,1);const j=f.record.requiredAttributeRepair;
 for(const key of ['saveIntent','lastSaveError','beforeSource','plannedSource','amendment'])assert.deepEqual(j[key],old[key]);
 assert.equal(j.preclickSaveRecovery.amendmentId,'preclick-recovery');assert.ok(j.preclickSaveRecovery.saveIntent);assert.equal(j.preclickSaveRecovery.saveVerified,true);
});

test('unknown preclick correction stays original-ID readonly and cannot consume another Save even with the same explicit amendment',async()=>{
 const f=preclickFixture();let saves=0;const r=runFixture(f,{save:async(_p,_i,_r,_persist,{armSaveIntent})=>{await armSaveIntent();saves++;throw Error('new unknown');}});
 await assert.rejects(r.run,/new unknown/);await assert.rejects(r.run,/回读不符/);assert.equal(saves,1);
 assert.match(f.record.requiredAttributeRepair.lastSaveError,/20000ms/);assert.equal(f.record.requiredAttributeRepair.preclickSaveRecovery.lastSaveError,'new unknown');
 r.setCurrent({code:0,data:f.record.requiredAttributeRepair.plannedSource});await r.run();assert.equal(saves,1);assert.equal(r.counts().retries,1);
});

test('preclick correction rejects any earlier guard activity retry intent foreign scope or raw metadata drift',async()=>{
 for(const mutate of [f=>f.record.requiredAttributeRepair.nativeRequests=[],f=>f.record.requiredAttributeRepair.guardInstallProof=null,
  f=>f.record.requiredAttributeRepair.lastGuardSnapshot={},f=>f.record.requiredAttributeRepair.retry.intent={},f=>f.record.requiredAttributeRepair.saveVerified=false,
  f=>f.record.requiredAttributeRepair.lastSaveError='other timeout',f=>f.amendment.preclickSaveRecovery.originalSaveIntentArmedAt='wrong',
  f=>f.response.data.updated_at='different-original-version']){
  const f=preclickFixture();mutate(f);const r=runFixture(f);await assert.rejects(r.run);assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,0);
 }
});

test('page readiness timeout occurs before durable intent or guard installation and permits only a new preflight',async()=>{
 const f=fixture();f.record.requiredAttributeRepair={};let arms=0,clicks=0,evaluations=0;
 const page={waitForFunction:async(_fn,_arg,options)=>{assert.equal(options.timeout,60000);throw Error('not ready');},evaluate:async()=>evaluations++,click:async()=>clicks++};
 await assert.rejects(()=>submitNativeRequiredAttributesSave(page,f.input,f.record,async()=>{},{source:f.response.data,planned:buildRequiredAttributesSource(f.response.data,f.input,f.meta,f.amendment),amendment:f.amendment,armSaveIntent:async()=>arms++}),/not ready/);
 assert.equal(arms,0);assert.equal(clicks,0);assert.equal(evaluations,0);assert.equal(f.record.requiredAttributeRepair.saveIntent,undefined);
 delete f.record.requiredAttributeRepair;const r=runFixture(f);await r.run();assert.equal(r.counts().saves,1);
});

function retryPreflightFixture(){
 const f=preclickFixture(),j=f.record.requiredAttributeRepair;
 j.saveVerified=true;j.saveVerifiedAt='original-verified-save';j.phase='retry_unknown';
 j.schemaValidationAfterSave={passed:true,checkedCount:3,schemaHash:f.meta.hash};
 j.preclickSaveRecovery={amendmentId:f.amendment.preclickSaveRecovery.id,saveVerified:true,saveIntent:{armedAt:'successful-correction'},
  nativeRequests:[{method:'POST',url:endpoint,response:{httpStatus:200,body:{code:0}}}]};
 j.retry={intent:{publishId:'202',armedAt:'original-rejected-retry',scope:'original_family_all_children'},lastError:'原失败任务行或店铺不唯一，未再次发布'};
 f.amendment.retryPreflightRecovery={...clone(f.amendment),id:'retry-preflight-recovery',scope:'resume_original_required_attributes_retry_preflight',
  originalMainAmendmentId:f.amendment.id,originalRetryIntentArmedAt:j.retry.intent.armedAt,originalRetryLastError:j.retry.lastError,
  originalSaveVerifiedAt:j.saveVerifiedAt,plannedSourceFingerprint:requiredAttributesSourceFingerprint(j.plannedSource)};
 return f;
}

test('confirmed native Save with original query-only retry rejection permits one separate retry and zero more Saves',async()=>{
 const f=retryPreflightFixture(),old=clone(f.record.requiredAttributeRepair),r=runFixture(f);r.setCurrent({code:0,data:old.plannedSource});await r.run();await r.run();
 assert.equal(r.counts().saves,0);assert.equal(r.counts().retries,1);const j=f.record.requiredAttributeRepair;
 for(const key of ['saveIntent','lastSaveError','beforeSource','plannedSource','remoteChecks','amendment','retry','preclickSaveRecovery'])assert.deepEqual(j[key],old[key]);
 assert.equal(j.saveVerifiedAt,'original-verified-save');assert.ok(j.retryPreflightRecovery.intent);
});

test('a new retry timeout is permanently readonly; any original retry guard history or missing Save evidence rejects the correction',async()=>{
 const f=retryPreflightFixture();let calls=0;const r=runFixture(f,{retry:async(_p,_i,_r,_persist,{armIntent})=>{await armIntent();calls++;throw Error('retry response unknown');}});r.setCurrent({code:0,data:f.record.requiredAttributeRepair.plannedSource});
 await assert.rejects(r.run,/retry response unknown/);await r.run();assert.equal(calls,1);assert.equal(r.counts().saves,0);
 for(const mutate of [x=>x.record.requiredAttributeRepair.retry.nativeRequests=[],x=>x.record.requiredAttributeRepair.retry.guardError=null,
  x=>x.record.requiredAttributeRepair.retry.lastError='another error',x=>x.record.requiredAttributeRepair.preclickSaveRecovery.nativeRequests[0].response.body.code=1,
  x=>x.amendment.retryPreflightRecovery.originalRetryIntentArmedAt='other']){
  const x=retryPreflightFixture();mutate(x);const run=runFixture(x);run.setCurrent({code:0,data:x.record.requiredAttributeRepair.plannedSource});await assert.rejects(run.run);assert.equal(run.counts().saves,0);assert.equal(run.counts().retries,0);
 }
});
