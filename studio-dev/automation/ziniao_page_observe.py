"""Read the current native store page, excluding hidden form/session values."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from ziniao_plugin import native_cli, run


def observe(store_id, target_id, expected_origin, seller, country, focus_text=None):
    args = ['page', 'content', '--store-id', store_id, '--content-format', 'structured']
    if target_id:
        args.extend(['--target-id', target_id])
    value = run(native_cli(), *args)
    if value.get('ok') is not True:
        raise ValueError('原店铺页面读取失败；未导航或重试')
    while isinstance(value, dict) and 'content' not in value and isinstance(value.get('data'), dict):
        value = value['data']
    content = value.get('content')
    if not isinstance(content, dict) or not isinstance(content.get('text'), str):
        raise ValueError('原生页面结构已变化；未读取隐藏字段作为替代')
    url = value.get('url', '')
    parsed = urlsplit(url)
    if parsed.scheme+'://'+parsed.netloc != expected_origin.rstrip('/'):
        raise ValueError('原店铺页面域名不符')
    text = content['text']
    script = r'''(() => {
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&!e.closest('[aria-hidden="true"]');};
      const headers=[...document.querySelectorAll('.dropdown-account-switcher-header')].filter(visible);
      return JSON.stringify({origin:location.origin,labels:headers.map(e=>(e.innerText||e.textContent||'').trim().replace(/\s+/g,' '))});
    })()'''
    header_args=['page', 'exec', '--store-id', store_id, '--script', script]
    if target_id:
        header_args.extend(['--target-id', target_id])
    header=run(native_cli(), *header_args)
    if header.get('ok') is not True:
        raise ValueError('原店铺可见市场控件读取失败')
    while isinstance(header.get('data'), dict):
        header=header['data']
    if header.get('exceptionDetails'):
        raise ValueError('原店铺可见市场控件读取失败')
    selected=json.loads(header.get('result', ''))
    if (selected.get('origin') != expected_origin.rstrip('/')
            or selected.get('labels') != [seller+' '+country]):
        raise ValueError('原店铺可见市场身份不符')
    result = {key: value[key] for key in ('url', 'title', 'targetId', 'format') if key in value}
    result.update(at=datetime.now(timezone.utc).isoformat(), storeId=store_id,
                  expectedSeller=seller, expectedCountry=country, visibleIdentityVerified=True,
                  selectedHeader=selected,
                  content={key:content.get(key) for key in ('text', 'headings', 'buttons', 'links')},
                  hiddenFormsRecorded=False, navigated=False, businessWrites=False)
    if focus_text:
        focus_script=r'''(() => {
          const target=__FOCUS__,norm=s=>String(s||'').trim().replace(/\s+/g,' ');
          const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;};
          const nodes=[...document.querySelectorAll('*')].filter(e=>visible(e)&&e.children.length===0&&norm(e.textContent)===target);
          return JSON.stringify({count:nodes.length,nodes:nodes.slice(0,4).map(n=>{
            const ancestors=[];for(let p=n,i=0;p&&i<6;p=p.parentElement,i++)ancestors.push({tag:p.tagName,id:p.id,className:p.className,
              text:norm(p.innerText).slice(0,2200),href:p.getAttribute('href'),
              controls:[...p.querySelectorAll('a,button,kat-button')].filter(visible).slice(0,16).map(e=>({tag:e.tagName,id:e.id,text:norm(e.innerText||e.textContent),href:e.getAttribute('href'),aria:e.getAttribute('aria-label'),shadow:!!e.shadowRoot}))});
            return ancestors;})});
        })()'''.replace('__FOCUS__',json.dumps(focus_text,ensure_ascii=False))
        focus_args=['page','exec','--store-id',store_id,'--script',focus_script]
        if target_id:
            focus_args.extend(['--target-id',target_id])
        focus=run(native_cli(),*focus_args)
        if focus.get('ok') is not True:
            raise ValueError('只读目标上下文提取失败')
        while isinstance(focus.get('data'),dict):
            focus=focus['data']
        if focus.get('exceptionDetails'):
            raise ValueError('只读目标上下文提取失败')
        result['focusContext']=json.loads(focus.get('result',''))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store-id', required=True)
    parser.add_argument('--target-id')
    parser.add_argument('--expected-origin', required=True)
    parser.add_argument('--seller', required=True)
    parser.add_argument('--country', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--focus-text')
    args = parser.parse_args()
    try:
        result = observe(args.store_id, args.target_id, args.expected_origin, args.seller, args.country,args.focus_text)
    except Exception as error:
        raise SystemExit(str(error)) from None
    output = Path(args.output).resolve()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output':str(output), 'url':result['url'], 'identityVerified':True,
                      'text':result['content']['text'][:5000], 'focusContext':result.get('focusContext'), 'buttons':result['content']['buttons'][:20],
                      'links':result['content']['links'][:12]}, ensure_ascii=False))
