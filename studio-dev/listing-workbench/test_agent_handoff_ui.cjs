const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/agent-center.js','utf8');
function fixture(){
 const calls=[],toasts=[],refreshed=[],elements={};
 const modal={open:false,innerHTML:'',listeners:[],
  addEventListener(kind,fn){if(kind==='close')this.listeners.push(fn)},
  showModal(){this.open=true},close(){this.open=false;for(const fn of this.listeners.splice(0))fn()}};
 elements.modal=modal;
 for(const id of ['agentCopyHandoffForm','agentCopyHandoffBudget','agentCopyHandoffAsins','agentCopyHandoffConsent','agentCopyHandoffCancel','agentCopyHandoffSave'])
  elements[id]={value:'',checked:false,disabled:false,isConnected:true};
 const context=vm.createContext({names:{},render(){},view:'agent',serverRevision:7,
  esc:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  document:{getElementById:id=>elements[id]},toast:value=>toasts.push(value),
  flushWorkspace:async()=>{},setTimeout,clearTimeout});
 vm.runInContext(source,context);
 vm.runInContext("agentEpoch=3;agentSelectedTask='task';",context);
 context.agentApi=async(path,data)=>{calls.push({path,data});return {task:{id:'task'}}};
 context.agentRefresh=async epoch=>refreshed.push(epoch);
 const task={id:'task',productName:'Synthetic <product>',profile:{store:'Fixture',marketplace:'US',mode:'draft'},
  intake:{source:'selection-report'},taskMode:'production',status:'blocked',results:{facts:{ok:true}}};
 function valid(){elements.agentCopyHandoffBudget.value='2.50';elements.agentCopyHandoffConsent.checked=true;elements.agentCopyHandoffAsins.value='B012345678'}
 const submit=()=>elements.agentCopyHandoffForm.onsubmit({preventDefault(){}});
 return {context,calls,toasts,refreshed,elements,modal,task,valid,submit};
}
test('scope bar exposes only the four permitted stages',()=>{
 const f=fixture(),task={...f.task,executionScope:'selection_to_copy',cursor:4,results:{plan:{ok:true},facts:{ok:true},research:{ok:true},listing:{ok:true}}};
 const html=f.context.agentStageBar(task);
 assert.doesNotMatch(html,/商品图片|交付导出|钧飞刊登|在售核对/);
 assert.equal((html.match(/class="agent-stage /g)||[]).length,4);
});
test('eligibility excludes non-selection, running, publishing and exported tasks',()=>{
 const f=fixture();assert.equal(f.context.agentCanPrepareCopyHandoff(f.task),true);
 for(const change of [{intake:{}},{status:'running'},{profile:{mode:'publish'}},{exportAvailable:true},{copyHandoff:{}},{results:{publish:{ok:false}}}])
  assert.equal(f.context.agentCanPrepareCopyHandoff({...f.task,...change}),false);
});
test('dialog escapes product data and explains non-hard budget and no immediate execution',async()=>{
 const f=fixture();await f.context.agentCopyHandoffDialog(f.task,3);
 assert.match(f.modal.innerHTML,/Synthetic &lt;product&gt;/);
 assert.match(f.modal.innerHTML,/不是账单硬上限/);
 assert.match(f.modal.innerHTML,/保存并排队，不立即执行/);
 assert.equal(f.calls.length,0);
});
test('unchecked paid consent cannot submit',async()=>{
 const f=fixture();await f.context.agentCopyHandoffDialog(f.task,3);f.elements.agentCopyHandoffBudget.value='5';
 await f.submit();assert.equal(f.calls.length,0);assert.equal(f.toasts.length,1);
});
test('invalid budget cannot submit',async()=>{
 const f=fixture();await f.context.agentCopyHandoffDialog(f.task,3);f.valid();f.elements.agentCopyHandoffBudget.value='Infinity';
 await f.submit();assert.equal(f.calls.length,0);
});
test('cancel while workspace flush is pending sends no request',async()=>{
 const f=fixture();let release;f.context.flushWorkspace=()=>new Promise(resolve=>release=resolve);
 await f.context.agentCopyHandoffDialog(f.task,3);f.valid();const pending=f.submit();
 f.elements.agentCopyHandoffCancel.onclick();release();await pending;
 assert.equal(f.calls.length,0);assert.equal(f.modal.open,false);
});
test('new navigation while flush is pending sends no request',async()=>{
 const f=fixture();let release;f.context.flushWorkspace=()=>new Promise(resolve=>release=resolve);
 await f.context.agentCopyHandoffDialog(f.task,3);f.valid();const pending=f.submit();
 vm.runInContext("agentEpoch=4;view='listing';",f.context);release();await pending;
 assert.equal(f.calls.length,0);
});
test('repeated submit sends one authorization and never start',async()=>{
 const f=fixture();let release;f.context.flushWorkspace=()=>new Promise(resolve=>release=resolve);
 await f.context.agentCopyHandoffDialog(f.task,3);f.valid();const first=f.submit(),second=f.submit();
 release();await Promise.all([first,second]);
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].path,'prepare-copy-handoff');
 assert.equal(f.calls[0].data.workspaceRevision,7);assert.equal(f.calls[0].data.confirmPaidText,true);
 assert.equal(f.calls[0].data.acknowledgeBudgetNotHardCap,true);
 assert.equal(f.calls[0].data.budgetCny,2.5);assert.equal(f.modal.open,false);assert.equal(f.refreshed.length,1);
});
test('server rejection keeps dialog open and restores save',async()=>{
 const f=fixture();f.context.agentApi=async()=>{throw Error('facts not qualified')};
 await f.context.agentCopyHandoffDialog(f.task,3);f.valid();await f.submit();
 assert.equal(f.modal.open,true);assert.equal(f.elements.agentCopyHandoffSave.disabled,false);
 assert.deepEqual(f.toasts,['facts not qualified']);assert.equal(f.refreshed.length,0);
});
