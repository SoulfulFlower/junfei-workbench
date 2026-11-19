"""Run the IvyeaOps ASIN insight prompts against the captured gallery only."""
import json
import threading

import ivyea_asin_prompts as prompts

LOCK = threading.Lock()
ACTIVE = set()


def source(reference):
    return {key: reference.get(key) for key in ('asin', 'market', 'selectedAsin', 'title',
                                               'bullets', 'description', 'referenceImages')}


def analyze(product, *, complete=None, encode=None):
    from asin_reference import media_key, now
    from visual_studio import encode_reference, model_prompt

    reference = product.get('editorAsinReference') or {}
    gallery = reference.get('referenceImages') or []
    if not reference.get('capturedAt') or not gallery or len(gallery) > 7 or not all(map(media_key, gallery)):
        raise ValueError('请先采集 ASIN 的原始套图')
    evidence = source(reference)
    insight = reference.get('insight') or {}
    if insight.get('source') == evidence and insight.get('structured'):
        return insight

    product_id = product['id']
    with LOCK:
        if product_id in ACTIVE:
            raise ValueError('该产品的 ASIN 洞察正在运行')
        ACTIVE.add(product_id)
    try:
        complete = complete or model_prompt
        images = [(encode or encode_reference)(url) for url in gallery]
        market = reference['market']
        batches = []
        for offset in range(0, len(images), 4):
            end = min(offset + 4, len(images))
            prompt = prompts.image_batch(offset + 1, end, len(images))
            answer = complete(prompt, images[offset:end], market=market, purpose='asin_image_insight')
            batches.append(f'【图 {offset + 1}-{end}】\n{answer}')
        combined = '\n\n'.join(batches)
        summary = complete(prompts.text_task(prompts.image_summary(combined), web_search=False),
                           [], market=market, purpose='asin_image_summary')
        parts = [f"ASIN: {reference['asin']}", f'Marketplace: {market}']
        if reference.get('title'):
            parts.append(f"Current Title: {reference['title']}")
        if reference.get('bullets'):
            parts.append('Current Bullets:\n' + '\n'.join(f'- {item}' for item in reference['bullets']))
        if reference.get('description'):
            parts.append(f"Description: {reference['description'][:500]}")
        prompt = prompts.product_analysis(prompts.SKILL_KNOWLEDGE, '\n'.join(parts), summary)
        answer = complete(prompts.text_task(prompt), [], market=market, purpose='asin_product_insight',
                          json_output=True)
        try:
            structured = json.loads(answer[answer.index('{'):answer.rindex('}') + 1])
        except ValueError:
            raise ValueError('ASIN 洞察未返回有效 JSON，请核对模型回执后再试') from None
        if not isinstance(structured, dict) or not isinstance(structured.get('usp'), list):
            raise ValueError('ASIN 洞察缺少结构化卖点，请核对模型回执后再试')
        return {'source': evidence, 'structured': structured, 'imageInsights': summary, 'analyzedAt': now()}
    finally:
        with LOCK:
            ACTIVE.discard(product_id)
