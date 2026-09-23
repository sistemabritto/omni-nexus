# Project Agent Rules

## Agent Rules

- User prefers thorough, structured codebase audits with numbered investigation points covering specific areas
  - Prefer inline error states over alert() for user-facing error messages in UI components.
- When renaming routes in Next.js App Router, preserve query parameters by creating a redirect component that captures location.search and forwards it to the new route

## Empresas (multi-tenant)

Companies are a first-class entity in the dashboard: missions/projects/goals scope to a company via `company_id`, and the active company is a per-user UI state (localStorage `evo:active_company`).

- **Model** (`dashboard/backend/models.py:656`): `companies` — `cnpj` (String 18, unique, nullable), `name` (200, required), `slug` (200, unique, auto-generated from name if omitted), `domain` (300), `status` (default `active`), `logo_path` (workspace-relative).
- **Logo** — served via dedicated `GET /api/companies/<id>/logo` (send_file, `_require("view")`). Logos live under `REPO_ROOT/assets/company-logos/`, OUTSIDE both `WORKSPACE_DIR` (`REPO_ROOT/workspace`) and `ADMIN_ROOTS` (`.claude`, `config`, `docs`), so `/api/workspace/download` 403s on them even for admins → that's why a resource-scoped endpoint exists (fixed in 62d9f60). Rule of thumb: any asset stored outside `workspace/` needs its own endpoint, not a route through `/api/workspace/download`. NOTE: logo **upload** writes to `REPO_ROOT/workspace/assets/company-logos/<slug><ext>` — that's under the persistent `evonexus_evonexus_workspace` volume; writing to bare `REPO_ROOT/assets/` is ephemeral and the file vanishes on every redeploy.
- **API** (`dashboard/backend/routes/goals.py:140-241`, auth via `_require("view"|"manage")`):
  - `GET /api/companies` — lista ordenada por id
  - `POST /api/companies` — body `{name, slug?, cnpj?, domain?}`; 400 sem name; 409 slug/CNPJ duplicado; 201 com o objeto. Empresa nova nasce vazia (sem mission/project clone — P4 fase 2 `/empresa` Magneto).
  - `PATCH /api/companies/<id>` — aceita `cnpj | name | domain | status | logo_path` (logo_path null remove o logo)
  - `DELETE /api/companies/<id>` — apaga a empresa (SET NULL manual em `projects`/`goals`/`media_jobs`, pois SQLite não enforce FKs por padrão) e remove o arquivo de logo; se for a empresa ativa da UI, o frontend zera `activeCompanyId`
  - `GET|POST|DELETE /api/companies/<id>/logo` — GET serve inline (permissão view); POST multipart `file` (png/webp/jpg/svg) salva em `workspace/assets/company-logos/<slug><ext>` (sobrescreve); DELETE remove arquivo + campo
- **Frontend**: seleção no card do perfil da sidebar (`src/components/Sidebar.tsx` → `CompanySwitcher`, popover com "Gerenciar empresas" e "Nova empresa"; sem nenhuma empresa, o chip vira um botão "+ Adicionar empresa"); lista gerir/excluir em `src/components/CompanyListModal.tsx` (exclusão em 2 estágios inline); form criar/editar em `src/components/CompanyManagerModal.tsx` (slug auto-gerado editável, CNPJ com máscara, logo só pós-criação); contexto em `src/context/CompanyContext.tsx` (estado ativo em localStorage, `reload()` após mutações). i18n: chaves em `nav.companies.*` nos 3 locales (pt-BR/en-US/es) — sempre use esse prefixo, senão a chave literal aparece na UI.
- **DB vivo**: SQLite em `/workspace/dashboard/data/evonexus.db` DENTRO do container do serviço swarm `evonexus_evonexus_dashboard` (não há `/opt/evo-nexus/dashboard/data/evonexus.db` no host — stale). Consulta ad-hoc: `docker exec <container> python3 -c "import sqlite3; ..."`.

## Integrações: Plausible + Instagram (VPS)

Diagnóstico completo feito em 22/09/2026:

