import test from 'node:test';
import assert from 'node:assert/strict';
import {supplementUkRequiredAttributes} from './ego-uk-draft.mjs';

// Independent excerpts of the observed GB SHIRT schema 21fe010c36a58982.
// Collar, item type, outer and weave accept free strings; water is a strict enum.
function fixture(){
 const localized=value=>({items:{properties:{value,language_tag:{$ref:'#/$defs/language_tag'},marketplace_id:{$ref:'#/$defs/marketplace_id'}}}});
 const input={productId:'original-shirt',sha256:'original-snapshot',goods:{manufacturer:'Generic',description:"Women's Ribbed Long Sleeve Top\nStyle: Solid-color fitted pullover\nNeckline: Crew neck\nTexture: Fine ribbed\nMaterial: 95% Polyester, 5% Elastane"},destination:{categoryHints:{path:'Clothing, Shoes & Jewelry > Women > Clothing > Tops, Tees & Blouses > T-Shirts'}}};
 const prepared={destination:{countryCode:'GB',languageTag:'en_GB',marketplaceId:'A1F83G8C2ARO7P',categoryHints:{path:'Fashion Women Clothing Tops T-Shirts & Blouses T-Shirts'}}};
 const open={type:'string',anyOf:[{type:'string'},{type:'string',enum:['An unrelated suggested value']}]};
 const meta={country_code:'GB',locale:'en_GB',product_type_name:'SHIRT',hash:'21fe010c36a58982',schema_content:{$defs:{marketplace_id:{type:'string'},language_tag:{type:'string'}},properties:{
  manufacturer:localized({type:'string',maxLength:100}),collar_style:localized(structuredClone(open)),item_type_name:localized(structuredClone(open)),weave_type:localized(structuredClone(open)),
  outer:{items:{properties:{material:localized(structuredClone(open)),marketplace_id:{$ref:'#/$defs/marketplace_id'}}}},
  water_resistance_level:{items:{properties:{value:{type:'string',enum:['moisture_resistant','not_water_resistant','water_repellent','water_resistant','waterproof']},marketplace_id:{$ref:'#/$defs/marketplace_id'}}}}
 }}};
 // Exact T-shirt branch from the observed schema's allOf[6] else-chain.
 const condition={required:['shirt_form_type'],properties:{shirt_form_type:{contains:{required:['value'],properties:{value:{enum:['t_shirt']}}}}}};
 const consequence={properties:{collar_style:{items:{properties:{value:{enum:['Collarless']}}}}}};
 meta.schema_content.allOf=[{if:condition,then:consequence}];
 return{input,prepared,meta};
}

test('missing explicit water preserves five exact source evidence entries and never invents a default',()=>{
 const f=fixture(),before=structuredClone(f.input);
 assert.throws(()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared),error=>{
  assert.equal(error.ukMissingRequiredAttribute,'water_resistance_level');
  assert.equal(error.ukRequiredAttributeEvidence.manufacturer.value,'Generic');
  assert.equal(error.ukRequiredAttributeEvidence.collar_style.value,'Collarless');assert.equal(error.ukRequiredAttributeEvidence.collar_style.inferred,true);
  assert.equal(error.ukRequiredAttributeEvidence.item_type_name.value,'T-Shirt');
  assert.equal(error.ukRequiredAttributeEvidence['outer.material'].value,'95% Polyester, 5% Elastane');
  assert.equal(error.ukRequiredAttributeEvidence.weave_type.value,'Ribbed');
  assert.match(error.message,/不默认/);return true;
 });
 assert.deepEqual(f.input,before);
});

test('explicit water permits source-backed GB attributes while keeping all basis outside Amazon values',()=>{
 const f=fixture();f.input.ukPreparation={waterResistanceLevel:'not_water_resistant'};
 const original={care_instructions:[{value:'Machine Wash',language_tag:'en_GB',marketplace_id:'A1F83G8C2ARO7P'}]},before=structuredClone(original);
 const {attributes,evidence}=supplementUkRequiredAttributes(original,f.input,f.meta,f.prepared);
 assert.deepEqual(attributes.collar_style,[{value:'Collarless',language_tag:'en_GB',marketplace_id:'A1F83G8C2ARO7P'}]);
 assert.deepEqual(attributes.outer,[{material:[{value:'95% Polyester, 5% Elastane',language_tag:'en_GB'}],marketplace_id:'A1F83G8C2ARO7P'}]);
 assert.equal(attributes.weave_type[0].value,'Ribbed');assert.equal(attributes.manufacturer[0].value,'Generic');assert.equal(attributes.item_type_name[0].value,'T-Shirt');
 assert.deepEqual(attributes.water_resistance_level,[{value:'not_water_resistant',marketplace_id:'A1F83G8C2ARO7P'}]);
 assert.equal(evidence.water_resistance_level.source,'explicit_publication_amendment');assert.equal(evidence.weave_type.sourceValue,'Fine ribbed');
 assert.equal(JSON.stringify(attributes).includes('sourceValue'),false);assert.equal(JSON.stringify(attributes).includes('Knit'),false);assert.deepEqual(original,before);
});

