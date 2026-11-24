import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {runCollectionWorkflow} from './ego-collection-workflow.mjs';
import {managedUploadKey} from './ego-collection-upload.mjs';
import {schemaVariation,chooseCategory,prepareNativeDraft,resolveCategoryHints} from './ego-collection-prepare.mjs';

test('US pants matches the ordinary UK trousers leaf without admitting other branches',()=>{
 const candidates=[{index:0,text:'Fashion Women Clothing Trousers'},{index:1,text:'Fashion Men Clothing Trousers'},
  {index:2,text:'Fashion Women Clothing Activewear Trousers'},{index:3,text:'Fashion Women Clothing Underwear Pants'}];
 const hints={path:'Clothing, Shoes & Jewelry > Women > Clothing > Pants'};
 assert.equal(chooseCategory(candidates,hints,"Women's Mid-Rise Faux Suede Pants").index,0);
 assert.throws(()=>chooseCategory(candidates.slice(1),hints,'Women Pants'),/歧义/);
 assert.throws(()=>chooseCategory([...candidates,{index:4,text:candidates[0].text}],hints,'Women Pants'),/歧义/);
});
import {gbTshirtRecommendations,verifiedUsTshirtPath} from './fixtures/gb-category-recommendations.mjs';

async function fixture(t,fail){
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'erp-native-workflow-'));
 t.after(async()=>{assert.equal(path.dirname(path.resolve(root)),path.resolve(os.tmpdir()));assert.ok(path.basename(root).startsWith('erp-native-workflow-'));await fs.rm(root,{recursive:true,force:true});});
 const input={mode:'draft',accountId:7,productId:'NEW-PRODUCT',sha256:'frozen',store:'Target US',marketplace:'US',
  goods:{parentSku:'NEW-SKU',title:'Real product'},goodsItems:['S','M','L'].map(size=>({sku:'NEW-SKU-'+size,color:'Red',size})),assets:[{sha256:'asset'}],
  destination:{destinationId:'connected-store',marketId:'17',countryCode:'US'}};
 const state={collection:0,joins:0,saves:0,uploads:0,created:false,saved:false,failed:false,foreign:false};
 const row=()=>({id:'300',sourceMatch:true,join_platform:state.created?['amazon']:[]});
 const draft=()=>({id:'500',title:input.goods.title,sku:state.saved?input.goods.parentSku:'ERP-ALIAS',ready:state.saved,items:input.goodsItems});
 const crash=async(stage,persist)=>{if(fail===stage&&!state.failed){state.failed=true;await persist();throw Error('connection lost after '+stage);}};
 const adapters={
  query:async(_page,q)=>q.title?(state.created?[{id:'500',store:state.saved?input.store:'',sku:state.saved?input.goods.parentSku:'ERP-ALIAS'}]:[]):state.foreign?[{id:'999',store:input.store,sku:input.goods.parentSku}]:state.saved?[{id:'500',store:input.store,sku:input.goods.parentSku}]:[],
  upload:async(_p,_i,r,persist)=>{if(!r.uploads){state.uploads++;r.uploads={asset:{url:'https://image/asset'}};await persist();}return{asset:'https://image/asset'};},
  collect:async(_p,_i,_u,r,persist)=>{if(!state.collection){state.collection++;r.collection={status:'submit_unknown'};await crash('collection',persist);}r.collection={id:'300',status:'list_verified',row:row()};await persist();},
  rows:async()=>[row()],
  join:async(_p,j,persist)=>{state.joins++;j.status='join_unknown';j.sent=1;state.created=true;await crash('join',persist);j.response={body:{code:0}};j.status='native_join_verified';await persist();},
  read:async()=>({code:0,data:draft()}),
  prepare:async(_p,i,r,persist)=>{i.destination.sizeValues={S:'s',M:'m',L:'l'};r.resolvedDestination={...i.destination};await persist();},
  save:async(_p,_i,_u,r,persist)=>{state.saves++;r.status='save_unknown';r.requestSent=true;state.saved=true;await crash('save',persist);r.response={httpStatus:200,code:0};await persist();},
  verify:(response)=>{if(!response.data.ready)throw Error('not saved');return input.goodsItems.map(v=>({sku:v.sku}));},
  remote:async()=>({sha256:'asset',bytes:123})
 };
 const page={goto:async()=>{},waitForSelector:async()=>{}};
 return{input,state,adapters,page,file:path.join(root,'receipt.json')};
}

