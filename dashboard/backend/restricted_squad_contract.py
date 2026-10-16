"""Controller-owned editorial assignment gate for the single no-tools pilot.

This is not a queue dispatcher, grant or independent review implementation.
"""
import hashlib
from pathlib import Path
from squad_delivery_contract import FRONTS, METHODS, unavailable_methods, validate_handoff

VERSION = 'restricted-editorial-squad-v1'
ACTORS = ('pixel-social-media', 'mako-marketing', 'oath-verifier')
ROOT = Path(__file__).resolve().parents[2]


def preflight_contract(agent, *, workspace=None):
    """Resolve approved stable roles/methods before any inference. No network/DB."""
    root = Path(workspace) if workspace is not None else ROOT
    front = FRONTS.get('editorial')
    if not front or tuple(front[1:]) != ACTORS or agent != ACTORS[0]:
        raise ValueError('restricted_squad_role_mismatch')
    refs = [f'.claude/agents/{actor}.md' for actor in ACTORS]
    refs += list(METHODS['editorial'])
    refs += ['.claude/skills/dev-team-methods/handoff.md',
             '.claude/skills/design-quality/review.md']
    if unavailable_methods(root, refs):
        raise ValueError('restricted_squad_method_unavailable')
    hashes = {ref: hashlib.sha256((root / ref).read_bytes()).hexdigest() for ref in refs}
    return {'version': VERSION, 'front': 'editorial',
            'responsible': ACTORS[0], 'assistant': ACTORS[1], 'reviewer': ACTORS[2],
            'capability': 'internal_hypothetical_text', 'tool_policy': 'no_tools',
            'providerAvailability': 'not_probed', 'reviewStatus': 'required_not_started',
            'methodHashes': hashes, 'ownershipChanged': False,
            'publicationApproved': False}


def artifact_handoff(contract, *, ticket_id, run_id, artifact, sha256):
    """Bind the controlled artifact to a review candidate, never accept its content."""
    if (contract.get('version') != VERSION or contract.get('tool_policy') != 'no_tools'
            or tuple(contract.get(key) for key in ('responsible', 'assistant', 'reviewer')) != ACTORS):
        raise ValueError('restricted_squad_role_mismatch')
    result = validate_handoff(dict(companyId=1, front='editorial', taskId=ticket_id,
        currentOwner=ACTORS[0], version=run_id,
        objective='Rascunho interno integralmente hipotético sobre medição de chatbot',
        limits='Sem ferramentas, dados reais, publicação, mensagens ou aprovação automática',
        inputs=['Brief hipotético fixo do controlador'], output=artifact,
        acceptance=['Rótulo hipotético literal obrigatório',
                    'Período, população e denominadores explícitos',
                    'Resolução, retrabalho, custo e cálculos conferíveis',
                    'Não tratar três pageviews como tema vencedor',
                    'Revisão independente do conteúdo antes de qualquer aceite'],
        evidence=[dict(ref=artifact, sha256=sha256, version=run_id)], dependencies=[],
        nextAction='Oath verifica o arquivo e seus cálculos; Felipe decide o aceite',
        contributors=[ACTORS[0]], criticality='P1',
        tools=[dict(name='controller_no_tools_text', state='available',
                    evidenceRef='controller:internal-draft:' + run_id)]))
    if result['status'] != 'candidate_complete' or result['reviewer'] != ACTORS[2]:
        raise ValueError('restricted_squad_handoff_invalid')
    return {**result, 'contractVersion': VERSION, 'artifactSha256': sha256,
            'reviewStatus': 'pending_independent_review',
            'providerAccessBeforeCall': 'not_probed',
            'capabilityUsed': 'no_tools_text_only', 'semanticAcceptance': 'not_verified'}
