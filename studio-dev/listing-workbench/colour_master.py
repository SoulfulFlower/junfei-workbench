"""Freeze an account-owned, content-reviewed image selection for colour editing.

This does not create a storyboard, fabricate AI QC or grant human approval.
"""
import hashlib
import json
import uuid
import generated_gallery
import agent_review
import image_provider
import studio_bridge
import visual_studio as visual


def selection_id(product):
    selection = product.get('generatedGallerySelection')
    if selection is None:
        return None
    content = {'productId': product['id'], 'color': product.get('masterColor'),
               'selection': {k: selection.get(k) for k in
                             ('version', 'sourceStudioProjectId', 'items')}}
    return 'selected-' + hashlib.sha256(json.dumps(content, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def prepare(product):
    project = studio_bridge.latest_project(product['id'], 'gallery')
    visual.require_ai_storyboard(project, product['id'], confirmed=True)
    rows = generated_gallery.selected(product, project['id'] if project else None)
    if not rows or not agent_review.gallery_approved(product, rows):
        raise ValueError('所选母版需先完成绑定内容哈希的智能体草稿审核；选择图片不等于审核')
    refs = rows[0][1].get('references') or []
    if not refs:
        raise ValueError('母版主图缺少原始产品参考图')
    # Accept an original local reference only; preserve its bytes and evidence.
    reference = refs[0]
    reference_raw = image_provider.local_image(reference)
    items = []
    for slot, (selection, job, index) in enumerate(rows):
        if job.get('storyboardProjectId') != project['id'] or job.get('storyboardSlot') != slot:
            raise image_provider.StoryboardRequired('所选母版图未绑定当前 AI 分镜对应图位，请用工作台分镜出图后重新选择')
        raw, info = generated_gallery.image_bytes(job, index)
        if selection.get('sha256') != info['sha256']:
            raise ValueError('所选母版图片与已审核哈希不一致')
        ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}[info['mime']]
        name = uuid.uuid4().hex + ext
        (image_provider.ROOT / 'uploads' / name).write_bytes(raw)
        items.append({'slot': slot, 'sourceUpload': '/uploads/' + name,
                      'sourceSha256': info['sha256'], 'sourceJobId': job['id'],
                      'sourceImageIndex': index, 'status': 'queued'})
    return {'id': selection_id(product), 'reference': reference, 'storyboardProjectId': project['id'],
            'referenceSha256': hashlib.sha256(reference_raw).hexdigest(),
            'source': 'completed_image_job_selection', 'reviewScope': 'draft_only',
            'humanReviewed': False, 'items': items}
