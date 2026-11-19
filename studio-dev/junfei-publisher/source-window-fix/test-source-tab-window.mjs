import test from 'node:test';
import assert from 'node:assert/strict';
import {open1688SourceTab} from './source-tab-window.mjs';

const url = 'https://s.1688.com/youyuan/index.htm?tab=imageSearch&imageId=123';
test('concurrent searches remain associated with their individual source windows', async () => {
  const calls = [];
  const tabs = new Map([[12, {id:12,windowId:50,index:2}], [24, {id:24,windowId:80,index:4}]]);
  const api = {tabs:{get:async id=>tabs.get(id),create:async p=>{calls.push(p);return p;}}};
  await Promise.all([open1688SourceTab(url,{id:12,windowId:50},api),open1688SourceTab(url,{id:24,windowId:80},api)]);
  assert.deepEqual(calls.map(p=>[p.windowId,p.openerTabId,p.index,p.active]),[[50,12,3,false],[80,24,5,false]]);
});
test('missing source identity cannot fall back to the user current window', async () => {
  let called = false;
  const api = {tabs:{get:async()=>{called=true;},create:async()=>{called=true;}}};
  for(const source of [undefined,{}, {id:1}, {id:-1,windowId:5}])
    await assert.rejects(open1688SourceTab(url,source,api),/source tab and window/);
  assert.equal(called,false);
});
test('a source moved into another window does not redirect the pending operation', async () => {
  let created=false;
  const api={tabs:{get:async()=>({id:1,windowId:99,index:0}),create:async()=>{created=true;}}};
  await assert.rejects(open1688SourceTab(url,{id:1,windowId:5},api),/closed or moved/);
  assert.equal(created,false);
});
test('a closed source and a failed create both stop without a second attempt', async () => {
  let calls=0;
  const api={tabs:{get:async()=>undefined,create:async()=>{calls++;throw Error('closed');}}};
  await assert.rejects(open1688SourceTab(url,{id:1,windowId:5},api),/closed or moved/);
  api.tabs.get=async()=>({id:1,windowId:5,index:0});
  await assert.rejects(open1688SourceTab(url,{id:1,windowId:5},api),/closed/);
  assert.equal(calls,1);
});
test('the helper cannot open an unrelated destination', async () => {
  const api={tabs:{get:async()=>assert.fail('must not query tabs'),create:async()=>assert.fail('must not create')}};
  for(const bad of ['https://example.com/','https://s.1688.com.example.com/','http://s.1688.com/'])
    await assert.rejects(open1688SourceTab(bad,{id:1,windowId:5},api),/destination/);
});
