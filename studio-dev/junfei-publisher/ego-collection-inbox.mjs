// Real ERP 产品 / 采集列表 transport, through its observed 商品添加 form.
// The ERP supplies authentication; no tokens or headers are read or copied.
export function inboxPayload(input,urls){
  const g=input.goods,pageUrl=input.destination.workbenchUrl;
  const u=new URL(pageUrl);
  if(!['http:','https:'].includes(u.protocol)||u.searchParams.get('product')!==input.productId||u.username||u.password)throw Error('成品来源页面身份不符');
  const image=n=>{const a=input.assets[n],url=a&&urls[a.sha256];if(!url||!/^https:\/\/junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com\//.test(url))throw Error('采集图片缺少已核对的ERP地址');return url;};
  if(input.mode!=='draft'||input.goodsItems.length!==new Set(input.goodsItems.map(v=>v.sku)).size)throw Error('采集子SKU集合无效');
  if(!/^\d+(\.\d{1,2})?$/.test(String(input.destination.purchaseCny))||Number(input.destination.purchaseCny)<=0)throw Error('采集列表需要有依据的人民币采购价，不能使用美元售价代替');
  const items=input.goodsItems.map(v=>{
    if(!v.color||!v.size||v.imageIndices.length!==7||new Set(v.imageIndices).size!==7)throw Error('采集颜色尺码或套图不完整');
    const images=v.imageIndices.map(image);
    return{sku:v.sku,variation:{Color:v.color,Size:v.size},main_image:images[0],images,price:String(input.destination.purchaseCny),quantity:String(v.quantity)};
  });
  return{title:g.title,source_url:pageUrl,brand:g.brand,manufacturer:g.manufacturer,manufacturer_number:'',
    describe:['Highlights\n'+g.highlights,'Bullet Points\n'+g.bullets.join('\n'),'Description\n'+g.description,'Search Terms\n'+g.terms].join('\n\n'),
    keywords:g.terms,bullet_point:g.bullets,is_variation:1,variation_theme:'color-size',parent_sku:g.parentSku,
    images:input.assets.map((_,i)=>image(i)),items};
}

export async function collectionRows(page,input){
  await page.evaluate(()=>{
    if(window.__inboxLookup)throw Error('已有采集列表查询');
    const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();
    window.__inboxLookup={open,send,result:null};
    XMLHttpRequest.prototype.open=function(method,url,...args){targets.set(this,String(method).toUpperCase()==='GET'&&new URL(url,location.href).href.startsWith('https://app.junfeikuajing.com/api/goods/index?'));return open.call(this,method,url,...args);};
    XMLHttpRequest.prototype.send=function(body){if(targets.get(this))this.addEventListener('loadend',()=>{try{window.__inboxLookup.result={status:this.status,body:JSON.parse(this.responseText)};}catch{}},{once:true});return send.call(this,body);};
  });
  let response;
  try{
    await page.fill('input[placeholder="关键词搜索"]',input.goods.title);
    await page.click('loc=role:button[name="搜索"]',{label:'核对成品来源与真实采集编号'});
    await page.waitForFunction(()=>window.__inboxLookup?.result,undefined,{timeout:10000});
    response=await page.evaluate(()=>window.__inboxLookup.result);
  }finally{await page.evaluate(()=>{const s=window.__inboxLookup;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__inboxLookup;}});}
  if(response.status!==200||response.body.code!==0||!Array.isArray(response.body.data?.list?.data)||response.body.data.list.last_page>1)throw Error('采集列表查询未完成或匹配不唯一');
  return response.body.data.list.data.filter(r=>r.title===input.goods.title).map(r=>({...r,id:String(r.id),sourceMatch:r.source_url===input.destination.workbenchUrl}));
}

export async function collectInbox(page,input,urls,record,persist){
  const payload=inboxPayload(input,urls);
  await page.goto('https://www.junfeikuajing.com/#/product/collect');
  await page.waitForSelector('input[placeholder="关键词搜索"]',{state:'visible'});
  let rows=(await collectionRows(page,input)).filter(r=>r.sourceMatch);
  if(rows.length>1)throw Error('ERP采集列表存在同名多条记录，需核对来源，不重复采集');
  if(rows.length===1){
    if(record.collection?.id&&record.collection.id!==rows[0].id)throw Error('采集列表编号与原回执不符');
    if(!rows[0].sourceMatch)throw Error('同名采集记录的成品来源未核对，不覆盖或重复采集');
    record.collection={...record.collection,id:rows[0].id,status:'list_verified',row:rows[0],url:'https://www.junfeikuajing.com/#/product/collect'};await persist();return;
  }
  if(record.collection?.id)throw Error('原采集编号暂未找到，保留已有草稿，不重新采集或转入');
  if(record.collection?.status==='submit_unknown'){
    const r=record.collection.response;
    if(r?.httpStatus===200&&r.code!==0&&/必填|不能为空|校验/.test(r.message||''))record.collection.status='rejected_validation';
    else throw Error('上次采集提交结果尚未找到，不重发');
  }
  const history=record.collection?[...(record.collection.history||[]),{status:record.collection.status,response:record.collection.response,payload:record.collection.payload}]:[];
  const submissions=record.collection?.submissions||0;
  record.collection={status:'preparing',history,sourceUrl:payload.source_url,createdAt:new Date().toISOString(),submissions};await persist();
  await page.click('loc=role:button[name="商品添加"]',{label:'打开ERP真实采集新增入口'});
  await page.waitForSelector('input[placeholder="请输入品牌名"]',{state:'visible'});
  const fields=await page.evaluate(values=>{
    if(location.hash!=='#/product/add')throw Error('ERP采集新增页面身份变化');
    const set=(e,v)=>{Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,v);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
    for(const [label,value]of Object.entries(values)){
      const found=[...document.querySelectorAll('.base-info .el-form-item')].filter(e=>e.querySelector('label')?.innerText.trim()===label);
      if(found.length!==1)throw Error('采集基础字段不唯一: '+label);const e=found[0].querySelector('input,textarea');if(!e)throw Error('基础字段缺失');set(e,value);
    }
    const groups=[...document.querySelectorAll('.variants-attr-ctn>div')];if(groups.length!==2)throw Error('颜色尺码输入结构变化');
    return groups.map((group,index)=>{const e=[...group.querySelectorAll('input')].filter(e=>!e.readOnly&&!e.disabled);if(e.length!==1)throw Error('变体属性输入不唯一');e[0].setAttribute('data-collection-attribute',String(index));return '[data-collection-attribute="'+index+'"]';});
  },{'商品来源':payload.source_url,'商品标题':payload.title,'品牌':payload.brand,'制造商':payload.manufacturer,'产品描述':payload.describe});
  const first=input.goodsItems[0];await page.fill(fields[0],first.color);await page.press(fields[0],'Enter');await page.fill(fields[1],first.size);await page.press(fields[1],'Enter');
  await page.waitForFunction(()=>document.querySelector('.table-ctn .el-table__body tr'),undefined,{timeout:5000});
  await page.evaluate(()=>{
    if(window.__finishedInboxHook)throw Error('已有采集请求观察');
    const originalOpen=XMLHttpRequest.prototype.open,originalSend=XMLHttpRequest.prototype.send,targets=new WeakMap();
    const state={originalOpen,originalSend,sent:false,response:null,error:null};window.__finishedInboxHook=state;
    XMLHttpRequest.prototype.open=function(method,url,...args){targets.set(this,String(method).toUpperCase()==='POST'&&new URL(url,location.href).href==='https://app.junfeikuajing.com/api/goods/create');return originalOpen.call(this,method,url,...args);};
    XMLHttpRequest.prototype.send=function(body){
      if(!targets.get(this))return originalSend.call(this,body);
      if(state.sent)throw Error('禁止重复创建本次采集记录');
      const original=JSON.parse(body),payload=window.__finishedInboxPayload;
      if(original.title!==payload.title||original.source_url!==payload.source_url||!original.items?.length)throw Error('采集表单身份不符');
      state.sent=true;
      this.addEventListener('loadend',()=>{let result={};try{result=JSON.parse(this.responseText);}catch{}state.response={httpStatus:this.status,code:result.code,message:result.message,data:result.data};},{once:true});
      return originalSend.call(this,JSON.stringify(payload));
    };
  });
  await page.evaluate(payload=>{window.__finishedInboxPayload=payload;},payload);
  record.collection.status='submit_unknown';record.collection.payload=payload;record.collection.submissions++;await persist();
  try{
    await page.click('.amazon-edit-detail-container .top-bar button:has-text("保存")',{label:'采集成品到ERP采集列表'});
    await page.waitForFunction(()=>window.__finishedInboxHook?.response,undefined,{timeout:25000});
    const response=await page.evaluate(()=>window.__finishedInboxHook.response);record.collection.response=response;await persist();
    if(response.httpStatus!==200||response.code!==0){if(response.httpStatus===200&&/必填|不能为空|校验/.test(response.message||'')){record.collection.status='rejected_validation';await persist();}throw Error('ERP采集保存未返回成功：'+(response.message||response.httpStatus));}
  }finally{await page.evaluate(()=>{const h=window.__finishedInboxHook;if(h){XMLHttpRequest.prototype.open=h.originalOpen;XMLHttpRequest.prototype.send=h.originalSend;delete window.__finishedInboxHook;delete window.__finishedInboxPayload;}});}
  await page.waitForFunction(()=>location.hash==='#/product/collect',undefined,{timeout:15000});
  await page.waitForFunction(title=>[...document.querySelectorAll('.el-table__body-wrapper tr')].some(r=>r.getBoundingClientRect().width&&r.innerText.includes(title)),input.goods.title,{timeout:15000});
  rows=(await collectionRows(page,input)).filter(r=>r.sourceMatch);
  if(rows.length!==1||!rows[0].sourceMatch)throw Error('采集列表未找到唯一的本款成品来源记录');
  record.collection={...record.collection,id:rows[0].id,status:'list_verified',row:rows[0],url:'https://www.junfeikuajing.com/#/product/collect'};await persist();
}
