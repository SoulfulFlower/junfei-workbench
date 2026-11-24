"""Account-scoped runtimes keep provider globals and asynchronous jobs isolated.
Only the authenticated front server selects an account; URL/body owner IDs are ignored.
Worker ports bind loopback and require an unpredictable per-process token.
"""
import atexit
import http.client
import json
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import accounts
import app_paths
import secrets_store

LOCK=threading.RLock()
WORKERS={}
WORKSPACE_ROOT=app_paths.DATA/'account-workspaces'
_SUPPLIER_THREAD=None
_SUPPLIER_STOP=threading.Event()


def legacy_owner():
    with accounts.connect() as c:
        row=c.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    return row['id'] if row else None


def needs_proxy(user,path):
    return path not in ('/api/sellersprite/settings','/api/sellersprite/test') and not app_paths.WORKER_USER and bool(user) and user['id']!=legacy_owner() and (path.startswith('/uploads/') or path.startswith('/api/') and not path.startswith('/api/auth/'))


def start(user_id):
    with LOCK:
        with accounts.connect() as c:
            user=c.execute('SELECT status FROM users WHERE id=?',(user_id,)).fetchone()
        if user is None or user['status']!='active':
            raise ValueError('账号已停用，未启动工作空间')
        item=WORKERS.get(user_id)
        if item and item['process'].poll() is None:return item
        root=WORKSPACE_ROOT/str(user_id)
        root.mkdir(parents=True,exist_ok=True)
        token=secrets.token_urlsafe(48)
        ready=root/'runtime-ready.json';ready.unlink(missing_ok=True)
        env=os.environ.copy()
        # Employee runtimes must never inherit server-owner API environment secrets.
        for name in ('DEEPSEEK_API_KEY','APIMART_API_KEY','SELLERSPRITE_MCP_KEY','OPENAI_API_KEY','OPENAI_BASE_URL'):env.pop(name,None)
        env.update(JUNFEI_SHARED_CREDENTIALS=str(secrets_store.ROOT),JUNFEI_ACCOUNTS_DB=str(accounts.DB),JUNFEI_ACCOUNT_DATA=str(root),JUNFEI_WORKER_USER=str(user_id),JUNFEI_INTERNAL_TOKEN=token,JUNFEI_PARENT_PID=str(os.getpid()))
        env['JUNFEI_LIBRARY_ROOT']=str(app_paths.DATA)
        log=open(root/'runtime.log','ab')
        command = [sys.executable, '--account-runtime'] if getattr(sys, 'frozen', False) else [sys.executable, str(app_paths.APP/'account_runtime.py')]
        process=subprocess.Popen(command,cwd=app_paths.APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        log.close()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise ValueError('独立工作空间启动失败，请联系管理员')
            if ready.is_file():
                value=json.loads(ready.read_text(encoding='utf-8'))
                if value.get('pid')==process.pid:
                    item={'process':process,'port':value['port'],'token':token};WORKERS[user_id]=item;return item
            time.sleep(.05)
        process.terminate()
        raise ValueError('独立工作空间启动超时，请重试')


def proxy(handler,user):
    item=start(user['id']);length=int(handler.headers.get('Content-Length','0'))
    path=urlsplit(handler.path).path
    limit=64*1024*1024 if path=='/api/state' else 16*1024*1024
    if length<0 or length>limit:return handler.reply(413,{'error':'请求超过大小限制'})
    payload=handler.rfile.read(length) if length else None
    headers={k:v for k,v in handler.headers.items() if k.lower() not in ('connection','transfer-encoding','x-junfei-internal','content-length')}
    headers['X-Junfei-Internal']=item['token']
    # Listing generation can include three rounds of bullet repair and review.
    timeout=3000 if handler.command=='POST' and path=='/api/generate/listing' else 600
    connection=http.client.HTTPConnection('127.0.0.1',item['port'],timeout=timeout)
    try:
        connection.request(handler.command,handler.path,body=payload,headers=headers)
        response=connection.getresponse();raw=response.read()
        handler.send_response(response.status)
        for name,value in response.getheaders():
            if name.lower() not in ('server','date','connection','transfer-encoding','content-length'):handler.send_header(name,value)
        handler.send_header('Content-Length',str(len(raw)));handler.end_headers();handler.wfile.write(raw)
    finally:connection.close()


def supplier_account_status(user_id,status,*,purge=False):
    """Only lifecycle state crosses spaces; credentials and product payloads stay private."""
    import supplier_capture
    path=app_paths.DATA if int(user_id)==legacy_owner() else WORKSPACE_ROOT/str(int(user_id))
    supplier_capture.set_scope_status(supplier_capture.scope_for_data(path),status,purge=purge)


def dispatch_supplier_once():
    """Wake the actual FIFO owner's runtime even when no browser tab visits that account."""
    if app_paths.WORKER_USER:
        return None
    import supplier_capture
    with LOCK:
        with accounts.connect() as c:
            users=[dict(row) for row in c.execute('SELECT id,role,status FROM users')]
        owner=next((u['id'] for u in sorted(users,key=lambda u:u['id']) if u['role']=='admin'),None)
        if os.environ.get('JUNFEI_LOCAL_MODE') == '1':
            users=[user for user in users if user['id']==owner]
        scopes={supplier_capture.scope_for_data(app_paths.DATA if u['id']==owner else WORKSPACE_ROOT/str(u['id'])):u for u in users}
        scope=supplier_capture.dispatch_scope(scopes)
        if scope is None:
            return None
        uid=scopes[scope]['id']
        if uid==owner:
            supplier_capture.maintain()
        else:
            start(uid)  # Its explicit startup hook only claims never-executed queued work.
        return uid


def start_supplier_dispatcher():
    global _SUPPLIER_THREAD
    if app_paths.WORKER_USER:
        return
    with LOCK:
        if _SUPPLIER_THREAD is not None and _SUPPLIER_THREAD.is_alive():
            return
        _SUPPLIER_STOP.clear()
        def dispatch():
            while not _SUPPLIER_STOP.is_set():
                try:
                    dispatch_supplier_once()
                except Exception:
                    logging.getLogger(__name__).exception('1688队列调度失败；保留原队列等待下次核对')
                _SUPPLIER_STOP.wait(2)
        _SUPPLIER_THREAD=threading.Thread(target=dispatch,daemon=True,name='1688-global-queue-dispatch')
        _SUPPLIER_THREAD.start()


def purge_user(user_id):
    """Remove only a validated employee workspace after stopping its runtime."""
    import shutil
    uid = int(user_id)
    if uid <= 0 or uid == legacy_owner():
        raise ValueError('不能清除管理员工作空间')
    with LOCK:
        base = WORKSPACE_ROOT.resolve()
        target = WORKSPACE_ROOT / str(uid)
        if target.is_symlink() or target.resolve().parent != base:
            raise ValueError('工作空间路径异常，已中止删除')
        supplier_account_status(uid,'purged',purge=True)
        item = WORKERS.pop(uid, None)
        if item and item['process'].poll() is None:
            item['process'].terminate()
            try: item['process'].wait(timeout=10)
            except subprocess.TimeoutExpired:
                item['process'].kill(); item['process'].wait(timeout=10)
        if target.exists(): shutil.rmtree(target)


def shutdown():
    _SUPPLIER_STOP.set()
    with LOCK:
        for item in list(WORKERS.values()):
            if item['process'].poll() is None:
                item['process'].terminate()
                try:item['process'].wait(timeout=5)
                except subprocess.TimeoutExpired:item['process'].kill();item['process'].wait(timeout=5)
atexit.register(shutdown)
