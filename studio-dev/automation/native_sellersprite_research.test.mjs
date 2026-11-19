import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {collectNativeReverse} from './native_sellersprite_research.mjs';

const expected={candidateAsin:'B0HPSJPMK4',queryAsin:'B0HPN6XY7G'};
const ready={url:'https://www.amazon.com/dp/B0HPSJPMK4',asin:expected.candidateAsin,delivery:'Denison 75020',query:expected.queryAsin,mode:'reverse',loading:false,noData:false,declaredTotal:'31',visibleRows:[['','1','quarter zip women']],headers:[]};
async function fixture(t, states, download) {
  const directory=await mkdtemp(join(tmpdir(),'native-sellersprite-test-'));const bound=resolve(tmpdir())+sep;
  t.after(async()=>{const target=resolve(directory);assert.ok(target.startsWith(bound));assert.ok(target.split(sep).at(-1).startsWith('native-sellersprite-test-'));await rm(target,{recursive:true,force:true});});
  const calls={fill:0,press:0,click:0,download:0};
  const page={evaluate:async()=>states.shift(),waitForFunction:async()=>true,fill:async()=>{calls.fill++;},press:async()=>{calls.press++;},screenshot:async()=>{},mouse:{click:async()=>{calls.click++;return {}; }},waitForEvent:async()=>{calls.download++;return await download();}};
  return {page,calls,options:{base:directory.replaceAll('\\','/')+'/',prefix:'isolated',start:false}};
}
test('wrong candidate or delivery or mode stops before query/export actions',async t=>{
  for(const patch of [{asin:'B0HR8N5S8Z'},{delivery:'London SW1A'},{mode:'mining'}]){
    const f=await fixture(t,[{...ready,...patch}],()=>{throw Error('must not export');});
    await assert.rejects(collectNativeReverse(f.page,expected,f.options),/scope mismatch|mode mismatch/);
    assert.deepEqual(f.calls,{fill:0,press:0,click:0,download:0});
  }
});
test('result query identity is rechecked before an export',async t=>{
  const f=await fixture(t,[ready,{...ready,query:'B0HR8N5S8Z'}],()=>{throw Error('must not export');});
  await assert.rejects(collectNativeReverse(f.page,expected,f.options),/query mismatch/);assert.equal(f.calls.click,0);
});
test('virtual rows plus failed native download remain export_pending',async t=>{
  const f=await fixture(t,[ready,ready,undefined,{x:100,y:100,query:expected.queryAsin}],()=>{throw Error('download timeout');});
  const r=await collectNativeReverse(f.page,expected,f.options);
  assert.equal(r.status,'export_pending');assert.equal(r.dataStatus,'collected');assert.equal(r.ui.visibleRows.length,1);assert.equal(r.ui.declaredTotal,'31');assert.equal(r.ui.rows,undefined);assert.equal(r.export,undefined);assert.match(r.exportError,/timeout/);assert.equal(f.calls.click,1);assert.equal(f.calls.download,1);
});
test('another ASIN download is rejected without saving or claiming completion',async t=>{
  let saved=0;const f=await fixture(t,[ready,ready,undefined,{x:100,y:100,query:expected.queryAsin}],async()=>({suggestedFilename:()=> 'ReverseASIN-US-B0HR8N5S8Z(4).xlsx',saveAs:async()=>{saved++;}}));
  const r=await collectNativeReverse(f.page,expected,f.options);assert.equal(r.status,'export_pending');assert.match(r.exportError,/filename \/ query mismatch/);assert.equal(saved,0);
});
test('explicit empty query result neither exports nor invents keyword rows',async t=>{
  const empty={...ready,visibleRows:[],noData:true,declaredTotal:null};const f=await fixture(t,[empty,empty],()=>{throw Error('must not export');});
  const r=await collectNativeReverse(f.page,expected,f.options);assert.equal(r.status,'empty');assert.equal(r.ui.visibleRows.length,0);assert.equal(f.calls.click,0);assert.equal(f.calls.download,0);
});
