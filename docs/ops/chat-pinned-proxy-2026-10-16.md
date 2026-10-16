# OpenCode 1.17.18 e proxy Flask WS: ensaio isolado

Continuação de bc0d3b2, autorizada pelo coordenador e alinhada com integrador. Não houve alteração do serviço ativo, push, instalação no host, troca de pin, grant ou inferência paga. O bootstrap de produção continua sem `ownedChatRead`.

## Origem dos artefatos e limites do ambiente

Inspeção por SSH `BatchMode=yes`, `StrictHostKeyChecking=yes`, `UpdateHostKeys=no`: contêiner `ad22a1d5194f`, imagem `excarplex/evo-nexus-dashboard@sha256:0d9722d2dba90b30f4a8019c119107051be6e84f7da548e3e14f03342a4ef93b`. Copiados por stdout somente exe público OpenCode e seis pacotes públicos Python com seus metadados/licenças. Nada de ENV, configurações, auth, cache ou sessões foi copiado.

OpenCode **1.17.18**, SHA256 **0cbfb6de55aa4ce3c74da12d8516376033693a88abca6238c5be32bf98130636**: exatamente o pin atestado pelo integrador. Arquivos locais em `/tmp/omni-opencode-1.17.18-proof`, fora do Git. O venv real da imagem, `/workspace/.venv`, já contém websocket-client1.9.2; sua ausência era apenas no venv local. Não foi necessário trocar a biblioteca do proxy ou instalar pacotes.

Pacotes de proxy copiados da imagem: websocket-client1.9.2, FlaskSock0.7.0, simple-websocket1.1.0, websockets16.0, wsproto1.3.2, h110.16. Frameworks locais e imagem coincidem em Flask3.1.3, Flask-login0.6.3, Werkzeug3.1.8 e Node ws8.20.0. Interpretadores têm patch diferente: imagem Python3.12.15/Node22.23.3; host Python3.12.3/Node22.23.2. Não se declara um clone completo da imagem ou teste do serviço ativo.

## Dois defeitos encontrados e menor correção

1. Com XDG privado e `--pure`, 1.17.18 ainda consultava `~/.opencode`. Em namespace sem acesso ao home padrão, falhava com `PermissionDenied: FileSystem.access(/root/.opencode)` antes de completar a leitura. O transporte agora cria HOME vazio/privado dentro do stage e o passa somente no env do subprocesso. Não muda HOME global nem qualquer perfil existente. O stage inteiro é removido ao terminar.
2. `websocket.create_connection(timeout=10)` também aplicava 10s ao recv posterior: fechava o proxy durante turno válido. Além disso, `simple_websocket.receive(timeout=30)` retorna None em espera ociosa, mas era tratado como desconexão. Mantemos 10s para conectar, desativamos apenas deadline de recv após handshake e mantemos a espera de30s como tick: None com connected=True continua; socket fechado termina. close() interrompe recv bloqueado. Cookie, Origin e frames binários/texto continuam no mesmo proxy/biblioteca.

## Prova executada

`tests/backend/test_pinned_chat_proxy.py` usa namespaces Linux de usuário/rede com somente lo e nenhuma rota de saída; o próprio teste verifica isso. FlaskSock real recebe WS real, proxy websocket-client real conecta ao TerminalServer real, e callback HTTP usa `_guard`/`_owned`/file ACL sobre bancos/arquivos temporários. GET do runtime também chega ao handler Node real. Não há grant injetado diretamente no transporte nem mock de cliente WS nesse ensaio. Sessão/cookie/contexto/fontes são fixtures; upstream é SSE falso em localhost. Isso não cria nem adota sessão pessoal real.

Sete casos passaram em57.75s: sucesso, usuário estrangeiro, Origin estrangeiro, path externo, fonte alterada durante execução, snapshot adulterado e no_tools. Sucesso executou read nativo da skill e referência, entregou marcador e receipt. Negativos não geraram receipt de sucesso; tenant/origin/no_tools fizeram zero requests de modelo. Schema efetivamente capturado tem somente read, SHA256 `77edfe40f049586e8a98748cef0a9ee8ad55ec3c9d37fc65a9cdf97c6a25363d`. Config ambiente permissiva/plugin sentinela não foram herdados. Há4requests no upstream falso no sucesso, incluindo request auxiliar sem tools; não é single-request.

Um oitavo ensaio introduziu31.000ms de silêncio no upstream falso: passou em42.55s, comprovando que os limites antigos de10/30s não encerram o turno. Não se reduziu o timeout de modelo do transporte. Prova sanitizada, hashes e versões: `chat-pinned-proxy-proof-2026-10-16.json`.

Adicionalmente:42 testes Node passaram, incluindo HOME isolado;4 Flask/relay passaram, incluindo espera ociosa, binário/texto e fechamento;2 E2E1.18 (sucesso/path) passaram após a alteração. Nenhuma prova1.18 foi usada como atestado1.17.

## Reproduzir sem instalação ou rede externa

Com os artefatos públicos já copiados para /tmp e dependências do projeto já disponíveis:

```sh
qa/capability-probe/run_pinned_proxy_proof.sh \
  /tmp/omni-opencode-1.17.18-proof \
  /home/sistemabritto/Documentos/evo-nexus/.venv/bin/python
```

O runner não baixa artefatos nem executa SSH; abre namespace novo, sobe somente lo e roda os sete testes. O teste confere hash do exe, websocket-client1.9.2 no diretório copiado e ausência de rota. Para repetir o caso longo, definir `PROOF_IDLE_DELAY_MS=31000` apenas na execução de teste. Isso torna os sete casos mais lentos; para reproduzir só sucesso, usar o comando pytest com `-k success` dentro do mesmo namespace, conforme histórico do ensaio.

## Aceite restante

As lacunas de CLI pin e proxy real têm agora evidência isolada com o binário correto; aguardam revisão/reexecução independente do integrador. Não é teste do upstream real, faturamento, serviços/MCP externos, single-request, TLS/reverse proxy externo ou de todas as superfícies legadas HTTP/PTY. Nenhuma ativação em produção é autorizada por este relatório. O integrador continua sendo o único responsável por integração/rollout após aceite.
