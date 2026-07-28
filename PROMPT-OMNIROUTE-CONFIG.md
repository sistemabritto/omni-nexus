# Prompt — Configurar o OmniRoute com um agente (Claude Code)

Este arquivo é um **prompt pronto pra copiar e colar** num agente de código
(Claude Code, Codex CLI, ou qualquer agente com acesso a shell/HTTP) para
**auditar e otimizar um OmniRoute remoto** — o gateway de IA da stack
[Omni-Nexus](https://github.com/sistemabritto/omni-nexus#readme).

Contém a configuração de produção real da **Sistema Britto** (VPS Swarm),
incluindo **triangulação de providers, fallback hierárquico, concurrency caps,
e resiliência never-stop**.

> Mantido por [Sistema Britto](https://sistemabritto.com.br) ·
> Versão: **3.8.46+** · OmniRoute é um projeto de [Diego Souza](https://github.com/diegosouzapw/OmniRoute) (MIT)

---

## Pré-requisitos

1. **OmniRoute no ar** — dashboard em `https://omni.SEU-DOMINIO.com.br`.
2. **Access Token Admin** — seção **Access Tokens** no dashboard (formato `oma_live_...`).
3. Agente com acesso HTTP (curl) ao endpoint do OmniRoute.

---

## O prompt

````text
Você vai auditar e otimizar um gateway OmniRoute remoto via management API.
Trabalhe em etapas, SEMPRE leia o estado antes de alterar, e valide cada
mudança com chamada real.

Servidor: {{OMNIROUTE_URL}}
Access Token (scope admin): {{ADMIN_TOKEN}}

## Fatos importantes sobre a API

- Access Tokens `oma_live_...` autenticam a maioria das rotas de gerenciamento
  (`Authorization: Bearer ...`) mas NÃO servem para inferência (`/v1/*`) nem
  para `/api/settings/<sub>` (exigem sessão dashboard OU API key `sk-...`
  com scope `manage`).
- API keys de inferência (`sk-...`) são criadas via `POST /api/keys`.
- `/v1/chat/completions` do OmniRoute strema SSE por padrão — sempre mande
  `"stream": false` em testes que fazem parse do JSON.
- Rotas de lifecycle (`/api/services/*`, `/api/mcp/*`, `/api/plugins/*`)
  são loopback-only — não tente por token remoto.
- O PATCH **em lote** `/api/providers` só aceita `ids[]` + `isActive` (e exige
  `isActive` sempre, mesmo para mudar outra coisa). Mas o **`PUT
  /api/providers/{id}` existe e funciona** — é por ele que se ajusta
  `globalPriority`, `maxConcurrent`, `healthCheckInterval`, `group` e
  `rateLimitOverrides` sem tocar no dashboard. Verificado em 2026-07-28
  contra a 3.8.48; a afirmação anterior de que isso exigia a UI estava errada.
- O refresh automático de quota (`autoRefreshProviderQuotaInterval`) controla
  quanto tempo o sistema espera entre checagens de rate limit dos providers.
- O combo strategy `auto` é zero-config e usa LKGP (Last Known Good Provider):
  variantes `auto/<categoria>[:<tier>]` (coding, reasoning, fast, cheap, free,
  pro...) são anunciadas em `GET /v1/models`.

---

## Etapa 1 — Validar acesso e inventariar

1. `GET /api/cli/whoami` → confirme scope admin.
2. `GET /api/settings` → salve o JSON completo (baseline).
3. `GET /api/providers` → liste conexões e anote `testStatus` e `backoffLevel`.
4. `GET /api/monitoring/health` → veja circuit breakers abertos (devem ser 0).

## Etapa 2 — Keys nomeadas para telemetria

1. `POST /api/keys {"name":"<consumidor>-provider"}` → key de inferência
   nomeada (ex.: evonexus-provider, bot-x, ide-y).
2. `POST /api/keys {"name":"agent-manage","scopes":["manage"]}` → key admin
   para rotas `/api/settings/*`.

## Etapa 3 — Otimizações globais de resiliência (APLICAR NA ORDEM)

### 3.1 — Resetar circuit breakers

`POST /api/resilience/reset {}` → providers que estavam HALF_OPEN/OPEN
voltam a CLOSED. Isso evita que providers bons fiquem excluídos por falhas
passadas.

### 3.2 — Retry config

`PATCH /api/settings` com access token:

```json
{
  "requestRetry": 5,
  "maxRetryIntervalSec": 60,
  "autoRefreshProviderQuota": true,
  "autoRefreshProviderQuotaInterval": 120,
  "disableSessionStickiness": false,
  "debugMode": false
}
```

**requestRetry=5**: mais tentativas antes de "Maximum combo retry limit".
**maxRetryIntervalSec=60**: providers têm 1 minuto pra se recuperar.
**autoRefreshProviderQuotaInterval=120**: quota checada a cada 2 minutos.

### 3.3 — Criar combo estratégico

`POST /api/combos {"name":"NEVE-Mastery","strategy":"auto","modePack":"quality-first"}`

Este combo usa o **Auto-Combo Engine** com 12 fatores de scoring:
health(0.20), quota(0.15), costInv(0.15), latencyInv(0.12), taskFit(0.08),
stability(0.05), tierPriority(0.05), tierAffinity(0.05),
specificityMatch(0.05), contextAffinity(0.05), connectionDensity(0.05).

O modePack `quality-first` favorece taskFit(0.37) + stability(0.15) para
produção de conteúdo, coding e análise — ideal para agentes autônomos.

### 3.4 — max_concurrent por provider (via API, `PUT /api/providers/{id}`)

```bash
PUT /api/providers/{id}  {"globalPriority": 1, "maxConcurrent": 3, "isActive": true}
```

Valores de referência por conexão:

| Provider | max_concurrent | Motivo |
|----------|:--------------:|--------|
| **NVIDIA** (free) | **3** | Free tier robusto, aguenta paralelismo |
| **Claude** (OAuth) | **1** | OAuth Pro serializa por segurança |
| **Codex** (OAuth) | **1** | OAuth Plus, serializado |
| **Gemini** (API key) | **2** | Rate limit agressivo |
| **Gemini Web** (free) | **2** | Idem |
| **Nous Research** (free) | **2** | Gratuito, bom paralelismo |
| **xAI** (API key) | **2** | Estável, aceita 2 |
| **Groq** (free) | **1** | Só transcrição de áudio |
| **OpenRouter** (API key) | **1** | Quando tiver crédito |
| **Perplexity Web** (free) | **1** | Uso esporádico |

Com `maxConcurrent` setado, o OmniRoute ativa **quota-share request
serialization** — um semáforo por conexão que filtra requisições em excesso.
Isso é o que previne o erro "Maximum combo retry limit reached" causado por
5 agentes batendo no mesmo provider simultaneamente.

### 3.5 — Reativar conexões desligadas

Se encontrar conexões com `isActive: false` (ex.: Codex), ative com:
`PATCH /api/providers {"ids":["<id>"],"isActive":true}`

Para conexões `credits_exhausted` que tenham
`providerSpecificData.importFreeModelsOnly: true`, tente forçar re-teste:
`POST /api/providers/<id>/test` (se a rota existir na versão).

## Etapa 4 — Validar fim-a-fim

1. `POST /v1/chat/completions {"model":"auto","messages":[{"role":"user",
   "content":"hi"}],"max_tokens":10,"stream":false}` → HTTP 200 + headers
   `X-OmniRoute-Provider`, `X-OmniRoute-Model`.
2. `GET /v1/models` → liste variantes `auto/` anunciadas (`auto/coding`,
   `auto/fast`, `auto/cheap`, etc.).
3. Teste com `model: "auto/coding"` (bias para coding tasks).
4. Teste com `model: "nvidia/deepseek-ai/deepseek-v4-flash"` (forçar NVIDIA).

## Etapa 5 — Relatório

Entregue: tabela antes/depois com as settings alteradas, keys criadas (nome +
4 últimos chars, NUNCA a key completa), status dos circuit breakers,
conexões ativas vs. inativas, e recomendação de uso:

```
# Uso recomendado em qualquer CLI agnóstica (Hermes, OpenCode, etc.)
OPENAI_BASE_URL=https://omniroute.seudominio.com.br/v1
OPENAI_API_KEY=sk-...chave-criada-na-etapa-2

# Para coding pesado
model: "auto/coding"
# Para tasks gerais (distribui entre todos providers)
model: "auto"
# Para forçar combo criado
model: "NEVE-Mastery"
# Para forçar provider específico
model: "nvidia/deepseek-ai/deepseek-v4-flash"
model: "cc/claude-sonnet-4-6"
```

---

## Estratégia de Roteamento (triangulação)

O OmniRoute com `strategy: auto` + `modePack: quality-first` distribui
requests entre os providers ativos baseado em **12 fatores de scoring**.
O resultado prático para 5 agentes simultâneos:

```
Agente 1 → NVIDIA (deepseek-v4-flash)    [coding leve]
Agente 2 → Claude (sonnet-4-6)           [heavy task]
Agente 3 → Nous (Hermes-4-405B)          [coding pesado]
Agente 4 → xAI (Grok-4.3)               [pesquisa]
Agente 5 → Gemini (3.1-pro-preview)      [análise]
```

Se um falha (ex.: Gemini 429), redistribui automaticamente via LKGP:
```
Gemini caiu → fallback: NVIDIA (qwen3.5-122b)
NVIDIA lotado → xAI ou Nous
Tudo saturado → Codex (gratuito, última barreira)
```

### Hierarquia de fallback na prática:

1. **NVIDIA Free Tier** (deepseek, qwen, glm-5.2, nemotron) — primary
2. **Claude OAuth** (sonnet, haiku, opus) — backup + heavy reasoning
3. **Nous Research** (Hermes-4-405B/70B) — coding gratuito
4. **xAI** (Grok-4.3) — pesquisa geral
5. **Gemini/ Gemini Web** (3.1-pro, 3.5-flash) — análise
6. **Codex** (gratuito, OAuth Plus) — última barreira
7. **Groq** (exclusivo para transcrição de áudio)
8. **OpenRouter** (quando recarregar créditos)
9. **Perplexity Web** (pesquisa especializada)

---

## Estratégia de Resiliência (3 camadas)

### Camada 1 — Provider Circuit Breaker
- OAuth: degrada em 5 falhas, abre em 8, reset 60s
- API key: degrada em 7, abre em 12, reset 30s
- Providers marcados OPEN são pulados pelo combo routing

### Camada 2 — Connection Cooldown (account-level)
- 429 → `rateLimitedUntil` com backoff exponencial
- `baseCooldownMs * 2 ** failureIndex`
- Providers OAuth com quota reset detectam automaticamente via refresh

### Camada 3 — Model Lockout (model-level)
- Modelos específicos com 403/404/429 entram em lockout individual
- `baseCooldownMs=120s`, `maxCooldownMs=30min`
- Habilitar no Dashboard → Settings → Model Lockout

---

## Regras de segurança

- NÃO altere: requireLogin, senhas, JWT/API secrets, portas, proxy global.
- NÃO reinicie serviços nem chame rotas de lifecycle.
- NÃO imprima keys/tokens completos no relatório.
- Toda mudança deve ser reversível com um único PATCH/PUT (documente o valor anterior).
- `rateLimitProtection` e `autoLearn` não estão na whitelist do PUT (400 /
  "No valid fields to update") — esses dois seguem sendo só pelo dashboard.
- `priority` é aceito e ecoado na resposta, mas **não persiste** na conexão:
  o campo que ordena providers é `globalPriority`.
````

---

## Auditoria de 2026-07-28 — o catálogo mente, teste modelo a modelo

Rodada real no gateway de produção (3.8.48), com um achado que muda o roteiro
acima: **`GET /v1/models` anuncia 230 modelos e a maioria não responde.** Dos
34 candidatos testados um a um com uma chamada real, **19 funcionaram**.

### O que responde (latência medida)

| Conta | Modelos vivos | Latência |
|---|---|---|
| `cc` (Claude OAuth) | `claude-sonnet-5`, `claude-sonnet-4-6`, `claude-opus-4-8`, `claude-haiku-4-5-20251001` | 1,6–2,8s |
| `cx` (Codex / ChatGPT Plus) | `gpt-5.5`, `-xhigh`, `-high`, `-medium`, `-low`, `gpt-5.6-terra-high`, `gpt-5.6-luna-high` | 1,0–12,3s |
| `nvidia` | `deepseek-ai/deepseek-v4-flash`, `nvidia/nemotron-3-super-120b-a12b`, `z-ai/glm-5.2` | 0,5–3,7s |
| `xai` | `grok-4.3` | 1,4s |
| `gemini` | `gemini-3-flash-preview` | 1,3s |

### O que não responde, e por quê

| Sintoma | Onde | Causa |
|---|---|---|
| **400** | `cx/gpt-5.6-sol*`, `cx/gpt-5.3-codex-spark` | *"not supported when using Codex with a ChatGPT account"* — são modelos de API paga. A família `terra`/`luna` e toda a 5.5 funcionam |
| **403** | `nous/*`, `groq/*` | bloqueio de **Cloudflare**, não credencial — e custa 15,7s por tentativa |
| **410 Gone** | `nvidia/qwen/qwen3.5-*` | saíram do catálogo da NVIDIA sem sair da listagem |
| **404** | `nvidia/…/devstral-2`, `moonshotai/kimi-k2.6` | idem |
| **503** | `gweb/*` | instabilidade do Gemini Web |
| **timeout 40s** | `deepseek-v4-pro`, `gemini-3.1-pro-preview` | os dois "pro" da lista |

**A consequência prática:** montar combo a partir da listagem é montar uma
cadeia que gasta retry em modelo morto. Teste cada membro com uma chamada de
`max_tokens: 16` antes de colocá-lo na cadeia — leva minutos e é a diferença
entre uma cadeia que rotaciona e uma que trava. Cuidado especial com o prefixo:
o Claude Code é `cc/`, não `claude/` nem `tllm/` (esse dá 403).

### Estratégias do combo, medidas

O campo `strategy` aceita: `priority`, `weighted`, `round-robin`,
`context-relay`, `fill-first`, `p2c`, `random`, `least-used`, `cost-optimized`,
`reset-aware`, `reset-window`, `headroom`, `strict-random`, `auto`, `lkgp`,
`context-optimized`, `fusion`, `pipeline`.

Com membros validados, 6 chamadas cada:

| Estratégia | Comportamento observado |
|---|---|
| **`least-used`** | reveza entre contas distintas — **triangulação real** |
| `p2c` | distribui, mas em rajadas no mesmo modelo |
| `headroom` | 100% no mais rápido; eficiente, sem distribuir |
| `priority` | 100% num só (segue a prioridade da **conexão**, não a ordem da lista) |
| `auto` | distribui mas **ignora os membros** e escolhe entre os 230 |

`auto` num combo populado é o pior dos dois mundos: você lista os modelos e ele
não os usa. Para cadeia controlada, `least-used`.

### A configuração que ficou em produção

Combo `NEVE-Mastery`, `strategy: least-used`, 9 membros cobrindo 5 contas:

```
cc/claude-sonnet-5 · cx/gpt-5.6-terra-high · nvidia/deepseek-ai/deepseek-v4-flash
xai/grok-4.3 · gemini/gemini-3-flash-preview · cc/claude-haiku-4-5-20251001
cx/gpt-5.5-medium · nvidia/z-ai/glm-5.2 · nvidia/nvidia/nemotron-3-super-120b-a12b
```

Prioridade e paralelismo por conexão, todos via `PUT /api/providers/{id}`:

| Conexão | globalPriority | maxConcurrent | Ativa |
|---|:---:|:---:|:---:|
| nvidia | 1 | 3 | sim |
| claude / codex | 2 | 1 | sim |
| xai / gemini | 3 | 2 | sim |
| gemini-web | 6 | 2 | sim (503 hoje, reserva) |
| perplexity-web | 7 | 1 | sim (fora do combo) |
| nous-research / groq | 9 | 1 | **não** — 403 Cloudflare custa 15,7s por tentativa |
| openrouter | 9 | 1 | **não** — sem crédito |

Validação: 12 chamadas seguidas, **12× HTTP 200**, 1,1–2,9s, revezando entre
`claude-sonnet-5`, `claude-haiku-4-5`, `gpt-5.6-terra-high` e `gpt-5.5-medium`.

### Pegadinhas da API confirmadas nesta rodada

- Login de sessão: `POST /api/auth/login {"password": "..."}` devolve cookie
  `auth_token`. As rotas de gestão aceitam esse cookie — **não é preciso access
  token** para auditar.
- `PUT /api/providers/{id}` aceita e persiste: `globalPriority`,
  `maxConcurrent`, `healthCheckInterval`, `group`, `rateLimitOverrides`
  (`{rpm,tpm,tpd,minTime}`), `isActive`.
- `priority` é aceito e **ecoado na resposta**, mas não persiste — quem ordena
  providers é `globalPriority`. Conferir sempre com um GET depois do PUT.
- `rateLimitProtection` e `autoLearn` devolvem 400 *"No valid fields to update"*
  — não estão na whitelist.
- `PUT /api/combos/{id}` aceita `models` como **string** `"provider/modelo"` e
  normaliza para objeto. Passar objeto dá `COMBO_002`.
- `POST /api/resilience/reset {}` devolve quantos breakers reabriu — nesta
  rodada foram 4 na primeira passada e 3 na segunda, todos abertos em silêncio.

## Referências

- [OmniRoute Auto-Combo Docs](https://omni.workflowapi.com.br/docs/routing/AUTO-COMBO)
- [OmniRoute Resilience Guide](https://omni.workflowapi.com.br/docs/architecture/RESILIENCE_GUIDE)
- [OmniRoute Architecture](https://omni.workflowapi.com.br/docs/architecture/ARCHITECTURE)
- [README do Omni-Nexus](README.md)
- [Stack de exemplo na VPS](evonexus-vps.stack.example.yml)