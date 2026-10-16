# Revisão funcional de squad e skills — 16/10/2026

## 1. Decisão proposta

Manter os 42 agentes e os sete setores publicados; não ocultar, apagar, redistribuir tickets ou habilitar heartbeats nesta revisão. Setor é descoberta visual, não despacho ou ACL. Os sete responsáveis sugeridos anteriormente são uma proposta de governança por entrega, não substitutos automáticos dos sete setores nem agentes escolhidos por volume bruto:

| Dono proposto | Entrega concreta | Especialistas/capacidades sob demanda, sem removê-los |
|---|---|---|
| Clawdia — operação | Fila priorizada com dono, prazo, bloqueio e próxima ação até aceite | Atlas acompanha projetos; Helm coordena engenharia; planners mantêm missão→projeto→goal→ticket |
| Mako — crescimento/oferta | Brief com público, oferta, CTA, hipótese, KPI e decisão | Sage estratégia; Nova produto; pesquisa compartilhada sem duplicar calendário de Pixel |
| Pixel — conteúdo/distribuição | Pacote por canal com mídia final, revisão, aprovação e URL publicada ou falha explícita | Copilot roteiro; Canvas direção/UI; worker compõe/renderiza; Postiz publica com autorização |
| Nex — vendas/CRM | Lead elegível com identidade, responsável, estágio e próxima ação registrada | Zara suporte e Pulse comunidade conforme demanda; nenhum outreach implícito |
| Dex — medição | Fonte/janela, baseline, taxonomia e coorte conteúdo→lead→conversa→venda | Prism estatística; Bolt implementação de tracking; fonte falha não vira zero |
| Bolt — desenvolvimento | Mudança delimitada com critérios e testes verificáveis | Hawk debug, Flow Git, Scout busca, Scroll docs, Quill documentação, Compass/Echo/Apex conforme ambiguidade/risco |
| Oath — verificação independente | Veredito por critério com evidência e limitações | Lens revisão código, Grid escreve testes, Probe exercita serviço, Vault segurança; Zen limpa código sem autoaprovar a entrega |

Flux, Lex, Aria, Kai, Mentor e Lumen preservam seus domínios. Seu baixo volume na fila observada não prova inutilidade. Oracle é descoberta/ativação no contrato atual, não um novo buscador ou executor genérico. Todos os papéis/identidades permanecem no catálogo existente [squad-catalog.md](squad-catalog.md).

## 2. Base e método

Worktree própria `audit/squad-functional`, derivada do SHA produtivo `8b7e054653365d4e5f69c87c89ce84e9a49d7cee`. `cf52663` já está integrado via `21e5b74`; não foi reaplicado. A nota inicial em squad-catalog.md sobre b1f28d4 descreve a investigação histórica, não esta base. Os seis módulos adaptados estão presentes nesta revisão integrada.

Leitura local dos contratos, loaders, handlers, empacotamento, cookbook, referências/licenças e artefatos sanitizados fornecidos pelos responsáveis. Nenhum DB vivo, ENV, memória, credencial, conta, modelo pago ou ferramenta externa foi consultado para este trabalho. Os scripts de skills não foram executados. Testes usam fixtures/mocks e guardas de credenciais do repositório.

Ferramenta reproduzível adicionada: `python3 scripts/audit_squad_runtime.py`. Saída JSON em [evidence/squad-runtime-2026-10-16.json](evidence/squad-runtime-2026-10-16.json). Não importa provider nem carrega configurações/env/DB/memórias. É snapshot local do código, não atestado do container. Hashes da persona limitada e documentos permitem comparar revisões sem despejar prompts/memórias.

## 3. Instalado, carregável, executável e testado são estados distintos

| Estado | Evidência nesta revisão | O que não comprova |
|---|---|---|
| Documento instalado no checkout | 220 SKILL.md/skill.md em `.claude/skills`; 15 em `skills-media` | Presença em volume/container, dependências ou autorização |
| Descoberto por API | `/api/skills` percorre apenas `.claude/skills`; testes Flask exercitam a rota | Lista não certifica tools. `has_scripts` verifica só arquivos no primeiro nível; falso pode esconder scripts aninhados |
| Referência recuperável na persona | Após este patch: 42 caminhos explícitos de documentos em 14 das 42 personas pelo recorte Python; 37 entradas de knowledge, 36 arquivo+referência raiz | Não é lista de todas as skills disponíveis; nomes abreviados, regras, links indiretos e plugins têm outros caminhos |
| Instrução no prompt | Loader real e testes de embedding confirmam pointers; Reels injeta o texto editorial | Pointer não significa conteúdo da skill injetado, leitura pelo modelo ou execução |
| Executável | 26 pastas de skills e quatro de skills-media contêm arquivos candidatos a script | Não foram checados bins, instalação, credenciais, custo, ACL ou serviço; status `not_verified` |
| Testado localmente | Testes de recuperação, montagem, links, licença local e validator puro de contraste | Não é prova de decisão do modelo, integração externa, revisão visual ou resultado comercial |
| Operacional em produção | Artefato sanitizado do integrador confirma API e preservação, sem execução de skill | A operação das skills permanece `not_verified`; não promover status por mocks |

