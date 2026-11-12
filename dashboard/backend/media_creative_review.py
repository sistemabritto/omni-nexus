"""Pure contract for a claimed audiovisual review, never an aesthetic judge.

The caller must verify local evidence files/digests/duration, derive the reviewer
from the authenticated session, enforce independence and persist atomically.
This validates structure and the expected render binding only; it does not
watch a video, grant approval, invoke a model or authorize publication.
"""
from __future__ import annotations

import math
from pathlib import PurePosixPath
import re

CRITERIA = ('identity', 'legibility', 'composition', 'rhythm', 'transitions', 'captions', 'audio')
METHODS = {
    'anti_slop': ('.claude/skills/design-quality/SKILL.md', 'b1cdf87d49b1653293d58424516fd80394008345'),
    'taste': ('.claude/skills/dev-team-methods/design-critique.md', 'f624f37a8c650b9cc550253104925efe4c8de246'),
}
_HEX = re.compile(r'[0-9a-f]{64}')


def _object(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{label}: expected fields {sorted(keys)}')
    return value


def _text(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{label}: nonempty bounded text required')
    return value.strip()


def _hash(value):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError('sha256: lowercase 64-character digest required')
    return value


def _number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'{label}: finite nonnegative seconds required') from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(number) or number < 0:
        raise ValueError(f'{label}: finite nonnegative seconds required')
    return number


def _evidence(value, duration):
    if not isinstance(value, list) or len(value) > 80:
        raise ValueError('evidence: bounded list required')
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('evidence: object required')
        kind = item.get('kind')
        if kind not in ('frame', 'time_range', 'audio_range', 'artifact'):
            raise ValueError('evidence: unsupported kind')
        temporal = kind in ('time_range', 'audio_range')
        _object(item, {'kind', 'ref', 'sha256'} | ({'start', 'end'} if temporal else set()), 'evidence')
        relative = _text(item['ref'], 'evidence.ref', 500)
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in ('', '.', '..') for part in relative.split('/')) or any(ord(char) < 32 for char in relative) or '\\' in relative or ':' in relative:
            raise ValueError('evidence.ref: local relative path required')
        row = {'kind': kind, 'ref': relative, 'sha256': _hash(item['sha256'])}
        if temporal:
            start, end = _number(item['start'], 'start'), _number(item['end'], 'end')
            if not start < end <= duration:
                raise ValueError('evidence: range outside reviewed duration')
            row.update(start=start, end=end)
        result.append(row)
    return result


def validate_creative_review(payload, *, render_sha256, version_id):
    """Normalize evidence assertions; reject stale render/version and unknown fields.

    No client reviewer/approval field is accepted. Nonpassing reviews remain
    recordable with findings, but are ineligible for the human approval gate.
    """
    keys = {'render_sha256', 'version_id', 'duration_seconds', 'brand_reference', 'methods', 'criteria', 'findings'}
    data = _object(payload, keys, 'review')
    if _hash(data['render_sha256']) != _hash(render_sha256):
        raise ValueError('review: render hash mismatch')
    expected_version = _text(version_id, 'expected version_id', 200)
    if _text(data['version_id'], 'version_id', 200) != expected_version:
        raise ValueError('review: version mismatch')
    duration = _number(data['duration_seconds'], 'duration_seconds')
    if duration <= 0:
        raise ValueError('duration_seconds: positive duration required')
    brand = _object(data['brand_reference'], ('source', 'version'), 'brand_reference')
    brand = {key: _text(value, 'brand.' + key, 500) for key, value in brand.items()}
    methods = _object(data['methods'], METHODS, 'methods')
    normalized_methods = {}
    for name, (source, version) in METHODS.items():
        method = _object(methods[name], ('source', 'version', 'application'), name)
        if method['source'] != source or method['version'] != version:
            raise ValueError(f'{name}: expected locally adapted source and pinned upstream version')
        normalized_methods[name] = {**method, 'application': _text(method['application'], name + '.application')}
    criteria = _object(data['criteria'], CRITERIA, 'criteria')
    normalized = {}
    for name in CRITERIA:
        row = _object(criteria[name], ('status', 'observation', 'evidence', 'reason'), name)
        if row['status'] not in ('PASS', 'FAIL', 'NOT_TESTED', 'NOT_APPLICABLE'):
            raise ValueError(name + ': invalid status')
        evidence = _evidence(row['evidence'], duration)
        if row['status'] in ('PASS', 'FAIL') and not evidence:
            raise ValueError(name + ': observed verdict requires evidence')
        reason = row['reason']
        if not isinstance(reason, str) or len(reason) > 4000:
            raise ValueError(name + ': invalid reason')
        if row['status'] in ('NOT_TESTED', 'NOT_APPLICABLE'):
            reason = _text(reason, name + '.reason')
        normalized[name] = {'status': row['status'], 'observation': _text(row['observation'], name + '.observation'),
                            'evidence': evidence, 'reason': reason.strip()}
    if not isinstance(data['findings'], list) or len(data['findings']) > 100:
        raise ValueError('findings: bounded list required')
    findings, ids = [], set()
    for item in data['findings']:
        _object(item, ('id', 'criterion', 'severity', 'status', 'description', 'resolution', 'evidence'), 'finding')
        identifier = _text(item['id'], 'finding.id', 100)
        if identifier in ids or item['criterion'] not in CRITERIA or item['severity'] not in ('P0', 'P1', 'P2') or item['status'] not in ('open', 'resolved'):
            raise ValueError('finding: invalid identity, criterion, severity or status')
        ids.add(identifier)
        evidence = _evidence(item['evidence'], duration)
        resolution = item['resolution']
        if not isinstance(resolution, str) or len(resolution) > 4000:
            raise ValueError('finding: invalid resolution')
        if item['status'] == 'resolved' and (not resolution.strip() or not evidence):
            raise ValueError('finding: resolution requires retest evidence')
        findings.append({**item, 'id': identifier, 'description': _text(item['description'], 'finding.description'),
                         'resolution': resolution.strip(), 'evidence': evidence})
    return {'render_sha256': render_sha256, 'version_id': expected_version,
            'duration_seconds': duration, 'brand_reference': brand, 'methods': normalized_methods,
            'criteria': normalized, 'findings': findings}


def creative_review_eligible(normalized):
    """Eligibility is not approval. The caller must still enforce its human gate."""
    try:
        data = validate_creative_review(normalized, render_sha256=normalized['render_sha256'], version_id=normalized['version_id'])
    except (KeyError, TypeError, ValueError):
        return False
    if data['criteria']['identity']['status'] != 'PASS':
        return False
    if any(row['status'] not in ('PASS', 'NOT_APPLICABLE') for row in data['criteria'].values()):
        return False
    return not any(row['status'] == 'open' and row['severity'] in ('P0', 'P1') for row in data['findings'])
