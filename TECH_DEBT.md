# TECH_DEBT.md — EvoNexus

Débitos técnicos abertos. Formato: status — item — contexto.

## Open

- **Relatório de 304 reels @caiomktviral ainda é resumido.** O HTML gerado (14.9KB) tem resumo executivo, métricas, top 15, piores e top 5 detalhado, mas o usuário indicou que "ainda tá muito resumido". Deep-dive completo (padrões de conteúdo, fórmulas dos top, análises visuais por segmento) fica pendente.
- **Compartilhar caminho do share é frágil por design.** `file_shares.path` fixo no banco é simples, mas não há UI de "reapontar" — só update manual em SQL. Considerar futuramente um endpoint de repoint ou versionamento de share.
- **Ferramentas desabilitadas no meio da sessão (limite de passos).** Conclusão do relatório exigiu retomada manual; considerar dividir pipelines longos em etapas menores com checkpoints.
- **`Content-Signal: ai-train=no` não está mais declarado nos 4 domínios liberados para IA em 03-04/09/2026.** Desativar o "robots.txt gerenciado" da Cloudflare resolveu o bloqueio de citação, mas junto derrubou o sinal explícito de "não treine com este conteúdo". Recuperar isso exige um `robots.txt` customizado servido pela própria origem — não investigado se o Ghost aceita isso nativamente. Ver `memory/cloudflare-ai-crawl-control-broken.md`.
- **Teste de CTA em andamento em 6 artigos do blog (pilar RASTREAR).** CTA de fim de artigo trocado de checkout direto para `/quiz` (funil grátis), tag `experimento-cta-quiz` no Ghost, iniciado 03/09/2026. Ler resultado em ~2 semanas (query documentada em `workspace/reports/[C]plausible-e-pivot-editorial-2026-09-03.md`) e decidir se generaliza para os outros ~70 artigos ou reverte.