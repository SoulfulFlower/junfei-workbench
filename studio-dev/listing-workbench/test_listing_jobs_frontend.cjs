const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/listing-jobs.js','utf8');

function harness(){
 const calls=[],owner={id:2},product={id:'P',name:'Product',material:'cotton'};
 const stored={products:[product],copy:{'P-US':{title:'Existing'}},reviews:{}};
 let job={id:'job-id','productId':'P',market:'US',status:'running',workspaceRevision:2},revision=2;
 const ctx=vm.createContext({Map,Set,Date,Math,Promise,JSON,encodeURIComponent,structuredClone,
  crypto:{randomUUID:()=> 'request-12345'},setTimeout:fn=>{queueMicrotask(fn)},
  signedUser:owner,serverReady:true,serverRevision:1,syncPending:false,syncBusy:false,syncConflict:false,
  state:structuredClone(stored),activeListingGeneration:new Map(),view:'products',selected:'P',market:'US',
  listingTextProvider:'Fixture',listingFields:[['title','Title']],
  render(){},mountListingProgress(){},updateListingCopyActions(){},syncLabel(){},toast(){},
  flushWorkspace:async()=>{},listingBatchReason:()=>'',confirm:()=>true,initServer:async()=>true,
  fetch:async(url,opts={})=>{
   calls.push({url,method:opts.method||'GET',data:opts.body&&JSON.parse(opts.body)});
   if(url==='/api/state')return {ok:true,json:async()=>({revision,state:structuredClone(stored)})};
   if(url.endsWith('/start'))return {ok:true,json:async()=>({job:structuredClone(job)})};
   if(url.endsWith('/list'))return {ok:true,json:async()=>({jobs:[structuredClone(job)]})};
   if(url.includes('/status?')){
    job={...job,status:'applied',resultAvailable:true,workspaceRevision:++revision};
    stored.copy['P-US']={title:'Generated on server'};
    return {ok:true,json:async()=>({job:structuredClone(job)})};
   }
   throw Error('Unexpected request '+url);
  }
 });
 vm.runInContext(source,ctx);
 return {ctx,calls,owner,product,stored,getJob:()=>job,setJob:value=>{job={...job,...value}}};
}

test('default generation starts one durable task and never POSTs its result to workspace',async()=>{
 const {ctx,product,calls}=harness();
 const result=await ctx.durableGenerateCurrent(product,'US',{});
 assert.equal(result.status,'saved');
 assert.equal(ctx.state.copy['P-US'].title,'Generated on server');
 const starts=calls.filter(c=>c.url.endsWith('/start'));
 assert.equal(starts.length,1);
 assert.deepEqual(starts[0].data,{productId:'P',market:'US',requestId:'request-12345',expectedRevision:1});
 assert.equal(calls.some(c=>c.url==='/api/generate/listing'),false);
 assert.equal(calls.some(c=>c.url==='/api/state'&&c.method==='POST'),false);
});

test('reopening the page recovers an existing running job without starting a model',async()=>{
 const {ctx,calls}=harness();
 await ctx.restoreListingJobs();
 await Promise.all([...vm.runInContext('durableListingPolls.values()',ctx)]);
 assert.equal(ctx.state.copy['P-US'].title,'Generated on server');
 assert.equal(calls.some(c=>c.method==='POST'),false);
 assert.equal(ctx.activeListingGeneration.size,0);
});

test('lost start acknowledgement reconciles the saved job and never retries the POST',async()=>{
 const {ctx,calls,product}=harness();
 const fetch=ctx.fetch;
 let starts=0;
 ctx.fetch=async(url,opts)=>{if(url.endsWith('/start')){starts++;throw Error('lost acknowledgement')}return fetch(url,opts)};
 const outcome=await ctx.durableGenerateCurrent(product,'US',{});
 await Promise.all([...vm.runInContext('durableListingPolls.values()',ctx)]);
 assert.equal(starts,1);assert.equal(outcome.status,'uncertain');
 assert.equal(ctx.state.copy['P-US'].title,'Generated on server');
 assert.equal(calls.filter(c=>c.method==='POST').length,0);
});

test('a lost poll response keeps reading the original task',async()=>{
 const {ctx,product,calls}=harness();
 const fetch=ctx.fetch;let polls=0;
 ctx.fetch=async(url,opts)=>{if(url.includes('/status?')&&++polls===1)throw Error('offline');return fetch(url,opts)};
 assert.equal((await ctx.durableGenerateCurrent(product,'US',{})).status,'saved');
 assert.equal(polls,2);assert.equal(calls.filter(c=>c.url.endsWith('/start')).length,1);
});

test('account change ends browser polling without writing another account workspace',async()=>{
 const {ctx,product}=harness(),fetch=ctx.fetch;
 ctx.fetch=async(url,opts)=>{const result=await fetch(url,opts);if(url.endsWith('/start'))ctx.signedUser={id:3};return result};
 assert.equal((await ctx.durableGenerateCurrent(product,'US',{})).status,'background');
 assert.equal(ctx.state.copy['P-US'].title,'Existing');
 assert.equal(ctx.activeListingGeneration.size,0);
});

test('server completion preserves unsaved browser edits',async()=>{
 const {ctx,product}=harness(),fetch=ctx.fetch;
 ctx.fetch=async(url,opts)=>{const result=await fetch(url,opts);if(url.includes('/status?')){
  ctx.syncPending=true;ctx.state.copy['P-US'].title='Unsaved local edit';
 }return result};
 assert.equal((await ctx.durableGenerateCurrent(product,'US',{})).status,'saved');
 assert.equal(ctx.state.copy['P-US'].title,'Unsaved local edit');
 assert.equal(ctx.durableListingCurrent(product,'US').status,'applied');
});

test('account change during polling clears only the original account busy marker',async()=>{
 const {ctx,product}=harness(),fetch=ctx.fetch;
 ctx.fetch=async(url,opts)=>{const result=await fetch(url,opts);if(url.includes('/status?'))ctx.signedUser={id:3};return result};
 assert.equal((await ctx.durableGenerateCurrent(product,'US',{})).status,'background');
 assert.equal(ctx.activeListingGeneration.size,0);
 assert.equal(ctx.state.copy['P-US'].title,'Existing');
});

test('retained conflict result is shown without creating another paid task',async()=>{
 const {ctx,owner,product,calls}=harness();
 ctx.rememberDurableListing(owner,{id:'old','productId':'P',market:'US',status:'ready',resultAvailable:true});
 let viewed=0;ctx.showDurableListingResult=async()=>{viewed++};
 assert.equal((await ctx.durableGenerateCurrent(product,'US',{})).status,'skipped');
 assert.equal(viewed,1);assert.equal(calls.length,0);
});

test('recovery also refreshes a result that finished between initial workspace and job reads',async()=>{
 const {ctx,stored,setJob}=harness();
 stored.copy['P-US']={title:'Already completed'};
 setJob({status:'applied',workspaceRevision:2});
 await ctx.restoreListingJobs();
 assert.equal(ctx.state.copy['P-US'].title,'Already completed');
});
