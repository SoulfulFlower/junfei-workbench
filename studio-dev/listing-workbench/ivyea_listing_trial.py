"""Run the original IvyeaOps copy template with selected SellerSprite evidence.

The original vision prompt is AGPL-3.0-only. See SOURCE-NOTICE.md.
"""
import json
import re
import threading

import ivyea_asin_prompts
import ivyea_copy_core
import listing_brand_policy
import provider

DATA_LIMIT = 3000
ACTIVE = set()
LOCK = threading.Lock()

# From IvyeaOps copywriting.py, semantic vision branch.
VISION_PROMPT = (
    "You are analyzing product images for an Amazon listing. "
    "Product type: {product_type}. "
    "Extract: materials, key features, dimensions/size cues, accessories included, "
    "color options, usage scenarios visible in images. "
    "Be specific and factual. Do not invent features not visible. "
    'Return JSON: {{"features": ["feature1", ...], "materials": "...", '
    '"size_hints": "...", "accessories": "...", "scenarios": ["..."]}}'
)


def compact_keyword_metrics(metrics, reverse_terms):
    rows = []
    mining_groups = []
    for metric in metrics:
        values = {key: metric[key] for key in ('searches', 'purchases', 'purchaseRate',
                                               'naturalRank', 'month', 'updatedTime')
                  if metric.get(key) not in (None, '')}
        if metric.get('asin'):
            row = {'asin': metric['asin'], **values}
            if metric.get('trafficPercentage') not in (None, ''):
                row['trafficPercentage'] = metric['trafficPercentage']
            if row not in rows:
                rows.append(row)
        if metric.get('seed'):
            seed = metric['seed']
            source = metric.get('seedSource') or ('reverse' if seed.strip().casefold() in reverse_terms else 'product_copy')
            group = next((sources for recorded, sources in mining_groups if recorded == values), None)
            if group is None:
                group = {}
                mining_groups.append((values, group))
                rows.append({'seedSources': group, **values})
            seeds = group.setdefault(source, [])
            if seed not in seeds:
                seeds.append(seed)
    for row in rows:
        sources = row.get('seedSources')
        if sources and len(sources) == 1:
            source, seeds = next(iter(sources.items()))
            if len(seeds) == 1:
                row.update(seed=seeds[0], seedSource=source)
                del row['seedSources']
    return rows


def keyword_input_report(product, market, *, required=True):
    """Pack complete evidence rows, with an audit kept outside the prompt budget."""
    research = (product.get('competitorResearch') or {}).get(market) or {}
    if research.get('source') != 'sellersprite':
        if not required:
            return {'keywords': [], 'omitted': [], 'dataCharacters': 16, 'dataLimit': DATA_LIMIT}
        raise ValueError('请先完成当前站点的卖家精灵反查和拓展')
    selected = []
    omitted = []
    for row in research.get('keywords', []):
        if not isinstance(row, dict) or row.get('selected') is not True:
            continue
        phrase = row.get('phrase')
        if not isinstance(phrase, str) or not phrase.strip():
            continue
        reason = ('missing_metrics' if not row.get('metrics') else
                  'invalid_placement' if row.get('placement', 'bullets') not in
                  ('title', 'highlights', 'bullets', 'description', 'backend') else
                  'restricted_claim' if provider.RESTRICTED_CLAIMS.search(phrase) else '')
        if reason:
            omitted.append({'phrase': phrase.strip(), 'placement': row.get('placement', 'bullets'), 'reason': reason})
        else:
            selected.append(row)
    by_phrase = {}
    for row in selected:
        phrase = row.get('phrase', '').strip()
        if not phrase:
            continue
        key = phrase.casefold()
        if key not in by_phrase:
            by_phrase[key] = {**row, 'phrase': phrase, 'metrics': list(row['metrics'])}
        else:
            # The same phrase can be selected from several seeds/ASINs. Preserve
            # each distinct source record once, rather than keeping only the last.
            metrics = by_phrase[key]['metrics']
            metrics.extend(metric for metric in row['metrics'] if metric not in metrics)
    plan = provider.selected_keyword_plan(
        {'keywords': list(by_phrase.values())}, listing_brand_policy.excluded_brand_terms(product))
    planned = {row['phrase'].casefold() for row in plan}
    omitted.extend({'phrase': row['phrase'], 'placement': row.get('placement', 'bullets'),
                    'reason': 'excluded_brand'} for key, row in by_phrase.items() if key not in planned)
    reverse_terms = {term['keyword'].strip().casefold()
                     for source in research.get('sources', [])
                     for term in source.get('keywordData', [])}
    # Within title candidates use the measured buying signals without applying the bullet volume band.
    titles = [row for row in plan if row['placement'] in ('title', 'highlights')]
    titles.sort(key=lambda row: (row['placement'] != 'title', *tuple(-max((float(m[field]) for m in row['metrics']
                                            if m.get(field) is not None and
                                            re.fullmatch(r'\d+(?:\.\d+)?', str(m[field]))), default=-1)
                                      for field in ('purchaseRate', 'purchases', 'trafficPercentage', 'searches'))))
    # Reserve the first core title phrase, then give selected bullet terms a turn
    # before additional title synonyms consume the original 3,000-character cap.
    ranked = titles[:1] + [row for row in plan if row['placement'] == 'bullets'] + titles[1:] + [
        row for row in plan if row['placement'] not in ('title', 'highlights', 'bullets')]
    rows = []
    for word in ranked:
        original = by_phrase[word['phrase'].casefold()]
        metrics = compact_keyword_metrics(word['metrics'], reverse_terms)
        if not metrics:
            omitted.append({'phrase': word['phrase'], 'placement': word['placement'],
                            'reason': 'missing_source', 'detail': '没有可核对的反查 ASIN 或拓展种子记录'})
            continue
        row = {'phrase': word['phrase'], 'placement': word['placement'],
               'reason': original.get('reason', '')[:100], 'metrics': metrics}
        if len(json.dumps({'keywords': [*rows, row]}, ensure_ascii=False)) > DATA_LIMIT:
            omitted.append({'phrase': word['phrase'], 'placement': word['placement'],
                            'reason': 'data_limit', 'detail': '完整来源与指标记录超出本次 3000 字符预算',
                            'recordCharacters': len(json.dumps(row, ensure_ascii=False))})
            continue
        rows.append(row)
    if required and not rows:
        raise ValueError('请勾选有反查或拓展来源的关键词，或减少单条关键词的数据量')
    sent = {row['phrase'].casefold() for row in rows}
    omissions = {row['phrase'].casefold(): row for row in omitted if row['phrase'].casefold() not in sent}
    return {'keywords': rows, 'omitted': list(omissions.values()),
            'dataCharacters': len(json.dumps({'keywords': rows}, ensure_ascii=False)),
            'dataLimit': DATA_LIMIT}


