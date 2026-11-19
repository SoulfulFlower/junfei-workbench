import test from 'node:test';
import assert from 'node:assert/strict';
import {schemaVariation} from './ego-collection-prepare.mjs';
import {patchDraftPayload} from './ego-finished-collection.mjs';
import {verifyPersistedDraft} from './ego-draft-readback.mjs';

function meta(){
 // The PANTS field names and theme were observed in the original native
 // receipt (US/fa4f0d17e14ab5bf). Enums below are controlled test values,
 // not a substitute for the complete schema read by the real workflow.
 return {country_code:'US',locale:'en_US',product_type_name:'PANTS',hash:'test-pants-schema',schema_content:{properties:{
  color:{items:{properties:{value:{type:'string'},language_tag:{type:'string'},marketplace_id:{type:'string'}}}},
  bottoms_size:{items:{required:['size_class','size_system'],properties:{
   size:{type:'string',enum:['s','m','l','x_l'],enumNames:['S','M','L','XL']},
   size_to:{type:'string'},body_type:{type:'string',enum:['regular','plus']},
   size_class:{type:'string',enum:['alpha']},waist_size:{type:'string'},height_type:{type:'string'},
   inseam_size:{type:'string'},size_system:{type:'string',enum:['test-us-system']},marketplace_id:{type:'string'}
  }}},variation_theme:{items:{properties:{name:{enum:['COLOR_NAME/SIZE_NAME']}}}}
 }}};
}

const sizes=['S','M','L','XL'];
function fixture(){
 const assets=Array.from({length:7},(_,slot)=>({sha256:String(slot).padStart(64,'0')}));
 const urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/test/'+i+'.png']));
 const input={mode:'draft',store:'Test US',marketplace:'US',masterColor:'Silver',handlingDays:3,assets,
  goods:{parentSku:'TEST-PANTS',title:'Silver pants',description:'Verified description',bullets:['one','two','three','four','five'],terms:'pants',highlights:'Side pockets',brand:'Test',manufacturer:'Test'},
  goodsItems:sizes.map(size=>({sku:'TEST-PANTS-'+size,color:'Silver',size,price:'27.98',quantity:88,imageIndices:[0,1,2,3,4,5,6]})),
  destination:{draftId:'123',marketId:'45',marketplaceId:'TESTMARKET',...schemaVariation(meta(),sizes.map(size=>({size})))}};
 const body={id:123,market_id:'45',country_code:'US',parent_sku:'TEST-PANTS',items:input.goodsItems.map((v,i)=>({id:500+i,sku:v.sku,standard_product_id:null,standard_product_type:null}))};
 return {input,body,urls};
}

test('observed PANTS bottoms_size path resolves four labels using only supported size themes',()=>{
 for(const theme of ['COLOR_NAME/SIZE_NAME','COLOR/SIZE','SIZE_NAME/COLOR_NAME','SIZE/COLOR']){
  const m=meta();m.schema_content.properties.variation_theme.items.properties.name.enum=[theme];
  const result=schemaVariation(m,sizes.map(size=>({size})));
  assert.deepEqual(result.variationFields,{color:'color.0.value',size:'bottoms_size.0.size'});
  assert.deepEqual(result.sizeValues,{S:'s',M:'m',L:'l',XL:'x_l'});
  assert.equal(result.themeValue,theme);assert.equal(result.sizeAttributeSchema.field,'bottoms_size');
  assert.deepEqual(result.sizeAttributes,{size_system:'test-us-system',size_class:'alpha'});
  assert.equal(result.sizeAttributeSchema.properties.body_type,undefined);
 }
 const serialized=meta();serialized.schema_content=JSON.stringify(serialized.schema_content);
 assert.equal(schemaVariation(serialized,[{size:'XL'}]).sizeValues.XL,'x_l');
});

test('bottoms size mapping rejects unsupported labels, missing fields and unproven required metadata',()=>{
 assert.throws(()=>schemaVariation(meta(),[{size:'XXL'}]),/尺码枚举/);
 for(const mutate of [
  m=>delete m.schema_content.properties.bottoms_size.items.properties.size,
  m=>m.schema_content.properties.bottoms_size.items.required.push('body_type'),
  m=>m.schema_content.properties.bottoms_size.items.properties.size_system.enum.push('another-system'),
  m=>m.schema_content.properties.variation_theme.items.properties.name.enum=['COLOR/SIZE/STYLE']
 ]){const m=meta();mutate(m);assert.throws(()=>schemaVariation(m,[{size:'S'}]),/不支持当前产品|必填尺码|尺码体系|未提供可用/);}
});

test('serialized native save and persisted readback keep bottoms_size for every original child and seven ordered images',()=>{
 const {input,body,urls}=fixture();
 const patch=(0,eval)('('+patchDraftPayload.toString()+')'),saved=patch(body,input,urls);
 for(const [i,row]of saved.items.entries()){
  assert.equal(row.id,body.items[i].id);assert.equal(row.sku,input.goodsItems[i].sku);
  assert.equal(row.variation['bottoms_size.0.size'],input.destination.sizeValues[sizes[i]]);
  assert.deepEqual(row.attributes.bottoms_size[0],{size:input.destination.sizeValues[sizes[i]],marketplace_id:'TESTMARKET',size_system:'test-us-system',size_class:'alpha'});
  assert.equal(row.attributes.apparel_size,undefined);assert.equal(row.attributes.shirt_size,undefined);
  assert.deepEqual(row.images,input.assets.map(a=>urls[a.sha256]));assert.equal(row.price,'27.98');assert.equal(row.quantity,'88');
  assert.equal(row.standard_product_id,null);assert.equal(row.standard_product_type,null);
 }
 assert.deepEqual(saved.images,[saved.main_image]);assert.equal(saved.publish,false);assert.equal(saved.with_publish,false);
 const actual={code:0,data:{...saved,sku:saved.parent_sku,market:{alias:input.store},extra:{images:saved.images,product_description:saved.product_description,bullet_point:saved.bullet_point,keywords:saved.keywords},items:saved.items.map(row=>({...row,pid:saved.id,extra:{images:row.images,attributes:row.attributes}}))}};
 assert.equal(verifyPersistedDraft(actual,input,urls).length,4);
 for(const mutate of [
  a=>a.data.items[0].variation['bottoms_size.0.size']='m',
  a=>delete a.data.items[0].extra.attributes.bottoms_size,
  a=>a.data.items[0].extra.attributes.bottoms_size[0].size_system='foreign',
  a=>a.data.items[0].extra.images.reverse()
 ]){const changed=structuredClone(actual);mutate(changed);assert.throws(()=>verifyPersistedDraft(changed,input,urls),/变体字段|必填尺码属性|七图顺序/);}
});
