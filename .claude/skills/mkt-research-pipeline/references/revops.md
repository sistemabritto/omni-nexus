> Adaptado pelo OmniNexus em 2026-10-15 de MarketingSkills; Copyright (c) 2025 Corey Haines, MIT. Fontes e modificações em ../ORIGIN.md.

# Nex — especificação de handoff/inbound-routing

Definir lifecycle, critérios de entrada/saída, fonte CRM, responsável, regra vigente e fallback antes de automatizar. Preservar lead válido antes de depender de enriquecimento; atribuição e valores enviados não se perdem em falha. ID estável da submissão e identidade CRM conciliada sustentam idempotência: replay não cria segundo contato, tarefa, alerta ou booking.

| Evidência | Próximo passo proposto |
|---|---|
| Cliente/conta existente verificados | Preservar owner e relação; encaminhamento conforme regra vigente |
| Fit verificado e owner disponível | Uma atribuição/tarefa, origem e motivo |
| Fit verificado, owner indisponível | Confirmação honesta e fila fallback; prazo só conforme cobertura/regra acordada |
| Unknown/ambíguo/timeout/quota | Aceitar e preservar submissão; fila pendente ou esclarecimento mínimo |
| Desqualificador explícito confiável | Registrar motivo real e alternativa conforme política; unknown não desqualifica |

Domínio pessoal não prova empresa. Não inferir atributos sensíveis. Reusar dados confiáveis e cache exato recente sem presumir acesso a fornecedor. Orçamento de espera vem de latência observada e UX atual, sem SLA universal. Resultado tardio pode completar campos aceitos e alertar owner atual, mas não reatribuir silenciosamente, trocar agenda exibida ou duplicar tarefa. Mudança de owner exige regra explícita e registro.

Validar com [fixtures](routing-fixtures.md); futuro shadow/piloto deve ser limitado e autorizado. Neste lote, são especificações, não CRM implementado. Nenhum write/enriquecimento/roteamento real ou automação externa é executado.
