# TECH_DEBT.md — EvoNexus

Débitos técnicos abertos. Formato: status — item — contexto.

## Open

- **Relatório de 304 reels @caiomktviral ainda é resumido.** O HTML gerado (14.9KB) tem resumo executivo, métricas, top 15, piores e top 5 detalhado, mas o usuário indicou que "ainda tá muito resumido". Deep-dive completo (padrões de conteúdo, fórmulas dos top, análises visuais por segmento) fica pendente.
- **Compartilhar caminho do share é frágil por design.** `file_shares.path` fixo no banco é simples, mas não há UI de "reapontar" — só update manual em SQL. Considerar futuramente um endpoint de repoint ou versionamento de share.
- **Ferramentas desabilitadas no meio da sessão (limite de passos).** Conclusão do relatório exigiu retomada manual; considerar dividir pipelines longos em etapas menores com checkpoints.