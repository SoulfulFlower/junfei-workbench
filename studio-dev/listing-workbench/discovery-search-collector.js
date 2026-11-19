/* Read-only current keyword-search observation. Only direct organic result
 * cards and the product-title anchor hierarchy observed on Amazon US on
 * 2026-11-06 are supported. Brand headings are excluded. No navigation, network, clicks or storage.
 * Unsupported structures fail closed; this is not independent qualification.
 */
expected => {
  'use strict';
  const markets={'amazon.com':'US','amazon.co.uk':'UK','amazon.de':'DE','amazon.fr':'FR','amazon.it':'IT','amazon.es':'ES','amazon.co.jp':'JP','amazon.ca':'CA','amazon.com.au':'AU','amazon.in':'IN','amazon.com.mx':'MX','amazon.com.br':'BR'};
  const marketIds={US:'ATVPDKIKX0DER',UK:'A1F83G8C2ARO7P',DE:'A1PA6795UKMFR9',FR:'A13V1IB3VIYZZH',IT:'APJ6JRA9NG5V4',ES:'A1RKKUPIHCS9HS',JP:'A1VC38T7YXB528',CA:'A2EUQ1WTGCTBG2',AU:'A39IBJ37TRP1C6',IN:'A21TJRUUN4KGV',MX:'A1AM78C64UM0Y8',BR:'A2Q3Y263D00KWC'};
  const queryKeys=['k','ref','ref_','qid','sprefix','crid','marketplaceID'];
  const conflicts=['me','k','q','seller','sellerid','merchant','merchantid','m','smid','field-keywords','field-merchant','rh','p_6'];
  const selector='.s-main-slot', cardSelector='[data-component-type="s-search-result"][data-asin]', titleSelector='a.a-link-normal.s-link-style > h2.a-text-normal';
  const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
  const base={schemaVersion:1,status:'blocked',capturedAt:new Date().toISOString()};
  const blocked=reason=>({...base,reason});
  const all=(root,sel)=>Array.from(root.querySelectorAll(sel));
  const visible=el=>{
    if(!el || el.nodeType!==1)return false;
    for(let n=el;n && n.nodeType===1;n=n.parentElement){
      const s=getComputedStyle(n);
      if(n.hidden || n.getAttribute('aria-hidden')==='true' || s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || Number(s.opacity)===0)return false;
    }
    if(Array.from(el.getClientRects()).some(r=>r.width>0 && r.height>0))return true;
    return getComputedStyle(el).display==='contents' && all(el,'*').some(visible);
  };
  const text=el=>visible(el)?clean(Array.from(el.childNodes).map(n=>n.nodeType===3?n.textContent:n.nodeType===1?text(n):'').join(' ')):'';
  const anyVisible=sel=>all(document,sel).some(visible);
  const classes=el=>clean(el.getAttribute('class')).split(' ');
  const parseURL=(raw,relative)=>{
    if(typeof raw!=='string' || !raw || /[\\\u0000-\u0020]/.test(raw) || /\/(?:\.|%2e){1,2}(?:\/|$)/i.test(raw.split(/[?#]/,1)[0]))return null;
    try{return relative?new URL(raw,location.href):new URL(raw);}catch(_){return null;}
  };
  const page=parseURL(location.href,false);
  if(!page)return blocked('invalid_url');
  const host=page.hostname.replace(/^www\./,'');
  if(page.protocol!=='https:' || page.username || page.password || page.port || !markets[host])return blocked('unsupported_amazon_host');
  base.marketplace=markets[host];
  if(/\/(?:ap\/|gp\/sign-in|signin)/i.test(page.pathname) || anyVisible('#ap_email, #ap_password'))return blocked('login_required');
  if(/captcha|validatecaptcha/i.test(page.pathname) || anyVisible('#captchacharacters, form[action*="validateCaptcha"], #challenge-container'))return blocked('captcha_or_challenge');
  if(anyVisible('#nav-interstitial, #interstitial, #automatedAccessMessage'))return blocked('access_interstitial');
  const bodyText=clean(document.body && document.body.innerText).slice(0,12000);
  if(/sorry, we just need to make sure you.re not a robot|enter the characters you see below|automated access to amazon|access denied|sorry! something went wrong/i.test(bodyText))return blocked('access_interstitial');
  if(!expected || typeof expected.query!=='string' || !expected.query.trim() || expected.query.length>300 || expected.marketplace!==base.marketplace)return blocked('search_target_mismatch');
  const pairs=[...page.searchParams.entries()], keywords=pairs.filter(([k])=>k.toLowerCase()==='k');
  const sameMarket=pairs=>{
    const ids=pairs.filter(([k])=>k.toLowerCase()==='marketplaceid');
    return !ids.length || (ids.length===1 && ids[0][0]==='marketplaceID' && ids[0][1]===marketIds[base.marketplace]);
  };
  if(page.pathname!=='/s' || keywords.length!==1 || keywords[0][0]!=='k' || pairs.some(([k])=>!queryKeys.includes(k)) || !sameMarket(pairs))return blocked('not_keyword_search');
  if(keywords[0][1]!==expected.query)return blocked('search_target_mismatch');
  base.query=expected.query;
  base.url='https://'+host+'/s?'+new URLSearchParams({k:base.query}).toString();
  const roots=all(document,selector).filter(visible);
  if(roots.length!==1)return blocked('missing_or_ambiguous_results');
  const root=roots[0];
  // Direct main-result children only. Nested carousels and recommendations are
  // deliberately excluded even when they reuse a result-card component.
  const cards=all(root,cardSelector).filter(c=>c.parentElement===root && visible(c));
  if(cards.length>1000)return blocked('unsupported_search_layout');
  const products=[], evidence=[], seen=new Set();
  for(const card of cards){
    const sponsored=classes(card).some(c=>/^(?:AdHolder|s-sponsored-result)$/i.test(c)) || card.getAttribute('data-sponsored')!==null ||
      all(card,'.puis-sponsored-label-text, .s-sponsored-label-info-icon, [data-component-type="sp-sponsored-result"], [data-cel-widget*="sp-sponsored"]').some(visible) ||
      /(?:^|\s)(?:Sponsored|Gesponsert|Sponsorisé|Sponsorizzato|Patrocinado)(?:\s|$)|スポンサー/i.test(text(card)) ||
      all(card,'a[href]').filter(visible).some(a=>/\/(?:sspa\/click|gp\/slredirect|slredirect)(?:[/?]|$)/i.test(a.getAttribute('href')||''));
    if(sponsored)continue;
    if(all(card,cardSelector+', .a-carousel-container, [data-component-type="recommendations"], [data-component-type="s-product-carousel"]').some(visible))return blocked('invalid_or_ambiguous_product_card');
    const asin=card.getAttribute('data-asin');
    const headings=all(card,'h2').filter(visible);
    // A separate brand h2 is not a product title. Only h2 directly inside the
    // observed product-title anchor may contribute title text.
    const titles=headings.filter(h=>{const a=h.parentElement;return classes(h).includes('a-text-normal') && a && a.tagName==='A' && visible(a) && classes(a).includes('a-link-normal') && classes(a).includes('s-link-style');});
    if(!/^[A-Z0-9]{10}$/.test(asin||'') || titles.length!==1)return blocked('invalid_or_ambiguous_product_card');
    const heading=titles[0], title=text(heading), anchor=heading.parentElement;
    // Only the observed product-title link hierarchy. Never fall back to brand
    // bylines, image alt text, price links or accessibility-only title strings.
    if(!title || title.length>2000 || !classes(heading).includes('a-text-normal') || !anchor || anchor.tagName!=='A' || !visible(anchor) || !classes(anchor).includes('a-link-normal') || !classes(anchor).includes('s-link-style'))return blocked('invalid_or_ambiguous_product_card');
    const link=parseURL(anchor.getAttribute('href'),true);
    if(!link)return blocked('invalid_or_ambiguous_product_card');
    const product=link.pathname.match(/^(?:\/(?:[^/]+)\/dp|\/dp|\/gp\/product)\/([A-Za-z0-9]{10})(?:\/.*)?$/);
    const q=[...link.searchParams.entries()];
    if(link.protocol!=='https:' || link.username || link.password || link.port || link.hostname.replace(/^www\./,'')!==host || !product || product[1].toUpperCase()!==asin || q.some(([k])=>conflicts.includes(k.toLowerCase())) || !sameMarket(q))return blocked('invalid_or_ambiguous_product_card');
    if(seen.has(asin))return blocked('invalid_or_ambiguous_product_card');
    seen.add(asin);
    const productURL='https://'+host+'/dp/'+asin;
    products.push({asin,title,productURL});
    evidence.push({asin,cardAsin:asin,title,anchorHref:productURL,cardSelector,titleSelector,directMainSlot:true,visible:true,sponsored:false});
    if(products.length===50)break;
  }
  // Without a separately verified zero-results layout, an empty or delayed
  // main slot cannot establish zero matches. No inference from body text.
  if(!products.length)return blocked('no_visible_search_products');
  return {...base,status:'captured',reason:'visible_keyword_search_observed',products,evidence:{selector,sourceURL:base.url,query:base.query,marketplace:base.marketplace,capturedAt:base.capturedAt,cards:evidence}};
}
