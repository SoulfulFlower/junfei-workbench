const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const workflow=fs.readFileSync(__dirname+'/workflow.js','utf8');
const enhancements=fs.readFileSync(__dirname+'/enhancements.js','utf8');
const helpers=workflow.slice(workflow.indexOf('const listingFields'),workflow.indexOf('function workflowVariants'))+
 workflow.slice(workflow.indexOf('function workflowSnapshot'),workflow.indexOf('const workflowEnhanceBefore'));
const generation=enhancements.slice(enhancements.indexOf('function listingBatchReason'),enhancements.indexOf('// Session bootstrap'));

function harness(){
 const products=[{id:'a',name:'First',material:'cotton',market:'US'},
  {id:'b',name:'Second',material:'linen',market:'UK'}];
 const state={products,copy:{'b-UK':{title:'Locked title',lockedFields:['title'],translations:{title:'保留标题'}}},reviews:{}};
 const events=[],start={},close={},options=products.map((_,i)=>({value:String(i)}));
 const results={lines:[],replaceChildren(){this.lines=[]},append(line){this.lines.push(line)}};
 const modal={querySelector:selector=>({'#listingBatchStart':start,'#listingBatchClose':close,'#listingBatchResults':results}[selector]),
  querySelectorAll:()=>options,showModal(){this.open=true}};
 const ctx=vm.createContext({state,signedUser:{id:2},structuredClone,activeListingGeneration:new Map(),
  listingTextProvider:'Fixture',view:'products',syncConflict:false,
  document:{getElementById:()=>modal,createElement:()=>({})},
  confirm:()=>{events.push('confirmed');return true},esc:String,toast(){},
  durableGenerateCurrent:async(p,site,button,opts)=>{events.push({id:p.id,site,batch:opts.batch});return p.id==='a'?{status:'failed',message:'Fixture failure'}:{status:'saved',message:'已更新当前 Listing 文案'}}
 });
 vm.runInContext(helpers+generation,ctx);
 return {ctx,products,state,events,start,results};
}

test('default entry delegates to the durable task module',async()=>{
 const {ctx,products,events}=harness();
 assert.equal((await ctx.generateCurrent(products[1],'UK',{}, {batch:true})).status,'saved');
 assert.deepEqual(events,[{id:'b',site:'UK',batch:true}]);
});

test('batch keeps the single confirmation and continues after one product failure',async()=>{
 const {ctx,start,events,results}=harness();
 ctx.listingBatchDialog();await start.onclick();
 assert.equal(events.filter(e=>e==='confirmed').length,1);
 assert.deepEqual(events.filter(e=>typeof e==='object'),[{id:'a',site:'US',batch:true},{id:'b',site:'UK',batch:true}]);
 assert.match(results.lines[0].textContent,/Fixture failure/);
 assert.match(results.lines[1].textContent,/已更新当前 Listing 文案/);
});

test('batch stops when the account changes',async()=>{
 const {ctx,start,events}=harness();
 ctx.durableGenerateCurrent=async(p)=>{events.push(p.id);ctx.signedUser={id:3};return {status:'background',message:'saved to original account'}};
 ctx.listingBatchDialog();await start.onclick();
 assert.ok(events.includes('a'));assert.equal(events.includes('b'),false);
});

test('locked fields still block a new generation before the task entry',()=>{
 const {ctx,products,state}=harness();
 state.copy['a-US']={lockedFields:['title','highlights','bullets','description','terms']};
 assert.match(ctx.listingBatchReason(products[0],'US'),/全部字段已锁定/);
});

test('history restores the chosen site version while preserving current locks',()=>{
 const {ctx,state}=harness(),p=state.products[1];
 p.copyHistory=[{market:'UK',copy:{title:'Older title',description:'Older'}},{market:'UK',copy:{title:'Old title',description:'Old'}},
  {market:'US',copy:{description:'US history'}}];
 const parts=Object.fromEntries(['historyLeft','historyRight','restoreHistory','historyPreview','closeHistory'].map(key=>[key,{value:'current'}]));
 const modal={style:{},querySelector:id=>parts[id.slice(1)],showModal(){},close(){}};
 ctx.market='UK';ctx.document={getElementById:()=>modal};ctx.render=()=>{};ctx.persist=()=>{};
 vm.runInContext(workflow.slice(workflow.indexOf('function workflowHistory')),ctx);
 ctx.workflowHistory(p);parts.historyLeft.value='1';parts.historyLeft.onchange();
 assert.match(parts.historyPreview.innerHTML,/Older/);assert.doesNotMatch(parts.historyPreview.innerHTML,/US history/);
 parts.restoreHistory.onclick();
 assert.equal(state.copy['b-UK'].title,'Locked title');assert.equal(state.copy['b-UK'].description,'Old');
 assert.equal(p.copyHistory.at(-1).copy.title,'Locked title');
});
