import test from 'node:test';
import assert from 'node:assert/strict';
import * as us from './ego-us-draft.mjs';

function fixture(){
 const market='USMARKET',language='en_US',sizes={S:'s',M:'m','3XL':'3x_l'};
 const assets=Array.from({length:14},(_,i)=>({sha256:String(i+1).padStart(64,'0'),slot:i%7+1,width:2000,height:2000}));
 const urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/isolated-us/'+i+'.png']));
 const goodsItems=['White','Black'].flatMap((color,c)=>Object.keys(sizes).map(size=>({sku:'Original-'+color+'-'+size,color,size,
  price:'21.35',quantity:88,imageIndices:Array.from({length:7},(_,i)=>c*7+i)})));
 const input={accountId:2,productId:'isolated-shirt',jobId:'isolated-publication',sha256:'frozen-collection-snapshot',
  marketplace:'US',mode:'draft',store:'Actual US Store',handlingDays:3,masterColor:'Black',assets,urls,goodsItems,
  goods:{parentSku:'Original',brand:'Original Brand',manufacturer:'Actual Maker',
   title:'Long Sleeve Tops for Women, Fine-Ribbed Fitted Crew Neck Pullover',highlights:'Fine ribbed fabric',
   description:"Women's Ribbed Long Sleeve Top\nStyle: Solid-color fitted pullover\nNeckline: Crew neck\nSleeves: Long, with narrow cuff edges\nTexture: Fine ribbed\nMaterial: 95% Polyester, 5% Elastane\nColors: White, black\nSizes: S, M, 3XL\n1 Pcs x women's fine-ribbed fitted long sleeve top",
   bullets:['Original first bullet','Original second bullet','Original third bullet','Original fourth bullet','Original fifth bullet'],terms:'original verified search terms'},
  publicationFacts:{countryOfOrigin:'CN',countryOfOriginEvidence:'Isolated supplier declaration',careInstructions:'Machine Wash',
   modelName:'Verified Supplier Style 123',itemCondition:'new_new',specialSizeType:'Standard'},
  destination:{draftId:'123',destinationId:'actual-us-destination',marketId:'45',marketplaceId:market,erpAccountId:'77',erpUserId:'77',
   countryCode:'US',languageTag:language,currency:'USD',schemaHash:'collection-schema',sizeValues:sizes,
   variationFields:{color:'color.0.value',size:'shirt_size.0.size'},shippingTemplate:{name:'Actual US Shipping'},
   categoryHints:{path:'Clothing, Shoes & Jewelry > Women > Clothing > Tops, Tees & Blouses > T-Shirts'}},
  ukTarget:{id:'actual-uk-destination',storeName:'Actual UK Store',countryCode:'GB',currency:'GBP',languageTag:'en_GB'},ukCommerce:{currency:'GBP'}};
 const property=properties=>({items:{properties}});
 const localized=(value={},translated=true)=>property({value:{type:'string',...value},...(translated?{language_tag:{type:'string'}}:{}),marketplace_id:{$ref:'#/$defs/marketplace_id'}});
 // Self-contained, minimal structural projection of the observed SHIRT schema.
 // Tests never load the production research files, receipts or account data.
 const meta={country_code:'US',locale:language,hash:'native-us-shirt-schema',product_type_name:'SHIRT',schema_content:{
  $defs:{marketplace_id:{type:'string',default:market}},
  required:['brand','bullet_point','country_of_origin','fabric_type','item_name','product_description'],
  properties:{
   main_product_image_locator:{type:'array',minItems:1,items:{type:'object',required:['media_location'],properties:{media_location:{type:'string',format:'uri',pattern:'^(https?|s3)://'},marketplace_id:{$ref:'#/$defs/marketplace_id'}},additionalProperties:false}},
   color:localized(),variation_theme:property({name:{enum:['COLOR/SIZE']}}),
   shirt_size:{items:{required:['size_class','size_system'],properties:{
    size:{type:'string',enum:['s','m','l','x_l','xx_l','3x_l','numeric_1']},
    size_class:{type:'string',enum:['age','alpha','alpha_jaspo','neck','neck_sleeve','numeric','numeric_go','numeric_height']},
    size_system:{type:'string',enum:['as1']},marketplace_id:{$ref:'#/$defs/marketplace_id'},
    body_type:{type:'string',enum:['plus','regular','slim'],description:'Provide the body type for apparel item, select "Regular" in case of no special body type.'},
    height_type:{type:'string',enum:['petite','regular','tall'],description:'Provide the height type for apparel item, select "Regular" in case of no special height type.'}
   }}},
   fabric_type:localized({maxLength:700}),country_of_origin:localized({enum:['CN','US','GB']},false),
   care_instructions:localized({maxLength:500}),department:localized({maxLength:50}),target_gender:localized({enum:['female','male','unisex']},false),
   age_range_description:localized({maxLength:1998}),fit_type:localized({maxLength:2201}),pattern:localized({maxLength:2200}),
   model_name:localized({maxLength:120}),condition_type:localized({enum:['new_new','used_good']},false),special_size_type:localized({maxLength:2200}),
   import_designation:localized({maxLength:2234}),style:localized({maxLength:120}),brand:localized({maxLength:100}),
   item_name:localized({maxLength:200}),bullet_point:localized({maxLength:500}),product_description:localized(),
   list_price:property({currency:{type:'string',enum:['USD']},value:{type:'number',minimum:0,description:'If you are unable to provide a value, enter 0.'},marketplace_id:{$ref:'#/$defs/marketplace_id'}}),
   neck:property({neck_style:{items:{properties:{value:{type:'string',enum:['Crew Neck','V-Neck']}}}},marketplace_id:{$ref:'#/$defs/marketplace_id'}}),
   sleeve:property({type:{items:{properties:{value:{type:'string',enum:['Cuff Sleeve','Sleeveless']},language_tag:{type:'string'}}}},
    length_description:{items:{properties:{value:{type:'string',enum:['long_sleeve','short_sleeve']}}}},marketplace_id:{$ref:'#/$defs/marketplace_id'}})
  },allOf:[{
   if:{required:['shirt_size'],properties:{shirt_size:{items:{allOf:[
    {required:['size_class'],properties:{size_class:{enum:['alpha']}}},
    {required:['size_system'],properties:{size_system:{enum:['as1']}}}
   ]}}}},
   then:{properties:{shirt_size:{items:{properties:{size:{enum:['s','m','l','x_l','xx_l','3x_l']}}}}}}
  }]
 }};
 const first=goodsItems.find(v=>v.color===input.masterColor),cover=urls[assets[first.imageIndices[0]].sha256];
 const body={id:123,uid:77,market_id:'45',country_code:'US',sku:input.goods.parentSku,parent_sku:input.goods.parentSku,
  title:input.goods.title,brand:input.goods.brand,manufacturer:input.goods.manufacturer,product_description:input.goods.description,
  bullet_point:input.goods.bullets,keywords:input.goods.terms,main_image:cover,images:[cover],
  attributes:{merchant_shipping_group:[{value:'actual-template-id',marketplace_id:market}],fabric_type:[{value:'Stale template wool'}],care_instructions:[{value:'Stale template dry clean'}]},
  items:goodsItems.map((v,i)=>({id:500+i,uid:77,pid:123,sku:v.sku,price:v.price,quantity:String(v.quantity),
   variation:{'color.0.value':v.color,'shirt_size.0.size':sizes[v.size]},main_image:urls[assets[v.imageIndices[0]].sha256],
   images:v.imageIndices.map(n=>urls[assets[n].sha256]),attributes:{fabric_type:[{value:'Stale template wool'}]}}))};
 return{input,meta,body,urls};
}

