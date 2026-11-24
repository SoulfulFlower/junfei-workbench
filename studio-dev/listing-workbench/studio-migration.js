// Mount the actual adapted IvyeaOps React visual editor in the product workspace.
let visualBundleReady;
async function openCreativeSkills(kind='images',{rule,onSaved}={}){
 const listing=kind==='listing',endpoint=listing?'/api/listing-skills':'/api/creative-skills',name=listing?'文案技能':'图片技能';
 try{
  const response=await fetch(endpoint);const data=await response.json();if(!response.ok)throw Error(data.error||'技能加载失败');
  const modal=document.getElementById('modal');modal.style.width='980px';modal.replaceChildren();
  const title=document.createElement('h2');title.textContent=name+' · 版本 '+data.version;
  const hint=document.createElement('p');hint.className='sub';hint.textContent=(listing?'事实整理 → 关键词分配 → 买家问题 → 转化文案 → 提交前自查。保存后用于下一次生成及局部改写，不会自动覆盖现有文案。':'策划 → 类目保真 → 生图 → 质检。保存后对新策划生效；已有方案保留原技能版本。')+' 固定的事实、内容限制和输出格式约束仍然生效。'+(data.editable?' 仅修改当前账号的技能。':' 当前不可编辑。');
  const body=document.createElement('div');body.style.cssText='max-height:60vh;overflow:auto';const fields={};
  for(const [key,label]of Object.entries(listing?{evidence:'① 产品事实与证据',keywords:'② 搜索量与关键词分配',conversion:'③ 五点与描述写作',questions:'④ 买家问题与评论洞察',review:'⑤ 提交前自查'}:{planning:'① 图片策划',apparel:'② 服装保真',household:'③ 日用百货保真',quality:'④ 图片质检'})){
   const section=document.createElement('details');section.open=rule ? key===rule : key==='planning'||key==='evidence';section.style.margin='14px 0';const summary=document.createElement('summary');summary.textContent=label;const area=document.createElement('textarea');area.value=data.rules[key];area.maxLength=6000;area.readOnly=!data.editable;area.setAttribute('aria-label',label);area.style.cssText='width:100%;min-height:180px;margin-top:12px;line-height:1.8';fields[key]=area;section.append(summary,area);body.append(section);
  }
  const actions=document.createElement('div');actions.className='actions';const status=document.createElement('p');status.setAttribute('role','status');const close=document.createElement('button');close.className='btn';close.textContent='关闭';close.onclick=()=>modal.close();actions.append(close);
  if(data.editable){const reset=document.createElement('button');reset.className='btn';reset.textContent='填入默认规则';reset.onclick=()=>{for(const key in fields)fields[key].value=data.defaults[key];status.textContent='已填入默认规则，点击保存后生效。'};const save=document.createElement('button');save.className='btn primary';save.textContent='保存技能';save.onclick=async()=>{save.disabled=true;try{const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:data.version,rules:Object.fromEntries(Object.entries(fields).map(([k,a])=>[k,a.value]))})});const saved=await r.json();if(!r.ok)throw Error(saved.error||'保存失败');data.version=saved.version;onSaved?.(saved.version);title.textContent=name+' · 版本 '+saved.version;status.textContent=listing?'✓ 已保存，下次生成或改写使用此版本。':'✓ 已保存，新策划会使用此版本。'}catch(e){status.textContent=e.message}finally{save.disabled=false}};actions.append(reset,save)}
  modal.append(title,hint,body,status,actions);modal.showModal();
 }catch(e){toast(e.message)}
}
function loadVisualEditor(){if(window.JunfeiVisual&&window.JunfeiProductEditor)return Promise.resolve();if(!visualBundleReady)visualBundleReady=new Promise((resolve,reject)=>{const css=document.createElement('link');css.rel='stylesheet';css.href='/visual-app/junfei-visual-studio.css';document.head.append(css);const script=document.createElement('script');script.src='/visual-app/studio.js';const failed=()=>{visualBundleReady=null;script.remove();css.remove();reject(Error('视觉编辑器加载失败，请重新加载页面'))};script.onload=()=>{if(window.JunfeiVisual&&window.JunfeiProductEditor)resolve();else failed()};script.onerror=failed;document.head.append(script)});return visualBundleReady}
const renderBeforeNativeStudio=render;render=function(){window.JunfeiVisual?.unmount();const result=renderBeforeNativeStudio();if(view==='images'){const workspace=document.querySelector('[data-product-workspace]');if(workspace)workspace.style.position='static';}return result};
const mountBeforeNativeStudio=mountImageGeneration;
mountImageGeneration=function(){
 mountBeforeNativeStudio();clearTimeout(imagePollTimer);clearTimeout(visualPollTimer);
 const asset=document.getElementById('assetInput')?.closest('section');if(!asset)return;
 const workspace=document.querySelector('[data-product-workspace]');if(workspace)workspace.style.position='static';
 const p=product();
 const notice=asset.parentElement?.querySelector(':scope > .notice');if(notice)notice.hidden=true;
 const hint=asset.querySelector('p');if(hint)hint.textContent='可以补传清晰的白底商品图和同款其他角度实拍。';
 document.getElementById('imageReferencePicker')?.remove();
 const count=asset.querySelector('h2 .sub');if(count)count.remove();
 // Preserve the real material library, but replace every old duplicate generation surface.
 const advanced=document.getElementById('visualStudio')?.closest('details');
 if(advanced){const intro=advanced.previousElementSibling;if(intro?.querySelector('#chatAboutImages'))intro.remove();advanced.remove()}
 document.getElementById('visualStudio')?.remove();
 const manual=document.getElementById('planColor')?.closest('details');manual?.remove();
 document.getElementById('submitImage')?.closest('section')?.remove();
 document.querySelector('.gallery')?.remove();document.getElementById('imageJobs')?.remove();
 const host=document.createElement('div');host.id='nativeVisualStudio';host.textContent='正在加载视觉套图编辑器…';asset.after(host);
 function context(){const market=p.market||p.sourceImport?.market||'US';return {productId:p.id,name:p.name,market,prepare:flushWorkspace,listing:state.copy[p.id+'-'+market]||{}}}
 async function mount(){try{await loadVisualEditor();if(host.isConnected)window.JunfeiVisual.mount(host,context())}catch(e){if(host.isConnected)host.textContent=e.message}}
 mount();
};

