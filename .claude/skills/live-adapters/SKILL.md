---
name: live-adapters
description: Contratos dos adapters Live para automações, integrações, materiais, pesquisa e GitHub/CI.
---

Use `operate_omni_adapter(adapter, operation, argumentsJson)` somente quando o
usuário pedir a operação. A presença no catálogo não autoriza agir. O servidor
reaplica ACL e vínculos; mudanças administrativas e remoções sempre exigem
aprovação humana no chat, mesmo com YOLO ligado. Não há autoaprovação.

As automações nativas são configurações globais do workspace, administradas
por um administrador explicitamente vinculado no servidor. Não atribua esses
recursos a uma empresa por hipótese. Memórias e materiais mantêm seus próprios
vínculos por usuário e empresa. Nunca copie memórias entre empresas.

## Operações

`argumentsJson` é uma string contendo um dos objetos abaixo.

- `heartbeats/create`: `{id, agent, interval_seconds, decision_prompt, max_turns?, timeout_seconds?, wake_triggers?}`. Nasce desativado. O prompt precisa ter ao menos 20 caracteres. Não aceita handler, script nem segredos.
- `heartbeats/update`: `{identifier, changes:{enabled?, interval_seconds?, max_turns?, timeout_seconds?, agent?, decision_prompt?, wake_triggers?}}`.
- `heartbeats/read_alerts`: `{identifier}`.
- `heartbeats/configure_alerts`: `{identifier, enabled?, categories?, cooldownSeconds?, quietStart?, quietEnd?, timezone?}`. Categorias: timeout, provider_exhausted, auth, unknown. Horário HH:MM, fuso IANA. O canal é o transporte já configurado; não invente destinatários nem envie alertas de teste.
- `routines/create`: `{name, script, frequency, time?, interval?, day?, days?}`. Escolha `script` de `routineExecutors` do catálogo. Frequências executáveis atuais: daily e weekly. `interval` é em minutos, `time` HH:MM. Dias em inglês. O fuso é o do scheduler do workspace. Nasce desativada; não afirme agenda ativa sem recarga confirmada. Monthly retorna bloqueio explícito enquanto o scheduler não tiver executor compatível.
- `routines/update`: `{identifier:"daily/slug", changes:{name?, time?, interval?, day?, days?, enabled?}}`.
- `triggers/create`: `{name, type:"webhook"|"event", source, agent, action_type:"script", action_payload, condition?}`. Escolha `action_payload` de `routineExecutors`; nasce desativado. Fontes: github, linear, telegram, discord, stripe, custom. Não retorna segredo de webhook ao agente.
- `triggers/update`: `{identifier:"123", changes:{name?, agent?, enabled?, event_filter?, condition?}}`.
- `integrations/create`: `{slug, displayName, description?, category?, envKeys?}`. Somente metadados de integração customizada; nomes de variáveis devem começar com `CUSTOM_<SLUG_EM_MAIÚSCULAS>_`. Não cria executor de API. O usuário insere os valores no painel de Integrações.
- `integrations/update`: `{slug, displayName?, description?, category?, envKeys?}`. Somente integração customizada existente.
- `integrations/configuration`: `{slug}`. Retorna o caminho do painel para credenciais. Nunca solicite token no chat.
- `integrations/test`: `{slug}`. Para plugin, use o slug global `plugin-github-github` ou `plugin-web-research-brave`. Testar saúde não prova todas as permissões de execução.
- `materials/edit`: `{artifactId:"file:<id>", content, expectedSha256}`. Leia antes com `read_omni_artifact`. Apenas fonte textual explicitamente vinculada, com hash atual. Preserva backup, autoria histórica e revisão. Roteiros de Gravações continuam usando seu fluxo editorial próprio.
- `skills/execute`: `{name, capability, input:{query}}`. Executores disponíveis: `mkt-creative-brief` + `creative-brand-context`; `mkt-brand-review` + `brand-review-context`. Executam leitura das referências de marca autorizadas e emitem recibo. Isso não gera imagem nem executa shell. Outras skills precisam de binding compatível; não prometa executor genérico.
- `internet/search`: `{query, count?, domains?, freshness?}`. Count 1–10; domains até cinco domínios; freshness pd/pw/pm/py. Exige Brave Search configurado no painel. A busca pode consumir cota. Não envie dados internos; cite fontes e data. Não afirma leitura integral das páginas.
- `removal/remove`: `{area:"heartbeats"|"routines"|"triggers"|"integrations", identifier}`. Aprovação humana específica, snapshot criptografado antes do efeito, sem retry automático. Não oferece exclusão de repositório, arquivo ou branch GitHub.

## Condições de gatilho

Use árvores limitadas `all`, `any`, `not` e folhas `{field, op, value}`.
Operadores: eq, ne, in, contains, gt, gte, lt, lte, exists, glob.
Campos podem ser caminhos como `data.amount`. Não use código ou expressões.

Exemplo: `{"all":[{"field":"source","op":"eq","value":"github"},{"field":"event_type","op":"glob","value":"issue*"}]}`.

## GitHub e self-healing

Antes de revisar, use `inspect_omni_area(area="github")` e o proprietário
retornado. `sistema-britto` é uma grafia explicitamente configurada para
`sistemabritto`; não é autorização para outra conta. Leia PR e `/files`,
seguindo `nextOffset` dentro da mesma página, conferindo sha256 do JSON,
depois `nextPage`. Não invente um diff quando a leitura falhar.

- `github/commit`: `{repository:"owner/repo", branch, headSha, message, files:[{path,content}], createBranch?}`. Vulcano ou Hawk, branch de trabalho, commit normal e arquivos textuais. Proíbe alteração da própria política/executor/workflows, force push, remoção e branches protegidas. Aprovação humana vinculada ao SHA e conteúdo.
- `github/ci`: `{repository, branch, headSha, workflow:"ci.yml"}`. Despacha somente workflow registrado e idêntico ao executor revisado.
- `github/rollout`: `{repository, branch, headSha, image, previousImage, ciRunId, buildRunId}`. Imagens `excarplex/evo-nexus-dashboard@sha256:<digest>`. Exige CI/build bem-sucedidos do mesmo SHA, workflow verificado, ambiente production configurado e política ativada pelo operador. A aprovação humana no Live é obrigatória; revisores adicionais no GitHub podem ser exigidos pelo operador. YOLO não dispensa aprovação. Não há shell/SSH/Docker exposto ao agente.
- `github/status`: `{jobId}`. Consulte o ID real retornado. Pending/running/dispatched não significam concluído. Running/uncertain após interrupção exige reconciliação; não repita para contornar erro.

O rollout começa desabilitado até o operador configurar o ambiente protegido,
credenciais e pin de host nos Secrets do GitHub. O agente não configura isso.
Lens mantém a revisão independente; não aprova a própria implementação.
