import csv
import json
import trial_979071716133 as t

sources=json.loads((t.OUT/'keyword-sources.json').read_text(encoding='utf-8'))
mining=json.loads((t.OUT/'keyword-mining.json').read_text(encoding='utf-8'))
rows={}
for group in mining:
    for row in group['items']:
        key=row['keyword']
        if key not in rows or (row.get('searches') or -1)>(rows[key].get('searches') or -1):rows[key]=row
names=['bustier top','women corset top','polka dot corset','womens polka dot top','polka dot top','polka dot tank top','crop tops for women','corset tops for women']
keywords=[]
for name in names:
    if name not in rows:continue
    row=rows[name]
    keywords.append({'phrase':name,'selected':True,'placement':'title' if name=='bustier top' else 'bullets','monthlySearches':row.get('searches'),'metrics':[dict(row,source='SellerSprite keyword_miner',market='US')],'reason':'实测关键词；女性短款胸衣式吊带上衣匹配；corset仅作款式身份，不宣称塑形、鱼骨或钢圈'})
for row in sources[0]['keywordData']:
    if row['keyword'] in ['polka dot top corset','black and white polka dot corset top','black polka dot corset top','black and white polka dot corset']:
        keywords.append({'phrase':row['keyword'],'selected':True,'placement':'description','monthlySearches':row.get('searches'),'metrics':[dict(row,source='SellerSprite traffic_keyword',asin='B0G8F3NL39',market='US')],'reason':'竞品实测反查词，颜色词仅用于黑底白点款说明'})
research={'market':'US','sources':sources,'mining':mining,'keywords':keywords,'structure':'仅借鉴竞品按材质、结构、颜色尺码展开的组织方式；描述严格遵守用户属性行模板。竞品绑带、背扣、鱼骨等属性无本品证据，不使用。','warnings':'反查词多数缺月搜索量；挖掘数据月份2026.09；购买率为市场估计，不是本品转化率。关键词挖掘每词最多5页，非全量。'}
t.dump('keyword-research-reviewed.json',research)
with (t.OUT/'keywords.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['phrase','monthlySearches','purchaseRate','purchases','month','source','placement']);writer.writeheader()
    for k in keywords:
        m=k['metrics'][0];writer.writerow({'phrase':k['phrase'],'monthlySearches':k['monthlySearches'],'purchaseRate':m.get('purchaseRate'),'purchases':m.get('purchases'),'month':m.get('month'),'source':m['source'],'placement':k['placement']})
def update(s):
    p=next(p for p in s['products'] if p['id']==t.PID)
    p.setdefault('competitorResearch',{})['US']=research
t.change(update)
t.dump('listing-before-correction.json',t.state()['copy'][t.PID+'-US'])
print('RESEARCH_SAVED',len(rows),len(keywords),flush=True)
result=t.provider.generate_listing(t.product(),'US')
t.dump('listing-corrected-result.json',result)
copy=result['copy']
assert 'Fabric Name:' in copy['description'] and '\nNotes:\n' in copy['description']
assert '\n\n1 Pcs x ' in copy['description']
t.change(lambda s:s['copy'].__setitem__(t.PID+'-US',copy))
t.dump('listing-reviewed.json',copy)
print('CORRECTED',json.dumps({k:copy[k] for k in ['title','highlights','bullets','description','terms']},ensure_ascii=True),flush=True)
