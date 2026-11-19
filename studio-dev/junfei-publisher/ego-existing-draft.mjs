// Ego Page API adapter. Does not launch browsers, publish, or infer product facts.
export function validateRequest(request) {
  if (!request || typeof request.draftId !== 'string' || !/^\d+$/.test(request.draftId) ||
      typeof request.store !== 'string' || !request.store.trim() ||
      typeof request.erpSku !== 'string' || !request.erpSku.trim()) {
    throw new Error('明确草稿ID、店铺和ERP SKU为必填');
  }
  if (request.patch) {
    const keys = Object.keys(request.patch);
    const limits={title:75,highlights:125,description:2000,terms:249,brand:50,manufacturer:50};
    if (!keys.length || keys.some(key=>!['title','highlights','description','bullets','terms','brand','manufacturer'].includes(key))) {
      throw new Error('ego仅支持文案及Generic品牌/制造商的草稿修改');
    }
    if(keys.some(key=>['brand','manufacturer'].includes(key))&&
       (request.patch.brand!=='Generic'||request.patch.manufacturer!=='Generic'))throw new Error('品牌及制造商仅允许同时设为Generic，不能指定未经核实品牌');
    for (const key of keys) {
      const value=request.patch[key];
      if(typeof request.evidence?.[key]!=='string'||!request.evidence[key].trim())throw new Error('缺少字段来源: '+key);
      if(key==='bullets') {
        if(!Array.isArray(value)||value.length!==5||value.some(x=>typeof x!=='string'||!x.trim()||[...x].length>500||/[\r\n]/.test(x)))throw new Error('五点必须为五条非空单行文本，每条不超过500字符');
      } else if(typeof value!=='string'||!value.trim()||
          (key==='terms'?new TextEncoder().encode(value).length:[...value].length)>limits[key]) {
        throw new Error('草稿字段类型或长度不正确: '+key);
      }
    }
  }
  return request;
}

export async function inspectDraft(page, request, options={}) {
  validateRequest(request);
  const actual = await page.evaluate((keys) => {
    const value = (placeholder) => {
      const controls = [...document.querySelectorAll('input,textarea')]
        .filter(e => e.getAttribute('placeholder') === placeholder);
      if (controls.length !== 1) throw new Error('控件不唯一: ' + placeholder);
      return controls[0].value;
    };
    const skuControls = [...document.querySelectorAll('input')]
      .filter(e => e.getAttribute('placeholder')?.startsWith('父Sku,'));
    if (skuControls.length !== 1) throw new Error('SKU控件不唯一');
    const copy={};
    if(keys.includes('title'))copy.title=value('产品标题');
    if(keys.includes('highlights'))copy.highlights=value('商品亮点');
    if(keys.includes('description'))copy.description=value('产品描述');
    if(keys.includes('brand'))copy.brand=value('品牌');
    if(keys.includes('manufacturer'))copy.manufacturer=value('制造商');
    if(keys.includes('bullets')||keys.includes('terms')) {
      const controls=[...document.querySelectorAll('textarea[placeholder="Bullet Point"]')];
      if(controls.length!==6||controls.slice(0,5).some(e=>!e.closest('.el-form-item')?.innerText.trim().startsWith('五点描述'))||
          !controls[5].closest('#product-attr-keywords')||!controls[5].closest('.el-form-item')?.innerText.trim().startsWith('关键词'))throw new Error('五点/后台词控件结构变化，停止操作');
      if(keys.includes('bullets'))copy.bullets=controls.slice(0,5).map(e=>e.value);
      if(keys.includes('terms'))copy.terms=controls[5].value;
    }
    return {url:location.href, store:value('店铺'),erpSku:skuControls[0].value,copy,
      description:value('产品描述'),price:value('价格'),quantity:value('库存'),
      shippingTemplate:value('亚马逊运输模板'),handlingDays:value('处理时间')};
  },options.allCopy?['title','highlights','description','brand','manufacturer','bullets','terms']:Object.keys(request.patch||{}));
  const url = new URL(actual.url);
  if (url.origin !== 'https://www.junfeikuajing.com' ||
      url.hash !== `#/amazon/product/${request.draftId}?type=draft` ||
      actual.store !== request.store || actual.erpSku !== request.erpSku) {
    throw new Error('草稿身份不匹配，停止操作');
  }
  return actual;
}

export async function applyDescription(page, request) {
  validateRequest(request);
  if (!request.patch) throw new Error('缺少修改内容');
  const before = await inspectDraft(page, request);
  if (patchMatches(before,request.patch)) {
    throw new Error('页面已含目标内容；先核对保存结果，不重复提交');
  }
  const selectors={title:'input[placeholder="产品标题"]',highlights:'input[placeholder="商品亮点"]',description:'textarea[placeholder="产品描述"]',terms:'#product-attr-keywords textarea[placeholder="Bullet Point"]',brand:'input[placeholder="品牌"]',manufacturer:'input[placeholder="制造商"]'};
  for(const [key,value] of Object.entries(request.patch)) {
    // Junfei may populate manufacturer when brand changes. Do not type again
    // into an already matching reactive control (observed GenericGeneric).
    if(['brand','manufacturer'].includes(key)&&(await inspectDraft(page,request)).copy[key]===value)continue;
    if(['brand','manufacturer'].includes(key)) {
      await page.fill(selectors[key],'');
      await page.waitForFunction(({placeholder})=>document.querySelector(`input[placeholder="${placeholder}"]`)?.value==='',
        {placeholder:key==='brand'?'品牌':'制造商'},{timeout:5000});
    }
    if(key==='bullets')for(let i=0;i<5;i++)await page.fill(`textarea[placeholder="Bullet Point"] >> nth=${i}`,value[i]);
    else await page.fill(selectors[key],value);
  }
  const after = await inspectDraft(page, request);
  if (!patchMatches(after,request.patch)) throw new Error('文案填写后核对失败');
  assertSettingsUnchanged(before,after);
  return {before,after};
}

