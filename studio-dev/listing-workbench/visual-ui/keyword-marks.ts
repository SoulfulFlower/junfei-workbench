export type KeywordMetric = Record<string, unknown> & {seedSources?:Record<string,string[]>};
export type MarkedKeyword = {
  phrase:string; translation?:string; metrics:KeywordMetric[]; snapshot:boolean;
};
export type KeywordMatch = {start:number; end:number; keyword:number; kind:'exact'|'variant'};
export type KeywordSegment = {start:number; end:number; keywords:number[]; matches:KeywordMatch[]};

const escapePattern=(value:string)=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const wordSeparator='[\\s\\p{Pd}]+';

function naturalKeywordPattern(phrase:string):string {
  // These are grammatical variants. Product attributes remain required in the same order.
  if(!/^[a-z\s'’\p{Pd}]+$/iu.test(phrase))return '';
  const tokens=phrase.toLowerCase().split(/[\s\p{Pd}]+/u).filter(Boolean);
  let audience='';
  if(/^(?:women|men)['’]s$/.test(tokens[0]))audience=tokens.shift()!.split(/['’]/)[0];
  else if(['women','men'].includes(tokens[tokens.length-1])){
    audience=tokens.pop()!;
    if(tokens[tokens.length-1]==='for')tokens.pop();
  }
  if(!tokens.length)return '';
  const garmentForms:Record<string,string>={
    cardigan:'cardigans?',cardigans:'cardigans?',sweater:'sweaters?',sweaters:'sweaters?',
    shirt:'shirts?',shirts:'shirts?',jacket:'jackets?',jackets:'jackets?',
    coat:'coats?',coats:'coats?',dress:'dress(?:es)?',dresses:'dress(?:es)?',top:'tops?',tops:'tops?',
  };
  const body=tokens.map((token,index)=>{
    if(token==='button'&&tokens[index+1]!=='front')return 'button(?:'+wordSeparator+'front)?';
    return garmentForms[token]||escapePattern(token);
  }).join(wordSeparator);
  return audience?'(?:'+body+wordSeparator+'(?:for'+wordSeparator+')?'+audience+'|'+
    audience+"['’]s"+wordSeparator+body+')':body;
}

export function listingKeywords(report:any, input:any):MarkedKeyword[] {
  const words=new Map<string,MarkedKeyword>();
  const add=(rows:any, snapshot:boolean)=>{
    if(!Array.isArray(rows))return;
    for(const row of rows){
      if(!row||typeof row.phrase!=='string'||!row.phrase.trim()||(!snapshot&&row.selected===false))continue;
      const phrase=row.phrase.trim(), key=phrase.toLowerCase();
      if(!words.has(key))words.set(key,{phrase,translation:typeof row.translation==='string'?row.translation:undefined,
        metrics:Array.isArray(row.metrics)?row.metrics.filter((metric:any)=>metric&&typeof metric==='object'):[],snapshot});
    }
  };
  if(report?.source==='sellersprite')add(report.keywords,false);
  add(input?.keywords,true);
  return [...words.values()];
}

export function keywordSegments(value:string, keywords:MarkedKeyword[]):KeywordSegment[] {
  const hits:KeywordMatch[]=[];
  keywords.forEach((word,keyword)=>{
    const phrase=word.phrase.split(/[\s\p{Pd}]+/u).filter(Boolean)
      .map(escapePattern).join(wordSeparator);
    if(!phrase)return;
    const collect=(pattern:string,kind:KeywordMatch['kind'])=>{
      if(!pattern)return;
      const expression=new RegExp('(?<![\\p{L}\\p{N}])'+pattern+'(?![\\p{L}\\p{N}])','giu');
      for(const match of value.matchAll(expression)){
        const start=match.index!,end=start+match[0].length;
        if(kind==='variant'&&hits.some(hit=>hit.keyword===keyword&&hit.kind==='exact'&&hit.start<=start&&hit.end>=end))continue;
        hits.push({start,end,keyword,kind});
      }
    };
    collect(phrase,'exact');
    collect(naturalKeywordPattern(word.phrase),'variant');
  });
  const points=[...new Set(hits.flatMap(hit=>[hit.start,hit.end]))].sort((a,b)=>a-b);
  const segments:KeywordSegment[]=[];
  for(let index=0;index<points.length-1;index++){
    const start=points[index],end=points[index+1];
    const matching=new Map<number,KeywordMatch>();
    for(const hit of hits){
      if(hit.start<=start&&hit.end>=end&&(!matching.has(hit.keyword)||hit.kind==='exact'))matching.set(hit.keyword,hit);
    }
    const matches=[...matching.values()];
    if(matches.length)segments.push({start,end,keywords:matches.map(hit=>hit.keyword),matches});
  }
  return segments;
}

export function keywordNumber(value:unknown, percent=false):string {
  if(typeof value!=='number'||!Number.isFinite(value))return '—';
  return percent?(value*100).toLocaleString('en-US',{maximumFractionDigits:2})+'%':
    value.toLocaleString('en-US',{maximumFractionDigits:2});
}

export function keywordMetricSource(metric:KeywordMetric):string {
  if(metric.asin)return '反查 '+String(metric.asin);
  const label=(source:string)=>source==='reverse'?'（反查种子）':'（商品资料种子）';
  if(metric.seedSources)return Object.entries(metric.seedSources).map(([source,seeds])=>
    '拓展 '+seeds.join('、')+label(source)).join('；');
  return metric.seed?'拓展 '+String(metric.seed)+label(String(metric.seedSource||'')):'来源未记录';
}

export function groupedKeywordMetrics(metrics:KeywordMetric[]) {
  const groups=new Map<string,{metric:KeywordMetric;sources:string[]}>();
  const fields=['searches','purchases','purchaseRate','trafficPercentage','products','naturalRank','month','updatedTime'];
  for(const metric of metrics){
    // ASIN-specific ranks and traffic shares remain attached to their original competitor.
    const key=JSON.stringify([metric.asin||'',...fields.map(field=>metric[field]??null)]);
    const source=keywordMetricSource(metric),group=groups.get(key);
    if(group){if(!group.sources.includes(source))group.sources.push(source);}
    else groups.set(key,{metric,sources:[source]});
  }
  return [...groups.values()];
}
