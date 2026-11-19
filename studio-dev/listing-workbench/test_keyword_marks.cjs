const assert=require('node:assert/strict');
const fs=require('node:fs');
const test=require('node:test');
const ts=require('./visual-ui/node_modules/typescript');
const source=fs.readFileSync(__dirname+'/visual-ui/keyword-marks.ts','utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const helpers={};
new Function('exports',compiled)(helpers);
const {listingKeywords,keywordSegments,groupedKeywordMetrics,keywordNumber}=helpers;
const word=phrase=>({phrase,metrics:[],snapshot:false});

test('matching handles hyphens, case, boundaries and overlapping complete phrases',()=>{
  const text='Cable-knit cardigan and cardigans; cardigan with pockets.';
  const words=['cable knit cardigan','cardigan','cardigan with pockets'].map(word);
  const segments=keywordSegments(text,words);
  const found=index=>segments.filter(segment=>segment.matches.some(match=>match.keyword===index&&match.kind==='exact')).map(segment=>text.slice(segment.start,segment.end)).join('');
  assert.equal(found(0),'Cable-knit cardigan');
  assert.equal(found(2),'cardigan with pockets');
  assert.equal(found(1),'cardigancardigan');
  assert.equal(keywordSegments('cable. knit cardigan',[word('cable knit cardigan')]).length,0);
  assert.equal(keywordSegments('a [pocket] + [pocket]',[word('[pocket]')]).length,2);
});

test('natural variants retain original keyword identity and require the attribute and audience',()=>{
  const words=[word('button cardigans for women')];
  const text='This button-front cardigan for women has large buttons.';
  const segments=keywordSegments(text,words);
  assert.equal(segments.length,1);
  assert.equal(text.slice(segments[0].start,segments[0].end),'button-front cardigan for women');
  assert.equal(segments[0].matches[0].kind,'variant');
  assert.equal(segments[0].matches[0].keyword,0);
  assert.equal(keywordSegments('women’s button cardigan',words)[0].matches[0].kind,'variant');
  for(const unrelated of ['button cardigan for men','cardigan for women','button-front cardigan','button cardigan. For women']){
    assert.equal(keywordSegments(unrelated,words).length,0,unrelated);
  }
});

test('exact hits stay exact when a broader natural variant also overlaps',()=>{
  const text='cable-knit cardigan for women';
  const words=[word('cable knit cardigan'),word('cable knit cardigan women')];
  const segments=keywordSegments(text,words);
  assert.equal(segments[0].matches.find(match=>match.keyword===0).kind,'exact');
  assert.equal(segments[0].matches.find(match=>match.keyword===1).kind,'variant');
  assert.equal(keywordSegments('button cardigans for women',[word('button cardigans for women')])[0].matches[0].kind,'exact');
  assert.equal(keywordSegments('cotton cardigan sweater for women',[word('cotton cardigan sweaters for women')])[0].matches[0].kind,'variant');
});

test('saved research takes precedence over generation snapshots and retains snapshot-only terms',()=>{
  const report={source:'sellersprite',keywords:[{phrase:'Cardigan',selected:true,metrics:[{searches:500}]},
    {phrase:'unselected',selected:false,metrics:[{searches:100}]}]};
  const input={keywords:[{phrase:'cardigan',metrics:[{searches:200}]},{phrase:'old keyword',metrics:[]}]};
  const words=listingKeywords(report,input);
  assert.equal(words.length,2);
  assert.equal(words[0].metrics[0].searches,500);
  assert.equal(words[1].snapshot,true);
  assert.equal(listingKeywords({source:'ai',keywords:report.keywords},null).length,0);
});

test('same mining metrics retain sources while competitor-specific metrics stay separate',()=>{
  const rows=[{seed:'first',searches:500,purchaseRate:0.1},{seed:'second',searches:500,purchaseRate:0.1},
    {asin:'B000000001',searches:500,trafficPercentage:0.2},{asin:'B000000002',searches:500,trafficPercentage:0.2}];
  const grouped=groupedKeywordMetrics(rows);
  assert.equal(grouped.length,3);
  assert.equal(grouped[0].sources.length,2);
  assert.equal(keywordNumber(0), '0');
  assert.equal(keywordNumber(null),'—');
  assert.equal(keywordNumber(0.0745,true),'7.45%');
});
