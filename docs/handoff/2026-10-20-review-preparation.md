# Continuação local: autonomia e Party Mode, 20/10/2026

## O que este commit representa

Preparação autorizada para revisão, não implantação. Base original: `sistemabritto/omni-nexus-live`, branch `fix/live-handoff-read-catalogs`, commit `beec8dfecf662122eb695540c7715e3242057d8b`. Branch de entrega: `review/autonomy-party-2026-10-20`. O SHA canônico é o commit publicado nessa branch; confirme-o com `git rev-parse HEAD` após obter a branch. Não confundir este pacote com mudanças locais anteriores ou com o quiz do repositório `sistemabritto/site`.

Foram preparados:
- Autonomia: revalidação de autorização/política, checkpoints e reconciliação somente por evidência exata, sem repetir mutações incertas. Rollout continua desligado.
- Party Mode: conversa separada por texto, dois a três agentes em ordem, até oito rodadas; isolamento por usuário/empresa, cancelamento, recuperação de histórico e bloqueio de repetição de turno. Sem voz, ferramentas ou execução de tarefas. Flag padrão OFF.
- Dois acréscimos às listas de testes do CI, sem mudar gatilhos, permissões ou gates de produção.

As alterações foram integradas a partir dos commits locais de preparação `7a53701740fd7e61895e979bea76a762f994c3fb` (autonomia) e `fd1bfcad576cbe07055a8af27d2f6428f5e0d219` (Party). Esses identificadores documentam a origem; não substituem o SHA remoto publicado.

## Verificação já executada

- 104 testes Python passaram na seleção abaixo, com GitHub/HTTP/provedor/CLI simulados.
- Fixtures Node de Party e todos os 13 contratos/SSR existentes do frontend passaram, incluindo individual Live, empresa, cancelamento e recuperação.
- Build TypeScript/Vite e lint dos quatro arquivos TS/TSX alterados passaram. Aviso existente de bundle grande permanece.
- Verificação de espaços do diff passou. Baseline anterior: terminal 48 testes e bridge 6 testes passaram.

Limites: Python local 3.12 e Node 24, enquanto CI declara Python 3.11 e Node 22. A tentativa ampla de CI backend foi interrompida por bloqueio de uma chamada real à API x.ai; não existe resultado completo verde dessa suíte. Não a repita com credenciais ou rede reais sem isolamento explícito. Browser real, mobile/touch/reflow não foram verificados: Chromium local não iniciou no sandbox e o navegador remoto não alcançou localhost. Não houve teste com voz, microfone, provedor real ou VPS/produção.

## Retomar sem apagar trabalho existente

No checkout correto, inspecione antes de qualquer alteração:

```sh
git status --short
git branch --show-current
git log -5 --oneline
git fetch origin review/autonomy-party-2026-10-20
git worktree add ../omni-review-2026-10-20 origin/review/autonomy-party-2026-10-20
cd ../omni-review-2026-10-20
git rev-parse HEAD
git diff --stat beec8dfecf662122eb695540c7715e3242057d8b..HEAD
```

Use um destino novo para o worktree. Não use `reset --hard`, `clean`, force-push ou sobrescrita de arquivos para resolver diferenças. Preserve commits e mudanças não commitadas do PC. Compare toda alteração local antes de decidir merge/cherry-pick. O commit local antigo `e4161a2`, caso exista, pertence ao trabalho de quiz: compare no repositório `site`, seguindo o handoff daquele pacote; não o aplique aqui.

Com dependências já disponíveis, a seleção segura revisada é:

```sh
uv run --no-sync pytest -q tests/backend/test_live_self_healing.py tests/backend/test_live_adapters.py tests/backend/test_live_github.py tests/backend/test_live_handoff_access.py tests/backend/test_live_party.py
node qa/party-mode/session-tests.cjs
node review/voice-first/mobile-host-tests.cjs
node review/voice-first/render-tests.cjs
node review/voice-first/integrated-flow-tests.cjs
npm --prefix dashboard/frontend run build
git diff --check
```

Para reproduzir em instalação limpa, siga o lockfile e as versões declaradas no CI; mantenha chamadas externas simuladas. Mais detalhes: `docs/live-pipeline-recovery.md` e `qa/party-mode/README.md`.

## Pendências antes de ativar ou implantar

1. Concluir revisão visual/mobile e CI isolado nas versões declaradas, sem inferir que build/SSR equivalem a QA real.
2. Revisar o diff completo contra o alvo real de um futuro PR: `main`/`develop` não são esta base de trabalho.
3. Autonomia CI ainda despacha por branch mutável: checagem anterior e observação posterior não garantem atomicidade de SHA. Rollout só reconcilia com run ID explicitamente reconhecido; resposta GitHub 204 pode exigir conferência manual. Não enfraquecer gates para contornar isso.
4. Party usa política existente por turno, não um novo teto agregado mensal. Cancelar descarta retorno e próximos participantes, mas não garante interrupção/reembolso de chamada já iniciada.
5. Manter `NEXUS_PARTY_MODE_ENABLED=false`, gates de execução/consumo e rollout desativados. Não alterar segredos/permissões, migrar, criar tags, publicar imagens ou despachar workflows nesta retomada de revisão.
6. **Rollout depende de nova autorização explícita do usuário depois que ele retornar.** Publicar esta branch não autoriza merge, PR, ativação ou deploy.

A branch de revisão não corresponde aos gatilhos push de CI/publicação inspecionados. CI dispara em PR para main/develop; rollout é manual e exige SHA/imagens/CI/build conferidos. Não iniciar esses fluxos apenas por ler este documento.
