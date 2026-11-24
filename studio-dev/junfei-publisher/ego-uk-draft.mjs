// Prepare an existing native copy. No upload, copy, exemption application or
// publish occurs here. All writes use the ERP's observed json-update Save.
import {schemaVariation,chooseCategory,resolveCategoryHints,sameCategoryPath,requestRecommendationsForSourceTitle} from './ego-collection-prepare.mjs';
import {saveDraft} from './ego-draft-save.mjs';
import {readPersistedDraft,verifyPersistedDraft,assertMainImageLocatorSchema} from './ego-draft-readback.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';
import {ensureUkBrandExemption} from './ego-uk-exemption.mjs';
import {supplementUkCoat} from './ego-uk-coat-attributes.mjs';

const clone=x=>JSON.parse(JSON.stringify(x));
const present=x=>typeof x==='string'&&x.length>0;
const amount=x=>typeof x!=='boolean'&&/^\d+(?:\.\d{1,2})?$/.test(String(x))&&Number(x)>0&&Number(x)<10000000;
const integer=x=>typeof x!=='boolean'&&/^\d+$/.test(String(x))&&Number.isSafeInteger(Number(x));
const materialEvidenceSource='original_migrated_fabric_type';
function preparationTarget(input){const override=input.ukPreparation?.shippingTemplate;if(override&&(!present(override.name)||Object.keys(override).some(k=>k!=='name')))throw Error('英国实际运输模板修订无效');return {...input.ukTarget,...(override?{shippingTemplate:override}:{})};}

export function validateUkInputs(input){
 const t=input.ukTarget,c=input.ukCommerce,source=input.destination;
 if(input.marketplace!=='US'||!input.goods?.parentSku||!input.goodsItems?.length||!source)throw Error('缺少本款美国正式快照');
 if(!t||!present(t.id||t.destinationId)||!present(t.storeName)||t.storeName===input.store||t.countryCode!=='GB'||t.currency!=='GBP'||t.languageTag!=='en_GB')throw Error('英国目标连接编号、店铺、站点或币种不完整');
 if((t.id||t.destinationId)===source.destinationId)throw Error('英国必须使用独立目标连接编号');
 if(!present(t.shippingTemplate?.name))throw Error('缺少英国实际运输模板名称');
 if((t.marketId&&String(t.marketId)===String(source.marketId))||(t.marketplaceId&&t.marketplaceId===source.marketplaceId))throw Error('英国不能继承美国站点编号');
 if(!c||c.currency!=='GBP'||!integer(c.handlingDays)||Number(c.handlingDays)>30||!c.pricingBasis||c.pricingBasis.currency!=='GBP')throw Error('缺少本款英国GBP定价依据或处理时间');
 const skus=input.goodsItems.map(v=>v.sku);
 if(skus.some(s=>!present(s))||new Set(skus).size!==skus.length||skus.includes(input.goods.parentSku))throw Error('美国原父子SKU无效');
 for(const v of input.goodsItems){
  if(!present(v.color)||!present(v.size)||!amount(c.variantPrices?.[v.sku])||!integer(c.quantities?.[v.sku]))throw Error('英国逐SKU价格、库存或颜色尺码不完整：'+v.sku);
  if(v.imageIndices?.length!==7||new Set(v.imageIndices).size!==7)throw Error('原逐SKU七图映射不完整：'+v.sku);
 }
 return true;
}

function schemaObject(meta){return typeof meta.schema_content==='string'?JSON.parse(meta.schema_content):meta.schema_content;}
export function resolveUkSchema(meta,input){
 const t=input.ukTarget,schema=schemaObject(meta),marketplaceId=schema?.$defs?.marketplace_id?.default;
 if(meta.country_code!=='GB'||meta.locale!=='en_GB'||!present(marketplaceId)||marketplaceId===input.destination.marketplaceId||!meta.hash)throw Error('未取得真实英国类目schema');
 if(t.marketplaceId&&t.marketplaceId!==marketplaceId)throw Error('英国schema与配置Amazon站点编号不符');
 assertMainImageLocatorSchema(meta,marketplaceId);
 return {...schemaVariation(meta,input.goodsItems),marketplaceId,countryCode:'GB',languageTag:'en_GB',currency:'GBP',requireMainImageLocator:true};
}

function rawValue(row,field){
 if(Object.hasOwn(row.variation||{},field))return row.variation[field];
 const [name,index,key]=field.split('.');return (row.extra?.attributes||row.attributes)?.[name]?.[Number(index)]?.[key];
}

// Identifiers are source facts. A native copy/editor default is not a new GTIN.
export function extractSourceIdentifiers(source){
 const read=row=>{const out={};for(const key of ['standard_product_type','standard_product_id']){
  if(!Object.hasOwn(row,key)||(row[key]!==null&&(typeof row[key]!=='string'||!row[key].trim()||row[key].length>100||/[\r\n\0]/.test(row[key]))))throw Error('美国来源商品编码/type未完整回读');out[key]=row[key];
 }return out;};
 if(source?.country_code!=='US'||!source.sku||!Array.isArray(source.items)||!source.items.length||new Set(source.items.map(r=>r.sku)).size!==source.items.length)throw Error('原美国商品编码来源身份不完整');
 return{countryCode:'US',sourceId:String(source.id),parentSku:source.sku,parent:read(source),children:Object.fromEntries(source.items.map(row=>[row.sku,read(row)]))};
}

// Only actual color/size values identify copied rows. Native copy may reorder
// rows and regenerate every SKU; neither generated suffixes nor row positions
// carry the source identity.
export function restoreSkuMapping(rows,input,target){
 if(!Array.isArray(rows)||rows.length!==input.goodsItems.length||rows.some(r=>!/^\d+$/.test(String(r.id))||Number(r.id)<=0)||new Set(rows.map(r=>String(r.id))).size!==rows.length)throw Error('复制后的子体数量或ERP子体ID不符');
 const source=input.destination,fields=target.variationFields,sourceFields=source.variationFields||{color:'color.0.value',size:'apparel_size.0.size'};
 const seen=new Set();
 return rows.map(row=>{
  const color=rawValue(row,fields.color)??rawValue(row,sourceFields.color),size=rawValue(row,fields.size)??rawValue(row,sourceFields.size);
  const candidates=input.goodsItems.filter(v=>v.color===color&&new Set([v.size,source.sizeValues?.[v.size],target.sizeValues?.[v.size]].filter(x=>x!==undefined)).has(size));
  if(candidates.length!==1||seen.has(candidates[0].sku))throw Error('复制子体颜色尺码无法唯一对应原SKU：'+String(color)+' / '+String(size));
  const v=candidates[0];seen.add(v.sku);return{...row,sku:v.sku,variation:{[fields.color]:v.color,[fields.size]:target.sizeValues[v.size]}};
 });
}

export function makeUkInput(input,draftId,meta){
 validateUkInputs(input);if(!/^\d+$/.test(String(draftId)))throw Error('缺少原复制草稿编号');
 const resolved=resolveUkSchema(meta,input),t=preparationTarget(input),c=input.ukCommerce;
 const destination={};
 // Browser and ERP login identity may be shared; an ERP market ID cannot.
 for(const k of ['browserBinding','page','storeId','storeName','seller','erpAccount','erpAccountId','erpUserId','baseUrl','workbenchUrl','purchaseCny'])if(input.destination[k]!==undefined)destination[k]=input.destination[k];
 Object.assign(destination,resolved,{draftId:String(draftId),storeName:t.storeName,shippingTemplate:clone(t.shippingTemplate),categoryHints:resolveCategoryHints(t.categoryHints,input.categoryHints,input.destination.categoryHints)});
 destination.destinationId=t.id||t.destinationId;
 for(const k of ['marketId','erpAccountId','erpUserId'])if(t[k]!==undefined)destination[k]=t[k];
 const prepared={...clone(input),store:t.storeName,marketplace:'UK',mode:'draft',destination,
  goods:{...clone(input.goods),brand:t.brand||input.goods.brand},
  goodsItems:input.goodsItems.map(v=>({...clone(v),price:String(c.variantPrices[v.sku]),quantity:Number(c.quantities[v.sku])})),
  handlingDays:Number(c.handlingDays),pricingBasis:clone(c.pricingBasis)};
 if(!prepared.goods.brand)throw Error('缺少实际适用品牌，不能自动采用Generic');
 return prepared;
}

// Preserve proven source product facts, while revalidating them against UK
// enums. Locale/market IDs, the actual size-system singleton and a schema-
// supported zero list-price sentinel migrate; positive prices never convert.
export function migrateAttributes(attributes,meta,source,target){
 const schema=schemaObject(meta),props=schema.properties,result={};
 const resolve=definition=>definition?.$ref?.startsWith('#/$defs/')?schema.$defs?.[definition.$ref.slice(8)]:definition;
 const walk=(value,definition,path)=>{
  definition=resolve(definition);
  if(Array.isArray(value)){if(!definition?.items)throw Error('英国schema不支持原属性 '+path);return value.map((v,i)=>walk(v,definition.items,path+'.'+i));}
  if(value&&typeof value==='object'){
   const out={};for(const [key,v]of Object.entries(value)){
    if(key==='marketplace_id'){out[key]=target.marketplaceId;continue;}
    if(key==='language_tag'){out[key]=target.languageTag;continue;}
    const def=resolve(definition?.properties?.[key]);if(!def)throw Error('英国schema缺少原属性 '+path+'.'+key);
    if(key==='currency'&&/^list_price\.\d+$/.test(path)&&v==='USD'&&target.currency==='GBP'){
     if(value.value!==0)throw Error('美国正数或未核实参考价不能直接换为英国货币');
     if(!def.enum?.includes('GBP'))throw Error('英国实际schema未支持GBP参考价货币');
     out[key]='GBP';continue;
    }
    if(key==='size_system'&&def.enum&&!def.enum.includes(v)&&def.enum.length===1){out[key]=def.enum[0];continue;}
    out[key]=walk(v,def,path+'.'+key);
   }return out;
  }
  if(definition?.enum&&!definition.enum.includes(value)){
   const canonical=typeof value==='string'?definition.enum.filter(v=>typeof v==='string'&&v.toLowerCase()===value.toLowerCase()):[];
   if(canonical.length===1)return canonical[0];
   throw Error('原属性不在英国schema枚举内 '+path+'：'+value);
  }
  return value;
 };
 for(const [key,value]of Object.entries(attributes||{})){
  if(['merchant_shipping_group','fulfillment_availability','supplier_declared_has_product_identifier_exemption','externally_assigned_product_identifier'].includes(key))continue;
  // GB SKIRT omits the US department field; retain the same explicit female
  // classification through its supported target_gender instead.
  if(key==='department'&&!props?.department&&meta.product_type_name==='SKIRT'&&meta.country_code==='GB'&&
     source.countryCode==='US'&&target.countryCode==='GB'&&props?.target_gender&&
     Array.isArray(value)&&value.length===1&&value[0]?.value==='Womens'&&
     attributes.target_gender?.length===1&&attributes.target_gender[0]?.value==='female')continue;
  if(!props?.[key])throw Error('英国schema不支持原商品属性 '+key);
  if(key==='list_price'&&props[key].items?.properties?.value_with_tax){
   const item=props[key].items,fields=item.properties,amount=resolve(fields.value_with_tax),currency=resolve(fields.currency);
   if(source.countryCode!=='US'||source.currency!=='USD'||target.countryCode!=='GB'||target.currency!=='GBP'||
      !target.marketplaceId||target.marketplaceId===source.marketplaceId||fields.value||item.additionalProperties!==false||
      !item.required?.includes('currency')||!item.required.includes('value_with_tax')||amount?.type!=='number'||amount.minimum!==0||
      !/unable\s+to\s+provide[\s\S]*\benter\s+0\b/i.test(amount.description||'')||
      !Array.isArray(currency?.enum)||currency.enum.length!==1||currency.enum[0]!=='GBP')throw Error('英国真实schema未提供唯一GBP及明确允许未知值0的含税参考价字段');
   if(!Array.isArray(value)||value.length!==1||!value[0]||typeof value[0]!=='object'||Array.isArray(value[0])||
      value[0].currency!=='USD'||value[0].value!==0||!Object.hasOwn(value[0],'value')||
      Object.keys(value[0]).some(field=>!['currency','value','marketplace_id'].includes(field))||
      (value[0].marketplace_id!==undefined&&value[0].marketplace_id!==source.marketplaceId))throw Error('仅可迁移已核实美国零参考价，不能换算正数、未知或不完整参考价');
   result[key]=walk([{currency:'GBP',value_with_tax:0,marketplace_id:target.marketplaceId}],props[key],key);
  }else result[key]=walk(value,props[key],key);
 }
 return result;
}

