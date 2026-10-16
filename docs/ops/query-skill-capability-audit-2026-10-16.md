# Descoberta por query — auditoria e primeiro adaptador executável

Base7f2bb2a; checkout isolado query-skill-capabilities. Spec canônica: [end-to-end-capability-spec.md](end-to-end-capability-spec.md). Não altera providers, fila, grants, skills autorais, arquivos de credenciais ou config global. Sem Claude Code, inferência, deploy, instalação ou ativação de MCP nesta fatia. Leitura externa mínima GitHub autorizada é registrada separadamente abaixo.

## Primeiras quebras comprováveis no código

1. Catálogo/presença de docs não é tool runtime. `agent_catalog.py` declara operational_status=not_verified corretamente; `/api/skills` só lista/lê. Dockerfiles copiam skills, mas o volume/_defaults do runtime real precisa ser conferido, não inferido do checkout.
2. `terminal-server/src/claude-bridge.js:_ensureOpencodeProviderConfig` força build.tools.skill=false devido ao catálogo extenso. Pode haver Read/Bash por outro caminho, mas falta descoberta bounded que escolha o cookbook quando usuário não sabe o nome. Não removido esse limite global.
3. `chat-bridge.js` envia runtimes incompatíveis com Agent SDK (incluindo cli não suportada nessa ponte) a `_startOpenAICompatibleSession`, explicitamente sem CLI tools. Esse fallback não equivale a um agente tool-capable, mesmo que o provider responda texto. Não corrigido aqui: owner runtime deve decidir/atestar o caminho OpenCode/Codex sem trocar política/modelo silenciosamente.
4. `/api/mcp-servers` lê configuração de projeto/usuário Claude; não faz tools/list nem prova encaminhamento/auth/rede ao OpenCode/Codex/Live.12declarações de MCP no checkout; nenhum servidor ativado/testado por esta frente.

## Matriz por entrada — configuração estática ≠ sessão real

| Entrada | Instalado/configurado | Anunciado/permitido | Prova de chamada / lacuna |
|---|---|---|---|
| Harness provider_fallback CLI normal | CLI/modelo via configuração; filesystem depende do cwd/volume; OpenCode inline registra provider | Usa capacidades nativas da CLI, não catálogo universal/MCPs Claude automaticamente. Flags reais dependem invocação | Sem inferência nesta rodada; tools_list efetiva da sessão NÃO atestada |
| Chat via Agent SDK | allowedTools inclui Read/Write/Edit/Bash/Glob/Grep/Agent/Skill/WebSearch/WebFetch/NotebookEdit/ToolSearch | canUseTool/trust/ACL continuam necessários; lista nativa não comprova MCP remoto | Fonte estática; não executou consulta externa/modelo |
| Chat via fallback HTTP | Provider responde chat, mas ponte não fornece CLI tools | Não afirmar capacidade de execução; sem remover no_tools global | Quebra de modalidade comprovada no código; correção runtime separada |
| Terminal OpenCode | Bridge pode desabilitar skill nativo; root config e user config não provam sessão | Sem catálogo inteiro; novo seletor não está ainda conectado diretamente ao terminal | Binários OpenCode/Codex presentes localmente; nenhuma sessão chamada |
| Live browser | read_current_omni_session/search_omni_context + operações internas estreitas em managed-context-client/managed-session | Owned user/company/agent/conversation, origem HTTPS, permissões e flags. Sem MCP arbitrário | Nova consulta chama adaptador local real na fixture Flask; anúncio/uso pelo modelo remoto NÃO atestados |
| Live tarefas internas / piloto EDIT / fila | live_task_dispatch e internal_ticket_draft usam tool_policy=no_tools; executor e policy próprios | Proteção intencional: OpenCode --pure, tools deny, MCP/plugin/instructions vazios por processo | Preservado. Não deve receber ferramentas só para satisfazer um pedido que requer outra modalidade |
| Media-worker | Docker copia catálogo scoped; media_worker/opencode.json skill=true | Não herda catálogo completo do dashboard; composição isolada sem API/credencial de publicação | Não executado nesta fatia; não exigir design-quality global no worker |