function preparedFixture(){
 const f=fixture(),prepared=us.makeUsPreparedInput(f.input,f.meta,'Actual Synced Brand');
 prepared.destination.shippingTemplate={name:'Actual US Shipping',id:'actual-template-id'};
 const attributes=us.usProductAttributes(prepared,f.meta);
 return{...f,prepared,attributes,wire:{...f.input,usPrepared:prepared,usProductAttributes:attributes}};
}
function persisted(body,input){return{code:0,data:{...structuredClone(body),market:{alias:input.store},sku:input.goods.parentSku,
 extra:{images:body.images,attributes:body.attributes,product_description:body.product_description,bullet_point:body.bullet_point,keywords:body.keywords},
 items:body.items.map(row=>({...structuredClone(row),pid:body.id,extra:{images:row.images,attributes:row.attributes}}))}};}

test('US preparation requires explicit origin and care facts and validates the actual schema and synced brand',()=>{
 const f=preparedFixture();
 assert.equal(f.prepared.goods.brand,'Actual Synced Brand');assert.equal(f.input.goods.brand,'Original Brand');
 assert.equal(f.prepared.destination.requireMainImageLocator,true);assert.equal(f.input.destination.requireMainImageLocator,undefined);
 assert.equal(f.prepared.destination.sizeAttributes.size_class,'alpha');assert.equal(f.prepared.destination.sizeAttributes.size_system,'as1');
 assert.equal(f.prepared.destination.sizeAttributes.body_type,'regular');assert.equal(f.prepared.destination.sizeAttributes.height_type,'regular');
 assert.equal(f.attributes.fabric_type[0].value,'95% Polyester, 5% Elastane');
 assert.equal(f.attributes.care_instructions[0].value,'Machine Wash');assert.equal(f.attributes.country_of_origin[0].value,'CN');
 for(const change of [i=>delete i.publicationFacts.countryOfOrigin,i=>i.publicationFacts.countryOfOrigin='China',i=>delete i.publicationFacts.careInstructions,i=>i.publicationFacts.careInstructions='']){
  const input=structuredClone(f.input);change(input);
  assert.throws(()=>us.usProductAttributes(us.makeUsPreparedInput(input,f.meta,'Actual Synced Brand'),f.meta));
 }
 for(const change of [m=>m.country_code='GB',m=>m.locale='en_GB',m=>m.schema_content.$defs.marketplace_id.default='OTHER',m=>delete m.hash]){
  const meta=structuredClone(f.meta);change(meta);assert.throws(()=>us.makeUsPreparedInput(f.input,meta,'Actual Synced Brand'));
 }
 assert.throws(()=>us.makeUsPreparedInput(f.input,f.meta,''));
});

