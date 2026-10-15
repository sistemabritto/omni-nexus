# OmniNexus Live · aplicação global

A central inicial não era uma reforma global. Este incremento aplica o sistema visual a todas as rotas existentes, preservando funções e hierarquia de permissões.

- Frame de workspace em todas as rotas autenticadas: cabeçalho da área, descrição curta e contexto de empresa. Contexto UI não representa garantia multitenant.
- Navegação em seis domínios expansíveis: Workspace; Trabalho; Operação; Memória/conhecimento; Conexões/ferramentas; Administração. Conversa, squad e aprovações têm entradas explícitas. Configurações, empresas e plugins continuam acessíveis.
- Mobile primeiro: drawer nomeado, alvo de toque, grupos expansíveis, inert fechado, Escape, contenção/restauração de foco, scroll do menu independente e safe-area. Operações densas usam quebra de linha; tabelas usam rolagem interna no telefone e mantêm layout tabular no desktop.
- Tokens semânticos substituem cores arbitrárias em 96 arquivos sem alterar paletas de dados/agentes. DM Sans/Space Grotesk conectam o site e o produto; fontes de código permanecem técnicas. Cores semânticas de falha/alerta/sucesso não são substituídas por marca.
- Contraste/foco/superfícies consistentes, formulários e controles de toque, sem depender de hover. Novos switches preservam a forma visual em uma área de toque 44px. Motion reduzido e idioma de documento acompanhando locale.
- Logos/avisos upstream permanecem, inclusive quando a empresa selecionada usa logo próprio. Nome aprovado é OmniNexus Live, sem renomear identificadores de código, rotas ou imagens.

UI/UX Pro Max usada: pesquisas de sistema visual, React e `keyboard focus modal --domain ux`; prioridades de acessibilidade, touch e layout aplicadas. A marca deriva de Sistema Britto; a sugestão genérica de landing page/roxo foi descartada. O site de referência não foi alterado.

Cobertura: `qa/global-ui/route-matrix.md`, `gallery.html`, resultados e capturas. Dados são fixtures locais, não produção. Funções Live e endpoints de áudio são frente separada; a interface não declara voz disponível nem inclui chave no cliente.
