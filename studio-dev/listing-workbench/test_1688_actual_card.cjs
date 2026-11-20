// Test an anonymized card with the observed DOM structure and no offer link.
const {chromium} = require('../junfei-publisher/node_modules/playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const context = await browser.newContext();
    await context.route('**/*', route => route.abort());
    const page = await context.newPage();
    await page.setContent(`
      <article data-tracker="offer" data-renderkey="fixture_700000000001">
        <h2 class="titleText">示例自粘门窗密封条</h2>
        <span class="priceItem"><span>¥</span> <span>0</span> <span>.57</span></span>
        <span class="shopName">示例供应商</span>
        <img width="48" height="48" src="https://cbu01.alicdn.com/fixture.jpg">
      </article>`);
    assert.equal(await page.locator('a[href*="/offer/"]').count(), 0);
    await page.addScriptTag({path:path.join(__dirname, 'extension/1688-search.js')});
    const result = await page.evaluate(() => collect1688SearchPage());
    assert.equal(result.offers.length, 1);
    const offer = result.offers[0];
    assert.equal(offer.offerId, '700000000001');
    assert.equal(offer.url, 'https://detail.1688.com/offer/700000000001.html');
    assert.equal(offer.priceText, '¥0.57');
    assert.equal(offer.supplierText, '示例供应商');
    assert.match(offer.title, /示例自粘门窗密封条/);
    assert.ok(offer.imageUrl.startsWith('https://cbu01.alicdn.com/'));
    console.log('ACTUAL_DOM_OK: card ID, title, split price ¥0.57, supplier and image extracted with no offer anchor');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
