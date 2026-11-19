"""紫鸟官方本地 WebDriver 接口连接检查；密码仅在内存中使用。"""
import json, uuid, threading, tkinter as tk
from tkinter import ttk
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent
app=tk.Tk(); app.title('紫鸟官方 WebDriver · 连接检查');app.geometry('600x430')
ttk.Label(app,text='填写紫鸟登录信息（不是亚马逊账号）；密码不保存到文件。').pack(pady=12)
fields={}
for key,label in [('company','公司名'),('username','用户名'),('password','密码')]:
 row=ttk.Frame(app);row.pack(fill='x',padx=20,pady=5)
 ttk.Label(row,text=label,width=10).pack(side='left')
 e=ttk.Entry(row,show='*' if key=='password' else '');e.pack(side='left',fill='x',expand=True);fields[key]=e
out=tk.Text(app,height=12);out.pack(fill='both',expand=True,padx=20,pady=10)
def display(text):
 app.after(0,lambda:(out.insert('end',text+'\n'),out.see('end')))
def run(creds):
 try:
  session=requests.Session();session.trust_env=False
  for action in ['updateCore','getBrowserList']:
   r=session.post('http://127.0.0.1:19886',json={**creds,'action':action,'requestId':str(uuid.uuid4())},timeout=125);r.raise_for_status();data=r.json()
   code=data.get('statusCode');display(action+' 状态码：'+str(code))
   if str(code)!='0':
    display('接口尚未就绪，请检查权限、账号信息或内核更新。');return
   if action=='getBrowserList':
    shops=[{k:x.get(k) for k in ['browserOauth','browserName','siteId']} for x in data.get('browserList',[])]
    (ROOT/'shops.local.json').write_text(json.dumps(shops,ensure_ascii=False,indent=2),encoding='utf-8')
    for shop in shops: display(str(shop.get('browserName'))+' / '+str(shop.get('siteId')))
    display('连接成功；仅获取店铺列表，未启动或发布商品。')
 except requests.ConnectionError:display('本地接口尚未启动（127.0.0.1:19886）。')
 except Exception as e:display('连接检查失败：'+type(e).__name__)
 finally:creds.clear();app.after(0,lambda:button.config(state='normal'))
def connect():
 creds={k:e.get() for k,e in fields.items()}
 if not all(creds.values()):display('请填写公司名、用户名和密码。');return
 fields['password'].delete(0,'end');button.config(state='disabled');threading.Thread(target=run,args=(creds,),daemon=True).start()
button=ttk.Button(app,text='检查接口并获取店铺列表',command=connect);button.pack(pady=8)
app.mainloop()
