# Esteira de vídeo — o que cada bug real já ensinou

Pipeline de vídeo em três fases, mesma regra da esteira de conteúdo (**modelo
só onde há julgamento** — escolher o quê cortar é julgamento; recortar,
enquadrar, dar zoom e legendar é execução determinística, ffmpeg puro):

```
Fase 1A  corte_bruto            denoise (DeepFilterNet) + normalize + corte de silêncio
Fase 1B  corte_editorial        modelo propõe cortes extras (queda de conexão, "deixa eu
                                 recomeçar"), humano aprova via aplicar_corte_editorial
Fase 1C  cortes_virais          modelo escolhe trechos autocontidos, ffmpeg recorta em
                                 9:16 com fundo desfocado + avatar + zoom + legenda karaokê
```

`dashboard/backend/media_audio.py` (Fase 1A), `corte_editorial.py` (Fase 1B),
`cortes_virais.py` (Fase 1C) — todas chamam `invoke_with_fallback()` de
`provider_fallback.py` pro passo de julgamento.

---

## 0. `force_provider="opencode"` é obrigatório em qualquer chamada de modelo daqui

`Dockerfile.media-worker` só instala o binário `opencode` — nunca
`openclaude` nem `claude`. `invoke_with_fallback()` sem `force_provider`
segue a cadeia de `config/providers.json`, que na VPS tem
`active_provider=omnirouter` (cli_command `openclaude`). Toda chamada sem o
pin falha com `"<cli> binary not found in PATH"` até esgotar a cadeia
inteira em `anthropic:claude` — e o job **retenta sozinho**, reprocessando a
transcrição inteira (~4min de Groq num vídeo de 3h) a cada tentativa.

Achado ao vivo em 29/07/2026: o primeiro job real de `cortes_virais` rodou
**3 auto-retries completos** (19 blocos de transcrição cada) antes de eu
notar e parar manualmente (`PATCH /api/media/jobs/{id} {"status":"failed"}`).

```python
resultado = invoke_with_fallback(
    prompt=prompt, timeout_seconds=timeout_seconds, agent="", cwd=cwd,
    force_provider="opencode",
)
```

**Corolário:** `force_provider` sozinho não bastava — `FallbackEngine.attempts()`
só procurava o provider dentro da cadeia já resolvida do `active_provider`
corrente, e `opencode` não está no `fallback_providers` de `omnirouter`.
Corrigido em `provider_fallback.py`: quando o provider forçado não está na
cadeia ativa mas existe em `config/providers.json`, monta a entry direto de
lá. Sem isso, forçar qualquer provider fora da cadeia do momento vira
silenciosamente "No attempts made".

**Se for mexer num job novo desta esteira:** confirme que a chamada de
modelo tem `force_provider="opencode"` antes de rodar contra vídeo real —
não confie em teste só com mock.

## 1. Prompt grande estoura o limite de argumento do SO, não só do modelo

`cortes_virais.py` embute a transcrição inteira (30 mil palavras num vídeo
de 3h+) no prompt. Todo CLI aqui (claude/openclaude/opencode) recebe o
prompt como argumento de linha de comando — argv+envp compartilham o
`ARG_MAX` do kernel (~2MB no Linux, mas o ambiente do processo já ocupa
parte disso). Um prompt de centenas de KB estoura isso com
`[Errno 7] Argument list too long`.

Fix em `provider_fallback.py::_invoke_cli` — acima de `PROMPT_ARG_SAFE_BYTES`
(100KB) o prompt sai do argv e vai por stdin (`claude --print` e
`opencode run` leem stdin quando o prompt/mensagem posicional não é
passado). Prompts normais (heartbeats, rotinas) continuam exatamente como
antes — só o caminho raro de prompt gigante muda.

## 2. A resposta do modelo nem sempre é JSON estrito

`_extrair_json_array()` (mesma função copiada em `corte_editorial.py` e
`cortes_virais.py`) já viu, na mesma tarde, três formatos diferentes de
resposta pro mesmo pedido de "responda só com um array JSON":

1. JSON válido — o caminho feliz.
2. Sintaxe de dict Python (aspas simples) — `json.loads` rejeita com
   "Expecting property name enclosed in double quotes".
