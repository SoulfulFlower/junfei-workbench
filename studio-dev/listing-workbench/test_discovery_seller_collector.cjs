'use strict';
// Offline, dependency-free contract tests. The fake DOM is deliberately small;
// these do not establish compatibility with a live Amazon page or browser.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'discovery-seller-collector.js'),'utf8');
class Element {
  constructor(tag,attrs={},children=[]) {
    this.nodeType=1;this.tag=tag;this.attrs=attrs;this.hidden=!!attrs.hidden;this.style=attrs.style||{};
    this.childNodes=children.map(c=>typeof c==='string'?{nodeType:3,textContent:c}:c);
    this.childNodes.forEach(c=>{c.parentElement=this;});
  }
  getAttribute(k){return this.attrs[k]??null;}
  getClientRects(){return this.attrs.zero?[]:[{width:100,height:20}];}
  get innerText(){return this.childNodes.map(c=>c.nodeType===3?c.textContent:c.innerText).join(' ');}
  matches(s){
    if(s==='*') return true;
    if(s.startsWith('#')) return this.attrs.id===s.slice(1);
    if(s.startsWith('.')) return (this.attrs.class||'').split(' ').includes(s.slice(1));
    if(s==='a[href]') return this.tag==='a' && 'href' in this.attrs;
    if(s==='form[action*="validateCaptcha"]') return this.tag==='form' && (this.attrs.action||'').includes('validateCaptcha');
    if(s==='[offer-display-feature-name="merchantInfo"]') return this.attrs['offer-display-feature-name']==='merchantInfo';
    return false;
  }
  querySelectorAll(s){const selectors=s.split(',').map(x=>x.trim()),out=[];const walk=n=>{for(const c of n.childNodes||[]) if(c.nodeType===1){if(selectors.some(s=>c.matches(s)))out.push(c);walk(c);}};walk(this);return out;}
}
const el=(tag,attrs,...children)=>new Element(tag,attrs,children);
const anchor=(href='/sp?seller=A12345',name='Same Brand',attrs={})=>el('a',{href,...attrs},name);
const row=(a=anchor(),label='Sold by',attrs={})=>el('div',{id:'merchantInfoFeature_feature_div',...attrs},el('span',{class:'a-span3'},label),a);
function capture({url='https://www.amazon.com/dp/B012345678?auth=secret',rows=[row()],title='A product',extras=[]}={}) {
  const body=el('body',{},...(title===null?[]:[el('span',{id:'productTitle'},title)]),...rows,...extras);
  const document=el('document',{},body);document.body=body;
  return JSON.parse(JSON.stringify(vm.runInNewContext('('+source+')()',{
    document,location:{href:url},URL,Date,getComputedStyle:n=>({display:'block',visibility:'visible',opacity:'1',...n.style})
  },{timeout:1000})));
}
const test=require('node:test');
function blocked(options,reason){const r=capture(options);assert.equal(r.status,'blocked');if(reason)assert.equal(r.reason,reason);return r;}
test('visible merchant row, same brand name accepted, URL query removed',()=>{const r=capture();assert.equal(r.status,'captured');assert.equal(r.sellerName,'Same Brand');assert.equal(r.sellerId,'A12345');assert.equal(r.url,'https://www.amazon.com/dp/B012345678');assert.equal(r.marketplace,'US');assert.ok(!JSON.stringify(r).includes('secret'));assert.ok(!Number.isNaN(Date.parse(r.capturedAt)));});
test('gp/product URL normalized',()=>assert.equal(capture({url:'https://amazon.com/gp/product/B012345678/ref=abc'}).url,'https://www.amazon.com/dp/B012345678'));
test('title slug dp URL normalized',()=>assert.equal(capture({url:'https://amazon.com/Product-Name/dp/B012345678/'}).status,'captured'));
test('legacy labeled merchant anchor',()=>assert.equal(capture({rows:[el('div',{id:'merchant-info'},'Ships from Amazon. Sold by ',anchor())]}).status,'captured'));
test('legacy unrelated anchor after seller ignored',()=>assert.equal(capture({rows:[el('div',{id:'merchant-info'},'Sold by ',anchor(),' and ',anchor('/help','returns'))]}).status,'captured'));
test('hidden anchor',()=>blocked({rows:[row(anchor(undefined,undefined,{hidden:true}))]}));
test('hidden ancestor',()=>blocked({rows:[row(anchor(),'Sold by',{style:{display:'none'}})]}));
test('aria hidden',()=>blocked({rows:[row(anchor(undefined,undefined,{'aria-hidden':'true'}))]}));
test('zero bounds',()=>blocked({rows:[row(anchor(undefined,undefined,{zero:true}))]}));
test('display contents merchant row uses visible descendants and text',()=>{
  const r=capture({rows:[row(anchor(),'Shipper / Seller',{zero:true,style:{display:'contents'}})]});
  assert.equal(r.status,'captured');assert.equal(r.evidence.labelText,'Shipper / Seller Same Brand');
});
test('display contents nested structure can expose visible seller',()=>{
  const r=capture({rows:[row(el('div',{zero:true,style:{display:'contents'}},anchor()),'Sold by',{zero:true,style:{display:'contents'}})]});
  assert.equal(r.status,'captured');assert.equal(r.evidence.labelText,'Sold by Same Brand');
});
for(const attrs of [{hidden:true},{'aria-hidden':'true'},{style:{display:'contents',opacity:'0'}},{style:{display:'contents',visibility:'hidden'}}]) test('hidden display contents row rejected '+JSON.stringify(attrs),()=>blocked({rows:[row(anchor(),'Sold by',{zero:true,style:{display:'contents'},...attrs})]}));
test('ordinary zero-rect merchant row not rescued by visible descendants',()=>blocked({rows:[row(anchor(),'Sold by',{zero:true})]}));
test('display contents hidden ancestor still excludes seller',()=>blocked({rows:[el('div',{hidden:true},row(anchor(),'Sold by',{zero:true,style:{display:'contents'}}))]}));
test('display contents row ignores hidden duplicate seller anchors',()=>{
  const seller=anchor(undefined,undefined,{id:'sellerProfileTriggerId'});
  const r=capture({rows:[row(el('div',{},seller,anchor('/sp?seller=A99999','Same Brand',{id:'sellerProfileTriggerId',zero:true}),anchor('/sp?seller=A88888','Hidden',{hidden:true})),'Shipper / Seller',{zero:true,style:{display:'contents'}})]});
  assert.equal(r.status,'captured');assert.equal(r.sellerId,'A12345');assert.equal(r.evidence.labelText,'Shipper / Seller Same Brand');
});
test('display contents row with only hidden descendants stays blocked',()=>blocked({rows:[el('div',{id:'merchantInfoFeature_feature_div',zero:true,style:{display:'contents'}},el('span',{class:'a-span3',hidden:true},'Sold by'),anchor(undefined,undefined,{hidden:true}))]}));
test('transparent ancestor',()=>blocked({rows:[row(anchor(),'Sold by',{style:{opacity:'0'}})]}));
test('brand link is not seller',()=>blocked({rows:[el('div',{id:'bylineInfo'},anchor('/sp?seller=A12345'))]}));
test('ships from label rejected',()=>blocked({rows:[row(anchor(),'Ships from')]}));
test('observed US Shipper / Seller row and exact profile suffix accepted',()=>{
  const href='https://www.amazon.com/gp/help/seller/at-a-glance.html/ref=dp_merchant_link?seller=AP474B2KSJ0QL';
  const r=capture({url:'https://www.amazon.com/dp/B0HQC8H1K5',rows:[row(anchor(href,'pbnNwa',{id:'sellerProfileTriggerId'}),'Shipper / Seller')]});
  assert.equal(r.status,'captured');assert.equal(r.sellerId,'AP474B2KSJ0QL');assert.equal(r.sellerName,'pbnNwa');assert.equal(r.sellerLink,href);assert.equal(r.evidence.anchorHref,href);assert.equal(r.evidence.labelText,'Shipper / Seller pbnNwa');
});
test('combined label remains US only',()=>blocked({url:'https://www.amazon.co.uk/dp/B012345678',rows:[row(anchor(),'Shipper / Seller')]}));
for(const label of ['Shipper','Seller','Ships from / Seller','Shipper / Seller services','Not Shipper / Seller','Shipper/Seller']) test('nonexact combined label rejected '+label,()=>blocked({rows:[row(anchor(),label)]}));
test('hidden combined label rejected',()=>blocked({rows:[el('div',{id:'merchantInfoFeature_feature_div'},el('span',{class:'a-span3',hidden:true},'Shipper / Seller'),anchor())]}));
test('combined label not enabled in legacy layout',()=>blocked({rows:[el('div',{id:'merchant-info'},'Shipper / Seller ',anchor())]}));
test('observed suffix retains only seller identity',()=>{
  const r=capture({rows:[row(anchor('/gp/help/seller/at-a-glance.html/ref=dp_merchant_link?seller=A12345&token=secret#private'))]});
  assert.equal(r.status,'captured');assert.equal(r.evidence.anchorHref,'https://www.amazon.com/gp/help/seller/at-a-glance.html/ref=dp_merchant_link?seller=A12345');
});
for(const path of [
  '/gp/help/seller/at-a-glance.html/ref=evil',
  '/gp/help/seller/at-a-glance.html/ref=dp_merchant_link/extra',
  '/gp/help/seller/at-a-glance.html/ref=dp_merchant_link.evil',
  '/gp/help/seller/at-a-glance.html/redirect',
  '/sp/ref=dp_merchant_link',
  '/gp/help/seller/at-a-glance.html/extra/../ref=dp_merchant_link',
  '/gp/help/seller/at-a-glance.html/extra/%2e%2e/ref=dp_merchant_link',
  '/gp/help/seller/at-a-glance.html/extra/.%2E/ref=dp_merchant_link',
  '/gp/help/seller/at-a-glance.html/./ref=dp_merchant_link',
  '/gp/help/seller/at-a-glance.html/extra/..\\ref=dp_merchant_link',
  '/evil/../sp'
]) test('unobserved or traversal profile path rejected '+path,()=>blocked({rows:[row(anchor(path+'?seller=A12345'))]},'invalid_or_ambiguous_seller_link'));
test('fulfilled by label rejected',()=>blocked({rows:[row(anchor(),'Fulfilled by')]}));
test('generic merchant name rejected',()=>blocked({rows:[el('div',{id:'merchant-info'},anchor())]}));
test('legacy label substring rejected',()=>blocked({rows:[el('div',{id:'merchant-info'},'Unsold by ',anchor())]}));
test('inconsistent explicit seller identity rejected',()=>blocked({rows:[row(anchor(undefined,undefined,{'data-seller-id':'A99999'}))]},'invalid_or_ambiguous_seller_link'));
test('hidden sold by label rejected',()=>blocked({rows:[el('div',{id:'merchantInfoFeature_feature_div'},el('span',{class:'a-span3',hidden:true},'Sold by'),anchor())]}));
test('search card rejected',()=>blocked({rows:[el('div',{'data-component-type':'s-search-result'},'Sold by ',anchor())]}));
test('conflicting visible seller IDs',()=>blocked({rows:[row(),row(anchor('/sp?seller=A99999'))]},'conflicting_seller_evidence'));
test('conflicting names rejected',()=>blocked({rows:[row(),row(anchor(undefined,'Other'))]},'conflicting_seller_evidence'));
test('same duplicate evidence accepted',()=>assert.equal(capture({rows:[row(),row()]}).status,'captured'));
for(const query of ['seller=A12345&seller=A12345','seller=A12345&seller=A99999','seller=A12345&Seller=A12345','seller=A12345&me=A99999','seller=','seller=bad!']) test('invalid seller query '+query,()=>blocked({rows:[row(anchor('/sp?'+query))]},'invalid_or_ambiguous_seller_link'));
for(const host of ['amazon.com.evil.test','evilamazon.com','sellercentral.amazon.com','amazon.cn']) test('host rejected '+host,()=>blocked({url:'https://'+host+'/dp/B012345678'},'unsupported_amazon_host'));
test('HTTP page rejected',()=>blocked({url:'http://amazon.com/dp/B012345678'}));
test('credential URL rejected without leaking credentials',()=>{assert.ok(!JSON.stringify(blocked({url:'https://private:secret@amazon.com/dp/B012345678'})).includes('private'));});
test('wrong product URL rejected',()=>blocked({url:'https://amazon.com/s?k=product'},'not_product_page'));
test('bad ASIN rejected',()=>blocked({url:'https://amazon.com/dp/SHORT'}));
test('missing title',()=>blocked({title:null},'missing_or_ambiguous_product_title'));
for(const href of ['https://amazon.de/sp?seller=A12345','https://amazon.com.evil.test/sp?seller=A12345','http://amazon.com/sp?seller=A12345','/stores/SameBrand?seller=A12345','/sp?seller=A12345#x'].slice(0,4)) test('invalid seller destination '+href,()=>blocked({rows:[row(anchor(href))]}));
test('seller path and identity retained, all other query and hash removed',()=>{const r=capture({rows:[row(anchor('/gp/help/seller/at-a-glance.html?seller=A12345&token=secret#private'))]});assert.equal(r.evidence.anchorHref,'https://www.amazon.com/gp/help/seller/at-a-glance.html?seller=A12345');assert.ok(!JSON.stringify(r).includes('secret'));});
test('captcha control blocks',()=>blocked({extras:[el('input',{id:'captchacharacters'})]},'captcha_or_challenge'));
test('login blocks',()=>blocked({url:'https://amazon.com/ap/signin?token=secret'},'login_required'));
test('access denial blocks',()=>blocked({extras:[el('div',{},'Access Denied')]},'access_interstitial'));
test('interstitial control blocks',()=>blocked({extras:[el('div',{id:'interstitial'})]},'access_interstitial'));
test('unsupported locale label on US rejected',()=>blocked({rows:[row(anchor(),'Vendu par')]}));
const locales=[['amazon.com','US','Sold by'],['amazon.co.uk','UK','Sold by'],['amazon.de','DE','Verkauf durch'],['amazon.fr','FR','Vendu par'],['amazon.it','IT','Venduto da'],['amazon.es','ES','Vendido por'],['amazon.co.jp','JP','販売元'],['amazon.ca','CA','Vendu par'],['amazon.com.au','AU','Sold by'],['amazon.in','IN','Sold by'],['amazon.com.mx','MX','Vendido por'],['amazon.com.br','BR','Vendido por']];
for(const [host,market,label] of locales)test('market '+market,()=>{const r=capture({url:'https://www.'+host+'/dp/B012345678',rows:[row(anchor(),label)]});assert.equal(r.status,'captured');assert.equal(r.marketplace,market);});
test('plain JSON serializable contract',()=>{const r=capture();assert.deepEqual(Object.keys(r).sort(),['schemaVersion','status','reason','capturedAt','marketplace','asin','url','title','sellerId','sellerName','sellerLabel','sellerLink','sellerLinkSource','evidence'].sort());assert.equal(r.schemaVersion,1);assert.equal(r.sellerLinkSource,'visible_sold_by_link');});

