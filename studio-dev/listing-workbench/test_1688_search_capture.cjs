const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(__dirname + '/extension/popup.js', 'utf8');
const collector = fs.readFileSync(__dirname + '/extension/1688-search.js', 'utf8');
const handler = source.split(/\r?\n/).find(line => line.startsWith("$('capture1688Search').onclick="));
const urlPolicy = source.split(/\r?\n/).find(line => line.startsWith('function is1688SearchUrl('));
assert.ok(handler, 'search capture handler must be present');

async function capture({url, heading = '', body = '', owner = 'tester'}) {
  const controls = {capture1688Search: {}, status: {}};
  const visible = {getClientRects: () => [{}]};
  const card = {innerText: '45mm brown door weather seal 5m self adhesive ¥4.66 supplier sample item',
    querySelectorAll: () => [], querySelector: () => null};
  const link = {...visible, href: 'https://detail.1688.com/offer/705907720182.html',
    innerText: '45mm brown door seal', closest: () => card, getAttribute: () => null};
  const pageDocument = {body: {innerText: body}, querySelectorAll: selector =>
    selector.startsWith('a[') ? [link] : selector.startsWith('[data-tracker') ? [] : [{...visible, innerText: heading}]};
  const posted = [];
  const context = {
    $: id => controls[id], ready: Promise.resolve(),
    binding: {user: {username: 'tester'}, url: 'https://workbench.example', token: 'test'},
    URL, Date, Error,
    // Popup DOM deliberately contradicts the page, exposing accidental cross-context reads.
    document: {querySelectorAll: () => {throw Error('read popup DOM');}},
    chrome: {
      storage: {local: {get: async () => ({linkedOwner: owner, linkedAsin: 'B0HNSJ55Q3', linkedMarket: 'US'})}},
      tabs: {query: async () => [{id: 42}]},
      scripting: {executeScript: async ({func, target}) => {
        assert.equal(target.tabId, 42);
        const result = vm.runInNewContext('(' + func.toString() + ')()',
          {document: pageDocument, location: {href: url}, URL});
        return [{result}];
      }}
    },
    fetch: async (url, options) => {
      posted.push(JSON.parse(options.body));
      return {ok: true, json: async () => ({})};
    }
  };
  vm.runInNewContext(collector + '\n' + urlPolicy + '\n' + handler, context);
  await controls.capture1688Search.onclick();
  assert.equal(controls.capture1688Search.disabled, false);
  return {posted, status: controls.status.textContent};
}

(async () => {
  const imagePage = await capture({url: 'https://s.1688.com/selloffer/offer_search.htm', heading: '图片搜索'});
  assert.equal(imagePage.posted.length, 1);
  assert.equal(imagePage.posted[0].offers[0].offerId, '705907720182');
  assert.equal(imagePage.posted[0].asin, 'B0HNSJ55Q3');
  const normal = await capture({url: 'https://s.1688.com/selloffer/offer_search.htm?keywords=seal'});
  assert.equal(normal.posted.length, 0);
  assert.match(normal.status, /普通关键词/);
  const recommendations = await capture({url: 'https://s.1688.com/', heading: '找同款', body: '没有更多相关商品了'});
  assert.equal(recommendations.posted.length, 0);
  assert.match(recommendations.status, /推荐结果/);
  const queryImage = await capture({url: 'https://s.1688.com/?imageId=observed'});
  assert.equal(queryImage.posted.length, 1);
  const otherOwner = await capture({url: 'https://s.1688.com/?imageId=observed', owner: 'other'});
  assert.equal(otherOwner.posted.length, 0);
  assert.match(otherOwner.status, /当前账号关联/);
  const air = await capture({url: 'https://air.1688.com/kapp/1688-search/pc-image-search/?tab=imageSearch&imageId=1549408876533674324'});
  assert.equal(air.posted.length, 1);
  for (const url of ['https://air.1688.com/other/?imageId=1',
    'https://air.1688.com/kapp/1688-search/pc-image-search/unrelated?imageId=1',
    'https://air.1688.com.evil.example/kapp/1688-search/pc-image-search/?imageId=1',
    'https://user@air.1688.com/kapp/1688-search/pc-image-search/?imageId=1',
    'https://air.1688.com:8443/kapp/1688-search/pc-image-search/?imageId=1']) {
    const rejected = await capture({url});
    assert.equal(rejected.posted.length, 0, url);
  }
  console.log('1688 capture executes in page context; keyword recommendations and other accounts rejected');
})().catch(error => {console.error(error); process.exitCode = 1;});
