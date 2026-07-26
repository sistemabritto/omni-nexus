# Briefing — Kanban UX + pipeline autônomo de goals (EvoNexus)

## Visão (norte de tudo isso)

Teamwork overnight: proactive action taker, artifact maker, post sharer,
mega solution maker. O sistema deve rodar sozinho enquanto Felipe dorme ou
viaja — humano define o objetivo (Goal), os agentes fazem o resto: planejam,
quebram em tarefas, se atribuem, executam, produzem artefatos reais, se
revisam entre si (self-healing), e só acionam aprovação humana via Telegram
no caso estreito de publicação pública (redes sociais, links compartilhados).
Fora isso, é YOLO mode — autonomia total.

Contexto já existente que essa mudança deve aproveitar, não redesenhar do
zero:
- O bot do Telegram (`scripts/telegram_provider_bot.py`) já foi reescrito
  hoje (2026-07-15) pra rodar cada mensagem via
  `dashboard/backend/provider_fallback.invoke_with_fallback()` — motor
  agêntico real (Bash, spawn de qualquer um dos 38 agentes em
  `.claude/agents/*.md`), `--dangerously-skip-permissions`, sem gate de
  confirmação. Esse é o canal natural pra aprovação humana quando for
  necessária.
- `invoke_with_fallback()` já tem um mutex cross-container (`flock` num
  arquivo em `evonexus_workspace`, o único volume montado nos 3 serviços —
  dashboard/telegram/scheduler) — qualquer novo worker que rodar CLI
  agêntica via esse motor já herda a serialização, não precisa reinventar.
- `tickets.task_id` (FK real pra `goal_tasks.id`) foi adicionado hoje —
  resolver um ticket com `task_id` já marca a `goal_task` linkada como
  `done` e recalcula `goals.current_value` automaticamente
  (`dashboard/backend/heartbeat_outcome.py::_sync_goal_task_from_ticket`,
  chamado nos 3 caminhos que fecham ticket: heartbeat, PATCH manual, bulk
  action). Isso é a base pra unificar tickets e goal_tasks — mas hoje ainda
  são dois modelos/UIs paralelos.

## Problema 1 — nomenclatura e modelo de dados fragmentados

Hoje existem 5 conceitos competindo pelo mesmo vocabulário, sem uma fonte de
verdade única:

1. **Tickets** (`tickets` table) — Kanban real, `/kanban` e `/issues`,
   checkout atômico, `dashboard/frontend/src/pages/Kanban.tsx`.
2. **Routines** (`config/routines.yaml`) — scripts recorrentes (make
   morning, make eod...). A UI de `/scheduler` (`Scheduler.tsx`) literalmente
   chama isso de "Scheduled Tasks" — colide de propósito com o que
   qualquer usuário chamaria de "tarefa do kanban".
3. **Heartbeats** (`config/heartbeats.yaml`) — agentes proativos que
   acordam por intervalo/trigger e trabalham a fila de tickets
   (`.claude/rules/heartbeats.md`).
4. **Goal Tasks** (`goal_tasks` table) — unidades de trabalho dentro de uma
   Goal (Mission → Project → Goal → Task, `.claude/rules/goals.md`). Só
   aparecem em `/goals` (tree view), nunca no Kanban. Hoje são criadas
   manualmente (por Oracle/compass-planner ou por humano) já com
   `assignee_agent`, `priority`, `due_date` pré-definidos — human-planned,
   agent-executed.
5. **Scheduled Tasks (one-off)** — skill `schedule-task`
   (`.claude/skills/schedule-task/`), descrita como "sem criar uma routine
   completa" — um SEXTO mecanismo, ainda mais confuso.

**Pedido:** unificar. Direção sugerida (a validar/decidir na sessão de
planejamento, não é definitivo): Tickets vira a ÚNICA unidade de trabalho —
Routines fica restrito a scripts automáticos recorrentes sem semântica de
"tarefa atribuível", Heartbeats continuam sendo os workers que consomem a
fila de Tickets, e Goal Tasks deixa de ser tabela paralela (vira uma view do
Kanban filtrada por `goal_id`, ou é de fato absorvida — decisão de design
em aberto). Renomear "Scheduled Tasks" na UI do Scheduler pra algo que não
colida com "ticket"/"tarefa" (ex: "Rotinas").

## Problema 2 — pipeline de Goal é manual, precisa ser autônomo (inversão de fluxo)

