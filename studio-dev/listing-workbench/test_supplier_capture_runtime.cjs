const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {pathToFileURL}=require('node:url');
const URL='https://detail.1688.com/offer/123.html';
async function run(views,{resume=false,valid=true,kept=false,reconnect=false,oldExists=false,createError=false,newTabUrl='about:blank',existing=false,entries,tabCount=1,openedBy='agent',bound=false}={}){
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'junfei-supplier-runtime-'));
 const actions=[];
 let params;
 const page={url:async()=>views[0]?.pageUrl||views[0]?.url,evaluate:async code=>typeof code==='string'?{url:URL,title:'Fixture product',attributes:valid?{'材质':'棉'}:{},images:[]}:views.shift(),goto:async url=>{
  if(reconnect){const durable=JSON.parse(await fs.readFile(params.output,'utf8'));assert.equal(durable.browser.spaceId,991);assert.equal(durable.reconnect.stage,'bound');assert.equal(durable.browser.reconnectMissing,undefined)}
  actions.push(['goto',url]);
 }};
 const task={spaceId:987,name:'fixture',ownership:'agent',tabs:async()=>kept?[{url:URL,page}]:[{label:'p1'}],page:()=>page,handOff:async()=>actions.push(['handoff']),adopt:async()=>{actions.push(['adopt']);return {label:'p1'}}};
 const existingName='Junfei 1688 serial collection reconnect '+'b'.repeat(32);
 global.taskSpace=async name=>{actions.push([existing?'attachTaskSpace':'taskSpace']);if(existing)assert.equal(name,991);if(reconnect){if(createError)throw Error('creation_ack_unknown');return {...task,spaceId:991,name:existing?existingName:name,tabs:async()=>Array.from({length:tabCount},()=>({label:'p1',url:newTabUrl,openedBy}))}}return task};
 global.listTaskSpaces=async()=>{actions.push(['listTaskSpaces']);return entries??(oldExists?[{id:987,name:'fixture'}]:existing?[{id:991,name:existingName,ownership:'agent'}]:[])};
 global.takeOverTaskSpace=async()=>{actions.push(['takeOver']);return task};
 global.claimTaskSpace=async()=>{actions.push(['claimKept']);return task};
 try{
  params={url:URL,resume,runId:'a'.repeat(32),browser:{spaceId:987,name:'fixture',label:'p1',...(kept?{keptByCollector:true,keptUrl:URL}:{}),...(reconnect?{reconnectMissing:true,reconnectFromRunId:'b'.repeat(32)}:{}),...(existing?{reconnectExistingCreationRunId:'b'.repeat(32)}:{}),...(bound?{spaceId:991,name:existingName,reconnectFromRunId:'c'.repeat(32),reconnectOriginalMissingBrowser:{spaceId:987,name:'fixture',label:'p1'},reconnectBoundCreationBrowser:{spaceId:991,name:existingName,label:'p1'}}:{})},output:path.join(root,'result.json'),collector:path.join(root,'collector.js')};
  await fs.writeFile(params.collector,'/* fixture only */');
  const runtime=await fs.readFile(path.join(__dirname,'supplier_capture_runtime.mjs'),'utf8');
  const entry=path.join(root,'run.mjs');await fs.writeFile(entry,'const params='+JSON.stringify(params)+';\n'+runtime);
  await import(pathToFileURL(entry).href);
  return {result:JSON.parse(await fs.readFile(params.output,'utf8')),actions};
 }finally{delete global.taskSpace;delete global.takeOverTaskSpace;delete global.claimTaskSpace;delete global.listTaskSpaces;await fs.rm(root,{recursive:true,force:true})}
}
test('a visible challenge pauses before any product-page navigation',async()=>{
 const {result,actions}=await run([{url:'https://sec.1688.com/challenge',blocked:true}]);
 assert.equal(result.status,'paused');assert.equal(result.reason,'login_or_verification');
 assert.deepEqual(actions,[['taskSpace'],['handoff']]);
});
test('a new page navigates once, then CAPTCHA hands control back without retry',async()=>{
 const {result,actions}=await run([{url:'about:blank',blocked:false},{url:URL,blocked:true}]);
 assert.equal(result.status,'paused');assert.deepEqual(actions,[['taskSpace'],['goto',URL],['handoff']]);
});
test('explicit resume reads the same product page without goto or reload',async()=>{
 const {result,actions}=await run([{url:URL+'?from=old',blocked:false},{url:URL,blocked:false}],{resume:true});
 assert.equal(result.status,'collected');assert.deepEqual(actions,[['takeOver']]);
 assert.equal(result.supplier.captureMethod,'ego-serial-browser');
});
test('resume on a different product stops and never navigates back silently',async()=>{
 const {result,actions}=await run([{url:'https://detail.1688.com/offer/999.html',blocked:false}],{resume:true});
 assert.equal(result.reason,'verify_original_product_page');assert.deepEqual(actions,[['takeOver']]);
});
test('incomplete data pauses and leaves the original page available',async()=>{
 const {result,actions}=await run([{url:URL,blocked:false},{url:URL,blocked:false}],{valid:false});
 assert.equal(result.reason,'incomplete_product_page');assert.deepEqual(actions,[['taskSpace'],['handoff']]);
});
test('a deliberately kept session reuses the exact retained tab and login',async()=>{
 const {result,actions}=await run([{url:URL,blocked:false},{url:URL,blocked:false}],{kept:true});
 assert.equal(result.status,'collected');assert.deepEqual(actions,[['claimKept'],['adopt']]);
 assert.equal(result.browser.keptByCollector,undefined);
});

