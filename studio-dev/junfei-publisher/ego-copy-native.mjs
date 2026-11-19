// Native source-row Copy. The route is observed from the UI at runtime; no
// undocumented copy endpoint is synthesized. SKU correction is a later step.
import {queryDrafts} from './ego-collection-lookup.mjs';
import {readPersistedDraft} from './ego-draft-readback.mjs';
import {publicationFingerprint,verifyPublication,readNativePublication,readNativeOnline,resolvePublicationSource,queryPublicationRows} from './ego-publish-native.mjs';

export function verifyCopiedDraft(response,source,sourceEvidence,draftId){
 const d=response?.data,fields=source.destination.variationFields||{color:'color.0.value',size:'apparel_size.0.size'};
 if(response?.code!==0||String(d?.id)!==String(draftId)||String(d.uid)!==String(source.destination.erpAccountId)||d.title!==source.goods.title||d.items?.length!==source.goodsItems.length)throw Error('复制草稿账号、来源或子体数不符');
 if(d.market?.alias!==source.store||String(d.market_id)!==String(source.destination.marketId)||d.country_code!==source.destination.countryCode)throw Error('复制草稿的原店铺身份不符，禁止猜测目标');
 const get=(row,path)=>row.variation?.[path]??path.split('.').reduce((v,k)=>v?.[k],row.extra?.attributes);
 const shared=source.assets.map(v=>source.urls[v.sha256]),used=new Set();
 if(JSON.stringify(d.extra?.images)!==JSON.stringify(sourceEvidence.extra?.images))throw Error('复制草稿公共图库与原商品不符');
 if(JSON.stringify(d.extra?.images)!==JSON.stringify(shared)&&JSON.stringify(d.extra?.images)!==JSON.stringify([sourceEvidence.main_image]))throw Error('复制来源图库不符');
 const mapping=source.goodsItems.map(v=>{
  const matches=d.items.filter(row=>get(row,fields.color)===v.color&&get(row,fields.size)===source.destination.sizeValues[v.size]);
  if(matches.length!==1)throw Error('复制草稿颜色尺码不能唯一对应原SKU');
  const row=matches[0];if(!row.id||used.has(String(row.id))||String(row.pid)!==String(d.id)||String(row.uid)!==String(source.destination.erpAccountId))throw Error('复制草稿子体归属不符');used.add(String(row.id));
  const expected=v.imageIndices.map(i=>source.urls[source.assets[i].sha256]);
  const raw=row.extra?.images,inherited=raw==null||(Array.isArray(raw)&&!raw.length);
  // Copy identity is not publication readiness. A historical inherited source
  // can still be associated with its native copy; UK preparation rewrites it
  // to explicit child galleries and performs the strict publication check.
  const images=inherited&&JSON.stringify(shared)===JSON.stringify(expected)?shared:raw;
  if(row.main_image!==expected[0]||JSON.stringify(images)!==JSON.stringify(expected))throw Error('复制草稿原颜色的逐图顺序不符');
  return{sourceSku:v.sku,copiedSku:row.sku,itemId:String(row.id),color:v.color,size:v.size,images,imagesSource:inherited?'legacy_parent_gallery':'child_gallery'};
 });
 if(String(sourceEvidence.id)===String(d.id))throw Error('复制结果仍是源发布记录');
 return{draftId:String(d.id),erpAccountId:String(d.uid),copiedParentSku:d.sku,sourceParentSku:source.goods.parentSku,imagePersistenceVerified:mapping.every(v=>v.imagesSource==='child_gallery'),mapping};
}

