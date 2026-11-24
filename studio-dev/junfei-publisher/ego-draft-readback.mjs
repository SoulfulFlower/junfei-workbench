// Verify persisted data from the ERP's real, authenticated draft-show request.
// This checks every child gallery directly, without opening 24 image dialogs.
export function assertMainImageLocatorSchema(meta,marketplaceId){
 const schema=typeof meta?.schema_content==='string'?JSON.parse(meta.schema_content):meta?.schema_content;
 const field=schema?.properties?.main_product_image_locator,items=field?.items,media=items?.properties?.media_location,market=items?.properties?.marketplace_id;
 const resolvedMarket=market?.$ref?.startsWith('#/$defs/')?schema.$defs?.[market.$ref.slice(8)]:market;
 if(!meta?.hash||typeof marketplaceId!=='string'||!marketplaceId||schema?.$defs?.marketplace_id?.default!==marketplaceId||
    field?.type!=='array'||items?.type!=='object'||!items.required?.includes('media_location')||media?.type!=='string'||
    !resolvedMarket||(field.minItems!==undefined&&field.minItems>1)||(field.maxItems!==undefined&&field.maxItems<1))throw Error('当前真实schema不支持明确站点的MAIN图片定位属性，停止准备');
 return true;
}

export function verifyPersistedDraft(response,input,urls,{allowInherited=false}={}){
 const d=response?.data,g=input.goods,target=input.destination;
 const fields=target.variationFields||{color:'color.0.value',size:'apparel_size.0.size'};
 const sizeSchema=target.sizeAttributeSchema,sizeAttributes=target.sizeAttributes;
 const expectedSizeNode=size=>{
  const [field,,leaf]=fields.size.split('.'),node={[leaf]:size,marketplace_id:target.marketplaceId};
  if(sizeSchema===undefined&&sizeAttributes===undefined)return null;
  if(!sizeSchema||sizeSchema.field!==field||sizeSchema.countryCode!==(target.countryCode||'US')||!target.schemaHash||sizeSchema.schemaHash!==target.schemaHash||
     !Array.isArray(sizeSchema.required)||!sizeSchema.properties||typeof sizeSchema.properties!=='object'||
     !sizeAttributes||typeof sizeAttributes!=='object'||Array.isArray(sizeAttributes))throw Error('缺少匹配当前站点的真实尺码属性schema');
  if(Object.hasOwn(sizeAttributes,leaf)||Object.hasOwn(sizeAttributes,'marketplace_id'))throw Error('尺码元数据不能覆盖子SKU尺码或站点');
  Object.assign(node,sizeAttributes);
  for(const key of sizeSchema.required)if(typeof key!=='string'||node[key]===undefined||node[key]===null||node[key]==='')throw Error('缺少真实schema必填尺码属性：'+key);
  for(const [key,value]of Object.entries(node)){
   const definition=sizeSchema.properties[key];
   if(!definition)throw Error('真实schema不支持尺码属性：'+key);
   if(value===undefined||value===null||value===''||typeof value==='object'||
      (definition.enum&&!definition.enum.includes(value))||
      (Object.hasOwn(definition,'const')&&definition.const!==value)||
      (definition.type&&definition.type!==typeof value))throw Error('尺码属性不符合真实schema：'+key);
  }
  return node;
 };
 if(response?.code!==0||!d||String(d.id)!==String(target.draftId)||String(d.market_id)!==String(target.marketId)||d.country_code!==(target.countryCode||'US')||d.market?.alias!==input.store||d.sku!==g.parentSku)throw Error('ERP持久草稿身份不符');
 for(const [field,expected]of Object.entries({title:g.title,brand:g.brand,manufacturer:g.manufacturer}))if(d[field]!==expected)throw Error('持久文案字段不符 '+field);
 // ERP stores textarea line breaks as <br/> and decodes them on reopening.
 const text=value=>String(value??'').replace(/<br\s*\/?\s*>/gi,'\n').replace(/\r\n/g,'\n');
 if(text(d.extra?.product_description)!==text(g.description)||JSON.stringify(d.extra?.bullet_point)!==JSON.stringify(g.bullets)||d.extra?.keywords!==g.terms)throw Error('持久文案回读不符');
 if(d.items?.length!==input.goodsItems.length||new Set(d.items.map(v=>v.sku)).size!==d.items.length)throw Error('持久子SKU集合不符');
 const allImages=input.assets.map(a=>urls[a.sha256]);
 const first=input.goodsItems.find(v=>v.color===input.masterColor)||input.goodsItems[0];
 const cover=urls[input.assets[first.imageIndices[0]].sha256],parentImages=d.extra?.images;
 if(d.main_image!==undefined&&d.main_image!==cover)throw Error('持久父体封面不符');
 const verifyMain=(attributes,expected,sku)=>{
  if(target.requireMainImageLocator!==true)return;
  const locator=attributes?.main_product_image_locator;
  if(!Array.isArray(locator)||locator.length!==1||locator[0]?.media_location!==expected||locator[0]?.marketplace_id!==target.marketplaceId)throw Error('持久MAIN图片定位属性不符 '+sku);
 };
 verifyMain(d.extra?.attributes??d.attributes,cover,g.parentSku);
 // Existing explicit multicolour galleries remain valid. New writes keep a
 // cover only so the ERP cannot collapse all single-colour children to null.
 if(JSON.stringify(parentImages)!==JSON.stringify(allImages)&&JSON.stringify(parentImages)!==JSON.stringify([cover]))throw Error('持久产品图库不符');
 return input.goodsItems.map(v=>{
  const row=d.items.find(r=>r.sku===v.sku),expected=v.imageIndices.map(i=>urls[input.assets[i].sha256]);
  if(!row||String(row.pid)!==String(d.id)||row.variation?.[fields.color]!==v.color||row.variation?.[fields.size]!==target.sizeValues[v.size]||Number(row.price)!==Number(v.price)||String(row.quantity)!==String(v.quantity))throw Error('持久变体字段不符 '+v.sku);
  const sizeNode=expectedSizeNode(target.sizeValues[v.size]);
  if(sizeNode){
   const field=fields.size.split('.')[0],actual=(row.extra?.attributes??row.attributes)?.[field]?.[0];
   if(!actual||Object.entries(sizeNode).some(([key,value])=>actual[key]!==value))throw Error('持久必填尺码属性不符 '+v.sku);
  }
  const raw=row.extra?.images,inherited=raw==null||(Array.isArray(raw)&&raw.length===0);
  // Inheritance is readable only for a controlled migration. It is never
  // sufficient evidence for collection completion or publication.
  if(inherited&&!allowInherited)throw Error('子SKU未持久保存独立七图，禁止依赖父体继承：'+v.sku);
  const images=inherited&&allowInherited&&JSON.stringify(parentImages)===JSON.stringify(expected)?parentImages:raw;
  if(row.main_image!==expected[0]||JSON.stringify(images)!==JSON.stringify(expected))throw Error('持久七图顺序不符 '+v.sku);
  verifyMain(row.extra?.attributes??row.attributes,expected[0],v.sku);
  return{sku:v.sku,color:v.color,size:v.size,itemId:row.id,images,storedImages:raw??null,imagesSource:inherited?'parent_shared_gallery':'child_gallery',main:row.main_image,method:'erp_persisted_draft_show'};
 });
}

