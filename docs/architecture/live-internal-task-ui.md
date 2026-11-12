# Live: UI e client tools de tarefas internas

Patch frontend sobre PR81, consumidor do PR83 (`26539e4`). Sem alteração backend,
registro de tool remoto, flags, modelo, credenciais ou deploy.

| Fluxo | Implementação / evidência | Limite |
| --- | --- | --- |
| Pedido humano de resumo/rascunho | Formulário no mesmo chat; transcript da ação antes do pedido | Servidor revalida ticket, empresa, agente, gates e flags |
| `request_internal_task(ticketId,operation)` | Allowlist no dispatcher SDK real, teste com HTTP/fila simulados | Tool ainda precisa ser registrada no agente remoto |
| `read_internal_task_status(jobId)` / `cancel_internal_task(jobId)` | Mesmo vínculo autenticado; parâmetros extras rejeitados | Cancelamento solicitado não significa subprocesso interrompido |
| Retry de transporte | SHA-256 da conversa SDK + call ID, ou ID da ação humana mantido no singleton | Sem troca automática de ID para job falho/cancelado |
| Progresso, resultado, fonte | `/events`, status privado e leitura explícita do resultado completo no chat | Fontes autorizadas pelo backend; nenhuma URL arbitrária aceita |
| Reconexão | Restaura eventos e revalida até 20 tarefas recentes | Não reexecuta tarefa ao restaurar |

Há uma repetição automática de HTTP somente para resposta não confirmada e erros
transitórios, com o mesmo requestId e payload. Não é retry de execução/provider.
Depois disso, pedido humano sem confirmação conserva ticket/operação/origem durante
navegação SPA e término da voz, exibindo “Repetir mesmo pedido”. Outra conexão fica
bloqueada até confirmar esse pedido. Negação explícita para tarefa conhecida oculta seu texto/link em cache e encerra
a conexão de voz; é preciso retomar com contexto revalidado. Status/resultado podem ser consultados sem
reativar áudio usando o vínculo existente. Logout limpa toda a identidade; fechar
o navegador pode perder uma ação sem ACK. A fila do servidor e os eventos que já
foram confirmados permanecem disponíveis para recuperação autorizada.

Troca de empresa descarta a representação do contexto anterior. Ao retornar, retome
e consulte os eventos antes de repetir uma ação cuja resposta ficou desconhecida.
Sem identidade estável reemitida pelo SDK, uma nova chamada de tool não é considerada
retry da anterior. O agente remoto deve ser configurado para consultar status e não
pedir automaticamente uma nova execução após resultado falho ou confirmação incerta.

O worker do PR83 já emite eventos persistentes. Por isso a UI usa status como reparo
idempotente e não faz criação paralela nem depende de `recordWork` para cada polling.
O hook `recordWork('live_task',id)` também está permitido para reparo explícito.

Contexto/histórico são recuperados no início da conexão Live pelo PR81. O prompt da
tarefa do PR83 ainda recebe ticket/persona limitados, sem todos os fatos/histórico da
empresa. Não há prova de que esses dados adicionais cheguem ao executor da tarefa.
Não há aprovação por voz, publicação, edição do ticket ou novas integrações de harness.

Validação automatizada é sintética, sem CLI/provider, microfone real ou screenshots.
O QA de navegador roda no preview dev com CSP bypass somente no contexto de teste,
porque o cliente HTTP dev usa localhost:8080. Todas as APIs são interceptadas; só
HMR do preview local usa WebSocket real. Isso não valida CSP em produção.

Antes de habilitar: integrar PR81+PR83+este patch, registrar as tools corretamente,
validar isolamento efetivo do CLI/worker e executar o E2E real autorizado separado.
Flags continuam default OFF. Hermes/Codex não ganham adaptador por este patch.
