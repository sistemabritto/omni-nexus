---
name: social-schedule-postiz
displayName: "Agendar no Postiz (self-hosted)"
description: "Canonical path for putting any finished social content on the calendar: Postiz self-hosted is the official scheduling intermediary for every platform. Use when the user says 'agendar post', 'schedule this', 'publicar na quinta', 'colocar no calendário', 'mandar pro Postiz', or when a content skill (post-writer, thread-writer, carousel-writer, repurposer, content-calendar) has finished a draft that needs to actually go out. Never publish directly through a platform API."
category: social
envKeys: ["POSTIZ_URL", "POSTIZ_API_KEY", "POSTIZ_ALLOWED_MEDIA_HOSTS"]
metadata:
  version: 1.0.0
---

# Agendar no Postiz

Postiz self-hosted (`POSTIZ_URL`) é o **único** intermediário de agendamento e
publicação do workspace. Nenhuma skill e nenhum agente chama a API do X, do
LinkedIn, do Instagram ou do Threads diretamente — mesmo quando existe um token
`SOCIAL_*_ACCESS_TOKEN` no `.env`. Esses tokens continuam existindo só para
**leitura** (analytics: `social-instagram-report`, `social-linkedin-report`,
`social-youtube-report`). Escrita é sempre via Postiz.

**Por quê:** um único ponto de saída dá calendário unificado, retry, histórico e
— o mais importante — um gate de aprovação humana antes de qualquer coisa
pública. Publicação direta por API contorna esse gate.

## As duas rotas (escolha pela natureza do conteúdo)

### 1. Texto / imagem estática → gate de aprovação por ticket

Esta é a rota padrão para post, thread, carrossel e repurpose. Você **não**
publica: você prepara o conteúdo exato e o dashboard publica depois que o
humano aprova no Telegram.

No JSON de outcome do ticket:

```json
{
  "action": "work",
  "ticket_id": "<id>",
  "result": "Post de LinkedIn sobre GEO pronto para agendamento",
  "new_status": "review",
  "publish_intent": true,
  "publish_target": "linkedin",
  "publish_content": "<o texto EXATO que vai ao ar, não um resumo>",
  "publish_media": ["https://s3.workflowapi.com.br/post/media/xxx.png"],
  "publish_at": "2026-08-18T12:00:00Z"
}
```

- `publish_at` — **instante ISO-8601 em UTC**. Presente ⇒ o Postiz agenda para
  aquele momento. Ausente/`null` ⇒ publica assim que o humano aprovar.
  Lembre de converter de America/São_Paulo (UTC-3) para UTC: 09:00 BRT = `12:00Z`.
- Data no passado, texto solto ("quinta que vem") ou mais de 365 dias à frente
  são **recusados** — o gate falha fechado em vez de publicar na hora errada.
- `publish_target` aceita: `instagram`, `linkedin`, `x`, `threads`, `youtube`,
  `discord`, `whatsapp` (`PUBLISH_CHANNELS`).
- `publish_media` exige URL **HTTPS pública** cujo host esteja em
  `POSTIZ_ALLOWED_MEDIA_HOSTS`. Gere a URL com a skill `int-minio`:
  ```bash
  URL=$(python .claude/skills/int-minio/scripts/upload.py ./post.png | tail -1)
  ```
  Instagram **exige** ao menos uma mídia; LinkedIn/X/Threads aceitam só texto.

O card do Telegram mostra o texto real, as mídias e a data de agendamento —
aprovar significa "aprovei exatamente isto, saindo exatamente nessa hora".

### 2. Vídeo que precisa ser renderizado → MediaJob

Use o pipeline `POST /api/media/jobs` (skill `social-media-production`). Ele
compõe, renderiza, valida com ffprobe e cria draft/agendamento no Postiz
sozinho, num serviço isolado. Plataformas suportadas hoje: `instagram`,
`youtube`, `linkedin`, `tiktok`.

## Agendar direto pela API (scripts e lotes)

Para agendar em lote fora do fluxo de ticket — por exemplo, distribuir um
calendário editorial inteiro — use o cliente único do repositório. **Nunca
escreva um segundo cliente Postiz.**

```python
from dashboard.backend.postiz_client import PostizClient, build_platform_settings

client = PostizClient.from_env()          # None se POSTIZ_URL/API_KEY faltarem
integration = client.select_integration("x")
client.schedule_post(
    integration_id=integration["id"],
    content="texto exato",
    media=[],                              # [{"id": ..., "path": <url https>}]
    settings=build_platform_settings("x"), # X EXIGE who_can_reply_post
    scheduled_at_utc="2026-08-18T12:00:00+00:00",
)
```

Confirme sempre depois de agendar — `POST /posts` só diz que o workflow foi
criado, não que o post está na fila:

```python
client.confirm_scheduled([post_id], window=(inicio_iso, fim_iso))
```

`confirm_scheduled` falha fechado: post ausente da janela ou em `ERROR` nunca
conta como agendado.

## Payloads por plataforma

`build_platform_settings(platform, **kwargs)` monta o `settings` correto:

| Plataforma | Observação |
|---|---|
| `x` | `who_can_reply_post` é **obrigatório** (default `everyone`). O shape genérico `{"__type": "x"}` é recusado pelo Postiz. |
| `threads` | Só `__type`, sem campos extras. |
| `linkedin` | `page=True` para publicar como página em vez de perfil. |
| `instagram` | `post_type` `post` ou `story`; exige mídia. |
| `youtube` | `title` obrigatório (2–100 chars) + `visibility`. |
| `tiktok` | `privacy_level` default `SELF_ONLY` (privado) — passe explicitamente para tornar público. |

## Checklist antes de agendar

- [ ] `publish_content` é o texto final, não um resumo
- [ ] `publish_at` em UTC e no futuro
- [ ] Mídia hospedada via `int-minio` com host permitido
- [ ] Plataforma dentro de `PUBLISH_CHANNELS`
- [ ] Conteúdo respeita os limites da rede (X 280, LinkedIn ~3000, Threads 500)
- [ ] Nada foi publicado direto por API de plataforma

## Boundaries

- Não escreve o conteúdo — veja `social-post-writer`, `social-thread-writer`,
  `social-carousel-writer`.
- Não decide o calendário — veja `social-content-calendar`.
- Não publica sem aprovação humana quando o conteúdo é público.
- Não substitui o pipeline de vídeo — veja `social-media-production`.

## Related Skills

- `int-minio` — transforma arquivo local em URL pública para `publish_media`
- `social-media-production` — pipeline de vídeo (MediaJob)
- `social-content-calendar` — define os slots que viram `publish_at`
- `social-content-repurposer` — adapta um conteúdo por rede antes de agendar
