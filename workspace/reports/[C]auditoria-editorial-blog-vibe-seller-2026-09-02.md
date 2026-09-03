---
title: Auditoria editorial do blog — linha Vibe Seller
date: 2026-09-02
status: concluida
classification: interno
escopo: blog.sistemabritto.com.br (92 posts, 2 páginas, 18 tags, 1 autor)
metodo: leitura via Ghost Admin API + Content API + HTML público, somente leitura
---

# Resumo executivo

O blog publica bem e converte mal, e o motivo não é qualidade de texto: é
**arquitetura**. Em 76 artigos publicados não existe um único link interno, um
único caso real, uma única menção à tese, e a página de autor do Felipe está
**quebrada em produção**. O blog é hoje, com precisão técnica, o que a tese diz
para não ser: um catálogo de ferramentas de IA bem escrito.

Três achados mudam a ordem de prioridade de tudo o que vem depois:

1. **O `robots.txt` bloqueia GPTBot, ClaudeBot, Google-Extended, CCBot,
   Bytespider, Applebot-Extended, meta-externalagent e Amazonbot.** A Fase 6
   (GEO / AI Search) não está fraca: está **estruturalmente impossível** hoje.
   Nenhum trabalho de conteúdo muda isso; é uma chave no Cloudflare.
2. **A causa raiz é o prompt da esteira, não os artigos.** Ele descrevia a
   empresa como "vende automação e operação com IA para donos de empresa", e o
   blog é a saída fiel disso. Reescrever artigo por artigo sem corrigir o prompt
   reconstrói o mesmo blog em 25 dias, a 3 posts por dia.
3. **A página `/author/fsbritto/` exibe uma mensagem de erro do tema como H1** e
   está no sitemap. É o ativo de autoridade mais barato de arrumar e o único que
   o Google usa para saber quem assina 76 artigos.

O que foi corrigido nesta sessão foi a causa raiz (código, em branch, com
testes). O que depende de aprovação humana ou de acesso que a API não dá está
listado, sem meia-correção.

---

# Fase 1 — Inventário

Fonte: `GET /ghost/api/admin/posts/` com `status:all`, `formats=html,plaintext`,
em 02/09/2026. Inventário completo, campo a campo, em
`[C]inventario-artigos-blog-2026-09-02.csv` (92 linhas).

| Recorte | Valor |
|---|---:|
| Posts totais | 92 |
| Publicados | 76 |
| Rascunhos parados | 16 |
| Páginas | 2 |
| Tags cadastradas | 18 |
| Tags com pelo menos 1 post | 7 |
| Autores | 1 |

**Concentração temporal:** 56 dos 76 publicados saíram em agosto/2026, 15 em
julho. O blog tem, na prática, dois meses de vida útil de conteúdo e três posts
órfãos anteriores (nov/2025, mai/2026, jun/2026).

**Volume de texto:** mediana de 1.501 palavras, mínimo 380, máximo 2.479. Seis
artigos abaixo de 800 palavras. Volume não é o problema.

## Cobertura de campos (publicados)

| Campo | Preenchido |
|---|---:|
| `feature_image` | 76/76 |
| `custom_excerpt` | 74/76 |
| `meta_description` | **2/76** |
| `meta_title` | **1/76** |
| `tags` | **2/76** |
| `canonical_url` | 0/76 |
| Links internos para outro post | **0/76** |

## Classificação

| Classe | Qtd | Critério |
|---|---:|---|
| UPDATE | 72 | reposicionar para a tese, adicionar prova e links internos |
| MERGE | 4 | par duplicado; fundir no canônico e redirecionar 301 |
| DRAFT-REVIEW | 16 | rascunho parado; decidir reposicionar ou descartar |
| KEEP | 0 | nenhum artigo, hoje, já está na linha editorial correta |
| NOINDEX / DELETE | 0 | **nenhum artigo foi marcado para exclusão** |

Nenhum artigo foi classificado como ruim por ter poucos cliques, conforme a
regra da sessão. Aliás, não seria possível: não há dado de tráfego disponível
(ver Limitações). A classificação é por **aderência à tese e integridade
técnica**, não por desempenho.

