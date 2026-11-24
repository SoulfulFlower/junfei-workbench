let discoveryReportGeneration=0;
const selectionDomains={US:'amazon.com',UK:'amazon.co.uk',DE:'amazon.de',FR:'amazon.fr',IT:'amazon.it',ES:'amazon.es',JP:'amazon.co.jp',CA:'amazon.ca',AU:'amazon.com.au',IN:'amazon.in',MX:'amazon.com.mx',BR:'amazon.com.br'};
function selectionProductUrl(market,asin){
 return selectionDomains[market]&&typeof asin==='string'&&/^[A-Z0-9]{10}$/.test(asin)?'https://www.'+selectionDomains[market]+'/dp/'+asin:'';
}
function discoveryPanelHTML(){
 return `<section class="panel box" style="margin:18px 0"><h2>本地循环发现证据链</h2><p>标题词 → 搜索商品（同款待核验）→ 商品页实际 Seller 链接 → 卖家商品列表 → 新商品 → 新标题词。</p><p class="notice">可导入已采集的结构化 JSON，或对已有观察明确触发一次已绑定页面的 搜索 / Seller / 卖家列表只读预览，再从已记录的商品标题准备开头词。预览后需明确保存，才写入独立证据链。记录和词源可追溯，不等于同款、排名、货源、利润或选品已通过；发现数量与核验通过、实际入库分开计数。可预览有轮次和条数上限的后续步骤；计划不会自动执行。不会自动导航、翻页或搜索新词；同款及经营核实仍未接通。</p><div class="actions"><label>模板站点 <select id="discoveryMarket">${Object.keys(selectionDomains).map(m=>'<option>'+m+'</option>').join('')}</select></label><button class="btn" id="discoveryTemplate">下载空白格式说明</button><button class="btn" id="discoveryRefresh">刷新本地记录</button></div><label class="field">选择已采集证据 JSON（最多1 MiB）<input id="discoveryFile" type="file" accept=".json,application/json"></label><p id="discoveryInputInfo" class="sub">选择文件后先显示批次与条数，点击保存才写入独立发现账本。不会修改产品档案或启动任务。</p><button class="btn" id="discoverySave" disabled>验证并保存本地发现证据</button><div id="discoveryHistory" style="margin-top:14px"></div><div id="discoveryReport" style="margin-top:14px"></div></section>`;
}
async function discoveryParseFile(file){
 if(!file||file.size>1024*1024)throw Error('请选择不超过1 MiB的JSON文件');
 const data=JSON.parse(await file.text());
 if(!data||Array.isArray(data)||typeof data!=='object'||typeof data.cycleId!=='string'||!data.cycleId.trim()||!Number.isInteger(data.expectedRevision)||data.expectedRevision<0||!Array.isArray(data.events)||!data.events.length)throw Error('文件须包含cycleId、expectedRevision和非空events；空模板不能直接导入');
 return data;
}
function discoveryReportHTML(report){
 const h=selectionEscape,c=report.counts||{};
 return `<h3>发现循环 ${h(report.cycleId)} · 版本 ${h(report.revision)}</h3><p>发现商品 ${h(c.discoveredProducts??report.products?.length??0)} · 已记录 Seller ${h(c.recordedSellers??report.sellers?.length??0)} · 本账本核验通过 ${h(c.qualified??0)} · 实际入库 ${h(c.imported??0)}</p><p class="notice">所有边均为待核验观察；导入内容的浏览器来源尚未认证。品牌不是 Seller，店铺卡片不证明当前购买框卖家，第三方估算不是已核实销量。此页不会执行下一轮搜索。</p><h4>下一步待采集/核对</h4><pre style="white-space:pre-wrap;max-height:240px;overflow:auto">${h(JSON.stringify(report.queue||report.nextActions||[],null,2))}</pre><details><summary>完整节点、来源关系与阻断项</summary><pre style="white-space:pre-wrap;max-height:480px;overflow:auto">${h(JSON.stringify(report,null,2))}</pre></details><button class="btn" id="discoveryDownload">下载本次证据链报告</button><div id="discoveryBrowserPanel"></div>`;
}
function discoveryOwnerCurrent(owner,epoch){
 return owner&&owner===signedUser&&view==='selection'&&epoch===selectionEpoch;
}
function discoveryPromotionHTML(report){
 const h=selectionEscape, kinds=new Map((report.events||[]).map(event=>[event.id,event.kind]));
 const options=(report.products||[]).flatMap(product=>{
  const source=product.sources.find(item=>item.title&&item.similarity!=='REJECT'&&['search','store'].includes(kinds.get(item.eventId)));
  return source?[`<label class="field"><input type="checkbox" value="${h(product.id)}" data-discovery-promotion> ${h(product.id)} · ${h(source.title)}</label>`]:[];
 });
 if(!options.length)return '';
 return `<details style="margin-top:14px"><summary>核验后建档</summary><p>选择最多30个候选。入库须匹配本账号 CLI 台账中已完成选品、货源核验且有正利润报价证据的任务。已有档案只关联台账，继续执行仍由 CLI 负责。</p><div style="max-height:240px;overflow:auto">${options.join('')}</div><button class="btn primary" id="discoveryPromote">核验并加入产品档案</button><div id="discoveryPromotionResult" aria-live="polite"></div></details>`;
}
function discoveryShow(report,owner,epoch){
 if(!discoveryOwnerCurrent(owner,epoch))return;
 const box=document.getElementById('discoveryReport');if(!box)return;
 const generation=++discoveryReportGeneration;
 box.innerHTML=discoveryReportHTML(report)+discoveryPromotionHTML(report);
 document.getElementById('discoveryDownload').onclick=()=>{if(generation===discoveryReportGeneration&&discoveryOwnerCurrent(owner,epoch))download('discovery-'+report.cycleId+'.json',JSON.stringify(report,null,2))};
 const promote=document.getElementById('discoveryPromote');
 if(promote)promote.onclick=async()=>{
  const productKeys=Array.from(box.querySelectorAll('[data-discovery-promotion]:checked'),input=>input.value);
  if(!productKeys.length||productKeys.length>30)return toast('请选择1至30个发现候选');
  promote.disabled=true;
  try{
   await flushWorkspace();
   if(generation!==discoveryReportGeneration||!discoveryOwnerCurrent(owner,epoch))return;
   const before=JSON.stringify(state);
   const response=await selectionApi('/api/discovery/promote',{cycleId:report.cycleId,expectedRevision:report.revision,productKeys,revision:serverRevision});
   if(!discoveryOwnerCurrent(owner,epoch))return;
   selectionApplyImport(response,before);
   if(generation!==discoveryReportGeneration)return;
   const h=selectionEscape,labels={created:'已建档并关联',linked:'已关联原档案',reused:'已沿用原关联',blocked:'待核对'};
   document.getElementById('discoveryPromotionResult').innerHTML=response.outcomes.map(item=>`<p>${h(item.key)} · ${h(labels[item.status])}${item.productId?' · '+h(item.productId):''}${item.reason?' · '+h(item.reason):''}</p>`).join('');
  }catch(error){if(discoveryOwnerCurrent(owner,epoch))toast(error.message)}finally{promote.disabled=false}
 };
 if(typeof discoveryBrowserMount==='function')discoveryBrowserMount(report,owner,epoch);
}
async function discoveryHistory(epoch){
 const owner=signedUser;
 try{
  const data=await selectionApi('/api/discovery/history');
  if(!discoveryOwnerCurrent(owner,epoch))return;
  const box=document.getElementById('discoveryHistory');if(!box)return;
  box.replaceChildren();
  if(!data.items?.length){box.textContent='尚无循环证据记录。当前没有执行真实自动选品。';return}
  for(const item of data.items){
   const button=document.createElement('button');button.className='btn';button.style.margin='4px';button.textContent=item.cycleId+' · 版本 '+item.revision;
   button.onclick=async()=>{if(!discoveryOwnerCurrent(owner,epoch))return;const generation=++discoveryReportGeneration;if(typeof discoveryBrowserInvalidate==='function')discoveryBrowserInvalidate();try{const report=await selectionApi('/api/discovery/report?id='+encodeURIComponent(item.cycleId));if(generation===discoveryReportGeneration)discoveryShow(report,owner,epoch)}catch(error){if(generation===discoveryReportGeneration&&discoveryOwnerCurrent(owner,epoch))toast(error.message)}};
   box.append(button);
  }
 }catch(error){if(discoveryOwnerCurrent(owner,epoch))toast(error.message)}
}
function discoveryMount(epoch){
 const owner=signedUser,file=document.getElementById('discoveryFile'),save=document.getElementById('discoverySave'),info=document.getElementById('discoveryInputInfo');
 let payload=null,busy=false,readVersion=0;
 file.onchange=async()=>{
  const attempt=++readVersion;payload=null;save.disabled=true;
  try{
   const candidate=await discoveryParseFile(file.files?.[0]);
   if(attempt!==readVersion||!discoveryOwnerCurrent(owner,epoch))return;
   payload=candidate;info.textContent='待验证循环 '+candidate.cycleId+' · 目标版本 '+candidate.expectedRevision+' · '+candidate.events.length+'条。尚未保存或核验。';save.disabled=false;
  }catch(error){if(attempt===readVersion&&discoveryOwnerCurrent(owner,epoch))info.textContent=error.message}
 };
 save.onclick=async()=>{
  if(busy||!payload||!discoveryOwnerCurrent(owner,epoch))return;
  busy=true;save.disabled=true;file.disabled=true;
  const submitted=payload;
  const generation=++discoveryReportGeneration;if(typeof discoveryBrowserInvalidate==='function')discoveryBrowserInvalidate();
  try{
   const report=await selectionApi('/api/discovery/ingest',submitted);
   if(!discoveryOwnerCurrent(owner,epoch))return;
   payload=null;file.value='';info.textContent='证据结构已保存；没有执行搜索、核验通过或产品入库。';if(generation===discoveryReportGeneration)discoveryShow(report,owner,epoch);await discoveryHistory(epoch);
  }catch(error){if(discoveryOwnerCurrent(owner,epoch))toast(error.message)}
  finally{busy=false;if(discoveryOwnerCurrent(owner,epoch)){file.disabled=false;save.disabled=!payload}}
 };
 document.getElementById('discoveryTemplate').onclick=async()=>{
  if(!discoveryOwnerCurrent(owner,epoch))return;
  try{const market=document.getElementById('discoveryMarket').value;const schema=await selectionApi('/api/discovery/template?market='+encodeURIComponent(market));if(discoveryOwnerCurrent(owner,epoch))download('discovery-blank-'+market+'.json',JSON.stringify(schema,null,2))}catch(error){if(discoveryOwnerCurrent(owner,epoch))toast(error.message)}
 };
 document.getElementById('discoveryRefresh').onclick=()=>discoveryHistory(epoch);
 discoveryHistory(epoch);
}
