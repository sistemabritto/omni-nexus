<!-- Modified by Sistema Britto, 2026-10-15. -->
# OmniNexus Live: contrato de implementação v0.1

Status: proposta normativa, não API já publicada. Prioridade P0: fechar **Live → tools → providers/modelos → harness/dispatcher → resultado**, com contexto autorizado, antes de expandir o catálogo. Estado real em [evidências](omninexus-live-evidence.md).

## Posicionamento e independência nas três camadas

**OmniNexus Live** permanece o nome do produto. “Agnostic Live Voice Business Manager” é um posicionamento em discussão; não autoriza renomear produto, repositório ou domínio. Não implica desempenho “superinteligente” comprovado.

| Camada | Independência exigida | Condição para troca |
|---|---|---|
| Harness agnostic | Núcleo desacoplado do executor por adaptador canônico | Contrato e versão certificados; operações/capacidades exigidas verificadas |
| Provider agnostic | Transporte, autenticação e particularidades do serviço ficam em adaptadores de provider | Endpoint oficial, credencial autorizada, política, health e limites compatíveis |
| Model agnostic | Intenção e requisitos não dependem de um ID fixo de modelo | Modalidades, tools/schema, contexto, custo e compatibilidade verificados para o modelo exato |

Independência permite substituir componentes **entre combinações elegíveis**; não garante que todo harness aceite todo provider ou modelo. O registro deve validar a combinação completa `(harness/version, adapter/version, provider, model/version)` e seus requisitos. Certificar pares isolados não certifica automaticamente o conjunto. Aceite: uma substituição compatível preserva intenção, ACL e contrato de resultado; uma combinação incompatível é rejeitada antes da chamada, com motivo verificável.

## 1. Fronteiras e adaptadores

O núcleo não importa SDK nem interpreta stdout específico de harness. Adaptadores traduzem contratos canônicos para interfaces oficiais, com processos/ambientes isolados. Provider de voz, provider de inferência e harness executor têm identidades independentes; a existência de um modelo num gateway não prova compatibilidade com um executor.

| Alvo | Compromisso |
|---|---|
| Claude Code / OpenClaude | Partir do bridge existente; certificar o contrato por revisão exata, sem pressupor equivalência entre os dois |
| OpenCode | Adaptador extensível planejado; comprovar interface e testes antes de habilitar |
| Codex | **EM BREVE**, não habilitado/funcional comprovado no OmniNexus |
| Hermes | **EM BREVE**, não habilitado/funcional comprovado no OmniNexus |
| Cursor | Candidato, sujeito a interface oficial e avaliação |

Instalado no PC, binário presente na imagem, adaptador integrado, teste simulado e uso em produção são cinco evidências distintas. Nenhuma implica a seguinte.

## 2. Contrato canônico do adaptador

Operações internas propostas; não anunciar estas operações como endpoints HTTP existentes.

| Operação | Entrada e saída obrigatórias |
|---|---|
| `capabilities` / `version` | `contractVersion`, adapter/harness/version exatos, origem oficial, matriz compatível, evidência e validade |
| `health` | readiness separado de liveness; configuração, capacidade disponível, carga e erro sanitizado; nunca chave |
| `start` | contexto autorizado, intenção tipada, requisitos, seleção congelada, deadline, reserva de orçamento e chave idempotente; retorna `jobId` antes de trabalho longo |
| `status` | estado persistido, estágio, revisão selecionada, uso estimado/real e checkpoint |
| `stream` | eventos ordenados com cursor e sequência monotônica; replay após cursor sem duplicar efeitos |
| `cancel` | pedido idempotente, interrompe processo/provider quando suportado; confirma estado terminal e informa efeitos já realizados |
| `resume` | checkpoint + autorização atual; rejeita versão incompatível; sem suporte retorna `unsupported`, nunca reinicia em silêncio |
| `artifacts` | IDs, tipo MIME, hash, tamanho, origem, ACL, expiração e link autenticado/revogável; sem caminhos arbitrários |

Envelope de comando mínimo (exemplo de contrato, sem credenciais):

