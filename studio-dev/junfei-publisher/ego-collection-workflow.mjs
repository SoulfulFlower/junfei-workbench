// Account/store-level native collection. No product bindings, ZIPs or publish.
import fs from 'node:fs/promises';
import {stageFinishedUploads} from './ego-collection-upload.mjs';
import {collectInbox,collectionRows} from './ego-collection-inbox.mjs';
import {submitNativeJoin} from './ego-native-transfer.mjs';
import {queryDrafts,nativeDraftMatches} from './ego-collection-lookup.mjs';
import {prepareNativeDraft} from './ego-collection-prepare.mjs';
import {patchDraftPayload} from './ego-finished-collection.mjs';
import {saveDraft} from './ego-draft-save.mjs';
import {readPersistedDraft,verifyPersistedDraft} from './ego-draft-readback.mjs';
import {verifyRemoteAsset} from './ego-draft-images.mjs';
import {ensureExplicitDraftGalleries} from './ego-explicit-galleries.mjs';

const defaults={upload:stageFinishedUploads,collect:collectInbox,rows:collectionRows,join:submitNativeJoin,
 query:queryDrafts,prepare:prepareNativeDraft,save:saveDraft,read:readPersistedDraft,verify:verifyPersistedDraft,remote:verifyRemoteAsset};

