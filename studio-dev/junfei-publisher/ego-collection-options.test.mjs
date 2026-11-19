import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {pickOption} from './ego-collection-prepare.mjs';

function fixture({labels=['Other','Target','Last'],index,duplicates=false,noHover=false,loseFocus=false,disabled=false}={}){
 const state={open:true,hover:-1,keys:[],clicks:0,selected:null,snapshots:[]};
 const element=(text='')=>({innerText:text,disabled:false,visible:true,
  getBoundingClientRect(){return{width:this.visible?100:0};},
  getAttribute(name){return name==='aria-disabled'&&this.disabled?'true':null;}});
 const controls=[element(),...(index===undefined?[]:[element()])];if(duplicates)controls.push(element());
 const options=labels.map((label,i)=>({...element(label),classList:{contains:name=>name==='hover'?state.hover===i:name==='is-disabled'&&disabled&&label==='Target'}}));
 const dropdown={getBoundingClientRect:()=>({width:state.open?100:0})};
 const selector=index===undefined?'input[placeholder="变体主体"]':'[role=dialog][aria-label="替换变体主题"] input';
 const document={activeElement:null,querySelectorAll(query){
  if(query===selector)return controls;
  if(query==='.el-select-dropdown li')return state.open?options:[];
  if(query==='.el-select-dropdown')return[dropdown];
  throw Error('Unexpected selector '+query);
 }};
 const evaluate=(fn,arg)=>vm.runInNewContext('('+fn.toString()+')(argument)',{argument:arg,document,getComputedStyle:e=>({visibility:e.visible===false?'hidden':'visible'})});
 const page={evaluate:async(fn,arg)=>evaluate(fn,arg),
  focus:async locator=>{assert.equal(locator,selector+(index===undefined?'':' >> nth='+index));document.activeElement=loseFocus?{}:controls[index??0];},
  press:async(locator,key)=>{
   assert.equal(locator,selector+(index===undefined?'':' >> nth='+index));state.keys.push(key);
   if(key==='ArrowDown'){if(!noHover)state.hover=(state.hover+1)%options.length;return;}
   assert.equal(key,'Enter');assert.equal(document.activeElement,controls[index??0]);
   assert.equal(options[state.hover]?.innerText,'Target');state.selected='Target';state.open=false;
  },
  click:async()=>{state.clicks++;throw Error('<li> intercepts pointer events');},
  waitForFunction:async(fn,arg)=>assert.equal(evaluate(fn,arg),true)};
 const record={draftId:'original',preparationInteractions:[{step:'old',phase:'failed',error:'Original pointer failure'}]};
 const persist=async()=>state.snapshots.push(structuredClone(record));
 return{state,page,record,persist,control:{selector,...(index===undefined?{}:{index})}};
}

test('real option inspection selects through trusted focus/ArrowDown/Enter with zero pointer clicks and durable checkpoints',async()=>{
 const f=fixture();
 await pickOption(f.page,'Target',f.control,f.record,f.persist,'variation_theme');
 assert.equal(f.state.selected,'Target');assert.deepEqual(f.state.keys,['ArrowDown','ArrowDown','Enter']);assert.equal(f.state.clicks,0);
 assert.deepEqual(f.record.preparationInteractions[0],{step:'old',phase:'failed',error:'Original pointer failure'});
 assert.equal(f.record.preparationInteractions[1].phase,'selected');
 assert.deepEqual(f.state.snapshots.map(s=>s.preparationInteractions.at(-1).phase),['started','option_unique','target_hovered','selected']);
});

test('mapping selection focuses only the observed indexed dialog input',async()=>{
 const f=fixture({index:1});
 await pickOption(f.page,'Target',f.control,f.record,f.persist,'variation_size');
 assert.equal(f.state.selected,'Target');assert.equal(f.record.preparationInteractions.at(-1).control.index,1);
 assert.equal(f.record.preparationInteractions.at(-1).step,'variation_size');assert.equal(f.state.clicks,0);
});

test('duplicate, empty, disabled or absent options and ambiguous controls fail without Enter',async()=>{
 for(const [config,label]of [
  [{labels:['Target','Target']},'Target'],[{},''],[{labels:['Other']},'Target'],
  [{disabled:true},'Target'],[{duplicates:true},'Target']
 ]){
  const f=fixture(config);await assert.rejects(()=>pickOption(f.page,label,f.control,f.record,f.persist));
  assert.equal(f.state.keys.includes('Enter'),false);assert.equal(f.state.clicks,0);
  assert.equal(f.record.preparationInteractions.at(-1).phase,'failed');
 }
});

test('lost focus or a keyboard control that never highlights the target fails closed within the option-count bound',async()=>{
 for(const config of [{loseFocus:true},{noHover:true}]){
  const f=fixture(config);await assert.rejects(()=>pickOption(f.page,'Target',f.control,f.record,f.persist),/焦点|键盘定位/);
  assert.equal(f.state.keys.includes('Enter'),false);assert.ok(f.state.keys.length<=3);assert.equal(f.state.clicks,0);
 }
});

test('a changed highlight during checkpoint persistence is rechecked before any Enter',async()=>{
 const f=fixture();const persist=async()=>{await f.persist();if(f.record.preparationInteractions.at(-1).phase==='target_hovered')f.state.hover=0;};
 await assert.rejects(()=>pickOption(f.page,'Target',f.control,f.record,persist),/确认前高亮变化/);
 assert.equal(f.state.keys.includes('Enter'),false);assert.equal(f.state.clicks,0);
});