```json
{
  "contractVersion": "0.1",
  "conversationId": "conv_demo",
  "requestId": "req_demo",
  "idempotencyKey": "intent_demo",
  "requirements": {"text": true, "tools": true},
  "budget": {"currency": "USD", "maxCost": 0.10},
  "contextSnapshotId": "ctx_demo",
  "selectionId": "sel_demo"
}
```

Tenant/user/company são resolvidos e autorizados no servidor, nunca confiados a esse JSON. IDs canônicos: `tenantId`, `companyId`, `userId`, `conversationId` (continuidade), `voiceSessionId` (transporte), `runtimeSessionId` (executor), `requestId`, `jobId`, `attemptId`, `checkpointId`, `artifactId`, `eventId`. Mapear IDs externos privadamente; criar runtime não equivale a iniciar job.

Estados: `queued → starting → running → succeeded|failed|cancelled`; `running → checkpointed → queued` somente após retomada autorizada. Pedido de cancelamento é intenção até confirmação. Eventos `accepted`, `state_changed`, `text_delta`, `progress`, `checkpoint`, `artifact`, `usage`, `error`, `completed` carregam versão, IDs, sequência e timestamp. Entrega de eventos pode repetir; consumidores deduplicam por `eventId`. Falha de stream não comprova falha do job: consultar status antes de retry.

Erros tipados: `unauthorized`, `unsupported`, `incompatible_version`, `no_eligible_target`, `budget_exceeded`, `rate_limited`, `deadline_exceeded`, `provider_unavailable`, `checkpoint_incompatible`, `idempotency_conflict`. Expor causa sanitizada e possibilidade de retry, sem prompts privados/segredos.

## 3. Pools, capacidades e seleção

Registro versionado separado para harnesses, providers e modelos. Cada combinação precisa de aresta de compatibilidade testada. Templates de agente expressam preferências de estilo/modelo/provider e requisitos mínimos; não concedem ACL, não habilitam integração e não substituem política.

Cada capacidade registra `declared`, `verified`, evidência (`testId`, revisão, data, ambiente), restrições e expiração. Cobrir texto, visão, áudio entrada/saída, realtime, imagem, vídeo, tools, structured output (schema suportado), contexto entrada/saída, limites de arquivo/duração/tokens, concorrência, rate limit e custos por unidade/moeda/data. `unknown` é diferente de falso e nunca satisfaz requisito obrigatório. Nome de modelo não é prova de modalidade; áudio batch não implica realtime. Limite/custo declarado por provider não é medição local.

Algoritmo obrigatório:

1. Resolver principal, empresa, autorização de ferramenta e snapshot de contexto permitido.
2. Filtrar por integração habilitada, versão compatível, capacidades verificadas válidas, health, região/política e disponibilidade de credencial server-side.
3. Excluir alvos acima de contexto/limites, cota, carga, deadline ou orçamento; reservar custo e slot atomicamente por tenant e globalmente.
4. Ordenar elegíveis por política versionada (adequação, custo, carga; ID estável desempata). Sem elegíveis, falhar sem provider call.
5. IA pode julgar qualidade **somente entre IDs elegíveis**. Validar resposta; timeout/ID inválido usa ordenação determinística. Registrar motivo, candidatos e versão de política sem conteúdo sensível.
6. Revalidar autorização/reserva antes de iniciar. Persistir seleção e custos estimados; reconciliar uso real ao encerrar, incluindo tentativas falhas.

Fallback só para outro elegível com orçamento restante e mesma intenção/contexto autorizado. Após efeito externo, não repetir sem reconciliação/checkpoint; operações irreversíveis exigem confirmação conforme política da ferramenta. Dedupe por `(tenant, conversation, idempotencyKey)` e hash da intenção: mesma chave/payload retorna job existente; payload diferente retorna conflito. Não prometer exactly-once para APIs externas sem suporte. Slot usa lease com expiração e recovery; concorrência não pode ultrapassar teto por corrida entre workers.

## 4. Live, contexto e segurança

Voz e texto compartilham `conversationId` e log persistido; reconectar voz cria transporte, preservando continuidade autorizada. Interromper áudio não cancela job implicitamente. Status e links aparecem por escrito no chat mesmo que a voz desconecte; cancelar trabalho é ação explícita.

