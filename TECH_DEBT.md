# TECH_DEBT.md — EvoNexus

Débitos técnicos abertos. Formato: status — item — contexto.

## Open

- **Relatório de 304 reels @caiomktviral ainda é resumido.** O HTML gerado (14.9KB) tem resumo executivo, métricas, top 15, piores e top 5 detalhado, mas o usuário indicou que "ainda tá muito resumido". Deep-dive completo (padrões de conteúdo, fórmulas dos top, análises visuais por segmento) fica pendente.
- **Compartilhar caminho do share é frágil por design.** `file_shares.path` fixo no banco é simples, mas não há UI de "reapontar" — só update manual em SQL. Considerar futuramente um endpoint de repoint ou versionamento de share.
- **Ferramentas desabilitadas no meio da sessão (limite de passos).** Conclusão do relatório exigiu retomada manual; considerar dividir pipelines longos em etapas menores com checkpoints.
- **`Content-Signal: ai-train=no` recuperado em 3 dos 4 domínios (04/09/2026).** `sistemabritto.com.br`, `voicedream.com.br` e `zapmagico.com.br` são Next.js/Vercel com `robots.txt` controlado na origem — sinal reintroduzido sem risco (`sistemabritto/site`, `sistemabritto/voicedream`, `sistemabritto/zapoferta`, branch `fix/content-signal-ai-train-no`/`fix/robots-route-handler-content-signal`). **`blog.sistemabritto.com.br` (Ghost) segue sem o sinal** — Ghost não gera `robots.txt` customizável nativamente, e a última tentativa de injetar isso via Cloudflare foi o que causou o bloqueio total de 03/09. Recuperar aqui exige uma rota customizada servida pela própria origem (Ghost `routes.yaml` ou similar) — não investigado.
- **Teste de CTA em andamento em 6 artigos do blog (pilar RASTREAR).** CTA de fim de artigo trocado de checkout direto para `/quiz` (funil grátis), tag `experimento-cta-quiz` no Ghost, iniciado 03/09/2026. Ler resultado em ~2 semanas (query documentada em `workspace/reports/[C]plausible-e-pivot-editorial-2026-09-03.md`) e decidir se generaliza para os outros ~70 artigos ou reverte.