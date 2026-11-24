"""Shared public research cache; never stores credentials or employee products."""
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

DB=Path(__file__).resolve().parent/'data'/'shared-sellersprite.sqlite3'
TTL={'asin_detail':7*86400,'traffic_keyword':86400,'keyword_miner':86400,'review':86400}
TTL.update({name:86400 for name in ('product_research','keyword_research','keyword_research_trends','asin_sales_trend','traffic_keyword_stat')})

@contextmanager
def connection():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, tool TEXT, body TEXT, expires REAL, owner TEXT, lease REAL, hits INTEGER NOT NULL DEFAULT 0)')
    c.commit()
    try:
        with c:yield c
    finally:c.close()

def cache_key(name,args):
    args=dict(args.get('request',args))
    for field in ('asin','marketplace'):
        if isinstance(args.get(field),str):args[field]=args[field].strip().upper()
    if isinstance(args.get('keyword'),str):args['keyword']=' '.join(args['keyword'].casefold().split())
    return hashlib.sha256(json.dumps([1,name,args],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def get_or_fetch(name,args,fetch):
    if name not in TTL:return fetch()
    key=cache_key(name,args);owner=uuid.uuid4().hex;deadline=time.time()+125
    while True:
        now=time.time()
        with connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT body,expires,owner,lease FROM cache WHERE key=?',(key,)).fetchone()
            if row and row[0] and row[1]>now:
                c.execute('UPDATE cache SET hits=hits+1 WHERE key=?',(key,))
                return json.loads(row[0])
            if not row or not row[2] or row[3]<now:
                c.execute('INSERT INTO cache(key,tool,owner,lease) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET owner=excluded.owner,lease=excluded.lease',(key,name,owner,now+120))
                break
        if time.time()>deadline:raise ValueError('相同查询正在处理中，请稍后重试，未重复调用卖家精灵')
        time.sleep(.2)
    try:
        data=fetch()
        # Empty/error responses must not hide a later provider recovery.
        useful=isinstance(data,dict) and bool(data) and (name!='asin_detail' or bool(data.get('title'))) and (name not in ('traffic_keyword','keyword_miner','review','product_research','keyword_research') or any(data.get(k) for k in ('items','reviews','list','records')))
        with connection() as c:
            if useful:
                c.execute('UPDATE cache SET body=?,expires=?,owner=NULL,lease=0 WHERE key=? AND owner=?',(json.dumps(data,ensure_ascii=False),time.time()+TTL[name],key,owner))
            else:c.execute('DELETE FROM cache WHERE key=? AND owner=?',(key,owner))
        return data
    except BaseException:
        with connection() as c:c.execute('UPDATE cache SET owner=NULL,lease=0 WHERE key=? AND owner=?',(key,owner))
        raise

def stats():
    with connection() as c:
        row=c.execute('SELECT count(*),coalesce(sum(hits),0) FROM cache WHERE body IS NOT NULL').fetchone()
    return {'entries':row[0],'hits':row[1]}
