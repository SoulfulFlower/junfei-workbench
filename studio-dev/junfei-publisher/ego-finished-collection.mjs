// Finished-page collection adapter. Uses the ERP's own authenticated Save
// request; it never reads credentials, invokes publish, or creates a new draft.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {collectInbox} from './ego-collection-inbox.mjs';
import {saveDraft} from './ego-draft-save.mjs';
import {readPersistedDraft,verifyPersistedDraft} from './ego-draft-readback.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';
import {writeJsonAtomic} from './atomic_write_json.mjs';

export function patchDraftPayload(body,input,urls){
  const d=input.destination,g=input.goods,variants=input.goodsItems;
  const country=d.countryCode||'US',language=d.languageTag||'en_US',fields=d.variationFields||{color:'color.0.value',size:'apparel_size.0.size'};
  // This function is serialized into the Save hook. Keep its validation local;
  // only the caller's resolved, real-schema size metadata may survive a save.
  const sizeSchema=d.sizeAttributeSchema,sizeAttributes=d.sizeAttributes;
  const sizeNode=(size)=>{
    const [field,,leaf]=fields.size.split('.'),node={[leaf]:size,marketplace_id:d.marketplaceId};
    if(sizeSchema===undefined&&sizeAttributes===undefined)return node;
    if(!sizeSchema||sizeSchema.field!==field||sizeSchema.countryCode!==country||!d.schemaHash||sizeSchema.schemaHash!==d.schemaHash||
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
  if(input.mode!=='draft'||String(body.id)!==String(d.draftId)||
     String(body.market_id)!==String(d.marketId)||body.country_code!==country||body.with_publish||body.publish)throw Error('草稿身份、站点或保存模式不符');
  if(![g.parentSku,d.erpAssignedSku].filter(Boolean).includes(body.parent_sku)||
     !Array.isArray(body.items)||body.items.length!==variants.length||new Set(body.items.map(i=>i.sku)).size!==variants.length)throw Error('原SKU或子SKU集合变化');
  if(!g.title||g.title.length>75||!Array.isArray(g.bullets)||g.bullets.length!==5||g.bullets.some(s=>!s||s.length>500)||
     !g.description||g.description.length>2000||new TextEncoder().encode(g.terms).length>249||g.highlights.length>125)throw Error('采集文案字段不完整或超长');
  const expected=new Map(variants.map(v=>[v.sku,v]));
  if(expected.size!==variants.length||body.items.some(i=>!expected.has(i.sku)))throw Error('当前草稿不属于本产品全部子SKU');
  const image=i=>{const a=input.assets[i],u=a&&urls[a.sha256];if(!a||!u||!/^https:\/\/junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com\//.test(u))throw Error('成品图片缺少已核对的ERP地址');return u;};
  const items=body.items.map(item=>{
    const v=expected.get(item.sku),size=d.sizeValues[v.size];
    if(!size||!v.color||v.imageIndices.length!==7||new Set(v.imageIndices).size!==7)throw Error('颜色尺码或七图映射不完整');
    const images=v.imageIndices.map(image);
    const variation={[fields.size]:size,[fields.color]:v.color};
    // Retain ERP item IDs. Clear unverified auto-filled material, pattern,
    // model, dimensions and care claims instead of copying an old template.
    const cp=fields.color.split('.'),sp=fields.size.split('.');
    const attributes={[cp[0]]:[{[cp[2]]:v.color,language_tag:language,marketplace_id:d.marketplaceId}],
      [sp[0]]:[sizeNode(size)]};
    return {...item,sku:v.sku,variation,attributes,main_image:images[0],images,price:v.price,quantity:String(v.quantity),
      title:null,product_description:'',bullet_point:null,keywords:null,title_differentiation:''};
  });
  const first=variants.find(v=>v.color===input.masterColor)||variants[0];
  // Junfei compacts a child gallery to null when it equals the parent gallery.
  // Keep the non-buyable parent as a cover; every buyable SKU owns its seven
  // images. The native editor merges child images into its visible library.
  const images=[image(first.imageIndices[0])];
  return {...body,id:Number(d.draftId),market_id:String(d.marketId),country_code:country,parent_sku:g.parentSku,sku:g.parentSku,
    title:g.title,product_description:g.description,bullet_point:g.bullets,keywords:g.terms,brand:g.brand,manufacturer:g.manufacturer,
    part_number:'',price:first.price,quantity:String(first.quantity),variation_theme:d.themeValue||'COLOR_NAME/SIZE_NAME',variation:{},
    main_image:image(first.imageIndices[0]),images,items,with_publish:false,publish:false,
    attributes:{[fields.color.split('.')[0]]:[{[fields.color.split('.')[2]]:first.color,language_tag:language,marketplace_id:d.marketplaceId}],
      title_differentiation:g.highlights?[{value:g.highlights,language_tag:language,marketplace_id:d.marketplaceId}]:[],
      fulfillment_availability:[{fulfillment_channel_code:'DEFAULT',lead_time_to_ship_max_days:String(input.handlingDays)}]}};
}

async function readDraft(page){
  return page.evaluate(()=>{
    const value=ph=>{const es=[...document.querySelectorAll('input,textarea')].filter(e=>e.placeholder===ph&&e.getBoundingClientRect().width);if(es.length!==1)throw Error('活动字段不唯一: '+ph);return es[0].value;};
    const rows=[...document.querySelectorAll('.el-table__body-wrapper tr')].filter(r=>r.querySelector('input[placeholder="sku"]'));
    const parent=[...document.querySelectorAll('input')].find(e=>e.placeholder.startsWith('父Sku,')&&e.getBoundingClientRect().width);
    const bullets=[...document.querySelectorAll('textarea[placeholder="Bullet Point"]')].filter(e=>e.getBoundingClientRect().width);
    return {url:location.href,store:value('店铺'),parentSku:parent?.value,title:value('产品标题'),description:value('产品描述'),
      bullets:bullets.slice(0,5).map(e=>e.value),terms:bullets[5]?.value,brand:value('品牌'),manufacturer:value('制造商'),
      handlingDays:value('处理时间'),theme:value('变体主体'),
      variants:rows.map(r=>({sku:r.querySelector('input[placeholder="sku"]').value,
        size:r.cells[3].querySelector('.text-clamp')?.textContent.trim()||r.cells[3].innerText.trim(),
        color:r.cells[4].querySelector('.text-clamp')?.textContent.trim()||r.cells[4].innerText.trim(),
        price:r.querySelector('input[placeholder="售价"]')?.value,quantity:r.querySelector('input[placeholder="库存"]')?.value}))};
  });
}

async function readImages(page,sku,expected,{keepOpen=false}={}){
  const selector=await page.evaluate(sku=>{
    const rs=[...document.querySelectorAll('.el-table__body-wrapper tr')].filter(r=>r.querySelector('input[placeholder="sku"]')?.value===sku);
    if(rs.length!==1)throw Error('子SKU图片行不唯一');
    document.querySelectorAll('[data-finished-image-target]').forEach(e=>e.removeAttribute('data-finished-image-target'));
    const target=rs[0].querySelector('.main_image');if(!target)throw Error('变体图片入口缺失');
    target.setAttribute('data-finished-image-target','true');target.scrollIntoView({block:'center'});return '[data-finished-image-target="true"]';
  },sku);
  await page.click(selector,{label:'核对当前子SKU的七图顺序'});
  await page.waitForFunction(expected=>{
    const d=[...document.querySelectorAll('[role=dialog][aria-label="编辑变体图片"]')].find(d=>d.getBoundingClientRect().width);
    if(!d||![...d.querySelectorAll('.image-box img,.main-page img')].every(i=>i.complete&&i.naturalWidth))return false;
    if(!expected)return true;
    // BaseImg can temporarily display the preceding image's already-loaded
    // base64. Wait for this SKU's actual ordered images, not just img.complete.
    const gallery=[...d.querySelectorAll('.product_wrap .image-box')].map(b=>({src:b.querySelector('img')?.src,url:b.querySelector('input[type=checkbox]')?.value}));
    const url=img=>{const m=gallery.filter(g=>g.src===img?.src);return m.length===1?m[0].url:null;};
    return url(d.querySelector('.main-page img'))===expected[0]&&JSON.stringify([...d.querySelectorAll('.img_wrap .wrapper .image-box img')].map(url))===JSON.stringify(expected);
  },expected,{timeout:15000});
  const result=await page.evaluate(()=>{
    const d=[...document.querySelectorAll('[role=dialog][aria-label="编辑变体图片"]')].find(d=>d.getBoundingClientRect().width);
    if(!d)throw Error('变体图片框缺失');
    const gallery=[...d.querySelectorAll('.product_wrap .image-box')].map(b=>({bytes:b.querySelector('img')?.src,url:b.querySelector('input[type=checkbox]')?.value}));
    const resolve=img=>{const found=gallery.filter(g=>g.bytes===img?.src);if(found.length!==1)throw Error('图片无法唯一对应成品图库');return found[0].url;};
    return{main:resolve(d.querySelector('.main-page img')),images:[...d.querySelectorAll('.img_wrap .wrapper .image-box img')].map(resolve)};
  });
  if(!keepOpen)await page.click('[role=dialog][aria-label="编辑变体图片"] button:has-text("取 消")',{label:'关闭只读图片核对'});
  return result;
}

export {readDraft,readImages};

export async function collectFinishedDraft(page,input,receipt){
  input=structuredClone(input);
  const d=input.destination,g=input.goods,url='https://www.junfeikuajing.com/#/amazon/product/'+d.draftId+'?type=draft';
  if(input.mode!=='draft'||!/^\d+$/.test(String(d.draftId))||input.accountId<1||!input.productId)throw Error('只接受明确账号、产品及既有草稿');
  const library=JSON.parse(await fs.readFile(d.imageReceipt,'utf8'));
  if(library.status!=='library_package_saved_reopened_verified'||library.accountId!==input.accountId||library.productId!==input.productId||library.sku!==g.parentSku)throw Error('图片回执与本账号产品不符');
  const urls={};for(const u of library.upload.uploads){if(u.remote?.sha256!==u.sha256)throw Error('图片回执缺少内容核对');urls[u.sha256]=u.url;}
  for(const asset of input.assets){const raw=await fs.readFile(asset.path);if(crypto.createHash('sha256').update(raw).digest('hex')!==asset.sha256||!urls[asset.sha256])throw Error('当前成品变化或缺少ERP图片，未覆盖旧图');}
  let record;
  try{record=JSON.parse(await fs.readFile(receipt,'utf8'));if(record.snapshotSha256!==input.sha256)throw Error('采集快照变化，先核对原操作');}
  catch(e){if(e.code!=='ENOENT')throw e;record={status:'prepared',draftId:String(d.draftId),draftUrl:url,accountId:input.accountId,productId:input.productId,snapshotSha256:input.sha256,published:false,variantChecks:[],createdAt:new Date().toISOString()};await fs.writeFile(receipt,JSON.stringify(record,null,2),{flag:'wx'});}
  const persist=()=>writeJsonAtomic(receipt,record);
  try{
    // A newly transferred draft is configured through its visible ERP form.
    // Keep that form until its first Save; the native transfer already has a
    // durable one-shot response and real list readback. Recheck the inbox
    // after saving, so a SPA navigation cannot discard those form edits.
    const transferred=record.status==='prepared'&&record.nativeTransfer?.status==='native_join_verified'
      &&record.nativeTransfer.sent===1&&record.nativeTransfer.response?.body?.code===0
      &&String(record.nativeTransfer.draftId)===String(d.draftId)
      &&record.nativeTransfer.collectionId===record.collection?.id
      &&record.collection?.row?.join_platform?.includes('amazon');
    if(!transferred)await collectInbox(page,input,urls,record,persist);
    if(await page.url()!==url)await page.goto(url);
    await page.waitForFunction(()=>document.querySelector('input[placeholder="产品标题"]')?.value,undefined,{timeout:20000});
    const before=await readDraft(page);
    if(before.url!==url||before.store!==input.store||![g.parentSku,d.erpAssignedSku].includes(before.parentSku)||before.variants.length!==input.goodsItems.length||before.variants.some(v=>!input.goodsItems.some(i=>i.sku===v.sku)))throw Error('目标草稿身份或子SKU集合不一致');
    if(record.status==='prepared'){
      record.before=before;
      await saveDraft(page,input,urls,record,persist,patchDraftPayload);
    }
    // A resumed uncertain operation only reads this same draft; it never saves.
    const persisted=await readPersistedDraft(page,d.draftId);
    const checks=verifyPersistedDraft(persisted,input,urls);
    await page.waitForFunction(({sku,store,count})=>document.querySelector('input[placeholder^="父Sku,"]')?.value===sku&&document.querySelector('input[placeholder="店铺"]')?.value===store&&document.querySelectorAll('.el-table__body-wrapper input[placeholder="sku"]').length===count,{sku:g.parentSku,store:input.store,count:input.goodsItems.length},{timeout:25000});
    const actual=await readDraft(page);
    for(const [field,expected]of Object.entries({parentSku:g.parentSku,store:input.store,title:g.title,description:g.description,terms:g.terms,brand:g.brand,manufacturer:g.manufacturer,handlingDays:input.handlingDays}))if(actual[field]!==expected)throw Error('重开后字段不一致: '+field);
    if(JSON.stringify(actual.bullets)!==JSON.stringify(g.bullets))throw Error('重开后五点不一致');
    for(const v of input.goodsItems){const row=actual.variants.find(r=>r.sku===v.sku);if(!row||row.color!==v.color||![v.size,d.sizeValues[v.size]].includes(row.size)||Number(row.price)!==Number(v.price)||row.quantity!==String(v.quantity))throw Error('重开后变体颜色尺码或价格不符: '+v.sku);}
    record.reopened=actual;record.persistedReadback=persisted;record.variantChecks=checks;await persist();
    // An old successful upload receipt does not prove the object still exists:
    // ERP draft deletion can remove files referenced by other test records.
    let next=0;const imageChecks=[];
    await Promise.all(Array.from({length:4},async()=>{while(next<input.assets.length){const asset=input.assets[next++],url=urls[asset.sha256];imageChecks.push({sha256:asset.sha256,url,remote:await verifyRemoteAsset(url,asset)});}}));
    record.imageChecks=imageChecks;await persist();
    if(transferred)await collectInbox(page,input,urls,record,persist);
    if(record.error){(record.history??=[]).push({error:record.error,reconciledAt:new Date().toISOString()});delete record.error;}
    record.status='saved_reopened_verified';record.verifiedAt=new Date().toISOString();record.warnings=['仅保存草稿；ERP自动填入而未经本款证据确认的旧模板属性已清除。'];await persist();
    return record;
  }catch(e){record.error=e.message;await persist();throw e;}
}