Contexto montado no servidor: persona versionada, fatos da empresa com fonte/data/revisão, memória consentida e trabalhos anteriores com ACL. Guardar proveniência, retenção e exclusão/retração. Recuperação não pode importar outra empresa nem inventar fatos ausentes; informar ausência/conflito ao usuário. Prompt de documento recuperado é dado, nunca autorização de ferramenta. RAG é um mecanismo possível, não recurso entregue pela existência de sessão runtime.

Reautorizar leitura, start, status, replay, cancel, resume e download. Negar acesso cruzado mesmo com ID válido. Chaves ficam no servidor, escopadas por tenant/provider; tokens efêmeros para browser somente quando o protocolo exigir, com validade/escopo mínimos e sem chave principal. Redigir logs e erros; limitar e auditar egress. Separar armazenamento, ambiente/processo, filesystem e orçamento por tenant. Revogação impede novas ações e leitura posterior; trabalhos em andamento seguem política explícita de encerramento.

### Aprovação por voz e encaminhamento ao Telegram (proposta)

O pedido “YOLO” foi esclarecido como **aprovar por voz**, preservando permissões, ACL, orçamento e gates da ferramenta. Não representa consentimento geral para ações futuras. Antes de pedir confirmação, o Live apresenta a ação concreta, alvo, parâmetros relevantes, efeito e custo/limite aplicável; uma fala ambígua não autoriza execução.

O servidor emite uma solicitação versionada com `approvalId`, hash da ação exata e seus parâmetros, `userId`, `tenantId`, `companyId`, revisão da proposta/política e `expiresAt`. A confirmação deve corresponder a essa solicitação e ao usuário autenticado com permissão para aprová-la; transcrição isolada ou conteúdo recuperado não prova identidade nem consentimento. Mudança de ação, parâmetros, empresa ou versão invalida a aprovação anterior. Expiração, revogação ou perda de permissão bloqueiam o consumo. Revalidar todos esses vínculos imediatamente antes de executar.

Persistir solicitação, decisão (`approved|denied|expired|revoked`), canal, autor, horário, versão e feedback sanitizado. Consumo atômico e idempotente vincula a aprovação a um único job/efeito: repetir a confirmação retorna o resultado já registrado. Decisões concorrentes entre voz e Telegram usam a mesma revisão, com primeira decisão válida persistida prevalecendo; decisão posterior recebe estado atual e não reabre a ação.

Para ações críticas/urgentes, prever encaminhamento pelos mecanismos existentes de Telegram **Approve/Deny + feedback**, com decisão e estado devolvidos à mesma conversa Live por `approvalId`. Esse retorno integrado é proposta, não capacidade comprovada. Só enviar ao destinatário vinculado e autorizado, conforme configuração explícita; respeitar mute, dedupe, expiração e política de notificações existente. Não reativar heartbeats nem spam, não considerar entrega da mensagem como aprovação e não executar por timeout. Negação/feedback retornam ao Live; revisão da ação exige novo consentimento.

Aceite: voz aprova somente a ação apresentada; mudança de empresa/parâmetro, replay, expiração e usuário sem ACL não executam; confirmações simultâneas voz/Telegram produzem uma decisão e um job; Deny+feedback chega ao Live; canal silenciado permanece silenciado.

### Operador, cliente e escopos de memória (proposta de produto)

Esta separação descreve o modelo desejado, **não acesso implantado ou permissões já concedidas**. O operador configura integrações, catálogo, versões, políticas e recursos de agentes/skills dentro do escopo autorizado. O cliente consulta seus trabalhos/dados e aprova ações para as quais tenha permissão; consultar ou aprovar não concede acesso a chaves, configuração de provider ou administração do tenant. O papel de operador também não implica acesso irrestrito aos dados de todos os clientes.

Skills e definições de agentes podem ser reutilizadas como recursos versionados, separadas dos dados/contextos de execução. Credenciais, artefatos, histórico, índices e fatos permanecem isolados por tenant e empresa; reutilizar uma definição não copia memória ou segredo de outro cliente. Validar dependências e política antes de disponibilizar um recurso reutilizável a um tenant.

