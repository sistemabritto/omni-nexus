"""Additive squad metadata and read-only evidence; never dispatches agents/tools."""
from pathlib import Path
import re
from squad_delivery_contract import agent_delivery_roles
from squad_operating_profiles import operating_profile

# Presentation sectors do not replace ACLs, ownership, commands or business/dev layers.
SECTORS = {
    'coordination': ('Coordenação e estratégia', [
        ('oracle', 'Oracle', 'Descoberta do negócio e contexto de conhecimento'),
        ('clawdia-assistant', 'Clawdia', 'Fila operacional, contexto e encaminhamento'),
        ('helm-conductor', 'Helm', 'Coordenação do ciclo de engenharia'),
        ('sage-strategy', 'Sage', 'Estratégia e prioridades de negócio'),
        ('mirror-retro', 'Mirror', 'Retrospectiva e aprendizado do processo'),
    ]),
    'projects': ('Produto e projetos', [
        ('atlas-project', 'Atlas', 'Acompanhamento de projetos e bloqueios'),
        ('nova-product', 'Nova', 'Requisitos e decisões de produto'),
        ('project-planner', 'Planejador de projetos', 'Transformar contexto em plano de projeto'),
        ('goal-suggester', 'Sugestor de objetivos', 'Propor objetivos para revisão'),
        ('goal-planner', 'Planejador de objetivos', 'Decompor objetivos em trabalho verificável'),
        ('compass-planner', 'Compass', 'Plano técnico e interfaces da implementação'),
        ('echo-analyst', 'Echo', 'Lacunas e critérios dos requisitos'),
        ('raven-critic', 'Raven', 'Crítica de riscos e coerência de planos'),
    ]),
    'growth': ('Marketing, criação e relacionamento', [
        ('mako-marketing', 'Mako', 'Pesquisa competitiva, posicionamento e campanhas'),
        ('pixel-social-media', 'Pixel', 'Conteúdo social e adaptação por canal'),
        ('reels-copilot', 'Coprodutor de Reels', 'Um roteiro por rodada no fluxo de revisão'),
        ('canvas-designer', 'Canvas', 'Design de interfaces e direção visual'),
        ('nex-sales', 'Nex', 'Qualificação, pipeline e próxima ação comercial'),
        ('pulse-community', 'Pulse', 'Comunidade e relacionamento coletivo'),
        ('zara-cs', 'Zara', 'Sucesso do cliente e tratamento de demandas'),
    ]),
    'data': ('Dados e pesquisa', [
        ('dex-data', 'Dex', 'Métricas, qualidade de dados e reconciliação'),
        ('prism-scientist', 'Prism', 'Análise científica e hipóteses estatísticas'),
        ('scout-explorer', 'Scout', 'Exploração de código e localização de evidências'),
        ('scroll-docs', 'Scroll', 'Pesquisa em documentação técnica'),
        ('quill-writer', 'Quill', 'Documentação técnica com exemplos verificáveis'),
    ]),
    'engineering': ('Engenharia e manutenção', [
        ('apex-architect', 'Apex', 'Arquitetura e decisões técnicas'),
        ('bolt-executor', 'Bolt', 'Implementação de mudanças delimitadas'),
        ('hawk-debugger', 'Hawk', 'Reprodução e correção de bugs'),
        ('trail-tracer', 'Trail', 'Rastreamento causal entre componentes'),
        ('zen-simplifier', 'Zen', 'Simplificação de código no escopo pedido'),
        ('flow-git', 'Flow', 'Histórico Git e organização de alterações'),
    ]),
    'quality': ('Qualidade e segurança', [
        ('lens-reviewer', 'Lens', 'Revisão de código: especificação e qualidade'),
        ('oath-verifier', 'Oath', 'Verificação independente com evidência'),
        ('grid-tester', 'Grid', 'Estratégia e implementação de testes'),
        ('probe-qa', 'Probe', 'QA interativo e diagnóstico de falhas de uso'),
        ('vault-security', 'Vault', 'Revisão de segurança e fronteiras de confiança'),
    ]),
    'operations': ('Administração e desenvolvimento humano', [
        ('flux-finance', 'Flux', 'Operação financeira e relatórios'),
        ('lex-legal', 'Lex', 'Análise jurídica e revisão de conformidade'),
        ('aria-hr', 'Aria', 'Pessoas e processos de RH'),
        ('kai-personal-assistant', 'Kai', 'Organização pessoal no domínio isolado'),
        ('mentor-courses', 'Mentor', 'Cursos e percursos de aprendizagem'),
        ('lumen-learning', 'Lumen', 'Retenção e revisão do aprendizado'),
    ]),
}
NATIVE_CATALOG = {
    slug: {'display_name': name, 'function': role, 'sector_id': sector, 'sector': label}
    for sector, (label, members) in SECTORS.items()
    for slug, name, role in members
}