function supplementUkMaterial(attributes,evidence,schema,target,resolve){
 if(Object.hasOwn(attributes,'material')||!schema.properties?.fabric_type)return;
 const fabric=attributes.fabric_type;
 if(!Array.isArray(fabric)||fabric.length!==1||typeof fabric[0]?.value!=='string')return;
 const sourceValue=fabric[0].value;
 const material=resolve(schema.properties.material),fields=resolve(material?.items)?.properties;
 const definition=resolve(fields?.value);
 if(material?.type!=='array'||!fields?.language_tag||!fields.marketplace_id||definition?.type!=='string')return;
 const values=[...new Set(definition.enum??(definition.anyOf||[]).flatMap(branch=>resolve(branch)?.enum||[]))];
 const uniqueEnum=text=>{
  const matches=values.filter(value=>typeof value==='string'&&value.toLowerCase()===text.toLowerCase());
  return matches.length===1?matches[0]:undefined;
 };
 const singleFiber=text=>{
  if(!/^[a-z][a-z -]*$/i.test(text)||/\b(?:blends?|mixed|mixture|polycotton)\b/i.test(text))return;
  return uniqueEnum(text)||(/^elastane$/i.test(text)?uniqueEnum('Spandex'):undefined);
 };
 const text=sourceValue.trim();
 let value=singleFiber(text.replace(/^100%\s*/, '')),blendBasis;
 if(!value){
  const parts=text.split(/\s*[,/]\s*/).map(part=>/^(\d{1,2}(?:\.\d{1,2})?)%\s*([a-z][a-z -]*)$/i.exec(part));
  if(parts.length<2||parts.some(part=>!part))return;
  // Hundredths of a percent keep the declared sum exact for accepted inputs.
  const fibers=parts.map(([,amount,fiber])=>({name:singleFiber(fiber.trim()),share:Math.round(Number(amount)*100)}));
  if(fibers.some(fiber=>!fiber.name||fiber.share<=0)||new Set(fibers.map(fiber=>fiber.name)).size!==fibers.length||
     fibers.reduce((total,fiber)=>total+fiber.share,0)!==10000)return;
  const primary=fibers.find(fiber=>fiber.share>5000);
  value=primary&&uniqueEnum(`${primary.name} Blend`);
  if(!value)return;
  blendBasis={transformation:'majority_fiber_blend_enum',primaryFiber:primary.name,primaryPercentage:primary.share/100};
 }
 attributes.material=[{value,language_tag:target.languageTag,marketplace_id:target.marketplaceId}];
 evidence.material={value,source:materialEvidenceSource,path:'fabric_type.0.value',sourceValue,...blendBasis};
}

