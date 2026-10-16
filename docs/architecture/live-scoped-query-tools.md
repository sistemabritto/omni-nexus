# Live: consulta sob demanda além do bootstrap

Base auditada: release/audio-providers-reviewed, 149c649d73599c436975069a36360709debf8012.
Branch isolada: fix/live-scoped-query-tools. Nenhuma publicação ou deploy nesta fatia.

## Diagnóstico concreto

- _work_payload já consulta a API/ACL canônica de tickets. Sem pergunta salva,
  retorna uma amostra declarada de três tickets concluídos; isso não é memória
  completa nem pesquisa de sessões.
- managed-context-client só expunha read_current_omni_session sem argumentos.
  managed-session aceitava esse nome e três operações de tarefas internas. Não
  havia ferramenta de consulta query-only nem dispatcher para /work-search.
- A memória enviada pelo /read era limitada aos últimos 30 eventos da conversa
  atual. Decisões correntes de outra conversa do mesmo usuário/empresa não eram
  pesquisáveis por essa chamada.
- /api/mcp-servers é catálogo de configurações, não um executor no Live. O .mcp.json
  auditado não declara MemPalace. MCPs externos configurados não estabelecem
  automaticamente ACL empresarial nem autorização de acesso aos seus dados.
- MemPalace produtivo auditado anteriormente possuía corpus global sem company_id/
  user_id. Não é seguro apontar o agente de voz diretamente para esse índice.
  Índice de código tampouco deve ser tratado como memória empresarial com dono.

## Menor correção

Reutiliza os stores, APIs, guards e transporte já existentes, sem framework RAG,
serviço, pacote, schema, reindexação ou credencial nova:

1. ConversationStore.search consulta revisões vigentes não retratadas via SQL,
   JOIN com conversations e filtros user_id/company_id antes de selecionar
   candidatos. Revalida autorização por conversa e no retorno. Busca lexical
   limitada a quatro termos, cinco hits, até 100 candidatos do mesmo escopo.
2. POST /api/live/omni-context/<id>/query aceita somente conversationId do browser
   vinculado e query (1–200 caracteres). Aplica _continuity_request: cookie,
   pessoa/admin ativo, Origin, empresa/agente, memory:view e runtime atuais.
   Reutiliza _work_payload/tickets:view para até três trabalhos. Resultados de
   trabalho persistidos são revalidados por _visible_event antes de retornar.
3. Retorna fonte, conversa/evento, revisão, kind, verified, excerto até 600 e links
   já autorizados. Texto é untrusted_reference_data. Não promove inferências.
4. search_omni_context é alias client-tool opcional com único parâmetro query.
   IDs de empresa, usuário, sessão, palace, MCP ou ferramenta são rejeitados.
   Browser captura os vínculos; modelo nunca escolhe tenant. Dispatcher aguarda
   bootstrap e flush de transcrições antes da consulta; não executa tarefas.
5. read_current_omni_session continua sem parâmetros. Seu /read agora acrescenta
   queryResult da última pergunta de usuário persistida: pesquisa a história Live
   própria, inclusive conversas anteriores, sem depender do alias novo. Os trabalhos
   permanecem em previousWork, evitando duplicação no payload. QueryResult é
   reduzido ao espaço disponível antes do limite de transporte. Sem pergunta útil,
   devolve resultado vazio rotulado, não uma alegação de memória completa.

O watermark, raw audio event_id, listener SDK de drenagem, playback e polling de
áudio foram preservados. A alteração de managed-session se restringe à whitelist
cliente e seleção da ferramenta, em quatro linhas de lógica. Nenhum código de
áudio ou bootstrap foi substituído.

## Escopo de acesso (sem novos grants)

História Live: somente mesmo usuário E mesma empresa, vinculados por servidor.
Conversas anteriores desse mesmo dono passam a ser pesquisáveis; isso é a ligação
funcional solicitada, não compartilhamento entre usuários ou empresas. Não adiciona
roles, permissões ou exceções. Trabalho empresarial segue a permissão tickets:view
existente sob o MVP pessoal/admin; não inventa restrição por created_by.

Explicitamente excluídos: embeddings MemPalace sem dono, histórico privado da dot,
arquivos arbitrários, índice global de código e execução de MCP indicado pelo
modelo. Nenhuma chamada MCP externa é apresentada como se tivesse acontecido.
Fontes adicionais precisam demonstrar ownership/ACL e conexão antes de integração.

## Prova disponível e limites

- Testes de banco reais sem mocks de recuperação: quarto ticket ausente do
  bootstrap é encontrado por Zephyr; decisão revisada de conversa anterior do
  mesmo usuário/empresa chega com revision=2; revisão obsoleta/retratada, empresaB,
  usuário32 e ticket company_id NULL ficam excluídos.
- Teste localhost abre Flask em 127.0.0.1, usa cookie assinado e Origin reais por
  fetch nativo Node, e executa os módulos TypeScript reais de client tool e
  ManagedSession. SQLite, guards e consultas são reais em fixtures temporárias.
- Duas respostas são capturadas em client_tool_result: consulta explícita e
  read_current_omni_session sem argumentos. A injeção companyId é rejeitada antes
  de chegar a /query. Nenhum endpoint /tasks é acionado.
- Socket/modelo de voz, signed-session e descoberta do runtime são fixtures. Não
  houve chamada a modelo, permissão de microfone, dado privado, VPS ou MCP externo.
  Portanto essa prova não substitui aceitação do agente remoto após deploy.

Validação final: 56 testes backend passaram, incluindo consulta HTTP, continuidade,
store, guards e tarefas internas. Os testes de client e sessão passaram. As 12
verificações de regressão de playback passaram com WebSocketConnection instalado;
TypeScript --noEmit passou. O reteste final também passou após o ajuste de orçamento adicional.

## Integração/publicação com coordenador

Sem alteração automática de agente remoto. O alias opcional só será invocado pelo
modelo se estiver declarado na configuração desse agente; nome, schema e descrição
precisam de revisão específica do integrador. Não inferir autorização para configurar
MCPs ou conceder novos acessos persistentes. O caminho read_current existente já
recebe queryResult e preserva seu schema vazio.

Após merge/CI/deploy pelo integrador, validar com conta autorizada: perguntar por
um trabalho conhecido fora da amostra, consultar decisão de conversa anterior,
confirmar origem/revisão e ausência cross-tenant. Verificar que o agente chama o
client tool existente e que o payload chega ao provider. Se não chamar, o bloqueio
remanescente está na declaração/política de ferramenta remota, não no índice.
Não foi alterada essa política nesta branch.

Não iniciar conversa paga automaticamente. Não prometer MCP global/semântico,
recall exaustivo ou sessão produtiva comprovada antes dessa aceitação.

## Reproduzir

    TYPESCRIPT_MODULE=/caminho/frontend/node_modules/typescript \
    NODE_PATH=/caminho/terminal-server/node_modules \
    python -B -m pytest -q -p no:cacheprovider \
      tests/backend/test_live_query_tools.py \
      tests/backend/test_live_continuity_endpoints.py \
      tests/backend/test_managed_live_context.py \
      tests/backend/test_live_conversation_store.py \
      tests/backend/test_live_task_dispatch.py

Para testes client/session/playback, usar node_modules existente da mesma base,
sem instalar dependências. O teste HTTP requer permissão de bind local.