test('fabric must come from one frozen Material line and never from stale template attributes',()=>{
 const f=fixture();f.input.templateAttributes={fabric_type:[{value:'Unverified acrylic'}]};
 for(const description of ['No material provided','Material: ','Material: Cotton\nMaterial: Polyester']){
  const input=structuredClone(f.input);input.goods.description=description;
  assert.throws(()=>us.usProductAttributes(us.makeUsPreparedInput(input,f.meta,'Actual Synced Brand'),f.meta),/材质/);
 }
 f.input.goods.description="Top<br/>Material: 95% Polyester, 5% Elastane<br/>Sizes: S, M, 3XL";
 const attrs=us.usProductAttributes(us.makeUsPreparedInput(f.input,f.meta,'Actual Synced Brand'),f.meta);
 assert.equal(attrs.fabric_type[0].value,'95% Polyester, 5% Elastane');
});

test('explicit future water facts fill only the schema-supported US field and invalid enum values stop preparation',()=>{
 const f=fixture();f.input.publicationFacts.waterResistanceLevel='not_water_resistant';
 f.meta.schema_content.properties.water_resistance_level={items:{properties:{value:{type:'string',enum:['not_water_resistant','water_resistant','waterproof']},marketplace_id:{$ref:'#/$defs/marketplace_id'}}}};
 const prepared=us.makeUsPreparedInput(f.input,f.meta,'Actual Synced Brand');
 assert.deepEqual(us.usProductAttributes(prepared,f.meta).water_resistance_level,[{value:'not_water_resistant',marketplace_id:'USMARKET'}]);
 prepared.publicationFacts.waterResistanceLevel='unverified';assert.throws(()=>us.usProductAttributes(prepared,f.meta),/美国实际枚举.*water_resistance_level/);
});