// Supplement the UK material type and the additional GB SHIRT requirements.
// Evidence stays in the receipt, separate from Amazon-facing attribute values.
export function supplementUkRequiredAttributes(attributes,input,meta,prepared,categoryChoice){
 const result=clone(attributes||{}),evidence={};
 if(meta.country_code!=='GB')return{attributes:result,evidence};
 const target=prepared?.destination,shirt=meta.product_type_name==='SHIRT';
 const hasUkLocale=meta.locale==='en_GB'&&meta.hash&&target?.countryCode==='GB'&&target.languageTag==='en_GB'&&target.marketplaceId;
 if(!shirt&&!hasUkLocale)return{attributes:result,evidence};
 const schema=schemaObject(meta),props=schema?.properties;
 const resolve=definition=>definition?.$ref?.startsWith('#/$defs/')?schema.$defs?.[definition.$ref.slice(8)]:definition;
 if(hasUkLocale&&schema?.$defs?.marketplace_id?.default===target.marketplaceId)supplementUkMaterial(result,evidence,schema,target,resolve);
 if(meta.product_type_name==='COAT'){
  const coat=supplementUkCoat(result,input,meta,prepared,categoryChoice);
  return{attributes:coat.attributes,evidence:{...evidence,...coat.evidence}};
 }
 if(meta.product_type_name==='SWEATSHIRT'&&hasUkLocale&&schema?.$defs?.marketplace_id?.default===target.marketplaceId){
  const description=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n');
  const materials=[...description.matchAll(/^Material:[ \t]*([^\r\n]+)$/gm)];
  const hoodedHalfZip=/^Style:[^\r\n]*\bhooded pullover\b/im.test(description)&&
   /^Closure:[ \t]*Half[- ]zip[ \t]*\r?$/im.test(description)&&/^Hood:[ \t]*Drawstring(?: hood)?[ \t]*\r?$/im.test(description);
  const halfZip=/^Style:[^\r\n]*\bhalf[- ]zip\b[^\r\n]*\bpullover\b/im.test(description)||hoodedHalfZip;
  const fauxSuedeButtonPullover=/^Style:[^\r\n]*\bpullover\b/im.test(description)&&/^Front: Four-button half placket\s*$/im.test(description)&&
   /^Faux suede made with polyester and elastane$/i.test(materials[0]?.[1].trim()??'');
  if((halfZip||fauxSuedeButtonPullover)&&materials.length===1&&input.goods.manufacturer){
   const loc=value=>({value,language_tag:target.languageTag,marketplace_id:target.marketplaceId});
   const outerMaterial=fauxSuedeButtonPullover?'Synthetic':materials[0][1].trim();
   const attrs={item_type_name:[loc('Sweatshirt')],manufacturer:[loc(input.goods.manufacturer)],
    outer:[{material:[{value:outerMaterial,language_tag:target.languageTag}],marketplace_id:target.marketplaceId}]};
   const confirmation=input.ukPreparation?.sweatshirtWeave;
   const supplierWeave=input.publicationFacts?.weaveTypeEvidence;
   const mappedWeave=new Map([['针织','Knit'],['梭织','Woven']]);
   const confirmed=confirmation?.source==='user_confirmation'&&confirmation.productId===input.productId&&
    confirmation.sourceUrl===input.goods.sourceUrl&&['Knit','Woven'].includes(confirmation.value);
   const supplied=supplierWeave?.source==='supplier_attribute'&&['织法','工艺'].includes(supplierWeave.field)&&
    supplierWeave.sourceUrl===input.goods.sourceUrl&&mappedWeave.has(supplierWeave.sourceValue)&&
    mappedWeave.get(supplierWeave.sourceValue)===supplierWeave.value;
   const weave=confirmed?confirmation:supplierWeave;
   if(confirmed||supplied){
    const definition=resolve(props?.weave_type?.items?.properties?.value);
    const accepts=definition?.enum?.includes(weave.value)||definition?.anyOf?.some(v=>v.enum?.includes(weave.value)||v.type==='string'&&!v.enum);
    if(!accepts)throw Error('英国卫衣实际类目不接受已核实的织法');
    attrs.weave_type=[loc(weave.value)];
   }
   for(const [key,value] of Object.entries(attrs))if(!Object.hasOwn(result,key)){
    result[key]=value;
    evidence[key]=key==='weave_type'?clone(weave):{
     source:fauxSuedeButtonPullover?'frozen_original_faux_suede_pullover':'frozen_original_half_zip_pullover',value:clone(value)};
   }
  }
  return{attributes:result,evidence};
 }
 const sweaterDescription=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n');
 const suppliedKnit=input.publicationFacts?.weaveTypeEvidence;
 const modelEvidence=input.publicationFacts?.supplierModelNumberEvidence;
 const sweaterLine=label=>{const rows=sweaterDescription.split(/\r?\n/).filter(row=>row.startsWith(label+':'));return rows.length===1?rows[0].slice(label.length+1).trim():'';};
 const cowlBlend=sweaterLine('Material').match(/^(\d+)%\s*polyester,\s*(\d+)%\s*(?:spandex|elastane)$/i);
 const ribbedCowlPullover=!sweaterLine('Style')&&/^Loose pullover shape$/i.test(sweaterLine('Fit'))&&
  /^Fine vertical ribbing$/i.test(sweaterLine('Texture'))&&/^Deep draped cowl$/i.test(sweaterLine('Neckline'))&&
  /\bcowl neck\b/i.test(input.goods?.title||'')&&/\bpullover\b/i.test(input.goods?.title||'')&&
  cowlBlend&&Number(cowlBlend[1])+Number(cowlBlend[2])===100&&Number(cowlBlend[1])>50&&
  /^https:\/\/detail\.1688\.com\/offer\/\d+\.html$/.test(input.goods?.sourceUrl||'')&&
  modelEvidence?.source==='supplier_attribute'&&modelEvidence.sourceUrl===input.goods.sourceUrl&&
  Boolean(input.publicationFacts?.supplierModelNumber)&&modelEvidence.value===input.publicationFacts.supplierModelNumber&&
  (!suppliedKnit||['Knit','Rib'].includes(suppliedKnit.value))&&
  input.publicationFacts?.waterResistanceLevelSource?.basis?.classification==='ordinary_apparel';
 const acrylicJacquardPullover=/^Style:[^\r\n]*\bknitted\s+pullover\b/im.test(sweaterDescription)&&
  /^Material:\s*100%\s*acrylic\s*$/im.test(sweaterDescription)&&/\bjacquard\b/i.test(input.goods?.title||'')&&
  /^https:\/\/detail\.1688\.com\/offer\/\d+\.html$/.test(input.goods?.sourceUrl||'')&&
  modelEvidence?.source==='supplier_attribute'&&modelEvidence.sourceUrl===input.goods.sourceUrl&&
  Boolean(input.publicationFacts?.supplierModelNumber)&&modelEvidence.value===input.publicationFacts.supplierModelNumber&&
  (!suppliedKnit||['Knit','Jacquard'].includes(suppliedKnit.value))&&
  input.publicationFacts?.waterResistanceLevelSource?.basis?.classification==='ordinary_apparel';
 const knitPullover=/^Style:[^\r\n]*\bpullover\b/im.test(sweaterDescription)&&
  /^Material:\s*Polyester-rich rib knit\s*$/im.test(sweaterDescription)&&suppliedKnit?.source==='supplier_attribute'&&
  suppliedKnit.value==='Knit'&&suppliedKnit.sourceUrl===input.goods?.sourceUrl||acrylicJacquardPullover||ribbedCowlPullover;
 if(meta.product_type_name==='SWEATER'&&hasUkLocale&&(/\bcardigan\b/i.test(input.goods?.title||'')||knitPullover)){
  const description=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n');
  const materials=[...description.matchAll(/^Material:\s*([^\r\n]+)$/gm)];
  if((/^Texture:\s*Knit\s*$/im.test(description)||knitPullover)&&materials.length===1&&input.goods.manufacturer&&input.publicationFacts?.waterResistanceLevel){
   const loc=value=>({value,language_tag:target.languageTag,marketplace_id:target.marketplaceId});
   const weave=acrylicJacquardPullover?'Jacquard':ribbedCowlPullover?'Rib':'Knit';
   if(acrylicJacquardPullover||ribbedCowlPullover){
    const value=resolve(props?.weave_type?.items?.properties?.value),choices=value?.enum??value?.anyOf?.flatMap(branch=>branch.enum??[])??[];
    if(!choices.includes(weave))throw Error('英国毛衣实际schema没有已核实的'+weave+'选项');
   }
   if(ribbedCowlPullover){const value=resolve(props?.outer?.items?.properties?.material?.items?.properties?.value),choices=value?.enum??value?.anyOf?.flatMap(branch=>branch.enum??[])??[];if(!choices.includes('Synthetic'))throw Error('英国毛衣实际schema没有Synthetic选项');}
   const attrs={item_type_name:[loc(knitPullover?'Pullover Sweater':'Cardigan Sweater')],manufacturer:[loc(input.goods.manufacturer)],
    ...(/\boversized\b/i.test(input.goods.title)&&props?.fit_type?{fit_type:[loc('Oversized')]}:{}),
    outer:[{material:[{value:ribbedCowlPullover?'Synthetic':materials[0][1].trim(),language_tag:target.languageTag}],marketplace_id:target.marketplaceId}],
    water_resistance_level:[{value:input.publicationFacts.waterResistanceLevel,marketplace_id:target.marketplaceId}],weave_type:[loc(weave)]};
   for(const [key,value] of Object.entries(attrs))if(!Object.hasOwn(result,key)){
    result[key]=value;
    evidence[key]={source:knitPullover?'frozen_original_knit_pullover':'frozen_original_knit_cardigan',value:clone(value)};
    if(acrylicJacquardPullover)evidence[key]={source:key==='weave_type'?'inferred_workbench_classification':'frozen_original_acrylic_knitted_pullover',
     value:clone(value),humanReviewed:false,...(key==='weave_type'?{supplierVerified:false,rule:'explicit_jacquard_design_catalogue_classification',
      basis:{title:input.goods.title,style:sweaterDescription.match(/^Style:\s*([^\r\n]+)$/im)?.[1],supplierModelNumberEvidence:clone(modelEvidence)}}:{})};
    if(ribbedCowlPullover)evidence[key]={source:['weave_type','outer','item_type_name'].includes(key)?'inferred_workbench_classification':'frozen_original_cowl_pullover',
     value:clone(value),humanReviewed:false,supplierVerified:false,rule:'source_bound_polyester_spandex_ribbed_cowl_pullover',
     basis:{material:sweaterLine('Material'),texture:sweaterLine('Texture'),fit:sweaterLine('Fit'),neckline:sweaterLine('Neckline'),supplierModelNumberEvidence:clone(modelEvidence)},
     note:'Catalogue classification from frozen source-bound product lines; original fabric percentages unchanged; not factory weave certification.'};
   }
  }
  return{attributes:result,evidence};
 }
 if(meta.product_type_name==='SKIRT'&&hasUkLocale&&schema?.$defs?.marketplace_id?.default===target.marketplaceId){
  const description=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n');
  const material=[...description.matchAll(/^Material:[ \t]*([^\r\n]+)$/gm)];
  const style=[...description.matchAll(/^Style:[ \t]*([^\r\n]*\bmini skirt\b[^\r\n]*)$/gim)];
  if(!sameCategoryPath(target.categoryHints?.path||'','Fashion > Women > Clothing > Skirts')||material.length!==1||style.length!==1)return{attributes:result,evidence};
  const loc=value=>({value,language_tag:target.languageTag,marketplace_id:target.marketplaceId});
  const choice=(key,value)=>{const d=resolve(props?.[key]?.items?.properties?.value),values=d?.enum??d?.anyOf?.flatMap(branch=>branch.enum??[])??[];if(!values.includes(value))throw Error('英国短裙类目没有有效属性 '+key);return value;};
  const attrs={item_type_name:[loc(choice('item_type_name','Skirt'))]};
  if(input.goods.manufacturer&&props.manufacturer)attrs.manufacturer=[loc(input.goods.manufacturer)];
  if(props.outer?.items?.properties?.material)attrs.outer=[{material:[{value:material[0][1].trim(),language_tag:target.languageTag}],marketplace_id:target.marketplaceId}];
  // The source confirms base-fabric composition, not a separate lining.
  // Keep that distinction explicit in the native free-text material field.
  const inner=props.inner?.items,innerValue=inner?.properties?.material?.items?.properties?.value;
  const liningText='Base fabric: '+material[0][1].trim()+'; separate lining not specified';
  if(!Object.hasOwn(result,'inner')&&inner?.properties?.marketplace_id&&innerValue?.type==='string'&&
     !innerValue.enum&&(!innerValue.maxLength||liningText.length<=innerValue.maxLength)){
   attrs.inner=[{material:[{value:liningText,language_tag:target.languageTag}],marketplace_id:target.marketplaceId}];
  }
  const weave=input.publicationFacts?.weaveTypeEvidence;
  if(weave?.source==='user_configured_defaults'&&weave.productId===input.productId&&weave.scope==='missing_catalogue_attribute_only'&&
     weave.supplierVerified===false&&weave.value==='Plain'&&weave.configuredAt&&typeof weave.instruction==='string'&&weave.instruction.trim())attrs.weave_type=[loc(choice('weave_type',weave.value))];
  for(const [key,value] of Object.entries(attrs))if(!Object.hasOwn(result,key)){
   result[key]=value;evidence[key]=key==='weave_type'?clone(weave):{source:key==='inner'?'frozen_base_fabric_with_explicit_unspecified_lining':key==='item_type_name'?'verified_category_mapping':'frozen_original_product_facts',value:clone(value),humanReviewed:false,...(key==='inner'?{separateLiningVerified:false,sourcePath:'goods.description/Material'}: {})};
  }
  return{attributes:result,evidence};
 }
 if(meta.product_type_name==='PANTS'&&hasUkLocale){
  const configured=input.publicationFacts?.weaveTypeEvidence;
  const sellerDefault=configured?.source==='user_configured_defaults'&&configured.productId===input.productId&&
    configured.scope==='missing_catalogue_attribute_only'&&configured.value==='Plain'&&configured.supplierVerified===false&&
    typeof configured.instruction==='string'&&configured.instruction.trim()&&configured.configuredAt;
  const weave=input.ukPreparation?.pantsWeave||(sellerDefault?configured:null), path=target.categoryHints?.path;
  const description=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n');
  const material=[...description.matchAll(/^Material:\s*([^\r\n]+)$/gm)];
  const style=[...description.matchAll(/^Style:[^\r\n]*\bwide-leg\b[^\r\n]*$/gim)];
  if(!weave||!path||!/^Fashion\s*>\s*Women\s*>\s*Clothing\s*>\s*Trousers$/i.test(path)||material.length!==1||style.length!==1||!input.goods.manufacturer)return{attributes:result,evidence};
  const loc=value=>({value,language_tag:target.languageTag,marketplace_id:target.marketplaceId});
  const choice=(definition,value)=>{
   const v=resolve(definition), values=v?.enum??v?.anyOf?.flatMap(branch=>branch.enum??[])??[];
   if(!values.includes(value))throw Error('英国裤装类目没有已核实的属性值 '+value);
   return value;
  };
  const p=key=>props?.[key]?.items?.properties;
  const attrs={item_type_name:[loc(choice(p('item_type_name')?.value,'Pants'))],
   ...(p('fit_type')?.value?{fit_type:[loc(choice(p('fit_type').value,weave.value==='Satin'?'Flowy':'Loose'))]}:{}),
   leg:[{style:[{value:choice(p('leg')?.style?.items?.properties?.value,'Wide'),language_tag:target.languageTag}],marketplace_id:target.marketplaceId}],
   manufacturer:[loc(input.goods.manufacturer)],outer:[{material:[{value:material[0][1].trim(),language_tag:target.languageTag}],marketplace_id:target.marketplaceId}],
   water_resistance_level:[{value:choice(p('water_resistance_level')?.value,input.publicationFacts?.waterResistanceLevel),marketplace_id:target.marketplaceId}],
   weave_type:[loc(choice(p('weave_type')?.value,weave.value))]};
  for(const [key,value] of Object.entries(attrs))if(!Object.hasOwn(result,key)){
   result[key]=value;
   evidence[key]=key==='weave_type'?clone(weave):key==='fit_type'?{source:weave.value==='Satin'?'verified_satin_wide_leg_classification':'inferred_workbench_classification',inferred:true,rule:'ordinary_women_wide_leg_trousers_fit',sourceFields:{style:style[0][0]},value:clone(value),humanReviewed:false,note:'Catalogue fit classification from the frozen wide-leg style; not supplier literal text.'}:{source:'frozen_original_product_facts',value:clone(value)};
  }
  return{attributes:result,evidence};
 }
 if(!shirt)return{attributes:result,evidence};
 const description=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n').replace(/\r\n/g,'\n');
 const field=name=>{const rows=description.split('\n').map(line=>line.match(new RegExp('^'+name+':\\s*(.+)$','i'))).filter(Boolean);return rows.length===1?rows[0][1].trim():null;};
 const tshirtPaths=()=>{const sourcePath=input.destination?.categoryHints?.path,ukPath=prepared.destination?.categoryHints?.path;return typeof sourcePath==='string'&&typeof ukPath==='string'&&/(?:^|[>\s])T-Shirts\s*$/i.test(sourcePath)&&/(?:^|[>\s])T-Shirts\s*$/i.test(ukPath)?{sourcePath,targetPath:ukPath}:null;};
 const fail=(key,reason)=>{const error=Error('英国必填属性 '+key+' 缺少明确依据：'+reason);error.ukRequiredAttributeEvidence=clone(evidence);error.ukRequiredAttributePreview=clone(result);error.ukMissingRequiredAttribute=key;throw error;};
 for(const key of ['manufacturer','collar_style','item_type_name','outer','weave_type'])if(Object.hasOwn(result,key))evidence[key]={value:clone(result[key]),source:'original_migrated_attribute'};
 const localized=(key,value)=>{
  const definition=resolve(props?.[key]?.items?.properties?.value),open=definition?.type==='string'&&!definition.enum||definition?.anyOf?.some(node=>node.type==='string'&&!node.enum);
  if(typeof value!=='string'||!value.trim()||!definition||(!open&&!definition.enum?.includes(value))||(definition.maxLength&&value.length>definition.maxLength))fail(key,'原文字段不符合实际英国schema');
  return[{value,language_tag:target.languageTag,marketplace_id:target.marketplaceId}];
 };
 const known=(key,value,basis)=>{if(Object.hasOwn(result,key)){evidence[key]={value:clone(result[key]),source:'original_migrated_attribute'};return;}result[key]=localized(key,value);evidence[key]={value, ...basis};};
 const construction=input.ukPreparation?.corduroyConstruction;
 const corduroyTunic=construction?.source==='supplier_attribute'&&construction.productId===input.productId&&
  construction.sourceUrl===input.goods.sourceUrl&&construction.sourceUrl===input.publicationFacts?.supplierModelNumberEvidence?.sourceUrl&&
  construction.schemaHash===meta.hash&&construction.categoryValue===categoryChoice?.value&&
  /\bBlouses\s*$/i.test(categoryChoice?.text||'')&&construction.supplierValues?.weave==='梭织'&&
  construction.supplierValues?.fabric==='灯芯绒'&&construction.supplierValues?.neckline==='圆领'&&
  construction.supplierValues?.composition==='涤纶（聚酯纤维）:100%'&&/^crew neck$/i.test(field('Neckline')||'')&&
  /\btunic\b/i.test(input.goods?.title||'')&&/^100% polyester corduroy$/i.test(field('Material')||'');
 if(corduroyTunic){
  known('collar_style','Collarless',{source:'verified_crew_neck_tunic',supplier:clone(construction)});
  known('item_type_name','Tunic Shirt',{source:'verified_category_mapping',category:categoryChoice.text});
  known('weave_type','Woven',{source:'supplier_attribute',basis:clone(construction)});
  if(props?.material)known('material','Polyester',{source:'supplier_attribute',basis:clone(construction)});
 }
 // Ordinary women's blouses have their own verified taxonomy leaf. Crew-neck
 // pullover construction and the bound supplier's weave supply missing facts;
 // neither a T-shirt classification nor a guessed weave is needed.
 const sourceBlousePath=input.destination?.categoryHints?.path;
 const ordinaryBlouse=hasUkLocale&&schema?.$defs?.marketplace_id?.default===target.marketplaceId&&
  /^Clothing,? Shoes & Jewelry\s*>\s*Women\s*>\s*Clothing\s*>\s*Tops,? Tees & Blouses\s*>\s*Blouses & Button-Down Shirts\s*>\s*Blouses$/i.test(sourceBlousePath||'')&&
  /^Fashion Women Clothing Tops T-Shirts & Blouses Blouses & Shirts Blouses$/i.test(categoryChoice?.text||'')&&
  typeof categoryChoice?.value==='string'&&/^\d+(?:,\d+)+$/.test(categoryChoice.value)&&
  /^crew\s+neck$/i.test(field('Neckline')||'')&&/\bpullover\b/i.test(field('Style')||'')&&
  !/\bpolo\b|\bfold(?:ed)?[ -]?collar\b|\bturn[ -]?down\b|\bbutton[ -]?(?:down|collar)\b|\bstand(?:ing)?[ -]?collar\b|\bmandarin\b|\bshirt[ -]?collar\b|\bturtle(?:neck)?\b|\bmock[ -]?neck\b/i.test(description);
 if(ordinaryBlouse){
  known('collar_style','Collarless',{source:'inferred_workbench_classification',inferred:true,
   rule:'crew_neck_pullover_blouse_no_folded_collar_v1',sourcePath:sourceBlousePath,targetCategory:clone(categoryChoice),
   sourceFields:{neckline:field('Neckline'),style:field('Style')},note:'Construction classification; not supplier literal text'});
  known('item_type_name','Blouse',{source:'verified_category_mapping',sourcePath:sourceBlousePath,targetCategory:clone(categoryChoice)});
  const weave=input.publicationFacts?.weaveTypeEvidence;
  const mapped=new Map([['针织','Knit'],['梭织','Woven']]);
  if(weave?.source==='supplier_attribute'&&['织法','工艺'].includes(weave.field)&&weave.sourceUrl===input.goods.sourceUrl&&
    weave.sourceUrl===input.publicationFacts?.supplierModelNumberEvidence?.sourceUrl&&mapped.get(weave.sourceValue)===weave.value&&mapped.has(weave.sourceValue)){
   known('weave_type',weave.value,{source:'supplier_attribute',basis:clone(weave)});
  }
 }
 if(!Object.hasOwn(result,'manufacturer')){
  const value=input.goods?.manufacturer;if(typeof value!=='string'||!value.trim())fail('manufacturer','冻结goods.manufacturer为空，未补Generic');
  known('manufacturer',value,{source:'frozen_goods',path:'goods.manufacturer'});
 }
 if(!Object.hasOwn(result,'collar_style')){
  const neck=field('Neckline'),style=field('Style'),paths=tshirtPaths();
  const conflict=/\bpolo\b|\bfold(?:ed)?[ -]?collar\b|\bturn[ -]?down\b|\bbutton[ -]?(?:down|collar)\b|\bstand(?:ing)?[ -]?collar\b|\bmandarin\b|\bshirt[ -]?collar\b|\bturtle(?:neck)?\b|\bmock[ -]?neck\b/i.test(description);
  let actualTshirtRule=false;const visit=node=>{if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(visit);return;}
   if(node.if?.required?.includes('shirt_form_type')&&node.if.properties?.shirt_form_type?.contains?.properties?.value?.enum?.includes('t_shirt')){
    const values=node.then?.properties?.collar_style?.items?.properties?.value?.enum;if(values?.length===1&&values[0]==='Collarless')actualTshirtRule=true;
   }for(const value of Object.values(node))visit(value);
  };visit(schema.allOf);
  if(!neck||!/^crew\s+neck$/i.test(neck)||!style||!/\bpullover\b/i.test(style)||!paths||conflict||!actualTshirtRule)fail('collar_style','仅可将准确T-Shirts、唯一Crew neck普通pullover且无翻折/立领冲突的原事实映射为实际schema的Collarless');
  known('collar_style','Collarless',{source:'inferred_workbench_classification',inferred:true,rule:'crew_neck_tshirt_no_folded_collar_v1',
   basis:'crew-neck ordinary T-shirt without folded/stand collar',sourceFields:{neckline:neck,style},...paths,note:'Workbench classification; not supplier literal text'});
 }
 if(!Object.hasOwn(result,'item_type_name')){
  const paths=tshirtPaths();if(!paths)fail('item_type_name','美国与已选英国节点须都明确以T-Shirts结尾');
  known('item_type_name','T-Shirt',{source:'verified_category_mapping',...paths});
 }
 if(!Object.hasOwn(result,'outer')){
  const material=field('Material');if(!material)fail('outer.material','需要唯一已冻结Material原文');
  const def=resolve(props?.outer?.items?.properties?.material?.items?.properties?.value),open=def?.type==='string'&&!def.enum||def?.anyOf?.some(node=>node.type==='string'&&!node.enum);
  if(!def||(!open&&!def.enum?.includes(material))||(def.maxLength&&material.length>def.maxLength))fail('outer.material','原材质不符合英国outer.material定义');
  result.outer=[{material:[{value:material,language_tag:target.languageTag}],marketplace_id:target.marketplaceId}];
  evidence['outer.material']={value:material,source:'frozen_description',path:'goods.description.Material',transformation:'original_material_text'};
 }
 if(!Object.hasOwn(result,'weave_type')){
  const texture=field('Texture');if(!texture||!/^fine\s+ribbed$/i.test(texture))fail('weave_type','需要唯一已冻结Texture: Fine ribbed原文，未猜测Knit或Woven');
  known('weave_type','Ribbed',{source:'frozen_description',path:'goods.description.Texture',sourceValue:texture,transformation:'original_ribbed_term_only',note:'No unsupported Knit/Woven classification'});
 }
 const explicit=input.ukPreparation?.waterResistanceLevel,frozen=input.publicationFacts?.waterResistanceLevel,water=explicit??frozen;
 if(water===undefined||water===null||water==='')fail('water_resistance_level','未保存显式防水等级；不默认选择不防水');
 const waterDefinition=resolve(props?.water_resistance_level?.items?.properties?.value);
 if(typeof water!=='string'||!waterDefinition?.enum?.includes(water))fail('water_resistance_level','显式值不在真实英国防水等级枚举内');
 if(Object.hasOwn(result,'water_resistance_level')&&result.water_resistance_level?.[0]?.value!==water)fail('water_resistance_level','原属性与显式设置冲突，未覆盖原事实');
 result.water_resistance_level=[{value:water,marketplace_id:target.marketplaceId}];
 evidence.water_resistance_level={value:water,source:explicit!==undefined?'explicit_publication_amendment':'frozen_publication_facts',path:explicit!==undefined?'ukPreparation.waterResistanceLevel':'publicationFacts.waterResistanceLevel',
  ...(explicit===undefined&&input.publicationFacts.waterResistanceLevelSource?{basis:clone(input.publicationFacts.waterResistanceLevelSource)}:{})};
 return{attributes:result,evidence};
}