function rememberListingLocation(p,step){
 if(!serverReady)return;
 const url=new URL(location.href);
 if(p){url.searchParams.set('product',p.id);url.searchParams.set('step',step)}
 else{url.searchParams.delete('product');url.searchParams.delete('step')}
 if(url.href!==location.href)history.replaceState(history.state,'',url);
}

const listingWorkspaceRenderBefore=render;
render=function(){
 if(['listing','images'].includes(view)){
  const p=product();
  if(p){
   if(listingWorkspaceProduct!==p.id){listingWorkspaceProduct=p.id;listingWorkspaceStep='product'}
   if(view==='images')listingWorkspaceStep='visual';
   else if(listingWorkspaceStep==='visual')listingWorkspaceStep='copy';
   market=p.sourceImport?.market||p.market||'US';
  }
 }
 listingWorkspaceRenderBefore();
 if(!['listing','images'].includes(view)){rememberListingLocation();return}
 const p=product();if(!p)return;
 const root=document.getElementById('content');
 const step=listingWorkspaceStep,copy=state.copy[p.id+'-'+market]||{},hasCopy=Boolean(copy.title?.trim());
 const switchStep=key=>openListingWorkspace(p.id,key);
 const header=document.createElement('section');header.className='listing-workspace-heading';header.dataset.productWorkspace='true';
 header.innerHTML=`<button type="button" class="link" id="wbBack">← 返回产品档案</button>
 <div class="wb-context"><strong>${esc(p.name)}</strong><span class="sub">${esc(market)} 站 · 产品 ID：${esc(p.id)}</span></div>
 <nav class="wb-steps" aria-label="Listing 工作流程">${Object.entries(listingSteps).map(([key,label])=>`<a href="?product=${encodeURIComponent(p.id)}&amp;step=${key}" data-wb-step="${key}"${key===step?' aria-current="page"':''}>${label}</a>`).join('')}</nav>`;
 header.querySelector('#wbBack').onclick=()=>go('products');
 header.querySelectorAll('[data-wb-step]').forEach(link=>link.onclick=e=>{
  if(e.button||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;
  e.preventDefault();switchStep(link.dataset.wbStep);
  const title=document.querySelector('.wb-main h1');title?.setAttribute('tabindex','-1');title?.focus({preventScroll:true});
 });
 const main=document.createElement('div');main.className='wb-main';main.dataset.workspaceStep=step;
 main.append(...root.children);root.append(header,main);
 const titlebar=main.querySelector(':scope > .titlebar');
 titlebar.querySelector('h1').textContent=listingSteps[step];
 titlebar.querySelector('p').textContent={
  product:'核对产品资料，分析当前站点的关键词和买家评论。',
  copy:'编辑当前站点的文案，输入后自动保存。',
  visual:'策划、制作并核对母版套图与变体图。',
  delivery:'核对文案、套图和审核状态，下载交付文件。',
 }[step];
 document.querySelectorAll('#productPicker').forEach(el=>el.remove());
 const titleActions=titlebar.querySelector('.actions');
 if(view==='listing'){
  const grid=main.querySelector('.grid'),facts=grid?.firstElementChild,editor=grid?.lastElementChild;
  for(const el of [...main.children]){
   if(el===titlebar)continue;
   if(el.contains(grid)){el.hidden=step!=='copy';if(el.tagName==='DETAILS')el.open=true;continue}
   const productPanel=el.matches('[data-workspace-panel="product"]')||el.querySelector('[data-workspace-panel="product"],#competitorAsins')||/来源链接/.test(el.querySelector('summary')?.textContent||'');
   el.hidden=step==='product'?!productPanel:step==='copy'?productPanel:true;
   if(step==='product'&&productPanel&&el.tagName==='DETAILS')el.open=Boolean(el.querySelector('#competitorAsins'));
  }
  if(facts)facts.hidden=step!=='product';if(editor)editor.hidden=step!=='copy';if(grid)grid.style.gridTemplateColumns='minmax(0,1fr)';
  if(step==='product'&&facts){const area=document.createElement('section');area.className='workspace-section wb-facts';area.innerHTML=`<h2>产品资料</h2><p class="sub">1688 提供本产品材质、采购价、尺寸、重量和包装资料；竞品 ASIN 仅用于关键词、文案策略和评论洞察。生成前核对供应商资料，缺失项不推断。</p><div class="wb-fact-list">${[['style','款式'],['material','材质'],['dimensions','产品尺寸'],['purchasePrice','采购价'],['packageDimensions','包装尺寸'],['productWeight','产品净重'],['packageWeight','包装毛重'],['packageContents','包装内容'],['features','卖点 / 使用场景'],['sourceUrl','货源链接']].map(([key,label])=>`<div><span>${label}</span><p>${esc(p[key]||'待补充')}</p></div>`).join('')}</div><div class="actions"><button class="link" id="wbEditFacts">编辑资料与变体</button></div>`;titlebar.after(area);area.querySelector('#wbEditFacts').onclick=editFacts}
  if(step==='copy'){main.querySelectorAll('textarea[data-field]').forEach(t=>{if(t.dataset.field==='zh')return;const field=t.closest('label');if(!field)return;const b=document.createElement('button');b.className='link';b.type='button';b.textContent='复制原文';b.onclick=async()=>{try{await navigator.clipboard.writeText(t.value);toast('已复制')}catch{toast('复制失败，请选中文字手动复制')}};field.append(b)})}
  if(step==='delivery'){
   const review=state.reviews[p.id]||{},panel=document.createElement('section');panel.className='workspace-section';panel.innerHTML=`<h2>交付检查 · ${esc(market)}</h2><div class="wb-checks">${[[hasCopy,'已填写标题'],[Boolean(copy.bullets?.trim()),'已填写五点描述'],[Boolean(copy.description?.trim()),'已填写产品描述'],[review.copy===true,'文案人工审核通过'],[review.images===true,'图片人工审核通过']].map(([ok,label])=>`<p>${ok?'✓':'○'} ${label}</p>`).join('')}</div><div class="actions"><button class="btn primary" id="wbExport" ${hasCopy?'':'disabled'}>下载文案＋生成图片 ZIP</button><button class="link" id="wbReview">前往审核中心</button><button class="link" id="wbImages">核对套图</button></div>`;main.append(panel);panel.querySelector('#wbExport').onclick=exportProductDelivery;panel.querySelector('#wbReview').onclick=()=>go('reviews');panel.querySelector('#wbImages').onclick=()=>switchStep('visual');
   const exportCopy=titleActions.querySelector('#export');exportCopy.className='link';panel.querySelector('.actions').append(exportCopy);
  }
  if(step==='product'){
   const actions=main.querySelector('.wb-facts .actions');
   for(const id of ['workspaceVariants','captureCurrentSupplier']){const control=titleActions.querySelector('#'+id);if(control&&actions){control.className='link';actions.append(control)}}
   if(actions&&p.sourceImport?.supplier?.variants?.length){
    const quotes=document.createElement('button');quotes.className='link';quotes.textContent='货源规格与报价';quotes.onclick=()=>showSupplierQuotes(p);actions.append(quotes);
   }
  }
  titleActions.hidden=step!=='copy';
 }
 document.getElementById('crumb').textContent='产品档案 / Listing 工作台 / '+listingSteps[step];
 rememberListingLocation(p,step);
};
// Review collection and evidence-grounded buyer insights in the product workflow.
const renderBeforeBuyerInsights=render;
render=function(){renderBeforeBuyerInsights();if(view!=='listing'||listingWorkspaceStep!=='product')return;mountBuyerInsights()};
function mountBuyerInsights(initialMarket){
 const p=product(),main=document.querySelector('.wb-main');if(!p||!main)return;
 const panel=document.createElement('section');panel.className='panel box';panel.style.marginBottom='20px';panel.innerHTML='<h2>买家评论与洞察</h2><p style="margin:12px 0">通过卖家精灵读取竞品评论，分析买家痛点、好评卖点、使用场景和改进机会。上方一键按钮可联合获取和分析关键词、评论；这里保留单独重取和重试入口。</p><div class="actions"><label>评论来源站点 <select id="reviewMarket" aria-label="评论来源站点"></select></label></div><label class="field"><span>竞品 ASIN（最多 5 个）</span><textarea id="reviewAsins" aria-label="评论竞品 ASIN" placeholder="每行一个 ASIN，也可直接使用上方竞品挖词的 ASIN" style="min-height:75px"></textarea></label><div class="actions"><button class="btn" id="useResearchAsins">使用竞品挖词的 ASIN</button><button class="btn" id="fetchBuyerReviews">单独重取评论</button><button class="btn" id="analyseBuyerReviews">单独重试评论分析</button></div><p role="status" id="buyerReviewStatus" style="margin:16px 0"></p><div id="buyerInsightsResult"></div>';
 main.append(panel);const site=panel.querySelector('#reviewMarket'),input=panel.querySelector('#reviewAsins'),status=panel.querySelector('#buyerReviewStatus'),result=panel.querySelector('#buyerInsightsResult'),fetchButton=panel.querySelector('#fetchBuyerReviews'),analyseButton=panel.querySelector('#analyseBuyerReviews');
 site.innerHTML=competitorMarketplaces.filter(([code])=>sellerSpriteSupportedMarkets.has(code)).map(([code,name])=>`<option value="${code}">${name}站 · ${code}</option>`).join('');site.value=initialMarket||market;
 let busy=false;
 function current(){return p.reviewResearch?.[site.value]}
 function draw(){const report=current();input.value=report?.input||p.competitorResearch?.[site.value]?.input||'';result.replaceChildren();analyseButton.disabled=!report?.samples?.length||busy;if(!report){status.textContent='尚未获取该站点评论。每个 ASIN 最多两次查询，各取 1–3 星和 4–5 星第 1 页 30 条。';return}status.textContent=`已保存 ${report.samples?.length||0} 条去重评论样本 · ${report.market} 站 · ${report.fetchedAt?new Date(report.fetchedAt).toLocaleString('zh-CN'):''}`;const note=document.createElement('p');note.className='notice';note.textContent=report.limitation||'';result.append(note);if(report.supplement){const extra=document.createElement('p');extra.textContent='补充评论参考 '+report.supplement.asin+' · 父体 '+report.supplement.parentAsin+' · 销售排名 #'+report.supplement.rank+' · '+report.supplement.structureEvidence;result.append(extra)}for(const source of report.sources||[]){const row=document.createElement('p');row.textContent=source.asin+' · '+source.count+' 条 · '+(source.error||'查询完成');result.append(row)}
 const analysis=report.analysis;if(analysis){const warning=document.createElement('p');warning.className='notice';warning.textContent=analysis.warning;result.append(warning);for(const [category,title]of [['pain_point','买家痛点 / 差评原因'],['positive','好评卖点'],['use_case','使用场景'],['improvement','改进与表达机会']]){const themes=(analysis.themes||[]).filter(t=>t.category===category);if(!themes.length)continue;const section=document.createElement('section');section.style.margin='20px 0';const h=document.createElement('h3');h.textContent=title;section.append(h);for(const theme of themes){const item=document.createElement('details');item.style.margin='12px 0';const summary=document.createElement('summary');summary.textContent=theme.title;item.append(summary);const suggestion=document.createElement('p');suggestion.textContent=theme.recommendation;suggestion.style.margin='12px 0';item.append(suggestion);for(const id of theme.evidenceIds){const sample=report.samples.find(s=>s.id===id);if(!sample)continue;const quote=document.createElement('blockquote');quote.style.cssText='border-left:3px solid #b3c7e0;padding:10px 14px;white-space:pre-wrap;margin:10px 0;background:#f7f9fd';quote.textContent=`${id} · ${sample.asin} · ${sample.rating||'未返回'} 星\n${sample.title}\n${sample.text}`;item.append(quote)}section.append(item)}result.append(section)}}
 const originals=document.createElement('details');const label=document.createElement('summary');label.textContent='查看全部已获取评论（'+(report.samples?.length||0)+' 条）';originals.append(label);for(const sample of report.samples||[]){const block=document.createElement('p');block.style.cssText='white-space:pre-wrap;margin:16px 0';block.textContent=`${sample.id} · ${sample.asin} · ${sample.rating||'未返回'} 星 · ${sample.date||''}\n${sample.title}\n${sample.text}`;originals.append(block)}result.append(originals)}
 site.onchange=draw;panel.querySelector('#useResearchAsins').onclick=()=>{input.value=document.getElementById('competitorAsins')?.value||p.competitorResearch?.[site.value]?.input||'';const researchSite=document.getElementById('competitorMarket')?.value;if(researchSite)site.value=researchSite;if(!input.value.trim())toast('请先在竞品挖词区域输入 ASIN')};
 async function request(action){if(busy)return;const targetMarket=site.value,asins=input.value.trim(),id=p.id,previous=p.reviewResearch?.[targetMarket];if(action==='fetch'&&!asins)return toast('请输入竞品 ASIN');if(action==='analyse'&&!previous?.samples?.length)return toast('请先获取评论样本');if(!confirm(action==='fetch'?'将调用卖家精灵评论接口，每个 ASIN 最多 2 次查询，可能消耗额度；获取新样本会替换该站点旧样本及分析，是否继续？':'将调用 DeepSeek 分析已保存的评论样本，可能产生费用，是否继续？'))return;busy=true;fetchButton.disabled=true;analyseButton.disabled=true;site.disabled=true;status.textContent=action==='fetch'?'正在获取评论样本，请勿重复提交…':'正在分析买家痛点和使用场景，保留证据引用…';try{const facts=Object.fromEntries(['name','material','style','dimensions','features','packageContents'].map(k=>[k,p[k]||'']));const r=await fetch('/api/reviews/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(action==='fetch'?{market:targetMarket,asins}:{report:previous,facts})});const data=await r.json();if(!r.ok)throw Error(data.error||'请求失败');const target=state.products.find(x=>x.id===id);if(!target)return;target.reviewResearch||={};if(action==='fetch'){if(!data.samples?.length){status.textContent='没有获取到评论正文：'+(data.sources||[]).map(s=>s.asin+' '+(s.error||'无正文')).join('；')+'。已保留原有样本及分析。';return}target.reviewResearch[targetMarket]=data}else{if(target.reviewResearch[targetMarket]!==previous)throw Error('评论样本已变化，请重新分析');previous.analysis=data}persist();if(panel.isConnected)draw();toast(action==='fetch'?'评论样本已保存，可继续 AI 分析':'评论洞察已保存，后续文案与图片策划会参考')}catch(e){if(status.isConnected)status.textContent='未完成：'+e.message+'；原有数据保留。'}finally{busy=false;fetchButton.disabled=false;analyseButton.disabled=!current()?.samples?.length;site.disabled=false}}
 fetchButton.onclick=()=>request('fetch');analyseButton.onclick=()=>request('analyse');draw();
}
if(view==='listing'&&listingWorkspaceStep==='product'&&!document.getElementById('buyerInsightsResult'))mountBuyerInsights();
// Editorial alternatives share the current product/site and version history.
const renderBeforeEditorialOptions=render;
render=function(){renderBeforeEditorialOptions();if(view!=='listing'||listingWorkspaceStep!=='copy')return;const p=product(),c=state.copy[p.id+'-'+market];if(!c)return;const main=document.querySelector('.wb-main');if(!main)return;const panel=document.createElement('section');panel.className='panel box';panel.style.marginBottom='20px';const h=document.createElement('h2');h.textContent='文案策略与候选方案';panel.append(h);const note=document.createElement('p');note.textContent=c.generationEngine?.version===2?'原版文案引擎已启用：候选写作 → 事实与关键词编辑 → 商业表达检查 → 中英对照。候选方案仍需审核，采用时会备份当前文案。':'依据本产品事实规划表达，候选方案仍需审核。采用方案会备份当前版本，并清空对应旧翻译。';note.className='sub';panel.append(note);if(c.editorialPlan){const plan=document.createElement('pre');plan.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;margin:16px 0;font:inherit';try{const data=JSON.parse(c.editorialPlan);plan.textContent=Object.entries(data).map(([k,v])=>k+'：'+(typeof v==='string'?v:JSON.stringify(v,null,2))).join('\n\n')}catch{plan.textContent=c.editorialPlan}panel.append(plan)}const alternatives=c.alternatives||{};function adopt(field,value){workflowSnapshot(p,'采用候选前备份');c[field]=value;if(c.translations)delete c.translations[field];c.zh='';delete c.contentAudit;c.warnings=(c.warnings||'')+'\n已手动采用候选方案：旧关键词落位核对可能失效，请重新人工核对。';p.status='制作中';state.reviews[p.id]={copy:false,images:false,note:'已采用候选文案，需重新审核'};persist();render();toast('已采用并备份原版本，请重新翻译及审核')}
for(const [i,text]of (alternatives.titles||[]).entries()){const row=document.createElement('div');row.style.cssText='margin:12px 0;padding:12px;background:#f6f8fc;border-radius:8px';const span=document.createElement('p');span.textContent='标题 '+(i+1)+' · '+Array.from(text).length+' 字符\n'+text;row.append(span);const b=document.createElement('button');b.className='link';b.textContent='采用此标题';b.onclick=()=>adopt('title',text);row.append(b);panel.append(row)}for(const [key,label]of [['bulletsConversion','五点 A · 购买决策'],['bulletsQuestions','五点 B · 买家问答']]){if(!alternatives[key])continue;const fold=document.createElement('details');const summary=document.createElement('summary');summary.textContent=label;const text=document.createElement('p');text.style.cssText='white-space:pre-wrap;margin:16px 0';text.textContent=alternatives[key].join('\n\n');const b=document.createElement('button');b.className='btn';b.textContent='采用此套五点';b.onclick=()=>adopt('bullets',alternatives[key].join('\n'));fold.append(summary,text,b);panel.append(fold)}if(!c.editorialPlan&&!Object.keys(alternatives).length){note.textContent='下一次生成将附带写作策略、多个标题和两套侧重不同的五点；已有文案保留。'}main.prepend(panel)};
// Highlight exact selected keyword phrases inside editable listing fields.
const renderBeforeKeywordMarks=render;
render=function(){renderBeforeKeywordMarks();if(view!=='listing'||listingWorkspaceStep!=='copy')return;mountKeywordMarks()};
function mountKeywordMarks(selector='textarea[data-field]'){
 const p=product(),copy=state.copy[p.id+'-'+market]||{},report=p.competitorResearch?.[market];
 const phrases=[...new Set([...(report?.keywords||[]).filter(k=>k.selected!==false).map(k=>k.phrase),...(copy.contentAudit?.keywordPlacements||[]).map(k=>k.phrase)].filter(x=>typeof x==='string'&&x.trim()).map(x=>x.trim()))].sort((a,b)=>b.length-a.length);
 const escapeRegex=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 if(!phrases.length)return;
 const expression=new RegExp('(^|[^\\p{L}\\p{N}])('+phrases.map(escapeRegex).join('|')+')(?=$|[^\\p{L}\\p{N}])','giu');
 let total=0;
 for(const area of document.querySelectorAll(selector)){
  if(area.closest('[hidden]')||area.closest('.keyword-mark-editor'))continue;
  if(!['title','highlights','bullets','description','terms'].includes(area.dataset.field||area.dataset.bulletField))continue;
  const wrap=document.createElement('div');wrap.className='keyword-mark-editor';area.before(wrap);const mirror=document.createElement('div');mirror.className='keyword-mark-mirror';mirror.setAttribute('aria-hidden','true');wrap.append(mirror,area);
  function update(){const value=area.value;expression.lastIndex=0;let cursor=0,count=0;mirror.replaceChildren();for(const match of value.matchAll(expression)){const start=match.index+match[1].length;mirror.append(document.createTextNode(value.slice(cursor,start)));const mark=document.createElement('span');mark.className='keyword-wave';mark.textContent=match[2];mark.title='已选关键词：'+match[2];mirror.append(mark);cursor=start+match[2].length;count++}mirror.append(document.createTextNode(value.slice(cursor)+'\n'));wrap.dataset.matches=count;mirror.scrollTop=area.scrollTop;mirror.scrollLeft=area.scrollLeft;return count}
  area.addEventListener('input',()=>{update();updateCount()});area.addEventListener('bulletcount',()=>{update();updateCount()});area.addEventListener('scroll',()=>{mirror.scrollTop=area.scrollTop;mirror.scrollLeft=area.scrollLeft});
  // Mirror the actual computed typography so editable text and decoration align.
  const style=getComputedStyle(area);for(const key of ['fontFamily','fontSize','fontWeight','fontStyle','lineHeight','letterSpacing','paddingTop','paddingRight','paddingBottom','paddingLeft','borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth','borderStyle','boxSizing','textAlign','tabSize'])mirror.style[key]=style[key];mirror.style.borderColor='transparent';area.classList.add('keyword-mark-input');total+=update();
 }
 const hint=document.getElementById('keywordMarkHint')||document.createElement('p');hint.className='sub';hint.id='keywordMarkHint';hint.style.margin='12px 0';if(!hint.isConnected)document.querySelector('.wb-main .grid')?.before(hint);
 function updateCount(){const count=[...document.querySelectorAll('.keyword-mark-editor')].reduce((n,el)=>n+(el.closest('[hidden]')?0:Number(el.dataset.matches||0)),0);hint.textContent='红色波浪线：已选关键词在文案中的实际词组匹配，共 '+count+' 处。仅用于编辑核对，不代表亚马逊收录；导出不带标记。'}updateCount();
}
const renderBeforeUsability=render;
render=function(){renderBeforeUsability();if(view!=='listing')return;const p=product(),main=document.querySelector('.wb-main');if(!main)return;
 if(listingWorkspaceStep==='product'){
  const panel=document.createElement('section');panel.className='panel box';panel.style.marginBottom='20px';panel.innerHTML='<h2>产品准备清单</h2><p class="sub">文案依据与物流资料分开检查，物流字段缺失不阻止文案生成。</p>';
  const checks=[['产品类型 / 款式',!!p.style,'facts'],['材质',!!p.material,'facts'],['目标受众（不明确时不推断）',!!p.targetAudience,'facts'],['产品尺寸 / 尺码资料',!!p.dimensions,'facts'],['当前站点关键词',(p.competitorResearch?.[market]?.keywords||[]).length>0,'research'],['当前站点评论洞察',!!p.reviewResearch?.[market]?.analysis,'reviews'],['采购价 · 内部使用',!!p.purchasePrice,'facts'],['包装尺寸 · 物流资料',!!p.packageDimensions,'facts'],['净重 / 毛重 · 物流资料',!!p.productWeight&&!!p.packageWeight,'facts']];
  const list=document.createElement('ul');for(const [label,ok]of checks){const row=document.createElement('li');row.textContent=(ok?'已填写 · ':'待补 · ')+label;list.append(row)}panel.append(list);main.append(panel);
 }
 if(listingWorkspaceStep!=='copy')return;
 const labels={title:'标题',highlights:'商品亮点',bullets:'五点描述',description:'产品描述',terms:'后台搜索词'},key=p.id+'-'+market;
 function reviewChange(oldCopy,newCopy,onApply){const modal=document.getElementById('modal');modal.style.width='1100px';modal.innerHTML='<h2>新旧文案对比</h2><p class="sub">核对事实和关键词后采用。关闭可保留当前文案。</p><div id="copyCompareRows" style="max-height:65vh;overflow:auto"></div><div class="actions" style="margin-top:16px"><button class="btn" id="closeCompare">暂不采用</button><button class="btn primary" id="applyCompare">采用新稿</button></div>';const rows=modal.querySelector('#copyCompareRows');for(const [field,label]of Object.entries(labels)){if(newCopy[field]===undefined)continue;const block=document.createElement('section');block.style.margin='18px 0';const h=document.createElement('h3');h.textContent=label+(oldCopy[field]===newCopy[field]?' · 未变化':' · 已变化');const columns=document.createElement('div');columns.className='bilingual-row';for(const [name,value]of [['当前文案',oldCopy[field]],['新草稿',newCopy[field]]]){const pre=document.createElement('pre');pre.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7fb;padding:15px;font:inherit';pre.textContent=name+'\n\n'+(value||'（空）');columns.append(pre)}block.append(h,columns);rows.append(block)}modal.querySelector('#closeCompare').onclick=()=>{modal.close();modal.style.width=''};modal.querySelector('#applyCompare').onclick=()=>{onApply();modal.close();modal.style.width=''};modal.showModal()}
 if(p.pendingCopy?.[market]){const pending=p.pendingCopy[market],panel=document.createElement('section');panel.className='workspace-section';panel.id='pendingCopyPreview';panel.innerHTML='<h2>文案草稿已保存 · 待核对</h2><p>打开对比核对新旧文案，再决定是否采用。</p><button class="btn primary">对比并选择采用</button>';const bulletLengths=String(pending.copy?.bullets||'').split(/\r?\n/).filter(x=>x.trim()).map(x=>Array.from(x).length);const checks=document.createElement('p');checks.className='notice';checks.style.marginTop='16px';checks.textContent='五点字符数：'+bulletLengths.join(' / ')+(bulletLengths.length!==5?'。五点数量异常，请核对。':bulletLengths.some(n=>n<350)?'。部分五点低于350字符目标，请检查事实是否充分、表达和埋词是否自然；不要为了凑字编造。':'。请继续核对事实与关键词表达。');panel.append(checks);panel.querySelector('button').onclick=()=>{const before=JSON.stringify(state.copy[key]||{});reviewChange(state.copy[key]||{},listingWithLocks(state.copy[key]||{},pending.copy),()=>{if(JSON.stringify(state.copy[key]||{})!==before)return toast('当前文案已变化，请重新打开对比');workflowSnapshot(p,'采用新生成稿前备份');state.copy[key]=listingWithLocks(state.copy[key]||{},pending.copy);delete p.pendingCopy[market];p.status='制作中';state.reviews[p.id]={copy:false,images:false,note:'新文案待审核'};persist();render();toast('已采用新稿，原版本已备份')})};main.prepend(panel)}
 const coverage=document.createElement('section');coverage.className='workspace-section';const summary=document.createElement('h3');summary.textContent='关键词覆盖 · 点击定位原文';const content=document.createElement('div');coverage.append(summary,content);main.prepend(coverage);
 function drawCoverage(){content.replaceChildren();const words=(p.competitorResearch?.[market]?.keywords||[]).filter(k=>k.selected!==false);const counts={hit:0,miss:0};for(const word of words){const phrase=word.phrase;if(typeof phrase!=='string'||!phrase.trim())continue;const re=new RegExp('(^|[^\\p{L}\\p{N}])'+phrase.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?=$|[^\\p{L}\\p{N}])','iu');const hits=[...document.querySelectorAll('textarea[data-field]')].filter(t=>labels[t.dataset.field]&&re.test(t.value));counts[hits.length?'hit':'miss']++;const row=document.createElement('button');row.className='btn';row.style.cssText='margin:8px 6px 0 0;text-align:left';const volumes=(word.metrics||[]).map(m=>Number(m.searches)).filter(v=>Number.isFinite(v)&&v>0);row.textContent=(hits.length?'✓ ':'○ ')+phrase+' · '+(volumes.length?Math.max(...volumes)+'/月':'搜索量未知')+' · '+(hits.map(t=>labels[t.dataset.field]).join('、')||'未使用');row.onclick=()=>{const t=hits[0];if(!t)return toast(word.reason||'未使用：请核对是否与产品事实匹配，避免为了埋词补造属性');const fold=t.closest('details');if(fold)fold.open=true;t.scrollIntoView({behavior:'smooth',block:'center'});t.focus();const index=t.value.toLowerCase().indexOf(phrase.toLowerCase());if(index>=0)t.setSelectionRange(index,index+phrase.length)};content.append(row)}summary.textContent='关键词覆盖：已使用 '+counts.hit+' / 未使用 '+counts.miss+' · 点击定位';if(!words.length)content.textContent='请先在素材与洞察获取并选择关键词。'}drawCoverage();
 for(const area of document.querySelectorAll('textarea[data-field]')){const field=area.dataset.field;if(!labels[field])continue;area.addEventListener('input',drawCoverage);const actions=document.createElement('div');actions.className='actions';const select=document.createElement('select');select.setAttribute('aria-label',labels[field]+'改写方式');select.innerHTML='<option value="natural">更自然</option><option value="concise">更精简</option><option value="keywords">融入已选关键词</option>';const button=document.createElement('button');button.className='btn';button.type='button';button.textContent='AI 改写此项';actions.append(select,button);area.closest('label')?.append(actions);button.onclick=async()=>{const original=area.value;if(!original.trim())return toast('请先填写文案');if(!confirm('仅将本项文案及产品资料发送给 DeepSeek 改写，可能产生费用，是否继续？'))return;button.disabled=true;button.textContent='改写中…';try{const response=await fetch('/api/listing/rewrite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({field,text:original,currentTitle:state.copy[key]?.title||'',market,mode:select.value,product:listingGenerationProduct(p,market)})});const data=await response.json();if(!response.ok)throw Error(data.error);if(!area.isConnected)return download(p.id+'-'+field+'-改写.txt',data.text);const before=state.copy[key]?.[field]??original;reviewChange({[field]:before},{[field]:data.text},()=>{if((state.copy[key]?.[field]??original)!==before)return toast('原文已修改，请重新对比');workflowSnapshot(p,'局部改写前备份');state.copy[key]||={...defaults(p)};state.copy[key][field]=data.text;if(state.copy[key].translations)delete state.copy[key].translations[field];state.copy[key].zh='';delete state.copy[key].contentAudit;p.status='制作中';state.reviews[p.id]={copy:false,images:false,note:'局部改写待审核'};persist();render()})}catch(e){toast(e.message)}finally{button.disabled=false;button.textContent='AI 改写此项'}}}
};

const renderBeforeListingSkills=render;
render=function(){renderBeforeListingSkills();if(view!=='listing'||listingWorkspaceStep!=='copy')return;const main=document.querySelector('.wb-main');if(!main)return;const bar=document.createElement('div');bar.className='actions';bar.style.marginBottom='16px';const button=document.createElement('button');button.className='btn';button.textContent='文案技能 · 查看 / 编辑';button.onclick=()=>openCreativeSkills('listing');const hint=document.createElement('span');hint.className='sub';hint.textContent='生成与局部改写自动使用：事实依据、搜索量分词、买家问题和提交前自查';const preview=document.createElement('a');preview.className='btn';preview.textContent='预览完整 Listing';preview.href='/api/listing/preview?productId='+encodeURIComponent(product().id);preview.target='_blank';preview.rel='noopener';bar.append(button,preview,hint);main.prepend(bar)};
// Keep the actual editable deliverable ahead of strategy and research.
const renderBeforeCopyLayout=render;
render=function(){
 renderBeforeCopyLayout();
 if(view!=='listing'||listingWorkspaceStep!=='copy')return;
 const main=document.querySelector('.wb-main'),grid=main?.querySelector('.grid');if(!main||!grid)return;
 const wrapper=grid.closest('details'),editor=grid.lastElementChild;
 editor.className='workspace-copy-editor';
 if(wrapper)wrapper.replaceWith(editor);else grid.replaceWith(editor);
 const titlebar=main.querySelector(':scope > .titlebar');
 const progress=main.querySelector('#listingGenerationProgress');
 if(progress)(main.querySelector('#pendingCopyPreview')||editor).before(progress);
 const pending=main.querySelector('#pendingCopyPreview');
 if(pending)editor.before(pending);
 const labels={title:'产品标题',highlights:'产品亮点',bullets:'五点描述',description:'产品描述',terms:'后台搜索词'};
 const nav=document.createElement('nav');nav.className='workspace-copy-nav';nav.setAttribute('aria-label','文案字段');
 for(const [key,label]of Object.entries(labels)){
  const input=editor.querySelector('textarea[data-field="'+key+'"]');if(!input)continue;
  const row=input.closest('.bilingual-row')||input.closest('label');
  const section=document.createElement('section');section.className='copy-deliverable';section.id='listing-field-'+key;
  const heading=document.createElement('h2');heading.textContent=label;
  const fieldFold=row.closest('details');
  if(fieldFold)fieldFold.replaceWith(section);else row.before(section);
  section.append(heading,row);
  const link=document.createElement('a');link.href='#'+section.id;link.textContent=label;
  link.onclick=e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();input.focus({preventScroll:true});section.scrollIntoView({block:'start'})};nav.append(link);
 }
 const box=editor.querySelector('.box');box?.prepend(nav);
 const aux=document.createElement('details');aux.className='workspace-tools';
 const summary=document.createElement('summary');summary.textContent='写作辅助与文案核对';aux.append(summary);
 for(const section of [...main.children]){
  if(section===editor||section===titlebar||section===progress||section===pending||section.hidden)continue;
  if(section.tagName==='DETAILS'){
   const block=document.createElement('section'),heading=document.createElement('h3'),caption=section.querySelector(':scope > summary');
   heading.textContent=caption?.textContent||'文案资料';
   caption?.remove();block.append(heading,...section.children);aux.append(block);section.remove();
  }else aux.append(section);
 }
 const actions=titlebar.querySelector('.actions');
 for(const id of ['export','workspaceVariants','captureCurrentSupplier'])actions.querySelector('#'+id)?.remove();
 const history=document.createElement('details');history.className='workspace-version-menu';
 const historyLabel=document.createElement('summary');historyLabel.textContent='版本记录';history.append(historyLabel);
 for(const id of ['workspaceSaveVersion','workspaceHistory']){const button=actions.querySelector('#'+id);if(button){button.className='link';history.append(button)}}
 actions.append(history);
 main.append(aux);
 editor.addEventListener('input',updateListingCopyActions);
 updateListingCopyActions();
};

function updateListingCopyActions(){
 const main=document.querySelector('.wb-main[data-workspace-step="copy"]');
 if(!main)return;
 const p=product(),copy=state.copy[p.id+'-'+market]||{};
 const generate=main.querySelector('#generateListing'),submit=main.querySelector('#submit');
 const pending=main.querySelector('#pendingCopyPreview');
 const running=activeListingGeneration.has(p.id+'-'+market);
 const ready=Boolean(copy.title?.trim()&&copy.description?.trim()&&String(copy.bullets||'').split(/\r?\n/).filter(line=>line.trim()).length===5);
 generate.hidden=Boolean(pending);
 submit.hidden=running||!ready;
 generate.classList.toggle('primary',!ready&&!pending);
 submit.classList.toggle('primary',!submit.hidden&&!pending);
 if(serverReady&&listingKeyConfigured&&!running)generate.textContent=(ready?'重新生成 ':'生成 ')+market+' 站文案';
}

// Five independent editors; retain the canonical field for generation, export and history.
const renderBeforeBulletBoxes=render;
render=function(){
 renderBeforeBulletBoxes();
 if(view!=='listing'||listingWorkspaceStep!=='copy')return;
 const original=document.querySelector('textarea[data-field="bullets"]');
 const row=original?.closest('.bilingual-row');if(!row)return;
 const translated=row.querySelector('textarea:not([data-field])');
 const split=value=>String(value||'').split(/\r?\n/).map(v=>v.trim());
 const english=split(original.value),chinese=split(translated?.value);
 // Preserve unexpected legacy paragraphs rather than truncating them.
 const count=Math.max(5,english.length,chinese.length);
 const group=document.createElement('div');group.className='bullet-boxes';
 const columns=[original,translated].filter(Boolean);
 for(const area of columns){const host=area.closest('.keyword-mark-editor')||area;host.hidden=true;}
 row.after(group);
 const editors=columns.map(()=>[]);
 for(let i=0;i<count;i++){
  const pair=document.createElement('div');pair.className='bullet-box-pair';
  columns.forEach((source,col)=>{
   const label=document.createElement('label');label.className='field bullet-box';
   const heading=document.createElement('span');heading.append(document.createTextNode('第 '+(i+1)+' 点 · '+(col?'中文翻译':'原文')));
   const counter=document.createElement('small');heading.append(counter);
   const input=document.createElement('textarea');input.dataset.bulletField=col?'translation':'bullets';input.dataset.bulletIndex=i;
   input.setAttribute('aria-label','第 '+(i+1)+' 点'+(col?'中文翻译':'原文'));
   input.value=(col?chinese:english)[i]||'';input.placeholder=col?'本点的中文翻译':'填写第 '+(i+1)+' 点描述';
   const updateCounter=()=>{const length=Array.from(input.value).length;counter.textContent=length+' 字符';counter.style.color=!col&&length>500?'#b42318':'';};updateCounter();input.addEventListener('bulletcount',updateCounter);
   input.addEventListener('input',()=>{source.value=editors[col].map(t=>t.value.replace(/\r?\n/g,' ')).join('\n');source.dispatchEvent(new Event('input',{bubbles:true}));updateCounter();});
   editors[col].push(input);label.append(heading,input);pair.append(label);
  });group.append(pair);
 }
 columns.forEach((source,col)=>{
  const save=source.oninput;
  source.oninput=function(event){if(save)save.call(this,event);const values=String(source.value).split(/\r?\n/);editors[col].forEach((input,i)=>{if(input.value!==(values[i]||''))input.value=values[i]||'';input.dispatchEvent(new Event('bulletcount'));});};
  // Keyword navigation continues to locate the corresponding individual box.
  const target=()=>{const before=source.value.slice(0,source.selectionStart||0);return editors[col][Math.min(before.split('\n').length-1,count-1)]||editors[col][0];};
  source.focus=()=>target().focus();source.scrollIntoView=options=>target().scrollIntoView(options);
  source.setSelectionRange=(start,end)=>{const prefix=source.value.slice(0,start),index=prefix.split('\n').length-1,offset=prefix.lastIndexOf('\n')+1,input=editors[col][index];if(input){input.scrollIntoView({behavior:'smooth',block:'center'});input.focus();input.setSelectionRange(start-offset,end-offset);}};
 });
 // Recount after automatic translations and keep keyword decorations on each box.
 mountKeywordMarks('textarea[data-bullet-field="bullets"]');
};

