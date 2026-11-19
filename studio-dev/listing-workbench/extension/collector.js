(async()=>{
const visible=el=>!!(el.getClientRects().length)&&getComputedStyle(el).visibility!=='hidden';
const pageTitle=document.title.replace(/\s*-\s*阿里巴巴.*$/,'').trim();
const title=pageTitle.length>10&&!/登录|验证码/.test(pageTitle)?pageTitle:[...document.querySelectorAll('h1')].filter(visible).map(e=>e.innerText.trim()).find(t=>t.length>10&&!/商品评价|商品属性|商品详情|包装信息|有限公司/.test(t))||'';
// Packaging sections are lazy mounted. Load their public table before taking
// the snapshot, and never interpret its column headers as product attributes.
const packageTable=t=>{const header=t.rows[0]?.innerText||'';return /重量\s*[（(]g[）)]/.test(header)&&(/规格|颜色|尺码/.test(header)||/长\s*[（(]cm[）)]/.test(header)&&/宽\s*[（(]cm[）)]/.test(header)&&/高\s*[（(]cm[）)]/.test(header));};
const packageHeading=[...document.querySelectorAll('h1,h2,h3')].find(e=>e.innerText.trim()==='包装信息');
if(packageHeading){
 const position={left:window.scrollX,top:window.scrollY};
 try{
  packageHeading.scrollIntoView({block:'start',behavior:'instant'});
  for(let attempt=0;attempt<16;attempt++){
   if([...document.querySelectorAll('table')].some(t=>visible(t)&&packageTable(t)&&t.rows.length>1))break;
   await new Promise(resolve=>setTimeout(resolve,250));
  }
 }finally{window.scrollTo(position);}
}
const attributes={};const allowed=new Set(['货源类别','适合季节','产地','含绒量','图案','是否库存','适用年龄段','是否外贸','是否连帽','是否可脱卸','款型','货号','适用场景','颜色','尺码','专利类型','产品尺寸','商品尺寸','尺寸','包装尺寸','包装规格','产品重量','净重','包装重量','毛重','采购价','价格','包装内容','包装清单','材质','材质成分','面料','里料','品牌','功能','适用性别','款式','面料名称','产品类别','厚薄','主面料成分','主面料成分的含量','里料成分','里料成分含量','风格','领型','版型','门襟','适合人群','款式细节','服装下摆设计','衣长','服装口袋样式','袖长']);for(const table of document.querySelectorAll('table')){if(!visible(table))continue;for(const row of table.rows){const cells=[...row.cells].map(c=>c.innerText.trim());for(let i=0;i+1<cells.length;i+=2){const k=cells[i],v=cells[i+1];if(allowed.has(k)&&v&&v.length<4000)attributes[k]=v}}}
// Capture only the product attribute summary, never page-wide account/sidebar text.
const attributeHeading=[...document.querySelectorAll('h1,h2,h3')].find(e=>e.innerText.trim()==='商品属性');
if(attributeHeading){const text=attributeHeading.parentElement.innerText;for(const [key,pattern] of Object.entries({'面料名称':/面料名称\s+([^\s]+)/,'主面料成分':/主面料成分\s+([^\s]+)/,'里料':/里料\s+([^\s]+)/,'功能':/功能\s+([^\s]+)/,'适用性别':/适用性别\s+([^\s]+)/})){const m=text.match(pattern);if(m)attributes[key]=m[1]}}
// Capture a qualified single-piece quote, not a first-order coupon headline.
const productHeading=[...document.querySelectorAll('h1')].find(e=>visible(e)&&e.innerText.trim()===title);
for(let node=productHeading,depth=0;node&&depth<5;node=node.parentElement,depth++){
 const text=node.innerText||'';if(text.length>5000)break;
 const quote=text.match(/[¥￥]\s*(\d+(?:\s*\.\s*\d+)?)\s*1件起批/);
 if(quote){attributes['采购价']='CNY '+quote[1].replace(/\s/g,'')+' / 件（1件起批，页面参考价，结算为准）';break}
}
const skuRows=[...document.querySelectorAll('.expand-view-item')].filter(visible).map(e=>e.innerText.trim()).filter(t=>t.length<=2000&&/[¥￥]/.test(t)&&/库存/.test(t)).slice(0,300);
const packagingTables=[...document.querySelectorAll('table')].filter(visible).filter(packageTable).slice(0,10).map(t=>[...t.rows].slice(0,301).map(r=>[...r.cells].map(c=>c.innerText.trim())));
// The old paired-cell scan could overwrite 颜色 with 尺码 from a packaging
// header. Rebuild these two fields from the actual paired attribute rows.
for(const key of ['颜色','尺码']){
 delete attributes[key];
 for(const table of document.querySelectorAll('table')){
  if(!visible(table)||packageTable(table))continue;
  for(const row of table.rows){const cells=[...row.cells].map(c=>c.innerText.trim());for(let i=0;i+1<cells.length;i+=2)if(cells[i]===key&&cells[i+1]&&cells[i+1]!==key)attributes[key]=cells[i+1];}
 }
}
// Global range/coupon headlines cannot establish a per-variant procurement cost.
if(skuRows.length)delete attributes['采购价'];
// Description content is lazy mounted after its own section enters the viewport.
// Restore the user's position after the bounded load attempt; never click order controls.
const detailSection=[...document.querySelectorAll('h1')].find(e=>e.innerText.trim()==='商品详情')?.closest('.od-collapse-module');
if(detailSection){
 const position={left:window.scrollX,top:window.scrollY};
 try{
  detailSection.scrollIntoView({block:'start',behavior:'instant'});
  for(let attempt=0;attempt<20;attempt++){
   if([...detailSection.querySelectorAll('*')].some(e=>e.shadowRoot?.querySelectorAll('img').length))break;
   await new Promise(resolve=>setTimeout(resolve,250));
  }
 }finally{window.scrollTo(position);}
}
// 1688 changes the V-DETAIL suffix across navigations. Identify the description
// by its observed class and product-detail section, rather than a suffix list.
// Read only supplier product photos, excluding extension/toolbox shadow images.
const supplierDetailHost=host=>!!detailSection&&host.classList?.contains('html-description')&&host.closest?.('.od-collapse-module')===detailSection;
const currentOfferId=location.pathname?.match(/^\/offer\/(\d+)\.html$/)?.[1]||new URL(location.href).pathname.match(/^\/offer\/(\d+)\.html$/)?.[1];
const photoUrl=raw=>{try{const u=new URL(raw);return u.protocol==='https:'&&/^cbu\d+\.alicdn\.com$/.test(u.hostname)&&u.pathname.startsWith('/img/ibank/')&&!u.username&&!u.password&&(!u.port||u.port==='443')?u.href:'';}catch{return '';}};
const imageObservations=[],seenImages=new Set();
const addImage=(e,origin)=>{const url=photoUrl(e.currentSrc||e.src);if(!url||seenImages.has(url)||imageObservations.length>=80)return;
 const link=e.closest?.('a[href]');if(link){try{const target=new URL(link.href,location.href);const offer=target.pathname.match(/^\/offer\/(\d+)\.html$/)?.[1];if(target.hostname==='detail.1688.com'&&offer&&offer!==currentOfferId)return;}catch{return;}}
 seenImages.add(url);imageObservations.push({url,origin,width:e.naturalWidth||null,height:e.naturalHeight||null,visuallyReviewed:false});};
for(const image of document.querySelectorAll('img'))if(visible(image))addImage(image,'product_page');
const roots=[{root:document,inDetail:false}],seenRoots=new Set([document]);
for(let i=0;i<roots.length&&i<512;i++){
 const {root,inDetail}=roots[i];
 // Supplier detail photos use loading=lazy with zero height until scrolled.
 // Retain their public CDN src as unreviewed observations; dimensions and
 // production approval still require loading and inspection downstream.
 if(inDetail)for(const image of root.querySelectorAll('img'))addImage(image,'supplier_detail');
 for(const host of root.querySelectorAll('*'))if(host.shadowRoot&&!seenRoots.has(host.shadowRoot)&&roots.length<512){seenRoots.add(host.shadowRoot);roots.push({root:host.shadowRoot,inDetail:inDetail||supplierDetailHost(host)});}
}
// Resolve the same public CDN object's known thumbnail suffix. A candidate is
// adopted only after the browser actually loads a larger image, never by name.
let nextImage=0;
async function loadOriginal(row){
 const u=new URL(row.url);
 if(!u.pathname.endsWith('_sum.jpg'))return;
 row.observedUrl=row.url;row.observedWidth=row.width;row.observedHeight=row.height;
 u.pathname=u.pathname.slice(0,-'_sum.jpg'.length);
 const candidate=photoUrl(u.href);if(!candidate)return;
 const result=await new Promise(resolve=>{
  const image=new Image();let done=false;
  const finish=value=>{if(done)return;done=true;clearTimeout(timer);image.onload=null;image.onerror=null;resolve(value);};
  const timer=setTimeout(()=>finish(null),4000);
  image.onload=()=>finish({width:image.naturalWidth,height:image.naturalHeight});
  image.onerror=()=>finish(null);image.src=candidate;
 });
 if(result&&result.width>80&&result.height>80&&result.width>=(row.width||0)&&result.height>=(row.height||0)
   &&(result.width>(row.width||0)||result.height>(row.height||0))){
  row.url=candidate;row.width=result.width;row.height=result.height;
  row.originalStatus='browser_loaded_larger_original';
 }else row.originalStatus='thumbnail_retained_original_unavailable';
}
await Promise.all(Array.from({length:Math.min(8,imageObservations.length)},async()=>{
 while(nextImage<imageObservations.length){const row=imageObservations[nextImage++];await loadOriginal(row);}
}));
const images=[...new Set(imageObservations.map(e=>e.url))];
return {url:location.href,title,attributes,images,imageObservations,skuRows,packagingTables,capturedAt:new Date().toISOString()};
})()