// Serialized by saveDraft into the page. Keep this function self contained.
export function patchUkDraftPayload(body,input,urls){
 const p=input.ukPrepared,target=p.destination,source=input.destination;
 if(input.mode!=='draft'||String(body.id)!==String(target.draftId)||body.country_code!=='GB'||body.with_publish||body.publish||!body.market_id||String(body.market_id)===String(source.marketId)||(target.marketId&&String(body.market_id)!==String(target.marketId)))throw Error('英国保存请求的草稿、店铺或站点身份不符');
 if(!Array.isArray(body.items)||body.items.length!==p.goodsItems.length||body.items.some(r=>!/^\d+$/.test(String(r.id))||Number(r.id)<=0)||new Set(body.items.map(v=>String(v.id))).size!==body.items.length)throw Error('英国草稿子体集合变化');
 const expected=input.ukCopiedRows;
 if(!expected||body.items.some(row=>!expected.some(e=>String(e.id)===String(row.id))))throw Error('英国草稿ERP子体编号变化');
 const image=index=>{const a=p.assets[index],u=a&&urls[a.sha256];if(!a||!u||!/^https:\/\/junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com\//.test(u))throw Error('原图URL或哈希映射缺失');return u;};
 const nativeShipping=body.attributes?.merchant_shipping_group?.[0]?.value;
 if(!nativeShipping||(target.shippingTemplate.id&&nativeShipping!==target.shippingTemplate.id))throw Error('英国实际运输模板ID未核对');
 const items=body.items.map(row=>{
  const mapped=expected.find(e=>String(e.id)===String(row.id)),v=p.goodsItems.find(v=>v.sku===mapped.sku);
  if(!v)throw Error('原SKU映射缺失');
  const images=v.imageIndices.map(image);
  const identifiers=p.sourceIdentifiers?.children?.[v.sku];if(p.sourceIdentifiers&&!identifiers)throw Error('缺少原美国子SKU商品编码证明');
  return{...row,...(identifiers?{standard_product_type:identifiers.standard_product_type,standard_product_id:identifiers.standard_product_id}:{}),sku:v.sku,market_id:String(body.market_id),country_code:'GB',variation:mapped.variation,
   attributes:{...input.ukItemAttributes[v.sku],...(target.requireMainImageLocator===true?{main_product_image_locator:[{media_location:images[0],marketplace_id:target.marketplaceId}]}:{}),merchant_shipping_group:[{value:nativeShipping,marketplace_id:target.marketplaceId}],
    fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:Number(v.quantity),lead_time_to_ship_max_days:Number(p.handlingDays)}]},
   price:v.price,quantity:String(v.quantity),main_image:images[0],images};
 });
 const first=p.goodsItems.find(v=>v.color===p.masterColor)||p.goodsItems[0];
 if(p.sourceIdentifiers&&(p.sourceIdentifiers.countryCode!=='US'||p.sourceIdentifiers.parentSku!==p.goods.parentSku||!p.sourceIdentifiers.parent))throw Error('原美国父商品编码证明不符');
 return{...body,...(p.sourceIdentifiers?{standard_product_type:p.sourceIdentifiers.parent.standard_product_type,standard_product_id:p.sourceIdentifiers.parent.standard_product_id}:{}),market_id:String(body.market_id),country_code:'GB',sku:p.goods.parentSku,parent_sku:p.goods.parentSku,
  title:p.goods.title,brand:p.goods.brand,manufacturer:p.goods.manufacturer,product_description:p.goods.description,bullet_point:p.goods.bullets,keywords:p.goods.terms,
  items,variation_theme:target.themeValue,price:first.price,quantity:'0',main_image:image(first.imageIndices[0]),images:[image(first.imageIndices[0])],
  attributes:{...input.ukParentAttributes,...(target.requireMainImageLocator===true?{main_product_image_locator:[{media_location:image(first.imageIndices[0]),marketplace_id:target.marketplaceId}]}:{}),merchant_shipping_group:[{value:nativeShipping,marketplace_id:target.marketplaceId}],
   fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:0,lead_time_to_ship_max_days:Number(p.handlingDays)}]},with_publish:false,publish:false};
}

