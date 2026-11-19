import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {assertPublicationInput,publicationFingerprint,publicationFailureObservation,verifyPublication} from './ego-publish-native.mjs';
import {repairNativeMainImage,patchMainImageSavePayload,installMainImageSaveGuard,submitNativeMainImageSave,mainImageSaveConfirmationStable,mainImageBusinessProjection} from './ego-publication-main-image.mjs';

const clone=value=>structuredClone(value),endpoint='https://app.junfeikuajing.com/api/amazon/goods/publish/json-update';
function fixture(){
 const assets=Array.from({length:35},(_,index)=>({sha256:createHash('sha256').update('main-repair-'+index).digest('hex'),width:1600,height:1600}));
 const urls=Object.fromEntries(assets.map((asset,index)=>[asset.sha256,'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/u/11/26/11/s_'+index+'.png']));
 const sizes={S:'s',M:'m',L:'l',XL:'x_l',XXL:'xx_l','3XL':'3x_l'},goodsItems=['01-white','01-black','01-brown','01-gray','01-red'].flatMap((color,c)=>Object.keys(sizes).map(size=>({sku:'Original-'+color+'-'+size,color,size,price:'13.95',quantity:88,imageIndices:Array.from({length:7},(_,index)=>c*7+index)})));
 const input={accountId:2,productId:'original-product',jobId:'original-job',sha256:'original-sha',marketplace:'US',mode:'draft',store:'Original US Store',masterColor:'01-white',assets,urls,goodsItems,
  goods:{parentSku:'Original',title:'Original title',brand:'Original Brand',manufacturer:'Original Maker',description:'Original description',bullets:['Original bullet'],terms:'original terms'},
  destination:{destinationId:'us',draftId:'101',marketId:'91',erpAccountId:'11',countryCode:'US',marketplaceId:'USMARKET',schemaHash:'actual-us-hash',sizeValues:sizes,variationFields:{color:'color.0.value',size:'shirt_size.0.size'}}};
 const common={fabric_type:[{value:'95% Polyester, 5% Elastane'}],country_of_origin:[{value:'CN'}],care_instructions:[{value:'Machine Wash'}],model_name:[{value:'1156'}],condition_type:[{value:'new_new'}],special_size_type:[{value:'Standard'}],merchant_shipping_group:[{value:'original-template',marketplace_id:'USMARKET'}],supplier_declared_has_product_identifier_exemption:[{value:true,marketplace_id:'USMARKET'}]};
 const cover=urls[assets[0].sha256],accepted={code:0,data:{id:202,uid:11,market_id:91,country_code:'US',market:{alias:input.store},sku:'Original',title:input.goods.title,brand:input.goods.brand,manufacturer:input.goods.manufacturer,
  product_type_name:'SHIRT',category_path:'Original category',price:'13.95',quantity:88,cost_price:'11.88',country_of_origin:'CN',standard_product_type:'UPC',standard_product_id:null,list_price:null,part_number:null,pallet_goods_id:null,pallet_service_unique:null,variation_theme:'COLOR_NAME/SIZE_NAME',main_image:cover,status:'publishing',errors:[],
  extra:{images:[cover],keywords:input.goods.terms,product_description:input.goods.description,bullet_point:input.goods.bullets,attributes:clone(common)},
  items:goodsItems.map((item,index)=>({id:203+index,pid:202,uid:11,sku:item.sku,price:item.price,quantity:item.quantity,cost_price:'11.88',title:null,list_price:null,standard_product_id:null,standard_product_type:null,
   status:'accepted',asin:null,main_image:urls[assets[item.imageIndices[0]].sha256],extra:{images:item.imageIndices.map(i=>urls[assets[i].sha256]),keywords:null,product_description:'',bullet_point:null,message:null,
    attributes:{...clone(common),fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:88,lead_time_to_ship_max_days:3}],parentage_level:[{value:'child'}],child_parent_sku_relationship:[{parent_sku:'Original',child_relationship_type:'variation'}],variation_theme:[{name:'COLOR_NAME/SIZE_NAME'}],color:[{value:item.color,marketplace_id:'USMARKET'}],shirt_size:[{size:sizes[item.size],size_system:'as1',size_class:'alpha',body_type:'regular',height_type:'regular',marketplace_id:'USMARKET'}]}}}))}};
 accepted.data.updated_at='2026-11-16 22:03:06';accepted.data.extra.updated_at='2026-11-16 16:36:44';for(const row of accepted.data.items){row.updated_at='2026-11-16 22:03:06';row.extra.updated_at='2026-11-16 16:36:44';}
 const response=clone(accepted),target=response.data.items.find(row=>row.sku==='Original-01-gray-XXL');response.data.status='failed';target.status='failed';
 response.data.errors=[{sku:target.sku,code:'18320',message:'Main image missing or incorrect',severity:'ERROR'}];target.extra.message=[{code:'18320',message:'Main image missing or incorrect',severity:'ERROR'}];
 const record={publishId:'202',fingerprint:publicationFingerprint(assertPublicationInput(input)),identity:verifyPublication(accepted,input,'202'),sourceEvidence:clone(accepted.data),sourceLink:{publishId:'202',draftId:'101'},phase:'publication_failed',status:'failed',mediaRecovery:{intent:{original:'keep'},nativeRequests:[{original:'keep'}]}};
 record.failureObservation=publicationFailureObservation(response,input,'202');record.latestObservation=record.failureObservation;
 const amendment={id:'main-amendment',scope:'repair_original_failed_main_image',marketplace:'US',accountId:2,productId:input.productId,jobId:input.jobId,snapshotSha256:input.sha256,publishId:'202',destinationId:'us',draftId:'101',erpAccountId:'11',marketId:'91',countryCode:'US',store:input.store,parentSku:'Original',failedChildId:String(target.id),failedSku:target.sku,mainImageUrl:target.main_image,assetSha256:assets[goodsItems.find(item=>item.sku===target.sku).imageIndices[0]].sha256,failureResponseFingerprint:record.failureObservation.responseFingerprint,authorizedAt:1794888000,retryOriginalTaskAfterVerifiedSave:true};
 const meta={hash:'actual-us-hash',country_code:'US',locale:'en_US',schema_content:{
  $defs:{marketplace_id:{default:'USMARKET'}},properties:{main_product_image_locator:{type:'array',items:{type:'object',required:['media_location'],properties:{marketplace_id:{$ref:'#/$defs/marketplace_id'},media_location:{type:'string'}}}}}
 }};
 const plan={source:response.data,variationFields:input.destination.variationFields,failedChildId:amendment.failedChildId,failedSku:amendment.failedSku,mainImageUrl:amendment.mainImageUrl,marketplaceId:'USMARKET'};
 const preview={};
 for(const key of ['market_id','title','id','brand','price','quantity','country_code','pallet_service_unique','pallet_goods_id','part_number','standard_product_type','standard_product_id','list_price','cost_price','manufacturer','country_of_origin','variation_theme','main_image','product_type_name','category_path','sku'])preview[key]=response.data[key];
 Object.assign(preview,{keywords:input.goods.terms,product_description:input.goods.description,bullet_point:input.goods.bullets,parent_sku:'Original',variation:{},images:Object.values(urls),attributes:{model_number:[{value:'OLD DEFAULT'}]},items:response.data.items.map(row=>({id:row.id,attributes:{color:clone(row.extra.attributes.color),shirt_size:[{size:row.extra.attributes.shirt_size[0].size,marketplace_id:'USMARKET'}],supplier_declared_has_product_identifier_exemption:[{value:true}]},keywords:null,list_price:null,product_description:'',price_info:{'purchasable_offer.0.maximum_seller_allowed_price.0.schedule.0.value_with_tax':'','purchasable_offer.0.minimum_seller_allowed_price.0.schedule.0.value_with_tax':''},bullet_point:null,title:null,main_image:row.main_image,images:clone(row.extra.images),variation:{'color.0.value':row.extra.attributes.color[0].value,'shirt_size.0.size':row.extra.attributes.shirt_size[0].size},standard_product_type:'UPC',cost_price:'11.88',price:'13.95',quantity:88,title_differentiation:'',sku:row.sku,standard_product_id:null}))});
 const saved=clone(response);saved.data.items.find(row=>row.id===target.id).extra.attributes.main_product_image_locator=[{marketplace_id:'USMARKET',media_location:target.main_image}];
 return{input,response,record,amendment,meta,plan,preview,saved,accepted};
}
const validate=async(_meta,records)=>{assert.equal(records.length,31);for(const record of records){assert.equal(record.attributes.care_instructions[0].value,'Machine Wash');assert.equal(record.attributes.model_name[0].value,'1156');if(record.id!=='parent')assert.equal(record.attributes.shirt_size[0].size_class,'alpha');}return{passed:true,checkedCount:31};};
const remote=async(_url,asset)=>({sha256:asset.sha256,bytes:100});
const retryAccepted=async(_page,_input,record)=>{record.mediaRecovery.nativeRequests=[{method:'POST',url:'https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish',payload:{ids:[202]},response:{httpStatus:200,body:{code:0}}}];};
function authorizeCorrective(f){
 const saveIntent={publishId:'202',failedChildId:f.amendment.failedChildId,amendmentId:f.amendment.id,armedAt:'2026-11-17T03:21:44.408Z'};
 f.record.mainImageRepair={amendmentId:f.amendment.id,amendment:clone(f.amendment),beforeSource:clone(f.response.data),beforeBusinessProjection:mainImageBusinessProjection(f.response.data),
  saveIntent,nativeRequests:[],lastSaveError:'page.waitForFunction timed out after 25000ms',retry:{},phase:'save_unknown'};
 f.amendment.correctiveSave={...clone(f.amendment),id:'corrective-amendment',scope:'explicit_idempotent_original_main_resave',originalMainAmendmentId:f.amendment.id,originalSaveIntentArmedAt:saveIntent.armedAt,authorizedAt:1794889000};
 return clone(f.record.mainImageRepair);
}

