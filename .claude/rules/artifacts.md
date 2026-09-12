# Artefatos — onde entregar relatório, análise e documento visual

**Regra:** todo artefato entregável ao Felipe é publicado no **próprio Nexus**,
via `/api/shares`, e aparece em `https://nexus.workflowapi.com.br/shares`.
Nunca em artefato do Claude Code, nunca em serviço externo.

**Por quê:** o OmniNexus é o produto. Um relatório hospedado fora dele é um
relatório que o Felipe não controla, não versiona, não consegue mostrar a
cliente e some quando a sessão morre. Dentro do Nexus ele tem link estável,
lista em `/shares`, revogação, expiração opcional e fica no volume de workspace
junto do resto do trabalho.

## Como publicar

```python
from dashboard.backend.sdk_client import evo

# 1. o arquivo precisa existir DENTRO do workspace (é o que a API aceita)
caminho = "workspace/reports/[C]nome-do-relatorio-2026-07-25.html"

# 2. cria o share
share = evo.post("/api/shares", {
    "path": caminho,
    "expires_in": None,        # "1h" | "24h" | "7d" | "30d" | None (sem expirar)
})
print(share["url"])            # https://nexus.workflowapi.com.br/share/<token>
```

| Endpoint | Para quê |
|---|---|
| `POST /api/shares` | cria o link (exige `workspace:manage`) |
| `GET /api/shares` | lista os ativos |
| `GET /api/shares/by-path` | achar share existente de um arquivo — use antes de criar outro |
| `DELETE /api/shares/{token}` | revoga |
| `GET /api/shares/{token}/view` | serve o conteúdo (é o que o `/share/<token>` renderiza) |

**Antes de criar um share novo**, consulte `GET /api/shares/by-path` — republicar
o mesmo arquivo gera link novo e o antigo que você já mandou no Telegram vira
lixo. Atualize o arquivo no lugar e o link existente passa a servir a versão nova.

## Onde os arquivos moram

| Tipo | Pasta |
|---|---|
| Relatório de execução, status, pós-incidente | `workspace/reports/` |
| Análise de conteúdo, calendário, research | `workspace/social/` |
| Estratégia, plano, OKR | `workspace/strategy/` |
| Artefato de feature (PRD, verificação, retro) | `workspace/development/features/{slug}/` |

Prefixo `[C]` em tudo que o agente criou, como no resto do workspace.

## Como o HTML deve ser

O share serve o arquivo cru, então ele precisa se bastar:

- **Um arquivo só.** CSS inline no `<style>`, sem CDN, sem fonte externa —
  a página é servida com headers de segurança restritivos e requisição externa
  falha calada.
- **Tema claro e escuro.** Tokens CSS em `:root`, redefinidos em
  `@media (prefers-color-scheme: dark)`. O Felipe abre no celular e no desktop.
- **Rolagem lateral só onde precisa.** Tabela e bloco de código dentro de um
  container com `overflow-x: auto`; o `body` nunca rola de lado.
- **Sem lorem, sem número inventado.** Vale a mesma regra do briefing de marca:
  dado real com origem, ou nenhum dado.
- Fonte do sistema resolve. Monoespaçada é a escolha certa para identificador,
  hash, nome de serviço e variável de ambiente — é o vernáculo do assunto.

## CTA com rastreio de clique

O share serve o HTML com `Content-Security-Policy: default-src 'none'`
(defesa contra prompt injection lendo a sessão do superadmin) — **nenhum
JavaScript roda**, então `fetch()` de tracking embutido no artefato é
bloqueado de propósito, sem exceção.

Se o artefato tem CTA e o clique precisa ser medido, o botão vira um
`<a href>` puro apontando pra `/api/shares/<token>/click` em vez do destino
direto:

```html
<a href="https://nexus.workflowapi.com.br/api/shares/<TOKEN>/click?to=<URL-ENCODED>&label=<rotulo>"
   target="_blank" rel="noopener">Texto do CTA</a>
```

A rota registra o clique (`ShareEvent`) e devolve `302` pro destino real —
zero script, zero CSP pra afrouxar. `to` só aceita host num allowlist fixo em
`routes/shares.py::_CLICK_REDIRECT_ALLOWED_HOSTS`; domínio novo precisa ser
adicionado lá antes de funcionar. Use sempre a URL absoluta do share
(`https://nexus.workflowapi.com.br/...`), nunca relativa.

O resultado aparece em `/shares` no Nexus, coluna "Cliques (conversão)", ao
lado de "Visualizações" — não precisa consultar API na mão. Ver
`memory/rastreio-de-clique-em-artefato-share.md` para os dois erros que já
custaram um deploy quebrado cada (URL relativa, e o gate de autenticação
global de `app.py` tendo sua própria lista de caminhos públicos, separada do
decorator da rota).

## Um share por canal — nunca reaproveite a mesma URL entre campanhas

A UTM do CTA (`to=...`) é escrita no arquivo em tempo de publicação — a CSP
mata todo JavaScript, então não existe leitura de referrer nem de query string
de entrada pra montar a UTM de saída dinamicamente. Ela nasce fixa no HTML.

