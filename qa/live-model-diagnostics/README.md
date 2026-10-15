# Diagnóstico Live — contrato v1 do PR48

Contrato consultado read-only em `/home/sistemabritto/Documents/Codex/2026-10-14/task/live-model-policy/docs/ops/live-model-policy-contract.md`. Patch adicional sobre `14b3d1c` (PR47); não sobrepõe PR49 nem altera transport/backend/flags/chaves/política de modelos.

HTTP `/api/live/status` fornece configuredModel, fallbackModels, fallbackBlockedModels e maxProviderAttempts. activeModel HTTP é sempre ignorado como prova de conexão. Uma consulta de metadados ocorre ao montar a página, com cookie/no-store e cancelamento no unmount; não inicia áudio/WebSocket. Iniciar continua dependendo de clique e dos guards de cota existentes.

Somente evento WS model_active confirma modelo ativo. model_attempt/model_switch mostram tentativa/conectando, motivo traduzido e limite informado. stop/erro/reconnect limpam modelo ativo. reconnect_required mostra nova sessão sem retomada de contexto, exige clique e não cria reconexão/replay. Sem modelo confirmado, a UI não presume que configuredModel está ativo. Não há seleção de modelo pelo browser.

Diagnóstico recolhível apresenta candidatos elegíveis versus bloqueados pela verificação de cota e oito eventos recentes em memória, sem persistência/log de exceções arbitrárias, áudio, prompts ou chaves. Erros enum de quota/rate/auth são traduzidos sem disparar fallback ou retry. Contexto não preservado aparece quando informado pelo contrato. Não se fixa um nome/modelo de produção na UI.

## QA

`state.cjs`: HTTP não prova ativo, tentativa/troca/ativo/stop/reset, eventos limitados e mensagens sanitizadas. `qa.cjs`: Chrome local 375×667 e 1440×900, APIs interceptadas, AudioContext/getUserMedia/WebSocket substituídos por mocks inertes. Verifica configuração vs ativo, tentativa/fallback/motivo, confirmação, perda de conexão/contexto, erro de quota sem retry e zero mic/socket no mount. Capturas com “active-fixture” representam eventos simulados, não sessão Gemini real. Não há áudio ou provider chamado. Resultados nesta pasta.

Compatibilidade de payload, consumo de cota real, Safari, leitor de tela e dispositivos físicos não validados nesta rodada. Integração/runtime/rollout pertencem ao executor backend. Não há novo gate de revisão.

Resultado: build TypeScript/Vite, ESLint e ambos os testes passaram. O aviso de chunk >500kB preexistente permanece.
