import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';

export function price(cost, grams) {
  throw Error('旧固定运费定价已停用；请通过报价定价模块生成明确售价及依据');
}
export function assertPricingScope(products, publishing) {
  if (publishing && products.some(p=>p.draftOnly === true)) {
    throw Error('草稿档案生成的交接包不能提交发布');
  }
  if (publishing && products.some(p=>Object.values(p.pricingBasis||{}).some(q=>q.scope==='draft_estimate_only'))) {
    throw Error('草稿情景估价不能提交发布；须先核实实际费用和适用渠道');
  }
}
export function validate(p) {
  for (const key of ['id','store','marketplace','currency','parentSku','title','description','shippingTemplate']) {
    if (typeof p[key] !== 'string' || !p[key].trim()) throw Error(`缺少 ${key}`);
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(p.id)) throw Error('id 仅支持字母、数字、下划线和横线');
  if (!Array.isArray(p.bullets) || p.bullets.length !== 5 || p.bullets.some(x => typeof x !== 'string' || !x.trim())) throw Error('需要完整五点');
  if (typeof p.searchTerms !== 'string' || !p.searchTerms.trim() || Buffer.byteLength(p.searchTerms, 'utf8') > 250) throw Error('搜索词必须非空且不超过250 UTF-8字节');
  if (!Array.isArray(p.variants) || !p.variants.length) throw Error('缺少变体');
  const skus = new Set(), combos = new Set();
  for (const v of p.variants) {
    if (![v.sku,v.color,v.size,v.mainImage].every(x => typeof x === 'string' && x.trim())) throw Error('变体缺少SKU/颜色/尺码/主图');
    if (v.sku.length > 40 || skus.has(v.sku)) throw Error(`SKU重复或超过40字符: ${v.sku}`);
    const combo = JSON.stringify([v.color,v.size]);
    if (combos.has(combo)) throw Error(`重复颜色尺码: ${combo}`);
    skus.add(v.sku); combos.add(combo);
    if (!Number.isInteger(v.quantity) || v.quantity < 0) throw Error('每个变体必须明确填写非负整数库存');
    if (!Array.isArray(v.images) || v.images.length > 8) throw Error('附图必须为数组，最多8张');
    if (v.price !== undefined) {
      if (!/^\d+(\.\d{1,2})?$/.test(String(v.price)) || Number(v.price) <= 0) throw Error('售价无效');
    } else {
      throw Error('各站点必须明确填写售价；缺价不得回退旧固定运费公式');
    }
  }
  return p;
}
function render(value, context) {
  if (typeof value === 'string') {
    return value.replace(/\{\{([\w.]+)\}\}/g, (_, key) => {
      const result = key.split('.').reduce((v,k) => v?.[k], context);
      if (result === undefined || result === null || typeof result === 'object') throw Error(`模板变量无效: ${key}`);
      return String(result);
    });
  }
  if (Array.isArray(value)) return value.map(x => render(x, context));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k,render(v,context)]));
  return value;
}
async function readJson(file) { return JSON.parse(await fs.readFile(file, 'utf8')); }
async function writeJson(file, data) {
  await fs.mkdir(path.dirname(file), {recursive:true});
  const tmp = file + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(data, null, 2));
  await fs.rename(tmp, file);
}

