# Revisão independente de design — Oath

Orientação local OmniNexus, 2026-10-15, compatível com o filtro Anti-Slop atribuído em ORIGIN.md. Oath é o papel real de verificação independente; não pode aprovar o próprio trabalho produzido na mesma conversa. Se essa independência não existir, registrar revisão independente pendente e encaminhar à faixa de verificação existente; não fabricar segunda revisão.

Carregar SKILL.md e contrast.md antes da revisão. Evidências do criador são contexto, não prova suficiente de revisão. Inspecionar o resultado no escopo solicitado e registrar por item PASS / FAIL / NÃO TESTADO / NÃO APLICÁVEL, evidência, ambiente/viewport/tema, impacto e correção. Falta de ferramenta vira NÃO TESTADO, não aprovação presumida.

| Critério | Evidência exigida |
|---|---|
| Marca e direção | Comparar tokens/componentes/fontes/voz com a fonte aprovada e indicar caminho/versão; ausência de brandbook é lacuna, não licença para trocar a marca. Requisitos e acessibilidade prevalecem. |
| Contraste | Valores resolvidos de foreground/fundo, tamanho/peso, razão bruta e limiar. 4,499 falha em 4,5; 18px regular exige 4,5, grande começa em 24px regular ou 14pt/56÷3px negrito. Fundo com alpha/imagem/gradiente precisa composição/amostragem real. Um cálculo de par opaco não certifica o design. |
| Responsividade | Inspeção real nos tamanhos afetados e intermediários: viewport registrado, texto longo/zoom, reflow, overflow, tabelas e conteúdo sob barras fixas. Screenshot de desktop não prova mobile. |
| Controles reais | Acionar controles relevantes e registrar ação→resultado: links/destinos, formulário inválido/sucesso, menu, diálogo/Escape, tabs, teclado/foco e estados vazio/loading/erro aplicáveis. Leitura de handler não equivale a clique realizado. |
| Propósito e conteúdo | Conferir hierarquia, CTA e motivos da composição; buscar fontes de métricas/depoimentos/claims. Não reprovar marca por uso de cards, gradientes ou fontes que o revisor pessoalmente evita. |
| Movimento e acesso | Quando afetado, observar reduced motion, foco/teclado e feedback percepível; só declarar o que foi exercitado. |

Testes/build e cálculo de contraste apoiam correção funcional; nenhum script determina qualidade estética. Usabilidade e composição exigem julgamento contextual e observação. Sem renderizador, entregar achados textuais/de código com inspeção visual e interações NÃO TESTADAS; não declarar o material aprovado visualmente.

Para esses fluxos, ler também [heurísticas UX](ux-heuristics.md) e registrar tarefa→problema→princípio→mudança→teste→evidência, incluindo limitações de dispositivo/leitor/microfone.