for(const failure of [undefined,'collection','join','save'])test('new product without bindings survives '+(failure||'normal execution'),async t=>{
 const f=await fixture(t,failure);
 if(failure)await assert.rejects(runCollectionWorkflow(f.page,f.input,f.file,f.adapters),/connection lost/);
 const r=await runCollectionWorkflow(f.page,f.input,f.file,f.adapters);
 assert.equal(r.status,'saved_reopened_verified');assert.equal(r.collection.id,'300');assert.equal(r.draftId,'500');assert.equal(r.variantChecks.length,3);assert.equal(r.published,false);
 assert.equal(f.state.collection,1);assert.equal(f.state.joins,1);assert.equal(f.state.saves,1);assert.equal(f.state.uploads,1);
 await runCollectionWorkflow(f.page,f.input,f.file,f.adapters);
 assert.equal(f.state.collection,1);assert.equal(f.state.joins,1);assert.equal(f.state.saves,1);
 if(failure==='join')assert.equal(r.nativeTransfer.reconciled,true);
});

test('a pre-existing foreign same-SKU draft stops before any collection/upload',async t=>{
 const f=await fixture(t);f.state.foreign=true;
 await assert.rejects(runCollectionWorkflow(f.page,f.input,f.file,f.adapters),/已有同SKU/);
 assert.equal(f.state.uploads,0);assert.equal(f.state.collection,0);assert.equal(f.state.joins,0);
});

test('an uncertain native submission with no joined evidence is not retried',async t=>{
 const f=await fixture(t,'join');await assert.rejects(runCollectionWorkflow(f.page,f.input,f.file,f.adapters));f.state.created=false;
 await assert.rejects(runCollectionWorkflow(f.page,f.input,f.file,f.adapters),/不重新转入/);assert.equal(f.state.joins,1);
});

test('another account cannot resume the receipt',async t=>{
 const f=await fixture(t);await runCollectionWorkflow(f.page,f.input,f.file,f.adapters);
 await assert.rejects(runCollectionWorkflow(f.page,{...f.input,accountId:8},f.file,f.adapters),/本账号/);
});

test('upload key is deterministic and cannot escape the uploader account directory',()=>{
 const asset={sha256:'a'.repeat(64),mime:'image/png'},a=managedUploadKey('u/19335/26/11/random.png',19335,asset);
 assert.equal(a,managedUploadKey('u/19335/26/11/other.png',19335,asset));assert.match(a,/s_a{32}\.png$/);
 assert.throws(()=>managedUploadKey('u/OTHER/26/11/random.png',19335,asset));
});

test('category routing distinguishes women cardigans from children and maternity',()=>{
 const candidates=['Women Clothing Sweaters Cardigans','Girls Clothing Sweaters Cardigans','Women Maternity Sweaters Cardigans'].map((text,index)=>({text,index}));
 assert.equal(chooseCategory(candidates,{},"Women's Cropped Wrap Cardigan").index,0);
 assert.throws(()=>chooseCategory([{text:'Women Cardigans',index:0},{text:'Women Cardigans',index:1}],{},'Women Cardigan'),/歧义/);
});

