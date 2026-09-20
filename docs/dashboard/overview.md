# Dashboard Overview

The EvoNexus web dashboard is a React + Flask application that gives you a visual interface to manage agents, heartbeats, routines, triggers, the projects/goals/tickets graph, knowledge, memory, costs, AI providers, and external APIs — the whole operation in one place.

## Starting the Dashboard

```bash
make dashboard-app
```

This starts the Flask backend (with WebSocket support) and serves the React frontend on a single port. Default: `http://localhost:8080`.

### Changing the Port

Set the port in `config/workspace.yaml`:

```yaml
dashboard:
  port: 8080
```

Or via environment variable:

```bash
EVONEXUS_PORT=9090 make dashboard-app
```

## First Run Setup

When no users exist in the database, the dashboard redirects to a setup wizard at `/setup`. The wizard has two steps:

1. **Workspace** -- your name (owner), company, timezone, and language
2. **Account** -- create your admin account (username, optional email, display name, password of at least 6 characters)

After setup completes, you are logged in as admin and can access all pages.

## Navigation Model

The sidebar is a **fixed** menu — nothing collapses except injected plugin groups. It is organized into three fixed sections plus a footer:

- **Cockpit** -- the single landing page (tabbed, deep-linkable)
- **work block** (untitled) -- Projects, Goals (Metas), Kanban, and Materiais. The first three are different zoom levels over the same Mission → Project → Goal → Ticket graph; Materiais is the workspace file browser.
- **Inteligência** -- everything that gives the operation its brain: Agents, Heartbeats, Routines, Triggers, and the Inteligência hub (link labeled "APIs", pointing to `/inteligencia`).
- **Footer** -- the gear icon opens Settings, next to your name/role badge and the logout button.

![Sidebar](../imgs/doc-overview.webp)

## Cockpit

Unified command center and landing page after login. A single page with a tab bar (`/?tab=` deep links):

| Tab | Shows |
|-----|-------|
| **Visão** | Aggregated metrics across all agents -- financial snapshot, community health, project status, social reach, recent reports, active agents |
| **Orquestração** | Live orchestration view of running agent work |
| **Aprovações** | Items awaiting human approval (gated goal actions) |
| **Pautas** | Content queue for social/editorial work |
| **Atividade** | Routine/agent activity feed |

Tabs that require permissions you don't have are hidden automatically.

## Work Block

### Projects

Overview of your missions and projects — the top level of the Mission → Project → Goal → Ticket graph. Each project rolls up its goals and open tickets.

### Goals (Metas)

Create measurable goals (`metric_type` + `target_value`) attached to missions and projects. This is the "what counts as done" layer — approvals for gated actions surface here and in the Cockpit's Aprovações tab.

### Kanban

Board view of tickets (persistent conversation/work threads assigned to agents). Drag between columns to change status; open a ticket to chat with the assigned agent in context.

![Kanban](../imgs/doc-issues.webp)

### Materiais (Workspace)

Browse and edit workspace output organized by domain (strategy, reports, social, finance, daily logs, …). Includes an in-browser file editor. This is where routines drop their artifacts and where humans review them.

![Materiais](../imgs/doc-workspace.webp)

## Inteligência

### Inteligência Hub

`/inteligencia` is a card grid that indexes everything in this section — Provedores, Conhecimento (RAG), Memória, MemPalace, Custos, Skills, MCP Servers, Plugins, and APIs. Each card links to its dedicated page; every sub-page has a "← Inteligência" back button.

### Agents

All agent definitions loaded from `.claude/agents/` — 17 business-domain agents (finance, projects, community, social, strategy, sales, courses, marketing, HR, customer success, legal, product, data, …) plus the engineering layer (architecture, planning, review, testing, security, …) and supporting planners. Each agent page has two interaction modes: a **chat** (agent-bound conversation) and a **terminal** (raw Claude Code session with multi-tab support).

![Agents](../imgs/doc-agents.webp)

### Heartbeats

