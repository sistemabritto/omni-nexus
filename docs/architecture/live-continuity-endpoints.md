# Live: continuidade, trabalhos anteriores e eventos escritos

Branch feat/live-continuity-endpoints, base cbd440e, derivada da PR58 5c4cd75.
Implementação local, não publicada/deployada. Sem edição de UI, dependências,
agente remoto, dados reais ou chamadas pagas. Execução continua no dispatcher.

## Configuração e isolamento

Feature flag app.config['NEXUS_LIVE_CONTINUITY_ENABLED'] is True, desligada por
padrão. NEXUS_LIVE_CONTINUITY_DB aponta para arquivo SQLite DEDICADO; default
é dashboard/data/live-continuity.sqlite3. Nunca usar o mesmo arquivo do context DB.
Schema/receipts e bindings são criados somente quando habilitado, no ambiente onde
rodar. Não há migração/import de MemPalace, histórico dot ou sessões sem ownership.

Reutiliza guards PR58: cookie pessoal/admin configurado, pessoa ativa, empresa
ativa, agente autorizado, Origin HTTPS same-host, contexto do usuário, vínculo
imutável conversationId. APIs novas revalidam runtime e memory:view. Trabalhos
exigem ainda tickets:view ou media_jobs:view e company_id igual ao do contexto.
IDs de usuário/empresa não vêm do modelo. ACL atual continua pessoal/admin;
expansão a membros exige ACL empresarial real, não uma ACL inventada.

Conversa lógica persistente difere de runtime e conexão ElevenLabs. Contexto novo
pode retomar latest(user,company) autorizado; a ligação de cada contexto é imutável.
A primeira leitura/gravação de contexto iniciado pelo usuário abre a primeira
conversa; conexões seguintes retomam latest. Nova conversa exige ação explícita
em contexto novo, antes de /read ou transcrições. Store serializa abertura inicial
para evitar criação duplicada por duas requisições concorrentes.

## Contrato HTTP para integrar na UI

Todos os POST abaixo ficam sob /api/live/omni-context/<contextId> e recebem
conversationId capturado da conexão, nunca escolhido pelo modelo:

| Sufixo | Outros campos aceitos | Efeito |
| --- | --- | --- |
| /continuity | nenhum | retoma a conversa lógica |
| /continuity | newConversation:true | inicia nova por escolha explícita em contexto sem binding |
| /transcript | eventId, role:user/assistant, text | gravação final idempotente |
| /notes | requestId, kind:fact/decision/pending/preference, text, confirmed:true | nota explicitamente confirmada |
| /notes | anteriores + eventId, expectedRevision, retract?:bool | correção/retratação com controle de revisão |
| /work-search | query | busca seletiva de trabalhos anteriores |
| /work-events | recordType:ticket/media_job, recordId | persiste andamento/resultado escrito autorizado |
| /events | after?:int | stream paginado de revisões para restaurar chat |

Receipts transacionais: mesmo ID e payload devolvem o mesmo event_id/revision;
payload divergente retorna 409. Transcrições usam hash(connectionId:eventId), notas
requestId, trabalhos hash(tipo+referência+revisão). Nenhum texto ou URL de resultado
é aceito por /work-events: backend deriva tudo do registro autorizado.

/events retorna logicalConversationId, events, next e hasMore (até 100 revisões).
Cada evento tem seq, event_id, revision, kind, text, source, verified e retracted;
resultados incluem links, reference, recordRevision e recordUpdatedAt.
UI faz upsert por (logicalConversationId,event_id), conservando maior revision, e
avança after=next. Retratação remove a representação atual. Não concatenar
cegamente cada replay. Progress e result são eventos distintos quando o estado do
registro mudou; retry do mesmo estado não produz outro evento. Em reconnect, usar
novo context/provider com a mesma conversa lógica e restaurar eventos paginados.

Notas confirmadas são declarações do usuário, não verificação externa de verdade.
Transcrições do browser permanecem não verificadas. Sugestão do modelo não deve
chamar /notes para confirmar a si mesma. Resumos distinguem fatos/inferências e
mantêm origem/revisão. Não há treinamento de pesos nem autoedição de políticas.

## Entrega ao provedor

/read, já consumido pelo client tool read_current_omni_session, acrescenta:

    continuity: {status,logicalConversationId,summaryRevision,
      summary:{facts,inferences,decisions,pending,preferences},
      kind:'untrusted_reference_data',current:[...],truncated}
    previousWork: {source,kind,results:[...],limit,coverage}

Seleciona até 30 eventos vigentes, excertos de 600 caracteres, orçamento de cerca de
6000 caracteres JSON para current antes dos metadados/summary. O resumo estruturado
repete somente os itens selecionados, não todo o histórico. SummaryRevision aponta
para a revisão derivada do store. Não envia histórico de auditoria nem fatos
retratados. Aplicar orçamento final de tokens no transporte antes de produção.

