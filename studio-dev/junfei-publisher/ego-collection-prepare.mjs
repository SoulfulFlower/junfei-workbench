const visible=e=>!!e.getBoundingClientRect().width;
const norm=s=>String(s).toLowerCase().replace(/[^a-z0-9]/g,'');

export function resolveCategoryHints(...sources){
 const hints=sources.filter(value=>value&&typeof value==='object'&&!Array.isArray(value));
 const chosen=hints.find(value=>typeof value.path==='string'&&value.path.trim())||hints.find(value=>typeof value.title==='string'&&value.title.trim());
 return chosen?structuredClone(chosen):{};
}

export function chooseCategory(candidates,hints={},title=''){
 const words=value=>String(value??'').toLowerCase().replace(/\bt[\s-]*shirts?\b/g,'tshirt').match(/[a-z]+/g)||[];
 const kinds=['tshirt','cardigan','sweater','hoodie','sweatshirt','dress','shirt','blouse','coat','jacket','bag','backpack','towel','pants','skirt','short','vest','shrug','pullover'];
 const type=word=>kinds.find(kind=>word===kind||word===kind+'s');
 const types=value=>[...new Set(words(value).map(type).filter(Boolean))];
 const path=typeof hints.path==='string'?hints.path.trim():'',source=path||[hints.title,title].filter(Boolean).join(' ');
 // The verified taxonomy leaf outranks words in its ancestors or a marketing
 // title. In particular, T-Shirts must not also become plain Shirts/Blouses.
 const leaf=path?path.split(/\s*(?:>|›|»|→|\|)\s*/).at(-1):source,wanted=types(leaf),sourceWords=words(source);
 const expectedGender=['women','men','girl','boy','baby'].filter(gender=>sourceWords.some(word=>word===gender||word===gender+'s'));
 const branches=[/\bactivewear\b/,/\bsports?\b/,/\bfitness\b/,/\bmaternity\b/,/\buniforms?\b/,/\bnovelty\b/,/\btraditional\b/,/\bcostumes?\b/,/\bworkwear\b/,/\bthermal\b/,/\bcompression\b/,/\bbase layers?\b/,/\bnightwear\b/,/\blingerie\b/,/\bunderwear\b/];
 const evidence=words(source).join(' '),requiredBranches=branches.filter(pattern=>pattern.test(evidence));
 const ranked=candidates.map(c=>{
  const text=words(c.text).join(' '),candidateWords=words(c.text),gender=['women','men','girl','boy','baby'].filter(value=>candidateWords.some(word=>word===value||word===value+'s'));
  const exact=Boolean(path&&norm(path)===norm(c.text)),candidateType=type(candidateWords.at(-1)),matched=candidateType&&wanted.includes(candidateType);
  let score=exact?100:matched?(wanted.length===1?40:8):0;
  if((expectedGender.length&&gender.some(value=>!expectedGender.includes(value)))||
     (path&&expectedGender.some(value=>!gender.includes(value)))||
     branches.some(pattern=>pattern.test(text)&&!pattern.test(evidence))||
     requiredBranches.some(pattern=>!pattern.test(text)))score=-Infinity;
  else if(!exact&&!matched)score=-Infinity;
  else score+=gender.filter(value=>expectedGender.includes(value)).length*4;
  return{...c,score};
 }).sort((a,b)=>b.score-a.score);
 if(!ranked.length||ranked[0].score<4||(ranked[1]&&ranked[0].score===ranked[1].score))throw Error('ERP类目推荐有歧义，请在产品资料补充准确的Amazon类目路径');
 return ranked[0];
}

