---
name: reach-video
description: Baixa e assiste videos publicos de Instagram e YouTube, extrai frames, transcreve e analisa fatores provaveis de desempenho com timestamps.
argument-hint: "<perfil-ou-video> [pergunta]"
allowed-tools: Bash, Read
user-invocable: true
---

# Reach Video

Este skill trabalha somente com URLs publicas acessiveis sem contornar login,
captcha, paywall, bloqueio regional ou controles da plataforma.

## Preflight

```bash
agent-reach doctor
```

O preflight deve confirmar `yt-dlp`, runtime JavaScript do yt-dlp e o backend
de transcricao configurado. Configure `GROQ_API_KEY` (preferencial) ou
`OPENAI_API_KEY` para transcrever quando nao houver captions.

## Coleta

Para um video individual:

```bash
yt-dlp --dump-json --no-playlist "<URL>"
yt-dlp --write-subs --write-auto-subs --sub-langs 'pt.*,en.*' \
  --sub-format vtt --skip-download --no-playlist "<URL>"
yt-dlp --no-playlist -o '/tmp/reach.%(ext)s' "<URL>"
ffmpeg -i /tmp/reach.mp4 -vf 'fps=2,scale=512:-2' /tmp/reach-frame-%03d.jpg
agent-reach transcribe "<URL>" -o /tmp/reach-transcript.txt
```

Uma falha no OpenCLI nao prova que a URL individual esta inacessivel. Para
Reels/posts publicos recebidos diretamente do usuario, execute o probe do
`yt-dlp` antes de declarar bloqueio. OpenCLI e necessario para descoberta de
perfil, busca e listagem; nao para todo URL individual que o extractor consiga
ler sem login.

Para o exemplo solicitado, o comando tenta descobrir ate cinco videos publicos
com o backend oficial do Agent Reach:

```bash
agent-reach doctor
opencli instagram profile caiomktviral -f yaml
opencli instagram user caiomktviral -f yaml
```

Se o OpenCLI retornar URLs individuais, processe cada URL com o fluxo acima.
Se a descoberta falhar, preserve o erro e solicite URLs diretas. Nunca use
cookies copiados, login automatizado ou bypass de CAPTCHA.

Quando o vídeo já tiver captions, não envie áudio a um provider: use o VTT.
Quando não tiver, `agent-reach transcribe` deve ser executado somente depois
de validar a chave do provider.

Leia todos os frames e alinhe-os com a transcricao antes de analisar.

## Relatorio obrigatorio

Para cada video, produza:

1. Identificacao, duracao e fonte da transcricao.
2. Observacoes por timestamp: hook, promessa, cena, texto na tela, cortes,
   ritmo, prova, CTA e encerramento.
3. Sinais de embalagem, formato, assunto e clareza da promessa.
4. Hipoteses de desempenho separadas dos fatos observados.
5. Metricas publicas disponiveis, sem inventar alcance, retencao, CTR ou
   conversoes.
6. Tres testes reproduziveis para novo conteudo.
7. Limitacoes e evidencias ausentes.

Use “sinal observado”, “provavel contribuinte” e “hipotese a testar”; nunca
afirme causalidade sem dados de retencao/alcance ou experimento.

Falha de autenticacao, rate limit, extractor, ausencia de captions ou sessao
necessaria deve ser reportada como limitacao. Nao usar `instaloader`, cookies
copiados, login programatico ou tentativa de burlar controles da plataforma.
