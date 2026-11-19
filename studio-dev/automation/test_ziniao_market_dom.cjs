// Execute the production browser IIFE against the actual observed menu markup.
// Python only parses AST/HTML; no business module, browser or network is loaded.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const path=require('node:path'),{spawnSync}=require('node:child_process');
// Minimal excerpt of research-e2e-20261117/real-market-menu-03.json. Retains
// the observed header, menu hierarchy, seller boundary and exact country rows.
const observedMarkup=String.raw`<div class="dropdown-account-switcher account-switcher-root">
 <div class="dropdown-account-switcher-header dropdown-account-switcher-header-expanded" role="button" tabindex="0" aria-expanded="true">
  <div class="dropdown-account-switcher-header-label"><span class="dropdown-account-switcher-header-label-global">Example Store</span><span class="dropdown-account-switcher-header-label-divider"></span><span class="dropdown-account-switcher-header-label-regional dropdown-account-switcher-header-label-regional-child">德国</span></div>
 </div>
 <div class="dropdown-account-switcher-list-pointer-area"><div class="dropdown-account-switcher-list-arrow"></div><div class="dropdown-account-switcher-list"><div class="dropdown-account-switcher-list-content-wrapper">
  <div class="dropdown-account-switcher-list-header">切换账户</div><div class="dropdown-account-switcher-list-scrollable">
   <div class="dropdown-account-switcher-list-item" tabindex="0" title="Example Store"><span class="core-icon-normal dropdown-account-switcher-list-item-icon dropdown-account-switcher-list-item-icon-expanded"></span><div class="dropdown-account-switcher-list-item-label dropdown-account-switcher-list-item-label-expanded">Example Store</div></div>
   <div class="dropdown-account-switcher-list-item dropdown-account-switcher-list-item-indented" tabindex="0" title="美国"><img src="https://d1uznvntk80v7s.cloudfront.net/flags/us.svg" class="kat-flag dropdown-account-switcher-list-item-country-flag" alt="" aria-hidden="true" data-test="country-flag-US"><div class="dropdown-account-switcher-list-item-label">美国</div></div>
   <div class="dropdown-account-switcher-list-item dropdown-account-switcher-list-item-indented" tabindex="0" title="英国"><img src="https://d1uznvntk80v7s.cloudfront.net/flags/gb.svg" class="kat-flag dropdown-account-switcher-list-item-country-flag" alt="" aria-hidden="true" data-test="country-flag-GB"><div class="dropdown-account-switcher-list-item-label">英国</div></div>
   <div class="dropdown-account-switcher-list-item dropdown-account-switcher-list-item-indented" tabindex="0" title="德国"><img src="https://d1uznvntk80v7s.cloudfront.net/flags/de.svg" class="kat-flag dropdown-account-switcher-list-item-country-flag" alt="" aria-hidden="true" data-test="country-flag-DE"><div class="dropdown-account-switcher-list-item-label">德国</div><span class="core-icon-normal dropdown-account-switcher-list-item-selected-icon"></span></div>
  </div><a class="dropdown-account-switcher-list-item dropdown-account-switcher-list-see-all" href="/account-switcher/default/merchantMarketplace?returnTo=%2Famazonsell%2Fbusiness">查看所有账户</a>
 </div></div></div>
</div>`;
const extract=String.raw`
import ast,json,sys
from html.parser import HTMLParser
from pathlib import Path
tree=ast.parse(Path(sys.argv[1]).read_text(encoding='utf-8'))
script=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MARKET_CLICK_SCRIPT' for t in node.targets))
class MenuParser(HTMLParser):
 def __init__(self):
  super().__init__();self.root={'tag':'document','attrs':{},'children':[]};self.stack=[self.root]
 def handle_starttag(self,tag,attrs):
  node={'tag':tag,'attrs':dict(attrs),'children':[]};self.stack[-1]['children'].append(node)
  if tag not in ('img','input','br','hr','meta','link'):self.stack.append(node)
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i]['tag']==tag:self.stack=self.stack[:i];break
 def handle_data(self,data):self.stack[-1]['children'].append(data)
p=MenuParser();p.feed(sys.argv[2])
print(json.dumps({'script':script,'dom':p.root},ensure_ascii=False))
`;
const parsed=spawnSync(process.env.PYTHON||'python',['-X','utf8','-c',extract,
 path.join(__dirname,'ziniao_market.py'),observedMarkup],{encoding:'utf8'});
assert.equal(parsed.status,0,parsed.stderr);
const production=JSON.parse(parsed.stdout),base={seller:'Example Store',country:'英国',flag:'GB',origin:'https://sellercentral.amazon.co.uk'};

