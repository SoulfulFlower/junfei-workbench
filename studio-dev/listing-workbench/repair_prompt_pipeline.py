"""Typed repair instructions with an explicit, local Codex text optimizer.

This reconstructs the observed public request semantics. It does not claim to
reproduce LinkFox's private server prompt or provider-internal expansion.
No transport, image submission, persistence, or account credentials live here.
"""
from copy import deepcopy
import hashlib
import json
import re


VERSION = 'codex-repair-typed-v1'
_SLOT = re.compile(r'\[([^\]]*)\]')
_RATIO = re.compile(r'[1-9][0-9]{0,2}:[1-9][0-9]{0,2}')


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def template_objects(text):
    """Match the native bracket editor: examples become empty typed slots."""
    if not isinstance(text, str):
        raise ValueError('原始修图模板必须是文本')
    result, end = [], 0
    for match in _SLOT.finditer(text):
        before = text[end:match.start()]
        if before.strip():
            result.append({'type': 'text', 'text': before})
        placeholder = match.group(1)
        if placeholder.strip():
            result.append({'type': 'tag', 'text': '', 'placeholder': placeholder})
        end = match.end()
    if text[end:].strip():
        result.append({'type': 'text', 'text': text[end:]})
    return result


def normalize_objects(objects):
    if not isinstance(objects, (list, tuple)) or len(objects) > 512:
        raise ValueError('修图输入节点格式错误')
    result = []
    for node in objects:
        if not isinstance(node, dict) or node.get('type') not in ('text', 'tag', 'newLine'):
            raise ValueError('修图输入节点类型错误')
        kind = node['type']
        item = {'type': kind}
        if kind != 'newLine':
            value = node.get('text', '')
            if not isinstance(value, str):
                raise ValueError('修图节点内容必须是文本')
            item['text'] = value
            if kind == 'tag':
                placeholder = node.get('placeholder', '')
                if not isinstance(placeholder, str):
                    raise ValueError('修图占位内容必须是文本')
                item['placeholder'] = placeholder
        result.append(item)
    return result


def objects_prompt(objects):
    return ''.join('\n' if node['type'] == 'newLine' else node.get('text', '')
                   for node in normalize_objects(objects))


def _size(value):
    value = '' if value is None else value
    if not isinstance(value, str) or (value not in ('', 'auto') and not _RATIO.fullmatch(value)):
        raise ValueError('修图比例须为空、auto或有效宽高比')
    return value


def _capability(capabilities):
    """Accept a server-produced route snapshot, never infer from a model name."""
    if capabilities is None:
        capabilities = {}
    if not isinstance(capabilities, dict):
        raise ValueError('修图模型能力记录格式错误')
    value = deepcopy(capabilities)
    source = value.get('source')
    source = source if isinstance(source, dict) else {}
    enabled = (value.get('localTextExpansion') is True
               and source.get('kind') == 'local_text_optimizer'
               and source.get('provider') == 'Codex Tools'
               and isinstance(source.get('model'), str) and bool(source['model'].strip()))
    # Provider builtin behavior remains unknown, irrespective of image model ID.
    return value, enabled


def _constraints(preservation):
    policy = {'identity': True, 'noNewFacts': True, 'neutralWhiteBalance': True,
              'fringeTexture': True}
    if preservation is not None:
        if not isinstance(preservation, dict):
            raise ValueError('修图保真配置格式错误')
        for key, enabled in preservation.items():
            if key not in policy or not isinstance(enabled, bool):
                raise ValueError('修图保真配置字段错误')
            policy[key] = enabled
    texts = {
        'identity': 'Preserve the source product identity, geometry and unchanged parts; apply only the requested edits.',
        'noNewFacts': 'Do not invent product facts, labels, dimensions, materials or accessories.',
        'neutralWhiteBalance': 'Keep unchanged product colours faithful under neutral white balance; avoid an added warm/yellow cast unless explicitly requested.',
        'fringeTexture': 'Where visible, preserve individual fringe strands, attachment rows, spacing, edges and fabric texture; do not merge them into a solid band.',
    }
    return [{'id': key, 'text': texts[key]} for key in texts if policy[key]]


def _codex_optimizer(prompt, images):
    import visual_studio
    import provider
    settings = visual_studio.proxy_vision_settings()
    if not settings or provider.text_provider_name(settings) != 'Codex Tools':
        raise ValueError('修图扩写必须使用当前账号已配置的 Codex Tools 文本路线')
    return visual_studio.model_prompt(prompt, images, market='analysis',
                                     purpose='official_repair_original_optimizer')