Os 4 MERGE são pares de duplicação quase literal, com o canônico proposto:

| Descartar (301 →) | Manter |
|---|---|
| `...e-mail-marketing-personalizado...-2` | `...e-mail-marketing-personalizado...` |
| `make-e-zapier...qual-vale-mais-a-pena...` | `make-e-zapier...qual-escolher...` |
| `como-agendar-post-no-instagram-pelo-pc...passo-a-passo-sem-gambiarra` | `...sem-depender-do-celular` |
| `como-automatizar-o-whatsapp-de-graca...sem-depender-de-agencia-ou-programador` | `...sem-virar-refem-de-ferramenta` |

---

# Fase 2 — Diagnóstico

## 2.1 O blog ainda parece um blog genérico de ferramentas de IA?

**EVIDÊNCIA. Sim, e é mensurável.** Busca literal no corpo dos 76 artigos:

| Termo procurado | Artigos que contêm |
|---|---:|
| "vibe seller" / "vibe coder" / "vibe cod" | **0** |
| JURISMART | **0** |
| Voice Dream | **0** |
| Omni Nexus / EvoNexus | **0** |
| Laboratório de Insights | 2 (menção incidental, não como caso) |
| equity | **0** |
| valuation | **0** |
| licenciamento | **0** |
| comoditização | **0** |
| moat | **0** |
| "build vs buy" / "build ou buy" | **0** |
| "Felipe" | **1** |

Um blog cuja tese é "Vibe Coder constrói, Vibe Seller monetiza" não menciona a
tese em nenhum dos 76 artigos e menciona o nome do fundador uma vez.

**EVIDÊNCIA complementar:** os domínios mais linkados a partir do blog são
`agendor.com.br` (20), `automationanywhere.com` (16), `pipefy.com` (12),
`zapier.com` (10) e `make.com` (8). O blog empresta autoridade a catálogos de
ferramenta e não empresta nenhuma a si mesmo.

## 2.2 Quanto conteúdo existe em cada eixo

Duas leituras, deliberadamente separadas, porque elas discordam e a diferença é
o diagnóstico:

**Leitura de superfície (HIPÓTESE)** — classificação por vocabulário de título e
H2, no CSV:

| Eixo | Artigos | % |
|---|---:|---:|
| RASTREAR | 35 | 46% |
| FERRAMENTA / TOPO DE FUNIL | 20 | 26% |
| VIBE CODAR | 19 | 25% |
| MONETIZAR | 2 | 3% |
| CASE / BUILD IN PUBLIC | 0 | 0% |
| FORA DA TESE | 0 | 0% |

**Leitura substantiva (EVIDÊNCIA)** — um artigo só está em RASTREAR se ensina a
**encontrar** o dinheiro mal resolvido, e só está em MONETIZAR se diz **quem
captura** o valor:

| Eixo | Artigos |
|---|---:|
| RASTREAR de verdade | ~0 |
| VIBE CODAR de verdade | ~0 (nenhum mostra construção real) |
| MONETIZAR de verdade | ~0 |
| CASE / BUILD IN PUBLIC | **1** |

O único artigo de build in public do blog inteiro é
`como-refiz-nosso-site-em-1-dia-com-hermes-agent-e-atingi-99-de-performance`
(13/05/2026, 380 palavras). É o artigo mais curto do blog e o único que conta
uma história real.

Os 46% de "RASTREAR" da leitura de superfície são, quase todos, títulos do tipo
"quanto custa X" e "vale a pena X". Isso é **intenção comercial de compra de
ferramenta**, não rastreamento de oportunidade. O eixo parece cheio porque o
vocabulário coincide; ele está vazio.

## 2.3 Quais artigos atraem atenção mas não intenção

