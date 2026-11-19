// Normal UK editor refresh/application only. The application has one durable
// intent; any later invocation refreshes the same draft and never reapplies.
import {randomUUID,createHash} from 'node:crypto';
import {setTimeout as wait} from 'node:timers/promises';

const clone=structuredClone,fold=value=>String(value??'').trim().toLowerCase();
const origin='https://app.junfeikuajing.com',base='/api/amazon/category/upc-exemption/';
const scopeKeys=['seller_id','country_code','primary_category_name','product_type_name','brand'];
const scopeSame=(a,b)=>scopeKeys.every(key=>key==='brand'?fold(a?.[key])===fold(b?.[key]):a?.[key]===b?.[key]);
const schemaOf=meta=>typeof meta?.schema_content==='string'?JSON.parse(meta.schema_content):meta?.schema_content;

export function assertUkExemptionContext(prepared,meta,ui){
 const d=prepared.destination,schema=schemaOf(meta);
 if(prepared.marketplace!=='UK'||prepared.mode!=='draft'||d?.countryCode!=='GB'||!/^\d+$/.test(String(d.draftId))||
    meta?.country_code!=='GB'||meta.locale!=='en_GB'||!meta.hash||meta.hash!==d.schemaHash||schema?.$defs?.marketplace_id?.default!==d.marketplaceId||
    !meta.product_type_name||ui.url!=='https://www.junfeikuajing.com/#/amazon/product/'+d.draftId+'?type=draft'||ui.store!==prepared.store||
    !prepared.goods?.brand||fold(ui.brand)!==fold(prepared.goods.brand)||!/^\d+$/.test(String(ui.nativeMarketId))||
    (d.marketId!==undefined&&String(d.marketId)!==String(ui.nativeMarketId)))throw Error('英国品牌豁免的原草稿、店铺、站点、品牌或实际市场ID不符');
 return{accountId:prepared.accountId,productId:prepared.productId,jobId:prepared.jobId,snapshotSha256:prepared.sha256,draftId:String(d.draftId),store:prepared.store,
  countryCode:'GB',nativeMarketId:String(ui.nativeMarketId),marketplaceId:d.marketplaceId,schemaHash:meta.hash,productType:meta.product_type_name,brand:prepared.goods.brand};
}

export function assertUkExemptionScope(payload,identity,{nativeScope,categoryChoice}={}){
 if(!payload||JSON.stringify(Object.keys(payload).sort())!==JSON.stringify([...scopeKeys].sort())||
    scopeKeys.some(key=>typeof payload[key]!=='string'||!payload[key].trim())||payload.country_code!=='GB'||
    payload.product_type_name!==identity.productType||fold(payload.brand)!==fold(identity.brand)||
    (nativeScope&&!scopeSame(payload,nativeScope))||
    (categoryChoice?.text&&!fold(categoryChoice.text).startsWith(fold(payload.primary_category_name)+' ')&&fold(categoryChoice.text)!==fold(payload.primary_category_name)))throw Error('英国豁免原生请求的seller、国家、类目、类型或品牌范围不符');
 return clone(payload);
}

export function parseUkExemptionCheck(observation,identity,options={}){
 const request=observation?.request;
 if(request?.method!=='POST'||request.url!==origin+base+'check'||request.response?.httpStatus!==200||request.response.body?.code!==0)throw Error('英国品牌豁免刷新未返回真实成功结果');
 const scope=assertUkExemptionScope(request.payload,identity,options),data=request.response.body.data;
 if(!data||data.status_map?.available!=='允许销售'||![null,'waiting','applying','timeout','unavailable','available','failed'].includes(data.status))throw Error('英国品牌豁免刷新状态或实际状态映射未核实');
 return{scope,status:data.status,allowed:data.status==='available',notDetected:data.status===null,statusMap:clone(data.status_map)};
}

