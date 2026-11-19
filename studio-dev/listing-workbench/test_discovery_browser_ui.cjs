const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 const calls=[],shown=[],toasts=[],elements={};
 for(const id of ['discoveryBrowserPanel','discoveryBrowserTarget','discoveryBrowserCapture','discoveryBrowserCheck','discoveryBrowserRefresh','discoveryBrowserInfo','discoveryBrowserHistory','discoveryBrowserReceipt','discoveryBrowserSave','discoveryStoreTarget','discoveryStoreCapture','discoveryKeywordTarget','discoveryKeywordPhrase','discoveryKeywordPrepare','discoveryKeywordSave','discoveryKeywordInfo','discoveryKeywordPreview','discoverySearchTarget','discoverySearchCapture','discoverySearchPhrase','discoveryPlanMaxActions','discoveryPlanMaxRounds','discoveryPlanPrepare','discoveryPlanInfo','discoveryPlanPreview','discoveryFamilyTarget','discoveryFamilyCapture','discoveryFamilyAssess','discoveryFamilyInfo','discoveryFamilyAssessment','discoveryRunInspect','discoveryRunInfo','discoveryRunInspection'])
  elements[id]={value:'0',disabled:false,textContent:'',innerHTML:'',children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)}};
 const report={cycleId:'cycle',revision:2,events:[{id:'keyword-1',kind:'keyword',marketplace:'US',phrase:'Cotton Travel'}, {id:'search-1',kind:'search',marketplace:'US',products:[{asin:'B012345678',title:'Visible product'}]},
  {id:'seller-1',kind:'seller',sellerId:'A1SELLER',sellerName:'Visible seller',marketplace:'US'},
  {id:'store-1',kind:'store',status:'captured',sellerId:'A1SELLER',marketplace:'US',products:[{asin:'B098765432',title:'Cotton Travel Bags'}]}]};
 const context=vm.createContext({view:'selection',signedUser:{id:1},selectionEpoch:3,crypto:{randomUUID:()=> '00000000-0000-0000-0000-000000000001'},
  document:{getElementById:id=>elements[id],createElement:()=>({})},
  selectionEscape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  discoveryOwnerCurrent:(owner,epoch)=>owner===context.signedUser&&epoch===context.selectionEpoch&&context.view==='selection',
  discoveryShow:r=>shown.push(r),discoveryHistory:async()=>{},toast:m=>toasts.push(m)});
 vm.runInContext(fs.readFileSync(__dirname+'/discovery-browser-ui.js','utf8'),context);
 const receipt={captureId:'capture-00000000-0000-0000-0000-000000000001',status:'captured',trust:'unverified_observation',
  preparedBatch:{cycleId:'cycle',expectedRevision:2,events:[{id:'seller-1',kind:'seller',parentId:'search-1',asin:'B012345678'}]}};
 context.selectionApi=async(path,data)=>{calls.push({path,data});return path.endsWith('/captures')?{items:[]}:receipt};
 context.discoveryBrowserMount(report,context.signedUser,3);
 return{context,report,receipt,calls,shown,toasts,elements};
}
test('mount does not execute browser or write evidence; only search products are targets',()=>{
 const f=fixture();assert.equal(f.calls.length,0);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
 const targets=f.context.discoveryBrowserTargets({...f.report,events:[...f.report.events,{kind:'store',products:[{asin:'OTHER'}]}]});
 assert.equal(targets.length,1);assert.match(f.elements.discoveryBrowserPanel.innerHTML,/不接管/);assert.match(f.elements.discoveryBrowserPanel.innerHTML,/待核实/);
});
test('explicit capture dispatches once with pinned parent revision then waits for save',async()=>{
 const f=fixture();let release;
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const first=f.elements.discoveryBrowserCapture.onclick(),second=f.elements.discoveryBrowserCapture.onclick();
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].path,'/api/discovery/capture-seller');
 assert.equal(f.calls[0].data.expectedRevision,2);assert.equal(f.calls[0].data.parentId,'search-1');
 release(f.receipt);await Promise.all([first,second]);
 assert.equal(f.elements.discoveryBrowserSave.disabled,false);assert.equal(f.calls.length,1);
});
test('prepared capture saves only to discovery ledger, never starts selection or production',async()=>{
 const f=fixture();await f.elements.discoveryBrowserCapture.onclick();await f.elements.discoveryBrowserSave.onclick();
 assert.deepEqual(f.calls.map(x=>x.path),['/api/discovery/capture-seller','/api/discovery/ingest']);
 assert.equal(f.calls[1].data.expectedRevision,2);assert.equal(f.shown.length,1);
});
test('network uncertainty blocks recapture and checks same receipt without POST retry',async()=>{
 const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('connection lost')};
 await f.elements.discoveryBrowserCapture.onclick();await f.elements.discoveryBrowserCapture.onclick();
 assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserCapture.disabled,true);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {captureId:f.receipt.captureId,status:'execution_unknown',reason:'timeout'}};
 await f.elements.discoveryBrowserCheck.onclick();await f.elements.discoveryBrowserCapture.onclick();
 assert.equal(f.calls.length,2);assert.match(f.calls[1].path,/^\/api\/discovery\/capture\?id=capture-/);assert.equal(f.calls[1].data,undefined);
 assert.equal(f.elements.discoveryBrowserSave.disabled,true);
});
test('blocked captured result does not save or treat missing seller as nonexistent',async()=>{
 const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {captureId:f.receipt.captureId,status:'blocked',reason:'visible_sold_by_link_not_found'}};
 await f.elements.discoveryBrowserCapture.onclick();await f.elements.discoveryBrowserSave.onclick();
 assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.match(f.elements.discoveryBrowserInfo.textContent,/未形成可保存证据/);
});
test('changed account and navigation discard late capture preview',async()=>{
 for(const change of [f=>{f.context.signedUser={id:2}},f=>{f.context.view='listing'},f=>{f.context.selectionEpoch=4}]){
  const f=fixture();let release;f.context.selectionApi=async()=>new Promise(r=>release=r);
  const p=f.elements.discoveryBrowserCapture.onclick();change(f);release(f.receipt);await p;
  assert.equal(f.elements.discoveryBrowserReceipt.textContent,'');await f.elements.discoveryBrowserSave.onclick();assert.equal(f.shown.length,0);
 }
});
test('new report mount invalidates old callbacks and response even under same account',async()=>{
 const f=fixture();let release;f.context.selectionApi=async()=>new Promise(r=>release=r);
 const p=f.elements.discoveryBrowserCapture.onclick(),oldSave=f.elements.discoveryBrowserSave.onclick;
 f.context.discoveryBrowserMount({...f.report,cycleId:'other'},f.context.signedUser,3);
 release(f.receipt);await p;await oldSave();
 assert.equal(f.elements.discoveryBrowserReceipt.textContent,'');assert.equal(f.shown.length,0);
});
test('history read of other cycle cannot expose save for current report',async()=>{
 const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[{captureId:'previous',status:'captured'}]}:{...f.receipt,captureId:'previous',preparedBatch:{...f.receipt.preparedBatch,cycleId:'other'}}};
 await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick();
 assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.calls.every(x=>!x.data),true);
});
test('stale save never updates expected revision or automatically retries',async()=>{
 const f=fixture();await f.elements.discoveryBrowserCapture.onclick();
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('stale revision')};
 await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,2);assert.equal(f.calls[1].data.expectedRevision,2);assert.deepEqual(f.toasts,['stale revision']);
});
test('no search targets or crypto support cannot invoke browser',async()=>{
 const f=fixture();f.context.discoveryBrowserMount({...f.report,events:[]},f.context.signedUser,3);
 await f.elements.discoveryBrowserCapture.onclick();assert.equal(f.calls.length,0);
 f.context.discoveryBrowserMount(f.report,f.context.signedUser,3);f.context.crypto={};
 await f.elements.discoveryBrowserCapture.onclick();assert.equal(f.calls.length,0);
});
test('all observed text is escaped or assigned textContent',async()=>{
 const f=fixture();f.report.events.find(e=>e.kind==='search').products[0].title='<img src=x onerror=bad>';
 f.context.discoveryBrowserMount(f.report,f.context.signedUser,3);assert.doesNotMatch(f.elements.discoveryBrowserPanel.innerHTML,/<img/);
 assert.match(f.elements.discoveryBrowserPanel.innerHTML,/&lt;img/);
 const receipt={...f.receipt,reason:'<script>bad</script>'};f.context.selectionApi=async()=>receipt;
 await f.elements.discoveryBrowserCapture.onclick();assert.match(f.elements.discoveryBrowserReceipt.textContent,/<script>/);assert.equal(f.elements.discoveryBrowserReceipt.innerHTML,'');
});

