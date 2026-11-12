# Proposta: recuperação autorizada para OmniNexus Live

Status: contrato executável isolado, NÃO conectado a rotas ou produção.
Base: PR58 head 5c4cd751d0f8849c6b746accdabd3e75532a5b8e.
Branch: feat/live-memory-contract. Sem dependências, serviços ou acesso a dados reais.

## Comparação com PR58

PR58 usa ElevenLabs WebSocketConnection, managed-session.ts e
createManagedContextTools(). O dispatcher aceita apenas read_current_omni_session,
sem parâmetros, e responde via client_tool_result. O backend managed_live_context.py
valida cookie, administrador pessoal configurado, origem, contexto, sessão runtime
e conversationId. read_context retorna tarefas por empresa; não recupera MemPalace.
O MVP declara que não existe ACL de membros por empresa. Não apresentar essa
restrição de administrador pessoal como multitenancy geral.

A ponte deve estender esse fluxo, não setup_message do Gemini legado. Arquivos
futuros de integração serão managed_live_context.py, managed-context-client.ts e
managed-session.ts, sob coordenação do integrador. Este protótipo NÃO os altera.
O mínimo Live pode ser entregue sem esta ponte.

## Contrato e sequência futura

1. Client tool futuro recall_omni_memory recebe apenas {query:string}. O schema e
   o dispatcher devem rejeitar chaves extras. Modelo não envia tenant, wing, path,
   palace, session ou conversation. contextId e conversationId são capturados
   pelo client autenticado, como no binding existente, não argumentos do modelo.
2. Endpoint futuro POST /api/live/omni-context/<id>/memory recebe o envelope do
   browser {conversationId, query}; aplica _guard(write=True), _owned e vínculo
   imutável de conversa. Revalida runtime e agente como read_context, exige a
   permissão de memória e usa a empresa do registro autorizado no servidor.
   Hoje a política continua pessoal/admin; expansão exige ACL real por empresa.
3. Uma closure authorize() sem argumentos de modelo retorna Scope(company_id,
   runtime_session_id). Revalidar no início e antes de enviar resultado evita
   devolver contexto após revogação. Na integração usar transação/snapshot de
   versão de autorização para alterações concorrentes; uma comparação simples
   não substitui esse controle de autorização distribuída.
4. ScopedBackend.search(scope, query, limit) restringe o corpus ANTES da busca.
   Uma consulta global seguida de pós-filtro não é implementação válida.
   ownership(document_id) lê registro autoritativo supervisionado, não metadados
   do hit. O contrato também valida empresa, sessão, revisão e tombstone de cada
   resultado. None na sessão significa compartilhamento empresarial explícito;
   origem desconhecida significa registro ausente ou verified=False.
5. Retorno: {status,kind:'untrusted_reference_data',memories:[{reference,revision,
   text}]}. Máximo 3 excertos de 600 caracteres; query até 500. IDs são opacos,
   nunca caminhos. Documento recuperado é dado não confiável, sem autoridade para
   instruir ferramentas. Não retornar exceções, caminhos ou credenciais.
6. O client devolve JSON como client_tool_result para ElevenLabs. Configuração
   futura do agente precisa anunciar a ferramenta e tratar os excertos como
   referência, sem prometer memória em respostas quando indisponível/vazia.
   Nenhuma alteração remota do agente é parte deste trabalho.

live_memory_contract.py implementa o núcleo puro dos passos 3–5. A implementação
produtiva de ScopedBackend/authorize/ownership está deliberadamente ausente.
Logo, não habilitar uma rota com adapter global como atalho.

## Índice legado e atribuição supervisionada (não executada)

Produção auditada: MemPalace3.11.0, Chroma1.5.9, 1026 embeddings no palace global.
Metadados não têm company_id/session_id. Wings agentes/desenvolvimento/memoria
não são ACL. Não copiar todo o corpus automaticamente para uma empresa.

Plano:

- Inventariar somente metadados e identificar fontes, revisões e donos, mantendo
  conteúdo sensível fora de relatórios e logs. Registrar ambiguidades para revisão.
