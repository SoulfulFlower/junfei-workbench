import test from 'node:test';
import assert from 'node:assert/strict';
import {validateUkInputs,resolveUkSchema,restoreSkuMapping,makeUkInput,patchUkDraftPayload,verifyUkDraft,prepareUkDraft,migrateAttributes,chooseUkRecommendedCategory,extractSourceIdentifiers,supplementUkRequiredAttributes,readUkPage,ukCategoryRadioReady,ukCategoryPathVisible} from './ego-uk-draft.mjs';
import {gbTshirtRecommendations,verifiedUsTshirtPath} from './fixtures/gb-category-recommendations.mjs';
import {gbShirtListPrice} from './fixtures/gb-shirt-list-price.mjs';

function fixture(){
 const assets=Array.from({length:7},(_,i)=>({sha256:String(i+1).padStart(64,'0'),slot:i+1,width:2000,height:2000}));
 const urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/original-'+i+'.png']));
 const goodsItems=[{sku:'Parent-Blue-S',color:'Blue',size:'S',imageIndices:[0,1,2,3,4,5,6],price:'29.55',quantity:88},{sku:'Parent-Blue-M',color:'Blue',size:'M',imageIndices:[0,1,2,3,4,5,6],price:'30.55',quantity:88}];
 const input={accountId:2,productId:'Product',marketplace:'US',store:'Real US',mode:'draft',masterColor:'Blue',assets,goodsItems,
  goods:{parentSku:'Parent',brand:'Actual Brand',manufacturer:'Maker',title:'A product',highlights:'Pockets',bullets:['1','2','3','4','5'],description:'A description',terms:'search terms'},
  destination:{draftId:'100',destinationId:'source-us',marketId:'11',marketplaceId:'USMARKET',erpUserId:'123',erpAccountId:'123',countryCode:'US',languageTag:'en_US',currency:'USD',sizeValues:{S:'s',M:'m'},variationFields:{color:'color.0.value',size:'apparel_size.0.size'}},
  ukTarget:{id:'target-uk',storeName:'Real UK',countryCode:'GB',currency:'GBP',languageTag:'en_GB',shippingTemplate:{name:'UK Tracked'}},
  ukCommerce:{currency:'GBP',variantPrices:{'Parent-Blue-S':'18.12','Parent-Blue-M':'19.15'},quantities:{'Parent-Blue-S':22,'Parent-Blue-M':23},handlingDays:4,pricingBasis:{source:'product_saved_prices',currency:'GBP'}}};
 const property=(properties)=>({items:{properties}});
 const meta={country_code:'GB',locale:'en_GB',hash:'uk-real-schema',product_type_name:'COAT',schema_content:{$defs:{marketplace_id:{default:'UKMARKET'}},properties:{
  main_product_image_locator:{type:'array',minItems:1,items:{type:'object',required:['media_location'],properties:{media_location:{type:'string',format:'uri',pattern:'^(https?|s3)://'},marketplace_id:{$ref:'#/$defs/marketplace_id'}},additionalProperties:false}},
  color:property({value:{type:'string'},marketplace_id:{type:'string'},language_tag:{type:'string'}}),
  apparel_size:property({size:{enum:['s','m']},size_system:{enum:['uk-system']},marketplace_id:{type:'string'}}),
  brand:property({value:{type:'string'},marketplace_id:{type:'string'},language_tag:{type:'string'}}),
  variation_theme:property({name:{enum:['COLOR_NAME/SIZE_NAME']}}),
  title_differentiation:property({value:{type:'string'},marketplace_id:{type:'string'},language_tag:{type:'string'}})
 }}};
 const sourceAttrs={color:[{value:'Blue',marketplace_id:'USMARKET',language_tag:'en_US'}],apparel_size:[{size:'s',size_system:'as1',marketplace_id:'USMARKET'}],merchant_shipping_group:[{value:'us-template'}]};
 const source={id:900,uid:123,sku:'Parent',country_code:'US',market_id:11,market:{alias:'Real US'},extra:{attributes:sourceAttrs,images:assets.map(a=>urls[a.sha256])},items:goodsItems.map((v,i)=>({id:901+i,uid:123,market_id:11,country_code:'US',sku:v.sku,variation:{'color.0.value':v.color,'apparel_size.0.size':input.destination.sizeValues[v.size]},extra:{attributes:{...sourceAttrs,apparel_size:[{size:input.destination.sizeValues[v.size],size_system:'as1',marketplace_id:'USMARKET'}]},images:null},main_image:urls[assets[0].sha256]}))};
 const copied={code:0,data:{...structuredClone(source),id:200,items:[source.items[1],source.items[0]].map((row,i)=>({...structuredClone(row),id:201+i,sku:'generated-'+i}))}};
 source.standard_product_type='UPC';source.standard_product_id=null;for(const row of source.items){row.standard_product_type=null;row.standard_product_id=null;}
 const prepared=makeUkInput(input,'200',meta);
 const ui={url:'https://www.junfeikuajing.com/#/amazon/product/200?type=draft',store:'Real UK',parentSku:'Parent',brand:'Actual Brand',brandStatus:'UPC豁免：允许销售',shippingTemplate:'UK Tracked',shippingTemplateId:'uk-template',handlingDays:'4',currencies:[['GBP'],['GBP']]};
 const body={id:200,market_id:'22',country_code:'GB',parent_sku:'generated-parent',items:structuredClone(copied.data.items),attributes:{merchant_shipping_group:[{value:'uk-template'}]}};
 return{input,urls,meta,source,copied,prepared,ui,body};
}

function persistedFrom(body,input){return{code:0,data:{...body,id:200,uid:123,market:{alias:'Real UK'},sku:body.parent_sku,extra:{images:body.images,product_description:body.product_description,bullet_point:body.bullet_point,keywords:body.keywords,attributes:body.attributes},items:body.items.map(row=>({...row,pid:200,extra:{images:row.images,attributes:row.attributes}}))}};}
const targetIdentityAttributes=p=>({brand:[{value:p.goods.brand,language_tag:p.destination.languageTag,marketplace_id:p.destination.marketplaceId}],variation_theme:[{name:p.destination.themeValue}]});
const mockSchemaValidation=(meta,records)=>({passed:true,checkedCount:records.length,schemaHash:meta.hash,scope:'isolated_test_adapter'});

test('UK category confirmation waits for the actual checked node and then the visible selected path',()=>{
 const expected={value:'actual-women-jumpers',text:'Fashion Women Clothing Jumpers'};
 const input={checked:false,value:expected.value};let reactiveChecked=false,visiblePath='Baby Products Baby Clothing Knitwear';
 const row={innerText:expected.text+'\n套头衫',querySelector:()=>input,classList:{contains:()=>reactiveChecked},getAttribute:()=>reactiveChecked?'true':'false'};
 const dialog={getBoundingClientRect:()=>({width:800}),querySelectorAll:()=>[row]};
 const doc={querySelectorAll:()=>[dialog],querySelector:()=>({getBoundingClientRect:()=>({width:740}),get innerText(){return visiblePath;}})};
 const run=fn=>Function('document','arg','return ('+fn.toString()+')(arg)')(doc,expected);
 assert.equal(run(ukCategoryRadioReady),false);input.checked=true;assert.equal(run(ukCategoryRadioReady),false);
 reactiveChecked=true;assert.equal(run(ukCategoryRadioReady),false);assert.equal(run(ukCategoryRadioReady),false);assert.equal(run(ukCategoryRadioReady),true);
 input.value='first-baby-node';assert.equal(run(ukCategoryRadioReady),false);input.value=expected.value;assert.equal(run(ukCategoryRadioReady),false);
 assert.equal(run(ukCategoryPathVisible),false);visiblePath='产品分类\nFashion\nWomen\nClothing\nJumpers\n说明';assert.equal(run(ukCategoryPathVisible),true);
});

test('verified US women Pullovers maps only the actual ordinary GB Jumpers leaf',async()=>{
 const f=fixture();f.input.categoryHints={path:'Clothing, Shoes & Jewelry > Women > Clothing > Sweaters > Pullovers'};
 f.input.destination.categoryHints=f.input.categoryHints;f.input.goods.description='Style: Loose crew-neck knitted pullover\nMaterial: 100% acrylic';
 const record={draftId:'200',sourceEvidence:{country_code:'US',product_type_name:'SWEATER'}};
 const rows=[{text:'Fashion Women Clothing Jumpers Cardigans & Sweatshirts Jumpers',value:'real-ordinary'},
  {text:'Fashion Women Clothing Jumpers Cardigans & Sweatshirts Sleeveless Jumpers',value:'sleeveless'},
  {text:'Fashion Women Clothing Maternity Knitwear Jumpers',value:'maternity'},
  {text:'Fashion Men Clothing Jumpers Cardigans & Sweatshirts Jumpers',value:'mens'}];
 assert.equal((await chooseUkRecommendedCategory(rows,f.input,record,async()=>{})).value,'real-ordinary');
 assert.equal(record.categoryMapping.source,'verified_us_pullover_to_observed_uk_jumpers');
 assert.equal(record.categoryMapping.humanReviewed,false);
 assert.equal(f.input.categoryHints.path,'Clothing, Shoes & Jewelry > Women > Clothing > Sweaters > Pullovers');
 await assert.rejects(chooseUkRecommendedCategory(rows.slice(1),f.input,record,async()=>{}),/节点缺失或有歧义/);
 await assert.rejects(chooseUkRecommendedCategory([...rows,rows[0]],f.input,record,async()=>{}),/节点缺失或有歧义/);
 record.sourceEvidence.product_type_name='SHIRT';
 await assert.rejects(chooseUkRecommendedCategory(rows,f.input,record,async()=>{}),/类目推荐有歧义/);
});

