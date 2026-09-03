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

