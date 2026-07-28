<p align="center">
  <a href="https://evolutionfoundation.com.br">
    <img src="public/cover.webp" alt="Evolution Foundation" height="60"/>
  </a>
</p>

<p align="center">
  <img src="public/cover.svg" alt="EvoNexus" width="100%"/>
</p>

<h1 align="center">Omni-Nexus</h1>

<p align="center">
  <b>Um time de agentes de IA que trabalha sozinho — e para em você para decidir.</b>
</p>

<p align="center">
  Distribuição turbinada do <a href="https://github.com/evolution-foundation/evo-nexus">EvoNexus</a> pronta para VPS:
  gateway de IA <a href="https://github.com/diegosouzapw/OmniRoute">OmniRoute</a> embutido na stack,
  esteira de conteúdo autônoma com aprovação humana, medição de funil fim a fim
  e bot do Telegram multi-provider.
</p>

<p align="center">
  Camada de upgrade mantida por <a href="https://sistemabritto.com.br"><b>Sistema Britto</b></a>
  sobre o EvoNexus da <a href="https://evolutionfoundation.com.br">Evolution Foundation</a>.
</p>

<p align="center">
  <a href="https://github.com/evolution-foundation/evo-nexus"><img src="https://img.shields.io/badge/upstream-evolution--foundation%2Fevo--nexus-00ffa7?style=for-the-badge" alt="Upstream" /></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/license-Apache%202.0-2563eb?style=for-the-badge" alt="License: Apache 2.0" /></a>
  <img src="https://img.shields.io/badge/testes-936%20automatizados-16a34a?style=for-the-badge" alt="936 testes" />
  <img src="https://img.shields.io/badge/deploy-Docker%20Swarm-0ea5e9?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Swarm" />
</p>

<p align="center">
  <a href="https://sistemabritto.com.br"><img src="https://img.shields.io/badge/site-sistemabritto.com.br-111827?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Site" /></a>
  <a href="https://instagram.com/sistemabritto"><img src="https://img.shields.io/badge/Instagram-@sistemabritto-E4405F?style=for-the-badge&logo=instagram&logoColor=white" alt="Instagram" /></a>
  <a href="https://youtube.com/@sistemabritto"><img src="https://img.shields.io/badge/YouTube-@sistemabritto-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube" /></a>
  <a href="https://www.linkedin.com/in/fsbritto/"><img src="https://img.shields.io/badge/LinkedIn-fsbritto-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn" /></a>
</p>

<p align="center">
  <a href="#-o-que-mudou-o-mapa-dos-upgrades">Upgrades</a> &middot;
  <a href="#-como-funciona-passo-a-passo-guia-sem-jargão">Guia sem jargão</a> &middot;
  <a href="#-a-esteira-de-conteúdo--do-tema-ao-post-publicado">Esteira de conteúdo</a> &middot;
  <a href="#-omniroute--o-gateway-de-ia-da-stack">OmniRoute</a> &middot;
  <a href="#-bot-do-telegram-multi-provider">Telegram</a> &middot;
  <a href="#-deploy-completo-na-vps-passo-a-passo">Deploy na VPS</a> &middot;
  <a href="#-créditos--agradecimentos">Créditos</a>
</p>

---

> **Disclaimer:** assim como o EvoNexus original, este é um projeto open source **não oficial**, **não afiliado, endossado ou patrocinado pela Anthropic**. "Claude" e "Claude Code" são marcas da Anthropic, PBC. O projeto integra o Claude Code como ferramenta de terceiros e exige que você forneça sua própria instalação e credenciais.

---

## O que é este fork

