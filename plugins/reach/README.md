# Reach: Agent Reach oficial

Este plugin integra o repositorio oficial
[`Panniantong/Agent-Reach`](https://github.com/Panniantong/Agent-Reach). Ele nao
reimplementa o projeto nem mascara falhas dos backends.

## Capacidades e limites

- YouTube usa `yt-dlp` e funciona sem login para leitura e legendas.
- URLs individuais e publicas de Reels/posts devem ser testadas primeiro com
  `yt-dlp`; esse caminho funciona na VPS quando o extractor consegue acessar a
  midia sem login.
- Descoberta de perfil, busca e listagem de posts no Instagram usam OpenCLI com
  uma sessao Chrome ja autenticada e controlada pelo usuario. O upstream
  documenta esse caminho como desktop-only.
- Em VPS headless, descoberta de perfis no Instagram nao e considerada
  configurada ate existir uma sessao Chrome/OpenCLI visivel e autorizada. Isso
  nao impede o teste de uma URL publica individual com `yt-dlp`.
- Nao usar login automatizado, cookies de terceiros, CAPTCHA bypass ou scraping
  alternativo.
- Metricas publicas nao provam causalidade. O relatorio usa hipoteses e sinais
  observaveis, sem afirmar retencao, CTR ou conversao sem dados da conta.

## Instalar o Agent Reach na VPS

```bash
uv tool install --force \
  'https://github.com/Panniantong/agent-reach/archive/main.zip'
agent-reach install --env=auto
agent-reach doctor
```

Use `--system` somente com autorizacao explicita para instalar dependencias do
host. O Agent Reach oficial mantem configuracao em `~/.agent-reach/`. O
`install-service.sh` faz a mesma instalacao para o usuario `evonexus`.

## Teste de YouTube

```bash
yt-dlp --dump-json 'https://www.youtube.com/watch?v=VIDEO_ID'
yt-dlp --write-auto-subs --sub-langs 'pt.*,en.*' --skip-download \
  'https://www.youtube.com/watch?v=VIDEO_ID'
```

## Instagram de referencia

Para uma URL individual publica:

```bash
yt-dlp --dump-json --no-playlist 'https://www.instagram.com/p/SHORTCODE/'
agent-reach transcribe 'https://www.instagram.com/p/SHORTCODE/' -o /tmp/reach-transcript.txt
```

Para descobrir perfis/posts, o caminho suportado pelo upstream e
desktop/OpenCLI. Depois de instalar o OpenCLI e a extensao no Chrome da sessao
autorizada:

```bash
opencli doctor
opencli instagram profile caiomktviral -f yaml
opencli instagram user caiomktviral -f yaml
```

Se o doctor indicar `AUTH_REQUIRED`, `429` ou backend ausente, o resultado e
"nao configurado"; nao tentar contornar a protecao. Para assistir e
transcrever um Reel, obter a URL publica individual retornada pelo OpenCLI e
usar `yt-dlp`/Whisper conforme o skill instalado.
