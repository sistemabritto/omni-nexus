"""Executable handoff contract. No dispatch, grants, ownership writes or approval."""
import re
from pathlib import Path
from squad_work_policy import work_policy

# Compatibility v1 candidate suggestions, never a fixed staffing/dispatch matrix.
FRONTS = {
    'operations': ('Operação', 'clawdia-assistant', 'atlas-project', 'oath-verifier'),
    'strategy': ('Estratégia', 'mako-marketing', 'sage-strategy', 'raven-critic'),
    'editorial': ('Conteúdo', 'pixel-social-media', 'mako-marketing', 'oath-verifier'),
    'visual': ('Direção visual', 'canvas-designer', 'bolt-executor', 'oath-verifier'),
    'engineering': ('Engenharia', 'bolt-executor', 'hawk-debugger', 'lens-reviewer'),
    'quality': ('Qualidade', 'oath-verifier', 'probe-qa', 'raven-critic'),
}
# Required local methods, not proof of installed plugins or working provider access.
METHODS = {
    'operations': ['.claude/skills/dev-team-methods/handoff.md'],
    'strategy': ['.claude/skills/mkt-creative-brief/SKILL.md'],
    'editorial': ['.claude/skills/video-editorial-pipeline/SKILL.md'],
    'visual': ['.claude/skills/design-quality/video-review.md'],
    'engineering': ['.claude/skills/dev-team-methods/handoff.md'],
    'quality': ['.claude/skills/design-quality/review.md'],
}
_SHA = re.compile(r'[a-f0-9]{64}')


def agent_delivery_roles(slug):
    return [dict(front=front, label=label, role=role,
                 responsible=owner, assistant=assistant, reviewer=reviewer,
                 methods=list(METHODS[front]), assignment="legacy_suggestion_not_assigned",
                 quality_coordinator="oath-verifier")
            for front, (label, owner, assistant, reviewer) in FRONTS.items()
            for role, actor in [('responsible', owner), ('assistant', assistant), ('reviewer', reviewer)]
            if actor == slug]


def _text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 2000


def validate_handoff(data):
    """Validate a candidate, never certify observations or accept a handoff.

    Caller separately validates company/persona ACL and local method availability.
    Client-declared evidence/tool states remain unverified. Existing owner is
    preserved even for a complete candidate; actual recipient ack is out of scope.
    """
    fields = {'companyId', 'front', 'taskId', 'currentOwner', 'version', 'objective',
              'limits', 'inputs', 'output', 'acceptance', 'evidence', 'dependencies',
              'nextAction', 'contributors', 'criticality', 'tools'}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('invalid_fields')
    if type(data['companyId']) is not int or data['companyId'] <= 0:
        raise ValueError('invalid_company')
    if not isinstance(data['front'], str) or data['front'] not in FRONTS:
        raise ValueError('unknown_front')
    for name in ('taskId', 'currentOwner', 'version', 'objective', 'limits', 'output', 'nextAction'):
        if not _text(data[name]):
            raise ValueError('invalid_' + name)
    if data['criticality'] not in ('P0', 'P1', 'P2'):
        raise ValueError('invalid_criticality')
    label, owner, assistant, reviewer = FRONTS[data['front']]
    for name in ('inputs', 'acceptance', 'contributors'):
        if not isinstance(data[name], list) or not 1 <= len(data[name]) <= 30 or not all(_text(v) for v in data[name]):
            raise ValueError('invalid_' + name)
    if reviewer in data['contributors'] or reviewer == data['currentOwner']:
        raise ValueError('reviewer_contributed')
    if not isinstance(data['dependencies'], list) or len(data['dependencies']) > 30 or not all(_text(v) for v in data['dependencies']):
        raise ValueError('invalid_dependencies')
    if not isinstance(data['evidence'], list) or not 1 <= len(data['evidence']) <= 30:
        raise ValueError('invalid_evidence')
    for row in data['evidence']:
        if not isinstance(row, dict) or set(row) != {'ref', 'sha256', 'version'} or not _text(row['ref']) or row['version'] != data['version'] or not isinstance(row['sha256'], str) or not _SHA.fullmatch(row['sha256']):
            raise ValueError('invalid_evidence_binding')
    if not isinstance(data['tools'], list) or not 1 <= len(data['tools']) <= 30:
        raise ValueError('invalid_tools')
    blockers = list(data['dependencies'])
    for tool in data['tools']:
        if not isinstance(tool, dict) or set(tool) != {'name', 'state', 'evidenceRef'} or not _text(tool['name']) or not _text(tool['evidenceRef']) or tool['state'] not in ('available', 'unavailable', 'not_verified'):
            raise ValueError('invalid_tool')
        if tool['state'] != 'available':
            blockers.append('tool:' + tool['name'] + ':' + tool['state'])
    return {'front': data['front'], 'label': label, 'responsible': owner,
            'assistant': assistant, 'reviewer': reviewer, 'currentOwner': data['currentOwner'],
            'proposedRecipient': owner, 'ownershipChanged': False,
            'status': 'blocked' if blockers else 'candidate_complete',
            'blockers': blockers, 'criticality': data['criticality'],
            'acceptance': list(data['acceptance']), 'requiredMethods': list(METHODS[data['front']]),
            'acknowledgement': 'not_recorded', 'evidenceStatus': 'declared_not_verified',
            'dispatchAllowed': False, 'publicationApproved': False,
            'assignmentStatus': 'legacy_suggestion_not_assigned',
            'workPolicy': work_policy(data['front'])}


def unavailable_methods(workspace, references):
    """Only readable, bounded local method text counts as packaged availability."""
    root = Path(workspace).resolve()
    unavailable = []
    for reference in references:
        try:
            path = (root / reference).resolve(strict=True)
            path.relative_to(root)
            if not path.is_file() or not 0 < path.stat().st_size <= 262144:
                raise ValueError('invalid_method')
            if not path.read_text(encoding='utf-8').strip():
                raise ValueError('empty_method')
        except (OSError, RuntimeError, ValueError, UnicodeError):
            unavailable.append(reference)
    return unavailable

