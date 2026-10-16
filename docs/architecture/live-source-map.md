# Mapa dirigido de fontes → Live

Revisão apenas de código local na base 149c649 + 45099f5. Nenhuma pesquisa externa,
leitura de corpus real, conexão remota, grant ou edição de agente/provedor.
45099f5 segue independente; este incremento é posterior e separável.

| Fonte existente | Caminho real e ACL | Cobertura em 45099f5 / menor lacuna |
| --- | --- | --- |
| Conversas, preferências, decisões Live | ConversationStore → user_id + company_id + revisões correntes → _query_payload → /query ou /read → dispatcher → client_tool_result | Coberto; cinco excertos. Requer o agente invocar tool. Sem dot/import legado. |
| Trabalhos e comentários de tickets | read_company_ticket_page → ACL /api/tickets, company_id SQL → _work_payload → previousWork/query | Coberto; busca seletiva, três trabalhos, fonte/revisão. Decisões aqui são texto registrado, não fatos inferidos. |
| Resultados de tarefas internas | LiveTaskBinding user/company/agent → owned/payload → work-events → _visible_event → histórico/tool | Resultado já persistido é coberto. read_internal_task_status consulta job conhecido. Consulta não reenfileira nem executa tarefas. |
| Decisão de roteamento | ExecutionRouteDecision(user_id,company_id) + binding → /api/execution/decisions/<job> | Referência auditável já aparece em resultados de tarefa. É decisão técnica de execução, não uma decisão empresarial. Falta catálogo de pesquisa dedicado se necessário. |
| Roteiros/documentos de Gravações | Recording.company_id + RecordingScript.number/sha256 → recordings_access.require_company → /api/recordings/<id> | Lacuna segura selecionada: conectar apenas script_revision corrente à mesma query, com hash e ACL canônica. Incremento abaixo. |
| MediaJobs/artefatos de vídeo | company_id, media_jobs:view; gravações vinculadas também passam recordings_access → work-events → link revalidado | Registro conhecido e resultado escrito cobertos. Busca textual de todos MediaJobs não é fornecida por 45099f5. Não abrir arquivos para preencher lacuna. |
| Knowledge Base/pgvector (documentos, decisions, notes) | /knowledge/connections/<cid>/search → knowledge:view → hybrid_search(cid,space_id); v1 usa token/connection e space scope | Não conectado. Há owner_id/visibility/access_rules de espaços, mas nenhum vínculo canônico comprovado empresa Live→connection/space. Não escolher conexão pelo modelo ou reaproveitar token global. Consulta também pode usar embedder remoto; não foi acionada. Próximo passo depende de vínculo/ACL explícito, não só adapter. |
| Docs e workspace | /api/docs e workspace file manager; raízes/path/folder permissions | Não são automaticamente documentos da empresa. Docs de produto e operações misturam audiências; caminhos de workspace não comprovam ownership empresarial. Falta atribuição/seleção autorizada. Não varrer pastas nem importar agent-memory. |
| MemPalace | índice REST global auditado, wing/room opcionais | Excluído: falta dono company/user no corpus legado. Upgrade não cria ACL. Precisa atribuição supervisionada separada. |
| MCPs externos/índice de código | mcp_servers lista configurações; execução pertence aos respectivos runtimes | Catálogo não é ligação ao Live. Não há execução MCP externa comprovada por 45099f5. Não generalizar configuração de projeto como grant empresarial. Índice de código não é memória empresarial autorizada. |

## Incremento de menor risco

Branch feat/live-owned-source-query, sobre 45099f5. Módulo novo
live_recording_source.search_current_scripts reutiliza require_company, exatamente
o gate de Gravações: sessão autenticada, media_jobs:view e grant RecordingAccess
para não administradores; admin segue a política canônica já existente.

SQL filtra company_id e RecordingScript.number == Recording.script_revision antes
da seleção. Devolve até três excertos de 600 caracteres, referência original da
API, recordingId, scriptId, revisão e SHA256. Digest inconsistente, revisão ausente
ou superseded não produz fallback histórico. A ACL é revalidada antes de entregar.

Não lê uploads, mídia, snapshots antigos, feedback de áudio, references_json ou URLs
externas. Não cria tabelas, permissões, conexões ou processos. Uma fonte negada
retorna status=denied/results=[] e não bloqueia memória/tickets já autorizados.
O orçamento de queryResult também remove documentos quando excederia o transporte.

Conexão: helper → _query_payload.documents → /query e queryResult do /read → mesmo
client tool/dispatcher de 45099f5. Nenhum novo nome de tool ou configuração remota.

## Prova e limites

Testes reais de SQL/Flask em fixtures: revisão2 da empresaA retorna fonte/hash;
revisão1, empresaB, digest inválido e revisão corrente ausente ficam excluídos.
ACL canônica é exercitada também com usuário viewer: sem RecordingAccess nega,
reader para empresaA permite, empresaB nega e revogação volta a negar. Não concedeu
acesso em ambiente produtivo: os grants de teste existem só no SQLite temporário.
Teste adicional verifica que denial da fonte não bloqueia a memória autorizada.

Essa fonte é um documento estruturado existente, não uma ligação arbitrária à
Knowledge Base nem um MCP externo. Não prova existência/volume dos roteiros reais
na VPS ou aceitação pelo agente de voz; isso cabe ao integrador após revisão e
publicação separadas. Nenhuma chamada paga foi feita.

## Reproduzir

    TYPESCRIPT_MODULE=/caminho/frontend/node_modules/typescript \
    NODE_PATH=/caminho/terminal-server/node_modules \
    python -B -m pytest -q -p no:cacheprovider \
      tests/backend/test_live_recording_source.py \
      tests/backend/test_live_query_tools.py \
      tests/backend/test_live_continuity_endpoints.py \
      tests/backend/test_managed_live_context.py \
      tests/backend/test_live_conversation_store.py \
      tests/backend/test_live_task_dispatch.py

Os testes HTTP existentes requerem loopback. Fonte/documentos/grants são fixtures;
SDK/socket/provider permanecem simulados conforme a prova de 45099f5.

Validação final do incremento: 59 testes aprovados (incluindo três novos da fonte,
a consulta HTTP local, a continuidade, os guards e tarefas internas), sete warnings
já oriundos da busca de tickets SQLAlchemy. git diff --check limpo.