export async function claimExecution(file, record) {
  let handle;
  try {
    handle = await fs.open(file, 'wx');
  } catch (error) {
    if (error.code === 'EEXIST') return false;
    throw error;
  }
  try {
    await handle.writeFile(JSON.stringify(record, null, 2));
    await handle.sync();
  } finally {
    await handle.close();
  }
  return true;
}
async function execute(page, steps, context, imageMap) {
  for (const original of steps) {
    if (original.action === 'eachVariant') {
      for (const [index, variant] of context.product.variants.entries()) await execute(page, original.steps, {...context, variant, index}, imageMap);
      continue;
    }
    const s = render(original, context);
    const locator = s.selector ? page.locator(s.selector) : null;
    if (s.action === 'goto') { await page.goto(s.url, {waitUntil:'domcontentloaded'}); continue; }
    if (s.action === 'assertCount') {
      await locator.first().waitFor({state:'visible'});
      if (await locator.count() !== Number(s.count)) throw Error(`元素数量不符: ${s.selector}`);
      continue;
    }
    if (!locator || await locator.count() !== 1) throw Error(`选择器必须唯一匹配: ${s.selector}`);
    switch (s.action) {
      case 'fill': await locator.fill(s.value); break;
      case 'click': await locator.click(); break;
      case 'select': await locator.selectOption({label:s.value}); break;
      case 'check': await locator.setChecked(s.value !== false); break;
      case 'upload': {
        const files = s.files.map(x => imageMap.get(path.resolve(context.base, x)));
        if (files.some(x => !x)) throw Error('上传图片未经过预处理');
        await locator.setInputFiles(files); break;
      }
      case 'assertText': {
        await locator.waitFor({state:'visible'});
        const until = Date.now() + 30000;
        while (!(await locator.innerText()).includes(s.value)) {
          if (Date.now() > until) throw Error(`未确认页面文字: ${s.value}`);
          await page.waitForTimeout(300);
        }
        break;
      }
      case 'assertValue': if (await locator.inputValue() !== s.value) throw Error(`字段核对失败: ${s.selector}`); break;
      default: throw Error(`未知动作: ${s.action}`);
    }
  }
}
async function main() {
  const args = process.argv.slice(2);
  const arg = key => { const i=args.indexOf(key); return i < 0 ? undefined : args[i+1]; };
  const input = arg('--products');
  if (!input) throw Error('用法: node listing.mjs --products products.json [--recipe recipe.json] [--run] [--publish]');
  if (args.includes('--publish') && !args.includes('--run')) throw Error('--publish 必须同时指定 --run');
  const base = path.dirname(path.resolve(input));
  const products = await readJson(input);
  if (!Array.isArray(products) || !products.length) throw Error('产品文件必须为非空数组');
  const ids = new Set();
  for (const p of products) { validate(p); if(ids.has(p.id)) throw Error('产品id重复'); ids.add(p.id); }
  assertPricingScope(products,args.includes('--publish'));
  const {default: sharp} = await import('sharp');
  const out = path.resolve(arg('--output') || path.join(base, 'run-output'));
  const imageMap = new Map();
  for (const p of products) {
    for (const v of p.variants) {
      for (const name of [v.mainImage,...v.images]) {
        const source = path.resolve(base, name);
        if (imageMap.has(source)) continue;
        const info = await sharp(source).rotate().toBuffer({resolveWithObject:true});
        const {width,height} = info.info;
        const scale = Math.max(1, 1600 / Math.min(width,height));
        const target = path.join(out,'images',crypto.createHash('sha256').update(source).digest('hex')+'.jpg');
        await fs.mkdir(path.dirname(target),{recursive:true});
        await sharp(info.data).resize(Math.ceil(width*scale),Math.ceil(height*scale)).flatten({background:'#ffffff'}).jpeg({quality:92}).toFile(target);
        imageMap.set(source,target);
      }
    }
  }
  await writeJson(path.join(out,'plan.json'),products);
  if (!args.includes('--run')) { console.log(`预检完成: ${products.length} 个产品；计划和图片: ${out}。未操作ERP。`); return; }
  const recipe = await readJson(arg('--recipe') || path.join(base,'recipe.json'));
  if (!recipe.calibrated || JSON.stringify(recipe).includes('REPLACE_')) throw Error('页面配置尚未校准：请填写真实页面选择器并设置 calibrated=true');
  for(const phase of ['setup','fields','verify','save','confirmSaved']) {
    if (!Array.isArray(recipe[phase]) || !recipe[phase].length) throw Error(`缺少页面步骤: ${phase}`);
  }
  for (const phase of ['verify','confirmSaved',...(args.includes('--publish')?['confirmSubmitted']:[])]) {
    if (!recipe[phase]?.some(s=>s.action?.startsWith('assert'))) throw Error(`${phase} 必须包含页面断言`);
  }
  if(args.includes('--publish') && !recipe.publish?.length) throw Error('缺少发布步骤');
  const {chromium} = await import('playwright');
  // 独立持久化登录目录；不读取其他浏览器的凭据。
  const browser = await chromium.launchPersistentContext(path.join(out,'browser-profile'), {channel:'msedge', headless:false, ignoreDefaultArgs:['--disable-extensions'], viewport:{width:1600,height:1000}});
  const page = browser.pages()[0] || await browser.newPage();
  page.setDefaultTimeout(30000);
  try {
    await page.goto('https://www.junfeikuajing.com/#/goods/amazon/draft', {waitUntil:'domcontentloaded'});
    const {createInterface} = await import('node:readline/promises');
    const terminal = createInterface({input:process.stdin,output:process.stdout});
    await terminal.question('请在浏览器完成登录，然后按回车开始执行：'); terminal.close();
    for (const product of products) {
      const recordFile = path.join(out,product.id+'.json');
      const record = {id:product.id,parentSku:product.parentSku,status:'started',time:new Date().toISOString()};
      if (!await claimExecution(recordFile, record)) {
        console.log(`跳过 ${product.id}: 已有执行记录，请核对原记录后决定后续操作`);
        continue;
      }
      const context = {product,base};
      try {
        for (const phase of ['setup','fields','verify']) await execute(page,recipe[phase],context,imageMap);
        record.status='saving_unknown'; record.url=page.url(); await writeJson(recordFile,record);
        await execute(page,recipe.save,context,imageMap);
        await execute(page,recipe.confirmSaved,context,imageMap);
        record.status='draft_saved'; record.url=page.url(); await writeJson(recordFile,record);
        if (args.includes('--publish')) {
          record.status='submission_unknown'; await writeJson(recordFile,record);
          await execute(page,recipe.publish,context,imageMap);
          await execute(page,recipe.confirmSubmitted,context,imageMap);
          record.status='submitted'; // 只证明已提交，不代表亚马逊全部变体在线。
        }
        await page.screenshot({path:path.join(out,product.id+'.png'),fullPage:true});
        record.url=page.url(); await writeJson(recordFile,record);
        console.log(`${product.id}: ${record.status}`);
      } catch(e) {
        record.error=e.message; record.url=page.url();
        await writeJson(recordFile,record);
        await page.screenshot({path:path.join(out,product.id+'-error.png'),fullPage:true}).catch(()=>{});
        throw Error(`${product.id}: ${e.message}。已停止批次，请核对记录，勿直接重复提交。`);
      }
    }
  } finally { await browser.close(); }
}
if (typeof process !== 'undefined' && process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main().catch(e=>{console.error(e.message);process.exitCode=1;});

