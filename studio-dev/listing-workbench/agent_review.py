"""Content-bound agent review for drafts, separate from human approval.

Records are attestations from an actual reviewer, not automatic quality scores.
Any product edit invalidates them. Account job ownership is checked separately
by generated_gallery.selected before these records can approve image handles.
"""
import hashlib
import json
from datetime import datetime
import app_paths

COPY_CHECKS = ('factsMatch', 'noUnsupportedClaims', 'noUnauthorizedMarks', 'keywordRelevance')
IMAGE_CHECKS = ('appearanceMatchesSource', 'dimensionsTextMatch', 'noUnauthorizedMarks', 'noUnsupportedClaims', 'visualQuality')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def product_digest(product):
    return digest({k:v for k,v in product.items() if k != 'agentDraftReview'})


def current(product):
    record = product.get('agentDraftReview')
    if not isinstance(record, dict): return None
    owner = app_paths.WORKER_USER
    if not owner:
        import account_spaces
        owner = account_spaces.legacy_owner()
    if (record.get('version') != 1 or record.get('scope') != 'draft_only'
            or type(record.get('accountId')) is not int or record['accountId'] != owner
            or record.get('reviewerType') != 'agent' or not record.get('reviewer')
            or not record.get('evidence') or record.get('productSha256') != product_digest(product)):
        return None
    try:
        date = datetime.fromisoformat(record['reviewedAt'].replace('Z', '+00:00'))
        if date.tzinfo is None: return None
    except (KeyError, ValueError, TypeError): return None
    return record


def copy_approved(product, listing):
    record = current(product)
    copy = record.get('copy', {}) if record else {}
    return (copy.get('sha256') == digest(listing)
        and all(copy.get('checks', {}).get(k) is True for k in COPY_CHECKS))


def gallery_approved(product, rows):
    record = current(product)
    reviewed = record.get('images', []) if record else []
    if not rows or len(reviewed) != len(rows): return False
    for slot, ((selection, job, index), item) in enumerate(zip(rows, reviewed)):
        if not isinstance(item, dict): return False
        sha = selection.get('sha256')
        if (not isinstance(sha, str) or len(sha) != 64
                or any(c not in '0123456789abcdef' for c in sha)
                or (item.get('slot'),item.get('jobId'),item.get('imageIndex'),item.get('sourceSha256'))
                    != (slot, job['id'], index, sha)
                or not all(item.get('checks', {}).get(k) is True for k in IMAGE_CHECKS)):
            return False
    return True


def studio_gallery_approved(product, project_id, runs, hashes):
    """Allow content-reviewed native finals as draft masters, without human flags."""
    record = current(product)
    reviewed = record.get('studioImages', []) if record else []
    if not runs or len(reviewed) != len(runs) or len(hashes) != len(runs): return False
    for slot, (run, sha, item) in enumerate(zip(runs, hashes, reviewed)):
        qc = (run.get('qc') or [])[-1:]
        qc = qc[0] if qc else {}
        if (not isinstance(item, dict) or not isinstance(sha, str) or len(sha) != 64
                or any(c not in '0123456789abcdef' for c in sha)
                or run.get('productId') != product.get('id') or run.get('projectId') != project_id
                or run.get('slot') != slot or run.get('status') not in ('approved', 'awaiting_manual')
                or qc.get('pass') is not True or qc.get('issues')
                or qc.get('technical', {}).get('sha256') != sha
                or (item.get('slot'), item.get('runId'), item.get('projectId'), item.get('sourceSha256'))
                    != (slot, run.get('id'), project_id, sha)
                or not all(item.get('checks', {}).get(k) is True for k in IMAGE_CHECKS)):
            return False
    return True