test('invalidating a report immediately disables old controls and explains pending capture',()=>{
 const f=fixture();f.context.discoveryBrowserInvalidate();
 for(const id of ['discoveryBrowserTarget','discoveryBrowserCapture','discoveryBrowserCheck','discoveryBrowserRefresh','discoveryBrowserSave'])assert.equal(f.elements[id].disabled,true);
 assert.match(f.elements.discoveryBrowserInfo.textContent,/回执/);assert.match(f.elements.discoveryBrowserInfo.textContent,/重新选择/);
 f.elements.discoveryBrowserCapture.onclick();assert.equal(f.calls.length,0);
});

function storeReceipt(f){return {...f.receipt,captureKind:'store',preparedBatch:{cycleId:'cycle',expectedRevision:2,events:[{id:'captured-store',kind:'store',status:'captured',parentId:'seller-1',sellerId:'A1SELLER',marketplace:'US',products:[{asin:'B098765432',title:'Cotton Travel Bags'}]}]}}}
function keywordReceipt(){return {status:'prepared',readOnly:true,sourceKind:'seller_listing_card',preparedBatch:{cycleId:'cycle',expectedRevision:2,events:[{id:'keyword-new',kind:'keyword',parentId:'store-1',asin:'B098765432',sourceTitle:'Cotton Travel Bags',phrase:'Cotton Travel'}]}}}
function setPhrase(f){f.elements.discoveryKeywordPhrase.value='Cotton Travel';f.elements.discoveryKeywordPhrase.oninput()}

