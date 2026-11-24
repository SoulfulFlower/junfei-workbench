// Test the exact card DOM observed in the dedicated Edge; block all network requests.
const {chromium} = require('../junfei-publisher/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const context = await browser.newContext();
    await context.route('**/*', route => route.abort());
    const page = await context.newPage();
    await page.setContent(fs.readFileSync(path.join(__dirname, '../automation/data/1688-air-card-705907720182-20261101.html'), 'utf8'));
    assert.equal(await page.locator('a[href*="/offer/"]').count(), 0);
    await page.addScriptTag({path:path.join(__dirname, 'extension/1688-search.js')});
    const result = await page.evaluate(() => collect1688SearchPage());
    assert.equal(result.offers.length, 1);
    const offer = result.offers[0];
    assert.equal(offer.offerId, '705907720182');
    assert.equal(offer.url, 'https://detail.1688.com/offer/705907720182.html');
    assert.equal(offer.priceText, '¥0.57');
    assert.equal(offer.supplierText, '义乌往复电子商务有限公司');
    assert.match(offer.title, /5米自粘型门窗密封条/);
    assert.ok(offer.imageUrl.startsWith('https://cbu01.alicdn.com/'));
    console.log('ACTUAL_DOM_OK: card ID, title, split price ¥0.57, supplier and image extracted with no offer anchor');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
