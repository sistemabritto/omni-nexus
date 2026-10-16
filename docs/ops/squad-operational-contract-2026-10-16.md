# Marco executável: validar squad antes da fila

Base7521b91; mesmo branch da correção de voz. Sem dispatch, fila, grants ou custos.

- `squad_delivery_contract.py`: seis frentes configuráveis, sem meta de contagem; responsável/apoio/revisor com slugs reais e métodos locais.
- `/api/agents`: campos aditivos `catalog.delivery_roles` e `display_label` (função · apelido); display_name e IDs existentes preservados. Nenhuma alteração global de nomes/avatars.
- `POST /api/agents/delivery-contract/validate`: acesso pessoal existente+origem+empresa/personas ACL. Recebe companyId/front/taskId/currentOwner/version/objective/limits/inputs/output/acceptance/evidence/dependencies/nextAction/contributors/criticality/tools. Fixture executável: função candidate em tests/backend/test_squad_delivery_contract.py.
- Rejeita autorrevisão/versão antiga/critério ausente; dependência/ferramenta não disponível/método ausente retorna blocked. Candidato completo não muda dono nem vira aprovação/execução; evidência declarada permanece não verificada. O executor da fila ainda não consome essa validação: não afirmar enforcement global ou habilitar retry.

Próximo marco do integrador único: integrar voz b0bfb19 e contrato, rodar suites respectivas, conferir /agents e validação com fixture autorizada sem invocar workers, então publicar a base pelo fluxo único. Confirmar comportamento real em UI: seleção por persona, rótulos/roles presentes e ACL preservada. Só depois considerar conectar o contrato ao dispatch sob escopo explícito e liberar qualquer fila. Esta entrega não reatribui nem desbloqueia tickets.

Voicefix conserva preferências legadas e acrescenta escopo por persona; testes/limites em live-persona-voice-2026-10-16.md. Handoff usa guia local dev-team-methods/handoff.md, sem instalar plugins completos ou contratar ferramentas.
