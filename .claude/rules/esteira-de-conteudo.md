# Esteira de conteúdo — o padrão que todo agente segue

A esteira produz 3 posts por dia, 7 dias por semana, do levantamento de pauta até
o post nas redes. Ela roda sozinha; esta rule existe para que continue rodando
**do jeito certo** quando um agente precisar tocar em qualquer etapa.

Regra geral: **o padrão está no código, não no seu julgamento.** Se você vai
gerar capa, escrever artigo, escolher CTA ou propor pauta, use as funções
listadas aqui em vez de reimplementar — cada uma delas existe porque a versão
"óbvia" já saiu errada em produção pelo menos uma vez.

```
domingo   weekly_content_research  → 21 pautas na fila (status: proposta)
                                   → abre o gate do ciclo no Telegram
humano    aprova o ciclo em lote   → aprovada
06:00     daily_content_pipeline   → escreve, cria draft, gera capa, abre o gate
humano    aprova o artigo          → publica no Ghost (publicada)
automático                         → deriva X/LinkedIn/Threads, um gate cada
30 em 30 derivar_redes_pendentes   → recupera o artigo agendado que ficou órfão
```

---

## -1. Todo gate tem de PEDIR, não só travar

A esteira tem três gates humanos: o ciclo de pautas, o artigo e cada rede. Os
dois últimos sempre mandaram card no Telegram. O primeiro, até 03/08/2026, não
mandava nada: `weekly_content_research` gravava as 21 pautas em `proposta`,
criava um ticket no inbox do **@pixel** (não do Felipe) e terminava em silêncio.
A única forma de liberar era alguém lembrar de abrir `/pautas` e clicar.

O resultado é o modo de falha mais caro que existe, porque não parece falha:
**01/08 e 03/08/2026 amanheceram com a fila cheia e a esteira não produziu
artigo nenhum.** A rotina das 06:00 rodou, não achou nada `aprovada`, saiu com
código 0. Nenhum erro, nenhum alerta — só dois dias sem conteúdo.

Piorava porque o único lugar que podia avisar olhava para o lado errado:
`briefing_dados.pauta_do_dia()` consultava só `escrita` e `aprovada`, então o
Good Morning dizia **"Pauta da esteira para hoje: _nada_"** com 11 pautas
paradas esperando decisão. Hoje consulta `proposta` também.

**A regra, para qualquer gate novo:** um gate que só bloqueia não é gate, é
travamento silencioso. Se o fluxo para esperando um humano, alguma coisa tem de
chegar ao humano — e no inbox de um agente não conta.

`gate_type='pauta_ciclo'` (`routes/approvals.py`) é como isso ficou. Dois
detalhes que não podem mudar:

- **A chave de idempotência é `pauta:{ciclo}`, sem `attempt`.** Os outros gates
  reabrem de propósito a cada retentativa; este não pode, porque o catch-up de
  boot (ver `routines.md`) reexecuta o research do mesmo ciclo. Com `attempt` na
  chave, cada reexecução abriria um card novo das mesmas 21 pautas.
- **Rejeitar não descarta pauta.** O ciclo volta a ser editável em `/pautas`;
  quem descarta é `vencer`, pela data. Um "não" no card não pode apagar o
  trabalho da rodada.

Testes: `tests/goals/test_gate_de_pauta.py`.

---

## 0. Derivação das redes — o agendado é o caso que falha

Aprovar o artigo pode **publicar agora** ou **agendar**. Os dois caminhos
publicam, e só um deles passa por código nosso na hora de ir ao ar:

| Caminho | Quem deriva as redes |
|---|---|
| Publicar agora | `heartbeat_outcome._derivar_redes_em_background`, na hora |
| Agendar (`publish_at`) | **ninguém, no momento da aprovação** — o Ghost publica sozinho depois |

Em 27/07/2026 os dois artigos do dia foram agendados (13h e 18h BRT). O Ghost
publicou os dois no horário e **nenhum post de X, LinkedIn ou Threads existiu**.
Nada acusou erro: `_run_blog_publish` deriva só quando `status != "scheduled"`,
e ali o artigo ainda nem estava publicado — `distribuir` recusa post fora de
`published`, então derivar na aprovação produziria um "ignorado" silencioso.

O webhook `post.published` do Ghost cobriria o caso. Ele **não cobre**: o
trigger existe e está habilitado no Nexus, mas `trigger_executions` está vazia
desde sempre, porque o webhook nunca foi cadastrado do lado do Ghost. E não dá
para cadastrar por código: a chave de Admin API devolve
`403 NoPermissionError` no endpoint de integrações. Criar webhook exige sessão
de staff no painel. Etapa manual que ninguém repete não é garantia.

