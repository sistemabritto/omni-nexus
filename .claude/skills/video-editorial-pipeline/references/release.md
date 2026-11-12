# Release aprovado → agendamento → distribuição

Use depois de editar, revisar prévia/snapshots e concluir QA. O novo registro
`media_releases` separa a aprovação final dos dados que o worker pode escrever.
Não é autorização para executar as chamadas reais agora: Felipe precisa aprovar
este render e cada copy/conta/horário específicos na sessão humana.

1. `PUT /api/media/jobs/<id>/release` cria revisão com `render_version` e
   `channels=[{platform,integration_id,content,scheduled_at_utc,settings?}]`.
   O job precisa estar ready_for_review/approved, com arquivo validado dentro
   do workspace e SHA-256 real igual ao checksum do job. Quatro plataformas
   com builders existentes: Instagram, YouTube, LinkedIn, TikTok. Nenhuma conta
   será conectada por este fluxo. O canal é uma integration_id explícita,
   não uma escolha inferida pelo agente. Data ISO tem timezone e está no futuro.
2. Apresente o snapshot completo, incluindo hash, versão, copy por canal,
   settings e calendário, ao Felipe. `GET .../release` devolve digest, revisão,
   aprovação e checkpoints. `POST .../release/approve {"digest":"..."}` exige
   sessão humana autenticada com permissão manage, registra username real e
   timestamp; Bearer token de agente não pode aprovar. Não enviar nome de
   aprovador pelo payload como se isso fosse prova de consentimento.
3. Após essa aprovação específica, `POST .../release/distribute` valida de novo
   o hash e todos os campos vinculados, verifica as contas já conectadas e usa
   o PostizClient existente para upload, draft e schedule por canal. Não há
   publish-now. O draft recebe a data aprovada antes de mudar o status; se o horário expirar
   durante upload/criação do draft, a aprovação é invalidada e nada é agendado. A mesma
   mídia só é reutilizável quando QA confirmou adequação a cada canal.
4. Releia `POST .../release/refresh`: IDs, state, remote_state e release_url ficam
   por canal. `scheduled` só após GET no Postiz confirmar QUEUE com copy,
   integration.id e publishDate exatos; PUBLISHED e URL só vêm da leitura
   remota, nunca de HTTP 200 ou de postId sozinho. URL pode continuar ausente.

Uma revisão nova exige `expected_digest` da revisão anterior e elimina sua
aprovação. Alteração do arquivo, checksum, título/copy base, calendário do job
ou dos canais/contas/settings/versão torna a aprovação inválida. PATCH do job
invalida a aprovação vinculada; mudanças no disco são verificadas pelo hash
antes das chamadas. Divergência remota de copy/conta/data também invalida.
Não use a antiga aprovação do beat sheet nem `job.status=approved` como prova.
PATCH não pode promover o worker a approved/scheduled/published.

Os antigos `/create-draft` e `/schedule` agora retornam 409
`bound_release_required`; não há atalho legado sem digest. O painel Mídias já usa esse contrato para revisar/selecionar contas por nome e
aprovar/agendar; outros clientes que usavam esses endpoints precisam migrar
antes do teste real.

Retries preservam upload e post_id de cada canal e não recriam canais já
confirmados. Rejeições HTTP inequívocas (ex.429) têm até três tentativas por
canal, acionadas explicitamente, sem loop automático. Timeout/5xx/resposta
ambígua ao criar post tornam o canal unknown: **parar e reconciliar**, sem novo
POST. Um checkpoint creating_draft interrompido também vira unknown. Com
post_id conhecido, retentar a mesma mudança de status não cria outro post.
Um lock persistido busy serializa as requisições; queda do processo deixa busy
para reconciliação pelo operador, sem expiração que possa duplicar publicação.

Depois que qualquer post foi criado/ficou incerto, substituir o release é
bloqueado até reconciliação. Invalidar aprovação ou cancelar o job **não cancela
posts já agendados no Postiz**. Preserve IDs/URLs e avise o Felipe; qualquer
alteração/cancelamento remoto exige autorização própria. Refresh é leitura
remota e continua disponível mesmo com aprovação invalidada.

Campos remotos conferidos na [documentação oficial de List Posts](https://docs.postiz.com/public-api/posts/list).
A instância self-hosted continua usando o prefixo /api/public/v1 do cliente
existente; nenhuma URL de conta/credencial é inventada por esta skill.