function matchesCompound(element,selector){
 if(selector===':scope')return true;
 let rest=selector;
 const tag=rest.match(/^[a-z][a-z0-9-]*/i);if(tag){if(element.tagName.toLowerCase()!==tag[0].toLowerCase())return false;rest=rest.slice(tag[0].length);}
 while(rest){
  const cls=rest.match(/^\.([\w-]+)/);if(cls){if(!element.classList.contains(cls[1]))return false;rest=rest.slice(cls[0].length);continue;}
  const attr=rest.match(/^\[([\w-]+)(?:="([^"]*)")?\]/);if(attr){if(!element.hasAttribute(attr[1])||(attr[2]!==undefined&&element.getAttribute(attr[1])!==attr[2]))return false;rest=rest.slice(attr[0].length);continue;}
  throw Error('Fixture does not support unobserved selector syntax: '+selector);
 }
 return true;
}
function selectorMatches(element,selector){
 const parts=selector.trim().split(/\s+(?=(?:[^"]*"[^"]*")*[^"]*$)/),last=parts.pop();
 if(!matchesCompound(element,last))return false;
 for(let i=parts.length-1,parent=element.parentElement;i>=0;i--){
  while(parent&&!matchesCompound(parent,parts[i]))parent=parent.parentElement;
  if(!parent)return false;parent=parent.parentElement;
 }
 return true;
}
class Element{
 constructor(node,parent,fixture){this.tagName=node.tag.toUpperCase();this.attrs={...node.attrs};this.parentElement=parent;this.fixture=fixture;this.style={display:'block',visibility:'visible'};this.rect={x:100,y:80,width:280,height:24};this.clicks=0;this.scrolls=0;this.nodes=node.children.map(child=>typeof child==='string'?child:new Element(child,this,fixture));}
 get children(){return this.nodes.filter(node=>node instanceof Element);}
 get previousElementSibling(){const siblings=this.parentElement?.children||[],index=siblings.indexOf(this);return index>0?siblings[index-1]:null;}
 get classList(){return{contains:name=>(this.attrs.class||'').split(/\s+/).includes(name)};}
 get innerText(){return this.nodes.map(child=>typeof child==='string'?child:child.innerText).join(' ').replace(/\s+/g,' ').trim();}
 set innerText(value){this.nodes=[String(value)];}
 get textContent(){return this.innerText;}
 get disabled(){return this.hasAttribute('disabled');}
 set disabled(value){if(value)this.attrs.disabled='';else delete this.attrs.disabled;}
 getAttribute(name){return Object.hasOwn(this.attrs,name)?this.attrs[name]:null;}
 hasAttribute(name){return Object.hasOwn(this.attrs,name);}
 setAttribute(name,value){this.attrs[name]=String(value);}
 removeAttribute(name){delete this.attrs[name];}
 querySelectorAll(selector){const alternatives=selector.split(',').map(s=>s.trim()),found=[];const visit=node=>{for(const child of node.children){if(alternatives.some(part=>selectorMatches(child,part)))found.push(child);visit(child);}};visit(this);return found;}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 closest(selector){for(let element=this;element;element=element.parentElement)if(selectorMatches(element,selector))return element;return null;}
 contains(target){for(let element=target;element;element=element.parentElement)if(element===this)return true;return false;}
 getBoundingClientRect(){for(let element=this;element;element=element.parentElement)if(element.style.display==='none')return{...this.rect,width:0,height:0};return{...this.rect};}
 scrollIntoView(){this.scrolls++;this.fixture.hitTarget=this;}
 click(){this.clicks++;this.fixture.clicked.push(this);}
}
function fixture(){
 const f={clicked:[],hitTarget:null,overlay:false,offscreen:false};
 f.document=new Element(production.dom,null,f);f.root=f.document.querySelector('.dropdown-account-switcher.account-switcher-root');
 f.header=f.root.querySelector('.dropdown-account-switcher-header');f.global=f.header.querySelector('.dropdown-account-switcher-header-label-global');
 f.region=f.header.querySelector('.dropdown-account-switcher-header-label-regional');
 f.rows=f.root.querySelectorAll('.dropdown-account-switcher-list-item');f.uk=f.rows.find(row=>row.getAttribute('title')==='英国');
 f.owner=f.rows.find(row=>row.getAttribute('title')==='Example Store');
 f.flag=f.uk.querySelector('img[data-test="country-flag-GB"]');
 assert.ok(f.root&&f.header&&f.global&&f.uk&&f.owner&&f.flag,'fixture must derive the real observed UK row and seller');
 f.document.elementFromPoint=()=>f.overlay?{}:f.hitTarget;
 Object.defineProperty(f.document,'cookie',{get(){throw Error('script must not read cookies');}});
 const window={};for(const name of ['localStorage','sessionStorage'])Object.defineProperty(window,name,{get(){throw Error('script must not read '+name);}});
 f.context={document:f.document,window,location:{origin:base.origin},innerWidth:1280,innerHeight:900,
  getComputedStyle:element=>element.style};
 f.run=(action='inspect',changes={})=>JSON.parse(vm.runInNewContext(production.script.replace('__MARKET_CONFIG__',JSON.stringify({...base,action,...changes})),f.context,{timeout:1000}));
 return f;
}
function refused(change,reason,action='click'){
 const f=fixture();change(f);const result=f.run(action);
 assert.equal(result.ok,false,JSON.stringify(result));if(reason)assert.equal(result.reason,reason);
 assert.equal(f.clicked.length,0,'guard rejection must not click any control');return result;
}

test('actual production script inspects the real Example Store UK row and clicks only that row once',()=>{
 const f=fixture(),inspected=f.run();assert.equal(inspected.ok,true);assert.equal(inspected.stage,'ready');assert.equal(inspected.clicked,false);
 assert.equal(inspected.selector,'.dropdown-account-switcher.account-switcher-root .dropdown-account-switcher-list-item[title="英国"]');
 assert.equal(f.clicked.length,0);assert.equal(f.uk.scrolls,1);
 const clicked=f.run('click');assert.equal(clicked.stage,'market_click_requested');assert.equal(clicked.clicked,true);
 assert.equal(f.clicked.length,1);assert.equal(f.clicked[0],f.uk);assert.equal(f.uk.clicks,1);assert.equal(f.header.clicks,0);
});

test('opening a closed unique header clicks once and an already open menu is a no-op',()=>{
 const f=fixture();f.header.setAttribute('aria-expanded','false');
 assert.equal(f.run().stage,'menu_closed');assert.equal(f.clicked.length,0);
 assert.equal(f.run('open').stage,'menu_open_requested');assert.equal(f.header.clicks,1);assert.equal(f.uk.clicks,0);
 f.header.setAttribute('aria-expanded','true');assert.equal(f.run('open').stage,'already_open');assert.equal(f.header.clicks,1);
});

test('already selected UK is an identity-checked no-op',()=>{
 const f=fixture();f.region.innerText='英国';assert.equal(f.run('click').stage,'already_selected');assert.equal(f.clicked.length,0);
});

test('wrong domain, authentication fields and wrong seller reject before input',()=>{
 refused(f=>f.context.location.origin='https://sellercentral.amazon.de','origin_changed');
 refused(f=>f.document.nodes.push(new Element({tag:'input',attrs:{type:'password'},children:[]},f.document,f)),'authentication_required');
 refused(f=>f.global.innerText='Other Seller','seller_mismatch');
 refused(f=>f.owner.innerText='Other Seller','seller_mismatch');
 refused(f=>f.owner.setAttribute('title','Other Seller'),'seller_mismatch');
});

test('ambiguous visible roots headers and UK candidates never trigger a click',()=>{
 refused(f=>f.document.nodes.push(new Element(production.dom.children[0],f.document,f)),'ambiguous_header');
 refused(f=>f.root.nodes.push(new Element({tag:'div',attrs:{class:'dropdown-account-switcher-header'},children:['Example Store 德国']},f.root,f)),'ambiguous_header');
 refused(f=>{const clone=new Element({tag:'div',attrs:{...f.uk.attrs},children:['英国']},f.uk.parentElement,f);f.uk.parentElement.nodes.push(clone);},'ambiguous_market');
});

test('disabled hidden unregistered or structurally changed market rows refuse input',()=>{
 refused(f=>f.uk.disabled=true,'market_disabled_or_changed');
 refused(f=>f.uk.setAttribute('aria-disabled','true'),'market_disabled_or_changed');
 refused(f=>f.uk.setAttribute('inert',''),'market_disabled_or_changed');
 refused(f=>f.uk.style.display='none','ambiguous_market');
 refused(f=>f.uk.setAttribute('aria-hidden','true'),'ambiguous_market');
 refused(f=>f.uk.setAttribute('class','dropdown-account-switcher-list-item'),'market_disabled_or_changed');
 refused(f=>f.uk.nodes.push('（待注册）'),'market_disabled_or_changed');
 refused(f=>f.flag.setAttribute('data-test','country-flag-US'),'flag_mismatch');
 refused(f=>f.uk.nodes.push(new Element({tag:'img',attrs:{'data-test':'country-flag-GB'},children:[]},f.uk,f)),'flag_mismatch');
});

test('nearest same-level seller boundary must be Example Store rather than another expanded account',()=>{
 refused(f=>{const parent=f.uk.parentElement,index=parent.nodes.indexOf(f.uk);parent.nodes.splice(index,0,new Element({tag:'div',attrs:{class:'dropdown-account-switcher-list-item',title:'Other Seller'},children:['Other Seller']},parent,f));},'seller_mismatch');
});

test('overlays offscreen controls and disabled headers reject instead of bypassing hit testing',()=>{
 refused(f=>f.overlay=true,'obscured');
 refused(f=>f.uk.rect.x=1300,'obscured');
 refused(f=>f.header.setAttribute('aria-disabled','true'),'header_disabled');
 refused(f=>f.header.setAttribute('role','link'),'header_disabled');
 refused(f=>f.header.setAttribute('aria-expanded','unknown'),'header_changed');
 refused(f=>{f.header.setAttribute('aria-expanded','false');f.overlay=true;},'obscured','open');
});
