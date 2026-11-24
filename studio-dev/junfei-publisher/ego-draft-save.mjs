// Uses the authenticated ERP Save action, including its enum confirmation.
export async function saveDraft(page,input,urls,record,persist,patchDraftPayload,{pending=false}={}){
 if(!pending)await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.getBoundingClientRect().width&&!b.disabled&&b.innerText.replace(/\s/g,'')==='保存'&&b.closest('form')?.innerText.includes('翻译类型')),undefined,{timeout:45000});
 if(record.response||record.requestSent)(record.saveAttempts??=[]).push({requestSent:record.requestSent,response:record.response,submitted:record.submitted,saveIntendedAt:record.saveIntendedAt});
 const install=String(function(input,urls){
  if(window.__finishedCollectionHook)throw Error('已有保存观察');
  const originalOpen=XMLHttpRequest.prototype.open,originalSend=XMLHttpRequest.prototype.send,targets=new WeakMap();
  const state={sent:false,response:null,error:null,payload:null,originalOpen,originalSend};window.__finishedCollectionHook=state;
  XMLHttpRequest.prototype.open=function(method,url,...args){targets.set(this,String(method).toUpperCase()==='POST'&&new URL(url,location.href).href==='https://app.junfeikuajing.com/api/amazon/goods/draft/json-update');return originalOpen.call(this,method,url,...args);};
  XMLHttpRequest.prototype.send=function(body){if(!targets.get(this))return originalSend.call(this,body);if(state.sent)throw Error('禁止重复保存');
   try{const payload=patchDraftPayload(JSON.parse(body),input,urls);state.payload=payload;state.sent=true;this.addEventListener('loadend',()=>{let r={};try{r=JSON.parse(this.responseText);}catch{}state.response={httpStatus:this.status,code:r.code,message:r.message};},{once:true});return originalSend.call(this,JSON.stringify(payload));}catch(e){state.error=e.message;throw e;}
  };
 });
 await page.evaluate('(()=>{const patchDraftPayload='+patchDraftPayload.toString()+';('+install+')('+JSON.stringify(input)+','+JSON.stringify(urls)+');})()');
 record.status='save_unknown';record.saveIntendedAt=new Date().toISOString();await persist();
 try{
  if(!pending){
   const sel=await page.evaluate(()=>{const es=[...document.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().width&&b.innerText.replace(/\s/g,'')==='保存'&&b.closest('form')?.innerText.includes('翻译类型'));if(es.length!==1)throw Error('保存按钮不唯一');es[0].setAttribute('data-exact-draft-save','true');es[0].scrollIntoView({block:'center',inline:'nearest'});return '[data-exact-draft-save]';});await page.click(sel,{label:'保存原生转入的美国站草稿'});
  }
  await page.waitForFunction(()=>window.__finishedCollectionHook?.response||window.__finishedCollectionHook?.error||[...document.querySelectorAll('.el-message-box')].some(e=>e.getBoundingClientRect().width),undefined,{timeout:20000});
  const box=await page.evaluate(()=>[...document.querySelectorAll('.el-message-box')].filter(e=>e.getBoundingClientRect().width).map(e=>e.innerText));
  if(box.length){
   if(box.length!==1||!box[0].includes('不在亚马逊选项中。确定要保存吗？')||/发布|删除/.test(box[0]))throw Error('非预期确认，未继续');
   const sel=await page.evaluate(()=>{const box=[...document.querySelectorAll('.el-message-box')].find(e=>e.getBoundingClientRect().width);const es=[...box.querySelectorAll('button')].filter(b=>b.innerText.trim()==='确定');if(es.length!==1)throw Error('保存确认按钮不唯一');es[0].setAttribute('data-enum-save-confirm','true');return '[data-enum-save-confirm]';});
   record.enumConfirmation=box[0];await persist();
   if(pending||(input.ukPrepared??input).destination?.countryCode==='GB'){
    await page.focus(sel);
    const stillOpen=await page.evaluate(()=>{const button=document.querySelector('[data-enum-save-confirm]');const hook=window.__finishedCollectionHook;return document.activeElement===button&&button?.closest('.el-message-box')?.innerText.includes('不在亚马逊选项中。确定要保存吗？')&&hook&&!hook.sent&&!hook.error;});
    if(!stillOpen)throw Error('原草稿确认框或保存观察变化，未继续');
    await page.press(sel,'Enter');
   }else await page.click(sel,{label:'确认仅保存已核对的变体草稿'});
  }
  await page.waitForFunction(()=>window.__finishedCollectionHook?.response||window.__finishedCollectionHook?.error,undefined,{timeout:25000});
 }finally{
  const result=await page.evaluate(()=>{const s=window.__finishedCollectionHook;return{sent:s.sent,response:s.response,error:s.error,payload:s.payload};});
  record.requestSent=result.sent;record.response=result.response;record.submitted=result.payload;if(result.error)record.error=result.error;await persist();
  await page.evaluate(()=>{const h=window.__finishedCollectionHook;if(h){XMLHttpRequest.prototype.open=h.originalOpen;XMLHttpRequest.prototype.send=h.originalSend;delete window.__finishedCollectionHook;}});
 }
 if(record.response?.httpStatus!==200||record.response.code!==0)throw Error(record.error||'ERP草稿保存未返回成功');
}
