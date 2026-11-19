const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/agent-center.js','utf8');
function fixture(){
 const calls=[],downloads=[],toasts=[],modal={innerHTML:'',open:false,showModal(){this.open=true},close(){this.open=false}};
 const elements={modal,agentImagePreparationClose:{},agentImagePreparationDownload:{}};
 const context=vm.createContext({names:{},render(){},view:'agent',serverRevision:7,signedUser:{id:1},
  esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  document:{getElementById:id=>elements[id]},toast:m=>toasts.push(m),download:(...args)=>downloads.push(args),
  flushWorkspace:()=>{throw Error('Read-only preview must not flush or save')},setTimeout,clearTimeout});
 vm.runInContext(source,context);vm.runInContext("agentEpoch=3;agentSelectedTask='task';",context);
 const task={id:'task',status:'blocked',executionScope:'selection_to_copy',profile:{mode:'draft'}};
 const preparation={readyForManualPreparation:false,plannedColorCount:2,galleryCountPerColor:7,plannedImageCount:14,
  blockers:['Missing <evidence>'],sets:[{color:'<Black>',role:'master',children:[{sku:'S&1',size:'M'}],references:[]}],
  productionReady:false,paidCallsAllowed:false};
 context.agentApi=async(path,data)=>{calls.push({path,data});return {preparation}};
 return {context,calls,downloads,toasts,elements,modal,task,preparation};
}
test('only stopped original copy scope exposes image metadata preview',()=>{
 const f=fixture();assert.equal(f.context.agentCanPreviewImages(f.task),true);
 for(const change of [{status:'running'},{executionScope:null},{profile:{mode:'publish'}}])
  assert.equal(f.context.agentCanPreviewImages({...f.task,...change}),false);
});
test('preview performs one GET without save, start or paid dispatch',async()=>{
 const f=fixture();await f.context.agentImagePreparationDialog(f.task,3);
 assert.deepEqual(f.calls,[{path:'image-preparation?id=task&revision=7',data:undefined}]);
 assert.equal(f.modal.open,true);assert.match(f.modal.innerHTML,/不是已完成图片数/);
 assert.match(f.modal.innerHTML,/Missing &lt;evidence&gt;/);assert.match(f.modal.innerHTML,/&lt;Black&gt;/);
 assert.match(f.modal.innerHTML,/S&amp;1/);assert.doesNotMatch(f.modal.innerHTML,/<Black>/);
});
test('unknown revision sends nothing',async()=>{
 const f=fixture();f.context.serverRevision=null;await f.context.agentImagePreparationDialog(f.task,3);
 assert.equal(f.calls.length,0);assert.equal(f.toasts.length,1);assert.equal(f.modal.open,false);
});
test('late response cannot open modal after navigation',async()=>{
 const f=fixture();let resolve;f.context.agentApi=()=>new Promise(r=>resolve=r);
 const promise=f.context.agentImagePreparationDialog(f.task,3);
 vm.runInContext("agentSelectedTask='other';",f.context);resolve({preparation:f.preparation});await promise;
 assert.equal(f.modal.open,false);
});
test('rejected snapshot displays error and cannot download',async()=>{
 const f=fixture();f.context.agentApi=async()=>{throw Error('stale snapshot')};
 await f.context.agentImagePreparationDialog(f.task,3);
 assert.deepEqual(f.toasts,['stale snapshot']);assert.equal(f.modal.open,false);assert.equal(f.downloads.length,0);
});
test('download contains only returned preparation and does not mutate task',async()=>{
 const f=fixture(),original=JSON.stringify(f.task);
 await f.context.agentImagePreparationDialog(f.task,3);f.elements.agentImagePreparationDownload.onclick();
 assert.equal(f.downloads.length,1);assert.equal(f.downloads[0][0],'image-preparation-task.json');
 assert.deepEqual(JSON.parse(f.downloads[0][1]),f.preparation);assert.equal(JSON.stringify(f.task),original);
 assert.equal(f.calls.length,1);f.elements.agentImagePreparationClose.onclick();assert.equal(f.modal.open,false);
});

test('account change during request prevents display',async()=>{
 const f=fixture();let resolve;f.context.agentApi=()=>new Promise(r=>resolve=r);
 const promise=f.context.agentImagePreparationDialog(f.task,3);
 f.context.signedUser={id:2};resolve({preparation:f.preparation});await promise;
 assert.equal(f.modal.open,false);
});
test('old download callback refuses changed account or epoch',async()=>{
 const f=fixture();await f.context.agentImagePreparationDialog(f.task,3);
 const handler=f.elements.agentImagePreparationDownload.onclick;
 f.context.signedUser={id:2};handler();assert.equal(f.downloads.length,0);
 f.context.signedUser=null;handler();assert.equal(f.downloads.length,0);
});
test('login screen closes and removes previous account modal contents',()=>{
 const auth=fs.readFileSync(__dirname+'/auth.js','utf8');
 const state={open:true,children:['private report'],closed:0,cleared:0,close(){this.open=false;this.closed++},replaceChildren(){this.children=[];this.cleared++}};
 const panel={removed:0,remove(){this.removed++}};
 const context=vm.createContext({document:{getElementById:id=>id==='modal'?state:panel}});
 const helper=auth.slice(auth.indexOf('function clearAccountDialogs(){'),auth.indexOf('function loginScreen('));
 vm.runInContext(helper,context);context.clearAccountDialogs();
 assert.equal(state.open,false);assert.equal(state.closed,1);assert.deepEqual(state.children,[]);assert.equal(panel.removed,1);
 assert.match(auth,/function loginScreen\(setup=false,register=false\)\{clearAccountDialogs\(\);/);
});
