# AGENT.md — EvoNexus

## Start Here
- Workspace de orquestração da Sistema Britto (Felipe). Responde sempre em pt-BR.
- Fluxo do workspace: definir meta → quebrar em problemas → resolver → entregar.
- Leia `CLAUDE.md` na raiz para contexto persistente (projetos, agentes, skills, memória).
- Leia `.claude/rules/` para configuração detalhada (esteira-de-conteudo.md e esteira-de-video.md são obrigatórios antes de tocar em capa/CTA/texto ou corte/enquadramento/vídeo).

## Purpose & Context
EvoNexus é o hub de automação da Sistema Britto: orquestra agentes, skills, rotinas (ADWs), heartbeats, integrações (Stripe, Omie, Ghost, Evolution API, Fathom, etc.) e o dashboard Nexus. Artefatos finais (relatórios, dashboards) vão para o Nexus (`/shares`), não para fora.

## Architecture / Design
- **Dashboard backend**: `dashboard/backend/` (Flask). Rotas em `dashboard/backend/routes/`. Banco SQLite em `/workspace/dashboard/data/evonexus.db`.
- **Shares (Nexus)**: `dashboard/backend/routes/shares.py`. Token em `file_shares` (SQLite) aponta para um **caminho fixo** relativo a `REPO_ROOT` (`/workspace`). O endpoint `/api/shares/<token>/view` serve SEMPRE o arquivo naquele caminho. Para "trocar o conteúdo de um link", atualize `file_shares.path` — não basta copiar arquivo para `shares/`.
- **Scheduler/rotinas**: `scheduler.py`, `ADWs/`, heartbeats em `config/heartbeats.yaml`.
- **Deploy VPS**: Docker Swarm (`evonexus-vps.stack.yml`). Containers: `evonexus_evonexus_dashboard`, `evonexus_evonexus_scheduler`, `evonexus_evonexus_media_worker`, `evonexus_omniroute`, `evonexus_evonexus_telegram`.

## Decisions Log
- **2026-08-15**: Investigação de share "preso no 105" revelou que token do Nexus aponta para caminho fixo no banco, não para diretório. Fix: atualizar `file_shares.path` do token para o novo arquivo. Documentar para não repetir o equívoco de "copiar para shares/" sem mexer no banco.
- **2026-08-15**: Sessão de análise de reels @caiomktviral fechada com 304 reels; relatório ainda resumido, aceito por hora pelo usuário (deep-dive completo fica como próximo passo).

## Runbook / Operations
- **Atualizar conteúdo de um share Nexus**:
  1. Gerar novo arquivo em `REPO_ROOT/workspace/reports/` (container dashboard).
  2. `UPDATE file_shares SET path='<caminho relativo>' WHERE token='<token>'` no `/workspace/dashboard/data/evonexus.db`.
  3. Validar: `curl -s -A "Mozilla/5.0" "https://nexus.workflowapi.com.br/api/shares/<token>/view"`.
- **SSH VPS**: `ssh evo-nexus-vps`. Container dashboard pode mudar de hash — use `docker ps --format "{{.Names}}" | grep dashboard`.

## Project File Structure
- `dashboard/backend/` — app Flask + rotas + modelos
- `dashboard/frontend/` — SPA (React)
- `ADWs/` — rotinas automatizadas
- `scripts/` — utilitários (`publish_artifact.py`, etc.)
- `workspace/` — dados de domínio (reports, shares, social, finance, ...)
- `media_worker/` — pipeline de vídeo
- `.claude/` — agents, skills, rules, commands

## References
- `LEARNINGS.md` — aprendizados duráveis
- `TECH_DEBT.md` — débitos técnicos abertos
- `handover/` — handoffs sequenciais de sessão