test('explicit missing-space reconnect verifies absence, binds a new blank page durably, and visits original queued URL once',async()=>{
 const {result,actions}=await run([{url:'about:blank',blocked:false},{url:URL,blocked:false}],{resume:true,reconnect:true});
 assert.equal(result.status,'collected');assert.deepEqual(actions,[['listTaskSpaces'],['taskSpace'],['goto',URL]]);
 assert.equal(result.browser.spaceId,991);assert.equal(result.browser.name,'Junfei 1688 serial collection reconnect '+'a'.repeat(32));
 assert.equal(result.browser.reconnectMissing,undefined);assert.equal(result.reconnect.oldSpaceAbsent,true);
 assert.equal(result.reconnect.previousBrowser.spaceId,987);assert.equal(result.reconnect.previousRunId,'b'.repeat(32));
});

test('reconnect refuses an existing original space or a non-resume authorization before creating anything',async()=>{
 for(const options of [{resume:true,reconnect:true,oldExists:true},{reconnect:true}]){
  const {result,actions}=await run([] ,options);
  assert.equal(result.status,'paused');assert.ok(['missing_browser_still_exists','invalid_missing_browser_reconnect'].includes(result.reason));
  assert.equal(actions.some(a=>a[0]==='taskSpace'||a[0]==='goto'||a[0]==='takeOver'),false);
 }
});

test('unknown space creation consumes reconnect intent and never navigates',async()=>{
 const {result,actions}=await run([],{resume:true,reconnect:true,createError:true});
 assert.equal(result.reason,'creation_ack_unknown');assert.equal(result.reconnect.stage,'creating');
 assert.equal(result.browser.reconnectMissing,undefined);assert.deepEqual(actions,[['listTaskSpaces'],['taskSpace']]);
});

test('reconnect will not navigate a newly created nonblank page or challenge',async()=>{
 const changed=await run([],{resume:true,reconnect:true,newTabUrl:URL});
 assert.equal(changed.result.reason,'reconnect_blank_page_required');assert.deepEqual(changed.actions,[['listTaskSpaces'],['taskSpace']]);
 const blocked=await run([{url:'https://sec.1688.com/challenge',blocked:true}],{resume:true,reconnect:true});
 assert.equal(blocked.result.reason,'login_or_verification');assert.deepEqual(blocked.actions,[['listTaskSpaces'],['taskSpace'],['handoff']]);
});

