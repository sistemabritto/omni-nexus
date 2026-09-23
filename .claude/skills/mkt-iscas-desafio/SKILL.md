---
name: mkt-iscas-desafio
description: "Mapa de controle e execução das iscas gratuitas (comentário→DM no Instagram) do Desafio Monetizar com IA — 21 dias, numeradas 01–21 nos 3 pilares Rastrear(01-07)/Construir(08-14)/Monetizar(15-21). Use quando Felipe pedir 'criar a isca do número NN', 'o gatilho NN não responde', 'qual o estado das iscas', 'falta qual isca', 'documentar a estratégia de iscas', ou qualquer coisa sobre gatilhos numéricos de comentário para DM do desafio. Fonte de verdade: workspace/strategy/[C]estrategia-iscas-desafio-monetizar-com-ia.md."
metadata:
  version: 1.0.0
---

# Iscas do Desafio Monetizar com IA (01–21)

Documento de referência:
`workspace/strategy/[C]estrategia-iscas-desafio-monetizar-com-ia.md`

**Sempre ler esse arquivo primeiro** antes de agir — ele é a fonte de verdade dos gatilhos,
destinos, status de expiração/linguagem e do padrão de qualidade. Este SKILL.md é só o roteador.

## O que é

Cada número 01–21 = um dia/missão do Desafio Monetizar com IA. A cada número, uma **isca
gratuita** é prometida num Reel e entregue via DM automática quando alguém comenta a palavra
gatilho (OpenReply). Os pilares: **Rastrear 01–07 · Construir 08–14 · Monetizar 15–21**.
Isca-pilar = 07 (Mapa Vibe Seller) e 15 (publicar validação).

## Quando usar

- Criar / revisar a isca de um número específico.
- Consultar o estado de todas as iscas ou gatilhos.
- Debugar "o gatilho NN não responde / não manda DM".
- Listar o que falta produzir entre 01 e 21.

## Fluxos

### "qual o estado das iscas?"
Ler §5 (disponibilidade + linguagem) e §4 (gatilhos reais). Reportar a tabela de status
(✅ ativa / 🟡 revisar linguagem / ⬜ a produzir). Não inventar estado — checar ao vivo se
houver dúvida:
```bash
ssh evo-nexus-vps "docker exec \$(docker ps -q -f name=postgres_postgres) \
  psql -U postgres -d openreply -x -c \"SELECT a.name,a.keywords,a.\\\"pendingNextReel\\\",t.slug,t.\\\"destinationUrl\\\" \
  FROM \\\"Automation\\\" a LEFT JOIN \\\"TrackedLink\\\" t ON t.\\\"automationId\\\"=a.id ORDER BY a.keywords[1];\""
```

### "criar a isca do número NN"
1. Tema em §3 (pilar + objetivo daquele dia).
2. Escrever HTML da isca (arquivo único, CSS inline, imagem data:) em `workspace/social/[C]...html`.
3. Humanizar a prosa com a skill humanizer (§6 item 2) — linguagem igual ao Reel, sem jargão no topo.
4. Publicar como Nexus share **sem expiração** (`expires_in=None`, ver skill nexus-artifact-share).
5. Abrir gatilho NN no OpenReply (§6 item 6): INSERT `Automation` + `TrackedLink`, transação única,
   `createdAt=(now() AT TIME ZONE 'UTC')`, `@{username}` nas public replies, modo `pendingNextReel`.
6. Validar: share HTTP 200, `/r/<slug>` dá 302 pro destino, XFO SAMEORIGIN na rota view.
7. Atualizar §3 e §5 do documento estratégico (status + token/share).

### "o gatilho NN não responde"
Checar em ordem: (a) `Automation.isActive` e `postId` correto; (b) `TrackedLink.destinationUrl`;
(c) share destino HTTP 200 + header `X-Frame-Options: SAMEORIGIN` (se abrir em branco, é isso —
ver commit b3f93b6); (d) `WebhookEvent` pra ver o texto exato do comentário (letra O vs dígito 0).

### "falta o quê?"
§3 lista todos os ⬜. Priorizar isca-pilar (07, 15) e números que já têm Reel rodando.

## Gotchas (não refazer esses erros)
- Antes de escrever/revisar o roteiro de uma isca, confirmar que o número/conteúdo que o vídeo promete/flasha bate com o que a DM realmente entrega — mismatch (ex: CTA promete "3 truques" mas o flash mostra um print de "10 segredos/macetes") é erro real de consistência que o Felipe vai pegar.
- Se a isca referencia um vídeo de referência específico (ex: Reel de outra conta), não adivinhar o conteúdo a partir de menções vagas no doc de estratégia. A Graph API só serve mídia da CONTA PRÓPRIA — reels externos (instagram.com/reel/<shortcode> de terceiros) não são acessíveis via API. Baixar o vídeo (yt-dlp / fetch direto) e transcrever com Groq Whisper (skill custom-int-groq, endpoint /openai/v1/audio/transcriptions, model whisper-large-v3-turbo) pra extrair o conteúdo real.
- Linguagem da isca ≠ linguagem do Reel → lead responde "que porra é essa". Humanizar antes.
- `now()` puro no `createdAt` do gatilho → bug de fuso, vincula no reel errado. Usar `(now() AT TIME ZONE 'UTC')`.
- `{username}` sem `@` na public reply → não marca a pessoa.
- Patch direto no container do dashboard some no recriar (backend é camada da imagem). Fix de código → CI + service update.
- Botão CTA usar `nexus.sistemabritto.com.br` (não mais `workflowapi`).
- Ao **renomear** a temática de uma isca já publicada (ex: "3 truques" → "10 segredos"), o nome do `Automation` é só 1 de pelo menos 5 lugares que carregam o texto antigo — sincronizar TODOS na mesma passada: (1) `Automation.name`; (2) `TrackedLink.slug` + campanha UTM (a busca pelo slug/campanha ANTIGO pode não bater — se a query por slug não achar nada, buscar por `automationId` ou por texto do label pra achar o TrackedLink certo); (3) `Automation.dmMessage` (o texto de entrega real da DM, ex: "lista completa dos 3 truques que usei" — fácil de esquecer, não é o campo mais óbvio); (4) label do botão do TrackedLink (ex: "Abrir a lista" → "Abrir os 10 segredos"); (5) doc de estratégia §8.4 (descrição) e §8.6 (checklist/próximos passos). Depois de editar, rodar um `SELECT *` (todas as colunas, não só `name`) no `Automation`+`TrackedLink` daquele gatilho pra confirmar que nenhuma referência ao texto antigo sobrou antes de declarar a rename completa. Ver skill `multi-section-count-sync` — mesmo princípio aplicado a docs HTML.