As contagens de referência acima incluem o caminho adicionado para Zen neste patch. A produção antes dele tinha 36 entradas knowledge, 35 com documento+referência raiz. Canvas continua corretamente com `persona_reference=false` para a raiz dev-team-methods; o subdocumento design-critique é agora mostrado separadamente. Não mudar esse booleano para “melhorar” estatística.

## 4. Rotas reais do prompt/runtime

- **Python/OpenCode e OpenClaude:** `provider_fallback._agent_prompt` retira frontmatter e corta no marcador de memória. `_embed_agent_for_openclaude` inclui a persona no prompt passado ao adaptador. As instruções novas antes do corte chegam como texto; os cookbooks não são automaticamente abertos por esse loader. Para Claude CLI, o adaptador usa `--agent`; não assumir que todo provider compartilha o recorte Python.
- **Heartbeat:** `step1_load_identity` carrega a identidade; `step6_assemble_context` acrescenta inbox/decisão/goal e exige ler contexto pertinente. Execução por provider e tool policy é etapa separada. Handlers `system` podem ignorar persona por projeto, não representar agente ausente.
- **Chat terminal:** `chat-bridge.js::loadAgentFile` extrai o body e constrói `systemPrompt` com identidade, política de ferramentas, contexto/plugin e memória segundo provider. Esse body não tem o mesmo corte do helper Python. Esta revisão não altera esse caminho, tools ou memória; os testes Python não certificam todas as variantes do SDK.
- **Reels Copilot:** `generate_reel` usa `agent=""` e injeta `_editorial_guidance()` com o conteúdo de social-reels-editorial/SKILL.md antes do schema. Testes capturam a chamada mock e verificam conteúdo/schema; nenhuma geração, gravação em DB ou campanha é executada. Ausência do documento preserva fluxo/schema com warning; não significa resultado editorial aprovado.
- **Live:** seletor é apresentação. A identidade de continuidade é curada, não a persona completa. `live_task_dispatch.submit` limita persona a 6000 caracteres e diz expressamente que ferramentas estão desabilitadas: os pointers no fim da persona podem não chegar, e a skill não pode ser lida nesse fluxo de texto. É fronteira deliberada; não liberar tools nem ampliar memória para satisfazer inventário. A delegação agentic autorizada continua sendo outra rota.
- **MediaJob:** skill social-media-production compõe isoladamente; worker renderiza/valida; aprovação e Postiz são etapas próprias. Não atribuir render/publicação ao roteiro do Copilot nem ao catálogo.

## 5. Anti-slop e revisão independente

**Visual:** já existe `design-quality` (adaptação textual Anti-Slop), compatível com marca e UI UX Pro Max, mais review.md, contrast.md e ux-heuristics.md. Canvas recebe direção de criação; Oath recebe checklist independente e o mesmo complemento de crítica. Oath deve registrar PASS/FAIL/NÃO TESTADO/NÃO APLICÁVEL e não autoaprovar seu próprio trabalho. Testes conferem recuperação real desses caminhos e o código puro do contraste (4,499 falha no limiar 4,5; tamanhos corretos), não inspeção de uma página ou qualidade estética certificada.

**Código:** Zen implementa simplificação; dev-ai-slop-cleaner orienta cleanup, Lens revisa especificação/qualidade e Oath verifica critérios. A persona de Zen só citava o nome abreviado da skill: foi adicionado caminho explícito e limite de escopo. Não é agente novo nem gate global. Não invocar todos os revisores para toda tarefa: aplicar conforme tipo/risco e manter um veredito final independente.

## 6. Seis módulos adaptados: utilidade, origem e limites

