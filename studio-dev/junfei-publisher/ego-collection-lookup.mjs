// Observe actual list requests dispatched by the normal ERP search form.
export async function queryDrafts(page,{sku='',title=''}){
 if(!sku&&!title)throw Error('草稿查重必须指定本款SKU或标题');
 await page.goto('https://www.junfeikuajing.com/#/goods/amazon/draft');await page.reload();
 await page.waitForSelector('input[placeholder="请输入sku"]',{state:'visible'});
 const needle=sku||title;
 await page.evaluate(needle=>{
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();window.__collectionDraftQuery={open,send,result:null};
  XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='GET'&&url.origin==='https://app.junfeikuajing.com'&&url.pathname.includes('/draft')&&[...url.searchParams.values()].includes(needle));return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(b){if(targets.get(this))this.addEventListener('loadend',()=>{let code;try{code=JSON.parse(this.responseText).code;}catch{}window.__collectionDraftQuery.result={status:this.status,code};},{once:true});return send.call(this,b);};
 },needle);
 let response;
 try{
  await page.fill('input[placeholder="请输入sku"]',sku);await page.fill('input[placeholder="请输入商品标题"]',title);await page.fill('input[placeholder="请输入商品id"]','');
  await page.click('loc=role:button[name="搜索"]');await page.waitForFunction(()=>window.__collectionDraftQuery?.result,undefined,{timeout:15000});response=await page.evaluate(()=>window.__collectionDraftQuery.result);
 }finally{await page.evaluate(()=>{const s=window.__collectionDraftQuery;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__collectionDraftQuery;}});}
 if(response.status!==200||response.code!==0)throw Error('草稿查重没有返回真实结果，不执行转入');
 await page.waitForFunction(()=>![...document.querySelectorAll('.el-loading-mask')].some(e=>e.getBoundingClientRect().width&&getComputedStyle(e).display!=='none'),undefined,{timeout:10000});
 return page.evaluate(()=>{
  const total=document.querySelector('.el-pagination__total')?.innerText.match(/\d+/)?.[0];if(total&&Number(total)>20)throw Error('SKU匹配过多，请先核对重复资料');
  return [...document.querySelectorAll('.el-table__body tr')].filter(r=>r.getBoundingClientRect().width&&r.cells.length===9).map(r=>({id:r.cells[1].innerText.trim(),title:r.cells[3].innerText.trim(),store:r.cells[4].innerText.trim(),sku:r.cells[5].innerText.trim(),status:r.cells[7].innerText.trim()}));
 });
}

export function nativeDraftMatches(data,input){
 if(!data||data.title!==input.goods.title||data.items?.length!==input.goodsItems.length)return false;
 const expected=new Set(input.goodsItems.map(v=>v.sku));
 return new Set(data.items.map(v=>v.sku)).size===expected.size&&data.items.every(v=>expected.has(v.sku));
}
