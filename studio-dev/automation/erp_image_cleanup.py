"""Plan or execute scoped ERP image cleanup in an existing EGO binding."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True,help='Existing workbench account data directory')
    parser.add_argument('--binding',required=True,help='Existing EGO task binding')
    parser.add_argument('--required-mib',type=float,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New durable cleanup directory')
    parser.add_argument('--execute',action='store_true',help='Delete only the verified planned pictures')
    args=parser.parse_args()
    if args.required_mib<=0:parser.error('--required-mib must be positive')
    root=Path(__file__).resolve().parent.parent
    data=args.data.resolve();output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    families=[];references=[]
    for file in (data/'publication-flow').glob('*/receipt.json'):
        packet_file=file.with_name('input.json')
        if not packet_file.is_file():continue
        receipt=json.loads(file.read_text(encoding='utf-8'))
        packet=json.loads(packet_file.read_text(encoding='utf-8'))
        us=receipt.get('usPrepare',{}).get('preparedInput') or packet.get('input')
        uk=receipt.get('ukPrepare',{}).get('preparedInput')
        if us and uk and us.get('urls'):
            families.append({'job':file.parent.name,'us':us,'uk':uk})
    for component,name in [('erp-collection','collection.json'),('publication-flow','input.json')]:
        for file in (data/component).glob('*/'+name):
            raw=json.loads(file.read_text(encoding='utf-8'));packet=raw.get('input',raw)
            if not isinstance(packet,dict):continue
            references.append({'productId':packet.get('productId'),
                'shas':[asset['sha256'] for asset in packet.get('assets',[])],
                'urls':list(packet.get('urls',{}).values())})
    config=json.loads((root/'automation/config.json').read_text(encoding='utf-8'))
    binding=config['browser']['task_bindings'][args.binding]
    label=binding['pages']['erp']
    request={'families':families,'otherReferences':references,'requiredMiB':args.required_mib,'execute':args.execute,'page':label}
    request_file=output/'request.json'
    request_file.write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
    module=(root/'automation/erp_image_cleanup.mjs').as_uri()
    script=output/'cleanup.mjs'
    script.write_text(
        'const fs=await import("node:fs/promises");\n'
        'const request=JSON.parse(await fs.readFile('+json.dumps(str(request_file))+',"utf8"));\n'
        'const {cleanupWorkbenchPictures}=await import('+json.dumps(module)+');\n'
        'console.log(await cleanupWorkbenchPictures(globalThis.amazonTask.page(request.page),request,'+
        json.dumps(output.as_uri()+'/')+'));\n',encoding='utf-8')
    command=[sys.executable,'-B','-X','utf8',str(root/'automation/ego_browser.py'),
        'run',str(script),'--binding',args.binding,'--application-job','--timeout','1200']
    return subprocess.run(command,cwd=root).returncode


if __name__=='__main__':
    raise SystemExit(main())
