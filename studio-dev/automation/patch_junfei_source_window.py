"""Prepare or apply the reviewed 2.9.60 source-tab routing patch, with backups."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SHA = 'b7a1c9a2826a1317c27201fc2f0c3add6522d1e92c0502ab28eac70465f95810'
MARKER = '// junfei-source-window-fix:20261106\n'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def patch_worker(original):
    if digest(original) != ORIGINAL_SHA:
        raise ValueError('Unrecognized plugin bundle; do not patch another version')
    text = original.decode('utf-8')
    start = text.index('Wi=function(){')
    end = text.index(';function Gi', start)
    source = text[start:end]
    replacements = [
        ('var n,i,s,o,c,u;', 'var n,i,s,o,c,u,__sourceWindowContext=t.__sourceWindowContext;'),
        ('chrome.tabs.create({url:a},function(){})', '__junfeiOpen1688SourceTab(a,__sourceWindowContext).catch(function(e){console.error("1688 source window:",e.message)})'),
        ('chrome.tabs.create({url:u},function(){})', '__junfeiOpen1688SourceTab(u,__sourceWindowContext).catch(function(e){console.error("1688 source window:",e.message)})'),
        ('return function(t,r){return e.apply(this,arguments)}}()',
         'return function(t,r,n){var a=n&&n.tab;if(!a||!Number.isInteger(a.id)||!Number.isInteger(a.windowId)){r({type:"filed",url:t&&t.url,message:"Cannot identify the source tab window"});return Promise.resolve()}return e.call(this,Object.assign({},t,{__sourceWindowContext:{id:a.id,windowId:a.windowId}}),r)}}()'),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError('Unexpected supplier handler structure')
        source = source.replace(before, after)
    text = text[:start] + source + text[end:]
    for before, after in [
        ('case 277:return Wi(u,r),', 'case 277:return Wi(u,r,n),'),
        ('case"getAddr":return Wi(a,r),', 'case"getAddr":return Wi(a,r,t),'),
    ]:
        if text.count(before) != 1:
            raise ValueError('Unexpected source message dispatcher')
        text = text.replace(before, after)
    return (MARKER + 'import {open1688SourceTab as __junfeiOpen1688SourceTab} from "./source-tab-window.mjs";\n' + text).encode('utf-8')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=ROOT/'junfei-publisher/local-extensions/junfei-collector-2.9.60')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--apply', action='store_true')
    a=ap.parse_args()
    plugin=a.root.resolve(strict=True)
    manifest=json.loads((plugin/'manifest.json').read_text('utf-8-sig'))
    if manifest.get('version')!='2.9.60' or manifest.get('background',{}).get('service_worker')!='js/service_worker.js':
        raise ValueError('Wrong extension version or entry point')
    worker=plugin/'js/service_worker.js'
    raw=worker.read_bytes()
    patched=patch_worker(raw)
    helper=(ROOT/'junfei-publisher/source-window-fix/source-tab-window.mjs').read_bytes()
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    (out/'service_worker.original.js').write_bytes(raw)
    (out/'service_worker.patched.mjs').write_bytes(patched)
    (out/'source-tab-window.mjs').write_bytes(helper)
    evidence={'plugin_root':str(plugin),'version':manifest['version'],'original_sha256':digest(raw),'patched_sha256':digest(patched),'helper_sha256':digest(helper),'applied':False,'at':datetime.now().astimezone().isoformat(),'scope':'getTaobaoAddr and external getAddr supplier search only; sender tab captured per request; no current-window fallback; active=false'}
    if a.apply:
        worker.write_bytes(patched)
        (plugin/'js/source-tab-window.mjs').write_bytes(helper)
        evidence['applied']=True
    (out/'patch-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=='__main__':
    main()