test('future frozen publication facts carry water provenance and a specific amendment takes precedence',()=>{
 const f=fixture();f.input.publicationFacts={waterResistanceLevel:'water_resistant',waterResistanceLevelSource:{source:'explicit_supplier_record'}};
 let result=supplementUkRequiredAttributes({},f.input,f.meta,f.prepared);
 assert.equal(result.attributes.water_resistance_level[0].value,'water_resistant');assert.deepEqual(result.evidence.water_resistance_level.basis,{source:'explicit_supplier_record'});
 f.input.ukPreparation={waterResistanceLevel:'not_water_resistant'};result=supplementUkRequiredAttributes({},f.input,f.meta,f.prepared);
 assert.equal(result.attributes.water_resistance_level[0].value,'not_water_resistant');assert.equal(result.evidence.water_resistance_level.path,'ukPreparation.waterResistanceLevel');
});

test('ambiguous descriptions missing facts and unrelated categories fail instead of manufacturing attributes',()=>{
 for(const alter of [f=>f.input.goods.manufacturer='',f=>f.input.goods.description+='\nNeckline: Crew neck',
  f=>f.input.goods.description=f.input.goods.description.replace('Crew neck','V neck'),
  f=>f.input.goods.description=f.input.goods.description.replace('Style: Solid-color fitted pullover\n',''),
  f=>f.input.goods.description+='\nCollar: Stand collar',f=>f.input.goods.description+='\nCollar: Turn-down collar',
  f=>f.input.goods.description+='\nStyle: Polo shirt',f=>delete f.meta.schema_content.allOf,
  f=>f.input.goods.description+='\nMaterial: Other',f=>f.input.goods.description=f.input.goods.description.replace('Fine ribbed','Knit'),
  f=>f.input.destination.categoryHints.path='Clothing > Blouses',f=>f.prepared.destination.categoryHints.path='Fashion Tops T-Shirts & Blouses']){
  const f=fixture();f.input.ukPreparation={waterResistanceLevel:'not_water_resistant'};alter(f);assert.throws(()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared),/明确依据/);
 }
});

test('water accepts only an explicit exact schema value and will not overwrite a conflicting source attribute',()=>{
 for(const water of ['',null,'Not Water Resistant',true,'unknown']){
  const f=fixture();f.input.ukPreparation={waterResistanceLevel:water};assert.throws(()=>supplementUkRequiredAttributes({},f.input,f.meta,f.prepared),/防水/);
 }
 const f=fixture();f.input.ukPreparation={waterResistanceLevel:'not_water_resistant'};
 assert.throws(()=>supplementUkRequiredAttributes({water_resistance_level:[{value:'waterproof',marketplace_id:'A1F83G8C2ARO7P'}]},f.input,f.meta,f.prepared),/冲突/);
});

test('existing migrated source facts are preserved and non-SHIRT schemas retain their prior behavior',()=>{
 const f=fixture();f.input.ukPreparation={waterResistanceLevel:'not_water_resistant'};
 const original={manufacturer:[{value:'Known Maker'}],collar_style:[{value:'Ribbed Collar'}],item_type_name:[{value:'Existing Item'}],outer:[{material:[{value:'Original material'}]}],weave_type:[{value:'Original weave'}]},before=structuredClone(original);
 const result=supplementUkRequiredAttributes(original,f.input,f.meta,f.prepared);
 for(const key of Object.keys(original)){assert.deepEqual(result.attributes[key],original[key]);assert.equal(result.evidence[key].source,'original_migrated_attribute');}
 assert.deepEqual(original,before);f.meta.product_type_name='COAT';delete f.input.ukPreparation;
 assert.deepEqual(supplementUkRequiredAttributes(original,f.input,f.meta,f.prepared),{attributes:original,evidence:{}});
});
