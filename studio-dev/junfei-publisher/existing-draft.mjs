import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const origin = 'https://www.junfeikuajing.com';
const fields = {
  title: '产品标题', description: '产品描述', price: '价格',
  quantity: '库存', handlingDays: '处理时间',
};
const attributes = {
  color: {label:'Color', select:true},
  material: {label:'Material Type', select:true},
  widthInches: {label:'Width shorter horizontal edge', unit:'Width Unit'},
  heightInches: {label:'Height base to top', unit:'Height Unit'},
  lengthInches: {label:'Length longer horizontal edge', unit:'Length Unit'},
};
export function validateRequest(r) {
  if (!r || !/^\d+$/.test(r.draftId) || typeof r.store !== 'string' || !r.store.trim()
      || typeof r.erpSku !== 'string' || !r.erpSku.trim()) throw Error('必须明确草稿ID、店铺与ERP SKU');
  if (!r.patch || typeof r.patch !== 'object' || Array.isArray(r.patch) || !Object.keys(r.patch).length) throw Error('缺少明确修改字段');
  for (const [key, value] of Object.entries(r.patch)) {
    const attribute = attributes[key];
    if ((!Object.hasOwn(fields, key) && !attribute) || typeof value !== 'string'
        || (!value.trim() && !(key === 'material' && value === ''))) throw Error(`不支持或无效字段: ${key}`);
    if (attribute && (typeof r.evidence?.[key] !== 'string' || !r.evidence[key].trim())) throw Error(`属性必须有来源依据: ${key}`);
    if (attribute?.unit && (!/^\d+(\.\d{1,2})?$/.test(value) || Number(value) <= 0 || !Number.isFinite(Number(value)))) throw Error('尺寸必须为明确的正数英寸值');
    if (key === 'price' && !/^\d+(\.\d{1,2})?$/.test(value)) throw Error('价格必须明确为正数');
    if (key === 'price' && Number(value) <= 0) throw Error('价格必须明确为正数');
    if (['quantity','handlingDays'].includes(key) && (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)))) throw Error('库存和处理时间必须为非负整数');
  }
  return r;
}
async function unique(locator) {
  if (await locator.count() !== 1) throw Error('页面字段必须唯一匹配');
  return locator;
}
async function input(page, placeholder) {
  return unique(page.getByPlaceholder(placeholder, {exact:true}));
}
function attributeRow(page, label) {
  return page.locator('.el-form-item').filter({has:page.locator('label .normal').filter({hasText:new RegExp('^\\s*'+label+'\\s*$')})});
}
async function attributeInput(page, label) {
  return unique(attributeRow(page,label).locator('input'));
}
async function patchInput(page, key) {
  const attr = attributes[key];
  if (!attr) return input(page, fields[key]);
  if (attr.unit && await (await attributeInput(page,attr.unit)).inputValue() !== '英寸(Inches)') throw Error('尺寸单位不是已校准的英寸，停止修改');
  return attributeInput(page,attr.label);
}
export async function applyPatch(page, patch) {
  for (const [key,value] of Object.entries(patch)) {
    const control=await patchInput(page,key);
    if (!attributes[key]?.select) {await control.fill(value);continue;}
    if (await control.inputValue() === value) continue;
    if (key === 'material' && value === '') {
      await control.hover();
      const clear=attributeRow(page,attributes[key].label).locator('.el-icon-circle-close:visible');
      await (await unique(clear)).click();
    } else {
      await control.click();
      const option=page.locator('.el-select-dropdown:visible li').filter({has:page.getByText(value,{exact:true})});
      await (await unique(option)).click();
    }
  }
}
export async function inspectDraft(page, r) {
  const url = new URL(page.url());
  if (url.origin !== origin || url.hash !== `#/amazon/product/${r.draftId}?type=draft`) throw Error('草稿编辑地址不符');
  const store = await (await input(page, '店铺')).inputValue();
  const erpSku = await (await input(page, '父Sku,可自定义填写内容，方便卖家在后台识别是什么产品，该内容不在平台商城展示')).inputValue();
  if (store !== r.store || erpSku !== r.erpSku) throw Error('草稿店铺或ERP SKU不符，停止修改');
  const values = {};
  for (const key of Object.keys(r.patch)) values[key] = await (await patchInput(page,key)).inputValue();
  return {draftId:r.draftId, store, erpSku, values};
}
// ledger.write must persist before returning; saving_unknown must survive crashes.
// Existing records are immutable execution barriers, including previously successful saves.
export async function updateExistingDraft(page, request, ledger) {
  const r = validateRequest(request);
  if (await ledger.read()) throw Error('已有执行记录；先对账，不重复保存');
  const record = {version:1, draftId:r.draftId, store:r.store, erpSku:r.erpSku,
    patch:r.patch, evidence:r.evidence || {}, status:'started', time:new Date().toISOString()};
  await ledger.write(record);
  try {
    await page.goto(`${origin}/#/amazon/product/${r.draftId}?type=draft`, {waitUntil:'domcontentloaded'});
    await page.getByPlaceholder('店铺', {exact:true}).waitFor({state:'visible'});
    record.before = await inspectDraft(page, r);
    await applyPatch(page,r.patch);
    const staged = await inspectDraft(page, r);
    if (Object.entries(r.patch).some(([k,v])=>staged.values[k] !== v)) throw Error('保存前字段断言失败');
    const saves = page.getByRole('button',{name:'保存',exact:true});
    // Two observed controls: product save followed by GPSR save. Reject changed layout.
    if (await saves.count() !== 2) throw Error('保存按钮布局已改变，需重新校准');
    record.status='saving_unknown'; await ledger.write(record);
    await saves.nth(0).click();
    await page.getByRole('alert').filter({hasText:'保存成功'}).waitFor({state:'visible'});
    await page.waitForURL(`${origin}/#/goods/amazon/draft`);
    const row = await unique(page.getByRole('row').filter({has:page.getByRole('cell',{name:r.draftId,exact:true})}));
    for (const name of [r.store,r.erpSku,'未发布']) {
      if (await row.getByRole('cell',{name,exact:true}).count() !== 1) throw Error('保存后列表身份或状态不符');
    }
    record.listRow = await row.innerText();
    await row.getByRole('button',{name:'编辑',exact:true}).click();
    await page.getByPlaceholder('店铺',{exact:true}).waitFor({state:'visible'});
    record.after = await inspectDraft(page,r);
    if (Object.entries(r.patch).some(([k,v])=>record.after.values[k] !== v)) throw Error('重新打开后字段未持久保存');
    record.status='draft_saved_verified'; record.verifiedAt=new Date().toISOString();
    await ledger.write(record);
    return record;
  } catch (e) {
    // Preserve unknown state after any save attempt; never convert it into retryable failure.
    record.error=e.message;
    if (record.status === 'started') record.status='stopped_before_save';
    await ledger.write(record);
    throw e;
  }
}

