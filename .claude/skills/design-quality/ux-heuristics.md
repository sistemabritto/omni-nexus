# Heurísticas UX aplicadas — criação e revisão

Síntese original OmniNexus, 2026-10-15, a partir do pedido do usuário e fontes abaixo. O contexto recebido relata um único print; esta referência não afirma ter inspecionado pixels nem presume um segundo print. A lista relatada repete Postel e distância do alvo é aplicação de Fitts, não vinte leis universais. Não redesenhar menu ou outros componentes só por ler este arquivo; preservar DS e escopo.

## Critérios por tarefa

- Navegação: agrupar por tarefa do usuário, com rótulos reconhecíveis e descoberta progressiva quando útil. Não limitar artificialmente a sete itens. Links de navegação e disclosure não recebem `role=menu` automaticamente; respeitar semântica e comportamento do padrão escolhido.
- Toque e ações: alvo de projeto mobile de 44×44 CSS px quando viável; distinguir do WCAG 2.2 AA mínimo de 24×24 CSS px, com exceções documentadas (espaçamento, equivalente, inline, controle do agente de usuário, essencial). Medir área realmente clicável e proximidade, não apenas ícone; separar ações destrutivas de ações frequentes.
- Seletor de squad: nomes, funções e setores legíveis; estado selecionado distinguível de foco e hover. Manter contexto da tarefa e indicar consequência da troca; não perder trabalho digitado.
- Voz: representar estados verdadeiros idle, conectando, ouvindo, processando, falando, interrompido e erro, conforme eventos reais. Texto e ícone complementam cor. Mute e fim de chamada têm significado claro; permissão negada e reconexão têm recuperação explícita. Esta é orientação textual, não alteração de VoiceDream/Live.
- Formulários: labels, ajuda e erro próximos; preservar dados após falha, explicar correção e próxima ação. Normalizar formatos inofensivos sem relaxar validação de schema, integridade ou permissão. A máxima de Postel não autoriza aceitar entrada ambígua/maliciosa ou esconder inconsistência de protocolo.
- Feedback: progresso somente quando medido ou estado conhecido; usar estado indeterminado honesto quando não há percentual real. Não prometer resposta garantida em 400ms, atribuir tudo a 80/20 ou tratar limiares de performance como garantia individual. Medir interações reais antes de alegar melhoria.

## QA com evidência

Para cada achado: **tarefa → problema → princípio → mudança proposta → teste → evidência**. Revisor Oath aplica os mesmos critérios independentemente; não julga estética por script.

Exercitar no escopo: teclado e foco, toque/área clicável, leitura por tecnologia assistiva, zoom e texto longo, reflow e reduced motion. Em fluxo de voz efetivamente autorizado, testar permissão de microfone negada, falha/conexão tardia, interrupção e reconexão com preservação do contexto. Não ligar microfone ou iniciar chamada para cumprir um checklist sem autorização da tarefa.

Registrar ambiente/viewport/estado e PASS/FAIL/NÃO TESTADO/NÃO APLICÁVEL. Sem navegador/dispositivo/leitor ou fluxo de voz autorizado, indicar limitação; não inventar teste ou conformidade. Comparar com DS aprovado, controles reais e critérios do brief antes de propor mudança.

## Fontes primárias consultadas

- [W3C — Target Size Minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum): mínimo AA e exceções. 44×44 é alvo do projeto, não definição desse mínimo.
- [RFC 9413 — Maintaining Robust Protocols](https://www.rfc-editor.org/rfc/rfc9413.html): limitações da tolerância a entradas e necessidade de especificações robustas; normalização não substitui validação/permissão.
- [web.dev — Optimize INP](https://web.dev/articles/optimize-inp): investigar latência da interação, trabalho de handlers/render e dados reais; sem garantia fixa de 400ms.
- [NN/g — Ten Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/): visibilidade de estado, controle, prevenção/recuperação de erro, reconhecimento e consistência; heurísticas precisam de aplicação contextual.

Essas fontes fundamentam critérios de avaliação; não foram copiadas como código, assets ou controlador de interface.
