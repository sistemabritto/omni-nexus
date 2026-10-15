# OmniNexus · proposta de design system compartilhável

Referência verificada em 2026-10-15: `/home/sistemabritto/Documentos/sistemabritto-site` (somente leitura).

## Evidência e direção

- `pages/index.tsx`: home atual com fundo #080b12, superfícies #0d1320 e #101722, ação #a3ff12, hover/ênfase #c4ff72, texto branco/slate-300, bordas brancas translúcidas. Cartões rounded-3xl, controles rounded-xl, CTAs min-h-12. Espaçamento gap-3/5/12 e p-5/7.
- `styles/globals.css`, `tailwind.config.ts`, `pages/_app.tsx`: Space Grotesk em títulos; DM Sans em corpo. Os arquivos globais ainda contêm paleta dourada anterior. Para esta proposta a home atual prevalece sobre o dourado legado.
- Tokens portáveis: `dashboard/frontend/src/pages/omninexus-tokens.css`. Nenhuma alteração no site. Fontes declaradas com fallback de sistema; não se baixou nem incorporou arquivos de fonte nesta entrega.

## Aplicação da UI/UX Pro Max

Skill efetivamente lida: `/home/sistemabritto/.codex/skills/ui-ux-pro-max/SKILL.md`, referências `pro-rules.md` e `quick-reference.md` §§1–3.
Buscas executadas: `AI workspace operations dashboard --design-system -p OmniNexus` e `responsive accessible forms --stack react`.
Resultado: Minimalism & Swiss Style apropriado a dashboards, formulários controlados React. A sugestão automática de landing page e a paleta roxa genérica foram rejeitadas por não corresponderem ao app e à referência de marca. A origem instalada não possui LICENSE/metadata que prove igualdade byte a byte com upstream; não se afirma isso. Fonte indicada pelo usuário: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill ; LICENSE upstream inspecionada: MIT, Next Level Builder (2024). Nenhum instalador executado, nenhum código/assets de Mark-LV ou MegaBrain utilizado.

## Melhorias propostas sobre a referência

- Conservar fundo escuro + lima; limitar o acento a ações/seleção, para estados operacionais continuarem legíveis.
- Trocar hero e grandes cartões promocionais por três regiões de trabalho: squad/sessões, conversa, contexto. Em telas médias contexto ocupa linha própria; em mobile as regiões ficam em uma coluna.
- Controles de pelo menos 44px, texto explícito além de cor, foco de teclado, labels persistentes, erros inline, movimento reduzido. Evitar hover/gradiente como única indicação de estado.
- Jobs mostram estados e etapas reais, sem inventar porcentagem. Falha de API não é apresentada como lista vazia bem-sucedida.
- Memória apresenta caminho da fonte, sem sugerir que o arquivo foi usado pelo modelo. Jobs são globais, identificados como tal; não há vínculo inventado com a sessão.
- Não aplicar um tema claro ainda: a referência é escura e este escopo não valida uma segunda paleta.

## Fronteira de implementação e licença

Esta implementação está dentro do frontend derivado EvoNexus, reutiliza AgentChat, auth, navegação e contratos existentes. Não é um frontend independente que dispense as condições de LICENSE. Preservados logo/copyright existentes; aviso adicional no rodapé da central e documentação. `LICENSE` exige não remover/modificar logo/copyright no frontend e notificar administradores via documentação ou settings. Texto de licença e nome do repositório intactos.

Recomendação de estrutura: manter por enquanto `dashboard/frontend` e `dashboard/backend` no mesmo repositório, com módulos/tokens próprios isolados e um adaptador explícito para APIs. Uma futura UI independente exige inventário de proveniência de componentes/assets e avaliação das condições de licença; separar diretórios ou renomear marca não resolve essas condições. Não há declaração de multitenancy pronto.

## Próxima evolução (proposta, sem capacidades novas nesta entrega)

Conversa contínua/memória deve indicar escopo e proveniência. Para conteúdo/redes, distinguir rascunho, revisão, aprovação e publicação; publicar exige autorização explícita. Para trabalho com código, mostrar projeto, repositório, branch, agente autor, tarefa, diff e revisão lado a lado com a conversa. A UI não deve inferir que escolher agente muda repo/branch, nem apresentar atividades globais como tarefas da sessão. Esses vínculos dependem de contratos reais do backend e serão alinhados antes da implementação. Nenhum outro repo foi editado e nenhuma rede social foi publicada nesta entrega.

Mobile primeiro: o contexto principal é a conversa. Na pequena tela o squad fica compacto e histórico/voz usam disclosure explícito; contexto de atividade/memória vem depois do chat. Desktop amplia para três regiões. A migração do Telegram precisa de alternativa autenticada validada, reconciliação de sessões/pendências e plano de retorno; sem desativação de bot/webhook nesta entrega.