export async function submitNativeCopy(page,input,record,persist){
 const source=input.source,publishId=String(input.copySource?.recordId||input.sourcePublication.publishId),section=input.copySource?.section||'publish';
 if(record.phase!=='copy_unknown'||String(record.intent?.sourcePublishId)!==String(input.sourcePublication.publishId)||String(record.intent?.sourceRecordId||publishId)!==publishId||record.nativeRequests?.length)throw Error('缺少已持久复制意图或已有原请求，禁止重发');
 await queryPublicationRows(page,{sku:source.goods.parentSku,section});
 const menu=await page.evaluate(({publishId,sku,store})=>{
  const rows=[...document.querySelectorAll('.el-table__body tr')].filter(r=>r.getBoundingClientRect().width&&r.cells[1]?.innerText.trim()===publishId&&r.innerText.includes(sku)&&r.innerText.includes(store));
  if(rows.length!==1)throw Error('发布中源行不唯一');const buttons=[...rows[0].querySelectorAll('button,.el-dropdown-link')].filter(v=>v.innerText.trim()==='操作');if(buttons.length!==1)throw Error('源行没有唯一的原生操作入口');buttons[0].setAttribute('data-native-copy-menu','true');return '[data-native-copy-menu]';
 },{publishId,sku:source.goods.parentSku,store:source.store});
 await page.hover(menu);
 await page.waitForFunction(()=>[...document.querySelectorAll('.el-dropdown-menu')].filter(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility!=='hidden').flatMap(e=>[...e.querySelectorAll('li')]).filter(e=>e.innerText.trim()==='复制').length===1,undefined,{timeout:6000});
 const action=await page.evaluate(()=>{
  const options=[...document.querySelectorAll('.el-dropdown-menu')].filter(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility!=='hidden').flatMap(e=>[...e.querySelectorAll('li')]).filter(e=>e.innerText.trim()==='复制');
  if(options.length!==1)throw Error('发布中原行没有唯一复制入口，保留检查点');options[0].setAttribute('data-native-copy-once','true');return '[data-native-copy-once]';
 });
 await page.evaluate(publishId=>{
  if(window.__nativeCopyWrite)throw Error('已有原生复制操作');const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__nativeCopyWrite={open,send,requests:[]};
  XMLHttpRequest.prototype.open=function(m,u,...r){targets.set(this,{method:String(m).toUpperCase(),url:new URL(u,location.href)});return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(body){const q=targets.get(this),s=window.__nativeCopyWrite;
   if(q?.method==='POST'&&q.url.origin==='https://app.junfeikuajing.com'&&q.url.pathname.startsWith('/api/amazon/goods/')){
    const payload=JSON.parse(body),ids=Array.isArray(payload.ids)?payload.ids:payload.id!==undefined?[payload.id]:[];
    if(!/(?:^|\/)copy(?:\/|$)/.test(q.url.pathname)||s.requests.length||ids.length!==1||String(ids[0])!==publishId)throw Error('拦截非目标复制或重复复制请求');
    const request={path:q.url.pathname,payload,sentAt:new Date().toISOString(),response:null};s.requests.push(request);
    this.addEventListener('loadend',()=>{let value;try{value=JSON.parse(this.responseText);}catch{}request.response={httpStatus:this.status,body:value};},{once:true});
   }return send.call(this,body);
  };
 },publishId);
 try{await page.click(action);await page.waitForFunction(()=>window.__nativeCopyWrite?.requests.some(v=>v.response),undefined,{timeout:25000});}
 finally{
  record.nativeRequests=await page.evaluate(()=>window.__nativeCopyWrite?.requests||[]);await persist();
  await page.evaluate(()=>{const s=window.__nativeCopyWrite;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__nativeCopyWrite;}});
 }
 const response=record.nativeRequests[0]?.response;
 if(response?.httpStatus!==200||response.body?.code!==0)throw Error('复制响应未知，仅查原记录，不再次复制');
}

