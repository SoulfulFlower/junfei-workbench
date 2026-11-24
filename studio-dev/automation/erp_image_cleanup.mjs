// ERP picture cleanup uses current native online readbacks and exact local bytes.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {queryPublicationRows,readNativeOnline} from '../junfei-publisher/ego-publish-native.mjs';

export async function collectOnlineEvidence(page, families, output) {
  let result=[];
  try{result=JSON.parse(await fs.readFile(output,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
  for(const family of families){
    if(result.some(row=>row.job===family.job))continue;
    const board={job:family.job,productId:family.us.productId,boards:[]};
    const rows=await queryPublicationRows(page,{sku:family.us.goods.parentSku,section:'online'});
    for(const input of [family.us,family.uk].filter(Boolean)){
      const matches=rows.filter(row=>row.sku===input.goods.parentSku&&row.market?.alias===input.store);
      if(matches.length!==1){board.reason='Online record is missing or ambiguous';break;}
      const online=await readNativeOnline(page,String(matches[0].id),input);
      const source=online.data;
      const items=new Map((source?.items??[]).map(item=>[item.sku,item]));
      if(source?.status!=='online'||items.size!==input.goodsItems.length||
          input.goodsItems.some(item=>!items.get(item.sku)?.asin)){board.reason='Online variant coverage incomplete';break;}
      board.boards.push({input,online});
    }
    board.complete=board.boards.length===2&&!board.reason;
    result.push(board);
    await fs.writeFile(output,JSON.stringify(result,null,2));
  }
  return result;
}

export async function readInventory(page) {
  await page.goto('https://www.junfeikuajing.com/#/setting/picture',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>location.hash==='#/setting/picture'&&document.body.innerText.includes('空间使用情况')&&
    !document.body.innerText.includes('NaNMB')&&document.querySelector('button.btn-next'),undefined,{timeout:15000});
  const pages=[];
  // Start at page one even when the SPA retained the previous pagination state.
  while(await page.evaluate(()=>!document.querySelector('button.btn-prev').disabled)){
    const before=await page.evaluate(()=>document.querySelector('.el-pager .active')?.innerText);
    await page.click('button.btn-prev',{label:'读取图片空间首页'});
    await page.waitForFunction(previous=>document.querySelector('.el-pager .active')?.innerText!==previous,before,{timeout:10000});
  }
  for(let number=0;number<100;number++){
    const observation=await page.evaluate(()=>({
      page:document.querySelector('.el-pager .active')?.innerText,
      capacity:document.body.innerText.split('\n').map(x=>x.trim()).filter(Boolean).slice(0,34),
      rows:[...document.querySelectorAll('.imgList')].map(box=>({
        url:box.querySelector('[data-clipboard-text]')?.getAttribute('data-clipboard-text'),
        sizeText:box.querySelector('.img_size')?.innerText.trim(),
        createdText:box.querySelector('.img_Top2 span')?.innerText.trim()
      })).filter(row=>row.url),
      nextDisabled:document.querySelector('button.btn-next').disabled
    }));
    pages.push(observation);
    if(observation.nextDisabled)return pages;
    const before=observation.rows[0]?.url;
    await page.click('button.btn-next',{label:'核对下一页旧图片'});
    await page.waitForFunction(previous=>document.querySelector('.imgList [data-clipboard-text]')?.getAttribute('data-clipboard-text')!==previous,before,{timeout:10000});
  }
  throw Error('Picture inventory exceeded bounded pagination');
}

export async function makePlan(evidence, inventory, otherReferences, requiredMiB) {
  if(!Number.isFinite(requiredMiB)||requiredMiB<=0)throw Error('Required capacity must be positive');
  const present=new Map(inventory.flatMap(page=>page.rows).map(row=>[row.url,row]));
  const candidates=[],blocked=[];
  for(const family of evidence.filter(row=>row.complete)){
    const source=family.boards[0].input;
    for(const asset of source.assets){
      const url=source.urls?.[asset.sha256];
      if(!url||!present.has(url)||candidates.some(row=>row.url===url))continue;
      const references=otherReferences.filter(row=>row.productId!==source.productId);
      if(references.some(row=>row.shas.includes(asset.sha256)||row.urls.includes(url))){blocked.push({url,reason:'referenced_by_another_product'});continue;}
      let accepted=true;
      for(const {input,online} of family.boards){
        const items=new Map(online.data.items.map(row=>[row.sku,row]));
        const consumers=input.goodsItems.filter(row=>row.imageIndices.some(index=>input.assets[index].sha256===asset.sha256));
        if(!consumers.length){accepted=false;break;}
        for(const consumer of consumers){
          const actual=items.get(consumer.sku);
          const gallery=[actual.main_image,...(actual.extra?.images??[])];
          if(gallery.length!==7||gallery.some(link=>!/^https:\/\/m\.media-amazon\.com\/images\//.test(link))){accepted=false;break;}
        }
      }
      if(!accepted){blocked.push({url,reason:'amazon_gallery_not_complete'});continue;}
      const bytes=await fs.readFile(asset.path);
      if(crypto.createHash('sha256').update(bytes).digest('hex')!==asset.sha256)throw Error('Local backup hash mismatch');
      const size=bytes.length/1024/1024;
      candidates.push({url,sha256:asset.sha256,backup:asset.path,productId:source.productId,
        slot:asset.slot,sizeMiB:size,store:source.store,onlineJob:family.job});
      if(candidates.reduce((sum,row)=>sum+row.sizeMiB,0)>=requiredMiB)return {candidates,blocked,requiredMiB};
    }
  }
  return {candidates,blocked,requiredMiB};
}

async function writeJournal(file, value) {
  const temporary=new URL(file.href+'.tmp');
  await fs.writeFile(temporary,JSON.stringify(value,null,2));
  await fs.rename(temporary,file);
}

export async function waitForCapacity(page, minimumFreeMiB, timeoutMs=45000) {
  const deadline=Date.now()+timeoutMs;
  let capacity;
  do{
    await page.goto('https://www.junfeikuajing.com/#/setting/picture',{waitUntil:'domcontentloaded'});
    await page.reload();
    await page.waitForFunction(()=>document.body.innerText.includes('空间使用情况')&&
      !document.body.innerText.includes('NaNMB'),undefined,{timeout:12000});
    capacity=await page.evaluate(()=>{
      const lines=document.body.innerText.split('\n').map(line=>line.trim()).filter(Boolean);
      const total=Number(lines[lines.indexOf('总容量:')+1]),used=Number(lines[lines.indexOf('已使用:')+1]);
      if(!Number.isFinite(total)||!Number.isFinite(used)||total<=0)throw Error('Capacity labels changed');
      return {totalMiB:total,usedMiB:used,freeMiB:Number((total-used).toFixed(2)),checkedAt:new Date().toISOString()};
    });
    if(capacity.freeMiB>=minimumFreeMiB)return capacity;
    await new Promise(resolve=>setTimeout(resolve,2000));
  }while(Date.now()<deadline);
  throw Error('ERP capacity has not recovered: '+JSON.stringify(capacity));
}

export async function deletePlannedPictures(page, plan, journalFile) {
  if(!plan.candidates.length)throw Error('No verified pictures to delete');
  let journal={schema:1,startedAt:new Date().toISOString(),batches:[],deleted:[],status:'ready'};
  try{journal=JSON.parse(await fs.readFile(journalFile,'utf8'));}
  catch(error){if(error.code!=='ENOENT')throw error;}
  if(journal.status==='delete_unknown')throw Error('Previous deletion unknown; reconcile the existing batch before retrying');
  const desired=new Set(plan.candidates.filter(row=>!journal.deleted.includes(row.url)).map(row=>row.url));
  // New invocation starts at page one. Deleting a page shifts later rows forward.
  await page.goto('https://www.junfeikuajing.com/#/setting/picture',{waitUntil:'domcontentloaded'});
  await page.reload();
  await page.waitForFunction(()=>location.hash==='#/setting/picture'&&document.body.innerText.includes('空间使用情况')&&
    !document.body.innerText.includes('NaNMB')&&document.querySelector('button.btn-next'),undefined,{timeout:15000});
  for(let step=0;step<150&&desired.size;step++){
    const observed=await page.evaluate(wanted=>{
      if(location.hash!=='#/setting/picture')throw Error('Picture page changed');
      const rows=[...document.querySelectorAll('.imgList')];
      const selected=[];
      for(const [index,box] of rows.entries()){
        const url=box.querySelector('[data-clipboard-text]')?.getAttribute('data-clipboard-text');
        if(box.querySelector('input[type=checkbox]')?.checked)throw Error('Existing picture selection must be reconciled');
        box.removeAttribute('data-cleanup-picture');
        if(wanted.includes(url)){
          if(!box.querySelector('.el-checkbox'))throw Error('Picture checkbox unavailable');
          box.setAttribute('data-cleanup-picture',String(index));
          selected.push({url,selector:'[data-cleanup-picture="'+index+'"] .el-checkbox'});
        }
      }
      return {selected,page:document.querySelector('.el-pager .active')?.innerText,
        first:rows[0]?.querySelector('[data-clipboard-text]')?.getAttribute('data-clipboard-text'),
        last:document.querySelector('button.btn-next').disabled};
    },[...desired]);
    if(!observed.selected.length){
      if(observed.last)break;
      await page.click('button.btn-next',{label:'定位已核实旧图片'});
      await page.waitForFunction(before=>document.querySelector('.imgList [data-clipboard-text]')?.getAttribute('data-clipboard-text')!==before,observed.first,{timeout:10000});
      continue;
    }
    for(const item of observed.selected)await page.click(item.selector,{label:'选择已有备份的旧图'});
    const urls=observed.selected.map(row=>row.url);
    await page.evaluate(expected=>{
      const checked=[...document.querySelectorAll('.imgList')].filter(box=>box.querySelector('input[type=checkbox]')?.checked)
        .map(box=>box.querySelector('[data-clipboard-text]')?.getAttribute('data-clipboard-text'));
      if(checked.length!==expected.length||checked.some(url=>!expected.includes(url)))throw Error('Delete selection changed');
      const buttons=[...document.querySelectorAll('button')].filter(button=>button.getClientRects().length&&button.innerText.trim()==='删除'&&!button.disabled);
      if(buttons.length!==1)throw Error('Delete control ambiguous');
      buttons[0].setAttribute('data-cleanup-delete','true');
    },urls);
    const batch={urls,intendedAt:new Date().toISOString(),status:'delete_unknown'};
    journal.batches.push(batch);journal.status='delete_unknown';
    await writeJournal(journalFile,journal);
    await page.evaluate(count=>{
      if(window.__pictureCleanupAudit)throw Error('Previous delete audit still active');
      const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,requests=new WeakMap();
      const state={open,send,requested:false,result:null,ids:null,error:null};
      window.__pictureCleanupAudit=state;
      XMLHttpRequest.prototype.open=function(method,url,...rest){
        requests.set(this,{method:String(method).toUpperCase(),url:new URL(url,location.href)});
        return open.call(this,method,url,...rest);
      };
      XMLHttpRequest.prototype.send=function(body){
        const request=requests.get(this);
        if(request?.method==='POST'&&request.url.href==='https://app.junfeikuajing.com/api/cloud-storage/file/delete'){
          const value=JSON.parse(body);
          if(state.requested||!Array.isArray(value.ids)||value.ids.length!==count||
              new Set(value.ids).size!==count||value.ids.some(id=>!Number.isSafeInteger(Number(id)))){
            state.error='Native delete IDs do not match the selected batch size';throw Error(state.error);
          }
          state.ids=value.ids.map(String);state.requested=true;
          this.addEventListener('loadend',()=>{
            let response;try{response=JSON.parse(this.responseText);}catch{}
            state.result={httpStatus:this.status,code:response?.code};
          },{once:true});
        }
        return send.call(this,body);
      };
    },urls.length);
    await page.click('[data-cleanup-delete]',{label:'删除已核实旧图库'});
    await page.waitForFunction(()=>window.__pictureCleanupAudit?.result||window.__pictureCleanupAudit?.error||
      [...document.querySelectorAll('.el-message-box')].some(box=>box.getClientRects().length&&box.innerText.includes('删除')),undefined,{timeout:15000});
    const confirmation=await page.evaluate(()=>{
      const state=window.__pictureCleanupAudit;
      if(state?.error)throw Error(state.error);
      if(state?.requested||state?.result)return null;
      const boxes=[...document.querySelectorAll('.el-message-box')].filter(box=>box.getClientRects().length&&box.innerText.includes('删除'));
      if(boxes.length!==1)throw Error('Delete confirmation ambiguous');
      const buttons=[...boxes[0].querySelectorAll('button')].filter(button=>button.innerText.trim()==='确定'&&!button.disabled);
      if(buttons.length!==1)throw Error('Confirm control changed');
      buttons[0].setAttribute('data-cleanup-confirm','true');
      return boxes[0].innerText;
    });
    batch.confirmation=confirmation;await writeJournal(journalFile,journal);
    if(confirmation!==null)await page.click('[data-cleanup-confirm]',{label:'确认已授权旧图清理'});
    await page.waitForFunction(()=>window.__pictureCleanupAudit?.result||window.__pictureCleanupAudit?.error,undefined,{timeout:15000});
    const response=await page.evaluate(()=>{
      const state=window.__pictureCleanupAudit;
      XMLHttpRequest.prototype.open=state.open;XMLHttpRequest.prototype.send=state.send;
      delete window.__pictureCleanupAudit;
      return {ids:state.ids,result:state.result,error:state.error};
    });
    batch.nativeResponse=response;await writeJournal(journalFile,journal);
    if(response.error||response.result?.httpStatus!==200||response.result.code!==0)throw Error('Native picture deletion not confirmed');
    await page.waitForFunction(expected=>{
      const visible=[...document.querySelectorAll('.imgList [data-clipboard-text]')].map(el=>el.getAttribute('data-clipboard-text'));
      return expected.every(url=>!visible.includes(url))&&![...document.querySelectorAll('.el-message-box')].some(box=>box.getClientRects().length);
    },urls,{timeout:15000});
    batch.status='removed_from_list';batch.finishedAt=new Date().toISOString();
    journal.deleted.push(...urls);journal.status='ready';
    for(const url of urls)desired.delete(url);
    await writeJournal(journalFile,journal);
    // The ERP can retain IDs of a just-deleted batch in its selection model.
    // Reload before selecting another batch so the native request is fresh.
    await page.reload();
    await page.waitForFunction(()=>document.body.innerText.includes('空间使用情况')&&
      !document.body.innerText.includes('NaNMB')&&document.querySelector('button.btn-next'),undefined,{timeout:15000});
  }
  journal.status=desired.size?'recheck_remaining':'list_verified';
  journal.remaining=[...desired];await writeJournal(journalFile,journal);
  return journal;
}

export async function reconcilePendingDeletion(page, journalFile) {
  const journal=JSON.parse(await fs.readFile(journalFile,'utf8'));
  if(journal.status!=='delete_unknown')return journal;
  const batch=journal.batches.at(-1);
  const audit=await page.evaluate(()=>{
    const state=window.__pictureCleanupAudit;
    if(!state)return null;
    const result={requested:state.requested,error:state.error,ids:state.ids,result:state.result};
    XMLHttpRequest.prototype.open=state.open;XMLHttpRequest.prototype.send=state.send;
    delete window.__pictureCleanupAudit;
    return result;
  });
  if(audit?.error&&audit.requested===false){
    batch.status='blocked_before_transmission';batch.nativeResponse=audit;
    journal.status='ready';await writeJournal(journalFile,journal);
    return journal;
  }
  const inventory=await readInventory(page);
  const present=new Set(inventory.flatMap(page=>page.rows).map(row=>row.url));
  if(batch.urls.some(url=>present.has(url)))throw Error('Original delete outcome unresolved; retain journal');
  batch.status='reconciled_absent_from_full_inventory';
  batch.finishedAt=new Date().toISOString();
  batch.nativeIdsUnavailable=!batch.nativeResponse?.ids;
  if(audit?.requested&&audit.result){
    batch.nativeResponse=audit;batch.nativeIdsUnavailable=!audit.ids;
  }
  journal.deleted=[...new Set([...journal.deleted,...batch.urls])];
  journal.status='ready';await writeJournal(journalFile,journal);
  return journal;
}

export async function cleanupWorkbenchPictures(page, request, outputDirectory) {
  const file=name=>new URL(name,outputDirectory);
  const evidence=await collectOnlineEvidence(page,request.families,file('online-evidence.json'));
  const inventory=await readInventory(page);
  await fs.writeFile(file('before-inventory.json'),JSON.stringify(inventory,null,2));
  const plan=await makePlan(evidence,inventory,request.otherReferences,request.requiredMiB);
  await fs.writeFile(file('plan.json'),JSON.stringify(plan,null,2));
  const estimatedMiB=plan.candidates.reduce((sum,row)=>sum+row.sizeMiB,0);
  if(!request.execute)return {mode:'plan',candidates:plan.candidates.length,estimatedMiB};
  if(estimatedMiB<request.requiredMiB)throw Error('Insufficient verified pictures; existing draft retained');
  const journal=await deletePlannedPictures(page,plan,file('delete-journal.json'));
  const after=await readInventory(page);
  await fs.writeFile(file('after-inventory.json'),JSON.stringify(after,null,2));
  const stillListed=after.flatMap(page=>page.rows).filter(row=>journal.deleted.includes(row.url));
  if(stillListed.length)throw Error('Deleted pictures still listed; reconcile before continuing');
  const before=inventory[0].capacity;
  const used=Number(before[before.indexOf('已使用:')+1]),total=Number(before[before.indexOf('总容量:')+1]);
  if(!Number.isFinite(used)||!Number.isFinite(total))throw Error('Original capacity labels changed');
  const capacity=await waitForCapacity(page,Math.max(0,request.requiredMiB-Math.max(0,used-total)));
  await fs.writeFile(file('verified-capacity.json'),JSON.stringify(capacity,null,2));
  return {mode:'executed',deleted:journal.deleted.length,estimatedMiB,capacity,
    note:'Recheck the actual upload signature and original task before resuming.'};
}
