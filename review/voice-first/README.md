# Live: apresentação montada localmente

Base `050a8b506b255fa69d61ae324d25be5b174839f4`, branch local `codex/live-voice-ux`, checkout isolado. Sem publicação ou deploy. O patch de `/providers` permanece separado.

## Implementação

`ManagedNexusLive.tsx` monta `VoiceFirstConversation.tsx`, seu CSS e `voice-first-bindings.ts`. Reserva de frontend confirmada pela coordenação. Bloco técnico de histórico, busca manual e logs duplicados saíram apenas da montagem: APIs e componentes antigos não foram apagados.

- Iniciar prepara a conexão, sem ativar mic. Falar/pausar permanece ação separada. Encerrar/cancelar usa o encerramento atual.
- Botões compactos: mínimo de 48 CSS px de altura e 44 CSS px de largura, início principal e encerramento secundário. Não usam o grupo genérico antigo.
- Transcrição recolhida por padrão. Feed principal só com resultados/andamento não retratados, texto copiável e fontes/links autorizados.
- Escrita usa o composer existente, em área opcional. Sem upload fictício: arquivos entram pelos links já suportados e por `safeWorkLink`.
- Erro de gravação preserva retry e gates de iniciar outra conexão. Não bloqueia o mic da conversa conectada.
- “Nova conversa” fica visível junto dos controles, na mesma empresa. Pede confirmação; com chamada ativa, encerra o áudio antes de `start(...,true)`. Gravação pendente, conexão em preparação ou escopo ativo incompatível bloqueiam a troca. “Retomar conversa” recupera a última conversa autorizada da empresa, usando o controlador atual.
- Link `/live` do Sidebar recebe só o rótulo “Live”; rota, ícone Radio, autorização e entrada única foram preservados.

Controlador, contratos de tools, persistência, ACLs, backend, voz remota, providers, RecordingsQueue e deploy não foram alterados. Recolher a transcrição não impede sua gravação. Clipboard só é solicitado por clique; falha oferece seleção manual.

## Validação executada

    node review/voice-first/render-tests.cjs
    node review/voice-first/integrated-flow-tests.cjs
    node qa/managed-live-context/session-tests.cjs
    node qa/managed-live-context/continuity-session-tests.cjs

O teste integrado carrega controlador, adaptador e componentes TS/TSX reais, faz SSR da página montada com contextos de teste e simula HTTP/provider/áudio/clipboard. Cobre início sem mic automático, falar/pausar, fim/cancelamento, retomada das falas salvas, nova conversa sem apagar a anterior, resultado com fonte/cópia e transcrição recolhida. Não prova SDK/provider real nem interação/medidas de navegador.

TypeScript focado em ManagedNexusLive, componente e adaptador passou, sem build completo. Os dois roteiros Playwright existentes tiveram seletores atualizados e verificação preparada dos controles entre 44 e 64 CSS px de altura; não executados.

## Limites e revisão

QA visual pendente: sandbox negou porta com `listen EPERM 127.0.0.1:5197` e Chrome com `setsockopt: Operation not permitted`. Não se ampliaram permissões nem se tentou contornar. Sem chamada paga, microfone real, CLI/harness ou imagem publicada. Integrador permanece único dono do rollout.

`preview.html` é uma prévia estática gerada do componente/CSS reais com estados sintéticos; não executa ações nem substitui QA visual. Problemas de geração de resultados ou recuperação de contexto continuam no contrato existente.

## Correção de nova conversa na mesma empresa

“Encerrar áudio” fecha a chamada e preserva os registros. Retomar é explícito e não muda o ID lógico existente. Nova conversa usa contexto novo e `newConversation:true`, sem troca de empresa ou exclusão de histórico. A seleção do agente é recuperada do estado da mesma empresa ao retornar à tela; o usuário não precisa reescolhê-lo após encerrar áudio.

O teste integrado também cobre nova conversa durante chamada ativa, bloqueio por gravação sem ACK, cancelamento durante conexão e ida/volta entre duas empresas sem falas cruzadas. HTTP, provider e áudio continuam simulados. O contrato oferece retomada da conversa mais recente; não foi criado um seletor de qualquer conversa antiga nem alterado backend/ACL.
