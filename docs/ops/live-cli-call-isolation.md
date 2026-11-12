# Isolamento por chamada Live

Referência preservada:94e7388e681974ea28cd51fd3da276033227a946 (PR85, CI38782733946verde). Novo delta só afeta tool_policy=no_tools; fluxo geral provider/router, configuração global e produção permanecem intactos.

OpenCode é o único adaptador habilitado nesse modo: Claude/OpenClaude falham fechado. Exige provider/model e endpoint+chave explícitos da tentativa selecionada; não usa login nativo nem credenciais herdadas. Invoca --pure sem --auto, em cwd/HOME/XDG temporários0700 com configuração explícita vazia+inline somente do provider escolhido. Não herda proxies, NODE_OPTIONS, configs/plugins/MCP/skills, outras chaves ou stores de auth. Após retorno/timeout/erro o estado privado é removido.

## Achado de runtime e recusa

Na versão1.17.18, rastreamento openat mostrou que o bootstrap lê /tmp/opencode.json apesar de OPENCODE_DISABLE_PROJECT_CONFIG=true e do config resolvido com plugin=[]. Um plugin-canário foi importado no ensaio antigo. --pure sozinho não basta. O delta recusa antes do processo quando encontra /etc/opencode ou opencode.json/opencode.jsonc/.opencode/AGENTS.md/CLAUDE.md/CONTEXT.md em ancestrais externos do diretório privado. Nunca apaga, altera ou sobrescreve esses arquivos para continuar. Não usa override de config gerenciada para contornar política administrativa.

Prova runtime:qa/live-cli-isolation/runtime.py. Requer namespace privado com /etc vazio e sem diretórios pessoais; o script aborta fora desse ambiente. Somente o executável188MB, o módulo provider_fallback.py desta revisão e fixtures sintéticos são montados em /work. Exemplo de montagem/documentação em qa/live-cli-isolation/README.md. O binário não está no Git.

O ensaio compara mesmo OpenCode1.17.18/SHA2560cbfb6de55aa4ce3c74da12d8516376033693a88abca6238c5be32bf98130636 da VPS, contra SSE em127.0.0.1. Config gerenciada/ancestral recusada antes de qualquer processo/modelo; fora dessas colisões, config/home/project hostis permanecem intactos, plugins/MCP-canário não iniciam, marcadores de instruções/credenciais externas não chegam ao provider, somente a chave sintética selecionada é usada, nenhuma ferramenta é anunciada, bash injetado é negado e temporários desaparecem.

O dispatcher recebeu também correção restrita de saída: parseia texto NDJSON em vez de devolver envelope bruto ao chat. Não muda output legado.

## Limites

Não é sandbox de OS do produto nem prova contra alteração concorrente de arquivos por outro processo do host. A imagem/ambiente devem permanecer controlados enquanto a chamada roda; falhar se houver config ancestral/gerenciada. O namespace loopback pertence apenas ao teste. Não comprova OmniRoute real, modelo upstream, preço, cancelamento imediato, outros harnesses ou credenciais externas. Flags de tarefas/continuidade continuam desligadas e sem rollout. Nenhuma tool remota foi registrada, nenhuma imagem publicada, nenhuma mensagem inter-task repetida, nenhum gasto externo.

Validação local do delta:53 testes focados aprovados e1deselecionado por exigir localhost; este cenário foi executado separadamente com CLI real e passou em14,32s. Duas execuções do adaptador no ensaio de isolamento (texto e tool injection) passaram; configurações externas recusadas antes do CLI. Hash do módulo e resultados estão no qa/live-cli-isolation.
