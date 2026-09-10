#!/usr/bin/env python3
"""Run inside dashboard after deploying proactive-reels image; idempotent API config."""
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import yaml


def api(path, method="GET", data=None):
    req = urllib.request.Request("http://127.0.0.1:8080/api"+path, method=method,
        headers={"Authorization": "Bearer "+os.environ["DASHBOARD_API_TOKEN"], "Content-Type": "application/json"},
        data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    root = Path('/workspace')
    backup = root / 'config/audits' / datetime.now(timezone.utc).strftime('proactive-%Y%m%dT%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    heartbeats = api('/heartbeats')
    (backup/'heartbeats.json').write_text(json.dumps(heartbeats), encoding='utf-8')
    routine_path = root/'config/routines.yaml'
    shutil.copy2(routine_path, backup/'routines.yaml')
    config = yaml.safe_load(routine_path.read_text())
    for bucket in ('daily', 'weekly'):
        for routine in config.get(bucket, []):
            if routine.get('script') in ('ai_news_daily_draft.py', 'ai_news_weekly_x_research.py'):
                routine['enabled'] = False
    temporary = routine_path.with_suffix('.yaml.tmp')
    temporary.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    temporary.replace(routine_path)
    goals = api('/goals')
    slug = 'reels-120-150-20260911'
    goal = next((g for g in goals if g['slug'] == slug), None)
    if goal is None:
        goal = api('/goals', 'POST', {'slug': slug, 'project_id': 3,
            'title': 'Publicar 120 Reels em 30 dias; meta estendida 150',
            'description': '11/09 a 10/10/2026 BRT: mínimo 4 Reels/dia. Magneto coproduz gancho visual/falado, headline, estrutura de linguagem e prompt OpenReply antes do post. Contagem apenas por media_id REELS confirmado em workspace/reports/reels/published.json; drafts e tickets não são publicações. Sem publicação ou disparo não autorizado.',
            'target_metric': 'Reels publicados únicos verificados', 'target_value': 120,
            'current_value': 0, 'due_date': '2026-10-10'})
    prompt = (f'Trabalhe somente no goal #{goal["id"]} (reels-120-150-20260911). '
        'Leia .claude/skills/social-reels-scripts/SKILL.md e references/coproducao-magneto.md. '
        'Consulte workspace/reports/reels/latest.json e a API Nexus usando EVONEXUS_API_URL e DASHBOARD_API_TOKEN. '
        'Ignore tickets de outros goals no inbox. Não modifique campanhas nem publique. '
        'Consulte os tickets deste goal antes de criar; evite duplicatas por data/slot. '
        'Se há menos de 8 roteiros aprovados/prontos, proponha no máximo 2 novos roteiros completos por execução '
        'com ID estável, evidência, 3 ganchos, estrutura de linguagem, CTA e prompt OpenReply. Salve em workspace/reports/reels/. '
        'Abra/atualize ticket de revisão para Felipe com caminho do material e pergunta concreta. '
        'Não espere 8 aprovações para reportar: informe ao Magneto os IDs e bloqueios. '
        'Não conte rascunhos como publicados nem complete a meta por tarefas concluídas. '
        'Encerre após os 2 pacotes ou quando a reserva for suficiente. Não explorar o workspace inteiro.')
    api('/heartbeats/pixel-growth-6h', 'PATCH', {'goal_id': str(goal['id']), 'decision_prompt': prompt,
        'timeout_seconds': 600, 'max_turns': 8, 'enabled': True})
    hb = {'id': 'reels-producer', 'agent': 'system', 'handler': 'reels_producer.tick',
          'interval_seconds': 1800, 'max_turns': 0, 'timeout_seconds': 60,
          'lock_timeout_seconds': 120, 'wake_triggers': ['interval', 'manual'],
          'enabled': False, 'goal_id': str(goal['id']), 'required_secrets': [],
          'decision_prompt': 'Monitor determinístico: evidência de publicação e brief Magneto; não publica.'}
    existing = {h['id'] for h in heartbeats['heartbeats']}
    if hb['id'] not in existing:
        api('/heartbeats', 'POST', hb)
    print(json.dumps({'goal_id': goal['id'], 'backup': str(backup), 'monitor': 'created disabled; manual test before enabling'}))


if __name__ == '__main__':
    main()
