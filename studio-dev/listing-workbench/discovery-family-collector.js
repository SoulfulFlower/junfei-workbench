/* Fixed read-only observer: no click, scroll, navigation, storage, or network.
 * Supports the legacy #twister anchor layout and the observed
 * #softlinesTwister_feature_div color/size inline radio layout. It does not read hidden scripts or infer parent ASINs.
 * Synthetic DOM tests do not establish live marketplace compatibility.
 */
() => {
  'use strict';
  const markets={'amazon.com':'US','amazon.co.uk':'UK','amazon.de':'DE','amazon.fr':'FR','amazon.it':'IT','amazon.es':'ES','amazon.co.jp':'JP','amazon.ca':'CA','amazon.com.au':'AU','amazon.in':'IN','amazon.com.mx':'MX','amazon.com.br':'BR'};
  const base={schemaVersion:1,status:'blocked',reason:'',capturedAt:new Date().toISOString()};
  const blocked=reason=>({...base,reason});
  const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
  const all=(root,selector)=>Array.from(root.querySelectorAll(selector));
  const visible=el=>{
    if(!el || el.nodeType!==1) return false;
    for(let n=el;n && n.nodeType===1;n=n.parentElement){
      const s=getComputedStyle(n);
      if(n.hidden || n.getAttribute('aria-hidden')==='true' || s.display==='none' || ['hidden','collapse'].includes(s.visibility) || Number(s.opacity)===0) return false;
    }
    if(Array.from(el.getClientRects()).some(r=>r.width>0 && r.height>0)) return true;
    return getComputedStyle(el).display==='contents' && all(el,'*').some(visible);
  };
  const text=el=>visible(el)?clean(Array.from(el.childNodes).map(n=>n.nodeType===3?n.textContent:n.nodeType===1?text(n):'').join(' ')):'';
  const any=selector=>all(document,selector).some(visible);
  let page;
  try{page=new URL(location.href);}catch(_){return blocked('invalid_url');}
  const host=page.hostname.replace(/^www\./,'');
  if(page.protocol!=='https:' || page.username || page.password || page.port || !markets[host]) return blocked('unsupported_amazon_host');
  base.marketplace=markets[host];
  if(/\/(?:ap\/|gp\/sign-in|signin)/i.test(page.pathname) || any('#ap_email, #ap_password')) return blocked('login_required');
  if(/captcha|validatecaptcha/i.test(page.pathname) || any('#captchacharacters, form[action*="validateCaptcha"], #challenge-container')) return blocked('captcha_or_challenge');
  if(any('#nav-interstitial, #interstitial, #automatedAccessMessage')) return blocked('access_interstitial');
  if(/sorry, we just need to make sure you.re not a robot|enter the characters you see below|automated access to amazon|access denied|sorry! something went wrong/i.test(clean(document.body && document.body.innerText).slice(0,12000))) return blocked('access_interstitial');
  const parseProduct=(raw,expected)=>{
    if(typeof raw!=='string' || raw.length>4000 || /[\\\u0000-\u0020]/.test(raw.split(/[?#]/,1)[0]) || /\/(?:\.|%2e){1,2}(?:\/|$)/i.test(raw.split(/[?#]/,1)[0])) throw Error('ambiguous_url');
    const u=new URL(raw,page.href), h=u.hostname.replace(/^www\./,'');
    const m=u.pathname.match(/^(?:\/[^/]+\/dp|\/dp|\/gp\/product)\/([A-Z0-9]{10})(?:\/(?:ref=[A-Za-z0-9_.=-]+)?)?$/);
    if(u.protocol!=='https:' || u.username || u.password || u.port || h!==host || u.hash || !m || (expected && m[1]!==expected)) throw Error('product_mismatch');
    if(Array.from(u.searchParams.keys()).some(k=>['asin','seller','sellerid','me','merchant','merchantid','k','q'].includes(k.toLowerCase()))) throw Error('identity_query');
    return {asin:m[1],url:'https://'+host+'/dp/'+m[1]};
  };
  let identity;
  try{identity=parseProduct(location.href);}catch(_){return blocked('not_product_page');}
  base.asin=identity.asin;base.url=identity.url;
  if(all(document,'#productTitle').filter(visible).filter(n=>text(n)).length!==1) return blocked('missing_or_ambiguous_product_title');
  // aria-hidden removes accessibility-tree text, not painted swatch labels.
  // Read only the rendered label tied to a visible radio inside its own button.
  const painted=el=>{
    if(!el || el.nodeType!==1) return false;
    for(let n=el;n && n.nodeType===1;n=n.parentElement){
      const s=getComputedStyle(n);
      if(n.hidden || s.display==='none' || ['hidden','collapse'].includes(s.visibility) || Number(s.opacity)===0) return false;
    }
    return Array.from(el.getClientRects()).some(r=>r.width>0 && r.height>0);
  };
  const paintedText=el=>painted(el)?clean(Array.from(el.childNodes).map(n=>n.nodeType===3?n.textContent:n.nodeType===1?paintedText(n):'').join(' ')):'';
  const hasClass=(el,name)=>(el.getAttribute('class')||'').split(/\s+/).includes(name);
  const inlineRoots=all(document,'#softlinesTwister_feature_div').filter(visible);
  if(inlineRoots.length){
    if(inlineRoots.length!==1) return blocked('missing_or_ambiguous_variant_container');
    const rows=all(inlineRoots[0],'[id^="inline-twister-row-"]').filter(visible);
    if(!rows.length || rows.length>2) return blocked('unsupported_variant_layout');
    const controls=[],rowIds=new Set();
    for(const row of rows){
      const id=row.getAttribute('id');
      if(!['inline-twister-row-color_name','inline-twister-row-size_name'].includes(id) || rowIds.has(id)) return blocked('unsupported_variant_layout');
      rowIds.add(id);
      const items=all(row,'li[data-asin]').filter(visible);
      if(!items.length) return blocked('unsupported_variant_layout');
      let selectedCount=0;
      for(const item of items){
        if(controls.length>=200) return blocked('variant_control_limit');
        const asin=item.getAttribute('data-asin');
        if(!/^[A-Z0-9]{10}$/.test(asin||'')) return blocked('conflicting_or_unsupported_variant_controls');
        // data-csa-c-item-id is a second live identity attribute when present.
        // Cachecolor/initiallyselected are not current selection evidence.
        if(item.getAttribute('data-csa-c-item-id') && item.getAttribute('data-csa-c-item-id')!==asin) return blocked('conflicting_or_unsupported_variant_controls');
        const radios=all(item,'input[role="radio"]').filter(visible);
        if(radios.length!==1 || !['true','false'].includes(radios[0].getAttribute('aria-checked'))) return blocked('conflicting_or_unsupported_variant_controls');
        const radio=radios[0],selected=radio.getAttribute('aria-checked')==='true';
        let button=radio.parentElement;
        while(button && button!==item && !hasClass(button,'a-button')) button=button.parentElement;
        if(!button || button===item || !visible(button) || hasClass(button,'a-button-selected')!==selected) return blocked('conflicting_or_unsupported_variant_controls');
        if(selected){selectedCount++;if(asin!==identity.asin) return blocked('conflicting_or_unsupported_variant_controls');}
        if(radio.getAttribute('data-asin') && radio.getAttribute('data-asin')!==asin) return blocked('conflicting_or_unsupported_variant_controls');
        const labelId=radio.getAttribute('aria-labelledby');
        if(!/^[a-z][a-z0-9_-]{0,100}$/i.test(labelId||'')) return blocked('conflicting_or_unsupported_variant_controls');
        const labels=all(button,'#'+labelId).filter(painted);
        if(labels.length!==1) return blocked('conflicting_or_unsupported_variant_controls');
        const images=all(labels[0],'img[alt]').filter(painted).map(n=>clean(n.getAttribute('alt'))).filter(Boolean);
        const label=images.length===1?images[0]:images.length===0?paintedText(labels[0]):'';
        if(!label || label.length>300) return blocked('conflicting_or_unsupported_variant_controls');
        controls.push({containerId:id,selector:'#'+id+' li[data-asin] input[role="radio"]',source:'visible_inline_twister_radio',asin,dataAsin:asin,href:null,label,selectedMarker:selected?'aria-checked+a-button-selected':''});
      }
      if(selectedCount!==1) return blocked('selected_variant_identity_missing');
    }
    if(new Set(controls.map(c=>c.asin)).size<2) return blocked('no_visible_alternative_variants');
    const keys=controls.map(c=>c.containerId+':'+c.asin);
    if(new Set(keys).size!==keys.length) return blocked('conflicting_or_unsupported_variant_controls');
    return {...base,status:'captured',reason:'visible_variant_controls_observed',selectedAsin:identity.asin,controls:controls.sort((a,b)=>(a.containerId+':'+a.asin).localeCompare(b.containerId+':'+b.asin))};
  }
  const twisters=all(document,'#twister').filter(visible);
  if(twisters.length!==1) return blocked('missing_or_ambiguous_variant_container');
  const containers=all(twisters[0],'[id^="variation_"]').filter(visible);
  if(!containers.length || containers.length>20) return blocked('unsupported_variant_layout');
  const controls=[],containerIds=new Set();
  let invalid=false,scanned=0;
  for(const container of containers){
    const id=container.getAttribute('id');
    if(!/^variation_[a-z0-9_]{1,64}$/.test(id) || containerIds.has(id)){invalid=true;break;}
    containerIds.add(id);
    const items=all(container,'li[data-asin]').filter(visible);
    if(!items.length){invalid=true;break;}
    for(const item of items){
      if(++scanned>200) return blocked('variant_control_limit');
      const asin=item.getAttribute('data-asin');
      if(!/^[A-Z0-9]{10}$/.test(asin||'')){invalid=true;break;}
      const selected=(item.getAttribute('class')||'').split(/\s+/).includes('swatchSelect');
      // Dynamic twister pages may leave old selected markers behind. Every
      // visible checked state must agree; header ARIA and initiallyselected
      // are deliberately never accepted as current identity.
      const checked=[item,...all(item,'[aria-checked]').filter(visible)].map(n=>n.getAttribute('aria-checked')).filter(v=>v!==null);
      if(checked.some(v=>!['true','false'].includes(v) || (v==='true')!==selected)){invalid=true;break;}
      const anchors=all(item,'a[href]').filter(visible);
      if(anchors.length!==1){invalid=true;break;}
      const anchor=anchors[0];
      let target;
      try{target=parseProduct(anchor.getAttribute('href'),asin);}catch(_){invalid=true;break;}
      const imgs=all(anchor,'img[alt]').filter(visible).map(n=>clean(n.getAttribute('alt'))).filter(Boolean);
      const label=text(anchor) || (imgs.length===1?imgs[0]:'');
      if(!label || label.length>300 || (selected && asin!==identity.asin)){invalid=true;break;}
      if(anchor.getAttribute('data-asin') && anchor.getAttribute('data-asin')!==asin){invalid=true;break;}
      controls.push({containerId:id,selector:'#'+id+' li[data-asin] a[href]',source:'visible_twister_anchor',asin,dataAsin:asin,href:target.url,label,selectedMarker:selected?'swatchSelect':''});
    }
    if(invalid) break;
  }
  if(invalid) return blocked('conflicting_or_unsupported_variant_controls');
  if(!controls.some(c=>c.selectedMarker==='swatchSelect')) return blocked('selected_variant_identity_missing');
  if(new Set(controls.map(c=>c.asin)).size<2) return blocked('no_visible_alternative_variants');
  const seen=new Map();
  for(const c of controls){
    const key=c.containerId+':'+c.asin;
    if(seen.has(key) && JSON.stringify(seen.get(key))!==JSON.stringify(c)) return blocked('conflicting_or_unsupported_variant_controls');
    seen.set(key,c);
  }
  return {...base,status:'captured',reason:'visible_variant_controls_observed',selectedAsin:identity.asin,controls:Array.from(seen.values()).sort((a,b)=>(a.containerId+':'+a.asin).localeCompare(b.containerId+':'+b.asin))};
}
