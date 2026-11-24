// Dependency-free pure DOM tests. These do not run a browser or prove all
// Amazon layouts. The accepted hierarchy is based on the recorded US page.
'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), test=require('node:test');
const source=fs.readFileSync(require('node:path').join(__dirname,'discovery-store-collector.js'),'utf8');
class Element{
  constructor(tag,attrs={},children=[]){this.nodeType=1;this.tagName=tag.toUpperCase();this.attrs=attrs;this.hidden=!!attrs.hidden;this.style=attrs.style||{};this.childNodes=children.map(c=>typeof c==='string'?{nodeType:3,textContent:c}:c);this.childNodes.forEach(c=>c.parentElement=this);}
  getAttribute(k){return this.attrs[k]??null;}
  getClientRects(){return this.attrs.zero?[]:[{width:100,height:20}];}
  get innerText(){return this.childNodes.map(c=>c.nodeType===3?c.textContent:c.innerText).join(' ');}
  matches(s){
    if(s==='*')return true;
    let rest=s;const tag=rest.match(/^[a-z][a-z0-9]*/i);if(tag){if(this.tagName!==tag[0].toUpperCase())return false;rest=rest.slice(tag[0].length);}
    while(rest){
      const token=rest.match(/^(?:([.#])([\w-]+)|\[([\w-]+)(?:(\*?=)"([^"]*)")?\])/);if(!token)throw Error('unsupported fixture selector '+s);
      if(token[1]==='#' && this.attrs.id!==token[2])return false;
      if(token[1]==='.' && !(this.attrs.class||'').split(' ').includes(token[2]))return false;
      if(token[3]){const value=this.getAttribute(token[3]);if(value===null || (token[4]==='=' && value!==token[5]) || (token[4]==='*=' && !value.includes(token[5])))return false;}
      rest=rest.slice(token[0].length);
    }
    return true;
  }
  querySelectorAll(sel){const selectors=sel.split(',').map(s=>s.trim()),out=[];const walk=n=>{for(const c of n.childNodes||[])if(c.nodeType===1){if(selectors.some(s=>c.matches(s)))out.push(c);walk(c);}};walk(this);return out;}
}
const el=(tag,attrs,...children)=>new Element(tag,attrs,children);
const heading=(title='A visible product',attrs={})=>el('h2',{class:'a-size-medium a-text-normal',...attrs},title);
const link=(title='A visible product',href='/Title/dp/B012345678/ref=sr_1_1?m=SELLER1&marketplaceID=ATVPDKIKX0DER&token=SECRET',attrs={})=>el('a',{class:'a-link-normal s-line-clamp-3 s-link-style a-text-normal',href,...attrs},heading(title));
const card=({asin='B012345678',title='A visible product',href,attrs={},children}={})=>el('div',{'data-component-type':'s-search-result','data-asin':asin,...attrs},...(children||[link(title,href)]));
const main=(...cards)=>el('div',{class:'s-main-slot s-result-list s-search-results sg-row'},...cards);
function capture({url='https://www.amazon.com/s?me=SELLER1&marketplaceID=ATVPDKIKX0DER&token=SECRET#private',expected={sellerId:'SELLER1',marketplace:'US'},cards=[card()],roots,extras=[]}={}){
  const body=el('body',{},...(roots||[main(...cards)]),...extras),document=el('document',{},body);document.body=body;
  return JSON.parse(JSON.stringify(vm.runInNewContext('('+source+')(expected)',{document,location:{href:url},URL,Date,expected,getComputedStyle:n=>({display:'block',visibility:'visible',opacity:'1',...n.style})},{timeout:1000})));
}
function blocked(options,reason){const r=capture(options);assert.equal(r.status,'blocked');assert.equal(r.products,undefined);if(reason)assert.equal(r.reason,reason);return r;}
test('observed title-link hierarchy, minimal canonical source and card evidence',()=>{
  const r=capture();assert.equal(r.status,'captured');assert.equal(r.marketplace,'US');assert.equal(r.sellerId,'SELLER1');assert.equal(r.url,'https://amazon.com/s?me=SELLER1');assert.deepEqual(r.products,[{asin:'B012345678',title:'A visible product',productURL:'https://amazon.com/dp/B012345678'}]);assert.equal(r.evidence.cards[0].anchorHref,r.products[0].productURL);assert.equal(r.evidence.sourceURL,r.url);assert.equal(r.evidence.capturedAt,r.capturedAt);assert.ok(!JSON.stringify(r).includes('SECRET'));assert.ok(!Number.isNaN(Date.parse(r.capturedAt)));
});
test('recorded live US first-card values accepted',()=>{const title="Women'S Open Front Ruffle Peplum Jean Jackets Lapel Double Breasted Lightweight Casual Fall Trendy Vintage Denim Jacket";const r=capture({url:'https://www.amazon.com/s?me=AP474B2KSJ0QL&marketplaceID=ATVPDKIKX0DER',expected:{sellerId:'AP474B2KSJ0QL',marketplace:'US'},cards:[card({asin:'B0HJVJJP8T',title,href:'/Cropped-Jackets-Breasted-Lightweight-Vintage/dp/B0HJVJJP8T/ref=sr_1_1?m=AP474B2KSJ0QL&marketplaceID=ATVPDKIKX0DER&s=merchant-items'})]});assert.equal(r.status,'captured');assert.equal(r.products[0].title,title);});
for(const url of ['http://amazon.com/s?me=SELLER1','https://amazon.com.evil.test/s?me=SELLER1','https://sellercentral.amazon.com/s?me=SELLER1','https://secret:private@amazon.com/s?me=SELLER1','https://amazon.com:444/s?me=SELLER1'])test('wrong origin rejected '+url,()=>blocked({url}));
for(const path of ['/stores/Brand','/sp','/s/','/dp/B012345678','/evil/../s','/evil/%2e%2e/s','/s\\'])test('not a seller listing '+path,()=>blocked({url:'https://amazon.com'+path+'?me=SELLER1'}));
for(const query of ['k=goods','me=SELLER1&me=SELLER1','me=SELLER1&me=OTHER1','ME=SELLER1','me=SELLER1&ME=SELLER1','me=SELLER1&%6de=OTHER1','me=SELLER1&seller=SELLER1','me=SELLER1&Seller=OTHER1','me=SELLER1&merchantid=OTHER1','me=SELLER1&m=OTHER1','me=SELLER1&smid=OTHER1','me=SELLER1&k=goods','me=SELLER1&rh=p_6:OTHER1','me=SELLER1&marketplaceID=A1F83G8C2ARO7P','me=SELLER1&marketplaceID=ATVPDKIKX0DER&marketplaceID=ATVPDKIKX0DER','me=SELLER1&marketplaceid=ATVPDKIKX0DER'])test('duplicate/conflicting identifying parameters rejected '+query,()=>blocked({url:'https://amazon.com/s?'+query},'not_seller_listing'));
test('wrong seller rejected',()=>blocked({url:'https://amazon.com/s?me=OTHER1'},'store_target_mismatch'));
for(const expected of [null,{}, {sellerId:'SELLER1',marketplace:'UK'},{sellerId:'bad',marketplace:'US'}])test('invalid expected target '+JSON.stringify(expected),()=>blocked({expected},'store_target_mismatch'));
test('login page blocked',()=>blocked({url:'https://amazon.com/ap/signin'},'login_required'));
test('login element blocked',()=>blocked({extras:[el('input',{id:'ap_email'})]},'login_required'));
test('captcha blocked',()=>blocked({extras:[el('input',{id:'captchacharacters'})]},'captcha_or_challenge'));
test('access denied blocked',()=>blocked({extras:[el('div',{},'Access Denied')]},'access_interstitial'));
test('interstitial blocked',()=>blocked({extras:[el('div',{id:'interstitial'})]},'access_interstitial'));
test('missing main slot blocked',()=>blocked({roots:[]},'missing_or_ambiguous_results'));
test('ambiguous main slots blocked',()=>blocked({roots:[main(card()),main(card())]},'missing_or_ambiguous_results'));
test('empty listing reports blocked, never nonexistent seller',()=>{const r=blocked({cards:[]},'no_visible_store_products');assert.equal(r.sellerId,'SELLER1');});
for(const attrs of [{hidden:true},{'aria-hidden':'true'},{style:{display:'none'}},{style:{visibility:'hidden'}},{style:{opacity:'0'}},{zero:true}])test('invisible card excluded '+JSON.stringify(attrs),()=>blocked({cards:[card({attrs})]},'no_visible_store_products'));
test('hidden main slot excluded',()=>{const r=main(card());r.hidden=true;blocked({roots:[r]},'missing_or_ambiguous_results');});
test('display contents main slot supported',()=>{const r=main(card());r.attrs.zero=true;r.style.display='contents';assert.equal(capture({roots:[r]}).status,'captured');});
test('ordinary zero-bounds main slot not rescued',()=>{const r=main(card());r.attrs.zero=true;blocked({roots:[r]},'missing_or_ambiguous_results');});
test('recommendation carousels and outside cards do not enter',()=>{const nested=el('div',{'data-component-type':'recommendations'},card({asin:'B012345679',href:'/dp/B012345679'}));const r=capture({cards:[card(),nested],extras:[card({asin:'B012345679',href:'/dp/B012345679'})]});assert.equal(r.products.length,1);assert.equal(r.products[0].asin,'B012345678');});
for(const sponsored of [card({attrs:{class:'AdHolder'}}),card({attrs:{'data-sponsored':'true'}}),card({children:[link(),el('span',{class:'puis-sponsored-label-text'},'Sponsored')]}),card({children:[link(),el('span',{},'Sponsored')]}),card({children:[link(),el('a',{href:'/sspa/click?url=/dp/B012345678'},'ad')]}),card({children:[link(),el('span',{'data-component-type':'sp-sponsored-result'},'ad')]})])test('marked sponsored cards excluded '+JSON.stringify(sponsored.attrs),()=>{const r=capture({cards:[sponsored,card({asin:'B012345679',href:'/dp/B012345679'})]});assert.equal(r.status,'captured');assert.equal(r.products.length,1);assert.equal(r.products[0].asin,'B012345679');});
test('only sponsored cards produce no-products block',()=>blocked({cards:[card({attrs:{class:'AdHolder'}})]},'no_visible_store_products'));
for(const attrs of [{hidden:true},{zero:true},{style:{opacity:'0'}}])test('hidden title not replaced by brand '+JSON.stringify(attrs),()=>blocked({cards:[card({children:[el('span',{},'Brand text'),el('a',{href:'/dp/B012345678',class:'a-link-normal s-link-style'},heading('Hidden',attrs))]})]},'invalid_or_ambiguous_product_card'));
test('brand link is never product title',()=>blocked({cards:[card({href:'/stores/Brand/page/ABC'})]},'invalid_or_ambiguous_product_card'));
test('brand and image-only card not inferred',()=>blocked({cards:[card({children:[el('span',{},'Brand'),el('img',{alt:'Invented product'})]})]},'invalid_or_ambiguous_product_card'));
test('wrong title hierarchy not supported',()=>blocked({cards:[card({children:[el('h2',{},el('a',{href:'/dp/B012345678'},'Title'))]})]},'invalid_or_ambiguous_product_card'));
test('ambiguous visible headings block batch',()=>blocked({cards:[card({children:[link(),link('Another')]})]},'invalid_or_ambiguous_product_card'));
test('hidden duplicate title ignored',()=>{const a=link('Hidden');a.hidden=true;assert.equal(capture({cards:[card({children:[link(),a]})]}).status,'captured');});
test('hidden title text omitted',()=>{const a=link('');a.childNodes[0].childNodes=[{nodeType:3,textContent:'Visible'},el('span',{hidden:true},'SECRET')];a.childNodes[0].childNodes.forEach(c=>c.parentElement=a.childNodes[0]);const r=capture({cards:[card({children:[a]})]});assert.equal(r.products[0].title,'Visible');assert.ok(!JSON.stringify(r).includes('SECRET'));});
for(const href of ['/dp/B012345679','https://amazon.de/dp/B012345678','https://evil.test/dp/B012345678','http://amazon.com/dp/B012345678','https://secret:private@amazon.com/dp/B012345678','/dp/B012345678?m=OTHER1','/dp/B012345678?m=SELLER1&m=SELLER1','/dp/B012345678?M=SELLER1','/dp/B012345678?me=SELLER1','/dp/B012345678?marketplaceID=A1F83G8C2ARO7P','/dp/B012345678?marketplaceID=ATVPDKIKX0DER&marketplaceID=ATVPDKIKX0DER','/dp/B012345678?seller=OTHER1','/evil/../dp/B012345678'])test('bad card link rejected '+href,()=>blocked({cards:[card({href})]},'invalid_or_ambiguous_product_card'));
for(const asin of ['SHORT','b012345678','BAD!345678',''])test('invalid data ASIN '+asin,()=>blocked({cards:[card({asin})]},'invalid_or_ambiguous_product_card'));
test('duplicate visible ASIN rejected',()=>blocked({cards:[card(),card()]},'invalid_or_ambiguous_product_card'));
test('long and blank titles rejected',()=>{blocked({cards:[card({title:'x'.repeat(2001)})]});blocked({cards:[card({title:'   '})]});});
test('bounded to fifty actual cards',()=>{const cards=Array.from({length:51},(_,i)=>{const asin='B'+String(i).padStart(9,'0');return card({asin,href:'/dp/'+asin,title:'Product '+i});});const r=capture({cards});assert.equal(r.status,'captured');assert.equal(r.products.length,50);assert.equal(r.evidence.cards.length,50);});
test('UK same hierarchy supported without claiming live UK validation',()=>{const r=capture({url:'https://www.amazon.co.uk/s?me=SELLER1&marketplaceID=A1F83G8C2ARO7P',expected:{sellerId:'SELLER1',marketplace:'UK'},cards:[card({href:'/dp/B012345678?marketplaceID=A1F83G8C2ARO7P'})]});assert.equal(r.status,'captured');assert.equal(r.marketplace,'UK');assert.equal(r.products[0].productURL,'https://amazon.co.uk/dp/B012345678');});
test('source contains no browser mutation or unbounded network operation',()=>{for(const forbidden of ['.click(','.goto(','.reload(','fetch(','localStorage','sessionStorage','document.cookie','XMLHttpRequest'])assert.ok(!source.includes(forbidden),forbidden);});