Inspeção local sanitizada: OpenCode e Codex disponíveis no PATH; .mcp.json e config de usuário existem; config OpenCode de usuário tem0MCPs declarados,0plugins e skill de build não especificado. Isso não atesta a config final da sessão/contêiner. DASHBOARD_API_TOKEN e override EVONEXUS_API_URL NÃO estão no processo desta execução. Portanto não foi feita leitura de integração externa conectada pelo SDK: falta contexto autenticado disponível aqui, não prova de credencial ausente na VPS. Não abrir arquivos .env nem copiar tokens para contornar. Auth/ACL/rede externos e tools/list remoto permanecem NÃO TESTADOS.

## Correção local concreta, sem plugin no pedido

`skill_capability_dispatch.py` adiciona bindings server-owned estreitos:

- Query thumbnail/miniatura/capa de vídeo/blog → skill instalada mkt-creative-brief + ORIGIN/examples/qa reais, hashes e conteúdo sem alterar autoria. Não ativa rotina social-ai-trends-blog inteira por mera palavra thumbnail.
- Query explícita revisar marca/identidade/thumbnail → mkt-brand-review. Não gera review estético automático ou imagem.
- Chamada real ao adaptador `_query_files` existente, que usa live_file_sources.search sobre referências explicitamente vinculadas ao usuário/empresa, com ACL/hash atuais. Expansão fixa marca/identidade/brand, sem inventar paleta/logo. Ausência retorna needs_authorized_brand_reference.
- Integração em `_query_payload`: funciona no /query e no zero-argument read que já carrega queryResult; nenhum schema remoto novo/grant necessário. Sessão remota precisa efetivamente chamar a ferramenta existente; não provar isso com mock.
- tools_list no resultado descreve adaptador já usado pelo controlador através do query tool; NÃO anuncia uma nova ferramenta MCP callable pelo modelo. Campos model_read_status=not_attested/external_call_status=not_attempted preservam a distinção.
- Scope revalidado antes/depois; links fora do workspace, secrets e excesso de orçamento bloqueiam skill; nenhum command/import/URL vem do texto. Tool policy no_tools não lê nem chama adaptador.
- Receipts SQLite owned e idempotentes guardam hash/skill/adapter/contagem, sem query ou texto privado. Conteúdo é referência não confiável, não autorização. Limite de transporte bloqueia carregamento para o modelo sem truncar documento silenciosamente.

Não é descoberta universal de todos os plugins: bindings sem adaptador atestado continuam sem execução automática. Não altera o chat HTTP nem distribui tools externas aos providers. Isso é gap restante explícito, não motivo para liberar Bash/MCP globalmente.

## Provas e aceite

Testes novos usam skill real do checkout, adaptador de arquivos real, Flask/SQLite e arquivos temporários autorizados. Terminal/provider HTTP é simulado. Cobrem query sem nome de plugin, leitura/hash de cookbook, brandrefs, escopo empresa/conversa, revogação, no_tools, segredo/link/budget e receipt idempotente. Não há imagem gerada, chamada externa, modelo, QA estética ou publicação.

Regressões iniciais:42passaram;2falharam só por socket localhost bloqueado no sandbox. As2regressões HTTP passaram após permitir socketslocalhost e reutilizar node_modules já existente por symlink local, sem instalar pacotes. Novo conjunto tem11testes passando; suíte final combinada:45passaram, incluindoHTTPlocalhost, com18avisosSQLAlchemy existentes. CI inclui novo teste explicitamente. Demais skills/plugins mantêm seus próprios gates e não ganham autorização por aparecerem neste inventário.

## Leitura externa real separada

Cliente GitHub `gh` já conectado: GET /user retornou apenas `{authenticated:true}` via filtro, sem imprimir usuário/token/dados privados. É prova real de autenticação/rede desse cliente local nesta execução; NÃO prova passagem de tools ao modelo, sessão no contêiner, execução do novo dispatcher ou qualquer MCP. Não foi ativada ferramenta nova, escrito recurso remoto ou feita inferência. O SDKdashboard continua sem token neste processo; não extrapolar GitHub para outras integrações.
