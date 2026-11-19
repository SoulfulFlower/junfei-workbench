/* Read-only DOM observation. Evaluate this expression, then invoke it in the page.
 * No network, navigation, clicks, storage, or inferred brand-to-seller mapping.
 * Unsupported layouts fail closed. URLs retain only the public seller identity.
 */
() => {
  'use strict';
  const markets = {'amazon.com':'US','amazon.co.uk':'UK','amazon.de':'DE','amazon.fr':'FR','amazon.it':'IT','amazon.es':'ES','amazon.co.jp':'JP','amazon.ca':'CA','amazon.com.au':'AU','amazon.in':'IN','amazon.com.mx':'MX','amazon.com.br':'BR'};
  const labels = {US:['Sold by'],UK:['Sold by'],DE:['Sold by','Verkauf durch'],FR:['Sold by','Vendu par'],IT:['Sold by','Venduto da'],ES:['Sold by','Vendido por'],JP:['Sold by','販売元'],CA:['Sold by','Vendu par'],AU:['Sold by'],IN:['Sold by'],MX:['Sold by','Vendido por'],BR:['Sold by','Vendido por']};
  const clean = s => String(s || '').replace(/\s+/g,' ').trim();
  const base = {schemaVersion:1,status:'blocked',reason:'',capturedAt:new Date().toISOString()};
  const blocked = reason => ({...base,reason});
  const visible = el => {
    if (!el || el.nodeType !== 1) return false;
    for (let n=el;n && n.nodeType===1;n=n.parentElement) {
      const s=getComputedStyle(n);
      if (n.hidden || n.getAttribute('aria-hidden')==='true' || s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || Number(s.opacity)===0) return false;
    }
    if (Array.from(el.getClientRects()).some(r=>r.width>0 && r.height>0)) return true;
    // display:contents has no box of its own. Only this structural case may
    // borrow visibility from descendants; ordinary zero-box elements stay out.
    return getComputedStyle(el).display==='contents' && Array.from(el.querySelectorAll('*')).some(visible);
  };
  const text = el => {
    if (!visible(el)) return '';
    return clean(Array.from(el.childNodes).map(n=>n.nodeType===3?n.textContent:n.nodeType===1?text(n):'').join(' '));
  };
  const all = (root,selector) => Array.from(root.querySelectorAll(selector));
  const anyVisible = selector => all(document,selector).some(visible);
  let page;
  try { page=new URL(location.href); } catch (_) {return blocked('invalid_url');}
  const host=page.hostname.replace(/^www\./,'');
  if (page.protocol!=='https:' || page.username || page.password || page.port || !markets[host]) return blocked('unsupported_amazon_host');
  base.marketplace=markets[host];
  if (/\/(?:ap\/|gp\/sign-in|signin)/i.test(page.pathname) || anyVisible('#ap_email, #ap_password')) return blocked('login_required');
  if (/captcha|validatecaptcha/i.test(page.pathname) || anyVisible('#captchacharacters, form[action*="validateCaptcha"], #challenge-container')) return blocked('captcha_or_challenge');
  if (anyVisible('#nav-interstitial, #interstitial, #automatedAccessMessage')) return blocked('access_interstitial');
  const bodyText=clean(document.body && document.body.innerText).slice(0,12000);
  if (/sorry, we just need to make sure you.re not a robot|enter the characters you see below|automated access to amazon|access denied|sorry! something went wrong/i.test(bodyText)) return blocked('access_interstitial');
  const product=page.pathname.match(/^(?:\/(?:[^/]+)\/dp|\/dp|\/gp\/product)\/([A-Z0-9]{10})(?:\/.*)?$/i);
  if (!product) return blocked('not_product_page');
  base.asin=product[1].toUpperCase();
  base.url='https://www.'+host+'/dp/'+base.asin;
  const titles=all(document,'#productTitle').filter(visible).map(text).filter(Boolean);
  if (titles.length!==1) return blocked('missing_or_ambiguous_product_title');
  base.title=titles[0].slice(0,2000);
  const acceptedLabels=labels[base.marketplace];
  // This combined label has only been observed in the US explicit merchant row.
  const isLabel=t=>(base.marketplace==='US' && clean(t)==='Shipper / Seller') || acceptedLabels.some(l=>clean(t).replace(/[:：]$/,'').toLowerCase()===l.toLowerCase());
  const candidates=[];
  let invalid=false;
  const add=(anchor,selector,labelText) => {
    if (!visible(anchor)) return;
    const name=text(anchor), raw=anchor.getAttribute('href');
    if (!name || !raw) {invalid=true;return;}
    // URL() normalizes dot segments and backslashes; reject them before parsing
    // so a traversal cannot masquerade as an allowlisted seller-profile path.
    const rawPath=raw.split(/[?#]/,1)[0];
    if (/[\\\u0000-\u0020]/.test(rawPath) || /\/(?:\.|%2e){1,2}(?:\/|$)/i.test(rawPath)) {invalid=true;return;}
    let link;
    try {link=new URL(raw,page.href);} catch (_) {invalid=true;return;}
    const params=Array.from(link.searchParams.entries());
    const sellerParams=params.filter(([k])=>k.toLowerCase()==='seller');
    const seller=sellerParams.length===1?sellerParams[0][1]:'';
    if (link.protocol!=='https:' || link.username || link.password || link.port || link.hostname.replace(/^www\./,'')!==host || !['/sp','/gp/help/seller/at-a-glance.html','/gp/help/seller/at-a-glance.html/ref=dp_merchant_link'].includes(link.pathname) || sellerParams.length!==1 || sellerParams[0][0]!=='seller' || !/^[A-Z0-9]{5,30}$/.test(seller) || params.some(([k])=>['me','merchant','merchantid','sellerid'].includes(k.toLowerCase()))) {invalid=true;return;}
    if (['data-seller-id','data-merchant-id'].some(k=>anchor.getAttribute(k) && anchor.getAttribute(k)!==seller)) {invalid=true;return;}
    // Preserve the observed path and host, but strip every non-identity query field.
    const safe=link.origin+link.pathname+'?seller='+seller;
    candidates.push({sellerId:seller,sellerName:name.slice(0,300),sellerLabel:clean(labelText).slice(0,2000),sellerLink:safe,sellerLinkSource:'visible_sold_by_link',evidence:{selector,labelText:clean(labelText).slice(0,2000),anchorText:name.slice(0,300),anchorHref:safe}});
  };
  // Amazon's explicit merchant row: a separate visible label and seller value.
  const rowSelector='#merchantInfoFeature_feature_div, [offer-display-feature-name="merchantInfo"], .offer-display-feature-merchant-info';
  for (const row of all(document,rowSelector).filter(visible)) {
    const labelNodes=all(row,'.a-span3, .offer-display-feature-label, .a-color-secondary').filter(n=>visible(n)&&isLabel(text(n)));
    if (!labelNodes.length) continue;
    for (const a of all(row,'a[href]').filter(visible)) add(a,rowSelector,text(row));
  }
  // Legacy layout must explicitly say Sold by immediately before the anchor.
  for (const row of all(document,'#merchant-info').filter(visible)) {
    for (const a of all(row,'a[href]').filter(visible)) {
      const before=[];
      let found=false;
      const walk=n=>{
        if (found) return;
        if (n===a) {found=true;return;}
        if (n.nodeType===3) before.push(n.textContent);
        else if (n.nodeType===1 && visible(n)) Array.from(n.childNodes).forEach(walk);
      };
      walk(row);
      const prefix=clean(before.join(' '));
      const suffix=prefix.toLowerCase().replace(/[:：]$/,'').trim();
      if (acceptedLabels.some(l=>suffix===l.toLowerCase() || suffix.endsWith(' '+l.toLowerCase()))) add(a,'#merchant-info',text(row));
    }
  }
  if (invalid) return blocked('invalid_or_ambiguous_seller_link');
  if (!candidates.length) return blocked('visible_sold_by_link_not_found');
  if (new Set(candidates.map(c=>c.sellerId)).size!==1 || new Set(candidates.map(c=>c.sellerName)).size!==1) return blocked('conflicting_seller_evidence');
  return {...base,...candidates[0],status:'captured',reason:'visible_sold_by_link_observed'};
}
