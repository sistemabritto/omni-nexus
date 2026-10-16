# Criação, vídeo e squad: decisão e efetividade — 16/10/2026

## 1. Resposta à pergunta sobre as referências

**As referências foram aproveitadas seletivamente, não integralmente instaladas.** Há um cookbook consistente e módulos locais de briefing, pesquisa/copy, direção visual, crítica, roteiro, edição e stickman. Isso ainda não prova um time que produz e revisa qualquer vídeo ponta a ponta. Não instalar todos os repositórios: vários são instruções, exemplos ou bibliotecas com licença própria, não ferramentas conectadas.

A revisão agora distingue: arquivo disponível → instrução recuperada pelo loader → prompt passado à tarefa → arquivo de saída → render real → inspeção independente da versão → aprovação humana → distribuição confirmada. Só avançar o estado que tem evidência. Em particular, JSON válido e teste com provider mockado não provam uso da skill pelo modelo nem qualidade visual.

Base desta frente: `a310ae1cd1d0aa9672d9d286b415bcd046bab23f`, que contém `4985996`. Worktree isolada `audit/creative-effectiveness`. Nenhum agente foi excluído/unido, ticket redistribuído, ACL/ENV/memória/OmniRoute alterado ou conteúdo publicado.

## 2. Proposta concreta do squad — quem entra, sai, fica e muda

**Entram competências nos agentes existentes; nenhum novo agente nesta etapa.** Pixel é dono da entrega criativa de vídeo até a publicação confirmada, com responsabilidade de cada etapa explícita. Não criar outro coordenador, diretor, editor e revisor genérico só porque uma tool falhou.

| Agente(s) preservado(s) | Decisão proposta, sem execução administrativa | Dono/entrega e limite |
|---|---|---|
| Mako | Fica; modifica contrato de entrega | Estratégia da campanha e brief versionado: oferta, público, objetivo, prova, CTA, formato; não duplica o calendário de Pixel |
| Sage, Nova | Ficam sob demanda; unificar planejamento de negócio no brief de Mako | Estratégia/produto em decisões reais; um brief canônico, não três planos concorrentes |
| Pixel | Fica e ganha competência explícita de handoff audiovisual | Roteiro, seleção editorial, B-roll com origem/direitos, repurpose, legenda/copy e pacote final; acompanha bloqueio até resultado, sem inventar prova de publicação |
| Reels Copilot | Fica especializado; sai da rota padrão de edição de bruto | Um roteiro no schema próprio, quando fluxo vigente autoriza; não editor/renderizador nem gatilho para campanhas encerradas |
| Canvas | Fica e amplia direção para motion/stickman/VSL no escopo | Quadro, hierarquia, identidade, cenas, ritmo/transições e continuidade visual; não promete renderer/modelo conectado por possuir storyboard |
| Bolt, Hawk, Trail, Flow, Quill, Scout, Scroll, Apex | Ficam especialistas; unificar implementação sob dono Bolt | Bolt implementa motor/integração; demais investigação/Git/docs/arquitetura proporcionais ao problema. Não criar sequência obrigatória de oito handoffs |
| Zen | Fica; sai da definição de revisor estético | Limpa código sem mudar comportamento; não certifica peça audiovisual nem substitui Oath |
| Oath | Fica e amplia revisão independente audiovisual | Inspeção da versão renderizada com Anti-Slop/Taste locais, observação/evidência e achados antes da aprovação humana; nunca autoaprova criação própria |
| Probe, Grid, Lens, Vault, Raven | Ficam sob demanda; unificar veredito final em Oath | Probe verifica reprodução técnica/áudio; Grid testes; Lens código; Vault segurança; Raven plano/risco. Seus critérios não são idênticos, mas não precisam todos operar em cada peça |
| Dex, Prism | Ficam; modificar entrega de medição | Dex reconcilia fontes/coortes/atribuição, Prism estatística quando necessária. Nenhum deles é “ausente” por heartbeat desabilitado |
| Nex, Zara, Pulse | Ficam; separar comercial, suporte e comunidade | Nex próxima ação comercial; Zara suporte/CS; Pulse comunidade. Compartilhar evidência/handoff, não fundir históricos/consentimentos |
| Clawdia, Atlas, Helm, Mirror | Ficam; unificar responsabilidade externa da fila em Clawdia | Atlas projeto, Helm ciclo técnico, Mirror retrospectiva. Um dono por handoff até aceite; sem controlador concorrente |
| Project-planner, Goal-suggester, Goal-planner, Compass, Echo | Ficam; saem da seleção manual obrigatória de tarefas simples | Planners preservam eventos/cascata; Compass plano técnico proporcional; Echo requisitos ambíguos. Não desligar automações ou confundir decomposição rejeitada com erro de agente |
| Oracle | Fica para descoberta/ativação; sai do fluxo rotineiro depois do onboarding | Não tratá-lo como novo buscador ou produtor pelo label Knowledge |
| Flux, Aria, Lex, Kai, Mentor, Lumen | Ficam sob demanda em seus domínios | Volume observado não sustenta exclusão; preservar finanças, pessoas, jurídico, pessoal isolado, cursos e aprendizagem |

