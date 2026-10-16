# Chat OpenCode: transporte isolado para revisão

Adaptador opt-in `OpenCodeReadTransport` usa o protocolo existente `--pure run --format json`. `ChatBridge` aceita a instância apenas no construtor do servidor; `server.js` não a instancia. Sem callback interno `resolveReadContext`, o caminho code continua bloqueado. sessionId/cwd/files enviados pelo browser não concedem acesso.

O callback deve derivar sessão owned, usuário, empresa, agente, revisão e documentos pela admissão existente. Deve revalidar ACL/revisão/hash em `verify` antes do snapshot, antes de invocar e antes de entregar resultado. Esta implementação consome esse contrato; a prova usa admissão fictícia. Nenhum grant novo ou wiring de produção foi criado.

Snapshot temporário com até oito documentos/64k, nomes sem diretórios, hashes conferidos e filtro de segredos. Configuração e estado XDG separados do diretório de documentos. Permissão deny por padrão; apenas nomes exatos do snapshot são permitidos a read. O OpenCode pede leitura por caminho relativo ao worktree; portanto a whitelist também aceita o sufixo exclusivo do diretório aleatório e nome exato. Não se amplia para read allow global. Processo sem auto, MCP/plugins/instruções globais, writes ou shell. Saída fica retida até revalidação; erro, cancelamento ou revogação não fazem fallback/replay. Receipt registra hashes e identidade interna, sem texto ou chave.

Prova reproduzível: `node qa/capability-probe/chat_transport_e2e.cjs`. OpenCode instalado 1.18.18, hash `bb71f45b564f9234a97f54d6252a4a41d2f4388ae4b078918f691824cc3b3e54`, upstream falso em localhost, credencial fictícia. Selector Python carregou mkt-creative-brief e cookbook instalados; ChatBridge invocou CLI real; ferramenta read nativa leu skill.md e brand.md; marcador chegou ao request seguinte e ao texto final com receipt. Schemas capturados anunciam somente read. Prova sanitizada em `chat-opencode-read-proof-2026-10-16.json`. Não é upstream real, modelo Drael, ACL real, single-request nem no_tools funcional. Não houve inferência paga. Nenhum Codex/Claude foi ativado.

O `reviewedSchemaSha256` do receipt referencia prova revisada anterior; não é interceptação do schema desta execução. O probe registra separadamente o hash dos schemas efetivamente capturados. Schema dinâmico deve ser reatestado pelo owner antes do rollout. Não alteramos o pin OpenCode 1.17.18 do execution_runtime.py.

Validação: 6 testes novos de transporte + 3 contratos Chat + 16 regressões fallback passaram. Testes com subprocessos requerem execução local fora da limitação do sandbox desta tarefa; não requerem rede externa. Prova E2E usa apenas listener loopback. `PROBE_OUTSIDE=1 node qa/capability-probe/chat_transport_e2e.cjs` também passou: read nativo negou arquivo sintético fora do snapshot, sem receipt de sucesso.

## Checklist do canário real, pelo integrador

- Revisar wiring server-owned e admissão usuário/empresa/agente sem aceitar autoridade do browser.
- Atestar versão/hash/binário e schemas no contêiner; comparar ferramentas anunciadas com read permitido e nenhuma API externa.
- Derivar snapshot exclusivamente de skill/cookbooks instalados e arquivo explicitamente autorizado; revalidar revisão/hash/ACL nas três fronteiras.
- Testar empresa estrangeira, caminho fora do snapshot, revogação durante execução, cancelamento e no_tools antes de modelo. Verificar que não há read externo nem replay.
- Fazer uma consulta read-only com conteúdo autorizado, conferir resultado nativo, receipt e resposta humana. Não converter fixture em prova real.
- Medir requests e retenção de logs; não alegar single-request. Não publicar mídia nem alterar grants/defaults/credenciais.

Limite remanescente: callback real e sua revisão de segurança, negativos adicionais (revogação/cancelamento) no CLI real e atestado do contêiner/upstream. Este incremento permanece local, sem deploy ou push.