test('store and keyword controls use only saved, matching predecessor observations',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);assert.equal(f.elements.discoveryKeywordPhrase.value,'');
 const mixed={events:[{id:'bad',kind:'keyword',sellerId:'FAKE'},...f.report.events,{id:'inaccessible',kind:'store',status:'inaccessible',products:[{asin:'FAKE'}]}]};
 assert.deepEqual(JSON.parse(JSON.stringify(f.context.discoveryStoreTargets(mixed))).map(t=>t.parentId),['seller-1']);
 assert.deepEqual(JSON.parse(JSON.stringify(f.context.discoveryKeywordTargets(mixed))).map(t=>t.asin),['B098765432']);
 f.context.discoveryBrowserMount({...f.report,events:[f.report.events.find(e=>e.kind==='search')]},f.context.signedUser,3);
 await f.elements.discoveryStoreCapture.onclick();setPhrase(f);await f.elements.discoveryKeywordPrepare.onclick();assert.equal(f.calls.length,0);
});
test('store capture sends exact pinned seller payload once and separately saves actual products',async()=>{
 const f=fixture();let release;
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const a=f.elements.discoveryStoreCapture.onclick(),b=f.elements.discoveryStoreCapture.onclick(),c=f.elements.discoveryBrowserCapture.onclick();
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].path,'/api/discovery/capture-store');
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].data)),{captureId:f.receipt.captureId,cycleId:'cycle',expectedRevision:2,parentId:'seller-1',sellerId:'A1SELLER'});
 release(storeReceipt(f));await Promise.all([a,b,c]);assert.equal(f.elements.discoveryBrowserSave.disabled,false);
 assert.match(f.elements.discoveryBrowserInfo.textContent,/实际可见店铺商品 1 条/);assert.match(f.elements.discoveryBrowserSave.textContent,/店铺商品/);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {...f.report,revision:3}};
 await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,2);assert.equal(f.calls[1].path,'/api/discovery/ingest');
 assert.equal(f.calls[1].data.events[0].products[0].title,'Cotton Travel Bags');assert.equal(f.shown.length,1);
});
test('store capture refuses mismatched kind, seller, parent, revision and empty products',async()=>{
 for(const mutate of [r=>{delete r.captureKind},r=>{r.preparedBatch.events[0].sellerId='OTHER'},r=>{r.preparedBatch.events[0].parentId='other'},r=>{r.preparedBatch.expectedRevision=3},r=>{r.preparedBatch.events[0].products=[]}]){
  const f=fixture(),receipt=storeReceipt(f);mutate(receipt);f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return receipt};
  await f.elements.discoveryStoreCapture.onclick();await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
 }
});
test('store scope failures remain blocked without fabricated products or automatic work',async()=>{
 for(const reason of ['capture_evidence_or_scope_invalid','page_or_ownership_changed','explicit_discovery_binding_required']){
  const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {captureId:f.receipt.captureId,captureKind:'store',status:'blocked',reason}};
  await f.elements.discoveryStoreCapture.onclick();await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.match(f.elements.discoveryBrowserInfo.textContent,new RegExp(reason));
 }
});
test('store uncertainty cannot be bypassed via seller capture or old terminal receipt',async()=>{
 const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('connection lost')};
 await f.elements.discoveryStoreCapture.onclick();await f.elements.discoveryBrowserCapture.onclick();assert.equal(f.calls.length,1);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[{captureId:'older',captureKind:'store',status:'blocked'},{captureId:f.receipt.captureId,status:'execution_unknown'}]}:{captureId:'older',captureKind:'store',status:'blocked'}};
 await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick();
 assert.equal(f.elements.discoveryStoreCapture.disabled,true);assert.equal(f.elements.discoveryBrowserCapture.disabled,true);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return storeReceipt(f)};
 await f.elements.discoveryBrowserHistory.children[1].onclick();assert.equal(f.elements.discoveryStoreCapture.disabled,false);assert.equal(f.elements.discoveryBrowserSave.disabled,false);
 assert.equal(f.calls.filter(c=>c.data).length,1);
});
test('same-kind history is viewable but cannot save across cycle, revision or ancestry',async()=>{
 for(const mutate of [r=>{r.preparedBatch.cycleId='other'},r=>{r.preparedBatch.expectedRevision=1},r=>{r.preparedBatch.events[0].parentId='foreign'}]){
  const f=fixture(),r=storeReceipt(f);r.captureId='history';mutate(r);
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[r]}:r};
  await f.elements.discoveryBrowserRefresh.onclick();assert.match(f.elements.discoveryBrowserHistory.children[0].textContent,/店铺商品/);
  await f.elements.discoveryBrowserHistory.children[0].onclick();assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.calls.every(c=>!c.data),true);
 }
});
test('store response discarded after account switch, away/back navigation, revision or invalidation',async()=>{
 for(const change of [f=>{f.context.signedUser={id:2}},f=>{f.context.view='listing';f.context.selectionEpoch++;f.context.view='selection'},f=>{f.report.revision++},f=>f.context.discoveryBrowserInvalidate()]){
  const f=fixture();let release;f.context.selectionApi=async()=>new Promise(r=>release=r);
  const pending=f.elements.discoveryStoreCapture.onclick();change(f);release(storeReceipt(f));await pending;
  assert.equal(f.elements.discoveryBrowserReceipt.textContent,'');await f.elements.discoveryBrowserSave.onclick();assert.equal(f.shown.length,0);
 }
});
test('new report or return mount never replays pending capture or late preview',async()=>{
 const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const p=f.elements.discoveryStoreCapture.onclick(),oldSave=f.elements.discoveryBrowserSave.onclick;
 f.context.discoveryBrowserInvalidate();f.context.selectionEpoch++;
 f.context.discoveryBrowserMount(f.report,f.context.signedUser,f.context.selectionEpoch);release(storeReceipt(f));await p;await oldSave();
 assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserReceipt.textContent,'');assert.equal(f.elements.discoveryBrowserSave.disabled,true);
});
test('keyword preview and save are separate explicit ledger-only actions',async()=>{
 const f=fixture();await f.elements.discoveryKeywordPrepare.onclick();assert.equal(f.calls.length,0);
 setPhrase(f);let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const a=f.elements.discoveryKeywordPrepare.onclick(),b=f.elements.discoveryKeywordPrepare.onclick();assert.equal(f.calls.length,1);
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].data)),{cycleId:'cycle',expectedRevision:2,parentId:'store-1',asin:'B098765432',phrase:'Cotton Travel'});
 release(keywordReceipt());await Promise.all([a,b]);assert.equal(f.elements.discoveryKeywordSave.disabled,false);assert.match(f.elements.discoveryKeywordInfo.textContent,/未执行搜索/);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {...f.report,revision:3}};
 await f.elements.discoveryKeywordSave.onclick();await f.elements.discoveryKeywordSave.onclick();
 assert.deepEqual(f.calls.map(c=>c.path),['/api/discovery/prepare-keyword','/api/discovery/ingest']);assert.equal(f.calls[1].data.events[0].kind,'keyword');
});
test('keyword editing or product change invalidates prepared and in-flight previews',async()=>{
 for(const change of [f=>{f.elements.discoveryKeywordPhrase.value='Cotton';f.elements.discoveryKeywordPhrase.oninput()},f=>f.elements.discoveryKeywordTarget.onchange()]){
  const f=fixture();setPhrase(f);let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
  const p=f.elements.discoveryKeywordPrepare.onclick();change(f);release(keywordReceipt());await p;await f.elements.discoveryKeywordSave.onclick();
  assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryKeywordSave.disabled,true);assert.equal(f.elements.discoveryKeywordPreview.textContent,'');
 }
});
test('keyword preview rejects wrong parent/product/title/phrase/kind or stale revision',async()=>{
 for(const mutate of [r=>{r.preparedBatch.expectedRevision=1},r=>{r.preparedBatch.events[0].parentId='other'},r=>{r.preparedBatch.events[0].asin='OTHER'},r=>{r.preparedBatch.events[0].sourceTitle='Invented'},r=>{r.preparedBatch.events[0].phrase='Different'},r=>{r.preparedBatch.events[0].kind='store'}]){
  const f=fixture(),r=keywordReceipt();mutate(r);setPhrase(f);f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return r};
  await f.elements.discoveryKeywordPrepare.onclick();await f.elements.discoveryKeywordSave.onclick();assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryKeywordSave.disabled,true);
 }
});
test('keyword response and save callbacks are discarded after scope changes',async()=>{
 for(const change of [f=>{f.context.signedUser={id:2}},f=>{f.context.selectionEpoch++},f=>{f.report.revision++},f=>f.context.discoveryBrowserInvalidate()]){
  const f=fixture();setPhrase(f);let release;f.context.selectionApi=async()=>new Promise(r=>release=r);
  const p=f.elements.discoveryKeywordPrepare.onclick();change(f);release(keywordReceipt());await p;await f.elements.discoveryKeywordSave.onclick();
  assert.equal(f.elements.discoveryKeywordPreview.textContent,'');assert.equal(f.shown.length,0);
 }
});
test('uncertain saves disable repeated submission until ledger is reloaded',async()=>{
 for(const kind of ['store','keyword']){
  const f=fixture();f.context.selectionApi=async()=>kind==='store'?storeReceipt(f):keywordReceipt();
  if(kind==='store')await f.elements.discoveryStoreCapture.onclick();else{setPhrase(f);await f.elements.discoveryKeywordPrepare.onclick()}
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('save disconnected')};
  const button=kind==='store'?f.elements.discoveryBrowserSave:f.elements.discoveryKeywordSave;
  await button.onclick();await button.onclick();assert.equal(f.calls.length,1);assert.equal(button.disabled,true);assert.equal(f.shown.length,0);
 }
});
test('late history response cannot overwrite newer history or a newer report',async()=>{
 const f=fixture(),releases=[];f.context.selectionApi=async()=>new Promise(r=>releases.push(r));
 const a=f.elements.discoveryBrowserRefresh.onclick(),b=f.elements.discoveryBrowserRefresh.onclick();
 releases[1]({items:[{captureId:'new',status:'blocked'}]});await b;releases[0]({items:[{captureId:'old',status:'blocked'}]});await a;
 assert.match(f.elements.discoveryBrowserHistory.children[0].textContent,/new/);
 const c=f.elements.discoveryBrowserRefresh.onclick();f.context.discoveryBrowserMount({...f.report,cycleId:'other'},f.context.signedUser,3);
 releases[2]({items:[{captureId:'late',status:'blocked'}]});await c;assert.doesNotMatch(f.elements.discoveryBrowserHistory.children[0].textContent,/late/);
});
test('all newly added controls are disabled on scope invalidation',()=>{
 const f=fixture();f.context.discoveryBrowserInvalidate();
 for(const id of ['discoveryStoreTarget','discoveryStoreCapture','discoveryKeywordTarget','discoveryKeywordPhrase','discoveryKeywordPrepare','discoveryKeywordSave'])assert.equal(f.elements[id].disabled,true);
});

function searchReceipt(f){return {...f.receipt,captureKind:'search',preparedBatch:{cycleId:'cycle',expectedRevision:2,events:[{id:'captured-search',kind:'search',parentId:'keyword-1',query:'Cotton Travel',marketplace:'US',products:[{asin:'B076543210',title:'Visible search result'}]}]}}}
function planReceipt(f){return {schemaVersion:1,status:'ready',readOnly:true,owner:1,cycleId:'cycle',revision:2,expectedRevision:2,limits:{maxActions:5,maxRounds:2},
 actions:[{kind:'search_capture',sourceEventId:'keyword-1',proposedRound:1,status:'proposed',executionAllowed:false}],executionAllowed:false,automaticNavigationImplemented:false};}

