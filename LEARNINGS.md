# LEARNINGS.md — EvoNexus

Aprendizados duráveis de sessões. Formato: data — contexto → lição.

## 2026-08-15

- **Shares Nexus não são apontados por diretório, e sim por caminho fixo no banco.** O token em `file_shares` (SQLite) guarda `path`; `/api/shares/<token>/view` serve sempre aquele arquivo. Trocar o conteúdo de um link exige `UPDATE file_shares SET path=... WHERE token=...`. Copiar arquivo para `workspace/shares/` não muda o que o link serve — o caminho no banco vence.
- **Investigar o sistema antes de assumir cache.** "Continua mostrando 105" não era cache do navegador nem do Nexus — era o token apontando para o arquivo antigo. Consultar `file_shares` no SQLite resolveu a causa raiz em uma query.
- **Relatório de 304 reels do @caiomktviral**: pipeline coleta (feed/user + max_id) → Groq Whisper (288 transcritos) → Britto-Vision/OmniRoute. Dados em `workspace/reach-caiomktviral-100/`. HTML gerado: `workspace/reports/[C]analise-304-reels-caiomktviral.html`.

## 2026-09-02

- **O blog é a saída fiel do prompt da esteira, não uma soma de artigos.** 76
  artigos publicados, 0 com a tese, 0 com caso real, 0 links internos, 1 com
  meta_title. Nenhum artigo estava errado sozinho; o prompt descrevia a empresa
  como "vende automação e operação com IA" e o blog virou exatamente isso.
  Auditar conteúdo gerado por pipeline sem ler o prompt que o gera é auditar o
  sintoma. Corrigir artigo por artigo, a 3 posts/dia, é refeito em 25 dias.
- **`robots.txt` do blog bloqueia GPTBot, ClaudeBot, Google-Extended, CCBot,
  Bytespider, Applebot-Extended, meta-externalagent e Amazonbot.** Vem do
  Cloudflare, antes das diretivas do Ghost. Qualquer trabalho de GEO rende zero
  enquanto estiver de pé. `Content-Signal: search=yes` preserva o SEO clássico.
  Bloquear treino (`ai-train=no`) e bloquear citação em resposta são trade-offs
  diferentes hoje amarrados na mesma chave.
- **Ghost Admin API não devolve o tema para token de API** (403
  `NoPermissionError` em `/themes/` e `/themes/{n}/download/`), mesmo padrão já
  conhecido do endpoint de integrações. Sem sessão de staff não há backup, e sem
  backup não se toca no tema, por mais óbvio que o bug pareça.
- **Cloudflare barra o User-Agent do urllib/requests no blog** com `error code:
  1010`, tanto na Content API quanto na Admin API. Mesmo comportamento já
  registrado para o EvoCRM. É preciso User-Agent de navegador.

## 2026-09-03/04

- **Ghost Admin API bloqueia POR ESQUEMA, não por escopo.** `PUT /settings/`,
  `/users/{id}/`, `/themes/`, `/redirects/download/` recusam **qualquer**
  token de integração com 403, mesmo com todas as permissões. É desenho do
  Ghost: só sessão de navegador escreve nesses endpoints. Achado idêntico do
  outro lado da stack: `PATCH /zones/{id}/bot_management` da Cloudflare
  devolve `10405 Method not allowed for this authentication scheme` pra
  qualquer campo, mesmo com a permissão certa no token. Duas plataformas
  diferentes, o mesmo padrão: existe uma classe de configuração que API token
  simplesmente não alcança, e vale checar isso ANTES de gastar tempo tentando
  granularidade fina — às vezes a saída certa é a bruta (desligar o recurso
  inteiro) porque a fina está tecnicamente inacessível.
- **Dashboard mente, arquivo servido não.** O painel do AI Crawl Control da
  Cloudflare mostrava "Allow" pra todos os bots via API enquanto o
  `robots.txt` ao vivo, sem cache, continuava bloqueando. A única fonte
  confiável foi testar o artefato real (`curl` com User-Agent do bot,
  `cf-cache-status: MISS`), nunca o resumo de um painel — nem o assistente de
  IA embutido no próprio painel da Cloudflare escapou desse erro.
- **CSP `default-src 'none'` num artefato público mata qualquer JS, inclusive
  tracking legítimo.** Medir clique de CTA num HTML servido por
  `/api/shares/<token>/view` não pode usar `fetch()` — a defesa contra prompt
  injection (ver `test_share_publico.py`) não abre exceção pra caso de uso
  bom. Resolvido com redirect no servidor (`<a href>` puro pra
  `/click?to=...`, sem script nenhum). Ver
  `memory/rastreio-de-clique-em-artefato-share.md`.
- **O gate de autenticação global tem lista própria de caminhos públicos,
  separada do decorator da rota.** Uma rota nova sem `@login_required`
  ainda cai em 401 se `app.py::auth_middleware` não souber que aquele
  caminho é público — descoberto só testando em produção, depois de um
  deploy. Checklist pra próxima rota pública: decorator ausente **e**
  caminho na condição de `auth_middleware`, os dois, sempre.
- **O blog já entrega tráfego, o problema é depois do clique.** Medido via
  SQL direto no Supabase do site: sessões vindas do blog convertem em CTA a
  0,9% contra 48% do Instagram, e 0% navegam pra uma segunda página — mesmo
  o blog já sendo a maior origem de visita pra `/sistema` e `/whatsapp`.
  Causa provável: as duas páginas pedem pagamento na primeira tela, sem
  passo grátis, enquanto o padrão que converte 48% é um gate gratuito. Teste
  em andamento com `/quiz` como degrau intermediário. Ver
  `memory/funil-real-blog-nao-converte.md`.