**OPINIÃO fundamentada, não evidência** — sem dado de tráfego, o julgamento é
por formato. Os candidatos são os 20 artigos de FERRAMENTA/TOPO cujo título é
sobre um produto de terceiro (`whatsapp business`, `make e zapier`,
`google workspace`, `meta ads`, `whatsapp web login`). Eles respondem uma
dúvida operacional que termina em si mesma: o leitor resolve o problema e vai
embora. É a mesma leitura que a auditoria de Growth fez do Reel de melhor
desempenho, que prometia CRM grátis.

## 2.4 Quais artigos poderiam levar a uma oferta

Todos os 76 já têm CTA — este é o único ponto em que a esteira acertou:

| Destino | Artigos |
|---|---:|
| `/whatsapp` | 35 |
| `/sistema` | 31 |
| `/socialjobs` | 8 |
| `/hermes` | 1 |
| sem CTA | 1 |

71 dos 79 links de oferta carregam UTM. **EVIDÊNCIA de lacuna:** `/vps` e
`/zapclub` existem, estão na navegação do site e receberam **0 links em 76
artigos** — havia 6 artigos com assunto de infraestrutura mandando o leitor
para a call de PRD.

## 2.5 Onde falta o quê

| Falta | Estado medido |
|---|---|
| Histórias reais | 1 artigo em 76 |
| Prova / dados próprios | 0 artigos |
| Experiência do fundador | 1 menção ao nome em 76 |
| Build vs buy | 0 artigos |
| Moat / defensabilidade | 0 artigos |
| Risco de comoditização | 0 artigos |
| CTA | presente em 75/76 (único item saudável) |
| Links internos | 0 em 76 |

## 2.6 Existe canibalização?

**EVIDÊNCIA. Sim: 13 pares** com sobreposição de núcleo semântico ≥ 62%, sendo
1 par com sobreposição total (100%) e 3 pares acima de 75%. Detalhe por par no
CSV, coluna `canibaliza_com`. Quatro pares são duplicação quase literal e viram
MERGE; os demais pedem diferenciação de ângulo, não fusão.

## 2.7 Para onde os artigos deveriam apontar

`/vibe-seller` **não existe** (404 verificado). Também não existem `/cases`,
`/sobre` nem `/diagnostico`. Existem e funcionam: `/whatsapp`, `/socialjobs`,
`/sistema`, `/vps`, `/zapclub`, `/links`. **Nenhum CTA novo foi apontado para
URL inexistente**, e a criação do hub `/vibe-seller` é proposta, não executada.

---

# Fase 3 — Arquitetura editorial

## Matriz de posicionamento

| | Ferramenta (o que qualquer LLM responde) | Operação (o que só quem opera responde) |
|---|---|---|
| **Atenção** | onde o blog está hoje: 20 artigos de produto de terceiro | topo com dor econômica nomeada |
| **Intenção** | "quanto custa X" sem dizer o que X evita perder | RASTREAR: a conta que o leitor refaz com os números dele |
| **Compra** | CTA presente, promessa genérica | MONETIZAR: quem captura o valor, com caso real |

## Clusters

### Pilar 1 — RASTREAR oportunidades

- **Intenção:** o leitor suspeita que perde dinheiro e não sabe onde.
- **Público:** dono de PME e head de operação com processo já rodando.
- **Funil:** topo qualificado → meio.
- **URL pilar (a criar):** `/tag/rastrear` + artigo âncora "Onde a sua operação
  perde dinheiro sem aparecer no caixa".
- **Existentes reaproveitáveis:** os ~10 artigos "quanto custa" e "como medir"
  (`quanto-custa-chatbot-de-ia-para-empresa-em-2026-na-pratica`,
  `como-medir-resultado-de-chatbot-sem-se-enganar-com-metrica-bonita`,
  `como-reduzir-custo-de-atendimento-...`), reescritos para começar pela conta.
- **Lacunas:** nenhum artigo ensina a *encontrar* o problema; todos assumem que
  o leitor já escolheu a solução.
- **CTA / oferta:** `/sistema` (call de diagnóstico que produz o PRD).
- **Evidência necessária:** a conta de guardanapo tem de ser refazível pelo
  leitor. Sem número inventado.
- **Canibalização:** alta entre os "quanto custa"; diferenciar por vertical.
- **Prioridade:** P0. É o eixo que falta e o que qualifica o resto.