test('source-bound acrylic jacquard pullover fills real GB SWEATER fields without inventing supplier weave certification',()=>{
 const f=fixture();f.meta.product_type_name='SWEATER';
 f.input.goods.title="Women's Fair Isle Jacquard Pullover Sweater";
 f.input.goods.description='Style: Loose crew-neck knitted pullover\nMaterial: 100% acrylic';
 f.input.goods.sourceUrl='https://detail.1688.com/offer/123456.html';
 f.input.publicationFacts={supplierModelNumber:'AC123',supplierModelNumberEvidence:{source:'supplier_attribute',value:'AC123',sourceUrl:f.input.goods.sourceUrl},waterResistanceLevel:'not_water_resistant',waterResistanceLevelSource:{basis:{classification:'ordinary_apparel'}}};
 const props=f.meta.schema_content.properties,value=choices=>({items:{properties:{value:{type:'string',...(choices?{enum:choices}:{})},language_tag:{},marketplace_id:{}}}});
 props.item_type_name=value(['Pullover Sweater']);props.manufacturer=value();props.water_resistance_level=value(['not_water_resistant']);
 props.weave_type=value(['Jacquard','Plain']);props.outer={items:{properties:{material:{items:{properties:{value:{type:'string'},language_tag:{}}}},marketplace_id:{}}}};
 const original=structuredClone(f.input),r=supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{});
 assert.equal(r.attributes.item_type_name[0].value,'Pullover Sweater');assert.equal(r.attributes.manufacturer[0].value,'Maker');
 assert.equal(r.attributes.outer[0].material[0].value,'100% acrylic');assert.equal(r.attributes.water_resistance_level[0].value,'not_water_resistant');
 assert.equal(r.attributes.weave_type[0].value,'Jacquard');assert.equal(r.evidence.weave_type.source,'inferred_workbench_classification');assert.equal(r.evidence.weave_type.supplierVerified,false);
 assert.deepEqual(f.input,original);
 for(const change of [x=>x.goods.description=x.goods.description.replace('100% acrylic','Acrylic blend'),x=>x.goods.title='Plain Pullover Sweater',x=>x.publicationFacts.supplierModelNumberEvidence.sourceUrl='https://detail.1688.com/offer/999.html',x=>x.publicationFacts.weaveTypeEvidence={value:'Woven'}]){
  const input=structuredClone(original);change(input);assert.equal(supplementUkRequiredAttributes({},input,f.meta,f.prepared,{}).attributes.weave_type,undefined);
 }
 props.weave_type=value(['Plain']);assert.throws(()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{}),/Jacquard选项/);
});

test('source-bound ribbed cowl SWEATER fills actual GB Rib and Synthetic choices with honest inferred evidence',()=>{
 const f=fixture();f.meta.product_type_name='SWEATER';
 f.input.goods.title='Cowl Neck Tops for Women, Ribbed Knit Long Sleeve Pullover Shirt';
 f.input.goods.description='Material: 95% polyester, 5% spandex\nNeckline: Deep draped cowl\nTexture: Fine vertical ribbing\nFit: Loose pullover shape';
 f.input.goods.sourceUrl='https://detail.1688.com/offer/123456.html';
 f.input.publicationFacts={supplierModelNumber:'CW123',supplierModelNumberEvidence:{source:'supplier_attribute',value:'CW123',sourceUrl:f.input.goods.sourceUrl},waterResistanceLevel:'not_water_resistant',waterResistanceLevelSource:{basis:{classification:'ordinary_apparel'}}};
 const p=f.meta.schema_content.properties,value=choices=>({items:{properties:{value:{type:'string',...(choices?{enum:choices}:{})},language_tag:{},marketplace_id:{}}}});
 p.item_type_name=value(['Pullover Sweater']);p.manufacturer=value();p.water_resistance_level=value(['not_water_resistant']);p.weave_type=value(['Rib','Plain']);
 p.outer={items:{properties:{material:{items:{properties:{value:{type:'string',enum:['Synthetic','Cotton']},language_tag:{}}}},marketplace_id:{}}}};
 const original=structuredClone(f.input),r=supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{});
 assert.equal(r.attributes.weave_type[0].value,'Rib');assert.equal(r.attributes.outer[0].material[0].value,'Synthetic');assert.equal(r.attributes.item_type_name[0].value,'Pullover Sweater');
 assert.equal(r.evidence.weave_type.source,'inferred_workbench_classification');assert.equal(r.evidence.weave_type.supplierVerified,false);assert.deepEqual(f.input,original);
 for(const change of [x=>x.goods.description+='\nFit: Fitted',x=>x.goods.description=x.goods.description.replace('95%','85%'),x=>x.goods.description=x.goods.description.replace('Fine vertical ribbing','Woven'),x=>x.publicationFacts.supplierModelNumberEvidence.sourceUrl='foreign',x=>x.publicationFacts.weaveTypeEvidence={value:'Woven'},x=>x.publicationFacts.waterResistanceLevelSource.basis.classification='protective_apparel']){
  const input=structuredClone(original);change(input);assert.equal(supplementUkRequiredAttributes({},input,f.meta,f.prepared,{}).attributes.weave_type,undefined);
 }
 p.weave_type=value(['Plain']);assert.throws(()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{}),/Rib选项/);
 p.weave_type=value(['Rib']);p.outer.items.properties.material.items.properties.value.enum=['Cotton'];assert.throws(()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{}),/Synthetic选项/);
});

test('GB SKIRT preserves explicit gender when its schema omits the US Womens department',()=>{
 const f=fixture();f.meta.product_type_name='SKIRT';
 f.meta.schema_content.properties.target_gender={items:{properties:{value:{enum:['female','male']},language_tag:{type:'string'},marketplace_id:{type:'string'}}}};
 const attrs={department:[{value:'Womens'}],target_gender:[{value:'female',marketplace_id:'USMARKET'}]};
 const migrated=migrateAttributes(attrs,f.meta,f.input.destination,f.prepared.destination);
 assert.equal(migrated.department,undefined);assert.equal(migrated.target_gender[0].value,'female');
 assert.equal(migrated.target_gender[0].marketplace_id,'UKMARKET');
 attrs.department[0].value='Mens';assert.throws(()=>migrateAttributes(attrs,f.meta,f.input.destination,f.prepared.destination),/不支持原商品属性 department/);
 attrs.department[0].value='Womens';f.meta.product_type_name='COAT';
 assert.throws(()=>migrateAttributes(attrs,f.meta,f.input.destination,f.prepared.destination),/不支持原商品属性 department/);
});

