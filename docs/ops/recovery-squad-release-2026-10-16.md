# Tickets e catálogo — integração sobre ac5e6f5

Inclui 6d30473(PR88) e cf52663. Backend somente: validação de dono em PATCH/bulk, retry de reatribuição sem evento/timestamp duplicado e preflight de thread immutable antes do lote; campo catalog aditivo em GET /api/agents. Não reabre tarefas, não remove bloqueios/aprovações nem reativa heartbeat.

87 testes tickets+catálogo passaram; 56 regressões de ownership/sweep/skills passaram. 42 personas comparadas ao loader real em sete setores. Skills de conhecimento existem nesta base integrada, divergindo da main histórica do autor. operational_status segue not_verified. A mudança não chega ao seletor visual; nenhum frontend/Live/voz/provider foi alterado.

Publicar somente dashboard. Runtime/worker continuam a5410f8. Preservar ENV/dados/sessões/agentes/memórias/atribuições/permissões e configuração remota do agente Live. Backup/rollback image-only para dashboard ac5e6f5; não restaurar DB antigo. Nenhuma compra, ação Cakto/Cloudflare, envio, geração ou chamada paga faz parte da validação.
