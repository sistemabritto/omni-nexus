# Fatia Live → fila existente → resultado persistente

Implementação local opt-in sobre continuidade `33d84de` e PR78. Sem UI, registro de tool remoto, rollout, nova credencial, Telegram ou execução real de provider. Não altera o SHA3a282bd do PR78.

## Contrato para UI

Base `/api/live/omni-context/<contextId>`; mesmos guard cookie pessoal/admin + Origin HTTPS, pessoa/empresa/agente/conversa e memory:view. IDs do usuário/empresa/agente são derivados do contexto, nunca aceitos do modelo.

- `POST /tasks`: `{conversationId,requestId,operation,ticketId}`. operation é somente `summarize_ticket` ou `draft_ticket`. Responde201 `{jobId,status,reference,replayed:false,mode:'internal_text_no_tools'}`; retry idêntico responde200 com mesmo job e `replayed:true`. RequestId reaproveitado com outro ticket/operação/conversa lógica retorna409. Não aceita prompt, comando, shell, arquivo, modelo, provider, usuário, empresa ou URL arbitrários.
- `POST /tasks/<jobId>/status`: `{conversationId}`. Revalida ownership, devolve status/links e repara evento escrito caso tenha faltado, sem reexecutar.
- `POST /tasks/<jobId>/cancel`: `{conversationId}`. Pendente cancela por CAS; rodando responde `cancel_requested`. Só depois de retorno do subprocesso o worker confirma `cancelled` e descarta saída. Não promete interrupção imediata nem devolução do custo já incorrido.
- `GET /api/live/tasks/<jobId>`: link privado ao resultado/status, com output limitado a12000caracteres quando success. Login e ownership são revalidados. Ausente, empresa inativa/movida, agente/usuário revogado ou token de API retornam negação sem conteúdo.
- `/work-events` passa a aceitar `recordType:'live_task'` para replay do resultado. Worker já grava eventos no store da conversa lógica; o polling `/events` da continuidade os mostra mesmo se a conexão Live cair. recordWork('live_task',jobId) é reparo opcional após receber o jobId.

Idempotência de transporte: UI deriva requestId estável do tool_call_id capturado do SDK/conversa ou de ação humana persistida; o modelo só fornece ticketId/operação. Retry de rede reutiliza o mesmo ID. Não gerar ID novo para repetir automaticamente um job falho/cancelado. Novo pedido humano é outra ação. Erros e fontes são apresentados no chat, não só falados.

## Execução e limites efetivos

Reutiliza OrchestrationJob e OrchestrationWorker/chat_orchestrator, não cria outro executor. Nova LiveTaskBinding guarda user/company/agent/conversa lógica/ticket/versão/requestId e metadados da tentativa. Job+binding são confirmados na mesma transação; unicidade no banco evita jobs duplicados. Worker faz claim CAS antes de chamar provider. `live_pending` impede um worker antigo, que só lê pending, de executar essa tarefa pelo caminho genérico durante rollback.

Somente ticket atribuído ao agente do contexto, da empresa ativa, open/in_progress, sem lock, motivo de bloqueio, approval_id ou requires_human_approval. Revalida owner/gates/revisão antes de executar e autorização novamente antes de expor resultado. Não muda ticket, não fecha trabalho nem remove aprovações. Novo rascunho não é publicação ou aprovação final.

O prompt usa snapshot limitado do ticket e persona do servidor antes dos marcadores de memória; não importa memória global/dot. Esta fatia ainda não inclui todos os fatos/histórico da empresa no prompt da tarefa. A recuperação da continuidade continua no endpoint /read; a integração completa precisa selecionar referências autorizadas e verificar sua versão antes de fornecê-las ao executor.

`invoke_with_fallback` é o mesmo motor, com routing_key do agente e política por chamada no_tools. OpenCode recebe config de processo com ferramentas builtin explicitamente desabilitadas/deny; --auto é retirado. Claude recebe --tools vazio, MCP explícito vazio e sem bypass. OpenClaude nesse modo falha fechado por adaptador não comprovado. Calls legados mantêm comportamento anterior; esta mudança não declara que o YOLO legado foi corrigido globalmente. Diretório isolado por job, sem adotar sessão antiga. Nenhuma configuração compartilhada é sobrescrita.

