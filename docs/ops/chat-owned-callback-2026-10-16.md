# Callback owned do Chat: entrega local

Incremento sobre 409bf75. Nenhum push, deploy, grant, credencial, pin ou sessão pessoal foi criado. `TerminalServer` só habilita o caminho com `options.ownedChatRead` fornecido pelo bootstrap de servidor, contendo backendBase fixo, publicOrigin fixo e binário/hash/schema revisados. Não há variável do browser ou configuração de produção que ligue essa opção. O bin/server.js permanece sem essa opção.

## Identidade e autoridade

O WS legado guardava apenas wsId e sessionId escolhido pelo browser. O proxy Flask autenticava o usuário, mas descartava o cookie no handshake interno. Agora encaminha cookie e Origin recebidos; Node guarda ambos somente em WeakMap da conexão viva, sem SessionStore/logs. Origin precisa ser exatamente o publicOrigin do bootstrap; o callback envia esse Origin recebido e Host público fixo ao Flask. HTTP nativo preserva Host (fetch local ignorava esse header). Não se inventa Origin a partir de JSON/browserfiles.

POST `/api/live/omni-context/runtime-read` reutiliza `_guard(write=True)`, identidade Flask-login, configuração pessoal existente, continuidade habilitada, permissão memory e `_owned`. API token compartilhado é rejeitado. sessionId é somente seletor: busca exige runtime_session_id + current_user; contexto deve existir, ter conversa vinculada, agente permitido e empresa ativa. GET do runtime confirma id/agente atuais (server.js agora inclui agentName nessa resposta). Sem query, só autoriza entrada na sessão. Com query, `dispatch_query` carrega skill/cookbooks instalados e `live_file_sources.search` lê apenas bindings existentes com ACL/digest atuais. Não chama `_persist_file_results` nem persist_receipt; não cria contexto/conversa/file grant.

O callback reconstrói o pacote nas três fronteiras de revalidação: antes de staging, antes do CLI e antes de entregar saída. Digest inclui principal, contexto/conversa, revisões/fontes e bytes dos documentos. Alteração/revogação descarta saída e recibo. Browser não fornece callback, identidade, documentos ou diretório autorizado; Symbol interno só existe no processo servidor. `no_tools` enviado pelo cliente só pode restringir a execução.

Na opção owned, join WS é autorizado antes de devolver histórico; querystring não libera history. Respostas vão somente ao iniciador, não a assinantes legados. Textos novos desse modo não entram em histórico/JSONL legado: ficam na resposta efêmera; receipt guarda hashes. A arquitetura legacy geral não foi convertida em ACL universal.

## Integridade e evidência

ReceiptRoot rejeita symlink, caminho canônico divergente, owner incorreto ou permissões para grupo/outros. EEXIST exige arquivo regular, owner/mode/nlink e tamanho corretos, O_NOFOLLOW e bytes idênticos; arquivo arbitrário/symlink não vira receipt confiável. Snapshot é conferido após resultado; nomes são Markdown e não podem ser AGENTS.md/CLAUDE.md/configs executáveis.

Prova: `tests/backend/test_owned_chat_read_callback.py`, `qa/capability-probe/server_owned_chat_e2e.cjs` e `chat-owned-callback-proof-2026-10-16.json`. O E2E instancia TerminalServer real com bootstrap opt-in, usa WS real/chat_send e callback HTTP Flask real com cookie assinado, DB temporário owned e ACL de arquivo real da fixture. Não injeta grant diretamente no transporte. Registro de runtime e autoridades pessoais são fixtures, não sessão real do Felipe; GET runtime nessa suíte usa o adaptador HTTP simulado existente. A regressão existente testa handlers HTTP reais separadamente.

Sete casos passaram: sucesso, outro usuário, Origin estrangeiro, path externo, fonte alterada durante execução, snapshot alterado e no_tools. Sucesso leu skill e referência com marcador; 4 requests no upstream falso (há request auxiliar sem tools). Todo request com ferramentas anuncia somente read; não é single-request. Usuário/origem estrangeiros e no_tools fizeram zero requests de modelo. Negativos não criaram receipt de sucesso. Ambiente de teste contém config permissiva e plugin sentinela; --pure + XDG separado + OPENCODE_CONFIG_CONTENT impediram carregamento efetivo do plugin. Prova combinada dessas proteções, não prova isolada de cada flag.

