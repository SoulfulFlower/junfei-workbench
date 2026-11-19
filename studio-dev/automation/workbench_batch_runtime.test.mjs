import test from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {run} from './workbench_batch_runtime.mjs';

test('unknown queue request is never replayed and cached capture is reused',async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'workbench-batch-'));let requests=0,known=false;
 const page={label:'p1',url:async()=>'http://127.0.0.1:18775/products',fetch:async(url,options)=>{
  assert.equal(options.headers['X-Workspace-Account'],'2');
  if(url==='/api/auth/status')return{ok:true,status:200,body:JSON.stringify({user:{id:2,username:'test'}})};
  if(url==='/api/supplier-capture/status')return{ok:true,status:200,body:'{"paused":false}'};
  if(url==='/api/supplier-capture/result')return{ok:known,status:known?200:400,body:known?'{"id":"original","status":"queued"}':'{"error":"unknown"}'};
  if(url==='/api/supplier-capture/request'){requests++;throw Error('response lost');}
  throw Error('unexpected endpoint '+url);
 }};
 globalThis.listTaskSpaces=async()=>[{id:18,name:'batch',ownership:'agent'}];
 globalThis.taskSpace=async()=>({pages:async()=>[page],page:()=>page});
 const plan={accountId:2,workbench:{id:18,name:'batch',page:'p1'},action:'supplier-add',suppliers:['https://detail.1688.com/offer/123.html'],jobs:[],outputDirectory:directory};
 try{
  const first=await run({...plan,runId:'one',resultFile:path.join(directory,'one.json')});assert.match(first.error,/response lost/);assert.equal(requests,1);
  const second=await run({...plan,runId:'two',resultFile:path.join(directory,'two.json')});assert.equal(second.actions[0].reconciliationOnly,true);assert.equal(requests,1);
  known=true;const third=await run({...plan,runId:'three',resultFile:path.join(directory,'three.json')});assert.equal(third.actions[0].reused,true);assert.equal(requests,1);
 }finally{delete globalThis.listTaskSpaces;delete globalThis.taskSpace;await fs.rm(directory,{recursive:true,force:true});}
});

test('wrong real account fails before supplier or original-task requests',async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'workbench-account-'));let calls=0;
 const page={label:'p1',url:async()=>'http://127.0.0.1:18775/products',fetch:async(url)=>{calls++;assert.equal(url,'/api/auth/status');return{ok:true,status:200,body:'{"user":{"id":3}}'};}};
 globalThis.listTaskSpaces=async()=>[{id:18,name:'batch',ownership:'agent'}];globalThis.taskSpace=async()=>({pages:async()=>[page],page:()=>page});
 try{const report=await run({accountId:2,workbench:{id:18,name:'batch',page:'p1'},action:'status',suppliers:[],jobs:['a'.repeat(32)],outputDirectory:directory,resultFile:path.join(directory,'result.json')});assert.match(report.error,/登录账号不符/);assert.equal(calls,1);}
 finally{delete globalThis.listTaskSpaces;delete globalThis.taskSpace;await fs.rm(directory,{recursive:true,force:true});}
});
