const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,name),'utf8');
const plain=value=>JSON.parse(JSON.stringify(value));
function client(fetch){
 const p={id:'coat',masterColor:'White'};
 const context={fetch,Uint8Array,state:{products:[p],reviews:{}},signedUser:{id:2},serverRevision:62,
  syncConflict:false,syncPending:false,flushWorkspace:async()=>{},basePersist(){},syncLabel(){},showConflict(){}};
 vm.createContext(context);vm.runInContext(read('colour-api.js'),context);
 return {context,p,api:vm.runInContext('ColourApi',context)};
}

test('colour client preserves endpoints, request payloads and error status',async()=>{
 const requests=[];const {api}=client(async(url,options)=>{
  requests.push({url,options});return {ok:true,json:async()=>({retained:true})};
 });
 await api.sets('coat&US');
 const payload={productId:'coat',colorKey:'dark gray',confirmed:true,revision:62};
 await api.post('reinstate',payload);
 assert.equal(requests[0].url,'/api/colours/sets?productId=coat%26US');
 assert.equal(requests[1].url,'/api/colours/reinstate');
 assert.deepEqual(JSON.parse(requests[1].options.body),payload);
 const failed=client(async()=>({ok:false,status:409,json:async()=>({error:'Version changed'})}));
 await assert.rejects(()=>failed.api.post('master',payload),e=>e.status===409&&e.message==='Version changed');
});

test('association writes merge only after successful account and version checks',async()=>{
 const {context,p}=client(async()=>({ok:true,json:async()=>({revision:63,product:{id:'coat',masterColor:'White',colors:2},review:{images:false}})}));
 await context.saveColourAssociation(p,'reinstate','dark gray');
 assert.equal(p.colors,2);assert.equal(context.serverRevision,63);
 assert.equal(context.state.reviews.coat.images,false);
 const conflict=client(async()=>({ok:false,status:409,json:async()=>({error:'stale'})}));
 await assert.rejects(()=>conflict.context.saveColourAssociation(conflict.p,'master','dark gray'),/stale/);
 assert.equal(conflict.p.masterColor,'White');assert.equal(conflict.context.serverRevision,62);
 assert.equal(conflict.context.syncConflict,true);
});

test('in-flight local edits or account changes prevent stale response adoption',async()=>{
 let current;
 const edited=client(async()=>{current.state.products[0].localEdit='preserve';return {ok:true,json:async()=>({revision:63,product:{id:'coat',masterColor:'Dark Gray'}})}});
 current=edited.context;
 await assert.rejects(()=>current.saveColourAssociation(edited.p,'master','dark gray'),/同时有其他修改/);
 assert.equal(edited.p.localEdit,'preserve');assert.equal(edited.p.masterColor,'White');assert.equal(current.syncConflict,true);
 const switched=client(async()=>{current.signedUser={id:3};return {ok:true,json:async()=>({revision:63,product:{id:'coat',masterColor:'Dark Gray'}})}});
 current=switched.context;
 await assert.rejects(()=>current.saveColourAssociation(switched.p,'master','dark gray'),/登录账号已变化/);
 assert.equal(switched.p.masterColor,'White');assert.equal(current.serverRevision,62);
});

test('view predicates preserve confirmed-master and pending-colour distinctions',()=>{
 const context={};vm.createContext(context);vm.runInContext(read('colour-view-rules.js'),context);
 const rules=vm.runInContext('ColourViewRules',context),groups=[
  {key:'white',ready:true,listingEligible:true},
  {key:'dark gray',ready:false,listingEligible:false},
  {key:'light brown',ready:false,listingEligible:false}
 ];
 assert.deepEqual(plain(rules.confirmedMasters(groups)),[groups[0]]);
 assert.deepEqual(plain(rules.targets(groups,'white')),groups.slice(1));
 assert.equal(rules.canGenerate(groups[1],false,'verified-image','white'),false);
 assert.equal(rules.canGenerateAll(groups,false,'white'),false);
 assert.equal(rules.canGenerate({...groups[1],ready:true},false,'verified-image','white'),true);
});

test('split script dependencies load and old mount adapter runs without HTTP side effects',()=>{
 const files=['colour-api.js','colour-view-rules.js','colour-pixel-tools.js','colour-page.js','colour-sets.js'];
 const html=read('index.html');let previous=-1;
 for(const file of files){const offset=html.indexOf('src="'+file+'"');assert.ok(offset>previous,file);previous=offset;}
 const calls=[];const context={mountImageGeneration(){calls.push('base')},mountBuyerInsights(){},render(){},product(){return null},
  document:{getElementById(){return null}},clearTimeout(){},fetch(){throw Error('Unexpected HTTP request during mounting')}};
 vm.createContext(context);for(const file of files)vm.runInContext(read(file),context,{filename:file});
 context.mountImageGeneration();assert.deepEqual(calls,['base']);
 for(const file of ['colour-page.js','colour-pixel-tools.js'])assert.doesNotMatch(read(file),/\bfetch\s*\(/);
});