test('missing water facts and schemas without that field preserve prior US behavior without adding a default',()=>{
 const f=fixture(),before=structuredClone(f.input);
 f.meta.schema_content.properties.water_resistance_level={items:{properties:{value:{type:'string',enum:['not_water_resistant']},marketplace_id:{$ref:'#/$defs/marketplace_id'}}}};
 assert.equal(us.usProductAttributes(us.makeUsPreparedInput(f.input,f.meta,'Actual Synced Brand'),f.meta).water_resistance_level,undefined);assert.deepEqual(f.input,before);
 f.input.publicationFacts.waterResistanceLevel='not_water_resistant';delete f.meta.schema_content.properties.water_resistance_level;
 assert.equal(us.usProductAttributes(us.makeUsPreparedInput(f.input,f.meta,'Actual Synced Brand'),f.meta).water_resistance_level,undefined);
});

test('US pants require a single proven leg cut and serialize it using the live schema hierarchy',async()=>{
 const {input:original,prepared:input,meta,body,urls}=preparedFixture();
 input.goodsItems=input.goodsItems.slice(0,4);
 original.goodsItems=original.goodsItems.slice(0,4);
 body.items=body.items.slice(0,4);
 meta.product_type_name='PANTS';
 meta.schema_content.properties.leg={items:{properties:{marketplace_id:{$ref:'#/$defs/marketplace_id'},style:{items:{properties:{language_tag:{type:'string'},value:{anyOf:[{type:'string'},{enum:['Wide','Straight']}]}}}}}}};
 const description=style=>`Material: Polyester\nStyle: ${style}`;
 input.goods.description=description('Full-length, wide-leg pull-on pants');
 body.product_description=input.goods.description;
 const attributes=us.usProductAttributes(input,meta);
 const leg=[{style:[{value:'Wide',language_tag:'en_US'}],marketplace_id:'USMARKET'}];
 assert.deepEqual(attributes.leg,leg);
 const saved=us.patchUsDraftPayload(body,{usPrepared:input,usProductAttributes:attributes},urls);
 assert.deepEqual(saved.attributes.leg,leg);
 assert.deepEqual(saved.items.map(row=>row.attributes.leg),[leg,leg,leg,leg]);
 assert.deepEqual(saved.items.map(row=>row.images),body.items.map(row=>row.images));
 original.goods.description=input.goods.description;
 const oldReadback=persisted(saved,input);
 delete oldReadback.data.items[0].extra.attributes.leg;
 const oldRecord={preparedInput:input,phase:'us_draft_verified',schemaObservation:meta,productAttributes:{...attributes}};
 delete oldRecord.productAttributes.leg;
 await assert.rejects(()=>us.prepareUsDraft({},original,oldRecord,async()=>assert.fail('should not certify an incomplete draft'),{
  read:async()=>oldReadback,save:async()=>assert.fail('should not repeat an old save')
 }),/美国子SKU商品属性不符.*leg/);
 input.goods.description=description('Full-length pants')+'\nLeg style: Straight';
 assert.equal(us.usProductAttributes(input,meta).leg[0].style[0].value,'Straight');
 for(const style of ['Full-length pants','Wide-leg and straight-leg assorted pants']){
  input.goods.description=description(style);
  assert.throws(()=>us.usProductAttributes(input,meta),/唯一已核实的腿型/);
 }
 input.goods.description=description('Tapered-leg pants');
 assert.throws(()=>us.usProductAttributes(input,meta),/美国裤装实际类目不支持 leg/);
});