O [EvoNexus](https://github.com/evolution-foundation/evo-nexus) é uma camada operacional multi-agente construída sobre o CLI do Claude Code: **38 agentes especializados** (17 de negócio + 21 de engenharia), 190+ skills, rotinas agendadas, heartbeats, tickets, goals e um dashboard web completo. Toda essa base vem do projeto original da [Evolution Foundation](https://evolutionfoundation.com.br) — leia o [README upstream](https://github.com/evolution-foundation/evo-nexus#readme) para conhecer a plataforma em profundidade.

O **Omni-Nexus** é o que o [Sistema Britto](https://sistemabritto.com.br) construiu em cima dessa base **usando o sistema em produção, todos os dias, para operar um negócio real**. Cada upgrade listado aqui nasceu de um problema que aconteceu de verdade: um post que não foi ao ar, uma conta de API que veio maior do que devia, um número no painel que estava mentindo.

Duas frentes:

1. **Autonomia de infraestrutura** — rodar o EvoNexus inteiro numa VPS com Docker Swarm, sem depender de gateway de IA externo e sem exigir login claude.ai. Qualquer provider, vários ao mesmo tempo, com fallback automático.
2. **Autonomia de operação** — um time de agentes que produz trabalho de verdade (conteúdo, publicação, medição, briefing) e para em **gates humanos** antes de qualquer coisa ir ao ar.

> 🧭 Não é técnico e só quer entender **o que esse sistema faz pela sua empresa**? Vá direto para o [guia sem jargão](#-como-funciona-passo-a-passo-guia-sem-jargão).

---

## 🚀 O que mudou: o mapa dos upgrades

| # | Upgrade | O problema que resolve | Benefício direto | No dia a dia |
|---|---|---|---|---|
| 1 | **[Esteira de conteúdo autônoma](#-a-esteira-de-conteúdo--do-tema-ao-post-publicado)** | Produzir conteúdo consistente exige pauta, texto, capa, publicação e distribuição — cinco tarefas, todo dia | 3 posts/dia, 7 dias/semana, do levantamento de pauta ao post nas redes | Você aprova no Telegram em vez de escrever, editar e publicar |
| 2 | **[Gates humanos em tudo](#gate-humano--a-regra-que-nunca-quebra)** | IA que publica sozinha erra em público | Nada vai ao ar sem um toque seu | Um gate por artigo, um por rede. A esteira produz e **para** |
| 3 | **[Rodízio de capa](#capa--nunca-a-mesma-cara-duas-vezes)** | Toda thumbnail saía com a mesma pose e a mesma expressão | 48 combinações antes de repetir (pose × registro × lado × enquadramento) | O feed para de parecer gerado em série |
| 4 | **[Guardas anti-IA](#texto--o-que-denuncia-que-foi-ia)** | Travessão, CTA genérico e data errada denunciam texto de IA | Guard determinístico no código, não só no prompt | O texto passa por humano sem "cheiro de robô" |
| 5 | **[Rodízio de funil nas pautas](#pauta--a-semana-fala-de-três-assuntos-não-de-um)** | 18 das 21 pautas da semana caíram no mesmo funil | Cada dia nasce com um assunto de cada oferta | Um leitor de WhatsApp, um de conteúdo, um de automação — todo dia |
| 6 | **[Medição fim a fim (UTM + cliques)](#-medição--o-clique-é-o-que-fecha-o-funil)** | O site tinha 636 pageviews e **1** clique registrado: nenhum botão chamava o tracker | Atribuição real de qual artigo gerou qual lead | Você sabe qual post trouxe cliente, não só qual teve view |
| 7 | **[Painel de rotinas honesto 🐍/🤖](#-painel-de-rotinas--o-que-roda-de-verdade-e-quanto-custa)** | A página listava rotinas que não existiam e somava custo errado | Lê o agendador real (`schedule.get_jobs()`), não regex sobre o código | Você vê o que roda, quando, se deu certo e quanto custou |
| 8 | **[Python onde não há julgamento](#-python-onde-não-há-julgamento-modelo-onde-há)** | Rotinas chamavam LLM para narrar tabela que já era estruturada | Uma esteira de 4 chamadas em série desligada: **44% de todo o custo de rotina** | A conta de API cai; a qualidade não |
| 9 | **[Varredor de artigo agendado](#o-caso-que-falhava-o-artigo-agendado)** | Artigo agendado publicava sozinho e **nenhuma rede era derivada** — sem erro nenhum | Varredura a cada 15 min + idempotência por artigo | Nenhum post some em silêncio |
| 10 | **[OmniRoute na stack](#-omniroute--o-gateway-de-ia-da-stack)** | Gateway público fora do ar derruba bot, heartbeat e rotina | 237+ providers self-hosted com fallback automático | Seu sistema não cai porque um terceiro caiu |
| 11 | **[Telegram multi-provider](#-bot-do-telegram-multi-provider)** | O canal nativo exige login claude.ai dentro do container | Bot responde pelo provider ativo, troca no chat, sobrevive a redeploy | Você opera a empresa do celular |
| 12 | **[Artefatos dentro do Nexus](#-artefatos--relatório-com-link-estável-dentro-do-seu-produto)** | Relatório hospedado fora some quando a sessão morre | `/shares` com link estável, revogação e expiração | Relatório que você mostra a cliente, versionado no seu domínio |
| 13 | **[Memória com recall semântico](#-memória--o-agente-que-não-esquece-entre-sessões)** | `/clear` apagava tudo que o agente aprendeu | MemPalace indexa memória, aprendizados e histórico de features | O agente lembra do incidente de três semanas atrás |
| 14 | **[Pipeline VPS + hardening](#-deploy-completo-na-vps-passo-a-passo)** | Deploy manual, trust de workspace quebrando como root, auto-update matando sessão | GitHub Actions → Docker Hub → `service update` | Push na branch, e a produção sobe |
| 15 | **[936 testes automatizados](#-a-suíte-de-testes--cada-teste-é-uma-cicatriz)** | Cada bug corrigido voltava depois | Suíte que documenta o **porquê** de cada regra | Nenhuma correção de produção é perdida |

---

## 🏭 A esteira de conteúdo — do tema ao post publicado

O upgrade de maior impacto operacional. É uma linha de produção completa que roda sozinha e para em você nos pontos de decisão:

```
domingo    weekly_content_research  →  21 pautas na fila            (status: proposta)
você       aprova o ciclo em lote                                   (status: aprovada)
06:00      daily_content_pipeline   →  escreve, cria draft,
                                       gera capa, abre o gate        (status: escrita)
você       aprova o artigo          →  publica no Ghost             (status: publicada)
automático                          →  deriva X / LinkedIn / Threads, um gate cada
15 em 15   derivar_redes_pendentes  →  recupera o artigo agendado que ficou órfão
```

### Gate humano — a regra que nunca quebra

**Nada é publicado sem aprovação.** Um gate por artigo, um por rede. O artigo nasce sempre como `draft` no Ghost; quem decide se vai ao ar é você, no Telegram. Criar já publicado tiraria do humano exatamente a decisão que o fluxo inteiro existe para preservar.

**Impacto na produtividade:** o trabalho pesado (pesquisar assunto, escrever 600+ palavras, gerar capa, adaptar para 3 redes, publicar em 4 lugares) sai da sua mesa. O que sobra é ler e decidir — cerca de 4 toques por dia.

### Pauta — a semana fala de três assuntos, não de um

A rotina semanal levanta pauta por **volume de busca real** (DataForSEO), passa por seis etapas de filtro e só então enfileira:

| Etapa | O que protege |
|---|---|
| **Cache de 30 dias** | Volume de busca é média de 12 meses — reconsultar a mesma seed é dinheiro queimado pelo mesmo número |
| **Filtro de cauda longa comercial** | Regex de compra/domínio/ruído com limite de palavra (`\b`) — sem isso, `api` casava dentro de "japinha" |
| **Dedupe por núcleo** | 60% de sobreposição vira canibalização de SEO |
| **Avaliador de ICP** | Um modelo julga público-alvo (nota 0–10, mínimo 6) — regex deixava passar pauta do negócio de outro |
| **Rodízio de funis** | Sem ele, o funil de maior volume levava os 21 slots. Aconteceu: **18 de 21** |
| **X como reserva** | O que está em alta hoje não tem histórico de volume — e é a pauta que a concorrência ainda não escreveu |

**Benefício direto:** o calendário nasce equilibrado. Cada dia tem um post para cada oferta, em vez de três posts sobre o mesmo assunto.

### Capa — nunca a mesma cara duas vezes

O gerador de thumbnail gira **quatro eixos ao mesmo tempo** — pose (4 fotos de referência), registro facial (6), lado do quadro (2) e enquadramento (2). Pose e registro andam em passos diferentes, então duas capas vizinhas nunca coincidem em nenhum dos dois, e a combinação inteira só se repete a cada **48**.

Três dos seis registros contrariam o texto de propósito. Capa que apenas confirma o título é a que o olho já aprendeu a pular.

Na regeração por feedback, a variação vem do par `(artigo, feedback)`: o mesmo feedback devolve a mesma capa (retry é idempotente), e um feedback novo cai em outra pose. Devolver a arte anterior depois que o autor pediu outra é a pior resposta possível a um gate.

### Texto — o que denuncia que foi IA

| Guarda | Por que existe |
|---|---|
| **Travessão proibido, com guard no código** | O símbolo é gramatical em português, mas hoje o leitor o lê como assinatura de texto gerado. Instrução negativa no prompt sozinha não resolve: o modelo reincide, porque encaixar aposto com travessão é hábito de treino. O guard roda no título, no excerpt e no HTML **antes** do corte de limite de caractere — trocar `—` por vírgula muda o tamanho, e um post medido a 280 antes da troca estoura depois |
| **Humanizer no prompt** | O antídoto ao texto de IA, carregado sempre |
| **Data de hoje explícita** | Sem isso o modelo escreve o ano errado com convicção |
| **Mínimo de 600 palavras** | Artigo curto é recusado, não publicado torto |
| **CTA por funil, escolhido por código** | Modelo inventa CTA genérico, e CTA genérico não converte. A classificação é determinística e testada seed por seed |

**Impacto:** o texto sai pronto para publicar, não pronto para revisar.

### O caso que falhava: o artigo agendado

Aprovar um artigo pode **publicar agora** ou **agendar**. Os dois publicam — e só um passava por código nosso na hora de ir ao ar.

Num dia de produção, os dois artigos foram agendados. O Ghost publicou os dois no horário e **nenhum post de X, LinkedIn ou Threads existiu**. Nada acusou erro: a derivação só rodava quando o artigo não estava agendado, e naquele momento ele ainda nem estava publicado.

O webhook do Ghost cobriria o caso, mas não cobre: a chave de Admin API devolve `403` no endpoint de integrações — criar webhook exige sessão de staff no painel. **Etapa manual que ninguém repete não é garantia.**

A solução: um varredor a cada 15 minutos que lista o que o Ghost publicou nas últimas 26h e deriva o que falta. A idempotência é obrigatória — três caminhos podem mandar derivar o mesmo artigo, e sem ela cada um abriria seu próprio trio de aprovações. Ela conta **todos** os estados, não só os pendentes: reabrir o que o humano rejeitou é insistir num texto que ele leu e recusou.

E a rede já derivada é pulada **antes** da chamada ao modelo, nunca depois. Gerar para descartar seriam 96 chamadas desperdiçadas por dia.

---

## 📊 Medição — o clique é o que fecha o funil

```
artigo publicado → visita com UTM → clique no CTA → lead → fechado
```

Cada seta é medida. A do meio faltava: o tracker existia no site com endpoint e tabela prontos, e **nenhum botão o chamava**. Resultado: **636 pageviews contra 1 clique registrado**. A taxa de conversão do painel ficava travada em zero, e não dava para dizer se um artigo gerava interesse.

**A convenção de UTM que a esteira carimba sozinha:**

| Parâmetro | Valor | Responde |
|---|---|---|
| `utm_source` | `blog`, `x`, `linkedin`, `threads` | de qual canal veio |
| `utm_campaign` | slug do artigo | **qual post converteu** |
| `utm_content` | rede / variação | qual peça converteu |

A marcação é idempotente: link que já tem origem volta intacto. Marcar duas vezes produziria duas origens, e o analytics leria a primeira — origem errada com cara de origem certa.

**Regra inegociável:** clique sem pageview na janela entra como *não atribuído*. **Nunca inventar origem para não deixar o número feio.**

**Impacto na produtividade:** você para de decidir conteúdo por sensação. O painel diz qual artigo trouxe clique, e o rodízio de funil da semana seguinte se ajusta ao que funcionou.

---

## 🐍 Painel de rotinas — o que roda de verdade, e quanto custa

A página `/routines` é a **fonte única** do que está agendado. Antes, ela lia regex sobre o código-fonte e listava ~20 rotinas como se todas estivessem no ar — a maioria não tinha script nenhum, e uma delas (a que dispara posts reais) falhava em silêncio a cada tick porque o agendador procurava o arquivo no caminho errado.

Hoje ela lê `schedule.get_jobs()` — o agendador de verdade — com próxima execução real, histórico e custo acumulado. E cada rotina traz o motor que a move:

| Selo | O que significa | Consequência |
|---|---|---|
| 🐍 **Python** | código determinístico | custa CPU; pode rodar de 15 em 15 min |
| 🤖 **Modelo** | chama uma LLM | custa dinheiro **toda** execução |

A detecção segue os imports locais um nível — o entrypoint de quatro linhas que chama o modelo lá dentro não engana. E não confunde `import` com chamada: uma rotina que importa o runner mas só roda script continua sendo 🐍 (comprovado: 27 execuções, US$ 0,00).

A interface foi reconstruída em grid fluido: cabe inteira no desktop sem rolagem lateral e vira cards no mobile — porque a decisão "essa rotina está custando caro demais" costuma acontecer no celular.

---

## ⚖️ Python onde não há julgamento, modelo onde há

**A regra ao criar rotina nova: se a saída é determinística, escreva em Python. Modelo só onde existe julgamento** — escolher pauta, escrever texto, avaliar ICP. Narrar tabela que já é estruturada não é julgamento.

Dois casos reais dessa regra aplicada:

**A esteira que duplicava outra esteira.** Uma rotina diária encadeava **quatro** chamadas de LLM em série para produzir o mesmo artigo de blog que a esteira principal já produz com uma chamada — e melhor: pauta por volume de busca real, humanizer, CTA de funil e capa com rodízio. Custava **US$ 11,92, 44% de todo o gasto em rotina**, com 27% a 75% de acerto, e estava 100% quebrada havia dias. Desligada.

**Briefing e fechamento do dia.** Duas skills escritas para conversa, rodando como cron. A matinal mandava o agente ler seis fontes, gerar um HTML e **perguntar ao usuário se ele queria entrar num projeto** — pergunta que às 07:00 ninguém responde. A do fim do dia mandava ler a conversa da sessão, que no cron não existe.

Agora o Python coleta o que é consulta (aprovações pendentes, rotinas que falharam, tarefas, tickets, pauta do dia, commits, arquivos tocados) e entrega tudo pronto. Ao modelo sobra o que ele faz bem e o Python não faz: ler o dia inteiro de uma vez, decidir o que ali é aprendizado e escrever a recomendação.

**Benefício direto:** o mesmo briefing, uma fração do custo, e sem pergunta que ninguém lê. Ausência também é informação — seção vazia aparece escrita como "nada", porque omitir deixa o leitor sem saber se não havia pendência ou se a consulta falhou.

---

## 🧭 Como funciona, passo a passo (guia sem jargão)

Esqueça "gateway", "Swarm" e "provider" por um momento. Esta seção explica **o que o sistema faz** e **como você usa isso no seu trabalho**, sem pressupor conhecimento técnico.

### A ideia central

Você não fica configurando ferramenta nem escrevendo prompt o dia inteiro. Você diz **o que quer alcançar**, o sistema quebra isso em passos concretos, um time de agentes de IA especializados executa, e você só aparece pra **aprovar ou corrigir o rumo** — pelo dashboard ou pelo Telegram, do celular.

O ciclo é sempre o mesmo, em 4 níveis, cada um mais concreto que o anterior:

```
Missão            "o que eu quero pra minha empresa" (ex.: faturar R$1M até dez/2026)
  └─ Projeto       uma frente de trabalho (ex.: "Evo AI", "Lançamento do curso X")
       └─ Meta      um número que prova progresso (ex.: "100 clientes pagantes")
            └─ Ticket   uma tarefa real, do tamanho de uma tarde
```

Você só precisa criar o topo (a Missão). **A partir daí a IA sugere o resto** — os Projetos, as Metas de cada projeto, e a quebra de cada Meta em Tickets — e cada sugestão só se torna real depois que você aprova ou rejeita, geralmente com um toque no Telegram. Nada é criado por trás das suas costas.

### O passo a passo na prática

1. **Você cria uma Missão** — na página `/goals`, ou simplesmente descrevendo o objetivo. Ex.: "Quero R$1M de faturamento até dezembro."
2. **A IA sugere Projetos** — chega no Telegram: *"Sugiro 3 projetos pra essa missão. Aprovar?"* Um toque e os projetos existem.
3. **A IA sugere Metas por Projeto** — *"Pro projeto Evo AI, sugiro: 100 clientes pagantes até 30/06, lançar a v2 da cobrança."*
4. **A IA quebra cada Meta em Tickets** — tarefas do tamanho certo pra executar essa semana, já com prioridade e responsável sugeridos.
5. **Os agentes trabalham os Tickets** — cada Ticket tem um agente-dono. Eles avançam sozinhos entre as reuniões: é o mecanismo de **heartbeat**, em que o agente "acorda" de tempos em tempos, olha a fila dele, decide se há algo a fazer, e age.
6. **O progresso sobe sozinho** — Ticket resolvido avança a Meta; todas as Metas concluídas fecham o Projeto. Nenhuma planilha para atualizar.
7. **Você só entra pra decidir, não pra operar** — cada degrau para numa aprovação. Publicar conteúdo real também. A IA propõe; você decide.

### Onde você vê tudo isso

| Página | Pra que serve |
|---|---|
| **Projetos** | Suas frentes de trabalho ativas |
| **Metas** | A árvore Missão → Projeto → Meta, com % de progresso |
| **Kanban** | Os Tickets — o trabalho real, dia a dia |
| **Agentes** | Seu "time": 38 especialistas (financeiro, comercial, social, jurídico, dados…) |
| **Habilidades** | O que cada agente sabe fazer (190+ skills prontas) |
| **Heartbeats** | Quais agentes estão em modo proativo e com que frequência acordam |
| **Rotinas** | O que roda automático, quando, se deu certo e 🐍/🤖 quanto custa |
| **Gatilhos** | Eventos que acordam um agente na hora |
| **Atividades** | Histórico de tudo que aconteceu — auditoria |
| **Compartilhados** | Relatórios publicados com link estável |

### Um exemplo concreto — gerar clientes pelas redes sociais

1. Você cria a Meta "5.000 seguidores no Instagram até setembro".
2. A IA quebra em Tickets: calendário de conteúdo, 10 posts, 3 reels, sequência de e-mail.
3. O agente de social media pega os tickets e produz.
4. Antes de qualquer coisa ir ao ar, cai uma aprovação no seu Telegram com o texto e a mídia exatos — aprova, rejeita ou pede ajuste.
5. Aprovado, a publicação sai de verdade — e o sistema só marca como publicado depois de confirmar na plataforma. Sem fabricar sucesso.
6. O clique gerado volta com UTM, o painel atribui ao artigo que o produziu, e a Meta avança com número real.

**O ganho pra sua rotina:** você troca "lembrar de postar, escrever, editar imagem, publicar, acompanhar" por "aprovar alguns toques por dia". O sistema é a memória e a mão de obra; você é a decisão.

---

## 🔀 OmniRoute — o gateway de IA da stack

O [OmniRoute](https://github.com/diegosouzapw/OmniRoute) (MIT, criado por [diegosouzapw](https://github.com/diegosouzapw)) roda **dentro da sua stack Swarm** como o serviço opcional `omniroute`, e o EvoNexus fala com ele pela rede interna.

**Por que isso importa:**

- **Fim da dependência externa** — se um gateway público cai (503), seu bot e seus heartbeats caem junto. Self-hosted, o único ponto de falha é a sua VPS.
- **237+ providers com fallback automático** — OpenAI, Anthropic, Gemini, DeepSeek, Groq, NVIDIA e o que mais quiser; com `auto` ele roteia pro melhor disponível e cai pro próximo se um falhar.
- **Codex OAuth embutido** — conecte sua conta ChatGPT Plus/Pro e use a cota do Codex como um provider comum.
- **Compressão de tokens** (RTK/Caveman) — reduz o custo de contexto conforme o conteúdo.
- **Latência mínima** — acesso por alias DNS do Swarm, sem sair pra internet e sem passar pelo Traefik.

```
Telegram / Dashboard / Heartbeats / Rotinas
        |
        v
EvoNexus (provider ativo: omnirouter)
        |
        v  http://omniroute:20128/v1  (rede interna do Swarm)
OmniRoute (self-hosted)
        |
        +-- Codex OAuth (ChatGPT Plus)      [priority 1]
        +-- NVIDIA NIM                       [fallback]
        +-- OpenRouter / Gemini / DeepSeek…  [fallback]
```

**Segurança:** o dashboard do OmniRoute usa **auth nativa** (login + JWT). Não coloque basic-auth do Traefik na frente — as chamadas internas usam header `Authorization` próprio e entram em loop de 401. O `REQUIRE_API_KEY=true` garante que a API `/v1` só responde com chave válida.

**Configuração assistida por agente:** [PROMPT-OMNIROUTE-CONFIG.md](PROMPT-OMNIROUTE-CONFIG.md) — prompt pronto pra colar num Claude Code que audita e otimiza o seu OmniRoute pela management API. Extraído de uma configuração real em produção.

### Seletor de providers

A página **Providers** ganhou o provider **OMNIROUTER** (qualquer endpoint OpenAI-compatível), somando-se aos existentes (Anthropic nativo, OpenRouter, OpenAI, Gemini, NVIDIA NIM, Codex Auth, Bedrock, Vertex).

Regras de resolução de chave que este fork corrigiu — leia antes de debugar um 401:

1. **A chave do próprio provider em `config/providers.json` sempre vence** — é ela que a página Providers grava.
2. As chaves do `.env` são **fallback**, usadas só quando o provider não tem chave própria.
3. `NVIDIA_API_KEY` do ambiente só é enviada para endpoints `*.nvidia.com` — nunca vaza para outros gateways.

O terminal e o chat usam o CLI [OpenClaude](https://www.npmjs.com/package/@gitlawb/openclaude) para providers não-Anthropic, com ambiente limpo por sessão, `--fallback-model` automático e auto-update desativado em produção (um self-update no meio da sessão matava o processo).

---

## 💬 Bot do Telegram multi-provider

No EvoNexus original, o canal do Telegram usa o modo nativo do Claude Code — que **exige login claude.ai dentro do container** e não funciona com providers OpenAI-compatíveis. Este fork adiciona o **modo `provider`**: um runtime próprio que responde pelo provider ativo do dashboard.

| Recurso | Como |
|---|---|
| Responder pelo provider ativo | Chat Completions no provider configurado |
| **Trocar de provider no chat** | `/provider omnirouter` · `/provider status` · `/provider default` |
| Sessão nova | `/new` |
| Áudio → texto | Transcrição via Whisper na API da Groq |
| Imagens | Descreve e responde sobre fotos enviadas |
| URLs | Baixa e resume links colados |
| Memória por chat | Histórico local por conversa, com identificação de quem falou |
| Fallback | Percorre a cadeia de providers se o primário falha |

**Benefício direto:** o bot **sobrevive a redeploys sem re-login** e você escolhe o custo por conversa — o dia a dia no modelo barato, o trabalho pesado com um comando.

**E é onde os gates chegam:** aprovar artigo, aprovar post de rede, aprovar Projeto sugerido, aprovar Meta sugerida. A empresa inteira cabe no bolso.

---

## 📎 Artefatos — relatório com link estável, dentro do seu produto

Todo relatório, análise ou documento visual entregue por um agente é publicado **no próprio Nexus**, via `/shares` — nunca em serviço externo.

**Por quê:** um relatório hospedado fora é um relatório que você não controla, não versiona, não consegue mostrar a cliente e que some quando a sessão morre. Dentro do Nexus ele tem link estável, lista, revogação, expiração opcional e fica junto do resto do trabalho.

O HTML gerado se basta: CSS inline, sem CDN, tema claro **e** escuro, rolagem lateral só onde precisa. E republicar o mesmo arquivo atualiza o conteúdo **no mesmo link** — porque gerar link novo transforma o que você já mandou no Telegram em lixo.

---

## 🧠 Memória — o agente que não esquece entre sessões

Sessões são efêmeras (`/clear`, redeploys, novos terminais); memória não pode ser. Todo agente segue um protocolo de recall no início e de persistência no fim:

| Camada | O que guarda |
|---|---|
| **Hot cache** | Pessoas, termos e projetos ativos — ~90% do que se precisa por dia |
| **Memória do agente** | Aprendizados por agente, com a lição **e quando aplicá-la** |
| **MemPalace (busca semântica)** | Indexa memória, aprendizados de todos os agentes e artefatos de feature — decisões, incidentes e retros |
| **Tickets** | Trabalho inacabado vira ticket, nunca só uma nota na conversa. Conversa morre; ticket fica no kanban |

**Regra prática:** se você mencionar algo que soa como já discutido ("aquele bug", "como fizemos antes"), o agente consulta a base **antes** de dizer que não sabe.

---

## 🧪 A suíte de testes — cada teste é uma cicatriz

**936 testes automatizados** no repositório. Eles não existem por métrica de cobertura: quase todos guardam um erro que aconteceu de verdade em produção, e o docstring explica **por quê**.

Exemplos do que está travado por teste:

- Trocar a keyword de uma pauta já aprovada **devolve o status para proposta** — aprovação é sobre um assunto concreto, não sobre uma posição no calendário.
- Preservar rascunho não pode apagar o slot do dia seguinte — já abriu buraco no calendário e o dia amanheceu com dois posts.
- Cada seed de pauta classifica no funil certo — quatro estavam erradas, e palavra que aparece nos três funis não pode ser critério de nenhum.
- Repositório sem remote **não reporta commit** — informar o que não aconteceu viola a regra de não inventar dado.
- A suíte não fala com o mundo real: um `conftest` bloqueia rede, porque rodar os testes já acordou um heartbeat de produção e queimou token.

---

## 🚢 Deploy completo na VPS (passo a passo)

### Pré-requisitos

- VPS com **Docker Swarm** inicializado (`docker swarm init`)
- **Traefik** rodando na rede externa `network_public` (entrypoint TLS `websecure`, cert resolver `letsencryptresolver`)
- **Portainer** (recomendado) ou SSH para `docker stack deploy`
- Dois subdomínios apontando pra VPS: um pro EvoNexus, um pro dashboard do OmniRoute

### 1. Publique as imagens no seu Docker Hub

O workflow [`.github/workflows/docker-publish-britto.yml`](.github/workflows/docker-publish-britto.yml) builda as imagens Swarm e publica **no seu namespace**. Faça fork e configure em *Settings → Secrets and variables → Actions*:

| Secret | Valor |
|---|---|
| `DOCKERHUB_USERNAME` | seu usuário do Docker Hub (vira o namespace das imagens) |
| `DOCKERHUB_TOKEN` | Access Token (Docker Hub → Account Settings → Security) |

Qualquer push na branch de deploy (ou tag `vX.Y.Z`, ou disparo manual) publica `:latest` e `:sha-xxxx`. Build típico: ~2 min com cache.

### 2. Suba a stack no Portainer

Use a [`evonexus-vps.stack.example.yml`](evonexus-vps.stack.example.yml) como base. Ela sobe 4 serviços:

| Serviço | O que é |
|---|---|
| `evonexus_dashboard` | Flask + React + terminal web + heartbeats (exposto via Traefik) |
| `evonexus_scheduler` | Rotinas agendadas (ADWs) |
| `evonexus_telegram` | Bot do Telegram em modo provider |
| `omniroute` | Gateway de IA (opcional, mas recomendado) |

Variáveis da stack:

| Variável | Como gerar |
|---|---|
| `EVONEXUS_DOMAIN` | seu domínio (ex.: `nexus.seudominio.com.br`) |
| `DASHBOARD_API_TOKEN` | `openssl rand -base64 32` |
| `OMNIROUTE_DOMAIN` | domínio do dashboard do OmniRoute |
| `OMNIROUTE_INITIAL_PASSWORD` | senha de login do OmniRoute |
| `OMNIROUTE_JWT_SECRET` | `openssl rand -base64 48` |
| `OMNIROUTE_API_KEY_SECRET` | `openssl rand -hex 32` |
| `OMNIROUTE_STORAGE_KEY` | `openssl rand -hex 32` — **guarde bem: cifra o SQLite do OmniRoute; perder = perder as configs** |
| `SMTP_*` | opcionais (notificações por email) |

A stack **não contém nenhuma credencial de propósito** — todos os tokens de integrações são configurados depois, pela UI.

### 3. Configure o OmniRoute

1. Acesse o domínio do OmniRoute e faça login com a `OMNIROUTE_INITIAL_PASSWORD`.
2. Na aba de **providers**, conecte o que você usa. A **ordem de prioridade** define o roteamento do `auto`.
3. Na aba **Endpoints**, gere uma **API key** (`sk-...`) para o EvoNexus.

> ⚠️ As keys vivem no SQLite do volume `omniroute_data`. Zerar o volume mata todas as keys. E para zerar no Swarm, `docker volume rm` falha com "volume in use" enquanto containers parados de tasks antigas existirem — remova-os antes.

### 4. Plugue o OmniRoute como provider

Dashboard → **Providers** → **OMNIROUTER**:

| Campo | Valor |
|---|---|
| Base URL | `http://omniroute:20128/v1` (DNS interno do Swarm — não use a URL pública) |
| API Key | a key gerada no passo 3 |
| Model | `auto` |

Marque como ativo. Dashboard, terminal, heartbeats, rotinas e Telegram passam a responder pelo OmniRoute.

### 5. Telegram (opcional)

1. Crie um bot no [@BotFather](https://t.me/BotFather).
2. Dashboard → **Integrations** → salve `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
3. O serviço já sobe em `TELEGRAM_MODE=provider`. Mande um `ping`.

> ⚠️ Cada deploy precisa do **seu próprio bot/token** — dois pollers no mesmo token brigam (HTTP 409).

### 6. Atualizações

Push na branch de deploy → GitHub Actions publica as imagens → na VPS:

```bash
docker service update --force --image SEU_USUARIO/evo-nexus-dashboard:latest evonexus_evonexus_dashboard
docker service update --force --image SEU_USUARIO/evo-nexus-runtime:latest  evonexus_evonexus_telegram
docker service update --force --image SEU_USUARIO/evo-nexus-runtime:latest  evonexus_evonexus_scheduler
```

### Troubleshooting rápido

| Sintoma | Causa provável |
|---|---|
| `401 Unauthorized: chave API inválida/expirada` | Key errada **no providers.json** (o `.env` é só fallback) — ou key do OmniRoute morta por reset de volume |
| Bot responde `All providers failed` | Provider ativo sem chave válida; teste `/provider status` no chat |
| Terminal morre com exit 1 no meio da sessão | Auto-update do CLI (já travado nesta versão) |
| `workspace has not been trusted` como root | Os entrypoints re-seedam o trust a cada boot — confira se está na imagem atualizada |
| Dashboard do OmniRoute em loop de 401 | Basic-auth do Traefik na frente — remova; a auth é nativa |
| Rotina do scheduler "rodou" mas nada persistiu | Rotina não escreve no SQLite direto: o container do scheduler não monta o volume do banco, e escrever no arquivo cria um banco fantasma na camada efêmera. Use a API |

---

## 🧬 O que vem do upstream (e continua aqui)

Tudo do EvoNexus original está preservado: os 38 agentes, as 190+ skills, rotinas/scheduler, heartbeats (protocolo de 9 passos), goals (cascata Mission → Project → Goal → Ticket, com sugestão automática por IA em cada degrau, aprovada pelo humano), tickets com checkout atômico, memória persistente em duas camadas, knowledge base semântica, dashboard completo com auditoria e gestão de usuários, e as 19+ integrações (Google, Linear, GitHub, Discord, Stripe, Omie, Bling, Asaas, Fathom, Todoist…).

Documentação da plataforma: [README original](https://github.com/evolution-foundation/evo-nexus#readme) · [docs.evolutionfoundation.com.br](https://docs.evolutionfoundation.com.br) · [docs/getting-started.md](docs/getting-started.md) · [docs/architecture.md](docs/architecture.md) · [ROUTINES.md](ROUTINES.md) · [CHANGELOG.md](CHANGELOG.md)

---

## 🙏 Créditos & Agradecimentos

Este fork existe porque outros construíram coisas excelentes antes:

- **[EvoNexus](https://github.com/evolution-foundation/evo-nexus)** pela **[Evolution Foundation](https://evolutionfoundation.com.br)** — a plataforma inteira: agentes, skills, rotinas, heartbeats, goals, tickets, dashboard e integrações. Este repositório é um fork derivado; **todo o mérito da base é deles**. Site: [evolutionfoundation.com.br](https://evolutionfoundation.com.br) · Suporte: suporte@evofoundation.com.br
- **[OmniRoute](https://github.com/diegosouzapw/OmniRoute)** por **[Diego Souza](https://github.com/diegosouzapw)** (MIT) — o gateway de IA self-hosted que esta distribuição embute na stack.
- **[oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode)** por **Yeachan Heo** (MIT) — 19 dos 21 agentes de engenharia e as skills `dev-*` derivam do OMC (herdado do upstream). Detalhes em [NOTICE.md](NOTICE.md).
- **[OpenClaude](https://www.npmjs.com/package/@gitlawb/openclaude)** — o CLI que permite rodar o protocolo do Claude Code em providers alternativos.

A camada de upgrade — esteira de conteúdo, gates, medição de funil, painel de rotinas, OmniRoute na stack, seletor de providers, Telegram multi-provider, pipeline VPS e hardening — é mantida por **[Sistema Britto](https://sistemabritto.com.br)**.

---

## 📄 Licença

Este fork mantém integralmente a licença do EvoNexus original: **Apache License 2.0 com condições adicionais de proteção de marca** — preservação de LOGO/copyright nos componentes de frontend e requisito de notificação de uso. Veja [LICENSE](LICENSE).

Em conformidade com essas condições, esta distribuição **não remove nem modifica** o LOGO e as informações de copyright do EvoNexus no console e nas aplicações. Para questões de licenciamento do EvoNexus, contate **suporte@evofoundation.com.br**.

## ™ Marcas

"Evolution Foundation", "Evolution" e "EvoNexus" são marcas da Evolution Foundation — veja [TRADEMARKS.md](TRADEMARKS.md). "Omni-Nexus" nomeia apenas esta distribuição derivada e não é afiliado à Evolution Foundation além da relação de fork. Atribuições de terceiros: [NOTICE](NOTICE) e [NOTICE.md](NOTICE.md).

---

<p align="center">
  <b>Sistema Britto</b><br/>
  <a href="https://sistemabritto.com.br">sistemabritto.com.br</a>
</p>

<p align="center">
  <a href="https://instagram.com/sistemabritto"><img src="https://img.shields.io/badge/Instagram-@sistemabritto-E4405F?style=flat-square&logo=instagram&logoColor=white" alt="Instagram" /></a>
  <a href="https://youtube.com/@sistemabritto"><img src="https://img.shields.io/badge/YouTube-@sistemabritto-FF0000?style=flat-square&logo=youtube&logoColor=white" alt="YouTube" /></a>
  <a href="https://www.linkedin.com/in/fsbritto/"><img src="https://img.shields.io/badge/LinkedIn-fsbritto-0A66C2?style=flat-square&logo=linkedin&logoColor=white" alt="LinkedIn" /></a>
  <a href="https://sistemabritto.com.br"><img src="https://img.shields.io/badge/Site-sistemabritto.com.br-111827?style=flat-square&logo=googlechrome&logoColor=white" alt="Site" /></a>
</p>

<p align="center">
  Um toolkit comunitário não oficial para o <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>
  <br/>
  Base por <a href="https://evolutionfoundation.com.br">Evolution Foundation</a> · Upgrade por <a href="https://sistemabritto.com.br">Sistema Britto</a> · © 2026
  <br/>
  <sub>Não afiliado à Anthropic</sub>
</p>