export async function copyNative(page,input,record,persist,adapters={}){
 const api={readSource:readNativePublication,querySourceRows:queryPublicationRows,readOnline:readNativeOnline,query:queryDrafts,read:readPersistedDraft,submit:submitNativeCopy,...adapters};
 const {source,target,sourcePublication}=input;
 if(!target?.ukTarget||target.ukTarget.countryCode!=='GB'||source.accountId!==target.accountId||source.productId!==target.productId||!sourcePublication?.publishId)throw Error('跨站复制缺少对应账号产品、英国目标或真实美国任务');
 const observed=await resolvePublicationSource(page,source,sourcePublication,{read:api.readSource,query:api.querySourceRows,readOnline:api.readOnline});
 const sourceEvidence=observed.response,sourceIdentity=observed.identity;
 if(sourceIdentity.countryCode!=='US')throw Error('跨站复制来源必须是美国发布中记录');
 const fingerprint=publicationFingerprint({accountId:source.accountId,productId:source.productId,sourcePublishId:sourcePublication.publishId,
  sourceFingerprint:sourcePublication.fingerprint,target:target.ukTarget,commerce:target.ukCommerce});
 if(record.fingerprint&&record.fingerprint!==fingerprint){
  // A category choice made after observing the UK editor is preparation
  // metadata. It must not replay an already verified native copy. All source,
  // destination identity and commerce fields still match the frozen proof.
  const identityTarget=structuredClone(target.ukTarget);delete identityTarget.categoryHints;
  const originalFingerprint=publicationFingerprint({accountId:source.accountId,productId:source.productId,sourcePublishId:sourcePublication.publishId,
   sourceFingerprint:sourcePublication.fingerprint,target:identityTarget,commerce:target.ukCommerce});
  if(record.phase!=='copy_verified'||!record.draftId||!target.ukTarget.categoryHints?.path||record.fingerprint!==originalFingerprint)throw Error('复制回执来源或英国目标不符');
 }
 if(record.draftId){
  // A prepared draft may already have its UK identity. Do not overwrite its
  // original copy proof with a check against the pre-correction US identity.
  if(record.phase!=='copy_verified'||!record.identity||record.identity.draftId!==String(record.draftId))throw Error('复制草稿缺少原关联证明');
  return record;
 }
 Object.assign(record,{fingerprint,sourcePublishId:String(sourcePublication.publishId)});
 // Preserve the evidence used for the original copy; later reads and UK
 // corrections must not rewrite that historical source snapshot.
 record.sourceEvidence??=structuredClone(sourceEvidence.data);record.urls??=structuredClone(source.urls);
 if(!record.intent){
  const exact=row=>row.sku===source.goods.parentSku&&String(row.market_id)===String(source.destination.marketId)&&row.country_code==='US'&&row.market?.alias===source.store;
  let copySource={recordId:observed.recordId,section:observed.section};
  const sourceRows=await api.querySourceRows(page,{sku:source.goods.parentSku,section:copySource.section});
  if(!sourceRows.some(row=>exact(row)&&String(row.id)===copySource.recordId)){
   const onlineRows=copySource.section==='online'?sourceRows:await api.querySourceRows(page,{sku:source.goods.parentSku,section:'online'}),candidates=onlineRows.filter(exact);
   if(candidates.length!==1)throw Error('发布中源行已变化且在线来源不唯一，不提交复制');
   const online=await api.readOnline(page,candidates[0].id,source),proof=verifyPublication(online,source,candidates[0].id,{allowOnline:true});
   if(!proof.allChildrenOnline)throw Error('在线复制来源未核实全部子体，不提交复制');
   copySource={recordId:String(candidates[0].id),section:'online'};
   record.onlineSourceObservation={recordId:copySource.recordId,identity:proof,checkedAt:new Date().toISOString()};
  }
  const baseline=await api.query(page,{title:source.goods.title});
  record.intent={createdAt:new Date().toISOString(),sourcePublishId:record.sourcePublishId,beforeDraftIds:baseline.map(v=>String(v.id)),
   sourceRecordId:copySource.recordId,sourceSection:copySource.section,sourceFingerprint:publicationFingerprint(sourceEvidence.data)};record.phase='copy_unknown';await persist();
  try{await api.submit(page,{...input,copySource},record,persist);}catch(error){record.lastSubmitError=String(error.message);await persist();}
 }
 const after=await api.query(page,{title:source.goods.title}),matched=[];
 for(const row of after.filter(v=>!record.intent.beforeDraftIds.includes(String(v.id)))){
  const response=await api.read(page,row.id);
  try{matched.push({row,response,identity:verifyCopiedDraft(response,source,sourceEvidence.data,row.id)});}catch{}
 }
 if(matched.length!==1){record.phase='copy_unknown';await persist();throw Error('复制后未确认唯一的来源草稿，不重新复制');}
 const found=matched[0];Object.assign(record,{draftId:String(found.row.id),identity:found.identity,phase:'copy_verified',
  sourceLink:{sourcePublishId:record.sourcePublishId,draftId:String(found.row.id),method:'persisted_intent_unique_new_variants_and_images',beforeDraftIds:record.intent.beforeDraftIds}});
 await persist();return record;
}