### Pilar 2 — VIBE CODAR

- **Intenção:** o leitor decidiu resolver e quer saber se monta ou compra.
- **Público:** quem tem alguém técnico, ou coragem de ter.
- **Funil:** meio.
- **URL pilar:** `/tag/vibe-codar`.
- **Existentes:** os 19 "como criar / como integrar / como automatizar".
- **Lacunas:** **build vs buy (0), custo de manter (0), moat (0)**. Todo artigo
  ensina a montar e nenhum diz quanto custa manter de pé.
- **CTA:** `/sistema` para escopo, `/vps` para infraestrutura.
- **Risco:** é o eixo mais fácil de escrever e o mais comoditizado. Sem a
  camada de decisão, compete com a documentação oficial da ferramenta.
- **Prioridade:** P1.

### Pilar 3 — MONETIZAR

- **Intenção:** o leitor construiu (ou comprou) e não vira dinheiro.
- **Funil:** meio → fundo.
- **URL pilar:** `/tag/monetizar`.
- **Existentes:** 2 artigos, ambos sobre conversão de página.
- **Lacunas:** receita recuperada, margem, licenciamento, propriedade
  intelectual, equity, valuation, parceria. **Eixo praticamente inexistente e é
  a metade da tese.**
- **CTA:** `/sistema`, `/zapclub`.
- **Prioridade:** P0 por lacuna, P1 por dificuldade — exige o caso real.

### Pilar 4 — CASES / BUILD IN PUBLIC

- **Intenção:** o leitor quer saber se quem escreve já fez.
- **Funil:** atravessa todos; é o que sustenta E-E-A-T e citação por LLM.
- **URL pilar:** `/tag/cases`.
- **Existentes:** 1 (`como-refiz-nosso-site-em-1-dia-com-hermes-agent...`).
- **Matéria-prima disponível e não usada:** Laboratório de Insights (~70
  usuários, unit economics que não fechou, sem retenção na renovação),
  JURISMART (diferenciação comprimida pelo ChatGPT antes de capturar mercado),
  Voice Dream (seed informado pelo fundador), Omni Nexus (o sistema que escreve
  este blog).
- **Prioridade:** P0. É o ativo mais barato: o material já existe e não precisa
  de pesquisa.

---

# Fase 4 — Roadmap de 90 dias

Prioridade por lacuna × custo de produção × distância da oferta. **Nenhum
artigo foi publicado, agendado ou criado como rascunho no Ghost.**

## Top 10 oportunidades

| # | Pauta | Pilar | P | Por que agora |
|---|---|---|---|---|
| 1 | Onde a sua operação perde dinheiro sem aparecer no caixa | RASTREAR | P0 | o eixo inteiro está vazio; é o artigo âncora da tese |
| 2 | JURISMART: por que a diferenciação evaporou quando o ChatGPT popularizou | CASE | P0 | caso real pronto; ensina comoditização, que tem 0 artigos |
| 3 | Vibe Coder constrói, Vibe Seller monetiza: a diferença que decide se você fica rico | MONETIZAR | P0 | resposta canônica para a pergunta de definição; hub de GEO |
| 4 | Laboratório de Insights: 70 usuários e por que isso não era um negócio | CASE | P0 | fracasso real ensina unit economics melhor que teoria |
| 5 | Build ou buy: quando montar sai mais caro que assinar | VIBE CODAR | P0 | 0 artigos hoje; é a decisão que antecede toda pauta do eixo |
| 6 | Quanto custa manter de pé o que você automatizou | VIBE CODAR | P1 | 19 artigos ensinam a montar, nenhum a manter |
| 7 | Como transformar automação em margem, não em custo escondido | MONETIZAR | P1 | fecha o loop dos artigos de automação existentes |
| 8 | O risco de comoditização: como saber se a sua solução tem prazo de validade | MONETIZAR | P1 | 0 artigos; conecta JURISMART à decisão do leitor |
| 9 | Como monetizar tecnologia com equity em vez de mensalidade | MONETIZAR | P2 | usa Voice Dream; assunto que ninguém escreve em pt-BR |
| 10 | Omni Nexus por dentro: o sistema que escreve este blog | CASE | P2 | build in public com prova verificável no próprio blog |

