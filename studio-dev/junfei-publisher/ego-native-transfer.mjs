// Native ERP collection -> Amazon draft. Persist intent before the sole POST;
// uncertain outcomes require reconciliation and never trigger another join.
export function nativeJoinAllowed(journal,row){
 if(String(row.id)!==String(journal.collectionId)||!Array.isArray(row.join_platform))throw Error('原生采集身份不符');
 if(row.join_platform.includes('amazon'))return false;
 const fresh=journal.createMode==='new_product'&&journal.noExistingDraft===true;
 const replacement=journal.oldDraftRemoved&&journal.zeroBeforeJoin?.rows?.length===0&&journal.replacementApproved;
 if(!['join_intended','join_not_sent'].includes(journal.status)||(!fresh&&!replacement))throw Error('原生转入结果未知或尚未完成查重，不重发');
 return true;
}

export async function submitNativeJoin(page,journal,persist){
 const current=await page.evaluate(id=>{
  if(location.hash!=='#/product/collect')throw Error('非采集列表');
  const rows=[...document.querySelectorAll('.el-table__body-wrapper tr')].filter(r=>r.innerText.includes(id));
  if(rows.length!==1)throw Error('采集行不唯一');return{id,join_platform:rows[0].innerText.includes('亚马逊草稿箱')?['amazon']:[]};
 },journal.collectionId);
 if(!nativeJoinAllowed(journal,current))return;
 const selector=await page.evaluate(id=>{
  const rows=[...document.querySelectorAll('.el-table__body-wrapper tr')],index=rows.findIndex(r=>r.innerText.includes(id));
  const fixed=document.querySelectorAll('.el-table__fixed-right .el-table__body tr')[index];
  const es=[...(fixed||rows[index]).querySelectorAll('input[placeholder="入仓到"]')].filter(e=>e.getBoundingClientRect().width&&getComputedStyle(e).visibility==='visible');
  if(es.length!==1)throw Error('原生转入入口不唯一');es[0].setAttribute('data-native-join','true');return '[data-native-join]';
 },journal.collectionId);
 await page.click(selector);await page.waitForFunction(()=>[...document.querySelectorAll('.el-select-dropdown')].some(e=>e.getBoundingClientRect().width&&e.innerText.trim()==='亚马逊草稿箱'),undefined,{timeout:5000});
 await page.evaluate(id=>{
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,requests=new WeakMap(),s={open,send,sent:0,response:null,rows:null};window.__nativeJoin=s;
  XMLHttpRequest.prototype.open=function(method,url,...rest){requests.set(this,{method:String(method).toUpperCase(),url:new URL(url,location.href).href});return open.call(this,method,url,...rest);};
  XMLHttpRequest.prototype.send=function(body){const q=requests.get(this);
   if(q?.url==='https://app.junfeikuajing.com/api/goods/join-platfrom'&&q.method==='POST'){
    const p=JSON.parse(body);if(s.sent||p.ids?.length!==1||String(p.ids[0])!==id||p.platform!=='amazon')throw Error('禁止重复或非目标原生转入');s.sent++;
    this.addEventListener('loadend',()=>{let response;try{response=JSON.parse(this.responseText);}catch{}s.response={http:this.status,body:response};},{once:true});
   }else if(q?.method==='GET'&&q.url.startsWith('https://app.junfeikuajing.com/api/goods/index?')){
    this.addEventListener('loadend',()=>{try{s.rows=JSON.parse(this.responseText).data.list.data;}catch{}},{once:true});
   }return send.call(this,body);
  };
 },journal.collectionId);
 journal.status='join_unknown';await persist();
 try{
  const option=await page.evaluate(()=>{const es=[...document.querySelectorAll('.el-select-dropdown')].filter(e=>e.getBoundingClientRect().width).flatMap(e=>[...e.querySelectorAll('li')]).filter(e=>e.innerText.trim()==='亚马逊草稿箱');if(es.length!==1)throw Error('目标选项不唯一');es[0].setAttribute('data-native-amazon','true');return '[data-native-amazon]';});
  await page.click(option,{label:'仅一次原生转入亚马逊草稿箱'});
  await page.waitForFunction(()=>window.__nativeJoin?.response,undefined,{timeout:25000});
  Object.assign(journal,await page.evaluate(()=>({sent:window.__nativeJoin.sent,response:window.__nativeJoin.response})));await persist();
  if(journal.response.http!==200||journal.response.body?.code!==0)throw Error('原生转入未返回成功');
  await page.waitForFunction(id=>window.__nativeJoin?.rows?.some(r=>String(r.id)===id&&r.join_platform.includes('amazon')),journal.collectionId,{timeout:15000});
  journal.row=await page.evaluate(id=>window.__nativeJoin.rows.find(r=>String(r.id)===id),journal.collectionId);journal.status='native_join_verified';await persist();
 }finally{
  const state=await page.evaluate(()=>{const s=window.__nativeJoin;return s?{sent:s.sent,response:s.response}:null;});
  if(state){Object.assign(journal,state);if(state.sent===0&&journal.status==='join_unknown')journal.status='join_not_sent';await persist();}
  await page.evaluate(()=>{const s=window.__nativeJoin;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__nativeJoin;}});
 }
}