function patchMatches(actual,patch) {
  return Object.entries(patch).every(([key,value])=>JSON.stringify(actual.copy?.[key]??(key==='description'?actual.description:undefined))===JSON.stringify(value));
}

function assertSettingsUnchanged(before,after) {
  for(const key of ['price','quantity','shippingTemplate','handlingDays'])if(before[key]!==after[key])throw new Error('经营参数发生变化: '+key);
}

export async function clickSaveDraft(page, request) {
  const actual = await inspectDraft(page, request);
  if (!request.patch||!patchMatches(actual,request.patch)) throw new Error('保存前文案不一致');
  return clickExactDraftSave(page);
}

export async function clickSaveUnchangedDraft(page,request,expected){
  const actual=await inspectDraft(page,request,{allCopy:true});
  for(const key of ['url','store','erpSku','copy','description','price','quantity','shippingTemplate','handlingDays'])
    if(JSON.stringify(actual[key])!==JSON.stringify(expected[key]))throw Error('保存图片前草稿字段变化: '+key);
  return clickExactDraftSave(page);
}

async function clickExactDraftSave(page){
  // Exact text prevents matching 保存并发布 or the separate GPSR 保存 button.
  const selector = await page.evaluate(() => {
    const buttons = [...document.querySelectorAll('button')].filter(e => {
      const text = e.innerText.replace(/\s/g,'').replace(/[\uE000-\uF8FF]/g,'');
      return text === '保存' && e.closest('form')?.innerText.includes('翻译类型');
    });
    if (buttons.length !== 1) throw new Error('草稿保存按钮不唯一');
    const button = buttons[0];
    const all = [...document.querySelectorAll('button')];
    return `button >> nth=${all.indexOf(button)}`;
  });
  await page.click(selector, {label:'保存已核对的草稿'});
  // Caller must inspect acknowledgement and independently reopen before verified.
  return {status:'save_clicked_pending_reconciliation'};
}

export async function reopenSavedDraft(page,request){
  validateRequest(request);
  await page.waitForFunction(()=>location.hash==='#/goods/amazon/draft' &&
    [...document.querySelectorAll('tr')].some(e=>e.innerText.includes('未发布')),
    undefined,{timeout:15000});
  const row=await page.evaluate(r=>{
    const rows=[...document.querySelectorAll('tr')].filter(e=>
      [...e.querySelectorAll('td')].some(c=>c.innerText.trim()===r.draftId));
    if(rows.length!==1)throw new Error('草稿列表ID不唯一');
    const cells=[...rows[0].querySelectorAll('td')].map(c=>c.innerText.trim());
    for(const value of [r.store,r.erpSku,'未发布'])
      if(cells.filter(c=>c===value).length!==1)throw new Error('草稿列表身份或状态不匹配');
    const buttons=[...rows[0].querySelectorAll('button')].filter(e=>e.innerText.trim()==='编辑');
    if(buttons.length!==1)throw new Error('草稿编辑按钮不唯一');
    return{text:rows[0].innerText,selector:`button >> nth=${[...document.querySelectorAll('button')].indexOf(buttons[0])}`};
  },{draftId:request.draftId,store:request.store,erpSku:request.erpSku});
  await page.click(row.selector,{label:'重开同一草稿核对保存结果'});
  await page.waitForFunction(({draftId})=>location.hash===`#/amazon/product/${draftId}?type=draft` &&
    document.querySelector('textarea[placeholder="产品描述"]') &&
    document.querySelector('input[placeholder="店铺"]')?.value &&
    document.querySelector('input[placeholder="亚马逊运输模板"]')?.value,
    {draftId:request.draftId},{timeout:15000});
  return row;
}

// Ledger creation must be exclusive. Never reset an unknown or successful run.
export async function updateEgoDraft(page, request, ledger) {
  validateRequest(request);
  if (!request.patch) throw new Error('缺少修改内容');
  const record = {draftId:request.draftId,store:request.store,erpSku:request.erpSku,
    patch:request.patch,evidence:request.evidence,status:'started',createdAt:new Date().toISOString()};
  await ledger.create(record);
  try {
    await page.goto(`https://www.junfeikuajing.com/#/amazon/product/${request.draftId}?type=draft`);
    await page.waitForFunction(({draftId}) =>
      location.hash === `#/amazon/product/${draftId}?type=draft` &&
      document.querySelector('textarea[placeholder="产品描述"]') &&
      document.querySelector('input[placeholder="店铺"]')?.value &&
      document.querySelector('input[placeholder="亚马逊运输模板"]')?.value,
      {draftId:request.draftId},{timeout:15000});
    record.changes = await applyDescription(page,request);
    record.status='save_unknown';
    await ledger.write(record);
    await clickSaveDraft(page,request);
    const row = await reopenSavedDraft(page,request);
    record.listRow=row.text;
    record.reopened=await inspectDraft(page,request);
    if(!patchMatches(record.reopened,request.patch))throw new Error('重开后文案未持久保存');
    assertSettingsUnchanged(record.changes.before,record.reopened);
    record.status='draft_saved_reopened_verified';record.published=false;
    record.verifiedAt=new Date().toISOString();
    await ledger.write(record);
    return record;
  } catch(error) {
    record.error=error.message;
    if(record.status==='started')record.status='stopped_before_save';
    await ledger.write(record);
    throw error;
  }
}
