// Observed Junfei product-library form, via Ego Page API. Library drafts are
// store-independent; this module never publishes or adds to stores.
// Junfei retains closed dialogs in the DOM. Mark only the currently visible
// product dialog so hidden copies cannot capture selectors or visibility waits.
const ROOT='[data-amazon-library-active="true"]';
const FIELDS={sourceUrl:'来源链接',sku:'SKU',brand:'品牌',manufacturer:'制造商',title:'标题',description:'描述',terms:'关键词',notes:'备注'};
const textSize=s=>[...s].length;
const expectedVariants=c=>c.variants.map(v=>({sku:v.sku,color:v.color,size:v.size,price:v.price,images:[]}));

// The delivery exporter preserves size labels in child SKUs (50 x 100 cm).
// Keep that identity intact; parent SKUs and receipt filenames stay stricter.
export const validLibraryVariantSku=s=>typeof s==='string'&&s.length<=40&&/^[-A-Za-z0-9_]+(?: [-A-Za-z0-9_]+)*$/.test(s);

export function validateLibraryCommerce(c){
  const price=s=>typeof s==='string'&&/^(?:0|[1-9]\d{0,4})(?:\.\d{1,2})?$/.test(s)&&Number(s)>0;
  if(!c||Object.keys(c).some(k=>!['currency','price','variants','evidence'].includes(k))||c.currency!=='USD'||!price(c.price))throw Error('产品库价格需明确USD正数金额');
  // The live, unsaved library form was verified with 24 rows on 2026-11-11.
  if(!Array.isArray(c.variants)||!c.variants.length||c.variants.length>24)throw Error('需明确1–24个产品库变体');
  const seen=new Set();
  for(const v of c.variants){
    if(!v||Object.keys(v).some(k=>!['sku','color','size','price'].includes(k))||!validLibraryVariantSku(v.sku)||seen.has(v.sku)||!price(v.price)||
      typeof v.color!=='string'||!v.color.trim()||textSize(v.color)>64||typeof v.size!=='string'||textSize(v.size)>128)throw Error('变体SKU、颜色、尺寸或价格不合法');
    seen.add(v.sku);
  }
  for(const k of ['price','variants'])if(typeof c.evidence?.[k]!=='string'||!c.evidence[k].trim())throw Error('产品库经营字段缺少依据: '+k);
  return c;
}

export function validateLibraryRequest(r){
  const allowed=['accountId','productId','store','marketplace','mode','sourceUrl','sku','brand','manufacturer','title','description','bullets','terms','notes','evidence','commerce'];
  if(!r||Object.keys(r).some(k=>!allowed.includes(k))||!Number.isSafeInteger(r.accountId)||r.accountId<1||
     typeof r.productId!=='string'||!r.productId.trim()||typeof r.store!=='string'||!r.store.trim()||r.marketplace!=='US'||r.mode!=='library_draft')throw Error('仅支持明确账号、产品、目标店铺的US产品库草稿请求');
  if(!/^[A-Za-z0-9_-]{1,40}$/.test(r.sku||''))throw Error('SKU不合法');
  for(const field of ['brand','manufacturer']){
    if(typeof r[field]!=='string'||!r[field].trim()||r[field]!==r[field].trim()||textSize(r[field])>50||/[\u0000-\u001f<>]/.test(r[field]))throw Error('品牌/制造商不合法');
    if(r[field]!=='Generic'&&(typeof r.evidence?.[field]!=='string'||!r.evidence[field].trim()))throw Error('非Generic品牌/制造商需要本次店铺同步及用户适用确认依据');
  }
  let url;try{url=new URL(r.sourceUrl);}catch{}
  if(!url||url.origin!=='https://detail.1688.com'||url.username||url.password||url.search||url.hash||!/^\/offer\/\d+\.html$/.test(url.pathname))throw Error('必须明确1688商品来源');
  for(const [key,limit] of Object.entries({title:75,description:2000,terms:249,notes:300})){
    if(typeof r[key]!=='string'||!r[key].trim()||(key==='terms'?new TextEncoder().encode(r[key]).length:textSize(r[key]))>limit)throw Error('字段缺失或超长: '+key);
  }
  if(!Array.isArray(r.bullets)||r.bullets.length!==5||r.bullets.some(s=>typeof s!=='string'||!s.trim()||/[\r\n]/.test(s)||textSize(s)>500))throw Error('必须有五条单行描述');
  for(const key of ['sourceUrl','title','description','bullets','terms'])if(typeof r.evidence?.[key]!=='string'||!r.evidence[key].trim())throw Error('字段缺少来源: '+key);
  if(r.commerce!==undefined)validateLibraryCommerce(r.commerce);
  return r;
}