test('UK skirt fills its actual category and composition while rejecting foreign product weave defaults',()=>{
 const f=fixture();f.meta.product_type_name='SKIRT';
 f.input.goods.description='Material: 95% polyester, 5% elastane\nStyle: Fitted mini skirt with short off-center front slit';
 f.prepared.destination.categoryHints={path:'Fashion > Women > Clothing > Skirts'};
 const setting={value:'Plain',source:'user_configured_defaults',productId:f.input.productId,scope:'missing_catalogue_attribute_only',supplierVerified:false,configuredAt:'2026-11-21T18:00:00+08:00',instruction:'Isolated seller setting'};
 f.input.publicationFacts={weaveTypeEvidence:setting};const p=f.meta.schema_content.properties;
 const value=choices=>({items:{properties:{value:{enum:choices}}}});
 p.item_type_name=value(['Skirt','Skort']);p.weave_type=value(['Plain','Satin']);p.manufacturer=value([]);
 p.outer={items:{properties:{material:{items:{properties:{value:{type:'string'},language_tag:{type:'string'}}}}}}};
 let r=supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{});
 assert.equal(r.attributes.item_type_name[0].value,'Skirt');assert.equal(r.attributes.weave_type[0].value,'Plain');
 assert.equal(r.attributes.outer[0].material[0].value,'95% polyester, 5% elastane');
 assert.equal(r.attributes.outer[0].material[0].marketplace_id,undefined);assert.equal(r.evidence.weave_type.supplierVerified,false);
 f.prepared.destination.categoryHints.path='Fashion Women Clothing Skirts';
 p.inner={items:{required:['material'],properties:{marketplace_id:{type:'string'},material:{items:{properties:{value:{type:'string',maxLength:500}}}}}}};
 r=supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{});
 assert.equal(r.attributes.item_type_name[0].value,'Skirt');assert.equal(r.attributes.inner[0].material[0].value,'Base fabric: 95% polyester, 5% elastane; separate lining not specified');
 assert.equal(r.evidence.inner.separateLiningVerified,false);
 p.inner.items.properties.material.items.properties.value.enum=['Cotton'];assert.equal(supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{}).attributes.inner,undefined);
 setting.productId='Other';assert.equal(supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{}).attributes.weave_type,undefined);
 setting.productId=f.input.productId;
 r=supplementUkRequiredAttributes({weave_type:[{value:'Satin'}]},f.input,f.meta,f.prepared,{});assert.equal(r.attributes.weave_type[0].value,'Satin');
 f.prepared.destination.categoryHints.path='Fashion > Women > Clothing > Trousers';
 assert.equal(supplementUkRequiredAttributes({},f.input,f.meta,f.prepared,{}).attributes.item_type_name,undefined);
});

test('UK pants consume an explicit product-bound seller weave setting without claiming supplier verification',()=>{
 const f=fixture();f.meta.product_type_name='PANTS';
 f.input.goods.description='Material: 95% Polyester, 5% Elastane\nStyle: Western wide-leg full-length trousers';
 f.prepared.destination.categoryHints={path:'Fashion > Women > Clothing > Trousers'};
 const setting={value:'Plain',source:'user_configured_defaults',productId:f.input.productId,
  scope:'missing_catalogue_attribute_only',supplierVerified:false,configuredAt:'2026-11-21T15:00:00+08:00',instruction:'Isolated seller test setting'};
 f.input.publicationFacts={waterResistanceLevel:'not_water_resistant',weaveTypeEvidence:setting};
 const p=f.meta.schema_content.properties;
 const value=choices=>({items:{properties:{value:{enum:choices}}}});
 p.item_type_name=value(['Pants']);p.weave_type=value(['Plain','Satin']);p.water_resistance_level=value(['not_water_resistant']);
 p.fit_type=value(['Loose','Flowy']);
 p.leg={items:{properties:{style:value(['Wide'])}}};
 const before=structuredClone(f.input);
 const read=()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared);
 assert.equal(read().attributes.weave_type[0].value,'Plain');assert.deepEqual(read().evidence.weave_type,setting);
 assert.equal(read().attributes.fit_type[0].value,'Loose');
 assert.equal(read().evidence.fit_type.source,'inferred_workbench_classification');
 assert.equal(read().evidence.fit_type.humanReviewed,false);
 const explicitFit=[{value:'Regular',language_tag:'en_GB',marketplace_id:'UKMARKET'}];
 assert.deepEqual(supplementUkRequiredAttributes({fit_type:explicitFit},f.input,f.meta,f.prepared).attributes.fit_type,explicitFit);
 assert.deepEqual(f.input,before);
 for(const [key,v] of [['productId','other'],['source','agent_guess'],['supplierVerified',true],['instruction','']]){
  f.input.publicationFacts.weaveTypeEvidence={...setting,[key]:v};assert.equal(read().attributes.weave_type,undefined);
 }
 f.input.publicationFacts.weaveTypeEvidence=setting;p.weave_type=value(['Satin']);assert.throws(read,/已核实的属性值/);
});

test('UK shipping readback uses the unique visible label when the native placeholder changes',async()=>{
 const current='input[data-studio-uk-shipping="true"]';
 let marked=false;
 const visible={getBoundingClientRect:()=>({width:100})};
 const shipping={...visible,placeholder:'Migrated Template',value:'UK Tracked',
  closest:()=>({__vue__:{value:'uk-template'}}),setAttribute:(name,value)=>{assert.equal(name,'data-studio-uk-shipping');assert.equal(value,'true');marked=true;}};
 const label={...visible,innerText:'配送模板',closest:()=>({querySelectorAll:()=>[shipping]})};
 const row={querySelector:()=>({}),innerText:'GBP'};
 const context={location:{href:'https://www.junfeikuajing.com/#/amazon/product/200?type=draft'},
  getComputedStyle:()=>({visibility:'visible'}),document:{querySelectorAll:selector=>selector.startsWith('label')?[label]:[row],
   querySelector:selector=>selector===current&&marked?shipping:selector.includes('亚马逊运输模板')?null:{value:'Other',closest:()=>({innerText:''})}}};
 const execute=(func,arg)=>Function('document','location','getComputedStyle','arg','return ('+func+')(arg)')
  (context.document,context.location,context.getComputedStyle,arg);
 const page={evaluate:async(func,arg)=>execute(func,arg),waitForFunction:async(func,arg)=>assert.ok(execute(func,arg))};
 const result=await readUkPage(page);
 assert.equal(result.shippingTemplate,'UK Tracked');assert.equal(result.shippingTemplateId,'uk-template');
 assert.deepEqual(result.currencies,[['GBP']]);
});

function materialFixture(){
 const f=fixture(),localized=value=>({type:'array',items:{type:'object',required:['language_tag','value'],properties:{value,
  language_tag:{type:'string'},marketplace_id:{$ref:'#/$defs/marketplace_id'}}}});
 f.meta.product_type_name='SWEATSHIRT';
 Object.assign(f.meta.schema_content.properties,{
  fabric_type:localized({type:'string'}),
  material:localized({type:'string',anyOf:[{type:'string'},{type:'string',enum:['Cotton','Polyester','Polyester Blend','Spandex']}]})
 });
 return f;
}

test('UK half-zip sweatshirt uses known facts and reserves weave for the exact confirmed source',()=>{
 const f=materialFixture();
 f.input.goods.description='Style: regular-cut half-zip pullover\nMaterial: 95% polyester, 5% spandex';
 f.input.goods.sourceUrl='https://detail.1688.com/offer/123.html';
 f.meta.schema_content.properties.weave_type={items:{properties:{value:{anyOf:[{type:'string'},{enum:['Cable']}]}}}};
 const read=()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared);
 assert.equal(read().attributes.item_type_name[0].value,'Sweatshirt');
 assert.equal(read().attributes.outer[0].material[0].value,'95% polyester, 5% spandex');
 assert.equal(read().attributes.weave_type,undefined);
 f.input.ukPreparation={sweatshirtWeave:{productId:'Product',sourceUrl:f.input.goods.sourceUrl,value:'Knit',source:'user_confirmation'}};
 assert.equal(read().attributes.weave_type[0].value,'Knit');
 f.input.ukPreparation.sweatshirtWeave.sourceUrl+='?different';
 assert.equal(read().attributes.weave_type,undefined);
});

test('UK hooded half-zip takes the woven value from the same frozen supplier',()=>{
 const f=materialFixture();
 f.input.goods.description='Style: Relaxed-fit hooded pullover\nMaterial: 95% polyester, 5% elastane\nClosure: Half zip\nHood: Drawstring';
 f.input.goods.sourceUrl='https://detail.1688.com/offer/123.html';
 f.meta.schema_content.properties.weave_type={items:{properties:{value:{enum:['Woven','Knit']}}}};
 const weave={source:'supplier_attribute',sourceUrl:f.input.goods.sourceUrl,field:'工艺',sourceValue:'梭织',value:'Woven'};
 f.input.publicationFacts={weaveTypeEvidence:weave};
 const read=()=>supplementUkRequiredAttributes({fabric_type:[{value:'95% polyester, 5% elastane'}]},f.input,f.meta,f.prepared);
 const result=read();
 assert.equal(result.attributes.weave_type[0].value,'Woven');
 assert.equal(result.attributes.item_type_name[0].value,'Sweatshirt');
 assert.equal(result.attributes.material[0].value,'Polyester Blend');
 assert.deepEqual(result.evidence.weave_type,weave);
 f.input.publicationFacts.weaveTypeEvidence={...weave,value:'Knit'};
 assert.equal(read().attributes.weave_type,undefined);
 f.input.publicationFacts.weaveTypeEvidence={...weave,sourceUrl:'https://detail.1688.com/offer/321.html'};
 assert.equal(read().attributes.weave_type,undefined);
});

