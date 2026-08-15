---
name: reach
description: Usa o Agent Reach oficial para investigar videos publicos e explicar sinais de performance.
---

Use os comandos oficiais do Agent Reach e dos backends que ele reportar em
`agent-reach doctor`. Nao invente um backend alternativo.

Para YouTube, use `yt-dlp` para metadados e legendas; quando nao houver
legenda, extraia audio e transcreva com o provider configurado. Para Instagram,
use apenas `opencli instagram ...` com sessao Chrome explicitamente controlada
pelo usuario. Se estiver em VPS headless sem essa sessao, declare a limitacao.

Ao analisar cada video, alinhe transcript e frames por timestamp e entregue:

1. hook e promessa nos primeiros segundos;
2. estrutura, cortes, ritmo, enquadramento, texto, audio e CTA;
3. sinais publicos observaveis, separados de interpretacao;
4. fatores provaveis de sucesso e contraevidencias;
5. confianca e dados faltantes, como retencao, CTR, alcance e conversao.

Use "hipotese" e "sinal associado", nunca causalidade confirmada com dados
publicos. Nao tente login automatizado, CAPTCHA bypass, cookies de terceiros ou
contorno de rate limit.