“Sai” acima significa proposta de retirar uma etapa da rotina obrigatória, não apagar/ocultar o agente no sistema. Nenhuma dessas mudanças administrativas foi aplicada. Cada slug, sessão, memória e ticket continua preservado.

## 3. Linha de produção e dono de cada entrega

| Etapa | Responsável | Critério de aceite |
|---|---|---|
| Estratégia/brief | Mako, consultando Sage/Nova quando preciso | Brief único com prova/hipótese, marca/fonte/versão e próximo passo |
| Roteiro/seleção de longo | Pixel; Copilot só no contrato próprio | História autônoma e timecodes/transcrição reais quando existentes, sem alegar seleção semântica automática por trim |
| Direção e B-roll | Canvas especifica visual; Pixel responde pela origem/direitos da seleção | Storyboard/beat sheet, fonte autorizada por asset; licença de código não autoriza mídia |
| Motion/VSL/mini-VSL | Canvas dirige; executor existente implementa | Cenas de motion sem footage obrigatória, duração/ritmo/narração planejados separados de tempo medido |
| Stickman | Canvas dirige, Pixel mantém narrativa | Personagem/voz/continuidade e prompts conforme etapa aprovada; skill não é API/renderer |
| Edição enriquecida/cortes | Pixel editorial; Bolt/motor implementa; Probe mede | Render versionado, mapa temporal quando aplicável, sem cortar palavras ou mudar sentido; QA técnico não basta para estética |
| Revisão criativa | Oath independente; Probe fornece observações técnicas | Render/hash/versão atual, identidade, legibilidade, composição, ritmo, transições, legendas e áudio observados; limitações explícitas |
| Aprovação | Felipe, sessão humana existente | Decisão sobre a versão e destinos/copy/calendário reais; não herdada do beat sheet ou de outro hash |
| Publicação | Pixel acompanha; adapter Postiz existente executa | Gate autorizado, ID/estado/URL confirmados; sem “publicado” por existir arquivo ou sucesso de heartbeat |
| Métricas | Dex, input comercial de Nex | Janela/coorte/denominador e reconciliação; atenção não é receita causal |

A frente de vídeo é dona dos motores/hooks/versões/MediaRelease. Esta frente fornece skills, contexto verificável e contrato puro de revisão. Não há renderer duplicado.

## 4. Modos combináveis e o que existe de fato

Entradas solicitadas: cortes de longo, edição enriquecida de cortes/brutos, faceless sem footage e stickman; VSL/mini-VSL inteiramente em motion é modalidade explícita. Elas podem coexistir num projeto, mantendo ordem das cenas, roteiro, assets autorizados, versão e QA comuns. Na base auditada, o planner editorial ainda oferece só `personal_footage`/`faceless_montage`; não anunciar suporte nativo aos novos IDs por atualizar a skill.

O owner de vídeo está implementando `production_spec` com `entry_modes` e cenas footage/image/motion/stickman sobre os executores existentes. Schema/endpoint/render dos novos modos só devem ser anunciados após o commit e a prova do owner. A skill de instrução não converte automaticamente o planner de dois modos em motor de cinco entradas.

| Capacidade | Evidência existente | Estado honesto |
|---|---|---|
| Brief/pesquisa/direção/revisão | Skills locais, licenças/pins, pointers recuperados pelo loader | Disponível/carregável; decisão criativa pelo modelo não testada nesta frente |
| Roteiro in-process | Reels injeta social-reels-editorial no prompt, teste captura schema | Prompt montado em mock; não reabrimos campanhas nem geramos roteiro real |
| Contexto de composição | Scoped catalog linkado ao job; novo preflight verifica os dois entrypoints e hashes | Executável/testado localmente sem modelo; uso pelo modelo continua not_verified |
| Corte/trim/versões existentes | Código e testes legados/integração do owner | Capacidade distinta de enriquecimento visual; esta frente não repete render sintético nem ouve áudio |
| Faceless/stickman/motion VSL combinados | Direção textual e trabalho de motor do owner | Não declarar vídeo produzido a partir do cookbook; prova audiovisual depende do commit/render correspondente |
| Revisão audiovisual independente | Novo validator puro e orientação Oath | Estrutura/hash/versão testados; hook/auth/persistência é do owner, e observação real continua necessária |
| Publicação/medição externa | Gates/adapters existentes | Não executados nesta revisão; status não é promovido por testes locais |