test('UK material requires unique native enum matches and complete unambiguous fabric proportions',()=>{
 const f=materialFixture(),project=(value,attributes={})=>supplementUkRequiredAttributes({fabric_type:[{value}],...attributes},f.input,f.meta,f.prepared);
 for(const sourceValue of ['Polyester',' polyester ','100% Polyester']){
  const {attributes,evidence}=project(sourceValue);
  assert.deepEqual(attributes.material,[{value:'Polyester',language_tag:'en_GB',marketplace_id:'UKMARKET'}]);
  assert.equal(evidence.material.sourceValue,sourceValue);
 }
 for(const sourceValue of ['95% Polyester, 5% Spandex','95% Polyester, 5% Elastane','75.01% Polyester / 24.99% Cotton']){
  const {attributes,evidence}=project(sourceValue);
  assert.equal(attributes.material[0].value,'Polyester Blend');
  assert.equal(evidence.material.transformation,'majority_fiber_blend_enum');
  assert.equal(evidence.material.primaryFiber,'Polyester');
  assert.equal(evidence.material.sourceValue,sourceValue);
 }
 for(const value of ['Polyester Blend','90% Polyester','94% Polyester, 5% Elastane, 1% Spandex','95% Polyester, 5% polyester',
  '95% Polyester, 6% Spandex','100% Polyester, 0% Spandex','50% Polyester, 50% Cotton','40% Polyester, 30% Cotton, 30% Spandex',
  '95% Cotton, 5% Spandex','Unknown']){
  const result=project(value);assert.equal(result.attributes.material,undefined,value);assert.equal(result.evidence.material,undefined,value);
 }
 const explicit=[{value:'Cotton',language_tag:'en_GB',marketplace_id:'UKMARKET'}];
 assert.deepEqual(project('Polyester',{material:explicit}).attributes.material,explicit);
 assert.equal(project('Polyester',{fabric_type:[{value:'Polyester'},{value:'Polyester'}]}).attributes.material,undefined);
 const enumValues=f.meta.schema_content.properties.material.items.properties.value.anyOf[1].enum;
 enumValues.push('polyester');assert.equal(project('Polyester').attributes.material,undefined);enumValues.pop();
 f.prepared.destination.marketplaceId='Another site';assert.equal(project('Polyester').attributes.material,undefined);
 f.prepared.destination.marketplaceId='UKMARKET';delete f.meta.schema_content.properties.material;
 assert.equal(project('Polyester').attributes.material,undefined);
});

test('fresh UK Save preserves fabric composition and writes localized material with private source evidence',async()=>{
 const f=materialFixture(),usFabric=value=>[{value,language_tag:'en_US',marketplace_id:'USMARKET'}];
 f.source.extra.attributes.fabric_type=usFabric('100% Polyester');
 f.source.items[0].extra.attributes.fabric_type=usFabric('95% Polyester, 5% Spandex');
 f.source.items[1].extra.attributes.fabric_type=usFabric('95% Polyester, 5% Elastane');
 const record={draftId:200,sourceEvidence:f.source,urls:f.urls},original=structuredClone(f.source),validations=[];
 let saved,reads=0;
 await prepareUkDraft({},f.input,record,async()=>{}, {
  validate:(meta,rows)=>{validations.push(structuredClone(rows));return mockSchemaValidation(meta,rows);},
  read:async()=>++reads===1?f.copied:persistedFrom(saved),prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),
  save:async(_page,wire,urls,r,_persist,patch)=>{saved=patch(f.body,wire,urls);r.submitted=saved;},
  ui:async()=>f.ui,remote:async(_url,a)=>({sha256:a.sha256,bytes:1})
 });
 assert.equal(record.phase,'uk_draft_verified');assert.equal(validations.length,2);assert.deepEqual(f.source,original);
 const localize=value=>[{value,language_tag:'en_GB',marketplace_id:'UKMARKET'}];
 const first=saved.items.find(row=>row.sku==='Parent-Blue-S'),second=saved.items.find(row=>row.sku==='Parent-Blue-M');
 assert.deepEqual(saved.attributes.material,localize('Polyester'));
 assert.deepEqual(first.attributes.material,localize('Polyester Blend'));
 assert.deepEqual(first.attributes.fabric_type,localize('95% Polyester, 5% Spandex'));
 assert.deepEqual(second.attributes.material,localize('Polyester Blend'));
 assert.deepEqual(second.attributes.fabric_type,localize('95% Polyester, 5% Elastane'));
 assert.equal(record.requiredAttributeEvidence.Parent.material.sourceValue,'100% Polyester');
 assert.equal(record.requiredAttributeEvidence[first.sku].material.primaryPercentage,95);
 assert.doesNotMatch(JSON.stringify(saved),/original_migrated_fabric_type|majority_fiber_blend_enum/);
 const materialBySku=rows=>Object.fromEntries(rows.map(row=>[row.id,row.attributes.material]));
 assert.deepEqual(materialBySku(validations[0]),materialBySku(validations[1]));
 assert.equal(record.materialReadback.bySku.Parent.status,'matched');
 assert.deepEqual(record.materialReadback.bySku[first.sku],{status:'matched',expectedValue:'Polyester Blend',
  observed:[{value:'Polyester Blend',languageTag:'en_GB',marketplaceId:'UKMARKET'}]});
 assert.deepEqual(record.materialReadback.bySku[second.sku],record.materialReadback.bySku[first.sku]);
 const missingOnReadback=persistedFrom(structuredClone(saved));
 delete missingOnReadback.data.items.find(row=>row.sku===first.sku).extra.attributes.material;
 let resumedSaves=0;
 await prepareUkDraft({},f.input,record,async()=>{}, {
  validate:mockSchemaValidation,read:async()=>missingOnReadback,ui:async()=>f.ui,remote:async(_url,a)=>({sha256:a.sha256,bytes:1}),
  prepare:async()=>assert.fail('verified UK draft must not be prepared again'),save:async()=>resumedSaves++
 });
 assert.equal(resumedSaves,0);assert.equal(record.phase,'uk_draft_verified');
 assert.deepEqual(record.materialReadback.bySku[first.sku],{status:'missing',expectedValue:'Polyester Blend',observed:null});
});

test('UK inputs require product GBP prices, explicit stock, UK identity and handling',()=>{
 assert.equal(validateUkInputs(fixture().input),true);
 for(const change of [f=>delete f.input.ukTarget.id,f=>f.input.ukTarget.marketId='11',f=>f.input.ukTarget.marketplaceId='USMARKET',f=>f.input.ukTarget.currency='USD',f=>f.input.ukTarget.storeName='Real US',f=>delete f.input.ukTarget.shippingTemplate,f=>delete f.input.ukCommerce.variantPrices['Parent-Blue-S'],f=>delete f.input.ukCommerce.quantities['Parent-Blue-M'],f=>f.input.ukCommerce.handlingDays=undefined]){const f=fixture();change(f);assert.throws(()=>validateUkInputs(f.input));}
});

test('UK schema and destination IDs are independently resolved; US IDs never survive',()=>{
 const f=fixture(),p=makeUkInput(f.input,'200',f.meta);
 assert.equal(p.destination.marketId,undefined);assert.equal(p.destination.marketplaceId,'UKMARKET');assert.equal(p.destination.destinationId,'target-uk');assert.equal(p.destination.erpAccountId,'123');assert.equal(p.goodsItems[1].price,'19.15');assert.equal(p.goodsItems[1].quantity,23);
 assert.equal(p.destination.requireMainImageLocator,true);assert.equal(f.input.destination.requireMainImageLocator,undefined);
 for(const change of [m=>m.country_code='US',m=>m.locale='en_US',m=>m.schema_content.$defs.marketplace_id.default='USMARKET',m=>delete m.hash]){const m=structuredClone(f.meta);change(m);assert.throws(()=>resolveUkSchema(m,f.input));}
});