Quem fecha o buraco é **`ADWs/routines/derivar_redes_pendentes.py`**, a cada 15
minutos: lista o que o Ghost publicou nas últimas 26h e deriva o que ainda não
foi. Lógica em `ghost_social_bridge.derivar_pendentes`.

**A idempotência é `redes_ja_derivadas(post_id)`**, e ela é obrigatória: três
caminhos podem mandar derivar o mesmo artigo (gate imediato, webhook, varredor)
e sem ela cada um abriria seu próprio trio de aprovações. Ela consulta
`/api/approvals` por `publish.source_id` e conta **todos** os estados, não só
`pending` — reabrir o que o humano rejeitou é insistir num texto que ele leu e
recusou. Dois cuidados ao mexer:

- **`source_id` ≠ `publish_ref`.** O primeiro é o artigo que originou um post de
  rede; o segundo é o artigo que o gate do blog publica. Confundir faz a
  aprovação do próprio artigo parecer derivação, e as três redes são puladas
  para sempre. `routes/approvals._render_publish_preview` expõe os dois.
- **Pular a rede ANTES de `adaptar`**, nunca depois. Gerar para descartar é uma
  chamada de modelo por rede a cada 15 minutos, 96 vezes ao dia.

Testes: `tests/goals/test_derivacao_de_agendado.py`.

---

## 1. Thumbnail — nunca a mesma cara duas vezes

**Módulo:** `dashboard/backend/thumbnail_maker.py`
**Como chamar:**

```python
from thumbnail_maker import gerar, montar_prompt, variacao_de
from ghost_publisher import briefing_de_capa

var = variacao_de(n)                       # n = prioridade da pauta
brief = briefing_de_capa(post, registro=var["registro"])
erro = gerar(montar_prompt(brief["headline"], brief["hook"], brief["expressao"],
                           brief["badge"], variacao=n),
             destino, referencia=var["pose"]["arquivo"])
```

`variacao_de(n)` gira quatro eixos de uma vez: **pose** (4 fotos), **registro
facial** (6), **lado do quadro** (2) e **enquadramento** (2). Pose e registro
andam em passos diferentes, então duas capas vizinhas nunca coincidem em
nenhum dos dois, e a combinação inteira só se repete a cada 48.

**A regra do Felipe, textual:** a expressão e a pose devem ser congruentes *ou
deliberadamente incongruentes* com o texto da thumb, para quebrar padrão. O que
não pode é toda capa sair com a mesma cara. Três dos seis registros contrariam o
texto de propósito — capa que apenas confirma o título é a que o olho já
aprendeu a pular.

**Nunca:**
- Passar `referencia=` fixo, ou omitir (cai sempre na mesma foto de braços cruzados).
- Inventar fallback de expressão. O antigo `"sorriso confiante"` é exatamente o
  que fazia toda capa sair igual; hoje a expressão vazia cai no registro sorteado.
- Usar foto de `assets/thumbnail-refs/` como referência de rosto — é captura do
  canal de OUTRO criador, guardada como referência de **estilo**. As fotos reais
  estão em `workspace/social/brands/evolution-foundation/library/images/faces/`.
- Acrescentar ao `POSES` uma foto com outra pessoa no quadro: `/v1/images/edits`
  pode escolher o rosto errado, que é o erro que o módulo existe para evitar.
- Chamar `/v1/images/generations` — não aceita imagem de entrada e recusa a
  referência de rosto. É `/v1/images/edits`.

Na regeração por feedback (`ghost_social_bridge`), a variação vem do par
`(post_id, feedback)`: o mesmo feedback devolve a mesma capa — retry é
idempotente — e um feedback novo cai em outra pose. Devolver a arte anterior
depois que o autor pediu outra é a pior resposta possível ao gate.

---

## 2. CTA — todo artigo aponta para um funil real

**Módulo:** `dashboard/backend/escritor_de_artigo.py` → `funil_de(keyword)`

| Funil | URL | Assunto |
|---|---|---|
| `whatsapp` | `sistemabritto.com.br/whatsapp` | atendimento, chatbot, disparo |
| `socialjobs` | `sistemabritto.com.br/socialjobs` | instagram, tiktok, youtube, reels, conteúdo |
| `sistema` | `sistemabritto.com.br/sistema` | automação, agentes, dados, leads, vendas |

**O `/sistema` é a oferta principal desde 27/07/2026.** Ele não vende mais
"solução web sob encomenda" — vende a **call de 1h por R$ 147 que produz o
PRD** do projeto. Quem chega pedindo site entra por ali. O CTA do artigo tem de
prometer isso, e não a solução pronta: clicar esperando uma coisa e encontrar
outra é a forma mais cara de perder quem já estava interessado.

Regra explícita, nunca escolha do modelo: ele inventa CTA genérico, e CTA
genérico não converte. Na dúvida vai para `/sistema`, o guarda-chuva.