## Brief padrão (aplica-se às 10)

Cada brief entregue no roadmap carrega, no formato que a esteira já consome:
título provisório, pergunta que responde, intenção, promessa, tese, outline em
H2 (cada H2 é pergunta), dados e provas necessários, fontes primárias, caso
relacionado, links internos de origem e destino, CTA, oferta, estágio de funil e
prioridade. O gerador desses campos é o próprio `montar_prompt`, agora com o
pilar e a lista de casos reais embutidos.

## Cadência sugerida (90 dias, sem aumentar volume)

| Janela | Foco | Entrega |
|---|---|---|
| Dias 1-15 | desbloqueio técnico + os 4 MERGE + página de autor | nenhum artigo novo |
| Dias 16-45 | Top 10, na ordem acima | 10 artigos âncora |
| Dias 46-75 | reescrita dos 20 FERRAMENTA/TOPO com camada de decisão | 20 UPDATE |
| Dias 76-90 | links internos retroativos + revisão dos 16 rascunhos | consolidação |

**Não** propus dezenas de pautas genéricas. A esteira já produz 21 por semana; o
problema nunca foi volume.

---

# Fase 5 — Melhorias de alto impacto

## Implementado nesta sessão (código, branch, testes)

Ver seção "Alterações" abaixo. Resumo: a causa raiz — o prompt da esteira — foi
reposicionada para a tese, com pilar por código, casos reais fechados,
metadados obrigatórios, links internos e dois funis que faltavam.

## Executado em 03/09/2026, com autorização do Felipe

Backup do estado anterior (92 posts com HTML completo, páginas, tags e autor)
em `workspace/reports/backups/ghost-2026-09-02/`. Todas as escritas foram
verificadas contra ele.

| # | O que | Resultado |
|---|---|---|
| 1 | Página `/about/` reescrita | era o placeholder default do Ghost, em inglês, assinado "Workflow API Studio". Agora é *Sobre a Sistema Britto e o Vibe Seller*, 474 palavras, com a tese, os quatro casos reais e as cinco ofertas. Slug `about` preservado. |
| 2 | Tags de pilar criadas | `rastrear`, `vibe-codar`, `monetizar`, `cases`, com descrição. |
| 3 | Taxonomia aplicada aos 76 posts | de 2 para **76** posts com tag. Pilar sempre em primeiro. Tag que já existia no post foi preservada. |
| 4 | `meta_title` | de 1 para **25**. Só onde há corte em fronteira natural: título mutilado é pior que campo vazio, porque sem ele o buscador recebe a frase inteira. |
| 5 | `meta_description` | de 2 para **74**, a partir do `custom_excerpt` que cada artigo já tinha. Nenhum texto novo foi inventado. |
| 6 | `canonical_url` nos 4 duplicados | aponta para o canônico. É o sinal correto quando não há 301 disponível, e não exige tocar em slug. |
| 7 | Links internos | de **0 para 32**, inseridos só onde a âncora já existia no texto do artigo. |

**Invariante verificado em toda escrita:** o texto lido pelo humano tem de
continuar idêntico. A comparação contra o backup, ao final, dá **0 posts com
texto alterado**, 76 ainda publicados, todos os slugs e `published_at`
preservados. O guard barrou 11 escritas na primeira passada; eram falso
positivo meu (envolver `chatbot,` num link cria espaço antes da vírgula), a
normalização foi corrigida e as 11 entraram depois.

## Ainda bloqueado (o token de API não tem permissão)

Sondagem de permissões do token de integração, em 03/09/2026:

| Endpoint | Resultado |
|---|---|
| posts, pages, tags | **200** — foi o que permitiu tudo acima |
| `PUT /users/{id}/` (bio do autor) | **403** `NoPermissionError` |
| `PUT /settings/` (navegação, timezone, twitter) | **403** |
| `GET /themes/` e download | **403** |
| `GET /redirects/download/` | **403** |

