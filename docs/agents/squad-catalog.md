# Squad — catálogo aditivo e proposta de organização

Inventário read-only em 2026-10-16, base `origin/main` b1f28d4. Os setores abaixo organizam apresentação e descoberta: não mudam ACL, camada business/engineering, dono, comandos, filas, agentes, memórias ou atribuições. Nenhum serviço externo ou publicação foi executado nesta entrega. Não é atestado do estado vivo da VPS.

## Entrega utilizável

`GET /api/agents` mantém resposta/nomes/descrições/locked existentes e acrescenta `catalog`: display_name, function, sector_id/sector e knowledge. A interface atual pode ignorar o campo sem regressão; agrupar visualmente por setor é aplicação futura do integrador, não redesenho incluído neste patch. Agentes personalizados/plugins recebem setor genérico sem renomear identidade.

Cada referência textual registra separadamente: `document_present` (SKILL.md encontrado), `persona_reference` (caminho explícito antes do corte de memória, alinhado ao loader real), `operational_status: not_verified`. A presença de script não comprova dependência, configuração, consentimento ou serviço. Nem referência carregável prova que o modelo leu/executou. A detecção é um limite inferior: skills citadas apenas por nome/aliases, regras, referências on-demand ou prompts próprios não entram automaticamente. Não instalar repositórios para preencher uma coluna.

## Setores propostos

| Setor | Nome | Slug preservado | Função |
|---|---|---|---|
| Coordenação e estratégia | Oracle | `oracle` | Descoberta do negócio e contexto de conhecimento |
| Coordenação e estratégia | Clawdia | `clawdia-assistant` | Fila operacional, contexto e encaminhamento |
| Coordenação e estratégia | Helm | `helm-conductor` | Coordenação do ciclo de engenharia |
| Coordenação e estratégia | Sage | `sage-strategy` | Estratégia e prioridades de negócio |
| Coordenação e estratégia | Mirror | `mirror-retro` | Retrospectiva e aprendizado do processo |
| Produto e projetos | Atlas | `atlas-project` | Acompanhamento de projetos e bloqueios |
| Produto e projetos | Nova | `nova-product` | Requisitos e decisões de produto |
| Produto e projetos | Planejador de projetos | `project-planner` | Transformar contexto em plano de projeto |
| Produto e projetos | Sugestor de objetivos | `goal-suggester` | Propor objetivos para revisão |
| Produto e projetos | Planejador de objetivos | `goal-planner` | Decompor objetivos em trabalho verificável |
| Produto e projetos | Compass | `compass-planner` | Plano técnico e interfaces da implementação |
| Produto e projetos | Echo | `echo-analyst` | Lacunas e critérios dos requisitos |
| Produto e projetos | Raven | `raven-critic` | Crítica de riscos e coerência de planos |
| Marketing, criação e relacionamento | Mako | `mako-marketing` | Pesquisa competitiva, posicionamento e campanhas |
| Marketing, criação e relacionamento | Pixel | `pixel-social-media` | Conteúdo social e adaptação por canal |
| Marketing, criação e relacionamento | Coprodutor de Reels | `reels-copilot` | Um roteiro por rodada no fluxo de revisão |
| Marketing, criação e relacionamento | Canvas | `canvas-designer` | Design de interfaces e direção visual |
| Marketing, criação e relacionamento | Nex | `nex-sales` | Qualificação, pipeline e próxima ação comercial |
| Marketing, criação e relacionamento | Pulse | `pulse-community` | Comunidade e relacionamento coletivo |
| Marketing, criação e relacionamento | Zara | `zara-cs` | Sucesso do cliente e tratamento de demandas |
| Dados e pesquisa | Dex | `dex-data` | Métricas, qualidade de dados e reconciliação |
| Dados e pesquisa | Prism | `prism-scientist` | Análise científica e hipóteses estatísticas |
| Dados e pesquisa | Scout | `scout-explorer` | Exploração de código e localização de evidências |
| Dados e pesquisa | Scroll | `scroll-docs` | Pesquisa em documentação técnica |
| Dados e pesquisa | Quill | `quill-writer` | Documentação técnica com exemplos verificáveis |
| Engenharia e manutenção | Apex | `apex-architect` | Arquitetura e decisões técnicas |
| Engenharia e manutenção | Bolt | `bolt-executor` | Implementação de mudanças delimitadas |
| Engenharia e manutenção | Hawk | `hawk-debugger` | Reprodução e correção de bugs |
| Engenharia e manutenção | Trail | `trail-tracer` | Rastreamento causal entre componentes |
| Engenharia e manutenção | Zen | `zen-simplifier` | Simplificação de código no escopo pedido |
| Engenharia e manutenção | Flow | `flow-git` | Histórico Git e organização de alterações |
| Qualidade e segurança | Lens | `lens-reviewer` | Revisão de código: especificação e qualidade |
| Qualidade e segurança | Oath | `oath-verifier` | Verificação independente com evidência |
| Qualidade e segurança | Grid | `grid-tester` | Estratégia e implementação de testes |
| Qualidade e segurança | Probe | `probe-qa` | QA interativo e diagnóstico de falhas de uso |
| Qualidade e segurança | Vault | `vault-security` | Revisão de segurança e fronteiras de confiança |
| Administração e desenvolvimento humano | Flux | `flux-finance` | Operação financeira e relatórios |
| Administração e desenvolvimento humano | Lex | `lex-legal` | Análise jurídica e revisão de conformidade |
| Administração e desenvolvimento humano | Aria | `aria-hr` | Pessoas e processos de RH |
| Administração e desenvolvimento humano | Kai | `kai-personal-assistant` | Organização pessoal no domínio isolado |
| Administração e desenvolvimento humano | Mentor | `mentor-courses` | Cursos e percursos de aprendizagem |
| Administração e desenvolvimento humano | Lumen | `lumen-learning` | Retenção e revisão do aprendizado |