test('UK selection records actual node values and fallback taxonomy before choosing, including ambiguous retries',async()=>{
 const f=fixture();f.input.categoryHints={path:'',title:'Long Sleeve Pullover'};f.input.destination.categoryHints={path:verifiedUsTshirtPath,evidence:'verified source category'};
 f.input.goods.title='Long Sleeve Tops for Women, Fine-Ribbed Fitted Crew Neck Pullover';
 assert.deepEqual(makeUkInput(f.input,200,f.meta).destination.categoryHints,f.input.destination.categoryHints);
 const record={draftId:'200',sourceEvidence:{original:'unchanged'}},snapshots=[];
 const selected=await chooseUkRecommendedCategory(gbTshirtRecommendations,f.input,record,async()=>snapshots.push(structuredClone(record)));
 assert.equal(selected.index,302);assert.equal(snapshots.length,2);assert.equal(snapshots[0].categoryChoice,undefined);
 assert.deepEqual(snapshots[0].categoryRecommendation.candidates,gbTshirtRecommendations);assert.deepEqual(snapshots[0].categoryRecommendation.hints,f.input.destination.categoryHints);
 assert.equal(snapshots[0].categoryRecommendation.store,f.input.ukTarget.storeName);assert.equal(snapshots[0].categoryRecommendation.countryCode,'GB');
 const original=structuredClone(record.categoryRecommendation),ordinary=gbTshirtRecommendations.find(row=>row.index===302),ambiguous=[ordinary,{...ordinary,index:999,value:'another-native-node'}];
 await assert.rejects(()=>chooseUkRecommendedCategory(ambiguous,f.input,record,async()=>snapshots.push(structuredClone(record))),/歧义/);
 assert.equal(snapshots.length,3);assert.equal(record.categoryChoice,undefined);assert.deepEqual(record.categoryRecommendation.candidates,ambiguous);
 assert.deepEqual(record.categoryRecommendationHistory,[original]);assert.equal(record.draftId,'200');assert.deepEqual(record.sourceEvidence,{original:'unchanged'});
 f.input.ukTarget.categoryHints={path:ordinary.text,evidence:'verified target node'};
 await chooseUkRecommendedCategory(gbTshirtRecommendations,f.input,record,async()=>{});assert.deepEqual(record.categoryRecommendation.hints,f.input.ukTarget.categoryHints);
 const missingNode={...ordinary};delete missingNode.value;
 await assert.rejects(()=>chooseUkRecommendedCategory([missingNode],f.input,record,async()=>{}),/节点编号/);assert.equal(record.categoryChoice,undefined);
});

test('new UK preparation stops when the actual target schema cannot accept a marketplace-specific MAIN locator',()=>{
 for(const mutate of [m=>delete m.schema_content.properties.main_product_image_locator,
  m=>m.schema_content.properties.main_product_image_locator.type='object',
  m=>delete m.schema_content.properties.main_product_image_locator.items.properties.marketplace_id,
  m=>m.schema_content.properties.main_product_image_locator.maxItems=0]){
  const f=fixture();mutate(f.meta);assert.throws(()=>makeUkInput(f.input,200,f.meta),/MAIN/);
 }
});

test('native regenerated and reordered children restore exact original SKUs by color/size',()=>{
 const f=fixture(),rows=restoreSkuMapping(f.copied.data.items,f.input,f.prepared.destination);
 assert.deepEqual(rows.map(r=>r.sku),['Parent-Blue-M','Parent-Blue-S']);
 assert.deepEqual(rows.map(r=>r.id),[201,202]);
 for(const change of [rows=>rows[0].variation['apparel_size.0.size']='unknown',rows=>rows[1].variation['apparel_size.0.size']='m',rows=>rows[1].id=rows[0].id]){const rows=structuredClone(f.copied.data.items);change(rows);assert.throws(()=>restoreSkuMapping(rows,f.input,f.prepared.destination));}
});

test('observed UK shipping correction affects preparation, preserving original copy target',()=>{
 const f=fixture(),original=structuredClone(f.input.ukTarget);f.input.ukPreparation={shippingTemplate:{name:'Actual UK Migrated Template'}};
 assert.equal(makeUkInput(f.input,'200',f.meta).destination.shippingTemplate.name,'Actual UK Migrated Template');assert.deepEqual(f.input.ukTarget,original);
 f.input.ukPreparation.shippingTemplate.id='guessed';assert.throws(()=>makeUkInput(f.input,'200',f.meta));
});

test('UK enum migration accepts only a unique case-equivalent actual enum',()=>{
 const meta={schema_content:{properties:{unit_count:{items:{properties:{type:{properties:{value:{enum:['count']}}}}}}}}};
 assert.deepEqual(migrateAttributes({unit_count:[{type:{value:'Count'}}]},meta,{},{}),{unit_count:[{type:{value:'count'}}]});
 assert.throws(()=>migrateAttributes({unit_count:[{type:{value:'grams'}}]},meta,{},{}));
 meta.schema_content.properties.unit_count.items.properties.type.properties.value.enum=['count','COUNT'];
 assert.throws(()=>migrateAttributes({unit_count:[{type:{value:'Count'}}]},meta,{},{}));
});

test('only the proven zero USD list-price sentinel can migrate to actual schema-supported GBP',()=>{
 const f=fixture(),schema=f.meta.schema_content;
 schema.$defs.list_price_currency={type:'string',enum:['GBP']};
 schema.properties.list_price={items:{properties:{currency:{$ref:'#/$defs/list_price_currency'},value:{type:'number'},marketplace_id:{type:'string'}}}};
 const original={list_price:[{currency:'USD',value:0,marketplace_id:'USMARKET'}],merchant_shipping_group:[{value:'us-template'}],fulfillment_availability:[{quantity:88}]};
 const migrated=migrateAttributes(original,f.meta,f.input.destination,f.prepared.destination);
 assert.deepEqual(migrated,{list_price:[{currency:'GBP',value:0,marketplace_id:'UKMARKET'}]});
 assert.equal(original.list_price[0].currency,'USD');
 for(const value of [12.34,'0',null,undefined]){
  const attrs={list_price:[{currency:'USD',value,marketplace_id:'USMARKET'}]};assert.throws(()=>migrateAttributes(attrs,f.meta,f.input.destination,f.prepared.destination),/参考价/);
 }
 for(const currency of [undefined,[],['USD']]){
  const meta=structuredClone(f.meta);meta.schema_content.$defs.list_price_currency.enum=currency;
  assert.throws(()=>migrateAttributes(original,meta,f.input.destination,f.prepared.destination),/GBP/);
 }
 schema.$defs.list_price_currency.enum=['USD','GBP'];
 assert.throws(()=>migrateAttributes({list_price:[{currency:'USD',value:12.34}]},f.meta,f.input.destination,f.prepared.destination),/参考价/);
 schema.properties.other_price=structuredClone(schema.properties.list_price);schema.$defs.list_price_currency.enum=['GBP'];
 assert.throws(()=>migrateAttributes({other_price:[{currency:'USD',value:0}]},f.meta,f.input.destination,f.prepared.destination),/枚举/);
});

test('actual GB SHIRT uses the explicitly permitted zero value_with_tax sentinel instead of the US value key',()=>{
 const source={countryCode:'US',currency:'USD',marketplaceId:'ATVPDKIKX0DER',languageTag:'en_US'},target={countryCode:'GB',currency:'GBP',marketplaceId:'A1F83G8C2ARO7P',languageTag:'en_GB'};
 const meta={schema_content:{$defs:{marketplace_id:{type:'string',default:target.marketplaceId}},properties:{list_price:structuredClone(gbShirtListPrice)}}};
 meta.schema_content.properties.care_instructions={items:{properties:{value:{type:'string'},marketplace_id:{type:'string'},language_tag:{type:'string'}}}};
 const original={list_price:[{currency:'USD',value:0,marketplace_id:source.marketplaceId}],care_instructions:[{value:'Machine Wash',language_tag:'en_US',marketplace_id:source.marketplaceId}]},before=structuredClone(original);
 const migrated=migrateAttributes(original,meta,source,target);
 assert.deepEqual(migrated.list_price,[{currency:'GBP',value_with_tax:0,marketplace_id:target.marketplaceId}]);
 assert.deepEqual(migrated.care_instructions,[{value:'Machine Wash',language_tag:'en_GB',marketplace_id:target.marketplaceId}]);assert.deepEqual(original,before);
 for(const value of [8.19,13.95,-1,'0',null,undefined,false])assert.throws(()=>migrateAttributes({list_price:[{currency:'USD',value,marketplace_id:source.marketplaceId}]},meta,source,target),/参考价/);
 for(const list of [[],null,[{currency:'USD'}],[{currency:'GBP',value:0}],[{currency:'USD',value:0,unknown:'unverified'}],[{currency:'USD',value:0,marketplace_id:'Other'}],[{currency:'USD',value:0},{currency:'USD',value:0}]])assert.throws(()=>migrateAttributes({list_price:list},meta,source,target),/参考价/);
 for(const alter of [m=>m.schema_content.properties.list_price.items.properties.value_with_tax.minimum=1,
  m=>delete m.schema_content.properties.list_price.items.properties.value_with_tax.description,
  m=>m.schema_content.properties.list_price.items.properties.currency.enum=['USD'],
  m=>m.schema_content.properties.list_price.items.properties.currency.enum=['USD','GBP'],
  m=>m.schema_content.properties.list_price.items.properties.value={type:'number'},
  m=>m.schema_content.properties.list_price.items.additionalProperties=true]){
  const changed=structuredClone(meta);alter(changed);assert.throws(()=>migrateAttributes(original,changed,source,target),/真实schema/);
 }
 assert.throws(()=>migrateAttributes(original,meta,source,{...target,currency:'USD'}),/真实schema/);
 assert.throws(()=>migrateAttributes(original,meta,{...source,countryCode:'GB'},target),/真实schema/);
});