export function schemaVariation(meta,items){
 const schema=typeof meta.schema_content==='string'?JSON.parse(meta.schema_content):meta.schema_content;
 const properties=schema?.properties;if(!properties)throw Error('ERP未返回真实类目schema');
 const get=(key,leaf)=>properties[key]?.items?.properties?.[leaf];
 const colorField=get('color','value')?'color.0.value':get('color_name','value')?'color_name.0.value':null;
 const sizeField=get('apparel_size','size')?'apparel_size.0.size':get('shirt_size','size')?'shirt_size.0.size':get('bottoms_size','size')?'bottoms_size.0.size':get('size','value')?'size.0.value':get('size_name','value')?'size_name.0.value':null;
 if(!colorField||!sizeField)throw Error('此类目不支持当前产品的颜色/尺码结构，请补齐实际变体维度');
 const themes=get('variation_theme','name')?.enum||[];
 const theme=['COLOR_NAME/SIZE_NAME','COLOR/SIZE','SIZE_NAME/COLOR_NAME','SIZE/COLOR'].find(v=>themes.includes(v));
 if(!theme)throw Error('ERP类目未提供可用的颜色尺码变体主题');
 const parts=sizeField.split('.'),sizeMeta=get(parts[0],parts[2]),values=sizeMeta.enum,labels=sizeMeta.enumNames||[];
 const aliases={small:'s',medium:'m',large:'l',xlarge:'xl',xxlarge:'xxl',xxxlarge:'xxxl',onesize:'onesize',均码:'onesize'};
 const canonical=s=>{let n=norm(s);return aliases[n]||n;};
 const sizeValues={};for(const label of new Set(items.map(i=>i.size))){
  if(!values){sizeValues[label]=label;continue;}
  const n=canonical(label),exact=values.filter(v=>norm(v)===norm(label));
  if(exact.length===1){sizeValues[label]=exact[0];continue;}
  const direct=values.filter(v=>canonical(v)===n);
  if(direct.length===1){sizeValues[label]=direct[0];continue;}
  const matched=values.filter((v,i)=>canonical(labels[i])===n);
  if(matched.length!==1)throw Error('ERP尺码枚举无法唯一对应：'+label+'；请补齐尺码体系');sizeValues[label]=matched[0];
 }
 const resolved={themeValue:theme,variationFields:{color:colorField,size:sizeField},sizeValues,languageTag:meta.locale||undefined,countryCode:meta.country_code,schemaHash:meta.hash};
 const itemSchema=properties[parts[0]].items,required=itemSchema.required||[];
 if(required.some(key=>key==='size_class'||key==='size_system')){
  if(!meta.hash||!meta.country_code)throw Error('必填尺码属性缺少真实schema身份');
  const deref=definition=>definition?.$ref?.startsWith('#/$defs/')?schema.$defs?.[definition.$ref.slice(8)]:definition;
  const uniqueDefault=definition=>{
   const d=deref(definition);if(!d)return undefined;
   const value=Object.hasOwn(d,'const')?d.const:Object.hasOwn(d,'default')?d.default:d.enum?.length===1?d.enum[0]:undefined;
   return value!==undefined&&(!d.enum||d.enum.includes(value))?value:undefined;
  };
  const definitions=itemSchema.properties,attributes={},actualSizes=[...new Set(Object.values(sizeValues))];
  const system=uniqueDefault(definitions.size_system);
  if(required.includes('size_system')&&system===undefined)throw Error('真实schema无法唯一确定尺码体系');
  if(system!==undefined)attributes.size_system=system;
  const classDefinition=deref(definitions.size_class);
  // A suggested default does not prove the class of these actual variants.
  let sizeClass=classDefinition&&Object.hasOwn(classDefinition,'const')?classDefinition.const:
   classDefinition?.enum?.length===1?classDefinition.enum[0]:undefined;
  if(sizeClass===undefined&&required.includes('size_class')){
   // A class may have several legal enums. Infer it only from the schema's
   // own if/then size restrictions, never from an English product title.
   const intersection=(a,b)=>a===undefined?b:a.filter(value=>b.includes(value));
   const itemConstraints=node=>{
    const result={};
    const visit=value=>{
     if(!value||typeof value!=='object')return;
     for(const key of ['size_class','size_system',parts[2]]){
      const definition=deref(value.properties?.[key]),enums=definition?.enum||(definition&&Object.hasOwn(definition,'const')?[definition.const]:undefined);
      if(enums)result[key]=intersection(result[key],enums);
     }
     for(const child of value.allOf||[])visit(child);
    };visit(node);return result;
   };
   const rootConstraints=node=>{
    const result={};
    const visit=value=>{
     if(!value||typeof value!=='object')return;
     for(const [key,enums]of Object.entries(itemConstraints(value.properties?.[parts[0]]?.items)))result[key]=intersection(result[key],enums);
     for(const child of value.allOf||[])visit(child);
    };visit(node);return result;
   };
   const classes=new Set(),classEnums=deref(definitions.size_class)?.enum;
   const walk=node=>{
    if(!node||typeof node!=='object')return;
    if(node.if&&node.then){
     const predicate=rootConstraints(node.if),then=rootConstraints(node.then),allowed=then[parts[2]];
     if(predicate.size_class&&allowed&&actualSizes.every(size=>allowed.includes(size))&&
        (!predicate.size_system||(system!==undefined&&predicate.size_system.includes(system)))){
      for(const value of predicate.size_class)if(!classEnums||classEnums.includes(value))classes.add(value);
     }
    }
    for(const value of Object.values(node))if(value&&typeof value==='object'){
     if(Array.isArray(value))value.forEach(walk);else walk(value);
    }
   };walk(schema);
   if(classes.size!==1)throw Error('真实schema无法按全部变体唯一确定尺码类别');
   [sizeClass]=classes;
  }
  if(sizeClass!==undefined)attributes.size_class=sizeClass;
  for(const key of required){
   if(key===parts[2]||key==='marketplace_id'||Object.hasOwn(attributes,key))continue;
   const value=uniqueDefault(definitions[key]);
   if(value===undefined)throw Error('真实schema必填尺码属性缺少已证明值：'+key);
   attributes[key]=value;
  }
  const project=(definition,value)=>{
   const d=deref(definition);if(!d)throw Error('真实schema缺少尺码属性定义');
   const result={};if(d.type)result.type=d.type;
   if(value!==undefined)result.enum=[value];
   else if(d.enum)result.enum=[...d.enum];
   return result;
  };
  const projected={
   [parts[2]]:{...project(sizeMeta),enum:actualSizes},
   marketplace_id:project(definitions.marketplace_id)
  };
  for(const [key,value]of Object.entries(attributes))projected[key]=project(definitions[key],value);
  resolved.sizeAttributeSchema={field:parts[0],countryCode:meta.country_code,schemaHash:meta.hash,required:[...required],properties:projected};
  resolved.sizeAttributes=attributes;
 }
 return resolved;
}

