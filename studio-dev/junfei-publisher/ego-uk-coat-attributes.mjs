// Source-backed coat fields and an explicitly frozen seller catalogue setting.
export function supplementUkCoat(attributes,input,meta,prepared,categoryChoice){
 const result=structuredClone(attributes),evidence={},target=prepared?.destination;
 const schema=typeof meta.schema_content==='string'?JSON.parse(meta.schema_content):meta.schema_content;
 if(meta.product_type_name!=='COAT'||meta.country_code!=='GB'||meta.locale!=='en_GB'||!meta.hash||
    target?.countryCode!=='GB'||target.languageTag!=='en_GB'||schema?.$defs?.marketplace_id?.default!==target.marketplaceId)return{attributes:result,evidence};
 const facts=input.usPreparation?.coatFacts,choice=input.ukPreparation?.coatWeave;
 const description=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n');
 const material=[...description.matchAll(/^Material:[ \t]*([^\r\n]+)$/gm)];
 const norm=v=>String(v||'').toLowerCase().replace(/[^a-z]/g,'');
 const path='Fashion Women Clothing Coats Jackets & Gilets Jackets';
 if(facts?.source!=='bound_supplier_catalogue_observation'||facts.productId!==input.productId||facts.sourceUrl!==input.goods?.sourceUrl||
    !facts.observation?.sha256||material.length!==1||material[0][1].trim().toLowerCase()!=='100% polyester'||
    !input.goods.manufacturer||norm(categoryChoice?.text)!==norm(path)||norm(target.categoryHints?.path)!==norm(path))return{attributes:result,evidence};
 const props=schema.properties,loc=value=>({value,language_tag:target.languageTag,marketplace_id:target.marketplaceId});
 const attrs={item_type_name:[loc('Fleece Jacket')],manufacturer:[loc(input.goods.manufacturer)],
  outer:[{material:[{value:material[0][1].trim(),language_tag:target.languageTag}],marketplace_id:target.marketplaceId}]};
 const values=props?.weave_type?.items?.properties?.value, enums=values?.enum??values?.anyOf?.flatMap(v=>v.enum??[])??[];
 if(choice?.source==='user_configured_defaults'&&choice.productId===input.productId&&choice.supplierVerified===false&&
    choice.scope==='missing_catalogue_attribute_only'&&choice.value==='Plain'&&choice.schemaHash===meta.hash&&
    typeof choice.instruction==='string'&&choice.instruction.trim()&&choice.configuredAt&&enums.includes(choice.value))attrs.weave_type=[loc(choice.value)];
 for(const [key,value]of Object.entries(attrs))if(!Object.hasOwn(result,key)&&props?.[key]){
  result[key]=value;evidence[key]=key==='weave_type'?structuredClone(choice):{
   source:key==='item_type_name'?'verified_category_mapping':'frozen_original_product_facts',value:structuredClone(value),humanReviewed:false};
 }
 return{attributes:result,evidence};
}
