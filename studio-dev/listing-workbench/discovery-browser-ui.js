/* Explicit current-page observations and local title previews. Never navigates or starts production. */
let discoveryBrowserGeneration=0;
const discoveryBrowserControlIds=['discoveryBrowserTarget','discoveryBrowserCapture','discoveryStoreTarget','discoveryStoreCapture','discoveryBrowserCheck','discoveryBrowserRefresh','discoveryBrowserSave','discoveryKeywordTarget','discoveryKeywordPhrase','discoveryKeywordPrepare','discoveryKeywordSave','discoverySearchTarget','discoverySearchCapture','discoveryPlanMaxActions','discoveryPlanMaxRounds','discoveryPlanPrepare','discoveryFamilyTarget','discoveryFamilyCapture','discoveryFamilyAssess','discoveryRunInspect'];
function discoveryBrowserInvalidate(){
 discoveryBrowserGeneration++;
 for(const id of discoveryBrowserControlIds){const element=document.getElementById(id);if(element)element.disabled=true}
 const info=document.getElementById('discoveryBrowserInfo');if(info)info.textContent='正在切换或更新报告，旧面板已停用；已发出的采集仍以原回执为准。若加载失败，请重新选择记录。';
}
function discoveryBrowserTargets(report){
 const result=[];
 for(const event of report.events||[])if(event.kind==='search')
  for(const product of event.products||[])result.push({parentId:event.id,asin:product.asin,marketplace:event.marketplace,title:product.title});
 return result;
}
function discoveryStoreTargets(report){
 return (report.events||[]).filter(e=>e.kind==='seller').map(e=>({parentId:e.id,sellerId:e.sellerId,marketplace:e.marketplace,title:e.sellerName||e.sellerId}));
}
function discoveryKeywordTargets(report){
 const result=[];
 for(const event of report.events||[])if(event.kind==='store'&&event.status==='captured')
  for(const product of event.products||[])result.push({parentId:event.id,asin:product.asin,marketplace:event.marketplace,title:product.title});
 return result;
}
function discoverySearchTargets(report){
 return (report.events||[]).filter(e=>e.kind==='keyword').map(e=>({parentId:e.id,marketplace:e.marketplace,query:e.phrase}));
}
function discoveryFamilyTargets(report){
 const result=[];
 for(const event of report.events||[]){
  const rows=['keyword','seller'].includes(event.kind)&&event.asin?[{asin:event.asin,title:event.sourceTitle||event.title||event.asin}]:
   event.kind==='search'||event.kind==='store'&&event.status==='captured'?event.products||[]:[];
  for(const product of rows)if(product?.asin)result.push({parentId:event.id,asin:product.asin,marketplace:event.marketplace,title:product.title||product.asin});
 }
 return result;
}
function discoveryBrowserMount(report,owner,epoch){
 const box=document.getElementById('discoveryBrowserPanel');if(!box)return;
 const ownerId=Number(owner.id),generation=++discoveryBrowserGeneration,snapshot=JSON.parse(JSON.stringify(report));
 const current=()=>Number(owner.id)===ownerId&&generation===discoveryBrowserGeneration&&discoveryOwnerCurrent(owner,epoch)&&report.cycleId===snapshot.cycleId&&report.revision===snapshot.revision;
 const h=selectionEscape,targets=discoveryBrowserTargets(snapshot),stores=discoveryStoreTargets(snapshot),products=discoveryKeywordTargets(snapshot),searches=discoverySearchTargets(snapshot),familyTargets=discoveryFamilyTargets(snapshot);
 const options=items=>items.map((t,i)=>'<option value="'+i+'">'+h(t.marketplace+' / '+(t.asin||t.sellerId)+' / '+t.title+' / 来源 '+t.parentId)+'</option>').join('');
 box.innerHTML='<h4>本地浏览器：只读采集当前已绑定页面</h4><p class="notice">只读取此账号明确绑定的 EGO 页面，不打开或跳转网页、不接管用户浏览器。必须先把目标页面打开在已绑定页面；缺少绑定、验证码或权限变化时停止。Seller、店铺与搜索观察先预览，明确保存后才进入独立发现账本的待核实证据链，不代表同款或选品通过，不启动任务或产品入库。</p>'+
 '<label>商品页 Seller 来源 <select id="discoveryBrowserTarget">'+options(targets)+'</select></label> '+
 '<button class="btn" id="discoveryBrowserCapture">只读采集当前商品页 Seller</button><br>'+
 '<label>变体家族页面来源 <select id="discoveryFamilyTarget">'+options(familyTargets)+'</select></label> '+
 '<button class="btn" id="discoveryFamilyCapture">只读采集当前商品页变体关系</button><p class="notice">仅观察已保存来源的当前商品页，不切换变体、不自动采集或保存到发现图谱。同标题、共享 detailASIN 或同品牌不能证明同家族；有来源的家族成员关系也不等于正式父子 ASIN 映射。缺证据保持待核实，不会因此丢弃各变体 Seller 的独立核实。</p>'+
 '<label>已保存 Seller <select id="discoveryStoreTarget">'+options(stores)+'</select></label> '+
 '<button class="btn" id="discoveryStoreCapture">只读采集当前卖家商品列表</button><p class="sub">店铺采集只关联本报告已保存的 Seller，读取当前页实际可见商品，不自动遍历或翻页。</p>'+
 '<label>已保存标题词 <select id="discoverySearchTarget">'+searches.map((t,i)=>'<option value="'+i+'">'+h(t.marketplace+' / '+t.query+' / 来源 '+t.parentId)+'</option>').join('')+'</select></label> '+
 '<button class="btn" id="discoverySearchCapture">只读采集当前搜索结果页</button><p id="discoverySearchPhrase" class="sub"></p><p class="sub">只使用已保存标题词的原始短语和站点。请先在已绑定页面打开对应搜索结果；此按钮不会搜索、导航或翻页。结果仅为可见商品观察，不能据此判为同款。</p>'+
 '<button class="btn" id="discoveryBrowserCheck" disabled>读取本次回执</button> '+
 '<button class="btn" id="discoveryBrowserRefresh">查看采集记录</button>'+
 '<p id="discoveryBrowserInfo" class="sub">不会自动填写浏览器绑定、导航或保存到发现图谱。先选择已保存的来源，再明确采集。</p>'+
 '<div id="discoveryBrowserHistory"></div><pre id="discoveryBrowserReceipt" style="white-space:pre-wrap;max-height:300px;overflow:auto"></pre>'+
 '<button class="btn" id="discoveryBrowserSave" disabled>仅保存这次待核实观察</button>'+
 '<h4>变体家族证据评估</h4><p class="sub">只读取本账号已保存的采集回执。家族观察与分组不代表选品合格，不替代各变体 Seller、货源或利润核实，也不会导入产品。</p>'+
 '<button class="btn" id="discoveryFamilyAssess">仅评估已保存家族证据</button>'+
 '<p id="discoveryFamilyInfo" class="sub">尚未评估；缺少证据保持待核实。</p><pre id="discoveryFamilyAssessment" style="white-space:pre-wrap;max-height:300px;overflow:auto"></pre>'+
 '<h4>从已保存店铺商品准备下一标题词</h4><p class="notice">只使用本报告店铺列表中的实际商品标题。列表卡片标题不等于商品详情页独立核实；请手动填写原始标题的开头短语，先预览，再单独保存。不会执行搜索、核验或导入产品。</p>'+
 '<label>店铺商品 <select id="discoveryKeywordTarget">'+options(products)+'</select></label> '+
 '<label>标题开头短语 <input id="discoveryKeywordPhrase" type="text" maxlength="300" value=""></label> '+
 '<button class="btn" id="discoveryKeywordPrepare">预览下一标题词</button>'+
 '<p id="discoveryKeywordInfo" class="sub">尚未准备或保存标题词。</p><pre id="discoveryKeywordPreview" style="white-space:pre-wrap;max-height:240px;overflow:auto"></pre>'+
 '<button class="btn" id="discoveryKeywordSave" disabled>仅保存此待核实标题词</button>'+
 '<h4>有界接续建议预览</h4><p class="notice">这是基于当前证据链提出的下一步建议，不是实际连续运行。尚未实现自动导航，不会采集、保存、核验或启动任务。以下额度只限制预览中的建议动作和可涉及的最大轮次序号，不是合格数量或经营准入标准。</p>'+
 '<label>最多建议动作（1–20）<input id="discoveryPlanMaxActions" type="number" min="1" max="20" step="1" value="5"></label> '+
 '<label>最大轮次序号（1–20）<input id="discoveryPlanMaxRounds" type="number" min="1" max="20" step="1" value="2"></label> '+
 '<button class="btn" id="discoveryPlanPrepare">仅预览接续建议</button>'+
 '<p id="discoveryPlanInfo" class="sub">尚未生成建议；不会自动运行。</p><pre id="discoveryPlanPreview" style="white-space:pre-wrap;max-height:300px;overflow:auto"></pre>'+
 '<h4>连续运行安全准备检查</h4><p class="notice">仅检查当前证据、回执和上方额度，不执行计划。自动导航尚未实现，执行权限始终关闭；检查结果不是可上线或选品合格结论。</p>'+
 '<button class="btn" id="discoveryRunInspect">只读检查运行准备情况</button>'+
 '<p id="discoveryRunInfo" class="sub">尚未检查；不会启动连续运行。</p><pre id="discoveryRunInspection" style="white-space:pre-wrap;max-height:300px;overflow:auto"></pre>';
 const get=id=>document.getElementById(id),target=get('discoveryBrowserTarget'),capture=get('discoveryBrowserCapture'),
  storeTarget=get('discoveryStoreTarget'),storeCapture=get('discoveryStoreCapture'),check=get('discoveryBrowserCheck'),refresh=get('discoveryBrowserRefresh'),
  info=get('discoveryBrowserInfo'),receiptBox=get('discoveryBrowserReceipt'),save=get('discoveryBrowserSave'),historyBox=get('discoveryBrowserHistory'),
  keywordTarget=get('discoveryKeywordTarget'),phrase=get('discoveryKeywordPhrase'),prepare=get('discoveryKeywordPrepare'),keywordSave=get('discoveryKeywordSave'),
  keywordInfo=get('discoveryKeywordInfo'),keywordBox=get('discoveryKeywordPreview'),
  searchTarget=get('discoverySearchTarget'),searchCapture=get('discoverySearchCapture'),searchPhrase=get('discoverySearchPhrase'),
  maxActions=get('discoveryPlanMaxActions'),maxRounds=get('discoveryPlanMaxRounds'),planPrepare=get('discoveryPlanPrepare'),
  planInfo=get('discoveryPlanInfo'),planBox=get('discoveryPlanPreview'),
  familyTarget=get('discoveryFamilyTarget'),familyCapture=get('discoveryFamilyCapture'),familyAssess=get('discoveryFamilyAssess'),
  familyInfo=get('discoveryFamilyInfo'),familyBox=get('discoveryFamilyAssessment'),
  runInspect=get('discoveryRunInspect'),runInfo=get('discoveryRunInfo'),runBox=get('discoveryRunInspection');
 let captureId='',prepared=null,keywordPrepared=null,busy=false,ledgerUncertain=false,readVersion=0,historyVersion=0,keywordVersion=0,searchVersion=0,planVersion=0,familyTargetVersion=0,familyVersion=0,runVersion=0;
 const unresolved=new Set(),captureExpectations=new Map();
 function controls(){
  if(!current())return;
  const uncertain=unresolved.size>0||ledgerUncertain;
  target.disabled=busy||uncertain||!targets.length;capture.disabled=target.disabled;
  familyTarget.disabled=busy||uncertain||!familyTargets.length;familyCapture.disabled=familyTarget.disabled;
  familyAssess.disabled=busy||uncertain;runInspect.disabled=busy||uncertain||!planLimits();
  storeTarget.disabled=busy||uncertain||!stores.length;storeCapture.disabled=storeTarget.disabled;
  searchTarget.disabled=busy||uncertain||!searches.length;searchCapture.disabled=searchTarget.disabled;
  check.disabled=busy||!captureId;refresh.disabled=busy;
  maxActions.disabled=busy;maxRounds.disabled=busy;planPrepare.disabled=busy||uncertain||!planLimits();
  save.disabled=busy||uncertain||!prepared;
  keywordTarget.disabled=busy||!products.length;phrase.disabled=keywordTarget.disabled;
  prepare.disabled=busy||uncertain||!products.length||!phrase.value.trim();keywordSave.disabled=busy||uncertain||!keywordPrepared;
 }
 // Refuse mismatched history/response batches even when cycle and revision happen to match.
 function validBatch(batch,kind){
  if(batch?.cycleId!==snapshot.cycleId||batch.expectedRevision!==snapshot.revision||!Array.isArray(batch.events)||batch.events.length!==1)return false;
  const e=batch.events[0];if(!e||e.kind!==kind)return false;
  if(kind==='seller')return targets.some(t=>t.parentId===e.parentId&&t.asin===e.asin);
  if(kind==='store')return stores.some(t=>t.parentId===e.parentId&&t.sellerId===e.sellerId)&&Array.isArray(e.products)&&e.products.length>0;
  if(kind==='search')return searches.some(t=>t.parentId===e.parentId&&t.query===e.query&&t.marketplace===e.marketplace)&&
   Array.isArray(e.products)&&e.products.length>0&&e.products.every(p=>p&&p.asin&&p.title&&p.similarity!=='EXACT');
  return kind==='keyword'&&products.some(t=>t.parentId===e.parentId&&t.asin===e.asin&&t.title===e.sourceTitle);
 }
 function validFamilyReceipt(receipt){
  return typeof receipt.cycleId==='string'&&Number.isInteger(receipt.expectedRevision)&&receipt.expectedRevision>=0&&
   typeof receipt.parentId==='string'&&typeof receipt.asin==='string'&&
   receipt.evidence&&typeof receipt.evidence==='object'&&!Array.isArray(receipt.evidence)&&
   !Object.hasOwn(receipt,'preparedBatch')&&receipt.executionAllowed===false&&receipt.qualificationEvaluated===false&&receipt.qualifiedCount===0;
 }
 function validFamily(receipt){
  return validFamilyReceipt(receipt)&&receipt.cycleId===snapshot.cycleId&&receipt.expectedRevision===snapshot.revision&&
   familyTargets.some(t=>t.parentId===receipt.parentId&&t.asin===receipt.asin);
 }
 function show(receipt,id,expected){
  if(!current())return;
  prepared=null;
  if(!receipt||receipt.captureId!==id){unresolved.add(id);info.textContent='回执编号不匹配，结果未确认。请继续读取原回执。';return}
  captureId=id;expected=expected||captureExpectations.get(id);
  const kind=receipt.captureKind||'seller',batch=receipt.preparedBatch;
  if(expected&&(kind!==expected.kind||(expected.kind==='family'&&expected.parentId&&
    (receipt.parentId!==expected.parentId||receipt.asin!==expected.asin||receipt.cycleId!==snapshot.cycleId||receipt.expectedRevision!==snapshot.revision)))){
   unresolved.add(id);receiptBox.textContent='';info.textContent='回执类型或来源与原采集请求不匹配，结果仍未确认。请读取原回执，不会保存或重新采集。';return;
  }
  if(kind==='family'&&receipt.status==='captured'&&!validFamilyReceipt(receipt)){
   unresolved.add(id);receiptBox.textContent='';info.textContent='家族回执缺少有效观察或包含不应有的保存数据，结果仍未确认。请读取原回执。';return;
  }
  if(['capture_started','execution_unknown'].includes(receipt.status))unresolved.add(id);
  else if(['captured','blocked','configuration_blocked'].includes(receipt.status))unresolved.delete(id);
  else unresolved.add(id);
  const e=batch?.events?.[0],matches=!expected?.parentId||(kind===expected.kind&&e?.parentId===expected.parentId&&
   (kind==='search'?e?.query===expected.query&&e?.marketplace===expected.marketplace&&(expected.searchVersion===undefined||expected.searchVersion===searchVersion):
    kind==='store'?e?.sellerId===expected.sellerId:e?.asin===expected.asin));
  if(receipt.status==='captured'&&matches&&['seller','store','search'].includes(kind)&&validBatch(batch,kind))prepared=JSON.parse(JSON.stringify(batch));
  if(kind==='family'&&expected?.familyTargetVersion!==undefined&&expected.familyTargetVersion!==familyTargetVersion){
   receiptBox.textContent='';info.textContent='变体家族来源已改变，本次回执不再显示为当前来源证据。可从采集记录读取，不会自动重采。';return;
  }
  receiptBox.textContent=JSON.stringify(receipt,null,2);
  save.textContent=kind==='family'?'家族回执仅供评估，不可保存到发现图谱':kind==='search'?'仅保存这次待核实搜索观察':kind==='store'?'仅保存这次待核实店铺商品观察':'仅保存这次待核实 Seller 证据';
  info.textContent=unresolved.size?'仍有采集结果未确认，仅可读取已有回执，不会自动重试或重新接管。':
   kind==='family'&&receipt.status==='captured'?(validFamily(receipt)?'已采集变体页面观察并保存回执，尚未核实家族或选品资格。请单独评估；不可保存到发现图谱，仍需各变体 Seller 独立核实。':'这是历史或不适用于当前来源的家族回执，不能视为当前证据，也不能保存到发现图谱。'):
   prepared?(kind==='search'?'已读取实际可见搜索商品 '+batch.events[0].products.length+' 条，尚未保存，不代表同款。':kind==='store'?'已读取实际可见店铺商品 '+batch.events[0].products.length+' 条，尚未保存。':'已读取候选 Seller 观察，尚未保存。')+'请核对来源后再保存；仍不代表独立核实。':
   '采集未形成可保存证据：'+(receipt.reason||receipt.status||'未知状态');
 }
 async function read(id){
  if(!current()||busy||!id)return;
  captureId=id;const version=++readVersion;busy=true;prepared=null;controls();
  try{const receipt=await selectionApi('/api/discovery/capture?id='+encodeURIComponent(id));if(current()&&version===readVersion)show(receipt,id,captureExpectations.has(id)?{...captureExpectations.get(id),familyTargetVersion:undefined,searchVersion:undefined}:undefined)}
  catch(error){if(current()){unresolved.add(id);info.textContent='回执未能确认：'+error.message+'。不会重新执行浏览器读取。'}}
  finally{busy=false;controls()}
 }
 refresh.onclick=async()=>{
  if(!current()||busy)return;
  const version=++historyVersion;
  try{
   const records=await selectionApi('/api/discovery/captures');if(!current()||version!==historyVersion)return;
   invalidateReviews();historyBox.replaceChildren();
   for(const receipt of records.items||[]){
    if(['capture_started','execution_unknown'].includes(receipt.status))unresolved.add(receipt.captureId);
    if(!captureExpectations.has(receipt.captureId)&&['seller','store','search','family'].includes(receipt.captureKind))captureExpectations.set(receipt.captureId,{kind:receipt.captureKind});
    const button=document.createElement('button');button.className='btn';button.textContent=(receipt.captureKind==='family'?'变体家族观察':receipt.captureKind==='search'?'搜索商品':receipt.captureKind==='store'?'店铺商品':'Seller')+' / '+receipt.captureId+' / '+receipt.status;
    button.onclick=()=>read(receipt.captureId);historyBox.append(button);
   }
   controls();
  }catch(error){if(current()&&version===historyVersion)toast(error.message)}
 };
 async function start(kind){
  if(!current()||busy||unresolved.size||ledgerUncertain)return;
  const chosen=(kind==='family'?familyTargets:kind==='search'?searches:kind==='store'?stores:targets)[Number((kind==='family'?familyTarget:kind==='search'?searchTarget:kind==='store'?storeTarget:target).value)];if(!chosen)return;
  const selectedSearchVersion=searchVersion,selectedFamilyVersion=familyTargetVersion;
  if(!globalThis.crypto?.randomUUID){toast('当前运行环境不能安全创建采集编号，未调用浏览器');return}
  captureId='capture-'+crypto.randomUUID();const id=captureId;prepared=null;busy=true;readVersion++;invalidateReviews();controls();receiptBox.textContent='';
  const expected={kind,...chosen,searchVersion:selectedSearchVersion,...(kind==='family'?{familyTargetVersion:selectedFamilyVersion}:{})};captureExpectations.set(id,expected);
  info.textContent='正在请求一次只读采集；不会导航、接管或自动写入发现图谱。';
  const payload={captureId:id,cycleId:snapshot.cycleId,expectedRevision:snapshot.revision,parentId:chosen.parentId,...(kind==='search'?{}:kind==='store'?{sellerId:chosen.sellerId}:{asin:chosen.asin})};
  try{const receipt=await selectionApi('/api/discovery/capture-'+kind,payload);if(current())show(receipt,id,expected)}
  catch(error){if(current()){unresolved.add(id);info.textContent='采集结果未确认：'+error.message+'。请读取本次回执，不会自动重试。'}}
  finally{busy=false;controls()}
 }
 familyCapture.onclick=()=>start('family');capture.onclick=()=>start('seller');storeCapture.onclick=()=>start('store');searchCapture.onclick=()=>start('search');
 familyTarget.onchange=()=>{
  familyTargetVersion++;prepared=null;receiptBox.textContent='';info.textContent='变体家族来源已改变，请确认当前绑定页面后手动采集。';controls();
 };
 function updateSearch(){
  searchVersion++;if(prepared?.events?.[0]?.kind==='search'){prepared=null;receiptBox.textContent=''}
  const chosen=searches[Number(searchTarget.value)];
  searchPhrase.textContent=chosen?'当前原始搜索短语：'+chosen.query+'（'+chosen.marketplace+'）':'本报告尚无已保存标题词。';
  controls();
 }
 searchTarget.onchange=updateSearch;
 check.onclick=()=>read(captureId);
 function clearKeyword(){
  keywordVersion++;keywordPrepared=null;keywordBox.textContent='';keywordInfo.textContent='内容已变化，请重新预览后保存。';controls();
 }
 keywordTarget.onchange=()=>{phrase.value='';clearKeyword()};phrase.oninput=clearKeyword;
 prepare.onclick=async()=>{
  if(!current()||busy||unresolved.size||ledgerUncertain||!phrase.value.trim())return;
  const chosen=products[Number(keywordTarget.value)];if(!chosen)return;
  const entered=phrase.value,selected=keywordTarget.value,version=++keywordVersion;
  keywordPrepared=null;busy=true;controls();keywordBox.textContent='';keywordInfo.textContent='正在验证标题开头短语，尚未写入账本。';
  const payload={cycleId:snapshot.cycleId,expectedRevision:snapshot.revision,parentId:chosen.parentId,asin:chosen.asin,phrase:entered};
  try{
   const result=await selectionApi('/api/discovery/prepare-keyword',payload);
   if(!current()||version!==keywordVersion||phrase.value!==entered||keywordTarget.value!==selected)return;
   const batch=result.preparedBatch,e=batch?.events?.[0];
   if(result.status!=='prepared'||!validBatch(batch,'keyword')||e.parentId!==chosen.parentId||e.asin!==chosen.asin||e.phrase!==entered.trim())throw Error('标题词预览与当前来源不匹配');
   keywordPrepared=JSON.parse(JSON.stringify(batch));keywordBox.textContent=JSON.stringify(result,null,2);keywordInfo.textContent='标题词已预览，尚未保存。来源仅为店铺卡片标题，未独立核实，也未执行搜索。';
  }catch(error){if(current()&&version===keywordVersion){keywordPrepared=null;keywordInfo.textContent='未形成可保存标题词：'+error.message}}
  finally{busy=false;controls()}
 };
 function planLimits(){
  const parse=value=>/^[0-9]+$/.test(value)&&Number.isInteger(Number(value))&&Number(value)>=1&&Number(value)<=20?Number(value):null;
  const actions=parse(maxActions.value),rounds=parse(maxRounds.value);
  return actions&&rounds?{maxActions:actions,maxRounds:rounds}:null;
 }
 function clearPlan(){
  runVersion++;runBox.textContent='';runInfo.textContent='额度已改变，请重新进行只读准备检查。';
  planVersion++;planBox.textContent='';planInfo.textContent='额度已变化，请重新预览。额度只控制建议范围，不代表经营核实。';controls();
 }
 maxActions.oninput=clearPlan;maxRounds.oninput=clearPlan;
 planPrepare.onclick=async()=>{
  const limits=planLimits();if(!current()||busy||unresolved.size||ledgerUncertain||!limits)return;
  const version=++planVersion,enteredActions=maxActions.value,enteredRounds=maxRounds.value;
  busy=true;controls();planBox.textContent='';planInfo.textContent='正在准备只读接续建议；没有执行任何动作。';
  try{
   const result=await selectionApi('/api/discovery/prepare-plan',{cycleId:snapshot.cycleId,expectedRevision:snapshot.revision,...limits});
   if(!current()||version!==planVersion||maxActions.value!==enteredActions||maxRounds.value!==enteredRounds)return;
   if(!result||!['ready','blocked','no_actions'].includes(result.status)||result.readOnly!==true||
      result.owner!==ownerId||result.cycleId!==snapshot.cycleId||result.revision!==snapshot.revision||result.expectedRevision!==snapshot.revision||
      result.executionAllowed!==false||result.automaticNavigationImplemented!==false||
      result.limits?.maxActions!==limits.maxActions||result.limits?.maxRounds!==limits.maxRounds||
      !Array.isArray(result.actions)||result.actions.length>limits.maxActions||
      !result.actions.every(a=>a?.status==='proposed'&&a.executionAllowed===false&&Number.isInteger(a.proposedRound)&&a.proposedRound>=1&&a.proposedRound<=limits.maxRounds&&snapshot.events.some(e=>e.id===a.sourceEventId)))throw Error('接续建议与当前账号、版本或预览范围不匹配');
   planBox.textContent=JSON.stringify(result,null,2);
   planInfo.textContent='已生成 '+result.actions.length+' 条下一步建议（'+result.status+'）。仅供查看，未连续运行、未导航、未采集或保存；不代表选品合格。';
  }catch(error){if(current()&&version===planVersion){planBox.textContent='';planInfo.textContent='未取得有效建议：'+error.message}}
  finally{busy=false;controls()}
 };
 function invalidateReviews(){
  planVersion++;planBox.textContent='';planInfo.textContent='采集记录可能已变化，请重新预览接续建议；不会自动执行。';
  familyVersion++;runVersion++;familyBox.textContent='';runBox.textContent='';
  familyInfo.textContent='采集记录可能已变化，请重新评估已保存证据。';runInfo.textContent='采集记录可能已变化，请重新进行只读准备检查。';
 }
 function readonlyScope(result){
  return result&&result.schemaVersion===1&&result.readOnly===true&&result.owner===ownerId&&
   result.cycleId===snapshot.cycleId&&result.revision===snapshot.revision&&result.executionAllowed===false;
 }
 familyAssess.onclick=async()=>{
  if(!current()||busy||unresolved.size||ledgerUncertain)return;
  const version=++familyVersion;busy=true;controls();familyBox.textContent='';familyInfo.textContent='正在只读评估本账号已保存回执；不会采集、保存图谱或导入产品。';
  try{
   const result=await selectionApi('/api/discovery/assess-families',{cycleId:snapshot.cycleId,expectedRevision:snapshot.revision});
   if(!current()||version!==familyVersion)return;
   if(!readonlyScope(result)||result.qualificationEvaluated!==false||result.qualifiedCount!==0||result.importedCount!==0||result.externalCallsPerformed!==0||
      !result.assessment||typeof result.assessment!=='object'||Array.isArray(result.assessment)||!Array.isArray(result.blockers)||!(/^[a-f0-9]{64}$/).test(result.historyFingerprint||''))throw Error('家族评估与当前账号、版本或只读边界不匹配');
   familyBox.textContent=JSON.stringify(result,null,2);familyInfo.textContent='已完成只读家族证据评估，未核实选品资格。缺证据仍待核实；来源成员关系不等于正式父子 ASIN 映射，各变体 Seller 核实均保留。';
  }catch(error){if(current()&&version===familyVersion){familyBox.textContent='';familyInfo.textContent='未取得有效家族评估：'+error.message}}
  finally{busy=false;controls()}
 };
 runInspect.onclick=async()=>{
  const limits=planLimits();if(!current()||busy||unresolved.size||ledgerUncertain||!limits)return;
  const version=++runVersion,enteredActions=maxActions.value,enteredRounds=maxRounds.value;
  busy=true;controls();runBox.textContent='';runInfo.textContent='正在只读检查连续运行的准备情况；不会执行任何建议。';
  try{
   const result=await selectionApi('/api/discovery/inspect-run',{cycleId:snapshot.cycleId,expectedRevision:snapshot.revision,...limits});
   if(!current()||version!==runVersion||maxActions.value!==enteredActions||maxRounds.value!==enteredRounds)return;
   if(!readonlyScope(result)||result.status!=='execution_disabled'||result.automaticNavigationImplemented!==false||
      result.persistentLiveQueueCreated!==false||result.externalCallsPerformed!==0||result.qualificationEvaluated!==false||result.qualifiedCount!==0||result.importedCount!==0||
      result.limits?.maxActions!==limits.maxActions||result.limits?.maxRounds!==limits.maxRounds||!Array.isArray(result.blockers)||
      result.binding?.liveOwnershipVerified!==false||!Number.isInteger(result.plannedActionCount)||result.plannedActionCount<0||result.plannedActionCount>limits.maxActions)throw Error('准备检查与当前账号、版本、额度或只读边界不匹配');
   runBox.textContent=JSON.stringify(result,null,2);runInfo.textContent='只读准备检查完成。自动导航尚未实现，执行权限关闭；未连续运行、未采集或保存，不代表选品合格或可上线。';
  }catch(error){if(current()&&version===runVersion){runBox.textContent='';runInfo.textContent='未取得有效准备检查：'+error.message}}
  finally{busy=false;controls()}
 };
 async function persist(kind){
  const pending=kind==='keyword'?keywordPrepared:prepared;
  if(!current()||busy||unresolved.size||ledgerUncertain||!pending||!validBatch(pending,pending.events?.[0]?.kind))return;
  const batch=JSON.parse(JSON.stringify(pending));busy=true;controls();
  // Once sent, do not re-enable this save after an uncertain outcome. Reload the ledger instead.
  prepared=null;keywordPrepared=null;
  try{
   const updated=await selectionApi('/api/discovery/ingest',batch);if(!current())return;
   prepared=null;keywordPrepared=null;discoveryShow(updated,owner,epoch);await discoveryHistory(epoch);
  }catch(error){if(current()){ledgerUncertain=true;toast(error.message);(kind==='keyword'?keywordInfo:info).textContent='保存未确认：'+error.message+'。请重新加载账本核对，不会自动重试。'}}
  finally{busy=false;controls()}
 }
 save.onclick=()=>persist('capture');keywordSave.onclick=()=>persist('keyword');
 // Start with explicit empty input, even when a browser restores a previous form value.
 phrase.value='';maxActions.value='5';maxRounds.value='2';updateSearch();controls();
}