## 5. Referências: o que foi aproveitado e o que não foi incorporado

| Referência | Aproveitamento local | Licença/evidência e limite |
|---|---|---|
| Open Design | mkt-creative-brief: brief/craft/QA e limites de marca | ORIGIN pin7abd6fc… e Apache-2.0 local. Refero e outros pacotes citados ali são referências externas, não apps instalados |
| Logo Design | Canvas: descoberta, conceitos e guidelines no escopo | Pin0ecf52e…/MIT; TRADEMARKS local exclui biblioteca de SVGs da MIT; biblioteca não copiada |
| Anti-Slop | design-quality: filtro subordinado à marca, contraste corrigido, revisão independente | Pinb1cdf87…/MIT local. Checker/MCP upstream não instalado; não certificar vídeo por cálculo de UI |
| Taste | design-critique: inventário/claims, crítica localizada e reteste | Pinf624f37…/MIT local; não biblioteca de assets, regras de gosto universais ou inspector instalado |
| Agency Agents | dev-team-methods: handoff aceito, hipóteses e papéis reaproveitados | Pin652b269…/MIT local. Nenhum roster inteiro, metas fictícias ou segundo controlador importado |
| Superpowers/Ponytail | Debug/verify, reuse-first e dívida explícita | Pins/avisos MIT locais; métodos não disparam processos/subagentes por si |
| MarketingSkills | Mako pesquisa/copy; Nex revops; Dex analytics/attribution | ORIGIN/pin/MIT local; CLIs e integrações de terceiros não incorporados |
| Método Reels Jake Schincariol | Método editorial PT-BR no Copilot/Pixel | Pind03c56b…/MIT local; sem promessa viral/hookscore, geração ou publicação |
| Stickman Director | Direção/storyboard/continuidade/prompt | Pin8fd806a…/MIT local; sem presets, API/voz ou resultado 4K comprovados |
| HyperFrames | Catálogo scoped, composição e worker existentes | Lockfile pin0.7.64 informa Apache-2.0. Instalado/carregável/runtime do serviço são verificações separadas; não atualizar CLI ou skills globais nesta auditoria |
| get-brolls, awesome-opus, motion/tiktok/b-roll packs | Ideias seletivas no sources.md: planejar→revisar→coletar, captions/overlap/facebox e vocabulário visual | Fonte é análise recebida documentada, não nova inspeção upstream; código/packs/assets não instalados. Facebox não é tracking; licença do motor/Remotion separada |
| SeeCut | Não incorporado | Curadoria recebida indica Noncommercial; sem código, assets ou nova conclusão de licença |
| PDF Let Claude Edit Your Videos | Síntese recebida de beat sheet, rough cut, timecodes, preview e áudio | O PDF não foi materializado/lido por esta frente. Não afirmar aproveitamento integral nem reprodução das páginas |

Avisos completos estão nos ORIGIN/LICENSE dos módulos já existentes e em video-editorial-pipeline/references/sources.md. Não copiamos novas fontes upstream. Marca, footage, fontes, música, memes e logos de terceiros exigem direitos próprios; licença de repo não cobre automaticamente esses assets. Não usar atualizador HOME-scoped de HyperFrames como auditor: pode modificar skills globais, e não foi executado.

## 6. Falhas técnicas corrigidas nesta entrega

1. **Skill disponível não era pré-condição da chamada paga.** media_workspace linka o catálogo best-effort; media_executor seguia mesmo sem os arquivos no cwd. Novo preflight lê só social-media-production e HyperFrames locais, com limite e UTF-8, registra hashes e falha antes do provider quando faltam. Erro de configuração é terminal para retry, sem loop. O prompt agora aponta caminhos completos; não presume leitura/aplicação pelo modelo. Routing/cwd/timeout/contrato de saída foram preservados.
2. **Orientação de Pixel perdida no corte de memória.** A descoberta editorial existente após o marcador de memória não chegava pelo loader Python. Novo handoff com paths completos foi inserido antes do corte, sem apagar conteúdo anterior. Canvas/Oath recebem referência específica de revisão audiovisual. Mako e Zen preservam suas competências/pointers já válidos.
3. **Nomes de filtros não são prova de QA.** Validator `media_creative_review.py` exige versão/hash, duração, fonte da marca, aplicação dos métodos e sete critérios com evidência local/hash/tempo e achados. FAIL/NOT_TESTED e P0/P1 abertos não habilitam aprovação; N/A precisa de motivo, identidade exige PASS. Nenhum reviewer/approved do cliente é aceito. O parser não vê/ouve o vídeo nem autentica o revisor: owner deve verificar refs/digests/duração, identidade/independência, CAS e persistência antes do gate humano.