test('native US Save runs from serialized source and preserves original IDs, SKUs and every child gallery',()=>{
 const f=preparedFixture(),before=structuredClone(f.body),patch=(0,eval)('('+us.patchUsDraftPayload.toString()+')');
 const output=patch(f.body,f.wire,f.urls);
 assert.equal(output.id,123);assert.equal(output.with_publish,false);assert.equal(output.publish,false);assert.equal(output.brand,'Actual Synced Brand');
 assert.deepEqual(output.items.map(v=>v.id),before.items.map(v=>v.id));assert.deepEqual(output.items.map(v=>v.sku),f.input.goodsItems.map(v=>v.sku));
 assert.deepEqual(output.images,[output.main_image]);
 assert.deepEqual(output.attributes.main_product_image_locator,[{media_location:output.main_image,marketplace_id:f.prepared.destination.marketplaceId}]);
 for(const row of output.items){
  const expected=f.input.goodsItems.find(v=>v.sku===row.sku);
  assert.deepEqual(row.images,expected.imageIndices.map(i=>f.urls[f.input.assets[i].sha256]));assert.equal(row.main_image,row.images[0]);
  assert.deepEqual(row.attributes.main_product_image_locator,[{media_location:row.images[0],marketplace_id:f.prepared.destination.marketplaceId}]);
  assert.equal(row.attributes.fabric_type[0].value,'95% Polyester, 5% Elastane');assert.equal(row.attributes.care_instructions[0].value,'Machine Wash');
  assert.equal(row.attributes.shirt_size[0].size_class,'alpha');assert.equal(row.attributes.shirt_size[0].size_system,'as1');
 }
 assert.deepEqual(f.body,before);assert.equal(us.verifyUsPrepared(persisted(output,f.prepared),f.prepared,f.urls,f.attributes).length,6);
 for(const change of [b=>b.id=124,b=>b.market_id='46',b=>b.country_code='GB',b=>b.sku='Foreign',b=>b.with_publish=true,b=>b.publish=true,
  b=>b.items.pop(),b=>b.items[0].sku='Foreign',b=>b.items[1].sku=b.items[0].sku,b=>b.attributes.merchant_shipping_group[0].value='OTHER']){
  const body=structuredClone(f.body);change(body);assert.throws(()=>patch(body,f.wire,f.urls));
 }
 const missingUrl={...f.urls};delete missingUrl[f.input.assets[0].sha256];assert.throws(()=>patch(f.body,f.wire,missingUrl));
});

test('US readback rejects lost parent or child facts even if SKU, price and galleries still match',()=>{
 const f=preparedFixture(),actual=persisted(us.patchUsDraftPayload(f.body,f.wire,f.urls),f.prepared);
 for(const change of [a=>delete a.data.extra.attributes.care_instructions,a=>a.data.extra.attributes.country_of_origin[0].value='US',
  a=>delete a.data.items[0].extra.attributes.fabric_type,a=>a.data.items[0].extra.attributes.shirt_size[0].size_system='foreign']){
  const altered=structuredClone(actual);change(altered);assert.throws(()=>us.verifyUsPrepared(altered,f.prepared,f.urls,f.attributes));
 }
});

test('new US MAIN readback rejects absent, duplicated, foreign-market or wrong-colour locators while old receipts remain readable',()=>{
 const f=preparedFixture(),actual=persisted(us.patchUsDraftPayload(f.body,f.wire,f.urls),f.prepared);
 assert.notEqual(actual.data.main_image,actual.data.items[0].main_image,'master Black must differ from child White');
 for(const change of [a=>delete a.data.extra.attributes.main_product_image_locator,
  a=>a.data.extra.attributes.main_product_image_locator[0].media_location=a.data.items[0].main_image,
  a=>a.data.extra.attributes.main_product_image_locator[0].marketplace_id='UKMARKET',
  a=>delete a.data.items[0].extra.attributes.main_product_image_locator,
  a=>a.data.items[0].extra.attributes.main_product_image_locator[0].media_location=a.data.main_image,
  a=>a.data.items[0].extra.attributes.main_product_image_locator[0].marketplace_id='UKMARKET',
  a=>a.data.items[0].extra.attributes.main_product_image_locator.push(structuredClone(a.data.items[0].extra.attributes.main_product_image_locator[0]))]){
  const changed=structuredClone(actual);change(changed);assert.throws(()=>us.verifyUsPrepared(changed,f.prepared,f.urls,f.attributes),/MAIN/);
 }
 const legacy=structuredClone(f.prepared);delete legacy.destination.requireMainImageLocator;
 delete actual.data.extra.attributes.main_product_image_locator;for(const row of actual.data.items)delete row.extra.attributes.main_product_image_locator;
 assert.equal(us.verifyUsPrepared(actual,legacy,f.urls,f.attributes).length,6);
});

