# Reforma global OmniNexus Live — cobertura e limites

## Problema verificado

UI34 modificou a central, mas manteve shell/menu anteriores. As capturas daquela entrega mostram o contraste entre nova central preto/lima e menu verde anterior. Inspeção pelo navegador disponível em `https://nexus.sistemabritto.com.br` chegou à tela real de login; não havia sessão autenticada do usuário conectada e captura desse navegador não estava disponível. Não há evidência para atribuir o problema a cache.

## Inventário e implementação

`routes.json` inventaria 59 padrões existentes em App.tsx, incluindo rotas parametrizadas, conhecimento aninhado, compartilhamentos, docs, onboarding e redirecionamentos. Autorização em App/backend é preservada. Navegação agrupada e expansível: Workspace, Trabalho, Operação, Memória/conhecimento, Conexões/ferramentas, Administração. Todas as entradas respeitam permissões existentes (inclusive manage em papéis/compartilhamentos). Rotas legadas permanecem disponíveis.

`WorkspaceHeader` aplica um frame recorrente por área e indica o contexto de empresa selecionado, sem afirmar isolamento multitenant. Drawer mobile tem botão nomeado, estado expandido, inert quando fechado, Escape, contenção/restauração de foco e bloqueio do scroll atrás. Empresas, gerenciar empresas, criar empresa, usuário, configurações, logout e plugins injetados continuam acessíveis.

`token-migration.json` registra 3.863 ocorrências em classes utilitárias de 96 arquivos migradas para tokens semânticos. A transformação é restrita ao padrão utility-[#HEX], preservando valores de dados/gráficos/agentes e lógica de negócio. Tokens globais derivam da home Sistema Britto: preto/lima, DM Sans/Space Grotesk declaradas com fallback de sistema. Títulos, superfícies, bordas, foco, formulários, tabs e tabelas passam a usar a mesma base. Tabelas conservam rolagem interna quando necessário. Login adota o nome aprovado e reduz movimento quando solicitado. Logos/copyright/avisos EvoNexus mantidos.

## Cobertura visual

`route-results.json`: resultado por rota e largura. `screenshots/`: capturas reais do app renderizado localmente, não mockups desenhados. `gallery.html`: galeria de inspeção. Testes usam identidade/empresas/agente locais e interceptam todas APIs/WebSockets; não entram em produção, criam objetos no servidor ou executam agentes. Alguns serviços retornam indisponibilidade deliberadamente: a cobertura valida navegação/frame/estados vazios/erro, não a funcionalidade de cada serviço real.

`navigation-results.json`: navegação de menu, empresa selecionada e persistência local, administração acessível ao admin, filtro de viewer, rota protegida exigindo login, query legada e drawer mobile. Testar seleção de empresa não comprova isolamento de dados de tenants.

A cobertura não inclui todos os conteúdos reais, todas as variações de dados, todos os modais ou leitor de tela. No caso parametrizado usa identificador de QA; ausência do recurso é um estado esperado. Nenhuma alegação de produto completo ou integração voz pronta. Live é frente separada; contrato proposto `/live` aguarda componente e endpoints reais e não é registrado por inferência neste incremento.

## Coordenação

Somente frontend e evidências. Nenhum backend, deploy, override Telegram, rename de repo ou alteração de licença. Commits UI34, branding36 e nome permanecem preservados. Backend coordena rename e único rollout. Não publicar sobre uma imagem/base que regreda os hotfixes em produção.

## Resultado final desta rodada

- 118/118 casos (59 padrões × 375/1440px) renderizaram no build congelado, sem barreira de erro e sem overflow da página ou conteúdo principal. Todas as rotas autenticadas apresentaram o novo shell. `frozen-build.json` registra os hashes dos assets usados.
- Navegação e Configurações acessadas em ambas as larguras; foco permanece no drawer e retorna ao botão Menu ao fechar; query legada preservada.
- Empresa Alfa com logo de teste e Empresa Beta sem logo foram selecionadas; persistência local e cabeçalho atualizados. Crédito/logo EvoNexus também é preservado quando há logo próprio de empresa. Isso não testa isolamento de dados no servidor.
- Usuário não autenticado recebe login; viewer não recebe link administrativo de Configurações.
- Plugin local de QA: switch com alvo 44×44, alteração interceptada no fixture e detalhe acessível por Enter. Nenhum plugin real foi instalado, ativado ou desativado.
- Build TypeScript/Vite passou; lint dos componentes novos e PluginCard passou; `git diff --check` passou. Aviso preexistente de chunk >500kB continua.
- A verificação mecânica confirmou 85 arquivos TSX com mudanças somente de tokens/fontes/aviso de modificação (após normalização); diferenças intencionais de interface estão discriminadas em `mechanical-validation.json`. Ao todo, 3.863 utilitários da paleta central e 875 da paleta secundária foram tokenizados.
- Novos nomes de grupos/áreas e textos do shell possuem recursos pt-BR/en-US/es. O restante das traduções existentes foi preservado; cópia legada de algumas páginas continua mista e não é apresentada como totalmente revisada editorialmente.

Revisão funcional com dados de produção, conteúdos parametrizados válidos, todos os modais, leitor de tela e dispositivos físicos ainda precisa de validação integrada. Esta rodada é a reforma global do frame e sistema visual com cobertura explícita; não é declaração de todos os fluxos de negócio ou voz completos.