Os testes comprovam a construção de argv/config e a fila com provider simulado; ainda é obrigatório verificar a versão efetiva do CLI/MCP/plugins em staging antes de habilitar. Configuração de ferramentas não é apresentada como sandbox completo do sistema operacional. Aliases/modelos registrados são solicitados, não prova do modelo upstream. Não há instalação de harnesses ou router novo.

Flags estritas `NEXUS_LIVE_CONTINUITY_ENABLED=true` e `NEXUS_LIVE_TASKS_ENABLED=true` são carregadas em app.config no boot; defaultsOFF. O store dedicado e a tabela de binding conservam dados ao desligar. Não habilitar tasks só por existir código: validar políticas efetivas, lifecycle/cancelamento, UI e E2E permitido antes do rollout. Criar as tabelas novas via inicialização create_all do app; nenhuma coluna existente foi reescrita.

## Registro ElevenLabs pendente

Nada foi alterado no agente remoto. Client tools futuras: request_internal_task(ticketId,operation), read_internal_task_status(jobId), cancel_internal_task(jobId). O client dispatcher precisa fazer allowlist desses nomes, injetar conversationId/contextId e requestId de origem confiável, e devolver resultados com jobId/status/link ao modelo. O endpoint não é webhook público e não aceita chave/escopo fornecido pelo modelo. Não confundir esse registro com a única tool read_current_omni_session hoje implantada.

## Aprovação por voz de ação crítica — contrato a implementar, não bypass

As operações acima são internas e preservam qualquer gate existente. Ticket crítico/gated é negado; a fatia NÃO aprova publicação ou outra ação externa. A aprovação obrigatória de ferramentas dot/Codex continua fora deste produto; este contrato não contorna as rejeições atuais.

Reusar pending_approvals e a lógica do aprovador existente. Já há dashboard-decision por cookie admin e decision do Telegram com allowlist individual/bridge; _apply_decision possui CAS status pending. Porém o esquema atual só aceita publish/decomposition/project_suggestion/goal_suggestion/pauta_ciclo e não contém um binding Live por company/session/digest. Também não se deve presumir que o CAS atual verifica atomicamente payload/expiração. Portanto não criar um gate inventado nem ligar decisão por voz diretamente ao helper antes dessa adaptação.

Contrato da próxima pequena fatia: servidor prepara desafio de decisão vinculado a user/company/conversa/approvalId, ação e alvo exatos, versão/hash do payload, permissões, expiração e nonce de uso único. Live apresenta/lê o resumo exato e a frase de confirmação; transcrição final de usuário autenticado identifica a decisão/desafio, sem confirmar por fala do assistente, texto citado, parâmetro confirmed do modelo ou correspondência frouxa. A identidade é a sessão autenticada; não alegar biometria de voz. Modelo não escolhe company/user/versão/decided_by.

Antes de consumir: revalidar ACL, ação/hash/versão, gate ainda pending, expiração, revogação e ligação da transcrição ao contexto; CAS no mesmo ponto de decisão/claim com idempotência. Mudança invalida o desafio. Aprovação repetida não repete efeito; aprovação não muda permanentemente permissões. Negar aceita feedback ligado à mesma decisão. Auditoria registra origem voz, usuário, contexto, evento da transcrição, digest e resultado; não exige salvar áudio bruto.

Para crítico/urgente, o pedido pode ser encaminhado pelo fluxo Telegram existente com Aprovar/Negar e feedback, dentro das autorizações aplicáveis. Resultado deve chegar aos eventos persistentes da sessão Live e ser falado/mostrado. Nenhuma mensagem real é enviada nesta entrega. Antes de ativar: testes de expiração, revogação, payload alterado, decisão duplicada/concomitante, usuário/empresa errados e zero efeitos reais. Essa aprovação por voz ainda não foi implementada nem validada.

Validação local: suíte combinada anterior com 116 testes aprovados (continuidade/voz/tickets/fila/fallback). Após as últimas proteções, 41 testes focados passaram, incluindo pending_approvals pendente mesmo com flags de ticket obsoletas e regressões do dispatcher/fallback. Os testes nunca chamam CLI, LLM, Telegram ou ação externa real.
