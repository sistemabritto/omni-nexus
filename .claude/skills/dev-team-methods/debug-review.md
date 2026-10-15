# Execução proporcional, debugging e revisão

Síntese modificada OmniNexus em 2026-10-15 de Superpowers e padrões de evidência Agency Agents; ver ORIGIN.md. Seguir agentes/fases já existentes, sem bootstrap global ou processo serial adicional.

## Escolher caminho

Pedido claro, limitado e já autorizado → Bolt executa com menor diff adequado e validação pertinente. Não criar cerimônia ou nova aprovação. Feature cruzada → Compass/plano existente registra objetivo, arquivos responsáveis, interfaces consumidas/produzidas, critérios e donos; um plano canônico, tarefas de entregas testáveis, sem escrever toda implementação antecipadamente. Requisitos desconhecidos relevantes são lacunas, não autorização para inventar escopo.

## Hawk/Bolt — bug

1. Reproduzir sintoma ou registrar reprodução indisponível com evidência coletada; ler erros, mudanças recentes e rastrear valores entre fronteiras. Não imprimir segredos/PII para investigar. Comparar um fluxo equivalente funcional.
2. Formular uma hipótese específica com motivo e previsão refutável. Testar a menor variação que distingue explicações; não acumular fixes especulativos.
3. Capturar regressão significativa no nível adequado; demonstrar que detecta o defeito quando viável. Sem teste automatizado aplicável, registrar reprodução/check manual e limite, sem teste que espelha implementação.
4. Corrigir causa com fix mínimo e reexecutar sintoma/regressão e verificações afetadas. Não aproveitar para refatorar partes não pedidas. Nova falha pede nova evidência; respeitar o circuito de três tentativas já existente no agente e encaminhar diagnóstico arquitetural com fatos, sem loop infinito ou controlador novo.

## Lens/Oath — revisão e conclusão

Uma faixa de revisão de código, usando Lens/fluxo existente, confere **especificação e qualidade** no mesmo artefato: pedido/critério, base/head ou versão exata, diff, contratos e testes. Priorizar falhas de comportamento, integração, segurança e manutenção com localização/evidência. Não duplicar revisores por este módulo; independência significa não autoaprovar, não um roster importado. Não iniciar subagentes automaticamente.

Oath valida conclusão independente dos critérios relevantes, com comandos/testes que realmente executou e inspeção adequada. Build/lint não prova comportamento nem estética. Review PASS não autoriza deploy/merge. “Não testado” ou evidência inconclusiva não vira reprovação subjetiva automática nem aprovação inventada. Sem renderer/navegador, inspeção visual fica pendente.

Entrega final proporcional: resultado e escopo; versão/commit; achados/revisão e correções; comandos executados, exit status e resultado; critério→evidência; limitações, riscos e próximos passos. Evidência anterior à última mudança precisa ser reavaliada se a mudança a invalida. Não repetir testes sem motivo nem citar comando que não rodou.

Não importar comandos Laravel/localhost, scripts de screenshot, regras de reprovação por gosto/notas premium, metas de performance genéricas, destruição automática de worktrees, visual companion/telemetria, bootstrap ou instaladores Superpowers. Esses métodos são instruções; não ferramentas novas ou permissão para escrever em produção.
