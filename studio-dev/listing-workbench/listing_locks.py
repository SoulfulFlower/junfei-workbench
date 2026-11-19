"""Persisted protections for the original and translated Listing fields."""
FIELDS = ('title', 'highlights', 'bullets', 'description', 'terms')


def locked(copy):
    flags = copy.get('lockedFields', []) if isinstance(copy, dict) else []
    return tuple(field for field in FIELDS if isinstance(flags, list) and field in flags)


def translated(copy, field):
    translations = copy.get('translations')
    return translations.get(field, '') if isinstance(translations, dict) else ''


def merge(current, candidate):
    result = {key: value for key, value in candidate.items() if key != 'lockedFields'}
    fields = locked(current)
    if fields:
        result['lockedFields'] = list(fields)
        translations = result.get('translations')
        result['translations'] = dict(translations) if isinstance(translations, dict) else {}
        for field in fields:
            result[field] = current.get(field, '')
            result['translations'][field] = translated(current, field)
        result.pop('contentAudit', None)
        result['zh'] = ''
    return result


def validate_state(previous, next_state):
    copies = next_state['copy']
    for copy in copies.values():
        if not isinstance(copy, dict) or 'lockedFields' not in copy:
            continue
        flags = copy['lockedFields']
        if (not isinstance(flags, list) or any(field not in FIELDS for field in flags)
                or len(flags) != len(set(flags))):
            raise ValueError('Listing 锁定字段格式无效')
    ids = {p['id'] for p in next_state['products']}
    for key, original in previous.get('copy', {}).items():
        fields = locked(original)
        if not fields or key.rsplit('-', 1)[0] not in ids:
            continue
        updated = copies.get(key)
        if not isinstance(updated, dict) or any(
                original.get(field, '') != updated.get(field, '') or translated(original, field) != translated(updated, field)
                for field in fields):
            raise ValueError('已锁定字段不可修改。请先单独保存解锁，再编辑原文或翻译。')
