# Acabamento local — modais de empresa

Branch `codex/company-dialog-polish`, derivada do commit integrado `2d397cf`. O commit preparado e a imagem em espera não foram alterados. Nenhuma implantação, chamada a produção ou alternativa ao fluxo de aprovação foi usada.

## Lacuna reproduzida

A rodada anterior validou rotas vazias/erro e navegação, mas não abriu os modais de empresa. `CompanyListModal` e `CompanyManagerModal` eram descendentes da sidebar transformada. O `position: fixed` ficava restrito ao bloco do menu: moldura de 299px no viewport de 375px e 239px no desktop de 1440px. Também não havia semântica de diálogo nem labels associados aos campos de texto. `baseline.json` e `before-*.png` documentam a reprodução com fixture local no build anterior; os componentes de empresa e a geometria da sidebar desse build são iguais aos de `2d397cf`.

## Correção

- `DialogFrame`: portal em `document.body` + `<dialog>.showModal()` para a camada superior, independente da transformação da sidebar. Somente os modais de empresa adotam o componente nesta rodada.
- Tab contido na camada ativa, Escape fecha apenas o diálogo superior, foco devolvido ao elemento anterior ou seletor de empresa. O drawer não captura teclado enquanto um diálogo está aberto.
- Confirmação de exclusão conserva as duas etapas e dá foco inicial a Cancelar, inclusive ao avançar de etapa; erro de exclusão aparece na própria camada ativa.
- Labels/IDs associados, nome obrigatório anunciado, controles de 44px, fontes e tokens globais, texto auxiliar legível. Upload continua desabilitado antes de criar a empresa.
- Erro de criação preserva os campos e mantém a ação de envio visível em landscape. APIs, payloads, máscara de CNPJ, geração de slug e regras de exclusão não foram alterados.

UI/UX Pro Max: prioridades de foco, touch e layout aplicadas; pesquisa local `modal focus return --domain ux` confirmou orientação de foco visível e não encoberto. Não se declara conformidade WCAG integral.

## Verificação

`npm run build` (TypeScript/Vite) e ESLint dos três componentes passaram; aviso de chunk preexistente >500kB permanece. `qa.cjs` testa 375×900, 812×375 e 1440×900 em Chrome local com movimento reduzido. Resultados/capturas em `results.json`, `after-list-*.png` e `after-form-*.png`.

Foram testados geometria, rótulos, Tab, Escape em edição aninhada, retorno de foco, duas etapas de exclusão com foco seguro, erro de exclusão visível, upload bloqueado antes da criação, máscara CNPJ, slug automático e erro de formulário mantendo valores/botão visíveis. Cada cenário emite um POST e um DELETE de fixture, ambos interceptados e devolvidos como falha; nenhuma empresa é criada ou removida no servidor. WebSockets e APIs reais são interceptados pelo fixture herdado de `qa/global-ui`.

QA de produção segue bloqueado pela autorização direta pendente na tarefa backend, após duas negativas. Leitor de tela, Safari e dispositivos físicos não foram validados. Não foi repetida a matriz de 118 rotas, pois o ajuste se limita aos diálogos e ao desvio de teclado do drawer quando um desses diálogos está aberto. Marca, créditos e licença EvoNexus permanecem.
