"""Stable human-facing SKU; internal product IDs stay unchanged."""
from datetime import datetime,timezone,timedelta
import re
BOUNDS=[(-20319,'A'),(-20284,'B'),(-19776,'C'),(-19219,'D'),(-18711,'E'),(-18527,'F'),(-18240,'G'),(-17923,'H'),(-17418,'J'),(-16475,'K'),(-16213,'L'),(-15641,'M'),(-15166,'N'),(-14923,'O'),(-14915,'P'),(-14631,'Q'),(-14150,'R'),(-14091,'S'),(-13319,'T'),(-12839,'W'),(-12557,'X'),(-11848,'Y'),(-11056,'Z')]
def initials(name):
    out=[]
    for ch in name:
        if ch.isascii() and ch.isalpha():out.append(ch.upper());continue
        try:
            raw=ch.encode('gbk')
            if len(raw)!=2:continue
            code=raw[0]*256+raw[1]-65536
            for bound,letter in reversed(BOUNDS):
                if code>=bound:out.append(letter);break
        except UnicodeError:continue
    return ''.join(out) or 'USER'
def ensure(product,user,used):
    if product.get('sku'):
        previous=product['sku']
        if re.fullmatch(r'[A-Za-z]+-\d{8}-\d{6}',previous) and previous.replace('-','') not in used:
            product['sku']=previous.replace('-','');used.discard(previous);used.add(product['sku'])
        return
    prefix=initials(user.get('name') or user.get('username',''))
    now=datetime.now(timezone(timedelta(hours=8)))
    sku=prefix+now.strftime('%Y%m%d%H%M%S')
    while sku in used:
        now+=timedelta(seconds=1);sku=prefix+now.strftime('%Y%m%d%H%M%S')
    product['sku']=sku;used.add(sku)
def folder(product):
    value=str(product.get('sku') or product['id'])
    return re.sub(r'[^A-Za-z0-9_-]','_',value)[:100] or 'product'