test('UK Save uses native UK market/template IDs and restores exact SKU/images/commerce',()=>{
 const f=fixture(),mapping=restoreSkuMapping(f.copied.data.items,f.input,f.prepared.destination);
 const wire={...f.input,ukPrepared:f.prepared,ukCopiedRows:mapping,ukParentAttributes:{supplier_declared_has_product_identifier_exemption:[{value:true}],fulfillment_availability:[{lead_time_to_ship_max_days:'4'}]},ukItemAttributes:{'Parent-Blue-M':{},'Parent-Blue-S':{}}};
 const body=patchUkDraftPayload(f.body,wire,f.urls);assert.equal(body.parent_sku,'Parent');assert.equal(body.market_id,'22');assert.equal(body.with_publish,false);assert.equal(body.attributes.merchant_shipping_group[0].value,'uk-template');assert.deepEqual(body.items.map(r=>r.sku),['Parent-Blue-M','Parent-Blue-S']);assert.equal(body.items[0].price,'19.15');assert.equal(body.items[0].quantity,'23');assert.deepEqual(body.items[0].images,f.input.assets.map(a=>f.urls[a.sha256]));
 assert.deepEqual(body.attributes.main_product_image_locator,[{media_location:body.main_image,marketplace_id:'UKMARKET'}]);
 for(const row of body.items)assert.deepEqual(row.attributes.main_product_image_locator,[{media_location:row.main_image,marketplace_id:'UKMARKET'}]);
 for(const change of [b=>b.market_id='11',b=>b.country_code='US',b=>b.publish=true,b=>delete b.attributes.merchant_shipping_group,b=>b.items[0].id=999]){const b=structuredClone(f.body);change(b);assert.throws(()=>patchUkDraftPayload(b,wire,f.urls));}
});

test('native UK invented parent and thirty child UPCs are replaced by exact original US null IDs and types',()=>{
 const f=fixture();f.source.items=Array.from({length:30},(_,n)=>({...structuredClone(f.source.items[0]),sku:'Original-'+n}));
 f.prepared.goodsItems=f.source.items.map(row=>({...structuredClone(f.prepared.goodsItems[0]),sku:row.sku}));
 f.prepared.sourceIdentifiers=extractSourceIdentifiers(f.source);
 const copied=f.source.items.map((row,n)=>({...structuredClone(row),id:500+n,sku:'generated-'+n,standard_product_type:'UPC',standard_product_id:String(796225904185+n)}));
 const mapping=copied.map((row,n)=>({...row,sku:f.source.items[n].sku,variation:{'color.0.value':'Blue','apparel_size.0.size':'s'}}));
 const wire={...f.input,ukPrepared:f.prepared,ukCopiedRows:mapping,ukParentAttributes:{},ukItemAttributes:Object.fromEntries(f.source.items.map(r=>[r.sku,{}]))};
 const body=patchUkDraftPayload({...f.body,standard_product_type:'UPC',standard_product_id:'796225904178',items:copied},wire,f.urls);
 assert.equal(body.standard_product_type,'UPC');assert.equal(body.standard_product_id,null);assert.equal(body.items.length,30);
 for(const row of body.items){assert.equal(row.standard_product_type,null);assert.equal(row.standard_product_id,null);}
});

test('known source identifiers survive UK copy defaults exactly rather than being globally cleared',()=>{
 const f=fixture();f.source.standard_product_id='123456789012';f.source.items[0].standard_product_type='EAN';f.source.items[0].standard_product_id='1234567890123';
 f.prepared.sourceIdentifiers=extractSourceIdentifiers(f.source);const mapping=restoreSkuMapping(f.copied.data.items,f.input,f.prepared.destination);
 const wire={...f.input,ukPrepared:f.prepared,ukCopiedRows:mapping,ukParentAttributes:{},ukItemAttributes:{'Parent-Blue-M':{},'Parent-Blue-S':{}}};
 const body=patchUkDraftPayload({...f.body,standard_product_id:'generated',items:f.body.items.map(r=>({...r,standard_product_type:'UPC',standard_product_id:'generated'}))},wire,f.urls);
 assert.equal(body.standard_product_id,'123456789012');const small=body.items.find(r=>r.sku==='Parent-Blue-S');assert.equal(small.standard_product_type,'EAN');assert.equal(small.standard_product_id,'1234567890123');
 const missing=structuredClone(f.source);delete missing.items[0].standard_product_id;assert.throws(()=>extractSourceIdentifiers(missing),/未完整回读/);
});

test('full mock preparation saves, reopens and hashes every original image without uploading',async()=>{
 const f=fixture(),record={draftId:200,sourceEvidence:f.source,urls:f.urls};let saved,persists=0,reads=0,remoteReads=0;
 await prepareUkDraft({},f.input,record,async()=>persists++,{
  validate:mockSchemaValidation,
  read:async()=>++reads===1?f.copied:persistedFrom(saved),
  prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),
  save:async(page,wire,urls,r,persist,patch)=>{saved=patch(f.body,wire,urls);r.saveIntendedAt='now';r.submitted=saved;await persist();},
  ui:async()=>f.ui,remote:async(url,a)=>{remoteReads++;return{sha256:a.sha256,bytes:500};}
 });
 assert.equal(record.phase,'uk_draft_verified');assert.equal(reads,2);assert.equal(remoteReads,7);assert.equal(record.preparedInput.destination.marketId,'22');assert.equal(record.preparedInput.destination.shippingTemplate.id,'uk-template');assert.equal(record.verification.length,2);assert.ok(persists>=8);
 assert.equal(saved.quantity,'0');assert.deepEqual(saved.attributes.fulfillment_availability,[{fulfillment_channel_code:'DEFAULT',quantity:0,lead_time_to_ship_max_days:4}]);
 for(const row of saved.items){const v=record.preparedInput.goodsItems.find(v=>v.sku===row.sku);
  assert.deepEqual(row.attributes.fulfillment_availability,[{fulfillment_channel_code:'DEFAULT',quantity:Number(v.quantity),lead_time_to_ship_max_days:4}]);
  assert.deepEqual(row.attributes.merchant_shipping_group,[{value:'uk-template',marketplace_id:'UKMARKET'}]);
 }
 assert.equal(saved.attributes.apparel_size[0].size_system,'uk-system');assert.equal(saved.items[0].attributes.color[0].marketplace_id,'UKMARKET');assert.equal(saved.items[0].attributes.apparel_size[0].size,'m');assert.equal(saved.items[0].attributes.supplier_declared_has_product_identifier_exemption[0].value,true);
 const p=record.preparedInput,actual=persistedFrom(saved);
 const inherited=structuredClone(actual);for(const row of inherited.data.items){row.market_id=null;row.country_code=null;}
 assert.ok(verifyUkDraft(inherited,p,f.urls,f.ui));
 for(const change of [d=>d.data.items[0].pid=999,d=>d.data.items[0].extra.attributes.color[0].marketplace_id='USMARKET',d=>d.data.items[0].extra.attributes.color[0].language_tag='en_US']){const d=structuredClone(inherited);change(d);assert.throws(()=>verifyUkDraft(d,p,f.urls,f.ui));}
 for(const change of [d=>d.data.market_id=11,d=>d.data.uid=555,d=>d.data.items[0].uid=999,d=>d.data.items[0].market_id=11,d=>d.data.items[0].country_code='US',d=>d.data.items[0].extra.attributes.supplier_declared_has_product_identifier_exemption[0].value=false,d=>d.data.extra.attributes.merchant_shipping_group[0].value='us-template',d=>d.data.items[0].extra.images.reverse(),d=>d.data.items[0].price='29.55']){const d=structuredClone(actual);change(d);assert.throws(()=>verifyUkDraft(d,p,f.urls,f.ui));}
 for(const change of [d=>d.data.extra.attributes.fulfillment_availability[0].quantity=88,d=>delete d.data.items[0].extra.attributes.fulfillment_availability[0].quantity,
  d=>d.data.items[0].extra.attributes.fulfillment_availability[0].quantity=88,d=>d.data.items[0].extra.attributes.fulfillment_availability[0].lead_time_to_ship_max_days=3,
  d=>delete d.data.items[0].extra.attributes.merchant_shipping_group,d=>d.data.items[0].extra.attributes.merchant_shipping_group[0].value='us-template']){
  const d=structuredClone(actual);change(d);assert.throws(()=>verifyUkDraft(d,p,f.urls,f.ui),/库存|处理时间|运输模板/);
 }
 for(const change of [u=>u.store='Real US',u=>u.brandStatus='UPC豁免：待审核',u=>u.currencies[0]=['USD'],u=>u.shippingTemplate='US Standard']){const ui=structuredClone(f.ui);change(ui);assert.throws(()=>verifyUkDraft(actual,p,f.urls,ui));}
});

