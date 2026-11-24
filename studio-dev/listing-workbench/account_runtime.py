"""Private child runtime. Never start this as an employee-facing server."""
import ctypes
import json
import os
import threading
import time
import app_paths
if not app_paths.WORKER_USER or not app_paths.INTERNAL_TOKEN:raise SystemExit('Internal account runtime only')
import server

def parent_watch():
    parent=int(os.environ['JUNFEI_PARENT_PID'])
    while True:
        time.sleep(5)
        if os.name=='nt':
            handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,parent)
            if not handle:os._exit(0)
            code=ctypes.c_ulong();ctypes.windll.kernel32.GetExitCodeProcess(handle,ctypes.byref(code));ctypes.windll.kernel32.CloseHandle(handle)
            if code.value!=259:os._exit(0)
        else:
            try:os.kill(parent,0)
            except OSError:os._exit(0)

server.studio_bridge.restart_tasks();server.visual_studio.start_worker();server.colour_sets.start_worker()
server.local_colour_tasks.start_worker()
server.supplier_capture.start_worker()
threading.Thread(target=parent_watch,daemon=True).start()
http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
ready=app_paths.DATA/'runtime-ready.json';temp=ready.with_suffix('.tmp');temp.write_text(json.dumps({'pid':os.getpid(),'port':http.server_port}),encoding='utf-8');temp.replace(ready)
http.serve_forever()
