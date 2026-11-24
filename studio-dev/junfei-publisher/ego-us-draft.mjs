// Complete the original US draft using the actual schema and frozen facts.
// Saves and exemption applications have durable intents; no draft is created.
import {schemaVariation} from './ego-collection-prepare.mjs';
import {readPersistedDraft,verifyPersistedDraft,assertMainImageLocatorSchema} from './ego-draft-readback.mjs';
import {saveDraft} from './ego-draft-save.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';
import {coatProductAttributes} from './ego-coat-attributes.mjs';

const clone=v=>structuredClone(v);
const schemaOf=meta=>typeof meta.schema_content==='string'?JSON.parse(meta.schema_content):meta.schema_content;
export function assertUsPreparedIdentity(input,p){
 const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 for(const key of ['accountId','productId','sha256','jobId','store','marketplace','mode','masterColor','handlingDays'])if(!eq(input[key],p?.[key]))throw Error('美国完善回执原身份不符 '+key);
 for(const key of ['destinationId','draftId','marketId','marketplaceId','erpAccountId','erpUserId','countryCode','browserBinding','page'])if(!eq(input.destination?.[key],p?.destination?.[key]))throw Error('美国完善回执原店铺站点不符 '+key);
 const {brand:originalBrand,...originalGoods}=input.goods,{brand:preparedBrand,...preparedGoods}=p.goods||{};
 if(!preparedBrand||!eq(originalGoods,preparedGoods)||!eq(input.goodsItems,p.goodsItems)||!eq(input.assets,p.assets)||!eq(input.urls,p.urls)||!eq(input.publicationFacts,p.publicationFacts))throw Error('美国完善回执原商品、素材或事实变化');
 return p;
}
export function makeUsPreparedInput(input,meta,brand){
 const schema=schemaOf(meta),d=input.destination;
 if(input.marketplace!=='US'||d.countryCode!=='US'||meta.country_code!=='US'||meta.locale!=='en_US'||!meta.hash||schema?.$defs?.marketplace_id?.default!==d.marketplaceId)throw Error('美国原草稿类目schema与站点不符');
 if(!/^[A-Z]{2}$/.test(input.publicationFacts?.countryOfOrigin||''))throw Error('请在产品资料保存实际原产国，再继续原发布任务');
 if(!brand||brand.length>50)throw Error('未取得本店铺实际同步品牌');
 assertMainImageLocatorSchema(meta,d.marketplaceId);
 const prepared={...clone(input),goods:{...clone(input.goods),brand},destination:{...clone(d),...schemaVariation(meta,input.goodsItems),requireMainImageLocator:true}};
 const sizeKey=prepared.destination.variationFields.size.split('.')[0],definition=schema.properties[sizeKey]?.items?.properties;
 if(input.publicationFacts?.specialSizeType==='Standard')for(const key of ['body_type','height_type']){
  const p=definition?.[key];if(!p)continue;
  const standardMeaning=/no special/i.test(p.description||'')||(key==='body_type'&&/select\s+["']?regular["']?\s+for\s+standard sizing/i.test(p.description||''));
  if(!p.enum?.includes('regular')||!standardMeaning)throw Error('实际schema未提供普通款尺码分类依据 '+key);
  prepared.destination.sizeAttributes[key]='regular';prepared.destination.sizeAttributeSchema.properties[key]={type:p.type,enum:['regular']};
  if(!prepared.destination.sizeAttributeSchema.required.includes(key))prepared.destination.sizeAttributeSchema.required.push(key);
 }
 return prepared;
}

export function usProductAttributes(input,meta){
 const schema=schemaOf(meta),d=input.destination,language=d.languageTag,market=d.marketplaceId;
 const localized=(key,value)=>{const p=schema.properties?.[key]?.items?.properties;if(!p?.value)throw Error('美国schema缺少商品属性 '+key);const v=p.value;if(v.enum&&!v.enum.includes(value))throw Error('商品属性不在美国实际枚举中 '+key);if(typeof value==='string'&&v.maxLength&&value.length>v.maxLength)throw Error('商品属性超长 '+key);return{value,...(p.language_tag?{language_tag:language}:{}),...(p.marketplace_id?{marketplace_id:market}:{})};};
 const description=input.goods.description.replace(/<br\s*\/?\s*>/gi,'\n').replace(/\r\n/g,'\n'),materials=description.split('\n').filter(x=>/^Material:/i.test(x));
 if(materials.length!==1||!materials[0].replace(/^Material:\s*/i,'').trim())throw Error('冻结商品描述缺少唯一材质事实，不能沿用ERP旧模板');
 const fabric=materials[0].replace(/^Material:\s*/i,'').trim();
 const facts=input.publicationFacts||{};
 if(!facts.careInstructions||!facts.modelName||!facts.itemCondition||!facts.specialSizeType)throw Error('本款护理、真实型号、商品状态或尺码分类资料不完整');
 const attrs={fabric_type:[localized('fabric_type',fabric)],country_of_origin:[localized('country_of_origin',facts.countryOfOrigin)],
  supplier_declared_has_product_identifier_exemption:[{value:true,marketplace_id:market}],
  fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',lead_time_to_ship_max_days:Number(input.handlingDays)}]};
 for(const [key,value]of [['brand',input.goods.brand],['item_name',input.goods.title],['product_description',input.goods.description],['care_instructions',facts.careInstructions],['model_name',facts.modelName],['condition_type',facts.itemCondition],['special_size_type',facts.specialSizeType]])if(schema.properties?.[key])attrs[key]=[localized(key,value)];
 if(facts.waterResistanceLevel!==undefined&&facts.waterResistanceLevel!==null&&facts.waterResistanceLevel!==''&&schema.properties?.water_resistance_level)attrs.water_resistance_level=[localized('water_resistance_level',facts.waterResistanceLevel)];
 if(schema.properties?.bullet_point)attrs.bullet_point=input.goods.bullets.map(value=>localized('bullet_point',value));
 if(facts.countryOfOrigin!=='US'&&schema.properties?.import_designation)attrs.import_designation=[localized('import_designation','Imported')];
 // The actual schema explicitly permits zero when no supported list price exists.
 if(schema.properties?.list_price){const def=schema.properties.list_price.items?.properties?.value;if(!/enter\s+0/i.test(def?.description||''))throw Error('缺少有依据的美国参考价，实际schema未允许未知值0');attrs.list_price=[{currency:'USD',value:0,marketplace_id:market}];}
 const line=label=>{const matches=description.split('\n').filter(x=>x.startsWith(label+':'));return matches.length===1?matches[0].slice(label.length+1).trim():'';};
 const style=line('Style'),neck=line('Neckline'),sleeves=line('Sleeves');
 if(meta.product_type_name==='SHIRT'){
  // Use unique, explicit frozen product lines, rather than guessing a fit
  // from a marketing title or reusing another product's template attributes.
  const permits=(definition,value)=>{
   const choices=definition?.enum??definition?.anyOf?.flatMap(branch=>branch.enum??[])??[];
   return choices.length?choices.includes(value):definition?.type==='string';
  };
  const fit=/^(Relaxed|Regular|Fitted|Slim|Oversized)(?: fit)?$/i.exec(line('Fit'));
  if(fit&&schema.properties?.fit_type){
   const value=fit[1][0].toUpperCase()+fit[1].slice(1).toLowerCase();
   if(!permits(schema.properties.fit_type.items?.properties?.value,value))throw Error('明确版型不在美国实际schema中');
   attrs.fit_type=[localized('fit_type',value)];
  }
  if(/^Long(?: sleeves?)?$/i.test(sleeves)&&schema.properties?.sleeve){
   const p=schema.properties.sleeve.items?.properties;
   const evidence=input.usPreparation?.sleeveType;
   if(evidence&&(evidence.value!=='Cuff Sleeve'||evidence.source!=='bound_supplier_photo_review'||evidence.reviewerType!=='agent'||
     evidence.humanReviewed!==false||evidence.sourceUrl!==facts.supplierModelNumberEvidence?.sourceUrl||
     evidence.sourceUrl!==input.goods.sourceUrl||!/^\/uploads\/[a-zA-Z0-9_-]+\.(png|jpg|jpeg|webp)$/.test(evidence.referenceImage||'')||
     !/^[a-f0-9]{64}$/.test(evidence.referenceSha256||'')||!evidence.observations))throw Error('袖型缺少同款已核实供货照片依据');
   const sleeveType=evidence?.value||'Long Sleeve';
   if(!permits(p?.type?.items?.properties?.value,sleeveType))throw Error('明确长袖不在美国实际schema中');
   const value={type:[{value:sleeveType,language_tag:language}],marketplace_id:market};
   if(p.length_description){
    if(!permits(p.length_description.items?.properties?.value,'long_sleeve'))throw Error('明确袖长不在美国实际schema中');
    value.length_description=[{value:'long_sleeve'}];
   }
   attrs.sleeve=[value];
  }
 }
 if(meta.product_type_name==='PANTS'){
  // Preserve the unique explicit style from the frozen listing for all pants.
  // A button-front or other construction still has a required style field.
  if(style&&schema.properties?.style)attrs.style=[localized('style',style)];
  const nested=(field,part,value)=>{
   const p=schema.properties?.[field]?.items?.properties, v=p?.[part]?.items?.properties?.value;
   const choices=v?.enum??v?.anyOf?.flatMap(branch=>branch.enum??[])??[];
   if(!choices.includes(value)||!p[part].items.properties.language_tag||!p.marketplace_id)throw Error('美国裤装实际类目不支持 '+field);
   return [{[part]:[{value,language_tag:language}],marketplace_id:market}];
  };
  if(/\bpull-on pants\b/i.test(style)&&/^Elastic$/i.test(line('Waist'))){
   if(schema.properties?.closure)attrs.closure=nested('closure','type','Pull On');
   if(schema.properties?.style)attrs.style=[localized('style',style)];
  }
  if(schema.properties?.leg?.items?.properties?.style){
   // Amazon can reject a missing leg style after accepting the ERP draft.
   const explicit=[...description.matchAll(/^Leg style:[ \t]*(\S[^\n]*)$/gim)].map(([,cut])=>cut);
   const styles=[...description.matchAll(/^Style:[ \t]*([^\n]*)$/gim)].map(([,value])=>value);
   const inferred=styles.flatMap(value=>[...value.matchAll(/\b(wide|straight|tapered|skinny|flared|boot[- ]cut)[- ]leg\b/gi)].map(([,cut])=>cut));
   const labels=new Set([...explicit,...inferred].map(cut=>cut.trim().toLowerCase().replace(/-/g,' ').replace(/ +leg$/,'')));
   if(labels.size!==1)throw Error('美国裤装缺少唯一已核实的腿型，请补齐同款供货资料再发布');
   const label=[...labels][0].replace(/\b\w/g,letter=>letter.toUpperCase());
   attrs.leg=nested('leg','style',label);
  }
  const closureDefault=facts.closureTypeEvidence;
  if(!attrs.closure&&closureDefault?.source==='user_configured_defaults'&&closureDefault.productId===input.productId&&
     closureDefault.scope==='missing_catalogue_attribute_only'&&closureDefault.value==='Button'&&closureDefault.supplierVerified===false&&
     typeof closureDefault.instruction==='string'&&closureDefault.instruction.trim()&&closureDefault.configuredAt){
   attrs.closure=nested('closure','type',closureDefault.value);
  }
  const amendment=input.usPreparation?.pantsRise||facts.riseTypeEvidence;
  if(amendment){
   const supported={'高腰':'High Rise','中腰':'Mid Rise','低腰':'Low Rise'};
   if(amendment.sourceUrl!==facts.supplierModelNumberEvidence?.sourceUrl||amendment.field!=='腰型'||
      !Object.hasOwn(supported,amendment.sourceValue)||supported[amendment.sourceValue]!==amendment.value)throw Error('美国裤装腰型缺少同一货源证据');
   attrs.rise=nested('rise','style',amendment.value);
  }
 }
 if(meta.product_type_name==='SKIRT'){
  // Use the skirt's frozen construction, rather than a stale clothing template.
  if(style&&schema.properties?.style)attrs.style=[localized('style',style)];
  if(/\bmini skirt\b/i.test(style)&&schema.properties?.item_length_description)attrs.item_length_description=[localized('item_length_description','Mini')];
  const evidence=input.usPreparation?.skirtFacts;
  if(evidence){
   const choices={'高腰':'High Rise','中腰':'Mid Rise','低腰':'Low Rise'};
   if(evidence.source!=='bound_supplier_catalogue_facts'||evidence.humanReviewed!==false||!evidence.retrievedAt||
      evidence.sourceUrl!==input.goods.sourceUrl||evidence.sourceUrl!==facts.supplierModelNumberEvidence?.sourceUrl||
      evidence.supplierModelNumber!==facts.supplierModelNumber||evidence.rise?.path!=='sourceImport.supplier.title'||
      choices[evidence.rise?.sourceValue]!==evidence.rise?.value||
      !evidence.rise?.sourceText?.includes(evidence.rise.sourceValue)||
      Object.keys(choices).filter(k=>evidence.rise.sourceText.includes(k)).length!==1||
      evidence.pattern?.path!=='sourceImport.supplier.attributes.图案'||evidence.pattern?.sourceValue!=='纯色'||evidence.pattern?.value!=='Solid')
    throw Error('短裙属性缺少同款货源原始标题/属性依据');
   const p=schema.properties.rise?.items?.properties,v=p?.style?.items?.properties?.value;
   if(!(v?.enum??v?.anyOf?.flatMap(b=>b.enum??[])??[]).includes(evidence.rise.value))throw Error('短裙腰型不在真实schema中');
   attrs.rise=[{style:[{value:evidence.rise.value,language_tag:language}],marketplace_id:market}];
   attrs.pattern=[localized('pattern',evidence.pattern.value)];
  }
  if(/^Visible side zipper$/i.test(line('Closure'))&&schema.properties?.closure){
   const p=schema.properties.closure.items?.properties,v=p?.type?.items?.properties?.value;
   const choices=v?.enum??v?.anyOf?.flatMap(branch=>branch.enum??[])??[];
   if(!choices.includes('Zipper'))throw Error('美国短裙实际类目不支持已核实的拉链闭合');
   attrs.closure=[{type:[{value:'Zipper',language_tag:language}],marketplace_id:market}];
  }
  if(schema.properties?.supplier_declared_dg_hz_regulation&&
     facts.waterResistanceLevelSource?.basis?.classification==='ordinary_apparel'&&
     /^\d+%\s*polyester,\s*\d+%\s*(?:spandex|elastane)$/i.test(fabric))
   attrs.supplier_declared_dg_hz_regulation=[localized('supplier_declared_dg_hz_regulation','not_applicable')];
 }
 if(/pullover/i.test(style)&&schema.properties?.style)attrs.style=[localized('style','Pullover')];
 const hoodedHalfZip=/\bhooded pullover\b/i.test(style)&&/^Half[- ]zip$/i.test(line('Closure'))&&/^Drawstring(?: hood)?$/i.test(line('Hood'));
 const halfZip=/\bhalf[- ]zip\b/i.test(style)||hoodedHalfZip;
 const fauxSuedeButtonPullover=/^Four-button half placket$/i.test(line('Front'))&&/\bpullover\b/i.test(style)&&
  /^Faux suede made with polyester and elastane$/i.test(fabric);
 if(meta.product_type_name==='SWEATSHIRT'&&(halfZip||fauxSuedeButtonPullover)){
  const permits=(definition,value)=>(definition?.enum??definition?.anyOf?.flatMap(branch=>branch.enum??[])??[]).includes(value);
  const neckStyle=schema.properties?.neck?.items?.properties?.neck_style?.items?.properties?.value;
  const fitStyle=schema.properties?.fit_type?.items?.properties?.value;
  if(/^(?:Tall )?stand collar$/i.test(line('Collar'))&&permits(neckStyle,'Collared Neck'))attrs.neck=[{neck_style:[{value:'Collared Neck',language_tag:language}],marketplace_id:market}];
  if(hoodedHalfZip&&permits(neckStyle,'Hooded Neck'))attrs.neck=[{neck_style:[{value:'Hooded Neck',language_tag:language}],marketplace_id:market}];
  if(halfZip&&/\bregular[- ]cut\b/i.test(style)&&permits(fitStyle,'Regular'))attrs.fit_type=[localized('fit_type','Regular')];
  if((fauxSuedeButtonPullover||hoodedHalfZip)&&/\brelaxed[- ]fit\b/i.test(style)&&permits(fitStyle,'Relaxed'))attrs.fit_type=[localized('fit_type','Relaxed')];
  if(schema.properties?.supplier_declared_dg_hz_regulation&&facts.waterResistanceLevelSource?.basis?.classification==='ordinary_apparel'&&
     (fauxSuedeButtonPullover||(halfZip&&/^\d+%\s*polyester,\s*\d+%\s*(?:spandex|elastane)$/i.test(fabric))))
   attrs.supplier_declared_dg_hz_regulation=[localized('supplier_declared_dg_hz_regulation','not_applicable')];
 }
 if(meta.product_type_name==='SWEATER'){
  // A frozen Fit line may describe the pullover when no Style line exists.
  // Keep this source-bound classification separate from supplier certification.
  const blend=fabric.match(/^(\d+)%\s*polyester,\s*(\d+)%\s*(?:spandex|elastane)$/i);
  const ribbedCowlPullover=!style&&/^Loose pullover shape$/i.test(line('Fit'))&&
   /^Fine vertical ribbing$/i.test(line('Texture'))&&/^Deep draped cowl$/i.test(neck)&&
   /\bcowl neck\b/i.test(input.goods.title)&&/\bpullover\b/i.test(input.goods.title)&&
   blend&&Number(blend[1])+Number(blend[2])===100&&Number(blend[1])>50&&
   /^https:\/\/detail\.1688\.com\/offer\/\d+\.html$/.test(input.goods.sourceUrl||'')&&
   facts.supplierModelNumberEvidence?.source==='supplier_attribute'&&
   facts.supplierModelNumberEvidence.sourceUrl===input.goods.sourceUrl&&
   Boolean(facts.supplierModelNumber)&&facts.supplierModelNumberEvidence.value===facts.supplierModelNumber;
  if(ribbedCowlPullover&&schema.properties?.style)attrs.style=[localized('style','Cowl Neck Ribbed Pullover')];
  const knitCardigan=/\bcardigan\b/i.test(input.goods.title)&&/^Knit$/i.test(line('Texture'))&&/\bbuttons\b/i.test(line('Front closure'));
  const knitPullover=/\bpullover\b/i.test(style)&&/^Polyester-rich rib knit$/i.test(fabric)&&
   facts.weaveTypeEvidence?.value==='Knit'&&facts.weaveTypeEvidence?.source==='supplier_attribute'&&
   Boolean(facts.supplierModelNumberEvidence?.sourceUrl)&&facts.weaveTypeEvidence.sourceUrl===facts.supplierModelNumberEvidence.sourceUrl;
  // Ordinary acrylic knitwear classification from the frozen, source-bound
  // composition and Style line; this is not a supplier certification.
  const acrylicPullover=/^100%\s*acrylic$/i.test(fabric)&&/\bknitted\s+pullover\b/i.test(style)&&
   /^https:\/\/detail\.1688\.com\/offer\/\d+\.html$/.test(input.goods.sourceUrl||'')&&
   facts.supplierModelNumberEvidence?.source==='supplier_attribute'&&
   facts.supplierModelNumberEvidence.sourceUrl===input.goods.sourceUrl&&
   Boolean(facts.supplierModelNumber)&&facts.supplierModelNumberEvidence.value===facts.supplierModelNumber;
  if(knitCardigan&&schema.properties?.style)attrs.style=[localized('style','Button-Front Knit Cardigan')];
  if(schema.properties?.supplier_declared_dg_hz_regulation&&((knitCardigan&&/^Polyester$/i.test(fabric))||knitPullover||acrylicPullover||ribbedCowlPullover)&&
     facts.waterResistanceLevelSource?.basis?.classification==='ordinary_apparel'){
   attrs.supplier_declared_dg_hz_regulation=[localized('supplier_declared_dg_hz_regulation','not_applicable')];
  }
 }
 if(/\bfitted\b/i.test(style)&&schema.properties?.fit_type)attrs.fit_type=[localized('fit_type','Fitted')];
 const corduroyTunic=meta.product_type_name==='SHIRT'&&/\bcorduroy\b/i.test(fabric)&&
  /\btunic\b/i.test(input.goods.title)&&/^Product: women['’]s\b[^\n]*\btunic\b/im.test(description);
 if(corduroyTunic){
  if(schema.properties?.style)attrs.style=[localized('style','Corduroy Tunic')];
  if(/^Relaxed$/i.test(line('Silhouette'))&&schema.properties?.fit_type)attrs.fit_type=[localized('fit_type','Relaxed')];
  const sleeveType=schema.properties?.sleeve?.items?.properties?.type?.items?.properties?.value;
  const sleeveChoices=sleeveType?.enum??sleeveType?.anyOf?.flatMap(branch=>branch.enum??[])??[];
  if(/\bbatwing\s+sleeves?\b/i.test(sleeves)&&sleeveChoices.includes('Batwing Sleeve')){
   attrs.sleeve=[{type:[{value:'Batwing Sleeve',language_tag:language}],marketplace_id:market}];
  }
 }
 if(/^crew neck$/i.test(neck)&&schema.properties?.neck)attrs.neck=[{neck_style:[{value:'Crew Neck',language_tag:language}],marketplace_id:market}];
 if(/^Long, with narrow cuff edges$/i.test(sleeves)&&schema.properties?.sleeve)attrs.sleeve=[{type:[{value:'Cuff Sleeve',language_tag:language}],length_description:[{value:'long_sleeve'}],marketplace_id:market}];
 // Use the explicit Women breadcrumb or the corroborated product description.
 const category=input.destination.categoryHints?.path||input.categoryHints?.path||'';
 if(/(?:^|>)\s*Women\s*(?:>|$)/i.test(category)||corduroyTunic){
  for(const [key,value]of [['department','Womens'],['target_gender','female'],['age_range_description','Adult']])if(schema.properties?.[key])attrs[key]=[localized(key,value)];
 }
 Object.assign(attrs,coatProductAttributes(input,meta));
 return attrs;
}

// Serialized by saveDraft: keep self contained and preserve native item IDs.
export function patchUsDraftPayload(body,wire,urls){
 const p=wire.usPrepared,d=p.destination;
 if(String(body.id)!==String(d.draftId)||String(body.market_id)!==String(d.marketId)||body.country_code!=='US'||body.sku!==p.goods.parentSku||body.with_publish||body.publish)throw Error('美国完善草稿身份或保存模式不符');
 if(!Array.isArray(body.items)||body.items.length!==p.goodsItems.length||new Set(body.items.map(r=>r.sku)).size!==p.goodsItems.length||body.items.some(r=>!p.goodsItems.some(v=>v.sku===r.sku)))throw Error('美国完善草稿原子SKU集合变化');
 const shipping=body.attributes?.merchant_shipping_group?.[0]?.value;
 if(!shipping||(d.shippingTemplate.id&&d.shippingTemplate.id!==shipping))throw Error('美国实际运输模板ID未核实');
 const attrs=wire.usProductAttributes;
 if(!attrs?.fabric_type?.[0]?.value||attrs.country_of_origin?.[0]?.value!==p.publicationFacts.countryOfOrigin)throw Error('美国商品材质或原产国事实缺失');
 const fields=d.variationFields,cp=fields.color.split('.'),sp=fields.size.split('.');
 const items=body.items.map(row=>{const v=p.goodsItems.find(v=>v.sku===row.sku),size=d.sizeValues[v.size],images=v.imageIndices.map(i=>urls[p.assets[i].sha256]);if(images.some(x=>!x)||images.length!==7)throw Error('美国原子SKU七图映射缺失');
  return{...row,attributes:{...structuredClone(attrs),...(d.requireMainImageLocator===true?{main_product_image_locator:[{media_location:images[0],marketplace_id:d.marketplaceId}]}:{}),merchant_shipping_group:[{value:shipping,marketplace_id:d.marketplaceId}],fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:Number(v.quantity),lead_time_to_ship_max_days:Number(p.handlingDays)}],parentage_level:[{value:'child',marketplace_id:d.marketplaceId}],child_parent_sku_relationship:[{parent_sku:p.goods.parentSku,child_relationship_type:'variation',marketplace_id:d.marketplaceId}],variation_theme:[{name:d.themeValue}],[cp[0]]:[{[cp[2]]:v.color,language_tag:d.languageTag,marketplace_id:d.marketplaceId}],[sp[0]]:[{[sp[2]]:size,...d.sizeAttributes,marketplace_id:d.marketplaceId}]},variation:{[fields.color]:v.color,[fields.size]:size},main_image:images[0],images};});
 const first=p.goodsItems.find(v=>v.color===p.masterColor)||p.goodsItems[0],cover=urls[p.assets[first.imageIndices[0]].sha256];
 return{...body,brand:p.goods.brand,manufacturer:p.goods.manufacturer,part_number:p.publicationFacts.supplierModelNumber||'',country_of_origin:p.publicationFacts.countryOfOrigin,items,images:[cover],main_image:cover,
  attributes:{...structuredClone(attrs),...(d.requireMainImageLocator===true?{main_product_image_locator:[{media_location:cover,marketplace_id:d.marketplaceId}]}:{}),fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',quantity:0,lead_time_to_ship_max_days:Number(p.handlingDays)}],skip_offer:[{value:true,marketplace_id:d.marketplaceId}],parentage_level:[{value:'parent',marketplace_id:d.marketplaceId}],child_parent_sku_relationship:[{child_relationship_type:'variation',marketplace_id:d.marketplaceId}],variation_theme:[{name:d.themeValue}],merchant_shipping_group:[{value:shipping,marketplace_id:d.marketplaceId}],...(p.goods.highlights?{title_differentiation:[{value:p.goods.highlights,language_tag:d.languageTag,marketplace_id:d.marketplaceId}]}:{})},with_publish:false,publish:false};
}

export function verifyUsPrepared(response,input,urls,attributes){
 const checks=verifyPersistedDraft(response,input,urls),d=response.data;
 const expected={...attributes,merchant_shipping_group:[{value:input.destination.shippingTemplate.id,marketplace_id:input.destination.marketplaceId}]};
 const contains=(actual,expected)=>expected&&typeof expected==='object'?actual&&typeof actual==='object'&&(!Array.isArray(expected)||actual.length===expected.length)&&Object.entries(expected).every(([k,v])=>contains(actual[k],v)):actual===expected;
 for(const [key,value]of Object.entries(expected))if(!contains(d.extra?.attributes?.[key],value))throw Error('美国持久商品属性不符 '+key);
 for(const row of d.items)for(const [key,value]of Object.entries(attributes))if(!contains(row.extra?.attributes?.[key],value))throw Error('美国子SKU商品属性不符 '+row.sku+' '+key);
 for(const row of d.items)if(!contains(row.extra?.attributes?.merchant_shipping_group,expected.merchant_shipping_group)||Number(row.extra?.attributes?.fulfillment_availability?.[0]?.quantity)!==Number(input.goodsItems.find(v=>v.sku===row.sku)?.quantity))throw Error('美国子SKU运输模板或库存属性不符 '+row.sku);
 return checks;
}

async function readUsSchema(page,input){
 const beforeOpen=()=>page.evaluate(()=>{if(window.__usPreparationSchema)throw Error('已有美国schema观察');const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__usPreparationSchema={open,send,data:null};XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.origin==='https://app.junfeikuajing.com'&&url.pathname==='/api/amazon/category/get-product-type');return open.call(this,m,u,...r);};XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{const r=JSON.parse(this.responseText);if(this.status===200&&r.code===0)window.__usPreparationSchema.data=r.data;}catch{}},{once:true});return send.call(this,b);};});
 try{const draft=await readPersistedDraft(page,input.destination.draftId,{beforeOpen});await page.waitForFunction(()=>window.__usPreparationSchema?.data,undefined,{timeout:20000});return{draft,meta:await page.evaluate(()=>window.__usPreparationSchema.data)};}
 finally{await page.evaluate(()=>{const s=window.__usPreparationSchema;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__usPreparationSchema;}});}
}

