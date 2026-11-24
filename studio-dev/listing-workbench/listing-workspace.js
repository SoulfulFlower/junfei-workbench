/* Product workspace inspired by IvyeaOps' four-step workflow. Existing service integrations remain authoritative. */
let listingWorkspaceStep='product',listingWorkspaceProduct='';
const listingWorkspaceRenderBefore=render;
render=function(){
 if(['listing','images'].includes(view)&&listingWorkspaceProduct!==product()?.id){const initialMarket=product()?.sourceImport?.market||product()?.market;if(initialMarket)market=initialMarket}
 listingWorkspaceRenderBefore();
 if(!['listing','images'].includes(view))return;
 const p=product();if(!p)return;
 if(listingWorkspaceProduct!==p.id){listingWorkspaceProduct=p.id;listingWorkspaceStep=view==='images'?'visual':'product'}
 if(view==='images')listingWorkspaceStep='visual';else if(listingWorkspaceStep==='visual')listingWorkspaceStep='copy';
 const root=document.getElementById('content'),header=root.querySelector('[data-product-workspace]');if(!header)return;
 const step=listingWorkspaceStep,copy=state.copy[p.id+'-'+market]||{},hasCopy=Boolean(copy.title?.trim());
 const switchStep=key=>{listingWorkspaceStep=key;go(key==='visual'?'images':'listing');window.scrollTo({top:0,behavior:'instant'})};
 header.innerHTML=`<div class="wb-heading"><div><button class="link" id="wbBack">← 产品档案</button><h2>Listing 工作台</h2><button class="btn" id="wbSupplierCapture">货源采集 · 更新本产品</button><p class="sub">从产品事实到文案、视觉套图与交付</p></div><div class="wb-context"><span class="badge">${esc(p.sourceImport?.market||p.market||'US')}</span><strong>${esc(p.name)}</strong><span class="sub">产品 ID：${esc(p.id)}</span></div></div><div class="wb-steps" role="tablist" aria-label="Listing 工作流程">${[['product','① 素材与洞察'],['copy','② Listing 文案'],['visual','③ 视觉套图'],['delivery','④ 交付']].map(([key,label])=>`<button class="${key===step?'active':''}" role="tab" aria-selected="${key===step}" data-wb-step="${key}">${label}${key==='copy'&&hasCopy?' ✓':''}</button>`).join('')}</div>`;
 header.querySelector('#wbSupplierCapture').onclick=openSupplierForProduct;header.querySelector('#wbBack').onclick=()=>go('products');header.querySelectorAll('[data-wb-step]').forEach(b=>b.onclick=()=>switchStep(b.dataset.wbStep));
 const body=document.createElement('div');body.className='wb-body';const rail=document.createElement('aside');rail.className='wb-rail panel';rail.innerHTML='<h3>产品项目</h3><input type="search" aria-label="搜索工作台产品" placeholder="搜索名称 / ID"><div class="wb-projects"></div>';
 const draw=term=>{const list=state.products.filter(x=>(x.name+' '+x.id).toLowerCase().includes(term.toLowerCase()));rail.querySelector('.wb-projects').innerHTML=list.map(x=>`<button class="wb-project ${x.id===p.id?'active':''}" data-wb-product="${esc(x.id)}"><strong>${esc(x.name)}</strong><span>${esc(x.id)}</span><small>${esc(x.status||'待补资料')}</small></button>`).join('')||'<p class="sub">没有匹配产品</p>';rail.querySelectorAll('[data-wb-product]').forEach(b=>b.onclick=()=>openProduct(b.dataset.wbProduct,'listing'))};draw('');rail.querySelector('input').oninput=e=>draw(e.target.value);
 const main=document.createElement('main');main.className='wb-main';for(const el of [...root.children])if(el!==header)main.append(el);body.append(rail,main);root.append(body);
 if(view==='listing'){
  const grid=main.querySelector('.grid'),facts=grid?.firstElementChild,editor=grid?.lastElementChild;
  for(const el of [...main.children]){
   if(el.contains(grid)){el.hidden=step!=='copy';if(el.tagName==='DETAILS')el.open=true;continue}
   const text=el.querySelector('summary')?.textContent||'';
   const productPanel=/产品图片|竞品挖词|来源链接/.test(text);
   el.hidden=step==='product'?!productPanel:step==='copy'?productPanel:true;
   if(step==='product'&&productPanel&&el.tagName==='DETAILS')el.open=true;
  }
  if(facts)facts.hidden=step!=='product';if(editor)editor.hidden=step!=='copy';if(grid)grid.style.gridTemplateColumns='minmax(0,1fr)';
  if(step==='product'&&facts){const area=document.createElement('section');area.className='panel box wb-facts';area.innerHTML=`<h2>产品资料</h2><p class="sub">1688 提供本产品材质、采购价、尺寸、重量和包装资料；竞品 ASIN 仅用于关键词、文案策略和评论洞察。生成前核对供应商资料，缺失项不推断。</p><div class="wb-fact-list">${[['style','款式'],['material','材质'],['dimensions','产品尺寸'],['purchasePrice','采购价'],['packageDimensions','包装尺寸'],['productWeight','产品净重'],['packageWeight','包装毛重'],['packageContents','包装内容'],['features','卖点 / 使用场景'],['sourceUrl','货源链接']].map(([key,label])=>`<div><span>${label}</span><p>${esc(p[key]||'待补充')}</p></div>`).join('')}</div><div class="actions"><button class="btn" id="wbEditFacts">编辑资料与变体</button><button class="btn primary" id="wbNextCopy">下一步：Listing 文案 →</button></div>`;main.prepend(area);area.querySelector('#wbEditFacts').onclick=editFacts;area.querySelector('#wbNextCopy').onclick=()=>switchStep('copy')}
  if(step==='copy'){main.querySelectorAll('textarea[data-field]').forEach(t=>{if(t.dataset.field==='zh')return;const field=t.closest('label');if(!field)return;const b=document.createElement('button');b.className='link';b.type='button';b.textContent='复制原文';b.onclick=async()=>{try{await navigator.clipboard.writeText(t.value);toast('已复制')}catch{toast('复制失败，请选中文字手动复制')}};field.append(b)})}
  if(step==='delivery'){
   const review=state.reviews[p.id]||{},panel=document.createElement('section');panel.className='panel box';panel.innerHTML=`<h2>交付检查 · ${esc(market)}</h2><p class="sub">导出已保存的文案和当前生成图片，包含中英文本、图片及审核状态。</p><div class="wb-checks">${[[hasCopy,'已填写标题'],[Boolean(copy.bullets?.trim()),'已填写五点描述'],[Boolean(copy.description?.trim()),'已填写产品描述'],[review.copy===true,'文案人工审核通过'],[review.images===true,'图片人工审核通过']].map(([ok,label])=>`<p>${ok?'✓':'○'} ${label}</p>`).join('')}</div><div class="actions"><button class="btn primary" id="wbExport" ${hasCopy?'':'disabled'}>下载文案＋生成图片 ZIP</button><button class="btn" id="wbReview">前往审核中心</button><button class="btn" id="wbImages">核对与下载图片</button></div>`;main.append(panel);panel.querySelector('#wbExport').onclick=exportProductDelivery;panel.querySelector('#wbReview').onclick=()=>go('reviews');panel.querySelector('#wbImages').onclick=()=>switchStep('visual');
  }
 }
 document.getElementById('crumb').textContent='产品档案 / Listing 工作台 / '+({product:'素材与洞察',copy:'Listing 文案',visual:'视觉套图',delivery:'交付'})[step];
};
if(['listing','images'].includes(view))render();