Proactive scheduled wake-ups for agents: an interval + a decision prompt that tells the agent when to act and when to stay quiet. List, enable/disable, trigger manually, and inspect each heartbeat's run history and cost.

![Heartbeats](../imgs/doc-heartbeats.webp)

### Routines

Automated workflows (ADWs) on a schedule: total runs, success rate, average duration, token usage, cost, and a "Run Now" button per routine.

![Routines](../imgs/doc-routines.webp)

### Triggers

Reactive event triggers — webhook and event-based. Execute skills or routines in response to external events (GitHub push, Stripe payment, Linear updates). Filter by type and status.

![Triggers](../imgs/doc-triggers.webp)

### Providers

Pick and configure which LLM backend powers EvoNexus — Anthropic (default) or alternates via [OpenClaude](https://www.npmjs.com/package/@gitlawb/openclaude): OpenRouter, OpenAI, Gemini, Codex Auth, NVIDIA NIM, OmniRoute, AWS Bedrock, Vertex AI. Includes the **Trust mode** toggle (default ON): when on, the terminal executes tools without per-action confirmation. See [providers.md](providers.md) for the full reference.

### Knowledge Base

Multi-server semantic search (vector + BM25 hybrid via pgvector) over your documents, with OCR, chunking, spaces/units organization, upload, and API keys. Bring Your Own Postgres. See [knowledge.md](knowledge.md).

![Knowledge Base](../imgs/doc-knowledge.webp)

### Memory

Browse the persistent memory system: workspace memory, per-agent memory, and shared context that survives across sessions.

![Memory](../imgs/doc-memory.webp)

### MemPalace

Optional local semantic index powered by [MemPalace](https://github.com/milla-jovovich/mempalace) — enable with one click, add directories as sources, search by meaning. Runs locally. See [knowledge-base.md](knowledge-base.md).

### Costs

Token usage and cost tracking: trends over time, input vs output breakdown, per-routine and per-agent cost comparison.

![Costs](../imgs/doc-costs.webp)

### Skills

Browse all installed skills grouped by prefix (`social-`, `fin-`, `int-`, `prod-`, etc). Open a skill to read its full description, trigger conditions, and source file.

![Skills](../imgs/doc-skills.webp)

### MCP Servers

Manage Model Context Protocol servers wired into the agent runtime.

### Plugins

Installed plugins plus a **marketplace** tab for discovering, installing, and removing plugins (each can inject its own pages into the sidebar).

### APIs (Integrations)

Status board for 20 external service integrations (Stripe, Omie, Asaas, Bling, GitHub, Discord, Telegram, YouTube, Instagram, LinkedIn, Fathom, Evolution API, …). Green = connected, yellow = needs configuration. Social accounts connect via OAuth from this page. The menu item is labeled "Integrações"; the page and hub card are labeled **APIs**.

![APIs](../imgs/doc-integrations.webp)

## Settings

Opened from the gear icon in the sidebar footer (next to your name), with six tabs:

- **Workspace** -- edit workspace name, owner, company, language, timezone, and dashboard port (`config/workspace.yaml`)
- **Backups** -- export/restore workspace data, local ZIP downloads, S3 status, merge or replace restore modes
- **Docs** -- this documentation, embedded
- **Users** -- create, edit, deactivate users; assign roles
- **Roles** -- custom roles with a granular permission matrix (see [users-and-roles.md](users-and-roles.md))
- **Audit** -- full audit trail: logins, config changes, routine executions (admin)

## Direct URLs (not in the menu)

A few routed pages are reachable by URL even though they aren't in the sidebar:

- `/tasks` -- one-off scheduled actions (see [Scheduled Tasks](../routines/scheduled-tasks.md))
- `/scheduler` -- start/stop background services and watch live logs
- `/systems` -- register external apps/services for quick access
- `/templates` -- preview HTML report templates
- `/shares` -- manage public share links for workspace artifacts
- `/media` -- media production jobs (render queue)