export async function openNewLibraryForm(page){
  await page.goto('https://www.junfeikuajing.com/#/product/library');
  await page.waitForFunction(()=>location.hash==='#/product/library'&&
    document.querySelector('input[placeholder="请输入标题"]')&&
    [...document.querySelectorAll('button')].some(e=>e.innerText.trim()==='添加'),undefined,{timeout:15000});
  if(await page.evaluate(()=>[...document.querySelectorAll('[role="dialog"][aria-label="产品详情"]')].some(e=>e.getBoundingClientRect().width>0)))throw Error('已有产品详情表单打开，请先核对原操作；不会覆盖或重复添加');
  await page.click('loc=role:button[name="添加"]',{label:'打开新品资料表单'});
  await page.waitForFunction(()=>[...document.querySelectorAll('[role="dialog"][aria-label="产品详情"]')]
    .filter(e=>e.getBoundingClientRect().width>0).length===1,undefined,{timeout:10000});
}

export async function inspectLibraryForm(page){
  const out=await page.evaluate(()=>{
    const dialogs=[...document.querySelectorAll('[role="dialog"][aria-label="产品详情"]')].filter(e=>e.getBoundingClientRect().width>0);
    if(dialogs.length!==1)throw Error('产品详情对话框不唯一');const d=dialogs[0];
    for(const old of document.querySelectorAll('[data-amazon-library-active]'))old.removeAttribute('data-amazon-library-active');
    d.setAttribute('data-amazon-library-active','true');
    const all=[...d.querySelectorAll('input,textarea')];
    const value=p=>{const found=all.filter(e=>e.getAttribute('placeholder')===p);if(found.length!==1)throw Error('产品库控件不唯一: '+p);return found[0].value;};
    // Element UI separates header and body into different tables. Match the
    // enclosing component and cell positions; every variant input has the same
    // placeholder, so placeholder-only selectors silently miss SKU edits.
    const variantTables=[...d.querySelectorAll('.el-table')].filter(t=>{
      const h=[...t.querySelectorAll('.el-table__header th')].map(e=>e.innerText.trim());
      return h[2]==='SKU'&&h[3]==='颜色'&&h[4]==='尺寸'&&h[5]==='价格';
    });
    if(variantTables.length!==1)throw Error('产品库变体表结构变化');
    const variants=[...variantTables[0].querySelectorAll('.el-table__body tr')].map(row=>{
      const controls=[...row.querySelectorAll('input')].filter(e=>e.type!=='checkbox');
      if(controls.length!==4||controls.some((e,i)=>e.closest('td')?.cellIndex!==i+2))throw Error('产品库变体字段结构变化');
      return {sku:controls[0].value,color:controls[1].value,size:controls[2].value,price:controls[3].value,
        images:[...row.querySelectorAll('img')].map(e=>e.getAttribute('src'))};
    });
    const bulletControls=all.filter(e=>e.getAttribute('placeholder')==='五点描述');
    if(bulletControls.length!==5||bulletControls.some((e,i)=>e.closest('td')?.previousElementSibling?.innerText.trim()!==`五点描述${i+1}`))throw Error('产品库五点结构变化');
    return {url:location.href,form:{source:value('来源'),sourceUrl:value('来源链接'),sku:value('SKU'),brand:value('品牌'),manufacturer:value('制造商'),title:value('标题'),description:value('描述'),terms:value('关键词'),notes:value('备注'),bullets:bulletControls.map(e=>e.value)},
      shipping:Object.fromEntries(['价格','长','宽','高','重量','中文名','英文名','申报价格','海关编码','是否带电','请选择开发人','请选择采购人','制造商编号'].map(p=>[p,value(p)])),
      variants,imageCount:d.querySelectorAll('img').length,variantSkuControlCount:all.filter(e=>e.getAttribute('placeholder')==='SKU').length};
  });
  if(out.url!=='https://www.junfeikuajing.com/#/product/library')throw Error('产品库来源/路由不匹配');
  return out;
}

function assertMatches(actual,r){
  for(const key of Object.keys(FIELDS))if(actual.form[key]!==r[key])throw Error('产品库填写核对失败: '+key);
  if(actual.form.source!=='1688'||JSON.stringify(actual.form.bullets)!==JSON.stringify(r.bullets))throw Error('货源类型或五点核对失败');
  if(r.commerce){
    if(actual.shipping['价格']!==r.commerce.price||JSON.stringify(actual.variants)!==JSON.stringify(expectedVariants(r.commerce)))throw Error('产品库价格或变体核对失败');
  }
}
function assertUntouched(before,after,r={}){
  const expected={...before};
  if(r.commerce){expected.shipping={...before.shipping,'价格':r.commerce.price};expected.variants=expectedVariants(r.commerce);}
  for(const key of ['shipping','imageCount','variantSkuControlCount','variants'])if(JSON.stringify(expected[key])!==JSON.stringify(after[key]))throw Error('未授权的产品库字段发生变化: '+key);
}