Nenhuma credencial de Cloudflare existe no workspace (`.env`, `.env.example`,
`config/`, stacks), então o `robots.txt` também não é alcançável por aqui.

## O bloqueio que ficou maior do que parecia

**O tema está quebrado em `tag.hbs` E em `author.hbs`, com o mesmo erro:**

```
[tag.hbs] The {{pagination}} helper was used outside of a paginated context.
[author.hbs] The {{pagination}} helper was used outside of a paginated context.
```

`/tag/rastrear/` e `/author/fsbritto/` devolvem **HTTP 400** e exibem a
mensagem de erro como H1. Consequência direta: **a taxonomia está correta no
dado, mas as páginas de pilar não abrem**, e a navegação por pilar não pode ser
publicada até isso ser consertado. Como o `Disallow` já bloqueia os crawlers de
IA e o 400 impede indexação, não há dano de ranking — há trabalho parado.

Isto não pôde ser corrigido nem contornado: o download do tema é 403, então não
existe backup, e a regra desta sessão é não alterar tema sem backup.

## Pendente para quem tem acesso ao painel (runbook)

Em ordem de impacto. Os cinco primeiros são cliques, não projetos.

### 1. Liberar os crawlers de IA (Cloudflare) — maior impacto isolado

Painel do Cloudflare → domínio `sistemabritto.com.br` → **AI Crawl Control**
(antigo *AI Audit* / *Bots*) → desativar o bloqueio para os agentes de
**resposta**: `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`.

Mantenha `Content-Signal: ai-train=no`. São dois trade-offs diferentes hoje
presos na mesma chave: `ai-train` protege o conteúdo de virar treino;
`Disallow` a esses agentes impede a **citação em resposta**, que é o objetivo
declarado da Fase 6. Enquanto estiver como está, todo trabalho de GEO rende
zero.

Como conferir depois: `curl -sL https://blog.sistemabritto.com.br/robots.txt`
não deve mais listar `GPTBot` sob `Disallow: /`.

### 2. Corrigir o tema (`tag.hbs` e `author.hbs`)

Ghost admin → **Design → Change theme → Download** o tema `sistema-britto`
(guarde o zip: é o backup que a API não deixa fazer). Nos dois arquivos, o
`{{pagination}}` precisa estar dentro do bloco `{{#foreach posts}}` /
`{{/foreach}}` da coleção, ou o `routes.yaml` precisa declarar a taxonomia
como coleção paginada.

Destrava de uma vez: as páginas de pilar, a página de autor e a navegação por
pilar do item 4.

### 3. Escrever a bio do autor

Ghost admin → **Settings → Staff → Felipe Britto**. Hoje `bio` e
`meta_description` estão vazios, e é isso que deixa o `Person` do JSON-LD sem
`description`. Sugestão, alinhada à fonte de verdade e sem número novo:

> Felipe Britto rastreia oportunidades de negócio, vibe coda a solução quando
> faz sentido e encontra a forma de capturar o valor. Veio de marketing e
> vendas, e constrói a partir do problema comercial, não da tecnologia.
> Fundador da Sistema Britto.

### 4. Navegação por pilar

**Só depois do item 2**, senão os itens do menu levam a páginas com erro.
Ghost admin → **Settings → Navigation**:

| Label | URL |
|---|---|
| Rastrear | `/tag/rastrear/` |
| Vibe Codar | `/tag/vibe-codar/` |
| Monetizar | `/tag/monetizar/` |
| Sobre | `/about/` |
| Site | `https://www.sistemabritto.com.br/` |

E em **secondary navigation**, remover o "Sign up": `members_signup_access`
está em `none`, então o botão abre um portal que não aceita ninguém.

### 5. Duas settings erradas

Ghost admin → **Settings → General**:

- `timezone` está em `America/Argentina/Buenos_Aires`; o certo é
  `America/Sao_Paulo`. Os dois estão em UTC-3 hoje e nenhum usa horário de
  verão, então a troca **não desloca** nenhum agendamento existente da esteira.