test('search targets only saved keyword events and displays exact escaped phrase without calls',async()=>{
 const f=fixture(),mixed={events:[...f.report.events,{id:'wrong',kind:'search',phrase:'invented'}]};
 assert.deepEqual(JSON.parse(JSON.stringify(f.context.discoverySearchTargets(mixed))),[{parentId:'keyword-1',marketplace:'US',query:'Cotton Travel'}]);
 assert.match(f.elements.discoverySearchPhrase.textContent,/Cotton Travel/);assert.equal(f.calls.length,0);
 f.report.events[0].phrase='<script> & exact';f.context.discoveryBrowserMount(f.report,f.context.signedUser,3);
 assert.doesNotMatch(f.elements.discoveryBrowserPanel.innerHTML,/<script>/);assert.match(f.elements.discoveryBrowserPanel.innerHTML,/&lt;script&gt;/);
 assert.match(f.elements.discoverySearchPhrase.textContent,/<script> & exact/);
 f.context.discoveryBrowserMount({...f.report,events:[]},f.context.signedUser,3);
 await f.elements.discoverySearchCapture.onclick();assert.equal(f.calls.length,0);assert.equal(f.elements.discoverySearchCapture.disabled,true);
});

test('search capture sends only pinned four fields once, and requires explicit ledger save',async()=>{
 const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const pending=f.elements.discoverySearchCapture.onclick();await f.elements.discoverySearchCapture.onclick();await f.elements.discoveryStoreCapture.onclick();await f.elements.discoveryPlanPrepare.onclick();
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].path,'/api/discovery/capture-search');
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].data)),{captureId:f.receipt.captureId,cycleId:'cycle',expectedRevision:2,parentId:'keyword-1'});
 release(searchReceipt(f));await pending;
 assert.equal(f.elements.discoveryBrowserSave.disabled,false);assert.match(f.elements.discoveryBrowserInfo.textContent,/不代表同款/);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {...f.report,revision:3}};
 await f.elements.discoveryBrowserSave.onclick();await f.elements.discoveryBrowserSave.onclick();
 assert.deepEqual(f.calls.map(c=>c.path),['/api/discovery/capture-search','/api/discovery/ingest']);
 assert.equal(f.calls[1].data.events[0].query,'Cotton Travel');assert.equal(f.calls[1].data.events[0].products[0].similarity,undefined);
});

test('search refuses kind parent exact phrase market revision and fabricated EXACT claims',async()=>{
 for(const mutate of [r=>{delete r.captureKind},r=>{r.captureKind='store'},r=>{r.preparedBatch.events[0].parentId='other'},
 r=>{r.preparedBatch.events[0].query='cotton travel'},r=>{r.preparedBatch.events[0].query='Cotton  Travel'},
 r=>{r.preparedBatch.events[0].marketplace='UK'},r=>{r.preparedBatch.expectedRevision++},r=>{r.preparedBatch.events[0].products=[]},
 r=>{r.preparedBatch.events[0].products[0].similarity='EXACT'}]){
  const f=fixture(),receipt=searchReceipt(f);mutate(receipt);f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return receipt};
  await f.elements.discoverySearchCapture.onclick();await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
 }
});

test('changing search source invalidates pending and prepared search previews',async()=>{
 for(const inFlight of [true,false]){
  const f=fixture();let release;f.context.selectionApi=async()=>inFlight?new Promise(r=>release=r):searchReceipt(f);
  const pending=f.elements.discoverySearchCapture.onclick();if(!inFlight)await pending;
  f.elements.discoverySearchTarget.onchange();if(inFlight){release(searchReceipt(f));await pending}
  assert.equal(f.elements.discoveryBrowserSave.disabled,true);await f.elements.discoveryBrowserSave.onclick();assert.equal(f.shown.length,0);
 }
});

test('search response discarded on logout navigation back forward revision and remount',async()=>{
 for(const change of [f=>{f.context.signedUser=null},f=>{f.context.view='listing'},f=>{f.context.selectionEpoch++;f.context.view='selection'},
 f=>{f.report.revision++},f=>f.context.discoveryBrowserInvalidate(),f=>f.context.discoveryBrowserMount({...f.report,cycleId:'other'},f.context.signedUser,3)]){
  const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
  const pending=f.elements.discoverySearchCapture.onclick(),oldSave=f.elements.discoveryBrowserSave.onclick;change(f);release(searchReceipt(f));await pending;await oldSave();
  assert.equal(f.calls.length,1);assert.equal(f.shown.length,0);assert.equal(f.elements.discoveryBrowserReceipt.textContent,'');
 }
});

test('search and all other captures share uncertainty and never retry after unrelated history',async()=>{
 const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('search disconnected')};
 await f.elements.discoverySearchCapture.onclick();
 for(const button of ['discoverySearchCapture','discoveryBrowserCapture','discoveryStoreCapture','discoveryKeywordPrepare','discoveryPlanPrepare']){
  setPhrase(f);await f.elements[button].onclick();assert.equal(f.elements[button].disabled,true);
 }
 assert.equal(f.calls.length,1);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[{captureId:'old',captureKind:'search',status:'blocked'}]}:{captureId:'old',captureKind:'search',status:'blocked'}};
 await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick();
 assert.match(f.elements.discoveryBrowserHistory.children[0].textContent,/搜索商品/);assert.equal(f.elements.discoverySearchCapture.disabled,true);assert.equal(f.calls.filter(c=>c.data).length,1);
});

test('history search receipts recheck exact current keyword and revision before saving',async()=>{
 for(const mutate of [r=>{r.preparedBatch.events[0].query='Other'},r=>{r.preparedBatch.events[0].marketplace='UK'},r=>{r.preparedBatch.events[0].parentId='old'},r=>{r.preparedBatch.expectedRevision--},r=>{r.preparedBatch.cycleId='other'}]){
  const f=fixture(),receipt=searchReceipt(f);receipt.captureId='history-search';mutate(receipt);
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[receipt]}:receipt};
  await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick();await f.elements.discoveryBrowserSave.onclick();
  assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.calls.every(c=>!c.data),true);
 }
});

test('valid search history can be explicitly saved without recapture',async()=>{
 const f=fixture(),receipt=searchReceipt(f);receipt.captureId='history-search';
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[receipt]}:receipt};
 await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick();assert.equal(f.elements.discoveryBrowserSave.disabled,false);
 await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.filter(c=>c.data).length,1);assert.equal(f.calls[2].path,'/api/discovery/ingest');
});

test('unknown search save blocks all new action types and never upgrades revision',async()=>{
 const f=fixture();f.context.selectionApi=async()=>searchReceipt(f);await f.elements.discoverySearchCapture.onclick();
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('save disconnected')};
 await f.elements.discoveryBrowserSave.onclick();setPhrase(f);
 for(const button of ['discoverySearchCapture','discoveryBrowserCapture','discoveryStoreCapture','discoveryKeywordPrepare','discoveryPlanPrepare','discoveryBrowserSave'])await f.elements[button].onclick();
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].data.expectedRevision,2);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
});

test('plan controls are explicit preview only with finite quotas and no automatic calls',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);assert.equal(f.elements.discoveryPlanMaxActions.value,'5');assert.equal(f.elements.discoveryPlanMaxRounds.value,'2');
 assert.match(f.elements.discoveryBrowserPanel.innerHTML,/不是实际连续运行/);assert.match(f.elements.discoveryBrowserPanel.innerHTML,/最大轮次序号/);
 assert.doesNotMatch(f.elements.discoveryBrowserPanel.innerHTML,/id="discoveryPlan(?:Save|Execute|Start)"/);
 let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const pending=f.elements.discoveryPlanPrepare.onclick();await f.elements.discoveryPlanPrepare.onclick();await f.elements.discoverySearchCapture.onclick();
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[{path:'/api/discovery/prepare-plan',data:{cycleId:'cycle',expectedRevision:2,maxActions:5,maxRounds:2}}]);
 release(planReceipt(f));await pending;assert.match(f.elements.discoveryPlanInfo.textContent,/未连续运行/);assert.match(f.elements.discoveryPlanPreview.textContent,/search_capture/);
 assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.elements.discoveryKeywordSave.disabled,true);assert.equal(f.calls.length,1);
});