def keyword_input(product, market, *, required=True):
    return keyword_input_report(product, market, required=required)['keywords']


def exact_placements(rows, copy):
    def words(value):
        return ' ' + ' '.join(re.findall(r"[^\W_]+", value.casefold())) + ' '

    fields = {'商品亮点': copy['highlights']}
    for name, label in (('titles', '标题'), ('bullets_a', '五点 A'), ('bullets_b', '五点 B'),
                        ('search_terms', '后台词')):
        fields.update({f'{label} {i}': value for i, value in enumerate(copy[name], 1)})
    return [{'phrase': row['phrase'], 'matches': [{'field': label, 'text': value}
                                                  for label, value in fields.items()
                                                  if words(row['phrase']) in words(value)]}
            for row in rows]


def parse_object(raw):
    start, end = raw.find('{'), raw.rfind('}')
    if start < 0 or end < start:
        raise ValueError('文案模型未返回 JSON，请先核对模型回执')
    try:
        return json.loads(raw[start:end + 1])
    except ValueError:
        raise ValueError('文案模型返回的 JSON 无法解析，请先核对模型回执') from None


def run(product, market):
    from asin_reference import now
    from visual_studio import encode_reference, model_prompt

    packing = keyword_input_report(product, market)
    rows = packing['keywords']
    reference = product.get('editorAsinReference') or {}
    if reference.get('market') != market:
        reference = (product.get('sourceImport') or {}).get('amazon') or {}
    facts = [product.get('features'), product.get('style'), product.get('material'),
             product.get('dimensions'), product.get('packageContents')]
    notes = [f"产品: {product['name']}"]
    if product.get('targetAudience'):
        notes.append(f"目标受众: {product['targetAudience']}")
    if any(facts):
        notes.append('卖点: ' + '\n'.join(dict.fromkeys(value for value in facts if value)))
    if reference.get('title'):
        notes.append(f"参考标题: {reference['title']}")
    if reference.get('bullets'):
        notes.append('参考五点:\n' + '\n'.join(reference['bullets'][:5]))
    assets = [item['url'] for item in product.get('assets') or []
              if item.get('source') in ('1688货源采集', '供应商图', '产品实拍', '实拍图')
              and item.get('url', '').startswith('/uploads/')]
    primary = (product.get('imageReferenceSelection') or {}).get('primary')
    images = ([primary] if primary in assets else assets[:1]) or (reference.get('referenceImages') or [])[:4]
    key = (product['id'], market)
    with LOCK:
        if key in ACTIVE:
            raise ValueError('该产品的原版文案验收正在运行')
        ACTIVE.add(key)
    try:
        vision = {}
        if images:
            raw = model_prompt(VISION_PROMPT.format(product_type=product['name']),
                               [encode_reference(url) for url in images],
                               market=market, purpose='ivyea_listing_copy_vision')
            vision = {**parse_object(raw), 'mode': 'vision'}
        prompt = ivyea_copy_core._build_listing_prompt(market, product['name'], '\n'.join(notes), vision,
                                                       {'available': True, 'data': {'keywords': rows}})
        raw = model_prompt(ivyea_asin_prompts.text_task(prompt, web_search=False), [], market=market,
                           purpose='ivyea_listing_copy_text', json_output=True)
        copy = parse_object(raw)
        for field, count in (('titles', 5), ('bullets_a', 5), ('bullets_b', 5), ('search_terms', 2)):
            if not isinstance(copy.get(field), list) or len(copy[field]) != count or not all(
                    isinstance(value, str) and value.strip() for value in copy[field]):
                raise ValueError(f'文案模型返回的 {field} 数量异常，请先核对模型回执')
        if not isinstance(copy.get('highlights'), str) or not copy['highlights'].strip():
            raise ValueError('文案模型未返回商品亮点，请先核对模型回执')
        return {'keywordsSent': rows, 'dataCharacters': packing['dataCharacters'],
                'keywordInputAudit': packing,
                'imageInputs': images, 'copy': copy, 'placements': exact_placements(rows, copy),
                'generatedAt': now()}
    finally:
        with LOCK:
            ACTIVE.discard(key)
