import {useEffect,useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import type {TextareaHTMLAttributes} from 'react';
import {createPortal} from 'react-dom';
import {groupedKeywordMetrics,keywordNumber,keywordSegments} from './keyword-marks';
import type {KeywordMatch,MarkedKeyword} from './keyword-marks';

type Props=Omit<TextareaHTMLAttributes<HTMLTextAreaElement>,'value'> & {
  value:string; keywords:MarkedKeyword[]; market:string; 'data-copy-field':string;
};
type Hover={matches:KeywordMatch[];x:number;y:number};

export default function KeywordTextarea({value,keywords,market,...props}:Props){
  const input=useRef<HTMLTextAreaElement>(null),mirror=useRef<HTMLDivElement>(null);
  const tooltip=useRef<HTMLDivElement>(null),hideTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const [hover,setHover]=useState<Hover|null>(null);
  const id=useId();
  const segments=useMemo(()=>keywordSegments(value,keywords),[value,keywords]);
  const close=()=>{clearTimeout(hideTimer.current);setHover(null)};
  const deferClose=()=>{clearTimeout(hideTimer.current);hideTimer.current=setTimeout(close,180)};
  useEffect(()=>()=>clearTimeout(hideTimer.current),[]);
  useEffect(()=>{close()},[value,keywords]);
  useEffect(()=>{
    const onScroll=(event:Event)=>{if(!(event.target instanceof Node&&tooltip.current?.contains(event.target)))close()};
    window.addEventListener('scroll',onScroll,true);
    window.addEventListener('resize',close);
    return()=>{window.removeEventListener('scroll',onScroll,true);window.removeEventListener('resize',close)};
  },[]);
  useLayoutEffect(()=>{
    const area=input.current,layer=mirror.current;if(!area||!layer)return;
    const sync=()=>{
      const style=getComputedStyle(area);
      for(const name of ['fontFamily','fontSize','fontWeight','fontStyle','lineHeight','letterSpacing','paddingTop',
        'paddingRight','paddingBottom','paddingLeft','borderTopWidth','borderRightWidth','borderBottomWidth',
        'borderLeftWidth','boxSizing','textAlign','textIndent','tabSize','wordBreak','overflowWrap'] as const)layer.style[name]=style[name];
      layer.style.width=(area.clientWidth+parseFloat(style.borderLeftWidth)+parseFloat(style.borderRightWidth))+'px';
      layer.style.height=area.offsetHeight+'px';layer.scrollTop=area.scrollTop;layer.scrollLeft=area.scrollLeft;
    };
    const observer=new ResizeObserver(sync);observer.observe(area);sync();
    return()=>observer.disconnect();
  },[value,segments]);
  useLayoutEffect(()=>{
    const element=tooltip.current;if(!element||!hover)return;
    const box=element.getBoundingClientRect();
    element.style.left=Math.max(8,Math.min(hover.x+12,window.innerWidth-box.width-8))+'px';
    element.style.top=Math.max(8,Math.min(hover.y+18,window.innerHeight-box.height-8))+'px';
  },[hover]);
  const show=(matches:KeywordMatch[],x:number,y:number)=>{
    clearTimeout(hideTimer.current);
    setHover(previous=>JSON.stringify(previous?.matches)===JSON.stringify(matches)?previous:{matches,x,y});
  };
  const rendered:React.ReactNode[]=[];
  let cursor=0;
  for(const segment of segments){
    rendered.push(value.slice(cursor,segment.start));
    const kind=segment.matches.some(match=>match.kind==='exact')?'exact':'variant';
    rendered.push(<mark key={segment.start} data-keyword-segment={segment.keywords.join(',')} data-keyword-start={segment.start} data-keyword-kind={kind}>
      {value.slice(segment.start,segment.end)}</mark>);
    cursor=segment.end;
  }
  rendered.push(value.slice(cursor)+'\n');
  return <div className="pe-keyword-editor">
    <div className="pe-keyword-mirror" aria-hidden="true" ref={mirror}>{rendered}</div>
    <textarea {...props} value={value} ref={input} className={'pe-keyword-input '+(props.className||'')}
      aria-describedby={hover?id:undefined}
      onMouseMove={event=>{
        const area=input.current;if(!area)return;
        const box=area.getBoundingClientRect();
        if(event.clientX>box.left+area.clientWidth||event.clientY>box.top+area.clientHeight){close();return;}
        const marks=mirror.current?.querySelectorAll<HTMLElement>('[data-keyword-segment]')||[];
        for(const mark of Array.from(marks)){
          if(Array.from(mark.getClientRects()).some(rect=>event.clientX>=rect.left&&event.clientX<=rect.right&&event.clientY>=rect.top&&event.clientY<=rect.bottom)){
            const segment=segments.find(item=>item.start===Number(mark.dataset.keywordStart));
            if(segment)show(segment.matches,event.clientX,event.clientY);return;
          }
        }
        close();
      }}
      onMouseLeave={deferClose}
      onSelect={event=>{
        const area=event.currentTarget;
        const segment=segments.find(item=>area.selectionStart>=item.start&&area.selectionStart<item.end);
        if(!segment){close();return;}
        const mark=mirror.current?.querySelector<HTMLElement>(`mark[data-keyword-start="${segment.start}"]`);
        const rect=mark?.getBoundingClientRect();
        if(rect)show(segment.matches,rect.left,rect.bottom);
      }}
      onBlur={deferClose}
      onKeyDown={event=>{if(event.key==='Escape')close();props.onKeyDown?.(event)}}
      onScroll={event=>{
        if(mirror.current){mirror.current.scrollTop=event.currentTarget.scrollTop;mirror.current.scrollLeft=event.currentTarget.scrollLeft;}
        close();props.onScroll?.(event);
      }}/>
    {hover&&createPortal(<div id={id} role="tooltip" className="pe-keyword-tooltip" ref={tooltip}
      style={{left:hover.x+12,top:hover.y+18}} onMouseEnter={()=>clearTimeout(hideTimer.current)} onMouseLeave={deferClose}>
      {hover.matches.map(match=>{
        const word=keywords[match.keyword];
        return <section key={word.phrase}>
          <div className={'pe-keyword-match-kind '+match.kind}>{match.kind==='exact'?'完整词组匹配':'自然变体匹配'}</div>
          {match.kind==='variant'&&<div className="pe-keyword-variant-copy">文案表达 · {value.slice(match.start,match.end)}</div>}
          {match.kind==='variant'&&<div className="pe-keyword-meta">对应原关键词</div>}
          <strong>{word.phrase}</strong>{word.translation&&<div>{word.translation}</div>}
          <div className="pe-keyword-meta">{match.kind==='variant'?'原关键词数据 · ':''}卖家精灵 · {market} 站 · {word.snapshot?'生成时保存的数据':'已保存的关键词数据'}</div>
          {!word.metrics.length&&<p>未返回指标数据</p>}
          {groupedKeywordMetrics(word.metrics).map(({metric,sources},number)=><div className="pe-keyword-metric" key={number}>
            <div className="pe-keyword-sources">{sources.join('；')}</div>
            <dl>{[['月搜索量',keywordNumber(metric.searches)],['月购买量',keywordNumber(metric.purchases)],
              ['月购买率',keywordNumber(metric.purchaseRate,true)],['竞品流量占比',metric.asin?keywordNumber(metric.trafficPercentage,true):'—'],
              ['相关商品数',keywordNumber(metric.products)],['自然排名',metric.asin?keywordNumber(metric.naturalRank):'—']].map(([label,amount])=>
              <div key={label}><dt>{label}</dt><dd>{amount}</dd></div>)}</dl>
            <div className="pe-keyword-meta">数据月份／更新时间 · {String(metric.month||metric.updatedTime||'未返回')}</div>
          </div>)}
        </section>;
      })}
    </div>,document.body)}
  </div>;
}
