"""Correct only colour-pattern facts, preserving the saved description layout."""
import json
import trial_979071716133 as t

old=json.loads((t.OUT/'listing-before-all-color-fact-check.json').read_text(encoding='utf-8'))
def update(s):
    p=next(p for p in s['products'] if p['id']==t.PID)
    p['features']=p['features'].replace('波点与纯色可选','22种底色与波点配色可选')
    p['copyNotes']=p['copyNotes'].replace('颜色样式含波点和纯色，不能宣称所有颜色均波点。','已逐张核对22张货源颜色图，均有波点；底色和点纹颜色随变体变化，不写纯色选项。')
    c=s['copy'][t.PID+'-US'];tr=old['translations'].copy()
    tr['highlights']=tr['highlights'].replace('可选波点或纯色','多种波点配色可选')
    tr['bullets']=tr['bullets'].replace('波点或纯色衣身','波点衣身')
    rows=tr['bullets'].splitlines()
    rows[3]='波点配色：同款短上衣提供22种底色与点纹配色组合。请查看所选变体图片，确认对应底色及波点颜色。主图展示的黑白配色仅代表其中一种颜色选项。'
    tr['bullets']='\n'.join(rows)
    tr['description']=tr['description'].replace('部分配色为波点，另有纯色可选','波点；底色与点纹颜色随配色变化').replace('多种配色，含波点及纯色','22种波点配色')
    tr['terms']=tr['terms'].replace('、纯色','')
    c['translations']=tr;c['zh']='\n\n'.join(tr[k] for k in ['title','bullets','description'])
    c['editorialPlan']=old['editorialPlan'].replace('波点/纯色','底色与点纹配色').replace('波点与纯色可选','22种波点配色可选')
t.change(update)
c=t.state()['copy'][t.PID+'-US'];t.dump('listing-result-final.json',c)
assert '纯色' not in json.dumps(c['translations'],ensure_ascii=False)
assert c['description'].split('Notes:')[1]==old['description'].split('Notes:')[1]
print('Saved colour facts and Chinese translations; original Notes retained')