test('native Save payload restores all original attrs and galleries and changes only the failed child MAIN locator',()=>{
 const f=fixture(),before=clone(f.preview),patched=patchMainImageSavePayload(f.preview,f.plan);
 assert.deepEqual(f.preview,before);assert.deepEqual(patched.attributes,f.response.data.extra.attributes);assert.deepEqual(patched.images,f.response.data.extra.images);
 for(const row of patched.items){const original=f.response.data.items.find(item=>item.id===row.id),expected=clone(original.extra.attributes);if(String(row.id)===f.amendment.failedChildId)expected.main_product_image_locator=[{marketplace_id:'USMARKET',media_location:original.main_image}];assert.deepEqual(row.attributes,expected);assert.equal(row.standard_product_type,null);assert.deepEqual(row.images,original.extra.images);assert.equal(row.price,original.price);assert.equal(row.sku,original.sku);}
 assert.equal(patched.items.length,30);assert.equal(patched.publish,undefined);assert.equal(patched.with_publish,undefined);
});

test('wrong original ID SKU prices image URLs extra write flags and duplicate children are rejected before sending',()=>{
 for(const alter of [body=>body.id=999,body=>body.sku='Other',body=>body.items[0].price='999',body=>body.items[0].sku='Other-S',body=>body.items[0].images.reverse(),body=>body.images.push('https://other.example/new.png'),body=>body.with_publish=true,body=>body.items[1]=clone(body.items[0])]){
  const f=fixture();alter(f.preview);assert.throws(()=>patchMainImageSavePayload(f.preview,f.plan));
 }
});