async function pickOption(page,text,inputSelector){
 // Some ERP layouts render the long select behind the following form rows.
 // Use its native keyboard navigation and verify the hovered option before Enter.
 const count=await page.evaluate(text=>{const es=[...document.querySelectorAll('.el-select-dropdown li')].filter(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible');if(es.filter(e=>e.innerText.trim()===text).length!==1)throw Error('英国选项不唯一：'+text);return es.length;},text);
 await page.focus(inputSelector);
 for(let n=0;n<=count;n++){
  const hover=await page.evaluate(()=>[...document.querySelectorAll('.el-select-dropdown li.hover')].filter(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible').map(e=>e.innerText.trim()));
  if(hover.length===1&&hover[0]===text){await page.press(inputSelector,'Enter');await page.waitForFunction(p=>document.querySelector(p.selector)?.value===p.text,{selector:inputSelector,text},{timeout:10000});return;}
  await page.press(inputSelector,'ArrowDown');
 }
 throw Error('英国选项键盘定位失败：'+text);
}

async function ukShippingSelector(page){
 return page.evaluate(()=>{
  const visible=e=>e.getBoundingClientRect().width>0&&getComputedStyle(e).visibility==='visible';
  const labels=[...document.querySelectorAll('label.el-form-item__label')].filter(e=>visible(e)&&e.innerText.trim()==='配送模板');
  if(labels.length!==1)throw Error('英国配送模板标签未唯一匹配');
  const inputs=[...(labels[0].closest('.el-form-item')?.querySelectorAll('.el-select input.el-input__inner')||[])].filter(visible);
  if(inputs.length!==1)throw Error('英国配送模板控件未唯一匹配');
  inputs[0].setAttribute('data-studio-uk-shipping','true');
  return 'input[data-studio-uk-shipping="true"]';
 });
}

export async function readUkPage(page,expected){
 await page.waitForFunction(()=>document.querySelector('input[placeholder="店铺"]')?.value&&document.querySelector('input[placeholder="产品标题"]')?.value&&[...document.querySelectorAll('.el-table__body-wrapper tr')].some(r=>r.querySelector('input[placeholder="sku"]')),undefined,{timeout:20000});
 const shipping=await ukShippingSelector(page);
 await page.waitForFunction(selector=>document.querySelector(selector)?.value,shipping,{timeout:20000});
 if(expected)await page.waitForFunction(p=>{const rows=[...document.querySelectorAll('.el-table__body-wrapper tr')].filter(r=>r.querySelector('input[placeholder="sku"]'));return document.querySelector('input[placeholder="店铺"]')?.value===p.store&&document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.innerText.includes('UPC豁免：允许销售')&&rows.length===p.count&&rows.every(r=>/\bGBP\b/.test(r.innerText));},{store:expected.store,count:expected.goodsItems.length},{timeout:20000});
 return page.evaluate(selector=>{
  const shippingInput=document.querySelector(selector),selectedId=shippingInput?.closest('.el-select')?.__vue__?.value;
  const shippingTemplateId=typeof selectedId==='string'&&selectedId?selectedId:null;
  return{url:location.href,store:document.querySelector('input[placeholder="店铺"]')?.value,
  parentSku:document.querySelector('input[placeholder^="父Sku,"]')?.value,brand:document.querySelector('input[placeholder="品牌"]')?.value,
  brandStatus:document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.innerText,
  shippingTemplate:shippingInput?.value,shippingTemplateId,
  handlingDays:document.querySelector('input[placeholder="处理时间"]')?.value,
  currencies:[...document.querySelectorAll('.el-table__body-wrapper tr')].filter(r=>r.querySelector('input[placeholder="sku"]')).map(r=>r.innerText.match(/\b(?:GBP|USD|EUR)\b/g)||[])};
 },shipping);
}

function verifyUkUi(ui,prepared){
 if(ui.url!=='https://www.junfeikuajing.com/#/amazon/product/'+prepared.destination.draftId+'?type=draft'||ui.store!==prepared.store||ui.brand!==prepared.goods.brand||!ui.brandStatus?.includes('UPC豁免：允许销售')||ui.shippingTemplate!==prepared.destination.shippingTemplate.name||!ui.shippingTemplateId||(prepared.destination.shippingTemplate.id&&String(ui.shippingTemplateId)!==String(prepared.destination.shippingTemplate.id))||String(ui.handlingDays)!==String(prepared.handlingDays)||ui.currencies?.length!==prepared.goodsItems.length||ui.currencies.some(values=>!values.includes('GBP')||values.includes('USD')||values.includes('EUR')))throw Error('英国店铺、GBP币种、实际品牌允许销售、运输模板或处理时间未核实');
 return ui;
}

export function verifyUkDraft(response,prepared,urls,ui){
 const checks=verifyPersistedDraft(response,prepared,urls),d=response.data,attrs=d.extra?.attributes;
 const verifyIdentifiers=(row,expected)=>{if(!expected||!Object.hasOwn(expected,'standard_product_type')||!Object.hasOwn(expected,'standard_product_id')||row.standard_product_type!==expected.standard_product_type||row.standard_product_id!==expected.standard_product_id)throw Error('英国持久商品编码与原美国来源不符：'+row.sku);};
 if(prepared.sourceIdentifiers)verifyIdentifiers(d,prepared.sourceIdentifiers.parent);
 const verifyIdentityAttributes=(attributes,sku)=>{
  const brand=attributes?.brand?.[0];
  if(brand?.value!==prepared.goods.brand||brand.language_tag!==prepared.destination.languageTag||brand.marketplace_id!==prepared.destination.marketplaceId||
     attributes?.variation_theme?.[0]?.name!==prepared.destination.themeValue)throw Error('英国持久品牌或变体主题不符：'+sku);
 };
 verifyIdentityAttributes(attrs,prepared.goods.parentSku);
 const verifyOfferAttributes=(attributes,quantity,sku)=>{
  const offer=attributes?.fulfillment_availability?.[0],shipping=attributes?.merchant_shipping_group?.[0];
  if(offer?.fulfillment_channel_code!=='DEFAULT'||offer.quantity!==quantity||offer.lead_time_to_ship_max_days!==Number(prepared.handlingDays)||
     shipping?.value!==prepared.destination.shippingTemplate.id||shipping.marketplace_id!==prepared.destination.marketplaceId)throw Error('英国持久库存、处理时间或运输模板不符：'+sku);
 };
 verifyOfferAttributes(attrs,0,prepared.goods.parentSku);
 if(String(d.uid)!==String(prepared.destination.erpUserId)||attrs?.supplier_declared_has_product_identifier_exemption?.[0]?.value!==true)throw Error('英国持久ERP账号或豁免不符');
 for(const row of d.items){
  if(prepared.sourceIdentifiers)verifyIdentifiers(row,prepared.sourceIdentifiers.children[row.sku]);
  // Native ERP children store their market on the parent and return null for
  // these two columns. Only a proven parent link may inherit it; explicit
  // foreign markets or locales remain errors. Image galleries never inherit.
  const attrs=row.extra?.attributes||{},linked=String(row.pid)===String(d.id),market=row.market_id==null?linked:String(row.market_id)===String(d.market_id),country=row.country_code==null?linked:row.country_code==='GB';
  verifyIdentityAttributes(attrs,row.sku);
  verifyOfferAttributes(attrs,Number(prepared.goodsItems.find(v=>v.sku===row.sku)?.quantity),row.sku);
  const foreign=Object.values(attrs).filter(Array.isArray).flat().some(v=>v&&typeof v==='object'&&((v.marketplace_id&&v.marketplace_id!==prepared.destination.marketplaceId)||(v.language_tag&&v.language_tag!==prepared.destination.languageTag)));
  if(String(row.uid)!==String(d.uid)||!linked||!market||!country||foreign||attrs.supplier_declared_has_product_identifier_exemption?.[0]?.value!==true)throw Error('英国子体ERP账号、站点或豁免不符：'+row.sku);
 }
 verifyUkUi(ui,prepared);return checks;
}

export async function chooseUkRecommendedCategory(candidates,input,record,persist,recommendationTitle=input.goods.title){
 const t=preparationTarget(input),hints=resolveCategoryHints(t.categoryHints,input.categoryHints,input.destination.categoryHints);
 if(record.categoryRecommendation)(record.categoryRecommendationHistory??=[]).push(record.categoryRecommendation);
 delete record.categoryChoice;
 record.categoryRecommendation={observedAt:new Date().toISOString(),draftId:String(record.draftId),store:t.storeName,countryCode:'GB',candidates:clone(candidates),hints:clone(hints),title:recommendationTitle};await persist();
 if(recommendationTitle!==input.goods.title&&candidates.filter(row=>sameCategoryPath(row.text,t.categoryHints?.path)).length!==1)
  throw Error('英国 ERP 重新识别后仍未找到唯一的已核实类目');
 // US Pullovers and the actual GB women's Jumpers leaf describe the same
 // ordinary pullover family. Never substitute maternity/sport/sleeveless nodes.
 const description=String(input.goods?.description||'').replace(/<br\s*\/?\s*>/gi,'\n');
 let categoryHints=hints;
 if(/^Clothing, Shoes & Jewelry\s*>\s*Women\s*>\s*Clothing\s*>\s*Sweaters\s*>\s*Pullovers$/i.test(hints.path||'')&&
    record.sourceEvidence?.country_code==='US'&&record.sourceEvidence?.product_type_name==='SWEATER'&&
    /^Style:[^\r\n]*\bpullover\b/im.test(description)){
  const matches=candidates.filter(row=>/^Fashion\s+Women\s+Clothing\s+Jumpers\s+Cardigans\s*&\s*Sweatshirts\s+Jumpers$/i.test(row.text.trim()));
  if(matches.length!==1)throw Error('英国普通女士Jumpers节点缺失或有歧义，保留原草稿');
  categoryHints={...hints,path:matches[0].text};
  record.categoryMapping={source:'verified_us_pullover_to_observed_uk_jumpers',sourcePath:hints.path,
   sourceProductType:'SWEATER',targetPath:matches[0].text,targetValue:matches[0].value,humanReviewed:false};await persist();
 }
 const selected=chooseCategory(candidates,categoryHints,input.goods.title);
 if(typeof selected.value!=='string'||!selected.value.trim())throw Error('英国类目推荐未读到原生节点编号，保留候选待核对');
 record.categoryChoice=selected;await persist();return selected;
}

// These callbacks are serialized into the native page. Keep them self contained.
export function installUkSchemaObservation(token){
 if(window.__ukSchema)throw Error('已有英国schema观察');
 const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();
 const state={token,installedAt:new Date().toISOString(),open,send,requests:[],data:null};window.__ukSchema=state;
 const hookedOpen=function(method,url,...rest){
  const target=new URL(url,location.href);
  if(String(method).toUpperCase()==='GET'&&target.origin==='https://app.junfeikuajing.com'&&target.pathname==='/api/amazon/category/get-product-type')targets.set(this,target);else targets.delete(this);
  return open.call(this,method,url,...rest);
 };
 const hookedSend=function(body){
  const url=targets.get(this);
  if(url){
   const entry={url:url.href,method:'GET',countryCode:url.searchParams.get('country_code'),startedAt:new Date().toISOString(),httpStatus:null,code:null,parseError:null,metaIdentity:null,accepted:false};state.requests.push(entry);
   this.addEventListener('loadend',()=>{
    entry.httpStatus=this.status;entry.completedAt=new Date().toISOString();let result;
    try{result=JSON.parse(this.responseText);}catch(error){entry.parseError=String(error.message||error);return;}
    entry.code=result?.code??null;entry.message=typeof result?.message==='string'?result.message.slice(0,300):null;
    const meta=result?.data;entry.metaIdentity=meta&&typeof meta==='object'?{country_code:meta.country_code,locale:meta.locale,hash:meta.hash,product_type_name:meta.product_type_name,version:meta.version}:null;
    entry.accepted=entry.countryCode==='GB'&&this.status===200&&result?.code===0&&meta?.country_code==='GB'&&meta.locale==='en_GB'&&typeof meta.hash==='string'&&Boolean(meta.hash.trim())&&
     typeof meta.product_type_name==='string'&&Boolean(meta.product_type_name)&&(!url.searchParams.get('product_type_name')||url.searchParams.get('product_type_name')===meta.product_type_name);
    if(entry.accepted)state.data=meta;
   },{once:true});
  }
  return send.call(this,body);
 };
 state.hookedOpen=hookedOpen;state.hookedSend=hookedSend;XMLHttpRequest.prototype.open=hookedOpen;XMLHttpRequest.prototype.send=hookedSend;
 return{installed:true,token,installedAt:state.installedAt};
}

export function ukSchemaObservationSnapshot(expectedToken){
 const state=window.__ukSchema,meta=state?.data;
 return{present:Boolean(state),expectedToken,token:state?.token??null,installedAt:state?.installedAt??null,
  bindings:{open:Boolean(state)&&XMLHttpRequest.prototype.open===state.hookedOpen,send:Boolean(state)&&XMLHttpRequest.prototype.send===state.hookedSend},
  requests:state?.requests||[],hasData:Boolean(meta),metaIdentity:meta?{country_code:meta.country_code,locale:meta.locale,hash:meta.hash,product_type_name:meta.product_type_name,version:meta.version}:null,observedAt:new Date().toISOString()};
}

export function ukSchemaObservationReady(expectedToken){
 const state=window.__ukSchema;
 if(!state||state.token!==expectedToken||XMLHttpRequest.prototype.open!==state.hookedOpen||XMLHttpRequest.prototype.send!==state.hookedSend)throw Error('英国schema观察token或原型绑定已变化，未继续保存');
 const failed=state.requests.find(row=>row.countryCode==='GB'&&row.completedAt&&!row.accepted);
 if(failed)throw Error('英国schema原生响应未通过严格检查：HTTP '+failed.httpStatus+' code '+failed.code+(failed.parseError?' JSON解析失败':''));
 return Boolean(state.data);
}

export function releaseUkSchemaObservation(expectedToken){
 const state=window.__ukSchema;if(!state||state.token!==expectedToken)return false;
 if(XMLHttpRequest.prototype.open===state.hookedOpen)XMLHttpRequest.prototype.open=state.open;
 if(XMLHttpRequest.prototype.send===state.hookedSend)XMLHttpRequest.prototype.send=state.send;
 delete window.__ukSchema;return true;
}

export async function observeUkSchemaPreparation(page,input,record,persist,selectCategory){
 const token='uk-schema:'+record.draftId+':'+Date.now()+':'+Math.random().toString(36).slice(2),target=preparationTarget(input);
 if(record.schemaRequestObservation)(record.schemaRequestObservationHistory??=[]).push(record.schemaRequestObservation);
 record.schemaRequestObservation={token,draftId:String(record.draftId),store:target.storeName,countryCode:'GB',stage:'installing',startedAt:new Date().toISOString()};
 const capture=async()=>{const snapshot=await page.evaluate(ukSchemaObservationSnapshot,token);Object.assign(record.schemaRequestObservation,snapshot);await persist();return snapshot;};
 const check=snapshot=>{if(!snapshot.present||snapshot.token!==token||!snapshot.bindings.open||!snapshot.bindings.send)throw Error('英国schema观察未确认token和原型绑定，未继续保存');};
 try{
  const installed=await page.evaluate(installUkSchemaObservation,token),initial=await capture();
  if(installed?.installed!==true||installed.token!==token)throw Error('英国schema观察安装未确认');check(initial);
  record.schemaRequestObservation.stage='selecting_category';await persist();await selectCategory();
  check(await capture());record.schemaRequestObservation.stage='awaiting_schema';await persist();
  await page.waitForFunction(ukSchemaObservationReady,token,{timeout:20000});
  const meta=await page.evaluate(token=>{const state=window.__ukSchema;if(state?.token!==token)throw Error('英国schema观察token变化');return state.data;},token);
  if(meta?.country_code!=='GB'||meta.locale!=='en_GB'||typeof meta.hash!=='string'||!meta.hash.trim())throw Error('英国schema响应身份不符');
  record.schemaRequestObservation.stage='schema_received';return meta;
 }catch(error){record.schemaRequestObservation.error=String(error.message||error);throw error;}
 finally{
  try{await capture();record.schemaRequestObservation.endedAt=new Date().toISOString();await persist();}
  finally{await page.evaluate(releaseUkSchemaObservation,token);}
 }
}

export function ukAutoRecommendationStable(){
 // A store change may finish opening recommendations after the first check.
 // That dialog takes precedence over the now-covered auto button.
 if([...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].some(dialog=>dialog.getBoundingClientRect().width))return true;
 const buttons=[...document.querySelectorAll('button')].filter(button=>button.getBoundingClientRect().width&&!button.disabled&&button.innerText.trim()==='自动识别产品类型');
 if(buttons.length!==1)return false;const button=buttons[0],rect=button.getBoundingClientRect(),style=getComputedStyle(button),x=rect.x+rect.width/2,y=rect.y+rect.height/2,hit=document.elementFromPoint(x,y);
 if(!rect.width||!rect.height||style.pointerEvents==='none'||style.visibility==='hidden'||Number(style.opacity??1)!==1||x<0||y<0||x>=innerWidth||y>=innerHeight||!hit||(hit!==button&&!button.contains(hit))){button.__ukRecommendationStable=null;return false;}
 const fingerprint=JSON.stringify([rect.x,rect.y,rect.width,rect.height]);button.__ukRecommendationStable=button.__ukRecommendationStable?.fingerprint===fingerprint?{fingerprint,count:button.__ukRecommendationStable.count+1}:{fingerprint,count:1};return button.__ukRecommendationStable.count>=3;
}

export async function openUkCategoryRecommendations(page){
 const hasDialog=await page.evaluate(()=>[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].some(dialog=>dialog.getBoundingClientRect().width));
 if(!hasDialog){
  await page.evaluate(()=>{if([...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].some(dialog=>dialog.getBoundingClientRect().width))return;const buttons=[...document.querySelectorAll('button')].filter(button=>button.getBoundingClientRect().width&&!button.disabled&&button.innerText.trim()==='自动识别产品类型');if(buttons.length!==1)throw Error('英国自动识别产品类型入口不唯一或缺失');buttons[0].scrollIntoView({block:'center',inline:'nearest'});});
  await page.waitForFunction(ukAutoRecommendationStable,undefined,{timeout:10000});
  const appeared=await page.evaluate(()=>[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].some(dialog=>dialog.getBoundingClientRect().width));
  if(!appeared)await page.click('loc=role:button[name="自动识别产品类型"]');
 }
 await page.waitForFunction(()=>[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"] label.el-radio')].some(row=>row.getBoundingClientRect().width),undefined,{timeout:20000});
}

export function ukCategoryRadioReady(selected){
 const dialog=[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].find(e=>e.getBoundingClientRect().width);
 if(!dialog)return false;
 const rows=[...dialog.querySelectorAll('label.el-radio')],checked=rows.filter(e=>e.querySelector('input')?.checked&&e.classList.contains('is-checked')&&e.getAttribute('aria-checked')==='true');
 const row=checked[0],text=row?.innerText.split(/[\u3400-\u9fff]/)[0].replace(/[\uE000-\uF8FF]/g,' > ').replace(/\s+/g,' ').trim();
 if(checked.length!==1||row.querySelector('input').value!==selected.value||text!==selected.text){for(const item of rows)item.__ukCategoryReadyState=null;return false;}
 const key=JSON.stringify([selected.value,text]);row.__ukCategoryReadyState=row.__ukCategoryReadyState?.key===key?{key,count:row.__ukCategoryReadyState.count+1}:{key,count:1};
 return row.__ukCategoryReadyState.count>=3;
}

export function ukCategoryPathVisible(selected){
 const block=document.querySelector('.el-form-item#product-attr-product_type');
 return Boolean(block?.getBoundingClientRect().width&&block.innerText.replace(/\s+/g,' ').includes(selected.text));
}

async function prepareUkPage(page,input,record,persist){
 const t=preparationTarget(input),url='https://www.junfeikuajing.com/#/amazon/product/'+record.draftId+'?type=draft';if(await page.url()===url)await page.reload();else await page.goto(url);
 await page.waitForSelector('input[placeholder="店铺"]',{state:'visible'});
 await page.waitForFunction(expected=>expected.stores.includes(document.querySelector('input[placeholder="店铺"]')?.value)&&document.querySelector('input[placeholder="产品标题"]')?.value===expected.title,{stores:[input.store,t.storeName],title:input.goods.title},{timeout:20000});
 const meta=await observeUkSchemaPreparation(page,input,record,persist,async()=>{
  const store=await page.evaluate(()=>document.querySelector('input[placeholder="店铺"]')?.value);
  if(store!==input.store&&store!==t.storeName)throw Error('复制草稿属于未知店铺，不覆盖');
  if(store!==t.storeName){await page.click('input[placeholder="店铺"]');await page.waitForFunction(label=>[...document.querySelectorAll('.el-select-dropdown li')].some(e=>e.getBoundingClientRect().width&&e.innerText.trim()===label),t.storeName,{timeout:10000});await pickOption(page,t.storeName,'input[placeholder="店铺"]');await page.waitForFunction(store=>document.querySelector('input[placeholder="店铺"]')?.value===store,t.storeName,{timeout:10000});}
  // Choosing a real UK category forces the country's schema, even when the
  // source category name happens to be identical.
  await openUkCategoryRecommendations(page);
  const readRecommendations=async browser=>{
   await browser.waitForFunction(()=>[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"] label.el-radio')].some(row=>row.getBoundingClientRect().width),undefined,{timeout:20000});
   return browser.evaluate(()=>{const d=[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].find(e=>e.getBoundingClientRect().width);return [...d.querySelectorAll('label.el-radio')].map((e,index)=>({index,text:e.innerText.split(/[\u3400-\u9fff]/)[0].replace(/[\uE000-\uF8FF]/g,' > ').replace(/\s+/g,' ').trim(),value:e.querySelector('input')?.value}));});
  };
  let candidates=await readRecommendations(page),recommendationTitle=input.goods.title;
  const targetPath=t.categoryHints?.path,sourceTitle=input.destination.categoryHints?.title||input.categoryHints?.title;
  if(targetPath&&sourceTitle&&!sameCategoryPath(sourceTitle,input.goods.title)&&
     !candidates.some(row=>sameCategoryPath(row.text,targetPath))){
   recommendationTitle=sourceTitle;
   candidates=await requestRecommendationsForSourceTitle(page,sourceTitle,input.goods.title,readRecommendations);
  }
  const selected=await chooseUkRecommendedCategory(candidates,input,record,persist,recommendationTitle);
  const selector=await page.evaluate(selected=>{const d=[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].find(e=>e.getBoundingClientRect().width);const e=d?.querySelectorAll('label.el-radio')[selected.index],text=e?.innerText.split(/[\u3400-\u9fff]/)[0].replace(/[\uE000-\uF8FF]/g,' > ').replace(/\s+/g,' ').trim();if(!e||e.querySelector('input')?.value!==selected.value||text!==selected.text)throw Error('英国类目列表或节点变化');e.setAttribute('data-uk-category','true');e.scrollIntoView({block:'center',inline:'nearest'});return '[data-uk-category]';},selected);
  await page.click(selector);
  await page.waitForFunction(ukCategoryRadioReady,selected,{timeout:10000});
  record.categorySelectionObservation={value:selected.value,text:selected.text,radioChecked:true,observedAt:new Date().toISOString()};await persist();
  await page.click('[role=dialog][aria-label="亚马逊产品类型推荐"] .el-dialog__footer button:has-text("确定")');
  await page.waitForFunction(ukCategoryPathVisible,selected,{timeout:10000});
  record.categorySelectionObservation.visiblePathVerifiedAt=new Date().toISOString();await persist();
 });
 record.schemaObservation=clone(meta);await persist();
 const prepared=makeUkInput(input,record.draftId,meta);
 await page.evaluate(p=>{const set=(e,v)=>{if(!e)throw Error('英国字段缺失');Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,String(v));e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};set(document.querySelector('input[placeholder="品牌"]'),p.goods.brand);set(document.querySelector('input[placeholder="处理时间"]'),p.handlingDays);},prepared);
 const shipping=await ukShippingSelector(page);
 await page.evaluate(selector=>{const e=document.querySelector(selector);if(!e)throw Error('英国运输模板控件变化');e.scrollIntoView({block:'center',inline:'nearest'});},shipping);
 await page.click(shipping);await page.waitForFunction(name=>[...document.querySelectorAll('.el-select-dropdown li')].some(e=>e.getBoundingClientRect().width&&e.innerText.trim()===name),t.shippingTemplate.name,{timeout:10000});await pickOption(page,t.shippingTemplate.name,shipping);
 const exemption=await ensureUkBrandExemption(page,prepared,record,persist,{schemaObservation:meta});
 if(!prepared.destination.marketId)prepared.destination.marketId=exemption.nativeMarketId;
 return {meta,prepared,ui:await readUkPage(page,prepared)};
}

export async function prepareUkDraft(page,input,record,persist,adapters={}){
 validateUkInputs(input);const api={read:readPersistedDraft,prepare:prepareUkPage,save:saveDraft,ui:readUkPage,remote:verifyRemoteAsset,validate:validateSchemaAttributes,...adapters};
 if(!record.draftId||!record.sourceEvidence||!record.urls)throw Error('缺少原复制回执及已核对源图，禁止新建或重传');
 const imageHashes=async prepared=>{const unique=new Map();for(const a of prepared.assets)unique.set(a.sha256,a);record.imageChecks=[];for(const [sha256,asset]of unique){const remote=await api.remote(record.urls[sha256],asset);if(remote.sha256!==sha256||!(remote.bytes>0))throw Error('英国复制图片原文件哈希不符');record.imageChecks.push({sha256,url:record.urls[sha256],remote});await persist();}};
 const urls=record.urls,source=record.sourceEvidence.data||record.sourceEvidence;
 const validateAttributes=async(meta,records,prepared,field)=>{
  try{
   const proof=await api.validate(meta,records,prepared);
   if(!proof?.passed||proof.checkedCount!==records.length||proof.schemaHash!==meta?.hash)throw Error('英国真实schema校验未返回完整通过证明');
   record[field]=proof;await persist();
  }catch(error){if(error.schemaValidation){record[field]=error.schemaValidation;await persist();}throw error;}
 };
 const rawAttributeRecords=(response,prepared)=>[{id:prepared.goods.parentSku,attributes:response.data?.extra?.attributes},
  ...response.data.items.map(row=>({id:row.sku,attributes:row.extra?.attributes}))];
 const validateSavedAttributes=(meta,response,prepared)=>{
  const rows=rawAttributeRecords(response,prepared),target=prepared.destination;
  const values=rows.flatMap(({id,attributes})=>{
   const evidence=record.requiredAttributeEvidence?.[id]?.material;
   if(evidence?.source!==materialEvidenceSource)return [];
   const raw=attributes?.material,observed=Array.isArray(raw)?raw.map(entry=>({value:entry?.value??null,
    languageTag:entry?.language_tag??null,marketplaceId:entry?.marketplace_id??null})):null;
   const [single]=observed||[];
   const matches=observed?.length===1&&single.value===evidence.value&&
    single.languageTag===target.languageTag&&single.marketplaceId===target.marketplaceId;
   const status=raw==null||observed?.length===0?'missing':matches?'matched':'different';
   return [[id,{status,expectedValue:evidence.value,observed}]];
  });
  // This records the existing readback. The existing schema proof governs Save.
  if(values.length)record.materialReadback={observedAt:new Date().toISOString(),bySku:Object.fromEntries(values)};
  return validateAttributes(meta,rows,prepared,'schemaValidationAfterSave');
 };
 if(source.sku!==input.goods.parentSku||source.country_code!=='US'||String(source.market_id)!==String(input.destination.marketId)||source.items?.length!==input.goodsItems.length||new Set(source.items.map(r=>r.sku)).size!==source.items.length||source.items.some(row=>!input.goodsItems.some(v=>v.sku===row.sku)))throw Error('复制来源与美国正式父子SKU快照不符');
 const sourceFields=input.destination.variationFields||{color:'color.0.value',size:'apparel_size.0.size'};
 for(const v of input.goodsItems){const row=source.items.find(r=>r.sku===v.sku),size=input.destination.sizeValues?.[v.size]??v.size;
  if(rawValue(row,sourceFields.color)!==v.color||rawValue(row,sourceFields.size)!==size)throw Error('美国来源SKU的原颜色尺码不符：'+v.sku);
  const images=v.imageIndices.map(i=>urls[input.assets[i]?.sha256]),own=row.extra?.images??row.images;
  const inherited=own==null||(Array.isArray(own)&&own.length===0),actualImages=inherited?source.extra?.images??source.images:own;
  if(images.some(u=>!u)||row.main_image!==images[0]||JSON.stringify(actualImages)!==JSON.stringify(images))throw Error('美国来源逐SKU原图序未核实：'+v.sku);
 }
 const actual=await api.read(page,record.draftId);
 if(record.phase==='uk_draft_verified'||record.saveIntendedAt||record.requestSent){
  // An uncertain Save is always reconciled against this exact draft. Failure
  // to prove it does not authorize another Save, copy or upload.
  if(!record.preparedInput)throw Error('上次英国保存待对账，保留原草稿不重复提交');
  const p=record.preparedInput;
  if(p.store!==input.ukTarget.storeName||p.goods.parentSku!==input.goods.parentSku||p.goodsItems.length!==input.goodsItems.length||p.goodsItems.some(v=>!input.goodsItems.some(s=>s.sku===v.sku&&s.color===v.color&&s.size===v.size)||Number(v.price)!==Number(input.ukCommerce.variantPrices[v.sku])||Number(v.quantity)!==Number(input.ukCommerce.quantities[v.sku]))||Number(p.handlingDays)!==Number(input.ukCommerce.handlingDays))throw Error('英国保存回执与当前产品输入不同，保留原草稿待对账');
  if(!record.preparedInput.destination.marketId&&String(actual.data?.market_id)!==String(input.destination.marketId))record.preparedInput.destination.marketId=String(record.submitted?.market_id??actual.data.market_id);
  const ui=await api.ui(page,record.preparedInput);verifyUkUi(ui,record.preparedInput);
  if(!record.preparedInput.destination.shippingTemplate.id)record.preparedInput.destination.shippingTemplate.id=record.submitted?.attributes?.merchant_shipping_group?.[0]?.value??actual.data?.extra?.attributes?.merchant_shipping_group?.[0]?.value;
  record.verification=verifyUkDraft(actual,record.preparedInput,urls,ui);
  if(!record.schemaObservation)throw Error('原英国保存缺少真实schema证明，仅保留原草稿待对账');
  await validateSavedAttributes(record.schemaObservation,actual,p);
  await imageHashes(record.preparedInput);record.phase='uk_draft_verified';record.reconciledAt=new Date().toISOString();await persist();return record;
 }
 const rows=actual.data?.items;
 if(actual.code!==0||String(actual.data?.id)!==String(record.draftId)||![input.store,input.ukTarget.storeName].includes(actual.data?.market?.alias)||String(actual.data?.uid)!==String(input.destination.erpUserId))throw Error('复制草稿或ERP账号身份不符');
 const sourceIdentifiers=extractSourceIdentifiers(source);
 const staged=await api.prepare(page,input,record,persist),p=staged.prepared;
 p.sourceIdentifiers=sourceIdentifiers;
 record.schemaObservation=clone(staged.meta);await persist();
 verifyUkUi(staged.ui,p);
 if(!p.destination.shippingTemplate.id)p.destination.shippingTemplate.id=String(staged.ui.shippingTemplateId);
 const mapping=restoreSkuMapping(rows,input,p.destination);
 for(const row of mapping){const v=input.goodsItems.find(v=>v.sku===row.sku),expected=v.imageIndices.map(i=>urls[input.assets[i].sha256]),raw=row.extra?.images??row.images,images=raw==null||(Array.isArray(raw)&&!raw.length)?actual.data.extra?.images??actual.data.images:raw;
  if(row.main_image!==expected[0]||JSON.stringify(images)!==JSON.stringify(expected))throw Error('原复制草稿逐SKU图序已变化，保留待核对：'+v.sku);}
 record.skuCorrection=mapping.map(row=>({itemId:row.id,originalCopiedSku:rows.find(r=>String(r.id)===String(row.id)).sku,sourceSku:row.sku,variation:row.variation}));
 // The selected native ElSelect value proves this UK template's ID before
 // validation. The Save hook rechecks its actual request against that value.
 const targetProperties=schemaObject(staged.meta).properties,brandDefinition=targetProperties?.brand?.items?.properties;
 if(!brandDefinition?.value||!brandDefinition.language_tag||!brandDefinition.marketplace_id||
    (brandDefinition.value.enum&&!brandDefinition.value.enum.includes(p.goods.brand))||
    (brandDefinition.value.maxLength&&p.goods.brand.length>brandDefinition.value.maxLength)||
    !targetProperties?.variation_theme?.items?.properties?.name?.enum?.includes(p.destination.themeValue))throw Error('英国真实schema未支持已核实品牌或变体主题');
 const targetIdentityAttributes={brand:[{value:p.goods.brand,language_tag:p.destination.languageTag,marketplace_id:p.destination.marketplaceId}],variation_theme:[{name:p.destination.themeValue}]};
 const migrateSourceAttributes=(attributes,sku)=>{
  // These two values come from the verified UK editor/schema. Exclude their
  // US forms before validating the remaining source facts against UK enums.
  const {brand,variation_theme,main_product_image_locator,...facts}=attributes||{};
  const migrated={...migrateAttributes(facts,staged.meta,input.destination,p.destination),...clone(targetIdentityAttributes)};
  record.requiredAttributeEvidence??={};
  try{const supplemented=supplementUkRequiredAttributes(migrated,input,staged.meta,p,record.categoryChoice);record.requiredAttributeEvidence[sku]=supplemented.evidence;return supplemented.attributes;}
  catch(error){if(error.ukRequiredAttributeEvidence)record.requiredAttributeEvidence[sku]=error.ukRequiredAttributeEvidence;throw error;}
 };
 let parentAttrs;const itemAttrs={};
 try{parentAttrs=migrateSourceAttributes(source.extra?.attributes||source.attributes,p.goods.parentSku);
  for(const v of p.goodsItems){const s=source.items.find(r=>r.sku===v.sku);const attrs=migrateSourceAttributes(s.extra?.attributes||s.attributes,v.sku);for(const [field,value]of [[p.destination.variationFields.color,v.color],[p.destination.variationFields.size,p.destination.sizeValues[v.size]]]){const [key,,leaf]=field.split('.');if(!attrs[key]?.length)attrs[key]=[{}];attrs[key][0][leaf]=value;attrs[key][0].marketplace_id=p.destination.marketplaceId;}itemAttrs[v.sku]=attrs;}
 }catch(error){record.requiredAttributeError=String(error.message);await persist();throw error;}
 const shipping=[{value:p.destination.shippingTemplate.id,marketplace_id:p.destination.marketplaceId}];
 Object.assign(parentAttrs,{fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:0,lead_time_to_ship_max_days:Number(p.handlingDays)}],
  merchant_shipping_group:clone(shipping),supplier_declared_has_product_identifier_exemption:[{value:true}]});
 for(const v of p.goodsItems)Object.assign(itemAttrs[v.sku],{supplier_declared_has_product_identifier_exemption:[{value:true}],merchant_shipping_group:clone(shipping),
  fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:Number(v.quantity),lead_time_to_ship_max_days:Number(p.handlingDays)}]});
 if(p.destination.requireMainImageLocator===true){
  const main=v=>{const url=urls[p.assets[v.imageIndices[0]]?.sha256];if(!url)throw Error('英国原子SKU主图映射缺失：'+v.sku);return[{media_location:url,marketplace_id:p.destination.marketplaceId}];};
  const first=p.goodsItems.find(v=>v.color===p.masterColor)||p.goodsItems[0];parentAttrs.main_product_image_locator=main(first);
  for(const v of p.goodsItems)itemAttrs[v.sku].main_product_image_locator=main(v);
 }
 // The hook must match the independently observed selected template ID;
 // neither schema validation nor Save may import the US shipping ID.
 const wire={...clone(input),ukPrepared:p,ukCopiedRows:mapping,ukParentAttributes:parentAttrs,ukItemAttributes:itemAttrs};
 await validateAttributes(staged.meta,[{id:p.goods.parentSku,attributes:parentAttrs},...p.goodsItems.map(v=>({id:v.sku,attributes:itemAttrs[v.sku]}))],p,'schemaValidationBeforeSave');
 record.preparedInput=p;record.schemaProof={country:staged.meta.country_code,productType:staged.meta.product_type_name,hash:staged.meta.hash};record.phase='uk_save_unknown';await persist();
 await api.save(page,wire,urls,record,persist,patchUkDraftPayload);
 p.destination.marketId=String(record.submitted.market_id);
 p.destination.shippingTemplate.id=record.submitted.attributes?.merchant_shipping_group?.[0]?.value;
 if(!p.destination.shippingTemplate.id)throw Error('英国实际运输模板ID未保存，需核对原草稿');
 record.preparedInput=p;await persist();
 const reopened=await api.read(page,record.draftId),ui=await api.ui(page,p);record.verification=verifyUkDraft(reopened,p,urls,ui);
 await validateSavedAttributes(staged.meta,reopened,p);
 await imageHashes(p);
 record.phase='uk_draft_verified';record.verifiedAt=new Date().toISOString();await persist();return record;
}
