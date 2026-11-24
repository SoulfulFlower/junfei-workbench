// 独立 Edge 执行器。大脑通过本地 JSON 队列逐步派发动作，不开放网络端口。
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {assertAllowedPageUrl} from './brain-url-policy.mjs';
import {stopWhenBrowserCloses} from './brain-session-lifecycle.mjs';
import {trackPages} from './brain-page-tracker.mjs';
import {resolveEdgeProfile} from './brain-edge-profile.mjs';
import {pageMetadata} from './brain-page-metadata.mjs';
import {pasteImageToSearch} from './brain-image-paste.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const state = path.join(root, 'brain-state');
let profilePath = process.env.JUNFEI_EDGE_PROFILE_DIR;
if (!profilePath) {
  profilePath = await fs.readFile(path.join(state, 'edge-profile.path'), 'utf8').catch(error => {
    if (error.code === 'ENOENT') return undefined;
    throw error;
  });
}
const edgeProfile = resolveEdgeProfile(state, profilePath?.trim());
const inbox = path.join(state, 'commands');
const results = path.join(state, 'results');
const session = crypto.randomUUID();
const origin = 'https://www.junfeikuajing.com';
const allowedRoot = process.argv[2] ? await fs.realpath(process.argv[2]) : null;
let browser, page, lock;
let pageDialogs = [];
let stopping = false;