test('verified taxonomy leaf selects ordinary women T-shirts without scoring ancestor Blouses or a pullover title',()=>{
 const candidates=structuredClone(gbTshirtRecommendations),hints={path:verifiedUsTshirtPath,evidence:'verified source taxonomy'},title='Long Sleeve Tops for Women, Fine-Ribbed Fitted Crew Neck Pullover';
 const ordinary=candidates.find(row=>row.text==='Fashion Women Clothing Tops T-Shirts & Blouses T-Shirts');
 assert.equal(chooseCategory(candidates,hints,title).value,ordinary.value);
 const reordered=[...candidates].reverse().map((row,index)=>({...row,index:index+1000}));
 assert.equal(chooseCategory(reordered,hints,title).index,reordered.find(row=>row.value===ordinary.value).index);
 assert.throws(()=>chooseCategory(candidates.filter(row=>row.value!==ordinary.value),hints,title),/歧义/);
 assert.throws(()=>chooseCategory([...candidates,{...ordinary,index:999,value:'another-node'}],hints,title),/歧义/);
 assert.equal(chooseCategory(candidates,{path:'Women > Clothing > Blouses'},'Women T-Shirt').index,299);
 for(const target of ['Fashion Women Clothing Activewear Shirts & Tees T-Shirts','Fashion Women Clothing Maternity Tops & Tees T-Shirts'])assert.equal(chooseCategory(candidates,{path:target},title).text,target);
 assert.throws(()=>chooseCategory(candidates.filter(row=>row.text.includes('Men Clothing')),hints,title),/歧义/);
 assert.throws(()=>chooseCategory([{index:0,text:'Clothing T-Shirts'}],hints,title),/歧义/);
 assert.throws(()=>chooseCategory([{index:0,text:'Girls Clothing T-Shirts'}],{path:'Baby > Girls > T-Shirts'},'Baby T-Shirt'),/歧义/);
});

test('a nonempty taxonomy path outranks empty hint objects and title-only hints without mutating frozen inputs',()=>{
 const empty={path:'',title:'Marketing pullover'},verified={path:verifiedUsTshirtPath,evidence:'verified category link'};
 const result=resolveCategoryHints({},empty,verified);assert.deepEqual(result,verified);result.path='changed';assert.equal(verified.path,verifiedUsTshirtPath);
 assert.deepEqual(resolveCategoryHints({path:'   '},{title:'Women Cardigan'}),{title:'Women Cardigan'});
});

test('ambiguous category candidates and hints are durable before choosing, without another draft',async()=>{
 const candidates=[{index:0,text:'Women Cardigans'},{index:1,text:'Women Cardigans'}];
 const input={store:'Target US',goods:{title:'Women Cardigan'},destination:{categoryHints:{path:'',title:'Women cardigan'}}};
 const record={draftId:'500',collection:{id:'300'},error:'Original checkpoint retained'},saved=[];
 const run=async()=>{
  let count=0;
  const page={goto:async()=>{},waitForFunction:async()=>{},click:async()=>{throw Error('Must not choose an ambiguous category');},
   evaluate:async()=>[undefined,'Target US',true,candidates,undefined][count++]};
  await assert.rejects(prepareNativeDraft(page,input,record,async()=>saved.push(structuredClone(record))),/类目推荐有歧义/);
 };
 await run();
 assert.equal(saved.length,1);assert.deepEqual(saved[0].categoryRecommendation.candidates,candidates);
 assert.deepEqual(saved[0].categoryRecommendation.hints,input.destination.categoryHints);
 assert.equal(saved[0].categoryRecommendation.title,input.goods.title);assert.equal(saved[0].categoryRecommendation.draftId,'500');
 assert.equal(record.collection.id,'300');assert.equal(record.error,'Original checkpoint retained');assert.equal(record.categoryChoice,undefined);
 const original=structuredClone(record.categoryRecommendation);await run();
 assert.deepEqual(record.categoryRecommendationHistory,[original]);assert.equal(record.draftId,'500');
});

