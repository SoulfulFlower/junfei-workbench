import io
import json
import zipfile
from pathlib import Path
from PIL import Image,ImageDraw
from live_e2e import OUT,product,workspace,PRODUCT,dump
import studio_bridge as bridge
import visual_studio as visual
import listing_preview

p=product();copy=workspace()['copy'][PRODUCT+'-UK'];view=bridge.get_view(p)
images=view['sets']['gallery']['images'];summary=[]
canvas=Image.new('RGB',(1400,700),'#e9edf2');draw=ImageDraw.Draw(canvas)
for index,image in enumerate(images):
    rid=image.get('_runId')
    if not rid:continue
    run=visual.get_run(rid);raw,_=bridge.result_image(rid)
    photo=Image.open(io.BytesIO(raw)).convert('RGB');photo.save(OUT/'images'/f'final-{index+1}.png')
    photo.thumbnail((340,320));x=index%4*350;y=index//4*350;canvas.paste(photo,(x,y))
    draw.text((x+8,y+324),str(index+1)+' '+('AI check passed' if image.get('render_qa',{}).get('ready') else 'Review required'),fill='#203047')
    summary.append({'slot':index+1,'mode':run.get('mode','image_model'),'runId':rid,'status':run['status'],'qc':run.get('qc',[])})
canvas.save(OUT/'final-contact-sheet.jpg');dump('final-results.json',summary)
html=listing_preview.render(p,copy,view).decode('utf-8')
for index,image in enumerate(images):
    if image.get('final_url'):html=html.replace(image['final_url'].replace('&','&amp;'),'images/final-'+str(index+1)+'.png')
(OUT/'Listing-preview.html').write_text(html,encoding='utf-8')
report='''# 英国站完整Listing实测

产品：IMP-UK-B0FVS1X3SP / 788 Hooded Fleece Jacket

- 真实调用卖家精灵：4个ASIN读取成功，307个去重词，21条评论样本。
- 1688服务器直读仍被拦截，本次使用产品中已有的插件采集资料；没有用空结果覆盖。
- DeepSeek文案生成、编辑复核后已存入当前UK文案；原文案已备份。
- 实际调用生图生成7张，另外重做场景图1次；保留全部版本。
- 主图与细节图另制作6张原图保真排版，产品来自原图提取、缩放及裁切，不是模型重画。
- 当前7张图片中3张通过单图AI检查，4张仍需复核。原图排版的部分AI报告包含火焰残留等与实际图像不符的疑似误报，未据此自动批准。场景图仍有商标字形改写，属于实际问题，未批准交付。
- 图像中的实际品牌标识与Generic默认品牌存在冲突，品牌/授权未核实，不能直接视为可上架文件。
- 本次生成的是完整审核草稿，未发布到亚马逊。

软件修正：超长标题/亮点一次局部精简并重新校验；等价列表输出规范化；后台词清除尺码颜色清单；中文服装身份触发穿着规则；原图保真排版；质检补充当前分镜依据并区分输入/输出；原图版本恢复可正确读取本地图片；完整Listing预览。

打开 Listing-preview.html 可查看完整文案、中文翻译、7张图和内部提示。图片在 images/。实际费用以服务商后台账单为准。
'''
(OUT/'实测报告.md').write_text(report,encoding='utf-8')
with zipfile.ZipFile(OUT/'UK-Listing-完整审核草稿.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in ('Listing-preview.html','listing-final.json','final-results.json','实测报告.md','final-contact-sheet.jpg'):
        archive.write(OUT/name,name)
    for path in sorted((OUT/'images').glob('final-*.png')):archive.write(path,'images/'+path.name)
print('EXPORT_OK',len(images),sum(im.get('render_qa',{}).get('ready',False) for im in images),flush=True)