3. Um nível extra de escape, como se o modelo tivesse serializado a
   resposta duas vezes (`\"` em vez de `"`, `\n` literal em vez de quebra de
   linha real) — `json.loads` rejeita com "Expecting ',' delimiter".

A função tenta as três, nessa ordem: `json.loads` → `ast.literal_eval`
(aceita a sintaxe Python com segurança, é avaliação de literal, não `eval`)
→ embrulhar o trecho em aspas e deixar o próprio parser JSON desescapar.
`[`/`]`/`{`/`}` nunca são afetados pelos escapes, então a fatia
`bruto[inicio:fim+1]` continua correta antes de qualquer uma das três
tentativas.

**Se escrever um prompt novo que peça JSON pro modelo nesta esteira, reuse
`_extrair_json_array`, não escreva um `json.loads` cru de novo.**

## 3. `zoompan` reavalia toda a cadeia de filtros anteriores por frame

Comportamento conhecido do ffmpeg, não bug nosso. Compor o fundo (crop +
blur em resolução reduzida + overlay do avatar) e SÓ DEPOIS aplicar
`zoompan` + legenda num segundo passe evita que o blur/overlay seja
recalculado a cada frame de saída. Medido ao vivo em 29/07/2026: com os
dois no mesmo filtergraph, 8 segundos de clipe não terminavam em 10 minutos
de CPU. Em duas passadas: ~10s reais pra 8s de clipe.

`renderizar_corte_viral()` em `cortes_virais.py` faz isso: `ffmpeg` #1
compõe pra `composto.mp4` (sem zoompan, sem legenda), `ffmpeg` #2 aplica
zoompan+subtitles em cima do composto.

## 4. Ordem importa: cortar no tamanho original, escalar depois

Escalar o frame 1280x720 inteiro pra cobrir o canvas 1080x1920 ANTES de
cortar (`scale=-2:1920` vira um intermediário de 3413x1920) desperdiça a
maior parte desse upscale gigante — a maioria dos pixels calculados é
cortada fora um filtro depois. Cortar a faixa vertical no tamanho original
primeiro (mesma lógica do crop cru da V1) e só então escalar é ordens de
magnitude mais rápido. Vale pra qualquer filtro de "cover crop" nesta
esteira, não só o fundo desfocado.

## 5. `-loop 1` numa imagem estática é infinito sem `-shortest`

O avatar (PNG estático) entra no `ffmpeg` com `-loop 1` pra durar o clipe
inteiro. Sem `-shortest` no comando de saída, esse input não tem fim
natural e o encode roda pra sempre (ou até um limite default enorme) —
medido ao vivo: arquivo de saída crescendo sem parar, 14+ minutos de CPU
até eu matar o processo manualmente. Qualquer composição que mistura vídeo
real (com duração) e imagem em loop precisa de `-shortest`.

## 6. Avatar circular — crop não pode ser geometricamente centrado

`preparar_avatar_circular()` gera o círculo com `geq` (sem Pillow — o
media-worker não tem lib de imagem instalada, só ffmpeg). A foto fonte
(retrato 960x1280) sobra na altura depois do scale-to-cover; crop
centralizado corta a mesma fatia de cima e de baixo, e numa selfie isso
corta testa/queixo do rosto sem necessidade — o rosto fica no terço
superior da foto, o resto é ombro/mesa. `AVATAR_VIES_VERTICAL=0.20` desloca
o corte pra manter mais do topo. Validado visualmente (não só por teste
mockado): extraí frame real do container com `ffmpeg -ss ... -frames:v 1` e
conferi o enquadramento antes de considerar resolvido.

## 7. Legenda tem que respeitar a safe zone das redes, não só caber no vídeo

TikTok/Reels/Shorts sobrepõem UI própria na parte de baixo do vídeo
(legenda/descrição do app, ícones de ação, nome de usuário) — um `MarginV`
baixo o bastante pra "caber no quadro" ainda assim conflita com essa UI.
`LEGENDA_MARGIN_V = 520` (27% da altura de 1920px) ficou confirmado por
feedback real depois que `340` (17.7%) não bastou.

## 8. Zoom só de rampa cansa — pulso periódico por cima resolve sem "visão"