Validação adicional: 8 testes de transporte, 2 de servidor, 3 contratos e 16 fallback passaram (29 Node); 26 testes Flask/regressões/encaminhamento proxy e 7 E2E passaram (33 Python); 2 rechecks E2E de sucesso/no_tools confirmaram histórico/JSONL vazios. `websocket-client` está ausente no venv local: teste do proxy usa módulo fake e não comprova Flask WS real. Nenhum pacote foi instalado.

## Bloqueios para revisão do integrador

- Contêiner atestado pelo integrador usa OpenCode **1.17.18**, SHA256 `0cbfb6de55aa4ce3c74da12d8516376033693a88abca6238c5be32bf98130636`. Provas locais usam **1.18.18**, SHA256 `bb71f45b564f9234a97f54d6252a4a41d2f4388ae4b078918f691824cc3b3e54`. Binário global local inspecionado é 1.18.23/hash `de0724a36eaf3166e7f1ff38d0f4478b95ccc47725e9597b3fe66d3d3e18baa2`, também diferente. Compatibilidade do pin 1.17.18 não comprovada; não trocar pin nem ativar por esta fixture.
- Config do contêiner permissiva/plugins existentes não são grants; revisar isolamento no binário efetivo antes de conectar upstream real. reviewedSchemaSha256 permanece referência de prova revisada, não interceptação dinâmica no runtime.
- Atestar dependência e handshake do proxy Flask WS no contêiner, publicOrigin real e conectividade interna backend/terminal. Nenhuma requisição remota nesta entrega.
- Revisar superfícies legadas HTTP/PTY e política de logs antes de rollout geral. Este opt-in protege o caminho de consulta owned, não redefine autorização de toda a aplicação.
- Não houve Drael/Claude/Codex real, inferência paga ou mídia. O upstream é SSE fake localhost. Canário read-only real continua reservado ao integrador após revisão.

## Correção obrigatória após revisão independente de a0cc07b

Não usar a0cc07b isoladamente. A revisão demonstrou que mode=chat escolhia HTTP antes do transporte owned; active=anthropic/cli=openclaude também podiam chegar ao SDK legado. ChatBridge agora verifica o opt-in no topo: no_tools nega antes de carregar provider; somente active explícito não-anthropic, mode=code e cli=opencode compatíveis são admitidos, sem heurística/fallback. Divergência nos campos do provider selecionado também bloqueia. Configuração admitida é copiada por turno para não ser alterada durante awaits. Sem opt-in, contratos legados continuam operantes.

Rewind owned agora é explicitamente não suportado: rejeitado antes de ler JSONL, cortar histórico, limpar sdkSessionId ou escrever marcador. Cada turno é autorizado antes de mudar mode/active/history. SID original e bindingRevision da conexão são capturados; trocar de sessão (inclusive alias para o mesmo objeto) ou sair/voltar invalida o turno e impede entregar eventos antigos. Join ainda pode devolver cache legado depois de autorização; não se declara ausência universal de leituras/cache no servidor.

13 regressões novas passaram (8 roteamento + 5 turno), incluindo reprodução exata modechat+transportdummy+no_tools+HTTPstub e rewind após revogação. Teste de roteamento instrumenta apenas import SDK para contar e impedir inferência em caso de regressão. Negativos: zero HTTP/SDK/native/upstream, e no_tools também zero loadProviderConfig. Testes de turno verificam estado idêntico e zero log I/O/bridge antes de negar. 29 regressões Node anteriores também passaram: **42 Node**, sem inferência. Os **7 E2E** pelo bootstrap real foram repetidos após a correção e passaram (upstream falso localhost; não atestam 1.17.18/proxy Flask real). Nada habilitado em produção.


## Seleção de CI

`test_owned_chat_read_callback.py` está na seleção explícita de backend do CI: os quatro testes puros de guard/owned/ACL/relay rodam sem CLI. Os sete casos `real_server_bootstrap_ws_callback_cli` exigem `OMNI_LOCAL_CHAT_BOOTSTRAP_PROOF=1`; o step CI fixa essa variável em0. Para reprodução local desses casos, ativar somente na execução pytest com CLI disponível, nunca em produção. Os sete casos pin/proxy continuam com seu opt-in separado `OMNI_PINNED_PROXY_PROOF` e namespace exigido pelo runner; não entram implicitamente no CI.
