# Automated Routines

Managed by the scheduler (`make scheduler`, runs `scheduler.py`) — see `ROUTINES.md` for
narrative details.

**Reality check (panorama 2026-07-17, item 3):** a prior version of this file documented
~20 daily/weekly/monthly routines as if all were scheduled. Most had no backing script at
all — `scripts/publish_scheduled.py` (the one that actually dispatches real posts to X)
was even silently failing every tick because `scheduler.py` looked for it under the wrong
path. That's fixed. What's below is now split into what's genuinely scheduled vs what
still requires a manual skill invocation — no more promising automation that doesn't run.

## Onde ver o que roda

`/routines` no dashboard é a **fonte única**: lista o que o agendador
registrou de fato (`schedule.get_jobs()`, não regex sobre o código-fonte), com
a próxima execução real, o histórico de execução e o custo acumulado. Cada
rotina traz o motor que a move:

| Selo | O que significa | Consequência |
|---|---|---|
| 🐍 **Python** | código determinístico | custa CPU; pode rodar de 15 em 15 min |
| 🤖 **Modelo** | chama uma LLM | custa dinheiro **toda** execução |

Detectado em `dashboard/backend/routines_registry.py::motor_do_script`, que
segue os imports locais um nível — o entrypoint de quatro linhas que chama o
modelo lá dentro não engana. A regra ao criar rotina nova: **se a saída é
determinística, escreva em Python.** Modelo só onde existe julgamento (escolher
pauta, escrever texto, avaliar ICP). Narrar tabela que já é estruturada não é
julgamento.

## Desligadas em 27/07/2026 — a esteira AI News

`AI News Daily Draft` e `AI News Weekly X Research` (`enabled: false` em
`config/routines.yaml`). A diária era uma corrente de **quatro** chamadas de
Claude em série (Sage → Quill → Raven → Mako) que produzia o mesmo artigo de
blog que a Esteira de Conteúdo já produz com uma chamada, e melhor: pauta por
volume de busca real, humanizer, CTA de funil, capa com rodízio de pose e gate
único.

Custou **US$ 11,92, 44% de todo o gasto em rotina**, com 27% a 75% de acerto, e
estava 100% quebrada desde 24/07 — os 10 itens da fila em `failed`, falhando
todo dia às 19:00. O que ela tinha de único, pauta em alta no X, a esteira
principal já faz em `weekly_content_research.pautas_do_x()`.

## Core (`scheduler.py`, ships with the repo)

| Time | Routine | Script |
|---------|--------|--------|
| 07:00 | Good Morning (briefing) | `good_morning.py` |
| 21:00 | End of Day | `end_of_day.py` |
| 21:00 | Daily Backup | `backup.py` |
| 21:15 | Memory Sync | `memory_sync.py` |
| 04:00 | Uso Modelos DIA (cost telemetry) | `uso_modelos_dia.py` |
| Every hour, 08h-20h BRT | Hourly Report | `hourly_report.py` |
| Sunday 09:00 | Memory Lint | `memory_lint.py` |
| A cada 15 min | Derivar Redes Pendentes | `derivar_redes_pendentes.py` — recupera o artigo agendado que o Ghost publicou sozinho e ninguém derivou (ver `esteira-de-conteudo.md` §0) |
| Friday 08:00 | Weekly Review | `weekly_review.py` — reactivated; checks overdue items weekly |

`run_adw()` resolves a script's real location with a 3-candidate fallback
(`ADWs/routines/custom/<name>` → `ADWs/routines/<name>` → top-level `scripts/<name>`) so
a script doesn't need to be relocated just to be scheduled — see `scheduler.py::run_adw`.

## Deadline heartbeat (in-process, zero Claude cost)

`deadline-check` (`config/heartbeats.example.yaml`) — every 4h, checks for active Goals
and open/in_progress/blocked Tickets past their `due_date` and alerts via Telegram if any
exist. Closes the gap between Weekly Review runs (Fridays only). Handler:
`dashboard/backend/deadline_check.py::tick`. Ships `enabled: false` — enable via
`/scheduler` → Heartbeats after reviewing.

## Operacional diário (`config/routines.yaml`, local/gitignored — notifies via WhatsApp)

Decision (2026-07-17): only this cluster gets formalized scheduling; notification channel
is WhatsApp (Evolution Go, instância `sistema-britto`) to the superadmin's number, **not
e-mail**. Requires `WHATSAPP_PHONE` + `EVOLUTION_GO_URL`/`EVOLUTION_GO_KEY` in `.env` — see
`.env.example`. All ship `enabled: false`; flip to `true` in `config/routines.yaml` once
those env vars are set.

| Time | Routine | Script | Agent |
|---------|--------|--------|--------|
| 06:50 | Review Todoist | `custom/review_todoist.py` → skill `prod-review-todoist` | @clawdia |
| 07:15 | Email Triage | `custom/email_triage.py` → skill `gog-email-triage` | @clawdia |
| every 30min | Sync Meetings (Fathom) | `custom/sync_meetings.py` → skill `int-fathom` | @clawdia |
| 21:30 | Dashboard Consolidado (WhatsApp) | `daily_status_report.py` | system (no Claude — pure SQL report) |

`config/routines.yaml` and `ADWs/routines/custom/*.py` are gitignored by design (same
pattern as `config/heartbeats.yaml` vs `.example.yaml`, or `.claude/agents/custom-*.md`) —
personal-to-workspace automation, not shipped in the repo. **On a VPS deploy, these do
NOT ride along with a `docker service update`** — they need to be placed on that machine
directly (same as `config/heartbeats.yaml` and `.env` already are).

## Not scheduled — invoke manually via skill

Everything below has a skill (or documented `/skill-name`) but no backing routine script —
run it in a Claude Code session (`/skill-name`) or ask the relevant agent directly. Adding
scheduling for any of these is the natural next step of this same pattern, once there's a
real script wired the way Review Todoist/Email Triage/Sync Meetings are above.

| Routine | Agent | How to run today |
|---------|--------|--------|
| Social Analytics (daily/weekly/monthly) | @pixel | `/social-analytics-report` or ask Pixel |
| Licensing (daily/weekly/monthly) | @atlas | ask Atlas |
| Financial Pulse / Weekly / Monthly Close | @flux | ask Flux |
| Community Pulse / Weekly / Monthly | @pulse | ask Pulse |
| FAQ Sync | @pulse | ask Pulse |
| Trends | @clawdia | ask Clawdia |
| Strategy Digest | @sage | ask Sage |
| Linear Review / GitHub Review | @atlas | ask Atlas |
| Learning Review Weekly | learn-* skills | `/learner` or relevant `learn-*` skill |
| Health Check-in | @kai | ask Kai |