test('MAIN repair validates all thirty-one records before Save, verifies original media, saves once and retries the same family once',async()=>{
 const f=fixture(),oldRecovery=clone(f.record.mediaRecovery),events=[],snapshots=[];let current=f.response;
 const result=await repairNativeMainImage({},f.input,f.record,async()=>snapshots.push(clone(f.record)),{amendment:f.amendment,schemaObservation:f.meta,
  observe:async()=>({response:current,meta:f.meta}),validate:async(meta,rows)=>{events.push('schema');return validate(meta,rows);},remote:async(url,asset)=>{events.push('media');return remote(url,asset);},
  save:async(_page,_input,record)=>{assert.ok(snapshots.at(-1).mainImageRepair.saveIntent);assert.equal(record.mainImageRepair.beforeSource.items.length,30);events.push('save');current=f.saved;},
  retry:async(page,input,record)=>{assert.ok(snapshots.at(-1).mainImageRepair.retry.intent);events.push('retry');return retryAccepted(page,input,record);}});
 assert.deepEqual(events,['schema','schema','media','save','schema','retry']);assert.equal(result.saveVerified,true);assert.equal(result.retry.requestAccepted,true);assert.equal(f.record.phase,'publication_failed');assert.equal(f.record.publishId,'202');assert.deepEqual(f.record.mediaRecovery,oldRecovery);
 assert.deepEqual(result.beforeSource,f.response.data);assert.deepEqual(result.beforeAttributes.parent,f.response.data.extra.attributes);
});