export async function runCollectionWorkflow(page,original,file,adapters={}){
 const input=structuredClone(original),api={...defaults,...adapters};let record;
 try{record=JSON.parse(await fs.readFile(file,'utf8'));}
 catch(e){if(e.code!=='ENOENT')throw e;record={accountId:input.accountId,productId:input.productId,destinationId:input.destination.destinationId,
  snapshotSha256:input.sha256,status:'workflow_prepared',phase:'查重与准备',stages:{},published:false};await fs.writeFile(file,JSON.stringify(record,null,2),{flag:'wx'});}
 if(record.accountId!==input.accountId||record.productId!==input.productId||record.snapshotSha256!==input.sha256||record.published!==false||input.mode!=='draft')throw Error('采集回执与本账号产品内容不符');
 if(record.destinationId&&record.destinationId!==input.destination.destinationId)throw Error('采集回执属于其他目标店铺');
 record.stages??={};
 const persist=async()=>{record.updatedAt=new Date().toISOString();await fs.writeFile(file+'.tmp',JSON.stringify(record,null,2));await fs.rename(file+'.tmp',file);};
 const phase=async(key,text,done=false)=>{record.phase=text;record.stages[key]=done?'completed':'running';await persist();};
 try{
  // SKU lookup is always before collection/creation, even after a restart.
  await phase('dedupe','查找原SKU和历史回执');
  const existing=await api.query(page,{sku:input.goods.parentSku});record.skuLookup=existing;await persist();
  if(!record.draftId&&existing.some(r=>r.sku===input.goods.parentSku&&r.store===input.store))throw Error('目标店铺已有同SKU草稿，但没有本次来源回执；保留它，不重复创建或覆盖');
  if(record.draftId&&existing.some(r=>r.sku===input.goods.parentSku&&r.store===input.store&&r.id!==String(record.draftId)))throw Error('目标店铺有多条同SKU草稿，请先对账，不重复提交');
  await phase('dedupe','SKU查重完成',true);
  await phase('images','读取或上传当前产品成品图片');const urls=await api.upload(page,input,record,persist);await phase('images','成品图片已上传并核对',true);
  // Complete a still-open, explicitly untransmitted Save confirmation without
  // pressing Save again. Otherwise an unknown transmitted Save is read-only.
  if(record.status==='save_unknown'&&record.requestSent===false&&record.draftId&&record.resolvedDestination){
   Object.assign(input.destination,record.resolvedDestination,{draftId:record.draftId});
   const pending=await page.evaluate(id=>location.hash==='#/amazon/product/'+id+'?type=draft'&&[...document.querySelectorAll('.el-message-box')].some(e=>e.getBoundingClientRect().width&&e.innerText.includes('不在亚马逊选项中。确定要保存吗？')),record.draftId);
   if(pending)await api.save(page,input,urls,record,persist,patchDraftPayload,{pending:true});
  }
  await phase('collection','保存或核对ERP采集列表');await api.collect(page,input,urls,record,persist);await phase('collection','采集列表已保存',true);
  let transfer=record.nativeTransfer;
  if(!record.draftId){
   const baseline=await api.query(page,{title:input.goods.title});
   if(!transfer){
    if(record.collection.row.join_platform.includes('amazon'))throw Error('采集记录已转入，但缺少草稿来源检查点；保留记录，不再次转入');
    transfer=record.nativeTransfer={status:'join_intended',createMode:'new_product',noExistingDraft:true,collectionId:record.collection.id,
     beforeDraftIds:baseline.map(r=>r.id),parentSku:input.goods.parentSku,store:input.store,startedAt:new Date().toISOString()};await persist();
   }
   if(['join_intended','join_not_sent'].includes(transfer.status)){
    await phase('native','原生转入亚马逊草稿箱');
    await page.goto('https://www.junfeikuajing.com/#/product/collect');await page.waitForSelector('input[placeholder="关键词搜索"]',{state:'visible'});
    const rows=(await api.rows(page,input)).filter(r=>r.sourceMatch);if(rows.length!==1||rows[0].id!==transfer.collectionId)throw Error('原采集来源不唯一');
    await api.join(page,transfer,persist);
   }
   // A lost native response is reconciled from the real joined flag plus the
   // unique new draft containing this exact child-SKU set; it is never resent.
   await page.goto('https://www.junfeikuajing.com/#/product/collect');await page.waitForSelector('input[placeholder="关键词搜索"]',{state:'visible'});
   const rows=(await api.rows(page,input)).filter(r=>r.sourceMatch);if(rows.length!==1||!rows[0].join_platform.includes('amazon'))throw Error('原生转入结果尚未确认，保留原检查点，不重新转入');
   record.collection.row=rows[0];
   const after=await api.query(page,{title:input.goods.title});const candidates=after.filter(r=>!transfer.beforeDraftIds.includes(r.id)&&(!r.store||r.store===input.store));
   const matched=[];for(const row of candidates){const data=await api.read(page,row.id);if(nativeDraftMatches(data.data,input))matched.push({row,data:data.data});}
   if(matched.length!==1)throw Error('原生转入后没有唯一的本款草稿，保留原编号，不重复创建');
   const found=matched[0];record.draftId=found.row.id;record.draftUrl='https://www.junfeikuajing.com/#/amazon/product/'+record.draftId+'?type=draft';
   Object.assign(transfer,{draftId:record.draftId,status:'native_join_verified',erpAssignedSku:found.data.sku,
    identityProof:{id:found.row.id,skus:found.data.items.map(v=>v.sku),parentSku:input.goods.parentSku,collectionId:record.collection.id,sourceMatch:true},
    reconciled:!transfer.response?.body||transfer.response.body.code!==0});await persist();
  }
  if(!transfer||transfer.collectionId!==record.collection.id||String(transfer.draftId)!==String(record.draftId))throw Error('缺少同一采集记录的原生草稿关联');
  await phase('native','原生草稿关联已核对',true);
  Object.assign(input.destination,record.resolvedDestination||{}, {draftId:record.draftId,erpAssignedSku:transfer.erpAssignedSku||input.destination.erpAssignedSku,nativeCollectionId:record.collection.id});
  let saved=await api.read(page,record.draftId),checks;
  try{checks=api.verify(saved,input,urls);}catch{}
  if(!checks){
   let inherited;try{inherited=verifyPersistedDraft(saved,input,urls,{allowInherited:true});}catch{}
   if(inherited?.some(v=>v.imagesSource==='parent_shared_gallery')){
    if(record.status==='save_unknown'&&record.requestSent!==false&&record.response?.code!==0)throw Error('原保存结果未知，仅对账，不再次保存图片');
    await phase('draft','将父体继承图片固定到每个子SKU');
    saved=await ensureExplicitDraftGalleries(page,input,urls,record,persist,{read:api.read,save:api.save,initialResponse:saved});
    checks=api.verify(saved,input,urls);
   }
  }
  if(!checks){
   if(record.status==='save_unknown'&&record.requestSent!==false)throw Error('原保存结果与成品未一致，先对账，不自动重发未知保存');
   await phase('draft','自动选择店铺、类目和真实变体字段');await api.prepare(page,input,record,persist);
   record.status='prepared';await persist();await api.save(page,input,urls,record,persist,patchDraftPayload);
   saved=await api.read(page,record.draftId);checks=api.verify(saved,input,urls);
  }
  await phase('draft','草稿已保存并重开',true);record.variantChecks=checks;record.persistedReadback=saved;await persist();
  await phase('verification','核对全部SKU、图序和远端图片哈希');
  const imageChecks=[];let next=0;await Promise.all(Array.from({length:4},async()=>{while(next<input.assets.length){const a=input.assets[next++];imageChecks.push({sha256:a.sha256,url:urls[a.sha256],remote:await api.remote(urls[a.sha256],a)});}}));
  record.imageChecks=imageChecks;record.resolvedDestination={...input.destination};
  // Final lookup proves repeated clicks/resumes did not create another draft.
  const final=await api.query(page,{sku:input.goods.parentSku}),same=final.filter(r=>r.sku===input.goods.parentSku&&r.store===input.store);
  if(same.length!==1||same[0].id!==String(record.draftId))throw Error('最终草稿查重不唯一');record.finalDraftRows=same;
  record.status='saved_reopened_verified';record.nativeTransfer=transfer;record.verifiedAt=new Date().toISOString();
  if(record.error){(record.history??=[]).push({error:record.error,resolvedAt:record.verifiedAt});delete record.error;}
  await phase('verification','原生采集与目标店铺草稿全部核对通过',true);return record;
 }catch(e){record.error=e.message;record.phase='已保留检查点：'+e.message;await persist();throw e;}
}