def compile_repair(row, brief, images, size='', *, objects=None,
                   need_optimize=None, image_capabilities=None,
                   preservation=None, optimizer=None):
    """Return (compiled_prompt, audit), without altering the original config.

    ``image_capabilities`` must come from the server, not request JSON. Its
    ``source`` describes the local text route, not an image-model builtin flag.
    ``optimizer`` is an injectable callable for isolated verification only.
    """
    if not isinstance(brief, str):
        raise ValueError('修图要求必须是文本')
    if need_optimize is not None and not isinstance(need_optimize, bool):
        raise ValueError('是否扩写须为布尔值')
    size = _size(size)
    cfg = deepcopy(row['config'])
    nodes = normalize_objects(objects if objects is not None else [{'type': 'text', 'text': brief}])
    input_prompt = objects_prompt(nodes)
    if not input_prompt.strip():
        raise ValueError('请填写修图要求；未填写的模板示例不会作为要求提交')
    if len(input_prompt) > 20000:
        raise ValueError('修图要求过长')
    # Both representations are saved. Never silently substitute stale editor
    # text for the user's current visible instruction.
    if objects is not None and input_prompt.strip() != brief.strip():
        raise ValueError('修图文本与输入节点不一致，请同步当前输入后重试')
    caps, available = _capability(image_capabilities)
    requested = need_optimize is True
    effective = requested and available
    protection = _constraints(preservation)
    policy = cfg.get('optimizePrompt') or cfg.get('systemPrompt') or ''
    if not isinstance(policy, str):
        raise ValueError('原始修图扩写策略必须是文本')
    bindings = {'customer_keywords': input_prompt, 'ListingUserSelectedSize': size}
    audit = {
        'strategyVersion': VERSION,
        'strategy': 'local_codex_reconstruction',
        'privateServerPromptKnown': False,
        'id': row.get('id'), 'name': row.get('name'),
        'rawConfig': cfg, 'entryValue': row.get('entryValue'),
        'entrySha256': row.get('entrySha256'),
        'userOriginal': brief, 'inputPrompt': input_prompt, 'objects': nodes,
        'templateObjects': template_objects(cfg.get('prompt', '')),
        'runtimeBindings': bindings, 'requestedSize': size,
        'templateRequestedOptimize': bool(cfg.get('needOptimize')),
        'requestedNeedOptimize': requested, 'effectiveNeedOptimize': effective,
        'builtinProviderExpansion': False, 'localTextExpansion': available,
        'capabilities': caps, 'preservation': protection,
        'optimizerPolicyOriginal': policy, 'optimizerPolicySha256': _digest(policy),
        'optimizerInput': None, 'optimizedPrompt': None,
        'optimizationAccepted': False,
        'executionProvider': 'Codex Tools',
        'optimizationReason': ('local_codex_text_optimizer' if effective else
                               'not_requested' if not requested else 'local_optimizer_capability_unverified'),
    }
    selected = input_prompt
    if effective:
        bound = policy
        for key, value in bindings.items():
            bound = bound.replace('{' + key + '}', value)
        # The full original policy is retained and used; these explicit limits
        # describe our independent compiler, not a recovered private prompt.
        limit = max(1200, min(6000, len(input_prompt) * 3))
        instruction = (
            'Compile one concise image-edit instruction. The supplied current input and source images '
            'are authoritative; source template examples are placeholders, not product facts. '
            'Do not add unsupported facts, visible text, colour changes or extra edits. '
            'If the current input is already clear, retain it with only essential clarifications. '
            'Return only the final instruction, without explanation or repeated rules. '
            f'Keep the answer within {limit} characters.\n'
            '[CURRENT INPUT]\n' + input_prompt + '\n[/CURRENT INPUT]\n'
            '[TYPED INPUT AND BINDINGS]\n' + json.dumps({'objects': nodes, 'bindings': bindings}, ensure_ascii=False)
            + '\n[/TYPED INPUT AND BINDINGS]\n'
            '[PRESERVATION]\n' + '\n'.join(item['text'] for item in protection)
            + '\n[/PRESERVATION]\n'
            '[FULL ORIGINAL TEMPLATE OPTIMIZATION POLICY]\n' + bound
            + '\n[/FULL ORIGINAL TEMPLATE OPTIMIZATION POLICY]\n'
            'Return the concise current-product instruction only. Do not copy example subjects or claims.'
        )
        audit['optimizerInput'] = instruction
        audit['optimizerInputSha256'] = _digest(instruction)
        answer = (optimizer or _codex_optimizer)(instruction, images)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError('修图扩写未返回完整文本，未提交图片生成')
        audit['optimizedPrompt'] = answer
        audit['optimizedPromptSha256'] = _digest(answer)
        # Never retry a paid response merely to shorten it. Retain its receipt
        # via visual_studio and the original output here, then use clear input.
        if len(answer.strip()) <= limit:
            selected = answer.strip()
            audit['optimizationAccepted'] = True
        else:
            audit['optimizationReason'] = 'verbose_output_retained_original_input'
    final = selected.rstrip() + '\n\n[Preservation]\n' + '\n'.join(item['text'] for item in protection)
    if size not in ('', 'auto'):
        final += '\nRequested aspect ratio: ' + size + '.'
    audit['compiledPrompt'] = final
    audit['compiledPromptSha256'] = _digest(final)
    audit['inputPromptSha256'] = _digest(input_prompt)
    return final, audit
