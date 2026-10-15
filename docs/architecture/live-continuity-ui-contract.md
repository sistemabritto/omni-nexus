# UI de continuidade — preparação isolada

LiveContinuityPanel não está montado em App/Live. Não há endpoint novo ou fluxo produtivo ativado neste PR. O adaptador depende da fatia backend em desenvolvimento; o integrador deve confirmar o contrato final antes de conectá-lo. Não muda modelo, voz ou agente remoto.

O contrato foi lido na implementação local de endpoints do executor de continuidade: POST `/api/live/omni-context/:contextId/continuity`, body `{conversationId}`; POST `.../work-search`, body `{conversationId,query}`. O segundo ID é da conexão do provedor obtida pelo SDK, fechado no adaptador; não é ID lógico nem ID de usuário/empresa. Esses valores nunca vêm de argumentos do modelo. Credencial do provedor não está no adaptador. O servidor mantém ownership, empresa, agente e vínculo imutável; o contexto da UI não é ACL.

`createBoundContinuityGateway` expõe somente resume/searchWork. Recurso desabilitado/404 é indisponibilidade, não histórico vazio. O backend retorna current (revisões vigentes), summaryRevision, truncated e kind=untrusted_reference_data. A UI chama isso de contexto atual recuperado; não promete histórico completo nem envia audit history ao modelo. Exibe fonte, revisão e confirmação de cada registro. Trabalhos vêm de tickets/comentários autorizados e sua cobertura limitada fica explícita; referências externas não viram links.

`onResume(snapshot)` é responsabilidade do controlador/integrador: reidratar a conversa pelo mecanismo suportado e confirmar a aplicação. Apenas ler o snapshot não prova que o provedor o recebeu. Nova conversa exige callback separado que obtenha vínculo fresco e faça a ação explícita autorizada pelo backend. A UI não cria automaticamente ao carregar, encerrar, trocar voz ou buscar trabalhos.

`writeStatus` deve refletir ACK real de gravação. Pending/error não são persistência confirmada; a UI impede iniciar outra conversa nessas condições. Nova conversa fica bloqueada com conexão ativa. Alterações/correções/retrações continuam no backend e não são implementadas neste PR.

Para trocar empresa/usuário, o controlador deve descartar o gateway antigo, fechar conexão, invalidar resultados em voo e montar o painel com nova key e gateway autorizado. Nenhuma sessão legada sem dono é adotada. O componente também invalida resultados atrasados ao trocar gateway/empresa ou desmontar. Trocar voz não cria outra conversa lógica nem deve apagar transcrições; reconexão e gravação idempotente são responsabilidade do controlador/backend, ainda não integrados por esta preparação.