// Fill the observed table by verified cell positions. All four inputs have the
// literal placeholder "placeholder"; global placeholder selectors are unsafe.
// This helper never saves. Callers must persist intent before invoking it.
export async function fillLibraryCommerce(page,c){
  validateLibraryCommerce(c);
  const before=await inspectLibraryForm(page);
  if(before.variants.length||before.shipping['价格'])throw Error('仅允许填写空价格及空变体表');
  await page.fill(`${ROOT} input[placeholder="价格"]`,c.price);
  for(let index=0;index<c.variants.length;index++){
    await page.click(`${ROOT} button:has-text("添加变体")`,{label:'添加产品库草稿变体'});
    const selectors=await page.evaluate(index=>{
      const d=document.querySelector('[data-amazon-library-active="true"]');
      const tables=[...d.querySelectorAll('.el-table')].filter(t=>{
        const h=[...t.querySelectorAll('.el-table__header th')].map(e=>e.innerText.trim());return h[2]==='SKU'&&h[3]==='颜色'&&h[4]==='尺寸'&&h[5]==='价格';
      });
      if(tables.length!==1)throw Error('产品库变体表结构变化');
      const rows=[...tables[0].querySelectorAll('.el-table__body tr')];
      if(rows.length!==index+1)throw Error('新增变体数量异常');
      const inputs=[...rows[index].querySelectorAll('input')].filter(e=>e.type!=='checkbox');
      if(inputs.length!==4||inputs.some((e,i)=>e.closest('td')?.cellIndex!==i+2||e.value))throw Error('新增变体控件非空或结构变化');
      return inputs.map((e,i)=>{const key=index+'-'+i;e.setAttribute('data-amazon-variant-control',key);return '[data-amazon-library-active="true"] input[data-amazon-variant-control="'+key+'"]';});
    },index);
    for(const [i,key] of ['sku','color','size','price'].entries())await page.fill(selectors[i],c.variants[index][key]);
  }
  const after=await inspectLibraryForm(page);
  if(JSON.stringify(before.form)!==JSON.stringify(after.form))throw Error('填写变体期间文案字段发生变化');
  assertUntouched(before,after,{commerce:c});
  return after;
}

export async function startSaveObservation(page){
  return page.evaluate(()=>{
    if(window.__amazonLibrarySaveObserver)throw Error('已有保存观察，先核对原操作');
    const capture={startedAt:performance.now(),messages:[],responses:[]};
    window.__amazonLibrarySaveCapture=capture;
    const collect=()=>{
      for(const e of document.querySelectorAll('.el-message,.el-notification,.el-form-item__error')){
        if(e.getBoundingClientRect().width<=0)continue;
        const text=e.innerText.trim().slice(0,1000);
        if(text&&!capture.messages.includes(text)&&capture.messages.length<30)capture.messages.push(text);
      }
    };
    const observer=new MutationObserver(collect);observer.observe(document.body,{childList:true,subtree:true,characterData:true});
    window.__amazonLibrarySaveObserver=observer;
    // Observe only this known product-save response. Do not read request bodies,
    // headers, cookies, credentials or other endpoints. Axios rejects 422 without
    // displaying its body in this ERP, so DOM notifications alone are insufficient.
    const originalOpen=XMLHttpRequest.prototype.open,originalSend=XMLHttpRequest.prototype.send,requests=new WeakMap();
    const wrappedOpen=function(method,url,...args){
      let target=false;try{target=String(method).toUpperCase()==='POST'&&new URL(url,location.href).href==='https://app.junfeikuajing.com/api/product/store';}catch{}
      requests.set(this,target);return originalOpen.call(this,method,url,...args);
    };
    const wrappedSend=function(...args){
      if(requests.get(this))this.addEventListener('loadend',()=>{
        const result={status:this.status};
        if(this.status===422){
          try{
            const text=this.responseType==='json'?this.response:this.responseText;
            const body=typeof text==='string'&&text.length<1048576?JSON.parse(text):text;
            if(body&&typeof body==='object'){
              if(typeof body.message==='string')result.message=body.message.slice(0,1000);
              if(body.errors&&typeof body.errors==='object'&&!Array.isArray(body.errors))result.validationErrors=Object.fromEntries(Object.entries(body.errors)
                .filter(([key])=>!/password|token|secret|authorization|cookie|api.?key/i.test(key)).slice(0,40)
                .map(([key,value])=>[key,(Array.isArray(value)?value:[value]).filter(x=>typeof x==='string').map(x=>x.slice(0,1000)).slice(0,10)]));
            }
          }catch{result.bodyUnreadable=true;}
        }
        capture.responses.push(result);
      },{once:true});
      return originalSend.apply(this,args);
    };
    XMLHttpRequest.prototype.open=wrappedOpen;XMLHttpRequest.prototype.send=wrappedSend;
    window.__amazonLibrarySaveXHRHook={originalOpen,originalSend,wrappedOpen,wrappedSend};
    return capture.startedAt;
  });
}