Resultados escritos também chegam por esse read. Antes de reexibir um resultado,
o backend revalida acesso ao registro original; movido/deletado/revogado produz
retracted=true, sem texto, links ou source original. Links de vídeo são calculados
na leitura, nunca persistidos como signed URL. GET /api/live/omni-context/<id>/
artifacts/<jobId>/video revalida cookie, pessoa, empresa e media_jobs:view e somente
serve arquivo existente sob media_workspace_root com Cache-Control:no-store.
Links externos livres, result_json, caminhos locais e URLs sugeridas pelo modelo
não são incorporados. Links externos de registros exigem adaptador validado futuro.

## Trabalhos anteriores: cobertura exata

/work-search reutiliza read_company_ticket_page e ACL canônica /api/tickets;
company_id é filtro SQL antes da leitura. Seleção lexical de até 4 termos úteis,
até 3 tickets e 2 comentários relevantes por ticket. Na leitura ao provedor a
consulta é derivada da última transcrição de usuário persistida. Não é busca
semântica e pode perder sinônimos; mantém ordenação canônica da API.

Descrição, status e comentários podem conter resultados, decisões ou roteiros;
referências originais e hash de conteúdo/updatedAt estabelecem versão atual.
Não é arquivo histórico de todas as versões. Tickets sem company_id são excluídos.
Por política pessoal/admin, tickets da empresa são compartilhados e não precisam
ter created_by igual ao usuário. Conversas são privadas por user_id+company_id.

/work-events suporta tickets e media_jobs existentes com company_id explícito.
Mídia retorna link do trabalho original e vídeo somente se caminho resolve dentro
da raiz permitida e arquivo existe. Não percorre arquivos arbitrários, não abre
workspace/roteiros soltos, nem executa/renderiza/publica. Não lê KG, diary, WAL,
MemPalace legado ou dot. Outras fontes exigem demonstrar ownership antes de ampliar.

## O que ainda depende do executor UI/integrador

Nenhum arquivo UI foi editado. É necessário ligar:

1. Transcript final e texto enviado → /transcript, com ID estável até saved:true.
   Não reenviar parcial como final. O backend não observa o WebSocket direto.
2. Conexão → /continuity; restauração visual via /events paginado. Desligar voz,
   reload e troca de voz preservam logicalConversationId; não chamar new por isso.
3. Início de conexão → read_current_omni_session ou mecanismo suportado do SDK para
   reidratar contexto. Dispatcher atual só entrega quando agente chama tool.
   Esta branch não altera configuração remota, voz ou agente v4.
4. Dispatcher existente, após criar/atualizar trabalho → /work-events com ID do
   registro; UI atualiza /events durante chamada. Sem esse hook ou polling, os
   eventos não aparecem automaticamente. Não foi introduzido executor paralelo.
5. Consulta sobre trabalhos → persistir pergunta antes do tool read, ou futuro
   tool query-only para /work-search coordenado com UI.
6. Ao corrigir/retratar/revogar conteúdo já enviado, fechar e reidratar conexão limpa
   segundo capacidades do SDK. Não se pode retirar texto já transmitido.

A menor fatia backend funcional está entregue e testada no seam HTTP→dispatcher.
Só se pode prometer captura/exibição automática após esses hooks UI. Retenção,
eliminação física, backup/restauração e ACL transacional de revogação distribuída
continuam requisitos antes de rollout amplo. Rollback desliga flag e conserva dados.

## Evidência reproduzível

Flask/SQLite temporários exercitam gravação, retry, reconnect, ACL, correção e
busca anterior. Harness carrega TypeScript real managed-session.ts e
managed-context-client.ts da PR58, sem modificá-los. JSON real produzido pelo Flask
é fornecido ao fetch simulado, client_tool_call é disparado e sendMessage captura
client_tool_result com texto persistido/referência anterior/resultado escrito.
Isso prova entrega no limite do transporte mock, não SDK/LLM/provedor real.

Usar dependências já instaladas do projeto:

    TYPESCRIPT_MODULE=/caminho/frontend/node_modules/typescript \
    NODE_PATH=/caminho/terminal-server/node_modules \
    python -B -m pytest -q -p no:cacheprovider \
      tests/backend/test_live_continuity_endpoints.py \
      tests/backend/test_managed_live_context.py \
      tests/backend/test_live_conversation_store.py \
      tests/backend/test_live_memory_contract.py tests/tickets/test_tickets.py

O teste PR58 actual_terminal_http abre servidor 127.0.0.1 e requer permissão de
loopback. Demais testes do provider não abrem rede. Todos dados e vídeos são fixtures.

Validação final desta fatia: 70 testes aprovados (9 endpoints novos, 10 PR58,
9 store de continuidade, 10 contrato de recuperação, 32 tickets), incluindo o teste
HTTP loopback e o dispatcher TS real com provider simulado. Há 30 warnings de
SQLAlchemy das rotas/testes existentes, sem falhas. git diff --check limpo.
