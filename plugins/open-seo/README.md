# OpenSEO — plugin do OmniNexus

Camada de dados de SEO do workspace. Sobe o [OpenSEO](https://github.com/every-app/open-seo)
(alternativa open source a Semrush/Ahrefs, MIT) self-hosted e expõe o MCP dele
para os 38+ agentes do OmniNexus.

Instalado a partir do upstream oficial no commit `f569726` (2026-07-23).

## O que este plugin entrega

| Peça | Onde |
|---|---|
| Serviço self-hosted | `docker-compose.yml` → service `open-seo` (imagem oficial `ghcr.io/every-app/open-seo`) |
| MCP server | `.mcp.json` → `plugin-open-seo-openseo` (HTTP, `${OPEN_SEO_URL}/mcp`) |
| Agent skills | `.claude/skills/plugin-open-seo-*` (7 skills, vendored do upstream) |
| Manifesto | `plugins/open-seo/plugin.yaml` |

### Skills instaladas

| Skill | Para quê |
|---|---|
| `plugin-open-seo-seo-project-setup` | cria o workspace de SEO do projeto (contexto, metas, posicionamento) — **rode esta primeiro** |
| `plugin-open-seo-keyword-research` | descoberta de keywords, métricas, SERP, volume/KD/intenção |
| `plugin-open-seo-keyword-clustering` | agrupa keywords por intenção e mapeia para páginas |
| `plugin-open-seo-competitor-analysis` | pegada orgânica de UM concorrente |
| `plugin-open-seo-competitive-landscape` | mapa do mercado: líderes, temas vencedores, gaps |
| `plugin-open-seo-link-prospecting` | prospecção de backlinks + rascunho de outreach |
| `plugin-open-seo-seo-coach` | modo consultor: explica workflows e sugere próximo passo |

A skill upstream `openseo-review-web-content` foi deliberadamente **não**
instalada: ela é específica do site do próprio projeto OpenSEO (`web/`) e só
geraria ruído nos agentes daqui.

## Setup

### 1. Credencial (obrigatória)

O OpenSEO é a UI/MCP; quem devolve dado de SEO é o **DataForSEO**, cobrado
pay-as-you-go direto na conta do usuário. Sem a chave o serviço sobe e a UI
abre, mas toda query volta vazia.

```bash
# .env
DATAFORSEO_API_KEY=<base64 de login:senha do DataForSEO>
```

Como gerar: `docs/DATAFORSEO_API_KEY.md` no upstream, ou
<https://dataforseo.com/?aff=255379>.

### 2. Subir o serviço

```bash
docker compose up -d open-seo
curl -s http://127.0.0.1:3001/ -o /dev/null -w '%{http_code}\n'   # espera 200
```

A porta é publicada **só em 127.0.0.1** e o modo de auth é `local_noauth`
(padrão upstream para deploy privado). Se um dia isso for exposto na internet,
troque o `AUTH_MODE` antes — `local_noauth` não tem login.

### 3. Conferir o MCP

O `.mcp.json` já registra `plugin-open-seo-openseo` apontando para
`http://127.0.0.1:3001/mcp`. Reinicie a sessão do Claude Code e confirme que as
ferramentas `research_keywords`, `get_keyword_metrics`, `get_ranked_keywords`
etc. aparecem.

Em Swarm/VPS, troque a URL para o nome do serviço na rede interna
(`http://open-seo:3001/mcp`) — o container do dashboard resolve por DNS de
serviço, não por `127.0.0.1`.

## Variáveis de ambiente

| Var | Obrigatória | Default | Para quê |
|---|---|---|---|
| `DATAFORSEO_API_KEY` | **sim** | — | dados de SEO (custo real por request) |
| `OPEN_SEO_PORT` | não | `3001` | porta publicada |
| `OPEN_SEO_IMAGE` | não | `ghcr.io/every-app/open-seo:latest` | pinar uma versão |
| `OPEN_SEO_ALLOWED_HOST` | não | vazio | hostname público, se exposto |
| `OPENSEO_TELEMETRY_DISABLED` | não | `1` | telemetria anônima do upstream (desligada por padrão aqui) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | não | — | conectar Search Console (dados de 1ª parte) |
| `BETTER_AUTH_SECRET` | não | — | só necessário fora do `local_noauth` |

## Atualizar

```bash
docker compose pull open-seo && docker compose up -d open-seo
```

As skills são vendored — para acompanhar o upstream, recopie de
`.agents/skills/` do repositório oficial e reaplique o namespace
`plugin-open-seo-*` no nome do diretório e no `name:` do frontmatter (é o que
`dashboard/backend/plugin_file_ops.py::_enforce_namespace` faz no install
automático).

## Licença

OpenSEO é MIT — cópia em `plugins/open-seo/LICENSE`. As skills vendored
mantêm a atribuição ao upstream no rodapé de cada `SKILL.md`.
