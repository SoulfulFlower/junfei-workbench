const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const source=html.slice(html.indexOf('function titleFieldLimits()'),html.indexOf('function renderListing('));
test('editor counts spaces and rejects 59/76 while accepting 60/75 in every market',()=>{
 const messages=[],context=vm.createContext({market:'US',toast:value=>messages.push(value),TextEncoder});
 vm.runInContext(source,context);
 for(const market of ['US','UK','JP','DE']){
  context.market=market;
  for(const n of [59,60,75,76]){
   const title='a b '+('x'.repeat(n-4));
   assert.equal(context.checkTitleFields({title,highlights:'Button closure'}),n>=60&&n<=75);
   assert.match(context.copyFieldCount('title',title),/要求 60–75 字符（含空格）/);
  }
 }
 assert.match(messages[0],/当前 59 字符/);
});
