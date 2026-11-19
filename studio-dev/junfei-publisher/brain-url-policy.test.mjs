import test from 'node:test';
import assert from 'node:assert/strict';
import {assertAllowedPageUrl} from './brain-url-policy.mjs';

test('allows only exact public 1688 search and product detail HTTPS origins', () => {
  for (const url of [
    'https://s.1688.com/selloffer/offer_search.htm?keywords=test',
    'https://www.1688.com/',
    'https://detail.1688.com/offer/705907720182.html',
    'https://air.1688.com/kapp/1688-search/pc-image-search/?imageId=1',
  ]) assert.doesNotThrow(() => assertAllowedPageUrl(url));
});

test('allows only the dedicated 1688 image-search route on air.1688.com', () => {
  for (const url of [
    'https://air.1688.com/kapp/1688-search/pc-image-search',
    'https://air.1688.com/kapp/1688-search/pc-image-search/',
  ]) assert.doesNotThrow(() => assertAllowedPageUrl(url));
  for (const url of [
    'https://air.1688.com/app/ctf-page/payment-cashier-pc-air/batch-cashier.html',
    'https://air.1688.com/kapp/1688-search/other/',
    'https://air.1688.com.evil.example/kapp/1688-search/pc-image-search/',
  ]) assert.throws(() => assertAllowedPageUrl(url), /执行器拒绝访问/);
});

test('keeps the ERP and local workbench origins available', () => {
  for (const url of [
    'https://www.junfeikuajing.com/#/goods/amazon/draft',
    'http://127.0.0.1:18765/',
    'http://localhost:18765/',
  ]) assert.doesNotThrow(() => assertAllowedPageUrl(url));
});

test('rejects unrelated Alibaba origins and lookalike 1688 hosts', () => {
  for (const url of [
    'https://www.alibaba.com/',
    'https://login.1688.com/',
    'https://cart.1688.com/',
    'https://trade.1688.com/',
    'https://evil.1688.com/',
    'https://1688.com/',
    'https://detail.1688.com.evil.example/',
  ]) assert.throws(() => assertAllowedPageUrl(url), /执行器拒绝访问/);
});

test('rejects non-HTTPS 1688 pages and malformed URLs with a useful diagnostic', () => {
  assert.throws(() => assertAllowedPageUrl('http://detail.1688.com/offer/1.html'), /detail\.1688\.com/);
  assert.throws(() => assertAllowedPageUrl('not a URL'), /无效 URL/);
});
