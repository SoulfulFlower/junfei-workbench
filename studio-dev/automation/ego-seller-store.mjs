// Read only the opened Amazon storefront. This module never navigates, calls a
// paid service, reads rank fields, or upgrades observations to selection proof.
const domains = { US: 'www.amazon.com', UK: 'www.amazon.co.uk' };

export async function captureSellerStore(page, { sellerId, marketplace = 'US', excludedAsins = [] }) {
  if (!/^[A-Z0-9]{5,30}$/.test(sellerId || '') || !domains[marketplace]) {
    throw new Error('Unsupported marketplace or invalid seller identity');
  }
  const initial = new URL(await page.url());
  function assertUrl(url) {
    if (url.protocol !== 'https:' || url.hostname !== domains[marketplace] ||
        url.port || url.username || url.password || url.pathname !== '/s' ||
        url.searchParams.get('me') !== sellerId) {
      throw new Error('Opened page is not the expected Amazon seller storefront');
    }
  }
  assertUrl(initial);
  await page.waitForSelector('[data-component-type="s-search-result"][data-asin]', {
    state: 'visible', timeout: 15000,
  });
  const observed = await page.evaluate(() => ({
    url: location.href,
    capturedAt: new Date().toISOString(),
    pageTitle: document.title,
    sortKey: document.querySelector('#s-result-sort-select')?.value || '',
    products: [...document.querySelectorAll('[data-component-type="s-search-result"][data-asin]')]
      .slice(0, 50).map(card => ({
        asin: card.getAttribute('data-asin'),
        title: card.querySelector('h2')?.innerText?.trim() || '',
        imageUrl: card.querySelector('img.s-image')?.src || '',
        priceText: card.querySelector('.a-price .a-offscreen')?.textContent?.trim() || '',
        // Do not read the entire card: extensions may inject candidate BSR.
      })),
  }));
  assertUrl(new URL(observed.url));
  if (new URL(observed.url).searchParams.get('s') &&
      new URL(observed.url).searchParams.get('s') !== observed.sortKey) {
    throw new Error('Storefront sort control does not match the loaded URL');
  }
  const excluded = new Set(excludedAsins.map(asin => String(asin).toUpperCase()));
  const seen = new Set();
  const rejected = [];
  const products = observed.products.filter(item => {
    if (!/^[A-Z0-9]{10}$/.test(item.asin || '') || !item.title || seen.has(item.asin)) return false;
    seen.add(item.asin);
    if (excluded.has(item.asin)) {
      rejected.push(item.asin);
      return false;
    }
    return true;
  });
  if (!products.length) throw new Error('No unused identifiable products on the opened storefront');
  return {
    sellerId, marketplace, url: observed.url, capturedAt: observed.capturedAt,
    pageTitle: observed.pageTitle, sortKey: observed.sortKey,
    pageSummary: `${products.length} observed cards; seller listing dates not established`,
    products,
    excludedAsins: rejected,
    qualification: 'unverified_observation',
    sellerListedDate: null,
    limitations: 'Newest Arrivals order does not establish a seller listing date, FBM, same-product sales or rights.',
  };
}
