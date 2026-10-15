# Restauração da navegação — prévia local

Base: implantação `4894e29`. Referência anterior à reforma global: `536b925^` (Sidebar). Branch isolada: `codex/restore-original-navigation`. Não há alteração de backend, serviços, endpoints, permissões ou implantação.

## Diferenças objetivas

A reforma expandiu 9 links para 32 (+23), reorganizou os três blocos originais em seis grupos recolhíveis e iniciou quatro fechados. Nenhum dos nove destinos originais foi apagado, mas ordem, visibilidade e nomes mudaram. Agentes virou Squad de agentes, Missões virou Projetos e missões, Kanban virou Quadro de trabalho. Heartbeats/Rotinas/Gatilhos saíram de Inteligência para Operação; Integrações passou a Conexões. Configurações foi duplicada como link além da engrenagem original. `comparison.json` registra cada destino adicionado.

Restaura-se exatamente a definição original: Cockpit (OmniNexus Live), Missões, Kanban, Materiais; Inteligência (Agentes, Heartbeats, Rotinas, Gatilhos, Integrações). Blocos nativos sempre abertos, com os mesmos filtros `resource/view`. Plugins mantêm sua injeção e colapso originais. Engrenagem, empresas e perfil continuam no rodapé. Rotas extras continuam registradas; não foram removidas páginas nem seus acessos internos.

## Identidade e licença

O nome textual grande precedia a logo e aumentava o cabeçalho. Agora o asset já existente Sistema Britto lidera o topo; OmniNexus Live aparece secundário. A logo da empresa selecionada continua no bloco seguinte. Sem logo de empresa, a logo EvoNexus permanece intacta nesse bloco; com logo de empresa, a logo EvoNexus permanece no rodapé visível, como antes. Nenhum asset ou crédito foi removido.

LICENSE, condição 1(a): “you may not remove or modify the LOGO or copyright information”. Condição 1(b): exige aviso claro do uso de EvoNexus para administradores, acessível pela documentação/configurações. Ambos os avisos existentes são preservados. Não se presume que esconder créditos permita retirar a logo, nem se declara aprovação jurídica. Outras superfícies não são alteradas nesta correção focada.

## QA e limites

Capturas e resultados são do app real compilado localmente com identidade/dados de fixture e todas as APIs/WebSockets interceptados, sem mutações reais. Não representam sessão autenticada em produção. A definição dos nove links foi comparada literalmente à referência Git. QA cobre desktop 1440×900 e mobile 375×900, admin e usuário restrito, ordem/rótulos, cliques dos destinos permitidos, drawer/Tab/Escape/foco e logos visíveis.

TypeScript/Vite e ESLint da sidebar passaram; permanece o aviso preexistente de chunk >500kB. Os quatro cenários de QA passaram. Grupos de plugins foram preservados no código, mas o fixture não instalou plugins de terceiros.

Nenhuma implantação foi realizada; a prévia exige revisão visual antes do handoff de rollout. Leitor de tela, Safari e dispositivos físicos não testados.
