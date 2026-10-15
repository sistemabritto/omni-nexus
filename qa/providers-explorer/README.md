# Providers: fatia local independente

Base: `050a8b506b255fa69d61ae324d25be5b174839f4`.
Branch: `codex/providers-capability-preview`. Não publicada.

Escopo: `ProviderExecutionExplorer.tsx`, seu CSS e cliente tipado. A página
`Providers.tsx` recebeu somente um import e a montagem acompanhada do rótulo de
configuração legada. Não foram alterados menu, Live, voz, providers reais,
templates, backend ou deploy. Nenhum commit do PR86 foi integrado.

O cliente usa o contrato ainda em rascunho da outra frente:
GET `/api/execution/catalog` e POST `/api/execution/decisions/preview`.
Sem esses endpoints na versão-base, a UI informa “ainda não integrado”. Não
inventa catálogo de produção, não faz discovery, não inicia harness ou provider.
Metadados indicam configuração/declaracão, não atestado da instalação atual.
Hermes e Codex permanecem “Em breve”, independentemente de ferramentas no PC.

Prévia exige revisão correspondente, `selected:null`, `execution_allowed:false`,
`provider_calls:0`, tentativas vazias e candidatos inelegíveis do pool retornado.
Filtros/refresh invalidam resultados em voo; HTTP409 exige atualização do catálogo.
Somente o servidor pode evoluir esse contrato; integração central ainda pendente.

Validação executada:

    node qa/providers-explorer/client-tests.cjs
    node qa/providers-explorer/render-tests.cjs

Checagem TypeScript focada nos dois arquivos novos também passou, sem bundle/build
completo. O teste React usa o renderizador real do servidor: não cobre DOM,
interação de navegador, CSS ou responsividade.

`ui-qa.cjs` prepara casos desktop/mobile com APIs sintéticas, mas NÃO foi validado
neste ambiente. A porta local e o Chrome foram negados pelo sandbox (`EPERM`).
Não se ampliaram permissões. O script usa CSP bypass só na fixture porque o
cliente HTTP dev legado aponta para localhost:8080; todas as APIs são simuladas.

Para QA visual posterior, em ambiente já autorizado com preview na porta5197:

    NODE_PATH=/caminho/dependencias QA_BROWSER_EXECUTABLE=/caminho/chrome \
      node qa/providers-explorer/ui-qa.cjs

Graphify foi solicitado em prioridade baixa e sem clustering, sem uso de LLM ou
harness. Os artefatos gerados do grafo não fazem parte do patch da interface.
As dependências existentes foram reutilizadas por symlink local, sem instalação.
