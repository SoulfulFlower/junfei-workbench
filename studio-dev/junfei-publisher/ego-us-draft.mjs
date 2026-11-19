// Complete the original US draft using the actual schema and frozen facts.
// Saves and exemption applications have durable intents; no draft is created.
import {schemaVariation} from './ego-collection-prepare.mjs';
import {readPersistedDraft,verifyPersistedDraft,assertMainImageLocatorSchema} from './ego-draft-readback.mjs';
import {saveDraft} from './ego-draft-save.mjs';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';

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
  if(!p.enum?.includes('regular')||!/no special/i.test(p.description||''))throw Error('实际schema未提供普通款尺码分类依据 '+key);
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
 if(meta.product_type_name==='PANTS'){
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
   const explicit=line('Leg style');
   const cuts=[...style.matchAll(/\b(wide|straight|tapered|skinny|flared|boot[- ]cut)[- ]leg\b/gi)];
   const labels=new Set(cuts.map(([,cut])=>cut.toLowerCase().replace(/-/g,' ')));
   if(explicit)labels.add(explicit.toLowerCase().replace(/-/g,' '));
   if(labels.size!==1)throw Error('美国裤装缺少唯一已核实的腿型，请补齐同款供货资料再发布');
   const label=[...labels][0].replace(/\b\w/g,letter=>letter.toUpperCase());
   attrs.leg=nested('leg','style',label);
  }
  const amendment=input.usPreparation?.pantsRise;
  if(amendment){
   const supported={'高腰':'High Rise','中腰':'Mid Rise','低腰':'Low Rise'};
   if(amendment.sourceUrl!==facts.supplierModelNumberEvidence?.sourceUrl||amendment.field!=='腰型'||
      !Object.hasOwn(supported,amendment.sourceValue)||supported[amendment.sourceValue]!==amendment.value)throw Error('美国裤装腰型缺少同一货源证据');
   attrs.rise=nested('rise','style',amendment.value);
  }
 }
 if(/pullover/i.test(style)&&schema.properties?.style)attrs.style=[localized('style','Pullover')];
 if(meta.product_type_name==='SWEATER'&&/\bcardigan\b/i.test(input.goods.title)&&/^Knit$/i.test(line('Texture'))&&/\bbuttons\b/i.test(line('Front closure'))){
  if(schema.properties?.style)attrs.style=[localized('style','Button-Front Knit Cardigan')];
  if(schema.properties?.supplier_declared_dg_hz_regulation&&/^Polyester$/i.test(fabric)&&
     facts.waterResistanceLevelSource?.basis?.classification==='ordinary_apparel'){
   attrs.supplier_declared_dg_hz_regulation=[localized('supplier_declared_dg_hz_regulation','not_applicable')];
  }
 }
 if(/\bfitted\b/i.test(style)&&schema.properties?.fit_type)attrs.fit_type=[localized('fit_type','Fitted')];
 if(/^crew neck$/i.test(neck)&&schema.properties?.neck)attrs.neck=[{neck_style:[{value:'Crew Neck',language_tag:language}],marketplace_id:market}];
 if(/^Long, with narrow cuff edges$/i.test(sleeves)&&schema.properties?.sleeve)attrs.sleeve=[{type:[{value:'Cuff Sleeve',language_tag:language}],length_description:[{value:'long_sleeve'}],marketplace_id:market}];
 // These facts follow the explicit Women breadcrumb, rather than a model guess.
 const category=input.destination.categoryHints?.path||input.categoryHints?.path||'';
 if(/(?:^|>)\s*Women\s*(?:>|$)/i.test(category)){
  for(const [key,value]of [['department','Womens'],['target_gender','female'],['age_range_description','Adult']])if(schema.properties?.[key])attrs[key]=[localized(key,value)];
 }
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
 await page.evaluate(()=>{if(window.__usPreparationSchema)throw Error('已有美国schema观察');const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__usPreparationSchema={open,send,data:null};XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.origin==='https://app.junfeikuajing.com'&&url.pathname==='/api/amazon/category/get-product-type');return open.call(this,m,u,...r);};XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{const r=JSON.parse(this.responseText);if(this.status===200&&r.code===0)window.__usPreparationSchema.data=r.data;}catch{}},{once:true});return send.call(this,b);};});
 try{const draft=await readPersistedDraft(page,input.destination.draftId);await page.waitForFunction(()=>window.__usPreparationSchema?.data,undefined,{timeout:20000});return{draft,meta:await page.evaluate(()=>window.__usPreparationSchema.data)};}
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
