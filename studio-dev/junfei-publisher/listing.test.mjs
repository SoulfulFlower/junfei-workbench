import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {price,validate,assertPricingScope,claimExecution} from './listing.mjs';
const product = () => ({id:'test',store:'test',marketplace:'美国',currency:'USD',parentSku:'P',title:'title',description:'desc',shippingTemplate:'FBM',bullets:['1','2','3','4','5'],searchTerms:'cotton shirt',variants:[{sku:'P-Black-M',color:'Black',size:'M',mainImage:'main.jpg',images:[],quantity:88,costRmb:43,weightGrams:390}]});
test('旧公式禁用；缺价不再自动计算',()=>{assert.throws(()=>price(43,390),/已停用/);assert.throws(()=>validate(product()),/明确填写售价/);const p=product();p.variants[0].price='31.06';assert.equal(validate(p).variants[0].price,'31.06');});
test('中文搜索词按UTF-8字节校验',()=>{const p=product();p.searchTerms='衣'.repeat(84);assert.throws(()=>validate(p),/250/);});
test('重复SKU与颜色尺码组合被拒绝',()=>{const p=product();p.variants[0].price='31.06';p.variants.push({...p.variants[0]});assert.throws(()=>validate(p),/SKU重复/);p.variants[1].sku='different';assert.throws(()=>validate(p),/重复颜色尺码/);});
test('非美元不得套用美元价格',()=>{const p=product();p.currency='GBP';assert.throws(()=>validate(p),/明确填写售价/);p.variants[0].price='28.26';assert.equal(validate(p).variants[0].price,'28.26');});
test('库存必须显式提供',()=>{const p=product();delete p.variants[0].quantity;assert.throws(()=>validate(p),/库存/);});
test('草稿估价可以预检但不能发布',()=>{const p=product();p.pricingBasis={child:{scope:'draft_estimate_only'}};assert.doesNotThrow(()=>assertPricingScope([p],false));assert.throws(()=>assertPricingScope([p],true),/不能提交发布/);});
test('草稿档案交接包即使已填写变体售价也不能发布',()=>{
  const p=product();
  p.draftOnly=true;
  p.variants[0].price='31.06';
  assert.doesNotThrow(()=>assertPricingScope([p],false));
  assert.throws(()=>assertPricingScope([p],true),/草稿档案/);
});

test('并发执行只有一方可占位，结果未知时保留原回执', async t => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'junfei-claim-'));
  const file = path.join(directory, 'product.json');
  t.after(async () => {
    await fs.rm(file, {force:true});
    await fs.rmdir(directory);
  });
  const attempts = ['first', 'second'].map(id => ({id, status:'started'}));
  const claims = await Promise.all(attempts.map(record => claimExecution(file, record)));
  assert.equal(claims.filter(Boolean).length, 1);
  const original = attempts[claims.indexOf(true)];
  assert.deepEqual(JSON.parse(await fs.readFile(file, 'utf8')), original);
  const unknown = {...original, status:'saving_unknown'};
  await fs.writeFile(file, JSON.stringify(unknown));
  assert.equal(await claimExecution(file, {id:'retry', status:'started'}), false);
  assert.deepEqual(JSON.parse(await fs.readFile(file, 'utf8')), unknown);
});