| Módulo | Responsabilidade/entrega | Proveniência local e teste |
|---|---|---|
| logo-design | Canvas em pedido explícito de logo; conceitos e kit após escopo/aceite | kaankiziltug/logo-design-skill, pin no ORIGIN e MIT local; TRADEMARKS preservado e biblioteca de SVGs excluída da MIT, não incorporada; referências/caminhos testados |
| mkt-creative-brief | Mako brief; Pixel adaptação; Canvas direção | Open Design, pin e Apache local; Refero é referência externa não instalada; exemplos/QA e recuperação testados; não concede assets, render ou publicação |
| design-quality | Criador aplica critérios; Oath revisa visual independente | Anti-Slop 3.2.20/MIT, pin e licença local; validator puro e pointers testados; não instala MCP/scripts upstream |
| dev-team-methods | Handoff aceito, debug/review, crítica visual e reuso | Agency Agents/Superpowers/Taste/Ponytail, quatro pins e quatro MIT locais; módulos e referências testados; sem segundo controlador |
| mkt-research-pipeline | Mako pesquisa; Pixel social; Nex revops; Dex analytics/attribution; Oath evidência | MarketingSkills/Corey Haines, pin e MIT local; fixtures são especificação, não CRM executado |
| social-reels-editorial | Brief/prova/canal/roteiro no fluxo Pixel/Copilot | Pin e MIT Jake Schincariol local; conteúdo efetivamente montado no prompt do handler em mock; modelo/publicação não testados |

Todos os seis têm entrypoint, ORIGIN, hash/pin de origem, avisos de licença locais e links relativos resolvíveis; nenhum contém script candidato. Verificação é dos arquivos atribuídos já existentes, não consulta upstream atual nem parecer jurídico sobre todo asset. Avisos/limites foram preservados, sem copiar novas fontes externas ou executar instaladores. `NOTICE` e `NOTICE.md` preservam MIT de OMC para a camada herdada/cleaner; ORIGIN dos módulos novos registra suas fontes adicionais, não presumir que todo dev-* novo seja OMC. Licença de imagem/font/logo/asset precisa ser verificada separadamente antes de uso.

## 7. Fila atual e evidência de entrega

Fonte sanitizada: owner da fila, snapshot 16/10/2026 04:52 Bahia. Arquivos originais no PC: `/home/sistemabritto/Documents/Codex/2026-10-15/task-2/queue-review/evidence/fila-2026-10-16.md` e CSV homônimo (94 linhas). Nenhum dado foi relido da produção por esta tarefa. O owner continua responsável pela triagem/mudanças da fila.

| Dono | Blocked | Review | Idade dias | Sem movimento dias | Persona/heartbeat |
|---|---:|---:|---|---|---|
| Pixel | 63 | 0 | 2,0–78,9 | 0,1–72,2 | existe/ativo |
| Nex | 9 | 0 | 11,8–79,3 | 0,5–74,2 | existe/ativo |
| Mako | 5 | 0 | 26,1–34,4 | 9,1–33,0 | existe/ativo |
| Bolt | 3 | 0 | 19,8–34,4 | 3,7–26,3 | existe/ativo |
| Hawk | 2 | 0 | 31,8–34,0 | 26,1–26,3 | existe/ativo |
| Dex | 2 | 0 | 26,1–34,4 | 25,7–32,4 | existe/desabilitado |
| Compass | 1 | 0 | 122,1 | 101,3 | existe/desabilitado |
| Sem dono | 7 | 2 | 22,3–77,9 | 0,3–25,0 | não atribuir automaticamente |

Cinco blockers de Nex citam ausência de heartbeat, premissa hoje superada; conteúdo ainda depende de hipótese/janela/aprovação e não autoriza replay. Compass/Dex sem autopilot ativo não são falta de código ou skill. Pixel concentra publicação/campanha; dois itens encerrados pelo usuário permanecem protegidos. Acesso CRM403 e decisão de modelo de receita são bloqueios legítimos, sem contorno.

O owner verificou artefatos internos: plano off-page 7459 bytes, oferta anual 4779, copy 3831, WABA 3401, analytics 4528, spec CRM 2908, plano CTA 1687 e ZIP aula 42424. Existência/tamanho não provam aceite, upload, venda, deploy ou publicação. Dois Mako têm motivo técnico publish_targetNone sobre planos internos; somente o owner propõe revisão humana limitada para o off-page, sem worker, assignee ou resolved. Decisão de preço continua com Felipe.

Snapshot agregado anterior: 549 tickets, Pixel 449 (81,8%), Nex 18, Mako 14, Bolt 12, Dex cinco; não é produtividade recente. 22 media_jobs (14 failed, sete ready_for_review, um approved, zero postiz_post_id) justificam diagnóstico por etapa, não contratação automática. Nenhum motivo dos 14 foi obtido nesta revisão; publicação fora desses jobs não está excluída.

### Delta informado pelo owner após o snapshot