async function main() {
  const args=process.argv.slice(2);
  const arg=k=>{const i=args.indexOf(k);return i<0?undefined:args[i+1];};
  if (args.includes('--publish')) throw Error('此适配器仅修改已有草稿，不支持发布');
  if (!arg('--request')) throw Error('用法: node existing-draft.mjs --request request.json [--output 独立任务目录] [--run]');
  const r=validateRequest(JSON.parse(await fs.readFile(arg('--request'),'utf8')));
  if (!args.includes('--run')) { console.log(JSON.stringify({valid:true,erpTouched:false,request:r},null,2)); return; }
  if (!arg('--output')) throw Error('--run必须指定独立任务输出目录');
  const out=path.resolve(arg('--output')); await fs.mkdir(out,{recursive:true});
  const lock=await fs.open(path.join(out,'execution.lock'),'wx').catch(()=>{throw Error('任务正在执行或上次异常退出，须先核对锁和ERP实际结果');});
  let browser;
  try {
    const recordFile=path.join(out,'record.json');
    const ledger={
      read:async()=>{try{return JSON.parse(await fs.readFile(recordFile,'utf8'));}catch(e){if(e.code==='ENOENT')return null;throw e;}},
      write:async data=>{const tmp=recordFile+'.tmp';await fs.writeFile(tmp,JSON.stringify(data,null,2));await fs.rename(tmp,recordFile);},
    };
    if(await ledger.read()) throw Error('已有执行记录；先对账，不启动浏览器');
    const {chromium}=await import('playwright');
    browser=await chromium.launchPersistentContext(path.join(out,'browser-profile'),{channel:'msedge',headless:false});
    const page=browser.pages()[0]||await browser.newPage();
    await page.goto(`${origin}/#/goods/amazon/draft`);
    const {createInterface}=await import('node:readline/promises');
    const terminal=createInterface({input:process.stdin,output:process.stdout});
    try {await terminal.question('请在浏览器完成登录，然后按回车开始执行：');}finally{terminal.close();}
    try {console.log(JSON.stringify(await updateExistingDraft(page,r,ledger),null,2));}
    finally {await page.screenshot({path:path.join(out,'result.png'),fullPage:true}).catch(()=>{});}
  } finally {try {if(browser)await browser.close();}finally{await lock.close();await fs.unlink(path.join(out,'execution.lock'));}}
}
if(typeof process !== 'undefined' && process.argv[1] && import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href) main().catch(e=>{console.error(e.message);process.exitCode=1;});
