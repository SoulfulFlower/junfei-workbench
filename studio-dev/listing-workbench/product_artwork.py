"""Source-photo layouts: do not ask an image model to redraw product markings."""
import base64
import io
import threading
import time
import uuid
import os
import hashlib
import math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
from product_pixels import primary_product_cutout
from storyboard_variety import is_scene
import visual_studio as visual
import image_provider
import image_quality
import image_composition


SIZE_CHART_PREVIEW_BOX = (1510, 110, 1880, 490)


def crop_source(raw, box):
    if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in box):
        raise ValueError('原图裁剪须为四个0–1坐标')
    x1,y1,x2,y2=box
    if x2-x1<.05 or y2-y1<.05:raise ValueError('原图裁剪区域过小或顺序无效')
    with Image.open(io.BytesIO(raw)) as image:
        rect=[round(x1*image.width),round(y1*image.height),round(x2*image.width),round(y2*image.height)]
        if rect[2]-rect[0]<80 or rect[3]-rect[1]<80:raise ValueError('原图裁剪不足80像素，无法提供可读细节')
        output=io.BytesIO();image.crop(rect).save(output,'PNG')
        return output.getvalue(),{'originalSha256':hashlib.sha256(raw).hexdigest(),'sourceDimensions':list(image.size),'normalizedBox':box,'pixelBox':rect}

def font(size,bold=False):
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' if os.name == 'nt' else Path('/usr/share/fonts/truetype/dejavu')
    name = ('arialbd.ttf' if bold else 'arial.ttf') if os.name == 'nt' else ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')
    return ImageFont.truetype(str(folder/name),size)

def text(draw,value,x,y,width,size,bold=False):
    face=font(size,bold);line=''
    for word in value.split():
        candidate=(line+' '+word).strip()
        if draw.textlength(candidate,font=face)>width and line:
            draw.text((x,y),line,font=face,fill='#182536');y+=int(size*1.35);line=word
        else:line=candidate
    if line:draw.text((x,y),line,font=face,fill='#182536');y+=int(size*1.35)
    return y

