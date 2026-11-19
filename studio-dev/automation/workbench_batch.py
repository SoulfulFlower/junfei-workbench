"""Batch current workbench operations through its existing logged-in EGO page.

No cookies, direct 1688 navigation, browser creation, model calls or publish start.
Every invocation uses a new UTF-8 EGO round and retains its request journal.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent


def supplier_url(value):
    parsed = urlsplit(value)
    match = re.fullmatch(r'/offer/([1-9][0-9]*)\.html', parsed.path)
    if (parsed.scheme != 'https' or parsed.netloc != 'detail.1688.com' or
            parsed.username or parsed.password or parsed.fragment or not match):
        raise ValueError('货源仅接受已观察到的 https://detail.1688.com/offer/数字.html')
    return 'https://detail.1688.com/offer/' + match[1] + '.html'


def load_session(path):
    session = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    workbench = session.get('workbench', {})
    protected = {0, *session.get('protectedSpaceIds', [])}
    if (type(session.get('accountId')) is not int or session['accountId'] <= 0 or
            type(workbench.get('id')) is not int or workbench['id'] in protected or
            not isinstance(workbench.get('name'), str) or not workbench['name'] or
            not re.fullmatch(r'p[1-9][0-9]*', workbench.get('page', ''))):
        raise ValueError('需要当前已核对的账号与专属工作台空间；不接管或重建窗口')
    return {key: session[key] for key in ('accountId', 'workbench')}


def make_plan(args):
    session = load_session(args.session)
    urls = list(dict.fromkeys(supplier_url(url) for url in args.supplier))
    jobs = list(dict.fromkeys(args.job))
    if any(not re.fullmatch(r'[a-f0-9]{32}', job) for job in jobs):
        raise ValueError('只接受已有原刊登任务ID')
    if len(urls) > 20 or len(jobs) > 20:
        raise ValueError('一次最多20个货源与20个原任务')
    if args.action == 'supplier-add' and not urls:
        raise ValueError('请提供待采集货源 --supplier')
    if args.action == 'observe' and len(jobs) != 1:
        raise ValueError('原刊登只读刷新一次仅允许一个任务，后台串行使用ERP')
    if args.action != 'status' and not args.execute:
        raise ValueError('业务动作须显式 --execute；状态查询无需该参数')
    return {**session, 'action': args.action, 'suppliers': urls, 'jobs': jobs}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'supplier-add', 'observe'])
    parser.add_argument('--session', required=True, help='本批已确认的spaces.json')
    parser.add_argument('--supplier', action='append', default=[], help='可重复；统一队列处理，不直接开详情')
    parser.add_argument('--job', action='append', default=[], help='可重复；已有publication job ID')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(argv)
    try:
        plan = make_plan(args)
        output = Path(args.output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)
        run_id = uuid.uuid4().hex
        plan.update(runId=run_id, outputDirectory=str(output), resultFile=str(output / (run_id + '.json')))
        entry = output / (run_id + '.mjs')
        runtime = (HERE / 'workbench_batch_runtime.mjs').as_uri()
        entry.write_text('const {run}=await import(' + json.dumps(runtime) + ');\nawait run(' +
                         json.dumps(plan, ensure_ascii=False) + ');\n', encoding='utf-8')
        cli = shutil.which('ego-browser')
        if not cli:
            raise ValueError('ego-browser不可用，不另启浏览器或复制登录')
        result = subprocess.run([cli, 'nodejs', '-e', "await import('" + entry.as_uri() + "')"],
                                capture_output=True, encoding='utf-8', timeout=90)
        print(result.stdout, end='')
        if result.stderr:
            print(result.stderr, end='', file=__import__('sys').stderr)
        if not Path(plan['resultFile']).is_file():
            raise ValueError('运行没有完整回执；保留原round，不自动重发')
        report = json.loads(Path(plan['resultFile']).read_text(encoding='utf-8'))
        return result.returncode or int(bool(report.get('error')))
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(str(error), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