test('observed chrome newtab is a native blank for first creation and exact existing-creation reconciliation',async()=>{
 for(const existing of [false,true]){
  const {result,actions}=await run([{url:'chrome://newtab/',blocked:false},{url:URL,blocked:false}],
   {resume:true,reconnect:true,existing,newTabUrl:'chrome://newtab/'});
  assert.equal(result.status,'collected');
  assert.deepEqual(actions,[['listTaskSpaces'],[existing?'attachTaskSpace':'taskSpace'],['goto',URL]]);
  assert.equal(result.reconnect.creationCalls,existing?0:1);
  assert.deepEqual(result.reconnect.createdSpace,{spaceId:991,name:result.browser.name});
  if(existing)assert.equal(result.reconnect.existingCreationRunId,'b'.repeat(32));
 }
});

test('existing creation must be unique and agent owned; no fallback creation or takeover',async()=>{
 const name='Junfei 1688 serial collection reconnect '+'b'.repeat(32);
 for(const entries of [[],[{id:991,name,ownership:'user'}],[{id:991,name,ownership:'agent'},{id:992,name,ownership:'agent'}]]){
  const {result,actions}=await run([],{resume:true,reconnect:true,existing:true,entries});
  assert.equal(result.reason,'existing_creation_not_uniquely_agent_owned');assert.deepEqual(actions,[['listTaskSpaces']]);
 }
});

test('existing creation rejects multiple tabs, remote pages, or nonagent tabs before any navigation',async()=>{
 for(const opts of [{tabCount:2},{newTabUrl:URL},{newTabUrl:'chrome://newtab/?query=notblank'},{openedBy:'unknown'}]){
  const {result,actions}=await run([],{resume:true,reconnect:true,existing:true,...opts});
  assert.equal(result.reason,'reconnect_blank_page_required');
  assert.deepEqual(actions,[['listTaskSpaces'],['attachTaskSpace']]);
 }
});

test('bound creation uses original missing identity and accepts observed tab/document native aliases without new creation',async()=>{
 const {result,actions}=await run([{url:'chrome://new-tab-page/',documentURL:'chrome://new-tab-page/',blocked:false},
  {url:URL,documentURL:URL,blocked:false}],{resume:true,reconnect:true,existing:true,bound:true,newTabUrl:'chrome://newtab/'});
 assert.equal(result.status,'collected');assert.deepEqual(actions,[['listTaskSpaces'],['attachTaskSpace'],['goto',URL]]);
 assert.equal(result.reconnect.creationCalls,0);assert.equal(result.reconnect.previousStage,'bound');
 assert.equal(result.reconnect.previousBrowser.spaceId,987);assert.equal(result.reconnect.previousRunId,'c'.repeat(32));
 assert.equal(result.reconnect.existingCreationRunId,'b'.repeat(32));assert.equal(result.browser.spaceId,991);
 assert.equal(result.browserDiagnostics.tabs[0].url,'chrome://newtab/');
 assert.equal(result.browserDiagnostics.observations[0].pageUrl,'chrome://new-tab-page/');
 assert.equal(result.browserDiagnostics.observations[0].documentURL,'chrome://new-tab-page/');
});

test('bound reconciliation stops for remote document, unknown failure, challenge, or changed existing-space identity',async()=>{
 for(const initial of [{url:'https://elsewhere.example/',blocked:false},{url:'chrome://new-tab-page/',blocked:true}]){
  const {result,actions}=await run([initial],{resume:true,reconnect:true,existing:true,bound:true,newTabUrl:'chrome://newtab/'});
  assert.equal(result.status,'paused');assert.equal(actions.some(a=>a[0]==='goto'||a[0]==='taskSpace'),false);
 }
 const name='Junfei 1688 serial collection reconnect '+'b'.repeat(32);
 const changed=await run([],{resume:true,reconnect:true,existing:true,bound:true,entries:[{id:992,name,ownership:'agent'}]});
 assert.equal(changed.result.reason,'bound_creation_identity_changed');assert.deepEqual(changed.actions,[['listTaskSpaces']]);
});
