"""为已存在六个变体填入确认的颜色尺码，不新增变体。"""
from library_fill import action
SIZES=['60x60cm','90x90cm','90x140cm','140x140cm','140x180cm','140x220cm']
D={'role':'dialog','name':'修改属性值'}
for i,size in enumerate(SIZES,1):
    row={'role':'row','name':f'WYJ20261030100733-White-{i:02d}','exact':False}
    for col,value in [(4,'White'),(5,size)]:
        action({'action':'click','target':{'css':f'td:nth-child({col}) i.el-icon-edit-outline','scope':row}})
        action({'action':'fill','target':{'role':'textbox','name':'输入属性','scope':D},'value':value})
        action({'action':'click','target':{'role':'button','name':'确 定','scope':D}})
        print(i,value,flush=True)