test('authorization identity schema failure and wrong media proof stop before a Save intent or retry',async()=>{
 for(const alter of [f=>delete f.amendment.jobId,f=>f.amendment.mainImageUrl='https://other.example/new.png',f=>f.amendment.assetSha256='0'.repeat(64),f=>f.meta.country_code='GB',f=>f.meta.schema_content.properties.main_product_image_locator.items.required=[],f=>f.amendment.failureResponseFingerprint='0'.repeat(64)]){
  const f=fixture();alter(f);let writes=0;await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},{amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:f.response,meta:f.meta}),validate,remote,save:async()=>writes++,retry:async()=>writes++}));assert.equal(writes,0);assert.equal(f.record.mainImageRepair?.saveIntent,undefined);
 }
 const f=fixture();let writes=0;await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},{amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:f.response,meta:f.meta}),validate,remote:async()=>({sha256:'wrong',bytes:100}),save:async()=>writes++,retry:async()=>writes++}));assert.equal(writes,0);assert.equal(f.record.mainImageRepair.saveIntent,undefined);
});

test('an already correct original locator is read-only and never arms Save or retry',async()=>{
 const f=fixture();const result=await repairNativeMainImage({},f.input,f.record,async()=>{},{amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:f.saved,meta:f.meta}),validate,remote:async()=>assert.fail('no image fetch'),save:async()=>assert.fail('no save'),retry:async()=>assert.fail('no retry')});assert.equal(result.phase,'already_correct');assert.equal(result.consumedWithoutWrite,true);assert.equal(result.saveIntent,undefined);
});

test('unknown Save never repeats; later original-ID readback can prove it saved and perform only its separately intended retry',async()=>{
 const f=fixture();let saves=0,retries=0,current=f.response;
 const options={amendment:f.amendment,schemaObservation:f.meta,observe:async(_p,_i,id)=>{assert.equal(id,'202');return{response:current,meta:f.meta};},validate,remote,
  save:async()=>{saves++;throw Error('save response lost');},retry:async(page,input,record)=>{retries++;return retryAccepted(page,input,record);}};
 await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},options),/response lost/);assert.ok(f.record.mainImageRepair.saveIntent);
 await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},options),/不再次保存/);assert.equal(saves,1);assert.equal(retries,0);
 current=f.saved;await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(saves,1);assert.equal(retries,1);
 await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(saves,1);assert.equal(retries,1);
});

test('loss after retry click and later pending or accepted states never cause another save or retry',async()=>{
 const f=fixture();let current=f.response,saves=0,retries=0;
 const options={amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:current,meta:f.meta}),validate,remote,save:async()=>{saves++;current=f.saved;},retry:async()=>{retries++;throw Error('retry response lost');}};
 await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},options),/retry response lost/);
 for(const state of ['failed','waiting','publishing']){current=clone(f.saved);current.data.status=state;if(state!=='failed'){current.data.errors=[];for(const row of current.data.items){row.status=state==='waiting'?'waiting':'accepted';row.extra.message=null;}}await repairNativeMainImage({},f.input,f.record,async()=>{},options);}
 assert.equal(saves,1);assert.equal(retries,1);
});

test('after Save, unrelated attribute or gallery drift prevents same-family retry',async()=>{
 for(const mutate of [source=>source.items[0].extra.attributes.care_instructions[0].value='Dry Clean',source=>source.items[0].extra.images.reverse(),source=>source.extra.attributes.model_name[0].value='Wrong']){
  const f=fixture();let current=f.response,retries=0;await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},{amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:current,meta:f.meta}),validate,remote,save:async()=>{current=clone(f.saved);mutate(current.data);},retry:async()=>retries++}));assert.equal(retries,0);assert.equal(f.record.mainImageRepair.saveVerified,undefined);
 }
});

