import test from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {writeJsonAtomic} from './atomic_write_json.mjs';

test('sharing violations retry the same flushed local file without rewriting or replaying work',async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'atomic-checkpoint-'));
 const target=path.join(directory,'receipt.json');await fs.writeFile(target,'{"old":true}');let opens=0,renames=0;const sleeps=[],sources=[];
 const adapter={open:async(...args)=>{opens++;return fs.open(...args);},rename:async(from,to)=>{
  sources.push(from);renames++;
  assert.deepEqual(JSON.parse(await fs.readFile(from,'utf8')),{scope:'original-task',intent:'unknown'});
  if(renames<=2){assert.deepEqual(JSON.parse(await fs.readFile(to,'utf8')),{old:true});throw Object.assign(Error('sharing violation'),{code:renames===1?'EPERM':'EBUSY'});}
  return fs.rename(from,to);
 }};
 try{await writeJsonAtomic(target,{scope:'original-task',intent:'unknown'},{fs:adapter,sleep:async ms=>sleeps.push(ms)});assert.equal(opens,1);assert.equal(renames,3);assert.equal(new Set(sources).size,1);assert.deepEqual(sleeps,[50,50]);assert.deepEqual(JSON.parse(await fs.readFile(target,'utf8')),{scope:'original-task',intent:'unknown'});assert.deepEqual(await fs.readdir(directory),['receipt.json']);}
 finally{await fs.rm(directory,{recursive:true,force:true});}
});

test('permanent sharing failure preserves the old receipt and one complete recovery temporary file',async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'atomic-unknown-'));const target=path.join(directory,'receipt.json');await fs.writeFile(target,'{"prior":"retained"}');let renames=0;
 const adapter={open:(...args)=>fs.open(...args),rename:async()=>{renames++;throw Object.assign(Error('still busy'),{code:'EACCES'});}};
 try{let failure;try{await writeJsonAtomic(target,{intent:'armed'},{fs:adapter,attempts:3,sleep:async()=>{}});}catch(error){failure=error;}
 assert.equal(renames,3);assert.equal(failure.code,'EACCES');assert.deepEqual(JSON.parse(await fs.readFile(target,'utf8')),{prior:'retained'});assert.deepEqual(JSON.parse(await fs.readFile(failure.checkpointTemporaryPath,'utf8')),{intent:'armed'});assert.equal((await fs.readdir(directory)).length,2);}
 finally{await fs.rm(directory,{recursive:true,force:true});}
});

test('non-sharing errors fail immediately without repeated rename attempts',async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'atomic-invalid-'));let renames=0;
 try{await assert.rejects(writeJsonAtomic(path.join(directory,'receipt.json'),{intent:1},{fs:{open:(...args)=>fs.open(...args),rename:async()=>{renames++;throw Object.assign(Error('bad target'),{code:'EINVAL'});}},sleep:async()=>assert.fail('must not sleep')}),{code:'EINVAL'});assert.equal(renames,1);}
 finally{await fs.rm(directory,{recursive:true,force:true});}
});