test('a missing verified leaf uses the source title only for a fresh ERP recommendation',async()=>{
 const listingTitle='Faux Suede Tops for Women, Stand Collar Half-Button Pullover';
 const sourceTitle="Women's Faux Suede Stand Collar Half Button Pullover Sweatshirt";
 const path='Clothing, Shoes & Jewelry > Women > Clothing > Active > Active Sweatshirts';
 const incorrect=[{index:0,text:'Clothing Shoes & Jewelry Women Clothing Tops Tees & Blouses Blouses'}];
 const exact={index:49,text:'Clothing Shoes & Jewelry Women Clothing Active Active Sweatshirts'};
 const correct=[exact,{index:50,text:'Clothing Shoes & Jewelry Women Clothing Fashion Hoodies & Sweatshirts Fashion Sweatshirts'}];
 const input={store:'Target US',goods:{title:listingTitle},destination:{categoryHints:{path,title:sourceTitle}}};
 const record={draftId:'500',collection:{id:'300'}},activities=[];
 const replies=[undefined,'Target US',true,incorrect,correct,undefined];
 const page={goto:async()=>{},waitForFunction:async()=>{},click:async selector=>activities.push(['click',selector]),
  fill:async(selector,value)=>activities.push(['fill',selector,value]),
  evaluate:async(fn,arg)=>{
   if(arg===listingTitle){activities.push(['restore',arg]);return;}
   if(arg===exact.index)throw Error('Reached intended ERP radio selection');
   return replies.shift();
  }};
 await assert.rejects(prepareNativeDraft(page,input,record,async()=>{}),/Reached intended ERP radio selection/);
 assert.deepEqual(activities,[
  ['click','[role=dialog][aria-label="亚马逊产品类型推荐"] .el-dialog__footer button.el-button--default'],
  ['fill','input[placeholder="产品标题"]',sourceTitle],
  ['click','loc=role:button[name="自动识别产品类型"]'],
  ['restore',listingTitle],
 ]);
 assert.equal(record.categoryRecommendationHistory[0].title,listingTitle);
 assert.equal(record.categoryRecommendation.title,sourceTitle);
 assert.equal(record.categoryChoice.index,exact.index);
 assert.equal(input.goods.title,listingTitle);
 assert.equal(record.draftId,'500');
});

test('size values come from ERP schema and missing/ambiguous sizes block',()=>{
 const meta={country_code:'US',locale:'en_US',hash:'schema',schema_content:{properties:{
  color:{items:{properties:{value:{type:'string'}}}},
  apparel_size:{items:{properties:{size:{enum:['small','s','medium','m','x_l'],enumNames:['Small','S','Medium','M','X-Large']}}}},
  variation_theme:{items:{properties:{name:{enum:['COLOR_NAME/SIZE_NAME']}}}}
 }}};
 assert.deepEqual(schemaVariation(meta,[{size:'S'},{size:'XL'}]).sizeValues,{S:'s',XL:'x_l'});
 assert.throws(()=>schemaVariation(meta,[{size:'XXL'}]),/尺码枚举/);
});

test('SHIRT schema resolves all thirty color-size rows using its actual shirt_size path',()=>{
 // Paths and alpha values observed in the ERP SHIRT form, rather than a
 // product title or an invented apparel_size fallback.
 const meta={country_code:'US',locale:'en_US',product_type_name:'SHIRT',hash:'observed-shirt-schema',schema_content:{properties:{
  color:{items:{properties:{value:{type:'string'}}}},
  shirt_size:{items:{properties:{size:{enum:['s','m','l','x_l','xx_l','3x_l'],enumNames:['S','M','L','XL','XXL','3XL']},size_class:{enum:['alpha']},size_system:{enum:['as1']}}}},
  variation_theme:{items:{properties:{name:{enum:['COLOR_NAME/SIZE_NAME']}}}}
 }}};
 const items=['White','Black','Brown','Gray','Red'].flatMap(color=>['S','M','L','XL','XXL','3XL'].map(size=>({color,size})));
 for(const theme of ['COLOR_NAME/SIZE_NAME','COLOR/SIZE','SIZE_NAME/COLOR_NAME','SIZE/COLOR']){
  const m=structuredClone(meta);m.schema_content.properties.variation_theme.items.properties.name.enum=[theme];
  const result=schemaVariation(m,items);
  assert.deepEqual(result.variationFields,{color:'color.0.value',size:'shirt_size.0.size'});
  assert.deepEqual(result.sizeValues,{S:'s',M:'m',L:'l',XL:'x_l',XXL:'xx_l','3XL':'3x_l'});assert.equal(result.themeValue,theme);
 }
 const unsupported=structuredClone(meta);delete unsupported.schema_content.properties.shirt_size.items.properties.size;
 assert.throws(()=>schemaVariation(unsupported,items),/不支持当前产品/);
 meta.schema_content.properties.variation_theme.items.properties.name.enum=['COLOR/SIZE/STYLE'];
 assert.throws(()=>schemaVariation(meta,items),/未提供可用/);
});

