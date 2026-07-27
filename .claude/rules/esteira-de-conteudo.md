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
humano    aprova o ciclo em lote   → aprovada
06:00     daily_content_pipeline   → escreve, cria draft, gera capa, abre o gate
humano    aprova o artigo          → publica no Ghost (publicada)
automático                         → deriva X/LinkedIn/Threads, um gate cada
```

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

## 5. O que nunca muda

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
