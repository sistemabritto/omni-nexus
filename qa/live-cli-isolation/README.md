# Prova de runtime isolada (manual, opt-in)

Não instala CLI ou dependência e não roda automaticamente na CI. Requer Linux com unshare/bwrap e um OpenCode1.17.18 de origem autorizada já disponível. O script aborta se /etc/passwd ou diretório pessoal estiverem visíveis. Nunca executar diretamente no host nem na VPS.

Preparar scratch /tmp/live-harness-1.17.18 com executável opencode de hash0cbfb6de55aa4ce3c74da12d8516376033693a88abca6238c5be32bf98130636, este runtime.py como isolation-runtime.py e somente dashboard/backend/provider_fallback.py em code/dashboard/backend. Nenhum .env, auth store ou config real é copiado. Fixtures hostis são criados pelo próprio teste no namespace.

Comando utilizado:

```sh
unshare -Urn bwrap --unshare-pid --unshare-ipc --unshare-uts --die-with-parent --cap-add CAP_NET_ADMIN --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --symlink usr/bin /bin --symlink usr/sbin /sbin --proc /proc --dev /dev --tmpfs /tmp --dir /etc --bind /tmp/live-harness-1.17.18 /work --chdir /work --clearenv --setenv PATH /usr/bin:/usr/sbin:/bin /usr/bin/python3 /work/isolation-runtime.py
```

NET_ADMIN só sobe loopback dentro do namespace privado. Não há interface externa nem rota padrão. Runtime observa a fronteira do subprocesso e delega à implementação real; provider sintético SSE127.0.0.1 responde texto e tenta uma tool call não anunciada. Evidência sanitizada em isolation-runtime-proof.json no scratch. Contém somente argv, nomes de variáveis e booleanos de canários, nunca chave real.

Testes de regressão sem CLI:tests/backend/test_live_cli_isolation.py. A CI os executa sem modelo/rede externa. A prova manual é complementar, não substitui smoke de imagem nem autoriza publicação/consumo.

Prova UI/API/fila com CLI real: preparar também a cópia scratch de qa/managed-live-context/task-http-tests.cjs com espera n<1200 (30s, somente fixture), nome task-http-exact-tests.cjs. Executar `python -m pytest qa/live-cli-isolation/queue_runtime.py -q -p no:cacheprovider` no ambiente de testes já instalado. Não usa autenticação real; fixtures Flask criam usuário/empresa/ticket sintéticos. Provider selection é injetada para localhost; o wrapper de execução e o CLI são reais. Mesmo SDK action ID gera uma invocação de CLI; duas requisições internas são título+resposta.

Evidências desta execução:runtime-proof.json e queue-proof.json; contêm hash do módulo testado.53 testes focados aprovados; prova da fila corrigida:1passed em14,32s. CI completa revalida o commit resultante.
