"""Read-only runtime capability context. Never returns credential values."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path


def runtime_preflight(root: Path, *, env=None, conn=None) -> str:
    env = os.environ if env is None else env
    api = bool(env.get('EVONEXUS_API_URL') and env.get('DASHBOARD_API_TOKEN'))
    pg = bool(env.get('OPENREPLY_DATABASE_URL') or all(env.get(k) for k in (
        'OPENREPLY_PG_HOST', 'OPENREPLY_PG_USER', 'OPENREPLY_PG_PASSWORD', 'OPENREPLY_PG_DB')))
    lines = [
        '## Preflight de capacidades (configuração, não autorização nem prova de conectividade)',
        f'Nexus API configurada: {api}. Use sdk_client.evo; não consulte SQLite local de outro container.',
        f'OpenReply Postgres direto configurado: {pg}. SSH disponível: {bool(shutil.which("ssh"))}.',
        'Quando Postgres direto estiver configurado, use psycopg2 com OPENREPLY_DATABASE_URL ou OPENREPLY_PG_* do ambiente, sem imprimir valores. SQL e validação seguem a skill custom-int-openreply.',
        'Exemplos legados de SSH/docker/psql não são pré-requisitos no container com conexão direta. Não peça credencial já configurada; confira o erro concreto usando leitura antes de escalar.',
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