test('invalid plan quota inputs never dispatch and valid boundaries remain integers',async()=>{
 for(const value of ['','0','21','1.5','1e1','NaN','-1',' 2 ','Infinity']){
  for(const field of ['discoveryPlanMaxActions','discoveryPlanMaxRounds']){
   const f=fixture();f.elements[field].value=value;f.elements[field].oninput();await f.elements.discoveryPlanPrepare.onclick();
   assert.equal(f.calls.length,0);assert.equal(f.elements.discoveryPlanPrepare.disabled,true);
  }
 }
 const f=fixture();f.elements.discoveryPlanMaxActions.value='20';f.elements.discoveryPlanMaxRounds.value='1';
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {...planReceipt(f),limits:{maxActions:20,maxRounds:1}}};
 await f.elements.discoveryPlanPrepare.onclick();assert.equal(f.calls[0].data.maxActions,20);assert.equal(f.calls[0].data.maxRounds,1);
});

test('plan response rejected for foreign stale unbounded executable or fabricated proposals',async()=>{
 for(const mutate of [r=>{r.owner=2},r=>{r.cycleId='other'},r=>{r.revision=3},r=>{r.expectedRevision=3},r=>{r.readOnly=false},
 r=>{r.executionAllowed=true},r=>{r.automaticNavigationImplemented=true},r=>{r.limits.maxActions=6},r=>{r.limits.maxRounds=3},
 r=>{r.actions[0].executionAllowed=true},r=>{r.actions[0].status='executed'},r=>{r.actions[0].proposedRound=3},r=>{r.actions[0].sourceEventId='made-up'},
 r=>{r.actions=Array(6).fill(r.actions[0])},r=>{r.status='executed'}]){
  const f=fixture(),receipt=planReceipt(f);mutate(receipt);f.context.selectionApi=async()=>receipt;
  await f.elements.discoveryPlanPrepare.onclick();assert.equal(f.elements.discoveryPlanPreview.textContent,'');assert.match(f.elements.discoveryPlanInfo.textContent,/未取得有效建议/);
 }
});

test('changing plan limits discards pending and completed previews without execution',async()=>{
 for(const inFlight of [true,false]){
  const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return inFlight?new Promise(r=>release=r):planReceipt(f)};
  const pending=f.elements.discoveryPlanPrepare.onclick();if(!inFlight)await pending;
  f.elements.discoveryPlanMaxActions.value='4';f.elements.discoveryPlanMaxActions.oninput();if(inFlight){release(planReceipt(f));await pending}
  assert.equal(f.elements.discoveryPlanPreview.textContent,'');assert.equal(f.calls.length,1);
 }
});

test('plan interrupted by account report or back forward never resurfaces or reruns',async()=>{
 for(const change of [f=>{f.context.signedUser={id:2}},f=>{f.context.view='listing';f.context.selectionEpoch++;f.context.view='selection'},
 f=>{f.report.revision++},f=>f.context.discoveryBrowserInvalidate(),f=>f.context.discoveryBrowserMount({...f.report,cycleId:'other'},f.context.signedUser,3)]){
  const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
  const pending=f.elements.discoveryPlanPrepare.onclick();change(f);release(planReceipt(f));await pending;
  assert.equal(f.elements.discoveryPlanPreview.textContent,'');assert.equal(f.calls.length,1);
 }
});

test('blocked plan shown as preview result; failure needs explicit retry and never executes',async()=>{
 const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {...planReceipt(f),status:'blocked',actions:[],blockers:[{reason:'execution_unknown'}]}};
 await f.elements.discoveryPlanPrepare.onclick();assert.match(f.elements.discoveryPlanInfo.textContent,/blocked/);assert.equal(f.calls.length,1);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('network')};
 await f.elements.discoveryPlanPrepare.onclick();assert.equal(f.calls.length,2);assert.equal(f.elements.discoveryPlanPreview.textContent,'');
 assert.match(f.elements.discoveryPlanInfo.textContent,/network/);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
});

test('scope invalidation disables search and preview controls immediately',()=>{
 const f=fixture();f.context.discoveryBrowserInvalidate();
 for(const id of ['discoverySearchTarget','discoverySearchCapture','discoveryPlanMaxActions','discoveryPlanMaxRounds','discoveryPlanPrepare'])assert.equal(f.elements[id].disabled,true);
});

function familyReceipt(f){return {captureId:f.receipt.captureId,captureKind:'family',status:'captured',cycleId:'cycle',expectedRevision:2,parentId:'search-1',asin:'B012345678',executionAllowed:false,qualificationEvaluated:false,qualifiedCount:0,
 evidence:{source:'amazon_variant_page',selectedAsin:'B012345678',variantAsins:['B012345678','B098765432'],trust:'unverified_observation'}}}
function familyAssessment(){return {schemaVersion:1,readOnly:true,owner:1,cycleId:'cycle',revision:2,executionAllowed:false,qualificationEvaluated:false,qualifiedCount:0,importedCount:0,externalCallsPerformed:0,
 assessment:{groups:[],pending:[{asin:'B012345678',reason:'missing_reciprocal_evidence'}]},blockers:[],historyFingerprint:'a'.repeat(64)}}
function runInspection(){return {schemaVersion:1,status:'execution_disabled',readOnly:true,owner:1,cycleId:'cycle',revision:2,executionAllowed:false,automaticNavigationImplemented:false,persistentLiveQueueCreated:false,
 externalCallsPerformed:0,qualificationEvaluated:false,qualifiedCount:0,importedCount:0,limits:{maxActions:5,maxRounds:2},plannedActionCount:1,binding:{status:'configured',liveOwnershipVerified:false},
 blockers:[{reason:'live_bounded_runner_not_implemented',retryAllowed:false}]}}
const familyActionIds=['discoveryFamilyCapture','discoveryBrowserCapture','discoveryStoreCapture','discoverySearchCapture','discoveryKeywordPrepare','discoveryPlanPrepare','discoveryFamilyAssess','discoveryRunInspect'];

test('family targets retain exact saved source across keyword seller search and captured store',async()=>{
 const f=fixture();f.report.events[0]={...f.report.events[0],asin:'B011111111',sourceTitle:'<img src=x onerror=bad>'};f.report.events[2].asin='B022222222';
 const mixed={...f.report,events:[...f.report.events,{id:'unseen',kind:'store',status:'inaccessible',products:[{asin:'FAKE'}]},{id:'wrong-kind',kind:'family',asin:'FAKE'}]};
 assert.deepEqual(JSON.parse(JSON.stringify(f.context.discoveryFamilyTargets(mixed))).map(t=>[t.parentId,t.asin]),[['keyword-1','B011111111'],['search-1','B012345678'],['seller-1','B022222222'],['store-1','B098765432']]);
 f.context.discoveryBrowserMount(mixed,f.context.signedUser,3);assert.equal(f.calls.length,0);assert.doesNotMatch(f.elements.discoveryBrowserPanel.innerHTML,/<img/);assert.match(f.elements.discoveryBrowserPanel.innerHTML,/&lt;img/);
 assert.match(f.elements.discoveryBrowserPanel.innerHTML,/共享 detailASIN/);assert.match(f.elements.discoveryBrowserPanel.innerHTML,/不等于正式父子 ASIN 映射/);assert.match(f.elements.discoveryBrowserPanel.innerHTML,/不会因此丢弃各变体 Seller/);
 f.context.discoveryBrowserMount({...f.report,events:[]},f.context.signedUser,3);await f.elements.discoveryFamilyCapture.onclick();assert.equal(f.calls.length,0);assert.equal(f.elements.discoveryFamilyCapture.disabled,true);
});

