// Same-source catalogue observation, not guessed sleeve construction or dimensions.
export function coatProductAttributes(input,meta){
 if(meta.product_type_name!=='COAT'||!input.usPreparation?.coatFacts)return{};
 const e=input.usPreparation.coatFacts,source=input.goods?.sourceUrl;
 const schema=typeof meta.schema_content==='string'?JSON.parse(meta.schema_content):meta.schema_content;
 const market=input.destination.marketplaceId,language=input.destination.languageTag;
 const raglan=e.sleeve?.value==='Raglan Sleeve'&&e.sleeve.sourceValue==='插肩袖';
 const lantern=e.sleeve?.value==='Lantern Sleeve'&&e.sleeve.sourceValue==='灯笼袖';
 if(e.source!=='bound_supplier_catalogue_observation'||e.productId!==input.productId||e.sourceUrl!==source||
    e.humanReviewed!==false||!/^https:\/\/detail\.1688\.com\/offer\/\d+\.html$/.test(source)||
    !/^[a-f0-9]{64}$/.test(e.observation?.sha256||'')||!e.observation?.observedAt||
    e.closure?.value!=='Zipper'||e.closure.sourceValue!=='拉链'||
    !raglan&&!lantern||
    e.sleeve.length!=='long_sleeve'||e.sleeve.sourceLength!=='长袖'||
    e.itemLength?.value!=='Standard Length'||!e.itemLength.sourceValue?.startsWith('普通款(')||
    e.dangerousGoods?.value!=='not_applicable'||e.dangerousGoods.source!=='inferred_workbench_classification'||
    e.dangerousGoods.supplierVerified!==false||e.dangerousGoods.basis!=='ordinary_apparel_100_percent_polyester'||
    input.publicationFacts?.waterResistanceLevelSource?.basis?.classification!=='ordinary_apparel')throw Error('外套属性缺少冻结的同款真实货源依据');
 const desc=String(input.goods.description).replace(/<br\s*\/?\s*>/gi,'\n');
 const line=label=>{const rows=desc.split('\n').filter(x=>x.startsWith(label+':'));return rows.length===1?rows[0].slice(label.length+1).trim():'';};
 const textMatches=raglan?
  e.closure.frozenLineLabel==='Front'&&line('Front')===e.closure.frozenLine&&/^Full zipper(?:; chevron quilting)?$/i.test(line('Front'))&&
   line('Sleeves')===e.sleeve.frozenLine&&/^Smooth raglan long sleeves; plain straight openings$/i.test(line('Sleeves'))&&
   /^Fitted padded jacket$/i.test(line('Style'))&&e.style?.value===line('Style')&&e.style.source==='frozen_listing'&&e.style.supplierVerified===false:
  line('Closure')===e.closure.frozenLine&&/^Front half zipper(?: with a long red pull)?$/i.test(line('Closure'))&&/\blong sleeves\b/i.test(line('Style'));
 if(!/^100% polyester$/i.test(line('Material'))||!textMatches)throw Error('外套属性与原冻结文案冲突');
 const permits=(definition,value)=>(definition?.enum??definition?.anyOf?.flatMap(b=>b.enum??[])??[]).includes(value);
 const nested=(field,key,value,translated)=>{
  const p=schema.properties?.[field]?.items?.properties,v=p?.[key]?.items?.properties;
  if(!p?.marketplace_id||!permits(v?.value,value)||translated&&!v.language_tag)throw Error('实际COAT schema不支持 '+field+'.'+key);
  return{[key]:[{value,...(translated?{language_tag:language}:{})}],marketplace_id:market};
 };
 const localized=(field,value)=>{
  const p=schema.properties?.[field]?.items?.properties;
  if(!p?.marketplace_id||!permits(p.value,value))throw Error('实际COAT schema不支持 '+field);
  return{value,...(p.language_tag?{language_tag:language}:{}),marketplace_id:market};
 };
 const sleeve=nested('sleeve','type',e.sleeve.value,true);
 const length=nested('sleeve','length_description',e.sleeve.length,false);sleeve.length_description=length.length_description;
 const attributes={closure:[nested('closure','type',e.closure.value,true)],sleeve:[sleeve],
        item_length_description:[localized('item_length_description',e.itemLength.value)],
        supplier_declared_dg_hz_regulation:[localized('supplier_declared_dg_hz_regulation',e.dangerousGoods.value)]};
 if(raglan){
  const p=schema.properties?.style?.items?.properties,v=p?.value,style=line('Style');
  if(!p?.marketplace_id||!p?.language_tag||v?.type!=='string'||
     (v.enum&&!v.enum.includes(style))||style.length<(v.minLength??1)||style.length>(v.maxLength??Infinity)||
     new TextEncoder().encode(style).length>(v.maxUtf8ByteLength??Infinity))throw Error('实际COAT schema不支持 style');
  attributes.style=[{value:style,language_tag:language,marketplace_id:market}];
 }
 return attributes;
}