O owner concluiu uma única recuperação administrativa do plano off-page: blocked/Mako → review/assignee NULL, sem worker, outreach, modelo ou resolved. Totais posteriores informados: **91 blocked / três review; dez sem dono (sete blocked + três review)**. A matriz MD foi atualizada e o CSV preserva o snapshot anterior para rastreabilidade. Revisão humana de fontes/baseline/keywords permanece pendente; preço anual e CRM403 continuam bloqueados. Esta auditoria não executou essa transição e não redistribuiu tickets.

## 8. Correções aditivas entregues e preservação

1. Catálogo acrescenta `reference_documents`: distingue raiz de subdocumento, presença do arquivo e instrução de leitura. `knowledge`, o detector estrito e `operational_status=not_verified` continuam com semântica anterior. Symlink externo não conta como documento do workspace. Nenhuma nova permissão/execução é concedida.
2. Zen ganha pointer explícito do cleaner antes do corte de memória; mantém conteúdo anterior, frontmatter e responsabilidade. Não substitui revisor visual.
3. Auditor offline inventaria todos os entrypoints locais, candidatos a script, hints por nome, pointers limitados e seis proveniências, sem carregar providers ou executar skills.
4. Testes de comportamento cobrem subdocumento sem falsa raiz, corte de memória, duplicatas/arquivo ausente/symlink, montagem real de pointers e origem local dos seis módulos.

Sem mudanças em seletor Live, loaders, ACL, memórias, dados, ENV, OmniRoute, tasks, heartbeats, personas legadas além do parágrafo aditivo de Zen, licenças ou configurações. Só o integrador publica. Catálogo continua evidência local por resposta; não cacheia “operacional”.

## 9. Limites que podem mudar a proposta

Faltam provas operacionais por skill/provider: chamada de leitura efetiva ou tool trace sanitizado, dependências/binaries e fonte de dados no serviço correto, permissão/escopo, resultado e artefato aceito. Não solicitar geração paga só para preencher esta matriz. Faltam também motivo/etapa dos jobs de vídeo, URLs de entrega e demanda recente por domínio. Um fluxo de vídeo com volume sustentado pode justificar produtor dedicado; tracking recorrente pode justificar função especializada; filas pequenas podem continuar skills dos donos atuais.

Instalado e carregável foram verificados localmente. Execução de modelo, ferramentas externas, revisão visual real e resultado comercial continuam NÃO TESTADOS. A proposta de sete responsáveis é revisável e não autoriza mudanças no roster/fila.

## 10. Validação desta entrega

124 testes locais passaram em 2,14 s: catálogo, auditor funcional, design cookbook, métodos de equipe, Reels editorial, pesquisa marketing, logo e brief criativo. O teste de Reels captura prompt/schema no limite mockado e aborta antes de DB. O teste do catálogo mantém campos/locked e compara o corpo ao loader Python real. O auditor novo cobre memória/caminhos/symlink e preserva status não verificado. `git diff --check` sem erros. Não houve teste pago, publicação, inspeção visual ou demonstração de que um modelo decidiu ler a skill. Revisão independente do patch permanece para o integrador/faixa revisora; testes do autor não substituem essa revisão.


## 11. Revisão independente e integração

O integrador reproduziu os 124 testes originais e comparou byte a byte o JSON
do auditor offline à evidência entregue. Acrescentou regressões para frontmatter/
memória e symlink cíclico: o último agora conta como documento ausente, sem
falhar o catálogo. A CI inclui a suíte nova. Nenhum graph cache integra o lote.

A produção monta `.claude` em volume persistente: trocar só a imagem não aplica
o pointer de Zen. O rollout deve aplicar exclusivamente o parágrafo aditivo,
com hash/CAS, backup privado e rollback delimitado, preservando todos os bytes
anteriores/posteriores, frontmatter e memória. As outras personas não mudam.

O delta administrativo do off-page informado pelo owner não foi autorizado por
esta integração: contrariou a orientação de somente dry-run. O owner confirmou
suspensão, sem rollback ou novas mutações. O ticket ficou em revisão humana,
sem assignee, com gates preservados; o payload `would_recover` registrado é
imperfeito e o `resolved_at` antigo não comprova resolução atual. Esta publicação
não contém o script de recuperação nem altera a fila. Totais são snapshots
fornecidos pelo owner, não resultado de execução de skills.

Montagem de pointers e presença de documentos são as provas desta faixa.
Uso pelo modelo, ferramentas externas e causas das falhas de mídia continuam
pendentes; este lote não é revisão funcional completa do squad.
