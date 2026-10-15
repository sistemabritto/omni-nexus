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

## Lacunas de reuse-first e dívida deliberada

Complemento seletivo de Ponytail MIT (ORIGIN.md e LICENSE-ponytail), modificado pelo OmniNexus em 2026-10-15. Antes de nova solução, procurar implementação/padrão existente e callers reais; preferir reuso compatível, depois recurso da plataforma/stdlib e dependência já instalada. Escolher o menor diff completo e legível, sem cortar validação de fronteira, segurança, recuperação de dados ou acessibilidade. Não resumir isso a menor número de linhas nem reescrever arquitetura para reduzir contagem.

Na revisão Lens/Oath, ler também callers, testes e contexto de carga afetados. Um achado precisa de caso concreto, impacto e correção proporcional; ganhos micro ou gosto não são bloqueio automático. Nada aqui cria segunda faixa de revisão ou repete o protocolo de debugging acima.

Se uma limitação conhecida for deliberadamente adiada no escopo autorizado, registrar no mecanismo de dívida/ticket já existente: localização/versão, motivo, limite assumido, risco, dono e gatilho de retomada. Comentário `shortcut:` é opcional conforme convenção local, não obrigação de poluir código. Sem gatilho/dono, marcar lacuna; não fabricar aceite ou tickets. Levantamento é read-only até pedido de persistência no fluxo autorizado. Medição de economia exige baseline e resultado reais; benchmark autoral Ponytail não prevê economia Britto.

Não instalar plugin/hooks/comandos Ponytail nem escrever modo/configuração global; seu estado upstream não é isolado por projeto/sessão. Não injetar instruções de desenvolvedor em prompt de voz do usuário. Estes são métodos locais, sem alteração de runtime, compactação, voz ou telemetria.