- Operador autorizado aprova manifest de ownership por documento/fonte, com ID
  opaco, empresa, visibilidade (empresa ou sessão), revisão/hash, aprovador,
  versão da decisão e tombstone. Fontes mistas devem ser separadas ou atribuídas
  por documento; negar herança por diretório quando houver dúvida. Symlinks e
  mudanças de raiz não devem alterar silenciosamente o ownership.
- Registros não atribuídos permanecem em quarentena, não recuperáveis no Live.
  Sem deduzir autorização de wing, room, nomes de empresa no texto ou do modelo.
- Antes de qualquer migração aprovada, obter snapshot consistente do SQLite e
  artefatos vetoriais sob o playbook do operador. Cópia de SQLite isolada não
  garante consistência com HNSW. Validar restauração fora de produção.
- Em staging, selecionar particionamento compatível com Chroma existente e
  autorização pré-busca: palaces/coleções por empresa verificada, ou adaptador
  com filtro obrigatório por metadados materializados a partir do manifest.
  Sessão privada precisa do mesmo filtro obrigatório. Escolha após medir o
  adaptador existente, sem criar agora outra base ou novo serviço.
- Se materializar company_id no índice, fazer job supervisionado, versionado,
  idempotente, com contagens/hashes reconciliados. Não trocar embeddings durante
  atribuição. Mudança de modelo é migração separada e exige reindexação.
- Tombstones/revisões devem invalidar busca, KG, diário, WAL, closets e caches
  SE esses derivados estiverem habilitados. Ausência de ligação atual no Live
  não garante propagação de exclusão futura. Nunca testar exclusão em produção.

## Rollback e revogação (propostos)

Feature flag desligada por padrão; desligar a ponte deixa o mínimo Live intacto.
Não fazer dual-write nesta fase. Manter índice legado intacto e manifest
versionado; rollback não pode reativar permissões revogadas nem fatos excluídos.
Uma eventual troca de índice precisa de ponteiro versionado, validação de leitura
antes da ativação e snapshots consistentes restauráveis. Contexto já entregue a
um provedor não pode ser “desenviado”: se revogado/excluído, encerrar a conversa e
criar sessão limpa; cache e retomada não podem reinseri-lo. Reconfirmar política
real de retenção do provedor antes de memória sensível.

## Testes reproduzíveis e limites

Da raiz deste checkout:

    python3 -B -m unittest discover -s tests/backend -p test_live_memory_contract.py -v

Dez testes sem libs externas, rede, Flask, Chroma ou provedor. Fixtures em RAM:
empresaA compartilhada, A1/A2 privadas, empresaB e legado sem dono. Fluxo real do
contrato: armazenamento fixture → pré-filtro → recuperação → ownership/revisão
→ contexto → resposta determinística mock. Atualização/exclusão só em RAM.
Há testes de adapter defeituoso cross-scope, parâmetros tenant injetados,
revogação durante consulta, falha sanitizada e limites de payload.

Isso NÃO prova integração HTTP, SDK ElevenLabs, recall semântico, segurança de
prompt injection, autorização concorrente distribuída ou qualidade da resposta
do LLM. Reteste futuro obrigatório: endpoint com fixtures/ACL real e código PR58,
client_tool_call/result simulado pelo SDK, fechamento/troca de contexto enquanto
busca está pendente, consulta no índice staging pré-filtrado, atualização/exclusão
em todos os derivados habilitados. Conversa paga só mediante autorização própria.

## Estimativa e ordem

- Contrato + testes + proposta: entregues nesta branch.
- Endpoint/auth binding e client tool PR58 + testes HTTP/SDK offline: 1–2 dias.
- Inventário/manifest e revisão humana: 1–3 dias técnicos; prazo humano depende
  de quantidade e ambiguidade das fontes e não está incluído.
- Adaptador pré-filtrado, atribuição staging e retestes de atualização/exclusão:
  2–4 dias; mais se KG/diário/WAL realmente participarem.
- Validação/rollout coordenado e rollback ensaiado: 0,5–1 dia após aprovação.

São estimativas, não compromisso de rollout. Bloqueios para ativar: dono dos
1026 embeddings, política explícita de memória compartilhada vs sessão, ACL
real quando sair do MVP pessoal, adaptador com pré-filtro e aprovação de rollout.
