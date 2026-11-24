"""Owner-scoped read-only assessment of local guarded family capture receipts."""
import cyclic_discovery as ledger
import discovery_family


def assess(user, data):
    import discovery_plan
    ledger._owner(user)
    if not isinstance(data, dict) or set(data) != {'cycleId', 'expectedRevision'}:
        raise ValueError('Expected cycleId and expectedRevision only')
    cycle = ledger._id(data['cycleId'], 'cycleId')
    if type(data['expectedRevision']) is not int or data['expectedRevision'] < 0:
        raise ValueError('Invalid expectedRevision')
    graph = ledger.report(user, cycle)
    if graph['revision'] != data['expectedRevision']:
        raise ValueError('stale_revision')
    receipts, history_fingerprint, blockers = discovery_plan._attempts(user)
    family_receipts = [r for r in receipts if r.get('captureKind') == 'family' and r.get('status') == 'captured' and r.get('cycleId') == cycle]
    assessment = discovery_family.assess_recorded(graph, family_receipts)
    # Recheck both immutable event snapshot and receipt snapshot before returning.
    # This is an assessment, not a dispatch lock or execution authorization.
    latest = ledger.report(user, cycle)
    _, latest_history, latest_blockers = discovery_plan._attempts(user)
    if latest != graph or latest_history != history_fingerprint or latest_blockers != blockers:
        raise ValueError('assessment_scope_changed')
    return {'schemaVersion': 1, 'readOnly': True, 'owner': user,
            'cycleId': cycle, 'revision': graph['revision'],
            'executionAllowed': False, 'qualificationEvaluated': False,
            'qualifiedCount': 0, 'importedCount': 0, 'externalCallsPerformed': 0,
            'historyFingerprint': history_fingerprint, 'blockers': blockers,
            'assessment': assessment}
