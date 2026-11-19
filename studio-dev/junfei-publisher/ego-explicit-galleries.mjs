// Junfei nulls child images when they equal the parent gallery. Never publish
// that representation: pin seven images on every child, with a parent cover.
import {readPersistedDraft,verifyPersistedDraft} from './ego-draft-readback.mjs';
import {saveDraft} from './ego-draft-save.mjs';

export function draftBusinessProjection(data){
 const fields=['sku','uid','market_id','country_code','title','brand','manufacturer','part_number','country_of_origin','price','quantity','cost_price','list_price','product_type_name','category_path','variation_theme','standard_product_type','standard_product_id'];
 const extraFields=['attributes','keywords','product_description','bullet_point','length_unit','length','width','height','weight_unit','weight'];
 const pick=row=>({fields:Object.fromEntries(fields.filter(k=>row[k]!==undefined).map(k=>[k,row[k]])),extra:Object.fromEntries(extraFields.filter(k=>row.extra?.[k]!==undefined).map(k=>[k,row.extra[k]]))});
 const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):typeof v==='string'?v.replace(/<br\s*\/?\s*>/gi,'\n').replace(/\r\n/g,'\n'):v;
 return JSON.stringify(canonical({...pick(data),items:[...(data.items||[])].sort((a,b)=>a.sku.localeCompare(b.sku)).map(pick)}));
}

// Self-contained: saveDraft serializes this exact function into the page.
export function patchDraftGalleryPayload(body,input,urls){
 const s=input.galleryRepairSource,d=input.destination;
 if(!s||String(body.id)!==String(s.id)||String(s.id)!==String(d.draftId)||String(body.market_id)!==String(s.market_id)||body.country_code!==s.country_code||body.parent_sku!==s.sku||body.with_publish||body.publish||body.items?.length!==s.items?.length)throw Error('图片修复草稿身份或保存模式不符');
 const stable=v=>JSON.stringify(v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,JSON.parse(stable(v[k]))])):Array.isArray(v)?v.map(x=>JSON.parse(stable(x))):v??null);
 const text=v=>String(v??'').replace(/<br\s*\/?\s*>/gi,'\n').replace(/\r\n/g,'\n');
 for(const k of ['title','brand','manufacturer','part_number','country_of_origin','standard_product_type','standard_product_id','product_type_name','category_path','variation_theme'])if(text(body[k])!==text(s[k]))throw Error('图片保存不得修改商品字段 '+k);
 for(const k of ['price','quantity','cost_price','list_price'])if(text(body[k])!==text(s[k]))throw Error('图片保存不得修改经营字段 '+k);
 for(const k of ['product_description','keywords'])if(text(body[k])!==text(s.extra?.[k]))throw Error('图片保存不得修改文案 '+k);
 for(const k of ['attributes','bullet_point'])if(stable(body[k])!==stable(s.extra?.[k]))throw Error('图片保存不得修改属性或五点 '+k);
 const image=i=>{const a=input.assets[i],u=a&&urls[a.sha256];if(!u||!/^https:\/\//.test(u))throw Error('缺少已验证图片URL');return u;};
 const seen=new Set();
 const items=body.items.map(row=>{
  const old=s.items.find(v=>String(v.id)===String(row.id)),v=input.goodsItems.find(v=>v.sku===row.sku);
  if(!old||!v||old.sku!==row.sku||seen.has(row.sku)||v.imageIndices?.length!==7||new Set(v.imageIndices).size!==7)throw Error('图片修复子SKU或七图映射不符');seen.add(row.sku);
  for(const k of ['price','quantity','cost_price','list_price','title'])if(text(row[k])!==text(old[k]))throw Error('图片保存不得修改子体 '+k);
  if(stable(row.attributes)!==stable(old.extra?.attributes))throw Error('图片保存不得修改子体属性');
  for(const k of ['product_description','keywords'])if(text(row[k])!==text(old.extra?.[k]))throw Error('图片保存不得修改子体文案');
  if(stable(row.bullet_point)!==stable(old.extra?.bullet_point))throw Error('图片保存不得修改子体五点');
  const images=v.imageIndices.map(image);return{...row,main_image:images[0],images};
 });
 const first=input.goodsItems.find(v=>v.color===input.masterColor)||input.goodsItems[0],cover=image(first.imageIndices[0]);
 return{...body,main_image:cover,images:[cover],items,with_publish:false,publish:false};
}

export async function ensureExplicitDraftGalleries(page,input,urls,record,persist,adapters={}){
 const api={read:readPersistedDraft,save:saveDraft,...adapters};
 let response=adapters.initialResponse||await api.read(page,input.destination.draftId),checks;
 const owner=input.destination.erpAccountId||input.destination.erpUserId;
 if(!owner||String(response?.data?.uid)!==String(owner)||(response.data.items||[]).some(v=>String(v.uid)!==String(owner)))throw Error('图片检查ERP账号不符');
 try{checks=verifyPersistedDraft(response,input,urls);}catch{}
 if(checks){
  if(record.explicitGallery?.businessBefore&&draftBusinessProjection(response.data)!==record.explicitGallery.businessBefore)throw Error('图片保存后非图片业务资料发生变化，停止发布');
  if(record.explicitGallery){record.explicitGallery.status='verified';record.explicitGallery.checks=checks;await persist();}
  return response;
 }
 // Only the known shared-gallery compaction is migrated. Any SKU, price,
 // text, ordering or foreign-record mismatch remains a hard stop.
 const legacy=verifyPersistedDraft(response,input,urls,{allowInherited:true});
 if(!legacy.some(v=>v.imagesSource==='parent_shared_gallery'))throw Error('不是可迁移的父体图片继承记录');
 if(record.explicitGallery?.saveIntendedAt)throw Error('原图片保存尚未核对通过，仅对账，不重复提交');
 const state=record.explicitGallery={status:'preparing',draftId:String(response.data.id),businessBefore:draftBusinessProjection(response.data),source:structuredClone(response.data)};
 await persist();
 await api.save(page,{...input,galleryRepairSource:state.source},urls,state,persist,patchDraftGalleryPayload);
 response=await api.read(page,input.destination.draftId);
 checks=verifyPersistedDraft(response,input,urls);
 if(draftBusinessProjection(response.data)!==state.businessBefore)throw Error('图片保存后非图片业务资料发生变化，停止发布');
 state.status='verified';state.checks=checks;await persist();return response;
}
