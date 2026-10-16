# Seletor de squad no Live

Base produtiva 21e5b74. Consome catalog de GET /api/agents para nomes, funções e setores; os slugs autorizados de opções Live continuam determinando as escolhas. Metadados não adicionam agentes nem concedem ferramentas/permissões. Busca local ignora acentos e consulta nome/função/setor/slug. Seleção fora da busca permanece visível; seleção repetida não reconecta. Catálogo indisponível usa lista autorizada, dados legados quando existentes e recarga explícita sem apagar escolha. Agrupamento legado é fallback; fonte de catálogo prevalece para setor.

Controller, bindings, áudio, autenticação, empresa global, identidade e flags não foram alterados. Durante conversa, escolha/busca ficam bloqueadas. Troca de empresa preserva comportamento existente: encerra conversa antiga, desliga mic e exige novo clique para conectar. Não há promessa de memória consultada, ferramenta operacional ou execução por voz.

## Evidência

- PASS: 91 testes locais de seletor/catálogo/acesso/continuidade/tarefas/playback, com HTTP local e provider injetado.
- PASS: TypeScript/Vite build e ESLint dos três módulos alterados/novos.
- PASS: Chrome da build em 375×900 e 1440×900, reduced motion: 7 setores/42 agentes; metadado sem autorização/locked não acrescenta escolha; busca por métricas sem acento; seleção atual preservada fora da busca; escolha repetida sem requests de sessão; Tab até select; controles >=44px e sem overflow.
- PASS: SDK real com WebSocket 100% simulado: sessão ativa bloqueia seletor, troca global A→B encerra antiga sem reconexão automática; catálogo 503 usa fallback e recarga falhando/recuperando mantém slug escolhido. Nenhum mic ou provider real.
- PASS: capturas 375/1440 inspecionadas. Nos controles opacos habilitados: texto rgb(243,244,249) / fundo rgb(16,23,34), fonte 16px, contraste bruto 16.37347152216777. Isso não certifica contraste da página inteira.
- NÃO TESTADO: telefone físico/Safari/leitor de tela, mic/áudio humano ou respostas reais do modelo.

Reproduzir browser: servir frontend/dist com SPA fallback em 127.0.0.1:5199; QA_PLAYWRIGHT_MODULE aponta para Playwright já instalado, QA_OUTPUT_DIR define evidências; node qa/live-squad-selector/browser-qa.cjs. APIs e WebSocket são fixtures, não dados produtivos. CI cobre o contrato Node via test_live_squad_selector.py.

Publicar dashboard somente, backup/rollback image-only para 21e5b74. Preservar ENV/dados/sessões e demais serviços; não ativar tarefas/routing/alias. Verificar SHA OCI e chunk servido, catálogo pela autenticação existente e estados de tickets antes/depois. Teste autenticado de Live continua exigindo cookie pessoal; não fabricar sessão para provar UI em produção.