export async function readUkExemptionUi(page){
 return page.evaluate(()=>{const store=document.querySelector('input[placeholder="店铺"]'),brand=document.querySelector('input[placeholder="品牌"]'),value=store?.closest('.el-select')?.__vue__?.value;
  return{url:location.href,store:store?.value,brand:brand?.value,status:brand?.closest('.el-form-item')?.innerText||'',nativeMarketId:typeof value==='string'||typeof value==='number'?String(value):null};});
}

// Self-contained callback: both endpoints and the five-key native request were
// observed in 43/44. Refresh POSTs are read-only; apply is the sole mutation.
export function installUkExemptionGuard(plan){
 if(window.__ukExemptionAction)throw Error('已有英国豁免操作观察');
 const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,fetch=window.fetch,targets=new WeakMap();
 const state={token:plan.token,mode:plan.mode,open,send,fetch,requests:[],error:null,plan};window.__ukExemptionAction=state;
 const fold=value=>String(value??'').trim().toLowerCase(),keys=['seller_id','country_code','primary_category_name','product_type_name','brand'];
 const hookedOpen=function(method,url,...rest){targets.set(this,{method:String(method).toUpperCase(),url:new URL(url,location.href)});return open.call(this,method,url,...rest);};
 const hookedSend=function(body){
  const target=targets.get(this);if(!target){state.error='拦截缺少原生open记录的XHR';throw Error(state.error);}if(['GET','HEAD'].includes(target.method))return send.call(this,body);
  try{
   const kind=target.url.href==='https://app.junfeikuajing.com/api/amazon/category/upc-exemption/check'?'check':target.url.href==='https://app.junfeikuajing.com/api/amazon/category/upc-exemption/apply'?'apply':null;
   if(state.error||target.method!=='POST'||!kind||(kind==='apply'&&(plan.mode!=='apply'||state.requests.some(row=>row.kind==='apply'))))throw Error('拦截非目标或重复英国豁免申请写入');
   const payload=JSON.parse(body);
   if(JSON.stringify(Object.keys(payload).sort())!==JSON.stringify([...keys].sort())||keys.some(key=>typeof payload[key]!=='string'||!payload[key].trim())||
      payload.country_code!=='GB'||payload.product_type_name!==plan.identity.productType||fold(payload.brand)!==fold(plan.identity.brand)||
      (plan.nativeScope&&keys.some(key=>key==='brand'?fold(payload[key])!==fold(plan.nativeScope[key]):payload[key]!==plan.nativeScope[key]))||
      (plan.categoryText&&!fold(plan.categoryText).startsWith(fold(payload.primary_category_name)+' ')&&fold(plan.categoryText)!==fold(payload.primary_category_name)))throw Error('拦截英国豁免请求身份或字段变化');
   const record={kind,method:target.method,url:target.url.href,payload,sentAt:new Date().toISOString(),response:null};state.requests.push(record);
   this.addEventListener('loadend',()=>{let body,parseError;try{body=JSON.parse(this.responseText);}catch(error){parseError=String(error.message||error);}record.response={httpStatus:this.status,body,parseError};},{once:true});
   return send.call(this,JSON.stringify(payload));
  }catch(error){state.error=String(error.message||error);throw error;}
 };
 state.hookedOpen=hookedOpen;state.hookedSend=hookedSend;XMLHttpRequest.prototype.open=hookedOpen;XMLHttpRequest.prototype.send=hookedSend;
 if(typeof fetch==='function'){const hookedFetch=function(input,init){const method=String(init?.method||input?.method||'GET').toUpperCase();if(!['GET','HEAD'].includes(method)){state.error='拦截非原生XHR的豁免写入';return Promise.reject(Error(state.error));}return fetch.apply(this,arguments);};state.hookedFetch=hookedFetch;window.fetch=hookedFetch;}
 return{installed:true,token:state.token};
}

export function ukExemptionGuardSnapshot(){
 const s=window.__ukExemptionAction;return{present:Boolean(s),token:s?.token,bindings:{open:Boolean(s)&&XMLHttpRequest.prototype.open===s.hookedOpen,send:Boolean(s)&&XMLHttpRequest.prototype.send===s.hookedSend,fetch:Boolean(s?.hookedFetch)&&window.fetch===s.hookedFetch},requests:s?.requests||[],error:s?.error||null,observedAt:new Date().toISOString()};
}