test('family capture sends exact five fields once and never enables graph saving',async()=>{
 const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const pending=f.elements.discoveryFamilyCapture.onclick();for(const id of familyActionIds)await f.elements[id].onclick();
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[{path:'/api/discovery/capture-family',data:{captureId:f.receipt.captureId,cycleId:'cycle',expectedRevision:2,parentId:'search-1',asin:'B012345678'}}]);
 release(familyReceipt(f));await pending;assert.match(f.elements.discoveryBrowserReceipt.textContent,/amazon_variant_page/);assert.match(f.elements.discoveryBrowserInfo.textContent,/尚未核实家族或选品资格/);
 assert.match(f.elements.discoveryBrowserSave.textContent,/不可保存到发现图谱/);assert.equal(f.elements.discoveryBrowserSave.disabled,true);await f.elements.discoveryBrowserSave.onclick();await f.elements.discoveryKeywordSave.onclick();
 assert.equal(f.calls.length,1);assert.equal(f.shown.length,0);
});

test('family can explicitly capture reciprocal keyword or store source without inventing evidence',async()=>{
 for(const kind of ['keyword','store']){
  const f=fixture();f.report.events[0].asin='B011111111';f.report.events[0].sourceTitle='Known root product';f.context.discoveryBrowserMount(f.report,f.context.signedUser,3);
  const targets=f.context.discoveryFamilyTargets(f.report),i=targets.findIndex(t=>t.parentId===(kind==='keyword'?'keyword-1':'store-1'));f.elements.discoveryFamilyTarget.value=String(i);
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return {...familyReceipt(f),parentId:targets[i].parentId,asin:targets[i].asin}};
  await f.elements.discoveryFamilyCapture.onclick();assert.equal(f.calls[0].data.parentId,targets[i].parentId);assert.equal(f.calls[0].data.asin,targets[i].asin);assert.equal(Object.keys(f.calls[0].data).length,5);
  assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.match(f.elements.discoveryBrowserInfo.textContent,/已采集变体页面观察/);
 }
});

test('family receipts reject cross-kind stale mismatched malformed or graph-saveable responses',async()=>{
 for(const mutate of [r=>{delete r.captureKind},r=>{r.captureKind='seller'},r=>{r.captureKind='search'},r=>{r.captureId='wrong'},r=>{r.cycleId='other'},r=>{r.expectedRevision++},r=>{r.parentId='other'},r=>{r.asin='B000000000'},
 r=>{delete r.evidence},r=>{r.evidence=[]},r=>{r.executionAllowed=true},r=>{r.qualificationEvaluated=true},r=>{r.qualifiedCount=1},r=>{r.preparedBatch={cycleId:'cycle',expectedRevision:2,events:[{kind:'seller',parentId:'search-1',asin:'B012345678'}]}}]){
  const f=fixture(),receipt=familyReceipt(f);mutate(receipt);f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return receipt};
  await f.elements.discoveryFamilyCapture.onclick();await f.elements.discoveryBrowserSave.onclick();await f.elements.discoveryBrowserCapture.onclick();
  assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.elements.discoveryFamilyCapture.disabled,true);assert.equal(f.elements.discoveryBrowserReceipt.textContent,'');
 }
});

test('family uncertainty blocks every action until that exact original receipt resolves',async()=>{
 const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('disconnected')};await f.elements.discoveryFamilyCapture.onclick();setPhrase(f);
 for(const id of familyActionIds){await f.elements[id].onclick();assert.equal(f.elements[id].disabled,true)}assert.equal(f.calls.length,1);
 const old={captureId:'old-family',captureKind:'family',status:'blocked'};
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[old,{captureId:f.receipt.captureId,captureKind:'family',status:'execution_unknown'}]}:old};
 await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick();assert.equal(f.elements.discoveryFamilyCapture.disabled,true);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return familyReceipt(f)};await f.elements.discoveryBrowserHistory.children[1].onclick();
 assert.equal(f.elements.discoveryFamilyCapture.disabled,false);assert.equal(f.elements.discoveryBrowserCapture.disabled,false);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
 assert.equal(f.calls.filter(c=>c.data).length,1);assert.match(f.elements.discoveryBrowserHistory.children[0].textContent,/变体家族观察/);
});

test('seller store and search uncertainties also block family and readiness actions',async()=>{
 for(const source of ['discoveryBrowserCapture','discoveryStoreCapture','discoverySearchCapture']){
  const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('unknown')};await f.elements[source].onclick();
  for(const id of ['discoveryFamilyCapture','discoveryFamilyAssess','discoveryRunInspect']){await f.elements[id].onclick();assert.equal(f.elements[id].disabled,true)}assert.equal(f.calls.length,1);
 }
});

test('family receipt cannot become a seller receipt during explicit recovery or history reads',async()=>{
 for(const fromHistory of [false,true]){
  const f=fixture();let initial=true;const descriptor={captureId:f.receipt.captureId,captureKind:'family',status:'execution_unknown'};
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});if(path.endsWith('/captures'))return {items:[descriptor]};if(initial){initial=false;throw Error('unknown')}return f.receipt};
  if(fromHistory){initial=false;await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick()}
  else{await f.elements.discoveryFamilyCapture.onclick();await f.elements.discoveryBrowserCheck.onclick()}
  await f.elements.discoveryBrowserSave.onclick();await f.elements.discoveryBrowserCapture.onclick();
  assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.elements.discoveryFamilyCapture.disabled,true);assert.equal(f.calls.some(c=>c.path==='/api/discovery/ingest'),false);
 }
});

test('family history is readable evidence only, including older cycles, and never a batch',async()=>{
 for(const mutation of [r=>{},r=>{r.cycleId='old-cycle';r.expectedRevision=1},r=>{r.preparedBatch={cycleId:'cycle',expectedRevision:2,events:[{kind:'seller',parentId:'search-1',asin:'B012345678'}]}}]){
  const f=fixture(),receipt=familyReceipt(f);receipt.captureId='family-history';mutation(receipt);f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?{items:[receipt]}:receipt};
  await f.elements.discoveryBrowserRefresh.onclick();await f.elements.discoveryBrowserHistory.children[0].onclick();await f.elements.discoveryBrowserSave.onclick();
  assert.equal(f.calls.every(c=>!c.data),true);assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.shown.length,0);
  if(receipt.cycleId==='old-cycle')assert.match(f.elements.discoveryBrowserInfo.textContent,/历史或不适用于当前来源/);
 }
});