**Hoje:** humano (ou Oracle) cria Mission → Project → Goal → já quebra em
Tasks manualmente, já atribui agente, já define prioridade/prazo. Os
agentes só executam o checklist. Confirmado ao vivo hoje: 24 goal_tasks
ficaram semanas em `open` porque fechar o ticket espelhado nunca tocava a
task — e cada Goal existente foi montada à mão, task por task
(`memory/vps-api-token-separation.md` e o histórico desta sessão têm mais
contexto se precisar).

**Como devia ser:**
1. Humano cria só a **Goal** (objetivo + métrica + prazo alvo).
2. Um agente/processo de planejamento (compass-planner? um novo
   orquestrador dedicado a Goals? decisão de design) quebra a Goal em
   tarefas.
3. As tarefas se **auto-atribuem** ao agente especialista responsável
   (mapeando pro catálogo de 38 agentes em `.claude/agents/`), com
   **prioridade e deadline gerados pelos próprios agentes**, não pelo
   humano.
4. Execução produz **artefatos reais** (drafts, posts, código, documentos —
   não só um checkbox marcado `done`).
5. Depois da execução, os agentes fazem **review entre si** — um ciclo de
   self-healing/crítica (o workspace já tem `raven-critic` como crítico
   adversarial e `oath-verifier` como verificador de evidência — avaliar se
   esse ciclo deveria reusar esses agentes ou precisa de um novo).
6. **Aprovação humana só entra via Telegram**, e só quando a ação for
   publicação em rede social ou compartilhamento de link público. Todo o
   resto roda em YOLO mode (`--dangerously-skip-permissions`, sem gate).

**Pedido:** desenhar e implementar esse pipeline. Pontos em aberto pra
decidir na sessão (não assumir, perguntar/decidir explicitamente):
- Quem é o agente/processo responsável por "quebrar Goal em Tasks"? Um
  heartbeat dedicado, uma extensão do `helm-conductor` (que já orquestra
  ciclos de trabalho, `.claude/rules/dev-phases.md`), ou um novo componente?
- Onde mora o "self-healing review loop" — é outro heartbeat, é parte do
  mesmo run, é um novo status de ticket (`review` já existe no enum de
  status)?
- Como o gate de aprovação sabe distinguir "isso é publicação pública" de
  "isso é trabalho interno"? Precisa de uma flag explícita no ticket/task
  (ex: `requires_human_approval: bool` ou reconhecer por
  `assignee_agent in (pixel-social-media, mako-marketing, ...)` + ação de
  publish)?

## Problema 3 — UI do Kanban (desktop + mobile)

`dashboard/frontend/src/pages/Kanban.tsx`:
- **Bug real de mobile**: grid usa `min-w-[1440px]` (`md:min-w-[1180px]`)
  mesmo em `grid-cols-1` — força scroll horizontal numa tela que devia ser
  1 coluna vertical (linha 164). Precisa virar mobile-first de verdade.
- **Sem botão de criar ticket na própria página** — só existe via o
  chat de um agente.
- Card do ticket é funcional mas simples — reavaliar visualmente (o
  workspace já tem o agente `canvas-designer` pra isso — "não existe skill
  chamada 'UI UX pro max'", esse é o especialista real de UI/UX aqui).

**Pedido:** redesign completo (desktop + mobile), usando `canvas-designer`
ou equivalente pra garantir qualidade visual — tipografia distinta, sem
padrão de "AI slop" genérico.

## Problema 4 — criação de ticket é um `prompt()` nativo do navegador

`dashboard/frontend/src/components/AgentChat.tsx:476`:
```js
const createAndBindTicket = useCallback(async () => {
  const title = prompt('New ticket title:')
  ...
```
Isso é chamado a partir do pill "No ticket" no topo do chat (dropdown,
`AgentChat.tsx` ~linha 1108). Sem descrição, sem prioridade, sem
vínculo a goal — literalmente o dialog nativo `window.prompt()`.

**Pedido:** substituir por um modal de verdade (title, description,
priority, assignee_agent, **goal_id — deixar linkar a uma Goal/Task
existente ou criar nova**), acessível tanto do pill no chat quanto de um
botão "novo ticket" direto na página do Kanban.

## Escopo e constraints

- Manter o fluxo de deploy já em uso: push na branch → GH Actions builda
  `excarplex/evo-nexus-{dashboard,runtime}:latest` → `docker service
  update --force` na VPS Swarm (sem SSH direto, comandos rodados por
  Felipe). Ver `.claude/rules/` e o histórico desta sessão se precisar do
  fluxo exato.
- Repo: `sistemabritto/omni-nexus`, branch de trabalho
  `feat/chat-openclaude-provider-routing`, merge em `main`.
- Qualquer dúvida de decisão de produto (não técnica) — perguntar ao
  Felipe explicitamente em vez de assumir, ele pediu isso.