Isso significa: **reaproveitar o mesmo token de share em dois canais diferentes
mistura a atribuição dos dois**, silenciosamente. Aconteceu em 12/09/2026 —
`[C]guia-ser-mencionado-por-ia-v2.html` já rodava com `utm_source=instagram`
(105 views, cliques reais registrados) quando surgiu a necessidade de mandar o
mesmo guia por um disparo de WhatsApp. Mandar o link de sempre teria feito
todo clique do WhatsApp contar como Instagram no painel de crescimento — o
mesmo tipo de erro que `medicao-de-crescimento.md` já documentou pra outros
pontos do funil.

**A regra:** cada canal/campanha que usa o mesmo conteúdo ganha seu **próprio
arquivo e seu próprio share**, com a UTM do canal já embutida nos CTAs:

1. Copie o HTML pra um novo caminho (`[C]nome-do-guia-<canal>.html`) — nunca
   escreva por cima do arquivo original, ele continua servindo o canal antigo.
2. Nos `href` de clique, troque só os pares de UTM (`utm_source`, `utm_medium`,
   `utm_campaign`) pelos do canal novo; mantenha `utm_content` se o ativo
   (o guia/isca) é o mesmo — é isso que permite comparar depois "o mesmo
   material converteu melhor vindo de onde".
3. `POST /api/shares` com o caminho novo → token novo.
4. **O self-link tem uma dependência circular**: os `href` de clique do
   próprio arquivo apontam pro token do PRÓPRIO share
   (`/api/shares/<TOKEN>/click?...`), e o token só existe depois do passo 3.
   Publique primeiro com um placeholder óbvio no lugar do token
   (`__TOKEN_PLACEHOLDER__`), crie o share, pegue o token de volta, faça
   `sed`/substituição no arquivo trocando o placeholder pelo token real, e
   sobrescreva o mesmo caminho — o share serve o arquivo ao vivo, não tira
   snapshot no `POST`, então essa segunda escrita já atualiza o link existente
   sem precisar de outro `POST`.
5. Confirme os dois pontos antes de considerar pronto: `GET .../view` devolve
   200, e `GET .../click?to=...` devolve `302` com o `Location` já carregando
   a UTM do canal novo (não a do original).

## Material com marca própria — o pageview precisa cair no painel único

Quando um share vai ser divulgado publicamente (isca de tráfego pago/orgânico,
material de campanha), expor `nexus.workflowapi.com.br` na barra de endereço
do lead é errado duas vezes: mostra a ferramenta interna em vez da marca, e
qualquer medição de visita fica presa no `/shares` do Nexus — um painel que
ninguém confere no dia a dia — em vez do painel único de crescimento (`/admin`
do site, mesma tabela `pageviews` que todo o resto do funil usa).

**Achado ao vivo em 12/09/2026:** um `rewrite` puro do `next.config.js`
apontando direto pro domínio do Nexus resolve a barra de endereço, mas é
proxy cego — a página nunca passa pelo `_app.tsx` do site (é quem chama
`/api/track` em toda navegação normal), então a visita simplesmente não é
medida em lugar nenhum que alguém olhe.

**A correção, e o padrão pra replicar em qualquer guia novo** (ver
`sistemabritto/site`, `pages/api/guia-ia-proxy.ts` + `next.config.js`):

1. `next.config.js` reescreve o path público (`/guia-x`) pra uma rota
   **interna** da API do site (`/api/guia-x-proxy`), nunca direto pro domínio
   externo — só passando pelo nosso próprio código dá pra fazer o passo 2.
2. Essa rota de API busca o conteúdo do share no servidor (`fetch` do
   `/api/shares/<token>/view`), grava um pageview em `pageviews` (mesmos
   campos que `pages/api/track.ts` usa: `session_id`, `path`, `referrer`,
   `utm_*`) lendo a UTM da querystring de entrada, e só depois devolve o
   HTML. A gravação é best-effort — falhar em medir nunca pode impedir o
   lead de ler o material.
3. **Repasse o header `Content-Security-Policy` da resposta do Nexus.** Um
   proxy que só copia o corpo e ignora os headers perde essa defesa — o share
   existe justamente pra bloquear todo JS (inclusive prompt injection lendo a
   sessão do superadmin). `upstream.headers.get('content-security-policy')` →
   `res.setHeader(...)`.
4. Sem `session_id` persistente entre páginas (a página não roda JS, não tem
   `sessionStorage`) — cada visita gera o próprio `session_id` só pra
   satisfazer o schema. O clique dentro do guia continua medido à parte, pelo
   `/api/shares/<token>/click` do Nexus — não duplica esse tracking, só fecha
   o buraco do lado do pageview.

## Quando NÃO usar share

- Conteúdo que vai para o blog → Ghost (`custom-int-ghost`).
- Conteúdo que vai para rede social → Postiz (`social-schedule-postiz`).
- Nota interna que ninguém vai abrir no navegador → markdown no workspace, sem
  share. Share é para o que se lê como página.

## Regras relacionadas

- `integrations.md` — Ghost, Postiz e o resto das integrações
- `dev-phases.md` — onde os artefatos de cada fase moram