async function setNativeShipping(page,input,record,persist){
 await page.evaluate(()=>document.querySelector('input[placeholder="亚马逊运输模板"]').scrollIntoView({block:'center'}));await page.click('input[placeholder="亚马逊运输模板"]');
 await page.waitForFunction(()=>[...document.querySelectorAll('.el-select-dropdown li')].some(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible'),undefined,{timeout:10000});
 const options=await page.evaluate(()=>[...document.querySelectorAll('.el-select-dropdown li')].filter(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible').map(e=>e.innerText.trim()));
 const required=input.destination.shippingTemplate?.name,choices=required?options.filter(x=>x===required):options;
 if(choices.length!==1)throw Error('美国实际运输模板不唯一，请保存本店铺适用模板');
 record.shippingObservation={observedAt:new Date().toISOString(),options,selected:choices[0]};await persist();
 await page.focus('input[placeholder="亚马逊运输模板"]');
 for(let n=0;n<=options.length;n++){
  const hover=await page.evaluate(()=>[...document.querySelectorAll('.el-select-dropdown li.hover')].filter(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible').map(e=>e.innerText.trim()));
  if(hover.length===1&&hover[0]===choices[0]){await page.press('input[placeholder="亚马逊运输模板"]','Enter');await page.waitForFunction(name=>document.querySelector('input[placeholder="亚马逊运输模板"]')?.value===name,choices[0],{timeout:5000});const id=await page.evaluate(()=>document.querySelector('input[placeholder="亚马逊运输模板"]')?.closest('.el-select')?.__vue__?.value);if(typeof id!=='string'||!id)throw Error('美国原生模板选中ID未读到');record.shippingObservation.selectedId=id;await persist();return{name:choices[0],id};}
  await page.press('input[placeholder="亚马逊运输模板"]','ArrowDown');
 }
 throw Error('美国运输模板键盘选择未确认');
}

async function prepareUsPage(page,input,record,persist){
 const categoryDialog=await page.evaluate(()=>{
  const dialogs=[...document.querySelectorAll('[role="dialog"][aria-label="亚马逊产品类型推荐"]')].filter(el=>el.getClientRects().length);
  if(!dialogs.length)return null;
  const close=dialogs[0].querySelector('button.el-dialog__headerbtn');
  if(dialogs.length!==1||!close||close.disabled||!close.getClientRects().length)throw Error('无法安全关闭原草稿的类目推荐');
  close.setAttribute('data-us-close-category-recommendation','true');
  return '[data-us-close-category-recommendation="true"]';
 });
 if(categoryDialog){
  await page.click(categoryDialog,{label:'保留原草稿已核实类目'});
  await page.waitForFunction(()=>![...document.querySelectorAll('[role="dialog"][aria-label="亚马逊产品类型推荐"]')].some(el=>el.getClientRects().length),undefined,{timeout:8000});
 }
 await page.evaluate(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='同步店铺品牌');if(!b)throw Error('美国同步品牌控件变化');b.scrollIntoView({block:'center'});});
 record.brandSync={intendedAt:new Date().toISOString(),store:input.store};await persist();
 await page.evaluate(marketId=>{const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__usBrandSync={open,send,result:null};XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.origin==='https://app.junfeikuajing.com'&&url.pathname==='/api/amazon/publish/get-defaultSet-by-market'&&url.searchParams.get('market_id')===marketId);return open.call(this,m,u,...r);};XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{window.__usBrandSync.result={httpStatus:this.status,body:JSON.parse(this.responseText)};}catch{}},{once:true});return send.call(this,b);};},String(input.destination.marketId));
 try{await page.click('loc=role:button[name="同步店铺品牌"]');await page.waitForFunction(()=>window.__usBrandSync?.result,undefined,{timeout:20000});record.brandSync.response=await page.evaluate(()=>window.__usBrandSync.result);await persist();if(record.brandSync.response?.httpStatus!==200||record.brandSync.response?.body?.code!==0)throw Error('本次美国店铺品牌同步未返回成功');}
 finally{await page.evaluate(()=>{const s=window.__usBrandSync;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__usBrandSync;}});}
 const brand=await page.evaluate(()=>document.querySelector('input[placeholder="品牌"]').value);record.brandSync={...record.brandSync,brand,observedAt:new Date().toISOString()};await persist();
 let status=await page.evaluate(()=>document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.innerText||'');
 if(!status.includes('UPC豁免：允许销售')){
  record.exemption??={};
  if(!record.exemption.intendedAt&&!/申请中|申请失败/.test(status)){
   record.exemption.intendedAt=new Date().toISOString();record.exemption.brand=brand;record.exemption.store=input.store;await persist();
   await page.evaluate(()=>{const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__usExemptionApply={open,send,result:null};XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,url.origin==='https://app.junfeikuajing.com'&&url.pathname==='/api/amazon/category/upc-exemption/apply');return open.call(this,m,u,...r);};XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{window.__usExemptionApply.result={httpStatus:this.status,body:JSON.parse(this.responseText)};}catch{}},{once:true});return send.call(this,b);};});
   try{await page.click('loc=role:button[name="申请UPC豁免"]');await page.waitForFunction(()=>window.__usExemptionApply?.result,undefined,{timeout:20000});}
   finally{record.exemption.response=await page.evaluate(()=>window.__usExemptionApply?.result);await persist();await page.evaluate(()=>{const s=window.__usExemptionApply;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__usExemptionApply;}});}
  }
  const refresh=await page.evaluate(()=>{const e=document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.querySelector('.el-icon-refresh');if(!e)return false;e.setAttribute('data-us-preparation-exemption-read','true');e.scrollIntoView({block:'center'});return true;});
  if(refresh)await page.click('[data-us-preparation-exemption-read]');
  await page.waitForFunction(()=>document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.innerText.includes('UPC豁免：允许销售'),undefined,{timeout:20000});
 }
 status=await page.evaluate(()=>document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item')?.innerText);record.exemption={...record.exemption,brand,status,checkedAt:new Date().toISOString()};await persist();
 return{brand,shippingTemplate:await setNativeShipping(page,input,record,persist)};
}

