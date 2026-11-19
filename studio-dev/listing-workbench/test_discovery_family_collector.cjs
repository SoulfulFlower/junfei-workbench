'use strict';
// Offline minimal DOM fixtures, not a live Amazon compatibility claim.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const test=require('node:test'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'discovery-family-collector.js'),'utf8');
const A='B000000001',B='B000000002',C='B000000003';
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
    if(s==='*')return true;
    if(s.startsWith('#'))return this.attrs.id===s.slice(1);
    if(s==='[id^="inline-twister-row-"]')return (this.attrs.id||'').startsWith('inline-twister-row-');
    if(s==='input[role="radio"]')return this.tag==='input' && this.attrs.role==='radio';
    if(s==='[id^="variation_"]')return (this.attrs.id||'').startsWith('variation_');
    if(s==='li[data-asin]')return this.tag==='li' && 'data-asin' in this.attrs;
    if(s==='a[href]')return this.tag==='a' && 'href' in this.attrs;
    if(s==='img[alt]')return this.tag==='img' && 'alt' in this.attrs;
    if(s==='[aria-checked]')return 'aria-checked' in this.attrs;
    if(s==='form[action*="validateCaptcha"]')return this.tag==='form' && (this.attrs.action||'').includes('validateCaptcha');
    return false;
  }
  querySelectorAll(s){const selectors=s.split(',').map(s=>s.trim()),out=[];const walk=n=>{for(const c of n.childNodes||[])if(c.nodeType===1){if(selectors.some(s=>c.matches(s)))out.push(c);walk(c);}};walk(this);return out;}
}
const el=(tag,attrs,...children)=>new Element(tag,attrs,children);
function item(asin,selected=false,attrs={},anchorAttrs={},label=asin) {
  return el('li',{'data-asin':asin,class:selected?'swatchSelect':'',...attrs},el('a',{href:'/dp/'+asin,...anchorAttrs},label));
}
function capture({url='https://amazon.com/dp/'+A,items=[item(A,true),item(B)],containerAttrs={},twisterAttrs={},extras=[],title=true,twister=true}={}) {
  const body=el('body',{},...(title?[el('span',{id:'productTitle'},'Example product')]:[]),...(twister?[el('div',{id:'twister',...twisterAttrs},el('div',{id:'variation_color_name',...containerAttrs},...items))]:[]),...extras);
  const doc=el('document',{},body);doc.body=body;
  return JSON.parse(JSON.stringify(vm.runInNewContext('('+source+')()',{
    document:doc,location:{href:url},URL,Date,
    getComputedStyle:n=>({display:(n.attrs.class||'').split(/\s+/).includes('aok-hidden')?'none':'block',visibility:'visible',opacity:'1',...n.style})
  },{timeout:1000})));
}
function blocked(options,reason){const result=capture(options);assert.equal(result.status,'blocked');if(reason)assert.equal(result.reason,reason);return result;}
test('fixed visible selected identity and two swatch anchors',()=>{const r=capture();assert.equal(r.status,'captured');assert.equal(r.selectedAsin,A);assert.equal(r.controls.length,2);assert.equal(r.controls[0].source,'visible_twister_anchor');assert.equal(r.controls[0].selector,'#variation_color_name li[data-asin] a[href]');assert.equal(r.controls[0].selectedMarker,'swatchSelect');assert.ok(!Object.hasOwn(r,'parentAsin'));});
test('image-only option has visible alt label',()=>{const r=capture({items:[item(A,true),item(B,false,{}, {},el('img',{alt:'Blue'}))]});assert.equal(r.status,'captured');assert.equal(r.controls[1].label,'Blue');});
test('tracking and twister suffix stripped without parent inference',()=>{const r=capture({url:'https://amazon.com/dp/'+A+'?secret=do-not-keep',items:[item(A,true),item(B,false,{}, {href:'/dp/'+B+'/ref=twister_B099999999?psc=1'})]});assert.equal(r.status,'captured');assert.ok(!JSON.stringify(r).includes('do-not-keep'));assert.ok(!JSON.stringify(r).includes('B099999999'));});
test('one-sided snapshot merely records controls without claiming family',()=>{const r=capture();assert.equal(r.status,'captured');assert.equal(r.dedupEligible,undefined);assert.equal(r.verified,undefined);});
for(const attrs of [{hidden:true},{'aria-hidden':'true'},{style:{opacity:'0'}},{style:{display:'none'}},{style:{visibility:'hidden'}},{zero:true}])test('hidden or zero-box selected option is not identity '+JSON.stringify(attrs),()=>blocked({items:[item(A,true,attrs),item(B)]}));
test('display contents containers can be visible through real children',()=>assert.equal(capture({containerAttrs:{zero:true,style:{display:'contents'}}}).status,'captured'));
test('hidden ancestor cannot be rescued',()=>blocked({twisterAttrs:{hidden:true}}));
test('href disagrees with data-ASIN',()=>blocked({items:[item(A,true),item(B,false,{}, {href:'/dp/'+C})]},'conflicting_or_unsupported_variant_controls'));
test('anchor data-ASIN disagrees',()=>blocked({items:[item(A,true),item(B,false,{}, {'data-asin':C})]}));
test('selected marker conflicts with page identity',()=>blocked({items:[item(A,true),item(B,true)]}));
test('page URL update with stale selected marker fails closed',()=>blocked({url:'https://amazon.com/dp/'+B}));
test('initiallyselected is not current selection',()=>blocked({items:[item(A,false,{'data-initiallyselected':'true'}),item(B)]},'selected_variant_identity_missing'));
test('header ARIA selection claim is not current selection',()=>blocked({items:[item(A),item(B)],containerAttrs:{'aria-label':'Selected Color is Green'}}));
test('aria-checked on selected li must agree',()=>blocked({items:[item(A,true,{'aria-checked':'false'}),item(B)]}));
test('aria-checked on unselected option must agree',()=>blocked({items:[item(A,true),item(B,false,{}, {'aria-checked':'true'})]}));
test('matching aria-checked corroborates selected marker',()=>assert.equal(capture({items:[item(A,true,{'aria-checked':'true'}),item(B,false,{}, {'aria-checked':'false'})]}).status,'captured'));
test('aria-checked alone is unsupported rather than trusted',()=>blocked({items:[item(A,false,{'aria-checked':'true'}),item(B)]}));
test('no controls and outside twister recommendations fail closed',()=>blocked({items:[],extras:[el('div',{id:'recommendations'},item(A,true),item(B))]}));
test('multiple visible twisters fail closed',()=>blocked({extras:[el('div',{id:'twister'},el('div',{id:'variation_size_name'},item(A,true),item(B)))]}));
test('missing product title fails closed',()=>blocked({title:false}));
test('multiple option anchors are ambiguous',()=>blocked({items:[item(A,true),el('li',{'data-asin':B},el('a',{href:'/dp/'+B},'B'),el('a',{href:'/dp/'+B},'More'))]}));
test('different selected marker on duplicate option fails closed',()=>blocked({items:[item(A,true),item(A),item(B)]}));
test('no alternative target fails closed',()=>blocked({items:[item(A,true)]},'no_visible_alternative_variants'));
test('oversized controls fail closed rather than truncate',()=>blocked({items:[item(A,true),...Array.from({length:200},()=>item(B))]},'variant_control_limit'));
test('oversized label fails closed',()=>blocked({items:[item(A,true),item(B,false,{}, {},'x'.repeat(301))]}));
for(const href of ['https://evil.test/dp/'+B,'https://amazon.co.uk/dp/'+B,'http://amazon.com/dp/'+B,'https://user:pass@amazon.com/dp/'+B,'/x/../dp/'+B,'/%2e%2e/dp/'+B,'/dp/'+B+'?asin='+B,'/dp/'+B+'#private'])test('malformed or cross-market href rejected '+href,()=>blocked({items:[item(A,true),item(B,false,{}, {href})]}));
test('captcha visible blocks',()=>blocked({extras:[el('input',{id:'captchacharacters'})]},'captcha_or_challenge'));
test('login visible blocks',()=>blocked({extras:[el('input',{id:'ap_password'})]},'login_required'));
test('access error blocks',()=>blocked({extras:[el('div',{},'Access denied')]},'access_interstitial'));
test('collector contains no execution or persistence APIs',()=>assert.ok(!/\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage)\b|\.click\(|\.scrollIntoView\(|location\.(?:assign|replace)\(/.test(source)));

function radioItem(asin,selected,label,kind='color',changes={}){
  const id=kind+'_'+asin+'-announce';
  return el('li',{'data-asin':asin,'data-csa-c-item-id':asin,...changes.li},
    el('span',{class:'a-button a-button-toggle'+(selected?' a-button-selected':''),...changes.button},
      el('span',{class:'a-button-inner'},
        el('input',{role:'radio','aria-checked':selected?'true':'false','aria-labelledby':id,...changes.radio}),
        el('span',{id,'aria-hidden':'true'},kind==='color'?el('img',{alt:label}):label))));
}
function inlineCapture({color=[radioItem(A,true,'Green'),radioItem(B,false,'Blue')],size=[radioItem(A,true,'Medium','size'),radioItem(C,false,'Large','size')],...options}={}){
  return capture({...options,twister:false,extras:[el('div',{id:'softlinesTwister_feature_div'},
    el('div',{id:'inline-twister-row-color_name'},...color),
    el('div',{id:'inline-twister-row-size_name'},...size)),...(options.extras||[])]});
}
test('observed inline radios retain null href and real radio source',()=>{const r=inlineCapture();assert.equal(r.status,'captured');assert.equal(r.controls.length,4);assert.ok(r.controls.every(c=>c.href===null));assert.ok(r.controls.every(c=>c.source==='visible_inline_twister_radio'));assert.equal(r.controls[0].selector,'#inline-twister-row-color_name li[data-asin] input[role="radio"]');assert.equal(r.controls[0].selectedMarker,'aria-checked+a-button-selected');assert.equal(r.controls[0].label,'Green');assert.equal(r.controls[2].label,'Medium');});
test('inline radio plus selected CSS must agree',()=>assert.equal(inlineCapture({color:[radioItem(A,true,'Green','color',{button:{class:'a-button'}}),radioItem(B,false,'Blue')]}).status,'blocked'));
test('inline checked ASIN must agree across dimensions and URL',()=>assert.equal(inlineCapture({size:[radioItem(B,true,'Medium','size'),radioItem(C,false,'Large','size')]}).status,'blocked'));
test('inline CSA item ID contradiction is not ignored',()=>assert.equal(inlineCapture({color:[radioItem(A,true,'Green','color',{li:{'data-csa-c-item-id':B}}),radioItem(B,false,'Blue')]}).status,'blocked'));
test('every visible inline dimension must show one current selection',()=>assert.equal(inlineCapture({size:[radioItem(A,false,'Medium','size'),radioItem(C,false,'Large','size')]}).status,'blocked'));
test('hidden duplicated fallback radio ignored',()=>{const x=radioItem(A,true,'Green');x.childNodes.push(el('span',{class:'a-button aok-hidden'},el('input',{role:'radio','aria-checked':'true'})));x.childNodes[x.childNodes.length-1].parentElement=x;assert.equal(inlineCapture({color:[x,radioItem(B,false,'Blue')]}).status,'captured');});
test('inline stale initiallyselected flag is never selection evidence',()=>{const x=radioItem(A,true,'Green','color',{li:{'data-initiallyselected':'false'}});assert.equal(inlineCapture({color:[x,radioItem(B,false,'Blue','color',{li:{'data-initiallyselected':'true'}})]}).status,'captured');});
// Minimal HTML fixture parser for stored real li.outerHTML. No scripts execute.
function parseFixtureHTML(html){
  const root=el('fixture',{}),stack=[root],voidTags=new Set(['input','img','hr','br','meta','link']);
  const tokens=html.match(/<!--[^]*?-->|<[^>]+>|[^<]+/g)||[];
  for(const token of tokens){
    if(token.startsWith('<!--'))continue;
    if(token.startsWith('</')){if(stack.length>1)stack.pop();continue;}
    if(token.startsWith('<')){
      const match=token.match(/^<([a-z0-9-]+)([^]*)>$/i);if(!match)continue;
      const attrs={};for(const a of match[2].matchAll(/([a-z0-9_:-]+)(?:="([^"]*)"|='([^']*)')?/gi))attrs[a[1]]=a[2]??a[3]??'';
      const node=el(match[1].toLowerCase(),attrs);node.parentElement=stack.at(-1);stack.at(-1).childNodes.push(node);
      if(!voidTags.has(node.tag)&&!token.endsWith('/>'))stack.push(node);
    }else{stack.at(-1).childNodes.push({nodeType:3,textContent:token,parentElement:stack.at(-1)});}
  }
  return root.childNodes.filter(n=>n.nodeType===1);
}
for(const [file,expected] of [['12-candidate-fresh-load.json','captured'],['15-bridge-fresh-controls.json','captured'],['08-green-medium-after-timeout.json','blocked'],['10-blue-medium-transition.json','blocked']]){
  const fixture=path.join(__dirname,'..','outputs','variant-evidence-20261106',file);
  test('actual saved control HTML '+file,{skip:!fs.existsSync(fixture)},()=>{
    const raw=JSON.parse(fs.readFileSync(fixture,'utf8').replace(/^\uFEFF/,''));
    const rows=raw.rows.map(row=>el('div',{id:row.id},...row.options.flatMap(option=>parseFixtureHTML(option.html))));
    const result=capture({url:raw.url,twister:false,extras:[el('div',{id:'softlinesTwister_feature_div'},...rows)]});
    assert.equal(result.status,expected,result.reason);
    if(expected==='captured'){assert.ok(result.controls.every(c=>c.href===null));assert.equal(result.selectedAsin,new URL(raw.url).pathname.split('/').at(-1));}
  });
}
