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
