"""Recheck existing, account-owned artwork without an image-generation request."""
import base64
import copy
import hashlib
import threading
import time
import uuid
import studio_bridge as bridge
import visual_studio as visual
import image_quality


def start(data, product):
    if data.get('confirmed') is not True:
        raise ValueError('请确认对现有成图执行新的模型检查')
    project = bridge.latest_project(product['id'], data.get('deliverable', 'gallery'))
    if not project or data.get('projectId') != project['id']:
        raise ValueError('分镜版本已变化，请核对当前方案')
    visual.require_ai_storyboard(project, product['id'])
    source = visual.get_run(data.get('runId'))
    index = data.get('slot')
    if type(index) is not int or not 0 <= index < len(project['plan']['slots']) or source.get('productId') != product['id'] or source.get('slot') != index:
        raise ValueError('现有成图与产品或图位不匹配')
    if source.get('status') not in ('approved', 'awaiting_manual', 'needs_revision', 'review_error') or not source.get('image'):
        raise ValueError('仅可重检已有确定成图，不处理未知提交或生成失败')
    raw, mime = bridge.result_image(source['id'])
    sha = hashlib.sha256(raw).hexdigest()
    if data.get('sha256') != sha:
        raise ValueError('成图内容哈希不符')
    with bridge.LOCK:
        runs = visual.list_projects(product['id'])['runs']
        if any(r['projectId'] == project['id'] and r['status'] not in bridge.TERMINAL for r in runs):
            raise ValueError('请等待当前图片任务完成')
        if bridge.get_view(product)['jobs'].get('review_image', {}).get('status') in ('running', 'queued'):
            raise ValueError('已有成图复核执行中，请先查询原任务')
        task = bridge.task_new(product, 'review_image')
        task.update(sourceRunId=source['id'], sourceSha256=sha)
        bridge.task_save(task)

    def work():
        try:
            run = copy.deepcopy(source)
            run.update(id=uuid.uuid4().hex, projectId=project['id'], status='reviewing', manual=False,
                       mode='existing_artwork_review', sourceRunId=source['id'], sourceSha256=sha,
                       reviewedAt=time.time(), previousQc=copy.deepcopy(source.get('qc', [])))
            visual.save_run(run)
            qc = visual.review(project, index, 'data:' + mime + ';base64,' + base64.b64encode(raw).decode(),
                               source_layout=source.get('mode') == 'source_layout', submitted_references=source.get('references'))
            gallery = project.get('deliverable', 'gallery') == 'gallery'
            technical = image_quality.inspect(raw, main=gallery and index == 0, full_bleed=gallery and index > 0)
            qc['technical'] = technical
            qc['issues'] = [*qc.get('issues', []), *[item['message'] for item in technical['issues'] if item['severity'] == 'error']]
            qc['pass'] = qc.get('pass') is True and technical['pass'] and not qc['issues']
            run['qc'] = [*source.get('qc', []), qc]
            run['status'] = 'awaiting_manual' if qc.get('pass') and not qc.get('issues') else 'needs_revision'
            visual.save_run(run)
            project['set_qa'] = None
            visual.save_project(project)
            task.update(status='done', done_count=1, progress=1, runId=run['id'],
                        message='原文件复核完成，保留历史检查，未调用生图接口')
        except Exception as error:
            if 'run' in locals():
                run.update(status='review_error', error=str(error))
                visual.save_run(run)
            task.update(status='failed', error=str(error))
        bridge.task_save(task)
    threading.Thread(target=work, daemon=True).start()
    return task
