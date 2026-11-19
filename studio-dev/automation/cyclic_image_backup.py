"""Account for permanently unavailable supplier images without hiding failures."""


def partition_backups(records, exceptions=()):
    permitted = {x['url']: x for x in exceptions}
    downloaded, unavailable = [], []
    for record in records:
        if record['status'] == 'downloaded':
            downloaded.append(record)
            continue
        proof = permitted.pop(record['url'], None)
        if (not proof or not record.get('source', '').startswith('supplier_')
                or record.get('error') != 'Error: HTTP 404'
                or proof.get('http_status') != 404 or not proof.get('reason')
                or not proof.get('evidence_file')):
            raise ValueError('Image download incomplete; no confirmed supplier404 exception')
        unavailable.append({**record, **proof, 'productionApproved': False})
    if permitted:
        raise ValueError('Unused image exceptions; review the current manifest')
    return downloaded, unavailable