### Plausible (`track.workflowapi.com.br`)
- **Stack swarm** `plausible` (`/opt/plausible.yml` na VPS): `plausible` (web) + `plausible_db` (pg 15) + `plausible_events_db` (ClickHouse). Dados persistentes em `/opt/plausible/{db,clickhouse,events,logs}` no host. **App roda `ghcr.io/plausible/community-edition:v3.2.1`** (upgrade feito 22/09 — Docker Hub `plausible/analytics:latest` está congelado em v2.0.0 jul/2023; imagens novas só saem no GHCR). ClickHouse ficou `latest` de propósito (downgrade p/ 24.12 dava exit 210 — formato dos dados). Backup PG de antes do upgrade: `/opt/plausible/backup-dump-20260922.sql`.
- **Domínio é `track.workflowapi.com.br`** — os nomes `analytics.`/`plausible.`/`stats.workflowapi.com.br` existem em DNS (Cloudflare) mas não têm rota no Traefik → 404. Rota: `traefik.http.routers.plausible.rule=Host(\`track.workflowapi.com.br\`)` apontando p/ porta 8000 do web.
- **SITES**: id=1 `blog.sistemabritto.com.br`, id=2 `sistemabritto.com.br` (site principal — **cadastro SEM `www.`**, ver regra de normalização abaixo). Admin: `sistemabritto@gmail.com` / `track@Britto01`.
- **⚠️ Normalização de domínio (causa raiz real dos eventos "sumindo")**: a v3 **normaliza removendo o prefixo `www.`** do domínio antes de casar com a tabela `sites`. Consequência prática: um site cadastrado COM `www.` nunca casa e todos os eventos caem como `dropped_not_found` no `ingest_counters` — mesmo com o snippet instalado e o client recebendo 202 Accepted. **Cadastro no Plausible sempre SEM `www.`** (o snippet pode manter `data-domain="www...."` que o normalizador resolve). Fix aplicado 22/09: rename do site id=2 `www.sistemabritto.com.br` → `sistemabritto.com.br`. Ver skill `plausible-vps-diagnostics` para o playbook completo.
- **⚠️ Ingestão/validação**: o endpoint de ingestão é `POST /api/event?st=<dominio>` (o legado `/i` voltou a servir HTML na v3). O **202 do endpoint NÃO significa que persistiu** — confirme no ClickHouse. Como checar: `clickhouse-client --user default --password "" -q "SELECT site_id, count(), toString(max(timestamp)) FROM plausible_events_db.events_v2 GROUP BY site_id"` (tabela legada `events` está VAZIA — não confiar nela) e os drops em `plausible_events_db.ingest_counters` (col `site_domain` + `status` = `buffered|dropped_not_found`). Events gravam em `events_v2` (col `site_id` = id inteiro do site).
- **API v3**: `http://plausible_plausible:8000/api/v1/stats/{aggregate|timeseries}?site_id=<domínio>&period=30d` c/ `Bearer PLAUSIBLE_API_KEY` (rede interna da VPS; o Cloudflare barra requisições externas à API com 403 c/ código 1010 — 504s intermites também). `period` é formato compacto (`30d`), **não** `lastThirtyDays`. Métricas snake_case (`visitors,pageviews,bounce_rate`). `breakdown?property=...` ainda dá 400 p/ `pathname/referrer_domain/country_code` (nomes novos não mapeados) — fallback: query direta no ClickHouse via `clickhouse-client`.
- **Ruído nos logs**: loop de erro `Ch.Connection disconnected` a cada ~5s no web (Mint HTTPError) — não bloqueia inserts.
- **Snippet do site principal**: já presente em `sistemabritto-site/pages/_app.tsx` (commit `f1d0d94`) — injetado **client-side** via `next/script` afterInteractive, então NUNCA aparece no HTML cru (grep no HTML mentiu; está nos chunks JS `/_next/static/immutable/chunks/`). Deploy em produção via Vercel (git push origin main).

### Instagram (Graph API)
- Token IGAA (Login do Instagram) criado 19/09 — **validade 60 dias (~expira 18/nov)**; sem Page Token configurado (`SOCIAL_INSTAGRAM_1_PAGE_TOKEN` vazio). Para expiração exata e para renovar, precisa **App Access Token** (app do Meta Business) — o `debug_token` com token de user dá OAuthException 100.
- Token de user IGAA não autoriza `debug_token`; o token segue funcionando p/ leitura mesmo assim (perfis/posts/insights OK).
- **Limitação de paginação**: `GET {node}/media` só devolve ~50 posts recentes; `paging.cursors.before` da página seguinte retorna lista VAZIA. Não há como paginar além disso via Graph API social — para histórico maior, usar export/backup ou insights por post individual.
 - Cliente: `.claude/skills/int-instagram/scripts/instagram_client.py` (`accounts|profile|recent_posts|top_posts|post_insights|account_insights|summary`).

### OpenReply (comentário→DM) — conexão do dashboard p/ criar campanhas do reels-copilot
- O reels-copilot (`dashboard/backend/reels_copilot.py`) cria a campanha OpenReply de cada reel via `create_openreply_campaign`. **O container do dashboard NÃO tem `docker` nem `ssh` no PATH** — o caminho antigo `sh -c "docker exec … psql"` falhava sempre (`openreply_status='failed'` em todos os reels). Corrigido 22/09 (commit `20102dc`): conexão **Postgres DIRETA pela rede interna do swarm** (`postgres_postgres:5432`, resolvido por DNS interno do container) via `psycopg2` (já no venv), SQL parametrizado.
- Credenciais por env no serviço `evonexus_evonexus_dashboard`: `OPENREPLY_PG_HOST=postgres_postgres`, `OPENREPLY_PG_PORT=5432`, `OPENREPLY_PG_USER=postgres`, `OPENREPLY_PG_PASSWORD=<senha p/ extrair de `docker service inspect openreply_openreply-web` → campo `DATABASE_URL`>`, `OPENREPLY_PG_DB=openreply`. **No redeploy, re-addar esses 5 junto com `APPROVAL_BRIDGE_TOKEN`/`APPROVAL_APPROVER_IDS`/`REELS_AUTO_ARCHIVE_PAST_REMINDER=1`** (caem sem `--env-add`). `OPENREPLY_DATABASE_URL` completo tem precedência sobre os campos individuais.
- Postgres COMPARTILHADO (`postgres_postgres`, banco `openreply`) — tabela `"Automation"` (colunas CamelCase precisam de aspas duplas). Campanha do reel usa `pendingNextReel=true` → o worker do OpenReply amarra sozinho ao próximo reel publicado.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Python Tool Management

- When fixing type errors, prefer to only fix newly introduced errors if pre-existing errors are already accepted by CI
