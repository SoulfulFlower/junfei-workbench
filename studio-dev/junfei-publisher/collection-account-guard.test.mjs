import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';

test('a collection request keeps its captured account header across an account switch',async()=>{
 const source=(await fs.readFile(new URL('../listing-workbench/auth.js',import.meta.url),'utf8')).split('const authStyle=')[0];
 const requests=[],window={fetch:async(_u,options)=>{requests.push(new Headers(options.headers));return{status:200};}};
 const context=vm.createContext({window,Headers});vm.runInContext(source,context);vm.runInContext('signedUser={id:3}',context);
 await window.fetch('/api/erp-collection/start',{headers:{'X-Workspace-Account':'2'}});
 await window.fetch('/api/erp-collection/view',{});
 assert.equal(requests[0].get('X-Workspace-Account'),'2');assert.equal(requests[1].get('X-Workspace-Account'),'3');
});
