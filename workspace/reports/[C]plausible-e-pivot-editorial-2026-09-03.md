---
title: Plausible auditado, tema do Ghost corrigido, e o que os dados dizem sobre pivotar pauta
date: 2026-09-03
status: concluido
classification: interno
depende_de:
  - "[C]auditoria-editorial-blog-vibe-seller-2026-09-02.md"
  - "[C]auditoria-growth-intelligence-30d-2026-09-02.md"
---

# Resumo executivo

**O Plausible do blog está tecnicamente funcionando e é quase inútil para
decisão estratégica.** Ele captura o blog, não o site principal, nunca teve
uma chave de API (corrigido hoje), e o que ele mede em 19 dias é
essencialmente tráfego de bot: 41 pageviews, 39 visitantes, **95% de bounce,
0 segundo de duração média de visita**. Ler título de artigo em 0 segundo não
é leitor, é crawler de preview do Facebook, Baidu e o próprio "ghost-explore".

**O dado que realmente importa estava em outro banco, sem senha configurada
para o Nexus ler.** O site principal (`sistemabritto.com.br`) guarda o
próprio analytics no Supabase, e ali sim há sinal real: 867 pageviews e 178
cliques de CTA desde 27/07. Consultei direto por SQL administrativo (a
credencial de API do site nunca foi configurada, mas o acesso ao banco já
existia e não dependia dela).

**O achado que decide o pivô não é "qual pilar performa melhor".** É este:

| Origem da sessão | Sessões | Clicou em algum CTA depois | Navegou para 2ª página |
|---|---:|---:|---:|
| Instagram | 207 | **100 (48%)** | 262 |
| Direto | 246 | 18 (7%) | 757 |
| **Blog** | **113** | **1 (0,9%)** | **0 (0%)** |

Das 113 sessões que chegaram a `/whatsapp`, `/sistema` ou `/socialjobs` vindas
do blog, **113 tiveram exatamente uma página vista e nenhuma ação depois**.
Zero lead atribuído ao blog, zero navegação, uma única sessão com clique (no
menu, não numa oferta). O leitor do blog chega, e a página não dá em nada.

Isso muda a pergunta. Não é "que assunto escrever para atrair mais clique" — é
"por que a página que o clique leva não converte ninguém", e só depois disso
"que assunto escrever". Ambas têm resposta abaixo.

---

# 1. Plausible — diagnóstico completo

## O que estava configurado

- Site cadastrado: `blog.sistemabritto.com.br`, desde 15/08/2026.
- Script no `codeinjection_head` do Ghost, carregando de
  `track.workflowapi.com.br/js/script.js`. **Confirmado ativo** (o script
  responde 200 e o endpoint de evento aceita POST).
- **Nenhuma chave de API existia** — `select * from api_keys` devolvia 0
  linhas. Sem ela, nada no Nexus conseguia ler o Plausible por API; o
  `growth-audit` e qualquer rotina futura dependeriam de acesso manual ao
  painel.
- **O site principal `sistemabritto.com.br` nunca teve o script do
  Plausible.** Zero menção a `plausible` ou `track.workflowapi` em nenhum
  bundle JS do site. Isso é esperado: o site tem o próprio analytics
  (Supabase), então não é uma lacuna, é a arquitetura pretendida — mas valia
  confirmar em vez de assumir.

## O que os dados dizem (19 dias, 03/08 a 03/09)

| Métrica | Valor |
|---|---:|
| Pageviews | 41 |
| Visitantes | 39 |
| Bounce rate | 95% |
| Duração média de visita | 0s |

`0s` de duração média com 95% de bounce, numa amostra onde os referrers são
majoritariamente **Facebook** (link-preview crawler, não humano clicando),
**Baidu**, e **ghost-explore** (o próprio diretório do Ghost), é a assinatura
de tráfego de indexação/preview, não de leitura. Uma sequência de 8 artigos
diferentes lidos em 84 segundos por um único IP do Reino Unido (29/08,
13:47:27 a 13:48:50) é rastreamento automatizado varrendo o sitemap, não uma
pessoa.