async function write(file, value) {
  const temp = `${file}.${process.pid}.tmp`;
  await fs.writeFile(temp, JSON.stringify(value, null, 2), 'utf8');
  await fs.rename(temp, file);
}
function target(descriptor) {
  let scope = page;
  if (descriptor.scope) scope = target(descriptor.scope);
  let value;
  if (descriptor.role) value = scope.getByRole(descriptor.role, {name: descriptor.name, exact: descriptor.exact !== false});
  else if (descriptor.placeholder) value = scope.getByPlaceholder(descriptor.placeholder, {exact:true});
  else if (descriptor.label) value = scope.getByLabel(descriptor.label, {exact:true});
  else if (descriptor.text) value = scope.getByText(descriptor.text, {exact:descriptor.exact !== false});
  else if (descriptor.css) value = scope.locator(descriptor.css);
  else throw Error('缺少明确定位信息');
  if (descriptor.index !== undefined) value = value.nth(descriptor.index);
  return value;
}
function checkUrl(url) {
  assertAllowedPageUrl(url);
}
async function observe(id) {
  if (!page || page.isClosed()) throw Error('专属 Edge 已没有可用标签页');
  await page.waitForLoadState('domcontentloaded', {timeout:8000}).catch(() => {});
  await page.waitForTimeout(350); // Vue弹窗及短暂校验提示在事件后的下一帧更新。
  const url = page.url();
  const metadata = pageMetadata(url);
  if (!metadata.allowed) return {url:metadata, blockedByPolicy:true};
  if (url.includes('/login')) return {url, needsLogin:true, message:'请在 Edge 手动登录，脚本不读取或填写凭据'};
  const snapshot = await page.locator('body').ariaSnapshot({timeout:15000});
  const screenshot = path.join(results, `${id}.png`);
  await page.screenshot({path:screenshot, fullPage:false});
  const messages = await page.locator('.el-message:visible, .el-notification:visible, .el-message-box:visible').allTextContents();
  return {url, title:await page.title(), snapshot, screenshot, messages, dialogs:pageDialogs.splice(0)};
}
async function act(command) {
  if (command.action === 'inspectPages') {
    return await Promise.all(browser.pages().map(async (candidate, index) => {
      const url = candidate.url();
      return {index, ...pageMetadata(url)};
    }));
  }
  if (command.action === 'selectPage') {
    const pages = browser.pages();
    if (!Number.isInteger(command.index) || command.index < 0 || command.index >= pages.length) throw Error('标签页序号无效，请重新检查');
    page = pages[command.index];
    checkUrl(page.url());
    return {index:command.index, url:page.url(), title:await page.title()};
  }
  if (command.action === 'snapshot') return;
  if (command.action === 'pasteImageToSearch') {
    if (!command.target || typeof command.imageBase64 !== 'string') throw Error('图片粘贴需要明确搜索框定位和剪贴板图片数据');
    const locator = target(command.target);
    if (await locator.count() !== 1) throw Error('搜索框定位必须唯一匹配，请重新观察页面');
    return await pasteImageToSearch({page, locator, imageBase64:command.imageBase64});
  }
  if (command.action === 'inspectCss') {
    checkUrl(page.url());
    return await page.locator(command.css).evaluateAll(elements => elements.map((el,index) => ({index,tag:el.tagName.toLowerCase(),type:el.type||'',text:(el.innerText||el.textContent||'').trim().slice(0,300),html:el.outerHTML.slice(0,2000),value:('value' in el && el.type!=='password' && el.type!=='file')?el.value:undefined,disabled:!!el.disabled})));
  }
  if (command.action === 'clickCssIndex') {
    checkUrl(page.url());
    const locator = page.locator(command.css).nth(command.index);
    if (await locator.count() !== 1) throw Error('CSS序号目标无效');
    await locator.click();
    return;
  }
  if (command.action === 'inspectContext') {
    checkUrl(page.url());
    const locator = page.locator(command.css).nth(command.index ?? 0);
    if (await locator.count() !== 1) throw Error('inspectContext目标无效');
    return await locator.evaluate(el => ({self:el.outerHTML,parents:Array.from((function*(){let n=el;for(let i=0;n&&i<6;i++,n=n.parentElement)yield n})()).map(n=>n.outerHTML.slice(0,7000))}));
  }
  if (command.action === 'inspectVisible') {
    return await page.locator('input:visible, textarea:visible, select:visible, [contenteditable="true"]:visible').evaluateAll(elements => elements.map((el, index) => {
      const item = el.closest('.el-form-item, .form-group, fieldset, tr, [role="row"]');
      const label = item?.querySelector('.el-form-item__label, label, th, [role="columnheader"]')?.innerText?.trim() || '';
      const type = el.type || el.tagName.toLowerCase();
      return {
        index, tag:el.tagName.toLowerCase(), type,
        id:el.id || '', name:el.getAttribute('name') || '',
        placeholder:el.getAttribute('placeholder') || '',
        ariaLabel:el.getAttribute('aria-label') || '', label,
        value:type === 'password' || type === 'file' ? undefined : el.value,
        checked:('checked' in el) ? el.checked : undefined,
        disabled:!!el.disabled,
        options:el.tagName === 'SELECT' ? Array.from(el.options).map(option => ({label:option.label, value:option.value, selected:option.selected})) : undefined,
        context:(item?.innerText || '').trim().slice(0,180)
      };
    }));
  }
  if (command.action === 'fillVisible') {
    const controls = page.locator('input:visible, textarea:visible, select:visible, [contenteditable="true"]:visible');
    const count = await controls.count();
    if (!Number.isInteger(command.index) || command.index < 0 || command.index >= count) throw Error('可见控件序号无效，请重新检查页面');
    const locator = controls.nth(command.index);
    const info = await locator.evaluate(el => ({tag:el.tagName.toLowerCase(), type:el.type || ''}));
    if (!['text','textarea'].includes(info.type) && info.tag !== 'textarea') throw Error('fillVisible 仅允许文本输入框');
    await locator.fill(String(command.value));
    return;
  }
  if (command.action === 'goto') {
    checkUrl(command.url);
    await page.goto(command.url, {waitUntil:'domcontentloaded'});
    return;
  }
  checkUrl(page.url());
  if (page.url().includes('/login')) throw Error('需要手动登录后才能执行');
  if (command.action === 'screenshot') return;
  const locator = target(command.target || {});
  if (await locator.count() !== 1) throw Error('定位必须唯一匹配，请重新观察页面');
  switch (command.action) {
    case 'click': await locator.click(); break;
    case 'hover': await locator.hover(); break;
    case 'inspect': return await locator.evaluate(el => ({
      html:el.outerHTML.slice(0,30000),
      fields:Array.from(el.querySelectorAll('input:not([type=password]),textarea,select')).map(x=>({tag:x.tagName,type:x.type,placeholder:x.getAttribute('placeholder'),value:x.type==='file'?undefined:x.value}))
    }));
    case 'fill': await locator.fill(String(command.value)); break;
    case 'press': await locator.press(command.key); break;
    case 'select': await locator.selectOption({label:command.value}); break;
    case 'check': await locator.setChecked(command.value !== false); break;
    case 'read': return await locator.innerText();
    case 'upload': {
      if (!allowedRoot) throw Error('请在窗口选择产品文件夹后重新连接 Edge');
      const files = await Promise.all(command.files.map(file => fs.realpath(file)));
      for (const file of files) {
        const rel = path.relative(allowedRoot, file);
        if (rel.startsWith('..') || path.isAbsolute(rel)) throw Error('图片必须位于本次产品资料目录');
        if (!/\.(jpe?g|png|webp)$/i.test(file)) throw Error('仅支持产品图片上传');
      }
      await locator.setInputFiles(files);
      break;
    }
    default: throw Error(`不支持的动作: ${command.action}`);
  }
}

