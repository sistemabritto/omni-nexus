# Squad ligado ao executor restrito — EDIT07 somente

Base1cb0a06 (squad/voz ativo), integração PR92c30455eb. Apenas backend/testes/docs; runner/provider_fallback, UI, worker, ENV, ACL e demais tickets permanecem iguais.

## Contrato efetivamente consumido

`run_draft` chama `restricted_squad_contract.preflight_contract` antes da inferência. Contrato `restricted-editorial-squad-v1`, frente editorial, slugs exatos: responsável `pixel-social-media`, apoio `mako-marketing`, revisor `oath-verifier`. Deriva de FRONTS já publicado; drift/colisão de papéis ou persona/método local indisponível impede chamada de modelo. Documento vazio, inválido ou externo não conta como método. Hashes dos arquivos locais ficam no evento `internal_draft_contract_validated`, não seu conteúdo.

Capacidade delimitada: `internal_hypothetical_text`, política obrigatória `no_tools`. Não comprova disponibilidade/custo de provider antes da chamada: metadata diz `providerAvailability=not_probed`. Cada fallback continua passando pelo isolamento existente; adapter incompatível falha fechado, sem fallback nativo/outer retry. Nenhuma persona completa, inbox, descrição livre, ferramenta ou credencial adicional é enviada ao modelo. Os métodos são verificados como disponibilidade local, não alegação de aplicação semântica pelo modelo.

Antes de gravar o arquivo, controlador revalida o mesmo contrato/hashes sob a transação de conclusão. Alteração de método ou papéis durante a inferência impede persistência/entrega e mantém apenas o piloto bloqueado, respeitando CAS e edição humana concorrente.

Resultado válido: arquivo controlado O_NOFOLLOW/O_EXCL, SHA, `internal_draft_ready` com `delivery_handoff` vinculado a runID/artefato/hash e Oath. Ticket segue para review mantendo Pixel; não resolved. `reviewStatus=pending_independent_review`, aceite semântico não verificado, acknowledgement não registrado, ownershipChanged/dispatchAllowed/publicationApproved=false. Oath/Mako não são disparados automaticamente; presença de persona/método não é execução de revisão. O hash controlado do artefato não prova conteúdo correto.

## PR92 preservada

Promptv2 exige primeira linha plana literal RASCUNHO — EXEMPLO HIPOTÉTICO. Mesma aceitação `str.lstrip().startswith(HYPOTHESIS_LABEL)`, sem normalizar heading/fence/aspas/JSON/BOM/preâmbulo. Diagnóstico do rejeitado só enums/bytes/linhas/flags/etapa; nenhum corpo/trecho/hash/raciocínio/erro externo retido. Uso numérico válido preservado; NULL não vira zero. Não há como recuperar causa exata do texto anterior não retido.

## Testes e aplicação

201 testes offline passaram (heartbeats, isolamentoCLI, provider cwd, contrato squad), incluindo guard antes de modelo, revisão independente pendente e revogação de método durante a inferência. Fonte antiga de teste mencionada por engano não existia, nenhuma execução ocorreu nessa seleção; seleção corrigida e suíte acima integralmente verde. Sem modelo/geração real. CI já seleciona todo tests/heartbeats, incluindo novo teste.

Único dono do próximo retry: tarefa responsável da fila `01a13f7c-2a2b-715e-8cd0-3ae08045b0d2`. Integrador não desbloqueia nem dispara. Handoff somente depois de CI, imagem final/fixture offline, rollout dashboard, verificação dos hashes e preflight readonly na versão ativa. Dono da fila revalida ociosidade de atores/runs/locks/estado anterior e usa CAS para uma tentativa somente de EDIT07. Nenhum outro ticket/campanha/retry liberado por implicação.

Aceite de conteúdo precisa período/população/denominadores, definições de resolução/retrabalho/custo e cálculos conferíveis; exemplo inteiramente hipotético e nenhuma inferência de vencedor a partir de3PV. Sucesso do heartbeat não basta. Revisão independente e aceite humano continuam pendentes até evidência real; nenhuma publicação externa é autorizada.

Backup/rollback: somente dashboard, voltar a1cb0a06 preservando worker2eed8fd e dados/ENV. Não restaurar DB antigo nem reabrir piloto automaticamente em rollback. Nova tentativa só com estado atual e autorização já delimitada, sem afrouxar isolamento.
