# Complemento de crítica visual — apenas lacunas do cookbook

Síntese modificada OmniNexus, 2026-10-15, de Taste Skill MIT; origem/aviso em ORIGIN.md e LICENSE-taste-skill. Não é terceiro design system. Se disponível, usar o cookbook `.claude/skills/design-quality/SKILL.md` e UI UX Pro Max para critérios já cobertos, sem duplicar gates. Requisitos/acessibilidade → tokens/componentes Britto aprovados → recomendações UX → filtro de qualidade.

## Antes do layout/revisão

Criador Canvas e revisor Oath recebem a mesma versão de brief, tokens/componentes, escopo e claims/provas. Registrar fonte/caminho/commit efetivo; não inventar identidade ou um segundo conjunto de tokens. Inventariar somente telas/estados que o pedido afeta e suas transições: ideal, vazio, carregando, erro, permissão e recuperação pertinentes. Estado não acessível no ambiente fica pendente; inventário não é prova de execução.

Listar afirmação → prova/origem/direitos antes de organizar seções. Conteúdo sem evidência não vira prova visual, depoimento ou métrica fictícia. Asset existente não é automaticamente reutilizável: verificar origem/licença/atribuição próprias; não copiar biblioteca/imagens Taste. Não forçar imagens, animações ou seções para atingir quotas.

## Crítica e reteste

Quando houver render disponível em tarefa autorizada, inspecionar screenshots responsivos dos viewports/estados afetados, com versão e contexto registrados. Comparar o que está realmente visível à direção aprovada; código/inspector passing não prova qualidade visual, reduced motion ou conversão.

Selecionar até três correções prioritárias reais, não inventar três defeitos quando há menos. Para cada uma: problema localizado → screenshot/viewport/estado → impacto → critério do brief/UX → correção proposta → reteste e evidência. Priorizar falhas de funcionamento, acesso, marca e prova; recomendações de hierarquia, ritmo/tipografia e composição vêm depois. Não redesenhar por conta própria; corrigir somente escopo autorizado e registrar restante.

Brand drift contra o brief, prova inventada, ação quebrada e falha de acessibilidade são achados de reprovação com evidência concreta. Gosto estético é recomendação fundamentada, não FAIL automático ou nota que demonstra conversão. Não importar bans de cores/fontes/cards, direção aleatória, quatro imagens, oito animações ou quotas de rounds.

Após correção, repetir os testes afetados nos mesmos estados/viewports e registrar antes/depois. Não repetir indefinidamente nem presumir sucesso porque a implementação foi alterada. Usar PASS/FAIL/NÃO TESTADO/NÃO APLICÁVEL por critério, sem esconder limitações; sem renderer, entregar revisão textual/de código e screenshots/interações NÃO TESTADOS.

Não instalar/executar scripts/servidor/inspector Taste. O contraste upstream só reprova abaixo de 2,6, insuficiente para AA; o inspector padrão não verifica reduced motion; servidor pode expor raiz/symlinks/dotfiles e há flag GPU insegura. Usar os critérios corretos do cookbook já existente; não transplantar essas ferramentas.