test('UK schema guard checks the exact selected-template payload before Save and raw parent/children after readback',async()=>{
 const f=fixture(),record={draftId:200,sourceEvidence:f.source,urls:f.urls},validations=[];let saved,reads=0;
 await prepareUkDraft({},f.input,record,async()=>{}, {
  validate:(meta,records,prepared)=>{validations.push(structuredClone(records));assert.equal(prepared.destination.shippingTemplate.id,'uk-template');return mockSchemaValidation(meta,records);},
  read:async()=>++reads===1?f.copied:persistedFrom(saved),prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),
  save:async(_page,wire,urls,r,persist,patch)=>{assert.equal(r.schemaValidationBeforeSave.passed,true);saved=patch(f.body,wire,urls);r.saveIntendedAt='before-save';r.submitted=saved;await persist();},
  ui:async()=>f.ui,remote:async(_url,a)=>({sha256:a.sha256,bytes:1})
 });
 assert.equal(validations.length,2);assert.equal(record.schemaValidationAfterSave.checkedCount,3);
 const byId=records=>Object.fromEntries(records.map(row=>[row.id,row.attributes]));
 const expected={Parent:saved.attributes,...Object.fromEntries(saved.items.map(row=>[row.sku,row.attributes]))};
 assert.deepEqual(byId(validations[0]),expected);assert.deepEqual(byId(validations[1]),expected);
});

test('UK rebuilds each colour MAIN from its own frozen gallery and rejects lost or parent-inherited MAIN after Save',async()=>{
 const f=fixture(),oldSku=f.input.goodsItems[1].sku;
 for(let i=7;i<14;i++){const asset={sha256:String(i+1).padStart(64,'0'),slot:i-6,width:2000,height:2000};f.input.assets.push(asset);f.urls[asset.sha256]='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/red-'+i+'.png';}
 Object.assign(f.input.goodsItems[1],{sku:'Parent-Red-M',color:'Red',imageIndices:[7,8,9,10,11,12,13]});
 for(const key of ['variantPrices','quantities']){f.input.ukCommerce[key]['Parent-Red-M']=f.input.ukCommerce[key][oldSku];delete f.input.ukCommerce[key][oldSku];}
 const cover=f.urls[f.input.assets[0].sha256],staleMain=[{media_location:cover,marketplace_id:'USMARKET'}];
 f.source.extra.attributes.main_product_image_locator=structuredClone(staleMain);
 for(let i=0;i<f.source.items.length;i++){
  const row=f.source.items[i],v=f.input.goodsItems[i],images=v.imageIndices.map(n=>f.urls[f.input.assets[n].sha256]);
  row.sku=v.sku;row.variation['color.0.value']=v.color;row.extra.attributes.color=[{value:v.color,marketplace_id:'USMARKET',language_tag:'en_US'}];
  row.extra.images=images;row.main_image=images[0];row.extra.attributes.main_product_image_locator=structuredClone(staleMain);
 }
 f.copied.data.items=[...f.source.items].reverse().map((row,i)=>({...structuredClone(row),id:201+i,sku:'generated-'+i}));
 f.body.items=structuredClone(f.copied.data.items);f.prepared=makeUkInput(f.input,200,f.meta);
 const sourceBefore=structuredClone(f.source),record={draftId:200,sourceEvidence:f.source,urls:f.urls},validations=[];let saved,reads=0;
 await prepareUkDraft({},f.input,record,async()=>{}, {
  read:async()=>++reads===1?f.copied:persistedFrom(saved),prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),
  validate:(meta,records)=>{validations.push(structuredClone(records));return mockSchemaValidation(meta,records);},
  save:async(_page,wire,urls,r,persist,patch)=>{const serialized=(0,eval)('('+patch.toString()+')');saved=serialized(f.body,wire,urls);r.saveIntendedAt='before-save';r.submitted=saved;await persist();},
  ui:async()=>f.ui,remote:async(_url,a)=>({sha256:a.sha256,bytes:1})
 });
 assert.equal(validations.length,2);assert.deepEqual(f.source,sourceBefore);
 for(const records of validations){
  assert.deepEqual(records[0].attributes.main_product_image_locator,[{media_location:cover,marketplace_id:'UKMARKET'}]);
  for(const row of records.slice(1)){const v=f.input.goodsItems.find(v=>v.sku===row.id);assert.deepEqual(row.attributes.main_product_image_locator,[{media_location:f.urls[f.input.assets[v.imageIndices[0]].sha256],marketplace_id:'UKMARKET'}]);}
 }
 const actual=persistedFrom(saved),red=actual.data.items.find(row=>row.sku==='Parent-Red-M');assert.notEqual(red.main_image,actual.data.main_image);
 for(const mutate of [a=>delete a.data.extra.attributes.main_product_image_locator,
  a=>delete a.data.items.find(row=>row.sku==='Parent-Red-M').extra.attributes.main_product_image_locator,
  a=>a.data.items.find(row=>row.sku==='Parent-Red-M').extra.attributes.main_product_image_locator[0].media_location=cover,
  a=>a.data.items.find(row=>row.sku==='Parent-Red-M').extra.attributes.main_product_image_locator[0].marketplace_id='USMARKET']){
  const changed=structuredClone(actual);mutate(changed);assert.throws(()=>verifyUkDraft(changed,record.preparedInput,f.urls,f.ui),/MAIN/);
 }
 const legacy=structuredClone(record.preparedInput);delete legacy.destination.requireMainImageLocator;
 const oldActual=structuredClone(actual);delete oldActual.data.extra.attributes.main_product_image_locator;for(const row of oldActual.data.items)delete row.extra.attributes.main_product_image_locator;
 assert.equal(verifyUkDraft(oldActual,legacy,f.urls,f.ui).length,2);
 await assert.rejects(()=>prepareUkDraft({},f.input,record,async()=>{}, {
  read:async()=>oldActual,ui:async()=>f.ui,prepare:async()=>assert.fail('do not prepare a saved draft again'),save:async()=>assert.fail('do not repeat unknown Save')
 }),/MAIN/);
});

test('missing or conflicting native UK template IDs block before validation or Save',async()=>{
 for(const alter of [f=>delete f.ui.shippingTemplateId,f=>f.prepared.destination.shippingTemplate.id='us-template']){
  const f=fixture();alter(f);let validates=0,saves=0;
  await assert.rejects(()=>prepareUkDraft({},f.input,{draftId:200,sourceEvidence:f.source,urls:f.urls},async()=>{}, {
   read:async()=>f.copied,prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),validate:()=>{validates++;},save:async()=>saves++
  }));
  assert.equal(validates,0);assert.equal(saves,0);
 }
});

test('schema errors persist their proof before any UK Save and uncertain saved failures remain read-only',async()=>{
 const fail=(meta,records)=>{const error=Error('isolated schema rejection');error.schemaValidation={passed:false,checkedCount:records.length,schemaHash:meta.hash,errors:[{id:records[0].id,path:'/unrecognized_flag'}]};throw error;};
 const first=fixture(),blocked={draftId:200,sourceEvidence:first.source,urls:first.urls};let firstSaves=0;
 await assert.rejects(()=>prepareUkDraft({},first.input,blocked,async()=>{}, {
  read:async()=>first.copied,prepare:async()=>({meta:first.meta,prepared:first.prepared,ui:first.ui}),validate:fail,save:async()=>firstSaves++
 }),/schema rejection/);
 assert.equal(firstSaves,0);assert.equal(blocked.schemaValidationBeforeSave.passed,false);assert.equal(blocked.saveIntendedAt,undefined);
 const f=fixture(),record={draftId:200,sourceEvidence:f.source,urls:f.urls};let saved,reads=0,saves=0,validates=0;
 const read=async()=>{if(++reads===1)return f.copied;const actual=persistedFrom(saved);actual.data.extra.attributes.unrecognized_flag=[{value:true}];return actual;};
 const validate=(meta,records)=>{validates++;if(validates===1)return mockSchemaValidation(meta,records);assert.deepEqual(records[0].attributes.unrecognized_flag,[{value:true}]);return fail(meta,records);};
 await assert.rejects(()=>prepareUkDraft({},f.input,record,async()=>{}, {
  read,prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),validate,
  save:async(_page,wire,urls,r,persist,patch)=>{saves++;saved=patch(f.body,wire,urls);r.saveIntendedAt='before-save';r.submitted=saved;await persist();},ui:async()=>f.ui
 }),/schema rejection/);
 assert.equal(saves,1);assert.equal(record.schemaValidationAfterSave.passed,false);assert.equal(record.phase,'uk_save_unknown');
 await assert.rejects(()=>prepareUkDraft({},f.input,record,async()=>{}, {
  read,ui:async()=>f.ui,validate,prepare:async()=>assert.fail('must not prepare again'),save:async()=>assert.fail('must not save again')
 }),/schema rejection/);
 assert.equal(saves,1);assert.equal(validates,3);
});