test('known preflight failure without an intent can recheck the same immutable before-source and save only once',async()=>{
 const f=fixture();let current=f.response,saves=0,healthyMedia=false;
 const options={amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:current,meta:f.meta}),validate,
  remote:async(url,asset)=>{if(!healthyMedia)throw Error('temporary public GET failure');return remote(url,asset);},save:async()=>{saves++;current=f.saved;},retry:retryAccepted};
 await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},options),/temporary public GET/);
 const original=clone(f.record.mainImageRepair.beforeSource);assert.equal(f.record.mainImageRepair.saveIntent,undefined);
 healthyMedia=true;await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(saves,1);assert.deepEqual(f.record.mainImageRepair.beforeSource,original);
});

test('later ASINs and reordered object keys remain provider observations rather than another Save or retry',async()=>{
 const f=fixture();let current=f.response,saves=0,retries=0;
 const options={amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:current,meta:f.meta}),validate,remote,save:async()=>{saves++;current=f.saved;},retry:async(page,input,record)=>{retries++;return retryAccepted(page,input,record);}};
 await repairNativeMainImage({},f.input,f.record,async()=>{},options);
 current=clone(f.saved);current.data.status='publishing';current.data.asin='B0PARENT';current.data.errors=[];
 for(const row of current.data.items){row.status='accepted';row.asin='B0'+row.id;row.extra.message=null;row.extra.attributes=Object.fromEntries(Object.entries(row.extra.attributes).reverse());}
 const target=current.data.items.find(row=>String(row.id)===f.amendment.failedChildId);target.extra.attributes.main_product_image_locator=[{media_location:target.main_image,marketplace_id:'USMARKET'}];
 await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(saves,1);assert.equal(retries,1);assert.equal(f.record.mainImageRepair.saveVerified,true);
});

test('healthy or pending before Save consumes this authorization without a write, including if failure returns later',async()=>{
 for(const state of ['publishing','waiting'])for(const afterPreflight of [false,true]){
  const f=fixture(),noLongerFailed=clone(f.accepted);noLongerFailed.data.status=state;let reads=0,remotes=0,current;
  const options={amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:current||(afterPreflight&&++reads===1?f.response:noLongerFailed),meta:f.meta}),validate,
   remote:async(url,asset)=>{remotes++;return remote(url,asset);},save:async()=>assert.fail('must not save'),retry:async()=>assert.fail('must not retry')};
  const result=await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(result.consumedWithoutWrite,true);assert.equal(result.resolvedNoWriteVerified,true);assert.equal(result.saveWasNeeded,false);assert.equal(result.saveIntent,undefined);
  current=f.response;await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(result.saveIntent,undefined);assert.equal(remotes,afterPreflight?1:0);
 }
});

