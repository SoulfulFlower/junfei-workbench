// Compatibility adapter: retain the existing mount order and shared workspace hooks.
const mountBeforeColourSets=mountImageGeneration;
mountImageGeneration=function(){mountBeforeColourSets();mountColourVariants()};
// Focused work areas: retain original controls and their event handlers.
let visualLayoutTab='master';
const mountBeforeFocusedLayout=mountImageGeneration;
mountImageGeneration=function(){
 mountBeforeFocusedLayout();
 const host=document.getElementById('nativeVisualStudio'),asset=document.getElementById('assetInput')?.closest('section');if(!host||!asset)return;
 const fold=document.createElement('details');fold.className='panel box workspace-materials';
 const summary=document.createElement('summary');summary.textContent='补传商品实拍 · 关联变体颜色';asset.before(fold);fold.append(summary,asset);
 const colors=host.nextElementSibling;if(!colors?.classList.contains('colour-variant-panel'))return;
 const advanced=colors.querySelector('.colour-advanced');
 const nav=document.createElement('div');nav.className='workspace-modebar';nav.setAttribute('aria-label','图片制作方式');
 for(const [key,label]of [['master','母版套图 · 策划 / 生成 / 审核'],['colors','变体换色 · 复用母版']]){const b=document.createElement('button');b.className='btn';b.textContent=label;b.onclick=()=>select(key);b.dataset.mode=key;nav.append(b)}
 function select(key){
  visualLayoutTab=key;host.hidden=key!=='master';colors.hidden=key!=='colors';
  nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===key)));
 }
 fold.before(nav);advanced.append(fold);select(visualLayoutTab);
};
// One research entry: keywords and review insights share the same ASIN/site input.
function arrangeUnifiedResearch(){
 if(view!=='listing'||listingWorkspaceStep!=='product')return;
 const main=document.querySelector('.wb-main'),input=document.getElementById('competitorAsins'),research=input?.closest('section'),reviews=document.getElementById('buyerInsightsResult')?.closest('section');if(!main||!research||!reviews)return;
 let combined=main.querySelector('#unifiedResearch');
 if(!combined){
  combined=document.createElement('section');combined.id='unifiedResearch';combined.className='workspace-section';
  const heading=document.createElement('h2');heading.textContent='关键词与买家评论 · 联合 AI 分析';
  const intro=document.createElement('p');intro.className='sub';intro.style.margin='12px 0';intro.textContent='输入同站点竞品 ASIN，一次获取关键词和评论，分析流量词、买家痛点与卖点；结果自动供后续文案和图片策划使用。';
  combined.append(heading,intro);main.querySelector(':scope > .titlebar').after(combined);
  const next=document.createElement('button');next.type='button';next.className='link research-next';next.textContent='继续编辑 Listing 文案 →';next.onclick=()=>document.querySelector('[data-wb-step="copy"]')?.click();combined.append(next);
 }
 const next=combined.querySelector('.research-next');
 research.querySelector('h2').textContent='竞品 ASIN 与关键词';const intro=research.querySelector('h2 + p');if(intro)intro.hidden=true;
 const oldFold=research.parentElement?.tagName==='DETAILS'?research.parentElement:null;
 research.classList.add('research-subsection');combined.insertBefore(research,next);if(oldFold)oldFold.remove();
 reviews.classList.add('research-subsection');combined.insertBefore(reviews,next);
 if(!reviews.querySelector('.review-retry')){
  const retry=document.createElement('details');retry.className='review-retry';const summary=document.createElement('summary');summary.textContent='评论获取异常？展开单独重取 / 重试分析';retry.append(summary);
  const result=document.getElementById('buyerInsightsResult'),status=document.getElementById('buyerReviewStatus');
  for(const el of [...reviews.children])if(el!==result&&el!==status&&el.tagName!=='H2')retry.append(el);
  reviews.querySelector('h2').textContent='买家评论与 AI 洞察';reviews.append(retry);
 }
 const site=document.getElementById('competitorMarket'),reviewSite=document.getElementById('reviewMarket'),reviewInput=document.getElementById('reviewAsins');
 const sync=()=>{if(reviewSite.value!==site.value){reviewSite.value=site.value;reviewSite.onchange?.()}reviewInput.value=input.value};
 // Replace listeners on the persistent controls when the review panel is remounted.
 if(input._unifiedSync)input.removeEventListener('input',input._unifiedSync);if(site._unifiedSync)site.removeEventListener('change',site._unifiedSync);
 input._unifiedSync=site._unifiedSync=sync;input.addEventListener('input',sync);site.addEventListener('change',sync);sync();

}
const mountBuyerBeforeUnified=mountBuyerInsights;
mountBuyerInsights=function(initialMarket){mountBuyerBeforeUnified(initialMarket);arrangeUnifiedResearch()};
const renderBeforeUnifiedResearch=render;
render=function(){renderBeforeUnifiedResearch();arrangeUnifiedResearch()};
async function exportProductDelivery(button=document.getElementById('wbExport')){
 const p=product();if(!p)return;
 if(button){button.disabled=true;button.textContent='正在打包文案和图片…'}
 try{await flushWorkspace();const response=await fetch('/api/listing/export?productId='+encodeURIComponent(p.id));if(!response.ok){const error=await response.json();throw Error(error.error||'导出失败')}
 const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=(p.sku||p.id)+'-Listing与图片-备份.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);toast('已导出文案与图片备份，请查看下载文件');
 }catch(e){toast(e.message)}finally{if(button){button.disabled=false;button.textContent='下载文案＋生成图片 ZIP'}}
}