`escrever()` já anexa o CTA se o modelo esquecer, e carimba a UTM de origem no
link (`dashboard/backend/utm.py`). Sem a UTM o clique chega ao site sem dizer de
onde veio, e o painel de crescimento não consegue atribuir nada.

**Cuidado ao mexer em `funil_de`:** `tests/goals/test_research_semanal.py` confere
seed por seed que cada uma classifica no próprio funil. Quatro já estavam erradas
— `roteiro para reels` caía em `/sistema`, e `gerar leads com inteligência
artificial` caía em `/whatsapp` porque `"lead"` pertencia a ele. Palavra que
aparece nos três funis não pode ser critério de nenhum.

---

## 3. Texto — humanizado, com data certa, sem promessa vazia

**Módulo:** `dashboard/backend/escritor_de_artigo.py` → `escrever(pauta)`

O prompt já carrega:
- **`humanizer.md`** (`.claude/skills/mkt-quality-gate/experts/`) — o antídoto ao
  texto de IA. Não reescreva o prompt sem ele.
- **A data de hoje, explícita.** Sem isso o modelo escreve "2025" com convicção.
- **Mínimo de 600 palavras.** Artigo curto é recusado, não publicado torto.
- **Gancho de notícia da semana**, quando existe — é o que faz a LLM citar o artigo.
- **Proibição dos termos de marca** que não são nossos.

**Travessão é proibido, e a proibição não é só no prompt.** `sem_travessao()`
(`escritor_de_artigo.py`) roda no título, no excerpt e no HTML antes de publicar,
e em `ghost_social_bridge.limpar()` antes do corte de limite de caractere — nessa
ordem, porque trocar `—` por vírgula muda o tamanho e um post de X medido a 280
antes da troca estoura depois. O símbolo é gramatical em português; o problema é
que hoje o leitor o lê como assinatura de texto gerado, e foi a primeira coisa
que o Felipe apontou ao revisar o site em 27/07/2026. Instrução negativa no
prompt sozinha não resolve: o modelo reincide, porque encaixar aposto com
travessão é hábito de treino. Testes: `tests/goals/test_sem_travessao.py`.

**O limite de caractere da rede é medido em BYTES, e nunca se mira nele.**
`ghost_social_bridge.medida()` conta `len(texto.encode("utf-8"))` e
`teto_de(rede)` desconta 5% do limite nominal (X: 266 de 280; Threads: 475 de
500). As duas coisas existem pelo mesmo incidente: entre 28/07 e 02/08/2026,
**dez derivações do X e uma do Threads foram aprovadas no Telegram e nunca
saíram** — o Postiz devolveu `400 {"provider":"x","message":"post is too long,
please fix it"}`, a aprovação parou em `approved` sem virar `published`, e o
único registro foi um comentário no ticket. O humano aprovava e o post não
existia.

O corte não estava errado; estava certo demais. `garantir_link` calculava a
sobra para o texto final medir exatamente 280, então todo post do X saía entre
270 e 280, colado no teto — e aí qualquer divergência entre a nossa régua e a
do validador que está no caminho derruba o post inteiro. Os dados das 20
derivações registradas mostram onde a régua deles está:

| Rede | publicou até | recusou a partir de |
|---|---|---|
| X | 272 bytes | 276 bytes |
| Threads | 501 bytes | 502 bytes |