# Approved display aliases only. Persona filenames, commands and owners stay stable.
DISPLAY_NAMES = {
    'clawdia-assistant': 'Hera', 'mako-marketing': 'Orion',
    'pixel-social-media': 'Dante', 'canvas-designer': 'Íris',
    'bolt-executor': 'Vulcano', 'oath-verifier': 'Argos',
}
for _slug, _display_name in DISPLAY_NAMES.items():
    NATIVE_CATALOG[_slug]['display_name'] = _display_name

# Audited textual modules proposed in earlier work. Presence is checked, not assumed.
EXPECTED_KNOWLEDGE = {
    'mako-marketing': ['mkt-creative-brief', 'mkt-research-pipeline', 'dev-team-methods'],
    'pixel-social-media': ['mkt-creative-brief', 'mkt-research-pipeline', 'social-reels-editorial', 'video-editorial-pipeline'],
    'canvas-designer': ['logo-design', 'mkt-creative-brief', 'design-quality', 'dev-team-methods'],
    'reels-copilot': ['social-reels-editorial'],
    'nex-sales': ['mkt-research-pipeline', 'dev-team-methods'],
    'dex-data': ['mkt-research-pipeline', 'dev-team-methods'],
    'oath-verifier': ['design-quality', 'mkt-research-pipeline', 'dev-team-methods'],
}
_PATH = re.compile(r'\.claude/(skills(?:-media)?)/([a-z0-9][a-z0-9-]*)/SKILL\.md')
_DOCUMENT_PATH = re.compile(
    r'\.claude/skills(?:-media)?/[a-z0-9][a-z0-9-]*/'
    r'(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+\.md\b'
)


def reference_documents(source: str, workspace: Path) -> list[dict]:
    """Explicit read pointers in the bounded persona, not model/tool execution.

    Keep subdocuments separate from the strict root-SKILL detector. In
    particular, design-critique.md does not imply SKILL.md was requested.
    Symlinks escaping the workspace are not evidence of a readable document.
    """
    root = workspace.resolve()
    documents = []
    for relative in sorted(set(_DOCUMENT_PATH.findall(_runtime_body(source)))):
        path = root / relative
        try:
            within_workspace = path.resolve().is_relative_to(root)
        except (OSError, RuntimeError):
            within_workspace = False
        documents.append({
            'path': relative,
            'kind': 'skill_root' if path.name == 'SKILL.md' else 'reference_document',
            'document_present': within_workspace and path.is_file(),
            'read_instruction_in_persona': True,
            'model_read_status': 'not_verified',
            'operational_status': 'not_verified',
        })
    return documents


def _runtime_body(source: str) -> str:
    """Match the existing persona loader's frontmatter/memory boundaries."""
    if source.startswith('---'):
        parts = source.split('---', 2)
        if len(parts) == 3:
            source = parts[2]
    for marker in ('\n# Persistent Agent Memory', '\n## MEMORY.md'):
        source = source.split(marker, 1)[0]
    return source.strip()


def catalog_entry(name: str, source: str, workspace: Path) -> dict:
    entry = dict(NATIVE_CATALOG.get(name, {
        'display_name': name, 'function': 'Função definida na persona existente',
        'sector_id': 'custom', 'sector': 'Personalizados e plugins',
    }))
    entry['delivery_roles'] = agent_delivery_roles(name)
    entry['delivery_profile'] = operating_profile(name)
    primary = next((r for r in entry['delivery_roles'] if r['role'] == 'responsible'), None)
    entry['display_label'] = (primary['label'] + ' · ' if primary else '') + entry['display_name']
    body = _runtime_body(source)
    referenced = {(layer, slug) for layer, slug in _PATH.findall(body)}
    candidates = referenced | {('skills', slug) for slug in EXPECTED_KNOWLEDGE.get(name, [])}
    entry['knowledge'] = [
        {'name': slug, 'path': f'.claude/{layer}/{slug}/SKILL.md',
         'document_present': (workspace / '.claude' / layer / slug / 'SKILL.md').is_file(),
         'persona_reference': (layer, slug) in referenced,
         'operational_status': 'not_verified'}
        for layer, slug in sorted(candidates)
    ]
    entry['evidence_scope'] = 'files_and_explicit_persona_paths_only'
    entry['reference_documents'] = reference_documents(source, workspace)
    # reels_copilot.generate_reel uses agent="" in this base: persona alone is insufficient.
    entry['execution_note'] = (
        'Handler in-process: referência na persona não comprova inclusão no prompt de geração.'
        if name == 'reels-copilot' else
        'Referência carregável não comprova leitura pelo modelo nem execução de ferramenta.'
    )
    return entry