Memória privada é escopada por `(tenantId, companyId, userId)`; memória compartilhada da empresa por `(tenantId, companyId)` e ACL explícita. A recuperação respeita esses escopos e registra proveniência. Compartilhar um fato privado exige ação autorizada e explícita, sem promoção automática por resumo, treinamento, índice ou reutilização de skill. Retração, revisão e retenção aplicam-se a cada escopo.

Aceite: cliente consulta/aprova somente o que sua ACL permite e não altera configuração restrita; operador configura somente seu escopo; dois usuários da mesma empresa compartilham apenas fatos explicitamente compartilhados; outra empresa/tenant não recupera dados privados ou compartilhados, mesmo usando a mesma skill/agente.

## 5. Lifecycle oficial e atualização

Registrar pacote/repositório oficial verificado, versão fixa, digest, licença e protocolo suportado. Não instalar `latest` em runtime; proibir auto-update durante sessão/job. Atualização: detectar versão candidata → preparar isoladamente → rodar contrato/regressão → drenar worker ocioso (sem lease/job/retomada ativa) → ativar canário → promover ou rollback. Não substituir binário usado por processo ativo.

Manter versão anterior e manifesto/configuração compatível; checkpoints anotam versão. Rollback preserva transações novas, não restaura banco antigo sobre trabalho recente; se checkpoint incompatível, manter worker anterior ou informar bloqueio. Licenças são verificadas por dependência, sem herdar suposições do orquestrador.

## 6. Entregas e critérios de aceite

| Prioridade / responsável funcional | Aceite verificável |
|---|---|
| P0 contexto/backend + UI | Voz e texto alternam na mesma conversa; persona/fato/trabalho conhecido têm fonte; ausência é declarada; troca de empresa não vaza memória |
| P0 tools/dispatcher | Pedido autorizado inicia exatamente um job observável no executor existente; status/erro/artefato retornam no chat; criar sessão sozinho não passa |
| P0 providers/policy | Requisitos incompatíveis e orçamento insuficiente não fazem chamada; IA nunca escolhe ID inelegível; corrida de reservas respeita limites |
| P0 continuidade | Reconnect/retry não duplica efeito; crash após checkpoint retoma ou informa incompatibilidade; cancelamento libera recurso e contabiliza uso |
| P0 isolamento | Usuário/empresa diferente não lê status, stream, memória ou artefato; revogação durante execução é exercitada |
| P1 adapter | Cada novo harness passa o mesmo conjunto de contrato/version/health/start/stream/cancel/resume/artifacts antes de habilitação |
| P1 lifecycle | Atualização espera ociosidade; falha em canário restaura versão anterior sem perder dados ou matar sessão ativa |

### Prova ponta a ponta real (gate de conclusão P0)

Executar somente no ambiente e com provider/custos explicitamente autorizados para esse teste. A autorização para documentação não autoriza chamada real nem deploy. Escolher um único executor já integrado; não esperar o catálogo amplo.

1. Preparar tenant/empresa de teste e um fato conhecido, persona versionada e trabalho anterior com fonte; outra empresa contém um marcador proibido.
2. Entrar no Live real, falar o pedido de retomar trabalho, continuar por texto e conferir o mesmo `conversationId`.
3. Capturar cadeia de IDs da tool → seleção provider/modelo → dispatcher → processo real, com versão e uso, sem segredos ou contexto privado no relatório.
4. Conferir conteúdo contra as fontes preparadas; marcador da outra empresa não pode aparecer. Solicitar dado ausente deve produzir ausência explícita.
5. Acompanhar status e abrir artefato autorizado no chat. Repetir request/reconectar sem segundo efeito; testar cancelamento e falha controlada com recuperação.
6. Registrar commit/digest, ambiente, horário, autorização, IDs sanitizados, provider/modelo/harness, custo e resultado por passo. Separar testes simulados dos reais. Somente marcar produção após promoção autorizada e smoke específico.

## 7. Referência opcional

Orca pode inspirar execução, mas não é dependência instalada nem solução de RAG ou isolamento tenant. Qualquer adoção exige revisar código, licença e maturidade naquela revisão; não há requisito de adoção para fechar P0.