export async function finishSaveObservation(page){
  return page.evaluate(()=>{
    const capture=window.__amazonLibrarySaveCapture||{startedAt:Infinity,messages:[]};
    window.__amazonLibrarySaveObserver?.disconnect();delete window.__amazonLibrarySaveObserver;
    const hook=window.__amazonLibrarySaveXHRHook;
    if(hook){if(XMLHttpRequest.prototype.open===hook.wrappedOpen)XMLHttpRequest.prototype.open=hook.originalOpen;if(XMLHttpRequest.prototype.send===hook.wrappedSend)XMLHttpRequest.prototype.send=hook.originalSend;delete window.__amazonLibrarySaveXHRHook;}
    return {messages:capture.messages,responses:capture.responses||[],requests:performance.getEntriesByType('resource')
      .filter(e=>e.name==='https://app.junfeikuajing.com/api/product/store'&&e.startTime>=capture.startedAt)
      .map(e=>({url:e.name,responseStatus:e.responseStatus,startTime:e.startTime,responseEnd:e.responseEnd}))};
  });
}

export async function stageLibraryDraft(page,r,ledger){
  validateLibraryRequest(r);
  const before=await inspectLibraryForm(page);
  // Only a new, empty form is accepted. Existing products use a different tool.
  if(Object.entries(before.form).some(([k,v])=>k==='bullets'?v.some(Boolean):k==='source'?!['','1688'].includes(v):Boolean(v))||
    Object.values(before.shipping).some(Boolean)||before.imageCount||before.variantSkuControlCount!==1||before.variants?.length)throw Error('新品表单非空，停止以免覆盖已有产品');
  const record={accountId:r.accountId,productId:r.productId,targetStore:r.store,marketplace:r.marketplace,sku:r.sku,request:r,before,status:'library_staging',createdAt:new Date().toISOString(),published:false,storeDraftCreated:false};
  await ledger.create(record);
  try{
    if(before.form.source!=='1688'){
      const visible=await page.evaluate(()=>[...document.querySelectorAll('.el-select-dropdown')].some(e=>e.getBoundingClientRect().width>0&&e.innerText.split('\n').includes('1688')));
      if(!visible)await page.click(`${ROOT} input[placeholder="来源"]`,{label:'选择货源平台'});
      await page.waitForFunction(()=>[...document.querySelectorAll('.el-select-dropdown li')].some(e=>e.getBoundingClientRect().width>0&&e.innerText.trim()==='1688'),undefined,{timeout:5000});
      const selector=await page.evaluate(()=>{
        const all=[...document.querySelectorAll('li')],found=all.filter(e=>e.closest('.el-select-dropdown')&&e.getBoundingClientRect().width>0&&e.innerText.trim()==='1688');
        if(found.length!==1)throw Error('1688选项不唯一');return `li >> nth=${all.indexOf(found[0])}`;
      });
      await page.click(selector,{label:'使用1688货源类型'});
    }
    for(const [key,p] of Object.entries(FIELDS)){
      const current=(await inspectLibraryForm(page)).form[key];
      if(current===r[key])continue;
      const tag=key==='description'?'textarea':'input';
      await page.fill(`${ROOT} ${tag}[placeholder="${p}"]`,r[key]);
    }
    for(let i=0;i<5;i++)await page.fill(`${ROOT} textarea[placeholder="五点描述"] >> nth=${i}`,r.bullets[i]);
    if(r.commerce)await fillLibraryCommerce(page,r.commerce);
    record.staged=await inspectLibraryForm(page);assertMatches(record.staged,r);assertUntouched(before,record.staged,r);
    record.status='library_draft_staged_not_saved';record.stagedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(e){record.error=e.message;record.status='library_stopped_before_save';await ledger.write(record);throw e;}
}

// Saving this incomplete library draft does not create a store listing. Unknown
// results retain their record; callers must reconcile by SKU instead of retrying.
export async function saveStagedLibraryDraft(page,record,ledger){
  validateLibraryRequest(record.request);
  if(record.status!=='library_draft_staged_not_saved')throw Error('仅允许保存已核对且未提交的产品库草稿');
  await assertSaveState(page,record);
  const selector=await page.evaluate(()=>{
    const d=[...document.querySelectorAll('[role="dialog"][aria-label="产品详情"]')].filter(e=>e.getBoundingClientRect().width>0);
    if(d.length!==1)throw Error('产品详情对话框不唯一');
    const buttons=[...d[0].querySelectorAll('button')].filter(e=>e.innerText.replace(/\s/g,'')==='保存');
    if(buttons.length!==1)throw Error('产品库保存按钮不唯一');
    return `button >> nth=${[...document.querySelectorAll('button')].indexOf(buttons[0])}`;
  });
  record.status='library_save_unknown';await ledger.write(record);
  try{
    const startedAt=await startSaveObservation(page);
    await page.click(selector,{label:'保存未发布的产品库资料'});
    await page.waitForFunction(({sku,title,startedAt})=>
      performance.getEntriesByType('resource').some(e=>e.name==='https://app.junfeikuajing.com/api/product/store'&&e.startTime>=startedAt&&e.responseEnd>e.startTime&&e.responseStatus>=400)||
      (![...document.querySelectorAll('[role="dialog"][aria-label="产品详情"]')].some(e=>e.getBoundingClientRect().width>0)&&
      [...document.querySelectorAll('tr')].some(tr=>[...tr.querySelectorAll('td')].some(td=>td.innerText.trim()===sku)&&tr.innerText.includes(title))),
      {sku:record.sku,title:record.request.title,startedAt},{timeout:15000});
    record.saveObservation=await finishSaveObservation(page);
    const rejected=record.saveObservation.requests.find(r=>r.responseStatus>=400);
    if(rejected){
      const validation=record.saveObservation.responses?.find(r=>r.status===422);
      const detail=validation?.validationErrors?JSON.stringify(validation.validationErrors):validation?.message||record.saveObservation.messages.join('；');
      throw Error(`产品库保存被拒绝 HTTP ${rejected.responseStatus}：${detail||'页面未返回可读原因；先按SKU对账'}`);
    }
    const row=await page.evaluate(({sku,title})=>{
      const rows=[...document.querySelectorAll('tr')].filter(tr=>[...tr.querySelectorAll('td')].some(td=>td.innerText.trim()===sku));
      if(rows.length!==1||!rows[0].innerText.includes(title))throw Error('产品库SKU/标题行不唯一');
      const cells=[...rows[0].querySelectorAll('td')].map(td=>td.innerText.trim());
      if(!/^\d+$/.test(cells[1]||''))throw Error('产品库ID无法确认');
      const buttons=[...rows[0].querySelectorAll('button')].filter(b=>b.innerText.trim()==='编辑');
      if(buttons.length!==1)throw Error('产品库编辑按钮不唯一');
      return {id:cells[1],text:rows[0].innerText,selector:`button >> nth=${[...document.querySelectorAll('button')].indexOf(buttons[0])}`};
    },{sku:record.sku,title:record.request.title});
    record.libraryId=row.id;record.listRow=row.text;await ledger.write(record);
    await page.click(row.selector,{label:'重开新产品核对已保存内容'});
    await page.waitForFunction(sku=>[...document.querySelectorAll('[role="dialog"][aria-label="产品详情"] input[placeholder="SKU"]')].some(e=>e.value===sku),record.sku,{timeout:10000});
    record.reopened=await assertSaveState(page,record);
    record.status='library_draft_saved_reopened_verified';record.verifiedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(e){
    record.error=e.message;
    if(!record.saveObservation){try{record.saveObservation=await finishSaveObservation(page);}catch(observationError){record.observationError=observationError.message;}}
    await ledger.write(record);throw e;
  }
}

async function assertSaveState(page,record){
  const actual=await inspectLibraryForm(page);
  if(record.mediaPackage){
    // Text and commerce must still match the original request independently of
    // the image receipt. Only the exact, separately verified images may differ.
    const withoutImages={...actual,imageCount:record.before.imageCount,variants:actual.variants.map(v=>({...v,images:[]}))};
    assertMatches(withoutImages,record.request);assertUntouched(record.before,withoutImages,record.request);
    const {verifyLibraryPackageForSave}=await import('./ego-library-package.mjs');
    await verifyLibraryPackageForSave(page,record,actual);
  }else{assertMatches(actual,record.request);assertUntouched(record.before,actual,record.request);}
  return actual;
}