test('family source changes discard late display but permit explicit original receipt review',async()=>{
 for(const inFlight of [true,false]){
  const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return inFlight?new Promise(r=>release=r):familyReceipt(f)};
  const pending=f.elements.discoveryFamilyCapture.onclick();if(!inFlight)await pending;f.elements.discoveryFamilyTarget.value='1';f.elements.discoveryFamilyTarget.onchange();if(inFlight){release(familyReceipt(f));await pending}
  assert.equal(f.elements.discoveryBrowserReceipt.textContent,'');assert.equal(f.elements.discoveryBrowserSave.disabled,true);
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return familyReceipt(f)};await f.elements.discoveryBrowserCheck.onclick();assert.match(f.elements.discoveryBrowserReceipt.textContent,/amazon_variant_page/);
  assert.equal(f.calls.filter(c=>c.data).length,1);
 }
});

test('new family controls discard callbacks after account logout navigation revision and remount',async()=>{
 for(const request of [{id:'discoveryFamilyCapture',box:'discoveryBrowserReceipt',response:f=>familyReceipt(f)},{id:'discoveryFamilyAssess',box:'discoveryFamilyAssessment',response:()=>familyAssessment()},{id:'discoveryRunInspect',box:'discoveryRunInspection',response:()=>runInspection()}]){
  for(const change of [f=>{f.context.signedUser=null},f=>{f.context.signedUser={id:2}},f=>{f.context.signedUser.id=2},f=>{f.context.view='listing'},f=>{f.context.selectionEpoch++;f.context.view='selection'},f=>{f.report.revision++},f=>f.context.discoveryBrowserInvalidate(),f=>f.context.discoveryBrowserMount({...f.report,cycleId:'other'},f.context.signedUser,3)]){
   const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
   const pending=f.elements[request.id].onclick(),oldClick=f.elements[request.id].onclick;change(f);release(request.response(f));await pending;await oldClick();
   assert.equal(f.elements[request.box].textContent,'');assert.equal(f.calls.length,1);assert.equal(f.shown.length,0);
  }
 }
});

test('family assessment is explicit readonly owner evidence with no caller observations or save',async()=>{
 const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const pending=f.elements.discoveryFamilyAssess.onclick();for(const id of familyActionIds)await f.elements[id].onclick();
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[{path:'/api/discovery/assess-families',data:{cycleId:'cycle',expectedRevision:2}}]);
 release(familyAssessment());await pending;assert.match(f.elements.discoveryFamilyAssessment.textContent,/missing_reciprocal_evidence/);assert.match(f.elements.discoveryFamilyInfo.textContent,/未核实选品资格/);assert.match(f.elements.discoveryFamilyInfo.textContent,/各变体 Seller 核实均保留/);
 await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
});

test('family assessment rejects foreign stale executable or qualification-upgrading responses',async()=>{
 for(const mutate of [r=>{r.schemaVersion=2},r=>{r.owner=2},r=>{r.cycleId='other'},r=>{r.revision++},r=>{r.readOnly=false},r=>{r.executionAllowed=true},r=>{r.qualificationEvaluated=true},r=>{r.qualifiedCount=1},r=>{r.importedCount=1},r=>{r.externalCallsPerformed=1},r=>{r.assessment=null},r=>{r.assessment=[]},r=>{r.blockers=null},r=>{r.historyFingerprint='unknown'}]){
  const f=fixture(),response=familyAssessment();mutate(response);f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return response};await f.elements.discoveryFamilyAssess.onclick();
  assert.equal(f.elements.discoveryFamilyAssessment.textContent,'');assert.match(f.elements.discoveryFamilyInfo.textContent,/未取得有效家族评估/);assert.equal(f.calls.length,1);
 }
});

test('readiness inspection sends bounded four fields once and never starts a run',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);assert.doesNotMatch(f.elements.discoveryBrowserPanel.innerHTML,/id="discovery(?:Family|Run)(?:Execute|Start|Save|Resume)"/);
 let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const pending=f.elements.discoveryRunInspect.onclick();for(const id of familyActionIds)await f.elements[id].onclick();
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[{path:'/api/discovery/inspect-run',data:{cycleId:'cycle',expectedRevision:2,maxActions:5,maxRounds:2}}]);
 release(runInspection());await pending;assert.match(f.elements.discoveryRunInfo.textContent,/执行权限关闭/);assert.match(f.elements.discoveryRunInfo.textContent,/不代表选品合格或可上线/);assert.match(f.elements.discoveryRunInspection.textContent,/execution_disabled/);
 await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);
});

test('readiness rejects foreign stale unbounded executable active queue and qualification claims',async()=>{
 for(const mutate of [r=>{r.schemaVersion=2},r=>{r.owner=2},r=>{r.cycleId='other'},r=>{r.revision++},r=>{r.status='ready'},r=>{r.readOnly=false},r=>{r.executionAllowed=true},r=>{r.automaticNavigationImplemented=true},r=>{r.persistentLiveQueueCreated=true},
 r=>{r.externalCallsPerformed=1},r=>{r.qualificationEvaluated=true},r=>{r.qualifiedCount=1},r=>{r.importedCount=1},r=>{r.limits.maxActions=6},r=>{r.limits.maxRounds=3},r=>{r.blockers=null},r=>{r.binding.liveOwnershipVerified=true},r=>{r.plannedActionCount=6},r=>{r.plannedActionCount=-1},r=>{r.plannedActionCount=1.2}]){
  const f=fixture(),response=runInspection();mutate(response);f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return response};await f.elements.discoveryRunInspect.onclick();
  assert.equal(f.elements.discoveryRunInspection.textContent,'');assert.match(f.elements.discoveryRunInfo.textContent,/未取得有效准备检查/);assert.equal(f.calls.length,1);
 }
});

test('readiness rejects invalid quotas and invalidates pending and completed result on edits',async()=>{
 for(const value of ['','0','21','1.5','1e1','NaN','-1',' 2 ','Infinity'])for(const field of ['discoveryPlanMaxActions','discoveryPlanMaxRounds']){
  const f=fixture();f.elements[field].value=value;f.elements[field].oninput();await f.elements.discoveryRunInspect.onclick();assert.equal(f.calls.length,0);assert.equal(f.elements.discoveryRunInspect.disabled,true);
 }
 for(const inFlight of [true,false]){
  const f=fixture();let release;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return inFlight?new Promise(r=>release=r):runInspection()};
  const pending=f.elements.discoveryRunInspect.onclick();if(!inFlight)await pending;f.elements.discoveryPlanMaxActions.value='4';f.elements.discoveryPlanMaxActions.oninput();if(inFlight){release(runInspection());await pending}
  assert.equal(f.elements.discoveryRunInspection.textContent,'');assert.equal(f.calls.length,1);
 }
});

test('capture or refreshed history clears previous assessment and readiness without rerunning',async()=>{
 for(const action of ['discoveryFamilyCapture','discoveryBrowserCapture','discoveryBrowserRefresh']){
  const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/assess-families')?familyAssessment():path.endsWith('/inspect-run')?runInspection():path.endsWith('/captures')?{items:[]}:action==='discoveryFamilyCapture'?familyReceipt(f):f.receipt};
  await f.elements.discoveryFamilyAssess.onclick();await f.elements.discoveryRunInspect.onclick();assert.notEqual(f.elements.discoveryFamilyAssessment.textContent,'');assert.notEqual(f.elements.discoveryRunInspection.textContent,'');
  await f.elements[action].onclick();assert.equal(f.elements.discoveryFamilyAssessment.textContent,'');assert.equal(f.elements.discoveryRunInspection.textContent,'');assert.equal(f.calls.length,3);
 }
});