await fs.mkdir(inbox, {recursive:true});
await fs.mkdir(results, {recursive:true});
try {
  try {
    lock = await fs.open(path.join(state, 'worker.lock'), 'wx');
  } catch(error) {
    if (error.code !== 'EEXIST') throw error;
    const pid = Number(await fs.readFile(path.join(state, 'worker.lock'), 'utf8'));
    let alive = true;
    try { process.kill(pid, 0); } catch(e) { if (e.code === 'ESRCH') alive = false; else throw e; }
    if (alive) throw Error('已有大脑协作执行器正在运行，请勿重复连接');
    await fs.unlink(path.join(state, 'worker.lock'));
    lock = await fs.open(path.join(state, 'worker.lock'), 'wx');
  }
  await lock.writeFile(String(process.pid));
  browser = await chromium.launchPersistentContext(edgeProfile, {
    channel:'msedge', headless:false,
    // Playwright 默认禁用扩展；ERP 的采集插件需要在此专用会话正常运行。
    ignoreDefaultArgs:['--disable-extensions'],
    viewport:{width:1440,height:1000}
  });
  page = browser.pages()[0] || await browser.newPage();
  const configurePage = candidate => {
    candidate.setDefaultTimeout(15000);
    candidate.on('dialog', async dialog => {
      pageDialogs.push({type:dialog.type(), message:dialog.message()});
      await dialog.dismiss(); // 记录校验提示；不会自动接受确认框。
    });
  };
  trackPages(browser, {select:candidate => { page = candidate; configurePage(candidate); }, onEmpty:() => { stopping = true; }});
  stopWhenBrowserCloses(browser, () => { stopping = true; });
  await page.goto(origin + '/#/goods/amazon/draft', {waitUntil:'domcontentloaded'});
  await write(path.join(state, 'ready.json'), {session, pid:process.pid, status:'ready', allowedRoot});
  console.log('BRAIN_READY 请在独立 Edge 窗口手动登录。执行器已等待大脑派发动作。');
  process.on('SIGTERM', () => {stopping = true;});
  process.on('SIGINT', () => {stopping = true;});
  while (!stopping) {
    for (const name of (await fs.readdir(inbox)).filter(n => /^[0-9a-f-]+\.json$/.test(n)).sort()) {
      if (stopping) break;
      const resultFile = path.join(results, name);
      try { await fs.access(resultFile); continue; } catch {}
      let command;
      try {
        command = JSON.parse(await fs.readFile(path.join(inbox, name), 'utf8'));
        if (command.session !== session) throw Error('旧会话指令已失效，不会重放');
        const id = name.slice(0,-5);
        // 动作前写入未知结果检查点；异常退出时不会自动重放。
        await write(resultFile, {id, session, status:'in_progress_unknown', action:command.action});
        const value = await act(command);
        const observation = await observe(id);
        await write(resultFile, {id, session, status:'done', value, ...observation});
        console.log(`动作完成 ${command.action} ${id}`);
      } catch(error) {
        const observation = await observe(name.slice(0,-5)).catch(() => ({}));
        await write(resultFile, {session, status:'error', action:command?.action, error:error.message, ...observation});
        console.log(`${/定位|locator\.|Timeout/.test(error.message) ? 'BRAIN_DIAGNOSTIC' : 'BRAIN_PROBLEM'} ${error.message}`);
      }
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
} catch(error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  await browser?.close().catch(()=>{});
  if (lock) {
    await write(path.join(state, 'ready.json'), {session, status:'closed'});
    await lock.close();
    await fs.unlink(path.join(state, 'worker.lock')).catch(()=>{});
  }
}