O par que só bytes explica: um post de **271 caracteres foi recusado** e um de
**272 passou** — o primeiro tinha quatro acentos (276 bytes), o segundo nenhum.
Contar caractere é otimista com português exatamente na hora em que a margem
importa. Testes: `test_ghost_social_bridge.py` (seção "o limite é medido em
bytes") e `test_publicacao_com_imagem_e_link.py`.

Artigo nasce **sempre `draft`** no Ghost (`criar_rascunho`). Quem decide se vai ao
ar é o gate no Telegram — criar já publicado tiraria do humano exatamente a
decisão que o fluxo inteiro existe para preservar.

`?source=html` é obrigatório no Ghost, tanto no create quanto no update: sem ele
a API devolve 201 e **descarta o corpo do artigo em silêncio**.

---

## 4. Temas — a semana fala de três assuntos, não de um

**Módulo:** `ADWs/routines/weekly_content_research.py`

Ordem das etapas, e o que cada uma protege:

1. **Cache primeiro** (`pauta_fila.keywords_em_cache`, 30 dias). Volume de busca
   do DataForSEO é média de 12 meses — reconsultar a mesma seed é dinheiro
   queimado para receber o mesmo número. Uma rodada típica reaproveita 24/24.
2. **Filtro de cauda longa comercial** — regex `COMPRA`/`DOMINIO`/`RUIDO`.
   Use `\b` nas siglas: `api` sem limite de palavra casava dentro de "japinha",
   e `japinha do cv instagram` (14.800/mês) virou a pauta #1.
3. **Dedupe por núcleo** (60% de sobreposição) — contra canibalização.
4. **Avaliador de ICP** (`avaliador_de_pauta.py`, nota 0-10, mínimo 6). Um modelo
   que conhece o sistemabritto.com.br julga público-alvo, coisa que regex não
   faz: deixava passar `mercado pago api` (negócio de outro) e `como postar story
   pelo pc` (consumidor final). Fail-open: se ele cair, o regex já filtrou.
5. **Rodízio de funis** (`alternar_funis`) — **obrigatório antes de contar o que
   falta**. Sem ele a seleção é pura ordem de retorno esperado, e o WhatsApp, que
   tem volume muito acima dos outros, leva os 21 slots: em 27/07/2026 foram 18 de
   21, com os três posts do mesmo dia sobre o mesmo assunto. Como o calendário
   fatia a lista em blocos de três, intercalar é o que faz cada dia nascer com um
   assunto de cada funil. Funil que esgota não segura os outros.
6. **X como reserva** (`pautas_do_x`) — quando o SEO não fecha os 21. O que está
   em alta hoje não tem histórico de volume, e é justamente a pauta que a
   concorrência ainda não escreveu.

### A fila (`dashboard/backend/pauta_fila.py`)

`gravar_ciclo(pautas)` é o único caminho de escrita na fila. Ele:

- É idempotente por `(ciclo, prioridade)`; **quem decide preservação é o slot**
  (`publish_at`), não a prioridade. Preservar por prioridade abriu buraco no
  calendário: uma pauta `escrita` no dia anterior apagou o post das 09h do dia
  seguinte, e o dia amanheceu com dois posts.
- Pauta cuja prioridade está tomada é **empurrada para a próxima livre**, nunca
  descartada.
- Trocar a keyword de uma pauta `aprovada` **devolve o status para `proposta`**.
  Aprovação é sobre um assunto concreto, não sobre uma posição no calendário.
  Regravar com a mesma keyword preserva a aprovação.
- Pauta vence em `DIAS_ATE_VENCER = 2`. Gancho de notícia morto é assunto velho.

---

## 5. Medição — o clique é o que fecha o funil

```
artigo publicado → visita com UTM → clique no CTA → lead → fechado
```

Cada seta acima é medida. A do meio faltou até 27/07/2026: `trackCta` existia
no site com endpoint e tabela prontos, e **nenhum botão a chamava** — 636
pageviews contra 1 clique registrado. A taxa de conversão do painel ficava
travada em zero, e não dava para dizer se um artigo gerava interesse.

**Convenção de UTM** (`dashboard/backend/utm.py`):

| Parâmetro | Valor | Para quê |
|---|---|---|
| `utm_source` | `blog`, `x`, `linkedin`, `threads` | de qual canal veio |
| `utm_campaign` | **slug do artigo** | qual post converteu |
| `utm_content` | rede/variação, quando houver | qual peça converteu |

`marcar()` é idempotente: link que já tem `utm_source` volta intacto. Marcar
duas vezes produziria `utm_source=blog&utm_source=x` e o analytics leria o
primeiro — origem errada com cara de origem certa.

**Como a atribuição funciona.** `cta_clicks` não guarda UTM e não precisa: o
`session_id` do clique é o mesmo do pageview de entrada, que carrega a UTM. O
endpoint `/api/admin/analytics` do site junta os dois e devolve
`attribution.bySource` e `attribution.byCampaign`. Clique sem pageview na
janela entra como `clicksUnattributed` — **nunca inventar origem para não
deixar o número feio**.

**Ao mexer no site** (`sistemabritto/site`): todo CTA novo chama
`trackCta(page, label, action)`. O terceiro argumento diz de qual seção da
página veio — sem ele o painel informa que `/whatsapp` converteu, mas não se
foi o botão do topo ou o do preço. Em CTA que leva para fora (`wa.me`), o
`track()` usa `fetch` com `keepalive`, então o registro sobrevive à navegação;
sem isso os cliques que mais convertem seriam os que nunca aparecem.

## 6. O que nunca muda

- **Nada é publicado sem gate humano.** Um gate por artigo, um por rede. A
  esteira produz e para.
- **Rotina do scheduler não escreve no SQLite direto.** O container do scheduler
  não monta `evonexus_dashboard_data`; escrever no arquivo cria um banco fantasma
  na camada efêmera, e o trabalho some no próximo redeploy. Use `sdk_client.evo`.
- **Sem dado inventado.** Vale a mesma regra do briefing de marca: número com
  origem, ou nenhum número.

## Regras relacionadas

- `artifacts.md` — relatório e documento visual vão para o Nexus (`/shares`)
- `routines.md` — o que é agendado e o que exige skill manual
- `goals.md` — como a esteira se liga a uma meta mensurável