export function ukExemptionButtonStable(token){
 const s=window.__ukExemptionAction;
 if(!s||s.token!==token||XMLHttpRequest.prototype.open!==s.hookedOpen||XMLHttpRequest.prototype.send!==s.hookedSend||!s.hookedFetch||window.fetch!==s.hookedFetch||s.error)throw Error('英国豁免原生护栏绑定失效，未点击');
 const plan=s.plan,store=document.querySelector('input[placeholder="店铺"]'),brand=document.querySelector('input[placeholder="品牌"]'),market=store?.closest('.el-select')?.__vue__?.value,fold=value=>String(value??'').trim().toLowerCase();
 if(location.href!=='https://www.junfeikuajing.com/#/amazon/product/'+plan.identity.draftId+'?type=draft'||store?.value!==plan.identity.store||fold(brand?.value)!==fold(plan.identity.brand)||String(market)!==plan.identity.nativeMarketId)throw Error('英国豁免点击前原草稿店铺品牌变化');
 const button=document.querySelector('[data-uk-exemption-action="'+token+'"]');if(!button)return false;
 const rect=button.getBoundingClientRect(),style=getComputedStyle(button),x=rect.x+rect.width/2,y=rect.y+rect.height/2,hit=document.elementFromPoint(x,y);
 if(button.disabled||!rect.width||!rect.height||style.pointerEvents==='none'||style.visibility==='hidden'||Number(style.opacity??1)!==1||x<0||y<0||x>=innerWidth||y>=innerHeight||!hit||(hit!==button&&!button.contains(hit))){s.stability=null;return false;}
 const fingerprint=JSON.stringify([rect.x,rect.y,rect.width,rect.height]);s.stability=s.stability?.fingerprint===fingerprint?{fingerprint,count:s.stability.count+1}:{fingerprint,count:1};return s.stability.count>=3;
}

async function nativeExemptionAction(page,prepared,journal,persist,{identity,nativeScope,categoryChoice,mode}){
 if(mode==='apply'&&(!journal.applyIntent||journal.applyRequests?.length))throw Error('英国豁免缺少持久申请意图或已有请求，不重复申请');
 const token=randomUUID(),plan={token,mode,identity,nativeScope,categoryText:categoryChoice?.text},action={token,mode,startedAt:new Date().toISOString()};
 (journal.actions??=[]).push(action);await persist();
 try{
  const installed=await page.evaluate(installUkExemptionGuard,plan),guard=await page.evaluate(ukExemptionGuardSnapshot);
  if(installed?.installed!==true||installed.token!==token||guard.token!==token||!guard.bindings.open||!guard.bindings.send||!guard.bindings.fetch||guard.error)throw Error('英国豁免原生护栏未确认');
  action.installProof=guard;await persist();
  const selector=await page.evaluate(({token,mode})=>{const block=document.querySelector('input[placeholder="品牌"]')?.closest('.el-form-item');const targets=mode==='check'?[...block?.querySelectorAll('.el-icon-refresh')||[]]:[...block?.querySelectorAll('button')||[]].filter(button=>button.innerText.trim()==='申请UPC豁免');
   const visible=targets.filter(node=>node.getBoundingClientRect().width&&!node.disabled);if(visible.length!==1)throw Error('英国豁免原生控件不唯一');visible[0].setAttribute('data-uk-exemption-action',token);visible[0].scrollIntoView({block:'center',inline:'nearest'});return '[data-uk-exemption-action="'+token+'"]';},{token,mode});
  await page.waitForFunction(ukExemptionButtonStable,token,{timeout:10000});
  const fresh=await page.evaluate(ukExemptionGuardSnapshot);if(fresh.token!==token||!fresh.bindings.open||!fresh.bindings.send||!fresh.bindings.fetch||fresh.error||fresh.requests.some(row=>row.kind==='apply'))throw Error('英国豁免点击前护栏变化');
  await page.click(selector);
  await page.waitForFunction(mode=>window.__ukExemptionAction?.error||window.__ukExemptionAction?.requests.some(row=>row.kind===mode&&row.response),mode,{timeout:20000});
 }finally{
  try{action.observation=await page.evaluate(ukExemptionGuardSnapshot);action.endedAt=new Date().toISOString();if(mode==='apply')journal.applyRequests=action.observation.requests.filter(row=>row.kind==='apply');await persist();}
  finally{await page.evaluate(token=>{const s=window.__ukExemptionAction;if(s?.token!==token)return;if(XMLHttpRequest.prototype.open===s.hookedOpen)XMLHttpRequest.prototype.open=s.open;if(XMLHttpRequest.prototype.send===s.hookedSend)XMLHttpRequest.prototype.send=s.send;if(window.fetch===s.hookedFetch)window.fetch=s.fetch;delete window.__ukExemptionAction;},token);}
 }
 const observed=action.observation,requests=observed.requests.filter(row=>row.kind===mode),request=requests.filter(row=>row.response).at(-1);
 if(observed.error||!request||(mode==='apply'&&requests.length!==1)||request.response?.httpStatus!==200||request.response.body?.code!==0)throw Error(observed.error||'英国豁免原生'+(mode==='check'?'刷新':'申请')+'结果待核对');
 return{request,ui:await readUkExemptionUi(page)};
}

