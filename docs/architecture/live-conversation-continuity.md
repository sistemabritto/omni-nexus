# Continuidade Live entre chamadas — implementação isolada

Branch feat/live-conversation-continuity, sobre f87ae64 (contrato de recuperação),
base PR58 5c4cd75. Sem dependências novas, rotas, UI, configuração remota ou deploy.

## Menor entrega implementada

ConversationStore é um store SQLite puro, usando arquivo DEDICADO informado pelo
integrador. Testes usam somente TemporaryDirectory. Persistência transacional de
conversas lógicas, eventos versionados, revisões, retratações e resumo estruturado
derivado. Nenhuma leitura de dados MemPalace/empresa/provedor reais.

- Principal(user_id, company_id) vem de identidade autenticada e contexto
  autorizado do servidor, nunca dos argumentos do modelo ou localStorage.
- allowed(principal, conversation_id_or_None) é callback obrigatório de ACL viva:
  verifica pessoa ativa, empresa permitida, contexto e revogação. Comparações SQL
  ainda exigem o mesmo dono usuário/empresa. Callback permissivo de fixture NÃO
  é autorização produtiva. A política PR58 atual é pessoal/admin; não inventar
  membros por empresa inexistentes.
- latest(principal) retorna ID da última conversa autorizada; None se nenhuma.
  NÃO cria conversa. Nova conversa usa create_explicit, acionada somente por
  decisão humana explícita. Se nenhuma existe, UI mostra iniciar conversa.
- record grava transcript/fact/inference/decision/pending/preference; source
  obrigatório e revisão conservada. Fonte e verified são fornecidos pelo
  adaptador servidor, não pelo modelo. Sugestões de modelo são unverified.
- snapshot retorna histórico paginado por limite (50 padrão/100 máximo), resumo
  estruturado atualizado, revisão do resumo e current_context, que contém só a
  revisão vigente dos eventos não retratados. history contém revisões antigas
  para auditoria humana e NÃO pode ser enviado ao provedor como contexto atual.
- Correção: record com event_id e expected_revision. Conflito impede sobrescrita
  concorrente. Retratação cria revisão/tombstone; atualiza resumo na mesma
  transação. Retratação é lógica, não apagamento físico ou política LGPD.

Resumo determinístico, sem chamada LLM: fatos, inferências, decisões, pendências e
preferências. Cada item mantém origem, event_id, revisão e verified. Todo registro
não verificado entra em inferências, mesmo que sugerido como preferência/fato.
Preferência confirmada pode ser corrigida/retratada. Não há treinamento de pesos,
autoedição de políticas nem promoção automática de afirmações do modelo.
O resumo estrutura declarações de origem; não verifica verdade externa.

## Interface proposta ao executor UI/integrador

Futuros endpoints, a implementar com os guards PR58, ACL atual e no-store:

    GET  /api/live/conversations/latest  # empresa obtida do contexto autorizado
    POST /api/live/conversations         # ação humana explícita
    GET  /api/live/conversations/<id>     # snapshot autorizado
    POST /api/live/conversations/<id>/events
    POST /api/live/conversations/<id>/corrections

É proposta, não API disponível. IDs de usuário/empresa não são parâmetros de tool.
Payload de criação deve derivar company do contexto já aprovado; troca de empresa
resolve outro principal antes de retornar latest, nunca reusa estado da anterior.
O backend precisa validar payloads estritos, tamanho, origem/CSRF, autoria e ACL
antes de chamar store. Correções/verified exigem ação humana ou ferramenta de
leitura com evidência confiável; transcripts do assistente não viram fatos.

Conversation_id lógico persistente difere do conversationId ElevenLabs e do
runtime_session_id. PR58 liga um conversationId de provedor por contexto e não
aceita religar outro. NÃO remover essa proteção. Nova conexão de provedor pode
criar um novo vínculo de contexto/runtime autorizado associado à mesma conversa
lógica após validar ownership. Design do vínculo N conexões → 1 conversa lógica
fica sob coordenação do integrador, sem adotar sessão legada sem dono.

Reload/reconnect/desligar/ligar/troca de voz consultam latest/snapshot e reutilizam
a conversa lógica. Alteração de voz não seleciona empresa nem cria conversa.
Ao desconectar, a UI não apaga histórico nem solicita create_explicit. Uma
pendência de append precisa ser confirmada ou reenviada com deduplicação; não
prometer persistência para áudio/transcrição ainda não recebido no servidor.

## Dependências ainda necessárias para comportamento real

1. Rotas autenticadas, vínculo lógico ↔ context/runtime/provider e ACL real.
2. Adaptador de eventos ElevenLabs: salvar texto final de usuário/assistente e
   eventos de decisão/pendência com origem confiável. Definir final vs parcial,
   ordering e chave de idempotência para evitar duplicação em reconexão. O store
   atual não deduplica reenvio de novos eventos: essa capacidade é um requisito
   ANTES de habilitar captura automática/retry, não um recurso já entregue.
3. UI para retomar latest, iniciar nova explicitamente, corrigir e confirmar
   preferência; tratamento de gravação pendente/erro. Não tratar SDK onDisconnect
   como exclusão de conversa. Testes reais do SDK ainda não executados.
4. Reidratar resumo/current_context no provedor via mecanismo suportado e validado
   no SDK/provider selecionado. Necessário definir orçamento de contexto, seleção
   dos itens relevantes e instrução de tratar conteúdo como referência. snapshot
   pode ter resumo grande; não enviar diretamente sem orçamento/tokenização.
5. Ao corrigir/retratar algo já enviado, atualizar/encerrar conversa remota conforme
   capacidade real do provedor. Não é possível retirar texto já transmitido.
   Revogação deve fechar conexão e impedir cache/reenvio. ACL de callback precisa
   ser transacional/versionada para reduzir corridas com revogação concorrente.
6. Antes de produção: índice de consulta por dono, paginação por cursor, política de
   retenção/eliminação física, backup/restauração, permissões do arquivo e limites
   de crescimento. user_version=1 só para DB dedicado; não migra base existente.

Memória semântica continua separada: contrato f87ae64 exige ownership verificado e
pré-filtro obrigatório. Este store não atribui os 1026 embeddings legados a tenant,
não chama MemPalace e não cria serviço/base vetorial alternativa. Preferências
nesta menor entrega são da conversa; compartilhamento entre conversas futuras
precisa de escopo explícito e confirmação, não inferência automática.

## Testes offline reproduzíveis

    python3 -B -m unittest discover -s tests/backend -p test_live_conversation_store.py -v
    python3 -B -m unittest discover -s tests/backend -p test_live_memory_contract.py -v

9 testes de continuidade + 10 de recuperação. Cobrem SQLite reaberto, reload,
reconnect/troca de voz simulados, contexto→resposta mock, A/B e A1/A2, usuário
adverso, revogação, rollback durante write, resumo/correção/retratação e conflito
concorrente de revisão. Não provam endpoint/SDK/provedor real nem transcrição
persistida automaticamente. Nenhuma chamada paga e nenhum dado real.

## Integração e estimativa

Menor próxima entrega utilizável: endpoints + vínculo lógico e UI latest/new,
transcrições finais com idempotência, confirmação de gravação e reidratação com
orçamento. Estimativa 2–4 dias técnicos após alinhamento das interfaces; testes
SDK/voz com provider e política de retenção podem ampliar. Não deve bloquear o
primeiro teste de voz sem memória. Ativação por flag separada, desligada por padrão;
rollback desliga a ponte sem remover o DB nem reativar eventos retratados.