- `twitter` está em `@ghost`, o placeholder de fábrica.
- `lang` está vazio; o certo é `pt-BR` (o HTML já sai correto pelo tema, mas o
  campo alimenta o feed e o e-mail).

### 6. 301 dos 4 duplicados (opcional)

`canonical_url` já resolve o sinal para o buscador. Se quiser o 301 de fato:
Ghost admin → **Settings → Advanced → Redirects → Download/Upload**, e
acrescentar as quatro entradas ao `redirects.json`. A API recusa esse endpoint
para token de integração.

### 7. No repositório `sistemabritto/site` (não clonado nesta máquina)

- Criar o hub `/vibe-seller` (hoje 404). Enquanto não existir, o canônico da
  tese é o artigo #3 do roadmap.
- Atualizar `llms.txt`: descreve a empresa como "parceiro de implementação",
  sem a tese Rastrear → Vibe Codar → Monetizar.

**Nenhum slug publicado foi alterado. Nenhum artigo foi publicado, despublicado
ou apagado, e nenhum texto de artigo foi reescrito.** As escritas de 03/09 nos
76 posts mexeram em tags, `meta_title`, `meta_description`, `canonical_url` e na
inserção de link em texto que já existia — verificado contra o backup, com 0
posts de texto alterado.

---

# Fase 6 — GEO / AI Search

## O bloqueio que precede tudo

`https://blog.sistemabritto.com.br/robots.txt`, verificado em 02/09/2026:

```
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /

User-agent: Amazonbot            Disallow: /
User-agent: Applebot-Extended    Disallow: /
User-agent: Bytespider           Disallow: /
User-agent: CCBot                Disallow: /
User-agent: ClaudeBot            Disallow: /
User-agent: Google-Extended      Disallow: /
User-agent: GPTBot               Disallow: /
User-agent: meta-externalagent   Disallow: /
```

**EVIDÊNCIA:** o blog está fechado para todos os principais crawlers de IA. O
bloco vem antes das diretivas do próprio Ghost, o que indica origem no
Cloudflare (política de sinais de conteúdo / bloqueio de crawlers de IA), não no
tema nem no CMS.

**Consequência:** qualquer investimento em "ser citado por LLM" rende zero
enquanto isso estiver de pé. `Content-Signal: search=yes` preserva a busca
tradicional, então o SEO clássico não está afetado.

**Decisão que é do Felipe, não minha:** `ai-train=no` protege o conteúdo de
treino; `Disallow` a GPTBot/ClaudeBot também impede a **citação em resposta**,
que é o objetivo declarado da Fase 6. Os dois não são o mesmo trade-off e hoje
estão amarrados na mesma chave. Recomendação: liberar os agentes de *resposta*
(GPTBot, ClaudeBot, PerplexityBot) mantendo `ai-train=no`.

## As nove perguntas da Fase 6

Testadas contra o corpo dos 76 artigos:

| Pergunta | O blog responde? |
|---|---|
| O que é Vibe Seller? | **Não** — 0 menções |
| Diferença entre Vibe Coder e Vibe Seller? | **Não** — 0 menções |
| Como encontrar oportunidades de negócio com IA? | Não — nenhum artigo ensina a rastrear |
| Como monetizar uma solução criada com IA? | Não |
| Vale a pena criar um SaaS com IA? | Não |
| Como avaliar risco de comoditização? | **Não** — 0 menções |
| Build ou buy? | **Não** — 0 menções |
| Como transformar automação em margem? | Parcialmente — 8 artigos citam "margem" de passagem |
| Como monetizar tecnologia com equity? | **Não** — 0 menções |

## O que já está tecnicamente correto

Não é tudo ruim, e vale registrar para não ser refeito:

- Article schema (JSON-LD) presente em todo post, com `author` Person,
  `publisher` Organization, `datePublished`, `dateModified` e `image`.
