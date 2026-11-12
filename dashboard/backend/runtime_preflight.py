"""Read-only runtime capability context. Never returns credential values."""
from __future__ import annotations

import os
import sys
import importlib.util
import shutil
import sqlite3
from pathlib import Path


def runtime_preflight(root: Path, *, env=None, conn=None) -> str:
    env = os.environ if env is None else env
    # Mirror sdk_client.EvoClient: an omitted URL uses localhost/FLASK_PORT.
    # Missing override is not missing authentication or evidence of a failure.
    api = bool(env.get('DASHBOARD_API_TOKEN', '').strip())
    custom_api = bool(env.get('EVONEXUS_API_URL', '').strip())
    # reels_copilot._openreply_pg_connect supplies host/user/db defaults.
    pg = bool(env.get('OPENREPLY_DATABASE_URL', '').strip() or env.get('OPENREPLY_PG_PASSWORD', ''))
    try:
        pg_driver = importlib.util.find_spec('psycopg2') is not None
    except (ImportError, ValueError):
        pg_driver = False
    lines = [
        '## Preflight de capacidades (configuração, não autorização nem prova de conectividade)',
        f'Nexus API configurada: {api}. Use sdk_client.evo; não consulte SQLite local de outro container.',
        f'Endpoint customizado da API: {custom_api}; sem override o sdk_client usa localhost/FLASK_PORT. Isso não prova acesso entre containers.',
        f'Python deste runtime: {sys.executable}; use o mesmo interpretador nas sondagens. python3 do sistema não comprova dependência ausente no venv.',
        f'OpenReply Postgres direto configurado: {pg}. psycopg2 neste runtime: {pg_driver}. SSH disponível: {bool(shutil.which("ssh"))}.',
        'Quando Postgres direto estiver configurado, use psycopg2 com OPENREPLY_DATABASE_URL ou OPENREPLY_PG_* do ambiente, sem imprimir valores. SQL e validação seguem a skill custom-int-openreply.',
        'Exemplos legados de SSH/docker/psql não são pré-requisitos no container com conexão direta. Não peça credencial já configurada; confira o erro concreto usando leitura antes de escalar.',
        'Sonde OpenReply com SELECT 1 em transação read-only antes de alegar falta de acesso; não ative campanha, DM ou link público apenas porque há credencial. Campanha com a mesma keyword não prova que o destino/material pedido já existe.',
        'Preserve os gates humanos e o escopo autorizado; configuração presente não autoriza publicação ou novas permissões.',
        'Antes de alegar agente offline, consulte GET /api/heartbeats e procure por agent (não só id). Success com duração zero pode ser skip.',
        'Antes de alegar arquivo/repositório ausente, leia comentários anteriores e caminhos de artefatos; registre o caminho realmente procurado. Código no computador do usuário não implica checkout disponível neste container.',
    ]
    if conn is not None:
        try:
            rows = conn.execute('SELECT agent, id FROM heartbeats WHERE enabled=1 ORDER BY agent,id').fetchall()
            lines.append('Heartbeats habilitados agora: ' + ', '.join(f'{r[0]} ({r[1]})' for r in rows))
        except sqlite3.Error:
            lines.append('Inventário local de heartbeats indisponível; confirme pela API antes de afirmar ausência.')
    skills = Path(root) / '.claude' / 'skills'
    relevant = ('custom-int-openreply', 'social-reels-scripts', 'create-goal')
    found = [f'.claude/skills/{n}/SKILL.md' for n in relevant if (skills / n / 'SKILL.md').is_file()]
    if found:
        lines.append('Skills locais relevantes (leia o SKILL.md antes de usar): ' + ', '.join(found))
    return '\n'.join(lines)