function conditionalShirtSchema(country='US',system='as1'){
 // Minimal projection of native-raw-schema-107: item-level required differs
 // from the ERP UI's flattened required flags, and class is conditional.
 const alpha=['s','m','l','x_l','xx_l','3x_l'];
 const branch=(sizeClass,sizes)=>({
  if:{required:['shirt_size'],properties:{shirt_size:{items:{allOf:[
   {required:['size_class'],properties:{size_class:{enum:[sizeClass]}}},
   {required:['size_system'],properties:{size_system:{enum:[system]}}}
  ]}}}},
  then:{properties:{shirt_size:{items:{properties:{size:{enum:sizes}}}}}}
 });
 const numeric=branch('numeric',['numeric_1']),age=branch('age',['1_year']);age.else=branch('alpha',alpha);numeric.else=age;
 return{country_code:country,locale:country==='US'?'en_US':'en_GB',hash:'real-'+country,schema_content:{
  $defs:{marketplace_id:{type:'string',default:country==='US'?'USMARKET':'UKMARKET'}},
  properties:{
   color:{items:{properties:{value:{type:'string'}}}},
   shirt_size:{items:{required:['size_class','size_system'],properties:{
    size:{type:'string',enum:[...alpha,'numeric_1','1_year']},
    size_class:{type:'string',enum:['age','alpha','alpha_jaspo','neck','neck_sleeve','numeric','numeric_go','numeric_height']},
    size_system:{type:'string',enum:[system]},marketplace_id:{$ref:'#/$defs/marketplace_id'},
    body_type:{type:'string',enum:['regular','plus']}
   }}},
   variation_theme:{items:{properties:{name:{enum:['COLOR/SIZE']}}}}
  },allOf:[numeric]
 }};
}

test('native conditional size enums uniquely prove the class and target system without copying UI required flags',()=>{
 const items=['S','M','L','XL','XXL','3XL'].map(size=>({size}));
 for(const [country,system]of [['US','as1'],['GB','actual-uk-system']]){
  const meta=conditionalShirtSchema(country,system);if(country==='GB')meta.schema_content=JSON.stringify(meta.schema_content);
  const result=schemaVariation(meta,items),proof=result.sizeAttributeSchema;
  assert.deepEqual(result.sizeAttributes,{size_system:system,size_class:'alpha'});
  assert.equal(proof.field,'shirt_size');assert.equal(proof.countryCode,country);assert.equal(proof.schemaHash,meta.hash);
  assert.deepEqual(proof.required,['size_class','size_system']);
  assert.deepEqual(proof.properties.size.enum,['s','m','l','x_l','xx_l','3x_l']);
  assert.deepEqual(proof.properties.size_class.enum,['alpha']);assert.deepEqual(proof.properties.size_system.enum,[system]);
  assert.equal(proof.properties.body_type,undefined);assert.ok(JSON.stringify(proof).length<1000);
 }
 const suggested=conditionalShirtSchema();suggested.schema_content.properties.shirt_size.items.properties.size_class.default='alpha';
 assert.equal(schemaVariation(suggested,[{size:'numeric_1'}]).sizeAttributes.size_class,'numeric');
});

test('SKIRT uses its native size field and proves the class separately for US and GB',()=>{
 const items=['Brown','Black','White'].flatMap(color=>['S','M'].map(size=>({color,size})));
 for(const [country,system] of [['US','as1'],['GB','as4']]){
  const meta=JSON.parse(JSON.stringify(conditionalShirtSchema(country,system)).replaceAll('shirt_size','skirt_size'));
  meta.product_type_name='SKIRT';
  const result=schemaVariation(meta,items);
  assert.deepEqual(result.variationFields,{color:'color.0.value',size:'skirt_size.0.size'});
  assert.deepEqual(result.sizeValues,{S:'s',M:'m'});
  assert.deepEqual(result.sizeAttributes,{size_system:system,size_class:'alpha'});
  assert.equal(result.sizeAttributeSchema.field,'skirt_size');
  const unknown=structuredClone(meta);delete unknown.schema_content.properties.skirt_size.items.properties.size;
  assert.throws(()=>schemaVariation(unknown,items),/不支持当前产品/);
  assert.throws(()=>schemaVariation(meta,[{size:'S'},{size:'numeric_1'}]),/唯一确定尺码类别/);
 }
});