test('normal Save chooses the original Save beside Save-and-publish and confirms only its observed color warning',async()=>{
 const f=fixture(),sent=[],clicked=[];f.record.mainImageRepair={saveIntent:{publishId:'202'}};let boxVisible=false;
 const attrs={},button=(label,parent)=>({innerText:label,disabled:false,parentElement:parent,getBoundingClientRect:()=>({x:20,y:20,width:100,height:25}),setAttribute:(key,value)=>attrs[key]=value,scrollIntoView(){}});
 const toolbar={querySelectorAll:()=>[save,publish]},gpsrParent={querySelectorAll:()=>[gpsr]},save=button('保存',toolbar),publish=button('保存并发布',toolbar),gpsr=button('保存',gpsrParent),confirm=button('确定',{});
 const warning={innerText:'提示\n颜色：#01-white，01-black，01-brown，01-gray，01-red\n不在亚马逊选项中。确定要保存吗？\n取消确定',getBoundingClientRect:()=>({x:10,y:10,width:boxVisible?200:0,height:100}),querySelectorAll:()=>[confirm]};
 class XHR{constructor(){this.listeners=[];}open(method,url){this.method=method;this.url=url;}addEventListener(_event,listener){this.listeners.push(listener);}send(body){sent.push(JSON.parse(body));this.status=200;this.responseText=JSON.stringify({code:0});for(const listener of this.listeners)listener();}}
 const context=vm.createContext({window:{fetch:()=>assert.fail('unexpected fetch')},XMLHttpRequest:XHR,URL,Date,innerWidth:1280,innerHeight:900,getComputedStyle:()=>({opacity:'1',visibility:'visible',pointerEvents:'auto'}),location:{href:'https://www.junfeikuajing.com/#/amazon/product/202?type=publish'},document:{elementFromPoint:()=>confirm,querySelectorAll:selector=>selector==='button'?[save,publish,gpsr]:selector==='.el-message-box'?[warning]:[]},payload:f.preview,endpoint});
 const page={evaluate:async(fn,arg)=>{assert.equal(typeof fn,'function','native helper must use documented callback plus JSON, never string execution semantics');context.arg=arg;return clone(vm.runInContext('('+fn.toString()+')(arg)',context));},
  waitForFunction:async(fn,arg)=>{context.waitArg=arg;for(let count=0;count<6;count++)if(vm.runInContext('('+fn.toString()+')(waitArg)',context))return;assert.fail('fake wait condition never completed');},
  click:async selector=>{clicked.push(selector);if(selector==='[data-original-main-save]'){assert.equal(attrs['data-original-main-save'],'true');boxVisible=true;}else{assert.equal(selector,'[data-original-main-confirm]');assert.equal(attrs['data-original-main-confirm'],'true');vm.runInContext('const request=new XMLHttpRequest();request.open("POST",endpoint);request.send(JSON.stringify(payload));',context);boxVisible=false;}}};
 await submitNativeMainImageSave(page,f.input,f.record,async()=>{},{source:f.response.data,amendment:f.amendment});
 assert.deepEqual(clicked,['[data-original-main-save]','[data-original-main-confirm]']);assert.equal(sent.length,1);assert.deepEqual(sent[0],patchMainImageSavePayload(f.preview,f.plan));assert.equal(context.window.__mainImageSave,undefined);
 assert.equal(f.record.mainImageRepair.confirmGuardProof.guardId,f.amendment.id);assert.equal(f.record.mainImageRepair.confirmGuardProof.prototypeBound,true);assert.equal(f.record.mainImageRepair.confirmGuardProof.fetchBound,true);
});

test('the production native Save guard emits only one rebuilt original-task request and blocks publishing or another ID',()=>{
 for(const bad of [{url:endpoint.replace('json-update','re-publish')},{id:999},{publish:true}]){
  const f=fixture(),sent=[];class XHR{open(method,url){this.method=method;this.url=url;}addEventListener(){}send(body){sent.push(JSON.parse(body));}}
  const context=vm.createContext({window:{},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com/#/amazon/product/202?type=publish'},plan:f.plan,payload:{...f.preview,...(bad.id?{id:bad.id}:{}),...(bad.publish?{publish:true}:{})},endpoint:bad.url||endpoint});
  vm.runInContext('const patchMainImageSavePayload='+patchMainImageSavePayload.toString()+';('+installMainImageSaveGuard.toString()+')(plan);',context);
  assert.throws(()=>vm.runInContext('const xhr=new XMLHttpRequest();xhr.open("POST",endpoint);xhr.send(JSON.stringify(payload));',context));assert.equal(sent.length,0);
 }
 const f=fixture(),sent=[];class XHR{open(){}addEventListener(){}send(body){sent.push(JSON.parse(body));}}
 const context=vm.createContext({window:{},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com'},plan:f.plan,payload:f.preview,endpoint});
 vm.runInContext('const patchMainImageSavePayload='+patchMainImageSavePayload.toString()+';('+installMainImageSaveGuard.toString()+')(plan);const xhr=new XMLHttpRequest();xhr.open("POST",endpoint);xhr.send(JSON.stringify(payload));',context);
 assert.equal(sent.length,1);assert.deepEqual(sent[0],patchMainImageSavePayload(f.preview,f.plan));assert.throws(()=>vm.runInContext('const other=new XMLHttpRequest();other.open("POST",endpoint);other.send(JSON.stringify(payload));',context));assert.equal(sent.length,1);
});

test('an explicit corrective save has a separate one-shot intent and preserves the old unknown history intact',async()=>{
 const f=fixture(),original=authorizeCorrective(f);let current=f.response,saves=0,retries=0;const snapshots=[];
 const options={amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:current,meta:f.meta}),validate,remote,
  save:async(_p,_i,view)=>{saves++;assert.equal(view.mainImageRepair,f.record.mainImageRepair.correctiveSave);assert.ok(snapshots.at(-1).correctiveSave.saveIntent);assert.equal(view.mainImageRepair.saveIntent.scope,'explicit_idempotent_original_main_resave');current=f.saved;},
  retry:async(page,input,record)=>{retries++;return retryAccepted(page,input,record);}};
 const result=await repairNativeMainImage({},f.input,f.record,async()=>snapshots.push(clone(f.record.mainImageRepair)),options);
 assert.equal(saves,1);assert.equal(retries,1);assert.equal(result.correctiveSave.saveVerified,true);assert.equal(result.saveVerifiedByCorrectiveId,'corrective-amendment');
 for(const key of ['saveIntent','nativeRequests','lastSaveError','beforeSource','amendment'])assert.deepEqual(result[key],original[key]);
 await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(saves,1);assert.equal(retries,1);
});

test('an unknown corrective response never permits another corrective save or original Save',async()=>{
 const f=fixture();authorizeCorrective(f);let saves=0;
 const options={amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:f.response,meta:f.meta}),validate,remote,save:async()=>{saves++;throw Error('corrective response lost');},retry:async()=>assert.fail('no retry')};
 await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},options),/corrective response lost/);
 assert.ok(f.record.mainImageRepair.correctiveSave.saveIntent);
 await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},options),/不再次保存/);assert.equal(saves,1);
});

