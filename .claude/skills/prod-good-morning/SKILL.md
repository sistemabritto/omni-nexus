---
name: prod-good-morning
description: "Morning orientation that recaps recent work, checks agenda, emails, meetings and tasks, then helps decide what to work on. Trigger when user says 'good morning', 'morning', 'start my day', 'what do I have today', or anything that signals beginning of a work session. Use it proactively — if a user opens with a greeting at the start of a session, run this skill before doing anything else."
---

# Good Morning

Orienta o começo do dia: o que está pendente, o que a agenda reserva, e uma
recomendação de onde começar.

## Antes de tudo: o dossiê chegou?

Esta skill roda de dois jeitos, e a diferença muda quase tudo:

| Como veio | O que fazer |
|---|---|
| Com `--dossie-pronto` nos argumentos | **Modo cron.** Os dados já estão no argumento. Siga a Trilha A. |
| Sem argumento (alguém digitou "bom dia") | **Modo conversa.** Siga a Trilha B. |

A distinção existe porque a rotina das 07:00 já coletou tudo o que é consulta
antes de te chamar (`ADWs/routines/good_morning.py` →
`dashboard/backend/briefing_dados.py`). Refazer aquela coleta com ferramenta é
pagar duas vezes pelo mesmo dado — e era o que fazia esta skill custar US$ 0,16
por manhã.

---

## Trilha A — modo cron (com dossiê)

O argumento traz, já apurados: aprovações pendentes, rotinas que falharam nas
últimas 24h, tarefas do Todoist, tickets abertos e a pauta da esteira para
hoje.

**Não** releia CLAUDE.md, logs de sessão, overviews de projeto nem o Todoist.
Já está tudo no dossiê.

Faça só o que falta, nesta ordem:

1. **Agenda de hoje** — `/gog-calendar`. É a única fonte que o Python não
   alcança: o acesso é por MCP, com o OAuth do Claude Code.
2. **E-mails que pedem ação** — Gmail MCP (`list_emails`, e `get_email` só nos
   que parecerem exigir resposta). Não invoque `/gog-email-triage`: ela manda a
   própria notificação e o Felipe receberia duas.
3. **Escreva o briefing** em pt-BR, curto, e termine com a linha de Telegram
   descrita abaixo.

Não pergunte nada ao final. Ninguém está lendo às 07:00 — a pergunta só
aparece na Trilha B.

### Formato do briefing

Nesta ordem, porque é a ordem do que trava:

1. **Travando agora** — aprovações pendentes e rotinas falhando. Se não houver
   nenhuma, escreva uma linha dizendo isso; a ausência é informação.
2. **Agenda** — compromissos, horário, com quem.
3. **Pede resposta** — e-mails que exigem ação.
4. **Pendências** — tarefas atrasadas primeiro, depois as de hoje, depois os
   tickets.
5. **Recomendação** — **uma** frase dizendo por onde começar, e por quê. Faça
   uma escolha de verdade, sem hedge. É a única parte do briefing que não é
   transcrição, e é para ela que você foi chamado.

Termine a saída com exatamente uma linha:

```
TELEGRAM_MSG: <briefing inteiro, formatado para leitura no celular>
```

O Python lê essa linha e envia uma vez. **Nunca** chame a ferramenta do
Telegram você mesmo — resultaria em mensagem duplicada.

---

## Trilha B — modo conversa (sem dossiê)

Aqui há alguém do outro lado, e vale gastar contexto.

1. Leia **CLAUDE.md**, os **3 últimos logs** de `workspace/daily-logs/` e o
   overview dos projetos ativos. Se algum não existir, siga com o que houver.
2. Colete agenda (`/gog-calendar`), e-mails (Gmail MCP) e tarefas
   (`todoist today`).
3. Dê o mesmo briefing da Trilha A, acrescentando 2-4 bullets do que estava em
   andamento nas sessões recentes.
4. Aí sim pergunte: *"Quer entrar num projeto ou começar algo novo?"* — se
   escolher um projeto, liste os problemas abertos de cada um, uma linha por
   problema, e trabalhe no que for escolhido.

## Tom

Direto e curto, nos dois modos. É orientação de começo de dia, não relatório.
Bullets secos, uma recomendação clara, e sai da frente.
