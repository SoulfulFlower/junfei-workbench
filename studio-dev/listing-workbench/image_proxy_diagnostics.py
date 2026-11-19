"""Persist bounded, redacted local-proxy errors without request bodies or keys."""
import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
import app_paths


class ProxyHTTPError(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__('Codex Tools HTTP '+str(diagnostic['httpStatus'])+'：'+diagnostic['message']+
                         '；错误记录 '+diagnostic['id']+'，未自动重试')


def redact(message, key):
    message=str(message)
    if key:message=message.replace(key,'[已隐藏]')
    message=re.sub(r'(?i)\b(?:bearer|authorization|cookie|access[_-]?token|refresh[_-]?token|api[_-]?key|password)\b\s*[:=]?\s*[^\s,;]+',
                   '[认证信息已隐藏]',message)
    message=re.sub(r'(?i)https?://[^\s<>"\']+',lambda m:clean_url(m.group()),message)
    message=re.sub(r'[A-Za-z0-9._~+/=-]{24,}','[长标识已隐藏]',message)
    message=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[账号已隐藏]',message)
    return ''.join(c for c in message if c in '\n\t' or ord(c)>=32)[:2000]


def clean_url(value):
    try:
        u=urlsplit(value)
        return u.scheme+'://'+(u.hostname or '')+u.path
    except ValueError:return '[地址已隐藏]'


def capture(error, endpoint, key):
    message='反代未提供可解析的错误说明'
    try:
        raw=error.read(32769)
        if len(raw)<=32768:
            value=json.loads(raw)
            obj=value.get('error') if isinstance(value,dict) else None
            candidate=obj.get('message') if isinstance(obj,dict) else obj
            if isinstance(candidate,str) and candidate.strip():message=redact(candidate,key)
    except (OSError,ValueError,TypeError):pass
    diagnostic={'id':uuid.uuid4().hex,'provider':'Codex Tools','httpStatus':error.code,
                'path':urlsplit(endpoint).path,'message':message,
                'capturedAt':datetime.now(timezone(timedelta(hours=8))).isoformat(),
                'requestBodySaved':False,'rawResponseSaved':False,'retrySubmitted':False}
    directory=app_paths.DATA/'image-errors'
    try:
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/(diagnostic['id']+'.json')
        with path.open('x',encoding='utf-8') as stream:json.dump(diagnostic,stream,ensure_ascii=False,indent=2)
        diagnostic['saved']=True
    except OSError:diagnostic['saved']=False
    return diagnostic