test('unsupported actual US MAIN schema blocks before native preparation or Save',async()=>{
 for(const mutate of [m=>delete m.schema_content.properties.main_product_image_locator,
  m=>m.schema_content.properties.main_product_image_locator.type='object',
  m=>delete m.schema_content.properties.main_product_image_locator.items.properties.marketplace_id,
  m=>m.schema_content.properties.main_product_image_locator.maxItems=0]){
  const f=fixture();mutate(f.meta);const calls=[];
  assert.throws(()=>us.makeUsPreparedInput(f.input,f.meta,'Actual Synced Brand'),/MAIN/);
  await assert.rejects(()=>us.prepareUsDraft({},f.input,{},async()=>{}, {
   readSchema:async()=>({draft:persisted(f.body,f.input),meta:f.meta}),preparePage:async()=>calls.push('prepare'),save:async()=>calls.push('save')
  }),/MAIN/);
  assert.deepEqual(calls,[]);
 }
});

test('prepared US identity allows verified brand and schema enrichment while rejecting foreign targets, content or images',()=>{
 const f=preparedFixture();assert.doesNotThrow(()=>us.assertUsPreparedIdentity(f.input,f.prepared));
 for(const change of [p=>p.store='Other Store',p=>p.marketplace='UK',p=>p.mode='publish',p=>p.destination.countryCode='GB',
  p=>p.destination.destinationId='other',p=>p.destination.draftId='124',p=>p.destination.marketId='46',p=>p.destination.marketplaceId='OTHER',
  p=>p.destination.erpAccountId='78',p=>p.assets[0].sha256='different',p=>p.assets.reverse(),p=>p.goods.title='Other Title',
  p=>p.goods.description='Other description',p=>p.goods.bullets[0]='Other bullet',p=>p.goods.terms='Other terms',p=>p.goodsItems[0].imageIndices.reverse()]){
  const prepared=structuredClone(f.prepared);change(prepared);assert.throws(()=>us.assertUsPreparedIdentity(f.input,prepared));
 }
});

test('an uncertain US Save with missing frozen input never reopens preparation or submits another Save',async()=>{
 const f=fixture(),calls=[];
 const forbidden=name=>async()=>{calls.push(name);throw Error('unexpected '+name);};
 for(const checkpoint of [{saveIntendedAt:'before-crash',requestSent:true,phase:'us_save_unknown'},{phase:'us_draft_verified'}]){
  await assert.rejects(()=>us.prepareUsDraft({},f.input,checkpoint,async()=>{},
   {readSchema:forbidden('schema'),read:forbidden('read'),preparePage:forbidden('page'),save:forbidden('save')}));
 }
 assert.deepEqual(calls,[]);
});

