import json,sqlite3
from pathlib import Path
import visual_studio as v
s=json.loads(sqlite3.connect('data/studio.sqlite3').execute('select body from workspace where id=1').fetchone()[0]);p=s['products'][0];ref=Path('data/live-check/source-url.txt').read_text();p['name']='供应商788藏青色连帽夹克';p['colorNames']='藏青色';p['market']='UK'
brief='真实付费整套测试。只制作同一件藏青色788连帽夹克。主体参考是800像素供应商图，右上火焰为营销图标，全部去掉。必须保留胸前标识、领标、袖章与拉链结构，不许猜测放大不可读文字。不要新增品牌。不做无依据尺寸、包装配件和其他颜色；第4张改为尺码选择指南，不标数值，仅提示Check size chart；第6张改为结构/口袋细节而非包装。任何无法从正面看到的背面结构不要生成。最多短英文文案。分别制作白底、生活场景、连帽结构、尺码选择、材质近景、正面细节、日常穿搭。图上不写保暖性能、防水或重量。'
try:
 result=v.plan({'references':[ref],'brief':brief,'count':7,'deliverable':'gallery','language':'en'},p,{})
 Path('data/live-check/full-image-project.json').write_text(json.dumps({'id':result['id'],'productId':p['id']}),encoding='utf-8')
 print('PLAN',result['id'],flush=True)
except Exception as e:print('PLAN_ERROR',type(e).__name__,str(e),flush=True)