def compose(raw,index,headline,caption,preserve_full_source=False):
    product=Image.open(io.BytesIO(raw)).convert('RGBA') if preserve_full_source else primary_product_cutout(raw)
    canvas=Image.new('RGBA',(2000,2000),'#FFFFFF' if index==0 else '#F3F5F7')
    if index==0:
        if preserve_full_source:
            # A worn source can legitimately end at a sleeve or trouser crop.
            # Keep that photographed boundary at the output edge, not suspended
            # above a newly introduced white footer. No garment is extrapolated.
            layer=ImageOps.contain(product,(2000,2000),Image.Resampling.LANCZOS)
            canvas.alpha_composite(layer,((2000-layer.width)//2,2000-layer.height))
        else:
            layer=ImageOps.contain(product,(1840,1840),Image.Resampling.LANCZOS)
            canvas.alpha_composite(layer,((2000-layer.width)//2,(2000-layer.height)//2))
    else:
        draw=ImageDraw.Draw(canvas)
        y=text(draw,headline,140,130,1720,82,True)
        text(draw,caption,140,y+24,1720,44)
        if index==4 and not preserve_full_source:
            # Show real pixels, without synthesising new labels, weave or seams.
            part=product.crop((0,0,product.width,int(product.height*.58)))
            layer=ImageOps.contain(part,(1700,1350),Image.Resampling.LANCZOS)
        elif index==5 and not preserve_full_source:
            part=product.crop((0,int(product.height*.46),product.width,product.height))
            layer=ImageOps.contain(part,(1700,1350),Image.Resampling.LANCZOS)
        else:layer=ImageOps.contain(product,(1550,1440),Image.Resampling.LANCZOS)
        canvas.alpha_composite(layer,((2000-layer.width)//2,2000-110-layer.height))
    output=io.BytesIO();canvas.convert('RGB').save(output,'PNG');return output.getvalue()


def compose_size_chart(raw, chart, headline):
    """Typeset the verified table without an image model copying its numbers."""
    canvas=Image.new('RGB',(2000,2000),'#F3F5F7')
    drawing=ImageDraw.Draw(canvas)
    title=font(88,True)
    label=headline or 'Size Guide'
    if drawing.textlength(label,font=title)>1320:
        raise ValueError('尺码图标题过长，无法在产品预览旁清楚排版')
    drawing.text((110,147),label,font=title,fill='#182536')
    basis={'garment_measurements':'Garment measurements','body_measurements':'Body measurements'}.get(chart.get('measurementsScope'),'Measurements')
    drawing.text((112,273),basis+' ('+str(chart['units'])+')',font=font(48),fill='#46505b')
    left,top,right,bottom=SIZE_CHART_PREVIEW_BOX
    with Image.open(io.BytesIO(raw)) as source:
        preview=ImageOps.contain(source.convert('RGB'),(right-left,bottom-top),Image.Resampling.LANCZOS)
    canvas.paste(preview,(right-preview.width,top+(bottom-top-preview.height)//2))
    rows=[chart['columns'],*chart['rows']]
    column=len(chart['columns'])
    cell_width=1780//column
    # A small offered size set still needs a readable full-canvas table.
    # The old 174px cap left most of a two-size chart empty.
    cell_height=min(380,1250//len(rows))
    if cell_height<52 or cell_width<125:
        raise ValueError('尺码表信息过多，无法在标准商品图中清楚排版')
    x0,y0=110,550
    for row_index,row in enumerate(rows):
        top=y0+row_index*cell_height
        drawing.rectangle((x0,top,x0+1780,top+cell_height),fill='#e2e8ee' if row_index==0 else '#fff')
        for index,value in enumerate(row):
            label=str(value)
            size=min(98,max(56,round(cell_height*.26)))
            if not row_index and len(label)>=10:size=max(49,size-7)
            bold=row_index==0 or index==0
            face=font(size,bold)
            while size>28 and drawing.textlength(label,font=face)>cell_width-28:
                size-=2;face=font(size,bold)
            if drawing.textlength(label,font=face)>cell_width-28 or '\n' in label:
                raise ValueError('尺码表单元格超出可读排版范围')
            drawing.text((x0+index*cell_width+cell_width//2,top+cell_height//2),label,anchor='mm',font=face,fill='#182536')
        drawing.line((x0,top+cell_height,x0+1780,top+cell_height),fill='#ced6df',width=2)
    output=io.BytesIO();canvas.save(output,'PNG');return output.getvalue()


def start(data,product):
    import studio_bridge as bridge
    project=bridge.latest_project(product['id'],data.get('deliverable','gallery'))
    if not project or project.get('deliverable','gallery')!='gallery':raise ValueError('请先策划画廊套图；原图排版暂不用于A+')
    if data.get('projectId') and data['projectId']!=project['id']:raise ValueError('分镜版本已变化，请核对当前方案')
    visual.require_ai_storyboard(project,product['id'])
    if data.get('confirmed') is not True:raise ValueError('请确认使用原图排版及AI质检')
    indices=data.get('indices',[i for i in range(len(project['plan']['slots'])) if i!=1])
    if not isinstance(indices,list) or not indices or any(type(i) is not int or not 0<=i<len(project['plan']['slots']) for i in indices):raise ValueError('请选择有效分镜')
    for index in indices:
        image=(project.get('uiPlan') or {}).get('images',[])
        image=image[index] if image else {}
        if image.get('production_method')=='blocked':raise ValueError('此分镜缺少事实或素材，不能排版')
        if is_scene(image) and image.get('production_method')!='source_layout':raise ValueError('场景分镜必须明确选择真实素材排版')
    crops=data.get('sourceCrops',{})
    if not isinstance(crops,dict) or any(str(i) not in {str(n) for n in indices} or str(i) in ('0',str(len(project['plan']['slots'])-1)) for i in crops):
        raise ValueError('只可为当前选择的非主图及非尺码图指定原图裁剪')
    reference_indices=data.get('sourceReferenceIndices',{})
    if not isinstance(reference_indices,dict):raise ValueError('原图参考图位无效')
    for key,index in reference_indices.items():
        if key not in {str(n) for n in indices} or type(index) is not int or index not in project.get('uiPlan',{}).get('images',[])[int(key)].get('source_reference_indices',[]):
            raise ValueError('只能选用当前分镜已经核实关联的原图')
    with bridge.LOCK:
        if any(r['projectId']==project['id'] and r['status'] not in bridge.TERMINAL for r in visual.list_projects(product['id'])['runs']):raise ValueError('请等待当前图片任务完成')
        if bridge.get_view(product)['jobs'].get('render_set',{}).get('status')=='running':raise ValueError('已有批次在运行')
        task=bridge.task_new(product,'render_set',len(indices))
    def work():
        try:
            encoded=visual.encode_reference(project['references'][0]);source=base64.b64decode(encoded.split(',',1)[1])
            cache=image_provider.ROOT/'studio-results';cache.mkdir(exist_ok=True)
            failed=0
            for pos,index in enumerate(indices):
                slot=project['plan']['slots'][index]
                chart=None
                if project.get('uiPlan'):
                    im=project['uiPlan']['images'][index];copy=bridge.artwork_copy(im)
                    if im.get('size_chart'):
                        from ivyea_pipeline import size_chart_evidence
                        chart=size_chart_evidence(project.get('sizeEvidence'))
                        if not chart:raise ValueError('尺码图缺少已核实的尺寸表')
                    elif set(copy)-{'headline','subline'}:raise ValueError('原图排版目前只支持标题与副标题，请先简化此分镜文字')
                    headline=copy.get('headline','');caption=copy.get('subline','')
                else:headline=slot['headline'];caption=slot['caption']
                task.update(stage='card-'+str(index),message='正在保留原图产品并排版第'+str(index+1)+'张',progress=pos/len(indices));bridge.task_save(task)
                references=im.get('source_reference_indices',[]) if project.get('uiPlan') else []
                mapped=bool(references)
                selected_source=source
                if mapped:
                    ref_index=reference_indices.get(str(index),references[0])
                    if type(ref_index) is not int or not 0<=ref_index<len(project['references']):raise ValueError('分镜实物图关联无效')
                    selected_source=base64.b64decode(visual.encode_reference(project['references'][ref_index]).split(',',1)[1])
                crop_proof=None
                if str(index) in crops:selected_source,crop_proof=crop_source(selected_source,crops[str(index)])
                raw=(compose_size_chart(selected_source,chart,headline) if chart else
                     compose(selected_source,index,headline,caption,preserve_full_source=mapped))
                rid=uuid.uuid4().hex
                (cache/(rid+'.image')).write_bytes(raw)
                run={'id':rid,'projectId':project['id'],'productId':product['id'],'slot':index,'image':'local:'+rid,'status':'reviewing','mode':'source_layout','attempt':0,'manual':False,'qc':[],'autoRepair':False,'jobIds':[],'next':0,'config':{'resolution':'2K','size':'1:1','model':'source-photo-layout'}}
                run['sourceLayout']={'referenceIndex':ref_index if mapped else 0,'originalReference':project['references'][ref_index if mapped else 0],'crop':crop_proof,'outputSha256':hashlib.sha256(raw).hexdigest()}
                visual.save_run(run)
                try:
                    technical=image_quality.inspect(raw,main=index==0,full_bleed=index>0,size_chart=bool(chart))
                    composition=image_composition.for_project(raw,project,index)
                    technical['composition']=composition
                    technical['issues'].extend(composition['issues'])
                    technical['pass']=technical['pass'] and composition['pass']
                    qc=(visual.review(project,index,'data:image/png;base64,'+base64.b64encode(raw).decode(),source_layout=True)
                        if technical['pass'] else {'pass':False,'issues':[],'reviewModel':'本地构图与技术检查','at':time.time()})
                    qc['technical']=technical
                    qc['issues']=[*qc.get('issues',[]),*[i['message'] for i in technical['issues'] if i['severity']=='error']];qc['pass']=qc.get('pass') is True and technical['pass'] and not qc['issues']
                    run['qc']=[qc];run['status']='awaiting_manual' if qc['pass'] else 'needs_revision'
                    if not qc['pass']:failed+=1
                except Exception as e:run.update(status='review_error',error=str(e));failed+=1
                visual.save_run(run);task.update(done_count=pos+1,progress=(pos+1)/len(indices));bridge.task_save(task)
            task.update(status='done',message='原图排版完成，'+str(failed)+'张需复核；产品像素来自原图，未调用生图接口重画')
        except Exception as e:task.update(status='failed',error=str(e))
        bridge.task_save(task)
    threading.Thread(target=work,daemon=True).start();return task