Contrato detalhado em [creative-review-contract.md](creative-review-contract.md); fixture é sintética e não prova revisão real. O novo video-review.md aplica conteúdo real dos métodos locais a marca/legibilidade/composição/ritmo/transição/captions/áudio sem importar scripts ou impor gosto estético.

## 7. Carga atual — evidência para decidir, não para reexecutar

Owner da fila forneceu snapshot somente leitura **16/10/2026 06:26:53 Bahia**: **91 blocked / três review / 411 resolved / 44 closed**. Pendências não tiveram updated_at posterior ao snapshot05:45:29. Não reutilizamos os números de setembro como “carga atual”.

| Dono | Blocked | Review | Idade blocked (dias) | Sem movimento blocked (dias) |
|---|---:|---:|---|---|
| Pixel | 63 | 0 | 2,0–79,0 | 0,2–72,3 |
| Nex | 9 | 0 | 11,9–79,4 | 0,6–74,3 |
| Mako | 4 | 0 | 26,2–34,5 | 9,2–33,1 |
| Bolt | 3 | 0 | 19,8–34,5 | 3,8–26,4 |
| Hawk | 2 | 0 | 31,9–34,0 | 26,2–26,4 |
| Dex | 2 | 0 | 26,2–34,4 | 25,8–32,4 |
| Compass | 1 | 0 | 122,2 | 101,4 |
| Sem dono | 7 | 3 | 22,3–78,0 | 0–25,1 |

Sem dono review: idade22,7–55,8 e idle0,1–22,1dias. Pixel tem21 motivos NULL+40sweep+1agent_blocked+1review_exhausted; Nex7NULL+1sweep+1agent_blocked; Mako3NULL+1agent_blocked. Esses campos são procedência de bloqueio, não diagnóstico causal completo. Cinco motivos de Nex “sem heartbeat” são historicamente obsoletos, sem comprovar execução atual. Dex/Compass existem, com autopilots desabilitados; não criar substitutos.

Plano off-page5de37020 continua review/NULL desde04:57:04, sem execução/conclusão. CRM403/modelo de receita e campanha/rascunho encerrados permanecem protegidos. Código do site existe no PC, checkout equivalente ausente do dashboard, e GoalsBolt9/11/12 tiveram decomposição rejeitada: não tratar isso como ausência de skill nem autorização de replay.

Esta carga sustenta melhorar continuidade e ambiente, não demitir/criar agentes pelo nome. Papéis propostos de QA/criação não alteram nenhum assignee. Fonte detalhada rastreável é a matriz sanitizada do owner, sem novo acesso a DB nesta frente.

## 8. Migração reversível proposta, sem execução automática

1. Revisar com Felipe a matriz de dono/entrega e registrar a decisão, mantendo todos os slugs/ACL/sessões/memórias/tickets. Usar nomes funcionais na apresentação; não ocultar agentes como parte desta entrega.
2. Integrador revisa os commits técnicos e incorpora os hooks do owner de vídeo numa única base. Fazer piloto determinístico interno e comprovar versão/render/revisão; não consumir modelo pago só para provar a coluna de skill.
3. Para novos projetos, registrar brief e asset versionados e escolher entradas combináveis. Handoffs preservam autor, responsável e aceite. Tickets legados não são redistribuídos/reabertos por migração; aplicar critérios explícitos e escopo vigente item a item com owner da fila.
4. Operar um único brief/calendário e um único veredito criativo independente. Especialistas só entram quando o critério exige; não encadear todos por padrão. Publicação continua no gate humano existente.
5. Rollback técnico reverte commits/hooks da nova modalidade sem apagar registros de review/versão, invalidar hashes antigos ou restaurar aprovações obsoletas. Rollback de organização devolve apresentação/roteamento propostos, sem perder histórico, aliases ou ownership registrado. Só revisar saída definitiva de algum agente após janela de demanda e resultados observados.

## 9. Verificação e bloqueios

**204 testes locais passaram em17,25s**, incluindo loaders de Mako/Pixel/Canvas/Oath/Zen, catálogo/skill references/licenças locais, prompt de Reels, preflight real do scaffold com provider mock, output ausente, retry, stack/gates existentes e contrato de review.23avisos legados Query.get. Os testes não invocam modelos nem observam um render real; “aplicação criativa da skill” continua não verificada por eles. Fixtures estão rotuladas, sem falso áudio/vídeo aprovado.

Falta: commit/hook integrado do owner para os modos combinados e persistência/QA/MediaRelease, renderer na versão real de serviço, observação independente efetiva da versão produzida e decisão humana sobre a proposta administrativa do squad. Evidências do motor/render que o owner fornecer devem ser ligadas ao seu commit/versão; não promover instrução a ferramenta conectada ou render comprovado antes disso. Integrador único publica. Sem alteração em busca/ACL/ENV/memória/OmniRoute nesta frente.
