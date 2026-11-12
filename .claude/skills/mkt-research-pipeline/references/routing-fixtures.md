> Adaptado pelo OmniNexus em 2026-10-15 de MarketingSkills; Copyright (c) 2025 Corey Haines, MIT. Fontes e modificações em ../ORIGIN.md.

# Fixtures de revisão — especificação, não replay executado

Usar IDs e pessoas fictícios claramente identificados em sandbox. Não são leads reais. Casos a preparar para implementação futura; critérios não comprovam o estado do CRM até executar contra sistema autorizado.

| Caso | Entrada/ocorrência simulada | Resultado esperado e evidência a observar |
|---|---|---|
| Duplicação | submission fixture-A entregue duas vezes | Mesmo ID/lead; só uma tarefa/atribuição/booking; conferir ledger e contagens |
| Timeout | fixture-B válido; enriquecimento estoura orçamento | Lead persistido antes da espera, confirmação fallback, fila pending; nenhuma rejeição por unknown |
| Resultado tardio | sucesso de B após owner já atribuído | Campos permitidos completos; owner/agenda intactos; sem nova tarefa/booking |
| Owner indisponível | fixture-C com fit verificado e owner ausente | Fila fallback com motivo e prazo definido pela equipe, sem descarte ou SLA inventado |
| Empresa desconhecida | fixture-D sem match confiável | Pending/unknown; contato preservado, sem desqualificação nem empresa inferida por e-mail pessoal |
| Cliente existente | fixture-E com identidade CRM verificada | Owner atual preservado; sem criar relação duplicada |
| Falso match/quota | fixture-F ambíguo ou fornecedor sem quota | Submissão aceita e fila de revisão; falha de terceiro não apaga lead |

No futuro, verificar tanto resposta visível quanto registros/tarefas e histórico de owner. Relatório: caso, ambiente, entrada, ID esperado/observado, resultado, evidência e PASS/FAIL/NÃO TESTADO. Neste lote todos os replays operacionais são NÃO TESTADOS; apenas descoberta e documentos são testados.