test('corrective scope mismatches requests evidence or changed source timestamps cannot reach a write',async()=>{
 for(const alter of [f=>f.amendment.correctiveSave.originalSaveIntentArmedAt='Other',f=>f.amendment.correctiveSave.failedSku='Other',f=>f.amendment.correctiveSave.accountId=3,
  f=>f.record.mainImageRepair.nativeRequests.push({unknown:true}),f=>f.record.mainImageRepair.guardError='blocked',f=>f.record.mainImageRepair.retry.intent={publishId:'202'},
  f=>f.response.data.updated_at='later',f=>f.response.data.items[0].extra.updated_at='later',f=>f.response.data.extra.attributes.model_name[0].value='changed']){
  const f=fixture();authorizeCorrective(f);alter(f);let writes=0;
  await assert.rejects(()=>repairNativeMainImage({},f.input,f.record,async()=>{},{amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:f.response,meta:f.meta}),validate,remote,save:async()=>writes++,retry:async()=>writes++}));
  assert.equal(writes,0);assert.equal(f.record.mainImageRepair.correctiveSave?.saveIntent,undefined);
 }
});

test('corrective authorization is consumed without a write if the original task becomes healthy or pending',async()=>{
 for(const status of ['publishing','waiting']){
  const f=fixture();authorizeCorrective(f);let current=clone(f.accepted);current.data.status=status;
  const options={amendment:f.amendment,schemaObservation:f.meta,observe:async()=>({response:current,meta:f.meta}),validate,remote:async()=>assert.fail('no media request'),save:async()=>assert.fail('no Save'),retry:async()=>assert.fail('no retry')};
  const result=await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(result.correctiveSave.consumedWithoutWrite,true);assert.equal(result.resolvedNoWriteVerified,true);
  current=f.response;await repairNativeMainImage({},f.input,f.record,async()=>{},options);assert.equal(result.correctiveSave.saveIntent,undefined);
 }
});

test('the confirmation waits for three stable hit-tested observations after animation or overlay ends',()=>{
 let opacity='0.5',blocked=false;const button={innerText:'确定',disabled:false,getBoundingClientRect:()=>({x:10,y:10,width:40,height:20}),contains:()=>false},box={innerText:'known original warning',getBoundingClientRect:()=>({x:0,y:0,width:100,height:100}),querySelectorAll:()=>[button]};
 const open=()=>{},send=()=>{},fetch=()=>{};
 const context=vm.createContext({window:{fetch,__mainImageSave:{guardId:'original-guard',hookedOpen:open,hookedSend:send,hookedFetch:fetch,requests:[],error:null}},XMLHttpRequest:{prototype:{open,send}},document:{querySelectorAll:()=>[box],elementFromPoint:()=>blocked?{}:button},innerWidth:800,innerHeight:600,getComputedStyle:()=>({opacity,visibility:'visible',pointerEvents:'auto'})});
 const check=()=>vm.runInContext('('+mainImageSaveConfirmationStable.toString()+')("original-guard")',context);
 assert.equal(check(),false);opacity='1';assert.equal(check(),false);assert.equal(check(),false);assert.equal(check(),true);blocked=true;assert.equal(check(),false);blocked=false;assert.equal(check(),false);assert.equal(check(),false);assert.equal(check(),true);
});

