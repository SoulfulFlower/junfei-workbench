import test from 'node:test';
import assert from 'node:assert/strict';
import {pasteImageToSearch} from './brain-image-paste.mjs';

function fixture({url='https://s.1688.com/', info={tag:'input',type:'text',readOnly:false,disabled:false,visible:true,hint:'search-input'}}={}) {
  const calls=[];
  const locator={evaluate:async()=>info,click:async()=>calls.push('click'),press:async key=>calls.push(key)};
  const page={url:()=>url,evaluate:async(_fn,value)=>{calls.push(['clipboard',value]);return;}};
  return {page,locator,calls};
}
const imageBase64=Buffer.from('a'.repeat(100)).toString('base64');

test('clicks the search field and pastes image from clipboard without opening upload UI',async()=>{
  const f=fixture();
  const result=await pasteImageToSearch({...f,imageBase64});
  assert.deepEqual(f.calls.map(x=>Array.isArray(x)?'clipboard':x),['click','clipboard','Control+V']);
  assert.equal(result.method,'clipboard-paste');
});

test('rejects file inputs and buttons without interacting with the page',async()=>{
  for(const info of [{tag:'input',type:'file',readOnly:false,disabled:false,visible:true,hint:'search'},{tag:'button',type:'button',readOnly:false,disabled:false,visible:true,hint:'以图搜款'}]){
    const f=fixture({info});
    await assert.rejects(pasteImageToSearch({...f,imageBase64}));
    assert.deepEqual(f.calls,[]);
  }
});

test('rejects non-search elements and unapproved 1688 paths',async()=>{
  const badTarget=fixture({info:{tag:'input',type:'text',readOnly:false,disabled:false,visible:true,hint:'username'}});
  await assert.rejects(pasteImageToSearch({...badTarget,imageBase64}),/搜索框标识/);
  const badUrl=fixture({url:'https://detail.1688.com/offer/123456789.html'});
  await assert.rejects(pasteImageToSearch({...badUrl,imageBase64}),/只允许/);
});

test('does not fall back to an upload button when clipboard write fails',async()=>{
  const f=fixture();
  f.page.evaluate=async()=>{throw new Error('clipboard denied')};
  await assert.rejects(pasteImageToSearch({...f,imageBase64}),/clipboard denied/);
  assert.deepEqual(f.calls,['click']);
});