const renderBeforeSku=render;
render=function(){renderBeforeSku();if(!['listing','images'].includes(view))return;const p=product(),context=document.querySelector('.wb-context');if(!p||!context)return;
 const row=document.createElement('div');row.className='workspace-sku';const label=document.createElement('span');label.textContent='产品 SKU：'+(p.sku||'刷新后自动生成');const edit=document.createElement('button');edit.className='link';edit.textContent='修改 SKU';edit.onclick=()=>{const value=prompt('产品 SKU（员工拼音缩写＋日期时间，不加分隔符，可手动修改）',p.sku||'');if(value===null)return;const sku=value.trim();if(!/^[A-Za-z0-9_-]{1,100}$/.test(sku))return toast('SKU限1–100位字母、数字、横线或下划线');if(state.products.some(x=>x.id!==p.id&&x.sku===sku))return toast('此SKU已被其他产品使用');p.sku=sku;persist();render();toast('产品SKU已保存')};row.append(label,edit);context.append(row);
};

const renderBeforeExportColour=render;
render=function(){renderBeforeExportColour();if(view!=='listing'||listingWorkspaceStep!=='delivery')return;const button=document.getElementById('wbExport'),p=product();if(!button||!p)return;
 const label=document.createElement('label');label.textContent='导出图片颜色（颜色＋编号）：';label.style.cssText='display:block;margin:16px 0';const input=document.createElement('input');input.value=p.masterColor||'';input.placeholder='例如：褐色；留空按主体素材识别';input.setAttribute('aria-label','导出图片颜色');input.onchange=()=>{p.masterColor=input.value.trim().slice(0,60);persist()};label.append(input);button.closest('.actions').before(label);
};

// Saved images belong only to the visual step of the product workspace.
const renderBeforeSavedImages=render;
render=function(){
 renderBeforeSavedImages();
 if(view!=='images')return;
 const main=document.querySelector('.wb-main'),p=product();if(!main||!p)return;
 const panel=document.createElement('section');panel.className='panel box';panel.id='savedProductImages';panel.style.marginBottom='20px';
 const heading=document.createElement('h2');heading.textContent='已生成图片';
 const status=document.createElement('p');status.className='sub';status.textContent='正在读取本产品已保存的成图…';
 const results=document.createElement('div');results.style.cssText='display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px';
 panel.append(heading,status,results);main.querySelector(':scope > .titlebar').after(panel);
 void (async()=>{try{
  const accountId=signedUser?.id;
  const [response,jobs]=await Promise.all([fetch('/api/studio/view?productId='+encodeURIComponent(p.id)),imageApi('jobs')]);
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'图片读取失败');if(!panel.isConnected||signedUser?.id!==accountId||product()?.id!==p.id)return;
  const saved=[];
  for(const [kind,plan] of Object.entries(data.sets||{}))for(const [i,item] of (plan.images||[]).entries()){
   if(item.final_url)saved.push({url:item.final_url,name:(kind==='gallery'?'产品套图':'A+图片')+' '+(i+1),reviewed:item.human_reviewed});
  }
  for(const job of jobs.jobs||[])if(job.productId===p.id&&job.status==='completed')for(const [i,url] of (job.images||[]).entries()){
   if(url)saved.push({url,name:(job.slot||'生成图片')+' '+(i+1),reviewed:false});
  }
  const seen=new Set(),unique=saved.filter(item=>{if(seen.has(item.url))return false;seen.add(item.url);return true});
  for(const item of unique){
   const card=document.createElement('div'),a=document.createElement('a');a.href=item.url;a.target='_blank';a.rel='noopener';
   const image=document.createElement('img');image.src=item.url;image.alt=item.name;image.style.cssText='width:100%;height:180px;object-fit:contain;background:#f5f7fa;border-radius:8px';
   image.onerror=()=>{label.textContent=image.alt+' · 加载失败，请刷新或重新登录'};
   const label=document.createElement('p');label.className='sub';label.textContent=image.alt+' · '+(item.reviewed?'已人工确认':'待人工核对');
   a.append(image);card.append(a,label);results.append(card);
  }
  heading.textContent='已生成图片 · '+unique.length+' 张';status.textContent=unique.length?'点击图片查看原图；可在下方继续编辑套图和查看换色结果。':'本产品尚无已保存的成图，可在下方制作。';
 }catch(error){if(panel.isConnected)status.textContent='读取失败：'+error.message}})();
};

// Preserve material-binding mount order after the focused layout wrapper.
const mountBeforeColourBindings=mountImageGeneration;
mountImageGeneration=function(){mountBeforeColourBindings();mountColourBindings()};
