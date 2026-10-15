# Revisão OmniNexus

Branch `codex/omninexus-ui`, base `bea1ced`. Worktree isolada. Nenhuma alteração de backend, produção ou deploy.

Rotas: `/` e `/omninexus` central; painel anterior preservado em `/overview`. Auth e onboarding originais preservados. Prévia local de build: `http://127.0.0.1:5187/` (precisa das APIs autenticadas para uso real).

## Contratos existentes reutilizados

- Dashboard: GET /api/agents, /api/orchestration-jobs, /api/memory e /api/memory/<path>.
- Terminal: GET /api/sessions/by-agent/<agent>; POST /api/sessions/create `{agentName}`; PATCH /api/sessions/<id> `{archived:true}`.
- Chat: componente AgentChat e protocolo WebSocket existentes; sem mudança de contrato. Novo prop opcional `voiceEnabled=false` na central desabilita captura/transcrição. Demais consumidores mantêm comportamento anterior.
- Encerrar significa arquivar, não cancelar execução. Sessões marcadas ativas impedem esse botão; jobs em andamento permanecem administráveis na tela existente. Sessões arquivadas direcionam ao agente para leitura/restauração.
- Aprovações indicam somente as solicitações recebidas pelo chat aberto. Não é um contador global.

## QA reproduzível

`qa.cjs` intercepta TODAS as URLs `/api/` no navegador, usa identidade/dados de teste locais e nunca executa agentes. Não é modo demo do produto. Usa Playwright já instalado em `/tmp/zapmagico-mcp-checks/node_modules/playwright` e Chrome disponível. Ajustar caminho se executar noutro ambiente.

`results.json` e screenshots documentam os casos realizados. Capturas têm dados de teste e não comprovam conectividade real de produção. Live backend / streaming / approval resolution continuam dependentes da integração com o executor de backend; nenhum contrato foi alterado aqui.

Limitações conhecidas: configuração DEV existente usa APIs cross-port enquanto a CSP restringe self; QA usa build de produção em localhost com APIs interceptadas. Não se alterou essa configuração em paralelo ao executor de backend. Fontes web não foram incorporadas; fallback de sistema no preview offline. Aviso Vite sobre chunk existente >500kB permanece.

## Resultado verificado

- `npm run build` passou (TypeScript + Vite); somente aviso de chunk existente acima de 500kB.
- ESLint da página nova passou; `git diff --check` passou.
- Desktop/tablet/mobile e landscape: capturas e métricas em `results.json`; sem overflow horizontal, sem pageerror, botões da central >=44px, falha de criação explícita e fonte de memória abrindo.
- `session-results.json`: retomar, arquivar, criar sessão, troca de agente limpa sessão anterior, voz desativada. WebSocket bloqueado no teste para não acionar execução real.
- `contrast.json`: contraste calculado dos principais pares de texto/fundo entre 12.5:1 e 17.92:1. Não substitui auditoria integral WCAG nem teste com leitor de tela.
- Movimento reduzido ativado nas capturas. Tema claro, texto ampliado do sistema e leitor de tela não foram validados nesta entrega.
- `graphify update .` concluído sem LLM/API; saída gerada preservada em `/tmp/omninexus-graphify-update.patch`, fora do commit de UI para evitar ruído. Aviso de parser SQL opcional ausente; não foi instalado.

Mobile primeiro: o seletor e a ação nova sessão permanecem acessíveis; histórico/voz são recolhidos por padrão em 375px e possuem botão explícito de expansão. Link “Ir à conversa” reduz a distância ao chat. Desktop expõe as ferramentas continuamente. Teste mobile verifica expansão e recolhimento. Nenhum bot ou webhook Telegram foi desligado. Uma migração futura deve reconciliar sessões, jobs e aprovações pendentes antes da troca de canal.

Links antigos `/?tab=...` redirecionam para `/overview` preservando toda a query string; o painel anterior continua acessível. Novos textos da central estão em pt-BR nesta primeira entrega; as páginas existentes conservam i18n.

A prévia Vite de build serve os assets, não fornece backend nem proxy autenticado. As capturas/testes locais usam interceptação explícita de API. Revisão funcional contra serviços reais exige integração coordenada com o executor de backend; esta entrega não a simula nem muda configuração de produção.