## Lacunas verificadas e próximos passos

Os módulos auditados propostos nos PRs anteriores (`logo-design`, `mkt-creative-brief`, `design-quality`, `dev-team-methods`, `mkt-research-pipeline`, `social-reels-editorial`) não existem na revisão histórica b1f28d4 consultada pelo autor. Isso significa “ausente nesta revisão”, não “nunca integrado” nem “ausente em todo container”. O catálogo checa o arquivo a cada resposta, portanto após integração passa a refletir presença e referência sem hardcode de status aprovado. Integrador deve conferir seu HEAD e imagem efetivos.

Reels é exceção importante: `generate_reel` nesta base usa `agent=""`; persona não prova orientação incluída no prompt in-process. Preservar o carregamento explícito e os testes do PR64 ao integrar. `/api/skills` descobre `.claude/skills`; o catálogo também reconhece caminho explícito `.claude/skills-media`, sem alegar que esse diretório está listado no endpoint original de skills. Não alterar loader só para fazer inventário parecer completo.

Fluxo aplicável: coordenação existente seleciona papel → persona/runtime carregam orientação pertinente → executor produz artefato → revisor independente valida critério/evidência → ação externa usa sua autorização real. Catálogo não despacha agentes nem cria segundo controlador.

## Sobreposições que devem ser esclarecidas, sem remover ninguém

- Clawdia organiza fila operacional; Helm coordena ciclo de engenharia. Handoff tem dono até aceite; não criar coordenação concorrente.
- Atlas acompanha projeto; planejadores de projeto/objetivo propõem cascata; Compass planeja interfaces técnicas. Distinguir acompanhamento, proposta e execução.
- Mako define pesquisa/posicionamento; Pixel adapta conteúdo; coprodutor produz um roteiro no contrato próprio; Canvas cuida de interface/direção visual. Nenhum catálogo concede publicação.
- Lens revisa código; Oath verifica conclusão independente; Grid escreve testes; Probe exercita uso; Vault revisa segurança. Não somar gates idênticos ou autoaprovar trabalho próprio.
- Dex reconcilia métricas; Prism avalia hipóteses estatísticas; Scroll pesquisa documentação e Scout localiza código. Preservar o tipo de evidência de cada papel.

## Permissões, ferramentas e licenças

As permissões continuam calculadas por `has_agent_access`, fora deste catálogo. Não mudar locked para tornar alguém “disponível”. Conexão, credencial, preço/orçamento, direitos de asset e aprovação humana continuam pré-requisitos próprios para ferramenta operacional. Higgsfield preparado/desabilitado não é ferramenta liberada nem geração autorizada.

Nenhuma fonte upstream foi copiada nesta entrega: descrições/setores são metadados originais locais. As skills previamente adaptadas mantêm seus LICENSE/ORIGIN; ausência não autoriza instalar pacotes/assets ou relicenciar referências. Inventário não lê segredos, não testa credenciais e não executa scripts de skills.

## Validação

46 testes locais: cobertura das 42 personas; recorte de prompt comparado ao loader real; arquivo versus referência pós-memória; fallback custom; endpoint aditivo preservando descrição/model/locked e arquivo original. Sem simulação de comportamento de modelo, teste de serviço externo ou alteração de produção. `git diff --check` sem erros.

## Revalidação na integração produtiva

Integração sobre ac5e6f5: todos os seis módulos citados acima estão presentes. Os 42 testes por persona comparam o recorte ao loader real nessa base, sem alegar leitura pelo modelo. O incremento continua somente na API; nenhum seletor visual consome catalog neste lote. Reels preserva a leitura explícita da skill já integrada; a nota do catálogo permanece cautelosa sobre o handler in-process.
