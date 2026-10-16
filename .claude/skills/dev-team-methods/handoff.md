# Responsabilidades e handoff aceito

Síntese modificada OmniNexus, 2026-10-15, atribuída em ORIGIN.md. Usa competências seletivas, sem importar personas/roster/controlador Agency Agents.

Clawdia mantém a fila operacional visível e seus itens com dono, estado verdadeiro e próxima ação; Helm continua coordenando engenharia conforme fluxo existente. Propor um handoff não transfere responsabilidade: o dono atual permanece até aceite explícito do destinatário e registro no mecanismo já usado pela equipe. Se não houver ferramenta/aceite, registrar “proposto, não aceito” e continuar como dono; não inventar ack ou runtime de fila.

Contrato de handoff: ID da tarefa/ticket, versão/commit/artefato exato, dono atual, destinatário proposto, objetivo/limites, inputs com origem, output esperado, critérios de aceite, evidências disponíveis e pendentes, dependências, próxima ação e condição de aceite. Registrar quando/quem aceitou apenas se ocorreu; nunca transferir silenciosamente ao emitir mensagem. Mudança de escopo/versão após aceite precisa de alinhamento sobre o delta, não invalida tudo sem motivo.

Por papel:

- Bolt: explicitar contratos input/output, schema/erro relevante, IDs de correlação e comportamento sob timeout/retry/duplicação. Para efeito repetível, definir chave idempotente, estado e recuperação; não declarar idempotência porque há um campo chamado id. Adotar padrões do repositório sem arquitetura extra.
- Mako: ligar hipótese de crescimento ao público/oferta, prova, baseline real ou ausente, métrica/janela e critério de refutação; sem promessa de uplift universal.
- Pixel: origem e direitos dos materiais, adaptação por canal, roteiro/storyboard/repurpose e CTA confirmados. Plano não é render, publicação ou agendamento concluído.
- Nex: estágio CRM só com critério/evidência, dono e próxima ação; lacuna de dado não é desqualificação automática. Leitura não autoriza mudança real no CRM ou contato com lead.
- Dex: taxonomia consistente, IDs/dedup e reconciliação com fonte da verdade; janela/denominador explícitos, dados ausentes não viram zero, nenhum dado pessoal desnecessário em logs/analytics.
- Oath: verificação independente com evidência própria e limites; Lens: revisão de código. Não aprovar o próprio trabalho como se fosse segundo revisor.

Cenários de aceite a verificar no processo real: destinatário indisponível mantém dono atual; recusa registra motivo/pendência; versão antiga exige identificar delta; entrega duplicada referencia mesmo ID sem duplicar tarefa; timeout de comunicação é aceite desconhecido, não confirmado. São critérios textuais de processo, não implementação de scheduler ou testes operacionais executados.

## Contrato executável local do squad

`dashboard/backend/squad_delivery_contract.py` define papéis por entrega com slugs existentes, criticidade P0/P1/P2 e critérios mínimos. `/api/agents` expõe `catalog.delivery_roles` e `display_label` aditivos; não são grants nem assignees de tickets. A validação pessoal autorizada `POST /api/agents/delivery-contract/validate` apenas confere o candidato, ACL dos participantes e documentos locais. Não solicitar novo acesso para chamar essa rota: se indisponível, registrar bloqueio.

O pacote deve identificar empresa, frente, tarefa, dono atual, versão, objetivo/limites, inputs com origem, output, critérios de aceite, evidências ligadas à mesma versão, dependências, próxima ação, participantes reais da autoria, criticidade e estado das ferramentas com referência de diagnóstico. Revisor que contribuiu ou é dono autoral não passa como independente. Os valores de ferramentas/evidência são declarados, não prova de observação. `candidate_complete` significa formato completo; `dispatchAllowed=false`, aceite não registrado e dono preservado continuam valendo. Nenhuma liberação de fila, publicação ou aprovação é concedida por essa validação.
