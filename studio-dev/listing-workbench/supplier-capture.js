/* Local queue status only. Polling never opens a supplier page or retries a CAPTCHA. */
let supplierQueueRefreshing=false,supplierQueueResuming=false;
async function refreshSupplierQueue(){
 if(supplierQueueRefreshing||supplierQueueResuming)return;
 supplierQueueRefreshing=true;
 try{
  const r=await fetch('/api/supplier-capture/status');if(!r.ok)return;
  const data=await r.json();
  const pending=data.items.filter(x=>['queued','reading'].includes(x.state));
  let bar=document.getElementById('supplierQueueStatus');
  if(!pending.length&&!data.canResume){bar?.remove();return}
  if(!bar){bar=document.createElement('div');bar.id='supplierQueueStatus';bar.className='notice';bar.setAttribute('role','status');bar.style.cssText='margin:12px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap';document.querySelector('main header')?.after(bar)}
  bar.replaceChildren();
  const text=document.createElement('span');
  text.textContent=data.paused
   ? data.canResume?`1688采集已暂停 · ${pending.length}项待处理。请在 EGO「${data.browser.name||'Junfei 1688 serial collection'}」窗口完成登录或验证。`:'1688共享采集会话已暂停，等待原采集账号处理。'
   :`1688串行采集 · ${pending.length}项待处理 · 每款采完至少等待${data.intervalSeconds||90}秒 · 已采集资料直接复用`;
  if(data.ownerUnavailable)text.textContent='1688原采集账号已停用或删除，需要管理员恢复账号并核对原任务；队列保留暂停或未知结果，未重新打开商品页。';
  bar.append(text);
  if(data.canResume){
   const button=document.createElement('button');button.className='btn';button.textContent='已完成验证，继续采集';
   if(data.reason!=='login_or_verification'){
    text.textContent=`1688采集已暂停 · ${data.reason==='execution_unknown'?'上次执行中断，结果待核对':'原商品页资料尚未完整或浏览器控制已交还'}。请在原 EGO 采集窗口核对商品页，继续时只读取当前页。`;
    button.textContent='已处理，读取原页继续';
   }
   button.onclick=async()=>{supplierQueueResuming=true;button.disabled=true;button.textContent='正在读取原页…';try{
    const response=await fetch('/api/supplier-capture/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed:true})});
    const result=await response.json();if(!response.ok)throw Error(result.error||'继续失败');
    toast(result.paused?'原采集页仍未就绪，队列保持暂停':'已继续1688采集');
   }catch(e){toast(e.message)}finally{supplierQueueResuming=false;await refreshSupplierQueue()}};
   bar.append(button);
  }
 }catch{}finally{supplierQueueRefreshing=false}
}
function watchSupplierPreview(supplier){
 if(!supplier.captureId)return;
 const original=supplier.captureId;
 setTimeout(async()=>{
  const section=document.getElementById('supplier-import-preview');
  if(!document.getElementById('modal')?.open||section?.dataset.captureId!==original)return;
  try{
   const response=await fetch('/api/supplier-capture/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:supplier.url})});
   if(!response.ok)return;
   const result=await response.json();
   if(result.status==='collected'){
    Object.assign(supplier,result.supplier);delete supplier.captureId;delete supplier.captureStatus;
    section.outerHTML=supplierPreviewHtml(supplier);
    const name=document.getElementById('importName');if(name&&!name.value.trim())name.value=supplier.title;
    return;
   }
   supplier.captureStatus=result.status;
   if(['cancelled','archived'].includes(result.status)){
    const message=section.querySelector('[data-capture-message]');if(message)message.textContent=result.message||'此采集已取消，原记录已保留。';
    return;
   }
   const message=section.querySelector('[data-capture-message]');if(message)message.textContent=result.status==='paused'?'采集队列已暂停，请在页面上方处理验证后继续。':'正在统一队列中依次采集，完成后自动显示资料。';
  }catch{}
  watchSupplierPreview(supplier);
 },3000);
}
setInterval(refreshSupplierQueue,5000);

const supplierProductWaits=new Set();
async function captureSupplierForProduct(p,url){
 if(supplierProductWaits.has(p.id))return toast('此产品已在采集队列中，无需重复提交');
 const owner=signedUser;
 supplierProductWaits.add(p.id);
 try{
  await flushWorkspace();
  const snapshot=JSON.stringify(state.products.find(x=>x.id===p.id));
  const r=await fetch('/api/supplier-capture/request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
  let result=await r.json();if(!r.ok)throw Error(result.error||'采集提交失败');
  if(result.status!=='collected')toast('已加入统一采集队列，完成后更新本产品；无需重复打开商品页');
  while(result.status!=='collected'){
   if(['cancelled','archived'].includes(result.status))throw Error(result.message||'此采集已取消，原记录已保留。');
   if(signedUser!==owner)return;
   await new Promise(resolve=>setTimeout(resolve,3000));
   const response=await fetch('/api/supplier-capture/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
   result=await response.json();if(!response.ok)throw Error(result.error||'读取采集结果失败');
  }
  do{await flushWorkspace()}while(syncBusy);
  if(signedUser!==owner||JSON.stringify(state.products.find(x=>x.id===p.id))!==snapshot)throw Error('产品资料已变化，采集资料已缓存；重新点击货源采集可直接复用');
  syncBusy=true;
  try{
   for(let attempt=0;attempt<3;attempt++){
    const response=await fetch('/api/state');if(!response.ok)throw Error('无法读取最新产品资料');
    const {revision,state:workspace}=await response.json();
    const target=workspace.products.find(x=>x.id===p.id);
    if(signedUser!==owner||JSON.stringify(target)!==snapshot||JSON.stringify(state.products.find(x=>x.id===p.id))!==snapshot)throw Error('产品资料已变化，采集资料保留在缓存中，未覆盖修改');
    const previous=target.sourceImport?.supplier;
    target.sourceImport||={};
    if(previous?.url&&previous.url!==url)(target.sourceImport.supplierHistory||=[]).push(previous);
    target.sourceImport.supplier=result.supplier;target.sourceUrl=url;
    const filled=structuredClone(target);applySupplierPreview(filled,result.supplier);
    for(const field of ['style','material','dimensions','purchasePrice','packageDimensions','productWeight','packageWeight','packageContents','colorNames','sizeNames','features'])if(!target[field])target[field]=filled[field];
    if(!target.colorNames||target.colorNames===filled.colorNames)target.colors=filled.colors;
    if(!target.sizeNames||target.sizeNames===filled.sizeNames)target.sizes=filled.sizes;
    if(target.status==='已通过')target.status='需修改';
    workspace.reviews[p.id]={...workspace.reviews[p.id],copy:false,images:false,note:'货源资料已更新，待核对'};
    const save=await fetch('/api/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,state:workspace})});
    if(save.status===409)continue;
    const saved=await save.json();if(!save.ok)throw Error(saved.error||'保存失败');
    if(signedUser===owner&&!syncPending){state=workspace;serverRevision=saved.revision;basePersist();syncLabel('已保存到数据库');render()}
    toast('货源资料已更新，已有事实字段保留；请核对采集资料');return;
   }
   throw Error('工作空间仍在更新，采集资料已缓存，请稍后重试保存');
  }finally{syncBusy=false;if(syncPending&&!syncConflict)setTimeout(pushState,450)}
 }catch(e){toast(e.message)}finally{supplierProductWaits.delete(p.id)}
}
