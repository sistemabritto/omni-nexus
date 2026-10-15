# Media workspace handoff — 2026-10-15

## Diagnóstico por leitura

SQLite aberto com `file:/workspace/dashboard/data/evonexus.db?mode=ro` e SELECT:
22 jobs = 14 `failed`, 7 `ready_for_review`, 1 `approved`. Nenhum job com
`postiz_post_id`; nenhuma publicação ou agendamento comprovados por esses registros.
Todos estão em `publication_mode=draft`, sem `scheduled_at_utc`.

Cinco social_clip falharam com `Manifesto de entrada não encontrado`, incluindo
`092b9b17-a8f3-4110-ab2c-18bfe4a432a3`. O arquivo
`/workspace/media/jobs/<id>/input/job.json` desse job não existe em nenhum dos dois
containers. `docker inspect` confirma o mesmo volume
`evonexus_evonexus_media` em `/workspace/media`, mas dashboard `RW=false` e
worker `RW=true`. Ambos têm `MEDIA_WORKSPACE=/workspace/media`.

A API cria esse manifesto antes de o worker chamar OpenCode. Portanto, dashboard
sem escrita não consegue entregar um novo manifesto ao worker. Não afirmamos que
o mount RO atual explica sozinho toda a história dos 14 erros antigos. Na stack
versionada de main, o dashboard nem sequer monta esse volume: sem o mount, grava
num filesystem próprio que o worker não vê.

## Correção isolada

`evonexus-vps.stack.yml`: dashboard monta `evonexus_media:/workspace/media:rw`
e declara `MEDIA_WORKSPACE=/workspace/media`. Worker, Live, UI, credenciais e
configuração de Portainer não são alterados. É uma correção do artefato de stack;
nenhuma alteração de produção foi aplicada.

PR32 (`fix/media-retry-loop`, commit 65f1b5d) já contém correções complementares:
criação do scaffold antes de persistir o job e limite de tentativas. Este patch
não duplica essa implementação. O integrador precisa avaliar ambos; só alterar o
mount não adiciona esses guardrails à imagem atualmente em uso.

## Evidência simulada

- Teste de contrato reproduziu falha em main: dashboard sem media mount.
- Mesmo teste passa com o patch; rejeita ausência, volume diferente ou mount RO.
- Teste da API com SQLite em memória e diretório temporário: create → run →
  executor lendo o manifesto → estados de geração/render/validação simulados →
  aprovação → draft → schedule. Nenhum modelo/render/ffprobe/Postiz real.
- Verifica bloqueio do upload antes de aprovação, idempotência de upload/draft e
  preservação da data UTC para o draft que será agendado.
- Suites existentes de rotas, workspace e máquina de estados passaram.

## Checklist do teste real — execução exclusiva do integrador

- [ ] Revisar PR32 e este patch junto com as alterações já implantadas. Não fazer
  deploy cego desta stack main inteira: há divergência conhecida entre Git e
  configuração viva, incluindo o mount RO; preservar Live/UI/Portainer e envs.
- [ ] Revisar motivo do mount RO antes da aplicação; o contrato atual da API
  exige escrita. Se a política exigir RO, será necessário redesenhar a criação
  dos manifestos no worker, fora do escopo deste patch.
- [ ] Aplicar somente a mudança de mount/env pelo integrador autorizado; verificar
  mesmo volume e destino em ambos, dashboard RW=true e worker RW=true. Montagem
  local Swarm requer colocação no mesmo nó (ambos estão restritos a manager na
  stack atual; clusters multi-manager precisam política adicional).
- [ ] Confirmar limites de tentativas e que jobs históricos não serão reativados.
- [ ] Obter autorização explícita para um novo conteúdo e assets, orçamento/modelo
  e destino de teste antes de executar geração real. Não reutilizar campanha21,
  rascunho Instagram encerrado ou o job aprovado antigo.
- [ ] Criar um único job autorizado; confirmar que input/job.json é legível nos
  dois containers antes de iniciar a geração e que não há credenciais no arquivo.
- [ ] Conferir skills, binário e modelo do worker. `process_social_clip_job` em
  main não fixa `force_provider`; a regra local exige OpenCode. Ainda não houve
  invocação real nessa investigação, portanto não declaramos esse estágio validado.
- [ ] Executar composição/render/ffprobe do job autorizado, inspecionar vídeo e
  esperar `ready_for_review`; registrar ID, hash e metadados.
- [ ] Obter aprovação desse conteúdo. Criar draft somente com destino autorizado;
  validar integração e data sem inferir publicação por resposta HTTP.
- [ ] Agendamento real exige autorização específica de conteúdo, destino e horário.
  Confirmar no Postiz o estado/data; a rota atual marca scheduled após change_status
  e não prova por si só publicação futura. Registrar evidência sem publicar agora.

## Limites e ferramentas

Não geramos mídia paga, não publicamos, não agendamos posts reais, não alteramos
credenciais nem reprocessamos jobs. OpenCode está instalado localmente, mas não
foi invocado; nenhum modelo Drael foi selecionado ou validado, e defaults globais
não foram alterados. Nenhum uso de Claude Code nesta execução.

Coordenação enviada às threads 01a13f7c-2a2b-715e-8cd0-3ae08045b0d2 (sem conflito
confirmado) e 01a13c9a-dd49-73a0-a0fc-87b82fb29016 (único integrador/deploy).
