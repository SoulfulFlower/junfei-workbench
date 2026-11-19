// Reusable normal-UI research. No API, model, archive mutation or supplier detail access.
const fs = await import('node:fs/promises');
const {createHash} = await import('node:crypto');
export function assertResearchIdentity(ui, expected) {
  if (new URL(ui.url).hostname !== 'www.amazon.com' || !ui.delivery?.includes('75020') || ui.asin !== expected.candidateAsin) throw Error('Research candidate / US75020 scope mismatch');
  if (expected.query && ui.query !== expected.query) throw Error('SellerSprite query mismatch');
  if (expected.mode && ui.mode !== expected.mode) throw Error('SellerSprite mode mismatch');
}
export async function readNativeKeywordState(page) {
  return await page.evaluate(() => ({url:location.href,asin:document.querySelector('#ASIN')?.value,delivery:document.querySelector('#glow-ingress-line2')?.innerText,query:document.querySelector('input[placeholder="关键词 或 ASIN"],input[placeholder="主人~请输入子ASIN"],input[placeholder="主人~请输入关键词"]')?.value,mode:document.querySelector('.nav-item-ext.active a')?.innerText==='关键词挖掘'?'mining':document.querySelector('.nav-item-ext.active a')?.innerText==='关键词反查'?'reverse':null,loading:/卖家精灵插件查询中/.test(document.body.innerText),noData:/暂无数据|未查询到相关数据|未查到相关数据|未能找到相关关键词|未能找到相关流量词/.test(document.body.innerText.slice(0,2000)),declaredTotal:document.body.innerText.match(/为您找到\s*([\d,]+)\s*条结果/)?.[1]||null,rowScope:'currently rendered virtual table rows only; use original native XLSX for full loaded/exported records',headers:[...document.querySelectorAll('table.vxe-table--header th')].map(e=>e.innerText),visibleRows:[...document.querySelectorAll('table.vxe-table--body tbody tr')].map(e=>[...e.querySelectorAll('td')].map(c=>c.innerText)).filter(c=>c[2]?.trim()),mainText:[...document.querySelectorAll('main')].filter(e=>e.querySelector('table.vxe-table--body')).map(e=>e.innerText.slice(0,30000)).join('\n'),challenge:Boolean(document.querySelector('#captchacharacters,form[action*="validateCaptcha"]'))||/robot check|verify you are human/i.test(document.title)}));
}
export async function collectNativeReverse(page, expected, options) {return await collectNativeKeywordTable(page,{candidateAsin:expected.candidateAsin,query:expected.queryAsin,sourceAsin:expected.queryAsin,mode:'reverse'},options);}
export async function collectNativeMining(page, expected, options) {return await collectNativeKeywordTable(page,{candidateAsin:expected.candidateAsin,query:expected.keyword,sourceAsin:expected.sourceAsin||expected.candidateAsin,mode:'mining'},options);}
async function collectNativeKeywordTable(page, expected, options) {
  const {base,prefix,start=false,exportFile=true,timeoutMs=45000}=options;
  if(!base||!(/^(?:[A-Za-z]:[\\/]|\/)/.test(base))||!(/^[A-Za-z0-9_-]+$/.test(prefix)))throw Error('Absolute output directory and safe research prefix required');
  const initial=await readNativeKeywordState(page);assertResearchIdentity(initial,{candidateAsin:expected.candidateAsin,mode:expected.mode});
  if(initial.challenge)throw Error('Human verification required; stop this space');
  const beforeFingerprint=JSON.stringify(initial.visibleRows);let dispatch,transition,transitionError;
  if(start){
    if(expected.mode==='reverse'&&!/^[A-Z0-9]{10}$/.test(expected.query))throw Error('Expected real ASIN required');
    const selector=expected.mode==='reverse'?'loc=css:input[placeholder="关键词 或 ASIN"],input[placeholder="主人~请输入子ASIN"]':'loc=css:input[placeholder="主人~请输入关键词"]';
    await page.fill(selector,expected.query);
    dispatch=await page.press(selector,'Enter');
    try{await page.waitForFunction(prev=>/卖家精灵插件查询中/.test(document.body.innerText)||JSON.stringify([...document.querySelectorAll('table.vxe-table--body tbody tr')].map(e=>[...e.querySelectorAll('td')].map(c=>c.innerText)).filter(c=>c[2]?.trim()))!==prev, beforeFingerprint,{timeout:10000});}catch(e){transitionError=String(e);}
    transition=await readNativeKeywordState(page);
  }
  let waitError;try{await page.waitForFunction(()=>!/卖家精灵插件查询中/.test(document.body.innerText)&&Boolean(document.querySelector('table.vxe-table--body')||/暂无数据|未查询到相关数据|未查到相关数据|未能找到相关关键词|未能找到相关流量词/.test(document.body.innerText.slice(0,2000))),undefined,{timeout:Math.min(timeoutMs,45000)});}catch(e){waitError=String(e);}
  const ui=await readNativeKeywordState(page);assertResearchIdentity(ui,expected);
  const result={at:new Date().toISOString(),marketplace:'US',candidateAsin:expected.candidateAsin,sourceAsin:expected.sourceAsin,query:expected.query,mode:expected.mode,source:'normal SellerSprite plugin UI',dispatch,transition,transitionError,waitError,status:ui.loading?'pending':transitionError?'unresolved':ui.visibleRows.length?'collected':ui.noData?'empty':'unresolved',ui};
  result.dataStatus=result.status;
  if(result.dataStatus==='collected')result.status=exportFile?'export_pending':'observed';
  await fs.writeFile(base+prefix+'.json',JSON.stringify(result,null,2));
  if(result.dataStatus==='collected'&&exportFile){
    try {
      await page.evaluate(()=>{const b=[...document.querySelectorAll('button')].filter(e=>e.innerText.trim()==='导出');if(b.length!==1)throw Error('Unique native export button required');b[0].scrollIntoView({block:'center'});});
      await page.waitForFunction(()=>{const b=[...document.querySelectorAll('button')].find(e=>e.innerText.trim()==='导出');if(!b)return false;const r=b.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return r.width>0&&r.height>0&&!!hit&&(hit===b||b.contains(hit));},undefined,{timeout:5000});
      const point=await page.evaluate(()=>{const b=[...document.querySelectorAll('button')].find(e=>e.innerText.trim()==='导出'),r=b.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);if(!(hit===b||b.contains(hit)))throw Error('Native export obstructed');return {x,y,query:document.querySelector('input[placeholder="关键词 或 ASIN"],input[placeholder="主人~请输入子ASIN"],input[placeholder="主人~请输入关键词"]')?.value};});if(point.query!==expected.query)throw Error('Native export query changed');result.exportHitProof=point;
      let error;const pending=page.waitForEvent('download',{timeout:30000}).catch(e=>{error=String(e);return null});
      try{result.exportReceipt=await page.mouse.click(point.x,point.y,{label:'export actual keyword table'});}catch(e){await pending;throw e;}const dl=await pending;
      if(dl){const name=dl.suggestedFilename().replace(/[\\/:*?"<>|]/g,'_');if(!name.endsWith('.xlsx')||(expected.mode==='reverse'&&!name.includes(expected.query)))throw Error('Native download filename / query mismatch');const path=base+'exports/'+prefix+'-'+name;await dl.saveAs(path);const bytes=await fs.readFile(path);if(bytes.length<4||bytes.subarray(0,4).toString('hex')!=='504b0304')throw Error('Native XLSX archive signature missing');result.export={filename:name,path,url:dl.url(),bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};result.status='collected';}else result.exportError=error;
    } catch(e) {result.exportError=String(e);}
  }
  await fs.writeFile(base+prefix+'.json',JSON.stringify(result,null,2));await page.screenshot({path:base+prefix+'.png'});
  return result;
}
export async function captureVisibleReviews(page, expectedAsin) {
  const ui=await page.evaluate(()=>({url:location.href,asin:document.querySelector('#ASIN')?.value,delivery:document.querySelector('#glow-ingress-line2')?.innerText,summary:document.querySelector('#reviewsMedley')?.innerText||null,items:[...document.querySelectorAll('#reviewsMedley [id^="customer_review-"],#reviewsMedley [data-hook="review"]')].map(e=>({id:e.id,text:e.innerText})).filter(x=>x.text),nativeRating:document.querySelector('#averageCustomerReviews')?.innerText||null,moreReviewLinks:[...document.querySelectorAll('#reviewsMedley a')].filter(e=>/review|评价|评论/i.test(e.innerText)).map(e=>({text:e.innerText,url:e.href})).slice(0,10)}));
  assertResearchIdentity(ui,{candidateAsin:expectedAsin});return {at:new Date().toISOString(),marketplace:'US',sourceAsin:expectedAsin,source:'Amazon visible native product review section',...ui};
}