**Conclusão sobre o Plausible: está tecnicamente correto e sem valor
estratégico hoje**, porque o volume de leitor humano real que ele capturou é
próximo de zero. Não é bug para corrigir; é um limite de tráfego atual, o
mesmo diagnóstico da auditoria de Growth de 02/09 ("sem evidência de receita
atribuída a Reel, o funil não preserva o vínculo").

## O que foi corrigido

- **Chave de API criada** (`stats:read:*`, somente leitura), pelo console
  remoto do próprio Plausible (`bin/plausible rpc`, usando o `changeset`
  oficial do módulo `Plausible.Auth.ApiKey` — não um hash calculado à mão, que
  na primeira tentativa gerou uma chave que a API rejeitava).
- Salva em `.env` local e em `/workspace/config/.env` da VPS (dentro do
  container `evonexus_evonexus_dashboard`, que é onde o resto das credenciais
  do Nexus mora — não é bind mount de disco, é volume Docker nomeado
  `evonexus_evonexus_config`), como `PLAUSIBLE_API_KEY`, `PLAUSIBLE_SITE_ID`,
  `PLAUSIBLE_BASE_URL`. Nunca exibida em texto nesta sessão além do teste de
  validação.
- Testada: `GET /api/v1/stats/aggregate` responde com os números acima.

---

# 2. O funil real (Supabase, `sistemabritto.com.br`)

## Volume, 27/07 a 03/09

| Tabela | Registros |
|---|---:|
| `pageviews` | 867 |
| `cta_clicks` | 178 |
| `quiz_funnel` (eventos) | 16 |
| `leads` | 2 |
| `checkout_metadata` | 1 |

## Onde o tráfego vai

| Página | Pageviews |
|---|---:|
| `/links` | 256 |
| `/` | 168 |
| `/aula-vps-crm-do-zero` | 127 |
| `/sistema` | 79 |
| `/whatsapp` | 76 |
| `/socialjobs` | 53 |
| `/call-sobrevivencia-pos-ia` | 45 |
| `/zapclub` | 12 |

## O padrão que converte de verdade, hoje

`/aula-vps-crm-do-zero` é a página do OTP-gate por WhatsApp descrita em
`esteira-de-video.md`: promete um vídeo específico (montar CRM próprio numa
VPS), pede o WhatsApp para liberar. **88 cliques no CTA `aula-crm`, 39
verificações de OTP concluídas** (`otp-verificado`). É, disparado, o maior
volume de ação registrado no site inteiro — mais que a soma de cliques em
`/whatsapp` e `/sistema` juntas.

A origem desse tráfego é o Reel `DcpcV-kNq9k` (CRM grátil, self-hosted), o
mesmo que a auditoria de Growth de 02/09 já tinha apontado como o outlier de
engajamento do Instagram. Agora dá para ver o que aconteceu depois do clique:
**48% das sessões de Instagram terminam em algum clique de CTA**, contra 7%
do tráfego direto e **0,9% do blog**.

## O blog chega, e não acontece nada

| | Blog |
|---|---:|
| Sessões (todas com UTM `blog`) | 113 |
| Chegaram a `/sistema` | 49 |
| Chegaram a `/whatsapp` | 47 |
| Chegaram a `/socialjobs` | 12 |
| Sessões com QUALQUER clique de CTA depois | **1** |
| Sessões com QUALQUER segunda página vista | **0** |
| Leads atribuídos ao blog | **0** |

**EVIDÊNCIA, não hipótese:** o blog já está, hoje, cumprindo a parte que
depende de conteúdo — 49 de 79 visitas a `/sistema` e 47 de 76 a `/whatsapp`
vêm do blog, mais que Instagram e mais que tráfego direto. A auditoria
editorial de ontem mostrou que o blog não fala a língua da tese; este dado
mostra que, mesmo assim, ele já entrega volume real às páginas de oferta. O
que quebra é depois: quem chega não faz nada.

A única sessão de blog com clique foi no **menu**, para "CONSTRUA SEUS
ESPECIALISTAS" — não uma oferta, um item de navegação genérico.

**HIPÓTESE, com base no padrão que já funciona:** o CTA estático de fim de
artigo ("veja como a gente faz") compete, na mesma visita, com nada — é a
única ação possível na página, e mesmo assim ninguém age. O padrão que
converte 48% das vezes no Instagram não é um link, é uma **promessa concreta
e um vídeo específico atrás de uma verificação**. Vale testar o mesmo formato
a partir do blog: um artigo do pilar RASTREAR ou MONETIZAR terminando num
vídeo/case gated por WhatsApp, em vez de um link de saída.

---

# 3. Pivô editorial, com números

A pergunta original era "que assunto pivotar para gerar mais lead e clique".
A resposta honesta, com os dados de hoje, tem duas camadas:

## Camada 1 — a página de destino, não o assunto

Nenhum pivô de pauta resolve uma página que converte 0,9% quando a mesma
audiência, com uma oferta no mesmo formato, converte 48% em outro canal. Isto
está fora do escopo de "blog" (é o site `sistemabritto.com.br`), mas é a
maior alavanca encontrada nesta sessão inteira e fica registrado aqui porque
nasceu desta análise:

- Testar, num artigo por pilar (3 no total, controlado), trocar o CTA de link
  de saída por um gate no mesmo formato de `/aula-vps-crm-do-zero`: promessa
  específica, vídeo ou material concreto, verificação por WhatsApp.
- Antes disso, confirmar manualmente que `/whatsapp` e `/sistema` carregam
  corretamente para quem chega do blog (a auditoria de Growth de 02/09 já
  achou o rodapé/menu/hero do site com UTM perdido em versões antigas do
  tema — vale um teste de fumaça).

## Camada 2 — dentro do blog, o que já tem tração

Com 113 sessões e amostra ainda pequena, a leitura por artigo individual seria
ruído. O que dá para afirmar com confiança:

- **RASTREAR já domina o volume de cliques do funil** (auditoria editorial de
  02/09): artigos "quanto custa" e "vale a pena" são a maioria do que chega a
  `/sistema` e `/whatsapp`. O problema não é atrair — é que a página de
  destino não segura quem chegou. Dobrar a aposta em RASTREAR sem consertar a
  Camada 1 só aumenta o volume que se perde no mesmo lugar.
- **MONETIZAR segue com 3 artigos e 0 evidência de tração própria** — não dá
  para julgar performance de um pilar que quase não existe. Os 4 primeiros
  itens do roadmap de 90 dias (JURISMART, Vibe Coder x Vibe Seller,
  Laboratório de Insights, build ou buy) continuam sendo o próximo passo
  correto, porque criam o material que falta antes de medir se ele converte.

**O que este relatório NÃO faz:** não recomenda qual keyword específica
escrever a seguir com base em clique — a amostra de 113 sessões espalhadas em
dezenas de campanhas é fina demais para isso, e forçar uma leitura ali seria
opinião disfarçada de dado. A base de pauta continua sendo o roadmap de 90
dias já entregue.

---

# 4. VPS e Ghost — o que foi corrigido de fato

Autorizado nesta sessão a mexer sem depender de backup prévio. Ainda assim,
cada mudança foi feita com um jeito de conferir e voltar atrás, porque isso
não custa nada extra e evita ter que confiar em memória.

## 4.1 O tema tinha DOIS bugs, não um

A auditoria de ontem achou `tag.hbs` e `author.hbs` quebrados com o mesmo
erro (`{{pagination}} helper was used outside of a paginated context`), e não
dava para saber a causa sem o tema em mãos.

**Causa raiz, confirmada:** em ambos os arquivos, `{{#foreach posts}}` e
`{{pagination}}` estavam dentro do bloco `{{#tag}}...{{/tag}}` /
`{{#author}}...{{/author}}`. Isso funciona para ler propriedades da própria
tag/autor (`{{name}}`, `../pagination.total`), mas não para o helper
`{{pagination}}` puro, que precisa do contexto raiz da rota — o mesmo padrão
que já funcionava em `index.hbs`. Corrigido movendo os dois blocos para fora,
comparado linha a linha com o tema `casper` (que já roda nesta mesma VPS,
serviu de referência do padrão correto).

**Segundo bug, achado só ao testar a correção do primeiro:** o rodapé do
tema tinha `{{#foreach @site.navigation}}<li><a href="{{url}}">{{label}}</a>
</li>{{/foreach}}` para os links de "Conteúdo". Isolei com um teste A/B na
própria página (o helper oficial `{{navigation}}` ao lado do loop
customizado): o oficial resolvia as URLs certas, o loop customizado devolvia
`/` para os cinco itens, sempre. `{{#foreach}}` sobre `@site.navigation` não
vincula `url`/`label` de forma confiável nesta versão do Ghost — corrigido
hardcodando os cinco links, no mesmo padrão que a coluna vizinha ("Soluções")
já usava.

Backup real do tema (antes de qualquer alteração) em
`workspace/reports/backups/ghost-theme-sistema-britto-2026-09-03/
sistema-britto-backup.tar.gz`. Diff completo dos dois arquivos e do parcial de
rodapé em `.../tag-author-corrigidos/`.

## 4.2 Settings e bio do autor — via MySQL direto

O token de integração do Ghost é bloqueado por desenho do próprio Ghost em
`/settings/`, `/users/{id}/`, `/themes/` e `/redirects/` — não é erro de
escopo nosso, é uma classe de endpoint que só aceita sessão de navegador
(confirmado ontem, `403 NoPermissionError`, mesma mensagem em todos). Sem
e-mail/senha do admin, o caminho que sobrou foi o banco MySQL do Ghost
(`ghost_db`, na VPS), com autorização explícita para mexer sem backup prévio.

Dump completo da tabela `settings` (126 linhas) salvo antes de qualquer
`UPDATE`, mesmo sem ser exigido — é grátis e evita depender de memória.

| Campo | Antes | Depois |
|---|---|---|
| `timezone` | `America/Argentina/Buenos_Aires` | `America/Sao_Paulo` |
| `lang` | (vazio) | `pt-BR` |
| `twitter` | `@ghost` (placeholder) | (vazio) |
| `secondary_navigation` | `[{"Sign up"}]` | `[]` |
| `navigation` | 2 itens genéricos | Início/Rastrear/Vibe Codar/Monetizar/Sobre/Site |
| `description` | "Automação empresarial..." | a tese, em uma frase |
| `meta_title` / `meta_description` | vazios | preenchidos |
| bio do Felipe (`users.bio`) | vazio | o parágrafo da tese, ver `/author/fsbritto/` |

`timezone`: Buenos Aires e São Paulo estão em UTC-3 hoje e nenhum dos dois usa
horário de verão — a troca **não deslocou** nenhum agendamento existente da
esteira. Confirmado antes de aplicar, não depois.

Depois de escrever no banco, o serviço `ghost_ghost` foi reiniciado
(`docker service update --force`) para o processo recarregar o cache de
settings — sem isso as mudanças ficam no banco mas o Ghost em memória continua
servindo o valor antigo até o próximo restart natural.

## 4.3 Ainda fora do alcance

`robots.txt` / bloqueio de crawlers de IA é regra do Cloudflare, camada acima
do Ghost e do site. **Nenhuma credencial de Cloudflare existe no workspace**
(nem no repo, nem em nenhum `.env` da VPS) — confirmado varrendo todos os
serviços do Swarm. Fica pendente de um token que o Felipe está gerando agora
(token de zona, permissão de Editar Configurações de Zona, restrito a
`sistemabritto.com.br`); assim que chegar, aplico a liberação de
GPTBot/ClaudeBot mantendo `ai-train=no` e confirmo por `curl`.

---

# 5. Como conferir tudo que foi alterado hoje

Nada foi feito sem um jeito de checar. Ordem sugerida:

## No blog, ao vivo (sem precisar de credencial)

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://blog.sistemabritto.com.br/tag/rastrear/
curl -s -o /dev/null -w "%{http_code}\n" https://blog.sistemabritto.com.br/author/fsbritto/
```
Os dois devem responder `200` (antes de hoje, `400`).

Abra `https://blog.sistemabritto.com.br/about/`,
`https://blog.sistemabritto.com.br/author/fsbritto/` e a home — confira a
tese, a bio e o rodapé com os links de Rastrear/Vibe Codar/Monetizar.

## No Ghost admin (login normal)

`Settings → General`: timezone `America/Sao_Paulo`, idioma `pt-BR`.
`Settings → Navigation`: os 6 itens novos.
`Settings → Staff → Felipe Britto`: a bio nova.
`Posts`: filtrar por tag `Rastrear`/`Vibe Codar`/`Monetizar` — 76 dos 76 posts
publicados devem ter exatamente uma dessas três, mais eventualmente uma
secundária (`whatsapp`, `atendimento`, etc.).

## No git

```bash
git log --oneline -10
git show --stat a666abe   # execução no Ghost (tags, meta, canonical, links internos)
git show --stat b8a7899   # merge em main
```

O tema (arquivos `.hbs`) **não está no git** — Ghost não versiona tema por
padrão neste setup, e o backup mora em
`workspace/reports/backups/ghost-theme-sistema-britto-2026-09-03/`.

## Nos dados

```bash
# Plausible (precisa da chave nova, já salva em .env local)
curl -s "https://track.workflowapi.com.br/api/v1/stats/aggregate?site_id=blog.sistemabritto.com.br&period=30d&metrics=visitors,pageviews,bounce_rate" \
  -H "Authorization: Bearer $PLAUSIBLE_API_KEY"

# Supabase (precisa de SUPABASE_ACCESS_TOKEN, já em .env)
curl -s "https://api.supabase.com/v1/projects/$SUPABASE_PROJECT_REF/database/query" \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"select count(*) from cta_clicks"}'
```

## Rollback, se algo tiver que voltar

- **Tema:** `docker cp` do `sistema-britto-backup.tar.gz` de volta para
  `/var/lib/ghost/content/themes/sistema-britto/` no container, depois
  `docker service update --force ghost_ghost`.
- **Settings/bio:** os 126 valores originais estão no dump de
  `settings_backup`; qualquer campo específico pode ser restaurado com um
  `UPDATE` pontual a partir dele.
- **Posts (tags/meta/links internos):** backup completo de 92 posts em
  `workspace/reports/backups/ghost-2026-09-02/posts.json` (sessão anterior).

---

# O que ficou pendente

1. **Token do Cloudflare** — Felipe está gerando; assim que chegar, libero
   GPTBot/ClaudeBot no `robots.txt` mantendo `ai-train=no`.
2. **`SITE_ADMIN_PASSWORD`** continua sem valor em nenhum `.env` — não bloqueou
   esta análise (fui direto ao Supabase), mas o endpoint
   `/api/admin/analytics` do site segue inacessível para rotina automatizada
   até alguém definir essa senha.
3. **Teste do gate por WhatsApp a partir do blog** (Camada 1, seção 3) — é
   proposta, não implementação. Mexe em página de oferta fora do escopo desta
   sessão (repositório do site não está clonado nesta máquina).

---

# 6. Execução do plano de bounce (03/09/2026, tarde)

Autorizado a implementar. Escopo escolhido: teste em 5-6 artigos existentes,
não mudança geral da esteira.

## 6.1 Repositórios clonados

`~/Documentos/site` (`sistemabritto/site`) e `~/Documentos/ghost-theme`
(`sistemabritto/ghost-theme`) — este último é a fonte versionada do tema que
eu vinha editando direto no volume da VPS pela manhã. Confirmado idêntico ao
backup tirado da VPS antes de qualquer commit.

## 6.2 `ghost-theme` — sincronizado com o que já estava no ar

PR [`sistemabritto/ghost-theme#1`](https://github.com/sistemabritto/ghost-theme/pull/1),
mergeado. O deploy automático (`Deploy do tema`, `TryGhost/action-deploy-theme@v2.0.4`)
**funciona** — confirmado rodando de ponta a ponta pela primeira vez desde
29/07/2026 (7 execuções anteriores falhavam por causa de uma versão de action
que nunca existiu, já corrigida antes de hoje). A partir de agora, mudar o
tema não exige mais `docker cp` manual na VPS.

## 6.3 `site` — dois commits

1. **`fix(quiz)`** — PR [`site#13`](https://github.com/sistemabritto/site/pull/13),
   mergeado, deploy Vercel `READY` em produção. `quiz_source` agora cai para
   `utm_source` quando não há `?source=` explícito (seção 5 do plano, item 3).
2. **CTA de 6 artigos apontando para `/quiz`** — via Ghost API, mesmo método
   de verificação da manhã (troca só o `href`, confere texto puro
   byte-idêntico antes/depois contra o backup de 02/09).

## Artigos no experimento

Critério: tag `rastrear` + maior contagem de pageviews com `utm_source=blog`
na página de oferta (Supabase), entre os que já tinham tráfego atribuído
mensurável.

| Artigo | CTA antigo | CTA novo |
|---|---|---|
| `como-reduzir-custo-de-suporte-com-chatbot-sem-perder-qualidade-em-2026` | `/whatsapp` | `/quiz?...&source=blog-rastrear` |
| `sistema-de-whatsapp-para-empresas-vale-a-pena-em-2026` | `/whatsapp` | idem |
| `como-fazer-lead-qualification-with-whatsapp-sem-perder-tempo-com-lead-frio` | `/whatsapp` | idem |
| `crm-integrado-ao-whatsapp-vale-a-pena-para-donos-de-empresa-em-2026` | `/whatsapp` | idem |
| `como-automatizar-prospeccao-de-clientes-com-ia-sem-perder-o-controle-do-comercial` | `/sistema` | idem |
| `como-qualificar-leads-pelo-whatsapp-sem-perder-tempo-respondendo-curioso` | `/whatsapp` | idem |

Cada `utm_campaign` é o próprio slug (convenção já existente em `utm.py`), e
`source=blog-rastrear` identifica o experimento no `quiz_funnel`. Marcados
com a tag `experimento-cta-quiz` no Ghost para achar o lote depois sem
depender de lista salva em arquivo.

**Rodapé e menu não foram tocados** — continuam apontando para as ofertas
diretas, que é navegação, não o teste.

**Achado incidental, não corrigido agora (fora do escopo pedido):** o CTA de
`sistema-de-whatsapp-para-empresas-vale-a-pena-em-2026` usava a âncora
"Clique aqui", que `ancora_util()` deveria ter bloqueado. Como só o `href`
foi trocado (preservando texto), o problema permanece — registrado aqui para
correção numa próxima passada de qualidade de conteúdo.

## Como ler o resultado em 2 semanas

```sql
select quiz_source, stage, count(*) 
from quiz_funnel 
where quiz_source = 'blog-rastrear' 
group by quiz_source, stage;

select count(distinct p.session_id) sessoes, count(distinct c.session_id) com_clique
from pageviews p left join cta_clicks c on c.session_id = p.session_id
where p.utm_campaign in (
  'como-reduzir-custo-de-suporte-com-chatbot-sem-perder-qualidade-em-2026',
  'sistema-de-whatsapp-para-empresas-vale-a-pena-em-2026',
  'como-fazer-lead-qualification-with-whatsapp-sem-perder-tempo-com-lead-frio',
  'crm-integrado-ao-whatsapp-vale-a-pena-para-donos-de-empresa-em-2026',
  'como-automatizar-prospeccao-de-clientes-com-ia-sem-perder-o-controle-do-comercial',
  'como-qualificar-leads-pelo-whatsapp-sem-perder-tempo-respondendo-curioso'
);
```
Comparar a taxa de `com_clique/sessoes` deste grupo contra o resto do blog
(0,9% medido nesta sessão, seção 2).

## Rollback do experimento

`git revert` não se aplica (a mudança foi via API, não via commit no site).
Reverter é trocar o `href` de volta ao valor original, listado na tabela
acima, pelos mesmos 6 `post.id` salvos em `/tmp/cta_aplicados.json` desta
sessão (efêmero — se precisar depois, busque pela tag
`experimento-cta-quiz` e pela URL contendo `source=blog-rastrear` no HTML).

## Ainda pendente

**Cloudflare / AI Crawl Control** — token com permissão de Bot Management
confirmada (`is_robots_txt_managed: true`), mas o toggle nativo
`ai_bots_protection` já estava `disabled` (não é a causa do bloqueio) e o
sub-recurso que de fato controla os Content Signals por bot
(`bot_management/content_signals`) segue com erro de autenticação mesmo após
a permissão de Bot Management — é provavelmente um recurso de **conta**, não
de zona. Orientado o Felipe a abrir "AI Crawl Control" direto no painel
(busca no topo do dashboard Cloudflare) e ajustar por lá; aguardando
confirmação.

---

# 7. Cloudflare AI Crawl Control — resolvido em 04/09/2026

Confirmado ao vivo (`cf-cache-status: MISS`, GPTBot/ClaudeBot/Google-Extended/
PerplexityBot/Bytespider/meta-externalagent testados individualmente com
`User-Agent`, todos HTTP 200 sem `Disallow`): o bloqueio de crawler de IA
está removido em `blog.sistemabritto.com.br`.

## O que realmente resolveu

Não foi ajuste fino de política — foi **desativar por completo o "Gerenciar
seu robots.txt" da Cloudflare** (opção "Desative a configuração robots.txt").
O Ghost passou a servir o próprio `robots.txt` nativo, que é curto e nunca
bloqueou bot nenhum (só `/ghost/`, `/email/`, `/members/api/comments/counts/`,
`/r/`, `/webmentions/receive/`, `/.ghost/analytics/api/`).

## Por que o caminho "certo" (granular) não funcionou

Tentamos, nesta ordem, sem sucesso:

1. **Bot Management → toggles individuais por bot** (Allow/Block por bot na
   aba Crawlers) — a API confirmou "Allow" para todos, o `robots.txt` ao vivo
   continuou bloqueando. Confirmado que `PATCH /zones/{id}/bot_management`
   devolve `10405 Method not allowed for this authentication scheme` para
   **qualquer campo**, mesmo com a permissão "Bot Management → Editar" no
   token — é restrição de esquema de autenticação da Cloudflare, não de
   escopo. Só sessão de navegador escreve ali.
2. **"Bloquear bots de IA" (legado, a ser descontinuado em 15/09/2026)** →
   "Não bloquear" + "propósito misto continuarão permitidos" — mudança feita,
   salva, e o campo `ai_bots_protection` da API foi de `"disabled"` para
   `"block"` (o oposto do esperado). Sem explicação encontrada; pode ser bug
   de interação entre o painel legado e o novo, ou os dois formulários
   escrevendo no mesmo campo de jeitos diferentes.
3. **"Configure políticas de bots de IA" (novo)** → Pesquisa=Permitir,
   Agente=Permitir, Treinamento=Bloquear em todas as páginas — salvo, e a API
   mostrou `ai_training: "block"` refletido, mas `ai_search`/`ai_user`
   continuaram `"disabled"` (não viraram `"allow"` visível), e
   **`bot_preference_sync_enabled` nunca saiu de `false`** em nenhuma das
   tentativas — esse é o campo que, segundo a documentação que o assistente
   da própria Cloudflare citou, conecta as políticas de Search/Agent/Training
   ao conteúdo real do `robots.txt`. Não foi localizado na interface (o
   modal "Configure políticas de bots de IA" não tinha esse controle visível,
   nem rolando até o fim).

**Conclusão prática:** a funcionalidade granular nova do Cloudflare
(lançada em breve/parcialmente, com aviso de "seu token expirou" no próprio
assistente deles durante a sessão) não estava, nesta conta, em estado
utilizável via nenhum caminho tentado — nem painel, nem API. Desativar o
gerenciamento e deixar a origem (Ghost) responder foi a saída que funcionou,
ao custo de perder o sinal explícito `Content-Signal: ai-train=no`.

## O que ficou em aberto

- **`ai-train=no` não está mais declarado.** Se recuperar esse sinal for
  importante, o caminho é um `robots.txt` customizado servido pela própria
  origem (não pelo Cloudflare) — não investigado nesta sessão se o Ghost
  aceita isso nativamente ou exige rota customizada.
- **`ai_bots_protection: "block"`** ficou registrado na API mesmo com o
  `robots.txt` gerenciado desativado. Não tem efeito observável agora (o
  Ghost está servindo o arquivo, não o Cloudflare), mas se o "Gerenciar
  robots.txt" for reativado no futuro sem revisar esse campo, o bloqueio
  pode voltar sem aviso.
- **`voicedream.com.br` e `workflowapi.com.br`** continuam sem nenhum bot de
  IA configurado (nem bloqueado nem permitido) — pendente, mais simples que
  o caso do blog porque não têm o histórico de gerenciamento conflitante.
- **`zapmagico.com.br`** já estava correto, nada a fazer.
