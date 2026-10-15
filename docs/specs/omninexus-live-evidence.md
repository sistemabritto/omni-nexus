<!-- Modified by Sistema Britto, 2026-10-15. -->
# OmniNexus Live: evidências e handoff documental

Recorte: 2026-10-15. Documentação baseada em `3a282bd` (PR78); produção reportada em `7e84d6b`. Esta mudança não executa provider, não lê credenciais, não publica imagem e não faz deploy. Relatos fornecidos na delegação estão identificados separadamente da inspeção de arquivos. Contagens de testes abaixo são evidência anterior, não testes repetidos nesta revisão documental.

## Matriz de entrega

| Recurso / revisão | Implementado | Testado | Produção | Pendente |
|---|---|---|---|---|
| Voz ElevenLabs / `7e84d6b` | Sim, no recorte informado | Conversa real testada pelo usuário (relato) | Sim, informado pelo usuário | Não confundir conversa com execução de tarefa |
| Leitura Live → sessão/tickets | Cliente `read_current_omni_session`; backend cria/consulta runtime e retorna tickets | Testes de contexto no candidato; não é teste de despacho | Presente no recorte reportado | Despachar comandos e devolver trabalho real |
| Persona/RAG/histórico automático no Live | Não no recorte de produção/candidato | Nenhuma prova completa apresentada | Não comprovado | Recuperação autorizada + injeção + continuidade UI |
| PR78 / `3a282bd` | Integra PR71/73/74/75 | 1183 passaram, 2 skip (relato de integração); documento da branch detalha 107 Python selecionados + TS/build/QA simulada | Não promovido neste trabalho | Publicação bloqueada aguardando aprovação específica |
| Continuidade / `feat/live-continuity-endpoints` | Branch separada `task-6/memory-bridge`; commits `cbd440e`, `8823faa` inspecionados | 15 testes com provider simulado (relato) | Não comprovado | UI em integração e prova real completa |
| PR72 Gravações / PR56 MediaRelease | Integração em andamento (relato) | Não revalidado aqui | Não inferir | Integração e aceite específicos |
| PR76 fila | Pronto segundo relato | 24 testes (relato) | Não inferir | Integração pelo responsável |
| Contrato agnóstico/pools/dispatcher | Spec proposto | Não implementado por esta mudança | Não | Fechar P0 no executor existente |
| Codex / Hermes | **EM BREVE**, integração não comprovada | Sem prova completa | Não comprovado | Adaptador + contrato + teste real |
| OpenCode / Cursor | OpenCode planejado; Cursor candidato | Sem prova completa | Não comprovado | Avaliar interface e certificar |

Configuração pessoal reportada: usuário ID 1, chave presente e aceite de custo (`cost=true`). Esses indicadores não revelam a chave, não comprovam gratuidade e não autorizam migração ou alteração dessa configuração. Não foram consultados ambiente, banco ou servidor nesta revisão.

## Fontes inspecionadas

- [Integração de voz/acesso](../ops/live-voice-access-integration.md): base `7e84d6b`, composição exata PR71/73/74/75, validação simulada e ausência de RAG/persona/dispatch.
- [Revisão integrada anterior](../ops/live-integrated-review.md) e [transporte Gemini](../ops/gemini-live-transport.md): histórico de gates e testes; não sobrepõem o relato atual de voz ElevenLabs funcionando.
- [Backend de contexto](../../dashboard/backend/routes/managed_live_context.py): cria sessão runtime via bridge, consulta metadata/tickets; não executa comando.
- [Cliente de contexto](../../dashboard/frontend/src/live/managed-context-client.ts) e [sessão gerenciada](../../dashboard/frontend/src/live/managed-session.ts): ferramenta de leitura suportada.
- [Bridge terminal](../../dashboard/terminal-server/README.md): interface de sessões/Claude CLI já existente; não certifica adaptador universal.
- Branch de continuidade inspecionada em worktree irmã: `dashboard/backend/routes/managed_live_context.py`, endpoints opt-in de continuidade e commits acima. Esse código não foi copiado para esta branch documental.
- [LICENSE](../../LICENSE), [NOTICE](../../NOTICE), [NOTICE.md](../../NOTICE.md), [TRADEMARKS.md](../../TRADEMARKS.md): preservados byte a byte. EvoNexus mantém Apache 2.0 com condições adicionais; nenhuma licença comercial foi concedida por este texto.

## Links e referências

| Link | Validação nesta revisão |
|---|---|
| https://sistemabritto.com.br | Oficial confirmado explicitamente pelo usuário; ferramenta web não conseguiu acessar (não declarar HTTP OK) |
| https://www.instagram.com/sistemabritto/ | Oficial confirmado explicitamente pelo usuário; fetch bloqueado por throttling |
| Outras redes Sistema Britto | Removidas da apresentação por ausência de verificação nesta revisão; nenhum perfil VoiceDream foi associado |
| Links relativos novos | Conferência local de existência dos arquivos; não equivale a validar rotas em produção |

Orca não foi adotado nem instalado; a referência opcional não acrescenta dependência. Qualquer afirmação sobre sua licença/maturidade precisa estar vinculada à revisão consultada antes de adoção.

## Entrega para integração

Branch `docs/omninexus-live-contract`, baseada em `3a282bd`, somente README e specs. O integrador exclusivo é a thread `01a13c9a-dd49-73a0-a0fc-87b82fb29016`. Integrar apenas os commits documentais, conforme base escolhida pelo integrador; não promover PR78 implicitamente ao integrar documentação. Não executar testes pesados/build/containers para esta mudança.

A conclusão funcional requer o gate real do [spec](omninexus-live.md), com provider e custos autorizados. Esta entrega torna esse gate verificável, sem afirmar que foi executado.
