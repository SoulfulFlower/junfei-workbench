// Observe an already-opened formal supplier-queue page. This module never
// navigates, scrolls, requests data, loads images, selects a SKU or orders goods.
function supplierIdentity(value, offerId) {
  let url;
  try { url = new URL(value); } catch { throw Error('Supplier observation requires the current exact offer URL'); }
  if (url.protocol !== 'https:' || url.hostname !== 'detail.1688.com'
      || url.username || url.password || (url.port && url.port !== '443')
      || url.pathname !== `/offer/${offerId}.html`) {
    throw Error('Supplier observation current offer identity mismatch');
  }
  return url.origin + url.pathname;
}

export async function observeCurrentSupplier(page, {offerId} = {}) {
  if ((typeof offerId === 'number' && !Number.isSafeInteger(offerId))
      || !/^[1-9]\d*$/.test(String(offerId ?? ''))) {
    throw Error('An exact positive supplier offerId is required');
  }
  const expected = String(offerId);
  const canonicalUrl = supplierIdentity(await page.url(), expected);
  const result = await page.evaluate(({expected, canonicalUrl}) => {
    const current = new URL(location.href);
    if (current.protocol !== 'https:' || current.hostname !== 'detail.1688.com'
        || current.username || current.password || (current.port && current.port !== '443')
        || current.pathname !== `/offer/${expected}.html`
        || current.origin + current.pathname !== canonicalUrl) {
      throw Error('Supplier observation document offer identity mismatch');
    }
    const visible = element => Boolean(element?.getClientRects().length)
      && getComputedStyle(element).visibility !== 'hidden'
      && getComputedStyle(element).display !== 'none';
    const fullVisibleText = document.body?.innerText || '';
    const challenge = /验证码|安全验证|访问受限|安全检查|captcha|challenge/i.test(document.title)
      || [...document.querySelectorAll('#nc_1_wrapper,.nc-container,#baxia-dialog-content,iframe[src*="punish"],iframe[src*="captcha"]')].some(visible)
      || /请完成验证|拖动滑块/.test(fullVisibleText);
    if (challenge) throw Error('SUPPLIER_HUMAN_VERIFICATION_REQUIRED: stop the supplier queue');

    const rowsOf = table => [...table.rows].map(row => [...row.cells].map(cell => cell.innerText.trim()));
    const packagingTable = table => {
      const header = table.rows[0]?.innerText || '';
      return /重量\s*[（(]g[）)]/.test(header)
        && (/规格|颜色|尺码/.test(header)
          || (/长\s*[（(]cm[）)]/.test(header)
            && /宽\s*[（(]cm[）)]/.test(header)
            && /高\s*[（(]cm[）)]/.test(header)));
    };
    const packagingTables = [...document.querySelectorAll('table')]
      .filter(visible).filter(packagingTable).map(rowsOf);

    // Keep the entire actual attribute section and its original rows. A paired
    // projection is convenient, but its whitelist-free entries remain auditable.
    const headings = [...document.querySelectorAll('h1,h2,h3')];
    const attributeRoots = [...new Set(headings.filter(e => e.innerText.trim() === '商品属性')
      .map(e => e.closest('.od-collapse-module') || e.parentElement).filter(Boolean))];
    const attributeSections = attributeRoots.map(root => ({
      text: root.innerText || '',
      tables: [...root.querySelectorAll('table')].filter(visible)
        .filter(table => !packagingTable(table)).map(rowsOf),
    }));
    const attributeEntries = [];
    for (const section of attributeSections) {
      for (const table of section.tables) for (const cells of table) {
        if (cells.length % 2 !== 0) continue;
        for (let i = 0; i + 1 < cells.length; i += 2) {
          if (cells[i] && cells[i + 1]) attributeEntries.push({key: cells[i], value: cells[i + 1], source: 'attribute_table'});
        }
      }
    }
    // The actual gallery parameter list is outside the main attribute section.
    // Its observed decision-attributes-list items have two paragraph children.
    const summaryItems = [...new Set([
      ...document.querySelectorAll('.decision-attributes-list > li'),
      ...attributeRoots.flatMap(root => [...root.querySelectorAll('li')]),
    ])];
    const attributeSummary = [];
    for (const item of summaryItems) {
      const parts = [...item.children].filter(e => e.tagName === 'P' && visible(e)).map(e => e.innerText.trim());
      if (parts.length === 2 && parts[0] && parts[1]) {
        const entry = {key: parts[0], value: parts[1], source: 'attribute_summary'};
        attributeSummary.push(entry);
        attributeEntries.push(entry);
      }
    }
    const attributes = Object.fromEntries(attributeEntries.map(({key, value}) => [key, value]));
    const colourButtons = [...document.querySelectorAll('button.sku-filter-button')].map(e => ({
      text: e.innerText.trim(), active: e.classList.contains('active'),
      visible: visible(e), disabled: e.disabled || e.getAttribute('aria-disabled') === 'true',
      image: e.querySelector('img')?.currentSrc || e.querySelector('img')?.src || null,
    }));
    const selectedColours = colourButtons.filter(e => e.active);
    const skuRows = [...document.querySelectorAll('.expand-view-item')].filter(visible)
      .map(e => e.innerText.trim()).filter(text => /[¥￥]/.test(text) && /库存/.test(text));

    const detailSection = headings.find(e => e.innerText.trim() === '商品详情')?.closest('.od-collapse-module');
    const supplierDetailHost = host => Boolean(detailSection)
      && host.classList?.contains('html-description') && host.closest?.('.od-collapse-module') === detailSection;
    const photoUrl = raw => {
      try {
        const u = new URL(raw);
        return u.protocol === 'https:' && /^cbu\d+\.alicdn\.com$/.test(u.hostname)
          && u.pathname.startsWith('/img/ibank/') && !u.username && !u.password
          && (!u.port || u.port === '443') ? u.href : null;
      } catch { return null; }
    };
    const imageObservations = [], seenImages = new Set();
    const addImage = (element, origin) => {
      const url = photoUrl(element.currentSrc || element.src);
      if (!url || seenImages.has(url)) return;
      const link = element.closest?.('a[href]');
      if (link) {
        try {
          const target = new URL(link.href, location.href);
          const otherOffer = target.pathname.match(/^\/offer\/(\d+)\.html$/)?.[1];
          if (target.hostname === 'detail.1688.com' && otherOffer && otherOffer !== expected) return;
        } catch { return; }
      }
      seenImages.add(url);
      imageObservations.push({url, origin, visible: visible(element),
        width: element.naturalWidth || null, height: element.naturalHeight || null,
        alt: element.alt || '', evidenceScope: 'current_public_dom_no_load',
        visuallyReviewed: false, productionApproved: false});
    };
    for (const image of document.querySelectorAll('img')) if (visible(image)) addImage(image, 'product_page');
    const roots = [{root: document, inDetail: false}], seenRoots = new Set([document]);
    for (let i = 0; i < roots.length; i++) {
      const {root, inDetail} = roots[i];
      if (inDetail) for (const image of root.querySelectorAll('img')) addImage(image, 'supplier_detail');
      for (const host of root.querySelectorAll('*')) if (host.shadowRoot && !seenRoots.has(host.shadowRoot)) {
        seenRoots.add(host.shadowRoot);
        roots.push({root: host.shadowRoot, inDetail: inDetail || supplierDetailHost(host)});
      }
    }
    return {observedAt: new Date().toISOString(), offerId: expected, url: location.href,
      canonicalUrl, documentUrl: document.URL, title: document.title,
      fullVisibleText, selectedColourNames: selectedColours.map(e => e.text),
      selectedColours, colourButtons, skuRows, attributes, attributeEntries, attributeSections, attributeSummary,
      packagingTables, images: imageObservations.map(e => e.url), imageObservations,
      observationScope: 'currently rendered DOM only; no navigation, scrolling, lazy loading, image requests or SKU selection'};
  }, {expected, canonicalUrl});
  supplierIdentity(result?.url, expected);
  supplierIdentity(await page.url(), expected);
  if (result?.offerId !== expected) throw Error('Supplier observation result offer mismatch');
  return result;
}
