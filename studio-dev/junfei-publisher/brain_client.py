"""本地大脑动作接口；不调用模型、不保存模型密钥。"""
import json
from pathlib import Path
import sys
import time
import uuid

STATE = Path(__file__).resolve().parent / 'brain-state'


def send(command, timeout=25):
    ready = json.loads((STATE / 'ready.json').read_text(encoding='utf-8'))
    if ready.get('status') != 'ready':
        raise RuntimeError('请先在独立窗口连接 Edge')
    identifier = str(uuid.uuid4())
    payload = {**command, 'session': ready['session']}
    destination = STATE / 'commands' / (identifier + '.json')
    temporary = destination.with_suffix('.tmp')
    # Ensure non-ASCII store names survive Windows PowerShell/legacy console encodings.
    temporary.write_text(json.dumps(payload, ensure_ascii=True), encoding='utf-8')
    temporary.replace(destination)
    result_file = STATE / 'results' / destination.name
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_file.exists():
            try:
                result = json.loads(result_file.read_text(encoding='utf-8'))
            except (PermissionError, json.JSONDecodeError):
                # Windows 的原子替换/杀毒扫描可能短暂锁住回执；只重读，绝不重发动作。
                time.sleep(0.15)
                continue
            if result.get('status') != 'in_progress_unknown':
                return result
        time.sleep(0.15)
    return {'status': 'unknown', 'id': identifier, 'message': '动作结果未确认，不要重复派发；先读取该ID结果或重新观察页面'}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    command = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig')) if len(sys.argv) > 1 else json.load(sys.stdin)
    print(json.dumps(send(command), ensure_ascii=False, indent=2))