Zoom monotônico único (1.0 → `ZOOM_FINAL` do início ao fim do clipe) foi
sentido como "sem uns zoom in" pelo Felipe. Em vez de tentar detectar ONDE
enfatizar (isso pediria análise de conteúdo/áudio, fora do escopo
determinístico desta esteira), a rampa de base ganhou um pulso periódico
(seno, ~3.5s de período, só soma — nunca reduz abaixo da rampa) por cima —
dá uns "zoom in" leves e rítmicos sem precisar saber o que está sendo dito.

## 9. Link de share saindo com hostname interno

`routes/shares.py` montava a URL pública com `request.host_url` — que
reflete o Host de quem chamou a API. Quando quem chama é o `media_worker`
(via `sdk_client.evo`, hostname interno do service mesh), o link sai como
`http://evonexus-dashboard:8080/share/...`, que não abre em lugar nenhum
fora da rede Swarm. `NEXUS_PUBLIC_URL` já estava documentado em
`.env.example` pra esse cenário exato e já setado certo na VPS — só nunca
tinha sido lido pelo código. `_public_base_url()` agora prioriza
`NEXUS_PUBLIC_URL`/`NGROK_URL` sobre `request.host_url`.

## 10. Vídeo publicado via share funciona direto em `<video src>`

`routes/shares.py::view_share` já serve `.mp4`/`.webm`/etc. com
`Content-Type: video/mp4` de verdade (`_VIDEO_EXTS`) — a URL
`{NEXUS_PUBLIC_URL}/api/shares/{token}/view` pode ir direto num
`<video src="...">` num site externo (sistemabritto.com.br, por exemplo)
sem precisar de proxy nem de baixar o arquivo pra outro lugar. `<video>` sem
`crossorigin` não é bloqueado pelo CORS restrito da resposta (que autoriza
só a própria origem do Nexus) — CORS de elemento `<video>` só entra em jogo
se o JS tentar ler os frames via canvas/WebGL, não pra playback simples.

## 11. O front-end pode ficar dessincronizado de um back-end que ficou seguro

`sistemabritto/site`'s `pages/api/otp/send.ts` e `verify.ts` foram
reescritos em 29/07/2026 pra seguir o checklist de `otp-whatsapp.md`
(rate limit, TTL, tentativas, uso único). `pages/login.tsx`, o único
consumidor existente, nunca foi atualizado — continuava comparando o
código digitado contra `data.otp` da resposta de `/send`, campo que o
endpoint novo (corretamente) parou de devolver. Login por WhatsApp ficou
**quebrado silenciosamente** desde então: todo código digitado comparava
contra `undefined` e sempre falhava, sem nenhum log de erro do lado do
servidor (o servidor respondia certo, só o cliente nunca chamava
`/api/otp/verify`). Lição: blindar um endpoint não é o fim do trabalho —
todo consumidor existente precisa ser conferido contra o novo contrato.

## Página de vídeo com OTP (`sistemabritto/site`)

`pages/call-sobrevivencia-pos-ia.tsx` — gate de WhatsApp OTP reaproveitando
`/api/otp/send` + `/api/otp/verify` (já existentes e seguros) na frente de
um `<video>` apontando pro share do Nexus. Ao verificar, chama `/api/leads`
(best-effort — falha aí não pode travar quem já provou o número) que cria
lead no Supabase + deal no EvoCRM (`pipeline_id`/`stage_id` fixos em
`pages/api/leads.ts`, reaproveitável por qualquer funil novo, `source`
identifica de onde veio).

Envio do código do OTP usa a instância WhatsApp declarada em `EVO_INSTANCE`
(env var da Vercel) — checar contra `GET /instance/all` na Evolution Go
(`go.workflowapi.com.br`) se o remetente parecer errado; instância certa
pro Sistema Britto é `sistema-britto` (jid `5511914088571`), não `felipe`.

## Regras relacionadas

- `esteira-de-conteudo.md` — mesmo princípio "modelo só onde há julgamento",
  aplicado ao blog/redes em vez de vídeo
- `artifacts.md` — vídeo/relatório pro humano vai pro Nexus (`/shares`)
- `otp-whatsapp.md` — checklist de segurança que `pages/api/otp/*.ts` segue
