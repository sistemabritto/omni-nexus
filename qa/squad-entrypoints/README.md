# Squad: evidência de tela local

Tela implementada, não publicada por este branch. Browser QA usa fixture42nativos+1custombloqueado, authsimulada, consumooff, requestsAPIinterceptados, nenhumPOST/PUT/PATCH/DELETE. Em DEV, fixture remapeia localhost8080 para mesmaorigem porCSP; não é alteração de produto. Desligar HMR somente no servidor de QA para não disputar os mocks de websocket.

Aceite funcional: seis portas por padrão em /agents e alias /agentes; demais recolhidos; busca alcança especialista; locked sem link; Live seis entradas autorizadas, expansão36 e preservação da seleção ao recolher. Metadados nunca adicionam slug não autorizado. Clique continua nas URLs históricas /agents/<slug>. Critérios de revisão e contrato de handoff não são alterados.

Evidência: evidence/agents-{375,1440}.png, live-{375,1440}.png e results.json, renderização real com fixture; não screenshot de produção. Sem overflow horizontal nas larguras verificadas. Avatar-directions.html + evidence/avatar-directions.png são três opções concretas: retratoexistente/símbolofunção/monograma. Nenhum retrato novo foi gerado; decisão estética e possível retratorealista permanecem pendentes. Nomes principais são função+apelidoatual; IDs, vozes e histórico intactos.

TypeScript e ESLint devem rodar nos componentes novos/alterados. AgentDetail muda somente import de trackAgentVisit, agora helper próprio; lint completo desse arquivo tem achados preexistentes (refs/effects/unused) fora do escopo. Intelligence recebe entrada para /agentes. Vite config HMR de QA não entra no commit. Graphify gerado excluído.

Integrador único publica após canário ativo, confirma base/head e verifica telas reais autenticadas depois. Esta revisão não encerra squad: faltam decisão das figuras, voz por persona escolhida/verificada e aceite visual em produção; fila e quatro fluxos de vídeo não foram iniciados por este pacote.
