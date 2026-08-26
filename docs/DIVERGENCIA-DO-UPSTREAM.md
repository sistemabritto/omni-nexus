# Por que este fork divergiu do EvoNexus da Evolution Foundation

> **Upstream:** [`evolution-foundation/evo-nexus`](https://github.com/evolution-foundation/evo-nexus)
> **Este fork:** [`sistemabritto/omni-nexus`](https://github.com/sistemabritto/omni-nexus)
> **Mantido por:** [Sistema Britto](https://sistemabritto.com.br) — [@sistemabritto](https://instagram.com/sistemabritto)
> **Versão descrita:** `rc01`

Este documento existe porque "é um fork com umas mudanças" não é resposta
suficiente para quem vai operar isto em produção. São **395 commits** à frente
do upstream, e **106 deles** (27%) mexem em provider, fallback ou OmniRoute.
Essa concentração não é acidente: ela é a divergência.

---

## O problema que originou tudo

O EvoNexus upstream assume um mundo simples: existe um binário `claude`, ele
está autenticado, e quando você o chama ele responde. Todo agente, heartbeat e
rotina do workspace nasce desse pressuposto.

Esse mundo não é o mundo em que este fork roda. Aqui:

- **O binário nem sempre é `claude`.** Dependendo do provider ativo, o
  executável é `openclaude` (gateway compatível com OpenAI), `opencode` (o
  harness usado pela esteira de vídeo) ou o `claude` nativo. Cada um tem CLI,
  flags e formato de saída próprios.
- **A cota acaba.** Conta Claude com limite mensal derruba a sessão no meio de
  um job de três horas de vídeo. Sem rota alternativa, o trabalho morre.
- **O modelo se aposenta sem avisar.** Provider externo tira modelo do ar com
  `410 Gone` e tudo que apontava para ele para de responder.
- **A imagem não tem o binário que você esperava.** O `media-worker` instala
  apenas `opencode`; chamar sem pin explícito percorre a cadeia inteira
  procurando um `openclaude` que não existe naquele container.

Nenhuma dessas condições existe no ambiente de desenvolvimento do upstream, e
por isso nenhuma delas é tratada lá. Todas existem aqui, todas já derrubaram
produção, e é por isso que a camada de execução foi reescrita.

---

## 1. Camada de execução agnóstica de harness

**Arquivo:** `dashboard/backend/provider_fallback.py`

O upstream chama o CLI direto. Aqui, **nada chama CLI direto** — tudo passa por
`invoke_with_fallback()`, que resolve qual binário usar, com quais variáveis de
ambiente, com qual modelo, e o que fazer quando isso falha.

### `config/providers.json` é o mapa

Cada provider declara o binário e o ambiente que ele exige:

| Provider | `cli_command` | Papel |
|---|---|---|
| `omnirouter` | `openclaude` | **ativo** — gateway OmniRoute |
| `openrouter` | `openclaude` | fallback |
| `anthropic` | `claude` | fallback final, conta nativa |
| `opencode-go` | `opencode` | harness da esteira de vídeo |
| `nvidia` | `openclaude` | catálogo, fora da cadeia ativa |

O `active_provider` define a cadeia; `fallback_providers` define para onde cair.
Trocar de harness é editar um JSON, não reescrever chamada de agente.

### `force_provider` — o pin que a esteira de vídeo exige

`Dockerfile.media-worker` instala **só** o binário `opencode`. Sem pin, a cadeia
começa em `omnirouter`/`openclaude`, um binário que não existe ali, e falha
percorrendo a cadeia inteira até `anthropic:claude` — e o job **retenta
sozinho**, reprocessando ~4 min de transcrição por tentativa. Um job real rodou
3 retries completos antes de alguém notar.

```python
invoke_with_fallback(prompt=..., force_provider="opencode")
```

O pin sozinho não bastava: `FallbackEngine.attempts()` procurava o provider
forçado apenas **dentro da cadeia já resolvida** do `active_provider`, e
`opencode` não está no `fallback_providers` do `omnirouter`. Hoje, quando o
provider forçado existe em `providers.json` mas está fora da cadeia ativa, a
entrada é montada direto de lá. Sem isso, forçar qualquer provider fora da
cadeia do momento virava silenciosamente "No attempts made".

### Prompt grande sai do argv

Todo harness aqui recebe o prompt como argumento de linha de comando, e
`argv + envp` dividem o `ARG_MAX` do kernel (~2 MB no Linux, já parcialmente
ocupado pelo ambiente). A esteira de vídeo embute transcrições de 30 mil
palavras: estourava com `[Errno 7] Argument list too long`.

Acima de `PROMPT_ARG_SAFE_BYTES = 100_000` o prompt vai por **stdin**
(`claude --print` e `opencode run` leem stdin quando o prompt posicional é
omitido). Prompts normais seguem exatamente como antes — só o caminho raro muda.

### Erro vira resultado, não exceção

Falha de provider é `{"status": "failed", "error": ...}`, nunca uma exceção que
sobe. Um 401 no meio da cadeia tem de deixar a cadeia continuar, não derrubar o
processo do heartbeat.

### Detecção de 429 e cooldown

`is_429_error()` roda sobre stdout **e** stderr — o `opencode` escreve erro nos
dois. Um 429 põe aquele par provider:modelo em cooldown de
`DEFAULT_COOLDOWN_SECONDS = 60` e passa ao próximo, em vez de insistir.

### Teto de tempo por tentativa

`PER_ATTEMPT_TIMEOUT_CAP = 180` impede que uma tentativa travada consuma o
orçamento inteiro do job. O bot do Telegram usa um teto mais agressivo
(`TELEGRAM_PER_ATTEMPT_TIMEOUT_CAP = 45`): quem está esperando resposta no
celular não tolera três minutos de silêncio.

### Mutex entre containers

`_workspace_bash_lock` usa `flock()` num arquivo em `workspace/.locks/`. Um lock
em linha de banco não funcionaria: `dashboard.db` vive num volume montado só no
serviço do dashboard — telegram e scheduler não o enxergam, e o lock seria
per-container, coordenando nada. O volume `evonexus_workspace` está montado no
mesmo caminho nos três, então `flock()` ali é um mutex real, imposto pelo SO, e
liberado automaticamente se o processo morrer.

---

## 2. Combos de fallback com OmniRoute

**Gateway:** [OmniRoute](https://github.com/diegosouzapw/OmniRoute), embutido na
stack como serviço próprio.

O OmniRoute expõe combos `auto/*` (`auto/coding`, `auto/reasoning`, …) que
escolhem entre dezenas de modelos por trás de um endpoint só. O fork usa isso
como **primeira** camada de fallback, e mantém a cadeia de providers como
segunda. São duas camadas independentes de propósito:

```
invoke_with_fallback
   └── omnirouter (openclaude)         ← camada 1: OmniRoute escolhe o modelo
         model_chain:
           claude/claude-sonnet-5
           claude/claude-haiku-4-5-20251001
           claude/claude-opus-5
   └── openrouter (openclaude)         ← camada 2: outro gateway
   └── anthropic (claude)              ← camada 3: conta nativa
   └── opencode-go (opencode)          ← harness alternativo
```

### Por que Claude lidera o `model_chain`

Duas razões medidas em produção, não preferência:

1. **Vazamento de raciocínio.** Modelos Nemotron emitem `reasoning_content`, e o
   `openclaude` concatena esse campo à resposta. Não existe flag de supressão. O
   resultado chegava no Telegram como um monólogo interno em inglês, sem
   conclusão — exatamente o sintoma de "resposta confusa e inconclusiva". A
   correção foi tirar modelo de raciocínio da frente da cadeia.
2. **O catálogo mente.** O OmniRoute anuncia ~230 modelos; uma fração responde
   de fato. Liderar com um modelo que se sabe vivo evita pagar o custo de
   descobrir isso a cada requisição.

### `nvidia` saiu do `fallback_providers` do `omnirouter`

Decisão de 08/07/2026, reaplicada em 26/08/2026. Um fallback do OmniRoute para
NVIDIA direto **contorna o gateway**: a chamada some da telemetria do OmniRoute,
o custo não é contabilizado e a observabilidade que justifica ter gateway
desaparece justamente no momento de degradação, que é quando ela mais importa.
`nvidia` continua no catálogo de `providers.json` — só não é rota automática.

### Compressão

O OmniRoute traz uma pilha de 12 motores de compressão (RTK, Caveman,
LLMLingua-2), acionada por header `x-omniroute-compression`. Estava desligada;
hoje roda em modo empilhado RTK+Caveman. Contexto de agente é repetitivo por
natureza — é o caso em que compressão paga.

### Segredos do OmniRoute NÃO vêm do ambiente da stack

`JWT_SECRET`, `API_KEY_SECRET` e `STORAGE_ENCRYPTION_KEY` são lidos de
`/app/data/server.env`, **dentro do volume**. Definir essas variáveis no
ambiente do serviço as sobrescreve e **invalida toda API key já emitida** — o
Hermes e o Magneto desconectam com `401 AuthenticationError`. Isto está
documentado aqui porque já foi aprendido do jeito caro.

---

## 3. Self-healing do cache LKGP

**Arquivo:** `ADWs/routines/omniroute_lkgp_healer.py` · **Testes:**
`tests/goals/test_omniroute_lkgp_healer.py`

O OmniRoute guarda, por combo, qual foi o último provider/modelo que respondeu —
o *Last Known Good Provider*. Isso acelera a escolha em condição normal. O
problema: **quando o modelo cacheado se aposenta, o cache não se invalida
sozinho.** Cada requisição nova tenta primeiro o modelo morto, toma `410`, e só
então cicla pela pool inteira.

Confirmado ao vivo em 25/08/2026: `z-ai/glm-5.2`, aposentado em 21/08, ficou
preso no LKGP de `auto/coding`. Toda chamada de Magneto/Hermes que caía nesse
combo pagava a taxa de percorrer a pool antes de responder — somado ao timeout
por tentativa, o pedido inteiro falhava sem nunca alcançar um modelo vivo.

A rotina roda a cada 15 minutos e:

- **Só limpa em erro permanente.** `410`, `404`, ou mensagem citando fim de
  vida / descontinuação. Erro transitório (`429`, `5xx`) **nunca** dispara a
  limpeza — isso destruiria a utilidade do próprio cache durante um pico normal
  de uso, que é exatamente o cenário para o qual o LKGP existe.
- **É idempotente por incidente, não por tick.** Um arquivo de estado guarda a
  assinatura do erro tratado. Só o relógio decide se já foi tratado: nada de
  flag "já avisei" separada, porque `testStatus` continua `unavailable` por um
  tempo depois do clear, e a rotina limparia de novo no tick seguinte.
- **Reincidência escala para humano.** O mesmo erro voltando depois de 6h
  significa que a limpeza não resolveu — alguma outra coisa mantém o modelo
  morto no topo. Aí vale alerta, não mais uma limpeza silenciosa.

---

## 4. Fila de orquestração persistente (novidade da `rc01`)

**Arquivos:** `dashboard/backend/chat_orchestrator.py`,
`dashboard/backend/routes/orchestration.py`,
`dashboard/frontend/src/pages/Orchestration.tsx` · **Testes:**
`tests/backend/test_orchestration_jobs.py`

Um comando de orquestração disparado pelo Telegram podia levar minutos. O bot
respondia no mesmo request: se o processo reiniciasse, o trabalho sumia sem
deixar rastro, e quem pediu não tinha como saber em que pé estava.

A `rc01` persiste isso numa tabela (`orchestration_jobs`) com estágios
discretos por agente, consumida por um worker em background:

| Agente | Estágios |
|---|---|
| `ops` | pesquisa → redação → revisão |
| `projects` | planejamento → quebra de tarefas |
| `community` | análise → resposta |
| *(demais)* | execução |

Cada estágio é uma chamada `invoke_with_fallback()` — ou seja, herda a cadeia
inteira descrita acima. O resultado de um estágio alimenta o próximo, e é
gravado como checkpoint: um restart não perde o trabalho já feito.

`GET /api/orchestration-jobs` e a página `/orquestracao` no dashboard dão
visibilidade; `POST /api/orchestration-jobs/{id}/cancel` interrompe.

### O que foi corrigido antes de virar `rc01`

A primeira implementação não subia. Cada item abaixo virou teste de regressão:

- **`ModuleNotFoundError` no boot.** O blueprint importava
  `dashboard.backend.models`. O processo do dashboard sobe com
  `dashboard/backend` como cwd/WORKDIR, então o pacote `dashboard` não é
  importável de dentro dele — os outros 20 blueprints em `routes/` sempre
  usaram `from models import ...`. **O Flask inteiro morria nessa linha.**
- **Escrita em disco durante o import.** O blueprint fazia `mkdir` do diretório
  de locks em tempo de import — falha em filesystem somente-leitura e derruba a
  aplicação para proteger nada, já que `provider_fallback` cria o diretório
  quando pega o lock.
- **Chave primária vinda de variável de ambiente.** O id do job saía de
  `os.environ.get("JOB_ID")`. Com essa variável definida, todo job daquele
  container nasceria com o mesmo id e o segundo `POST` estouraria
  `IntegrityError`. Hoje é `uuid4()`.
- **Cancelamento que se desfazia sozinho.** `POST /cancel` gravava
  `status='cancelled'` e o worker seguia até o fim, sobrescrevendo com
  `'success'`. O humano via o pedido ser aceito e ignorado. Hoje o worker relê o
  status entre estágios e antes de marcar sucesso.
- **Sessão quebrada prendia o job em `running`.** Se o erro vinha de um commit,
  a sessão ficava inválida e o commit que gravaria `'failed'` também falhava.
  Hoje há `rollback()` antes.
- **A página nunca compilou.** Importava `date-fns` (não é dependência) e um
  símbolo `evo` que o SDK nunca exportou. Hoje usa `Intl.RelativeTimeFormat`
  nativo e o mesmo `fetch` das páginas vizinhas.
- **A rota não existia.** O componente estava importado em `App.tsx` sem
  `<Route>` correspondente e sem link na Sidebar — 343 linhas inalcançáveis.

---

## O que é específico daqui e o que volta para o upstream

| Camada | Volta para o upstream? |
|---|---|
| `provider_fallback.py` (harness-agnóstico, stdin, 429, mutex) | **Sim** — resolve problema genérico |
| Fila de orquestração + página | **Sim** |
| Combos OmniRoute + `model_chain` | Não — depende de gateway auto-hospedado |
| Self-healing do LKGP | Não — específico do OmniRoute |
| Esteira de conteúdo / vídeo, funis, UTM | Não — regra de negócio do Sistema Britto |
| Stacks de VPS (`*.stack.yml`) | Não — topologia própria |

O critério: **infraestrutura genérica volta, regra de negócio fica.**

---

## Onde ler mais

As regras operacionais vivem em `.claude/rules/` e são carregadas por todo
agente do workspace:

- `esteira-de-video.md` — por que `force_provider="opencode"` é obrigatório
- `esteira-de-conteudo.md` — gates humanos, CTA por funil, limite em bytes
- `routines.md` — o que é agendado de fato, e a janela perdida no redeploy
- `otp-whatsapp.md` — o endpoint que pode custar o número de WhatsApp

---

<p align="center">
  <a href="https://sistemabritto.com.br">sistemabritto.com.br</a> ·
  <a href="https://blog.sistemabritto.com.br">blog.sistemabritto.com.br</a> ·
  <a href="https://instagram.com/sistemabritto">@sistemabritto</a>
</p>