- `<link rel="canonical">` correto e autorreferente.
- `<html lang="pt-BR">` correto.
- Sitemap índice segmentado (pages/posts/authors/tags) com os 76 posts.
- H1 único por página, batendo com o título.
- Formato GEO já no prompt: título em pergunta, resposta nos dois primeiros
  parágrafos, H2 em pergunta.

## O que falta no schema

`keywords` ausente, `BreadcrumbList` ausente, e o Person do autor não tem
`description`, `sameAs` nem `jobTitle` — porque o campo de bio está vazio no
Ghost. **Preencher a bio do autor conserta o schema e a página de autor de uma
vez**, e é a intervenção de GEO com melhor relação custo/benefício depois do
`robots.txt`.

---

# Alterações feitas

Branch: `editorial/vibe-seller-blog`. Nada em `main`, nada em produção, nenhum
push.

| Arquivo | Mudança |
|---|---|
| `dashboard/backend/escritor_de_artigo.py` | tese Vibe Seller no prompt; `PILARES` + `pilar_de()`; lista fechada de casos reais; `meta_title`/`meta_description`/`tags` como campos do JSON; bloco de links internos; funis `/vps` e `/zapclub` |
| `dashboard/backend/ghost_publisher.py` | `criar_rascunho` aceita `meta_title`/`meta_description`; nova `publicados_recentes()` para alimentar o link interno |
| `ADWs/routines/daily_content_pipeline.py` | passa tags e metadados ao rascunho; busca os candidatos a link interno |
| `.claude/rules/esteira-de-conteudo.md` | seções 2.1 (pilar) e 2.2 (link interno e metadado); tabela de funis atualizada |
| `tests/goals/test_linha_editorial_vibe_seller.py` | 22 testes novos |
| `workspace/reports/[C]inventario-artigos-blog-2026-09-02.csv` | inventário de 92 posts |

**Testes:** `tests/goals/` — 743 passaram, 0 falharam. O teste
`test_rule_da_esteira.py::test_a_rule_cita_os_tres_funis_reais` falhou
corretamente ao introduzir `/vps` e só voltou a passar depois que a rule foi
atualizada; era o guard fazendo o trabalho dele.

**Rollback:** `git checkout main` descarta tudo. As mudanças são de prompt e de
campos opcionais; um artigo escrito com o prompt antigo continua válido e a
esteira não tem estado migrado.

---

# Limitações e bloqueios

| Item | Estado | Motivo |
|---|---|---|
| Tráfego por artigo, cliques, indexação | **NOT_AVAILABLE** | Plausible está instalado no blog (`track.workflowapi.com.br`) mas não há chave da Stats API no ambiente; Search Console não está conectado. Nenhuma classificação desta auditoria usou desempenho. |
| Backup do tema `sistema-britto` | **BLOQUEADO** | `GET /ghost/api/admin/themes/` devolve 403 `NoPermissionError` para token de API; download exige sessão de staff no painel. **Por isso nenhuma alteração de tema foi feita**, incluindo o `author.hbs` quebrado. |
| Repositório `sistemabritto/site` | **NÃO DISPONÍVEL** | não está clonado na máquina; `~/Documentos/sistemabritto` contém só assets. Itens 9 e 10 da Fase 5 dependem dele. |
| Origem do bloqueio de crawlers | **HIPÓTESE** | o formato aponta para Cloudflare, mas não tenho acesso ao painel para confirmar nem para reverter. |
| Ghost Admin API atrás de Cloudflare | contornado | chamadas com User-Agent de biblioteca recebem `error code: 1010`; é preciso User-Agent de navegador. Mesmo padrão já registrado para o EvoCRM. |

## Nota de segurança

`.claude/skills/custom-int-ghost/SKILL.md` traz uma chave de Admin API do Ghost
em texto claro, dentro de um exemplo de código. O arquivo **não está versionado**
(a skill é gitignored), então não vazou pelo repositório, e o valor não é
reproduzido aqui. Ainda assim é chave de escrita em produção num arquivo que
qualquer sessão lê: vale rotacionar e trocar o exemplo por `os.environ`.

Isso é independente do segredo do EvoCRM apontado na auditoria de Growth, cuja
rotação continua pendente.