test('a completed US Save recovers an unpersisted template ID from the durable request or original draft without writing',async()=>{
 for(const hasRequest of [true,false]){
  const f=preparedFixture(),output=us.patchUsDraftPayload(f.body,f.wire,f.urls),actual=persisted(output,f.prepared);
  const record={phase:'us_save_unknown',saveIntendedAt:'before-crash',requestSent:true,preparedInput:structuredClone(f.prepared),productAttributes:f.attributes};
  delete record.preparedInput.destination.shippingTemplate.id;if(hasRequest)record.submitted=output;
  let reads=0,persists=0;const writes=[];
  await us.prepareUsDraft({},f.input,record,async()=>persists++,{
   read:async(_page,id)=>{reads++;assert.equal(String(id),'123');return actual;},
   readSchema:async()=>writes.push('schema'),preparePage:async()=>writes.push('prepare'),save:async()=>writes.push('save'),validate:async()=>({passed:true})
  });
  assert.equal(reads,1);assert.deepEqual(writes,[]);assert.ok(persists>0);assert.equal(record.phase,'us_draft_verified');
  assert.equal(record.preparedInput.destination.shippingTemplate.id,'actual-template-id');assert.equal(record.verification.length,6);
 }
});

test('a saved US receipt with mismatched frozen identity stops before any page read or write',async()=>{
 const f=preparedFixture();
 for(const change of [p=>p.store='Other',p=>p.destination.marketId='46',p=>p.assets[0].sha256='wrong',p=>p.goods.description='Other']){
  const prepared=structuredClone(f.prepared);change(prepared);const calls=[];
  const fail=name=>async()=>{calls.push(name);throw Error('unexpected '+name);};
  await assert.rejects(()=>us.prepareUsDraft({},f.input,{preparedInput:prepared,saveIntendedAt:'before-crash',productAttributes:f.attributes},async()=>{},
   {read:fail('read'),readSchema:fail('schema'),preparePage:fail('prepare'),save:fail('save')}));
  assert.deepEqual(calls,[]);
 }
});

test('fresh US preparation persists resolved facts before its single Save and verifies the same original draft',async()=>{
 const f=fixture(),record={},events=[];let saved,reads=0;
 await us.prepareUsDraft({},f.input,record,async()=>events.push('persist'),{
  readSchema:async()=>({draft:persisted(f.body,f.input),meta:f.meta}),
  preparePage:async()=>({brand:'Actual Synced Brand',shippingTemplate:{name:'Actual US Shipping',id:'actual-template-id'}}),
  validate:async(_meta,records)=>{assert.equal(records.length,7);assert.equal(records[0].attributes.care_instructions[0].value,'Machine Wash');assert.equal(records[1].attributes.fabric_type[0].value,'95% Polyester, 5% Elastane');
   const first=f.input.goodsItems.find(v=>v.color===f.input.masterColor);assert.equal(records[0].attributes.main_product_image_locator[0].media_location,f.urls[f.input.assets[first.imageIndices[0]].sha256]);
   for(const row of records.slice(1)){const v=f.input.goodsItems.find(v=>v.sku===row.id);assert.deepEqual(row.attributes.main_product_image_locator,[{media_location:f.urls[f.input.assets[v.imageIndices[0]].sha256],marketplace_id:f.input.destination.marketplaceId}]);}return{passed:true};},
  save:async(_page,wire,urls,r,persist,patch)=>{
   assert.equal(r.preparedInput.goods.brand,'Actual Synced Brand');assert.equal(r.productAttributes.care_instructions[0].value,'Machine Wash');
   assert.ok(events.length>0);events.push('save');saved=patch(f.body,wire,urls);r.saveIntendedAt='before-save';r.requestSent=true;r.submitted=saved;await persist();
  },
  read:async(_page,id)=>{reads++;assert.equal(String(id),'123');return persisted(saved,record.preparedInput);}
 });
 assert.equal(events.filter(v=>v==='save').length,1);assert.equal(reads,1);assert.equal(record.phase,'us_draft_verified');assert.equal(record.verification.length,6);
 assert.equal(record.preparedInput.destination.draftId,'123');assert.equal(record.preparedInput.destination.shippingTemplate.id,'actual-template-id');
 assert.deepEqual(saved.items.map(v=>v.id),f.body.items.map(v=>v.id));assert.equal(f.input.goods.brand,'Original Brand');
});