export async function pickOption(page,text,control,record,persist,step='option'){
 const checkpoint={step,optionText:text,control:structuredClone(control),method:'trusted_keyboard',phase:'started',at:new Date().toISOString()};
 (record.preparationInteractions??=[]).push(checkpoint);
 const note=async phase=>{checkpoint.phase=phase;checkpoint.updatedAt=new Date().toISOString();await persist();};
 const inspect=({text,control,requireFocus=false})=>{
  const visible=e=>!!e?.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible';
  const controls=[...document.querySelectorAll(control.selector)];
  const field=control.index===undefined?(controls.length===1?controls[0]:null):controls[control.index];
  if(!visible(field)||field.disabled||field.getAttribute('aria-disabled')==='true')throw Error('ERP下拉输入不唯一、不可见或不可用');
  if(requireFocus&&document.activeElement!==field)throw Error('ERP下拉输入焦点变化');
  const options=[...document.querySelectorAll('.el-select-dropdown li')].filter(visible);
  const matches=options.filter(e=>e.innerText.trim()===text);
  if(matches.length!==1)throw Error('ERP选项不唯一 '+text);
  const target=matches[0];if(target.classList.contains('is-disabled')||target.getAttribute('aria-disabled')==='true')throw Error('ERP选项不可用 '+text);
  const hovered=options.filter(e=>e.classList.contains('hover'));
  if(hovered.length>1)throw Error('ERP下拉高亮选项不唯一');
  return{count:options.length,targetHovered:hovered.length===1&&hovered[0]===target};
 };
 try{
  await note('started');
  if(typeof text!=='string'||!text.trim()||!control||typeof control.selector!=='string'||!control.selector||
     (control.index!==undefined&&(!Number.isSafeInteger(control.index)||control.index<0)))throw Error('ERP下拉选项或输入定位为空');
  const initial=await page.evaluate(inspect,{text,control});checkpoint.optionCount=initial.count;await note('option_unique');
  const locator=control.selector+(control.index===undefined?'':' >> nth='+control.index);
  await page.focus(locator);
  for(let n=0;n<=initial.count;n++){
   const current=await page.evaluate(inspect,{text,control,requireFocus:true});
   if(current.count!==initial.count)throw Error('ERP下拉选项集合变化');
   if(current.targetHovered){
    await note('target_hovered');
    const fresh=await page.evaluate(inspect,{text,control,requireFocus:true});
    if(!fresh.targetHovered||fresh.count!==initial.count)throw Error('ERP下拉确认前高亮变化');
    await page.press(locator,'Enter');
    await page.waitForFunction(()=>![...document.querySelectorAll('.el-select-dropdown')].some(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible'),undefined,{timeout:5000});
    await note('selected');return;
   }
   if(n===initial.count)break;
   await page.press(locator,'ArrowDown');
  }
  throw Error('ERP下拉键盘定位未命中唯一选项 '+text);
 }catch(error){checkpoint.error=String(error.message||error);await note('failed');throw error;}
}

export async function prepareNativeDraft(page,input,record,persist){
 const url='https://www.junfeikuajing.com/#/amazon/product/'+record.draftId+'?type=draft';
 await page.goto(url);await page.waitForFunction(()=>document.querySelector('input[placeholder="产品标题"]')?.value,undefined,{timeout:20000});
 await page.evaluate(()=>{
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__collectionSchema={open,send,data:null};
  XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.origin==='https://app.junfeikuajing.com'&&url.pathname==='/api/amazon/category/get-product-type');return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{const r=JSON.parse(this.responseText);if(r.code===0)window.__collectionSchema.data=r.data;}catch{}},{once:true});return send.call(this,b);};
 });
 let meta;
 try{
  const current=await page.evaluate(()=>document.querySelector('input[placeholder="店铺"]')?.value);
  if(current&&current!==input.store)throw Error('原生草稿已属于其他店铺，不能覆盖');
  if(!current){await page.click('input[placeholder="店铺"]');await page.waitForFunction(label=>[...document.querySelectorAll('.el-select-dropdown li')].some(e=>e.getBoundingClientRect().width&&e.innerText.trim()===label),input.store,{timeout:10000});await pickOption(page,input.store,{selector:'input[placeholder="店铺"]'},record,persist,'store');}
  if(!current)try{await page.waitForFunction(()=>[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:5000});}catch{}
  const hasDialog=await page.evaluate(()=>[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].some(e=>e.getBoundingClientRect().width));
  if(!hasDialog){await page.click('loc=role:button[name="选择分类"]');}
  await page.waitForFunction(()=>[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"] label.el-radio')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:20000});
  const candidates=await page.evaluate(()=>{const d=[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].find(e=>e.getBoundingClientRect().width);return [...d.querySelectorAll('label.el-radio')].map((e,index)=>({index,text:e.innerText.split(/[\u3400-\u9fff]/)[0].replace(/[\uE000-\uF8FF]/g,' > ').replace(/\s+/g,' ').trim()}));});
  const hints=resolveCategoryHints(input.destination.categoryHints,input.categoryHints);
  if(record.categoryRecommendation)(record.categoryRecommendationHistory??=[]).push(record.categoryRecommendation);
  record.categoryRecommendation={observedAt:new Date().toISOString(),draftId:String(record.draftId),store:input.store,candidates:structuredClone(candidates),hints:structuredClone(hints),title:input.goods.title};await persist();
  const selected=chooseCategory(candidates,hints,input.goods.title);record.categoryChoice=selected;await persist();
  const selector=await page.evaluate(index=>{const d=[...document.querySelectorAll('[role=dialog][aria-label="亚马逊产品类型推荐"]')].find(e=>e.getBoundingClientRect().width);const e=d.querySelectorAll('label.el-radio')[index];if(!e)throw Error('类目列表变化');e.setAttribute('data-collection-category','true');e.scrollIntoView({block:'center',inline:'nearest'});return e.querySelector('.el-radio__input')?'[data-collection-category] .el-radio__input':'[data-collection-category]';},selected.index);
  await page.click(selector);await page.click('[role=dialog][aria-label="亚马逊产品类型推荐"] .el-dialog__footer button:has-text("确定")');
  await page.waitForFunction(()=>window.__collectionSchema?.data,undefined,{timeout:20000});meta=await page.evaluate(()=>window.__collectionSchema.data);
 }finally{await page.evaluate(()=>{const s=window.__collectionSchema;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__collectionSchema;}});}
 if(meta.country_code!==input.destination.countryCode)throw Error('ERP返回了其他站点的类目schema');
 const schema=typeof meta.schema_content==='string'?JSON.parse(meta.schema_content):meta.schema_content;
 record.schemaProof={country:meta.country_code,productType:meta.product_type_name,hash:meta.hash,
  variationProperties:Object.fromEntries(Object.entries(schema?.properties||{}).filter(([key])=>/^(?:color|color_name|size|size_name|.*_size)$/.test(key)).map(([key,definition])=>[key,Object.keys(definition?.items?.properties||{})])),
  themes:schema?.properties?.variation_theme?.items?.properties?.name?.enum||[]};await persist();
 Object.assign(input.destination,schemaVariation(meta,input.goodsItems));record.resolvedDestination={...input.destination};await persist();
 await page.evaluate(()=>{const e=document.querySelector('input[placeholder="变体主体"]');if(!e)throw Error('ERP变体主题控件变化');e.scrollIntoView({block:'center',inline:'nearest'});});
 await page.click('input[placeholder="变体主体"]');
 await page.waitForFunction(value=>[...document.querySelectorAll('.el-select-dropdown li')].some(e=>e.getBoundingClientRect().width&&e.innerText.includes('('+value+')')),input.destination.themeValue,{timeout:8000});
 const theme=await page.evaluate(value=>{const es=[...document.querySelectorAll('.el-select-dropdown li')].filter(e=>e.getBoundingClientRect().width&&e.innerText.includes('('+value+')'));if(es.length!==1)throw Error('ERP变体主题选项不唯一');return es[0].innerText.trim();},input.destination.themeValue);await pickOption(page,theme,{selector:'input[placeholder="变体主体"]'},record,persist,'variation_theme');
 await page.waitForFunction(()=>[...document.querySelectorAll('[role=dialog][aria-label="替换变体主题"]')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:8000});
 const mappings=await page.evaluate(()=>{const d=[...document.querySelectorAll('[role=dialog][aria-label="替换变体主题"]')].find(e=>e.getBoundingClientRect().width);return [...d.querySelectorAll('.el-table__body tr')].map((r,i)=>({field:r.cells[1]?.innerText.trim(),index:i}));});
 for(const mapping of mappings){
  const kind=mapping.field===input.destination.variationFields.color?'color':mapping.field===input.destination.variationFields.size?'size':null;if(!kind)throw Error('ERP主题包含未提供的第三变体维度');
  await page.click('[role=dialog][aria-label="替换变体主题"] input >> nth='+mapping.index);
  await page.waitForFunction(()=>[...document.querySelectorAll('.el-select-dropdown li')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:5000});
  const label=await page.evaluate(kind=>{const es=[...document.querySelectorAll('.el-select-dropdown li')].filter(e=>e.getBoundingClientRect().width&&new RegExp('^'+kind+'(?:\\('+kind+'\\))?$','i').test(e.innerText.trim()));if(es.length!==1)throw Error('无法关联采集的'+kind+'维度');return es[0].innerText.trim();},kind);await pickOption(page,label,{selector:'[role=dialog][aria-label="替换变体主题"] input',index:mapping.index},record,persist,'variation_'+kind);
 }
 await page.click('[role=dialog][aria-label="替换变体主题"] .el-dialog__footer button:has-text("确定")');
 await page.waitForFunction(()=>![...document.querySelectorAll('[role=dialog][aria-label="替换变体主题"]')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:5000});
 await page.evaluate(input=>{
  if(location.hash!=='#/amazon/product/'+input.destination.draftId+'?type=draft'||document.querySelector('input[placeholder="店铺"]')?.value!==input.store)throw Error('ERP草稿店铺身份变化');
  const set=(e,v)=>{if(!e)throw Error('ERP字段缺失');Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,String(v));e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
  const field=(ph,value)=>{const es=[...document.querySelectorAll('input,textarea')].filter(e=>e.placeholder===ph&&e.getBoundingClientRect().width);if(es.length!==1)throw Error('ERP字段不唯一 '+ph);set(es[0],value);};
  set(document.querySelector('input[placeholder^="父Sku,"]'),input.goods.parentSku);field('产品标题',input.goods.title);field('品牌',input.goods.brand);field('制造商',input.goods.manufacturer);field('制造商编号','');field('产品描述',input.goods.description);field('处理时间',input.handlingDays);
  const fields=[...document.querySelectorAll('textarea[placeholder="Bullet Point"]')].filter(e=>e.getBoundingClientRect().width);if(fields.length!==6)throw Error('ERP五点与搜索词控件变化');[...input.goods.bullets,input.goods.terms].forEach((v,i)=>set(fields[i],v));
  const rows=[...document.querySelectorAll('.el-table__body-wrapper tr')].filter(r=>r.querySelector('input[placeholder="sku"]'));if(rows.length!==input.goodsItems.length)throw Error('ERP子SKU数量不符');
  for(const row of rows){const sku=row.querySelector('input[placeholder="sku"]').value,v=input.goodsItems.find(i=>i.sku===sku);if(!v)throw Error('ERP包含其他产品子SKU');set(row.querySelector('input[placeholder="售价"]'),v.price);set(row.querySelector('input[placeholder="库存"]'),v.quantity);}
 },input);
}
