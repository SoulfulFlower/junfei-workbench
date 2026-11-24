"""Resolve approved originals without creating a paid colour-generation task."""
import hashlib
import colour_master
import studio_bridge
import visual_studio as visual
import image_provider
import generated_gallery
import agent_review


def context(product):
    project=studio_bridge.latest_project(product['id'],'gallery')
    visual.require_ai_storyboard(project,product['id'],confirmed=True)
    count=image_provider.image_budget.configuration().get('gallery_count',7)
    selected=generated_gallery.selected(product,project['id'])
    items=[]
    if selected is not None:
        if not agent_review.gallery_approved(product,selected):raise ValueError('请先确认所选母版的草稿审核')
        for slot,(selection,job,index) in enumerate(selected):
            if job.get('storyboardProjectId')!=project['id'] or job.get('storyboardSlot')!=slot:raise ValueError('母版图片与当前分镜图位不一致')
            raw,info=generated_gallery.image_bytes(job,index)
            if selection.get('sha256')!=info['sha256']:raise ValueError('所选母版内容已变化')
            items.append(_item(slot,raw,sourceJobId=job['id'],sourceImageIndex=index))
        refs=selected[0][1].get('references') or []
        mid=colour_master.selection_id(product)
    else:
        runs=visual.list_projects(product['id'])['runs'];latest={}
        for run in runs:
            if run['projectId']==project['id'] and run['slot'] not in latest:latest[run['slot']]=run
        if sorted(latest)!=list(range(count)) or any(not r.get('image') or r['status'] not in ('approved','awaiting_manual') for r in latest.values()):raise ValueError('请先完成并确认整套母版，再进行本地换色')
        originals=[]
        for slot,run in sorted(latest.items()):
            url=run.get('image','')
            raw=image_provider.local_image(url) if url.startswith('/uploads/') else studio_bridge.result_image(run['id'])[0]
            originals.append((slot,run,raw))
        if any(run['status']!='approved' for _,run,_ in originals):
            if not agent_review.studio_gallery_approved(product,project['id'],
                    [run for _,run,_ in originals],[hashlib.sha256(raw).hexdigest() for _,_,raw in originals]):
                raise ValueError('母版需通过当前文件哈希绑定的自动检查及智能体草稿核对；不代替人工审核')
        cards=(project.get('uiPlan') or {}).get('images') or []
        for slot,run,raw in originals:
            card=cards[slot] if slot<len(cards) else {}
            metadata={'baseRun':run['id'],'productAbsent':card.get('product_presence')=='absent'}
            source_layout=run.get('sourceLayout') or {}
            if (card.get('size_chart') is True and run.get('mode')=='source_layout'
                    and source_layout.get('outputSha256')==hashlib.sha256(raw).hexdigest()):
                from product_artwork import SIZE_CHART_PREVIEW_BOX
                metadata['sizeChartPreviewBox']=list(SIZE_CHART_PREVIEW_BOX)
            items.append(_item(slot,raw,**metadata))
        refs=project.get('references') or [];mid=project['id']
    cards=(project.get('uiPlan') or {}).get('images') or []
    for item in items:
        if item['slot']<len(cards) and cards[item['slot']].get('size_chart') is True:
            item['sharedSizeChart']={'policy':'all-variants-unchanged-v1','sourceSha256':item['sourceSha256']}
    if len(items)!=count or not refs:raise ValueError('母版图位或原始产品参考图不完整')
    return {'id':mid,'storyboardProjectId':project['id'],'reference':refs[0],'items':items,'count':count}


def _item(slot,raw,**metadata):
    # Content-addressed copies are account-local. Original uploads stay untouched.
    import pixel_recolour as pixel
    import io
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>18_000_000:raise ValueError('母版超过1800万像素')
        data=pixel.png(im)
    return {'slot':slot,'sourceUpload':pixel.asset(data),'sourceSha256':hashlib.sha256(data).hexdigest(),**metadata}