export async function waitUkExemptionAllowedUi(page,identity){
 await page.waitForFunction(identity=>{const brand=document.querySelector('input[placeholder="品牌"]'),fold=value=>String(value??'').trim().toLowerCase();return location.href==='https://www.junfeikuajing.com/#/amazon/product/'+identity.draftId+'?type=draft'&&document.querySelector('input[placeholder="店铺"]')?.value===identity.store&&fold(brand?.value)===fold(identity.brand)&&String(brand?.closest('.el-form-item')?.innerText).replace(/\s/g,'').includes('UPC豁免：允许销售');},identity,{timeout:10000});
}

export async function ensureUkBrandExemption(page,prepared,record,persist,{schemaObservation,...adapters}={}){
 const api={ui:readUkExemptionUi,refresh:(...args)=>nativeExemptionAction(...args),apply:(...args)=>nativeExemptionAction(...args),waitUi:waitUkExemptionAllowedUi,wait,now:()=>performance.now(),timeoutMs:180000,pollIntervalMs:5000,...adapters};
 if(!Number.isFinite(api.timeoutMs)||api.timeoutMs<0||api.timeoutMs>180000||!Number.isFinite(api.pollIntervalMs)||api.pollIntervalMs<=0||api.pollIntervalMs>5000||!Number.isFinite(api.now()))throw Error('英国豁免只读轮询时间配置无效');
 const initialUi=await api.ui(page),identity=assertUkExemptionContext(prepared,schemaObservation,initialUi);
 if(String(record.draftId)!==identity.draftId)throw Error('英国豁免原准备草稿编号不符');
 const fingerprint=createHash('sha256').update(JSON.stringify(identity)).digest('hex');
 const journal=record.brandExemption??={identity:clone(identity),fingerprint,nativeMarketId:identity.nativeMarketId,createdAt:new Date().toISOString()};
 if(journal.fingerprint!==fingerprint)throw Error('英国豁免已有其他草稿、店铺或品牌检查点，不覆盖');
 await persist();
 const refresh=async()=>{
  const observation=await api.refresh(page,prepared,journal,persist,{identity,nativeScope:journal.nativeScope,categoryChoice:record.categoryChoice,mode:'check'});
  if(assertUkExemptionContext(prepared,schemaObservation,observation.ui).nativeMarketId!==identity.nativeMarketId)throw Error('英国豁免刷新后实际市场ID变化');const checked=parseUkExemptionCheck(observation,identity,{nativeScope:journal.nativeScope,categoryChoice:record.categoryChoice});
  journal.nativeScope??=clone(checked.scope);journal.latestCheck={...clone(observation),status:checked.status,observedAt:new Date().toISOString()};(journal.checks??=[]).push(clone(journal.latestCheck));await persist();return{...checked,ui:observation.ui};
 };
 const accept=async current=>{if(!String(current.ui.status).replace(/\s/g,'').includes('UPC豁免：允许销售')){await api.waitUi(page,identity);current.ui=await api.ui(page);if(assertUkExemptionContext(prepared,schemaObservation,current.ui).nativeMarketId!==identity.nativeMarketId)throw Error('英国豁免UI等待后实际市场ID变化');if(!String(current.ui.status).replace(/\s/g,'').includes('UPC豁免：允许销售'))throw Error('英国原生刷新已允许但品牌UI尚未确认，继续只读核对');}journal.phase='allowed';journal.applicationState='available';journal.allowedAt=new Date().toISOString();await persist();return journal;};
 let current=await refresh();if(current.allowed)return accept(current);
 if(['failed','unavailable'].includes(current.status)||/申请失败|不可销售/.test(current.ui.status)){journal.phase='blocked';await persist();throw Error('英国品牌豁免当前申请失败或不可销售，保留原记录');}
 if(!journal.applyIntent&&current.notDetected&&!/申请中|等待申请|处理超时/.test(current.ui.status)){
  journal.applyIntent={identity:clone(identity),nativeScope:clone(journal.nativeScope),armedAt:new Date().toISOString()};journal.phase='apply_unknown';await persist();
  try{const result=await api.apply(page,prepared,journal,persist,{identity,nativeScope:journal.nativeScope,categoryChoice:record.categoryChoice,mode:'apply'});if(result.request?.method!=='POST'||result.request.url!==origin+base+'apply'||result.request.response?.httpStatus!==200||result.request.response.body?.code!==0)throw Error('英国豁免申请原生回执未确认');assertUkExemptionScope(result.request.payload,identity,{nativeScope:journal.nativeScope,categoryChoice:record.categoryChoice});journal.applyResponse=clone(result.request);journal.requestAcceptedAt=new Date().toISOString();await persist();}
  catch(error){journal.lastApplyError=String(error.message||error);await persist();}
 }
 const started=api.now();
 if(journal.poll)(journal.pollHistory??=[]).push(clone(journal.poll));
 const poll=journal.poll={startedAt:new Date().toISOString(),timeoutMs:api.timeoutMs,intervalMs:api.pollIntervalMs,attempts:0,elapsedMs:0,timedOut:false};
 const pending=async()=>{journal.applicationState=current.status===null?'unknown':current.status;journal.phase=current.status===null&&journal.applyIntent?'apply_unknown':'pending';poll.lastStatus=current.status;poll.elapsedMs=Math.max(0,api.now()-started);await persist();};
 await pending();
 for(;;){
  if(poll.attempts){const remaining=api.timeoutMs-Math.max(0,api.now()-started);if(remaining<=0)break;await api.wait(Math.min(api.pollIntervalMs,remaining));}
  if(Math.max(0,api.now()-started)>=api.timeoutMs)break;
  current=await refresh();poll.attempts++;poll.elapsedMs=Math.max(0,api.now()-started);
  if(current.allowed){poll.completedAt=new Date().toISOString();poll.result='available';await persist();return accept(current);}
  if(['failed','unavailable'].includes(current.status)){journal.phase='blocked';await persist();throw Error('英国品牌豁免原申请失败，不重复提交');}
  await pending();
 }
 poll.timedOut=true;poll.completedAt=new Date().toISOString();await pending();
 const error=Error(current.status===null?'英国品牌豁免原申请结果仍未知，不重复申请':'英国品牌豁免申请仍在处理中，仅核对原申请，不重复申请');
 error.code=current.status===null?'ERP_UK_EXEMPTION_UNKNOWN':'ERP_UK_EXEMPTION_PENDING';throw error;
}