test('family and readiness text including errors never render receipt markup as HTML',async()=>{
 const payload='<img src=x onerror=bad><script>bad</script>',f=fixture();const receipt=familyReceipt(f);receipt.evidence.title=payload;
 f.context.selectionApi=async()=>receipt;await f.elements.discoveryFamilyCapture.onclick();assert.match(f.elements.discoveryBrowserReceipt.textContent,/<script>/);assert.equal(f.elements.discoveryBrowserReceipt.innerHTML,'');
 const assessment=familyAssessment();assessment.assessment.pending[0].reason=payload;f.context.selectionApi=async()=>assessment;await f.elements.discoveryFamilyAssess.onclick();assert.match(f.elements.discoveryFamilyAssessment.textContent,/<script>/);assert.equal(f.elements.discoveryFamilyAssessment.innerHTML,'');
 const inspection=runInspection();inspection.blockers[0].reason=payload;f.context.selectionApi=async()=>inspection;await f.elements.discoveryRunInspect.onclick();assert.match(f.elements.discoveryRunInspection.textContent,/<script>/);assert.equal(f.elements.discoveryRunInspection.innerHTML,'');
 f.context.selectionApi=async()=>{throw Error(payload)};await f.elements.discoveryFamilyAssess.onclick();await f.elements.discoveryRunInspect.onclick();
 assert.match(f.elements.discoveryFamilyInfo.textContent,/<script>/);assert.equal(f.elements.discoveryFamilyInfo.innerHTML,'');assert.match(f.elements.discoveryRunInfo.textContent,/<script>/);assert.equal(f.elements.discoveryRunInfo.innerHTML,'');
});

test('read-only failures never retry by themselves and require another explicit click',async()=>{
 for(const id of ['discoveryFamilyAssess','discoveryRunInspect']){
  const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('disconnected')};await f.elements[id].onclick();assert.equal(f.calls.length,1);assert.equal(f.elements[id].disabled,false);
  await f.elements[id].onclick();assert.equal(f.calls.length,2);assert.equal(f.calls.some(c=>c.path==='/api/discovery/ingest'),false);
 }
});

test('unknown ledger save blocks family captures assessments and readiness too',async()=>{
 const f=fixture();await f.elements.discoveryBrowserCapture.onclick();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('save disconnected')};await f.elements.discoveryBrowserSave.onclick();
 for(const id of ['discoveryFamilyCapture','discoveryFamilyAssess','discoveryRunInspect']){await f.elements[id].onclick();assert.equal(f.elements[id].disabled,true)}
 assert.equal(f.calls.length,2);assert.equal(f.calls[1].path,'/api/discovery/ingest');
});

test('family controls require crypto and all new controls disable on scope invalidation',async()=>{
 const f=fixture();f.context.crypto={};await f.elements.discoveryFamilyCapture.onclick();assert.equal(f.calls.length,0);f.context.discoveryBrowserInvalidate();
 for(const id of ['discoveryFamilyTarget','discoveryFamilyCapture','discoveryFamilyAssess','discoveryRunInspect'])assert.equal(f.elements[id].disabled,true);
});

test('family page ownership route binding and inaccessible failures never qualify or fabricate membership',async()=>{
 for(const [status,reason] of [['blocked','page_or_ownership_changed'],['blocked','capture_evidence_or_scope_invalid'],['configuration_blocked','explicit_discovery_binding_required'],['execution_unknown','family_capture_timeout']]){
  const f=fixture(),receipt={...familyReceipt(f),status,reason};delete receipt.evidence;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return receipt};
  await f.elements.discoveryFamilyCapture.onclick();await f.elements.discoveryBrowserSave.onclick();assert.equal(f.calls.length,1);assert.equal(f.elements.discoveryBrowserSave.disabled,true);assert.equal(f.shown.length,0);
  assert.doesNotMatch(f.elements.discoveryBrowserInfo.textContent,/已采集变体页面观察/);assert.equal(f.elements.discoveryFamilyCapture.disabled,status==='execution_unknown');
 }
});


test('capture and history refresh invalidate a completed history-bound plan without rerunning it',async()=>{
 for(const action of ['discoveryFamilyCapture','discoveryBrowserCapture','discoveryBrowserRefresh']){
  const f=fixture();f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/prepare-plan')?planReceipt(f):path.endsWith('/captures')?{items:[]}:action==='discoveryFamilyCapture'?familyReceipt(f):f.receipt};
  await f.elements.discoveryPlanPrepare.onclick();assert.match(f.elements.discoveryPlanPreview.textContent,/search_capture/);
  await f.elements[action].onclick();assert.equal(f.elements.discoveryPlanPreview.textContent,'');assert.match(f.elements.discoveryPlanInfo.textContent,/采集记录可能已变化/);
  assert.equal(f.calls.length,2);assert.equal(f.calls.filter(c=>c.path==='/api/discovery/prepare-plan').length,1);
  await f.elements.discoveryPlanPrepare.onclick();assert.match(f.elements.discoveryPlanPreview.textContent,/search_capture/);assert.equal(f.calls.length,3);
 }
});

test('pending plan cannot overwrite newer history results or errors and does not allow concurrent capture',async()=>{
 for(const fails of [false,true]){
  const f=fixture();let resolveHistory,resolvePlan,rejectPlan;
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return path.endsWith('/captures')?new Promise(r=>resolveHistory=r):new Promise((resolve,reject)=>{resolvePlan=resolve;rejectPlan=reject})};
  const history=f.elements.discoveryBrowserRefresh.onclick(),plan=f.elements.discoveryPlanPrepare.onclick();
  await f.elements.discoveryFamilyCapture.onclick();assert.equal(f.calls.length,2);assert.equal(f.elements.discoveryFamilyCapture.disabled,true);
  resolveHistory({items:[{captureId:'new-family',captureKind:'family',status:'blocked'}]});await history;
  assert.equal(f.elements.discoveryPlanPreview.textContent,'');assert.match(f.elements.discoveryPlanInfo.textContent,/采集记录可能已变化/);
  if(fails)rejectPlan(Error('outdated plan failure'));else resolvePlan(planReceipt(f));await plan;
  assert.equal(f.elements.discoveryPlanPreview.textContent,'');assert.match(f.elements.discoveryPlanInfo.textContent,/采集记录可能已变化/);assert.doesNotMatch(f.elements.discoveryPlanInfo.textContent,/outdated plan failure/);
  assert.equal(f.calls.length,2);assert.equal(f.elements.discoveryPlanPrepare.disabled,false);
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return familyReceipt(f)};await f.elements.discoveryFamilyCapture.onclick();
  assert.equal(f.calls.length,3);assert.equal(f.elements.discoveryPlanPreview.textContent,'');
  f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return planReceipt(f)};await f.elements.discoveryPlanPrepare.onclick();
  assert.match(f.elements.discoveryPlanPreview.textContent,/search_capture/);assert.equal(f.calls.length,4);
 }
});

test('a pending plan from an older mount stays discarded after a new family capture',async()=>{
 const f=fixture();let resolvePlan;f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>resolvePlan=r)};
 const pending=f.elements.discoveryPlanPrepare.onclick();f.context.discoveryBrowserMount(f.report,f.context.signedUser,3);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return familyReceipt(f)};await f.elements.discoveryFamilyCapture.onclick();
 resolvePlan(planReceipt(f));await pending;assert.equal(f.elements.discoveryPlanPreview.textContent,'');assert.match(f.elements.discoveryPlanInfo.textContent,/采集记录可能已变化/);
 assert.equal(f.calls.length,2);assert.equal(f.calls[1].path,'/api/discovery/capture-family');assert.equal(f.elements.discoveryBrowserSave.disabled,true);
});