test('unproven, mixed and ambiguous size classes or systems stop before a draft save',()=>{
 const items=[{size:'S'},{size:'3XL'}];
 for(const change of [
  m=>delete m.schema_content.allOf,
  m=>m.schema_content.allOf.push({...structuredClone(m.schema_content.allOf[0].else.else),if:{properties:{shirt_size:{items:{properties:{size_class:{enum:['alpha_jaspo']},size_system:{enum:['as1']}}}}}}}),
  m=>m.schema_content.properties.shirt_size.items.properties.size_system.enum.push('other-system'),
  m=>m.schema_content.properties.shirt_size.items.required.push('body_type'),
  m=>delete m.hash
 ]){const meta=conditionalShirtSchema();change(meta);assert.throws(()=>schemaVariation(meta,items),/真实schema|必填尺码/);}
 assert.throws(()=>schemaVariation(conditionalShirtSchema(),[{size:'S'},{size:'numeric_1'}]),/唯一确定尺码类别/);
});

test('the actual schema field summary is durable even when variation parsing stops',async()=>{
 const meta={country_code:'US',product_type_name:'SHIRT',hash:'actual-response-hash',schema_content:JSON.stringify({properties:{
  color:{items:{properties:{value:{type:'string'}}}},shirt_size:{items:{properties:{size_class:{enum:['alpha']}}}},
  variation_theme:{items:{properties:{name:{enum:['COLOR_NAME/SIZE_NAME']}}}}
 }})};
 const input={store:'Target US',goods:{title:'Women Shirt'},goodsItems:[{size:'S',color:'Red'}],destination:{countryCode:'US'}};
 const record={draftId:'500',collection:{id:'300'}},saved=[];let count=0;
 const page={goto:async()=>{},waitForFunction:async()=>{},click:async()=>{},
  evaluate:async()=>[undefined,'Target US',true,[{index:0,text:'Women Shirts'}],'[category]',meta,undefined][count++]};
 await assert.rejects(prepareNativeDraft(page,input,record,async()=>saved.push(structuredClone(record))),/不支持当前产品/);
 assert.deepEqual(saved.at(-1).schemaProof,{country:'US',productType:'SHIRT',hash:'actual-response-hash',variationProperties:{color:['value'],shirt_size:['size_class']},themes:['COLOR_NAME/SIZE_NAME']});
 assert.equal(record.draftId,'500');assert.equal(record.collection.id,'300');assert.equal(record.resolvedDestination,undefined);
});

// Observed GB COAT uses abbreviated alpha enums, while Amazon labels use X-Small.
test('alpha size labels resolve XS and XXS without guessing numeric sizes or ambiguous aliases',()=>{
 const meta={country_code:'GB',locale:'en_GB',hash:'coat-alpha',schema_content:{properties:{
 color:{items:{properties:{value:{type:'string'}}}},
 apparel_size:{items:{properties:{size:{enum:['xx_s','x_s','s','m','x_l']}}}},
 variation_theme:{items:{properties:{name:{enum:['COLOR_NAME/SIZE_NAME']}}}}}}};
 assert.deepEqual(schemaVariation(meta,[{size:'XX-Small'},{size:'X-Small'},{size:'Small'},{size:'Medium'},{size:'X-Large'}]).sizeValues,{'XX-Small':'xx_s','X-Small':'x_s',Small:'s',Medium:'m','X-Large':'x_l'});
 const ambiguous=structuredClone(meta);ambiguous.schema_content.properties.apparel_size.items.properties.size.enum.push('xs');
 assert.throws(()=>schemaVariation(ambiguous,[{size:'X-Small'}]),/尺码枚举/);
 assert.throws(()=>schemaVariation(meta,[{size:'UK 8'}]),/尺码枚举/);
});