test('new US child metadata migrates locales while verified UK brand and theme replace their US forms',async()=>{
 const f=fixture(),properties=f.meta.schema_content.properties,property=properties=>({items:{properties}});
 f.input.ukTarget.brand='Actual UK Brand';properties.brand.items.properties.value.enum=['Actual UK Brand'];
 properties.list_price=property({currency:{type:'string',enum:['GBP']},value:{type:'number'},marketplace_id:{type:'string'}});
 properties.item_name=property({value:{type:'string'},language_tag:{type:'string'},marketplace_id:{type:'string'}});
 properties.parentage_level=property({value:{enum:['parent','child']},marketplace_id:{type:'string'}});
 properties.child_parent_sku_relationship=property({parent_sku:{type:'string'},child_relationship_type:{enum:['variation']},marketplace_id:{type:'string'}});
 const usMetadata={brand:[{value:'Actual US Brand',language_tag:'en_US',marketplace_id:'USMARKET'}],variation_theme:[{name:'COLOR/SIZE'}],
  list_price:[{currency:'USD',value:0,marketplace_id:'USMARKET'}],item_name:[{value:f.input.goods.title,language_tag:'en_US',marketplace_id:'USMARKET'}]};
 Object.assign(f.source.extra.attributes,structuredClone(usMetadata),{parentage_level:[{value:'parent',marketplace_id:'USMARKET'}]});
 for(const row of f.source.items)Object.assign(row.extra.attributes,structuredClone(usMetadata),{
  parentage_level:[{value:'child',marketplace_id:'USMARKET'}],child_parent_sku_relationship:[{parent_sku:'Parent',child_relationship_type:'variation',marketplace_id:'USMARKET'}]
 });
 f.prepared=makeUkInput(f.input,'200',f.meta);f.ui.brand='Actual UK Brand';const sourceBefore=structuredClone(f.source);
 const record={draftId:200,sourceEvidence:f.source,urls:f.urls};let saved,reads=0,saves=0;
 await prepareUkDraft({},f.input,record,async()=>{}, {
  validate:mockSchemaValidation,
  read:async()=>++reads===1?f.copied:persistedFrom(saved),prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),
  save:async(_page,wire,urls,r,persist,patch)=>{saves++;saved=patch(f.body,wire,urls);r.saveIntendedAt='before-save';r.submitted=saved;await persist();},
  ui:async()=>f.ui,remote:async(_url,a)=>({sha256:a.sha256,bytes:1})
 });
 assert.equal(saves,1);assert.equal(saved.brand,'Actual UK Brand');assert.equal(saved.variation_theme,'COLOR_NAME/SIZE_NAME');
 assert.deepEqual(saved.attributes.brand,[{value:'Actual UK Brand',language_tag:'en_GB',marketplace_id:'UKMARKET'}]);
 assert.equal(saved.attributes.variation_theme[0].name,saved.variation_theme);assert.equal(saved.attributes.list_price[0].currency,'GBP');
 assert.equal(saved.attributes.parentage_level[0].value,'parent');
 for(const row of saved.items){
  assert.equal(row.attributes.brand[0].value,'Actual UK Brand');assert.equal(row.attributes.variation_theme[0].name,saved.variation_theme);
  assert.equal(row.attributes.list_price[0].value,0);assert.equal(row.attributes.list_price[0].currency,'GBP');
  assert.equal(row.attributes.item_name[0].language_tag,'en_GB');assert.equal(row.attributes.item_name[0].marketplace_id,'UKMARKET');
  assert.equal(row.attributes.parentage_level[0].value,'child');assert.equal(row.attributes.parentage_level[0].marketplace_id,'UKMARKET');
  assert.equal(row.attributes.child_parent_sku_relationship[0].parent_sku,'Parent');assert.equal(row.attributes.child_parent_sku_relationship[0].marketplace_id,'UKMARKET');
 }
 assert.deepEqual(f.source,sourceBefore);
 const actual=persistedFrom(saved);assert.equal(verifyUkDraft(actual,record.preparedInput,f.urls,f.ui).length,2);
 for(const change of [a=>a.data.extra.attributes.brand[0].value='Actual US Brand',a=>a.data.extra.attributes.brand[0].language_tag='en_US',
  a=>a.data.extra.attributes.variation_theme[0].name='COLOR/SIZE',a=>delete a.data.items[0].extra.attributes.brand,
  a=>a.data.items[0].extra.attributes.brand[0].marketplace_id='USMARKET',a=>a.data.items[0].extra.attributes.variation_theme[0].name='COLOR/SIZE',
  a=>delete a.data.items[0].extra.attributes.variation_theme]){
  const altered=structuredClone(actual);change(altered);assert.throws(()=>verifyUkDraft(altered,record.preparedInput,f.urls,f.ui),/品牌|变体主题/);
 }
});

test('unknown Save is reconciled against original ID and never resubmitted',async()=>{
 const f=fixture(),p=f.prepared;p.destination.marketId='22';p.destination.shippingTemplate.id='uk-template';
 const exempt={...targetIdentityAttributes(p),supplier_declared_has_product_identifier_exemption:[{value:true}]};
 const wire={...f.input,ukPrepared:p,ukCopiedRows:restoreSkuMapping(f.copied.data.items,f.input,p.destination),ukParentAttributes:{...targetIdentityAttributes(p),supplier_declared_has_product_identifier_exemption:[{value:true}],fulfillment_availability:[{lead_time_to_ship_max_days:'4'}]},ukItemAttributes:{'Parent-Blue-M':exempt,'Parent-Blue-S':exempt}};
 const saved=patchUkDraftPayload(f.body,wire,f.urls),record={draftId:200,sourceEvidence:f.source,urls:f.urls,saveIntendedAt:'before_crash',preparedInput:p,schemaObservation:f.meta};let saves=0;
 const adapters={validate:mockSchemaValidation,read:async()=>persistedFrom(saved),ui:async()=>f.ui,save:async()=>saves++,remote:async(url,a)=>({sha256:a.sha256,bytes:1})};
 await prepareUkDraft({},f.input,record,async()=>{},adapters);assert.equal(record.phase,'uk_draft_verified');assert.equal(saves,0);
 record.phase='uk_save_unknown';record.preparedInput.goods.parentSku='wrong';await assert.rejects(()=>prepareUkDraft({},f.input,record,async()=>{},adapters));assert.equal(saves,0);
});

test('a crash after native Save recovers market/template from the durable request and readback',async()=>{
 const f=fixture(),record={draftId:200,sourceEvidence:f.source,urls:f.urls};let saved,saves=0;
 await assert.rejects(()=>prepareUkDraft({},f.input,record,async()=>{},
  {validate:mockSchemaValidation,read:async()=>f.copied,prepare:async()=>({meta:f.meta,prepared:f.prepared,ui:f.ui}),save:async(page,wire,urls,r,persist,patch)=>{saves++;saved=patch(f.body,wire,urls);r.saveIntendedAt='before-crash';r.submitted=saved;await persist();throw Error('connection lost after Save');}}),/connection lost/);
 assert.equal(record.preparedInput.destination.marketId,undefined);assert.equal(record.preparedInput.destination.shippingTemplate.id,'uk-template');
 // The native selected ID is now proven before Save. Retain recovery support
 // for an older frozen checkpoint that had only its durable Save request.
 delete record.preparedInput.destination.shippingTemplate.id;
 await prepareUkDraft({},f.input,record,async()=>{},
  {validate:mockSchemaValidation,read:async()=>persistedFrom(saved),ui:async()=>f.ui,prepare:async()=>assert.fail('must not prepare again'),save:async()=>assert.fail('must not save again'),remote:async(url,a)=>({sha256:a.sha256,bytes:1})});
 assert.equal(saves,1);assert.equal(record.phase,'uk_draft_verified');assert.equal(record.preparedInput.destination.marketId,'22');assert.equal(record.preparedInput.destination.shippingTemplate.id,'uk-template');
});

test('unverifiable copied source, ambiguous variants and missing UK facts stop before Save',async()=>{
 for(const mutate of [f=>f.source.sku='other',f=>f.copied.data.uid=999,f=>f.source.items[0].sku='other',f=>f.copied.data.items[0].main_image='https://different.test/p.png',f=>f.meta.schema_content.properties={...f.meta.schema_content.properties,color:undefined}]){
  const f=fixture();mutate(f);let saves=0;const r={draftId:200,sourceEvidence:f.source,urls:f.urls};
  await assert.rejects(()=>prepareUkDraft({},f.input,r,async()=>{},{validate:mockSchemaValidation,read:async()=>f.copied,prepare:async()=>({meta:f.meta,prepared:makeUkInput(f.input,200,f.meta),ui:f.ui}),save:async()=>saves++}));assert.equal(saves,0);
 }
});