test('losing XHR fetch or the exact guard identity during confirmation waits or after stability prevents any confirmation click',async()=>{
 for(const timing of ['during-stability','after-stability'])for(const target of ['open','send','fetch','guardId']){
  const f=fixture(),clicked=[],sent=[];f.record.mainImageRepair={saveIntent:{publishId:'202'}};let visible=false;
  const button=(text,parent)=>({innerText:text,disabled:false,parentElement:parent,getBoundingClientRect:()=>({x:20,y:20,width:100,height:25}),setAttribute(){},scrollIntoView(){}});
  const toolbar={querySelectorAll:()=>[save,publish]},save=button('保存',toolbar),publish=button('保存并发布',toolbar),confirm=button('确定',{});
  const box={innerText:'颜色：01-white，01-black，01-brown，01-gray，01-red 不在亚马逊选项中。确定要保存吗？',getBoundingClientRect:()=>({x:10,y:10,width:visible?200:0,height:100}),querySelectorAll:()=>[confirm]};
  class XHR{open(){}send(body){sent.push(body);}addEventListener(){}}
  const context=vm.createContext({window:{fetch:()=>{}},XMLHttpRequest:XHR,URL,Date,innerWidth:1280,innerHeight:900,getComputedStyle:()=>({opacity:'1',visibility:'visible',pointerEvents:'auto'}),location:{href:'https://www.junfeikuajing.com/#/amazon/product/202?type=publish'},document:{querySelectorAll:selector=>selector==='button'?[save,publish]:selector==='.el-message-box'?[box]:[],elementFromPoint:()=>confirm}});
  const loseGuard=()=>{if(target==='guardId')context.window.__mainImageSave.guardId='Other';else if(target==='fetch')context.window.fetch=()=>{};else context.XMLHttpRequest.prototype[target]=()=>{};};
  const page={evaluate:async(fn,arg)=>{context.arg=arg;return clone(vm.runInContext('('+fn.toString()+')(arg)',context));},
   waitForFunction:async(fn,arg)=>{context.waitArg=arg;if(fn===mainImageSaveConfirmationStable&&timing==='during-stability')loseGuard();for(let count=0;count<6;count++)if(vm.runInContext('('+fn.toString()+')(waitArg)',context)){if(fn===mainImageSaveConfirmationStable&&timing==='after-stability')loseGuard();return;}assert.fail('unexpected wait timeout');},
   click:async selector=>{clicked.push(selector);if(selector==='[data-original-main-save]')visible=true;else assert.fail('unprotected confirmation must not be clicked');}};
  await assert.rejects(()=>submitNativeMainImageSave(page,f.input,f.record,async()=>{},{source:f.response.data,amendment:f.amendment}),/护栏/);
  assert.deepEqual(clicked,['[data-original-main-save]']);assert.equal(sent.length,0);assert.equal(f.record.mainImageRepair.confirmGuardProof,undefined);
 }
});

test('an unconfirmed guard installation stops before either Save or color confirmation can be clicked',async()=>{
 const f=fixture();f.record.mainImageRepair={saveIntent:{publishId:'202'}};let clicks=0;
 const page={waitForFunction:async()=>{},click:async()=>clicks++,evaluate:async(fn)=>{
  assert.equal(typeof fn,'function');
  if(fn===installMainImageSaveGuard)return undefined;
  if(fn.name==='mainImageSaveGuardSnapshot')return{present:false,prototypeBound:false,fetchBound:false,requests:[],error:null,colorWarnings:[]};
 }};
 await assert.rejects(()=>submitNativeMainImageSave(page,f.input,f.record,async()=>{},{source:f.response.data,amendment:f.amendment}),/护栏未完成安装核验/);
 assert.equal(clicks,0);assert.equal(f.record.mainImageRepair.lastGuardSnapshot.present,false);assert.equal(f.record.mainImageRepair.guardInstallProof,undefined);
});