export async function readPersistedDraft(page,draftId,{beforeOpen}={}){
 if(!/^\d+$/.test(String(draftId)))throw Error('草稿编号无效');
 await page.goto('https://www.junfeikuajing.com/#/product/collect');await page.waitForSelector('input[placeholder="关键词搜索"]',{state:'visible'});
 if(beforeOpen)await beforeOpen();
 await page.evaluate(id=>{
  if(window.__persistedDraftRead)throw Error('已有草稿回读');
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__persistedDraftRead={open,send,result:null};
  XMLHttpRequest.prototype.open=function(m,u,...rest){targets.set(this,String(m).toUpperCase()==='GET'&&new URL(u,location.href).href==='https://app.junfeikuajing.com/api/amazon/goods/draft/show?id='+id);return open.call(this,m,u,...rest);};
  XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{try{window.__persistedDraftRead.result={status:this.status,body:JSON.parse(this.responseText)};}catch{}},{once:true});return send.call(this,b);};
 },String(draftId));
 let result;try{
  await page.goto('https://www.junfeikuajing.com/#/amazon/product/'+draftId+'?type=draft');
  await page.waitForFunction(()=>window.__persistedDraftRead?.result,undefined,{timeout:20000});result=await page.evaluate(()=>window.__persistedDraftRead.result);
 }finally{await page.evaluate(()=>{const s=window.__persistedDraftRead;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__persistedDraftRead;}});}
 if(result.status!==200||result.body.code!==0)throw Error('ERP持久草稿读取失败');return result.body;
}