export async function prepareUsDraft(page,input,record,persist,adapters={}){
 const api={readSchema:readUsSchema,read:readPersistedDraft,preparePage:prepareUsPage,save:saveDraft,validate:validateSchemaAttributes,...adapters};
 const validate=async(response,meta)=>{const data=response.data,records=[{id:'parent',attributes:data.attributes??data.extra?.attributes},...(data.items||[]).map(row=>({id:row.sku,attributes:row.attributes??row.extra?.attributes}))];try{const proof=await api.validate(meta,records,input);return proof;}catch(e){if(e.schemaValidation)record.schemaValidation=e.schemaValidation;await persist();throw e;}};
 const saved=Boolean(record.saveIntendedAt||record.requestSent||record.phase==='us_draft_verified');
 if(saved&&!record.preparedInput)throw Error('原美国保存结果待对账但冻结输入缺失，不重新保存');
 if(record.preparedInput){
  const p=assertUsPreparedIdentity(input,record.preparedInput);
  if(saved){
   const resumable=record.phase==='us_save_unknown'&&record.status==='save_unknown'&&record.requestSent===false&&
    record.response===null&&record.submitted===null&&!record.confirmationRecovery&&record.schemaValidation?.passed===true&&
    record.enumConfirmation?.includes('不在亚马逊选项中。确定要保存吗？')&&p.destination.shippingTemplate?.id;
   if(resumable&&await page.evaluate(({draftId,sku,savedText})=>{
    const boxes=[...document.querySelectorAll('.el-message-box')].filter(e=>e.getBoundingClientRect().width);
    return location.href==='https://www.junfeikuajing.com/#/amazon/product/'+draftId+'?type=draft'&&!window.__finishedCollectionHook&&
     document.querySelector('input[placeholder^="父Sku,"]')?.value===sku&&boxes.length===1&&boxes[0].innerText===savedText;
   },{draftId:p.destination.draftId,sku:p.goods.parentSku,savedText:record.enumConfirmation})){
    record.confirmationRecovery={originalSaveIntendedAt:record.saveIntendedAt,originalRequestSent:false,intendedAt:new Date().toISOString()};
    await persist();
    const wire={...input,usPrepared:p,usProductAttributes:record.productAttributes};
    await api.save(page,wire,input.urls,record,persist,patchUsDraftPayload,{pending:true});
    record.confirmationRecovery.response=record.response;await persist();
   }
   const actual=await api.read(page,p.destination.draftId);
   p.destination.shippingTemplate??={};
   if(!p.destination.shippingTemplate.id)p.destination.shippingTemplate.id=record.submitted?.attributes?.merchant_shipping_group?.[0]?.value??actual.data?.extra?.attributes?.merchant_shipping_group?.[0]?.value;
   const meta=record.schemaObservation;
   const leg=meta?.product_type_name==='PANTS'?usProductAttributes(p,meta).leg:undefined;
   const expected=leg?{...record.productAttributes,leg}:record.productAttributes;
   record.verification=verifyUsPrepared(actual,p,input.urls,expected);
   record.persistedSchemaValidation=await validate(actual,meta);record.phase='us_draft_verified';await persist();return record;
  }
 }
 const {draft,meta}=await api.readSchema(page,input);
 assertMainImageLocatorSchema(meta,input.destination.marketplaceId);
 // Validate the original frozen SKU/content/images before changing attributes.
 verifyPersistedDraft(draft,input,input.urls);
 if(String(draft.data.uid)!==String(input.destination.erpAccountId))throw Error('美国草稿ERP账号不符');
 const origin=input.publicationFacts?.countryOfOrigin;if(!origin)throw Error('请先保存本款实际原产国');
 record.schemaObservation=meta;await persist();
 const native=await api.preparePage(page,input,record,persist),prepared=makeUsPreparedInput(input,meta,native.brand);prepared.destination.shippingTemplate=native.shippingTemplate;
 const attributes=usProductAttributes(prepared,meta),wire={...input,usPrepared:prepared,usProductAttributes:attributes};record.productAttributes=attributes;record.preparedInput=prepared;
 const previewBody={...clone(draft.data),attributes:{merchant_shipping_group:[{value:native.shippingTemplate.id}]},with_publish:false,publish:false};
 const preview=patchUsDraftPayload(previewBody,wire,input.urls);record.schemaValidation=await validate({data:preview},meta);record.phase='us_save_unknown';await persist();
 await api.save(page,wire,input.urls,record,persist,patchUsDraftPayload);
 prepared.destination.shippingTemplate.id=record.submitted?.attributes?.merchant_shipping_group?.[0]?.value;if(!prepared.destination.shippingTemplate.id)throw Error('美国实际运输模板ID未持久记录');await persist();
 const actual=await api.read(page,prepared.destination.draftId);record.verification=verifyUsPrepared(actual,prepared,input.urls,attributes);record.persistedSchemaValidation=await validate(actual,meta);record.phase='us_draft_verified';record.verifiedAt=new Date().toISOString();await persist();return record;
}
