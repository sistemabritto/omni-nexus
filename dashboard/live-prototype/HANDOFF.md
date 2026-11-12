# Gemini Live — protótipo isolado

Atualização: transporte Python real e gates opt-in estão descritos em `docs/ops/gemini-live-transport.md`. O restante deste documento registra o marco original do protótipo; a anomalia de formato abaixo não comprova invalidez da chave.

Branch: codex/gemini-live-prototype, base bea1ced. Não modifica App.tsx, Sidebar, backend app.py, terminal server, rename ou rollout.

## Resultado da credencial

Arquivo ~/.config/omninexus/gemini.env: modo 600, atribuição única GEMINI_API_KEY, sem BOM/CR/espaços internos; valor 53 caracteres, sem formato usual AIza + 35 caracteres. Isso é anomalia de formato, não prova de rejeição remota. Nenhum segredo impresso, copiado, enviado, carregado em browser ou instalado em secret persistente. Usuário deve abrir pessoalmente o arquivo em editor local e substituir somente o valor pela chave completa copiada do Google AI Studio. Não colar em chat. Manter nome GEMINI_API_KEY e permissão 600. Agente não altera esse arquivo.

## Contrato proposto ao backend e UI

Mensagem enviada aos tasks backend 01a13c9a-dd49-73a0-a0fc-87b82fb29016 e UI 01a13cf9-7313-701b-a85a-3da6556820cf. Resposta de concordância ainda pendente. Tentativa de aviso ao source 01a13c7e-f40a-70ac-b2b3-0fc157cc40e2 retornou thread not found.

GET /api/live/status: autenticação por cookie do dashboard, Cache-Control no-store, resposta {enabled:boolean,freeTierVerified:boolean}; sem chave/modelo arbitrário recebido do browser.
WSS /api/live/ws: mesma origem, cookie validado pelo backend antes do upgrade, allowlist estrita de Origin, rate/concurrency limit por usuário, limite de frame 32 KB. Nunca confiar em authenticated/freeTierVerified enviados pelo browser. O host calcula essas condições.

Client -> {audio:base64 PCM16LE mono 16000 Hz}.
Server -> {status:'ready'|'reconnect_required'}, {audio:base64 PCM16LE mono 24000 Hz}, {interrupted:true}, {transcript:string,role:'user'|'model'}, {error:enum}.

bridge.cjs é adaptador injetável; openProvider deve retornar WebSocket do pacote ws já existente no terminal-server, configurado somente pelo servidor. Não há endpoint registrado ainda, nem carregador de credencial, nem chamada real. Não passar URL/erro bruto a browser/logs. Host deve evitar logging de URL com key do provider. Model vem da configuração validada após confirmação de disponibilidade e plano gratuito. Nenhuma ferramenta foi declarada.

UI: componente src/live/LiveConversation.tsx; integração posterior da rota autenticada /live por lazy import, a cargo do task de shell global. Entrada isolada /live-prototype.html pode ser servida por Vite sem mudar shell. Build: em dashboard/frontend, vite build --config live.vite.config.ts --configLoader runner. dist-live é artefato gerado, não commitável.

## Documentação oficial consultada em 2026-10-15

https://ai.google.dev/gemini-api/docs/live-api : PCM 16 kHz entrada, 24 kHz saída, WebSocket e interrupções.
https://ai.google.dev/gemini-api/docs/live-api/get-started-websocket : setup, realtimeInput.audio, serverContent.
https://ai.google.dev/gemini-api/docs/pricing : lista gemini-3.8-live e gemini-3.1-flash-live-preview no free tier, além do native audio 2.5. Isso não comprova o plano da credencial local. Nenhum modelo escolhido automaticamente; sem fallback pago, billing ou aceite de gastos.

## Validação e limites

Seis testes mock bridge passaram: gates, setup PTBR sem tools, PCM/interrupção, entradas inválidas, erros redigidos, goAway/disconnect. TypeScript e ESLint dos novos arquivos passaram. Build Vite passou usando dependências existentes; nada instalado.

Browser QA não disponível: cua.listBrowsers retornou lista vazia; IAB indisponível. Interface não foi visualmente inspecionada. Sem conversa real, teste com microfone, áudio PTBR ouvido, endpoint de produção ou smoke autenticado no domínio atual. Captura usa ScriptProcessorNode de protótipo; migrar para AudioWorklet antes de rollout amplo. Navegadores sem AudioContext 16kHz mostram erro em vez de enviar taxa incorreta. Reconexão inicia nova conversa após clique e perde contexto; nenhum áudio/transcrição persiste. Teste limitado a 120 segundos.

Próximo QA quando backend liberar: cookie inválido/Origin inválido bloqueiam upgrade; status false não pede microfone; clique pede microfone; negar mic mostra erro inline; falar PTBR produz áudio inteligível; interromper cancela fila; encerrar desliga indicador mic; repetir start/stop e navegar não deixa tracks; goAway exige novo clique; nunca chave em DevTools/assets/logs; confirmar projeto free tier antes de sessão real. Smoke no domínio atual somente após rollout coordenado.
