// Self-contained: Chrome serializes this function into the active result page.
function collect1688SearchPage() {
  const visible = element => !!element && element.getClientRects().length > 0;
  const compact = value => String(value || '').trim().replace(/\s+/g, ' ');
  const offers = [], seen = new Set();
  const cards = [...document.querySelectorAll('[data-tracker="offer"][data-renderkey]')].filter(visible);
  const anchors = [...document.querySelectorAll('a[href*="/offer/"]')].filter(visible);
  for (const entry of [...cards, ...anchors]) {
    const renderKey = entry.getAttribute('data-renderkey') || '';
    const cardId = (renderKey.match(/_(\d{8,20})$/) || [])[1];
    let offerId = cardId;
    let href = '';
    if (cardId) {
      href = 'https://detail.1688.com/offer/' + cardId + '.html';
    } else {
      try {
        const url = new URL(entry.href);
        if (url.protocol !== 'https:' || url.hostname !== 'detail.1688.com' || url.username || url.password) continue;
        offerId = (url.pathname.match(/^\/offer\/(\d{8,20})\.html$/) || [])[1];
        href = url.href;
      } catch { continue; }
    }
    if (!offerId || seen.has(offerId)) continue;
    let card = cardId ? entry : entry.closest('[data-offer-id],tr,[class*="offer"],[class*="Offer"],[class*="item"],[class*="Item"],[class*="product"],[class*="Product"]') || entry.parentElement;
    if (!cardId) for (let i = 0; i < 3 && card?.parentElement && compact(card.innerText).length < 60; i++) card = card.parentElement;
    const titleNode = card?.querySelector('[class*="titleText"]');
    const title = compact(titleNode?.innerText || entry.innerText || entry.getAttribute('title')).slice(0, 160);
    const text = compact(card?.innerText || entry.innerText).slice(0, 250);
    const image = [...(card?.querySelectorAll('img') || [])].find(visible);
    const imageUrl = image?.currentSrc || image?.src || '';
    const priceNode = card?.querySelector('[class*="priceItem"]');
    const priceSource = priceNode ? compact(priceNode.innerText).replace(/\s+/g, '') : text;
    const priceText = (priceSource.match(/[¥￥]\s*[\d,.]+(?:\s*[-~至]\s*[¥￥]?\s*[\d,.]+)?/) || [])[0] || '';
    const supplierNode = card?.querySelector('[class*="shopName"]');
    const supplierText = compact(supplierNode?.innerText || [...(card?.querySelectorAll('a') || [])]
      .find(a => visible(a) && !/offer\/\d+\.html/.test(a.href))?.innerText).slice(0, 100);
    if (title && text) {
      offers.push({offerId, title, url: href, imageUrl, priceText, supplierText, text});
      seen.add(offerId);
    }
    if (offers.length >= 6) break;
  }
  const imageMarker = [...document.querySelectorAll('h1,h2,h3,[role=heading],[aria-selected=true]')]
    .some(e => visible(e) && /(以图搜款|图片搜索|相似商品|找同款)/.test(compact(e.innerText)));
  return {url: location.href, offers, imageMarker,
    noMoreRelated: document.body.innerText.includes('没有更多相关商品了')};
}
