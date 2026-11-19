import test from 'node:test';
import assert from 'node:assert/strict';
import {sellerToken,assertSellerIdentity,captureSellerChain,assertGlobalSearchScope,searchTitleGlobally} from './native_amazon_discovery_chain.mjs';
test('seller links and native storefronts keep the same actual merchant',()=>{
  assert.equal(sellerToken('https://www.amazon.com/sp?seller=A14N1NDFBLTPZ1'),'A14N1NDFBLTPZ1');
  assertSellerIdentity('https://www.amazon.com/s?me=A14N1NDFBLTPZ1','A14N1NDFBLTPZ1');
  assert.throws(()=>assertSellerIdentity('https://www.amazon.com/s?me=OTHERSELLER','A14N1NDFBLTPZ1'),/token mismatch/);
  assert.throws(()=>sellerToken('https://www.amazon.com.evil.example/s?me=A14N1NDFBLTPZ1'),/Official US/);
  assert.throws(()=>sellerToken('http://www.amazon.com/s?me=A14N1NDFBLTPZ1'),/Official US/);
});
test('foreign seller link in source evidence cannot trigger navigation',async()=>{
  let navigations=0;const page={goto:async()=>{navigations++;}};
  const source={ui:{asin:'B0HPN6XY7G',url:'https://www.amazon.com/dp/B0HPN6XY7G',delivery:'Denison 75020',sellerLinks:[{text:'HNBAAA',href:'https://unrelated.example/sp?seller=A14N1NDFBLTPZ1'}]}};
  await assert.rejects(captureSellerChain({},page,source,{outputDirectory:'C:/research/',prefix:'isolated'}),/Official US/);assert.equal(navigations,0);
});
test('title research rejects a merchant-filtered result page',()=>{
  assertGlobalSearchScope('https://www.amazon.com/s?k=western+denim+shirt');
  for(const q of ['m=A14N1NDFBLTPZ1','me=A14N1NDFBLTPZ1','s=merchant-items'])assert.throws(()=>assertGlobalSearchScope('https://www.amazon.com/s?k=shirt&'+q),/merchant scope remained/);
});
test('title and expanded keyword provenance are mandatory before any page action',async()=>{
  const opts={outputDirectory:'C:/research/',prefix:'isolated'};
  await assert.rejects(searchTitleGlobally({}, {query:'Unseen term',sourceTitle:'Actual title',sourceAsin:'B0HR62VQVN'},opts),/Observed title opening/);
  await assert.rejects(searchTitleGlobally({}, {query:'Light cardigan',sourceTitle:'Actual title',sourceAsin:'B0HR62VQVN',keywordType:'expanded'},opts),/explicit expanded-keyword basis/);
});
