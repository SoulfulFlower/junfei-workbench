const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/discovery-ui.js','utf8')+'\n'+fs.readFileSync(__dirname+'/selection.js','utf8');
const payload={cycleId:'local-cycle',expectedRevision:0,events:[{id:'event-1',kind:'keyword'}]};
function fixture(){
 const calls=[],downloads=[],toasts=[],elements={};
 for(const id of ['discoveryFile','discoverySave','discoveryInputInfo','discoveryTemplate','discoveryMarket','discoveryRefresh','discoveryHistory','discoveryReport','discoveryDownload'])
  elements[id]={value:id==='discoveryMarket'?'US':'',files:[],disabled:false,textContent:'',innerHTML:'',children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)}};
 const context=vm.createContext({names:{},render(){},view:'selection',signedUser:{id:1},
  esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  document:{getElementById:id=>elements[id],createElement:()=>({style:{}})},
  toast:m=>toasts.push(m),download:(...args)=>downloads.push(args),clearTimeout,setTimeout});
 vm.runInContext(source,context);vm.runInContext('selectionEpoch=3',context);
 const report={cycleId:'local-cycle',revision:1,counts:{discoveredProducts:2,recordedSellers:1,qualified:0,imported:0},queue:[],products:[],sellers:[],edges:[],qualificationEvaluated:false};
 context.selectionApi=async(path,data)=>{calls.push({path,data});return path.endsWith('history')?{items:[]}:report};
 const file={size:100,text:async()=>JSON.stringify(payload)};
 return {context,calls,downloads,toasts,elements,report,file};
}
test('product links use actual marketplace and reject unknown/unsafe inputs',()=>{
 const f=fixture();
 assert.equal(f.context.selectionProductUrl('DE','B012345678'),'https://www.amazon.de/dp/B012345678');
 assert.equal(f.context.selectionProductUrl('JP','B012345678'),'https://www.amazon.co.jp/dp/B012345678');
 assert.equal(f.context.selectionProductUrl('CA','B012345678'),'https://www.amazon.ca/dp/B012345678');
 for(const args of [['XX','B012345678'],['US','<bad>'],['US',null]])
  assert.equal(f.context.selectionProductUrl(...args),'');
});
test('market statistics are explicitly third-party estimates',()=>{
 const s=fs.readFileSync(__dirname+'/selection.js','utf8');
 assert.match(s,/第三方月销量估算/);
 assert.doesNotMatch(s,/卖家精灵真实数据/);
});
test('file validation rejects large malformed or blank format without requests',async()=>{
 const f=fixture();
 for(const file of [null,{size:1024*1024+1,text:async()=>''},{size:1,text:async()=>'[]'},{size:10,text:async()=>'{broken'},{size:10,text:async()=>JSON.stringify({...payload,events:[]})}])
  await assert.rejects(()=>f.context.discoveryParseFile(file));
 assert.equal(f.calls.length,0);
});
test('file preview is local, explicit save sends one request with immutable version',async()=>{
 const f=fixture();let release;
 f.context.discoveryMount(3);await Promise.resolve();
 f.elements.discoveryFile.files=[f.file];await f.elements.discoveryFile.onchange();
 assert.equal(f.calls.filter(x=>x.data).length,0);assert.equal(f.elements.discoverySave.disabled,false);
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});if(path.endsWith('ingest'))return new Promise(r=>release=r);return {items:[]}};
 const first=f.elements.discoverySave.onclick(),second=f.elements.discoverySave.onclick();
 release(f.report);await Promise.all([first,second]);
 const saves=f.calls.filter(x=>x.path.endsWith('ingest'));assert.equal(saves.length,1);
 assert.equal(saves[0].data.expectedRevision,0);assert.equal(f.elements.discoverySave.disabled,true);
 assert.equal(f.calls.some(x=>x.path.includes('/selection/start')||x.path.includes('/selection/import')||x.path.includes('/agent/start')),false);
});
test('changed account during file read cannot stage or save data',async()=>{
 const f=fixture();let release;f.context.discoveryMount(3);
 f.elements.discoveryFile.files=[{size:100,text:()=>new Promise(r=>release=r)}];
 const read=f.elements.discoveryFile.onchange();f.context.signedUser={id:2};release(JSON.stringify(payload));await read;
 await f.elements.discoverySave.onclick();assert.equal(f.calls.filter(x=>x.data).length,0);
});
test('last chosen file wins when file reads return out of order',async()=>{
 const f=fixture();let first;f.context.discoveryMount(3);
 f.elements.discoveryFile.files=[{size:100,text:()=>new Promise(r=>first=r)}];const pending=f.elements.discoveryFile.onchange();
 f.elements.discoveryFile.files=[{size:100,text:async()=>JSON.stringify({...payload,cycleId:'last-cycle'})}];await f.elements.discoveryFile.onchange();
 first(JSON.stringify(payload));await pending;
 assert.match(f.elements.discoveryInputInfo.textContent,/last-cycle/);
});
test('rejected version does not auto retry or change expected revision',async()=>{
 const f=fixture();f.context.discoveryMount(3);f.elements.discoveryFile.files=[f.file];await f.elements.discoveryFile.onchange();
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});throw Error('stale revision')};
 await f.elements.discoverySave.onclick();assert.equal(f.calls.filter(x=>x.data).length,1);
 assert.equal(f.calls.find(x=>x.data).data.expectedRevision,0);assert.deepEqual(f.toasts,['stale revision']);
});
test('report escapes imported text and distinguishes observed from qualified',()=>{
 const f=fixture(),html=f.context.discoveryReportHTML({...f.report,cycleId:'<img onerror=bad>',queue:[{note:'<script>bad</script>'}]});
 assert.match(html,/&lt;img onerror=bad&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(html,/同款、排名|所有边均为待核验观察/);assert.match(html,/实际入库 0/);
});
test('late reports and old download callbacks cannot cross account boundary',()=>{
 const f=fixture(),owner=f.context.signedUser;f.context.discoveryShow(f.report,owner,3);
 const handler=f.elements.discoveryDownload.onclick;f.context.signedUser={id:2};handler();
 assert.equal(f.downloads.length,0);
 f.elements.discoveryReport.innerHTML='new account';
 f.context.discoveryShow(f.report,owner,3);assert.equal(f.elements.discoveryReport.innerHTML,'new account');
});
test('navigation during save does not display stale report or trigger another action',async()=>{
 const f=fixture();let release;f.context.discoveryMount(3);f.elements.discoveryFile.files=[f.file];await f.elements.discoveryFile.onchange();
 f.context.selectionApi=async(path,data)=>{f.calls.push({path,data});return new Promise(r=>release=r)};
 const pending=f.elements.discoverySave.onclick();vm.runInContext("selectionEpoch=4;view='listing'",f.context);
 release(f.report);await pending;assert.equal(f.elements.discoveryReport.innerHTML,'');
 assert.equal(f.calls.filter(x=>x.data).length,1);
});

test('selection cached market report is cleared across local login identities',()=>{
 const f=fixture();f.context.selectionResetAccountCache();
 vm.runInContext("selectionReport={secret:'prior account'};selectionChosenProfile='old-profile';",f.context);
 f.context.signedUser={id:2};f.context.selectionResetAccountCache();
 assert.equal(vm.runInContext('selectionReport',f.context),null);
 assert.equal(vm.runInContext('selectionChosenProfile',f.context),'');
});

test('latest history selection wins when reports return out of order',async()=>{
 const f=fixture(),pending={};
 f.context.selectionApi=async(path)=>path.endsWith('/history')?{items:[{cycleId:'older',revision:1},{cycleId:'newer',revision:1}]}:new Promise(r=>pending[path]=r);
 await f.context.discoveryHistory(3);
 const a=f.elements.discoveryHistory.children[0].onclick(),b=f.elements.discoveryHistory.children[1].onclick();
 pending['/api/discovery/report?id=newer']({...f.report,cycleId:'newer-cycle'});await b;
 pending['/api/discovery/report?id=older']({...f.report,cycleId:'older-cycle'});await a;
 assert.match(f.elements.discoveryReport.innerHTML,/newer-cycle/);assert.doesNotMatch(f.elements.discoveryReport.innerHTML,/older-cycle/);
});
test('completed older file save cannot replace a newer report selection',async()=>{
 const f=fixture();f.context.discoveryMount(3);f.elements.discoveryFile.files=[f.file];await f.elements.discoveryFile.onchange();
 let release;f.context.selectionApi=async(path)=>path.endsWith('/ingest')?new Promise(r=>release=r):{items:[]};
 const save=f.elements.discoverySave.onclick();
 f.context.discoveryShow({...f.report,cycleId:'chosen-newer'},f.context.signedUser,3);
 release({...f.report,cycleId:'old-saved'});await save;
 assert.match(f.elements.discoveryReport.innerHTML,/chosen-newer/);assert.doesNotMatch(f.elements.discoveryReport.innerHTML,/old-saved/);
});
