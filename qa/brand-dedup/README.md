# Logo duplicada no cabeçalho

Base `a9787c2` (PR42). O cabeçalho mostrava a logo fixa Sistema Britto e novamente a logo da empresa ativa. Quando ambos eram a mesma marca, havia duplicação. Remove-se apenas a segunda apresentação do topo: a empresa continua identificada pelo avatar/logo e nome no seletor do perfil. Notificações e fechar menu ficam no mesmo cabeçalho.

A logo EvoNexus intacta aparece uma vez, sempre no rodapé junto aos créditos visíveis; sem depender de a empresa ter logo. LICENSE 1(a) exige preservar logo/copyright e 1(b) aviso para admins em docs/settings. Nenhum asset, crédito, aviso ou acesso foi apagado. Nove links, ordem, permissões e rotas preservados. Nenhuma alteração de backend ou deploy.

QA local Chrome em 375×667 e laptop 1440×768, admin com logo de empresa igual à marca Sistema Britto e viewer sem logo de empresa. APIs/WebSockets interceptados, identidade e dados de fixture; não é QA autenticado de produção. Verifica uma imagem no cabeçalho, atribuição visível, ausência de overflow lateral, nove links para admin/quatro permitidos ao viewer, cliques de rotas, teclado mobile e retorno do foco. Capturas em PNG e resultados JSON. Safari/leitor de tela/dispositivo físico não testados.

Inclui acabamento solicitado: versão/consulta de versão retiradas da sidebar; perfil com padding vertical de 8px; créditos em uma linha visível, links sem gaps adicionais e alvos de toque preservados em 44px. Verifica que os nove links cabem sem rolagem nesses dois viewports. Plugins extras ou alturas menores podem exigir rolagem no nav; perfil/settings/logout/créditos permanecem disponíveis.

Resultado: quatro cenários passaram; os nove links cabem em 375×667 e 1440×768 sem overflow vertical do nav. TypeScript/Vite e ESLint passaram; Vite foi repetido após o último ajuste somente CSS. Permanece o aviso preexistente de chunk >500kB. Capturas revisadas localmente; nenhum novo gate de revisão ou implantação foi criado.
