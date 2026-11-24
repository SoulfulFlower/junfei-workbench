"""Run durable Junfei image jobs through the current authenticated Ego page."""
import argparse,json,uuid,subprocess,shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description='钧飞工作台三功能：原模板套图、修图、原始GLSL换色；复用当前浏览器登录')
    p.add_argument('--job',type=Path,required=True,help='JSON: {jobs:[{productId,mode,source,brief,...}]}')
    p.add_argument('--space',type=int,required=True,help='当前任务的Ego TaskSpace ID')
    p.add_argument('--page',default='p1');p.add_argument('--base',default='http://127.0.0.1:18769')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=1800)
    args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    data=json.loads(args.job.resolve().read_text('utf-8'))
    jobs=data.get('jobs')
    if not isinstance(jobs,list) or not jobs:raise ValueError('job需要非空jobs列表')
    for job in jobs:
        if job.get('mode') not in ('suite','repair','colour') or not job.get('productId') or not job.get('brief'):raise ValueError('每项需要productId/mode/brief')
        for field in ('source','maskFile','targetReferenceFile'):
            if job.get(field):
                path=Path(job[field]).expanduser().resolve()
                if not path.is_file():raise ValueError('图片不存在：'+str(path))
                job[field]=str(path)
        if not job.get('source'):raise ValueError('每项需要source本地原图')
        extra=job.get('referenceFiles',[])
        if not isinstance(extra,list) or len(extra)>2:raise ValueError('referenceFiles最多2张，与source合计不超过3张')
        resolved=[]
        for filename in extra:
            path=Path(filename).expanduser().resolve()
            if not path.is_file():raise ValueError('补充原图不存在：'+str(path))
            resolved.append(str(path))
        if 'referenceFiles'in job:job['referenceFiles']=resolved
    descriptor=output/'workbench-jobs.json'
    if descriptor.exists():
        old=json.loads(descriptor.read_text('utf-8'))
        if old['inputs']!=jobs or old['base']!=args.base.rstrip('/'):raise ValueError('此输出目录已绑定不同输入，请用新的版本目录')
        old.update(space=args.space,page=args.page,timeout=args.timeout)
        descriptor.write_text(json.dumps(old,ensure_ascii=False,indent=2),'utf-8')
    else:
        descriptor.write_text(json.dumps({'base':args.base.rstrip('/'),'space':args.space,'page':args.page,'output':str(output),
            'timeout':args.timeout,'inputs':jobs,'jobs':[{'input':j,'requestId':uuid.uuid4().hex} for j in jobs]},ensure_ascii=False,indent=2),'utf-8')
    # One fresh module per invocation; the durable descriptor carries resume state.
    wrapper=output/('run-'+uuid.uuid4().hex+'.mjs')
    helper=(Path(__file__).parent/'workbench_images.mjs').resolve().as_uri()
    wrapper.write_text('const {runJobs}=await import('+json.dumps(helper)+');\nawait runJobs('+json.dumps(str(descriptor))+');\n','utf-8')
    entry="await import('"+wrapper.as_uri()+"')"
    executable=shutil.which('ego-browser')
    if executable:command=[executable,'nodejs','-e',entry]
    else:
        # This Windows installation exposes ego-browser through its shell profile.
        shell=shutil.which('pwsh') or shutil.which('powershell')
        if not shell:raise RuntimeError('未找到ego-browser；按ego-browser技能安装CLI后重试')
        command=[shell,'-NoLogo','-Command','ego-browser nodejs -e "'+entry+'"']
    subprocess.run(command,check=True)
if __name__=='__main__':main()
